import anyio
import pytest

from app.pipeline.approval import ApprovalGate, ApprovalResult
from app.pipeline.context import RequestContext


def _context(identifier: str = "request") -> RequestContext:
    return RequestContext(
        id=identifier,
        original_model="model",
        resolved_model="model",
        original_payload={"messages": [{"role": "user", "content": "hi"}]},
    )


@pytest.mark.asyncio
async def test_approve_wakes_waiter_and_cleans_pending() -> None:
    gate = ApprovalGate(enabled=True, timeout_seconds=1)
    result = None

    async def wait() -> None:
        nonlocal result
        result = await gate.wait_for_approval(_context())

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(wait)
        while not await gate.get_pending():
            await anyio.sleep(0)
        approval_id = (await gate.get_pending())[0]["id"]
        assert await gate.approve(approval_id) is True
    assert result is not None and result.status == "approved"
    assert await gate.get_pending() == []


@pytest.mark.asyncio
async def test_modify_and_approve_returns_modified_payload() -> None:
    gate = ApprovalGate(enabled=True, timeout_seconds=1)
    result = None

    async def wait() -> None:
        nonlocal result
        result = await gate.wait_for_approval(_context())

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(wait)
        while not await gate.get_pending():
            await anyio.sleep(0)
        approval_id = (await gate.get_pending())[0]["id"]
        assert await gate.modify_and_approve(approval_id, {"model": "other"})
    assert result is not None
    assert result.modified_payload["model"] == "other"


@pytest.mark.asyncio
async def test_timeout_and_shutdown_reject_waiters() -> None:
    timeout_gate = ApprovalGate(enabled=True, timeout_seconds=0.01)
    timed_out = await timeout_gate.wait_for_approval(_context("timeout"))
    assert timed_out.status == "rejected"
    assert "timeout" in timed_out.reason.lower()

    gate = ApprovalGate(enabled=True, timeout_seconds=10)
    results: list[ApprovalResult] = []

    async def wait(identifier: str) -> None:
        results.append(await gate.wait_for_approval(_context(identifier)))

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(wait, "one")
        tasks.start_soon(wait, "two")
        while len(await gate.get_pending()) < 2:
            await anyio.sleep(0)
        assert await gate.reject_all_pending("server shutting down") == 2
    assert all(result.status == "rejected" for result in results)