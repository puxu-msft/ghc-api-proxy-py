from fastapi import APIRouter, Response
from prometheus_client import REGISTRY, generate_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4",
    )