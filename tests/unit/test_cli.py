from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
import typer.rich_utils
import yaml
from typer.testing import CliRunner

from app.cli import app
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
        "start-rolling",
        "rolling-controller",
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


def test_start_rolling_exposes_only_config_option() -> None:
    result = runner.invoke(app, ["start-rolling", "--help"])

    assert result.exit_code == 0
    assert "--config" in result.stdout
    assert "--generation-id" in result.stdout
    assert "--release-id" in result.stdout
    assert "--control-socket" in result.stdout
    assert "--host" not in result.stdout
    assert "--port" not in result.stdout
    assert "--fd" not in result.stdout


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

    # --manual and --verbose have nowhere to land in the spec's schema. The user ruled that the
    # switch proceeds with them inactive, so what is guarded is that they are said out loud.
    assert "--manual has no effect" in result.output
    assert "--verbose has no effect" in result.output


def test_start_passes_inherited_socket_fd_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    """An inherited listener stays on the pre-existing path.

    lifecycle.md writes the escalating shutdown for the stand-alone section, and whether it also
    governs the systemd path is an open question for the user. Until it is answered, `--fd` keeps
    the behaviour the systemd units already rely on.
    """
    uvicorn_run = Mock()
    standalone = Mock()
    monkeypatch.setattr("app.cli.uvicorn.run", uvicorn_run)
    monkeypatch.setattr("app.cli.run_standalone", standalone)

    result = runner.invoke(app, ["start", "--fd", "3"])

    assert result.exit_code == 0
    application = uvicorn_run.call_args.args[0]
    assert application.state.runtime.settings.host == "127.0.0.1"
    assert application.state.runtime.settings.port == 4141
    uvicorn_run.assert_called_once_with(
        application,
        fd=3,
        log_config=None,
        timeout_graceful_shutdown=300,
    )
    standalone.assert_not_called()


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


def test_start_rolling_uses_systemd_generation_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_runner = AsyncMock()
    standalone = Mock()
    monkeypatch.setattr("app.cli.run_systemd_generation", generation_runner)
    # Not `app.cli.run`: this path really has to run its coroutine. What is asserted is that the
    # rolling entry does not go through the stand-alone one.
    monkeypatch.setattr("app.cli.run_standalone", standalone)

    result = runner.invoke(
        app,
        [
            "start-rolling",
            "--generation-id",
            "g0000000000000001",
            "--release-id",
            "release-test",
            "--control-socket",
            "/tmp/ghc-generation-test.sock",
        ],
    )

    assert result.exit_code == 0
    generation_runner.assert_awaited_once()
    assert generation_runner.await_args is not None
    application = generation_runner.await_args.args[0]
    assert application.state.runtime.settings.port == 4141
    assert generation_runner.await_args.kwargs == {
        "generation_id": "g0000000000000001",
        "release_id": "release-test",
        "control_path": Path("/tmp/ghc-generation-test.sock"),
    }
    standalone.assert_not_called()


@pytest.mark.parametrize(
    "generation_id",
    ["g1", "g00000000000000001", "g000000000000000/", " generation"],
)
def test_start_rolling_rejects_noncanonical_generation_id(generation_id: str) -> None:
    result = runner.invoke(
        app,
        [
            "start-rolling",
            "--generation-id",
            generation_id,
            "--release-id",
            "release-test",
            "--control-socket",
            "/tmp/ghc-generation-test.sock",
        ],
    )
    assert result.exit_code == 2
    assert "generation id" in result.output.lower()


def test_start_rolling_rejects_relative_control_path() -> None:
    result = runner.invoke(
        app,
        [
            "start-rolling",
            "--generation-id",
            "g0000000000000001",
            "--release-id",
            "release-test",
            "--control-socket",
            "relative.sock",
        ],
    )
    assert result.exit_code == 2
    assert "absolute" in result.output.lower()


def test_rolling_controller_plan_is_dry_run_and_reports_blockers(tmp_path: Path) -> None:
    releases = tmp_path / "releases"
    (releases / "release-a").mkdir(parents=True)
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "rolling-controller",
            "--state-root",
            str(tmp_path / "state"),
            "--runtime-root",
            str(tmp_path / "run"),
            "--releases-root",
            str(releases),
            "--config",
            str(config),
            "--plan-release",
            "release-a",
        ],
    )

    assert result.exit_code == 0
    assert '"apply_enabled": false' in result.stdout
    assert "missing_private_canary_command" in result.stdout
    assert not (tmp_path / "state" / "frontier").exists()


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