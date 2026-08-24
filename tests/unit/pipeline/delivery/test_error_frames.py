"""What a mid-stream failure looks like on the wire, per leg.

Three things are pinned here and they fail in different ways.

**Shape.** The Anthropic leg's error frame must stay nested, with no `message` at the top level. That is not a style preference: Claude Code decides whether to retry by substring-matching `'"type":"overloaded_error"'` against the serialised error object, and it only builds that string when the object has no top-level `message` to take instead. Flatten this and the retry disappears silently. `.dev/docs/error-envelope/spec.md` §6.3, measured against Claude Code 2.1.241.

**Wiring.** A table can be correct and unused. The behaviour tests below drive real failures through `stream_delivery` and read what actually comes out, which is what separates "the mapping says `api_error`" from "the client receives `api_error`".

**Direction.** Generic delivery must not know any concrete format. It used to reach into the Anthropic table to spell the type, which on a Responses leg produced a category name from a dialect that leg does not speak.
"""

import ast
from pathlib import Path
from typing import Any

import orjson
import pytest

from app.errors import (
    ANTHROPIC_ERROR_TYPES,
    ErrorCategory,
    ErrorInfo,
)
from app.pipeline.delivery.formats.anthropic_messages import AnthropicFramer, error_frame


def _framer() -> AnthropicFramer:
    return AnthropicFramer(message_id="msg_1", model="claude-model")


def _payload(frame: bytes) -> dict[str, Any]:
    return orjson.loads(frame.decode().split("data: ", 1)[1])


def _info(category: ErrorCategory, *, code: str = "c") -> ErrorInfo:
    return ErrorInfo(category=category, message="something went wrong", status_code=500, code=code)


def test_the_anthropic_error_frame_is_nested_and_has_no_top_level_message() -> None:
    """The shape Claude Code's retry match depends on.

    Asserted as structure rather than against a literal string, because the literal would also pass for a frame that happens to serialise the same way today. What must hold is: the type lives inside `error`, and there is no `message` beside it at the top. A flattened frame satisfies neither.
    """
    payload = _payload(_framer().error(_info(ErrorCategory.OVERLOADED)))

    assert payload["type"] == "error"
    assert "message" not in payload, (
        "a top-level message is what makes the client take it instead of serialising the object"
    )
    assert isinstance(payload["error"], dict)
    assert payload["error"]["type"] == "overloaded_error"
    assert payload["error"]["message"]


def test_the_retry_match_a_client_performs_finds_what_it_looks_for() -> None:
    """The client's own predicate, run against this frame.

    Not a re-implementation of the client — it is one substring test, and writing it out is what makes the dependency visible at the place that could break it. `.dev/docs/error-envelope/reports/260824-claude-code-sse-retry-behavior.md` has the decompiled source this is taken from.

    Serialised without spaces here; the client parses and re-serialises before matching, so whitespace on the wire does not decide it. What decides it is whether the object it serialises is the whole error object or just a message.
    """
    payload = _payload(_framer().error(_info(ErrorCategory.OVERLOADED)))

    # What the client builds when there is no top-level `message` to take.
    serialised = orjson.dumps(payload).decode()

    assert '"type":"overloaded_error"' in serialised


@pytest.mark.parametrize(
    "category, spelled",
    [
        (ErrorCategory.TIMEOUT, "timeout_error"),
        (ErrorCategory.NETWORK, "api_error"),
        (ErrorCategory.INTERNAL, "api_error"),
        (ErrorCategory.UPSTREAM, "api_error"),
        (ErrorCategory.OVERLOADED, "overloaded_error"),
        (ErrorCategory.RATE_LIMIT, "rate_limit_error"),
    ],
)
def test_the_leg_spells_the_category_in_its_own_vocabulary(
    category: ErrorCategory, spelled: str
) -> None:
    """Transcribed by hand from the spec, not read from the table under test.

    Four of these collapse onto `api_error` and that is the point of listing them separately: the loss is real, it is Anthropic's own vocabulary that has no finer word, and a test generated from the mapping would have agreed with any mapping at all.
    """
    payload = _payload(_framer().error(_info(category)))

    assert payload["error"]["type"] == spelled


def test_the_code_survives_because_it_is_the_only_channel_left() -> None:
    """`INTERNAL` and `UPSTREAM` are indistinguishable by type, and by status too — the status was sent long ago.

    So a client transcript can only tell "this proxy broke" from "upstream broke" by `code`. Asserted as a difference between two frames rather than as one value, because the property is that they differ.
    """
    ours = _payload(_framer().error(_info(ErrorCategory.INTERNAL, code="proxy_delivery_failed")))
    theirs = _payload(_framer().error(_info(ErrorCategory.UPSTREAM, code="upstream_stream_failed")))

    assert ours["error"]["type"] == theirs["error"]["type"] == "api_error"
    assert ours["error"]["code"] != theirs["error"]["code"]


def test_a_frame_carries_no_code_when_there_is_none_to_carry() -> None:
    """Absence rather than `null`, which is the legacy chain's shape and what a client that already reads these expects."""
    payload = _payload(_framer().error(ErrorInfo(category=ErrorCategory.UPSTREAM, message="m", status_code=502)))

    assert "code" not in payload["error"]


def test_error_frame_and_the_json_body_are_one_object_on_this_leg() -> None:
    """The Anthropic leg is the one dialect where they really are the same shape, so they are built once.

    Pinned because the two could drift apart with nothing failing: each has its own tests, and both would keep passing while a client met two spellings of one contract.
    """
    from app.pipeline.delivery.formats.errors import write_error

    info = _info(ErrorCategory.RATE_LIMIT, code="rate_limited")

    assert _payload(_framer().error(info)) == write_error(info, wire_format="anthropic-messages")
    assert error_frame(info).data == write_error(info, wire_format="anthropic-messages")


def test_generic_delivery_does_not_know_any_concrete_format() -> None:
    """The direction that made the whole change necessary.

    `stream.py` serves every leg. It used to spell the error type itself by reading the Anthropic table, so a Responses leg received a word from a dialect it does not speak. Now it names a category and the framer spells it.

    Read statically rather than by import graph, because the graph would also be clean if the reach were dynamic — and what is being prevented is someone writing the import back, which is a line in this file.
    """
    source = Path("src/app/pipeline/delivery/stream.py").read_text()
    tree = ast.parse(source)

    reached = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "delivery.formats" in node.module
    ]

    assert not reached, f"generic delivery reached into a format: {[n.module for n in reached]}"
    assert "ANTHROPIC_ERROR_TYPES" not in source, (
        "spelling a leg's vocabulary here is the same reach by another route"
    )


def test_every_category_has_a_spelling_on_this_leg() -> None:
    """A subset check would pass with a row missing, and a missing row is a `KeyError` on the one path whose job is to report failures."""
    assert set(ANTHROPIC_ERROR_TYPES) == set(ErrorCategory)
