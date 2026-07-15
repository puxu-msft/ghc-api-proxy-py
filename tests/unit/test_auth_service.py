from pathlib import Path

import pytest

from app.auth.device_flow import DeviceCode
from app.auth.service import run_device_authentication


class FakeDeviceFlow:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def request_device_code(self) -> DeviceCode:
        self.events.append("request")
        return DeviceCode("device", "CODE", "https://github.com/login/device", 900, 5)

    async def poll_access_token(self, device: DeviceCode) -> str:
        assert device.user_code == "CODE"
        self.events.append("poll")
        return "ghu_token"


class FakeStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def save_token(self, token: str) -> None:
        assert token == "ghu_token"
        self.events.append("save")


@pytest.mark.asyncio
async def test_device_authentication_notifies_before_poll_and_save(tmp_path: Path) -> None:
    del tmp_path
    events: list[str] = []

    def notify(uri: str, code: str) -> None:
        assert uri == "https://github.com/login/device"
        assert code == "CODE"
        events.append("notify")

    await run_device_authentication(
        FakeDeviceFlow(events),
        FakeStore(events),
        notify=notify,
    )

    assert events == ["request", "notify", "poll", "save"]