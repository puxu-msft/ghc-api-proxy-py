"""Entry for the client end-to-end group.

Excluded from the default sweep in `pyproject.toml`, for the same reason `tests/tui` is: these drive a real binary and a real socket, they take seconds rather than milliseconds each, and they depend on something the repository does not install. Run them with `uv run pytest tests/e2e`.

The isolation lives here rather than at the root because only this group needs it — and a root-level `CLAUDE_CONFIG_DIR` would silently take that choice away from every other group.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from _harness import claude_available


@pytest.fixture(scope="session", autouse=True)
def require_claude() -> None:
    if not claude_available():
        pytest.skip("the `claude` binary this group drives is not installed", allow_module_level=True)


@pytest.fixture
def config_dir(tmp_path: Path) -> Generator[Path]:
    """A throwaway `CLAUDE_CONFIG_DIR`, so the run touches nothing the developer owns."""
    directory = tmp_path / "claude-config"
    directory.mkdir(parents=True, exist_ok=True)
    yield directory
