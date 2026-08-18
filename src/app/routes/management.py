from typing import Any

from fastapi import APIRouter, Query, Response

from app.deps import ModelCatalogDependency, RuntimeDependency, SettingsDependency
from app.transform.model_resolver import normalize_for_matching

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


@router.get("/api/tokenization/calibration")
async def tokenization_calibration(
    runtime: RuntimeDependency,
    protocol: str | None = Query(default=None),
    model: str | None = Query(default=None),
) -> dict[str, object]:
    state = runtime.tokenization_state
    snapshot = state.calibration.snapshot() if state is not None else {}
    normalized_model = normalize_for_matching(model) if model else None
    filtered = {
        key: value
        for key, value in snapshot.items()
        if (protocol is None or value["protocol"] == protocol.lower())
        and (normalized_model is None or value["model"] == normalized_model)
    }
    return {"version": 1, "calibration": filtered}


@router.get("/api/tokenization/limits")
async def tokenization_limits(
    runtime: RuntimeDependency,
    protocol: str | None = Query(default=None),
    model: str | None = Query(default=None),
) -> dict[str, object]:
    state = runtime.tokenization_state
    snapshot = state.prompt_limits.snapshot() if state is not None else {}
    normalized_model = normalize_for_matching(model) if model else None
    advertised: dict[str, int] = {}
    if runtime.upstream_services is not None:
        advertised = {
            normalize_for_matching(item.id): limit
            for item in runtime.upstream_services.model_catalog.models
            if (limit := item.capabilities.limits.max_prompt_tokens) is not None
        }
    result: dict[str, dict[str, object]] = {}
    if protocol is None or protocol.lower() == "anthropic":
        for advertised_model, advertised_limit in advertised.items():
            if normalized_model is not None and advertised_model != normalized_model:
                continue
            result[f"anthropic:{advertised_model}"] = {
                "protocol": "anthropic",
                "model": advertised_model,
                "advertised_limit": advertised_limit,
                "observed_limit": None,
                "observed_input_tokens": None,
                "source": None,
                "observed_at": None,
                "observation_count": 0,
                "difference": None,
            }
    for key, value in snapshot.items():
        if protocol is not None and value["protocol"] != protocol.lower():
            continue
        if normalized_model is not None and value["model"] != normalized_model:
            continue
        advertised_limit = advertised.get(str(value["model"]))
        observed_limit = int(value["observed_limit"])
        result[key] = {
            **value,
            "advertised_limit": advertised_limit,
            "difference": (
                observed_limit - advertised_limit
                if advertised_limit is not None
                else None
            ),
        }
    return {"version": 1, "limits": result}


@router.get("/favicon.ico", status_code=204)
@router.get("/.well-known/appspecific/com.chrome.devtools.json", status_code=204)
async def browser_probe() -> Response:
    return Response(status_code=204)
