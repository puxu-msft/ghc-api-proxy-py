from typing import Any

import pytest

from app.pipeline.delivery import (
    BlockBuffer,
    BufferCapExceeded,
    CompletedBlock,
    DeliveryError,
    DeliverySession,
)
from app.pipeline.translation_driver.content import (
    ReasoningContent,
    ReasoningSummaryPart,
)


def block(index: int, kind: str = "text", size: int = 10) -> CompletedBlock:
    payload: dict[str, Any] = {"type": kind, "text": "x" * size}
    return CompletedBlock(index=index, kind=kind, payload=payload)


def test_block_policy_releases_each_block_as_it_completes() -> None:
    buffer = BlockBuffer(policy="block")
    assert [b.index for b in buffer.add(block(0))] == [0]
    assert [b.index for b in buffer.add(block(1))] == [1]
    assert buffer.finish() == ()


def test_full_policy_holds_everything_until_the_response_ends() -> None:
    buffer = BlockBuffer(policy="full")
    assert buffer.add(block(0)) == ()
    assert buffer.add(block(1)) == ()
    assert [b.index for b in buffer.finish()] == [0, 1]


def test_full_policy_holds_a_tool_call_too() -> None:
    # A tool block releases under until-tool-use but must not under full.
    # Without this case the two policies are indistinguishable on text-only responses.
    buffer = BlockBuffer(policy="full")
    assert buffer.add(block(0)) == ()
    assert buffer.add(block(1, kind="tool_use")) == ()
    assert buffer.add(block(2)) == ()
    assert [b.index for b in buffer.finish()] == [0, 1, 2]


def test_until_tool_use_holds_until_a_tool_call_appears() -> None:
    buffer = BlockBuffer(policy="until-tool-use")
    assert buffer.add(block(0)) == ()
    assert buffer.add(block(1)) == ()
    # The tool block releases everything held so far, itself included and in order.
    released = buffer.add(block(2, kind="tool_use"))
    assert [b.index for b in released] == [0, 1, 2]


def test_until_tool_use_streams_per_block_after_the_first_tool_call() -> None:
    buffer = BlockBuffer(policy="until-tool-use")
    buffer.add(block(0))
    buffer.add(block(1, kind="tool_use"))
    assert [b.index for b in buffer.add(block(2))] == [2]


def test_until_tool_use_without_a_tool_call_still_delivers_at_the_end() -> None:
    buffer = BlockBuffer(policy="until-tool-use")
    buffer.add(block(0))
    buffer.add(block(1))
    assert [b.index for b in buffer.finish()] == [0, 1]


def test_block_policy_releases_one_assembler_batch_together() -> None:
    buffer = BlockBuffer(policy="block")

    released = buffer.add_many((block(0), block(1)))

    assert [b.index for b in released] == [0, 1]
    assert buffer.held_count == 0


def test_full_policy_holds_one_assembler_batch_together() -> None:
    buffer = BlockBuffer(policy="full")

    assert buffer.add_many((block(0), block(1))) == ()

    assert [b.index for b in buffer.finish()] == [0, 1]


def test_until_tool_use_decides_from_the_whole_assembler_batch() -> None:
    buffer = BlockBuffer(policy="until-tool-use")
    buffer.add(block(0))

    released = buffer.add_many((block(1), block(2, kind="tool_use")))

    assert [b.index for b in released] == [0, 1, 2]
    assert [b.index for b in buffer.add_many((block(3), block(4)))] == [3, 4]


def test_an_empty_batch_does_not_drain_what_an_earlier_batch_held() -> None:
    buffer = BlockBuffer(policy="until-tool-use")
    buffer.add(block(0))

    assert buffer.add_many(()) == ()
    assert buffer.held_count == 1
    assert [b.index for b in buffer.finish()] == [0]


def test_cap_rejects_a_whole_batch_without_changing_held_state() -> None:
    existing = block(0, size=1)
    first = block(1, size=1)
    second = block(2, size=1)
    cap = existing.size_bytes + first.size_bytes
    buffer = BlockBuffer(policy="full", cap_bytes=cap)
    buffer.add(existing)
    held_before = buffer.held_bytes

    with pytest.raises(BufferCapExceeded) as raised:
        buffer.add_many((first, second))

    assert raised.value.held == existing.size_bytes + first.size_bytes + second.size_bytes
    assert buffer.held_bytes == held_before
    assert buffer.held_count == 1
    assert buffer.finish() == (existing,)


def test_rejected_client_action_batch_does_not_latch_until_tool_use_open() -> None:
    first = block(0, size=1)
    later = block(2, size=1)
    cap = first.size_bytes + later.size_bytes
    rejected = block(1, kind="tool_use", size=cap * 2)
    buffer = BlockBuffer(policy="until-tool-use", cap_bytes=cap)
    assert buffer.add(first) == ()

    with pytest.raises(BufferCapExceeded):
        buffer.add_many((rejected,))

    assert buffer.add(later) == ()
    assert buffer.held_count == 2
    assert [b.index for b in buffer.finish()] == [0, 2]


def test_cap_abandons_the_response_rather_than_trimming() -> None:
    # Trimming or spilling would deliver something the model did not produce.
    buffer = BlockBuffer(policy="full", cap_bytes=60)
    buffer.add(block(0, size=10))
    with pytest.raises(BufferCapExceeded) as raised:
        buffer.add(block(1, size=200))
    assert raised.value.cap == 60


def test_cap_counts_typed_reasoning_state_held_beside_the_wire_payload() -> None:
    payload = {"type": "thinking", "thinking": "x", "signature": "carrier"}
    reasoning = ReasoningContent(
        visible_text="x",
        source_format="openai-responses",
        summary_parts=(
            ReasoningSummaryPart("x", {"large": "y" * 1000}),
        ),
    )
    reasoning_block = CompletedBlock(
        index=0,
        kind="thinking",
        payload=payload,
        reasoning=reasoning,
    )
    payload_only = len(repr(payload).encode())
    assert reasoning_block.size_bytes > payload_only + 1000

    buffer = BlockBuffer(policy="full", cap_bytes=payload_only + 100)
    with pytest.raises(BufferCapExceeded):
        buffer.add(reasoning_block)


def test_cap_of_zero_disables_the_guard() -> None:
    buffer = BlockBuffer(policy="full", cap_bytes=0)
    for index in range(20):
        buffer.add(block(index, size=1000))
    assert buffer.held_count == 20


def test_block_policy_holds_almost_nothing_so_the_cap_does_not_bite() -> None:
    buffer = BlockBuffer(policy="block", cap_bytes=80)
    for index in range(50):
        buffer.add(block(index, size=10))
    assert buffer.held_bytes == 0


def test_session_does_not_start_before_a_block_is_ready() -> None:
    session = DeliverySession(buffer=BlockBuffer(policy="full"))
    session.offer(block(0))
    # Nothing may reach the client yet, so the response must not be open.
    assert session.started is False
    assert session.committed_count == 0
    with pytest.raises(DeliveryError, match="before a complete block"):
        session.start_response()


def test_session_starts_once_the_first_block_is_delivered() -> None:
    session = DeliverySession(buffer=BlockBuffer(policy="block"))
    delivered = session.offer(block(0))
    assert [b.index for b in delivered] == [0]
    assert session.started is True
    assert session.committed_count == 1


def test_session_commits_one_offered_batch_in_order() -> None:
    session = DeliverySession(buffer=BlockBuffer(policy="block"))

    delivered = session.offer_many((block(0), block(1)))

    assert [b.index for b in delivered] == [0, 1]
    assert [b.index for b in session.delivered] == [0, 1]
    assert session.committed_count == 2


def test_session_commits_in_order_across_the_hold_and_the_release() -> None:
    session = DeliverySession(buffer=BlockBuffer(policy="until-tool-use"))
    session.offer(block(0))
    session.offer(block(1))
    session.offer(block(2, kind="tool_use"))
    session.offer(block(3))
    session.finish()
    assert [b.index for b in session.delivered] == [0, 1, 2, 3]


def test_finishing_an_empty_response_delivers_nothing_and_does_not_start() -> None:
    session = DeliverySession(buffer=BlockBuffer(policy="full"))
    assert session.finish() == ()
    assert session.started is False
