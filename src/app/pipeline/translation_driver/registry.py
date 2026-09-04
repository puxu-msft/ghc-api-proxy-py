"""Translator registry.

Translators register under the names `docs/.human-controlled/message-translation.md` uses.
`inbound.from-<format>` and `outbound.to-<format>`, so a format is added by registering a pair.
"""

from collections.abc import Callable, Mapping
from functools import partial
from typing import Any, Protocol

from app.config.schema import ModelTranslationConfig
from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.anthropic_messages import (
    from_anthropic_messages,
    to_anthropic_messages,
)
from app.pipeline.translation_driver.openai_chat_completions import (
    from_chat_completions_response,
    to_openai_chat_completions,
)
from app.pipeline.translation_driver.openai_responses import (
    from_openai_responses,
    to_openai_responses,
)
from app.pipeline.translation_driver.responses import (
    SemanticResponse,
    from_anthropic_response,
    from_openai_responses_response,
    to_anthropic_response,
    to_openai_responses_response,
)
from app.pipeline.translation_driver.semantic import SemanticRequest, TranslationTarget

type InboundTranslator = Callable[[Mapping[str, Any]], SemanticRequest]
type OutboundTranslator = Callable[[SemanticRequest, TranslationTarget], dict[str, Any]]
class ResponseReader(Protocol):
    """Reads an upstream response body into the intermediate form.

    `client_search_tool` is accepted by every reader and used by the one whose wire has a tool search to hand back. A `Callable` alias could not express an argument only some readers care about without either putting it on none of them — leaving the Responses reader unable to name the tool a `tool_search_call` belongs to — or forcing every future reader to grow a parameter about a format it does not speak.
    """

    def __call__(
        self,
        payload: Mapping[str, Any],
        *,
        client_search_tool: str = "",
        hosted_web_search_expected: bool = False,
    ) -> SemanticResponse: ...
type ResponseWriter = Callable[[SemanticResponse], dict[str, Any]]

INBOUND_PREFIX = "inbound.from-"
OUTBOUND_PREFIX = "outbound.to-"


class TranslatorNotFound(RuntimeError):
    """Raised before the network, so an unroutable translation never reaches upstream."""


def inbound_name(wire: WireFormat) -> str:
    return f"{INBOUND_PREFIX}{wire.value}"


def outbound_name(wire: WireFormat) -> str:
    return f"{OUTBOUND_PREFIX}{wire.value}"


class TranslatorRegistry:
    def __init__(self) -> None:
        self._inbound: dict[WireFormat, InboundTranslator] = {}
        self._outbound: dict[WireFormat, OutboundTranslator] = {}
        self._read_response: dict[WireFormat, ResponseReader] = {}
        self._write_response: dict[WireFormat, ResponseWriter] = {}

    def register_inbound(self, wire: WireFormat, translator: InboundTranslator) -> None:
        self._inbound[wire] = translator

    def register_outbound(self, wire: WireFormat, translator: OutboundTranslator) -> None:
        self._outbound[wire] = translator

    def register_response_reader(self, wire: WireFormat, reader: ResponseReader) -> None:
        self._read_response[wire] = reader

    def register_response_writer(self, wire: WireFormat, writer: ResponseWriter) -> None:
        self._write_response[wire] = writer

    @property
    def names(self) -> frozenset[str]:
        return frozenset(
            [inbound_name(wire) for wire in self._inbound]
            + [outbound_name(wire) for wire in self._outbound]
        )

    def inbound(self, wire: WireFormat) -> InboundTranslator:
        translator = self._inbound.get(wire)
        if translator is None:
            raise TranslatorNotFound(f"no translator registered as {inbound_name(wire)}")
        return translator

    def outbound(self, wire: WireFormat) -> OutboundTranslator:
        translator = self._outbound.get(wire)
        if translator is None:
            raise TranslatorNotFound(f"no translator registered as {outbound_name(wire)}")
        return translator

    def translate(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        target: WireFormat,
        target_model: TranslationTarget | None = None,
    ) -> tuple[dict[str, Any], SemanticRequest]:
        """Carry a payload from one wire format to another through the intermediate form.

        Both translators are looked up before either runs.
        A missing pair therefore fails whole rather than after half a conversion.

        `target_model` is what the resolved upstream model can do, and only the writer sees it: the reader is describing what the client said, which is the same whoever ends up answering. Omitting it yields the default — no published capabilities — so a writer declines to render anything it would have to guess at rather than rendering a guess.
        """
        to_semantic = self.inbound(source)
        to_wire = self.outbound(target)
        semantic = to_semantic(payload)
        return to_wire(semantic, target_model or TranslationTarget()), semantic

    def translate_response(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        target: WireFormat,
        client_search_tool: str = "",
        hosted_web_search_expected: bool = False,
    ) -> tuple[dict[str, Any], SemanticResponse]:
        """Carry a response back across, so the client sees the format it asked in.

        Both halves are resolved before either runs, as on the request side.
        """
        reader = self._read_response.get(source)
        if reader is None:
            raise TranslatorNotFound(f"no response reader registered for {source.value}")
        writer = self._write_response.get(target)
        if writer is None:
            raise TranslatorNotFound(f"no response writer registered for {target.value}")
        semantic = reader(
            payload,
            client_search_tool=client_search_tool,
            hosted_web_search_expected=hosted_web_search_expected,
        )
        return writer(semantic), semantic


def default_registry(config: ModelTranslationConfig | None = None) -> TranslatorRegistry:
    """Register every translator pair, with the configurable choices bound in.

    Bound here rather than threaded through `translate` so the registry keeps handing out plain `SemanticRequest -> dict` callables: a translator that needed config at call time would put that argument on every pair, including the ones that have nothing to configure.
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
            web_search_domain_restrictions=settings.to_openai_responses.web_search_domain_restrictions,
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
    # Chat Completions is registered as an *outbound* target and a response source
    # only. No inbound translator, no response writer: a client that speaks Chat
    # Completions is served by the direct passthrough leg, which forwards its bytes
    # rather than round-tripping them through the intermediate form, so a pair here
    # would be registration for a route that cannot be built.
    registry.register_outbound(WireFormat.OPENAI_CHAT_COMPLETIONS, to_openai_chat_completions)
    registry.register_response_reader(
        WireFormat.OPENAI_CHAT_COMPLETIONS, from_chat_completions_response
    )
    return registry
