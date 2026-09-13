"""Read-only History index and transport export routes."""

import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from app.history import HistoryMutation
from app.server.app_state import chain_of

router = APIRouter()


def _history_unavailable() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "type": "proxy_internal_error",
                "message": "history store is not available",
            }
        },
        status_code=503,
    )


@router.get("/history/api/entries")
async def list_history_entries(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    include_archived: bool = False,
) -> JSONResponse:
    writer = getattr(chain_of(request), "history_writer", None)
    if writer is None:
        return _history_unavailable()
    try:
        entries = await writer.list_entries(
            limit=limit,
            include_archived=include_archived,
        )
    except RuntimeError:
        return _history_unavailable()
    return JSONResponse({"data": [entry.as_dict() for entry in entries]})


@router.get("/history/api/entries/{entry_id}")
async def get_history_entry(
    entry_id: str,
    request: Request,
    include: str = Query(default=""),
) -> Response:
    if include == "transport":
        return await export_history_transport(entry_id, request)
    writer = getattr(chain_of(request), "history_writer", None)
    if writer is None:
        return _history_unavailable()
    try:
        entry = await writer.get_entry(entry_id)
    except RuntimeError:
        return _history_unavailable()
    if entry is None:
        return JSONResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": f"history entry {entry_id!r} does not exist",
                }
            },
            status_code=404,
        )
    result = entry.as_dict()
    if include:
        if include != "semantic":
            return JSONResponse(
                {
                    "error": {
                        "type": "invalid_request_error",
                        "message": "include must be 'semantic'",
                    }
                },
                status_code=400,
            )
        try:
            semantic = await writer.semantic_payload_for(entry_id)
        except RuntimeError:
            return _history_unavailable()
        if semantic is None:
            return JSONResponse(
                {
                    "error": {
                        "type": "source_unavailable",
                        "message": "semantic History payload is unavailable",
                    }
                },
                status_code=409,
            )
        result["semantic_request"] = semantic.get("semantic_request")
        result["semantic_response"] = semantic.get("semantic_response")
    return JSONResponse(result)


@router.get("/history/api/entries/{entry_id}/transport")
async def export_history_transport(entry_id: str, request: Request) -> Response:
    chain = chain_of(request)
    writer = getattr(chain, "history_writer", None)
    raw_capture = getattr(chain, "raw_capture", None)
    if writer is None or raw_capture is None:
        return _history_unavailable()
    try:
        entry = await writer.get_entry(entry_id)
        if entry is None:
            return JSONResponse(
                {
                    "error": {
                        "type": "source_unavailable",
                        "message": "history entry is not available for transport export",
                    }
                },
                status_code=409,
            )
        if entry.capture_ref is None:
            return JSONResponse(
                {
                    "error": {
                        "type": "source_unavailable",
                        "message": "history entry has no capture attachment",
                    }
                },
                status_code=409,
            )
        payload = await asyncio.to_thread(
            raw_capture.export_request,
            entry.capture_ref,
            entry_id,
        )
    except (OSError, ValueError):
        return JSONResponse(
            {
                "error": {
                    "type": "source_unavailable",
                    "message": "capture transport evidence is unavailable",
                }
            },
            status_code=409,
        )
    if not payload:
        return JSONResponse(
            {
                "error": {
                    "type": "source_unavailable",
                    "message": "capture transport evidence is empty",
                }
            },
            status_code=409,
        )
    return Response(
        content=payload,
        media_type="application/cbor-seq+zstd",
        headers={"X-Capture-Contains-Credentials": "true"},
    )


async def _mutate_history_entry(
    request: Request,
    entry_id: str,
    operation: str,
) -> JSONResponse:
    writer = getattr(chain_of(request), "history_writer", None)
    if writer is None:
        return _history_unavailable()
    try:
        mutation = await getattr(writer, operation)(entry_id)
    except RuntimeError:
        return _history_unavailable()
    if mutation is HistoryMutation.NOT_FOUND:
        return JSONResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": f"history entry {entry_id!r} does not exist",
                }
            },
            status_code=404,
        )
    if mutation is HistoryMutation.PINNED:
        return JSONResponse(
            {
                "error": {
                    "type": "conflict_error",
                    "message": "history entry is pinned",
                    "code": "entry_pinned",
                }
            },
            status_code=409,
        )
    return JSONResponse(
        {
            "id": entry_id,
            "operation": operation.removeprefix("_").removesuffix("_entry"),
            "state": (
                "already_applied"
                if mutation is HistoryMutation.ALREADY_APPLIED
                else "updated"
            ),
        }
    )


@router.post("/history/api/entries/{entry_id}/archive")
async def archive_history_entry(entry_id: str, request: Request) -> JSONResponse:
    return await _mutate_history_entry(request, entry_id, "archive_entry")


@router.post("/history/api/entries/{entry_id}/pin")
async def pin_history_entry(entry_id: str, request: Request) -> JSONResponse:
    return await _mutate_history_entry(request, entry_id, "pin_entry")


@router.post("/history/api/entries/{entry_id}/unpin")
async def unpin_history_entry(entry_id: str, request: Request) -> JSONResponse:
    return await _mutate_history_entry(request, entry_id, "unpin_entry")


__all__ = ["router"]
