"""What each entry point actually drags in.

The two chains looked identical to the import graph until 2026-08-19: importing anything under
`app.server` ran its package init, which imported `create_app`, which imported the existing chain.
Measured then, all 175 reachable modules were reachable from both entry points — the graph could
not tell the architecture anything, because the package init had merged it.

This is a structural assertion, not a style one. `D-ARCH = B` puts the wire shapes at the codec
boundary and nowhere inside; that is only checkable if importing the kernel does not also import
everything that predates it.

Each measurement runs in its own interpreter. It used to unload `app*` from this one and import again, which answered the question but left every later test in the process holding classes from a superseded import: `assert x is SomeEnum.MEMBER` then compares two objects that print the same and are not the same. Two rate-limiter tests failed that way whenever the run happened to order them after this file. A subprocess also measures the thing the test is named for — what a *fresh* interpreter drags in — rather than what is left after a partial unload inside a process that has already imported a thousand other things.
"""

import json
import subprocess
import sys

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


def test_the_new_chain_does_not_drag_in_the_existing_one() -> None:
    """The single fact that makes the reorganisation checkable rather than a matter of belief."""
    new_chain = reachable_from("app.server.pipeline_app")

    assert "app.server.app_factory" not in new_chain
    assert "app.pipeline.executor" not in new_chain
    assert not [name for name in new_chain if name.startswith("app.routes")]


def test_the_typed_kernel_is_a_leaf() -> None:
    """The content model is what every codec meets at, so it must not import any of them.

    A kernel that reached back into a protocol would make "wire shapes live at the codec boundary"
    unenforceable: the boundary would run through the middle of the kernel.
    """
    kernel = reachable_from("app.pipeline.translation_driver.content")

    assert not [
        name
        for name in kernel
        if name.startswith(("app.anthropic", "app.openai", "app.upstream", "app.routes"))
    ]


def test_pipeline_exceptions_stay_importable_without_the_pipeline() -> None:
    """`app.ghc_client` speaks this vocabulary, and the cycle it closed was a real outage.

    Normalising SDK errors needed the pipeline's exception names; importing them pulled in the
    executor, then `app.upstream`, then `app.ghc_client` itself, and the process would not start.
    """
    errors = reachable_from("app.pipeline.exceptions")

    assert not [name for name in errors if name.startswith(("app.upstream", "app.ghc_client"))]
