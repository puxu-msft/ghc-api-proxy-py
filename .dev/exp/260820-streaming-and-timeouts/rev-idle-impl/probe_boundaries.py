"""Boundary values, resolved through the real config object and the real wiring function."""
import sys
sys.path.insert(0, "/tmp/rev-idle-impl/tests/http")

import httpx
from test_pipeline_app import make_client  # type: ignore

from app.config.schema import ProxyConfig
from app.server.handler import stream_idle_seconds
from app.server.pipeline_app import CHAIN_STATE_KEY


def chain_with(section: dict):
    client, _ = make_client(
        lambda _: httpx.Response(200, json={"id": "m", "content": []}),
        overrides={"upstream_request_timeouts": section},
    )
    return getattr(client.app.state, CHAIN_STATE_KEY)


cases = [
    ("bundled default (nothing set)", {}, "claude-opus-5"),
    ("scalar 0", {"stream_idle": 0}, "claude-opus-5"),
    ("scalar 1", {"stream_idle": 1}, "claude-opus-5"),
    ("scalar 300, override 0 on a hit", {"stream_idle": 300, "stream_idle_overrides": {"opus": 0}}, "claude-opus-5"),
    ("scalar 300, override 0 on '*'", {"stream_idle": 300, "stream_idle_overrides": {"*": 0}}, "claude-opus-5"),
    ("scalar 0, override 5 on a hit", {"stream_idle": 0, "stream_idle_overrides": {"opus": 5}}, "claude-opus-5"),
    ("negative override", {"stream_idle": 300, "stream_idle_overrides": {"opus": -7}}, "claude-opus-5"),
    ("negative scalar", {"stream_idle": -7}, "claude-opus-5"),
]
for label, section, model in cases:
    try:
        chain = chain_with(section)
    except Exception as exc:
        print(f"{label:38s} -> REJECTED by validation: {type(exc).__name__}: {str(exc).splitlines()[0]}")
        continue
    print(f"{label:38s} -> stream_idle_seconds({model!r}) = {stream_idle_seconds(chain, model)}")
