"""The transport settings must reach the client that actually makes requests."""

from app.config.schema import ProxyConfig
from app.server.composition import transport_options


def test_proxy_applies_to_every_outgoing_request() -> None:
    config = ProxyConfig.model_validate({"proxy": "http://127.0.0.1:7890"})
    assert transport_options(config).proxy == "http://127.0.0.1:7890"


def test_absent_proxy_leaves_the_client_direct() -> None:
    assert transport_options(ProxyConfig()).proxy is None


def test_keepalive_interval_becomes_the_expiry() -> None:
    config = ProxyConfig.model_validate({"upstream_transport": {"tcp_keepalive_interval": 25}})
    assert transport_options(config).keepalive_expiry == 25.0


def test_zero_keepalive_disables_the_expiry() -> None:
    config = ProxyConfig.model_validate({"upstream_transport": {"tcp_keepalive_interval": 0}})
    assert transport_options(config).keepalive_expiry is None


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
    assert options.keepalive_expiry == 15.0
    assert options.http2 is True
