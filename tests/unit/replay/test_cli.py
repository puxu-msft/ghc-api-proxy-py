from __future__ import annotations

import json
import sys

import pytest

from app.replay import __main__ as replay_cli


def test_replay_cli_is_explicitly_disabled_without_history_authority(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "app.replay",
            "--capture",
            "/forged.capture",
            "--entry",
            "forged-entry",
            "--attempt",
            "0",
            "--deadline",
            "1",
        ],
    )

    assert replay_cli.main() == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": {
            "code": "replay_cli_unavailable",
            "message": (
                "replay CLI is disabled because no controlled History "
                "source authority is available"
            ),
            "not_started": True,
        }
    }
