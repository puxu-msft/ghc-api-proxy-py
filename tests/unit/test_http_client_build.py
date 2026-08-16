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


def test_http2_follows_the_ping_interval() -> None:
    enabled = ProxyConfig.model_validate({"upstream_transport": {"http2_ping_interval": 15}})
    disabled = ProxyConfig.model_validate({"upstream_transport": {"http2_ping_interval": 0}})
    assert transport_options(enabled).http2 is True
    assert transport_options(disabled).http2 is False


def test_the_spec_defaults_produce_a_keepalive_and_http2() -> None:
    options = transport_options(ProxyConfig())
    assert options.keepalive_expiry == 15.0
    assert options.http2 is True
