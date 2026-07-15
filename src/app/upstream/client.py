from dataclasses import dataclass

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config.settings import AppSettings
from app.upstream.urls import resolve_copilot_base_url


@dataclass(slots=True)
class SDKClients:
    openai: AsyncOpenAI
    anthropic: AsyncAnthropic

    async def close(self, *, close_http_client: bool = True) -> None:
        if close_http_client:
            await self.openai.close()


def create_http_client(settings: AppSettings) -> httpx.AsyncClient:
    upstream = settings.upstream
    return httpx.AsyncClient(
        http2=upstream.http2,
        proxy=upstream.proxy,
        limits=httpx.Limits(
            max_connections=upstream.max_connections,
            max_keepalive_connections=upstream.max_keepalive_connections,
            keepalive_expiry=upstream.keepalive_expiry,
        ),
        timeout=httpx.Timeout(
            connect=upstream.connect_timeout,
            read=upstream.read_timeout,
            write=upstream.read_timeout,
            pool=upstream.connect_timeout,
        ),
    )


def create_sdk_clients(
    settings: AppSettings,
    *,
    http_client: httpx.AsyncClient,
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
    http_client: httpx.AsyncClient,
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