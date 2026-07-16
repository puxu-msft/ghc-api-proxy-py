from typing import Any

from fastapi import APIRouter, Response

from app.deps import ModelCatalogDependency, RuntimeDependency, SettingsDependency

router = APIRouter(tags=["management"])


@router.get("/api/status")
async def status(runtime: RuntimeDependency) -> dict[str, Any]:
    return {
        "ready": runtime.is_ready,
        "checks": runtime.readiness_checks(),
    }


@router.get("/api/config")
async def config(settings: SettingsDependency) -> dict[str, Any]:
    data = settings.model_dump(mode="json")
    if data["auth"]["github_token"]:
        data["auth"]["github_token"] = "***"
    if data["upstream"]["api_key"]:
        data["upstream"]["api_key"] = "***"
    return data


@router.post("/api/event_logging/batch", status_code=204)
async def event_logging_batch() -> Response:
    return Response(status_code=204)


@router.get("/api/tokens")
async def tokens(runtime: RuntimeDependency) -> dict[str, bool]:
    return {
        "github_token": runtime.github_token_ready,
        "copilot_token": runtime.copilot_token_ready,
    }


@router.get("/api/models")
async def models(catalog: ModelCatalogDependency) -> dict[str, object]:
    return {
        "object": "list",
        "data": [model.model_dump(mode="json") for model in catalog.models],
        "disabled": sorted(set(model.id for model in catalog.models) - set(catalog.available_ids)),
    }


@router.get("/api/logs")
async def logs() -> dict[str, list[object]]:
    return {"data": []}


@router.get("/api/negotiation")
async def negotiation() -> dict[str, object]:
    return {"version": 2, "categories": {}}


@router.get("/favicon.ico", status_code=204)
@router.get("/.well-known/appspecific/com.chrome.devtools.json", status_code=204)
async def browser_probe() -> Response:
    return Response(status_code=204)