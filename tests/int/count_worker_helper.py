import time
from pathlib import Path
from typing import Any

from app.tokenization.worker import TokenEstimate


def blocked_count_job(_protocol: str, payload: dict[str, Any]) -> TokenEstimate:
    control = payload["metadata"]
    entered = Path(control["entered"])
    release = Path(control["release"])
    entered.write_text("entered", encoding="utf-8")
    deadline = time.monotonic() + 10
    while not release.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("test worker barrier was not released")
        time.sleep(0.01)
    return TokenEstimate(17, ())
