# PoC 结论：openai==2.21.0 `AsyncOpenAI` 底层 client.post 直通上游 SSE 原始字节

## 假设

用 `openai==2.21.0` 的 `AsyncOpenAI` 实例发上游请求时，能否绕开高层 `.chat.completions.create(stream=True)` 的 typed 事件解析，直接从底层 `client.post(...)` 拿到上游 SSE 响应的**原始字节流**逐块转发（零缓冲直通），同时仍复用该 SDK 实例的 base_url / 鉴权 header / 超时 / 连接池 / 重试配置。

## 判据

1. 能拿到 `httpx.Response`（未被 pydantic 解析、未被 SDK 的 `Stream`/`AsyncStream` 包装）。
2. 能注入任意自定义 header（`Copilot-Integration-Id`、`editor-version`、`X-Initiator`、`Openai-Intent`）与任意扩展 body 字段，且不被吞掉。
3. 字节流逐块到达（不是内部先聚合完再一次性吐出）。

## 方法

- 本地 mock 上游：`mock_server.py`（FastAPI + uvicorn），对 `POST /chat/completions` 返回 SSE，先回显一条 echo 事件（服务器实际收到的 header/body），再每隔 0.4 秒吐一个 `data: {...}` chunk，最后吐 `data: [DONE]`（无延迟）。
- 客户端：`poc_passthrough.py`，用同一个 `AsyncOpenAI(base_url=..., timeout=..., max_retries=...)` 实例调用底层 `client.post(...)`，逐块 `async for chunk in resp.aiter_bytes()` 打印时间戳并断言。

## 关键 API 形状（读源码 + 实测确认，`openai==2.21.0`）

`AsyncOpenAI` 继承自 `AsyncAPIClient`（`_base_client.py`），其 `post` 方法签名（节选，`_base_client.py:1858`）：

```python
async def post(
    self,
    path: str,
    *,
    cast_to: Type[ResponseT],
    body: Body | None = None,
    content: AsyncBinaryTypes | None = None,
    files: RequestFiles | None = None,
    options: RequestOptions = {},
    stream: bool = False,
    stream_cls: type[_AsyncStreamT] | None = None,
) -> ResponseT | _AsyncStreamT
```

拿原始字节的**关键点**是 `cast_to=httpx.Response`。在 `_process_response`（`_base_client.py:1697` 起）里有明确的短路分支：

```python
if cast_to == httpx.Response:
    return cast(ResponseT, response)
```

即只要 `cast_to` 精确等于 `httpx.Response` 类型本身，SDK 会直接把底层 `httpx.Response` 对象原样返回，**完全跳过** pydantic 校验/解析，也不会进入 `Stream`/`AsyncStream` 的 SSE 事件切分逻辑（那是 `.chat.completions.create(stream=True)` 走的 `stream_cls=Stream[ChatCompletionChunk]` 路径）。

同时把 `stream=True` 传给 `post`，它会一路透传到 `_base_client.py:1606` 的：

```python
response = await self._client.send(request, stream=stream or self._should_stream_response_body(request=request), **kwargs)
```

`self._client` 就是这个 `AsyncOpenAI` 实例内部持有的 `httpx.AsyncClient`（同一个连接池、同一个 base_url、同一个默认 header/鉴权、同一套 timeout 配置），`stream=True` 让 `httpx` 不预读 body，此时函数返回的 `httpx.Response` 是"惰性"的，`resp.is_stream_consumed == False`，可以用 `resp.aiter_bytes()` 逐块拉取。

### 能跑通的最小代码

```python
import httpx
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=KEY, base_url=BASE_URL, timeout=30.0)

resp: httpx.Response = await client.post(
    "/chat/completions",
    cast_to=httpx.Response,           # <- 关键：跳过 pydantic 解析，拿原始 httpx.Response
    body={"model": "...", "messages": [...], "stream": True, **extra_fields},
    options={"headers": {                # <- 自定义 header，走 RequestOptions["headers"]，
        "Copilot-Integration-Id": "vscode-chat",   #   会与 SDK 默认 header 合并（不覆盖鉴权）
        "editor-version": "vscode/1.99.0",
        "X-Initiator": "user",
        "Openai-Intent": "conversation-panel",
    }},
    stream=True,                        # <- 关键：底层 httpx.AsyncClient.send(..., stream=True)
)

async for chunk in resp.aiter_bytes():  # 原始字节，逐块到达，未做任何 SSE/JSON 解析
    await forward_to_downstream(chunk)

await resp.aclose()
```

## 实测结果（真实运行，2026-07-15）

命令：`uv run python exp/upstream-sdk-passthrough/poc_passthrough.py`（先在后台起 `uv run python exp/upstream-sdk-passthrough/mock_server.py`）。

关键输出：

```
[t= 0.028s] got httpx.Response object, status=200
[t= 0.028s] response.is_stream_consumed = False
[t= 0.028s] raw chunk (408 bytes): b'data: {"type": "echo", "headers": {"authorization": "Bearer sk-mock-does-not-matter", "copilot-integration-id": "vscode-chat", "editor-version": "vscode/1.99.0", "x-initiator": "user", "openai-intent": "conversation-panel", "user-agent": "AsyncOpenAI/Python 2.21.0"}, "body": {"model": "gpt-4o-mock", "messages": [{"role": "user", "content": "hi"}], "stream": true, "x_client_extra_field": {"foo": "bar"}}}\n\n'
[t= 0.429s] raw chunk (83 bytes): b'data: {"type": "chunk", "index": 0, ...}\n\n'
[t= 0.831s] raw chunk (83 bytes): b'data: {"type": "chunk", "index": 1, ...}\n\n'
[t= 1.232s] raw chunk (83 bytes): b'data: {"type": "chunk", "index": 2, ...}\n\n'
[t= 1.636s] raw chunk (83 bytes): b'data: {"type": "chunk", "index": 3, ...}\n\n'
[t= 2.034s] raw chunk (83 bytes): b'data: {"type": "chunk", "index": 4, ...}\n\n'
[t= 2.034s] raw chunk (14 bytes): b'data: [DONE]\n\n'

--- Inter-chunk deltas (s) ---
[0.4012724060000892, 0.40157838599998286, 0.4016052810000019, 0.4042357099999663, 0.3979123990000062, 4.55010000450784e-05]

ALL ASSERTIONS PASSED: raw SSE bytes passthrough via client.post(cast_to=httpx.Response, stream=True) works,
custom headers + extra body fields survive, chunks are delivered incrementally (no buffering).
```

逐判据核对：

1. **拿到原始 `httpx.Response`，未被解析** —— `type(resp) is httpx.Response`；`resp.is_stream_consumed == False`（返回时 body 尚未读取，证明不是先聚合完再返回）。通过。
2. **自定义 header 与扩展 body 字段完整透传** —— 服务器端实际收到的 header 里 `copilot-integration-id` / `editor-version` / `x-initiator` / `openai-intent` 均与客户端所设一致，且 SDK 默认注入的 `authorization`（`Bearer sk-mock-...`）、`user-agent`（`AsyncOpenAI/Python 2.21.0`）也共存不冲突。请求体里非标字段 `x_client_extra_field` 原样到达服务器。通过。
3. **逐块无缓冲** —— 相邻 chunk 到达时间差稳定在约 0.4 秒（对应 mock 服务端人为设置的发送间隔），而不是全部在 ~2 秒时刻同时出现；`resp.is_stream_consumed` 在拿到响应对象的那一刻为 `False`。通过。

## 环境记录

- `openai==2.21.0`，Python 3.14.2（`uv` 自动下载解释器并建 `.venv`，构建过程顺利，无兼容性问题）。
- `fastapi==0.129.0` + `uvicorn==0.40.0`（项目既有依赖）用作 mock 上游，未额外引入新依赖。
- 未使用真实 Copilot 凭据，全程针对本地 mock server。

## 结论

**可行。** `openai==2.21.0` 的 `AsyncOpenAI` 支持通过 `client.post(path, cast_to=httpx.Response, body=..., options={"headers": ...}, stream=True)` 拿到裸 `httpx.Response`，逐块 `aiter_bytes()` 即为上游 SSE 的原始字节，不经过任何 pydantic/事件解析；同时完整复用该实例的 `base_url`、默认鉴权 header、超时、连接池（因为走的就是实例内部同一个 `httpx.AsyncClient`），并可自由附加任意自定义 header 和任意扩展 body 字段。三条判据均以真实运行结果验证通过。

### 需要注意的边界/风险（供正式实现参考）

- **重试语义**：`AsyncOpenAI` 的内建重试（`max_retries`）只在拿到响应/发生异常**之前**生效（`_base_client.py` 的 for 循环在 `_client.send()` 之前）；一旦进入流式阶段（拿到 `httpx.Response` 并开始 `aiter_bytes()`），SDK 层不会在传输中途自动重试。这与裸 `httpx.AsyncClient` 直接调用完全一致——重试仅覆盖"建立连接/收到响应头"这一步，不覆盖"流式传输中断"。如果代理需要在流传输中途断线重连，需要在代理自己的转发层处理，与是否用 SDK 无关。
- **`options={"headers": ...}` 的合并语义**：额外 header 与 SDK 默认 header（`Authorization`、`User-Agent` 等）是合并而非整体替换，实测未出现覆盖 `Authorization` 的问题；如需覆盖默认值（例如自定义 `User-Agent`），同名 key 会覆盖默认值（未在本次 PoC 中单独测试覆盖场景，如有需要可另行验证，但源码 `_build_request` 中 header 合并逻辑是标准的"默认值 + 显式值覆盖"）。
- **`body` 走 `json_data`**：`client.post(..., body=...)` 内部对应 `FinalRequestOptions.json_data`，最终由 httpx 做 JSON 序列化再发送；这意味着扩展字段必须是 JSON 可序列化的普通 dict/list/标量，不能塞 Pydantic 模型实例（除非自己先 `model_dump()`）。
- **`cast_to` 必须精确等于 `httpx.Response` 这个类型对象**（不是字符串、不是子类，是 `is`/`==` 比较，见 `_base_client.py:1748`），否则会掉进 `AsyncAPIResponse(...).parse()` 分支重新触发 JSON/pydantic 解析。
- **`with_streaming_response` / `with_raw_response`** 是另一套封装（`AsyncOpenAIWithStreamedResponse`），基于设置 `RAW_RESPONSE_HEADER` 私有 header 实现，行为上是本 PoC 方案的"包装版"，但没有暴露自由拼接任意 path/body/headers 的灵活度，不如直接调 `client.post(cast_to=httpx.Response, ...)` 直观可控，**不推荐**作为代理场景的首选。

**因此不需要退回裸 `httpx.AsyncClient`**：用 `AsyncOpenAI.post(cast_to=httpx.Response, stream=True)` 这条路径，既能保真直通字节流，又能复用 SDK 的鉴权/连接池/超时配置，是本项目上游转发层的推荐实现方式。

## 产物

- `exp/upstream-sdk-passthrough/mock_server.py` —— 本地 mock SSE 上游（FastAPI + uvicorn）。
- `exp/upstream-sdk-passthrough/poc_passthrough.py` —— 实测脚本（含全部判据断言）。
- 运行方式：先 `uv run python exp/upstream-sdk-passthrough/mock_server.py &`，再 `uv run python exp/upstream-sdk-passthrough/poc_passthrough.py`。
