import json
import math
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from app.wire_json import WireJsonEncodeError, dumps, loads


class JsonBoundaryModel(BaseModel):
    created_at: datetime
    payload: bytes


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        42,
        3.5,
        "你好 🌍",
        [1, "two", False],
        {"nested": {"unknown": [1, 2, 3]}, "text": "café"},
    ],
)
def test_differential_round_trip_matches_stdlib(value: object) -> None:
    encoded = dumps(value)

    assert isinstance(encoded, bytes)
    assert loads(encoded) == json.loads(json.dumps(value, ensure_ascii=False))


def test_unknown_nested_fields_are_preserved() -> None:
    value = {"content": [{"type": "future_block", "future": {"enabled": True}}]}

    assert loads(dumps(value)) == value


def test_non_ascii_is_emitted_as_utf8_not_ascii_escape() -> None:
    encoded = dumps({"message": "你好"})

    assert "你好".encode() in encoded
    assert b"\\u4f60" not in encoded


def test_pydantic_json_mode_is_the_explicit_boundary() -> None:
    model = JsonBoundaryModel(
        created_at=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
        payload=b"abc",
    )

    decoded = loads(dumps(model.model_dump(mode="json")))

    assert decoded == {"created_at": "2026-07-15T12:00:00Z", "payload": "abc"}


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_floats_are_rejected(value: float) -> None:
    with pytest.raises(WireJsonEncodeError, match="non-finite"):
        dumps({"value": value})


def test_integer_beyond_json_safe_range_is_rejected() -> None:
    with pytest.raises(WireJsonEncodeError, match="53-bit"):
        dumps({"value": 2**53})


def test_datetime_requires_pydantic_json_mode() -> None:
    with pytest.raises(WireJsonEncodeError, match="datetime"):
        dumps({"created_at": datetime.now(UTC)})


def test_loads_accepts_bytes_bytearray_memoryview_and_text() -> None:
    payload = dumps({"status": "ok"})

    assert loads(payload) == {"status": "ok"}
    assert loads(bytearray(payload)) == {"status": "ok"}
    assert loads(memoryview(payload)) == {"status": "ok"}
    assert loads(payload.decode()) == {"status": "ok"}
