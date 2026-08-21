"""The transport settings must reach the client that actually makes requests.

Two of these assertions reach into httpx's private attributes on purpose. The defect this file now guards against is precisely that a setting looked wired and did nothing: `tcp_keepalive_interval` was mapped to the connection pool's idle expiry, which never writes to a socket and does not apply while a request is in flight. Asserting only on our own `TransportOptions` would have passed for that too.
"""

import datetime
import socket
import ssl
import threading
from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpcore2
import httpx2
import pytest

from app.config.schema import ProxyConfig
from app.server.composition import build_http_client, transport_options
from app.upstream.stream_cap import StreamCappedConnection


def socket_options_of_transport(transport: httpx2.AsyncBaseTransport) -> object:
    assert isinstance(transport, httpx2.AsyncHTTPTransport)
    return transport._pool._socket_options  # pyright: ignore[reportPrivateUsage]


def socket_options_of(client: httpx2.AsyncClient) -> object:
    """What the pool will actually set on each new connection."""
    return socket_options_of_transport(client._transport)  # pyright: ignore[reportPrivateUsage]


def limits_of(client: httpx2.AsyncClient) -> tuple[int, int, float | None]:
    transport = client._transport  # pyright: ignore[reportPrivateUsage]
    assert isinstance(transport, httpx2.AsyncHTTPTransport)
    pool = transport._pool  # pyright: ignore[reportPrivateUsage]
    return (
        pool._max_connections,  # pyright: ignore[reportPrivateUsage]
        pool._max_keepalive_connections,  # pyright: ignore[reportPrivateUsage]
        pool._keepalive_expiry,  # pyright: ignore[reportPrivateUsage]
    )


def _clear_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both cases of all four names, because httpx reads whichever it finds and a leftover would decide the test's answer."""
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)


def test_the_setting_lands_in_the_tier_below_the_environment() -> None:
    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:7890"})
    options = transport_options(config, proxy_from_cli=False)
    assert options.setting_proxy == "http://127.0.0.1:7890"
    assert options.cli_proxy is None


def test_the_same_value_from_the_command_line_lands_in_the_tier_above_it() -> None:
    """The string is identical; only its tier differs, and nothing in it says which.

    This is the whole reason `proxy_from_cli` exists: `load_proxy_config` merges CLI, `GHC_PROXY` and YAML into one field, so by the time anything downstream reads it the provenance is gone.
    """
    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:7890"})
    options = transport_options(config, proxy_from_cli=True)
    assert options.cli_proxy == "http://127.0.0.1:7890"
    assert options.setting_proxy is None


def test_absent_proxy_leaves_the_client_direct() -> None:
    options = transport_options(ProxyConfig(), proxy_from_cli=False)
    assert options.cli_proxy is None
    assert options.setting_proxy is None


def test_the_keepalive_interval_reaches_the_socket() -> None:
    """The interval is a TCP keep-alive now, not a pool expiry.

    Both idle and interval take the configured value, so a peer that has gone away is noticed within a bounded time rather than never. Read back off the pool because that is the only place the setting can be observed to exist.
    """
    config = ProxyConfig.model_validate({"upstream_transport": {"tcp_keepalive_interval": 25}})
    options = transport_options(config, proxy_from_cli=False)
    assert options.socket_options is not None
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options.socket_options
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 25) in options.socket_options
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 25) in options.socket_options

    client = build_http_client(config, proxy_from_cli=False)
    assert socket_options_of(client) == options.socket_options


def test_zero_keepalive_asks_for_no_socket_options_at_all() -> None:
    config = ProxyConfig.model_validate({"upstream_transport": {"tcp_keepalive_interval": 0}})
    assert transport_options(config, proxy_from_cli=False).socket_options is None
    assert socket_options_of(build_http_client(config, proxy_from_cli=False)) is None


def test_pooling_is_left_to_httpx() -> None:
    """Nothing here configures the pool, so httpx's own defaults are what apply.

    The old code passed a `Limits` carrying only `keepalive_expiry`, which left both connection caps at `None`; httpcore reads `None` as `sys.maxsize`, so naming one field had silently removed the caps. The 15-second idle expiry that mapping produced was never a setting anyone chose either — it was `tcp_keepalive_interval` landing in the wrong place — so it is not preserved and there is no key for it.
    """
    assert limits_of(build_http_client(ProxyConfig(), proxy_from_cli=False)) == (100, 20, 5.0)


def test_the_command_line_proxy_shuts_the_environment_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 1 of the priority `config.example.yaml` states: `--proxy` beats the environment.

    Named for the product rule now that the rule is implementable. The earlier version of this test deliberately avoided the name, because `load_proxy_config` flattened CLI, `GHC_PROXY` and YAML into one field and nothing downstream could tell them apart — naming it then would have frozen the wrong half.

    Nothing from the environment reaches the mounts, which is what "shuts out" means here — a single `all://` and no per-scheme or `NO_PROXY` pattern beside it.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7891")
    monkeypatch.setenv("NO_PROXY", "internal.example.com")

    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:9999"})
    client = build_http_client(config, proxy_from_cli=True)

    assert [pattern.pattern for pattern in client._mounts] == ["all://"]  # pyright: ignore[reportPrivateUsage]
    assert {describe_route(client, url) for url in ROUTE_SAMPLES} == {"http://127.0.0.1:9999"}


def test_the_environment_beats_the_setting_only_for_the_schemes_it_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tiers 2 and 3 are both live at once. Ruled 2026-08-21: per-scheme, not whole-tier.

    The setting goes on as `all://`, httpx's least specific pattern, so a named scheme in the environment is resolved ahead of it and the schemes the environment does not name fall through to the setting. No routing is decided by us — this asserts that httpx's own mount resolution produces the ruled outcome.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7891")

    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:9999"})
    client = build_http_client(config, proxy_from_cli=False)

    assert describe_route(client, "https://api.githubcopilot.com/v1") == "http://127.0.0.1:7891"
    assert describe_route(client, "http://api.githubcopilot.com/v1") == "http://127.0.0.1:9999"


def test_all_proxy_replaces_the_setting_rather_than_sitting_beside_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ALL_PROXY` lands on the same `all://` key, so it overwrites rather than merges.

    `config.example.yaml` names only `HTTP_PROXY` / `HTTPS_PROXY` in tier 2, but excluding `ALL_PROXY` would mean the one environment variable that says "everything" is the one the setting outranks.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7890")

    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:9999"})
    client = build_http_client(config, proxy_from_cli=False)

    assert {describe_route(client, url) for url in ROUTE_SAMPLES} == {"http://127.0.0.1:7890"}


def test_no_proxy_reaches_past_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `NO_PROXY` host is `all://<host>`, more specific than the setting's `all://`, so it still goes direct.

    Without this the setting would swallow `NO_PROXY` — the rule would be implemented for proxies and silently not for exemptions from them.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("NO_PROXY", "internal.example.com")

    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:9999"})
    client = build_http_client(config, proxy_from_cli=False)

    assert describe_route(client, "https://internal.example.com/x") == "direct"
    assert describe_route(client, "https://api.githubcopilot.com/v1") == "http://127.0.0.1:9999"


def test_the_setting_alone_still_carries_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing in the environment, tier 3 is the only tier, and it must route exactly as an explicit proxy would."""
    _clear_proxy_environment(monkeypatch)

    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:9999"})
    client = build_http_client(config, proxy_from_cli=False)

    assert {describe_route(client, url) for url in ROUTE_SAMPLES} == {"http://127.0.0.1:9999"}


def test_a_wildcard_no_proxy_beats_the_setting_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """`NO_PROXY=*` is the environment saying "no proxy for anything", which is tier 2 overruling tier 3.

    The one `NO_PROXY` form that cannot be a mount: httpx expresses it by returning an *empty* environment map, indistinguishable from an environment that names no proxy at all. Reading that emptiness as "the environment is silent" left the setting in charge and sent every request through it — the exact inverse of what was asked for, with every other test still green because every other `NO_PROXY` form produces an `all://<host>` entry that outranks the setting on its own.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7891")
    monkeypatch.setenv("NO_PROXY", "*")

    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:9999"})
    ours = build_http_client(config, proxy_from_cli=False)
    native = httpx2.AsyncClient()

    assert [describe_route(ours, url) for url in ROUTE_SAMPLES] == [
        describe_route(native, url) for url in ROUTE_SAMPLES
    ]
    assert {describe_route(ours, url) for url in ROUTE_SAMPLES} == {"direct"}


def test_an_empty_command_line_proxy_still_shuts_the_environment_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--proxy ""` is an operator overriding a configured proxy back to direct.

    Tier 1 having been *given* is what shuts the lower tiers out, not its value being non-empty. Deciding that on the value instead handed the request straight back to the environment the operator was overriding — and the config file's proxy would have been shut out while the environment was not, which is neither tier order.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7890")

    config = ProxyConfig.model_validate({"proxy": ""})
    client = build_http_client(config, proxy_from_cli=True)

    assert {describe_route(client, url) for url in ROUTE_SAMPLES} == {"direct"}


def test_a_socks_setting_the_environment_has_replaced_is_not_warned_about(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The warning reads the resolved routing, not the settings it came from.

    `ALL_PROXY` lands on the same `all://` key as the setting and replaces it outright, so no request can reach that SOCKS proxy and saying the keep-alive will not apply to it describes nothing.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7890")

    config = ProxyConfig.model_validate({"proxy": "socks5://127.0.0.1:1080"})
    with caplog.at_level("WARNING"):
        build_http_client(config, proxy_from_cli=False)

    assert not [record for record in caplog.records if "SOCKS" in record.message]


def test_a_socks_setting_the_environment_leaves_room_for_is_warned_about(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The control for the test above: the setting still carries http, so the warning must fire.

    Without this pair, a warning that had simply stopped working would look like the shadowing fix.
    """
    _clear_proxy_environment(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7891")

    config = ProxyConfig.model_validate({"proxy": "socks5://127.0.0.1:1080"})
    with caplog.at_level("WARNING"):
        build_http_client(config, proxy_from_cli=False)

    assert [record for record in caplog.records if "SOCKS" in record.message]


def test_http2_can_be_switched_off_for_an_http1_upstream() -> None:
    """One GOAWAY on a multiplexed connection kills every stream riding it, so this switch exists."""
    off = ProxyConfig.model_validate({"upstream_transport": {"http2": False}})
    on = ProxyConfig.model_validate({"upstream_transport": {"http2": True}})
    assert transport_options(off, proxy_from_cli=False).http2 is False
    assert transport_options(on, proxy_from_cli=False).http2 is True


def test_the_ping_interval_no_longer_decides_the_protocol() -> None:
    """It used to, which is how a key named after a ping interval became the HTTP/1.1 switch.

    Nothing reads `http2_ping_interval` today — neither httpx nor httpcore exposes an HTTP/2 PING interval — so it never produced a ping either. Pinned so the coupling cannot come back by accident: setting it to 0 must leave the protocol alone.
    """
    config = ProxyConfig.model_validate({"upstream_transport": {"http2_ping_interval": 0}})
    assert transport_options(config, proxy_from_cli=False).http2 is True


def test_the_spec_defaults_produce_a_keepalive_and_http2() -> None:
    options = transport_options(ProxyConfig(), proxy_from_cli=False)
    assert options.socket_options is not None
    assert options.http2 is True


def describe_route(client: httpx2.AsyncClient, url: str) -> str:
    """Where a URL would go: the proxy's origin, or `direct`.

    Comparable across clients, which identity is not — and comparing against native httpx is the only way to show the environment handling is equivalent rather than merely present.
    """
    transport = client._transport_for_url(httpx2.URL(url))  # pyright: ignore[reportPrivateUsage]
    pool = getattr(transport, "_pool", None)
    proxy_url = getattr(pool, "_proxy_url", None)
    return "direct" if proxy_url is None else str(proxy_url.origin)


ROUTE_SAMPLES = (
    "https://api.githubcopilot.com/v1",
    "http://api.githubcopilot.com/v1",
    "https://internal.example.com/x",
    "http://localhost:4141/v1",
)


def test_environment_routing_matches_native_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every destination goes where httpx's own reading of the environment would have sent it.

    The earlier version of this test set one variable and asserted that *some* non-empty transport matched an HTTPS URL. That passes for a great many wrong answers — including sending everything through the wrong proxy. Native httpx is the oracle here because reimplementing `NO_PROXY` is exactly what this code avoids doing.
    """
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7891")
    monkeypatch.setenv("NO_PROXY", "internal.example.com,localhost")

    ours = build_http_client(ProxyConfig(), proxy_from_cli=False)
    native = httpx2.AsyncClient()

    assert [describe_route(ours, url) for url in ROUTE_SAMPLES] == [
        describe_route(native, url) for url in ROUTE_SAMPLES
    ]
    # And not vacuously: this environment really does route some of them through a proxy and some direct.
    assert len({describe_route(ours, url) for url in ROUTE_SAMPLES}) > 1


def test_no_proxy_rules_share_one_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each `NO_PROXY` rule mounts the same direct transport, as httpx's own does.

    Giving each rule a transport of its own routes identically and pools differently: every rule would carry its own 100-connection cap, so the cap multiplies by however many rules an operator wrote. Routing tests cannot see that.
    """
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("NO_PROXY", "a.example.com,b.example.com,c.example.com")

    client = build_http_client(ProxyConfig(), proxy_from_cli=False)
    mounts = client._mounts  # pyright: ignore[reportPrivateUsage]
    direct = {
        id(transport)
        for transport in mounts.values()
        if transport is not None
        and getattr(getattr(transport, "_pool", None), "_proxy_url", None) is None
    }
    assert len(direct) == 1, "each NO_PROXY rule brought its own pool, and its own connection cap"


def test_a_socks_proxy_says_the_keepalive_will_not_apply(caplog: pytest.LogCaptureFixture) -> None:
    """httpcore's SOCKS pool takes no socket options, so the setting cannot reach that path.

    Measured on a real SOCKS5 connection: `SO_KEEPALIVE` reads back 0 while the same build over a direct connection reads 1. Nothing here can fix that — `AsyncSOCKSProxy.__init__` has no `socket_options` parameter — so the one thing it must not do is keep claiming the keep-alive applies.
    """
    config = ProxyConfig.model_validate({"proxy": "socks5://127.0.0.1:1080"})
    with caplog.at_level("WARNING"):
        build_http_client(config, proxy_from_cli=False)
    assert any("SOCKS" in record.message for record in caplog.records)


def _connection_of_the_proxy_pool(client: httpx2.AsyncClient) -> Any:
    """What the pool that carries a proxy would build for an HTTPS origin, without connecting.

    Finds it wherever the tier put it: `--proxy` makes the proxy pool the client's own transport, while the `proxy` setting mounts it. Asserting against `client._transport` alone would quietly read the *direct* pool in the mounted case and find no proxy connection to check.

    Typed `Any` deliberately: httpcore's pool attributes are untyped, and reading them at each call site spreads three unknown-type diagnostics per site instead of one place that says "this is third-party private state".
    """
    candidates = [client._transport, *client._mounts.values()]  # pyright: ignore[reportPrivateUsage]
    for transport in candidates:
        pool: Any = getattr(transport, "_pool", None)
        if pool is not None and getattr(pool, "_proxy_url", None) is not None:
            return pool.create_connection(httpcore2.Origin(b"https", b"example.invalid", 443))
    raise AssertionError("no transport in this client carries a proxy pool")


def test_a_direct_proxy_says_nothing_of_the_sort(caplog: pytest.LogCaptureFixture) -> None:
    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:7890"})
    with caplog.at_level("WARNING"):
        build_http_client(config, proxy_from_cli=False)
    assert not [record for record in caplog.records if "SOCKS" in record.message]


def test_the_socks_warning_prints_an_ipv6_origin_that_can_be_read_back(caplog: pytest.LogCaptureFixture) -> None:
    """httpx returns an IPv6 host without its brackets, and `socks5://::1:1080` is not a URL of anything.

    The round trip is the assertion rather than the string, because the point is that an operator can paste what the warning printed back into a config and get the same proxy.
    """
    config = ProxyConfig.model_validate({"proxy": "socks5://user:hunter2@[::1]:1080"})
    with caplog.at_level("WARNING"):
        build_http_client(config, proxy_from_cli=False)
    printed = [record for record in caplog.records if "SOCKS" in record.message]
    assert len(printed) == 1
    message = printed[0].getMessage()
    assert "hunter2" not in message
    origin = httpx2.URL(message.split(" ", 2)[1])
    assert origin.host == "::1"
    assert origin.port == 1080


def test_the_socks_warning_keeps_an_explicit_port_zero(caplog: pytest.LogCaptureFixture) -> None:
    """`if parsed.port` would drop it: httpx parses `:0` as the integer 0, which is falsy.

    Port 0 is not a working proxy destination, so this is about the warning telling the truth rather than about reachability — but the predicate is the one an operator's setting has to survive.
    """
    config = ProxyConfig.model_validate({"proxy": "socks5://user:hunter2@host.example:0"})
    with caplog.at_level("WARNING"):
        build_http_client(config, proxy_from_cli=False)
    printed = [record for record in caplog.records if "SOCKS" in record.message]
    assert len(printed) == 1
    assert "socks5://host.example:0" in printed[0].getMessage()


@pytest.mark.parametrize("proxy_from_cli", [True, False])
def test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive(
    monkeypatch: pytest.MonkeyPatch, proxy_from_cli: bool
) -> None:
    """Two patches land on the same `create_connection`, and the order decides whether both survive.

    Keep-alive first, cap second: the cap wraps the keep-alive closure and both apply. Reversed, the keep-alive closure is assigned over the cap's and the cap is unreachable — no error, and the socket options still correct, so every other assertion in this file would still pass. Measured on a real CONNECT tunnel: five concurrent requests on one h2 tunnel instead of the four connections a cap of 2 produces.

    Both tiers, because they put the proxy pool in different places: `--proxy` makes it the client's own transport, while the `proxy` setting mounts it under `all://`. The cap walks mounts as well as the default transport, and this is what says so for the pool that carries a proxy rather than for a direct one.
    """
    _clear_proxy_environment(monkeypatch)
    config = ProxyConfig.model_validate(
        {
            "proxy": "http://127.0.0.1:7890",
            "upstream_transport": {"tcp_keepalive_interval": 25, "max_streams_per_connection": 2},
        }
    )
    client = build_http_client(config, proxy_from_cli=proxy_from_cli)
    created = _connection_of_the_proxy_pool(client)

    assert isinstance(created, StreamCappedConnection), "the keep-alive patch was installed over the cap"
    # Constructing the tunnel does not connect, so the options are read off the connection it will use rather than off a socket.
    options = getattr(getattr(created._inner, "_connection", None), "_socket_options", None)  # pyright: ignore[reportPrivateUsage]
    assert options is not None
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options


def test_a_platform_without_the_timing_constants_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Keep-alive still goes on, but with the system's idle time — which looks like no effect at all.

    `TCP_KEEPIDLE` is Linux, `TCP_KEEPALIVE` is macOS for the same thing; both are tried. Where neither is there the value simply cannot be set, and the only honest thing left is to say which one was missing.
    """
    monkeypatch.delattr(socket, "TCP_KEEPIDLE", raising=False)
    monkeypatch.delattr(socket, "TCP_KEEPALIVE", raising=False)
    with caplog.at_level("WARNING"):
        options = transport_options(ProxyConfig(), proxy_from_cli=False)
    assert options.socket_options is not None
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options.socket_options
    assert any("TCP_KEEPIDLE" in record.message for record in caplog.records)


class _Origin(BaseHTTPRequestHandler):
    """Answers anything, including the absolute-URI form a forward proxy receives."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("content-length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def running_origin() -> Generator[int]:
    server = HTTPServer(("127.0.0.1", 0), _Origin)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5)


async def keepalive_on_the_wire(config: dict[str, Any], url: str) -> dict[str, int]:
    """What the kernel says about the socket this request actually used."""
    client = build_http_client(ProxyConfig.model_validate(config), proxy_from_cli=True)
    async with client, client.stream("GET", url) as response:
        sock = response.extensions["network_stream"].get_extra_info("socket")
        read = {"SO_KEEPALIVE": sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)}
        for name in ("TCP_KEEPIDLE", "TCP_KEEPINTVL", "TCP_KEEPCNT"):
            option = getattr(socket, name, None)
            if option is not None:
                read[name] = sock.getsockopt(socket.IPPROTO_TCP, option)
        await response.aread()
        return read


@pytest.mark.asyncio
@pytest.mark.parametrize("through_proxy", [False, True])
async def test_the_keepalive_is_on_the_socket_that_carries_the_request(through_proxy: bool) -> None:
    """The only assertion here that cannot be satisfied by a setting that does nothing.

    Everything else in this file reads back what was passed in. This opens a real connection — direct, and through a real forward proxy — and asks the kernel. It is here because httpcore takes `socket_options` on `AsyncHTTPProxy`, stores it, and then builds the connection without it: the proxy path read `SO_KEEPALIVE=0` while every parameter along the way looked correctly threaded.
    """
    with running_origin() as port:
        config: dict[str, Any] = {"upstream_transport": {"tcp_keepalive_interval": 25}}
        url = f"http://127.0.0.1:{port}/"
        if through_proxy:
            config["proxy"] = f"http://127.0.0.1:{port}"
            url = "http://example.invalid/"
        read = await keepalive_on_the_wire(config, url)

    assert read["SO_KEEPALIVE"] == 1
    assert read.get("TCP_KEEPIDLE") == 25
    assert read.get("TCP_KEEPINTVL") == 25
    assert read.get("TCP_KEEPCNT") == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("through_proxy", [False, True])
async def test_switching_the_keepalive_off_leaves_the_system_defaults(through_proxy: bool) -> None:
    """The control the assertion above needs: 25 has to be a value we set, not one the box already had."""
    with running_origin() as port:
        config: dict[str, Any] = {"upstream_transport": {"tcp_keepalive_interval": 0}}
        url = f"http://127.0.0.1:{port}/"
        if through_proxy:
            config["proxy"] = f"http://127.0.0.1:{port}"
            url = "http://example.invalid/"
        read = await keepalive_on_the_wire(config, url)

    assert read["SO_KEEPALIVE"] == 0
    assert read.get("TCP_KEEPIDLE") != 25


def test_a_socks_proxy_from_the_environment_is_warned_about_too(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`ALL_PROXY=socks5://…` fails exactly like a configured one, so it cannot be the quiet case."""
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
    with caplog.at_level("WARNING"):
        build_http_client(ProxyConfig(), proxy_from_cli=False)
    assert any("SOCKS" in record.message for record in caplog.records)


def test_the_socks_warning_does_not_carry_the_proxy_password(caplog: pytest.LogCaptureFixture) -> None:
    """A proxy URL may hold credentials, and a line about a setting is not worth logging them to produce."""
    config = ProxyConfig.model_validate({"proxy": "socks5://user:hunter2@127.0.0.1:1080"})
    with caplog.at_level("WARNING"):
        build_http_client(config, proxy_from_cli=False)
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "SOCKS" in logged
    assert "hunter2" not in logged
    assert "user" not in logged


def self_signed(host: str, directory: Path) -> tuple[Path, Path]:
    """A cert for `host`, and the file to trust it by. Both are thrown away with the tmp dir."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "cert.pem"
    key_path = directory / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


@contextmanager
def running_tls_origin(cert: Path, key: Path) -> Generator[int]:
    server = HTTPServer(("127.0.0.1", 0), _Origin)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert, keyfile=key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def pipe(source: socket.socket, sink: socket.socket) -> None:
    try:
        while chunk := source.recv(65536):
            sink.sendall(chunk)
    except OSError:
        pass


@contextmanager
def running_connect_proxy() -> Generator[int]:
    """The narrowest proxy that exercises the tunnel branch: read CONNECT, answer 200, then pipe."""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                client, _ = listener.accept()
            except OSError:
                return
            threading.Thread(target=tunnel, args=(client,), daemon=True).start()

    def tunnel(client: socket.socket) -> None:
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = client.recv(4096)
            if not chunk:
                return
            request += chunk
        target = request.split(b" ")[1].decode()
        host, _, port = target.partition(":")
        upstream = socket.create_connection((host, int(port)))
        client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
        pipe(upstream, client)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_the_keepalive_is_on_the_socket_of_a_connect_tunnel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The branch the product actually uses: HTTPS upstream, reached through a proxy.

    `create_connection` builds a tunnel connection here rather than a forward one, and that is a second call site that has to pass the socket options on. The forward test cannot see it. Reading the code says both branches were fixed together; reading the code is what got the proxy path wrong in the first place, so this asks the kernel.
    """
    cert, key = self_signed("localhost", tmp_path)
    monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    with running_tls_origin(cert, key) as origin_port, running_connect_proxy() as proxy_port:
        read = await keepalive_on_the_wire(
            {
                "upstream_transport": {"tcp_keepalive_interval": 25},
                "proxy": f"http://127.0.0.1:{proxy_port}",
            },
            f"https://localhost:{origin_port}/",
        )

    assert read["SO_KEEPALIVE"] == 1
    assert read.get("TCP_KEEPIDLE") == 25
    assert read.get("TCP_KEEPINTVL") == 25
    assert read.get("TCP_KEEPCNT") == 4
