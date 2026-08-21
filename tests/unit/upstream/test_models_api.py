from collections.abc import Mapping

import httpx2
import pytest

from app.upstream.models_api import ModelCatalog


@pytest.mark.asyncio
async def test_models_api_fetches_preserves_and_indexes_catalog() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url == "https://copilot.example/models"
        assert request.headers["authorization"] == "Bearer token"
        return httpx2.Response(
            200,
            headers={"ETag": '"catalog-v1"'},
            json={
                "object": "list",
                "data": [
                    {
                        "id": "claude-test",
                        "name": "Claude Test",
                        "vendor": "Anthropic",
                        "supported_endpoints": ["/v1/messages"],
                        "request_headers": {"x-model-route": "a"},
                        "future_field": {"keep": True},
                    }
                ],
            },
        )

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    catalog = ModelCatalog(http_client, "https://copilot.example")
    try:
        changed = await catalog.refresh({"Authorization": "Bearer token"})
    finally:
        await http_client.aclose()

    assert changed is True
    model = catalog.get("claude-test")
    assert model is not None
    assert model.model_extra == {"future_field": {"keep": True}}
    assert catalog.available_ids == frozenset({"claude-test"})


@pytest.mark.asyncio
async def test_models_api_uses_etag_and_keeps_catalog_on_304() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(
                200,
                headers={"ETag": '"v1"'},
                json={"object": "list", "data": [{"id": "model-a"}]},
            )
        assert request.headers["if-none-match"] == '"v1"'
        return httpx2.Response(304)

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    catalog = ModelCatalog(http_client, "https://copilot.example")
    try:
        assert await catalog.refresh({}) is True
        assert await catalog.refresh({}) is False
    finally:
        await http_client.aclose()

    assert catalog.get("model-a") is not None


def test_disabled_models_are_removed_only_from_available_index() -> None:
    catalog = ModelCatalog(None, "https://copilot.example", disabled_ids={"disabled"})
    catalog.replace_from_data(
        {"object": "list", "data": [{"id": "enabled"}, {"id": "disabled"}]}
    )

    assert catalog.get("disabled") is not None
    assert catalog.available_ids == frozenset({"enabled"})


@pytest.mark.asyncio
async def test_model_refresh_loop_waits_then_refreshes() -> None:
    class RecordingCatalog(ModelCatalog):
        def __init__(self) -> None:
            super().__init__(None, "https://copilot.example")
            self.headers: list[dict[str, str]] = []

        async def refresh(self, headers: Mapping[str, str]) -> bool:
            self.headers.append(dict(headers))
            raise RuntimeError("stop")

    catalog = RecordingCatalog()
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    with pytest.raises(RuntimeError, match="stop"):
        await catalog.run_refresh_loop({}, interval_seconds=30, sleep=sleep)

    assert sleeps == [30]
    assert catalog.headers == [{}]
