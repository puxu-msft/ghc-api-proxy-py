import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from enum import Enum
from typing import Any, cast

import orjson

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
class WireJsonEncodeError(ValueError):
    pass


def _validate_wire_value(value: object, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if abs(value) > 2**53 - 1:
            raise WireJsonEncodeError(f"integer at {path} exceeds the JSON-safe 53-bit range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WireJsonEncodeError(f"non-finite float at {path} is not valid wire JSON")
        return
    if isinstance(value, (datetime, date, time)):
        raise WireJsonEncodeError(
            f"datetime-like value at {path} requires Pydantic model_dump(mode='json')"
        )
    if isinstance(value, Enum):
        _validate_wire_value(value.value, path)
        return
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        for key, nested in mapping.items():
            if not isinstance(key, str):
                raise WireJsonEncodeError(f"object key at {path} must be a string")
            _validate_wire_value(nested, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(
        value,
        (bytes, bytearray, memoryview),
    ):
        sequence = cast(Sequence[object], value)
        for index, nested in enumerate(sequence):
            _validate_wire_value(nested, f"{path}[{index}]")
        return
    raise WireJsonEncodeError(f"unsupported wire JSON value at {path}")


def dumps(value: object) -> bytes:
    _validate_wire_value(value)
    try:
        return orjson.dumps(cast(Any, value), option=orjson.OPT_STRICT_INTEGER)
    except (orjson.JSONEncodeError, TypeError) as error:
        raise WireJsonEncodeError(str(error)) from error


def loads(data: bytes | bytearray | memoryview | str) -> JsonValue:
    value: JsonValue = orjson.loads(data)
    return value
