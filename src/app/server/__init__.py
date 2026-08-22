"""Inbound HTTP surface.

`docs/.human-controlled/request-pipeline.md` has requests enter this package and be handed to `app.pipeline`. It calls the entry `app.server.routes`, and since 2026-08-22 that is what it is called here too — the endpoints are in `routes/`, the codec that turns a body into a `RequestContext` is `inbound.py`, and the app that mounts them is `pipeline_app.py`.

Deliberately empty of imports, and the reason has changed. It used to be that re-exporting `create_app` here dragged the whole retired chain in behind anything under `app.server`; that chain now lives in `src/.archived/` and cannot be imported at all. What the emptiness buys today is narrower and still worth having: `app.server.inbound` imports the route table, so a package init that reached for the dispatcher would close a cycle through this package the moment it did.

Import the module you mean: `app.server.pipeline_app`, `app.server.routes.router`, `app.server.composition`, `app.server.http_errors`, `app.server.inbound`.
"""
