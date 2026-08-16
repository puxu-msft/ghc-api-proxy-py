"""Translation driver: inbound format <-> intermediate <-> upstream format.

The registry is populated with the pairs that exist today.
Registering a new format's pair is all it takes to add one.
"""

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.anthropic_messages import (
    from_anthropic_messages,
    to_anthropic_messages,
)
from app.pipeline.translation_driver.openai_responses import (
    from_openai_responses,
    to_openai_responses,
)
from app.pipeline.translation_driver.registry import (
    TranslatorNotFound,
    TranslatorRegistry,
    inbound_name,
    outbound_name,
)
from app.pipeline.translation_driver.semantic import (
    Conversion,
    SemanticRequest,
    SystemBlock,
    system_blocks_from_value,
)


def default_registry() -> TranslatorRegistry:
    registry = TranslatorRegistry()
    registry.register_inbound(WireFormat.ANTHROPIC_MESSAGES, from_anthropic_messages)
    registry.register_outbound(WireFormat.ANTHROPIC_MESSAGES, to_anthropic_messages)
    registry.register_inbound(WireFormat.OPENAI_RESPONSES, from_openai_responses)
    registry.register_outbound(WireFormat.OPENAI_RESPONSES, to_openai_responses)
    return registry


__all__ = [
    "Conversion",
    "SemanticRequest",
    "SystemBlock",
    "TranslatorNotFound",
    "TranslatorRegistry",
    "default_registry",
    "from_anthropic_messages",
    "from_openai_responses",
    "inbound_name",
    "outbound_name",
    "system_blocks_from_value",
    "to_anthropic_messages",
    "to_openai_responses",
]
