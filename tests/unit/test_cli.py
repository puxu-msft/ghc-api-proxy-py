import signal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
import typer.rich_utils
import uvicorn
import yaml
from typer.testing import CliRunner
from uvicorn._types import ASGIReceiveCallable, ASGISendCallable, Scope

from app.cli import app, serve_inherited
from app.config.loading import bundled_config_text
from app.config.schema import ProxyConfig
from app.lifecycle.entry import StandaloneOptions
from app.lifecycle.pidfile import PidfileError

runner = CliRunner()


@pytest.fixture(autouse=True)
def plain_help_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render help as plain, wide text for the assertions in this file only.

    Typer builds its console per call from these module globals.
    Setting them here beats an environment variable: no import-order dependency, no leak elsewhere.

    Left alone, `--port` arrives as two styled runs with an ANSI escape between the dashes.
    Long option names are also truncated at 80 columns.
    Both make an offered option look absent.
    """
    monkeypatch.setattr(typer.rich_utils, "COLOR_SYSTEM", None)
    monkeypatch.setattr(typer.rich_utils, "FORCE_TERMINAL", False)
    monkeypatch.setattr(typer.rich_utils, "MAX_WIDTH", 200)


def served_config(run: Mock) -> ProxyConfig:
    """The configuration handed to the lifecycle runner."""
    return cast(ProxyConfig, run.call_args.args[0].args[0])


def serve_options(run: Mock) -> StandaloneOptions:
    """The options handed to the lifecycle runner."""
    return cast(StandaloneOptions, run.call_args.args[0].args[1])


def test_cli_smoke() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "start",
        "auth",
        "login",
        "logout",
        "gen-config",
        "debug",
        "setup-claude-code",
        "setup-codex",
        "list-claude-code",
    ):
        assert command in result.stdout


def test_start_subcommand_exposes_bootstrap_options() -> None:
    result = runner.invoke(app, ["start", "--help"])

    assert result.exit_code == 0
    for option in (
        "--port",
        "--host",
        "--fd",
        "--graceful-timeout",
        "--verbose",
        "--rate-limit",
        "--history",
        "--github-token",
        "--proxy",
        "--config",
        "--manual",
    ):
        assert option in result.stdout
    # Removed 2026-08-22. It set a field name that had not existed since the rename in a8a7f87, so it silently did nothing; the base URL now comes from `model_providers.<name>.api_base_url` or from probing the subscription.
    # Asserted absent so it cannot drift back in unnoticed.
    assert "--ghc-api-base-url" not in result.stdout
    # Removed 2026-08-22 for the same reason and in the same round: it fed the legacy `AppSettings`, which the served chain does not read, so the served chain could never see it. Its sibling was deleted first and leaving this one behind made the pair inconsistent rather than principled.
    assert "--account-type" not in result.stdout


def test_auth_and_login_are_aliases() -> None:
    with pytest.MonkeyPatch.context() as patch:
        authenticate = AsyncMock()
        patch.setattr("app.cli.authenticate_device", authenticate)
        auth_result = runner.invoke(app, ["auth"])
        login_result = runner.invoke(app, ["login"])

    assert auth_result.exit_code == 0
    assert login_result.exit_code == 0
    assert auth_result.stdout == login_result.stdout
    assert authenticate.await_count == 2


def test_debug_subcommands_exist() -> None:
    result = runner.invoke(app, ["debug", "--help"])

    assert result.exit_code == 0
    assert "info" in result.stdout
    assert "models" in result.stdout
    assert "usage" in result.stdout


def test_gen_config_writes_a_loadable_config(tmp_path: Path) -> None:
    """What is generated must be a config the service can actually start from.

    Asserting on one key would only prove a file was written; validating it proves the generated shape is the one the loader accepts, which is the reason to generate it at all.
    """
    config_path = tmp_path / "nested" / "generated.yaml"

    result = runner.invoke(app, ["gen-config", str(config_path)])

    assert result.exit_code == 0
    assert config_path.is_file()
    assert str(config_path) in result.stdout

    generated = ProxyConfig.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    # Without a provider the catalog is empty and routing refuses every request.
    assert generated.default_model_provider in generated.model_providers


def test_gen_config_requires_a_destination() -> None:
    """The path is the whole argument, so omitting it must fail rather than pick a location.

    The flag this replaced defaulted to `config_file_path()`, which is not where `load_proxy_config` looks; a generated file nobody reads is worse than a usage error.
    """
    result = runner.invoke(app, ["gen-config"])

    assert result.exit_code != 0


def test_gen_config_keeps_an_existing_file_when_the_answer_is_no(tmp_path: Path) -> None:
    """Declining must leave the operator's file byte-for-byte, not merely exit non-zero.

    The exit code alone would still pass if the file had already been truncated on the way to asking, which is the failure this guards: the whole value of the prompt is that the old bytes survive it.
    """
    config_path = tmp_path / "config.yaml"
    theirs = "server:\n  port: 4321\n"
    config_path.write_text(theirs, encoding="utf-8")

    result = runner.invoke(app, ["gen-config", str(config_path)], input="n\n")

    assert result.exit_code != 0
    assert config_path.read_text(encoding="utf-8") == theirs


def test_gen_config_replaces_an_existing_file_when_the_answer_is_yes(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("server:\n  port: 4321\n", encoding="utf-8")

    result = runner.invoke(app, ["gen-config", str(config_path)], input="y\n")

    assert result.exit_code == 0
    assert config_path.read_text(encoding="utf-8") == bundled_config_text()


def test_gen_config_does_not_ask_about_a_path_that_is_free(tmp_path: Path) -> None:
    """No stdin at all, so a prompt here would abort on EOF rather than hang.

    Pinned because the check is `exists()`: a stray prompt on the ordinary first run is the way this lands on someone as a regression.
    """
    config_path = tmp_path / "fresh.yaml"

    result = runner.invoke(app, ["gen-config", str(config_path)])

    assert result.exit_code == 0
    assert config_path.is_file()


def test_start_merges_cli_overrides_and_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI options must reach both the settings and the server that binds the listener.

    The target moved from `uvicorn.run` to `app.lifecycle`, which owns the listener and the escalating shutdown. The guarded invariant is unchanged: these options must arrive.
    """
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(
        app,
        [
            "start",
            "--port",
            "4242",
            "--host",
            "0.0.0.0",
            "--graceful-timeout",
            "7",
            "--manual",
            "--verbose",
        ],
    )

    assert result.exit_code == 0
    config = served_config(run)
    assert config.server.port == 4242
    assert config.server.host == "0.0.0.0"
    assert config.graceful_cleanup_timeout == 7
    options = serve_options(run)
    assert options.host == "0.0.0.0"
    assert options.port == 4242
    assert options.cleanup_timeout == 7
    assert options.fd is None

    # `--manual` has nowhere to land in the spec's schema. The user ruled that the switch proceeds with it inactive, so what is guarded is that it is said out loud.
    assert "--manual has no effect" in result.output
    # `--verbose` was on that list until it acquired a real effect: it now sets the log level, which is what turns on the per-request arrival line. Announcing it as inactive would be the same defect in the opposite direction — a warning that is itself untrue.
    assert "--verbose has no effect" not in result.output


def test_an_inherited_listener_serves_the_same_chain_as_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--fd` used to serve the existing chain while `start` served this one.

    The docstring this replaces said `--fd` kept the old behaviour until the user answered whether lifecycle.md's escalating shutdown governs the systemd path. Answered 2026-08-19: switch it.
    Uvicorn keeps the listener here because systemd owns it, which is what makes the escalating ladder — written for the section that owns its own listener — not apply.
    """
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--fd", "3"])

    assert result.exit_code == 0, result.output
    served = run.call_args.args[0]
    # The whole point: the same helper, so the same chain. `--port` cannot be asserted alongside `--fd` — they are mutually exclusive, because the listener belongs to systemd here.
    assert served.func is serve_inherited
    assert served.args[1] == 3
    assert isinstance(served.args[0], ProxyConfig)


def test_the_systemd_path_says_when_it_stops_accepting() -> None:
    """Under systemd the listener is uvicorn's, so nothing in this process learns a drain has begun unless this class tells it.

    That was the state until 2026-08-22: `begin_draining` was wired only on the stand-alone path, which owns its own listener. On the deployment target the flag stayed false for the whole shutdown, and the retry paths — which refuse to open a new upstream request during a drain — could not see one.

    Asserted through `handle_exit` because that is what uvicorn installs as its signal handler, and the flag has to be true for the whole drain rather than at the end of it.
    """
    from app.cli import _DrainAnnouncingServer  # pyright: ignore[reportPrivateUsage]

    async def never_called(
        scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        """Uvicorn wants an application to build a `Config` around. Nothing here serves a request."""
        raise AssertionError("the app is never invoked by this test")

    announced: list[int] = []
    server = _DrainAnnouncingServer(
        uvicorn.Config(never_called),
        on_draining=lambda: announced.append(1),
    )

    server.handle_exit(signal.SIGTERM, None)

    assert announced == [1]
    # Uvicorn's own bookkeeping still happens: announcing must not replace the shutdown, only precede it.
    assert server.should_exit is True


def test_start_forwards_the_restart_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # --restart is what tells the new process to signal the one it replaces.
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--restart"])

    assert result.exit_code == 0
    assert serve_options(run).restart is True


def test_start_does_not_request_a_restart_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    assert runner.invoke(app, ["start"]).exit_code == 0
    assert serve_options(run).restart is False


def test_start_rejects_stdin_as_inherited_socket_fd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--fd", "0"])

    assert result.exit_code == 2
    assert "Invalid value for '--fd'" in result.output
    run.assert_not_called()


@pytest.mark.parametrize("bind_option", [("--host", "0.0.0.0"), ("--port", "4242")])
def test_start_rejects_fd_with_explicit_bind_option(
    bind_option: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--fd", "3", *bind_option])

    assert result.exit_code == 2
    # Names the option actually given rather than the whole set: the message is built from what conflicted, so an operator who passed one is not left scanning a list for which of them was theirs.
    assert f"--fd cannot be combined with {bind_option[0]}" in result.output
    run.assert_not_called()


@pytest.mark.parametrize(
    "option", [("--manual",), ("--rate-limit",), ("--github-token", "t")]
)
def test_fd_still_reports_the_options_the_config_cannot_carry(
    option: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Warned about, not refused — and the `--fd` path used to do neither.

    These differ from the ones above: they do not contradict an inherited listener, they simply have nowhere to live in `ProxyConfig`, and the project's ruling is that such an option is announced rather than rejected. The inherited-listener branch loaded its own config and threw the second return value away, so on that one path the announcement never happened. Serving still proceeds; that is what makes silence here indistinguishable from the option having worked.
    """
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--fd", "3", *option])

    assert result.exit_code == 0, result.output
    assert option[0] in result.output, result.output
    assert run.called is True, "an inactive option is a warning, not a refusal"


def test_a_refused_start_reports_cleanly_rather_than_as_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal's whole value is the instruction it carries; a traceback buries it.

    `PidfileError` is a `RuntimeError`, and nothing between `run_standalone` and click catches it, so it used to reach the default excepthook: a dozen frames, with `pass --restart to take over from it` at the bottom. Starting twice on one port is an ordinary operator action, not a program failure, and it should not read like one.

    The sharp assertion is the last one. Exit code 1 alone cannot tell the two apart — an unhandled exception produces it too.
    """
    message = "/run/x/standalone-4141.pid still records pid 4242, which is running; pass --restart"

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise PidfileError(message)

    monkeypatch.setattr("app.cli.run", refuse)

    result = runner.invoke(app, ["start"])

    assert result.exit_code == 1
    assert message in result.output, result.output
    assert not isinstance(result.exception, PidfileError), (
        "the refusal escaped unhandled, so the operator sees a traceback"
    )


def test_logout_clears_stored_token(monkeypatch: pytest.MonkeyPatch) -> None:
    clear = AsyncMock()
    monkeypatch.setattr("app.cli.clear_stored_token", clear)

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert "removed" in result.stdout.lower()
    clear.assert_awaited_once()

def test_start_hands_the_configured_tls_mode_to_the_listener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The config's TLS settings have to reach the thing that binds the socket.

    Everything else about TLS is exercised against real sockets, but those tests build `StandaloneOptions` directly. Nothing between the config file and that object was checked, and a listener that quietly serves plaintext for a `mode: both` config looks entirely healthy.
    """
    config = tmp_path / "config.yaml"
    config.write_text(
        "server:\n  port: 4199\n  tls:\n    mode: both\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.cli.tls_material_dir", lambda: tmp_path / "tls")
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--config", str(config)])

    assert result.exit_code == 0
    options = serve_options(run)
    assert options.tls_mode == "both"
    assert options.tls_material is not None, "both mode needs material or it serves plaintext"
    assert options.tls_material.cert_path.is_file()


def test_start_asks_for_no_tls_material_when_the_config_wants_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The negative control: an HTTP-only deployment must not have a key pair minted for it.
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  port: 4199\n", encoding="utf-8")
    monkeypatch.setattr("app.cli.tls_material_dir", lambda: tmp_path / "tls")
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    assert runner.invoke(app, ["start", "--config", str(config)]).exit_code == 0
    options = serve_options(run)
    assert options.tls_mode is False
    assert options.tls_material is None
    assert not (tmp_path / "tls").exists()


def test_the_configured_pidfile_dir_reaches_the_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`config.example.yaml` documents a `pidfile_dir` key, so setting it has to do something.

    It was parsed into `ProxyConfig` and pinned in `NOT_HOT_RELOADABLE`, but nothing ever read it: an operator who set the key got the default directory and no indication that their setting had been dropped.
    """
    config = tmp_path / "config.yaml"
    config.write_text('pidfile_dir: "/run/ghc-api-proxy"\n', encoding="utf-8")
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    assert runner.invoke(app, ["start", "--config", str(config)]).exit_code == 0
    assert serve_options(run).pidfile_dir == Path("/run/ghc-api-proxy")


def test_the_command_line_pidfile_dir_beats_the_configured_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text('pidfile_dir: "/run/ghc-api-proxy"\n', encoding="utf-8")
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(
        app, ["start", "--config", str(config), "--pidfile-dir", str(tmp_path / "typed")]
    )

    assert result.exit_code == 0
    assert serve_options(run).pidfile_dir == tmp_path / "typed"


def test_an_unset_pidfile_dir_is_left_for_the_lifecycle_to_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """None rather than a resolved path, and that is load-bearing.

    The name inside the directory is derived from the port actually bound, which `--fd` never states and port 0 leaves to the kernel. Resolving the location this early would put a guess in the file name.
    """
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    assert runner.invoke(app, ["start"]).exit_code == 0
    assert serve_options(run).pidfile_dir is None


def test_forcing_the_pidfile_is_off_unless_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    assert runner.invoke(app, ["start"]).exit_code == 0
    assert serve_options(run).force_write_pidfile is False

    run.reset_mock()
    assert runner.invoke(app, ["start", "--force-write-pidfile"]).exit_code == 0
    assert serve_options(run).force_write_pidfile is True


@pytest.mark.parametrize(
    "option", ["--restart", "--force-write-pidfile", "--pidfile-dir=/tmp/x"]
)
def test_fd_refuses_the_lifecycle_options_it_cannot_honour(
    option: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused, not reported as inactive.

    systemd owns the listener here: nothing in this process can hand it over or record it, so each of these asks for something that cannot happen on this path. That is what separates them from the ones the next test covers, which are merely homeless in `ProxyConfig` and get a warning. (`--host` and `--port` were already refused; `test_start_rejects_fd_with_explicit_bind_option` keeps that.)
    """
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--fd", "3", option])

    assert result.exit_code != 0
    assert option.split("=")[0] in result.output
    assert run.called is False, "nothing may be served once an option was refused"
