"""The built-in subscribers, and the single place that registers them.

`MAIN.md` asks the driver to provide subscription points that functional modules subscribe to, each with a unique id and an optional "before/after whom". This package is the first thing to take it up: what used to be a hardcoded call in the request path becomes a named subscriber that can be located, ordered, and tested on its own.

**Why a registry rather than another function call.** The compatibility fixups are not one thing that grew — they are a family that keeps arriving one upstream rejection at a time, and each one that lands as a fresh call inside some existing function makes the next one harder to see, harder to order against its siblings, and impossible to exercise without standing up everything around it. A name and an event give each of them somewhere to live.

**Not configurable, on purpose.** Protocol repair is a mandatory sanitizer: a request that upstream rejects whole is not a preference. The operator-facing `hooks:` subscription points in `config.example.yaml` are a different layer with their own undecided question — what a list item names — and this package deliberately does not pre-empt that answer by inventing a key of its own.

## Order

| id | event | goes before/after | why |
|---|---|---|---|
| `builtin:server-tool-capability` | `attempt.prepare` | — | Reads and edits `tools`. Anything else that comes to read `tools` has to say whether it wants the client's list or the one that will actually be sent, and answer it here rather than by landing at whatever position happens to work. |
| `builtin:blank-text-blocks` | `attempt.prepare` | after `builtin:server-tool-capability` | That pass flattens server-tool turns into text, so it can produce the very thing this one removes — a text block whose text came out empty. Running first would leave one behind, and the request would be refused over a block this chain wrote itself. |

`tests/unit/test_builtin_subscribers.py` locks the registered set and the frozen order, so a subscriber added without a decision about where it goes fails there rather than in production.
"""

from app.pipeline.direct_driver.base import EVENT_ATTEMPT_PREPARE
from app.pipeline.events import SubscriberRegistry
from app.pipeline.request import RequestContext
from app.pipeline.subscribers.blank_text import SUBSCRIBER_ID as BLANK_TEXT_BLOCKS_ID
from app.pipeline.subscribers.blank_text import drop_blank_text_blocks
from app.pipeline.subscribers.server_tools import SUBSCRIBER_ID as SERVER_TOOL_CAPABILITY_ID
from app.pipeline.subscribers.server_tools import adapt_server_tools


def register_builtin_subscribers(registry: SubscriberRegistry[RequestContext]) -> None:
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
        BLANK_TEXT_BLOCKS_ID,
        drop_blank_text_blocks,
    )


__all__ = [
    "BLANK_TEXT_BLOCKS_ID",
    "SERVER_TOOL_CAPABILITY_ID",
    "adapt_server_tools",
    "drop_blank_text_blocks",
    "register_builtin_subscribers",
]
