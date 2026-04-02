# 历史与审计系统

## 概述

历史系统（`history/`）提供所有 API 请求的完整审计记录，包括请求内容、响应内容、耗时、token 用量、管道处理详情。支持查询、统计、导出和 WebSocket 实时推送。

## HistoryStore 设计

### 数据结构

使用 `OrderedDict` 保持插入顺序，支持 O(1) 查找和 FIFO 淘汰：

```python
class HistoryStore:
    def __init__(self, max_entries: int = 200):
        self._max_entries = max_entries
        self._entries: OrderedDict[str, HistoryEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._ws_manager: WebSocketManager | None = None

        # 统计缓存
        self._stats = HistoryStats()
```

### 并发安全

所有写操作通过 `asyncio.Lock` 保护。由于 Python GIL + asyncio 单线程模型，读操作在不涉及 await 的情况下不需要锁，但为一致性起见，写操作统一加锁：

```python
async def add_entry(self, entry: HistoryEntry) -> None:
    async with self._lock:
        # FIFO 淘汰
        while len(self._entries) >= self._max_entries:
            evicted_id, evicted = self._entries.popitem(last=False)
            self._stats.subtract(evicted)

        self._entries[entry.id] = entry
        self._stats.add(entry)

    # 广播（在锁外执行）
    if self._ws_manager:
        await self._ws_manager.broadcast("history", {
            "type": "entry_added",
            "entry": entry.to_summary(),
        })

async def update_entry(self, entry_id: str, response: ResponseData) -> None:
    async with self._lock:
        entry = self._entries.get(entry_id)
        if entry:
            entry.response = response
            entry.completed_at = time.time()
            entry.status = "success"
            self._stats.update(entry)

    if self._ws_manager:
        await self._ws_manager.broadcast("history", {
            "type": "entry_updated",
            "entry": entry.to_summary() if entry else None,
        })
```

### FIFO 淘汰

当存储条目达到 `max_entries` 上限时，移除最旧的条目：

```
添加新条目
    │
    ├─ len < max_entries → 直接添加
    │
    └─ len >= max_entries
         │
         ├─ OrderedDict.popitem(last=False) → 移除最旧
         ├─ 从统计缓存减去被移除条目
         └─ 添加新条目
```

## HistoryEntry 数据结构

```python
@dataclass
class HistoryEntry:
    id: str                              # 请求 ID (uuid4)
    timestamp: float                     # 创建时间 (time.time())
    completed_at: float | None           # 完成时间
    endpoint: Literal["openai-chat-completions", "openai-responses", "anthropic-messages"]
    status: Literal["pending", "streaming", "success", "error"]

    # 请求信息
    model: str                           # 解析后的模型名
    original_model: str                  # 原始模型名
    request_payload: dict                # 完整请求体

    # 响应信息
    response: ResponseData | None

    # 管道处理详情
    pipeline: PipelineDetails

    # 计算属性
    @property
    def duration_ms(self) -> float | None:
        if self.completed_at:
            return (self.completed_at - self.timestamp) * 1000
        return None

    def to_summary(self) -> dict:
        """摘要信息（不含完整 payload/response）。"""
        messages = self.request_payload.get("messages", [])
        return {
            "id": self.id,
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "endpoint": self.endpoint,
            "model": self.model,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "usage": self.response.usage.to_dict() if self.response and self.response.usage else None,
            "request_summary": {
                "message_count": len(messages),
                "has_tools": bool(self.request_payload.get("tools")),
                "has_system": bool(self.request_payload.get("system") or
                    any(m.get("role") == "system" for m in messages)),
                "stream": self.request_payload.get("stream", False),
            },
            "response_summary": self.response.to_summary() if self.response else None,
        }

    def to_detail(self) -> dict:
        """完整详情（含 payload 和 response）。"""
        return {
            **self.to_summary(),
            "original_model": self.original_model,
            "request": self.request_payload,
            "response": self.response.to_dict() if self.response else None,
            "pipeline": self.pipeline.to_dict(),
        }

@dataclass
class ResponseData:
    content: list[dict] | str | None     # Anthropic content blocks 或 OpenAI content string
    stop_reason: str | None
    usage: Usage | None
    tool_calls: list[dict] | None

    def to_summary(self) -> dict:
        if isinstance(self.content, list):
            return {
                "content_block_count": len(self.content),
                "stop_reason": self.stop_reason,
            }
        return {
            "content_length": len(self.content) if self.content else 0,
            "stop_reason": self.stop_reason,
            "has_tool_calls": bool(self.tool_calls),
        }

    def to_dict(self) -> dict: ...

@dataclass
class PipelineDetails:
    attempts: int
    total_duration_ms: float
    sanitization: SanitizationResult | None
    model_resolved_from: str
    model_resolved_to: str
    format_translated: bool
    approval_status: str | None          # approved / rejected / approved_with_modifications / None
    rate_limiter_wait_ms: float
    retry_strategies_applied: list[str]  # 应用过的重试策略名称

    def to_dict(self) -> dict: ...
```

## 查询

### 过滤器

```python
@dataclass
class HistoryQuery:
    limit: int = 50
    offset: int = 0
    model: str | None = None
    endpoint: str | None = None          # "openai-chat-completions" | "openai-responses" | "anthropic-messages"
    status: str | None = None            # "success" | "error" | "pending"
    since: float | None = None           # Unix timestamp
    until: float | None = None           # Unix timestamp
    search: str | None = None            # 全文搜索关键词
```

### 查询逻辑

```python
async def query(self, q: HistoryQuery) -> tuple[list[dict], int]:
    """
    查询历史记录。

    返回: (条目摘要列表, 总匹配数)
    """
    results = []
    total = 0

    for entry in reversed(self._entries.values()):  # 最新在前
        if not self._matches(entry, q):
            continue
        total += 1
        if total > q.offset and len(results) < q.limit:
            results.append(entry.to_summary())

    return results, total

def _matches(self, entry: HistoryEntry, q: HistoryQuery) -> bool:
    """检查条目是否匹配查询条件。"""
    if q.model and entry.model != q.model:
        return False
    if q.endpoint and entry.endpoint != q.endpoint:
        return False
    if q.status and entry.status != q.status:
        return False
    if q.since and entry.timestamp < q.since:
        return False
    if q.until and entry.timestamp > q.until:
        return False
    if q.search:
        return self._text_search(entry, q.search)
    return True

def _text_search(self, entry: HistoryEntry, keyword: str) -> bool:
    """简单全文搜索：检查消息内容是否包含关键词。"""
    keyword_lower = keyword.lower()
    for msg in entry.request_payload.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str) and keyword_lower in content.lower():
            return True
        if isinstance(content, list):
            for block in content:
                text = block.get("text", "")
                if keyword_lower in text.lower():
                    return True
    return False
```

## 统计

### HistoryStats 缓存

为避免每次请求统计时遍历所有条目，使用增量更新的缓存：

```python
@dataclass
class HistoryStats:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    by_model: dict[str, ModelStats] = field(default_factory=dict)
    by_endpoint: dict[str, int] = field(default_factory=lambda: {"openai-chat-completions": 0, "openai-responses": 0, "anthropic-messages": 0})
    durations: list[float] = field(default_factory=list)  # 用于 p95 计算

    def add(self, entry: HistoryEntry) -> None:
        """添加条目到统计。"""
        self.total_requests += 1
        if entry.status == "success":
            self.successful_requests += 1
        elif entry.status == "error":
            self.failed_requests += 1

        self.by_endpoint[entry.endpoint] = self.by_endpoint.get(entry.endpoint, 0) + 1

        if entry.model not in self.by_model:
            self.by_model[entry.model] = ModelStats()
        self.by_model[entry.model].count += 1

    def update(self, entry: HistoryEntry) -> None:
        """条目完成时更新统计。"""
        if entry.response and entry.response.usage:
            usage = entry.response.usage
            self.total_input_tokens += usage.input_tokens
            self.total_output_tokens += usage.output_tokens

            model_stats = self.by_model.get(entry.model)
            if model_stats:
                model_stats.input_tokens += usage.input_tokens
                model_stats.output_tokens += usage.output_tokens

        if entry.duration_ms is not None:
            self.durations.append(entry.duration_ms)

    def subtract(self, entry: HistoryEntry) -> None:
        """移除条目时从统计减去（FIFO 淘汰）。"""
        self.total_requests -= 1
        if entry.status == "success":
            self.successful_requests -= 1
        elif entry.status == "error":
            self.failed_requests -= 1
        # ... 减去 tokens、model stats 等

    def to_dict(self) -> dict:
        durations = sorted(self.durations) if self.durations else []
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "by_model": {k: v.to_dict() for k, v in self.by_model.items()},
            "by_endpoint": self.by_endpoint,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "p95_duration_ms": durations[int(len(durations) * 0.95)] if durations else 0,
        }

@dataclass
class ModelStats:
    count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
```

## 导出

JSON 流式导出，避免一次性加载所有条目到内存：

```python
async def export_entries(
    self,
    q: HistoryQuery | None = None,
) -> AsyncIterator[str]:
    """流式导出历史记录为 JSON 数组。"""
    yield "["
    first = True
    for entry in reversed(self._entries.values()):
        if q and not self._matches(entry, q):
            continue
        if not first:
            yield ","
        yield json.dumps(entry.to_detail())
        first = False
    yield "]"
```

## WebSocket 管理器 (ws.py)

### 连接管理

```python
class WebSocketManager:
    """管理 WebSocket 连接并广播消息。"""

    def __init__(self):
        # 按频道分组的连接集合
        self._connections: dict[str, set[WebSocket]] = {
            "history": set(),
            "approval": set(),
        }
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """接受 WebSocket 连接并加入频道。"""
        await websocket.accept()
        async with self._lock:
            self._connections[channel].add(websocket)

    async def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """移除 WebSocket 连接。"""
        async with self._lock:
            self._connections[channel].discard(websocket)

    async def broadcast(self, channel: str, message: dict) -> None:
        """向频道内所有连接广播消息。"""
        async with self._lock:
            connections = list(self._connections.get(channel, set()))

        disconnected = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        # 清理断开的连接
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._connections[channel].discard(ws)
```

### 频道

| 频道 | 事件类型 | 用途 |
|------|----------|------|
| `history` | `entry_added` | 新请求记录添加 |
| `history` | `entry_updated` | 请求完成（含响应） |
| `history` | `stats_updated` | 统计数据更新 |
| `approval` | `approval_requested` | 新的待审批请求 |
| `approval` | `approval_resolved` | 审批决策完成 |
| `approval` | `approval_timeout` | 审批超时 |

### 路由中的 WebSocket 处理

```python
# routes/history.py

@router.websocket("/api/history/ws")
async def history_ws(
    websocket: WebSocket,
    ws_manager: WebSocketManager = Depends(get_ws_manager),
):
    await ws_manager.connect(websocket, "history")
    try:
        while True:
            # 保持连接，等待客户端关闭
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, "history")

# routes/approval.py

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

在 `pipeline/executor.py` 执行完成后记录历史：

```python
# 请求开始时创建条目
history_entry = HistoryEntry(
    id=ctx.id,
    timestamp=ctx.created_at,
    endpoint=ctx.endpoint,
    status="pending",
    model=ctx.resolved_model,
    original_model=ctx.original_model,
    request_payload=ctx.original_payload,
    response=None,
    pipeline=PipelineDetails(...),
)
await history_store.add_entry(history_entry)

# 流式响应完成后更新
# （通过累积器拿到完整响应后）
await history_store.update_entry(ctx.id, response_data)
```

## 配置

```yaml
history:
  max_entries: 200       # 最大存储条目数
  websocket: true        # 是否启用 WebSocket 推送
```

## 相关文档

- [整体架构概览](architecture.md)
- [API 端点规格](api-endpoints.md)（历史 API 详情）
- [流式处理](streaming.md)（流式累积器）
- [配置系统](config-system.md)
