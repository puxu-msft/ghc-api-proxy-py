from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from typer.testing import CliRunner

from app.cli import app

runner = CliRunner(env={"COLUMNS": "200"})


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
        ["start", "--port", "4242", "--host", "0.0.0.0", "--manual", "--verbose"],
    )

    assert result.exit_code == 0
    application = run.call_args.args[0]
    assert application.state.runtime.settings.port == 4242
    assert application.state.runtime.settings.host == "0.0.0.0"
    assert application.state.runtime.settings.approval.enabled is True
    assert application.state.runtime.settings.observability.log_level == "DEBUG"
    run.assert_called_once_with(application, host="0.0.0.0", port=4242, log_config=None)


def test_logout_clears_stored_token(monkeypatch: pytest.MonkeyPatch) -> None:
    clear = AsyncMock()
    monkeypatch.setattr("app.cli.clear_stored_token", clear)

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0
    assert "removed" in result.stdout.lower()
    clear.assert_awaited_once()