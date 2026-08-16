"""Translator registry.

Translators register under the names MAIN.md uses.
`inbound.from-<format>` and `outbound.to-<format>`, so a format is added by registering a pair.
"""

from collections.abc import Callable, Mapping
from typing import Any

from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.responses import SemanticResponse
from app.pipeline.translation_driver.semantic import SemanticRequest

type InboundTranslator = Callable[[Mapping[str, Any]], SemanticRequest]
type OutboundTranslator = Callable[[SemanticRequest], dict[str, Any]]
type ResponseReader = Callable[[Mapping[str, Any]], SemanticResponse]
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
    ) -> tuple[dict[str, Any], SemanticRequest]:
        """Carry a payload from one wire format to another through the intermediate form.

        Both translators are looked up before either runs.
        A missing pair therefore fails whole rather than after half a conversion.
        """
        to_semantic = self.inbound(source)
        to_wire = self.outbound(target)
        semantic = to_semantic(payload)
        return to_wire(semantic), semantic


    def translate_response(
        self,
        payload: Mapping[str, Any],
        *,
        source: WireFormat,
        target: WireFormat,
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
        semantic = reader(payload)
        return writer(semantic), semantic
