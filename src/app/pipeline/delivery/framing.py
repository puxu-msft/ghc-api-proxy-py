"""What delivery needs in order to write a block out, whichever protocol the client asked in.

The mirror of `BlockAssembler`. That one turns an upstream's events into blocks; this one turns blocks into a client's events. They are separate questions and a route can answer them differently: a request that arrives as Anthropic Messages and is translated to a Responses upstream is assembled by the Responses assembler and framed by the Anthropic framer, because the upstream leg and the client leg are two different protocols.

Getting that backwards is the specific mistake this type exists to make hard. `dialect_for` answers "which upstream spoke", and framing by it would start sending `response.*` events to a client that asked in Anthropic Messages — the main product path. The selector is `route.inbound_format`; see `framer_for`.

Stateful by necessity rather than by preference. The Anthropic side could be pure functions and is, underneath — but a Responses stream carries a sequence number that never repeats and an output index that must not skip, so the contract is an object constructed once per request.
"""

from typing import Protocol

from app.errors import ErrorInfo
from app.pipeline.delivery.assembling import Terminal
from app.pipeline.delivery.blocks import CompletedBlock, DeliveryUnit


class OutboundFramer[UnitT: DeliveryUnit = CompletedBlock](Protocol):
    def preamble(self) -> tuple[bytes, ...]:
        """The frames that open a response.

        Emitted with the first unit, never on its own: a turn that produces nothing must not leave the client holding a message that looks started.

        Empty on a leg that invents nothing — the direct Responses passthrough opens the response with upstream's own `response.created`, which arrives as an ordinary event and needs no counterpart from this side.
        """
        ...

    def block(self, block: UnitT) -> tuple[bytes, ...]:
        """One whole unit's frames. A caller never receives half a group."""
        ...

    def terminal(self, terminal: Terminal) -> tuple[bytes, ...]:
        """Close the response cleanly. Mutually exclusive with `error`."""
        ...

    def error(self, info: ErrorInfo) -> bytes:
        """The one frame that says a started stream will not end successfully.

        Takes the record rather than a pre-spelled type, and that is the whole of the change: the caller is generic delivery, which serves every leg, and it was reaching into `ANTHROPIC_ERROR_TYPES` to decide what to say. On a Responses leg that produced a category name from another dialect. Each framer now spells its own.
        """
        ...

    def keepalive(self) -> bytes:
        """What goes out between blocks so the connection is not silent."""
        ...

    @property
    def synthesises_terminal(self) -> bool:
        """Whether this leg may invent a terminal for a stream that ended without one.

        True for a translating leg: it is already writing every frame the client sees, so a configured stop reason is one more thing it spells, and a turn that stopped cleanly between blocks reads as complete rather than as an error.

        False for a direct passthrough. `direct-passthrough/spec.md` §8 forbids that leg synthesising a successful terminal, and §5.1 requires an error instead — the only honest terminal there is upstream's own, and this is exactly the case where it never arrived.

        Read by `stream._deliver` at that one ending. A leg-aware fact rather than a setting, because it is a property of what the leg is allowed to say, not of how an operator configured it.
        """
        ...
