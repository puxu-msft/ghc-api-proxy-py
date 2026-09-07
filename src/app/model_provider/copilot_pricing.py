"""The local snapshot of GitHub Copilot model pricing.

The upstream model catalog describes capabilities and legacy billing flags, but it
does not carry the current usage-based token prices. The bundled snapshot is
therefore the local cache used by the model metadata endpoints.
"""

import json
from importlib.resources import files
from typing import Any, cast

_SOURCE = "source"
_RETRIEVED_AT = "retrieved_at"
_CURRENCY = "currency"
_UNIT = "unit"
_MODELS = "models"
_RATES = ("input", "cached_input", "cache_write", "output")
_MODEL_ALIASES = {"mai-code-1-flash-picker": "mai-code-1-flash"}


def _load_snapshot() -> dict[str, Any]:
    raw = files("app.model_provider").joinpath("copilot_pricing.json").read_text(
        encoding="utf-8"
    )
    snapshot = json.loads(raw)
    if not isinstance(snapshot, dict):
        raise ValueError("Copilot pricing snapshot must be an object")
    return cast(dict[str, Any], snapshot)


_SNAPSHOT = _load_snapshot()


def _number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None


def _credits(value: int | float) -> int | float:
    converted = value * 100
    if isinstance(converted, int):
        return converted
    return int(converted) if converted.is_integer() else converted


def _normalized_tier(tier: object) -> dict[str, Any]:
    if not isinstance(tier, dict):
        raise ValueError("Copilot pricing tier must be an object")
    source = cast(dict[str, Any], tier)
    normalized = {
        key: value
        for key, value in source.items()
        if key in {"name", "input_min_tokens", "input_max_tokens"}
    }
    rates: dict[str, int | float] = {}
    for key in _RATES:
        value = _number(source.get(key))
        if value is None:
            if key == "cache_write":
                # The official table spells this as "Not applicable". Zero is
                # the machine-readable equivalent for a pricing field.
                rates[key] = 0
                continue
            raise ValueError(f"Copilot pricing tier is missing numeric {key!r}")
        rates[key] = value
    normalized.update(rates)
    normalized["credits"] = {key: _credits(value) for key, value in rates.items()}
    return normalized


def pricing_for(model_id: str) -> dict[str, Any] | None:
    """Return a copy of the current local price entry for one upstream model."""
    models_value = _SNAPSHOT.get(_MODELS)
    if not isinstance(models_value, dict):
        raise ValueError("Copilot pricing snapshot has no models object")
    models = cast(dict[str, Any], models_value)
    key = _MODEL_ALIASES.get(model_id, model_id)
    raw = models.get(key)
    if not isinstance(raw, dict):
        return None
    source = cast(dict[str, Any], raw)
    tiers = source.get("tiers")
    if not isinstance(tiers, list):
        raise ValueError(f"Copilot pricing entry {key!r} has no tiers list")
    typed_tiers = cast(list[Any], tiers)
    return {
        "currency": _SNAPSHOT.get(_CURRENCY, "USD"),
        "unit": _SNAPSHOT.get(_UNIT, "per_1m_tokens"),
        "source": _SNAPSHOT.get(_SOURCE),
        "retrieved_at": _SNAPSHOT.get(_RETRIEVED_AT),
        "tiers": [_normalized_tier(tier) for tier in typed_tiers],
    }
