# 手动审批系统

## 概述

手动审批系统（`pipeline/approval.py` + `routes/approval.py`）提供可选的请求审批门控。启用后，所有到上游的请求必须经过人工审批才能执行。

核心机制：使用 `asyncio.Event` 挂起请求处理协程，零 CPU 开销等待审批结果。

## 审批流程

```
客户端发送 API 请求
    │
    ▼
管道执行器：检查审批是否启用
    │
    ├─ 未启用 → 跳过，直接执行
    │
    └─ 已启用 ↓
         │
         ▼
    创建 PendingApproval
    ├─ 生成 approval_id
    ├─ 记录完整 payload
    ├─ 创建 asyncio.Event（初始未设置）
    ├─ 启动超时定时器
         │
         ▼
    WebSocket 广播：approval_requested 事件
         │
         ▼
    await event.wait()  ← 协程在此挂起，零 CPU 开销
         │
         │  ┌───────────────────────────────────┐
         │  │ 审批者通过管理 API 操作           │
         │  │                                   │
         │  │  POST /approve → 设置 approved    │
         │  │  POST /reject  → 设置 rejected    │
         │  │  POST /modify  → 修改+设置 approved│
         │  │  超时           → 设置 rejected    │
         │  └───────────────────────────────────┘
         │
         ▼ event.set() 唤醒
    检查审批结果
    ├─ approved → 继续执行管道
    ├─ approved_with_modifications → 使用修改后的 payload 继续
    └─ rejected → 返回 403 错误给客户端
```

## ApprovalGate 类

```python
class ApprovalGate:
    """手动审批门控。"""

    def __init__(
        self,
        enabled: bool = False,
        timeout_seconds: float = 300,  # 默认 5 分钟超时
    ):
        self.enabled = enabled
        self._timeout = timeout_seconds
        self._pending: dict[str, PendingApproval] = {}
        self._lock = asyncio.Lock()
        self._ws_manager: WebSocketManager | None = None

    def set_ws_manager(self, ws_manager: WebSocketManager) -> None:
        """注入 WebSocket 管理器用于推送通知。"""
        self._ws_manager = ws_manager

    async def wait_for_approval(
        self,
        request_id: str,
        payload: dict,
        endpoint: str,
        model: str,
    ) -> ApprovalResult:
        """
        提交请求等待审批。

        阻塞直到审批者做出决策或超时。
        """
        approval = PendingApproval(
            id=f"approval_{uuid4().hex[:12]}",
            request_id=request_id,
            payload=payload,
            endpoint=endpoint,
            model=model,
            created_at=time.time(),
            timeout_at=time.time() + self._timeout,
            event=asyncio.Event(),
            result=None,
        )

        async with self._lock:
            self._pending[approval.id] = approval

        # 广播通知
        if self._ws_manager:
            await self._ws_manager.broadcast("approval", {
                "type": "approval_requested",
                "approval": approval.to_summary(),
            })

        # 等待审批或超时
        try:
            await asyncio.wait_for(
                approval.event.wait(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            approval.result = ApprovalResult(
                status="rejected",
                reason="Approval timeout",
            )

        # 清理
        async with self._lock:
            self._pending.pop(approval.id, None)

        return approval.result

    async def approve(self, approval_id: str) -> bool:
        """批准请求。"""
        async with self._lock:
            approval = self._pending.get(approval_id)
        if not approval:
            return False

        approval.result = ApprovalResult(status="approved")
        approval.event.set()

        if self._ws_manager:
            await self._ws_manager.broadcast("approval", {
                "type": "approval_resolved",
                "approval": {"id": approval_id, "status": "approved"},
            })
        return True

    async def reject(self, approval_id: str, reason: str = "") -> bool:
        """拒绝请求。"""
        async with self._lock:
            approval = self._pending.get(approval_id)
        if not approval:
            return False

        approval.result = ApprovalResult(status="rejected", reason=reason)
        approval.event.set()

        if self._ws_manager:
            await self._ws_manager.broadcast("approval", {
                "type": "approval_resolved",
                "approval": {"id": approval_id, "status": "rejected", "reason": reason},
            })
        return True

    async def modify_and_approve(
        self,
        approval_id: str,
        modifications: dict,
    ) -> bool:
        """修改 payload 后批准。"""
        async with self._lock:
            approval = self._pending.get(approval_id)
        if not approval:
            return False

        # 合并修改
        modified_payload = {**approval.payload, **modifications}
        modified_fields = list(modifications.keys())

        approval.result = ApprovalResult(
            status="approved_with_modifications",
            modified_payload=modified_payload,
            modifications=modified_fields,
        )
        approval.event.set()

        if self._ws_manager:
            await self._ws_manager.broadcast("approval", {
                "type": "approval_resolved",
                "approval": {
                    "id": approval_id,
                    "status": "approved_with_modifications",
                    "modifications": modified_fields,
                },
            })
        return True

    async def get_pending(self) -> list[dict]:
        """获取所有待审批请求摘要。"""
        async with self._lock:
            return [a.to_summary() for a in self._pending.values()]

    async def get_pending_detail(self, approval_id: str) -> dict | None:
        """获取待审批请求完整详情（含 payload）。"""
        async with self._lock:
            approval = self._pending.get(approval_id)
        if not approval:
            return None
        return approval.to_detail()

    async def reject_all_pending(self, reason: str) -> int:
        """拒绝所有待审批请求（用于关闭时）。"""
        async with self._lock:
            pending = list(self._pending.values())

        count = 0
        for approval in pending:
            approval.result = ApprovalResult(status="rejected", reason=reason)
            approval.event.set()
            count += 1
        return count
```

## 数据结构

```python
@dataclass
class PendingApproval:
    id: str
    request_id: str
    payload: dict
    endpoint: str                     # "openai-chat-completions" | "openai-responses" | "anthropic-messages"
    model: str
    created_at: float
    timeout_at: float
    event: asyncio.Event
    result: ApprovalResult | None

    def to_summary(self) -> dict:
        """摘要（不含完整 payload）。"""
        messages = self.payload.get("messages", [])
        return {
            "id": self.id,
            "request_id": self.request_id,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "timeout_at": datetime.fromtimestamp(self.timeout_at).isoformat(),
            "endpoint": self.endpoint,
            "model": self.model,
            "summary": {
                "message_count": len(messages),
                "has_tools": bool(self.payload.get("tools")),
                "has_system": bool(self.payload.get("system")),
            },
        }

    def to_detail(self) -> dict:
        """完整详情（含 payload）。"""
        return {
            **self.to_summary(),
            "payload": self.payload,
        }

@dataclass
class ApprovalResult:
    status: Literal["approved", "rejected", "approved_with_modifications"]
    reason: str = ""
    modified_payload: dict | None = None
    modifications: list[str] | None = None
```

## 与管道集成

在 `pipeline/executor.py` 中：

```python
# 审批阶段
if approval_gate.enabled:
    ctx.transition("awaiting_approval")
    result = await approval_gate.wait_for_approval(
        request_id=ctx.id,
        payload=payload,
        endpoint=ctx.endpoint,
        model=ctx.resolved_model,
    )
    ctx.approval_status = result.status

    if result.status == "rejected":
        error = ApiError(type="rejected", message=f"Request rejected: {result.reason}")
        ctx.fail(error)
        raise RequestRejectedError(error)

    if result.modified_payload:
        payload = result.modified_payload
```

## 配置

```yaml
approval:
  enabled: false           # 是否启用手动审批
  timeout_seconds: 300     # 超时时间（秒），默认 5 分钟
```

CLI 参数：
```
--manual              启用手动审批
--approval-timeout    审批超时秒数（默认 300）
```

## 关闭处理

服务器关闭时，所有待审批请求自动拒绝：

```python
# server.py lifespan 关闭阶段
rejected = await approval_gate.reject_all_pending("server shutting down")
logger.info(f"Rejected {rejected} pending approval(s) during shutdown")
```

## 相关文档

- [整体架构概览](architecture.md)
- [请求执行管道](request-pipeline.md)
- [API 端点规格](api-endpoints.md)（审批 API 详情）
- [配置系统](config-system.md)
