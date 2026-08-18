from app.anthropic.feature_negotiation import (
    NEGOTIATION_CATEGORIES,
    FeatureNegotiationStore,
)
from app.anthropic.features import (
    build_anthropic_beta_headers,
    model_has_adaptive_thinking,
    model_supports_context_editing,
    model_supports_tool_search,
)
from app.models.common import ModelInfo


def test_store_supports_all_9_categories_and_ttl() -> None:
    now = 100.0
    store = FeatureNegotiationStore(default_ttl_seconds=10, clock=lambda: now)
    assert len(NEGOTIATION_CATEGORIES) == 9
    for category in NEGOTIATION_CATEGORIES:
        store.learn(category, "key", "value")
        assert store.is_active(category, "key", "value") is True
    now = 111.0
    for category in NEGOTIATION_CATEGORIES:
        assert store.is_active(category, "key", "value") is False


def test_store_pin_expire_and_config_union() -> None:
    store = FeatureNegotiationStore(default_ttl_seconds=10, clock=lambda: 100)
    store.learn("betas", "model", "learned")
    store.pin("betas", "model", "learned", True)
    store.expire("betas", "model", "learned")
    assert store.is_active("betas", "model", "learned") is True
    assert store.active_values("betas", "model", configured={"configured"}) == {
        "configured",
        "learned",
    }


def test_adaptive_thinking_prefers_metadata() -> None:
    model = ModelInfo.model_validate(
        {
            "id": "future-model",
            "capabilities": {"supports": {"adaptive_thinking": True}},
        }
    )
    assert model_has_adaptive_thinking(model.id, model) is True


def test_beta_headers_are_capability_driven_and_filtered() -> None:
    model = ModelInfo(id="claude-opus-4.6")
    headers = build_anthropic_beta_headers(
        model.id,
        model,
        context_editing=True,
        tool_search=True,
        strip={"context-management-2025-06-27"},
    )
    assert "context-management-2025-06-27" not in headers.get("anthropic-beta", "")


def test_context_editing_and_tool_search_detection() -> None:
    model = ModelInfo.model_validate(
        {
            "id": "future-model",
            "capabilities": {"supports": {"context_editing": True, "tool_search": True}},
        }
    )
    assert model_supports_context_editing(model.id, model) is True
    assert model_supports_tool_search(model.id, model) is True
