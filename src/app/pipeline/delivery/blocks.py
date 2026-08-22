"""Block-level delivery.

The project requires complete Anthropic content blocks as the delivery unit.
Before the first complete block the client sees no success headers, no message_start, no bytes.

`client_delivery.buffering_policy` chooses how much more than one block is held back.
`buffer_cap_bytes` bounds what is held.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.config.schema import BufferingPolicy

# The kinds a `CompletedBlock` can be. Anthropic's words, because a block *is* an Anthropic content block by definition (see `CompletedBlock`) whichever upstream it was assembled from — so these are the internal vocabulary rather than one format's, and they belong beside the type they describe.
#
# `TOOL_USE` used to be spelled three times: here as `TOOL_USE_KIND`, in the assembler as `TOOL_USE`, and again in `stream`. Three names for one string is three places for them to drift.
TEXT = "text"
THINKING = "thinking"
TOOL_USE = "tool_use"


class DeliveryError(RuntimeError):
    """A delivery-side failure. Distinct from an upstream one, which is retryable."""


class BufferCapExceeded(DeliveryError):
    """Held bytes passed `buffer_cap_bytes`, so the response is abandoned.

    Abandoning is the spec's choice.
    The guard bounds memory; trimming or spilling would deliver what the model did not produce.
    """

    def __init__(self, held: int, cap: int) -> None:
        super().__init__(f"buffered {held} bytes exceeds the {cap} byte cap")
        self.held = held
        self.cap = cap


class ResponseAlreadyStarted(DeliveryError):
    """Something tried to open the downstream response twice."""


@dataclass(frozen=True, slots=True)
class CompletedBlock:
    """One fully materialised Anthropic content block."""

    index: int
    kind: str
    payload: dict[str, Any]

    @property
    def size_bytes(self) -> int:
        return len(repr(self.payload).encode())


class BlockBuffer:
    """Holds completed blocks until the policy says they may go out.

    The cap is the only bound on how much this proxy holds for one response — byte-level global accounting was removed on 2026-08-19 in favour of `proactive_rate_limiter.max_inflight`, which bounds how many of these exist at once. So this one has to actually hold.

    Nothing outside reads or writes it. It is set once at construction and kept private: a module that could raise the cap, or add to `_held` directly, would be a second answer to "how much may this request hold" and neither answer would be the enforced one.
    """

    __slots__ = ("_cap_bytes", "_held", "_held_bytes", "_policy", "_released_after_tool_use")

    def __init__(self, policy: BufferingPolicy = "block", cap_bytes: int = 0) -> None:
        self._policy: BufferingPolicy = policy
        self._cap_bytes = cap_bytes
        self._held: list[CompletedBlock] = []
        # Kept as a running total rather than summed on demand. Summing per `add` is quadratic over a response, and the cap has to be checked on every one of them.
        self._held_bytes = 0
        self._released_after_tool_use = False

    @property
    def policy(self) -> BufferingPolicy:
        return self._policy

    @property
    def held_bytes(self) -> int:
        return self._held_bytes

    @property
    def held_count(self) -> int:
        return len(self._held)

    def add(self, block: CompletedBlock) -> tuple[CompletedBlock, ...]:
        """Take one completed block and return whatever may now be delivered.

        The cap is checked *before* the block goes in, so the buffer never holds more than it is allowed to even for the instant before raising.
        """
        self._enforce_cap(incoming=block.size_bytes)
        self._held.append(block)
        self._held_bytes += block.size_bytes

        if self.policy == "full":
            return ()
        if self.policy == "block":
            return self._drain()
        # until-tool-use: hold everything until a tool call appears, then stream per block.
        if self._released_after_tool_use:
            return self._drain()
        if block.kind == TOOL_USE:
            self._released_after_tool_use = True
            return self._drain()
        return ()

    def finish(self) -> tuple[CompletedBlock, ...]:
        """Release whatever is still held because the response ended."""
        return self._drain()

    def _drain(self) -> tuple[CompletedBlock, ...]:
        drained = tuple(self._held)
        self._held.clear()
        self._held_bytes = 0
        return drained

    def _enforce_cap(self, *, incoming: int) -> None:
        if self._cap_bytes <= 0:
            return
        projected = self._held_bytes + incoming
        if projected > self._cap_bytes:
            raise BufferCapExceeded(projected, self._cap_bytes)


@dataclass(slots=True)
class DeliverySession:
    """The single downstream writer.

    Tracks whether the response has been opened.
    The invariant is not that we buffered, but that nothing reached the client before block one.
    """

    buffer: BlockBuffer
    started: bool = False
    delivered: list[CompletedBlock] = field(default_factory=lambda: list[CompletedBlock]())

    @property
    def committed_count(self) -> int:
        return len(self.delivered)

    def offer(self, block: CompletedBlock) -> tuple[CompletedBlock, ...]:
        ready = self.buffer.add(block)
        return self._commit(ready)

    def finish(self) -> tuple[CompletedBlock, ...]:
        return self._commit(self.buffer.finish())

    def _commit(self, ready: Iterable[CompletedBlock]) -> tuple[CompletedBlock, ...]:
        blocks = tuple(ready)
        if blocks:
            self.started = True
            self.delivered.extend(blocks)
        return blocks

    def start_response(self) -> None:
        """Open the downstream response explicitly.

        Refused before a block is ready.
        That is what keeps success headers from going out ahead of usable content.
        """
        if self.started:
            raise ResponseAlreadyStarted("response has already started")
        raise DeliveryError("cannot start the response before a complete block is ready")
