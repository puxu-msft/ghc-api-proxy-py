"""Inbound HTTP surface.

MAIN.md: this module receives requests, does basic input format parsing, and hands them to
app.pipeline.

`app_factory` is the FastAPI application as it stands today, moved here unchanged when this
became a package. `inbound` is the parsing that feeds the new pipeline.
"""

from app.server.app_factory import create_app
from app.server.inbound import (
    ROUTES,
    InboundRequestError,
    InboundRoute,
    build_context,
    route_for_path,
)

__all__ = [
    "ROUTES",
    "InboundRequestError",
    "InboundRoute",
    "build_context",
    "create_app",
    "route_for_path",
]
