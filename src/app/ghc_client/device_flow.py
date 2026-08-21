import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import anyio
import httpx2

GITHUB_CLIENT_ID = "Iv1.b507a08c87ecfe98"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"


class DeviceFlowError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DeviceFlowClient:
    def __init__(
        self,
        http_client: httpx2.AsyncClient,
        *,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http_client
        self._sleep = sleep
        self._monotonic = monotonic

    def parse_device_code(self, data: Mapping[str, Any]) -> DeviceCode:
        try:
            return DeviceCode(
                device_code=str(data["device_code"]),
                user_code=str(data["user_code"]),
                verification_uri=str(data["verification_uri"]),
                expires_in=int(data["expires_in"]),
                interval=int(data["interval"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise DeviceFlowError("invalid device code response") from error

    async def request_device_code(self) -> DeviceCode:
        response = await self._http.post(
            DEVICE_CODE_URL,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"client_id": GITHUB_CLIENT_ID, "scope": "read:user"},
        )
        response.raise_for_status()
        return self.parse_device_code(response.json())

    async def poll_access_token(self, device: DeviceCode) -> str:
        interval = float(device.interval)
        deadline = self._monotonic() + device.expires_in
        while self._monotonic() < deadline:
            await self._sleep(interval)
            response = await self._http.post(
                ACCESS_TOKEN_URL,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                json={
                    "client_id": GITHUB_CLIENT_ID,
                    "device_code": device.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            token = data.get("access_token")
            if isinstance(token, str) and token:
                return token
            error = data.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if isinstance(error, str):
                raise DeviceFlowError(f"GitHub device authorization failed: {error}")
            raise DeviceFlowError("invalid access token response")
        raise DeviceFlowError("GitHub device authorization expired")
