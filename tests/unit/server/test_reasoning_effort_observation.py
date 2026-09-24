import pytest

from app.pipeline.request import RequestContext, WireFormat
from app.server.routes.inference import _reasoning_effort  # pyright: ignore[reportPrivateUsage]


def context_for(
    target_format: WireFormat,
    payload: dict[str, object],
) -> RequestContext:
    return RequestContext(
        inbound_format=WireFormat.ANTHROPIC_MESSAGES,
        requested_model="model",
        payload=payload,
        target_format=target_format,
    )


@pytest.mark.parametrize(
    ("target_format", "payload", "expected"),
    [
        (WireFormat.OPENAI_RESPONSES, {"reasoning": {"effort": "high"}}, "high"),
        (WireFormat.OPENAI_RESPONSES, {}, None),
        (WireFormat.OPENAI_CHAT_COMPLETIONS, {"reasoning_effort": "high"}, "high"),
        (WireFormat.OPENAI_CHAT_COMPLETIONS, {"reasoning_effort": "none"}, "none"),
        (WireFormat.OPENAI_CHAT_COMPLETIONS, {}, None),
        (WireFormat.COMMANDCODE, {"params": {"reasoning_effort": "high"}}, "high"),
        (WireFormat.COMMANDCODE, {"params": {"reasoning_effort": "none"}}, "none"),
        (WireFormat.COMMANDCODE, {}, None),
        (
            WireFormat.ANTHROPIC_MESSAGES,
            {"thinking": {"type": "disabled"}},
            "none",
        ),
        (WireFormat.ANTHROPIC_MESSAGES, {}, None),
    ],
)
def test_reasoning_effort_observation_reads_each_provider_bound_wire(
    target_format: WireFormat,
    payload: dict[str, object],
    expected: str | None,
) -> None:
    assert _reasoning_effort(context_for(target_format, payload)) == expected
