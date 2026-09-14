from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import anyio
import httpx2


@dataclass(frozen=True, slots=True)
class ModelCatalogPage:
    """One successful model catalog fetch.

    `raw` is the upstream wire payload; this library deliberately does not validate or model it.
    """

    raw: dict[str, Any]
    etag: str | None


async def fetch_models(
    http_client: httpx2.AsyncClient,
    base_url: str,
    headers: Mapping[str, str],
    *,
    etag: str | None = None,
) -> ModelCatalogPage | None:
    """Fetch the model catalog.

    Pass the previously returned `etag` to negotiate; returns `None` when upstream answers 304.
    """
    request_headers = dict(headers)
    if etag is not None:
        request_headers["If-None-Match"] = etag
    response = await http_client.get(
        f"{base_url.rstrip('/')}/models",
        headers=request_headers,
    )
    if response.status_code == 304:
        return None
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return ModelCatalogPage(raw=data, etag=response.headers.get("etag"))


async def run_model_refresh_loop(
    refresh: Callable[[], Awaitable[object]],
    *,
    interval_seconds: float,
    on_error: Callable[[Exception], None],
    sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
) -> None:
    """Refresh the catalog periodically; report one failure and keep the loop alive."""
    while True:
        await sleep(interval_seconds)
        try:
            await refresh()
        except Exception as error:
            on_error(error)
