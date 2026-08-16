"""Test-wide environment that must be set before Typer is imported.

Typer reads both of these once, at import time.
A `CliRunner(env=...)` applied per invocation therefore comes too late.

Without them the help text renders as a coloured, 80-column panel.
`--port` then arrives as two separately styled runs with an ANSI escape between the dashes.
Long option names are truncated with an ellipsis.
Tests asserting that an option is offered would fail on the rendering rather than on the CLI.
"""

import os

os.environ.setdefault("_TYPER_FORCE_DISABLE_TERMINAL", "1")
os.environ.setdefault("TERMINAL_WIDTH", "200")
