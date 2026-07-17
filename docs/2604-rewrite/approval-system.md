# 手动审批系统 `[本项目新增]`

> 本文档描述的是**本项目独有功能**——上游参考项目没有手动审批门控。标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。

## 概述

手动审批系统（`pipeline/approval.py` + `routes/approval.py`）提供可选的请求审批门控。启用后，所有到上游的请求必须经过人工审批才能执行。

**Python 独有功能**：JS 版本没有审批门控。这是 Python 重写版新增的功能，核心机制使用 AnyIO Event 挂起请求处理协程，并用 cancel scope 表达超时与 shutdown 取消，零 CPU 开销等待审批结果。

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
    ├─ 创建 AnyIO Event（初始未设置）
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
    def __init__(
        self,
        enabled: bool = False,
        timeout_seconds: float = 300,
    ):
        self.enabled = enabled
        self._timeout = timeout_seconds
        self._pending: dict[str, PendingApproval] = {}
        self._lock = anyio.Lock()
        self._ws_manager: WebSocketManager | None = None

    async def wait_for_approval(
        self, ctx: RequestContext,
    ) -> ApprovalResult:
        """提交请求等待审批。阻塞直到审批者决策或超时。"""

        approval = PendingApproval(
            id=f"approval_{uuid4().hex[:12]}",
            request_id=ctx.id,
            payload=ctx.original_payload,
            endpoint=ctx.endpoint,
            model=ctx.resolved_model,
            created_at=time.time(),
            timeout_at=time.time() + self._timeout,
            event=anyio.Event(),
            result=None,
        )

        async with self._lock:
            self._pending[approval.id] = approval

        # WebSocket 广播
        if self._ws_manager:
            await self._ws_manager.broadcast("approval", {
                "type": "approval_requested",
                "approval": approval.to_summary(),
            })

        # 等待审批或超时
        with anyio.move_on_after(self._timeout) as scope:
            await approval.event.wait()
        if scope.cancelled_caught:
            approval.result = ApprovalResult(
                status="rejected",
                reason="Approval timeout",
            )

        # 清理必须放在 finally 等价路径；实现时即使外层 shutdown cancel scope 取消，
        # 也要用短暂 shielded scope 移除 pending，避免泄漏。
        with anyio.CancelScope(shield=True):
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
        self, approval_id: str, modifications: dict,
    ) -> bool:
        """修改 payload 后批准。"""
        async with self._lock:
            approval = self._pending.get(approval_id)
        if not approval:
            return False

        modified_payload = {**approval.payload, **modifications}
        approval.result = ApprovalResult(
            status="approved_with_modifications",
            modified_payload=modified_payload,
            modifications=list(modifications.keys()),
        )
        approval.event.set()
        return True

    async def get_pending(self) -> list[dict]:
        """获取所有待审批请求摘要。"""
        async with self._lock:
            return [a.to_summary() for a in self._pending.values()]

    async def reject_all_pending(self, reason: str) -> int:
        """拒绝所有待审批请求（关闭时调用）。"""
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
    endpoint: str
    model: str
    created_at: float
    timeout_at: float
    event: anyio.Event
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
        return {**self.to_summary(), "payload": self.payload}

@dataclass
class ApprovalResult:
    status: Literal["approved", "rejected", "approved_with_modifications"]
    reason: str = ""
    modified_payload: dict | None = None
    modifications: list[str] | None = None
```

## REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/approval/pending` | GET | 获取所有待审批请求摘要 |
| `/api/approval/:id` | GET | 获取待审批请求详情（含 payload） |
| `/api/approval/:id/approve` | POST | 批准请求 |
| `/api/approval/:id/reject` | POST | 拒绝请求（可选 reason） |
| `/api/approval/:id/modify` | POST | 修改 payload 后批准 |

## WebSocket 事件

通过 `approval` 频道推送。审批的 WebSocket 通道与 [历史系统的 `/history/ws`](history-system.md#websocket-实时推送) 共享同一个 `WebSocketManager`（按频道订阅区分推送内容，不是各自独立的连接管理器实现），两者复用同一套连接生命周期管理、断连清理逻辑。

| 事件 | 说明 |
|------|------|
| `approval_requested` | 新的待审批请求到达 |
| `approval_resolved` | 审批决策完成（approved/rejected） |
| `approval_timeout` | 审批超时（自动拒绝） |

```python
@router.websocket("/api/approval/ws")
async def approval_ws(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
):
    await ws_manager.connect(websocket, "approval")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, "approval")
```

## 与管道集成

在 `pipeline/executor.py` 中（详见 [request-pipeline.md](request-pipeline.md) 的管道阶段与执行流程）：

```python
if approval_gate.enabled:
    ctx.transition("awaiting_approval")
    result = await approval_gate.wait_for_approval(ctx)
    ctx.approval_status = result.status

    if result.status == "rejected":
        ctx.fail(ApiError(type="rejected", message=f"Rejected: {result.reason}"))
        raise RequestRejectedError(result.reason)

    if result.modified_payload:
        payload = result.modified_payload
```

## 配置

配置键与 [config-system.md 的 `approval` section](config-system.md#approval-section-本项目独有-新增) 对齐（`approval.enabled` / `approval.timeout_seconds`）：

```yaml
approval:
  enabled: false           # 是否启用手动审批
  timeout_seconds: 300     # 超时时间（秒），默认 5 分钟
```

CLI 参数：
```
--manual              启用手动审批（映射 approval.enabled=true）
```
审批超时仅通过 config `approval.timeout_seconds`（默认 300）配置，无对应 CLI flag。

## 关闭处理

服务器关闭时，所有待审批请求自动拒绝：

```python
rejected = await approval_gate.reject_all_pending("server shutting down")
logger.info(f"Rejected {rejected} pending approval(s) during shutdown")
```

## 相关文档

- [设计文档总纲](DESIGN.md)
- [请求执行管道](request-pipeline.md)（管道阶段中的审批位置、与重试策略的先后顺序）
- [历史与审计系统](history-system.md#websocket-实时推送)（WebSocket 事件推送，共享同一 `WebSocketManager`）
- [优雅关闭](shutdown.md)（关闭时拒绝所有待审批请求）
- [配置系统](config-system.md#approval-section-本项目独有-新增)（`approval.*` 完整配置键清单）
