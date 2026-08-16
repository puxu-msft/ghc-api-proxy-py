from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path

import pytest

from app.lifecycle.rolling.generation.control import GenerationControlError, GenerationControlServer
from app.lifecycle.rolling.generation.phases import GenerationLifecycle


async def _request(path: Path, payload: object) -> dict[str, object]:
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        writer.write(json.dumps(payload).encode() + b"\n")
        await writer.drain()
        return json.loads(await reader.readline())
    finally:
        writer.close()
        await writer.wait_closed()


START_UNIX_SERVER = "app.lifecycle.rolling.generation.control.asyncio.start_unix_server"


@pytest.mark.asyncio
async def test_status_and_wait_use_one_versioned_lifecycle_snapshot(tmp_path: Path) -> None:
    lifecycle = GenerationLifecycle()
    path = tmp_path / "generation.sock"
    server = GenerationControlServer(
        path,
        lifecycle,
        generation_id="g0000000000000001",
        release_id="release-a",
    )
    await server.start()
    try:
        assert path.stat().st_mode & 0o777 == 0o600
        starting = await _request(path, {"version": 1, "command": "status"})
        assert starting["phase"] == "starting"
        assert starting["generation"] == "g0000000000000001"
        assert starting["ready"] is False
        assert starting["listener_families"] == ["http-v4", "http-v6"]
        assert starting["last_error"] is None
        revision = starting["revision"]
        assert isinstance(revision, int)

        waiter = asyncio.create_task(
            _request(
                path,
                {
                    "version": 1,
                    "command": "wait",
                    "after_revision": revision,
                    "timeout_ms": 1000,
                },
            )
        )
        await lifecycle.mark_ready()
        changed = await waiter
        assert changed["phase"] == "ready_accepting"
        assert changed["ready"] is True
        assert changed["accepting"] is True
        changed_revision = changed["revision"]
        assert isinstance(changed_revision, int)
        assert changed_revision > revision
    finally:
        await server.close()
    assert path.exists()
    path.unlink()


@pytest.mark.asyncio
async def test_protocol_rejects_bad_version_command_and_wait_timeout(tmp_path: Path) -> None:
    lifecycle = GenerationLifecycle()
    path = tmp_path / "generation.sock"
    server = GenerationControlServer(path, lifecycle, generation_id="g1", release_id="r1")
    await server.start()
    try:
        bad_version = await _request(path, {"version": 2, "command": "status"})
        assert bad_version["ok"] is False
        bad_command = await _request(path, {"version": 1, "command": "mutate"})
        assert bad_command["ok"] is False
        bool_revision = await _request(
            path,
            {"version": 1, "command": "wait", "after_revision": True},
        )
        assert bool_revision["ok"] is False
        timed_out = await _request(
            path,
            {"version": 1, "command": "wait", "after_revision": 0, "timeout_ms": 1},
        )
        assert timed_out == {"ok": False, "error": "wait_timeout"}
    finally:
        await server.close()
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_live_and_stale_paths_are_never_automatically_replaced(tmp_path: Path) -> None:
    lifecycle = GenerationLifecycle()
    path = tmp_path / "generation.sock"
    first = GenerationControlServer(path, lifecycle, generation_id="g1", release_id="r1")
    await first.start()
    second = GenerationControlServer(path, lifecycle, generation_id="g2", release_id="r2")
    try:
        with pytest.raises(GenerationControlError, match=r"lock is held|already active"):
            await second.start()
    finally:
        await first.close()

    with pytest.raises(GenerationControlError, match="requires explicit cleanup"):
        await second.start()
    path.unlink()

    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale_inode = path.lstat().st_ino
    stale.close()
    with pytest.raises(GenerationControlError, match="requires explicit cleanup"):
        await second.start()
    assert path.lstat().st_ino == stale_inode
    path.unlink()
    await second.start()
    await second.close()
    path.unlink()


@pytest.mark.asyncio
async def test_non_socket_control_path_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "generation.sock"
    path.write_text("keep", encoding="utf-8")
    server = GenerationControlServer(
        path,
        GenerationLifecycle(),
        generation_id="g1",
        release_id="r1",
    )
    with pytest.raises(GenerationControlError, match="non-socket"):
        await server.start()
    assert path.read_text(encoding="utf-8") == "keep"


@pytest.mark.asyncio
async def test_close_never_unlinks_control_path(tmp_path: Path) -> None:
    path = tmp_path / "generation.sock"
    server = GenerationControlServer(
        path,
        GenerationLifecycle(),
        generation_id="g1",
        release_id="r1",
    )
    await server.start()
    await server.close()

    assert path.exists()
    path.unlink()


@pytest.mark.asyncio
async def test_post_bind_failure_preserves_path_and_releases_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "generation.sock"
    async def fail_server(*_args: object, **_kwargs: object) -> asyncio.Server:
        raise OSError("server setup failed")

    monkeypatch.setattr(START_UNIX_SERVER, fail_server)
    failed = GenerationControlServer(
        path,
        GenerationLifecycle(),
        generation_id="g1",
        release_id="r1",
    )
    with pytest.raises(OSError, match="server setup failed"):
        await failed.start()
    assert path.exists()
    path.unlink()

    monkeypatch.undo()
    replacement = GenerationControlServer(
        path,
        GenerationLifecycle(),
        generation_id="g2",
        release_id="r2",
    )
    await replacement.start()
    await replacement.close()


@pytest.mark.asyncio
async def test_flush_tokenization_returns_generation_local_snapshot_receipt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "generation.sock"

    async def flush() -> dict[str, object]:
        return {
            "changed": True,
            "revision": 7,
            "sha256": "a" * 64,
            "path": str(tmp_path / "snapshot.json"),
            "canonical_updated": False,
            "reason": "local_snapshot",
        }

    server = GenerationControlServer(
        path,
        GenerationLifecycle(),
        generation_id="g0000000000000001",
        release_id="release-a",
        flush_tokenization=flush,
    )
    await server.start()
    try:
        response = await _request(
            path,
            {"version": 1, "command": "flush_tokenization"},
        )
    finally:
        await server.close()
        path.unlink()

    assert response["generation"] == "g0000000000000001"
    tokenization = response["tokenization"]
    assert isinstance(tokenization, dict)
    assert tokenization["revision"] == 7
    assert tokenization["canonical_updated"] is False


@pytest.mark.asyncio
async def test_path_created_after_absent_check_is_never_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "generation.sock"
    replacement_path = tmp_path / "replacement.sock"
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(replacement_path))
    replacement.listen(1)
    replacement_inode = replacement_path.lstat().st_ino

    original_lstat = Path.lstat
    injected = False

    def replace_after_check(candidate: Path) -> os.stat_result:
        nonlocal injected
        if candidate == path and not injected:
            injected = True
            os.replace(replacement_path, path)
            raise FileNotFoundError(path)
        return original_lstat(candidate)

    monkeypatch.setattr(
        "pathlib.Path.lstat",
        replace_after_check,
    )
    server = GenerationControlServer(
        path,
        GenerationLifecycle(),
        generation_id="g1",
        release_id="r1",
    )
    try:
        with pytest.raises(OSError):
            await server.start()
        assert path.lstat().st_ino == replacement_inode
    finally:
        replacement.close()
        path.unlink(missing_ok=True)
