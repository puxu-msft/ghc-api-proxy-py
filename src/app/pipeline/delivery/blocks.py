"""Block-level delivery.

The project requires complete Anthropic content blocks as the delivery unit.
Before the first complete block the client sees no success headers, no message_start, no bytes.

`client_delivery.buffering_policy` chooses how much more than one block is held back.
`buffer_cap_bytes` bounds what is held.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

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


class DeliveryUnit(Protocol):
    """What the buffer needs to know about the thing it is holding, and nothing else.

    Two legs produce different units. The translating leg produces `CompletedBlock`, an Anthropic content block. The direct Responses leg produces a run of upstream's own events, which is not Anthropic-shaped at all — `direct-passthrough/spec.md` §10 forbids that leg reusing `CompletedBlock`, because doing so makes one Anthropic `kind` field carry three unrelated jobs at once: the payload, the release predicate, and the log's classification.

    So the buffer asks for exactly the two facts its policies turn on, and neither of them names a format.
    """

    @property
    def size_bytes(self) -> int:
        """What holding this costs, for `buffer_cap_bytes`. Each leg measures what it actually holds."""
        ...

    @property
    def requires_client_action(self) -> bool:
        """Whether this unit is what `until-tool-use` has been waiting for.

        The question is whether the client must submit something — a tool output, an approval — before the model's turn can continue. On the Anthropic side that is a `tool_use` block. On the Responses side `spec.md` §7.1 answers it from the item's own execution semantics, because the same `tool_search_call` gives opposite answers depending on whether the server or the client runs it.
        """
        ...


@dataclass(frozen=True, slots=True)
class CompletedBlock:
    """One fully materialised Anthropic content block."""

    index: int
    kind: str
    payload: dict[str, Any]

    @property
    def size_bytes(self) -> int:
        return len(repr(self.payload).encode())

    @property
    def requires_client_action(self) -> bool:
        """`tool_use` is the Anthropic spelling of "the client owes the model something"."""
        return self.kind == TOOL_USE


class BlockBuffer[UnitT: DeliveryUnit = CompletedBlock]:
    """Holds completed units until the policy says they may go out.

    The cap is the only bound on how much this proxy holds for one response — byte-level global accounting was removed on 2026-08-19 in favour of `proactive_rate_limiter.max_inflight`, which bounds how many of these exist at once. So this one has to actually hold.

    Nothing outside reads or writes it. It is set once at construction and kept private: a module that could raise the cap, or add to `_held` directly, would be a second answer to "how much may this request hold" and neither answer would be the enforced one.

    Generic over the unit since 2026-08-31. It used to read `block.kind == TOOL_USE` directly, which meant the buffer could only ever hold Anthropic blocks — and the direct Responses leg, whose unit is a run of upstream's own events, had no way to use it without first translating into a shape it exists to avoid.
    """

    __slots__ = ("_cap_bytes", "_held", "_held_bytes", "_policy", "_released_after_tool_use")

    def __init__(self, policy: BufferingPolicy = "block", cap_bytes: int = 0) -> None:
        self._policy: BufferingPolicy = policy
        self._cap_bytes = cap_bytes
        self._held: list[UnitT] = []
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

    def add(self, block: UnitT) -> tuple[UnitT, ...]:
        """Take one completed unit and return whatever may now be delivered.

        The cap is checked *before* the unit goes in, so the buffer never holds more than it is allowed to even for the instant before raising.
        """
        self._enforce_cap(incoming=block.size_bytes)
        self._held.append(block)
        self._held_bytes += block.size_bytes

        if self.policy == "full":
            return ()
        if self.policy == "block":
            return self._drain()
        # until-tool-use: hold everything until the client is owed something, then stream per unit.
        if self._released_after_tool_use:
            return self._drain()
        if block.requires_client_action:
            self._released_after_tool_use = True
            return self._drain()
        return ()

    def finish(self) -> tuple[UnitT, ...]:
        """Release whatever is still held because the response ended."""
        return self._drain()

    def _drain(self) -> tuple[UnitT, ...]:
        drained = tuple(self._held)
        self._held.clear()
        self._held_bytes = 0
        return drained

    def enforce_cap_over(self, held_elsewhere: int) -> None:
        """Check the cap against bytes held outside this buffer as well.

        The buffer is not the only thing holding a response. On a direct passthrough leg the assembler queues events that have not become a deliverable unit yet, and `direct-passthrough/spec.md` §8 counts those first. Routing them through the same check keeps one answer to "how much may this request hold" rather than two.
        """
        self._enforce_cap(incoming=held_elsewhere)

    def _enforce_cap(self, *, incoming: int) -> None:
        if self._cap_bytes <= 0:
            return
        projected = self._held_bytes + incoming
        if projected > self._cap_bytes:
            raise BufferCapExceeded(projected, self._cap_bytes)


@dataclass(slots=True)
class DeliverySession[UnitT: DeliveryUnit = CompletedBlock]:
    """The single downstream writer.

    Tracks whether the response has been opened.
    The invariant is not that we buffered, but that nothing reached the client before unit one.
    """

    buffer: BlockBuffer[UnitT]
    started: bool = False
    delivered: list[UnitT] = field(default_factory=lambda: list[UnitT]())

    @property
    def committed_count(self) -> int:
        return len(self.delivered)

    def offer(self, block: UnitT) -> tuple[UnitT, ...]:
        ready = self.buffer.add(block)
        return self._commit(ready)

    def finish(self) -> tuple[UnitT, ...]:
        return self._commit(self.buffer.finish())

    def _commit(self, ready: Iterable[UnitT]) -> tuple[UnitT, ...]:
        blocks = tuple(ready)
        if blocks:
            self.started = True
            self.delivered.extend(blocks)
        return blocks

    def start_response(self) -> None:
        """Open the downstream response explicitly.

        Refused before a unit is ready.
        That is what keeps success headers from going out ahead of usable content.
        """
        if self.started:
            raise ResponseAlreadyStarted("response has already started")
        raise DeliveryError("cannot start the response before a complete block is ready")
