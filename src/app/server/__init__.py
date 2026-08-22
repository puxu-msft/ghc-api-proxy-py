"""Inbound HTTP surface.

`docs/.human-controlled/request-pipeline.md` has requests enter this package and be handed to `app.pipeline`. It calls the entry `app.server.routes`; no such module exists here — the real list is below — so that spelling is the document's, not this package's. The document also no longer spells out the basic input format parsing done on the way; `inbound.py` states and owns that choice.

Deliberately empty of imports. Re-exporting `create_app` here meant that importing *anything*
under `app.server` — including `pipeline_app`, which is the new chain — eagerly pulled in the
whole existing chain behind it. Measured before removing it: every one of the 175 reachable
modules was reachable from both entry points, so the dependency graph said the two chains were
one. They are not; the package init was.

Import the module you mean: `app.server.pipeline_app`, `app.server.app_factory`,
`app.server.composition`, `app.server.handler`, `app.server.inbound`.
"""
