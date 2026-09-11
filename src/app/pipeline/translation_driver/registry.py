"""Registry for wire decoders and encoders.

The registry is the only place that composes wire → IR and IR → wire stages.
"""

from collections.abc import Callable, Mapping
from functools import partial
from inspect import signature
from typing import Any

from app.config.schema import ModelTranslationConfig
from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.anthropic_messages import (
    from_anthropic_messages,
    to_anthropic_messages,
)
from app.pipeline.translation_driver.openai_chat_completions import (
    from_chat_completions_response,
    from_openai_chat_completions,
    to_openai_chat_completions,
    to_openai_chat_completions_response,
)
from app.pipeline.translation_driver.openai_responses import (
    from_openai_responses,
    to_openai_responses,
)
from app.pipeline.translation_driver.options import TranslationOptions
from app.pipeline.translation_driver.responses import (
    SemanticResponse,
    from_anthropic_response,
    from_openai_responses_response,
    to_anthropic_response,
    to_openai_responses_response,
)
from app.pipeline.translation_driver.semantic import (
    SemanticRequest,
    TranslationTarget,
)

type RequestReader = Callable[..., SemanticRequest]
type OutboundTranslator = Callable[..., dict[str, Any]]
type ResponseReader = Callable[..., SemanticResponse]
type ResponseWriter = Callable[..., dict[str, Any]]

DECODE_PREFIX = "decode.from-"
ENCODE_PREFIX = "encode.to-"


class TranslatorNotFound(RuntimeError):
    """Raised before the network, so an unroutable translation never reaches upstream."""


def decode_name(wire: WireFormat) -> str:
    return f"{DECODE_PREFIX}{wire.value}"


def encode_name(wire: WireFormat) -> str:
    return f"{ENCODE_PREFIX}{wire.value}"


# Compatibility names for integrations that still expose the old labels.
def inbound_name(wire: WireFormat) -> str:
    return f"inbound.from-{wire.value}"


def outbound_name(wire: WireFormat) -> str:
    return f"outbound.to-{wire.value}"


class TranslatorRegistry:
    def __init__(self, options: TranslationOptions | None = None) -> None:
        self._default_options = options or TranslationOptions()
        self._decoders: dict[WireFormat, RequestReader] = {}
        self._encoders: dict[WireFormat, OutboundTranslator] = {}
        self._read_response: dict[WireFormat, ResponseReader] = {}
        self._write_response: dict[WireFormat, ResponseWriter] = {}

    def register_decoder(self, wire: WireFormat, translator: RequestReader) -> None:
        self._decoders[wire] = translator

    def register_encoder(self, wire: WireFormat, translator: OutboundTranslator) -> None:
        self._encoders[wire] = translator

    def register_inbound(self, wire: WireFormat, translator: RequestReader) -> None:
        self.register_decoder(wire, translator)

    def register_outbound(self, wire: WireFormat, translator: OutboundTranslator) -> None:
        self.register_encoder(wire, translator)

    def register_response_reader(self, wire: WireFormat, reader: ResponseReader) -> None:
        self._read_response[wire] = reader

    def register_response_writer(self, wire: WireFormat, writer: ResponseWriter) -> None:
        self._write_response[wire] = writer

    @property
    def names(self) -> frozenset[str]:
        return frozenset(
            [name for wire in self._decoders for name in (decode_name(wire), f"inbound.from-{wire.value}")]
            + [
                name
                for wire in self._encoders
                for name in (encode_name(wire), f"outbound.to-{wire.value}")
            ]
        )

    def decoder(self, wire: WireFormat) -> RequestReader:
        translator = self._decoders.get(wire)
        if translator is None:
            raise TranslatorNotFound(f"no translator registered as {inbound_name(wire)}")
        return translator

    def encoder(self, wire: WireFormat) -> OutboundTranslator:
        translator = self._encoders.get(wire)
        if translator is None:
            raise TranslatorNotFound(f"no translator registered as {outbound_name(wire)}")
        return translator

    def inbound(self, wire: WireFormat) -> RequestReader:
        return self.decoder(wire)

    def outbound(self, wire: WireFormat) -> OutboundTranslator:
        return self.encoder(wire)

    def decode(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        options: TranslationOptions | None = None,
    ) -> SemanticRequest:
        snapshot = options or self._default_options
        reader = self.decoder(source)
        if "options" in signature(reader).parameters:
            return reader(payload, options=snapshot)
        return reader(
            payload,
            source_headers=snapshot.source_headers,
            translated=snapshot.translated,
        )

    def decode_request(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        options: TranslationOptions | None = None,
    ) -> SemanticRequest:
        return self.decode(payload, source=source, options=options)

    def encode(
        self,
        semantic: SemanticRequest,
        *,
        target: WireFormat,
        options: TranslationOptions | None = None,
    ) -> dict[str, Any]:
        snapshot = options or self._default_options
        return self.encoder(target)(
            semantic,
            snapshot.target,
            options=snapshot,
        )

    def translate(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        target: WireFormat,
        target_model: TranslationTarget | None = None,
        source_headers: Mapping[str, str] | None = None,
        options: TranslationOptions | None = None,
    ) -> tuple[dict[str, Any], SemanticRequest]:
        """Carry a payload from one wire format to another through the intermediate form.

        Both translators are looked up before either runs.
        A missing pair therefore fails whole rather than after half a conversion.

        `target_model` is what the resolved upstream model can do, and only the writer sees it: the reader is describing what the client said, which is the same whoever ends up answering. Omitting it yields the default — no published capabilities — so a writer declines to render anything it would have to guess at rather than rendering a guess.
        """
        base = options or self._default_options
        snapshot = TranslationOptions(
            source_headers=(
                source_headers if source_headers is not None else base.source_headers
            ),
            translated=source is not target,
            target=target_model or base.target,
            client_search_tool=base.client_search_tool,
            hosted_web_search_expected=base.hosted_web_search_expected,
            hand_over_stop_reasons=base.hand_over_stop_reasons,
            model_translation=base.model_translation,
        )
        reader = self.decoder(source)
        if "options" in signature(reader).parameters:
            semantic = reader(payload, options=snapshot)
        else:
            semantic = reader(
                payload,
                source_headers=snapshot.source_headers,
                translated=snapshot.translated,
            )
        writer = self.encoder(target)
        if "options" in signature(writer).parameters:
            encoded = writer(semantic, snapshot.target, options=snapshot)
        else:
            encoded = writer(semantic, snapshot.target)
        return encoded, semantic

    def encode_request(
        self,
        semantic: SemanticRequest,
        *,
        target: WireFormat,
        options: TranslationOptions | None = None,
    ) -> dict[str, Any]:
        return self.encode(semantic, target=target, options=options)

    def translate_response(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        target: WireFormat,
        client_search_tool: str = "",
        hosted_web_search_expected: bool = False,
        hand_over_stop_reasons: frozenset[str] | None = None,
        options: TranslationOptions | None = None,
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
        base = options or self._default_options
        snapshot = TranslationOptions(
            source_headers=base.source_headers,
            translated=source is not target,
            target=base.target,
            client_search_tool=client_search_tool or base.client_search_tool,
            hosted_web_search_expected=(
                hosted_web_search_expected or base.hosted_web_search_expected
            ),
            hand_over_stop_reasons=(
                hand_over_stop_reasons
                if hand_over_stop_reasons is not None
                else base.hand_over_stop_reasons
            ),
            model_translation=base.model_translation,
        )
        if "options" in signature(reader).parameters:
            semantic = reader(payload, options=snapshot)
        else:
            semantic = reader(
                payload,
                client_search_tool=snapshot.client_search_tool,
                hosted_web_search_expected=snapshot.hosted_web_search_expected,
                hand_over_stop_reasons=snapshot.hand_over_stop_reasons,
            )
        if "options" in signature(writer).parameters:
            encoded = writer(semantic, options=snapshot)
        else:
            encoded = writer(semantic)
        return encoded, semantic

    def decode_response(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        options: TranslationOptions | None = None,
    ) -> SemanticResponse:
        reader = self._read_response.get(source)
        if reader is None:
            raise TranslatorNotFound(f"no response reader registered for {source.value}")
        snapshot = options or self._default_options
        if "options" in signature(reader).parameters:
            return reader(payload, options=snapshot)
        return reader(
            payload,
            client_search_tool=snapshot.client_search_tool,
            hosted_web_search_expected=snapshot.hosted_web_search_expected,
            hand_over_stop_reasons=snapshot.hand_over_stop_reasons,
        )

    def encode_response(
        self,
        semantic: SemanticResponse,
        *,
        target: WireFormat,
        options: TranslationOptions | None = None,
    ) -> dict[str, Any]:
        writer = self._write_response.get(target)
        if writer is None:
            raise TranslatorNotFound(f"no response writer registered for {target.value}")
        snapshot = options or self._default_options
        if "options" in signature(writer).parameters:
            return writer(semantic, options=snapshot)
        return writer(semantic)


def default_registry(config: ModelTranslationConfig | None = None) -> TranslatorRegistry:
    """Register every translator pair, with the configurable choices bound in.

    Bound here rather than threaded through `translate` so the registry keeps handing out plain `SemanticRequest -> dict` callables: a translator that needed config at call time would put that argument on every pair, including the ones that have nothing to configure.
    """
    settings = config or ModelTranslationConfig()
    registry = TranslatorRegistry(
        TranslationOptions(model_translation=settings)
    )
    registry.register_decoder(WireFormat.ANTHROPIC_MESSAGES, from_anthropic_messages)
    registry.register_encoder(WireFormat.ANTHROPIC_MESSAGES, to_anthropic_messages)
    registry.register_decoder(WireFormat.OPENAI_RESPONSES, from_openai_responses)
    registry.register_encoder(
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
    registry.register_decoder(
        WireFormat.OPENAI_CHAT_COMPLETIONS, from_openai_chat_completions
    )
    registry.register_encoder(
        WireFormat.OPENAI_CHAT_COMPLETIONS, to_openai_chat_completions
    )
    registry.register_response_reader(
        WireFormat.OPENAI_CHAT_COMPLETIONS, from_chat_completions_response
    )
    registry.register_response_writer(
        WireFormat.OPENAI_CHAT_COMPLETIONS, to_openai_chat_completions_response
    )
    return registry
