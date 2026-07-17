import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import anyio
from anyio.to_thread import run_sync

from app.tokenization.calibration import CalibrationEngine
from app.tokenization.limits import PromptLimitRegistry
from app.wire_json import dumps, loads

_STATE_VERSION = 1
logger = logging.getLogger(__name__)


class TokenizationStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._revision = 0
        self._flushed_revision = 0
        self._flush_lock = anyio.Lock()
        self.calibration = CalibrationEngine(on_change=self._mark_dirty)
        self.prompt_limits = PromptLimitRegistry(on_change=self._mark_dirty)

    def _mark_dirty(self) -> None:
        self._revision += 1

    @property
    def dirty(self) -> bool:
        return self._revision != self._flushed_revision

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": _STATE_VERSION,
            "calibration": self.calibration.snapshot(),
            "prompt_limits": self.prompt_limits.snapshot(),
        }

    async def load(self) -> None:
        try:
            raw = await run_sync(self.path.read_bytes)
        except FileNotFoundError:
            return
        except OSError as error:
            logger.warning("tokenization state could not be read: %s", error)
            return
        try:
            value = loads(raw)
        except ValueError as error:
            logger.warning("tokenization state is corrupted; starting empty: %s", error)
            return
        if not isinstance(value, dict) or value.get("version") != _STATE_VERSION:
            logger.warning("unsupported tokenization state version; starting empty")
            return
        typed_value = cast(dict[str, Any], value)
        calibration = typed_value.get("calibration", {})
        prompt_limits = typed_value.get("prompt_limits", {})
        if not isinstance(calibration, dict) or not isinstance(prompt_limits, dict):
            logger.warning("invalid tokenization state shape; starting empty")
            return
        self.calibration = CalibrationEngine.from_snapshot(
            cast(dict[str, Any], calibration),
            on_change=self._mark_dirty,
        )
        self.prompt_limits = PromptLimitRegistry.from_snapshot(
            cast(dict[str, Any], prompt_limits),
            on_change=self._mark_dirty,
        )
        self._revision = 0
        self._flushed_revision = 0

    async def flush(self) -> bool:
        async with self._flush_lock:
            revision = self._revision
            if revision == self._flushed_revision:
                return False
            snapshot = self.snapshot()
            try:
                await run_sync(self._atomic_write, dumps(snapshot))
            except OSError as error:
                logger.warning("tokenization state could not be persisted: %s", error)
                return False
            self._flushed_revision = revision
            return True

    def _atomic_write(self, data: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(self.path)
        finally:
            with suppress(FileNotFoundError):
                temporary.unlink()

    async def run_periodic_flush(self, interval_seconds: float) -> None:
        while True:
            await anyio.sleep(interval_seconds)
            await self.flush()
