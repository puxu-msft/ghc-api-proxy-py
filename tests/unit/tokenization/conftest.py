from collections.abc import Callable
from typing import Any

import pytest

import app.tokenization.admission as admission_module


@pytest.fixture(autouse=True)
def inline_token_admission_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep admission-shape tests in-process; process semantics have dedicated tests."""

    async def run_sync(
        function: Callable[..., Any],
        *args: Any,
        **_kwargs: Any,
    ) -> Any:
        return function(*args)

    monkeypatch.setattr(admission_module, "run_sync", run_sync)
