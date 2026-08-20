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

import httpx
import pytest

from app.config.schema import ProxyConfig
from app.server.composition import build_http_client, transport_options


def socket_options_of_transport(transport: httpx.AsyncBaseTransport) -> object:
    assert isinstance(transport, httpx.AsyncHTTPTransport)
    return transport._pool._socket_options  # pyright: ignore[reportPrivateUsage]


def socket_options_of(client: httpx.AsyncClient) -> object:
    """What the pool will actually set on each new connection."""
    return socket_options_of_transport(client._transport)  # pyright: ignore[reportPrivateUsage]


def limits_of(client: httpx.AsyncClient) -> tuple[int, int, float | None]:
    transport = client._transport  # pyright: ignore[reportPrivateUsage]
    assert isinstance(transport, httpx.AsyncHTTPTransport)
    pool = transport._pool  # pyright: ignore[reportPrivateUsage]
    return (
        pool._max_connections,  # pyright: ignore[reportPrivateUsage]
        pool._max_keepalive_connections,  # pyright: ignore[reportPrivateUsage]
        pool._keepalive_expiry,  # pyright: ignore[reportPrivateUsage]
    )


def test_proxy_applies_to_every_outgoing_request() -> None:
    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:7890"})
    assert transport_options(config).proxy == "http://127.0.0.1:7890"


def test_absent_proxy_leaves_the_client_direct() -> None:
    assert transport_options(ProxyConfig()).proxy is None


def test_the_keepalive_interval_reaches_the_socket() -> None:
    """The interval is a TCP keep-alive now, not a pool expiry.

    Both idle and interval take the configured value, so a peer that has gone away is noticed within a bounded time rather than never. Read back off the pool because that is the only place the setting can be observed to exist.
    """
    config = ProxyConfig.model_validate({"upstream_transport": {"tcp_keepalive_interval": 25}})
    options = transport_options(config)
    assert options.socket_options is not None
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options.socket_options
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 25) in options.socket_options
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 25) in options.socket_options

    client = build_http_client(config)
    assert socket_options_of(client) == options.socket_options


def test_zero_keepalive_asks_for_no_socket_options_at_all() -> None:
    config = ProxyConfig.model_validate({"upstream_transport": {"tcp_keepalive_interval": 0}})
    assert transport_options(config).socket_options is None
    assert socket_options_of(build_http_client(config)) is None


def test_pooling_is_left_to_httpx() -> None:
    """Nothing here configures the pool, so httpx's own defaults are what apply.

    The old code passed a `Limits` carrying only `keepalive_expiry`, which left both connection caps at `None`; httpcore reads `None` as `sys.maxsize`, so naming one field had silently removed the caps. The 15-second idle expiry that mapping produced was never a setting anyone chose either — it was `tcp_keepalive_interval` landing in the wrong place — so it is not preserved and there is no key for it.
    """
    assert limits_of(build_http_client(ProxyConfig())) == (100, 20, 5.0)


def test_an_explicit_proxy_reaching_httpx_shuts_the_environment_out() -> None:
    """Pins the httpx-facing behaviour only: an explicit proxy is `all://`, and the environment is not consulted.

    Deliberately not named for the product's priority rule. `docs/.human-controlled/config.example.yaml` puts `HTTP_PROXY` / `HTTPS_PROXY` *above* the config file's `proxy`, but `load_proxy_config()` flattens CLI, `GHC_PROXY` and YAML into one field with no provenance, so nothing downstream can tell them apart. That predates this change and is not fixed here; naming this test after the rule would freeze the wrong half of it. Recorded in `docs/agents/delivery-keepalive/deferred.md`.
    """
    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:9999"})
    client = build_http_client(config)
    assert client._mounts == {}  # pyright: ignore[reportPrivateUsage]


def test_http2_can_be_switched_off_for_an_http1_upstream() -> None:
    """One GOAWAY on a multiplexed connection kills every stream riding it, so this switch exists."""
    off = ProxyConfig.model_validate({"upstream_transport": {"http2": False}})
    on = ProxyConfig.model_validate({"upstream_transport": {"http2": True}})
    assert transport_options(off).http2 is False
    assert transport_options(on).http2 is True


def test_the_ping_interval_no_longer_decides_the_protocol() -> None:
    """It used to, which is how a key named after a ping interval became the HTTP/1.1 switch.

    Nothing reads `http2_ping_interval` today — neither httpx nor httpcore exposes an HTTP/2 PING interval — so it never produced a ping either. Pinned so the coupling cannot come back by accident: setting it to 0 must leave the protocol alone.
    """
    config = ProxyConfig.model_validate({"upstream_transport": {"http2_ping_interval": 0}})
    assert transport_options(config).http2 is True


def test_the_spec_defaults_produce_a_keepalive_and_http2() -> None:
    options = transport_options(ProxyConfig())
    assert options.socket_options is not None
    assert options.http2 is True


def describe_route(client: httpx.AsyncClient, url: str) -> str:
    """Where a URL would go: the proxy's origin, or `direct`.

    Comparable across clients, which identity is not — and comparing against native httpx is the only way to show the environment handling is equivalent rather than merely present.
    """
    transport = client._transport_for_url(httpx.URL(url))  # pyright: ignore[reportPrivateUsage]
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

    ours = build_http_client(ProxyConfig())
    native = httpx.AsyncClient()

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

    client = build_http_client(ProxyConfig())
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
        build_http_client(config)
    assert any("SOCKS" in record.message for record in caplog.records)


def test_a_direct_proxy_says_nothing_of_the_sort(caplog: pytest.LogCaptureFixture) -> None:
    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:7890"})
    with caplog.at_level("WARNING"):
        build_http_client(config)
    assert not [record for record in caplog.records if "SOCKS" in record.message]


def test_a_platform_without_the_timing_constants_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Keep-alive still goes on, but with the system's idle time — which looks like no effect at all.

    `TCP_KEEPIDLE` is Linux, `TCP_KEEPALIVE` is macOS for the same thing; both are tried. Where neither is there the value simply cannot be set, and the only honest thing left is to say which one was missing.
    """
    monkeypatch.delattr(socket, "TCP_KEEPIDLE", raising=False)
    monkeypatch.delattr(socket, "TCP_KEEPALIVE", raising=False)
    with caplog.at_level("WARNING"):
        options = transport_options(ProxyConfig())
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
    client = build_http_client(ProxyConfig.model_validate(config))
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
        build_http_client(ProxyConfig())
    assert any("SOCKS" in record.message for record in caplog.records)


def test_the_socks_warning_does_not_carry_the_proxy_password(caplog: pytest.LogCaptureFixture) -> None:
    """A proxy URL may hold credentials, and a line about a setting is not worth logging them to produce."""
    config = ProxyConfig.model_validate({"proxy": "socks5://user:hunter2@127.0.0.1:1080"})
    with caplog.at_level("WARNING"):
        build_http_client(config)
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
