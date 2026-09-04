# 多协议适配

> 本文档是**目标设计**（design spec），标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。未特别标注者默认 `[上游稳定][采纳]`。

## 概述

本项目的核心是 OpenAI（Chat Completions / Responses / Embeddings）与 Anthropic（Messages / Count Tokens）两套原生协议实现，参见各自的模块文档。在此之上，`protocols/` 子包提供 **协议适配层**，把 Azure OpenAI 与 Google Gemini 的入站请求格式转换为内部规范，复用核心 pipeline（清洗、审批、限流、执行、重试、历史记录），再把出站响应转换回对应协议的格式。

适配层的统一模式：

```
入站协议特有格式（Azure deployment path / Gemini :method 路径）
    │
    ▼
解析入站请求 → 转为内部规范（OpenAI Chat Completions 或 Anthropic Messages payload）
    │
    ▼
复用核心 pipeline（sanitize → approval → rate limit → execute → retry）
    │
    ▼
核心响应（OpenAI/Anthropic 形状）
    │
    ▼
出站格式转换（转回 Azure/Gemini 形状）→ 返回给调用方
```

这一设计的收益：Azure/Gemini 适配层本身很薄，几乎不含业务逻辑（重试策略、feature negotiation、thinking 管道等）都只需实现一次，在核心协议里维护；适配层只负责“翻译”。

## 三重前缀注册 `[采纳但简化，见 BACKLOG 第 5 条]`

**上游做法**：每个 OpenAI 端点在三处路径都注册，覆盖不同客户端的 base_url 约定：

- 无前缀：`/chat/completions`、`/embeddings`、`/models`、`/responses`
- `/v1` 前缀：`/v1/chat/completions`、`/v1/embeddings`、`/v1/models`、`/v1/responses`
- `/openai/v1` 前缀：`/openai/v1/chat/completions`、`/openai/v1/embeddings`、`/openai/v1/models`、`/openai/v1/responses`

上游（Hono）对三个前缀分别挂载同一组 handler 函数（`handleChatCompletionV4` 等），本身没有重复 handler 代码，但路由注册是三段分散的样板。

**本项目的性能/简洁对策**：用 FastAPI 的单一 `APIRouter` 承载全部 handler，通过一个**注册循环**把同一个 router 挂载到三个 `prefix` 下，避免手写三段重复的 `app.include_router(...)` 调用：

```python
# routes/openai.py
router = APIRouter(tags=["openai"])

@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionsRequest, ...): ...

@router.post("/embeddings")
async def embeddings(request: EmbeddingsRequest, ...): ...

@router.get("/models")
async def list_models(...): ...

@router.get("/models/{model}")
async def get_model(model: str, ...): ...
```

```python
# server.py（应用工厂中）
OPENAI_PREFIXES = ("", "/v1", "/openai/v1")

for prefix in OPENAI_PREFIXES:
    app.include_router(openai_router, prefix=prefix)
```

FastAPI 对同一 `APIRouter` 实例多次 `include_router` 是受支持的用法——每次调用只是在 `app.routes` 上追加新的路由条目，指向**同一个** handler 函数对象，不产生 handler 代码重复，也不产生额外的运行时开销（每条路由仍是 O(1) 的路径匹配注册，不因挂载三次而拖慢请求处理）。`/responses` 端点因同时支持 HTTP POST 与 WebSocket GET，用同样的循环挂载对应的两个 router。

## Azure OpenAI 适配 `[采纳]`

模块：`protocols/azure.py`（转换逻辑）+ `routes/azure.py`（路由）。

### 经典 deployment 格式

```
POST /openai/deployments/:deployment/chat/completions
POST /openai/deployments/:deployment/embeddings
POST /openai/deployments/:deployment/responses
```

**deployment 路径段是权威 model**：Azure OpenAI 的语义是“deployment 名字决定实际调用的模型”，因此：

- 请求体中的 `model` 字段被**忽略**（如果调用方带了，也不作为 override 依据）。
- URL query 中的 `api-version` 参数被**忽略**（本项目不做版本化 API 协商，统一按最新支持的语义处理）。

### 机制：override 在快照原始 payload 之后应用

实现上必须注意应用顺序，否则历史记录会失真：

```python
# protocols/azure.py
async def prepare_azure_request(request: Request, deployment: str) -> AzureAdaptedRequest:
    """从经典 deployment 路径提取 override，但不提前修改 body。"""
    raw_body: dict = await request.json()
    return AzureAdaptedRequest(
        original_payload=raw_body,      # 调用方原样 body，交给 history 记录
        model_override=deployment,       # 仅作为独立的 override 通道
    )
```

```python
# routes/azure.py
@router.post("/deployments/{deployment}/chat/completions")
async def azure_chat_completions(deployment: str, request: Request, ...):
    adapted = await prepare_azure_request(request, deployment)
    # 核心 handler 内部：先用 original_payload 做历史快照，
    # 再用 model_override 覆盖 resolved_model，避免“快照已经是覆盖后的值”
    return await handle_chat_completions(
        payload=adapted.original_payload,
        model_override=adapted.model_override,
        ...
    )
```

**为什么顺序敏感**：如果在路由层直接把 `body["model"] = deployment` 写回请求体，那么后续任何“记录原始请求”的逻辑看到的都已经是覆盖后的值，调用方实际发了什么就无从追溯。保持 `model_override` 作为独立的显式通道，让 history 忠实反映调用方原始意图（`model` 字段是什么，就是什么），同时仍遵守 Azure“路径决定模型”的协议契约——override 只在解析路由、决定实际请求哪个上游模型时生效。

### v1 格式

```
/openai/v1/*
```

直接复用标准 OpenAI 路由（见上文三重前缀注册），无需专门适配——Azure 的 v1 API 层与 OpenAI v1 API 兼容。

## Google Gemini 适配 `[采纳]`

模块：`protocols/gemini.py`（转换逻辑）+ `routes/gemini.py`（路由）。

### 路径解析：`<model>:<method>`

```
POST /v1beta/models/:modelWithMethod
```

其中 `:modelWithMethod` 是形如 `gemini-2.5-pro:generateContent` 的复合段。**按最后一个 `:` 分割**，而非第一个：

```python
def parse_model_with_method(model_with_method: str) -> tuple[str, str]:
    """按最后一个冒号分割 <model>:<method>。

    model id 本身可能合法地包含冒号（如 vendor:family:variant 这类命名），
    但 method 后缀永远是三个已知 token 之一且从不含冒号，所以 rsplit
    （lastIndexOf 的语义）才能正确切分；indexOf/split 用第一个冒号会
    在 model id 含冒号时切错。
    """
    if ":" not in model_with_method:
        raise GeminiPathError(
            f'Invalid path "{model_with_method}": expected <model>:<method>'
        )
    model_id, _, method = model_with_method.rpartition(":")
    return model_id, method
```

`method` 分派表：

| method | 语义 | 对应 handler |
|--------|------|-------------|
| `generateContent` | 非流式生成 | `handle_generate_content` |
| `streamGenerateContent` | 流式生成（SSE） | `handle_stream_generate_content` |
| `countTokens` | Token 计数 | `handle_count_tokens` |

其他 method → 返回 Gemini 形状的 404：

```python
{
    "error": {
        "code": 404,
        "message": f'Method "{method}" is not implemented',
        "status": "NOT_FOUND",
    }
}
```

### 请求/响应格式转换

Gemini 的请求体（`GenerateContentRequest`）与内部规范（OpenAI Chat Completions payload）之间的核心映射：

| Gemini 字段 | 内部规范字段 | 说明 |
|-------------|-------------|------|
| `contents[].parts[]` | `messages[].content` | Gemini 用 `parts` 数组承载多模态内容片段，映射为 OpenAI 的 content blocks |
| `contents[].role`（`user`/`model`） | `messages[].role`（`user`/`assistant`） | `model` ↔ `assistant` 角色名互译 |
| `systemInstruction` | `messages[]` 中的 `system` 消息 | Gemini 系统指令独立字段，映射为首条 system 消息 |
| `generationConfig.temperature` / `topP` / `topK` / `maxOutputTokens` | `temperature` / `top_p` / （无直接对应） / `max_tokens` | 参数级映射；Gemini 特有的 `topK` 无 OpenAI 对应项，透传到 provider 特定扩展字段或丢弃（视上游支持而定） |
| `tools[].functionDeclarations[]` | `tools[].function` | Function calling 声明格式互译 |
| `safetySettings` | （无对应，本项目上游为 Copilot，不透传） | 忽略 |

Pydantic 模型定义详见 [data-models.md](data-models.md) 的 Gemini 模型章节（`models/gemini.py`）。转换函数（`protocols/gemini.py`）：

```python
def convert_gemini_request_to_openai(
    body: GenerateContentRequest, *, model: str, stream: bool,
) -> ChatCompletionsPayload:
    """Gemini GenerateContentRequest → 内部 OpenAI Chat Completions payload。"""
    ...

def convert_openai_response_to_gemini(
    chat: ChatCompletionResponse, model_id: str,
) -> GenerateContentResponse:
    """内部 OpenAI 响应 → Gemini GenerateContentResponse。"""
    ...
```

### 流式 streamGenerateContent 的 SSE 处理

流式路径按帧（per-frame）把内部 OpenAI SSE 事件翻译为 Gemini 帧，逐帧写出，不整体缓冲（遵循 [DESIGN.md](DESIGN.md#性能设计原则第一优先级) P6 的零缓冲直通原则）：

```python
async def pump_gemini_stream(
    upstream_stream: AsyncIterator[bytes], ctx: RequestContext,
) -> AsyncIterator[str]:
    """逐帧翻译 OpenAI SSE → Gemini SSE 帧，零整体缓冲。"""
    async for openai_event in parse_openai_sse(upstream_stream):
        gemini_frame = translate_openai_event_to_gemini(openai_event)
        if gemini_frame is not None:
            yield format_gemini_sse(gemini_frame)
    # 终态帧：finishReason + usageMetadata，从累积器（stream_accumulator）读取，
    # 不重新拉取上游或重算——沿用核心 SSE 累积器的旁路记账（见 request-pipeline.md）
```

Gemini 协议本身**没有** `[DONE]` 哨兵帧、也没有 keepalive/heartbeat 机制（这是 Anthropic/OpenAI SSE 才有的约定），因此 Gemini 流式路径不需要接入 [streaming-resilience.md](streaming-resilience.md) 的 keepalive 心跳；idle timeout 仍然生效（跨协议共享同一套流空闲检测）。

## 模型列表两种格式

- OpenAI 标准格式（`GET /models`、`/v1/models`、`/openai/v1/models`）：`id` / `object` / `created` / `owned_by` 四个基线字段，附加 Copilot 能力元数据作为扩展字段（符合 spec 的客户端忽略未知字段）。
- Anthropic 格式（`GET /anthropic/v1/models`）：过滤 `vendor == "Anthropic"`，返回 Anthropic SDK 的 `ModelInfo` 形状，使 Anthropic SDK 客户端指向 `.../anthropic` 时 `client.models.list()` 可直接解码。

Gemini **本身不提供独立的模型列表端点**（上游也没有实现，`/v1beta/models` GET 未注册）；Gemini 客户端如需模型目录，走 `/api/models`（内部完整格式）或标准 OpenAI `/v1/models`。

两种格式的解析、别名、Override 详见 [model-resolution.md](model-resolution.md)。

## wire format 错误检测

FastAPI 全局异常处理器（等价于 Starlette 的 exception handler）需要按**请求路径**决定返回哪种协议形状的错误体，因为客户端 SDK 只能解析自己协议约定的错误信封：

```python
def detect_error_wire_format(path: str) -> Literal["gemini", "openai", "anthropic"]:
    """按路径前缀匹配错误 wire format；默认 anthropic（覆盖 /v1/messages 及未匹配到
    具体协议前缀的路由——保证未处理异常也能产生协议正确的错误信封）。
    """
    if path.startswith("/v1beta"):
        return "gemini"
    openai_prefixes = (
        "/chat/completions", "/v1/chat/completions", "/openai",
        "/responses", "/v1/responses", "/embeddings", "/v1/embeddings",
    )
    if any(path.startswith(p) for p in openai_prefixes):
        return "openai"
    return "anthropic"
```

```python
@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception) -> Response:
    if request.headers.get("upgrade", "").lower() == "websocket":
        # WebSocket 已升级，无法再发送 HTTP 响应；连接已断开是正常情况（客户端断连），
        # 仅 debug 级别记录，不视为异常
        logger.debug("WebSocket error: %s", exc)
        return Response(status_code=500)

    logger.error("Unhandled route error in %s %s: %s", request.method, request.url.path, exc)
    wire_format = detect_error_wire_format(request.url.path)
    return format_error_response(exc, wire_format=wire_format)
```

### unknown endpoint 处理

对未命中任何路由的请求，分三类处理，避免把常见的浏览器噪音探针误记为“可疑的未知端点”：

1. **浏览器探针**（`/favicon.ico`、`/.well-known/appspecific/com.chrome.devtools.json`）：静默返回 `204 No Content`，不进入日志/告警管线。
2. **method-not-allowed**：路径存在但方法不匹配（如对 `/v1/messages` 发 `GET`）→ `405 Method Not Allowed`，`Allow` 响应头列出该路径实际支持的方法集合。
3. **unknown-not-found**：路径本身未注册 → `404 Not Found`。

```python
BROWSER_PROBE_PATHS = frozenset({
    "/favicon.ico",
    "/.well-known/appspecific/com.chrome.devtools.json",
})

async def not_found_handler(request: Request) -> Response:
    if request.url.path in BROWSER_PROBE_PATHS:
        return Response(status_code=204)

    classification = classify_unknown_endpoint(
        app_route_table, request.method, request.url.path,
    )
    if classification.kind == "method-not-allowed":
        log_unknown_endpoint(classification, request)
        return JSONResponse(
            {"error": "Method Not Allowed"},
            status_code=405,
            headers={"Allow": ", ".join(classification.allow)},
        )
    if classification.kind == "unknown-not-found":
        log_unknown_endpoint(classification, request)
    return JSONResponse({"error": "Not Found"}, status_code=404)
```

日志级别由顶层配置 section `unknown_endpoint_logging`（见 [config-system.md](config-system.md#unknown_endpoint_logging-section)）控制，区分 `not_found` 和 `method_not_allowed` 两档，各自可设为 `silent`/`debug`/`info`/`warn`/`error`，避免误配置的客户端反复触发未知端点探测时刷屏。

## 相关文档

- [设计文档总纲](DESIGN.md)
- [模型解析](model-resolution.md)（模型格式、别名、Family Override）
- [数据模型](data-models.md)（各协议 Pydantic 模型，含 Gemini）
- [流式处理](streaming.md)（SSE 直通机制，Gemini 流式路径复用）
- [请求执行管道](request-pipeline.md)（核心 pipeline，Azure/Gemini 复用）
- [BACKLOG](BACKLOG.md#5-三重前缀路由注册采纳但简化)（三重前缀注册的性能取舍）
