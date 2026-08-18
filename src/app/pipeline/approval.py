import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

import anyio

from app.history.ws import WebSocketManager
from app.pipeline.context import RequestContext


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    status: Literal["approved", "rejected", "approved_with_modifications"]
    reason: str = ""
    modified_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class PendingApproval:
    id: str
    request_id: str
    payload: dict[str, Any]
    endpoint: str
    model: str
    created_at: float
    timeout_at: float
    event: anyio.Event
    result: ApprovalResult | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "model": self.model,
            "created_at": self.created_at,
            "timeout_at": self.timeout_at,
        }


class ApprovalGate:
    def __init__(
        self,
        *,
        enabled: bool,
        timeout_seconds: float,
        max_pending: int = 1000,
        websockets: WebSocketManager | None = None,
    ) -> None:
        self.enabled = enabled
        self._timeout = timeout_seconds
        self._max_pending = max_pending
        self._websockets = websockets
        self._pending: dict[str, PendingApproval] = {}
        self._lock = anyio.Lock()
        self._creation_open = True
        self._quiesce_reason = "server_restarting"
        self._creation_predicate: Callable[[], bool] | None = None

    async def wait_for_approval(self, context: RequestContext) -> ApprovalResult:
        if not self.enabled:
            return ApprovalResult("approved")
        now = time.time()
        approval = PendingApproval(
            id=f"approval_{uuid4().hex[:12]}",
            request_id=context.id,
            payload=context.original_payload,
            endpoint=context.endpoint,
            model=context.resolved_model,
            created_at=now,
            timeout_at=now + self._timeout,
            event=anyio.Event(),
        )
        async with self._lock:
            if not self._creation_open or (
                self._creation_predicate is not None
                and not self._creation_predicate()
            ):
                return ApprovalResult("rejected", self._quiesce_reason)
            if len(self._pending) >= self._max_pending:
                return ApprovalResult("rejected", "Approval queue full")
            self._pending[approval.id] = approval
        if self._websockets:
            await self._websockets.broadcast(
                {"type": "approval_requested", "approval": approval.summary()},
                topic="approval",
            )
        try:
            with anyio.move_on_after(self._timeout) as scope:
                await approval.event.wait()
            if scope.cancel_called:
                approval.result = ApprovalResult("rejected", "Approval timeout")
                if self._websockets:
                    await self._websockets.broadcast(
                        {
                            "type": "approval_timeout",
                            "approval": {"id": approval.id},
                        },
                        topic="approval",
                    )
            assert approval.result is not None
            return approval.result
        finally:
            with anyio.CancelScope(shield=True):
                async with self._lock:
                    self._pending.pop(approval.id, None)

    async def _resolve(self, approval_id: str, result: ApprovalResult) -> bool:
        async with self._lock:
            approval = self._pending.get(approval_id)
            if approval is None or approval.result is not None:
                return False
            approval.result = result
            approval.event.set()
        if self._websockets:
            await self._websockets.broadcast(
                {
                    "type": "approval_resolved",
                    "approval": {"id": approval_id, "status": result.status},
                },
                topic="approval",
            )
        return True

    async def approve(self, approval_id: str) -> bool:
        return await self._resolve(approval_id, ApprovalResult("approved"))

    async def reject(self, approval_id: str, reason: str = "") -> bool:
        return await self._resolve(approval_id, ApprovalResult("rejected", reason))

    async def modify_and_approve(
        self,
        approval_id: str,
        modifications: dict[str, Any],
    ) -> bool:
        async with self._lock:
            approval = self._pending.get(approval_id)
            payload = {**approval.payload, **modifications} if approval else None
        if payload is None:
            return False
        return await self._resolve(
            approval_id,
            ApprovalResult("approved_with_modifications", modified_payload=payload),
        )

    async def get_pending(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [approval.summary() for approval in self._pending.values()]

    async def get_detail(self, approval_id: str) -> dict[str, Any] | None:
        async with self._lock:
            approval = self._pending.get(approval_id)
            return {**approval.summary(), "payload": approval.payload} if approval else None

    async def reject_all_pending(self, reason: str) -> int:
        async with self._lock:
            ids = list(self._pending)
        resolved = 0
        for approval_id in ids:
            resolved += int(await self.reject(approval_id, reason))
        return resolved

    async def quiesce(self, reason: str = "server_restarting") -> int:
        resolved_ids: list[str] = []
        async with self._lock:
            self._creation_open = False
            self._quiesce_reason = reason
            for approval_id, approval in self._pending.items():
                if approval.result is None:
                    approval.result = ApprovalResult("rejected", reason)
                    approval.event.set()
                    resolved_ids.append(approval_id)
        if self._websockets:
            for approval_id in resolved_ids:
                await self._websockets.broadcast(
                    {
                        "type": "approval_resolved",
                        "approval": {"id": approval_id, "status": "rejected"},
                    },
                    topic="approval",
                )
        return len(resolved_ids)

    async def resume(self) -> None:
        async with self._lock:
            self._creation_open = True

    def set_creation_predicate(self, predicate: Callable[[], bool] | None) -> None:
        self._creation_predicate = predicate


class ApprovalRejectedError(RuntimeError):
    pass
