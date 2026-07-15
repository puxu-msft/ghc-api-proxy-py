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
    auth_result = runner.invoke(app, ["auth"])
    login_result = runner.invoke(app, ["login"])

    assert auth_result.exit_code == 0
    assert login_result.exit_code == 0
    assert auth_result.stdout == login_result.stdout


def test_debug_subcommands_exist() -> None:
    result = runner.invoke(app, ["debug", "--help"])

    assert result.exit_code == 0
    assert "info" in result.stdout
    assert "models" in result.stdout
    assert "usage" in result.stdout