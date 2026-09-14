from typing import Any, cast

import httpx2

from app.config.schema import CommandCodeProviderConfig
from app.model_provider.commandcode.provider import CommandCodeProvider
from app.model_provider.types import ModelEndpoint


class _Client:
    base_url = "https://api.commandcode.ai"

    async def fetch_models(self) -> dict[str, Any]:
        return {"object": "list", "data": [{"id": "m"}]}

    async def send(self, *args: Any, **kwargs: Any) -> httpx2.Response:
        del args, kwargs
        return httpx2.Response(200, json={"events": []})


class _FailingCatalogClient(_Client):
    async def fetch_models(self) -> dict[str, Any]:
        raise RuntimeError("catalog unavailable")


def test_commandcode_config_and_static_catalog_are_independent_of_chat() -> None:
    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "models": ["deepseek/deepseek-v4-flash"],
        }
    )
    provider = CommandCodeProvider("cc", cast(Any, _Client()), config)

    descriptor = provider.describe("deepseek/deepseek-v4-flash")
    assert descriptor is not None
    assert descriptor.endpoints == frozenset({ModelEndpoint.COMMANDCODE_GENERATE})
    assert ModelEndpoint.OPENAI_CHAT_COMPLETIONS not in descriptor.endpoints


def test_commandcode_catalog_refresh_replaces_the_static_catalog() -> None:
    config = CommandCodeProviderConfig.model_validate(
        {"type": "commandcode", "api_key": "user_test", "models": []}
    )
    provider = CommandCodeProvider("cc", cast(Any, _Client()), config)

    assert provider.available_ids == frozenset()

    import asyncio

    asyncio.run(provider.refresh_catalog())
    assert provider.available_ids == frozenset({"m"})


def test_commandcode_catalog_failure_keeps_configured_static_catalog() -> None:
    config = CommandCodeProviderConfig.model_validate(
        {
            "type": "commandcode",
            "api_key": "user_test",
            "models": ["m"],
        }
    )
    provider = CommandCodeProvider(
        "cc",
        cast(Any, _FailingCatalogClient()),
        config,
    )

    import asyncio

    assert asyncio.run(provider.refresh_catalog()) is False
    assert provider.available_ids == frozenset({"m"})
