from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx

from app.auth.providers import FileTokenProvider
from app.ghc_client.device_flow import DeviceCode, DeviceFlowClient


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
) -> None:
    file_provider = FileTokenProvider(token_path)
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        device_flow = DeviceFlowClient(http_client)
        await run_device_authentication(device_flow, file_provider, notify=notify)


async def clear_stored_token(token_path: Path | None = None) -> None:
    await FileTokenProvider(token_path).clear_token()
