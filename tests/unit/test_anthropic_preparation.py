from app.anthropic.header_policy import forward_request_headers, forward_response_headers
from app.anthropic.request_preparation import prepare_anthropic_request
from app.anthropic.warmup import apply_warmup_policy, is_warmup_request


def test_request_header_floor_blocks_credentials_and_topology() -> None:
    selected = forward_request_headers(
        {"authorization": "bad", "x-forwarded-for": "1.2.3.4", "x-claude-code-id": "ok"},
        core={"authorization": "Bearer good"},
        strict=False,
        blacklist=[],
        whitelist=[],
    )
    assert selected == {"x-claude-code-id": "ok", "authorization": "Bearer good"}


def test_header_floor_blocks_complete_hop_by_hop_sets() -> None:
    request_headers = {
        name: "bad"
        for name in (
            "set-cookie", "expect", "keep-alive", "te", "trailer",
            "x-forwarded-port", "cf-connecting-ip", "x-client-ip",
        )
    }
    assert forward_request_headers(
        request_headers,
        core={},
        strict=False,
        blacklist=[],
        whitelist=[],
    ) == {}
    assert forward_response_headers(
        {"proxy-authenticate": "bad", "te": "bad", "upgrade": "bad"},
        strict=False,
        blacklist=[],
        whitelist=[],
    ) == {}


def test_response_header_floor_blocks_framing_even_if_whitelisted() -> None:
    selected = forward_response_headers(
        {"content-length": "99", "request-id": "req"},
        strict=True,
        blacklist=[],
        whitelist=["content-*", "request-id"],
    )
    assert selected == {"request-id": "req"}


def test_warmup_detection_and_fake_response() -> None:
    payload = {"model": "claude-test", "messages": [{"role": "user", "content": "Warmup"}]}
    assert is_warmup_request(payload) is True
    response = apply_warmup_policy(payload, "fake")
    assert response is not None
    assert response["content"][0]["text"] == "Cache warmed."


def test_request_preparation_strips_field_adds_betas_and_destacks() -> None:
    payload = {
        "model": "claude-test",
        "inference_geo": "us",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "a", "signature": "1"},
                    {"type": "thinking", "thinking": "b", "signature": "2"},
                ],
            }
        ],
    }
    prepared = prepare_anthropic_request(payload)
    assert "inference_geo" not in prepared.wire
    assert "anthropic-beta" in prepared.headers
    assert prepared.wire["messages"][0]["content"][1]["type"] == "text"
