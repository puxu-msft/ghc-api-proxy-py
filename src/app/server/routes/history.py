"""Read-only History index and transport export routes."""

import base64
from hmac import compare_digest

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import SecretStr

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


def _history_transport_access_denied() -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "type": "access_denied",
                "message": "history transport export access is denied",
            }
        },
        status_code=403,
    )


def _has_history_transport_access(request: Request) -> bool:
    """Check the separately configured management secret without trusting listener locality."""
    chain = chain_of(request)
    server = getattr(getattr(chain, "config", None), "server", None)
    configured_token = getattr(server, "history_export_token", None)
    supplied_token = request.headers.get("X-History-Export-Token")
    return (
        isinstance(configured_token, SecretStr)
        and supplied_token is not None
        and compare_digest(configured_token.get_secret_value(), supplied_token)
    )


@router.get("/history/api/entries")
async def list_history_entries(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    include_archived: bool = False,
    cursor: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
    outcome: str | None = None,
    delivery: str | None = None,
    capture_status: str | None = None,
) -> JSONResponse:
    writer = getattr(chain_of(request), "history_writer", None)
    if writer is None:
        return _history_unavailable()
    try:
        page = await writer.list_entries_page(
            limit=limit,
            include_archived=include_archived,
            cursor=cursor,
            session_id=session_id,
            agent_id=agent_id,
            outcome=outcome,
            delivery=delivery,
            capture_status=capture_status,
        )
    except RuntimeError:
        return _history_unavailable()
    except ValueError:
        return JSONResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": "history cursor is invalid",
                }
            },
            status_code=400,
        )
    return JSONResponse(
        {
            "data": [entry.as_dict() for entry in page.entries],
            "next_cursor": page.next_cursor,
        }
    )


@router.get("/history/api/entries/{entry_id}")
async def get_history_entry(
    entry_id: str,
    request: Request,
    include: str = Query(default=""),
) -> Response:
    export = request.query_params.get("export", "")
    if export:
        if include:
            return JSONResponse(
                {
                    "error": {
                        "type": "invalid_request_error",
                        "message": "include and export cannot be used together",
                    }
                },
                status_code=400,
            )
        if export == "transport":
            return await export_history_transport(entry_id, request)
        if export == "semantic":
            return await export_history_semantic(entry_id, request)
        if export == "full":
            return await export_history_full(entry_id, request)
        return JSONResponse(
            {
                "error": {
                    "type": "invalid_request_error",
                    "message": "export must be 'semantic', 'transport', or 'full'",
                }
            },
            status_code=400,
        )
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


async def export_history_semantic(entry_id: str, request: Request) -> Response:
    writer = getattr(chain_of(request), "history_writer", None)
    if writer is None:
        return _history_unavailable()
    try:
        entry = await writer.get_entry(entry_id)
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
    return JSONResponse(
        {
            "id": entry_id,
            "export": "semantic",
            "contains_credentials": False,
            "data": semantic,
        }
    )


async def export_history_full(entry_id: str, request: Request) -> Response:
    if not _has_history_transport_access(request):
        return _history_transport_access_denied()
    writer = getattr(chain_of(request), "history_writer", None)
    if writer is None:
        return _history_unavailable()
    try:
        entry = await writer.get_entry(entry_id)
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
        semantic = await writer.semantic_payload_for(entry_id)
        transport = await writer.transport_for(entry_id)
    except RuntimeError:
        return _history_unavailable()
    except (OSError, ValueError):
        return JSONResponse(
            {
                "error": {
                    "type": "source_unavailable",
                    "message": "History full export is unavailable",
                }
            },
            status_code=409,
        )
    if semantic is None or transport is None:
        return JSONResponse(
            {
                "error": {
                    "type": "source_unavailable",
                    "message": "History full export requires semantic and transport evidence",
                }
            },
            status_code=409,
        )
    return JSONResponse(
        {
            "id": entry_id,
            "export": "full",
            "contains_credentials": True,
            "entry": entry.as_dict(),
            "semantic": semantic,
            "transport": {
                "media_type": "application/cbor-seq+zstd",
                "encoding": "base64",
                "data": base64.b64encode(transport).decode("ascii"),
            },
        }
    )


@router.get("/history/api/entries/{entry_id}/transport")
async def export_history_transport(entry_id: str, request: Request) -> Response:
    if not _has_history_transport_access(request):
        return _history_transport_access_denied()
    writer = getattr(chain_of(request), "history_writer", None)
    if writer is None:
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
        if entry.transport_reference is None:
            return JSONResponse(
                {
                    "error": {
                        "type": "source_unavailable",
                        "message": "history entry has no archived transport envelope",
                    }
                },
                status_code=409,
            )
        payload = await writer.transport_for(entry_id)
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
    if mutation is HistoryMutation.ARCHIVE_FAILED:
        return JSONResponse(
            {
                "error": {
                    "type": "source_unavailable",
                    "message": "history archive could not be confirmed",
                    "code": "archive_failed",
                }
            },
            status_code=503,
        )
    response = JSONResponse(
        {
            "id": entry_id,
            "operation": operation.removeprefix("_").removesuffix("_entry"),
            "state": (
                "already_applied"
                if mutation is HistoryMutation.ALREADY_APPLIED
                else "archiving"
                if mutation is HistoryMutation.ARCHIVING
                else "updated"
            ),
        },
        status_code=202 if mutation is HistoryMutation.ARCHIVING else 200,
    )
    return response


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
