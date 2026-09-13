from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from fastapi import FastAPI

from app.history import (
    CaptureCapabilities,
    HistoryArchiveStore,
    HistoryDelivery,
    HistoryDurability,
    HistoryEntry,
    HistoryOutcome,
    HistorySubmission,
    HistoryWriter,
)
from app.observability.raw_capture import RawCaptureStore, iter_raw_capture_records
from app.pipeline.response_observation import FrozenJsonObject, freeze_json
from app.server.app_state import CHAIN_STATE_KEY
from app.server.routes.history import router


def _entry() -> HistoryEntry:
    usage = freeze_json({})
    empty = freeze_json([])
    assert isinstance(usage, FrozenJsonObject)
    return HistoryEntry(
        request_id="request-route-1",
        started_at="2026-09-13T00:00:00.000Z",
        finished_at="2026-09-13T00:00:01.000Z",
        outcome=HistoryOutcome.COMPLETED,
        delivery=HistoryDelivery.COMPLETE,
        status_code=200,
        inbound_format="anthropic-messages",
        requested_model="model",
        resolved_model="model",
        provider_name="provider",
        attempts=1,
        retry_count=0,
        replaced_failures=(),
        usage=usage,
        losses=empty,
        facts=empty,
        capture=CaptureCapabilities(),
        semantic_request=freeze_json(
            {"messages": [{"role": "user", "content": "hi"}]}
        ),
        semantic_response=freeze_json(
            {"content": [{"type": "text", "text": "hello"}]}
        ),
    )


@pytest.mark.asyncio
async def test_history_routes_read_durable_index_entry(tmp_path: Path) -> None:
    writer = HistoryWriter(
        database_path=tmp_path / "history.sqlite3",
        archive=HistoryArchiveStore(tmp_path / "archive"),
    )
    await writer.start()
    entry = _entry()
    try:
        assert (
            await writer.submit(
                entry,
                session_id="session-route",
                agent_id=None,
            )
            is HistorySubmission.ACCEPTED
        )
        await writer.wait_idle()
        receipt = writer.receipt_for(entry.request_id)
        assert receipt is not None
        assert receipt.state is HistoryDurability.DURABLE

        app = FastAPI()
        app.include_router(router)
        setattr(
            app.state,
            CHAIN_STATE_KEY,
            SimpleNamespace(history_writer=writer),
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            listed = await client.get("/history/api/entries")
            detail = await client.get("/history/api/entries/request-route-1")
            semantic = await client.get(
                "/history/api/entries/request-route-1?include=semantic"
            )

        assert listed.status_code == 200
        assert listed.json()["data"][0]["id"] == "request-route-1"
        assert detail.status_code == 200
        assert detail.json()["outcome"] == "completed"
        assert semantic.status_code == 200
        assert semantic.json()["semantic_request"]["messages"][0]["content"] == "hi"
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_history_routes_report_unavailable_store() -> None:
    app = FastAPI()
    app.include_router(router)
    setattr(app.state, CHAIN_STATE_KEY, SimpleNamespace(history_writer=None))

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/history/api/entries")

    assert response.status_code == 503
    assert response.json()["error"]["type"] == "proxy_internal_error"


@pytest.mark.asyncio
async def test_history_archive_is_one_way_and_pinned_entries_block_it(
    tmp_path: Path,
) -> None:
    writer = HistoryWriter(
        database_path=tmp_path / "history.sqlite3",
        archive=HistoryArchiveStore(tmp_path / "archive"),
    )
    await writer.start()
    entry = _entry()
    try:
        await writer.submit(entry, session_id="session-route", agent_id=None)
        await writer.wait_idle()

        app = FastAPI()
        app.include_router(router)
        setattr(app.state, CHAIN_STATE_KEY, SimpleNamespace(history_writer=writer))
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            pinned = await client.post(
                "/history/api/entries/request-route-1/pin"
            )
            blocked = await client.post(
                "/history/api/entries/request-route-1/archive"
            )
            unpinned = await client.post(
                "/history/api/entries/request-route-1/unpin"
            )
            archived = await client.post(
                "/history/api/entries/request-route-1/archive"
            )
            listed = await client.get("/history/api/entries")
            detail = await client.get("/history/api/entries/request-route-1")

        assert pinned.status_code == 200
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "entry_pinned"
        assert unpinned.status_code == 200
        assert archived.status_code == 200
        assert listed.json()["data"] == []
        assert detail.status_code == 404
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_history_transport_export_returns_filtered_binary_capture(
    tmp_path: Path,
) -> None:
    raw_capture = RawCaptureStore(tmp_path / "captures")
    capture = raw_capture.start(
        session_id="session-transport",
        agent_id=None,
        request_id="request-transport-1",
        method="POST",
        path="/v1/messages",
    )
    capture.request_body(b'{"model":"model"}')
    capture.request_body_end(complete=True)
    capture.upstream_response_body(b'{"ok":true}')
    capture.upstream_response_end(complete=True, attempt=0)
    capture.client_response_body(b'{"ok":true}', more_body=False)
    capture.finish(status_code=200, complete=True)
    raw_capture.flush()
    capture_ref = raw_capture.reference_for("session-transport", None)

    writer = HistoryWriter(
        database_path=tmp_path / "history.sqlite3",
        archive=HistoryArchiveStore(tmp_path / "archive"),
    )
    await writer.start()
    entry = replace(
        _entry(),
        request_id="request-transport-1",
        capture_ref=capture_ref,
    )
    try:
        await writer.submit(entry, session_id="session-transport", agent_id=None)
        await writer.wait_idle()
        app = FastAPI()
        app.include_router(router)
        setattr(
            app.state,
            CHAIN_STATE_KEY,
            SimpleNamespace(history_writer=writer, raw_capture=raw_capture),
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/history/api/entries/request-transport-1/transport"
            )
            included = await client.get(
                "/history/api/entries/request-transport-1?include=transport"
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/cbor-seq+zstd"
        )
        export_path = tmp_path / "export.cborseq.zst"
        export_path.write_bytes(response.content)
        records = list(iter_raw_capture_records(export_path))
        assert {record["request_id"] for record in records} == {
            "request-transport-1"
        }

        assert included.status_code == 200
        assert included.content == response.content
    finally:
        await writer.close()
        raw_capture.close()
