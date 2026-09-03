"""Which framer, which assembler, which buffer — the choices a route implies about delivery.

Split out of `app.server.handler` on 2026-08-22. Above `app.pipeline.delivery`, not inside it: every function here reads a `Route`, and `delivery` sits *below* `RequestContext` in the import graph — `app.pipeline.request` imports `delivery.assembling` for `Terminal`. Putting route-aware selection inside `delivery` would invert that, which is how an independent review caught it before it was written.
"""



from collections.abc import Callable
from typing import Any

from app.core.chain import Chain
from app.pipeline.delivery import BlockBuffer
from app.pipeline.delivery.assembling import BlockAssembler, ReplyDialect
from app.pipeline.delivery.formats.anthropic_messages import (
    AnthropicAssembler,
    AnthropicFramer,
)
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler, ResponsesFramer
from app.pipeline.delivery.formats.openai_responses_passthrough import (
    responses_passthrough_assembler,
)
from app.pipeline.delivery.framing import OutboundFramer
from app.pipeline.delivery.passthrough import PassthroughFramer
from app.pipeline.delivery.stream import StreamSettings
from app.pipeline.driver import CLIENT_SEARCH_TOOL, HandledRequest
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

    A synthesized reply is written by us and we write Anthropic, so it is deliverable — but **not** "whatever the route was", which is what this said until issue #1 and is the sentence the defect was living in. Being written in Anthropic is only half of deliverable; the other half is that the client leg has a framer that can write Anthropic blocks, and `framer_for` below picks that framer by `inbound_format`. A synthesized reply reaching a Responses client was framed by `ResponsesFramer`, which has no item shape for `server_tool_use` and raised mid-delivery.

    What makes the carve-out sound is upstream of here: both writers of a synthesized reply — the auto mode branch and the failed-search branch in `app.pipeline.driver` — only fire when `inbound_format` is Anthropic Messages, so the only client that can receive one is the client whose framer reads it. That is an invariant this function depends on and does not enforce; it is stated here because the version that went unstated cost a torn stream and, on the buffered path, an Anthropic body delivered to a Responses client under a 200 logged `ok`.
    """
    if handled.synthesized:
        return True
    return handled.route.inbound_format is not WireFormat.OPENAI_CHAT_COMPLETIONS

def carries_upstream_natively(handled: HandledRequest) -> bool:
    """Whether this route's client speaks the dialect upstream answered in, so nothing needs translating.

    `direct-passthrough/spec.md` §2.6 and the user's 2026-08-31 ruling: **every** leg where `translation_required` is false should carry upstream's own events rather than round-tripping them through an Anthropic intermediate. Three of the four are not here yet, each for its own recorded reason.

    `anthropic-messages` is built and unit-tested but not switched on — `spec.md` §2.8: `max_tokens` hand-over is a user ruling that is live on that leg today, it synthesises a block that has to precede the terminal, and native delivery has already released upstream's terminal by then. Turning it on before that is settled would regress the leg every Claude model takes, which §2.7 forbids. `deferred.md` D-5.

    `openai-chat-completions` has no ceiling to remove: it has no framer at all, so `one_shot_delivery` already forwards upstream's bytes. `openai-embeddings` is not streamed.

    A synthesized reply is excluded because this proxy wrote it, in Anthropic, and it has to be framed by whoever can write that — the invariant `delivers_blocks` already depends on.
    """
    if handled.synthesized:
        return False
    if handled.route.translation_required:
        return False
    return handled.route.inbound_format is WireFormat.OPENAI_RESPONSES


def framer_for(
    handled: HandledRequest,
    chain: Chain,
    *,
    message_id: str,
    model: str,
    on_passthrough_terminal_unit: Callable[[], None] | None = None,
) -> OutboundFramer[Any] | None:
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
        native = ResponsesFramer(response_id=message_id, model=model)
        # The passthrough writes upstream's own frames and delegates the two it still has to invent — an error and a keep-alive — to the very framer it replaces. Constructed either way so that delegate exists.
        return (
            PassthroughFramer(
                delegate=native,
                on_terminal_unit=on_passthrough_terminal_unit,
            )
            if carries_upstream_natively(handled)
            else native
        )
    return AnthropicFramer(
        message_id=message_id,
        model=model,
        # Read here rather than carried in on a delivery setting. It says how a thinking block's signature is spelled, which is a fact about the Anthropic wire format and therefore the
        # Anthropic framer's business; routing it through `StreamSettings` put a framing knob in the one object that is meant to name no format at all.
        signature_compat=chain.config.hook_fix_anthropic_sse.thinking.content_block_start_compat,
    )

def assembler_for(
    handled: HandledRequest, *, hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"})
) -> BlockAssembler[Any]:
    """Pick the assembler matching the upstream this route actually used.

    Dispatched on `dialect_for` rather than testing the wire format again, so the streaming and buffered paths cannot come to disagree about which upstream answered — one branch decides it for both.
    """
    if carries_upstream_natively(handled):
        # Nothing to translate, so nothing to fail to translate. This is what closes GitHub issues #2 and #3: the refusal they hit lives in `ResponsesAssembler`, which this leg no longer reaches.
        return responses_passthrough_assembler()
    if dialect_for(handled) is ReplyDialect.RESPONSES:
        # Only this one can see whether upstream cut an item short, and so only this one needs to know which endings will hand the turn back.
        return ResponsesAssembler(
            hand_over_stop_reasons=hand_over_stop_reasons,
            # Put on the context by the request translation. The streaming path needs it for the same reason the buffered one does — a `tool_search_call` names no tool — and reads it from the same place, so the two cannot come to deliver the model's search request under different names.
            client_search_tool=str(handled.context.extras.get(CLIENT_SEARCH_TOOL, "")),
        )
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
