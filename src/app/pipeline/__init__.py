"""The request pipeline.

Deliberately empty. This package once re-exported `execute_anthropic_pipeline`, which meant importing *any* module under `app.pipeline` — including leaves like `exceptions` — eagerly pulled in the existing executor, and through it `app.upstream` and `app.model_provider.ghc_client`. Nothing imported the re-export; every caller names `app.pipeline.executor` directly, and one of them (`app.anthropic
.client`) had already worked around the cycle with a function-local import.

Keeping it cost a real import cycle the moment `app.model_provider.ghc_client` needed to speak the pipeline's error vocabulary.
"""
