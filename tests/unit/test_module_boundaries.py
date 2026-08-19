"""What each entry point actually drags in.

The two chains looked identical to the import graph until 2026-08-19: importing anything under
`app.server` ran its package init, which imported `create_app`, which imported the existing chain.
Measured then, all 175 reachable modules were reachable from both entry points — the graph could
not tell the architecture anything, because the package init had merged it.

This is a structural assertion, not a style one. `D-ARCH = B` puts the wire shapes at the codec
boundary and nowhere inside; that is only checkable if importing the kernel does not also import
everything that predates it.
"""

import importlib
import sys


def reachable_from(module: str) -> set[str]:
    """The `app.*` modules imported as a side effect of importing one module."""
    for name in [name for name in sys.modules if name.startswith("app")]:
        del sys.modules[name]
    importlib.import_module(module)
    return {name for name in sys.modules if name.startswith("app.")}


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
