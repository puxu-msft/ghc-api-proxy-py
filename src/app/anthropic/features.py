from collections.abc import Iterable

from app.models.common import ModelInfo
from app.transform.model_resolver import normalize_for_matching

ADAPTIVE_PREFIXES = ("claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8")
CONTEXT_EDITING_PREFIXES = (
    "claude-haiku-4-5",
    "claude-sonnet-4",
    "claude-opus-4",
)


def model_has_adaptive_thinking(model_id: str, model: ModelInfo | None = None) -> bool:
    if model is not None:
        supports = model.capabilities.supports
        if supports.adaptive_thinking:
            return True
        if supports.max_thinking_budget and supports.max_thinking_budget > 0:
            return False
    normalized = normalize_for_matching(model_id)
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}-")
        for prefix in ADAPTIVE_PREFIXES
    )


def model_supports_context_editing(model_id: str, model: ModelInfo | None = None) -> bool:
    if model is not None and model.capabilities.supports.context_editing is not None:
        return model.capabilities.supports.context_editing
    normalized = normalize_for_matching(model_id)
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}-")
        for prefix in CONTEXT_EDITING_PREFIXES
    )


def model_supports_tool_search(model_id: str, model: ModelInfo | None = None) -> bool:
    if model is not None and model.capabilities.supports.tool_search is not None:
        return model.capabilities.supports.tool_search
    normalized = normalize_for_matching(model_id)
    if "haiku" in normalized:
        return False
    return any(
        marker in normalized
        for marker in ("sonnet-4-5", "sonnet-4-6", "opus-4-5", "opus-4-6")
    )


def build_anthropic_beta_headers(
    model_id: str,
    model: ModelInfo | None = None,
    *,
    context_editing: bool = False,
    tool_search: bool = False,
    extended_cache_ttl: bool = False,
    strip: Iterable[str] = (),
) -> dict[str, str]:
    betas: list[str] = []
    if not model_has_adaptive_thinking(model_id, model):
        betas.append("interleaved-thinking-2025-05-14")
    if context_editing:
        betas.append("context-management-2025-06-27")
    if tool_search:
        betas.append("advanced-tool-use-2025-11-20")
    if extended_cache_ttl:
        betas.append("extended-cache-ttl-2025-04-11")
    denied = set(strip)
    selected = [beta for beta in betas if beta not in denied]
    return {"anthropic-beta": ",".join(selected)} if selected else {}
