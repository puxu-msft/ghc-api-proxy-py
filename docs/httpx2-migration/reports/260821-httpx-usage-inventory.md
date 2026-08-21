# 本仓库 httpx 使用面清单（为迁移到 httpx2 而做的盘点）

盘点时间：2026-08-21。盘点范围：`src/` 与 `tests/`（`exp/`、`verification/`、`contrib/` 单列在 §8，不属于迁移必经面）。
**本文档只做盘点，未修改任何代码。** 所有行号对应盘点时的工作树状态。

> **与 `docs/tmp/260821-httpx2-ecosystem-compat.md` 的分工**（该文件同日 11:54 由并行会话产出）：那一份是**外部生态侧的实测调研** —— `openai` 3.3.1 / `anthropic` 1.0.0 的 `http_client=` 合同、`httpx-ws==0.9.0` 的兼容性与替代方案、OTel 插桩是否失效、双栈共存是否可行，均带探针证据。
> **本文档是仓库内部使用面的清单，不是生态结论的来源。** 凡涉及「httpx2 那边会怎样」的判断（本文 §9 的风险 1、4、6），**以那一份为准**；本文只负责说清楚「我们这边有哪些点会被打到、在哪一行」。两份如有冲突，生态侧结论优先。

## 0. 当前依赖现状（实测，非推断）

`.venv` 中实测安装版本：

| 包 | 版本 | 对 httpx 的依赖声明 |
|---|---|---|
| `httpx` | 0.28.1 | — |
| `httpcore` | 1.0.9 | — |
| `httpx-ws` | 0.9.0 | `httpx>=0.23.1`、`httpcore>=1.0.4` |
| `openai` | 2.21.0 | `httpx<1,>=0.23.0` |
| `anthropic` | 0.79.0 | `httpx<1,>=0.25.0` |
| `opentelemetry-instrumentation-httpx` | 0.60b1 | `httpx>=0.18.0`（extra `instruments`） |
| `h2` | 4.3.0 | — |
| `socksio` | 1.0.0 | — |
| `httpx2` | **未安装** | — |

`pyproject.toml:16-17,22` 声明：

```toml
    "httpx[http2,socks]",
    "httpx-ws",
    ...
    "opentelemetry-instrumentation-httpx",
```

注意 `httpx[http2,socks]` 的两个 extra 是**当前 composition root 真正依赖的能力**（HTTP/2 与 SOCKS 代理），迁移时必须确认 `httpx2` 的 extra 名称与可用性。

规模量级（实测计数）：`src/` 有 29 个文件出现 `httpx.`，合计 119 处符号引用；`tests/` 有 39 个文件、554 处。其中 `httpx.Response` 一项就占 src 70 处、tests 302 处 —— 绝大多数是**类型标注与构造**，属于机械替换面。

---

## 1. import 位置清单（按用途聚类）

### 1.1 `src/` —— 按用途分组

#### A. 连接层构建与传输层改造（迁移的真正核心，4 个文件）

| 文件:行号 | import 形态 |
|---|---|
| `src/app/server/composition.py:13-14,16-18` | `import httpcore` / `import httpx` / `from httpcore._async.http_proxy import AsyncForwardHTTPConnection, AsyncTunnelHTTPConnection` / `from httpcore._async.interfaces import AsyncConnectionInterface` / `from httpx._utils import get_environment_proxies` |
| `src/app/upstream/stream_cap.py:21-22` | `import httpx` / `from httpcore import AsyncConnectionInterface, Origin, Request, Response` |
| `src/app/upstream/client.py:3` | `import httpx`（旧的 `create_http_client`，`Limits` + `Timeout`） |
| `src/app/auth/service.py:5` | `import httpx`（device flow 自建一次性 client） |

#### B. 错误分类与异常映射（3 个文件）

| 文件:行号 | 用途 |
|---|---|
| `src/app/ghc_client/transport.py:1` | pre-header 可重试错误集合 |
| `src/app/ghc_client/errors.py:21` | `_CONNECTION_ERRORS` 归一化表 |
| `src/app/ghc_client/tokens.py:8` | `httpx.HTTPError` / `httpx.HTTPStatusError` 捕获 + `httpx.Headers` 构造 |

#### C. 作为公共接口类型：`httpx.Response` 出现在 Protocol / 方法签名（13 个文件）

`src/app/upstream/base.py:4`、`src/app/upstream/generic.py:4`、`src/app/upstream/copilot.py:12`、`src/app/upstream/models_api.py:5`、`src/app/model_provider/base.py:11`、`src/app/model_provider/github_copilot.py:6`、`src/app/ghc_client/client.py:4`、`src/app/openai/client.py:4`、`src/app/anthropic/client.py:8`、`src/app/tokenization/service.py:4`、`src/app/pipeline/direct_driver/base.py:14`、`src/app/pipeline/executor.py:5`、`src/app/server/handler.py:16`。

#### D. 路由层消费 `httpx.Response`（只读，3 个文件）

`src/app/routes/openai.py:1`、`src/app/routes/azure.py:3`、`src/app/routes/gemini.py:4`。

#### E. 客户端注入点（把 `AsyncClient` 当参数传递，5 个文件）

`src/app/ghc_client/models.py:6`、`src/app/ghc_client/account.py:3`、`src/app/ghc_client/device_flow.py:7`、`src/app/upstream/bootstrap.py:8`、`src/app/openai/responses_ws.py:4`。

#### F. WebSocket（httpx-ws，2 个文件）

| 文件:行号 | import 形态 |
|---|---|
| `src/app/openai/responses_ws.py:5` | `from httpx_ws import aconnect_ws` |
| `src/app/routes/responses_ws.py:2-3` | `from httpx_ws import WebSocketDisconnect as UpstreamWebSocketDisconnect` / `from httpx_ws import WebSocketNetworkError, WebSocketUpgradeError` |

#### G. 只在注释里提到（无代码依赖，迁移无关）

`src/app/server/pipeline_app.py:578` —— 注释提到 `httpx.ReadError`，无 import。

### 1.2 `tests/` —— 按用途分组

#### A. cassette 录制/回放基础设施（3 个文件，迁移影响最大）

`tests/int/recorded/cassettes.py:26`、`tests/int/recorded/record_cassette.py:28`、`tests/int/recorded/recorded_provider.py:19`。

#### B. httpx 私有属性结构守卫（2 个文件）

`tests/unit/server/test_http_client_build.py:16-17`（`import httpcore` + `import httpx`）、`tests/unit/upstream/test_stream_cap.py:10-11`（同上）。

#### C. `MockTransport` 驱动的 component/unit 测试（约 14 个文件）

`tests/component/ghc_client/test_account.py:1`、`test_client.py:3`、`test_device_flow.py:3`、`test_models.py:1`、`test_tokens.py:2`；`tests/unit/upstream/test_upstream_targets.py:3`、`test_models_api.py:3`、`test_stream_cap.py:11`；`tests/unit/model_provider/test_model_provider.py:4`；`tests/int/test_phase1_bootstrap.py:3`、`tests/int/test_pipeline_app.py:16`；`tests/e2e/claude/_harness.py:22`。

#### D. 直接构造 `httpx.Response` / `httpx.Request` 做输入桩（约 18 个文件）

`tests/component/pipeline/test_pipeline_executor.py:6`、`tests/e2e/claude/_upstream.py:16`、`tests/int/test_anthropic_responses_route.py:6`、`test_anthropic_responses_stream_route.py:8`、`test_anthropic_routes.py:4`、`test_azure_routes.py:1`、`test_gemini_routes.py:3`、`test_hooks_pipeline.py:6`、`test_openai_routes.py:3`、`test_recorded_upstream.py:16`、`test_responses_ws.py:4`；`tests/unit/anthropic/test_anthropic_client.py:4`、`tests/unit/openai/test_openai_clients.py:4`、`test_responses_ws_transport.py:5`、`tests/unit/ghc_client/test_pre_header_retry.py:6`、`test_upstream_error_normalization.py:10`、`tests/unit/pipeline/test_direct_driver.py:3`、`test_timeout_enforcement.py:10`、`tests/unit/pipeline/subscribers/test_builtin_subscribers.py:10`、`tests/unit/tokenization/test_token_counting.py:5`、`tests/unit/upstream/test_upstream_client.py:1`、`tests/unit/config/test_config_paths.py:10`。

#### E. ASGITransport（1 处）

`tests/int/test_pipeline_ops_routes.py:11`。

#### F. httpx-ws（1 处）

`tests/int/test_responses_ws.py:6`：`from httpx_ws import WebSocketNetworkError, WebSocketUpgradeError`。

#### G. import 存在性守卫（1 处，会挡住迁移）

`tests/unit/test_imports.py:10,11,14` 的 `CORE_MODULES` 列了 `"httpx"`、`"httpx_ws"`、`"opentelemetry.instrumentation.httpx"` 三个模块名，逐个 import 检查。迁移后这份名单本身要改。

---

## 2. 我们创建 httpx 客户端 / 传输层的所有位置

`src/` 里 `httpx.AsyncClient(...)` 只有 **3 处**（另有 3 处在 tests 基础设施，见 §5）：

### 2.1 主路径：`build_http_client`（唯一的共享连接池入口）

`src/app/server/composition.py:123-157`

```python
def build_http_client(config: ProxyConfig) -> httpx.AsyncClient:
    options = transport_options(config)

    def transport(proxy: str | None) -> httpx.AsyncHTTPTransport:
        # No `limits`. Pooling is httpx's to decide and always was; ...
        built = httpx.AsyncHTTPTransport(
            proxy=proxy,
            http2=options.http2,
            socket_options=options.socket_options,
        )
        if options.socket_options is not None:
            _keep_proxy_connections_alive(built, options.socket_options)
        return built

    direct = transport(None)
    _warn_about_socks(options)
    client = httpx.AsyncClient(
        transport=transport(options.proxy) if options.proxy is not None else direct,
        mounts=_proxy_mounts(options.proxy, transport, direct),
        http2=options.http2,
    )
    if options.max_streams_per_connection > 0:
        cap_streams_per_connection(client, options.max_streams_per_connection)
    return client
```

这一处同时覆盖了任务问的每一项，逐条对应：

| 关注点 | 现状 | 位置 |
|---|---|---|
| 连接池参数 `Limits` | **刻意不传**。注释（`composition.py:135`）记录了原因：曾经只传 `keepalive_expiry` 的 `Limits` 把两个连接上限置成 `None`，httpcore 读成 `sys.maxsize`，等于取消了 httpx 的默认上限 | `composition.py:135-140` |
| 超时 | **不设**，走 httpx 默认；超时改由 `asyncio.timeout` 在 driver 层执行（见 §2.4） | 无 |
| HTTP/2 | 同时传给 transport 和 client：`http2=options.http2` | `composition.py:138,150` |
| SOCKS 代理 | `httpx.AsyncHTTPTransport(proxy=...)`；SOCKS 路径无法附加 socket options，改为显式告警 | `composition.py:137`、`_warn_about_socks` 在 `203-222` |
| 自定义 transport | 是 —— `AsyncHTTPTransport` 加 `socket_options`（TCP keep-alive），并对代理池打补丁 | `composition.py:134-143,160-200` |
| 事件钩子（`event_hooks`） | **全仓库无一处使用**（`rg 'event_hooks'` 为空） | — |
| `base_url` | `AsyncClient` 上**不设**；base_url 由 `AsyncOpenAI` / `AsyncAnthropic` 各自持有 | `composition.py:329-342` |
| `mounts` | 是 —— 手工重建环境变量代理映射，见 `_proxy_mounts` | `composition.py:149,241-257` |

关键设计约束（迁移必须保留的语义），出自 `composition.py:126` 的文档串：

> Socket options can only be given to a transport, and handing `AsyncClient` a transport is also how you switch off its own reading of `HTTP_PROXY` / `HTTPS_PROXY` — `allow_env_proxies` in `httpx/_client.py` is `trust_env and transport is None`.

即：**因为传了 transport，httpx 就不再读环境代理，所以我们必须自己把环境代理重建成 mounts。** 这条依赖 httpx 内部实现细节，httpx2 若改了 `allow_env_proxies` 的判定，这段就要重写。

### 2.2 `_proxy_mounts` —— 复用 httpx 私有工具重建环境代理映射

`src/app/server/composition.py:241-257`

```python
) -> dict[str, httpx.AsyncBaseTransport]:
    ...
    if configured is not None:
        return {}
    return {
        pattern: direct if url is None else transport(url)
        for pattern, url in get_environment_proxies().items()
    }
```

`get_environment_proxies` 来自 `from httpx._utils import ...`（`composition.py:18`）。同样在 `_warn_about_socks` 里用到（`composition.py:217`）。

### 2.3 旧路径：`create_http_client`（唯一还在传 `Limits` / `Timeout` 的地方）

`src/app/upstream/client.py:21-37`

```python
def create_http_client(settings: AppSettings) -> httpx.AsyncClient:
    upstream = settings.upstream
    return httpx.AsyncClient(
        http2=upstream.http2,
        proxy=upstream.proxy,
        limits=httpx.Limits(
            max_connections=upstream.max_connections,
            max_keepalive_connections=upstream.max_keepalive_connections,
            keepalive_expiry=upstream.keepalive_expiry,
        ),
        timeout=httpx.Timeout(
            connect=upstream.connect_timeout,
            read=upstream.read_timeout,
            write=upstream.read_timeout,
            pool=upstream.connect_timeout,
        ),
    )
```

这条路径由 `src/app/upstream/bootstrap.py` 消费（`bootstrap.py:57` 字段、`95` 参数、`112`/`191` 传给 `create_sdk_clients` / `create_copilot_sdk_clients`）。**它与 §2.1 是两套并行的构建入口**，迁移时两套都要动，且要确认 `Limits` / `Timeout` 在 httpx2 里的构造签名是否一致。

### 2.4 一次性客户端：device flow 认证

`src/app/auth/service.py:38`

```python
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        device_flow = DeviceFlowClient(http_client)
```

不共享连接池，不走 composition root，不受代理/keep-alive 配置影响。**这是一处独立的、容易在迁移中被漏掉的构建点。**

### 2.5 传输层改造：对 httpcore 连接池打补丁（两处，互相有顺序依赖）

**(a) 代理池 socket options 补丁** —— `src/app/server/composition.py:160-200`

```python
    pool = getattr(transport, "_pool", None)
    if not isinstance(pool, httpcore.AsyncHTTPProxy):
        return

    def create_connection(origin: httpcore.Origin) -> AsyncConnectionInterface:
        if origin.scheme == b"http":
            return AsyncForwardHTTPConnection(
                proxy_origin=pool._proxy_url.origin,
                ...
                socket_options=socket_options,
            )
        return AsyncTunnelHTTPConnection(...)

    pool.create_connection = create_connection
```

**(b) 每连接并发流上限** —— `src/app/upstream/stream_cap.py:90-123`

```python
    pools_to_cap: dict[int, httpx.AsyncBaseTransport] = {}
    for transport in (client._transport, *client._mounts.values()):
        if transport is not None:
            pools_to_cap.setdefault(id(transport), transport)
    for transport in pools_to_cap.values():
        _cap_one(transport, max_streams)


def _cap_one(transport: httpx.AsyncBaseTransport, max_streams: int) -> None:
    pool = getattr(transport, "_pool", None)
    if pool is None:
        raise TypeError(f"{type(transport).__name__} carries no connection pool to cap")

    inner_create = pool.create_connection

    def create_connection(origin: Origin) -> AsyncConnectionInterface:
        return StreamCappedConnection(inner_create(origin), cast(_PoolWithRequests, pool), max_streams)

    pool.create_connection = create_connection
```

两者都改写同一个 `pool.create_connection`，顺序不可交换 —— `composition.py:153-155` 已把这条写死在注释里，并说明 `test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive` 是使交换两行变红的守卫。

### 2.6 客户端构建入口的调用者（迁移时的波及面）

| 入口 | 调用者 |
|---|---|
| `build_http_client` | `src/app/cli.py:139`、`src/app/cli.py:161`、`src/app/debug/models.py:229` |
| `create_http_client` | `src/app/upstream/bootstrap.py:110`（`client = http_client or create_http_client(settings)`），并经 `src/app/upstream/__init__.py:1,3` 导出 |
| `httpx.AsyncClient(timeout=30.0)` | `src/app/auth/service.py:38`（仅 device flow） |

生命周期收口在 `Chain.aclose`（`src/app/server/composition.py:282-283`）：

```python
    async def aclose(self) -> None:
        await self.http_client.aclose()
```

---

## 3. 把 httpx 客户端交给第三方库的位置

### 3.1 传给 `openai` / `anthropic` SDK 的 `http_client=`

全部为 `AsyncOpenAI(...)` / `AsyncAnthropic(...)` 的构造参数，共 **5 组 10 处**（src 3 组 + tests 2 组，tests 见 §5.4）。

**(a) 主路径 —— `build_copilot_provider`** `src/app/server/composition.py:330-346`

```python
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
        AsyncAnthropic(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
        token_manager,
        ghc_config,
        interaction_id=interaction_id,
    )
```

具体行：`composition.py:334`（OpenAI）、`composition.py:340`（Anthropic）。

**(b) 旧路径 —— `create_sdk_clients`** `src/app/upstream/client.py:40-62`，`http_client=http_client` 在 `client.py:53`（OpenAI）与 `client.py:59`（Anthropic）。

**(c) 旧路径 —— `create_copilot_sdk_clients`** `src/app/upstream/client.py:65-84`，`http_client=http_client` 在 `client.py:75`（OpenAI）与 `client.py:81`（Anthropic）。

> **这三组就是背景事实里 `httpx2` 拒收 `httpx.AsyncClient` 的直接击中点。** 迁移之前它们是 6 个必改行。

### 3.2 SDK 的 `client.post(cast_to=httpx.Response, ...)` —— 比 `http_client=` 更深的一层耦合

项目不用 SDK 的 typed 返回，而是用 `cast_to=httpx.Response` 让 SDK 把**原始 httpx 响应对象**交回来。这是记忆里「typed 构造请求体 + `client.post` 原始 SSE 直通」的落地形态。逐处：

`src/app/upstream/generic.py`：`:33`、`:47`、`:59`、`:71`、`:83`、`:100`

```python
        return await self._clients.openai.post(
            "/chat/completions",
            cast_to=httpx.Response,
            body=cast(OpenAIBody, dict(payload)),
            stream=stream,
        )
```

`src/app/ghc_client/client.py`：`:78`、`:94`（以及 `:75,91,122,138,151,162,175,194` 的返回类型标注）。

**这一类的迁移风险高于 `http_client=`**：`cast_to` 的值必须与 SDK 内部判定「这是原始响应类型」的那个类**是同一个对象**。SDK 换成 `httpx2` 后，传 `httpx.Response` 要么抛错、要么走进「当作 pydantic model 解析」的分支 —— 后者是静默错误路径。

### 3.3 传给 `httpx-ws`

`src/app/openai/responses_ws.py:20,32-38`

```python
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        url: str,
        *,
        connect: Callable[..., Any] = aconnect_ws,
        queue_size: int = 32,
    ) -> None:
        ...
        async with self._connect(
            self._url,
            client=self._http,
            queue_size=self._queue_size,
        ) as websocket:
```

`aconnect_ws(..., client=<httpx.AsyncClient>)` 是本仓库把共享连接池交给 `httpx-ws` 的唯一位置。异常类型消费在 `src/app/routes/responses_ws.py:2-3`。

实测 `httpx-ws==0.9.0` 依赖声明是 `httpx>=0.23.1`（无上界），它 `import httpx` 拿到的是旧包，因此**它不会自动跟着迁移到 `httpx2`**。

### 3.4 OpenTelemetry httpx 插桩点

`src/app/observability/tracing.py:8-9,17-18`

```python
from opentelemetry.instrumentation.httpx import (
    HTTPXClientInstrumentor,
)
...
    if not HTTPXClientInstrumentor().is_instrumented_by_opentelemetry:
        HTTPXClientInstrumentor().instrument()
```

`instrument()` 是**全局猴子补丁**，按模块名 patch `httpx.Client` / `httpx.AsyncClient` / `httpx.HTTPTransport.handle_request` / `httpx.AsyncHTTPTransport.handle_async_request`。它 patch 的是 `httpx` 这个包名 —— 迁移到 `httpx2` 后，这个调用会成功执行、不报错、但**插桩到一个没人使用的包上**，追踪静默消失。

调用者：`setup_tracing(app, enabled=...)`。存在性守卫在 `tests/unit/test_imports.py:14`。

---

## 4. 依赖 httpx 类型 / 异常的位置

### 4.1 公共接口签名里的 `httpx.Response`（Protocol 契约面）

这是整个代码库最宽的一条 httpx 依赖：**`httpx.Response` 是 upstream → provider → driver → pipeline → route 全链路的传输载体类型**。

| 层 | 文件:行号 | 形态 |
|---|---|---|
| upstream Protocol | `src/app/upstream/base.py:24,32,37,44,49,54` | `) -> httpx.Response: ...`（6 个方法的 Protocol 声明） |
| upstream 实现（generic） | `src/app/upstream/generic.py:30,44,56,68,79,97` | 返回类型 |
| upstream 实现（copilot） | `src/app/upstream/copilot.py:97,106,116,124,130,136` | 返回类型 |
| ghc client | `src/app/ghc_client/client.py:75,91,101,122,138,151,162,175,194` | 返回类型 + `Coroutine[Any, Any, httpx.Response]` |
| provider Protocol | `src/app/model_provider/base.py:42,54` | `send(...) -> httpx.Response` / `count_tokens(...) -> httpx.Response` |
| provider 实现 | `src/app/model_provider/github_copilot.py:145,178` | 返回类型 |
| openai 协议层 | `src/app/openai/client.py:19,26,28,44,49,64` | Protocol + 方法 |
| anthropic 协议层 | `src/app/anthropic/client.py:50,57,79,175,185,426` | Protocol + `AnthropicAttemptResult.response: httpx.Response` 字段 + `-> tuple[httpx.Response, PreparedAnthropicRequest]` |
| tokenization | `src/app/tokenization/service.py:18,46` | Protocol + `response: httpx.Response \| None` |
| driver | `src/app/pipeline/direct_driver/base.py:82,225,242` | `DriverOutcome.response: httpx.Response \| None` + `_send(...) -> httpx.Response` |
| executor | `src/app/pipeline/executor.py:42,46` | `AttemptResult.response: httpx.Response` |
| server handler | `src/app/server/handler.py:71` | `def response(self) -> httpx.Response \| None:` |
| routes | `src/app/routes/openai.py:27`、`src/app/routes/azure.py:23`、`src/app/routes/gemini.py:30` | 入参 `upstream: httpx.Response` |

签名里出现 `httpx.AsyncClient` 的公共接口：`src/app/ghc_client/models.py:21`（`fetch_models` 第一个位置参数）、`src/app/ghc_client/account.py:32`、`src/app/ghc_client/device_flow.py:30`、`src/app/ghc_client/tokens.py:45`、`src/app/model_provider/github_copilot.py:49`、`src/app/openai/responses_ws.py:20`、`src/app/upstream/models_api.py:14`、`src/app/upstream/bootstrap.py:57,95`、`src/app/upstream/client.py:21,43,68`、`src/app/server/composition.py:123,268,320,359`。

签名里出现 `httpx.Request` 的公共接口：**src 无**（`httpx.Request` 在 src 只有 `handler.py:164` 一处构造）。tests 里有 109 处。

### 4.2 我们自己**构造** `httpx.Response`（合成响应，非上游产物）

| 文件:行号 | 用途 |
|---|---|
| `src/app/server/handler.py:164,179` | 合成一条「web search 未执行」的 Anthropic 回复；先造 `httpx.Request("POST", "https://synthesized.invalid/messages", content=b"")`，再 `httpx.Response(200, content=body, headers=headers, request=request)` |
| `src/app/openai/client.py:58-62` | `/responses` 非流式的 call-id 归一化后重建响应 |
| `src/app/anthropic/client.py:287-295` | Responses→Anthropic 转换结果，`request=getattr(upstream, "_request", None)`、`extensions=upstream.extensions` |
| `src/app/anthropic/client.py:448-461` | `_responses_error_response`，同样带 `request=getattr(upstream, "_request", None)` |
| `src/app/pipeline/executor.py:413-419` | hooks 改写 body 后重建响应，同样带 `request=getattr(original, "_request", None)` |

### 4.3 `except httpx.XxxError` 错误映射表

**(a) pre-header 可重试集合** `src/app/ghc_client/transport.py:8-13`

```python
_RESPONSES_PRE_HEADERS_HTTPX_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)
```

**(b) 上游错误归一化** `src/app/ghc_client/errors.py:44`

```python
_CONNECTION_ERRORS = (OpenAIConnectionError, AnthropicConnectionError, httpx.TransportError)
```

**(c) token 交换** `src/app/ghc_client/tokens.py:142,146`

```python
            except (httpx.HTTPError, OSError) as error:
                last_error = error
                status = (
                    error.response.status_code
                    if isinstance(error, httpx.HTTPStatusError)
                    else None
                )
```

**(d) responses headers 阶段** `src/app/upstream/generic.py:89`

```python
        except (httpx.TransportError, OpenAIAPIConnectionError) as error:
```

**(e) `GhcApiClient` 同名捕获** `src/app/ghc_client/client.py:185`

```python
        except (httpx.TransportError, OpenAIAPIConnectionError, H2ProtocolError) as error:
```

**(f) token counting 降级** `src/app/tokenization/service.py:61`

```python
            except (httpx.HTTPError, OSError, ValueError):
```

### 4.4 `isinstance` 检查

| 文件:行号 | 形态 |
|---|---|
| `src/app/ghc_client/transport.py:29` | `isinstance(error, _RESPONSES_PRE_HEADERS_HTTPX_ERRORS)` |
| `src/app/ghc_client/transport.py:40-41` | `isinstance(cause, httpx.TransportError \| H2ProtocolError)` → `isinstance(cause, (*_RESPONSES_PRE_HEADERS_HTTPX_ERRORS, H2ProtocolError))`，沿 `__cause__` 链回溯 |
| `src/app/ghc_client/tokens.py:146` | `isinstance(error, httpx.HTTPStatusError)` |
| `src/app/server/composition.py:173` | `isinstance(pool, httpcore.AsyncHTTPProxy)` —— 针对 httpcore 而非 httpx |
| `tests/unit/server/test_http_client_build.py:26,37` | `assert isinstance(transport, httpx.AsyncHTTPTransport)` |

> 这里有一处**跨异常体系的隐患已被记录**：`h2.exceptions.ProtocolError` 不是 httpx 异常，httpcore 只守住 socket 读那一段，GOAWAY 与其后的帧落在同一次读里时会穿透。见 `src/app/ghc_client/transport.py:31` 的注释与 `.dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-poc.md`。迁移到 httpx2 时这条要重新验证 —— 它依赖的是 httpcore 的内部结构，不是 httpx 的公共契约。

### 4.5 其他 httpx 类型

| 符号 | 位置 |
|---|---|
| `httpx.Headers` | `src/app/ghc_client/tokens.py:128`：`headers = httpx.Headers(self._identity_headers)` 后 `.update(...)` |
| `httpx.URL` | `src/app/server/composition.py:232`：`parsed = httpx.URL(url)`，读 `.host` / `.port` / `.scheme`；注释记录了两个行为依赖 —— IPv6 host 不带方括号返回、显式 `:0` 解析成整数 0 |
| `httpx.Limits` / `httpx.Timeout` | 仅 `src/app/upstream/client.py:26,31` |
| `httpx.AsyncBaseTransport` | `src/app/upstream/stream_cap.py:105,113`、`src/app/server/composition.py:245` |
| `httpx.AsyncHTTPTransport` | `src/app/server/composition.py:134,136,161,243,244` |

---

## 5. 测试侧

### 5.1 `httpx.MockTransport`（31 处，13 个文件）

统一形态是 `httpx.AsyncClient(transport=httpx.MockTransport(handler))`，handler 是一个 `(httpx.Request) -> httpx.Response` 的同步函数。

| 文件:行号 | 备注 |
|---|---|
| `tests/component/ghc_client/test_tokens.py:46,87,117,143,184,214,250,277,305` | 最集中的一处；`:250` 与 `:305` 用 lambda 形态：`httpx.MockTransport(lambda _: httpx.Response(500))` |
| `tests/component/ghc_client/test_models.py:17,37,57,68` | `async with httpx.AsyncClient(transport=...) as http_client:` |
| `tests/component/ghc_client/test_account.py:33,52` | |
| `tests/component/ghc_client/test_client.py:32` | |
| `tests/component/ghc_client/test_device_flow.py:14` | |
| `tests/unit/upstream/test_upstream_targets.py:46,88,124,155,187` | |
| `tests/unit/upstream/test_models_api.py:32,62` | |
| `tests/unit/upstream/test_stream_cap.py:210` | 用来断言「MockTransport 没有池、cap 必须报错而非静默不生效」 |
| `tests/unit/model_provider/test_model_provider.py:64` | |
| `tests/unit/model_provider/test_model_provider.py:270` | **注入私有属性**：`provider._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))` |
| `tests/int/test_pipeline_app.py:77` | 整条 pipeline 的上游替身 |
| `tests/int/test_phase1_bootstrap.py:48` | |
| `tests/e2e/claude/_harness.py:68` | `httpx.AsyncClient(transport=httpx.MockTransport(upstream.handle))`，跑真实应用真实端口 |
| `tests/int/recorded/cassettes.py:345` | `class ReplayTransport(httpx.MockTransport)` —— **唯一一处继承** |

### 5.2 自定义 transport（继承 `httpx.AsyncBaseTransport`）

| 文件:行号 | 类 |
|---|---|
| `tests/int/recorded/cassettes.py:388` | `class RecordingTransport(httpx.AsyncBaseTransport)`，`__init__` 默认 `inner or httpx.AsyncHTTPTransport()`（`:392`） |
| `tests/int/test_recorded_upstream.py:293` | `class _FakeUpstream(httpx.AsyncBaseTransport)` |
| `tests/int/test_recorded_upstream.py:359` | 函数内局部 `class _Http2(httpx.AsyncBaseTransport)`，改写 `response.extensions["http_version"]` |

三者都实现 `async def handle_async_request(self, request: httpx.Request) -> httpx.Response`。

### 5.3 自定义 byte stream（继承 `httpx.AsyncByteStream`，8 个类）

`tests/int/recorded/cassettes.py:319`（`_ReplayStream`，同时实现 `__aiter__` 与 `__iter__`）、`tests/int/test_anthropic_responses_stream_route.py:40`（`ControlledResponsesStream`）与 `:73`（`StaticResponsesStream`）、`tests/int/test_anthropic_routes.py:15`、`tests/int/test_openai_routes.py:13`、`tests/int/test_gemini_routes.py:12`、`tests/unit/openai/test_openai_clients.py:12`、`tests/unit/upstream/test_upstream_targets.py:16`、`tests/int/test_recorded_upstream.py:302`（局部 `_Stream`）。

`httpx.AsyncByteStream` 也出现在签名里：`tests/int/test_anthropic_responses_stream_route.py:88,225`。

### 5.4 `ASGITransport` 与 `TestClient`

- **`httpx.ASGITransport` 只有 1 处**：`tests/int/test_pipeline_ops_routes.py:66`

  ```python
      return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
  ```

- **`fastapi.testclient.TestClient`** 在 int 层大量使用（实测 14 个文件、72 处），例如 `tests/int/test_pipeline_app.py:143,743,771`、`tests/int/test_anthropic_responses_stream_route.py:986,1153,1237,1293,1391,1428,1489,1520`、`tests/int/test_openai_routes.py:56,70,81,94`、`tests/int/test_anthropic_routes.py:134,149,167,188,202`、`tests/int/test_gemini_routes.py:40,50,61,68`、`tests/int/test_azure_routes.py:24,36`、`tests/int/test_management_routes.py:35,50,58,64`、`tests/int/test_history_routes.py:31,45`、`tests/int/test_health_routes.py`、`tests/int/test_approval_routes.py:13`、`tests/int/test_server_startup.py:13,44`、`tests/int/test_anthropic_responses_route.py:316`。

  **`TestClient` 归 starlette 管，不归我们管** —— 它内部 `import httpx` 并继承 `httpx.Client`。迁移到 httpx2 后，这一整片测试的行为取决于 `starlette==0.52.1` 用的是哪个 httpx。这一项不在我们的代码里，但会决定测试面能否跑通。

- `tests/int/test_pipeline_app.py:113` 的签名 `-> tuple[TestClient, list[httpx.Request]]`、`:1039,1126` 的 `-> httpx.Response` 把两个体系的类型混在同一个签名里。

### 5.5 cassette 回放机制是怎么接进 httpx 的

**接入点只有 transport 一层**，没有 monkeypatch，没有 vcrpy。链路：

1. **构造回放客户端** —— `tests/int/recorded/recorded_provider.py:49-51`

   ```python
   def replay_client(name: str) -> httpx.AsyncClient:
       """An httpx client that answers from the named cassette and never reaches the network."""
       return httpx.AsyncClient(transport=ReplayTransport(Cassette.read(cassette_path(name))))
   ```

2. **`ReplayTransport` 继承 `httpx.MockTransport`** —— `tests/int/recorded/cassettes.py:345-356`

   ```python
   class ReplayTransport(httpx.MockTransport):
       def __init__(self, cassette: Cassette) -> None:
           self._remaining = list(cassette.interactions)
           super().__init__(self._handle)
   ```

   即：**依赖 `MockTransport.__init__(handler)` 这个公共构造契约**，把自己的 `_handle` 作为 handler 传进去。

3. **`_handle` 返回带自定义 stream 与 extensions 的 `httpx.Response`** —— `cassettes.py:358-385`

   ```python
       def _handle(self, request: httpx.Request) -> httpx.Response:
           path = request.url.path
           ...
                   return httpx.Response(
                       interaction.status,
                       headers=interaction.headers,
                       stream=_ReplayStream(interaction.chunks),
                       # httpx reads these as bytes and a cassette holds text, so they go back as
                       # bytes on the way out.
                       extensions=cast(
                           dict[str, Any],
                           {name: value.encode() for name, value in interaction.extensions.items()},
                       ),
                   )
   ```

   依赖的 httpx 契约有 4 条：`request.url.path`、`request.headers`、`request.content`（`_request_shape` 在 `cassettes.py:221` 读）、以及 `Response(..., stream=..., extensions=...)` 这两个关键字参数。

4. **该客户端被交给真实 SDK** —— `recorded_provider.py:54-72`，`AsyncOpenAI(..., http_client=http_client)` / `AsyncAnthropic(..., http_client=http_client)`，即 §3.1 的第 4、5 组注入点。

5. **录制侧** —— `tests/int/recorded/record_cassette.py:56`

   ```python
       recorder = RecordingTransport()
       client = httpx.AsyncClient(transport=recorder, timeout=120)
   ```

   `RecordingTransport.handle_async_request`（`cassettes.py:395-435`）内部：`response.aiter_raw()` 取原始分块、`response.aclose()`、`response.extensions`、`response.headers`、`response.status_code`，再重建一个 `httpx.Response(..., stream=_ReplayStream(chunks), request=request, extensions=response.extensions)` 交回下游。

**结论：cassette 机制对 httpx 的依赖面是 `MockTransport` / `AsyncBaseTransport` / `AsyncByteStream` / `Request` / `Response` 五个公共类，加上 `aiter_raw` 与 `extensions` 两条行为契约。没有私有 API。** 这是整个测试基础设施里最容易迁移的一块 —— 前提是 httpx2 保留了这五个类的同名同签名。

### 5.6 从 history 数据库派生 cassette

`tests/int/recorded/from_history.py` —— 该文件**不 import httpx**（已确认），只产出 JSON 结构。迁移无关。

---

## 6. 触碰 httpx / httpcore 私有 API 的位置（跨大版本最易断）

分成两类：**httpx 私有** 与 **httpcore 私有**。后者数量更多，但 httpcore 不在本次迁移范围内 —— 不过 httpx2 换没换底层 httpcore，会直接决定这些代码还成不成立。

### 6.1 httpx 私有 API

| 文件:行号 | 私有面 | 用途 | 是否有守卫 |
|---|---|---|---|
| `src/app/server/composition.py:18` | `from httpx._utils import get_environment_proxies` | 复用 httpx 的 `NO_PROXY` 匹配逻辑而不自己实现 | **import 失败即崩**（`composition.py:250` 明确写了这是刻意选择：「A httpx that moves it fails at import, so this cannot decay into quietly returning no mounts」） |
| `src/app/upstream/stream_cap.py:106` | `client._transport`、`client._mounts` | 遍历所有需要打 cap 的 transport | 有：`tests/unit/upstream/test_stream_cap.py:134,145,157,237,243` |
| `src/app/anthropic/client.py:293,461`、`src/app/pipeline/executor.py:417` | `getattr(upstream, "_request", None)` | 重建响应时把原 request 带过去 | **无守卫** —— `getattr` 带默认值 `None`，属性一旦改名会**静默降级成 `request=None`**，不报错 |
| `tests/unit/server/test_http_client_build.py:32,36,92,169,195` | `client._transport`、`client._mounts` | 结构断言 | 自身即守卫 |

> `getattr(..., "_request", None)` 这三处是本清单里唯一**静默失效**的 httpx 私有依赖。httpx 的 `Response.request` 是有公共 property 的（未设置时抛 `RuntimeError`），代码绕开它正是为了不抛；迁移时这三处应当被显式检查。

### 6.2 httpcore 私有 API（httpx 之下的一层）

| 文件:行号 | 私有面 |
|---|---|
| `src/app/server/composition.py:16-17` | `from httpcore._async.http_proxy import AsyncForwardHTTPConnection, AsyncTunnelHTTPConnection` / `from httpcore._async.interfaces import AsyncConnectionInterface` |
| `src/app/server/composition.py:172` | `getattr(transport, "_pool", None)` |
| `src/app/server/composition.py:179-196` | `pool._proxy_url`、`pool._proxy_headers`、`pool._keepalive_expiry`、`pool._network_backend`、`pool._proxy_ssl_context`、`pool._ssl_context`、`pool._http1`、`pool._http2`（11 处，全部带 `# pyright: ignore[reportPrivateUsage]`） |
| `src/app/server/composition.py:200` | `pool.create_connection = create_connection`（写私有池的方法） |
| `src/app/upstream/stream_cap.py:49` | `self._pool._requests` 以及其元素的 `.connection` |
| `src/app/upstream/stream_cap.py:114,118,123` | `transport._pool`、`pool.create_connection` 读写 |
| `tests/unit/server/test_http_client_build.py:27,38,40-42` | `transport._pool._socket_options`、`pool._max_connections`、`pool._max_keepalive_connections`、`pool._keepalive_expiry` |
| `tests/unit/upstream/test_stream_cap.py:75,134,145,167,237,243,320` | `pool._requests` 结构守卫 + `client._transport._pool.create_connection(...)` |

`src/app/upstream/stream_cap.py:16` 的文档串已经把这条风险写死：

> **Private surface, named so an upgrade knows what to check.** `pool._requests` and the `.connection` on its elements. … httpcore's CHANGELOG has never once mentioned the pool internals — including in the release that rewrote them — so **upgrading httpcore means diffing its source, not reading its release notes**.

以及 `stream_cap.py:78-84` 那个针对 httpcore PR #1088 的前瞻性 `max_concurrent_requests()` 转发。

### 6.3 非 httpx 但同源的私有依赖

`tests/unit/model_provider/test_model_provider.py:270`：`provider._http = httpx.AsyncClient(...)` —— 改的是**我们自己**的私有属性，不是 httpx 的，迁移只需跟着改类型。

---

## 7. 已核实的未使用面 / 低估过的使用面

### 7.1 确认零使用（`rg` 退出码 1，可放心缩小迁移面）

- `event_hooks`（客户端事件钩子）—— **全仓库零处**
- `httpx.Client` / `httpx.HTTPTransport` / `httpx.BaseTransport`（同步 API）—— **我们的代码零处**；`fastapi.testclient.TestClient` 内部继承 `httpx.Client`，但那是 starlette 的依赖，不在我们的 import 面上
- `httpx.Auth`、`auth=` —— 零处（鉴权全部走 header）
- `httpx.Cookies`、`cookies=` —— 零处
- `follow_redirects` —— 零处（走 httpx 默认）
- vcrpy —— 零处（已于 `docs/tmp/260818-vcrpy-poc.md` 否决）

### 7.2 盘点中修正过一次的两项（原以为零使用，实测非零）

**(a) `client.stream(...)` 有 4 处，其中 2 处是真 httpx**

| 位置 | 是谁的 `stream` |
|---|---|
| `tests/int/test_pipeline_app.py:1241`、`:2023` | `TestClient.stream` —— starlette 的，不是我们的迁移面 |
| `tests/int/test_recorded_upstream.py:336` | `httpx.AsyncClient(transport=recorder)` 的，配 `response.aiter_raw()` 消费 |
| `tests/unit/server/test_http_client_build.py:301` | `build_http_client(...)` 返回的真客户端，`async with client, client.stream("GET", url) as response:` |

**(b) `response.extensions["network_stream"]` —— 一条此前未列入的 httpcore 契约依赖**

`tests/unit/server/test_http_client_build.py:302-305`

```python
    async with client, client.stream("GET", url) as response:
        sock = response.extensions["network_stream"].get_extra_info("socket")
        read = {"SO_KEEPALIVE": sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)}
```

这是**唯一能证明 `tcp_keepalive_interval` 真的落到了 socket 上的手段** —— 直接从内核读回 `SO_KEEPALIVE`。它依赖 `extensions["network_stream"]` 这个 httpcore 约定与 `.get_extra_info("socket")` 方法。迁移后若这条契约变化，这个测试要么崩（响，可接受），要么读到别的东西（哑，危险）。**它应当与 §6.2 的 httpcore 私有面一起评估。**

### 7.3 `httpx.URL` 的实际使用面（很窄）

`request.url` 只被读了两个属性：`.host`（14 处）与 `.path`（16 处）。另有 `src/app/server/composition.py:232-234` 独立构造 `httpx.URL(url)` 并读 `.scheme` / `.host` / `.port`。没有任何地方调用 `URL` 的方法（`copy_with`、`join` 等）。

---

## 8. 迁移必经面之外的 httpx 使用（供参考，不阻塞）

这些目录不参与产品构建，可以后置或直接放弃：

- `verification/final_acceptance/probes/01_dynamic_port_startup.py:5`、`02_anthropic_protocol.py:5`、`03_openai_three_prefixes.py:5`、`05_history_metrics.py:5`、`06_approval_system.py:5`、`07_gemini_azure.py:5` —— 全是 `import httpx` 的一次性验收探针。
- `exp/260820-h2-stream-cap/{run_poc,debug_probe,probe_costs,stream_cap}.py`、`exp/260820-h2-goaway-poc/run_poc.py`、`exp/260820-websearch-probe/{probe,record}.py`、`exp/260820-empty-text-probe/{probe,probe_empty_containers}.py`、`exp/260820-tool-pair-probe/pairing_probe.py`、`exp/phase2-acceptance/verify_acceptance.py`、`exp/upstream-sdk-passthrough/poc_passthrough.py` —— 归档实验。
- `exp/httpx-ws/poc.py:2,4,5` —— 用了 `from httpx_ws.transport import ASGIWebSocketTransport`，是本仓库唯一提到该符号的地方。

---

## 9. 迁移风险排序

按「改起来最可能出问题」降序。每条给出**为什么**，以及**失败时是响还是哑**（哑的更危险）。

> 排序依据是**本仓库这一侧的耦合深度与失效可见性**，不是对 httpx2 生态的判断。风险 1、4、6 涉及外部依赖是否跟进，**那部分以 `docs/tmp/260821-httpx2-ecosystem-compat.md` 的实测为准**；若那份已给出确定结论，本节对应条目的严重度应据此重排。

### 风险 1（最高）：`opentelemetry-instrumentation-httpx` 会静默插桩到错误的包

- 位置：`src/app/observability/tracing.py:8-9,17-18`
- 为什么：`HTTPXClientInstrumentor().instrument()` 按 `httpx` 这个**模块名**做全局猴子补丁。迁移后我们的客户端是 `httpx2.AsyncClient`，而它 patch 的仍是旧 `httpx`。
- 失败形态：**完全哑**。`instrument()` 正常返回、`is_instrumented_by_opentelemetry` 为真、无异常、无日志，只是上游请求的 span 全部消失。`tests/unit/test_imports.py:14` 只检查模块能否 import，抓不到这个。
- 加重因素：`opentelemetry-instrumentation-httpx` 上游是否发布了 httpx2 版本，是我们控制不了的外部依赖。

### 风险 2：`cast_to=httpx.Response` 的 8 处

- 位置：`src/app/upstream/generic.py:33,47,59,71,83,100`、`src/app/ghc_client/client.py:78,94`
- 为什么：`cast_to` 的值必须与 SDK 内部用来判定「返回原始响应」的那个类**是同一个对象**。SDK 换成 httpx2 后传旧 `httpx.Response`，会落进 SDK 的通用反序列化分支。
- 失败形态：**取决于 SDK 实现，可能哑**。若 SDK 尝试把 SSE 字节流当作 pydantic model 解析，会在运行时抛一个与 httpx 毫无关联的错误；若它宽容处理，就是静默返回错误类型的对象。
- 加重因素：这 8 处覆盖了 `/chat/completions`、`/responses`、`/v1/messages`、`/v1/messages/count_tokens`、`/embeddings` **全部上游端点**，其中 `/responses` 是主产品路径。

### 风险 3：`build_http_client` 的 transport + mounts 组合（`composition.py:123-257`）

- 为什么：这一段的正确性建立在**三条 httpx 内部行为**上，任意一条在 httpx2 里变化都会导致代理失效：
  1. `allow_env_proxies = trust_env and transport is None`（`composition.py:126` 引用），这是我们必须自建 mounts 的唯一理由；
  2. `httpx._utils.get_environment_proxies` 的存在与返回结构（pattern → url|None）；
  3. `mounts` 的匹配语义与 `all://` 优先级。
- 失败形态：**混合**。`get_environment_proxies` 移动 → import 崩溃，响（这是刻意设计）。但若 httpx2 改了 `allow_env_proxies` 的判定而保留了 `_utils` → 代理被**挂载两次**或环境代理被**忽略**，全哑，只有在代理后的部署里才暴露。
- 加重因素：`transport_options` 的三个字段（proxy / http2 / socket_options）各自对应过一次已修的静默缺陷，注释里都记着；这段代码的历史证明它就是静默失效的高发区。

### 风险 4：`httpx-ws` 拿到的是另一个 httpx

- 位置：`src/app/openai/responses_ws.py:5,20,32-38`；异常侧 `src/app/routes/responses_ws.py:2-3`
- 为什么：`httpx-ws==0.9.0` 声明 `httpx>=0.23.1` 且 `import httpx`。`aconnect_ws(url, client=self._http, ...)` 传进去的会是 `httpx2.AsyncClient`。
- 失败形态：**大概率是响的**（类型不匹配 / 属性缺失时抛错），但抛的位置在第三方库内部，错误信息不会指向我们的接线。
- 加重因素：httpx-ws 是否会发布 httpx2 版本未知。若不发布，要么保留旧 httpx 只为它用（双 httpx 共存，连接池不共享，破坏 §2.1 的整个设计），要么放弃该路径。**这是一个需要用户裁决的分叉，不该由迁移方案自行选择。**

### 风险 5：`getattr(upstream, "_request", None)` 的 3 处

- 位置：`src/app/anthropic/client.py:293,461`、`src/app/pipeline/executor.py:417`
- 为什么：读 httpx `Response` 的私有属性，且用 `getattr` 兜了默认值。
- 失败形态：**纯哑**。属性改名后一律得到 `None`，重建的响应就此失去 request 关联；下游任何读 `response.request` 的地方（含 SDK、含 OTel、含错误消息）会看到「无 request」。三处全部无守卫测试。
- 缓解成本极低：迁移时应改成显式访问 + 显式处理未设置的情况，而不是继续 `getattr` 兜底。

### 风险 6：`TestClient`（starlette）与我们的 httpx2 混用

- 位置：约 14 个 int 测试文件，72 处（§5.4）
- 为什么：`fastapi.testclient.TestClient` 继承 `httpx.Client`，归 `starlette==0.52.1` 管，我们不能改它用哪个 httpx。
- 失败形态：**响**（import 冲突 / 类型不匹配），但**波及面极大** —— 若 starlette 未跟进，这一整层测试都跑不起来，会掩盖迁移本身的其他问题。
- 备注：`tests/int/test_pipeline_ops_routes.py:66` 用的是我们自己的 `httpx.ASGITransport`，那一处可以自主迁移；`TestClient` 那 50+ 处不能。

### 风险 7：`httpcore` 私有面（`_pool` / `_requests` / `create_connection` / `network_stream`）

- 位置：`src/app/server/composition.py:160-200`、`src/app/upstream/stream_cap.py:49,106,114-123`、`tests/unit/server/test_http_client_build.py:302`
- 为什么：`stream_cap` 与代理 keep-alive 补丁都依赖 `httpx.AsyncHTTPTransport` 底下是 `httpcore` 的池，且池有 `_requests` / `create_connection`。若 httpx2 换掉了底层实现，这两个机制整体失效。同一层还挂着 `response.extensions["network_stream"].get_extra_info("socket")`（§7.2b），那是**唯一**能证明 keep-alive 真的写到了 socket 上的手段。
- 失败形态：**主体已被守卫覆盖，是响的**。`stream_cap._cap_one` 在没有 `_pool` 时主动 `raise TypeError`（`stream_cap.py:116`），`tests/unit/upstream/test_stream_cap.py:75` 有结构断言（`assert isinstance(pool._requests, list), "httpcore.AsyncConnectionPool no longer keeps \`_requests\`"`），`tests/unit/server/test_http_client_build.py` 有 10 处私有属性断言。**例外是 `network_stream`：`extensions` 是个 dict，键改名会抛 `KeyError`（响），但若换成另一个语义不同的对象则是哑的。**
- 之所以排名不更高：**这一处的设计已经预判了自己会断**，且断的时候多半是响的。真正的成本是「重新实现」而不是「发现」。

### 风险 8（最低）：机械类型替换面

- `httpx.Response` 类型标注 70 处（src）+ 302 处（tests）、`httpx.AsyncClient` 20 + 60 处、`httpx.Request` 109 处（tests）、异常类 5 类 6 处捕获、`httpx.Headers` / `httpx.URL` / `httpx.Limits` / `httpx.Timeout` 各 1-2 处。
- 为什么风险低：全部是 `import httpx` → `import httpx2 as httpx` 或逐符号替换即可；pyright 是 `strict` 模式（`pyproject.toml:[tool.pyright] typeCheckingMode = "strict"`，`include = ["src", "tests"]`），类型不匹配**会被静态检查抓住**，不会静默。
- 唯一需要注意的：异常类的**继承关系**若在 httpx2 里变了（例如 `HTTPStatusError` 不再继承 `HTTPError`），`src/app/ghc_client/tokens.py:142` 的 `except (httpx.HTTPError, OSError)` 会漏掉本该捕获的错误 —— 这一条 pyright 抓不到。

---

## 附：迁移时应当逐条勾掉的最小必改清单

1. `pyproject.toml:16-17,22` 三条依赖声明（含 `[http2,socks]` extra 的对应写法）
2. `src/app/server/composition.py` —— 整个客户端构建（含 `httpx._utils` 私有 import）
3. `src/app/upstream/client.py:21-37` —— 第二套构建入口（`Limits` / `Timeout`）
4. `src/app/auth/service.py:38` —— 第三个、独立的构建点
5. `src/app/upstream/stream_cap.py` —— `client._transport` / `client._mounts` / `_pool`
6. §3.1 的 6 个 `http_client=` 行
7. §3.2 的 8 个 `cast_to=httpx.Response`
8. `src/app/observability/tracing.py:8-18` —— OTel 插桩（需要外部依赖跟进）
9. `src/app/openai/responses_ws.py` + `src/app/routes/responses_ws.py` —— httpx-ws（需要用户裁决）
10. §4.3 的 6 张异常映射表 + §4.4 的 isinstance
11. §6.1 的 3 处 `getattr(..., "_request", None)`
12. `tests/int/recorded/cassettes.py` 三个类（`ReplayTransport` / `RecordingTransport` / `_ReplayStream`）
13. `tests/unit/test_imports.py:10,11,14` 的模块名单
14. `tests/unit/server/test_http_client_build.py:301-305` 的 `client.stream(...)` + `extensions["network_stream"]` 探针
15. 其余测试文件的机械替换（39 个含 `httpx.` 的测试文件，减去上面第 12、13、14 条已单列的 3 个）

---

## 盘点方法与本清单的可信度

- 事实来源：`rg` 全仓库检索 + 逐文件阅读，`.venv` 内 `importlib.metadata` 实测版本与依赖声明。行号对应 2026-08-21 的工作树。
- **可直接据以行动**：§1-§6 的文件:行号与代码摘录，全部来自实际检索输出或文件读取。
- **可直接据以行动**：§7.1 的零使用结论，每条都有 `rg` 退出码 1 佐证。
- **需要迁移时再验证**：§9 中关于 httpx2 行为的每一条推断（`allow_env_proxies` 是否仍是那个判定、`_utils` 是否还在、`MockTransport` 构造签名是否不变、异常继承关系是否变化）。本次盘点**没有安装 httpx2，没有读它的源码**，所有关于「httpx2 里会怎样」的话都是基于本仓库现状推出的**待验证假设**，不是观测。
- **需要用户裁决**：风险 4（httpx-ws 若不跟进，是双 httpx 共存还是放弃 WebSocket 路径）与风险 1（OTel 插桩若不跟进）是外部依赖问题，本清单不替方案做选择。
- 未覆盖：`exp/`、`verification/`、`contrib/` 只做了 import 层面的列举（§8），没有逐个阅读。

