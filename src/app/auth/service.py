from pathlib import Path

import httpx

from app.auth.device_flow import DeviceFlowClient
from app.auth.providers import FileTokenProvider


async def authenticate_device(token_path: Path | None = None) -> tuple[str, str]:
    file_provider = FileTokenProvider(token_path)
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        device_flow = DeviceFlowClient(http_client)
        device = await device_flow.request_device_code()
        token = await device_flow.poll_access_token(device)
    await file_provider.save_token(token)
    return device.verification_uri, device.user_code


async def clear_stored_token(token_path: Path | None = None) -> None:
    await FileTokenProvider(token_path).clear_token()