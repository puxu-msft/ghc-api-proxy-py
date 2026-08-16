from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from app.lifecycle.rolling.generation.control_client import (
    GenerationControlClient,
    GenerationControlClientError,
)


async def _server(path: Path, response: dict[str, object] | None) -> asyncio.Server:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        if response is None:
            await reader.read()
        else:
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

    return await asyncio.start_unix_server(handle, path=path)


def _valid_response() -> dict[str, object]:
    return {
        "ok": True,
        "version": 1,
        "generation": "g0000000000000001",
        "release": "release-a",
        "pid": 42,
        "phase": "ready_accepting",
        "ready": True,
        "accepting": True,
        "active_operations": 0,
        "listener_families": ["http-v4", "http-v6"],
        "last_error": None,
        "revision": 1,
    }


@pytest.mark.asyncio
async def test_status_deadline_covers_server_that_accepts_but_never_replies(
    tmp_path: Path,
) -> None:
    path = tmp_path / "control.sock"
    server = await _server(path, None)
    try:
        with pytest.raises(TimeoutError):
            await GenerationControlClient().status(path, timeout=0.05)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        {"version": 999},
        {"version": True},
        {"pid": "42"},
        {"pid": -1},
        {"ready": 1},
        {"phase": "invented"},
        {"phase": "starting", "ready": True, "accepting": True},
        {"generation": ["g0000000000000001"]},
        {"release": ["release-a"]},
        {"listener_families": "http-v4"},
        {"listener_families": {"http-v4": False, "http-v6": False}},
        {"active_operations": -1},
        {"revision": -1},
        {"last_error": {"message": "bad"}},
    ],
)
async def test_status_rejects_invalid_protocol_and_field_types(
    tmp_path: Path,
    mutation: dict[str, object],
) -> None:
    response = _valid_response()
    response.update(mutation)
    path = tmp_path / "control.sock"
    server = await _server(path, response)
    try:
        with pytest.raises(GenerationControlClientError):
            await GenerationControlClient().status(path)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_status_wraps_malformed_json_as_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "control.sock"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        writer.write(b"not-json\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_unix_server(handle, path=path)
    try:
        with pytest.raises(GenerationControlClientError, match="framing"):
            await GenerationControlClient().status(path)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_flush_tokenization_receipt_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "control.sock"
    object_path = tmp_path / "snapshots" / "objects" / "sha256"
    object_path.mkdir(parents=True)
    data = b'{"payload":{}}'
    digest = hashlib.sha256(data).hexdigest()
    snapshot = object_path / f"{digest}.json"
    snapshot.write_bytes(data)
    response: dict[str, object] = {
        "ok": True,
        "version": 1,
        "generation": "g0000000000000001",
        "release": "release-a",
        "tokenization": {
            "changed": True,
            "revision": 4,
            "sha256": digest,
            "path": str(snapshot),
            "canonical_updated": False,
            "reason": "local_snapshot",
        },
    }
    server = await _server(path, response)
    try:
        receipt = await GenerationControlClient().flush_tokenization(
            path,
            expected_generation="g0000000000000001",
            expected_release="release-a",
            snapshot_root=tmp_path / "snapshots",
        )
    finally:
        server.close()
        await server.wait_closed()
    assert receipt.revision == 4
    assert receipt.sha256 == digest
