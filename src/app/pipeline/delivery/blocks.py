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

TOOL_USE_KIND = "tool_use"


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


@dataclass(slots=True)
class BlockBuffer:
    """Holds completed blocks until the policy says they may go out."""

    policy: BufferingPolicy = "block"
    cap_bytes: int = 0
    _held: list[CompletedBlock] = field(default_factory=lambda: list[CompletedBlock]())
    _released_after_tool_use: bool = False

    @property
    def held_bytes(self) -> int:
        return sum(block.size_bytes for block in self._held)

    @property
    def held_count(self) -> int:
        return len(self._held)

    def add(self, block: CompletedBlock) -> tuple[CompletedBlock, ...]:
        """Take one completed block and return whatever may now be delivered."""
        self._held.append(block)
        self._enforce_cap()

        if self.policy == "full":
            return ()
        if self.policy == "block":
            return self._drain()
        # until-tool-use: hold everything until a tool call appears, then stream per block.
        if self._released_after_tool_use:
            return self._drain()
        if block.kind == TOOL_USE_KIND:
            self._released_after_tool_use = True
            return self._drain()
        return ()

    def finish(self) -> tuple[CompletedBlock, ...]:
        """Release whatever is still held because the response ended."""
        return self._drain()

    def _drain(self) -> tuple[CompletedBlock, ...]:
        drained = tuple(self._held)
        self._held.clear()
        return drained

    def _enforce_cap(self) -> None:
        if self.cap_bytes <= 0:
            return
        held = self.held_bytes
        if held > self.cap_bytes:
            raise BufferCapExceeded(held, self.cap_bytes)


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
