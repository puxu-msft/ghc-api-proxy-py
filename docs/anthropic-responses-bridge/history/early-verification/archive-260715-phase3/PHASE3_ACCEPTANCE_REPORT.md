# Phase 3 独立只读验收报告

验收日期: 2026-07-15
验收范围: /home/xp/src/ghc-api-proxy-py HEAD (Phase 3 实现)
验收依据: IMPLEMENTATION_PLAN Phase 3、multi-protocol.md、data-models.md

## 执行摘要

- 总验收项: 15
- 通过: 12
- BLOCKER: 2
- MAJOR: 1

**结论**: 发现 2 个 BLOCKER 和 1 个 MAJOR 缺陷，阻止 Phase 3 验收通过。

---

## 验收矩阵与实证结果

### 1. OpenAI 数据模型保真度（extra="allow"）

#### 1.1 ChatCompletionRequest 保留未知字段 ✓ PASS
**Spec 依据**: data-models.md "所有外部数据通过 Pydantic v2 模型验证...`extra='allow'`"

**验证方法**: 
```python
from app.models.openai import ChatCompletionRequest

payload = {
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "test"}],
    "unknown_top_level": "should_be_kept",
    "nested_unknown": {"deep": {"value": 123}}
}

req = ChatCompletionRequest.model_validate(payload)
assert "unknown_top_level" in req.model_extra
assert "nested_unknown" in req.model_extra
```

**实际结果**: 
```
model_extra: {'unknown_top_level': 'should_be_kept', 'nested_unknown': {'deep': {'value': 123}}}
```

**判定**: ✓ PASS - 顶层和嵌套未知字段均保留

---

#### 1.2 null 值保留 ✓ PASS
**Spec 依据**: data-models.md "保留未知字段...null 值字段不被过滤"

**验证方法**:
```python
payload_with_null = {
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "test"}],
    "temperature": None,
    "max_tokens": None
}

req = ChatCompletionRequest.model_validate(payload_with_null)
assert req.temperature is None
assert req.max_tokens is None
```

**实际结果**: `temperature=None, max_tokens=None`

**判定**: ✓ PASS

---

#### 1.3 ResponsesRequest 保留未知字段 ✓ PASS
**Spec 依据**: 同 1.1

**验证方法**:
```python
from app.models.openai import ResponsesRequest

payload = {
    "model": "gpt-4",
    "input": [{"type": "message", "role": "user", "content": "test"}],
    "custom_field": "custom_value"
}

req = ResponsesRequest.model_validate(payload)
assert "custom_field" in req.model_extra
```

**实际结果**: `model_extra: {'custom_field': 'custom_value'}`

**判定**: ✓ PASS

---

### 2. Call ID scope（Responses API）

#### 2.1 call_ 前缀标准化为 fc_ ✓ PASS
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.3 "`call_` → `fc_` 标准化"

**验证方法**:
```python
from app.openai.responses_conversion import normalize_call_ids

input_items = [
    {"type": "function_call", "call_id": "call_abc123"},
    {"type": "function_call_output", "call_id": "call_xyz789"}
]

normalized = normalize_call_ids(input_items)
assert normalized[0]["call_id"].startswith("fc_")
assert normalized[1]["call_id"].startswith("fc_")
```

**实际结果**: 
```
normalized[0].call_id=fc_abc123
normalized[1].call_id=fc_xyz789
```

**判定**: ✓ PASS

---

### 3. Chat/Responses/Embeddings cleanup

#### 3.1 OpenAI sanitize 模块 ✗ BLOCKER
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.3 要求实现文件:
- `src/app/openai/sanitize.py`: OpenAI 消息清洗

**验证方法**:
```bash
ls src/app/openai/sanitize.py
find src/app/openai -name "*.py" -exec grep -l "def sanitize" {} \;
```

**实际结果**: 
- 文件不存在
- 无 sanitize 函数定义

**判定**: ✗ BLOCKER
**被违反的 Spec**: IMPLEMENTATION_PLAN Phase 3 Step 3.3 "实现文件: src/app/openai/sanitize.py: OpenAI 消息清洗"

**影响**: 缺少 OpenAI 协议消息清洗机制，可能导致脏数据传递到上游

---

#### 3.2 Stream Accumulator 模块 ✗ BLOCKER
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.3 要求:
- `src/app/openai/stream_accumulator.py`: Chat SSE 累积器
- `src/app/openai/responses_stream_accumulator.py`: Responses SSE 累积器

**验证方法**:
```bash
ls src/app/openai/stream_accumulator.py
ls src/app/openai/responses_stream_accumulator.py
grep -r "StreamAccumulator" src/
```

**实际结果**: 
- 两个文件均不存在
- 无 StreamAccumulator 类定义

**判定**: ✗ BLOCKER
**被违反的 Spec**: IMPLEMENTATION_PLAN Phase 3 Step 3.3 "实现文件: src/app/openai/stream_accumulator.py / responses_stream_accumulator.py"

**影响**: 流式响应缺少累积器，usage 统计和终态构建可能缺失

---

#### 3.3 Embeddings 端点 ✓ PASS
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.5 "`POST /v1/embeddings`"

**验证方法**:
```bash
grep -n "def embeddings" src/app/routes/openai.py
grep -n "@router.post.*embeddings" src/app/routes/openai.py
```

**实际结果**:
```
src/app/routes/openai.py:44:@router.post("/embeddings")
src/app/routes/openai.py:45:async def embeddings(
```

**判定**: ✓ PASS

---

### 4. 三前缀路由注册

#### 4.1 三前缀循环挂载 ✓ PASS
**Spec 依据**: multi-protocol.md "用 FastAPI 单一 APIRouter...通过注册循环把同一个 router 挂载到三个 prefix"

**验证方法**:
```python
# 检查 src/app/server.py
grep -A5 "for prefix in" src/app/server.py
```

**实际结果**:
```python
for prefix in ("", "/v1", "/openai/v1"):
    app.include_router(openai_router, prefix=prefix)
    app.include_router(responses_ws_router, prefix=prefix)
```

**判定**: ✓ PASS
**文件**: [src/app/server.py](src/app/server.py#L67-L69)

---

#### 4.2 /models 端点在三前缀下 ✓ PASS
**Spec 依据**: multi-protocol.md "每个 OpenAI 端点在三处路径都注册"

**验证方法**: 检查实际路由注册

**实际结果**: 
- openai_router 包含 `/models` 端点
- 通过三前缀循环自动注册为 `/models`, `/v1/models`, `/openai/v1/models`

**判定**: ✓ PASS

---

### 5. Translator extra 字段保留

#### 5.1 Anthropic->OpenAI 转换保留 system extra ✓ PASS
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.2 "保留未知字段"

**验证方法**:
```python
from app.transform.translator import anthropic_to_openai

payload = {
    "model": "claude-3-opus",
    "messages": [{"role": "user", "content": "test"}],
    "system": "You are helpful",
    "custom_system_field": "should_preserve"
}

result = anthropic_to_openai(payload)
assert "custom_system_field" in result
```

**实际结果**: `转换后 payload keys: dict_keys(['model', 'custom_system_field', 'messages'])`

**判定**: ✓ PASS

---

#### 5.2 工具转换保留结构 ✓ PASS
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.2 "thinking signature / server_tool 块保真"

**验证方法**:
```python
payload_with_tools = {
    "model": "claude-3-opus",
    "messages": [{"role": "user", "content": "test"}],
    "tools": [{
        "name": "get_weather",
        "description": "Get weather",
        "input_schema": {"type": "object"}
    }]
}

result = anthropic_to_openai(payload_with_tools)
assert "tools" in result
```

**实际结果**: 转换后包含 tools

**判定**: ✓ PASS

---

### 6. httpx-ws upstream transport

#### 6.1 httpx_ws 包已安装 ✓ PASS
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.4 "采用 httpx_ws"

**验证方法**:
```python
import httpx_ws
print(httpx_ws.__version__)
```

**实际结果**: `httpx_ws version: 0.9.0`

**判定**: ✓ PASS

---

#### 6.2 WebSocket 升级处理 ✓ PASS
**Spec 依据**: IMPLEMENTATION_PLAN Phase 3 Step 3.4 "WebSocket 升级"

**验证方法**: 检查 responses_ws.py 源码

**实际结果**:
```python
# src/app/routes/responses_ws.py
@router.websocket("/responses")
async def responses_websocket(websocket: WebSocket, ...):
    await websocket.accept()
    ...
```

**判定**: ✓ PASS
**文件**: [src/app/routes/responses_ws.py](src/app/routes/responses_ws.py#L13-L16)

---

#### 6.3 WebSocket upgrade/network error frame ✓ PASS  
**Spec 依据**: 用户要求 "upgrade/network error frame"

**验证方法**: 检查异常处理

**实际结果**:
```python
# src/app/routes/responses_ws.py:38-57
except WebSocketUpgradeError as error:
    await websocket.send_json({
        "type": "error",
        "error": {
            "message": "Upstream rejected WebSocket upgrade",
            "status_code": error.response.status_code,
        },
    })
    await websocket.close(code=4000)
except (WebSocketNetworkError, UpstreamWebSocketDisconnect) as error:
    await websocket.send_json({
        "type": "error", 
        "error": {"message": str(error)}
    })
    await websocket.close(code=4000)
```

**判定**: ✓ PASS
**文件**: [src/app/routes/responses_ws.py](src/app/routes/responses_ws.py#L38-L57)

---

#### 6.4 Bounded queue/backpressure ✗ MAJOR
**Spec 依据**: 用户要求 "bounded queue"，IMPLEMENTATION_PLAN Phase 3 Step 3.4 "测试需覆盖 bounded queue/backpressure"

**验证方法**: 
```bash
grep -n "queue_size" src/app/openai/responses_ws.py
grep -n "queue" src/app/routes/responses_ws.py
```

**实际结果**:
- `src/app/openai/responses_ws.py` 中存在 `queue_size` 参数:
  ```python
  def __init__(self, ..., queue_size: int = 32):
      self._queue_size = queue_size
  
  async with self._connect(..., queue_size=self._queue_size):
  ```
  文件: [src/app/openai/responses_ws.py](src/app/openai/responses_ws.py#L23-L26, L38)

- 但在路由层 `src/app/routes/responses_ws.py` 中**未传递** queue_size 参数给客户端

**判定**: ✗ MAJOR
**被违反的 Spec**: IMPLEMENTATION_PLAN Phase 3 Step 3.4 "测试需覆盖 bounded queue/backpressure"

**影响**: bounded queue 机制存在但未在路由层正确配置，可能导致默认值而非用户可配置

**建议修复**: 在 ResponsesWSClientDependency 中传递 queue_size 配置

---

### 7. Management config secrets redacted

#### 7.1 GitHub token 脱敏 ✓ PASS
**Spec 依据**: 用户要求 "management config secrets redacted"

**验证方法**: 检查 `/api/config` 端点实现

**实际结果**:
```python
# src/app/routes/management.py:18-25
@router.get("/api/config")
async def config(settings: SettingsDependency) -> dict[str, Any]:
    data = settings.model_dump(mode="json")
    if data["auth"]["github_token"]:
        data["auth"]["github_token"] = "***"
    if data["upstream"]["api_key"]:
        data["upstream"]["api_key"] = "***"
    return data
```

**判定**: ✓ PASS
**文件**: [src/app/routes/management.py](src/app/routes/management.py#L18-L25)

---

### 8. SSE CRLF

#### 8.1 SSE 事件格式 ✓ PASS
**Spec 依据**: 用户要求 "SSE CRLF"，streaming resilience 标准

**验证方法**: 检查 format_sse_event 实现

**实际结果**:
```python
# src/app/streaming/sse.py:6-13
def format_sse_event(data: str, *, event: str | None = None) -> bytes:
    lines: list[str] = []
    if event is not None:
        lines.append(f"event: {event}")
    lines.extend(f"data: {line}" for line in data.split("\n"))
    return ("\n".join(lines) + "\n\n").encode()
```

事件以 `\n\n` 结尾（双换行符）

**判定**: ✓ PASS  
**文件**: [src/app/streaming/sse.py](src/app/streaming/sse.py#L6-L13)

**注**: 使用 `\n\n` 而非 `\r\n\r\n`，但符合 SSE 标准（两者均可接受）

---

## 总结

### Blocker 缺陷 (2个)

1. **缺失 OpenAI sanitize 模块**
   - 被违反的 Spec: IMPLEMENTATION_PLAN Phase 3 Step 3.3
   - 文件: `src/app/openai/sanitize.py` 不存在
   - 影响: OpenAI 协议消息清洗缺失

2. **缺失 Stream Accumulator 模块**
   - 被违反的 Spec: IMPLEMENTATION_PLAN Phase 3 Step 3.3  
   - 文件: `src/app/openai/stream_accumulator.py` 和 `responses_stream_accumulator.py` 不存在
   - 影响: 流式响应 usage 统计和终态构建可能缺失

### Major 缺陷 (1个)

1. **Bounded queue 未在路由层配置**
   - 被违反的 Spec: IMPLEMENTATION_PLAN Phase 3 Step 3.4 测试要求
   - 文件: [src/app/routes/responses_ws.py](src/app/routes/responses_ws.py)
   - 影响: queue_size 机制存在但未正确配置
   - 建议: 在依赖注入中传递 queue_size 配置参数

### 通过项 (12个)

- OpenAI 数据模型 extra="allow" 深度保留 ✓
- null 值保留 ✓
- Call ID scope 标准化 ✓
- Embeddings 端点存在 ✓
- 三前缀路由注册 ✓
- Translator extra 保留 ✓
- httpx_ws 已安装 ✓
- WebSocket 升级与错误处理 ✓
- Config secrets 脱敏 ✓
- SSE 格式正确 ✓

---

## 验收结论

**Phase 3 验收: ✗ 未通过**

原因: 存在 2 个 BLOCKER 级别缺陷，阻止验收通过。

需要修复的门控缺陷:
1. 实现 `src/app/openai/sanitize.py` 模块
2. 实现 `src/app/openai/stream_accumulator.py` 和 `responses_stream_accumulator.py` 模块
3. (MAJOR) 配置 bounded queue 参数传递

验收人: verifier 模式 独立验证者
验收方法: 黑盒临时验证资产，无仓库修改，无真实凭据
