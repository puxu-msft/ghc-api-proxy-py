from typing import cast

from app.wire_json import JsonValue


def _normalize_id(value: str) -> str:
    return f"fc_{value.removeprefix('call_')}" if value.startswith("call_") else value


def normalize_call_ids(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        mapping = cast(dict[str, JsonValue], value)
        return {
            key: _normalize_id(item) if key in ("id", "call_id") and isinstance(item, str)
            else normalize_call_ids(item)
            for key, item in mapping.items()
        }
    if isinstance(value, list):
        return [normalize_call_ids(item) for item in cast(list[JsonValue], value)]
    return value