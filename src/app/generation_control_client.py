from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.generation_identity import GenerationIdentityError, parse_generation_id
from app.release_identity import ReleaseIdentityError, parse_release_id


class GenerationControlClientError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GenerationStatus:
    generation: str
    release: str
    pid: int
    phase: str
    ready: bool
    accepting: bool
    active_operations: int
    listener_families: tuple[str, ...]
    last_error: str | None
    revision: int


class GenerationControlClient:
    async def status(self, path: Path, *, timeout: float = 2) -> GenerationStatus:
        deadline = asyncio.get_running_loop().time() + timeout
        return self._parse(
            await self._request(
                path,
                {"version": 1, "command": "status"},
                deadline=deadline,
            )
        )

    async def wait_ready(self, path: Path, *, timeout: float) -> GenerationStatus:
        deadline = asyncio.get_running_loop().time() + timeout
        status = await self.status(path, timeout=timeout)
        while not status.ready:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"generation did not become ready: {path}")
            response = await self._request(
                path,
                {
                    "version": 1,
                    "command": "wait",
                    "after_revision": status.revision,
                    "timeout_ms": max(1, int(remaining * 1000)),
                },
                deadline=deadline,
            )
            if response.get("ok") is not True:
                raise TimeoutError(f"generation wait timed out: {path}")
            status = self._parse(response)
        return status

    async def _request(
        self,
        path: Path,
        payload: dict[str, object],
        *,
        deadline: float,
    ) -> dict[str, object]:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"generation control deadline expired: {path}")
        async with asyncio.timeout(remaining):
            reader, writer = await asyncio.open_unix_connection(path)
        try:
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                async with asyncio.timeout(max(0, remaining)):
                    writer.write(
                        json.dumps(payload, separators=(",", ":")).encode() + b"\n"
                    )
                    await writer.drain()
                    line = await reader.readline()
                if not line:
                    raise GenerationControlClientError(
                        "control endpoint closed without response"
                    )
                if len(line) > 65_536:
                    raise GenerationControlClientError("control response exceeds 64 KiB")
                response = json.loads(line)
                if not isinstance(response, dict):
                    raise GenerationControlClientError("control response must be an object")
                return cast(dict[str, object], response)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
                raise GenerationControlClientError(
                    f"invalid control response framing: {error}"
                ) from error
        finally:
            writer.close()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining > 0:
                try:
                    async with asyncio.timeout(remaining):
                        await writer.wait_closed()
                except TimeoutError:
                    pass

    @staticmethod
    def _parse(response: dict[str, object]) -> GenerationStatus:
        if response.get("ok") is not True:
            raise GenerationControlClientError(str(response.get("error", "control request failed")))
        if type(response.get("version")) is not int or response["version"] != 1:
            raise GenerationControlClientError("unsupported control response version")
        try:
            generation = response["generation"]
            release = response["release"]
            phase = response["phase"]
            family_values = response["listener_families"]
            last_error = response.get("last_error")
            if not isinstance(generation, str) or not isinstance(release, str):
                raise GenerationControlClientError("generation and release must be strings")
            parse_generation_id(generation)
            parse_release_id(release)
            if not isinstance(phase, str):
                raise GenerationControlClientError("phase must be a string")
            if not isinstance(family_values, list):
                raise GenerationControlClientError("listener_families must be a string list")
            family_objects = cast(list[object], family_values)
            if not all(isinstance(value, str) for value in family_objects):
                raise GenerationControlClientError("listener_families must be a string list")
            families = tuple(cast(list[str], family_objects))
            if last_error is not None and not isinstance(last_error, str):
                raise GenerationControlClientError("last_error must be a string or null")
            for name in ("pid", "active_operations", "revision"):
                if type(response[name]) is not int:
                    raise GenerationControlClientError(f"{name} must be an integer")
            for name in ("ready", "accepting"):
                if type(response[name]) is not bool:
                    raise GenerationControlClientError(f"{name} must be a boolean")
            if phase not in {
                "starting",
                "ready_accepting",
                "quiescing",
                "drained_standby",
                "stopping",
                "failed",
            }:
                raise GenerationControlClientError(f"invalid generation phase: {phase}")
            pid = cast(int, response["pid"])
            active_operations = cast(int, response["active_operations"])
            revision = cast(int, response["revision"])
            if pid <= 0 or active_operations < 0 or revision < 0:
                raise GenerationControlClientError("numeric control fields are out of range")
            ready = cast(bool, response["ready"])
            accepting = cast(bool, response["accepting"])
            if ready != (phase == "ready_accepting") or accepting != ready:
                raise GenerationControlClientError("phase, ready, and accepting are inconsistent")
            return GenerationStatus(
                generation=generation,
                release=release,
                pid=pid,
                phase=phase,
                ready=ready,
                accepting=accepting,
                active_operations=active_operations,
                listener_families=families,
                last_error=last_error,
                revision=revision,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            GenerationIdentityError,
            ReleaseIdentityError,
        ) as error:
            raise GenerationControlClientError(f"invalid control response: {error}") from error
