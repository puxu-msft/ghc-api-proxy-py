"""Translation driver: inbound format <-> intermediate <-> upstream format.

The registry is populated with the pairs that exist today.
Registering a new format's pair is all it takes to add one.
"""

from functools import partial

from app.config.schema import ModelTranslationConfig
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
from app.pipeline.translation_driver.responses import (
    SemanticBlock,
    SemanticResponse,
    from_anthropic_response,
    from_openai_responses_response,
    to_anthropic_response,
    to_openai_responses_response,
)
from app.pipeline.translation_driver.semantic import (
    Conversion,
    SemanticRequest,
    SystemBlock,
    system_blocks_from_value,
)


def default_registry(config: ModelTranslationConfig | None = None) -> TranslatorRegistry:
    """Register every translator pair, with the configurable choices bound in.

    Bound here rather than threaded through `translate` so the registry keeps handing out plain
    `SemanticRequest -> dict` callables: a translator that needed config at call time would put
    that argument on every pair, including the ones that have nothing to configure.
    """
    settings = config or ModelTranslationConfig()
    registry = TranslatorRegistry()
    registry.register_inbound(WireFormat.ANTHROPIC_MESSAGES, from_anthropic_messages)
    registry.register_outbound(WireFormat.ANTHROPIC_MESSAGES, to_anthropic_messages)
    registry.register_inbound(WireFormat.OPENAI_RESPONSES, from_openai_responses)
    registry.register_outbound(
        WireFormat.OPENAI_RESPONSES,
        partial(
            to_openai_responses,
            system_prompts=settings.to_openai_responses.system_prompts,
        ),
    )
    registry.register_response_reader(WireFormat.ANTHROPIC_MESSAGES, from_anthropic_response)
    registry.register_response_writer(WireFormat.ANTHROPIC_MESSAGES, to_anthropic_response)
    registry.register_response_reader(
        WireFormat.OPENAI_RESPONSES, from_openai_responses_response
    )
    registry.register_response_writer(
        WireFormat.OPENAI_RESPONSES, to_openai_responses_response
    )
    return registry


__all__ = [
    "Conversion",
    "SemanticBlock",
    "SemanticRequest",
    "SemanticResponse",
    "SystemBlock",
    "TranslatorNotFound",
    "TranslatorRegistry",
    "default_registry",
    "from_anthropic_messages",
    "from_anthropic_response",
    "from_openai_responses",
    "from_openai_responses_response",
    "inbound_name",
    "outbound_name",
    "system_blocks_from_value",
    "to_anthropic_messages",
    "to_anthropic_response",
    "to_openai_responses",
    "to_openai_responses_response",
]
