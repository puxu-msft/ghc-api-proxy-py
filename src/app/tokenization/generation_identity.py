from __future__ import annotations

import re

_GENERATION_ID = re.compile(r"g([0-9]{16,})\Z")


class GenerationIdentityError(ValueError):
    """Raised when a generation identifier is not canonical."""


def parse_generation_id(value: str) -> int:
    match = _GENERATION_ID.fullmatch(value)
    if match is None:
        raise GenerationIdentityError(
            "generation id must be 'g' followed by at least 16 decimal digits"
        )
    number = int(match.group(1))
    canonical = f"g{number:016d}"
    if value != canonical:
        raise GenerationIdentityError(f"generation id is not canonical: {value!r}")
    return number
