from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer


class AccountType(StrEnum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


app = typer.Typer(
    name="ghc-api-proxy",
    help="High-performance multi-protocol GitHub Copilot API proxy.",
    no_args_is_help=True,
)
debug_app = typer.Typer(help="Inspect local and upstream proxy state.", no_args_is_help=True)
app.add_typer(debug_app, name="debug")


def _not_implemented(command: str) -> None:
    typer.echo(f"{command} is not implemented yet")


@app.command()
def start(
    port: Annotated[int | None, typer.Option("--port", "-p", min=1, max=65535)] = None,
    host: Annotated[str | None, typer.Option("--host", "-H")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    account_type: Annotated[
        AccountType | None,
        typer.Option("--account-type", "-a", case_sensitive=False),
    ] = None,
    ghc_api_base_url: Annotated[str | None, typer.Option("--ghc-api-base-url")] = None,
    rate_limit: Annotated[bool | None, typer.Option("--rate-limit/--no-rate-limit")] = None,
    history: Annotated[bool | None, typer.Option("--history/--no-history")] = None,
    github_token: Annotated[str | None, typer.Option("--github-token", "-g")] = None,
    proxy: Annotated[str | None, typer.Option("--proxy")] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", exists=False, file_okay=True, dir_okay=False),
    ] = None,
    manual: Annotated[bool, typer.Option("--manual")] = False,
    generate_config: Annotated[bool, typer.Option("--generate-config")] = False,
) -> None:
    """Start the API proxy server."""
    del (
        port,
        host,
        verbose,
        account_type,
        ghc_api_base_url,
        rate_limit,
        history,
        github_token,
        proxy,
        config,
        manual,
        generate_config,
    )
    _not_implemented("start")


def _authenticate() -> None:
    _not_implemented("auth")


@app.command("auth")
def auth() -> None:
    """Authenticate with GitHub Copilot."""
    _authenticate()


@app.command("login", hidden=False)
def login() -> None:
    """Alias for auth."""
    _authenticate()


@app.command()
def logout() -> None:
    """Remove locally stored authentication state."""
    _not_implemented("logout")


@app.command("setup-claude-code")
def setup_claude_code() -> None:
    """Configure Claude Code to use this proxy."""
    _not_implemented("setup-claude-code")


@app.command("setup-codex")
def setup_codex() -> None:
    """Configure Codex to use this proxy."""
    _not_implemented("setup-codex")


@app.command("list-claude-code")
def list_claude_code() -> None:
    """List detected Claude Code installations."""
    _not_implemented("list-claude-code")


@debug_app.command("info")
def debug_info() -> None:
    """Show proxy environment information."""
    _not_implemented("debug info")


@debug_app.command("models")
def debug_models() -> None:
    """Show upstream model information."""
    _not_implemented("debug models")


@debug_app.command("usage")
def debug_usage() -> None:
    """Show Copilot usage information."""
    _not_implemented("debug usage")


def main() -> None:
    app()