"""The model catalog, held statically.

The backend advertises no `/models` endpoint — measured by the reference converter
(`refs/codebuddy2api/converter.py`), which serves its own model list from a constant.
This table is that constant, dated: the ids were the reference's `DEFAULT_MODELS` on
2026-09-04. When upstream grows a model the list is extended by hand, which is the
same maintenance the reference accepted; a `disabled_models` entry in the provider
config removes one without a code change.

Every model speaks one endpoint. The upstream's only inference path is
`/v2/chat/completions`, so the descriptor advertises exactly that and the endpoint
gating fails closed for anything else.
"""

from typing import Any

from app.model_provider.types import ModelEndpoint

DEFAULT_MODEL_IDS = (
    "glm-5.2",
    "glm-5.1",
    "glm-5v-turbo",
    "kimi-k2.7",
    "kimi-k2.6",
    "kimi-k2.5",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "minimax-m3-pay",
    "hy3-preview-agent",
    "auto",
)

_CHAT_COMPLETIONS = ModelEndpoint.OPENAI_CHAT_COMPLETIONS.value


def static_catalog() -> dict[str, Any]:
    """The catalog in the same wire shape a Copilot `/models` response takes.

    Kept in that shape so the descriptor builder (`resolve_endpoints`, capabilities)
    and every report that reads a catalog answer one format rather than two.
    """
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "vendor": "codebuddy",
                "supported_endpoints": [_CHAT_COMPLETIONS],
                "capabilities": {"type": "chat"},
                "policy": {"state": "enabled"},
            }
            for model_id in DEFAULT_MODEL_IDS
        ],
    }
