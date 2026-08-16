"""Inbound HTTP surface.

MAIN.md: this module receives requests, does basic input format parsing, and hands them to
app.pipeline.

`app_factory` is the FastAPI application as it stands today, moved here unchanged when this
became a package. `inbound` is the parsing that feeds the new pipeline.
"""

from app.server.app_factory import create_app
from app.server.composition import Chain, build_chain, refresh_catalogs
from app.server.handler import HandledRequest, handle
from app.server.inbound import (
    ROUTES,
    InboundRequestError,
    InboundRoute,
    build_context,
    route_for_path,
)
from app.server.pipeline_app import create_pipeline_app

__all__ = [
    "ROUTES",
    "Chain",
    "HandledRequest",
    "InboundRequestError",
    "InboundRoute",
    "build_chain",
    "build_context",
    "create_app",
    "create_pipeline_app",
    "handle",
    "refresh_catalogs",
    "route_for_path",
]
