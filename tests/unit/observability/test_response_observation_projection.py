from app.observability.request_log import format_tokens
from app.observability.request_trace import RequestTrace
from app.pipeline.delivery.assembling import ReplyDialect, Terminal
from app.pipeline.response_observation import ResponsesObserver


def test_current_attempt_observation_replaces_every_legacy_fact_from_the_old_attempt() -> None:
    trace = RequestTrace(method="POST", path="/responses")
    old = Terminal(
        stop_reason="tool_use",
        usage={"input_tokens": 9, "output_tokens": 2},
        seen=True,
        dialect=ReplyDialect.RESPONSES,
        blocks=1,
        tools=["discarded"],
        thinking=["enc"],
    )
    trace.absorb(old)

    trace.absorb_response(ResponsesObserver().snapshot())

    assert trace.usage == {}
    assert trace.terminal_seen is False
    assert trace.stop_reason == ""
    assert trace.blocks == 0
    assert trace.tools == ()
    assert trace.thinking == ()
    assert trace.dialect is ReplyDialect.RESPONSES


def test_source_observation_is_the_final_legacy_projection_after_client_translation() -> None:
    trace = RequestTrace(method="POST", path="/v1/messages")
    translated = Terminal(
        stop_reason="tool_use",
        usage={
            "input_tokens": 9,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 2,
        },
        seen=True,
        dialect=ReplyDialect.RESPONSES,
        blocks=2,
        tools=["mapped_name"],
    )
    trace.absorb(translated)
    observer = ResponsesObserver()
    observer.observe_response({
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "name": "upstream_name",
                "content": [
                    {"type": "output_text", "text": "one"},
                    {"type": "output_text", "text": "two"},
                ],
            }
        ],
        "usage": {"input_tokens": 9, "output_tokens": 2},
    })

    trace.absorb_response(observer.snapshot())

    assert trace.blocks == 1
    assert trace.tools == ("upstream_name",)
    assert trace.usage == {"output_tokens": 2}
    assert trace.stop_reason == "tool_use"


def test_grok_usage_without_cached_tokens_keeps_the_total_input_count() -> None:
    observer = ResponsesObserver()
    observer.observe_response(
        {
            "status": "completed",
            "output": [],
            "usage": {
                "input_tokens": 65_700,
                "input_tokens_details": {"cache_write_tokens": 0},
                "output_tokens": 186,
            },
        }
    )
    trace = RequestTrace(method="POST", path="/responses")
    trace.absorb_response(observer.snapshot())

    assert format_tokens(trace.usage) == "↑65.7k+0 ↓186"


def test_provider_error_overrides_completed_legacy_ending_and_adds_detail() -> None:
    trace = RequestTrace(method="POST", path="/v1/responses")
    observer = ResponsesObserver()
    observer.observe_response({
        "status": "completed",
        "error": {
            "code": "server_error",
            "message": "provider completed with an error",
        },
        "output": [],
    })

    trace.absorb_response(observer.snapshot())

    assert trace.stop_reason == "error"
    assert trace.detail == (
        "provider response failed: upstream error message present"
    )
