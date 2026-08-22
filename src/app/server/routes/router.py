"""Every inbound path this app answers on, assembled into one router.

Kept out of the package `__init__` on purpose: `app.server.inbound` imports the route table, and an `__init__` that reached back for the dispatcher would close a cycle through the package the moment it did.
"""

from fastapi import APIRouter

from app.server.routes.inference import serve
from app.server.routes.ops import router as ops_router
from app.server.routes.table import OPENAI_PREFIXES, ROUTES


def build_router() -> APIRouter:
    """Register every inbound path: the model endpoints, their OpenAI-compatible prefixes, and the non-inference surface.

    One router rather than two handed separately to the factory. What this app answers on is a fact about the routes package, and splitting it across a caller meant the answer could only be read by looking in two places — which is how the ops endpoints came to be mounted by the factory while the inference ones were assembled here.
    """
    router = APIRouter()
    seen: set[str] = set()
    for route in ROUTES:
        paths = [route.path]
        if route.wire_format.value.startswith("openai-"):
            paths = [f"{prefix}{route.path}" for prefix in OPENAI_PREFIXES]
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            router.add_api_route(path, serve, methods=["POST"])
    # Health, the model list and metrics. A supervisor that cannot ask whether the process is ready has to guess, and the inference routes alone give it nothing to ask.
    router.include_router(ops_router)
    return router
