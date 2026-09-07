from __future__ import annotations

import base64
import binascii
import hashlib
import math
import time
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import orjson
import tiktoken

from app.observability.metrics import RESPONSIVENESS
from app.tokenization.types import (
    EstimateFeatures,
    EstimatorTiming,
    FeatureName,
    FeatureVector,
    PrefixFingerprint,
    ProfileKey,
    TokenComponent,
)

TOKENIZER_NAME = "o200k_base"
ESTIMATOR_GENERATION = 1
PROFILE_SCHEMA_REVISION = 1
_PREFIX_DOMAIN = b"ghc-api-proxy:responses-prefix:v1\0"
_COMPONENT_KINDS = (
    "framing",
    "function_call",
    "function_output",
    "instructions",
    "message",
    "reasoning_summary",
    "tools",
)
_ALWAYS_PRESENT_FEATURES = frozenset(
    {
        FeatureName.KNOWN_TOTAL,
        FeatureName.MESSAGE_ITEM_COUNT,
        FeatureName.FUNCTION_CALL_ITEM_COUNT,
        FeatureName.FUNCTION_OUTPUT_ITEM_COUNT,
        FeatureName.REASONING_ITEM_COUNT,
        FeatureName.MEDIA_COUNT,
        FeatureName.UNKNOWN_ITEM_COUNT,
    }
)
_KNOWN_TOP_LEVEL_FIELDS = frozenset(
    {
        "background",
        "client_metadata",
        "context_management",
        "conversation",
        "include",
        "input",
        "instructions",
        "max_output_tokens",
        "max_tool_calls",
        "metadata",
        "model",
        "parallel_tool_calls",
        "previous_response_id",
        "prompt_cache_key",
        "reasoning",
        "safety_identifier",
        "service_tier",
        "store",
        "stream",
        "temperature",
        "text",
        "tool_choice",
        "tools",
        "top_logprobs",
        "top_p",
        "truncation",
        "user",
    }
)
_KNOWN_ITEM_FIELDS = {
    "function_call": frozenset(
        {"agent", "arguments", "call_id", "caller", "id", "name", "status", "type"}
    ),
    "function_call_output": frozenset(
        {"agent", "call_id", "caller", "id", "name", "output", "status", "type"}
    ),
    "message": frozenset({"agent", "content", "id", "role", "status", "type"}),
    "reasoning": frozenset({"agent", "encrypted_content", "id", "status", "summary", "type"}),
}
_TEXT_PART_FIELDS = frozenset(
    {"annotations", "logprobs", "prompt_cache_breakpoint", "text", "type"}
)
_MEDIA_PART_FIELDS = frozenset(
    {
        "cache_control",
        "data",
        "detail",
        "file_data",
        "file_id",
        "file_url",
        "filename",
        "height",
        "image_url",
        "media_type",
        "mime_type",
        "page_count",
        "prompt_cache_breakpoint",
        "source",
        "transformations",
        "type",
        "width",
    }
)
_SUMMARY_PART_FIELDS = frozenset({"text", "type"})
_MEDIA_TYPES = frozenset({"document", "file", "image", "input_file", "input_image"})
_TEXT_PART_TYPES = frozenset({"input_text", "output_text", "text"})

OPAQUE_BYTES_REASON = "zero-prior:responses.opaque-reasoning-bytes"
OPAQUE_ITEMS_REASON = "zero-prior:responses.opaque-reasoning-items"
MEDIA_REASON = "zero-prior:media-without-capability-formula"
PDF_REASON = "zero-prior:pdf-without-capability-formula"
UNKNOWN_BYTES_REASON = "zero-prior:unknown-json-bytes"
UNKNOWN_ITEMS_REASON = "zero-prior:unknown-items"


@contextmanager
def _measure(
    phase: Literal["lookup", "estimate"],
    timings: list[EstimatorTiming] | None,
) -> Generator[None]:
    if timings is None:
        with RESPONSIVENESS.tokenizer[("responses", phase)].measure():
            yield
        return
    started = time.monotonic()
    failed = True
    try:
        yield
        failed = False
    finally:
        timings.append(
            EstimatorTiming(
                "responses",
                phase,
                time.monotonic() - started,
                failed,
            )
        )


def count_ordinary(encoding: tiktoken.Encoding, text: str) -> int:
    return len(encoding.encode_ordinary(text))


def _json_ready(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not permit non-finite floats")
        return value
    if isinstance(value, Mapping):
        ready: dict[str, object] = {}
        for key, nested in cast(Mapping[object, object], value).items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            ready[key] = _json_ready(nested)
        return ready
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview, str)):
        return [_json_ready(nested) for nested in cast(Sequence[object], value)]
    raise TypeError("value is not canonical JSON")


def _canonical_json(value: object) -> bytes:
    return orjson.dumps(_json_ready(value), option=orjson.OPT_SORT_KEYS | orjson.OPT_STRICT_INTEGER)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _input_items(payload: Mapping[str, Any]) -> tuple[object, ...]:
    if "input" not in payload:
        return ()
    value = payload.get("input")
    if isinstance(value, list):
        return tuple(cast(list[object], value))
    return (value,)


def _fingerprints(
    payload: Mapping[str, Any],
) -> tuple[str, str, tuple[PrefixFingerprint, ...]]:
    full_payload = {key: value for key, value in payload.items() if key != "stream"}
    context_payload = {
        key: value for key, value in payload.items() if key not in {"input", "stream"}
    }
    full_fingerprint = _sha256(_canonical_json(full_payload))
    context_digest = hashlib.sha256(_canonical_json(context_payload)).digest()
    context_fingerprint = context_digest.hex()
    previous = context_digest
    prefixes: list[PrefixFingerprint] = []
    for item_count, item in enumerate(_input_items(payload), start=1):
        encoded_item = _canonical_json(item)
        folded = hashlib.sha256()
        folded.update(_PREFIX_DOMAIN)
        folded.update(len(previous).to_bytes(8, "big"))
        folded.update(previous)
        folded.update(len(encoded_item).to_bytes(8, "big"))
        folded.update(encoded_item)
        previous = folded.digest()
        prefixes.append(PrefixFingerprint(item_count=item_count, digest=previous.hex()))
    return full_fingerprint, context_fingerprint, tuple(prefixes)


def _empty_string_set() -> set[str]:
    return set()


@dataclass(slots=True)
class _Analysis:
    encoding: tiktoken.Encoding
    component_tokens: dict[str, int] = field(
        default_factory=lambda: {kind: 0 for kind in _COMPONENT_KINDS}
    )
    component_instances: dict[str, int] = field(
        default_factory=lambda: {kind: 0 for kind in _COMPONENT_KINDS}
    )
    feature_values: dict[FeatureName, int | None] = field(
        default_factory=lambda: {
            name: 0 if name in _ALWAYS_PRESENT_FEATURES else None for name in FeatureName
        }
    )
    item_kinds: set[str] = field(default_factory=_empty_string_set)
    reasoning_origins: set[str] = field(default_factory=_empty_string_set)
    media_kinds: set[str] = field(default_factory=_empty_string_set)
    unknown_type_digests: set[str] = field(default_factory=_empty_string_set)
    low_confidence_reasons: set[str] = field(default_factory=_empty_string_set)

    def add_text(self, component: str, feature: FeatureName, text: str) -> None:
        count = count_ordinary(self.encoding, text)
        self.component_tokens[component] += count
        self.component_instances[component] += 1
        self.increment(feature, count)

    def add_structured_text(self, component: str, feature: FeatureName, value: object) -> None:
        self.add_text(component, feature, _canonical_json(value).decode("utf-8"))

    def add_framing(self, instances: int = 1) -> None:
        self.component_tokens["framing"] += 4 * instances
        self.component_instances["framing"] += instances

    def increment(self, feature: FeatureName, amount: int) -> None:
        current = self.feature_values[feature]
        self.feature_values[feature] = (current or 0) + amount

    def mark_present(self, feature: FeatureName) -> None:
        if self.feature_values[feature] is None:
            self.feature_values[feature] = 0

    def record_unknown(self, type_name: str, value: object) -> None:
        self.unknown_type_digests.add(_sha256(type_name.encode("utf-8")))
        self.increment(FeatureName.UNKNOWN_ITEM_COUNT, 1)
        self.increment(FeatureName.UNKNOWN_JSON_BYTES, len(_canonical_json(value)))
        self.low_confidence_reasons.update({UNKNOWN_BYTES_REASON, UNKNOWN_ITEMS_REASON})

    def record_media(self, value: Mapping[str, Any], item_type: str) -> None:
        self.increment(FeatureName.MEDIA_COUNT, 1)
        category = _media_category(value, item_type)
        source_kind = _media_source_kind(value)
        self.media_kinds.add(f"{category}:{source_kind}")
        self.low_confidence_reasons.add(MEDIA_REASON)
        decoded_bytes = _media_decoded_bytes(value)
        if decoded_bytes is not None:
            self.increment(FeatureName.MEDIA_DECODED_BYTES, decoded_bytes)
        pixel_count = _media_pixel_count(value)
        if pixel_count is not None:
            self.increment(FeatureName.MEDIA_PIXEL_COUNT, pixel_count)
        pdf_pages = _media_pdf_pages(value)
        if pdf_pages is not None:
            self.increment(FeatureName.PDF_PAGES, pdf_pages)
        if category == "pdf":
            self.low_confidence_reasons.add(PDF_REASON)

    def finish(self, payload: Mapping[str, Any]) -> EstimateFeatures:
        components = tuple(
            TokenComponent(
                kind=kind,
                tokens=self.component_tokens[kind],
                instances=self.component_instances[kind],
            )
            for kind in sorted(_COMPONENT_KINDS)
        )
        known_tokens = sum(component.tokens for component in components)
        self.feature_values[FeatureName.KNOWN_TOTAL] = known_tokens
        all_unknown_digests = sorted(self.unknown_type_digests, key=bytes.fromhex)
        retained_unknown_digests = tuple(all_unknown_digests[:8])
        full_fingerprint, context_fingerprint, prefix_fingerprints = _fingerprints(payload)
        return EstimateFeatures(
            known_tokens=known_tokens,
            components=components,
            profile_key=ProfileKey(
                item_kinds=tuple(sorted(self.item_kinds)),
                reasoning_origins=tuple(sorted(self.reasoning_origins)),
                media_kinds=tuple(sorted(self.media_kinds)),
                unknown_type_digests=retained_unknown_digests,
                unknown_type_count=len(all_unknown_digests),
                unknown_type_overflow=len(all_unknown_digests) > 8,
                has_previous_response_id="previous_response_id" in payload,
                context_management_mode=_context_management_mode(payload),
                truncation_mode=_truncation_mode(payload),
            ),
            feature_vector=FeatureVector.from_observations(self.feature_values),
            full_fingerprint=full_fingerprint,
            context_fingerprint=context_fingerprint,
            prefix_fingerprints=prefix_fingerprints,
            low_confidence_reasons=tuple(sorted(self.low_confidence_reasons)),
            estimator_generation=ESTIMATOR_GENERATION,
            profile_schema_revision=PROFILE_SCHEMA_REVISION,
        )


def _record_unknown_fields(
    analysis: _Analysis,
    value: Mapping[str, Any],
    allowed: frozenset[str],
    owner: str,
) -> None:
    for key in sorted(set(value) - allowed):
        analysis.record_unknown(f"{owner}.{key}", {key: value[key]})


def _textual_value(
    analysis: _Analysis,
    component: str,
    feature: FeatureName,
    value: object,
) -> None:
    if isinstance(value, str):
        analysis.add_text(component, feature, value)
    else:
        analysis.add_structured_text(component, feature, value)


def _analyze_message(analysis: _Analysis, item: Mapping[str, Any]) -> None:
    analysis.increment(FeatureName.MESSAGE_ITEM_COUNT, 1)
    analysis.mark_present(FeatureName.MESSAGE_TOKENS)
    role = item.get("role")
    if isinstance(role, str):
        analysis.add_text("message", FeatureName.MESSAGE_TOKENS, role)
    elif "role" in item:
        analysis.record_unknown("message.role", {"role": role})
    if "content" in item:
        content = item.get("content")
        if isinstance(content, str):
            analysis.add_text("message", FeatureName.MESSAGE_TOKENS, content)
        elif isinstance(content, list):
            for part in cast(list[object], content):
                analysis.add_framing()
                _analyze_message_part(analysis, part)
        else:
            analysis.record_unknown("message.content", {"content": content})
    _record_unknown_fields(analysis, item, _KNOWN_ITEM_FIELDS["message"], "message")


def _analyze_message_part(analysis: _Analysis, raw_part: object) -> None:
    if not isinstance(raw_part, Mapping):
        analysis.record_unknown(f"message-part:{_json_kind(raw_part)}", raw_part)
        return
    part = cast(Mapping[str, Any], raw_part)
    part_type = part.get("type")
    if isinstance(part_type, str) and part_type in _TEXT_PART_TYPES:
        text = part.get("text")
        if isinstance(text, str):
            analysis.add_text("message", FeatureName.MESSAGE_TOKENS, text)
        elif "text" in part:
            analysis.record_unknown(f"message-part:{part_type}:text", {"text": text})
        _record_unknown_fields(analysis, part, _TEXT_PART_FIELDS, f"message-part:{part_type}")
        return
    if isinstance(part_type, str) and part_type in _MEDIA_TYPES:
        analysis.record_media(part, part_type)
        _record_unknown_fields(analysis, part, _MEDIA_PART_FIELDS, f"media-part:{part_type}")
        return
    analysis.record_unknown(
        part_type if isinstance(part_type, str) else f"message-part:{_json_kind(part_type)}",
        part,
    )


def _analyze_function_call(analysis: _Analysis, item: Mapping[str, Any]) -> None:
    analysis.increment(FeatureName.FUNCTION_CALL_ITEM_COUNT, 1)
    analysis.mark_present(FeatureName.FUNCTION_CALL_TOKENS)
    for key in ("call_id", "name", "arguments"):
        if key in item and item[key] is not None:
            _textual_value(
                analysis,
                "function_call",
                FeatureName.FUNCTION_CALL_TOKENS,
                item[key],
            )
    _record_unknown_fields(
        analysis,
        item,
        _KNOWN_ITEM_FIELDS["function_call"],
        "function_call",
    )


def _analyze_function_output(analysis: _Analysis, item: Mapping[str, Any]) -> None:
    analysis.increment(FeatureName.FUNCTION_OUTPUT_ITEM_COUNT, 1)
    analysis.mark_present(FeatureName.FUNCTION_OUTPUT_TOKENS)
    if "call_id" in item and item["call_id"] is not None:
        _textual_value(
            analysis,
            "function_output",
            FeatureName.FUNCTION_OUTPUT_TOKENS,
            item["call_id"],
        )
    if "output" in item and item["output"] is not None:
        output = item["output"]
        if isinstance(output, list):
            for part in cast(list[object], output):
                analysis.add_framing()
                _analyze_function_output_part(analysis, part)
        else:
            _textual_value(
                analysis,
                "function_output",
                FeatureName.FUNCTION_OUTPUT_TOKENS,
                output,
            )
    _record_unknown_fields(
        analysis,
        item,
        _KNOWN_ITEM_FIELDS["function_call_output"],
        "function_call_output",
    )


def _analyze_function_output_part(analysis: _Analysis, raw_part: object) -> None:
    if not isinstance(raw_part, Mapping):
        analysis.record_unknown(f"function-output-part:{_json_kind(raw_part)}", raw_part)
        return
    part = cast(Mapping[str, Any], raw_part)
    part_type = part.get("type")
    if part_type == "input_text":
        text = part.get("text")
        if isinstance(text, str):
            analysis.add_text(
                "function_output",
                FeatureName.FUNCTION_OUTPUT_TOKENS,
                text,
            )
        elif "text" in part:
            analysis.record_unknown("function-output-part:input_text:text", {"text": text})
        _record_unknown_fields(
            analysis,
            part,
            _TEXT_PART_FIELDS,
            "function-output-part:input_text",
        )
        return
    if isinstance(part_type, str) and part_type in {"input_image", "input_file"}:
        analysis.record_media(part, part_type)
        _record_unknown_fields(
            analysis,
            part,
            _MEDIA_PART_FIELDS,
            f"function-output-part:{part_type}",
        )
        return
    analysis.record_unknown(
        part_type if isinstance(part_type, str) else f"function-output-part:{_json_kind(part_type)}",
        part,
    )


def _analyze_reasoning(analysis: _Analysis, item: Mapping[str, Any]) -> None:
    analysis.increment(FeatureName.REASONING_ITEM_COUNT, 1)
    analysis.reasoning_origins.add("responses-agent" if "agent" in item else "responses")
    if "summary" in item:
        analysis.mark_present(FeatureName.REASONING_SUMMARY_TOKENS)
        summary = item.get("summary")
        if isinstance(summary, str):
            analysis.add_text(
                "reasoning_summary",
                FeatureName.REASONING_SUMMARY_TOKENS,
                summary,
            )
        elif isinstance(summary, list):
            for part in cast(list[object], summary):
                analysis.add_framing()
                _analyze_summary_part(analysis, part)
        else:
            analysis.record_unknown("reasoning.summary", {"summary": summary})
    if "encrypted_content" in item:
        encrypted = item.get("encrypted_content")
        analysis.mark_present(FeatureName.OPAQUE_REASONING_BYTES)
        if isinstance(encrypted, str):
            analysis.increment(FeatureName.OPAQUE_REASONING_BYTES, len(encrypted.encode("utf-8")))
        elif encrypted is not None:
            analysis.increment(FeatureName.OPAQUE_REASONING_BYTES, len(_canonical_json(encrypted)))
            analysis.record_unknown("reasoning.encrypted_content", {"encrypted_content": encrypted})
        analysis.low_confidence_reasons.update({OPAQUE_BYTES_REASON, OPAQUE_ITEMS_REASON})
    _record_unknown_fields(analysis, item, _KNOWN_ITEM_FIELDS["reasoning"], "reasoning")


def _analyze_summary_part(analysis: _Analysis, raw_part: object) -> None:
    if not isinstance(raw_part, Mapping):
        analysis.record_unknown(f"reasoning-summary:{_json_kind(raw_part)}", raw_part)
        return
    part = cast(Mapping[str, Any], raw_part)
    part_type = part.get("type")
    if part_type == "summary_text":
        text = part.get("text")
        if isinstance(text, str):
            analysis.add_text(
                "reasoning_summary",
                FeatureName.REASONING_SUMMARY_TOKENS,
                text,
            )
        elif "text" in part:
            analysis.record_unknown("reasoning-summary:summary_text:text", {"text": text})
        _record_unknown_fields(
            analysis,
            part,
            _SUMMARY_PART_FIELDS,
            "reasoning-summary:summary_text",
        )
        return
    analysis.record_unknown(
        part_type if isinstance(part_type, str) else f"reasoning-summary:{_json_kind(part_type)}",
        part,
    )


def _analyze_item(analysis: _Analysis, raw_item: object) -> None:
    analysis.add_framing()
    if isinstance(raw_item, str):
        analysis.item_kinds.add("input_text")
        analysis.increment(FeatureName.MESSAGE_ITEM_COUNT, 1)
        analysis.mark_present(FeatureName.MESSAGE_TOKENS)
        analysis.add_text("message", FeatureName.MESSAGE_TOKENS, raw_item)
        return
    if not isinstance(raw_item, Mapping):
        analysis.item_kinds.add("unknown")
        analysis.record_unknown(f"input-item:{_json_kind(raw_item)}", raw_item)
        return
    item = cast(Mapping[str, Any], raw_item)
    item_type = item.get("type")
    if item_type == "message":
        analysis.item_kinds.add("message")
        _analyze_message(analysis, item)
        return
    if item_type == "function_call":
        analysis.item_kinds.add("function_call")
        _analyze_function_call(analysis, item)
        return
    if item_type == "function_call_output":
        analysis.item_kinds.add("function_call_output")
        _analyze_function_output(analysis, item)
        return
    if item_type == "reasoning":
        analysis.item_kinds.add("reasoning")
        _analyze_reasoning(analysis, item)
        return
    if isinstance(item_type, str) and item_type in _MEDIA_TYPES:
        analysis.item_kinds.add(item_type)
        analysis.record_media(item, item_type)
        _record_unknown_fields(analysis, item, _MEDIA_PART_FIELDS, f"media-item:{item_type}")
        return
    analysis.item_kinds.add("unknown")
    analysis.record_unknown(
        item_type if isinstance(item_type, str) else f"input-item:{_json_kind(item_type)}",
        item,
    )


def _analyze_top_level(analysis: _Analysis, payload: Mapping[str, Any]) -> None:
    if "instructions" in payload:
        instructions = payload.get("instructions")
        if isinstance(instructions, str):
            analysis.mark_present(FeatureName.INSTRUCTIONS_TOKENS)
            if instructions:
                analysis.add_text(
                    "instructions",
                    FeatureName.INSTRUCTIONS_TOKENS,
                    instructions,
                )
                analysis.add_framing()
        elif instructions is not None:
            analysis.record_unknown("top-level.instructions", {"instructions": instructions})
            if instructions:
                analysis.add_framing()
    if "tools" in payload:
        tools = payload.get("tools")
        analysis.mark_present(FeatureName.TOOLS_TOKENS)
        if tools:
            analysis.add_structured_text("tools", FeatureName.TOOLS_TOKENS, tools)
            declaration_count = len(cast(list[object], tools)) if isinstance(tools, list) else 1
            analysis.add_framing(1 + declaration_count)
    for raw_item in _input_items(payload):
        _analyze_item(analysis, raw_item)
    _record_unknown_fields(analysis, payload, _KNOWN_TOP_LEVEL_FIELDS, "top-level")


def _json_kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview, str)):
        return "array"
    return "unsupported"


def _context_management_mode(payload: Mapping[str, Any]) -> str:
    if "context_management" not in payload:
        return "absent"
    value = payload.get("context_management")
    if value is None:
        return "null"
    if isinstance(value, str):
        return value or "empty-string"
    if isinstance(value, Mapping):
        context = cast(Mapping[str, Any], value)
        mode = context.get("type")
        if isinstance(mode, str) and mode:
            return f"object:{mode}"
        edits = context.get("edits")
        if isinstance(edits, list):
            edit_types: set[str] = set()
            for raw_edit in cast(list[object], edits):
                if isinstance(raw_edit, Mapping):
                    edit = cast(Mapping[str, Any], raw_edit)
                    edit_type = edit.get("type")
                    if isinstance(edit_type, str):
                        edit_types.add(edit_type)
            ordered_edit_types = sorted(edit_types)
            return "edits:" + (",".join(ordered_edit_types) if ordered_edit_types else "empty")
        return "object"
    if isinstance(value, list):
        modes: set[str] = set()
        for raw_entry in cast(list[object], value):
            if isinstance(raw_entry, Mapping):
                entry = cast(Mapping[str, Any], raw_entry)
                mode = entry.get("type")
                if isinstance(mode, str):
                    modes.add(mode)
        ordered_modes = sorted(modes)
        return "list:" + (",".join(ordered_modes) if ordered_modes else "empty")
    return f"invalid:{_json_kind(value)}"


def _truncation_mode(payload: Mapping[str, Any]) -> str:
    if "truncation" not in payload:
        return "absent"
    value = payload.get("truncation")
    if isinstance(value, str):
        return value or "empty-string"
    if value is None:
        return "null"
    return f"invalid:{_json_kind(value)}"


def _media_category(value: Mapping[str, Any], item_type: str) -> str:
    media_type = _media_type(value)
    if item_type in {"document", "file", "input_file"} or media_type == "application/pdf":
        return "pdf" if media_type == "application/pdf" else "document"
    return "image"


def _media_type(value: Mapping[str, Any]) -> str | None:
    for key in ("media_type", "mime_type"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            return candidate.lower()
    raw_source = value.get("source")
    if isinstance(raw_source, Mapping):
        source = cast(Mapping[str, Any], raw_source)
        for key in ("media_type", "mime_type"):
            candidate = source.get(key)
            if isinstance(candidate, str):
                return candidate.lower()
    for key in ("image_url", "file_data"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.startswith("data:"):
            header = candidate.partition(",")[0]
            return header.removeprefix("data:").partition(";")[0].lower() or None
    return None


def _media_source_kind(value: Mapping[str, Any]) -> str:
    raw_source = value.get("source")
    if isinstance(raw_source, Mapping):
        source = cast(Mapping[str, Any], raw_source)
        source_type = source.get("type")
        if source_type in {"base64", "file", "url"}:
            return cast(str, source_type)
    if isinstance(value.get("file_id"), str):
        return "file"
    for key in ("image_url", "file_url"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            return "base64" if candidate.startswith("data:") else "url"
    if isinstance(value.get("file_data"), str):
        return "base64"
    return "unknown"


def _decode_base64(text: str, *, data_url_required: bool) -> int | None:
    encoded = text
    if text.startswith("data:"):
        header, separator, encoded = text.partition(",")
        if not separator or ";base64" not in header.lower():
            return None
    elif data_url_required:
        return None
    try:
        return len(base64.b64decode(encoded, validate=True))
    except (binascii.Error, ValueError):
        return None


def _media_decoded_bytes(value: Mapping[str, Any]) -> int | None:
    raw_source = value.get("source")
    if isinstance(raw_source, Mapping):
        source = cast(Mapping[str, Any], raw_source)
        if source.get("type") == "base64":
            data = source.get("data")
            if isinstance(data, str):
                return _decode_base64(data, data_url_required=False)
    image_url = value.get("image_url")
    if isinstance(image_url, str):
        return _decode_base64(image_url, data_url_required=True)
    file_data = value.get("file_data")
    if isinstance(file_data, str):
        return _decode_base64(file_data, data_url_required=False)
    if value.get("type") == "base64" and isinstance(value.get("data"), str):
        return _decode_base64(cast(str, value["data"]), data_url_required=False)
    return None


def _metadata_integer(value: Mapping[str, Any], key: str) -> int | None:
    candidate = value.get(key)
    if type(candidate) is int and candidate >= 0:
        return candidate
    raw_source = value.get("source")
    if isinstance(raw_source, Mapping):
        source = cast(Mapping[str, Any], raw_source)
        candidate = source.get(key)
        if type(candidate) is int and candidate >= 0:
            return candidate
    return None


def _media_pixel_count(value: Mapping[str, Any]) -> int | None:
    width = _metadata_integer(value, "width")
    height = _metadata_integer(value, "height")
    if width is None or height is None:
        return None
    return width * height


def _media_pdf_pages(value: Mapping[str, Any]) -> int | None:
    return _metadata_integer(value, "page_count")


def analyze_responses_input(
    payload: Mapping[str, Any],
    *,
    timings: list[EstimatorTiming] | None = None,
) -> EstimateFeatures:
    with _measure("lookup", timings):
        encoding = tiktoken.get_encoding(TOKENIZER_NAME)
    with _measure("estimate", timings):
        analysis = _Analysis(encoding)
        _analyze_top_level(analysis, payload)
        return analysis.finish(payload)
