"""The inbound HTTP endpoints.

`docs/.human-controlled/module-org.md` ratified `app.server.routes` and the code had never had it — the endpoints lived beside the factory that mounted them, and the name was taken by an unratified top-level `app/routes/` belonging to the chain that no entry point reaches. Ruled 2026-08-22 to use the ratified path.

Import-free by design, for the reason `router.py` states.
"""
