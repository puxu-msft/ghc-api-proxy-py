"""Which framer, which assembler, which buffer — the choices a route implies about delivery.

Split out of `app.server.handler` on 2026-08-22. Above `app.pipeline.delivery`, not inside it: every function here reads a `Route`, and `delivery` sits *below* `RequestContext` in the import graph — `app.pipeline.request` imports `delivery.assembling` for `Terminal`. Putting route-aware selection inside `delivery` would invert that, which is how an independent review caught it before it was written.
"""



from app.core.chain import Chain
from app.pipeline.delivery import BlockBuffer
from app.pipeline.delivery.assembling import BlockAssembler, ReplyDialect
from app.pipeline.delivery.formats.anthropic_messages import (
    AnthropicAssembler,
    AnthropicFramer,
)
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler, ResponsesFramer
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.stream import StreamSettings
from app.pipeline.driver import HandledRequest
from app.pipeline.request import WireFormat


def dialect_for(handled: HandledRequest) -> ReplyDialect:
    """Which upstream's vocabulary this route's reply came back in.

    Taken from the route rather than from the reply, because a buffered reply is read back after translation and by then looks Anthropic-shaped whatever answered it. The route is the only thing that still knows which upstream was actually spoken to, which is what the console line reports.

    Two dialects, not one per wire format: anything that is not a Responses upstream is assembled as Anthropic — `assembler_for` below dispatches on this very answer — so the pair describes what the code actually does rather than the whole `WireFormat` taxonomy. A third upstream would need its own assembler before it could need its own words.
    """
    if handled.synthesized:
        # We wrote it, and we write Anthropic. The route below is about who *would* have answered.
        return ReplyDialect.ANTHROPIC
    if handled.route.target_format is WireFormat.OPENAI_RESPONSES:
        return ReplyDialect.RESPONSES
    return ReplyDialect.ANTHROPIC

def delivers_blocks(handled: HandledRequest) -> bool:
    """Whether this route's *client* leg can be written a block at a time.

    Block delivery needs both halves: an assembler that finds a block's end in the upstream's events, and a framer that writes one in the client's. `assembler_for` above answers the first. This answers the second, and the two are separate questions — a route can have an assembler and still have nowhere to write what it produces.

    Chat Completions has no framer. Its boundaries are inside `choices[].delta` and nothing here reads them, so a request whose client leg speaks that dialect is delivered whole by `one_shot_delivery`. Ruled 2026-08-22, after a measurement: those bytes were reaching `AnthropicAssembler`, matching none of its event names, and leaving the client a 200 with an empty body.

    A synthesized reply is written by us and we write Anthropic, so it is deliverable whatever the route was — the same carve-out, for the same reason, that `dialect_for` makes.
    """
    if handled.synthesized:
        return True
    return handled.route.inbound_format is not WireFormat.OPENAI_CHAT_COMPLETIONS

def framer_for(
    handled: HandledRequest,
    chain: Chain,
    *,
    message_id: str,
    model: str,
) -> OutboundFramer | None:
    """The outbound framer for this route's client leg, or `None` when it has none and the stream is delivered whole.

    Selected on `route.inbound_format` — the protocol the client asked in — and deliberately **not** on `dialect_for`, which answers which upstream replied. On the main product path those are different formats: a request arriving as Anthropic Messages and served by a Responses upstream has to be answered in Anthropic Messages, and framing it by the upstream's dialect would start sending `response.*` events to a client that cannot read them.

    The pairing with `assembler_for` is the point. That one is chosen by the upstream leg, this one by the client leg, and a translated route uses one of each.
    """
    if not delivers_blocks(handled):
        # One-shot delivery forwards upstream's bytes unchanged, so it is only correct while upstream is answering in the protocol the client asked in. Today that holds by construction — the translator registry has no Chat Completions leg, so such a route cannot be built — and this says so out loud rather than relying on it. Registering one would otherwise send a Responses body to a Chat Completions client, verbatim and silently.
        if handled.route.translation_required:
            raise ValueError(
                f"no framer for {handled.route.inbound_format.value}, and its bytes were translated "
                f"from {handled.route.target_format.value}, so they cannot be forwarded unchanged"
            )
        return None
    if handled.route.inbound_format is WireFormat.OPENAI_RESPONSES:
        return ResponsesFramer(response_id=message_id, model=model)
    return AnthropicFramer(
        message_id=message_id,
        model=model,
        # Read here rather than carried in on a delivery setting. It says how a thinking block's signature is spelled, which is a fact about the Anthropic wire format and therefore the
        # Anthropic framer's business; routing it through `StreamSettings` put a framing knob in the one object that is meant to name no format at all.
        signature_compat=chain.config.hook_fix_anthropic_sse.thinking.content_block_start_compat,
    )

def assembler_for(
    handled: HandledRequest, *, hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"})
) -> BlockAssembler:
    """Pick the assembler matching the upstream this route actually used.

    Dispatched on `dialect_for` rather than testing the wire format again, so the streaming and buffered paths cannot come to disagree about which upstream answered — one branch decides it for both.
    """
    if dialect_for(handled) is ReplyDialect.RESPONSES:
        # Only this one can see whether upstream cut an item short, and so only this one needs to know which endings will hand the turn back.
        return ResponsesAssembler(hand_over_stop_reasons=hand_over_stop_reasons)
    return AnthropicAssembler()

def stream_settings(chain: Chain) -> StreamSettings:
    delivery = chain.config.client_delivery
    return StreamSettings(
        sse_ping_interval=delivery.sse_ping_interval,
        unterminated_stop_reason=delivery.unterminated_stream_stop_reason,
    )

def delivery_buffer(chain: Chain) -> BlockBuffer:
    delivery = chain.config.client_delivery
    return BlockBuffer(
        policy=delivery.buffering_policy,
        cap_bytes=delivery.buffer_cap_bytes,
    )

def stream_idle_seconds(chain: Chain) -> int:
    """How long upstream may go quiet mid-stream before the attempt is given up on.

    0 disables it, and 0 is the bundled default. The frozen invariant is never to false-kill legitimate thinking — silence on a live connection has no provably safe bound, so an operator setting this is choosing bounded waiting rather than accepting a default.
    """
    return chain.config.upstream_request_timeouts.stream_idle
