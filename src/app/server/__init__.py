"""Inbound HTTP surface.

MAIN.md: this module receives requests, does basic input format parsing, and hands them to
app.pipeline.

Deliberately empty of imports. Re-exporting `create_app` here meant that importing *anything*
under `app.server` — including `pipeline_app`, which is the new chain — eagerly pulled in the
whole existing chain behind it. Measured before removing it: every one of the 175 reachable
modules was reachable from both entry points, so the dependency graph said the two chains were
one. They are not; the package init was.

Import the module you mean: `app.server.pipeline_app`, `app.server.app_factory`,
`app.server.composition`, `app.server.handler`, `app.server.inbound`.
"""
