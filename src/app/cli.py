from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from anyio import run

from app.auth.service import authenticate_device, clear_stored_token
from app.config.loading import bundled_config_text, load_proxy_config
from app.config.paths import config_file_path, tls_material_dir
from app.config.schema import ProxyConfig
from app.lifecycle.entry import StandaloneOptions, run_standalone
from app.lifecycle.standalone import LIFECYCLE_LOGGER, ShutdownReport
from app.observability.logging import get_logger, setup_logging
from app.server.composition import build_chain, build_http_client
from app.server.pipeline_app import create_pipeline_app
from app.server.tls import resolve_tls_material


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


def _write_default_config(path: Path) -> None:
    """Write a starting config in the shape the spec defines.

    A copy of the shipped file rather than a dump of the schema defaults: dumping every default
    would produce hundreds of lines the operator did not choose and would then have to maintain,
    and it would freeze today's defaults into their file, where a later change to a default would
    silently not reach them.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundled_config_text(), encoding="utf-8")


def _generate_config(path: Path) -> None:
    _write_default_config(path)



# Options the old `AppSettings` served that the spec's `ProxyConfig` has nowhere to put. The user
# ruled on 2026-08-17 that the entry switch goes ahead with these inactive; naming each one and why
# is what keeps "temporarily inactive" from turning into "quietly gone".
_NO_HOME_IN_SPEC: dict[str, str] = {
    "--manual": "config.example.yaml has no `approval` section",
    "--rate-limit/--no-rate-limit": "the spec's `reactive_rate_limiter` has no `enabled` field",
    "--github-token": "the spec takes `model_providers.<name>.github_token_file`, not a token",
    "--account-type": "config.example.yaml has no `auth` section",
}


def _load_spec_config(
    *,
    config_path: Path | None,
    port: int | None,
    host: str | None,
    graceful_timeout: int | None,
    proxy: str | None,
    history: bool | None,
    ghc_api_base_url: str | None,
    verbose: bool,
    manual: bool,
    rate_limit: bool | None,
    github_token: str | None,
    account_type: AccountType | None,
) -> tuple[ProxyConfig, list[tuple[str, str]]]:
    """Read the spec's config and report which CLI options it cannot carry."""
    server: dict[str, object] = {}
    if port is not None:
        server["port"] = port
    if host is not None:
        server["host"] = host

    overrides: dict[str, object] = {}
    if server:
        overrides["server"] = server
    if graceful_timeout is not None:
        overrides["graceful_cleanup_timeout"] = graceful_timeout
    if proxy is not None:
        overrides["proxy"] = proxy
    if history is not None:
        overrides["history"] = {"enabled": history}

    config = load_proxy_config(config_path=config_path, cli_overrides=overrides)

    inactive: list[tuple[str, str]] = []
    supplied = {
        "--manual": manual,
        "--rate-limit/--no-rate-limit": rate_limit is not None,
        "--github-token": github_token is not None,
        "--account-type": account_type is not None,
    }
    for option, was_given in supplied.items():
        if was_given:
            inactive.append((option, _NO_HOME_IN_SPEC[option]))

    if ghc_api_base_url is not None:
        # Applied after loading rather than as an override: which provider it belongs to is only
        # known once the config names a default.
        name = config.default_model_provider
        providers = dict(config.model_providers)
        if name in providers:
            providers[name] = providers[name].model_copy(update={"base_url": ghc_api_base_url})
            config = config.model_copy(update={"model_providers": providers})
        else:
            inactive.append(
                ("--ghc-api-base-url", f"no provider named {name!r} to apply it to")
            )
    return config, inactive


async def serve_inherited(config: ProxyConfig, fd: int) -> None:
    """Serve the chain on a listener systemd already opened.

    Not `run_standalone`: that owns the listener so it can hand it over, and here systemd does.
    """
    http_client = build_http_client(config)
    try:
        chain = build_chain(config, http_client=http_client)
        server = uvicorn.Server(
            uvicorn.Config(
                create_pipeline_app(chain),
                fd=fd,
                log_config=None,
                timeout_graceful_shutdown=config.graceful_cleanup_timeout,
            )
        )
        await server.serve()
    finally:
        await http_client.aclose()


async def _serve_pipeline(config: ProxyConfig, options: StandaloneOptions) -> None:
    """Build the chain and serve it, closing the outbound client on the way out.

    The client is created here rather than inside `build_chain` because whoever creates it has to
    close it, and the chain is handed to an app that outlives neither.
    """
    http_client = build_http_client(config)
    try:
        chain = build_chain(config, http_client=http_client)
        # Wired here because this is the one scope holding both the chain that owns the display and the server that learns the listener has stopped accepting.
        outcome = await run_standalone(
            create_pipeline_app(chain), options, chain.active_requests.begin_draining
        )
        # `ShutdownReport` says of itself that it exists "so a caller can log it rather than guess", and until now every caller discarded it — the process simply stopped, and whether it drained cleanly or gave up on live requests was unknowable from the terminal.
        report_shutdown(outcome.report)
    finally:
        await http_client.aclose()


def _plural(count: int, noun: str) -> str:
    """`1 request` / `2 requests`. A count that reads as broken English reads as a broken program."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def report_shutdown(report: ShutdownReport) -> None:
    """The last line the process writes: what the shutdown actually did.

    Ordered by what an operator is deciding — whether anything was cut off, and whether cleanup finished. A clean drain says so in one short line; anything else names the count, because "2 requests cancelled" is the difference between a restart that was safe and one that was not.
    """
    parts: list[str] = []
    if report.interrupted_connections:
        parts.append(f"{_plural(report.interrupted_connections, 'connection')} interrupted")
    if report.cancelled_requests:
        parts.append(f"{_plural(report.cancelled_requests, 'request')} cancelled")
    if report.cleanup_timed_out:
        parts.append("cleanup exceeded its budget")
    if report.cleanup_error:
        parts.append(f"cleanup failed: {report.cleanup_error}")
    detail = f" — {', '.join(parts)}" if parts else ""
    clean = not parts and report.cleanup_completed
    get_logger(LIFECYCLE_LOGGER).info(f"stopped{detail}", status="ok" if clean else "fail")


@app.command()
def start(
    port: Annotated[int | None, typer.Option("--port", "-p", min=1, max=65535)] = None,
    host: Annotated[str | None, typer.Option("--host", "-H")] = None,
    fd: Annotated[int | None, typer.Option("--fd", min=1)] = None,
    graceful_timeout: Annotated[
        int | None,
        typer.Option("--graceful-timeout", min=1),
    ] = None,
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
    restart: Annotated[bool, typer.Option("--restart")] = False,
    pidfile: Annotated[Path | None, typer.Option("--pidfile")] = None,
) -> None:
    """Start the API proxy server."""
    if generate_config:
        output_path = config or config_file_path()
        _generate_config(output_path)
        typer.echo(f"Generated configuration: {output_path}")
        return

    if fd is not None and (host is not None or port is not None):
        raise typer.BadParameter("--fd cannot be combined with --host or --port")

    # Before anything that might log. Both serve paths hand uvicorn `log_config=None`, so nothing else installs a handler and, without this call, every line the process produces — its own and uvicorn's — is dropped by the root logger's default level and never reaches the terminal at all.
    setup_logging(log_format="text", log_level="DEBUG" if verbose else "INFO")

    cli_overrides: dict[str, object] = {}
    auth_overrides: dict[str, object] = {}
    upstream_overrides: dict[str, object] = {}
    if port is not None:
        cli_overrides["port"] = port
    if host is not None:
        cli_overrides["host"] = host
    if graceful_timeout is not None:
        cli_overrides["shutdown"] = {"graceful_timeout": graceful_timeout}
    if account_type is not None:
        auth_overrides["account_type"] = account_type.value
    if ghc_api_base_url is not None:
        upstream_overrides["ghc_api_base_url"] = ghc_api_base_url
    if rate_limit is not None:
        cli_overrides["rate_limiter"] = {"enabled": rate_limit}
    if history is not None:
        cli_overrides["history"] = {"enabled": history}
    if github_token is not None:
        auth_overrides["github_token"] = github_token
    if proxy is not None:
        upstream_overrides["proxy"] = proxy
    if manual:
        cli_overrides["approval"] = {"enabled": True}
    if verbose:
        cli_overrides["observability"] = {"log_level": "DEBUG"}
    if auth_overrides:
        cli_overrides["auth"] = auth_overrides
    if upstream_overrides:
        cli_overrides["upstream"] = upstream_overrides

    if fd is not None:
        # An inherited listener means systemd owns it, so uvicorn may keep it: lifecycle.md's
        # escalating shutdown is written for the stand-alone section, which owns its own listener.
        # What this path serves is no longer the difference — it is the same chain `start` serves.
        # Ruled 2026-08-19; what the existing chain offered and this one does not is inventoried
        # in `docs/agents/anthropic-responses-bridge/implementation.md`.
        proxy_config, _ = _load_spec_config(
            config_path=config,
            port=port,
            host=host,
            graceful_timeout=graceful_timeout,
            proxy=proxy,
            history=history,
            ghc_api_base_url=ghc_api_base_url,
            verbose=verbose,
            manual=manual,
            rate_limit=rate_limit,
            github_token=github_token,
            account_type=account_type,
        )
        run(partial(serve_inherited, proxy_config, fd))
        return

    proxy_config, inactive = _load_spec_config(
        config_path=config,
        port=port,
        host=host,
        graceful_timeout=graceful_timeout,
        proxy=proxy,
        history=history,
        ghc_api_base_url=ghc_api_base_url,
        verbose=verbose,
        manual=manual,
        rate_limit=rate_limit,
        github_token=github_token,
        account_type=account_type,
    )
    for option, reason in inactive:
        # Said out loud rather than dropped: an option that is accepted and then ignored is worse
        # than one that is refused, because nothing distinguishes it from having worked.
        typer.echo(f"warning: {option} has no effect on this path — {reason}", err=True)

    # Served through app.lifecycle rather than uvicorn.run: the escalating shutdown and the
    # SO_REUSEPORT handover both need to own the listener, which uvicorn.run does not give up.
    options = StandaloneOptions(
        host=proxy_config.server.host,
        port=proxy_config.server.port,
        tls_mode=proxy_config.server.tls.mode,
        # None for an HTTP-only deployment, so a listener cannot be built with TLS it has no
        # material for; generated once and reused when the operator named no cert.
        tls_material=resolve_tls_material(proxy_config, tls_dir=tls_material_dir()),
        cleanup_timeout=proxy_config.graceful_cleanup_timeout,
        pidfile=pidfile,
        restart=restart,
    )
    run(partial(_serve_pipeline, proxy_config, options))


def _authenticate() -> None:
    def notify(verification_uri: str, user_code: str) -> None:
        typer.echo(f"Visit {verification_uri} and enter code {user_code}")

    run(authenticate_device, notify)


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
    run(clear_stored_token)
    typer.echo("Stored GitHub token removed")


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
