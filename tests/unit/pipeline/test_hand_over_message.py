"""What the hand-over tells the client a turn ended of.

The field had one assertion before this file — `assert handed["input"]["message"]` at `tests/int/test_pipeline_app.py:3127`, a truthiness check whose fixture raises a hand-built exception that carries a message. Nothing had discriminating power over the *content*, which is how the field stayed at `str(error)` long enough for a user to read one in a transcript and ask for better.

Most cases here are shapes the investigation measured (`.dev/docs/upstream/retry-and-continuation/reports/260823-handover-error-shapes.md`); the two that are not say so in their own docstrings.

- The two h2 `repr`s are the only two the MCP server's journal held when it was read on 2026-08-23 (`~/.claude/plugins/data/ghc-api-proxy-helper-my-marketplace/auto-retry.jsonl`, 4 records: three `ConnectionTerminated`, one `StreamReset`). That is a snapshot of one file, not a frequency.
- The chain is built the way the installed stack builds it: httpcore raises `RemoteProtocolError(event)` with the h2 event object itself (`httpcore2/_async/http2.py:314`), and httpx re-raises `mapped_exc(str(exc)) from exc` (`httpx2/_transports/default.py:113-114`), so the object survives one link down while only its text reaches the top.

They pin the distinctions a reader has to be able to draw, not the exact sentence: an assertion on the whole string would go red every time the wording is improved, which is the opposite of what this field needs.
"""

import h2.errors
import h2.events
import httpcore2
import httpx2
import pytest
from anyio import BrokenResourceError
from h2.exceptions import ProtocolError as H2ProtocolError
from h2.exceptions import StreamClosedError
from openai import APIConnectionError

from app.pipeline.hand_over import interruption_message

REQUEST_ID = "a1b2c3d4"


def message(error: BaseException | None, *, stop_reason: str = "", attempt_count: int = 1) -> str:
    return interruption_message(
        error=error,
        stop_reason=stop_reason,
        request_id=REQUEST_ID,
        attempt_count=attempt_count,
    )


def through_httpx(event: object) -> httpx2.RemoteProtocolError:
    """The exception as the real stack assembles it, event object and all."""
    inner = httpcore2.RemoteProtocolError(event)
    try:
        try:
            raise inner
        except Exception as exc:
            raise httpx2.RemoteProtocolError(str(exc)) from exc
    except httpx2.RemoteProtocolError as mapped:
        return mapped


def goaway() -> httpx2.RemoteProtocolError:
    event = h2.events.ConnectionTerminated()
    event.error_code = h2.errors.ErrorCodes.NO_ERROR
    event.last_stream_id = 2147483647
    return through_httpx(event)


def stream_reset() -> httpx2.RemoteProtocolError:
    event = h2.events.StreamReset(stream_id=1011)
    event.error_code = h2.errors.ErrorCodes.CANCEL
    event.remote_reset = True
    return through_httpx(event)


def test_goaway_says_what_the_error_code_meant() -> None:
    """The old field ended at `error_code:0`. The word that number stands for is on the event, just not in its `repr`."""
    text = message(goaway())
    assert "NO_ERROR" in text
    assert "GOAWAY" in text
    # The original text is kept beside the gloss rather than replaced by it: the gloss explains the account, it is not the account.
    assert "<ConnectionTerminated error_code:0, last_stream_id:2147483647" in text
    assert "httpx2.RemoteProtocolError" in text


def test_stream_reset_is_distinguishable_from_a_graceful_shutdown() -> None:
    """The two shapes in the journal are told apart by an `error_code` the reader cannot decode.

    A remote `CANCEL` on one stream is upstream dropping this request; a `NO_ERROR` GOAWAY is upstream closing the whole connection politely. Both used to arrive as an opaque `repr`.
    """
    reset = message(stream_reset())
    assert "CANCEL" in reset
    assert "RST_STREAM" in reset
    assert "from upstream" in reset
    assert "1011" in reset
    assert "GOAWAY" not in reset
    # The pairing matters as much as either half: the two shapes must not be describable by the same words.
    assert "CANCEL" not in message(goaway())
    assert "RST_STREAM" not in message(goaway())


def test_a_reset_this_proxy_sent_is_not_reported_as_upstreams() -> None:
    event = h2.events.StreamReset(stream_id=7)
    event.error_code = h2.errors.ErrorCodes.CANCEL
    event.remote_reset = False
    text = message(through_httpx(event))
    assert "sent by this proxy" in text
    assert "from upstream" not in text


@pytest.mark.parametrize(
    "error",
    [
        httpx2.ReadError(""),
        httpx2.ConnectError(""),
        httpx2.RemoteProtocolError(""),
        httpx2.ReadTimeout(""),
        httpx2.WriteError(""),
    ],
)
def test_an_error_with_no_text_still_says_what_it_was(error: httpx2.HTTPError) -> None:
    """`str()` on every one of these can be empty, and an empty message is the one value that tells a reader nothing."""
    text = message(error)
    assert type(error).__name__ in text
    assert text.strip()


def test_a_real_connection_reset_reports_the_link_that_knows_why() -> None:
    """The shape a reset actually has: four links, and only the last one says anything.

    Measured against a real socket on 2026-08-23 (`260823-handover-error-shapes.md` §2.2(d)): `httpx2.ReadError('')` → `httpcore2.ReadError('')` → `anyio.BrokenResourceError('')` → `ConnectionResetError('[Errno 104] Connection reset by peer')`. `str(error)` on its own produced an empty field for this. How often it happens is not something this file knows — the report records the shape, not a rate.
    """
    try:
        try:
            try:
                try:
                    raise ConnectionResetError(104, "Connection reset by peer")
                except OSError as os_error:
                    raise BrokenResourceError from os_error
            except BrokenResourceError as broken:
                raise httpcore2.ReadError("") from broken
        except httpcore2.ReadError as core:
            raise httpx2.ReadError("") from core
    except httpx2.ReadError as read_error:
        text = message(read_error)
    assert "httpx2.ReadError" in text
    assert "Connection reset by peer" in text
    # `httpcore2.ReadError` is the one link that earns nothing: same class name as the link above it, and no text of its own.
    assert "httpcore2" not in text


def test_a_link_that_only_has_a_type_to_offer_still_offers_it() -> None:
    """Dropping a link because its text was already shown drops its class name with it.

    `RuntimeError('permission denied') from PermissionError('permission denied')` — an independent review built this against a version that kept only new text, and got the `RuntimeError` alone. The word that says what kind of failure it was is the inner class name, and it is the only thing that link had.
    """
    try:
        try:
            raise PermissionError("permission denied")
        except PermissionError as denied:
            raise RuntimeError("permission denied") from denied
    except RuntimeError as outer:
        text = message(outer)
    assert "RuntimeError" in text
    assert "PermissionError" in text
    assert text.count("permission denied") == 1


def test_an_explicit_cause_is_followed_even_when_it_is_falsy() -> None:
    """Python's rule for an explicit cause is `is not None`, not truthiness, and an exception may define `__bool__`.

    Constructed, not observed — but the delivery `try` catches whatever a framer raises, so a custom exception type is not structurally excluded.
    """

    class FalsyCause(Exception):
        def __bool__(self) -> bool:
            return False

    outer = RuntimeError("outer")
    outer.__cause__ = FalsyCause("the actual cause")
    outer.__context__ = LookupError("incidental context")
    text = message(outer)
    assert "the actual cause" in text
    assert "incidental context" not in text


def test_a_chain_cut_short_says_it_was_cut() -> None:
    """A chain that ended and a chain that hit the bound read the same otherwise."""
    deepest: BaseException = ConnectionResetError(104, "Connection reset by peer")
    for _ in range(6):
        try:
            try:
                raise deepest
            except BaseException as inner:
                raise RuntimeError from inner
        except RuntimeError as wrapped:
            deepest = wrapped
    text = message(deepest)
    assert "chain continues" in text
    assert "Connection reset by peer" not in text


def test_a_wrapper_with_a_fixed_message_does_not_hide_the_cause() -> None:
    """A defensive case, not an observed one.

    `openai.APIConnectionError` does **not** reach the hand-over today: the delivery path reads `httpx2.Response.aiter_bytes()` directly and header-stage SDK errors are normalised away before they leave `GhcApiClient` (`260823-handover-error-shapes.md` §2.3, code-read). It is here because it is the sharpest example of the shape the chain walk exists for — a wrapper whose own text is a constant — and because nothing stops a future path from wrapping one.
    """
    try:
        try:
            raise goaway()
        except Exception as exc:
            raise APIConnectionError(request=httpx2.Request("POST", "https://upstream.invalid/x")) from exc
    except APIConnectionError as wrapped:
        text = message(wrapped)
    assert "openai.APIConnectionError" in text
    assert "ConnectionTerminated" in text
    assert "NO_ERROR" in text


def test_a_bare_stream_id_is_not_passed_off_as_a_message() -> None:
    """`StreamClosedError(3)` stringifies to `3`, which reads like something upstream said.

    Its `__init__` sets `self.stream_id` without calling `super().__init__`, but the argument is already in `args` by then (`260823-handover-error-shapes.md` §2.2(g)).
    """
    text = message(StreamClosedError(3))
    assert "StreamClosedError" in text
    assert "stream 3" in text


def test_an_error_that_says_nothing_at_all_is_still_named() -> None:
    """A bare `h2.ProtocolError` has an empty `str()` and no cause chain at all."""
    text = message(H2ProtocolError())
    assert "h2.exceptions.ProtocolError" in text
    assert text.strip()


def test_the_same_text_is_not_repeated_down_the_chain() -> None:
    """httpx re-raises httpcore's message unchanged, so the naive chain prints one event twice."""
    assert message(goaway()).count("ConnectionTerminated error_code:0") == 1


def test_a_turn_cut_short_says_more_than_its_category() -> None:
    """`category` already carries the stop reason. A `message` equal to it spends a field to repeat one."""
    text = message(None, stop_reason="max_tokens")
    assert text != "max_tokens"
    assert "max_tokens" in text
    assert "upstream" in text


def test_the_line_carries_the_key_that_reaches_the_proxys_own_log() -> None:
    """The MCP server's journal records the client's identity and nothing that joins to this proxy's request trace."""
    text = message(goaway(), attempt_count=3)
    assert REQUEST_ID in text
    assert "attempt 3" in text


def test_a_long_error_body_is_cut_and_says_so() -> None:
    text = message(httpx2.HTTPError("x" * 400))
    assert len(text) < 400
    assert "more chars" in text
