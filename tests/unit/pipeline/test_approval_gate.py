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


@pytest.mark.asyncio
async def test_quiesce_rejects_pending_and_new_requests_until_resume() -> None:
    gate = ApprovalGate(enabled=True, timeout_seconds=10)
    pending_result: ApprovalResult | None = None

    async def wait() -> None:
        nonlocal pending_result
        pending_result = await gate.wait_for_approval(_context("pending"))

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(wait)
        while not await gate.get_pending():
            await anyio.sleep(0)
        assert await gate.quiesce() == 1
    assert pending_result == ApprovalResult("rejected", "server_restarting")

    new_result = await gate.wait_for_approval(_context("new"))
    assert new_result == ApprovalResult("rejected", "server_restarting")

    await gate.resume()
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(wait)
        while not await gate.get_pending():
            await anyio.sleep(0)
        approval_id = (await gate.get_pending())[0]["id"]
        assert await gate.reject(approval_id, "done")
    assert pending_result == ApprovalResult("rejected", "done")


@pytest.mark.asyncio
async def test_quiesce_and_concurrent_creation_share_one_atomic_boundary() -> None:
    gate = ApprovalGate(enabled=True, timeout_seconds=10)
    results: list[ApprovalResult] = []

    async def create(index: int) -> None:
        results.append(await gate.wait_for_approval(_context(f"racing-{index}")))

    async with anyio.create_task_group() as tasks:
        for index in range(100):
            tasks.start_soon(create, index)
        tasks.start_soon(gate.quiesce)
    assert len(results) == 100
    assert all(
        result == ApprovalResult("rejected", "server_restarting")
        for result in results
    )
    assert await gate.get_pending() == []


@pytest.mark.asyncio
async def test_generation_admission_predicate_blocks_creation_before_gate_commit() -> None:
    gate = ApprovalGate(enabled=True, timeout_seconds=10)
    accepting = False
    gate.set_creation_predicate(lambda: accepting)

    rejected = await gate.wait_for_approval(_context("closed"))
    assert rejected == ApprovalResult("rejected", "server_restarting")

    accepting = True
    result: ApprovalResult | None = None

    async def wait() -> None:
        nonlocal result
        result = await gate.wait_for_approval(_context("open"))

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(wait)
        while not await gate.get_pending():
            await anyio.sleep(0)
        approval_id = (await gate.get_pending())[0]["id"]
        assert await gate.reject(approval_id, "done")
    assert result == ApprovalResult("rejected", "done")
