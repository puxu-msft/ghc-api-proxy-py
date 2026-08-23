"""What each entry point actually drags in.

The two chains looked identical to the import graph until 2026-08-19: importing anything under `app.server` ran its package init, which imported `create_app`, which imported the existing chain.
Measured then, all 175 reachable modules were reachable from both entry points — the graph could not tell the architecture anything, because the package init had merged it.

This is a structural assertion, not a style one. `D-ARCH = B` puts the wire shapes at the codec boundary and nowhere inside; that is only checkable if importing the kernel does not also import everything that predates it.

Each measurement runs in its own interpreter. It used to unload `app*` from this one and import again, which answered the question but left every later test in the process holding classes from a superseded import: `assert x is SomeEnum.MEMBER` then compares two objects that print the same and are not the same. Two rate-limiter tests failed that way whenever the run happened to order them after this file. A subprocess also measures the thing the test is named for — what a *fresh* interpreter drags in — rather than what is left after a partial unload inside a process that has already imported a thousand other things.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

# Printed on the last line so the reader tolerates anything a plugin or a package init writes to stdout on the way past.
_PROBE = (
    "import importlib, json, sys;"
    "importlib.import_module(sys.argv[1]);"
    "print(json.dumps(sorted(n for n in sys.modules if n.startswith('app.'))))"
)


def reachable_from(module: str) -> set[str]:
    """The `app.*` modules a fresh interpreter imports as a side effect of importing one module."""
    finished = subprocess.run(
        [sys.executable, "-c", _PROBE, module],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(json.loads(finished.stdout.strip().splitlines()[-1]))


_ARCHIVED = (
    "app.routes",
    "app.hooks",
    "app.openai",
    "app.history",
    "app.delivery",
    "app.context",
    "app.deps",
    "app.runtime",
    "app.shutdown",
    "app.server.app_factory",
    "app.pipeline.executor",
    # Archived 2026-08-23, and the submodules here are why this tuple holds names rather than top-level packages: `app.protocols`, `app.models` and `app.model_provider.ghc_client` are all live, and only these modules under them went. A name that resolves again means one came back.
    "app.protocols.gemini",
    "app.models.gemini",
    # The pre-header transport guard. Its only caller was `GhcApiClient.send_responses_headers`, whose only caller was `CopilotUpstream` — an adapter to a protocol that had already been archived, and one nothing in `src/` or `tests/` ever instantiated. What it knew (a bare `h2.exceptions.ProtocolError` reaches callers unwrapped) now lives on the live path in `app/model_provider/ghc_client/errors.py`, which is what made it safe to move rather than rewire.
    "app.model_provider.ghc_client.transport",
)

_RESOLVES = (
    "import importlib.util, json, sys;"
    "print(json.dumps([n for n in sys.argv[1:] if importlib.util.find_spec(n) is not None]))"
)


def test_the_archived_chain_is_not_importable_at_all() -> None:
    """What used to be "the new chain does not drag in the old one", now that there is only one.

    Until 2026-08-22 both chains lived under `src/app/` and this asserted that importing the live one did not pull the other in. The archived chain moved to `src/.archived/`, which is not on the path and whose leading dot keeps it out of the packaging and the type checker, so that weaker statement is now trivially true — and would stay true if someone copied a module back.

    The assertion is the stronger one instead: these names do not resolve. It fails the moment a module returns to `src/app/` under an archived name, **including as an empty PEP 420 namespace package** — which is exactly what an emptied directory left behind, and what kept `import app.routes` succeeding after every one of its files had gone.
    """
    finished = subprocess.run(
        [sys.executable, "-c", _RESOLVES, *_ARCHIVED],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(finished.stdout.strip().splitlines()[-1]) == []


def test_the_typed_kernel_is_a_leaf() -> None:
    """The content model is what every codec meets at, so it must not import any of them.

    A kernel that reached back into a protocol would make "wire shapes live at the codec boundary" unenforceable: the boundary would run through the middle of the kernel.

    `app.anthropic` and `app.upstream` are the two that still exist; `app.openai` and `app.routes` went to the archive on 2026-08-22 and the test above covers them.
    """
    kernel = reachable_from("app.pipeline.translation_driver.content")

    assert not [name for name in kernel if name.startswith(("app.anthropic", "app.upstream"))]


def test_pipeline_exceptions_stay_importable_without_the_pipeline() -> None:
    """`app.model_provider.ghc_client` speaks this vocabulary, and the cycle it closed was a real outage.

    Normalising SDK errors needed the pipeline's exception names; importing them pulled in the executor, then `app.upstream`, then `app.model_provider.ghc_client` itself, and the process would not start.
    """
    errors = reachable_from("app.pipeline.exceptions")

    assert not [name for name in errors if name.startswith(("app.upstream", "app.model_provider.ghc_client"))]


def test_no_live_module_drives_h2_itself() -> None:
    """`_CONNECTION_ERRORS` maps the whole `h2.exceptions` family, and that mapping rests on this.

    The hierarchy carries no attribution — a review raised ten of its members through h2's public API, all from caller actions. What makes the mapping sound is that nothing here makes those calls: every h2 interaction in this process happens inside httpcore, which converts what it raises itself, so a *bare* `H2Error` has escaped through the one gap in that conversion and came from parsing the peer's bytes.

    Imports of `h2.events` and `h2.exceptions` are types being named — the gloss in `app.pipeline.hand_over` and the tuple in `app.model_provider.ghc_client.errors`. `h2.connection`, `h2.config` and `h2.stream` are the modules you reach for to drive a connection, and reaching for one of them is what would quietly turn that tuple into a claim nobody checked.
    """
    driving = {"h2.connection", "h2.config", "h2.stream", "h2.frame_buffer", "h2.windows"}
    offenders: list[str] = []
    for path in sorted(Path("src/app").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [f"{path}: import {a.name}" for a in node.names if a.name in driving]
            elif isinstance(node, ast.ImportFrom) and node.module in driving:
                offenders.append(f"{path}: from {node.module} import ...")

    assert offenders == [], "\n".join(offenders)
