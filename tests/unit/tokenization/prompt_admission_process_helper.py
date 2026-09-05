from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.tokenization.worker import TokenEstimate


def controlled_count(_tokenizer: str, text: str) -> int:
    control = json.loads(text)
    entered = Path(control["entered"])
    release = Path(control["release"])
    entered.write_text("entered", encoding="utf-8")
    while not release.exists():
        time.sleep(0.01)
    return int(control["result"])


def controlled_estimate(_protocol: str, payload: dict[str, Any]) -> TokenEstimate:
    return TokenEstimate(controlled_count("unused", payload["input"]), ())
