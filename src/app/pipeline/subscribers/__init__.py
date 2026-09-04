"""The built-in subscribers, and the single place that registers them.

`docs/.human-controlled/request-pipeline.md` asks the driver to provide subscription points that functional modules subscribe to, each with a unique id and an optional "before/after whom". This package is the first thing to take it up: what used to be a hardcoded call in the request path becomes a named subscriber that can be located, ordered, and tested on its own.

**Why a registry rather than another function call.** The compatibility fixups are not one thing that grew — they are a family that keeps arriving one upstream rejection at a time, and each one that lands as a fresh call inside some existing function makes the next one harder to see, harder to order against its siblings, and impossible to exercise without standing up everything around it. A name and an event give each of them somewhere to live.

**Protocol repair is not configurable, on purpose.** A request that upstream rejects whole is not a preference, so the sanitizers here have no switch. The operator-facing `hooks:` subscription points in `config.example.yaml` are a different layer with their own undecided question — what a list item names — and this package deliberately does not pre-empt that answer by inventing a key of its own.

**A compatibility reshape is the exception, and it is opt-in rather than mandatory.** This paragraph used to say the whole package was unconfigurable, which stopped being true with `builtin:repair-minted-reasoning-ids`: it repairs history this proxy damaged rather than a shape upstream refuses, it edits a body on a leg whose contract is to forward verbatim, and `.dev/docs/direct-passthrough/spec.md` §2.7 requires exactly that kind of pass to carry a declared, default-off switch. So the rule is per-pass and its own Spec clause decides: a sanitizer upstream forces has no key, a reshape this proxy chooses must have one.

## Order

| id | event | goes before/after | why |
|---|---|---|---|
| `builtin:server-tool-capability` | `attempt.prepare` | — | Reads and edits `tools`. Anything else that comes to read `tools` has to say whether it wants the client's list or the one that will actually be sent, and answer it here rather than by landing at whatever position happens to work. |
| `builtin:hosted-web-search-gate` | `attempt.prepare` | after `builtin:server-tool-capability` | Nothing forces it — the two are mutually exclusive by route, one acting only when the target is Anthropic Messages and the other only when it is Responses, so neither can see what the other wrote. Registered next to it because they answer the same question for the two legs, and a reader looking for "where is web search decided" should find both in one place rather than at either end of the list. |
| `builtin:anthropic-thinking-capability` | `attempt.prepare` | — | Nothing forces its position: `thinking` and `output_config` are touched by nothing else on this event, and its two neighbours read `tools` and `content`. Registered here, after the pair above, because it is the third capability gate and they belong together — all three answer "will the model this is going to actually take this field". |
| `builtin:repair-minted-reasoning-ids` | `attempt.prepare` | — | Nothing forces its position. It reads and edits `input`, which on this event nothing else touches: every neighbour works on `tools`, `messages` or `content`, and those belong to the Anthropic-shaped body. Off by default; `.dev/docs/direct-passthrough/spec.md` §6.5. |
| `builtin:blank-text-blocks` | `attempt.prepare` | before `builtin:reasoning-carrier-last-mile` | This pass only removes text blocks that say nothing. Removing one can put two thinking blocks together, so the following pass owns the resulting Anthropic-only repair rather than this remover inventing a separator itself. |
| `builtin:reasoning-carrier-last-mile` | `attempt.prepare` | **after `builtin:blank-text-blocks`** | Refuses every project or compatible synthetic carrier still present in provider-bound wire. On an Anthropic target only, it then owns the configured thinking adjacency repair. Running after blank removal means it sees the body actually being sent and leaves no second separator owner. |
| `builtin:anthropic-cache-control-vocabulary` | `attempt.prepare` | **after `builtin:server-tool-capability`, by an explicit constraint** | It removes the `cache_control` keys upstream refuses from every marker in the body, and `server_tools.py` can put one back while rewriting a result. It only deletes fields, never blocks or messages, but it still precedes the final invariant assertion so the last subscriber observes the exact provider-bound body. |
| `builtin:anthropic-trailing-assistant` | `attempt.prepare` | **after `builtin:reasoning-carrier-last-mile` and `builtin:anthropic-cache-control-vocabulary`** | It asserts an invariant over the finished provider-bound message list after the last block-moving and field-pruning passes. Stated with `after=` rather than by registration order because a constraint that matters should not be recoverable only by reading this table. |

`tests/unit/pipeline/subscribers/test_builtin_subscribers.py` locks the registered set and the frozen order, so a subscriber added without a decision about where it goes fails there rather than in production.
"""

import re
from collections.abc import Mapping, Sequence

from app.config.schema import AssistantMessageLayout, CacheControlMode, ThinkingDisplayPolicy
from app.pipeline.direct_driver.base import EVENT_ATTEMPT_PREPARE
from app.pipeline.events import SubscriberRegistry
from app.pipeline.request import RequestContext
from app.pipeline.subscribers.anthropic_cache_control import (
    SUBSCRIBER_ID as ANTHROPIC_CACHE_CONTROL_ID,
)
from app.pipeline.subscribers.anthropic_cache_control import prune_cache_control_fields
from app.pipeline.subscribers.anthropic_thinking import (
    SUBSCRIBER_ID as ANTHROPIC_THINKING_CAPABILITY_ID,
)
from app.pipeline.subscribers.anthropic_thinking import adapt_thinking_capability
from app.pipeline.subscribers.anthropic_trailing_assistant import (
    SUBSCRIBER_ID as ANTHROPIC_TRAILING_ASSISTANT_ID,
)
from app.pipeline.subscribers.anthropic_trailing_assistant import repair_trailing_assistant
from app.pipeline.subscribers.blank_text import SUBSCRIBER_ID as BLANK_TEXT_BLOCKS_ID
from app.pipeline.subscribers.blank_text import drop_blank_text_blocks
from app.pipeline.subscribers.hosted_web_search import SUBSCRIBER_ID as HOSTED_WEB_SEARCH_GATE_ID
from app.pipeline.subscribers.hosted_web_search import gate_hosted_web_search
from app.pipeline.subscribers.minted_reasoning_ids import (
    SUBSCRIBER_ID as MINTED_REASONING_IDS_ID,
)
from app.pipeline.subscribers.minted_reasoning_ids import repair_minted_reasoning_ids
from app.pipeline.subscribers.reasoning_carrier import (
    SUBSCRIBER_ID as REASONING_CARRIER_LAST_MILE_ID,
)
from app.pipeline.subscribers.reasoning_carrier import guard_and_layout_reasoning
from app.pipeline.subscribers.server_tools import SUBSCRIBER_ID as SERVER_TOOL_CAPABILITY_ID
from app.pipeline.subscribers.server_tools import adapt_server_tools


def register_builtin_subscribers(
    registry: SubscriberRegistry[RequestContext],
    *,
    web_search_models: Mapping[str, Sequence[re.Pattern[str]]] | None = None,
    web_search_enabled: bool = False,
    default_provider: str = "",
    thinking_efforts: Mapping[str, str] | None = None,
    thinking_display: ThinkingDisplayPolicy = "passthrough",
    assistant_message_layout: AssistantMessageLayout = "move_and_synthetic",
    cache_control: CacheControlMode = "sanitize",
    cache_control_sanitize: Sequence[tuple[re.Pattern[str], frozenset[str]]] = (),
    repair_minted_reasoning_ids_enabled: bool = False,
) -> None:
    """Add every built-in subscriber to a registry that has not been frozen yet.

    Takes the registry rather than building one so a caller that has its own subscribers ends up with one ordering over all of them. Two registries would mean two frozen orders and no rule about which runs first.

    Registering into the same registry twice raises `SubscriptionError` on the duplicate id, which is the intended answer rather than an oversight: a registry is built for one chain, and reusing one across two `build_chain` calls means the second chain's subscribers were meant to be somebody else's. Failing at startup names that; silently tolerating it would leave two chains sharing mutable wiring.
    """
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        SERVER_TOOL_CAPABILITY_ID,
        adapt_server_tools,
    )
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        HOSTED_WEB_SEARCH_GATE_ID,
        # Bound at registration rather than read from the context: both are configuration, fixed for the life of the chain, and threading them through every request would put a startup decision in a per-request field where something could change it mid-flight.
        lambda context: gate_hosted_web_search(
            context,
            web_search_models or {},
            enabled=web_search_enabled,
            default_provider=default_provider,
        ),
    )
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        ANTHROPIC_THINKING_CAPABILITY_ID,
        # Bound at registration for the reason its neighbour above gives: both are startup decisions, and a per-request field holding one is a field something can change mid-flight.
        lambda context: adapt_thinking_capability(
            context,
            efforts_by_model=thinking_efforts or {},
            display=thinking_display,
        ),
    )
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        MINTED_REASONING_IDS_ID,
        # Bound at registration for the reason its neighbours give: it is a startup decision, and a per-request field holding one is a field something can change mid-flight.
        lambda context: repair_minted_reasoning_ids(
            context, enabled=repair_minted_reasoning_ids_enabled
        ),
    )
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        BLANK_TEXT_BLOCKS_ID,
        drop_blank_text_blocks,
    )
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        REASONING_CARRIER_LAST_MILE_ID,
        lambda context: guard_and_layout_reasoning(
            context,
            assistant_message_layout=assistant_message_layout,
        ),
        # Blank removal may put two thinking blocks together. This pass is the sole owner of repairing that final Anthropic shape.
        after=(BLANK_TEXT_BLOCKS_ID,),
    )
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        ANTHROPIC_TRAILING_ASSISTANT_ID,
        repair_trailing_assistant,
        # This assertion runs last, after both the last block-moving pass and the last field-pruning pass.
        after=(REASONING_CARRIER_LAST_MILE_ID, ANTHROPIC_CACHE_CONTROL_ID),
    )
    registry.subscribe(
        EVENT_ATTEMPT_PREPARE,
        ANTHROPIC_CACHE_CONTROL_ID,
        # Bound at registration for the reason its neighbours give: it is a startup decision, and a per-request field holding one is a field something can change mid-flight.
        lambda context: prune_cache_control_fields(
            context, mode=cache_control, table=cache_control_sanitize
        ),
        # The second load-bearing constraint. `server_tools.py` carries a `cache_control` across when it rewrites a server-tool result into a text block, so it can put a marker back into the body after this pass would already have walked past it.
        after=(SERVER_TOOL_CAPABILITY_ID,),
    )


__all__ = [
    "ANTHROPIC_CACHE_CONTROL_ID",
    "ANTHROPIC_THINKING_CAPABILITY_ID",
    "ANTHROPIC_TRAILING_ASSISTANT_ID",
    "BLANK_TEXT_BLOCKS_ID",
    "HOSTED_WEB_SEARCH_GATE_ID",
    "MINTED_REASONING_IDS_ID",
    "REASONING_CARRIER_LAST_MILE_ID",
    "SERVER_TOOL_CAPABILITY_ID",
    "adapt_server_tools",
    "adapt_thinking_capability",
    "drop_blank_text_blocks",
    "gate_hosted_web_search",
    "guard_and_layout_reasoning",
    "prune_cache_control_fields",
    "register_builtin_subscribers",
    "repair_minted_reasoning_ids",
    "repair_trailing_assistant",
]
