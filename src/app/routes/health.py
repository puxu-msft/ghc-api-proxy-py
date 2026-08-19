from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.deps import RuntimeDependency

router = APIRouter(tags=["health"])


@router.get("/health/liveness")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health")
@router.get("/health/readiness")
async def readiness(runtime: RuntimeDependency) -> JSONResponse:
    checks = runtime.readiness_checks()
    body: dict[str, object] = {
        "status": "healthy" if runtime.is_ready else "unhealthy",
        "checks": checks,
    }
    return JSONResponse(
        body,
        status_code=200 if runtime.is_ready else 503,
    )
