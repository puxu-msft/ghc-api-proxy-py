"""Immutable per-request options shared by every wire codec stage."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from app.config.schema import ModelTranslationConfig
from app.pipeline.translation_driver.semantic import TranslationTarget


@dataclass(frozen=True, slots=True)
class TranslationOptions:
    """The complete codec snapshot for one request and all its retries."""

    source_headers: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    translated: bool = False
    target: TranslationTarget = field(default_factory=TranslationTarget)
    client_search_tool: str = ""
    hosted_web_search_expected: bool = False
    hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"})
    model_translation: ModelTranslationConfig | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_headers",
            MappingProxyType(dict(self.source_headers)),
        )

