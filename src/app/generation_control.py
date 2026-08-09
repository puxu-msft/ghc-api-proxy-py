from __future__ import annotations

import asyncio
import fcntl
import json
import os
import socket
import stat
from pathlib import Path
from typing import Any, cast

from app.generation import GenerationLifecycle, GenerationSnapshot

PROTOCOL_VERSION = 1


class GenerationControlError(RuntimeError):
    """Raised when the generation control endpoint cannot be safely managed."""


class GenerationControlServer:
    def __init__(
        self,
        path: Path,
        lifecycle: GenerationLifecycle,
        *,
        generation_id: str,
        release_id: str,
        listener_families: tuple[str, ...] = ("http-v4", "http-v6"),
    ) -> None:
        self._path = path
        self._lifecycle = lifecycle
        self._generation_id = generation_id
        self._release_id = release_id
        self._listener_families = listener_families
        self._server: asyncio.Server | None = None
        self._lock_fd: int | None = None

    async def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._acquire_lock()
        bound_socket: socket.socket | None = None
        try:
            self._require_absent_path()
            bound_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            previous_umask = os.umask(0o177)
            try:
                bound_socket.bind(str(self._path))
            finally:
                os.umask(previous_umask)
            bound_socket.listen(100)
            bound_socket.setblocking(False)
            self._server = await asyncio.start_unix_server(
                self._handle,
                sock=bound_socket,
                cleanup_socket=False,
            )
            bound_socket = None
        except BaseException:
            if bound_socket is not None:
                bound_socket.close()
            await self.close()
            raise

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def _require_absent_path(self) -> None:
        try:
            path_stat = self._path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(path_stat.st_mode):
            raise GenerationControlError(
                f"refusing to replace non-socket control path: {self._path}"
            )
        raise GenerationControlError(
            f"existing control endpoint requires explicit cleanup: {self._path}"
        )

    def _acquire_lock(self) -> None:
        lock_path = self._path.with_name(self._path.name + ".lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            raise GenerationControlError(f"control endpoint lock is held: {lock_path}") from error
        self._lock_fd = fd

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            try:
                request = json.loads(line)
                response = await self._dispatch(request)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                response = {"ok": False, "error": str(error)}
            writer.write(json.dumps(response, separators=(",", ":")).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, request: Any) -> dict[str, object]:
        if not isinstance(request, dict):
            raise TypeError("request must be an object")
        values = cast(dict[str, object], request)
        if values.get("version") != PROTOCOL_VERSION:
            raise ValueError(f"unsupported protocol version: {values.get('version')!r}")
        command = values.get("command")
        if command == "status":
            return self._response(await self._lifecycle.snapshot())
        if command == "wait":
            after_revision = values.get("after_revision")
            timeout_ms = values.get("timeout_ms", 30_000)
            if type(after_revision) is not int or after_revision < 0:
                raise ValueError("after_revision must be a non-negative integer")
            if type(timeout_ms) is not int or timeout_ms < 0:
                raise ValueError("timeout_ms must be a non-negative integer")
            timeout = None if timeout_ms == 0 else timeout_ms / 1000
            try:
                snapshot = await self._lifecycle.wait_for_change(
                    after_revision,
                    timeout,
                )
            except TimeoutError:
                return {"ok": False, "error": "wait_timeout"}
            return self._response(snapshot)
        raise ValueError(f"unsupported command: {command!r}")

    def _response(self, snapshot: GenerationSnapshot) -> dict[str, object]:
        return {
            "ok": True,
            "version": PROTOCOL_VERSION,
            "generation": self._generation_id,
            "release": self._release_id,
            "pid": os.getpid(),
            "phase": snapshot.phase.value,
            "ready": snapshot.phase.value == "ready_accepting",
            "accepting": snapshot.accepting,
            "active_operations": snapshot.active_operations,
            "listener_families": list(self._listener_families),
            "last_error": snapshot.last_error,
            "revision": snapshot.revision,
        }
