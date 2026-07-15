from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health/liveness")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


def _is_ready(value: object) -> bool:
    return bool(value)


@router.get("/health")
@router.get("/health/readiness")
async def readiness(request: Request) -> JSONResponse:
    checks = {
        "github_token": _is_ready(getattr(request.app.state, "github_token", None)),
        "copilot_token": _is_ready(getattr(request.app.state, "copilot_token", None)),
        "models": _is_ready(getattr(request.app.state, "models", None)),
    }
    healthy = all(checks.values())
    return JSONResponse(
        {
            "status": "healthy" if healthy else "unhealthy",
            "checks": checks,
        },
        status_code=200 if healthy else 503,
    )