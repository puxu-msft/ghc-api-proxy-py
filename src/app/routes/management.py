from typing import Any

from fastapi import APIRouter, Response

from app.deps import RuntimeDependency, SettingsDependency

router = APIRouter(tags=["management"])


@router.get("/api/status")
async def status(runtime: RuntimeDependency) -> dict[str, Any]:
    return {
        "ready": runtime.is_ready,
        "checks": runtime.readiness_checks(),
    }


@router.get("/api/config")
async def config(settings: SettingsDependency) -> dict[str, Any]:
    return settings.model_dump(mode="json")


@router.post("/api/event_logging/batch", status_code=204)
async def event_logging_batch() -> Response:
    return Response(status_code=204)


@router.get("/favicon.ico", status_code=204)
@router.get("/.well-known/appspecific/com.chrome.devtools.json", status_code=204)
async def browser_probe() -> Response:
    return Response(status_code=204)