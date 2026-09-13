"""Read-only History index routes."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

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
async def get_history_entry(entry_id: str, request: Request) -> JSONResponse:
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
    return JSONResponse(entry.as_dict())


__all__ = ["router"]
