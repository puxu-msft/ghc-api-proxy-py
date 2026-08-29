import os
import socket
from collections.abc import Callable
from functools import partial
from pathlib import Path
from types import FrameType
from typing import Annotated

import typer
import uvicorn
from anyio import run
from yaml import YAMLError

from app.config.loading import GITHUB_TOKEN_VARIABLE, bundled_config_text, load_proxy_config
from app.config.paths import tls_material_dir
from app.config.schema import ProxyConfig
from app.core.chain import Chain
from app.debug.models import collect_catalogs, render_json, render_text
from app.lifecycle.entry import StandaloneOptions, run_standalone
from app.lifecycle.listener import listening_urls
from app.lifecycle.pidfile import PidfileError
from app.lifecycle.standalone import LIFECYCLE_LOGGER, ShutdownReport
from app.lifecycle.tls import resolve_tls_material, serves_tls
from app.model_provider import ProviderNotConfigured
from app.model_provider.ghc_client.auth.providers import FileTokenProvider
from app.model_provider.ghc_client.auth.service import authenticate_device, clear_stored_token
from app.model_provider.ghc_client.config import GhcClientConfig
from app.observability.logging import get_logger, setup_logging
from app.server.composition import (
    build_chain,
    build_http_client,
    github_token_path,
    resolve_provider_base_urls,
)
from app.server.pipeline_app import create_pipeline_app

app = typer.Typer(
    name="ghc-api-proxy",
    help="High-performance multi-protocol GitHub Copilot API proxy.",
    no_args_is_help=True,
)
debug_app = typer.Typer(help="Inspect local and upstream proxy state.", no_args_is_help=True)
app.add_typer(debug_app, name="debug")


def _not_implemented(command: str) -> None:
    typer.echo(f"{command} is not implemented yet")


@app.command("gen-config")
def gen_config(
    out_path: Annotated[
        Path,
        typer.Argument(file_okay=True, dir_okay=False, help="Where to write the generated config."),
    ],
) -> None:
    """Write a starting config in the shape the spec defines.

    A copy of the shipped file rather than a dump of the schema defaults: dumping every default would produce hundreds of lines the operator did not choose and would then have to maintain, and it would freeze today's defaults into their file, where a later change to a default would silently not reach them.

    Its own command rather than a flag on `start`: as `start --generate-config` it sat among two dozen options that shape how the server runs, then returned before starting one, and the path it wrote came from `--config` — the option that everywhere else means *read this one*. The destination is now said outright, which is also why it has no default: the flag's was `config_file_path()` under `$XDG_CONFIG_HOME`, while `load_proxy_config` reads `spec_config_file_path()` under `$XDG_DATA_HOME`, so generating without a path wrote a file the service would never pick up.

    An existing file is confirmed before it is replaced. The command's whole output is a fixed document, so a second run destroys whatever the operator edited into the first and leaves nothing to recover it from — and the path most worth generating is the one the service actually reads, which is exactly the one most likely to already hold their settings. There is no `--force`: `yes | ghc-api-proxy gen-config <path>` answers it from a script, and declining exits non-zero, so nothing silently proceeds.
    """
    if out_path.exists():
        # Asked before `mkdir`, and before anything is opened for writing: a prompt that has already truncated the file is not a confirmation.
        typer.confirm(f"{out_path} already exists. Replace it?", abort=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(bundled_config_text(), encoding="utf-8")
    typer.echo(f"Generated configuration: {out_path}")



# Options the old `AppSettings` served that the spec's `ProxyConfig` has nowhere to put. The user ruled on 2026-08-17 that the entry switch goes ahead with these inactive; naming each one and why is what keeps "temporarily inactive" from turning into "quietly gone".
_NO_HOME_IN_SPEC: dict[str, str] = {
    "--manual": "config.example.yaml has no `approval` section",
    "--rate-limit/--no-rate-limit": "the spec's `reactive_rate_limiter` has no `enabled` field",
    "--github-token": "the spec takes `model_providers.<name>.github_token_file`, not a token",
}


def _load_spec_config(
    *,
    config_path: Path | None,
    port: int | None,
    host: str | None,
    graceful_timeout: int | None,
    proxy: str | None,
    history: bool | None,
    verbose: bool,
    manual: bool,
    rate_limit: bool | None,
    github_token: str | None,
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
    }
    for option, was_given in supplied.items():
        if was_given:
            inactive.append((option, _NO_HOME_IN_SPEC[option]))

    return config, inactive


class _DrainAnnouncingServer(uvicorn.Server):
    """Uvicorn, plus one line saying the listener has stopped accepting.

    The stand-alone path gets this for free: it owns its listener, so it knows the moment accepting stops and hands `begin_draining` down (`_serve_pipeline`). Under systemd the listener is uvicorn's, and until this class existed nothing on that path ever set the flag — so the footer never showed a drain, and, more consequentially, the retry paths could not tell a shutdown from ordinary running and would open a fresh upstream request in the middle of one.

    `handle_exit` rather than a lifespan hook, because the flag has to be true for the whole drain and `shutdown` runs at the end of it. Uvicorn calls this from its own signal handler; a second signal (force quit) calls it again, which is harmless — `begin_draining` only sets a flag.
    """

    def __init__(self, config: uvicorn.Config, *, on_draining: Callable[[], None]) -> None:
        super().__init__(config)
        self._on_draining = on_draining

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self._on_draining()
        super().handle_exit(sig, frame)


async def serve_inherited(config: ProxyConfig, fd: int, *, proxy_from_cli: bool) -> None:
    """Serve the chain on a listener systemd already opened.

    Not `run_standalone`: that owns the listener so it can hand it over, and here systemd does.

    TLS is handed to uvicorn as a certificate pair rather than built into an adapter. `both` — the shipped default — cannot be honoured here: serving two protocols on one port means inspecting the first byte of each accepted connection before handing it on, and that requires owning the accepts, which on this path uvicorn does. Until this existed the whole `server.tls` section was simply not read, so a socket-activated deployment using the shipped config served plaintext with nothing said about it. Answering HTTPS and saying what was dropped beats answering neither.
    """
    http_client = build_http_client(config, proxy_from_cli=proxy_from_cli)
    chain: Chain | None = None
    try:
        config = await resolve_provider_base_urls(config, http_client=http_client)
        chain = build_chain(config, http_client=http_client, proxy_from_cli=proxy_from_cli)
        # None for an HTTP-only deployment, in which case uvicorn is handed no certificate and serves plaintext exactly as before.
        material = resolve_tls_material(config, tls_dir=tls_material_dir())
        if config.server.tls.mode == "both":
            get_logger(LIFECYCLE_LOGGER).warning(
                "server.tls.mode is `both`, which an inherited listener cannot serve; this listener answers HTTPS only"
            )
        # Read off the socket, not off the config: the address belongs to whoever created it, and on this path that is systemd. `dup` because constructing a `socket` from a raw fd takes ownership of it, and closing that object would take uvicorn's listener with it.
        with socket.socket(fileno=os.dup(fd)) as inherited:
            host, port = inherited.getsockname()[:2]
        # `both` is reported as the HTTPS it actually became, per the warning above; saying `both` here would repeat a promise the previous line just withdrew.
        served_mode = serves_tls(config.server.tls.mode)
        get_logger(LIFECYCLE_LOGGER).info(
            f"listening on {listening_urls(str(host), int(port), served_mode)}", status="ok"
        )
        server = _DrainAnnouncingServer(
            uvicorn.Config(
                create_pipeline_app(chain),
                fd=fd,
                log_config=None,
                timeout_graceful_shutdown=config.graceful_cleanup_timeout,
                # Uvicorn treats `None` here as "no TLS", so an HTTP-only deployment passes through unchanged.
                ssl_certfile=material.cert_path if material is not None else None,
                ssl_keyfile=material.key_path if material is not None else None,
            ),
            on_draining=chain.active_requests.begin_draining,
        )
        await server.serve()
    finally:
        # The chain owns one outbound client per provider and nothing else closes them; `http_client` is this function's, built before the chain existed. Both, in that order, and the chain only if it got as far as being built.
        if chain is not None:
            await chain.aclose()
        await http_client.aclose()


async def _serve_pipeline(config: ProxyConfig, options: StandaloneOptions, *, proxy_from_cli: bool) -> None:
    """Build the chain and serve it, closing the outbound client on the way out.

    The client is created here rather than inside `build_chain` because whoever creates it has to close it, and the chain is handed to an app that outlives neither.
    """
    http_client = build_http_client(config, proxy_from_cli=proxy_from_cli)
    chain: Chain | None = None
    try:
        config = await resolve_provider_base_urls(config, http_client=http_client)
        chain = build_chain(config, http_client=http_client, proxy_from_cli=proxy_from_cli)
        # Wired here because this is the one scope holding both the chain that owns the display and the server that learns the listener has stopped accepting.
        def publish_connections(source: Callable[[], int]) -> None:
            chain.active_requests.connection_count = source

        outcome = await run_standalone(
            create_pipeline_app(chain), options, chain.active_requests.begin_draining, publish_connections
        )
        # `ShutdownReport` says of itself that it exists "so a caller can log it rather than guess", and until now every caller discarded it — the process simply stopped, and whether it drained cleanly or gave up on live requests was unknowable from the terminal.
        report_shutdown(outcome.report)
    finally:
        # Same ownership split as `serve_inherited`: the chain closes the per-provider clients it built, and this function closes the one it built itself.
        if chain is not None:
            await chain.aclose()
        await http_client.aclose()


def report_shutdown(report: ShutdownReport) -> None:
    """The last line the process writes: what the shutdown actually did.

    Ordered so the benign counts come first and anything that cost somebody comes after, because a clean drain then says so in one short line, and "2 requests cancelled" is the difference between a restart that was safe and one that was not.

    Neither count of the first kind makes the line say `fail`. Telling the idle pooled connections to go is what the first rung is *for*, and a request the barrier answered with a 503 got a well-formed "come back shortly" — that is the shutdown working, not failing. Marking either as an incident would report every ordinary restart as one.

    That decision was originally the other way for refusals, and measurement is what changed it. The 503 is the *mild* outcome: the harsh one is a pooled connection closed while the client's next request was already on the wire, which the kernel answers with an RST. `severed_connections` is that case, peeked for before each close, and it ranks above the two beside it because it is the only one that names a client who got nothing.

    **It is a floor, not a total, so `ok` here is not a certificate.** The peek sees one instant; a client that sends later in the drain meets a closed socket and is counted nowhere. Ten clients have been measured going unanswered while this read zero. A `fail` therefore means somebody certainly lost a request; an `ok` means none was caught.

    The noun stays plural at any count. `1 connections` is the reading the count already gives, and branching on it buys a nicety at the cost of a second code path through every line that reports a number — the same trade the footer's connection block settled the same way.
    """
    reported: list[str] = []
    if report.connections_asked_to_close:
        reported.append(f"{report.connections_asked_to_close} connections asked to close")
    if report.refused_requests:
        reported.append(f"{report.refused_requests} requests refused")
    incidents: list[str] = []
    if report.severed_connections:
        incidents.append(f"{report.severed_connections} connections severed with a request already sent")
    if report.interrupted_connections:
        incidents.append(f"{report.interrupted_connections} connections interrupted")
    if report.cancelled_requests:
        incidents.append(f"{report.cancelled_requests} requests cancelled")
    if report.cleanup_timed_out:
        incidents.append("cleanup exceeded its budget")
    if report.cleanup_error:
        incidents.append(f"cleanup failed: {report.cleanup_error}")
    parts = reported + incidents
    detail = f" — {', '.join(parts)}" if parts else ""
    clean = not incidents and report.cleanup_completed
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
    rate_limit: Annotated[bool | None, typer.Option("--rate-limit/--no-rate-limit")] = None,
    history: Annotated[bool | None, typer.Option("--history/--no-history")] = None,
    github_token: Annotated[str | None, typer.Option("--github-token", "-g")] = None,
    proxy: Annotated[str | None, typer.Option("--proxy")] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", exists=False, file_okay=True, dir_okay=False),
    ] = None,
    manual: Annotated[bool, typer.Option("--manual")] = False,
    restart: Annotated[bool, typer.Option("--restart")] = False,
    pidfile_dir: Annotated[Path | None, typer.Option("--pidfile-dir")] = None,
    force_write_pidfile: Annotated[bool, typer.Option("--force-write-pidfile")] = False,
) -> None:
    """Start the API proxy server."""
    if fd is not None:
        # An inherited listener belongs to systemd: this process neither chose the endpoint nor owns it, so nothing here can rebind it, hand it over, or record it. Each of these options asks for one of those. Refused rather than reported as inactive, because the option that gets silently dropped is the one whose absence nobody notices — which is the same failure `--restart` itself was just fixed for.
        conflicting = [
            name
            for name, given in (
                ("--host", host is not None),
                ("--port", port is not None),
                ("--restart", restart),
                ("--pidfile-dir", pidfile_dir is not None),
                ("--force-write-pidfile", force_write_pidfile),
            )
            if given
        ]
        if conflicting:
            raise typer.BadParameter(f"--fd cannot be combined with {', '.join(conflicting)}")

    # Before anything that might log. Both serve paths hand uvicorn `log_config=None`, so nothing else installs a handler and, without this call, every line the process produces — its own and uvicorn's — is dropped by the root logger's default level and never reaches the terminal at all.
    setup_logging(log_format="text", log_level="DEBUG" if verbose else "INFO")

    # Loaded and reported before the paths diverge. The inherited-listener branch used to load its own copy and discard the second return value, so every option this config cannot carry was accepted and then dropped without a word on that path — the same failure `--restart` was just fixed for, and the one the loop below exists to prevent.
    proxy_config, inactive = _load_spec_config(
        config_path=config,
        port=port,
        host=host,
        graceful_timeout=graceful_timeout,
        proxy=proxy,
        history=history,
        verbose=verbose,
        manual=manual,
        rate_limit=rate_limit,
        github_token=github_token,
    )
    for option, reason in inactive:
        # Said out loud rather than dropped: an option that is accepted and then ignored is worse than one that is refused, because nothing distinguishes it from having worked.
        typer.echo(f"warning: {option} has no effect on this path — {reason}", err=True)

    if fd is not None:
        # An inherited listener means systemd owns it, so uvicorn may keep it: lifecycle.md's escalating shutdown is written for the stand-alone section, which owns its own listener.
        # What this path serves is no longer the difference — it is the same chain `start` serves.
        # Ruled 2026-08-19; what the existing chain offered and this one does not is inventoried in `.dev/docs/anthropic-responses-bridge/implementation.md`.
        run(partial(serve_inherited, proxy_config, fd, proxy_from_cli=proxy is not None))
        return

    # `--pidfile-dir` beats the config key: both name the same directory, and the one typed on the command line is the more immediate statement of intent. Resolved here because the config key had no consumer at all — it was parsed into `ProxyConfig`, pinned in `NOT_HOT_RELOADABLE`, documented in `config.example.yaml`, and then never read, so an operator who set it got the default and no indication why.
    resolved_pidfile_dir = pidfile_dir
    if resolved_pidfile_dir is None and proxy_config.pidfile_dir:
        resolved_pidfile_dir = Path(proxy_config.pidfile_dir)

    # Served through app.lifecycle rather than uvicorn.run: the escalating shutdown and the
    # SO_REUSEPORT handover both need to own the listener, which uvicorn.run does not give up.
    options = StandaloneOptions(
        host=proxy_config.server.host,
        port=proxy_config.server.port,
        tls_mode=proxy_config.server.tls.mode,
        # None for an HTTP-only deployment, so a listener cannot be built with TLS it has no material for; generated once and reused when the operator named no cert.
        tls_material=resolve_tls_material(proxy_config, tls_dir=tls_material_dir()),
        cleanup_timeout=proxy_config.graceful_cleanup_timeout,
        pidfile_dir=resolved_pidfile_dir,
        restart=restart,
        force_write_pidfile=force_write_pidfile,
    )
    try:
        run(partial(_serve_pipeline, proxy_config, options, proxy_from_cli=proxy is not None))
    except PidfileError as error:
        # Turned into a message rather than left to the default excepthook. This one is not a crash: it is the ordinary case of starting a second time on a port that is already taken, and what it carries is an instruction — which of `--restart` and `--force-write-pidfile` the operator wants. A traceback buries that under a dozen frames and makes a routine refusal read as a failure of the program.
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error


def _selected_provider(provider: str, config: Path | None) -> tuple[ProxyConfig, str]:
    """Check that `provider` names a configured provider, and hand back the config it was found in.

    The config comes through `resolve_config_path` like every other entry point's — explicit `--config`, then `GHC_API_PROXY_CONFIG`, then the default location. An earlier version read a config only when `--config` was passed, which put the whole tenant feature behind a flag the operator on a tenant machine has no reason to type: they run `auth`, and got dotcom. Spec `.dev/docs/ghe-device-flow/spec.md` §3.5.

    **The provider is required and is never inferred**, ruled by the user 2026-08-28. `resolve_default_name` answers "which provider serves a request nobody qualified", which is a different question from "which account am I logging in as" — and these two commands write and delete credentials, where a default that quietly picks one for you produces a token stored under an identity the operator did not name. Naming it is one word, and it makes the confirmation line say something checkable.
    """
    proxy_config = _read_config(config)
    if provider not in proxy_config.model_providers:
        configured = ", ".join(sorted(proxy_config.model_providers)) or "none"
        raise typer.BadParameter(
            f"no model provider named {provider!r} is configured (configured: {configured})"
        )
    return proxy_config, provider


def _authenticate(provider: str, config: Path | None) -> None:
    """Log in against the tenant the named provider talks to, storing the token where that provider reads it.

    Both halves move together: a login that reaches the right host but writes to a file the provider never opens is as unusable as one that reached the wrong host, and doing only one of the two would leave the feature half-wired. Spec §3.5, §3.6.
    """
    proxy_config, provider_name = _selected_provider(provider, config)
    provider_config = proxy_config.model_providers[provider_name]
    try:
        web_base_url = GhcClientConfig(
            auth_base_url_override=provider_config.auth_base_url
        ).github_web_base_url
    except ValueError as error:
        # Refused rather than quietly sent to github.com: a device code issued by the wrong tenant yields a token the provider's own upstream will not honour, and nothing downstream would report where it came from.
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error
    token_path = github_token_path(proxy_config, provider_name)

    def notify(verification_uri: str, user_code: str) -> None:
        typer.echo(f"Visit {verification_uri} and enter code {user_code}")

    async def login() -> None:
        await authenticate_device(notify, token_path, web_base_url=web_base_url)
        # Which provider and which file, resolved and absolute. `github_token_file` is only now a path anything *writes*, and a configured one is taken verbatim: an unexpanded variable stays in the name, and a login that reports success while the service reads elsewhere has no other observable.
        typer.echo(
            f"Stored GitHub token for provider {provider_name!r}: {_resolved_token_path(token_path)}"
        )
        _warn_if_environment_shadows_the_token_file()

    run(login)


def _resolved_token_path(token_path: Path | None) -> Path:
    """Where the token file actually is, as an absolute path, including the default location.

    Asked of `FileTokenProvider` rather than spelled again here: it owns what "no path configured" resolves to, and a second copy of that expression would be a second answer the day either moves.
    """
    return FileTokenProvider(token_path).path.absolute()


def _warn_if_environment_shadows_the_token_file() -> None:
    """Say so when the token file is not the one the service will use.

    The file is the *third* source a provider consults. The first is `CLITokenProvider`, which `build_github_token_source` hard-codes to `CLITokenProvider(None)` and which `--github-token` no longer feeds — so in a running deployment it can never hold a token, and only the environment can shadow the file. **That is why one check is enough, and it stops being enough the moment the CLI level can carry a value.**

    Said out loud on the repository's own measure: an option accepted and then ignored is worse than one refused, because nothing distinguishes it from having worked. Spec §3.6.
    """
    if os.environ.get(GITHUB_TOKEN_VARIABLE, "").strip():
        typer.echo(
            f"warning: {GITHUB_TOKEN_VARIABLE} is set and takes priority over that file, so this does not change which token the service uses",
            err=True,
        )


_AUTH_CONFIG_OPTION = typer.Option(
    "--config",
    exists=False,
    file_okay=True,
    dir_okay=False,
    help="Read this config instead of the one the usual search finds.",
)
_AUTH_PROVIDER_ARGUMENT = typer.Argument(
    metavar="PROVIDER", help="Which configured model provider to act on."
)


@app.command("auth")
def auth(
    provider: Annotated[str, _AUTH_PROVIDER_ARGUMENT],
    config: Annotated[Path | None, _AUTH_CONFIG_OPTION] = None,
) -> None:
    """Authenticate with GitHub Copilot."""
    _authenticate(provider, config)


@app.command("login", hidden=False)
def login_command(
    provider: Annotated[str, _AUTH_PROVIDER_ARGUMENT],
    config: Annotated[Path | None, _AUTH_CONFIG_OPTION] = None,
) -> None:
    """Alias for auth."""
    _authenticate(provider, config)


@app.command()
def logout(
    provider: Annotated[str, _AUTH_PROVIDER_ARGUMENT],
    config: Annotated[Path | None, _AUTH_CONFIG_OPTION] = None,
) -> None:
    """Remove the stored authentication state of one model provider."""
    # Resolved exactly as `auth` resolves it, and for the reason `auth` exists: once a login writes a provider's own token file, a logout that clears some other path reports having removed authentication state while leaving a working token in place. Spec §3.7.
    #
    # **The OAuth origin is deliberately not derived here.** Removing a local file does not depend on where device codes come from, and requiring it would leave a deployment whose `auth_base_url` is a local stand-in unable to delete its own token through the CLI. Written down because §3.3's refusal is loud and a later reader could reasonably think it should apply to both commands.
    proxy_config, provider_name = _selected_provider(provider, config)
    token_path = github_token_path(proxy_config, provider_name)
    run(partial(clear_stored_token, token_path))
    # Named rather than announced in general. This clears one provider's file and nothing else, which is the whole reason the provider is a required argument rather than something inferred.
    typer.echo(
        f"Stored GitHub token removed for provider {provider_name!r}: {_resolved_token_path(token_path)}"
    )
    _warn_if_environment_shadows_the_token_file()


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


def _read_config(path: Path | None) -> ProxyConfig:
    """Load the config, reporting a bad one as an error rather than a traceback.

    A missing file and a config the schema rejects are both ordinary operator input on a command that accepts `--config`, and Typer's pretty traceback answers them with a stack that names this module rather than the key they mistyped. Pydantic's message already carries the field path and the reason, so it is passed through whole; only the frames are dropped.

    Scoped to the commands that read a config to answer a question — `debug models` first, and since 2026-08-28 `auth` and `logout` as well. `start` still raises through: changing what an already-shipped serving path does on a bad config was not part of implementing any of them. `auth` and `logout` are not that exception, because before that date they read no config at all, so there was no behaviour on a bad config to preserve.
    """
    try:
        return load_proxy_config(config_path=path)
    except (FileNotFoundError, ValueError, YAMLError) as error:
        # `ValueError` rather than `ValidationError` alone, and deliberately: pydantic's is a subclass of it, but so are the loader's own "configuration file must contain a mapping" and the `UnicodeDecodeError` a non-UTF-8 file raises. Naming only the pydantic one meant a config whose YAML root was a list answered with a traceback from `auth` down to `_read_yaml` — the exact shape this helper exists to prevent, on an input the operator can produce with one keystroke.
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=1) from error


@debug_app.command("models")
def debug_models(
    config: Annotated[
        Path | None,
        typer.Option("--config", exists=False, file_okay=True, dir_okay=False),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Report only this configured provider."),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print the complete decoded upstream payload, keyed by provider name unless --provider names one.",
        ),
    ] = False,
) -> None:
    """Show upstream model information."""
    proxy_config = _read_config(config)
    if provider is not None and provider not in proxy_config.model_providers:
        configured = ", ".join(sorted(proxy_config.model_providers)) or "none"
        raise typer.BadParameter(
            f"no model provider named {provider!r} is configured (configured: {configured})"
        )

    try:
        catalogs, failures = run(partial(collect_catalogs, proxy_config, provider))
    except ProviderNotConfigured as error:
        # `resolve_default_name` raises this with an empty name when the config leaves the choice open, and "no model provider named '' is configured" tells the operator nothing about which key to set.
        detail = (
            "config sets no `default_model_provider` and more than one provider is configured"
            if not error.name
            else str(error)
        )
        typer.echo(f"error: {detail}", err=True)
        raise typer.Exit(code=1) from error

    if catalogs:
        # `provider is None` and not `len(catalogs) == 1`: the shape follows what was asked for, so a deployment that happens to run one provider still gets a document naming it.
        rendered = (
            render_json(catalogs, keyed=provider is None) if as_json else render_text(catalogs)
        )
        typer.echo(rendered)
    for failure in failures:
        typer.echo(f"error: {failure.name}: {failure.reason}", err=True)
    if failures:
        raise typer.Exit(code=1)


@debug_app.command("usage")
def debug_usage() -> None:
    """Show Copilot usage information."""
    _not_implemented("debug usage")


def main() -> None:
    app()
