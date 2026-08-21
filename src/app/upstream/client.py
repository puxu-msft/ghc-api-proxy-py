from dataclasses import dataclass

import httpx2
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config.settings import AppSettings
from app.upstream.urls import resolve_copilot_base_url


@dataclass(slots=True)
class SDKClients:
    openai: AsyncOpenAI
    anthropic: AsyncAnthropic

    async def close(self) -> None:
        await self.openai.close()
        await self.anthropic.close()


def create_http_client(settings: AppSettings) -> httpx2.AsyncClient:
    upstream = settings.upstream
    return httpx2.AsyncClient(
        http2=upstream.http2,
        proxy=upstream.proxy,
        limits=httpx2.Limits(
            max_connections=upstream.max_connections,
            max_keepalive_connections=upstream.max_keepalive_connections,
            keepalive_expiry=upstream.keepalive_expiry,
        ),
        timeout=httpx2.Timeout(
            connect=upstream.connect_timeout,
            read=upstream.read_timeout,
            write=upstream.read_timeout,
            pool=upstream.connect_timeout,
        ),
    )


def create_sdk_clients(
    settings: AppSettings,
    *,
    http_client: httpx2.AsyncClient,
) -> SDKClients:
    upstream = settings.upstream
    openai_base_url = upstream.openai_base_url or "https://api.openai.com/v1"
    anthropic_base_url = upstream.anthropic_base_url or "https://api.anthropic.com"
    api_key = upstream.api_key or "proxy-managed"
    return SDKClients(
        openai=AsyncOpenAI(
            api_key=api_key,
            base_url=openai_base_url,
            http_client=http_client,
            max_retries=0,
        ),
        anthropic=AsyncAnthropic(
            api_key=api_key,
            base_url=anthropic_base_url,
            http_client=http_client,
            max_retries=0,
        ),
    )


def create_copilot_sdk_clients(
    settings: AppSettings,
    *,
    http_client: httpx2.AsyncClient,
) -> SDKClients:
    base_url = resolve_copilot_base_url(settings)
    return SDKClients(
        openai=AsyncOpenAI(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
        anthropic=AsyncAnthropic(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
    )
