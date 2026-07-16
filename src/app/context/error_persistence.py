from pathlib import Path
from typing import Any

from anyio.to_thread import run_sync

from app.pipeline.context import RequestContext
from app.wire_json import dumps


class ErrorPersistenceConsumer:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def handle(
        self,
        event: str,
        context: RequestContext,
        data: dict[str, Any],
    ) -> None:
        if event != "failed":
            return

        def write() -> None:
            self._directory.mkdir(parents=True, exist_ok=True)
            target = self._directory / f"{context.id}.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(dumps({"request_id": context.id, **data}))
            temporary.replace(target)

        await run_sync(write)