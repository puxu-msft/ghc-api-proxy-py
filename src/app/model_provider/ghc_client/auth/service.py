from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx2

from app.model_provider.ghc_client.auth.providers import FileTokenProvider
from app.model_provider.ghc_client.config import GITHUB_WEB_BASE_URL
from app.model_provider.ghc_client.device_flow import DeviceCode, DeviceFlowClient


class DeviceFlow(Protocol):
    async def request_device_code(self) -> DeviceCode: ...

    async def poll_access_token(self, device: DeviceCode) -> str: ...


class TokenStore(Protocol):
    async def save_token(self, token: str) -> None: ...


async def run_device_authentication(
    device_flow: DeviceFlow,
    token_store: TokenStore,
    *,
    notify: Callable[[str, str], None],
) -> None:
    device = await device_flow.request_device_code()
    notify(device.verification_uri, device.user_code)
    token = await device_flow.poll_access_token(device)
    await token_store.save_token(token)


async def authenticate_device(
    notify: Callable[[str, str], None],
    token_path: Path | None = None,
    *,
    web_base_url: str = GITHUB_WEB_BASE_URL,
) -> None:
    """Run Device Flow against `web_base_url` and store the token at `token_path`.

    Both are the host's to decide: which tenant issues the device code, and which file the provider that will use it reads. The default pair is dotcom plus the default token location, which is what a deployment naming no provider gets.
    """
    file_provider = FileTokenProvider(token_path)
    async with httpx2.AsyncClient(timeout=30.0) as http_client:
        device_flow = DeviceFlowClient(http_client, web_base_url=web_base_url)
        await run_device_authentication(device_flow, file_provider, notify=notify)


async def clear_stored_token(token_path: Path | None = None) -> None:
    await FileTokenProvider(token_path).clear_token()
