"""What delivery needs in order to write a block out, whichever protocol the client asked in.

The mirror of `BlockAssembler`. That one turns an upstream's events into blocks; this one turns blocks into a client's events. They are separate questions and a route can answer them differently: a request that arrives as Anthropic Messages and is translated to a Responses upstream is assembled by the Responses assembler and framed by the Anthropic framer, because the upstream leg and the client leg are two different protocols.

Getting that backwards is the specific mistake this type exists to make hard. `dialect_for` answers "which upstream spoke", and framing by it would start sending `response.*` events to a client that asked in Anthropic Messages — the main product path. The selector is `route.inbound_format`; see `framer_for`.

Stateful by necessity rather than by preference. The Anthropic side could be pure functions and is, underneath — but a Responses stream carries a sequence number that never repeats and an output index that must not skip, so the contract is an object constructed once per request.
"""

from typing import Protocol

from app.pipeline.delivery.assembling import Terminal
from app.pipeline.delivery.blocks import CompletedBlock


class OutboundFramer(Protocol):
    def preamble(self) -> tuple[bytes, ...]:
        """The frames that open a response.

        Emitted with the first block, never on its own: a turn that produces nothing must not leave the client holding a message that looks started.
        """
        ...

    def block(self, block: CompletedBlock) -> tuple[bytes, ...]:
        """One whole block's frames. A caller never receives half a group."""
        ...

    def terminal(self, terminal: Terminal) -> tuple[bytes, ...]:
        """Close the response cleanly. Mutually exclusive with `error`."""
        ...

    def error(self, *, error_type: str, message: str, code: str | None = None) -> bytes:
        """The one frame that says a started stream will not end successfully."""
        ...

    def keepalive(self) -> bytes:
        """What goes out between blocks so the connection is not silent."""
        ...
