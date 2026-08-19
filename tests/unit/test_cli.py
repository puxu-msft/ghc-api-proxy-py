from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
import typer.rich_utils
import yaml
from typer.testing import CliRunner

from app.cli import app, serve_inherited
from app.config.schema import ProxyConfig
from app.lifecycle.entry import StandaloneOptions

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
        "--account-type",
        "--ghc-api-base-url",
        "--rate-limit",
        "--history",
        "--github-token",
        "--proxy",
        "--config",
        "--manual",
        "--generate-config",
    ):
        assert option in result.stdout


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


def test_start_generates_config_and_exits(tmp_path: Path) -> None:
    """What is generated must be a config the service can actually start from.

    Asserting on one key would only prove a file was written; validating it proves the generated
    shape is the one the loader accepts, which is the reason to generate it at all.
    """
    config_path = tmp_path / "generated.yaml"

    result = runner.invoke(
        app,
        ["start", "--config", str(config_path), "--generate-config"],
    )

    assert result.exit_code == 0
    assert config_path.is_file()
    assert str(config_path) in result.stdout

    generated = ProxyConfig.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    # Without a provider the catalog is empty and routing refuses every request.
    assert generated.default_model_provider in generated.model_providers


def test_start_merges_cli_overrides_and_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI options must reach both the settings and the server that binds the listener.

    The target moved from `uvicorn.run` to `app.lifecycle`, which owns the listener and the
    escalating shutdown. The guarded invariant is unchanged: these options must arrive.
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

    The docstring this replaces said `--fd` kept the old behaviour until the user answered whether
    lifecycle.md's escalating shutdown governs the systemd path. Answered 2026-08-19: switch it.
    Uvicorn keeps the listener here because systemd owns it, which is what makes the escalating
    ladder — written for the section that owns its own listener — not apply.
    """
    run = Mock()
    monkeypatch.setattr("app.cli.run", run)

    result = runner.invoke(app, ["start", "--fd", "3"])

    assert result.exit_code == 0, result.output
    served = run.call_args.args[0]
    # The whole point: the same helper, so the same chain. `--port` cannot be asserted alongside
    # `--fd` — they are mutually exclusive, because the listener belongs to systemd here.
    assert served.func is serve_inherited
    assert served.args[1] == 3
    assert isinstance(served.args[0], ProxyConfig)


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
    assert "--fd cannot be combined with --host or --port" in result.output
    run.assert_not_called()


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

    Everything else about TLS is exercised against real sockets, but those tests build
    `StandaloneOptions` directly. Nothing between the config file and that object was checked, and
    a listener that quietly serves plaintext for a `mode: both` config looks entirely healthy.
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
