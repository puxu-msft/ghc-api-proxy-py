from __future__ import annotations

import json
import time
from pathlib import Path


def controlled_count(_tokenizer: str, text: str) -> int:
    control = json.loads(text)
    entered = Path(control["entered"])
    release = Path(control["release"])
    entered.write_text("entered", encoding="utf-8")
    while not release.exists():
        time.sleep(0.01)
    return int(control["result"])
