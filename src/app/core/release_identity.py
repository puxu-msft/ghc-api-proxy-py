from __future__ import annotations

import re

_RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*\Z")


class ReleaseIdentityError(ValueError):
    pass


def parse_release_id(value: str) -> str:
    if value in {".", ".."} or _RELEASE_ID.fullmatch(value) is None:
        raise ReleaseIdentityError(f"release id is not canonical: {value!r}")
    return value
