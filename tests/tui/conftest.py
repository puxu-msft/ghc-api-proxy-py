"""Entry for the terminal UI tests, kept apart from the rest of the suite.

Run them when `src/app/observability/tui.py` changes, or by hand:

    uv run pytest tests/tui

They are excluded from the default sweep by `--ignore=tests/tui` in `pyproject.toml`.
That flag only drops the directory from discovery, so naming the path above still collects it.

Why a separate entry rather than a marker or a shared fixture.
A TUI asserts on rendered terminal output.
It is therefore the one group that legitimately wants a real terminal, a fixed width and colour.
Putting that setup anywhere shared would impose a terminal environment on every other test.
It would equally stop a TUI test from choosing its own.
Terminal setup belongs here.
"""
