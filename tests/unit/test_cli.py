from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import typer.rich_utils
from typer.testing import CliRunner

from app.cli import app

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
    config_path = tmp_path / "generated.yaml"

    result = runner.invoke(
        app,
        ["start", "--config", str(config_path), "--generate-config"],
    )

    assert result.exit_code == 0
    assert config_path.is_file()
    assert "port: 4141" in config_path.read_text(encoding="utf-8")
    assert str(config_path) in result.stdout


def test_start_merges_cli_overrides_and_runs_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock()
    monkeypatch.setattr("app.cli.uvicorn.run", run)

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
    application = run.call_args.args[0]
    assert application.state.runtime.settings.port == 4242
    assert application.state.runtime.settings.host == "0.0.0.0"
    assert application.state.runtime.settings.shutdown.graceful_timeout == 7
    assert application.state.runtime.settings.approval.enabled is True
    assert application.state.runtime.settings.observability.log_level == "DEBUG"
    run.assert_called_once_with(
        application,
        host="0.0.0.0",
        port=4242,
        log_config=None,
        timeout_graceful_shutdown=7,
    )


def test_start_passes_inherited_socket_fd_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock()
    monkeypatch.setattr("app.cli.uvicorn.run", run)

    result = runner.invoke(app, ["start", "--fd", "3"])

    assert result.exit_code == 0
    application = run.call_args.args[0]
    assert application.state.runtime.settings.host == "127.0.0.1"
    assert application.state.runtime.settings.port == 4141
    run.assert_called_once_with(
        application,
        fd=3,
        log_config=None,
        timeout_graceful_shutdown=300,
    )


def test_start_rolling_uses_systemd_generation_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_runner = AsyncMock()
    uvicorn_run = Mock()
    monkeypatch.setattr("app.cli.run_systemd_generation", generation_runner)
    monkeypatch.setattr("app.cli.uvicorn.run", uvicorn_run)

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
    uvicorn_run.assert_not_called()


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
    monkeypatch.setattr("app.cli.uvicorn.run", run)

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
    monkeypatch.setattr("app.cli.uvicorn.run", run)

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