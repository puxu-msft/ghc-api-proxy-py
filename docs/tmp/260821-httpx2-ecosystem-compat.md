# HTTPX2 生态兼容性调研

日期：2026-08-21

## 结论摘要

**总判定：整体迁移没有不可绕过的生态阻断项，但“保留 `httpx-ws==0.9.0`，再把它接到 `httpx2.AsyncClient`”不是受支持的迁移方案。** `httpx-ws` 仍然建立在旧 `httpx`／`httpcore` 上，这是直接机械替换路径上的阻断项；不过 `httpx2>=2.6.0` 已经把 `httpx-ws` vendoring 为原生 WebSocket 功能，`2.7.0` 同步到上游 `httpx-ws 0.9.0`，`2.10.0` 又补了正确性修复，因此整体迁移可通过改用 `httpx2[ws]` 与 `AsyncClient.websocket()` 解阻。

明确建议：**现在开始分阶段迁移，而不是把 SDK 长期钉在旧大版本等待生态。** 推荐先允许 `httpx` 与 `httpx2` 共存，迁移普通出站请求和 SDK 注入，再把 Responses WebSocket 路径切到 `httpx2` 原生 WebSocket，最后移除旧 `httpx`／`httpx-ws`。迁移时必须把现有 `HTTPXClientInstrumentor` 改为 `HTTPX2ClientInstrumentor`；共存阶段则同时启用两个 instrumentor。不要调用 `httpx2.alias_httpx()`，因为它与真正的双栈共存互斥。

证据权重：上述迁移可行性判定为“强到足以据此行动”，依据是探针环境源码、三组本机运行探针、PyPI 实际依赖元数据以及上游 changelog／migration guide。生态成熟度判定为“足以选择迁移策略，但不能推导所有第三方插件都已跟进”，因为 HTTPX2 正式版只有约三个月历史，抽查到的集成工具仍然参差不齐。

## 1. OpenAI 3.3.1 与 Anthropic 1.0.0 的 `http_client=` 合同

### 1.1 OpenAI 3.3.1：静态类型只写 HTTPX2，运行时明确兼容两套 client

这里必须纠正题目前提中的一处事实：**已安装的 `openai==3.3.1` 并不拒收 `httpx.AsyncClient`。** 它的公开构造器注解是 `httpx2.AsyncClient | None`，但运行时校验明确同时接受 `httpx2.AsyncClient` 与 legacy `httpx.AsyncClient`。

源码证据：

- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/openai/_client.py:853-856`：公开参数注释和类型注解只指向 `httpx2.AsyncClient`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/openai/_base_client.py:1559-1567`：校验同时调用 `is_httpx2_async_client()` 与 `is_legacy_httpx_async_client()`，错误文本也写明两者都可接受。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/openai/_httpx2.py:25-45`：legacy 检测从已加载的 `sys.modules["httpx"]` 获取类并执行 `isinstance`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/openai/_base_client.py:1697-1703`：发送前会根据实际 client 家族把 auth 规范化到对应类型，说明 legacy 分支不只是宽松校验。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/openai/_base_client.py:1470-1475,1501-1514`：`DefaultAsyncHttpxClient` 已改成 `httpx2.AsyncClient` 的子类；旧名称保留，但底层已是 HTTPX2。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/openai/_httpx2.py:132-141`：新增的 `DefaultHttpx2Client`／`DefaultAsyncHttpx2Client` 直接构造 `httpx2.Client`／`httpx2.AsyncClient`。

版本边界：

- [`openai-python` CHANGELOG](https://github.com/openai/openai-python/blob/main/CHANGELOG.md) 记载 `2.47.0` 首次加入 experimental runtime HTTPX2 client 支持。
- `3.0.0` 于 2026-08-12 把 HTTPX2 改成默认 client，并停止自动安装旧 `httpx`；对应 PR 是 [`#3594`](https://github.com/openai/openai-python/pull/3594)。
- 官方 [`httpx2.md` migration guide](https://github.com/openai/openai-python/blob/main/httpx2.md) 明确把旧 HTTPX 支持称为 temporary、runtime-only escape hatch：运行时可用，但公开注解只接受 HTTPX2，mypy／Pyright 会拒绝 legacy client；这条兼容路径未来可能删除。
- 探针中的 `openai==3.3.1` 元数据只依赖 `httpx2<3,>=2.7.0`，不会替应用安装旧 `httpx`。因此运行时兼容不等于依赖合同继续包含旧 HTTPX。

实际运行探针的关键输出：

```text
versions: openai=3.3.1 anthropic=1.0.0 httpx=0.28.1 httpx2=2.12.0
openai+httpx: ACCEPTED stored=httpx.AsyncClient
openai+httpx2: ACCEPTED stored=httpx2.AsyncClient
openai.DefaultAsyncHttpxClient: type=openai._DefaultAsyncHttpxClient isinstance_httpx=False isinstance_httpx2=True
openai.DefaultAsyncHttpx2Client: type=httpx2.AsyncClient isinstance_httpx=False isinstance_httpx2=True
```

探针构造了两种 `AsyncClient`，分别传给 `openai.AsyncOpenAI(api_key="probe", http_client=client)`，随后检查 SDK 实际保存的 `_client` 类型并关闭 client。结论为“强到足以据此行动”：3.3.1 的 legacy 支持是源码中的刻意分支和实际可达行为，不是偶然 duck typing。

### 1.2 Anthropic 1.0.0：静态类型与运行时都只接受 HTTPX2

Anthropic 的结论不同：**`anthropic==1.0.0` 的 `http_client=` 只接受 `httpx2.Client`／`httpx2.AsyncClient`，旧 `httpx` client 在构造时就报 `TypeError`。**

源码证据：

- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/anthropic/_client.py:555-572`：`AsyncAnthropic.__init__` 的参数类型是 `httpx2.AsyncClient | None`，注释也只链接 HTTPX2 文档。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/anthropic/_base_client.py:989-992`：同步 client 只执行 `isinstance(http_client, httpx2.Client)`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/anthropic/_base_client.py:1685-1688`：异步 client 只执行 `isinstance(http_client, httpx2.AsyncClient)`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/anthropic/_base_client.py:1558-1604,1625-1638`：`DefaultAsyncHttpxClient` 是 `httpx2.AsyncClient` 子类，并带 Anthropic 自己的默认 timeout、limits、redirect、keepalive socket options 和 proxy mounts。

版本边界：

- [`anthropic-sdk-python` CHANGELOG](https://github.com/anthropics/anthropic-sdk-python/blob/main/CHANGELOG.md) 记载 `1.0.0` 于 2026-08-20 从 `0.125.0` 跨入新大版本，并以 breaking change 把 client 升到 HTTPX2，commit 为 `33e296749dda59c3b9af85d9bee37ae241b92a28`。
- 官方 [`MIGRATION.md`](https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md) 明确写明：传入旧 `httpx.Client`／`AsyncClient` 会在构造时抛 `TypeError`；所有交给 SDK 的 transport、timeout、limits 等对象也必须来自 `httpx2`。
- 探针元数据证实 `anthropic==1.0.0` 依赖 `httpx2<3,>=2.0.0`，不再依赖旧 `httpx`。

实际运行探针的关键输出：

```text
anthropic+httpx: REJECTED TypeError: Invalid `http_client` argument; Expected an instance of `httpx2.AsyncClient` but got <class 'httpx.AsyncClient'>
anthropic+httpx2: ACCEPTED stored=httpx2.AsyncClient
anthropic.DefaultAsyncHttpxClient: type=anthropic._DefaultAsyncHttpxClient isinstance_httpx=False isinstance_httpx2=True
```

因此，如果本项目继续向 Anthropic 1.0.0 注入自建 client，迁移不是可选优化，而是已经发生的 API 合同变化。

## 2. `httpx-ws==0.9.0`：直接兼容性与替代方案

### 2.1 它仍然建立在旧 HTTPX 栈上

`httpx-ws==0.9.0` 没有 HTTPX2 支持声明：

- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx_ws-0.9.0.dist-info/METADATA:21-24`：依赖是 `httpcore>=1.0.4`、`httpx>=0.23.1` 和 `wsproto`，没有 `httpx2`／`httpcore2`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx_ws/_api.py:10-17`：直接 import `httpcore`、`httpx`，并从旧 `httpcore` import `AsyncNetworkStream`／`NetworkStream`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx_ws/_api.py:1374-1386,1450-1453`：`AsyncWebSocketClient` 与 `aconnect_ws` 的 client 类型都写成 `httpx.AsyncClient`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx_ws/transport.py:8-10,193-218`：测试用 `ASGIWebSocketTransport` 继承旧 `httpx.ASGITransport`，请求／响应类型也来自旧 `httpx`。

截至 2026-08-21，GitHub issue／PR 搜索没有发现上游 `frankie567/httpx-ws` 对 `httpx2`、`httpcore2` 或 Pydantic port 的进行中支持；可复核的查询入口是 [`issues?q=httpx2`](https://github.com/frankie567/httpx-ws/issues?q=httpx2)，结果为 0。[`v0.9.0 release`](https://github.com/frankie567/httpx-ws/releases/tag/v0.9.0) 也没有提到 HTTPX2。该负面结论的权重是“足以判断当前没有公开迁移工作，但不能证明私下没有计划”。

### 2.2 为什么 happy path 能跑仍不能算兼容

本机做了一个真实 loopback WebSocket 探针：同一 FastAPI／Uvicorn echo endpoint 依次由 `httpx-ws+httpx`、`httpx-ws+httpx2` 和 HTTPX2 native WebSocket 访问。关键输出如下：

```text
versions: 0.28.1 2.12.0
httpx-ws+httpx: echo:httpx-ws+httpx
httpx-ws+httpx2: echo:httpx-ws+httpx2
httpx2-native: echo:httpx2-native
```

这说明 HTTPX2 2.12.0 在成功握手和正常收发路径上保留了足够相似的接口，`httpx-ws` 可借 duck typing 偶然工作；**它不构成可采用的兼容合同。** 反例已经静态存在：

- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx_ws/_api.py:718-724` 只捕获 `httpcore.WriteError`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx_ws/_api.py:1034-1086` 的后台接收只把 `httpcore.ReadError`／`httpcore.WriteError` 转为 `WebSocketNetworkError`。
- 探针证实 `httpcore.NetworkError is httpcore2.NetworkError` 为 `False`。所以 HTTPX2 网络流抛出的 `httpcore2.ReadError`／`WriteError` 不会进入这些错误归一化分支。
- `httpx-ws` 的 ASGI transport 仍继承旧 HTTPX transport，不能作为 HTTPX2 transport 合同来使用。

因此，“直接传 HTTPX2 client 给 `httpx-ws`”的判定是：happy path 实测可通，但错误语义和测试 transport 不兼容，**不应上线依赖**。证据权重为“强到足以否决该方案”。

### 2.3 首选替代：HTTPX2 自带 WebSocket

HTTPX2 已直接吸收这块能力，不需要等待 `httpx-ws` 发布双栈版本：

- [`HTTPX2 CHANGELOG`](https://github.com/pydantic/httpx2/blob/main/src/httpx2/CHANGELOG.md) 记载 `2.6.0` 于 2026-07-14 通过 PR [`#1042`](https://github.com/pydantic/httpx2/pull/1042) vendoring `httpx-ws` 并加入 native WebSocket，extra 为 `httpx2[ws]`。
- `2.7.0` 在同日把 vendored 代码更新到上游 `httpx-ws 0.9.0`。
- `2.10.0` 又修复了跨 fragmented frames 的最大消息长度执行，以及 unsolicited／duplicate Pong 处理。这意味着 HTTPX2 内置版本实际比原始 0.9.0 多了后续正确性修复。
- 官方 [WebSockets 文档](https://httpx2.pydantic.dev/websockets/) 给出 `Client.websocket()`／`AsyncClient.websocket()`、send／receive、ping、subprotocol、keepalive、异常和 ASGI transport 的完整合同，没有 experimental 警告。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx2/_client.py:1732-1779`：`AsyncClient.websocket()` 是正式公开 async context manager，并在缺少 `wsproto` 时明确要求安装 `httpx2[ws]`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx2/websockets/_api.py:43-55,181-211`：stream 类型和网络异常已经改到 `httpcore2`；这正是外部 `httpx-ws` 不能保证的部分。

本项目当前的接点集中在 `/home/xp/src/ghc-api-proxy-py/src/app/openai/responses_ws.py:4-39`：它把 `httpx.AsyncClient` 交给 `aconnect_ws`。原生 API 的发送／接收形状与当前调用接近，因此替换面明确，不需要另选一套完全不同的 WebSocket 库。备选的 `websockets` 或 `aiohttp` 也能工作，但会引入独立的代理、TLS、auth、timeout 和连接生命周期配置面，不如复用同一个 HTTPX2 client。

## 3. `opentelemetry-instrumentation-httpx` 是否会失效

### 3.1 最新版已支持两套栈，但 instrumentor 是分开的

探针环境解析到 `opentelemetry-instrumentation-httpx==0.65b0`。它同时支持 HTTPX 与 HTTPX2，但不是一个旧 instrumentor 自动覆盖两个包：

- [`opentelemetry-python-contrib` CHANGELOG](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/CHANGELOG.md) 记载 2026-07-16 的 `1.44.0/0.65b0` 通过 PR [`#4730`](https://github.com/open-telemetry/opentelemetry-python-contrib/pull/4730) 加入 HTTPX2 支持。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/opentelemetry/instrumentation/httpx/package.py:4-8`：依赖能力声明同时包含 `httpx>=0.18.0` 与 `httpx2>=2.0.0`。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/opentelemetry/instrumentation/httpx/__init__.py:443-451`：模块分别 import `httpx` 和 `httpx2`。
- 同文件 `:1277-1312`：instrumentor 按自己的 `_module_name` 分别 wrap 对应包的 `HTTPTransport`／`AsyncHTTPTransport`。
- 同文件 `:1796-1802,1821-1826`：`HTTPXClientInstrumentor` 绑定模块名 `httpx`，`HTTPX2ClientInstrumentor` 绑定模块名 `httpx2`。

本机真实 HTTP loopback 探针先只启用旧 instrumentor，再同时启用两个，输出如下：

```text
legacy-instrumentor-only: 1 ['http://127.0.0.1:36617/probe']
both-instrumentors: 2 ['http://127.0.0.1:36617/probe', 'http://127.0.0.1:36617/probe']
```

每轮都分别发送一条 `httpx.get()` 与一条 `httpx2.get()`。只启用 `HTTPXClientInstrumentor` 时只有旧 HTTPX 请求生成 span；再启用 `HTTPX2ClientInstrumentor` 后两条都生成 span。

### 3.2 对本项目的直接影响

`/home/xp/src/ghc-api-proxy-py/src/app/observability/tracing.py:8-18` 当前只 import 并启用 `HTTPXClientInstrumentor`。因此：

- 如果业务请求整体改成 HTTPX2，而 tracing 初始化不改，**HTTPX 相关出站 trace 会静默整体消失**。
- 如果迁移时同步改成 `HTTPX2ClientInstrumentor`，trace 能继续工作，不存在库级阻断。
- 如果分阶段双栈共存，应同时启用 `HTTPXClientInstrumentor` 与 `HTTPX2ClientInstrumentor`；二者有独立的 instrumented 状态和 patch 目标。

这里的判定是“强到足以据此行动”，因为源码 patch 点和导出 span 的运行结果一致。

## 4. 同一进程双栈共存是否可行

### 4.1 依赖解析与运行时没有已知硬冲突

双栈共存是可行的，而且当前探针环境已经这样运行：

- `httpx==0.28.1` 依赖 `httpcore==1.*`；见 `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx-0.28.1.dist-info/METADATA:27-30`。
- `httpx2==2.12.0` 依赖名称不同且精确匹配的 `httpcore2==2.12.0`；见 `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx2-2.12.0.dist-info/METADATA:29-35`。
- `httpcore2` 自己声明 asyncio 与 Trio 后端支持；见 `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpcore2-2.12.0.dist-info/METADATA:30-39,58-65`。两栈共享 AnyIO／h11／h2 一类底层库，但探针解析结果满足双方约束，没有 resolver 冲突。

对象身份探针输出：

```text
modules: httpx=0.28.1 httpx2=2.12.0 httpcore=1.0.9 httpcore2=2.12.0
client classes identical: False
core exception classes identical: False
transport classes: legacy=httpx.AsyncHTTPTransport modern=httpx2.AsyncHTTPTransport
pools: legacy=httpcore.AsyncConnectionPool modern=httpcore2.AsyncConnectionPool
```

这意味着两套 client、transport、pool 和异常家族完全分开。它们能在同一个 asyncio 或 Trio 进程里并存，但不能跨栈共享 transport、pool、response、exception 或配置对象。前述 WebSocket loopback 探针也在同一 asyncio event loop 中依次成功使用两套 client，给出了运行时正证据。

### 4.2 TLS／SSL context 是行为差异，不是共存冲突

- 旧 `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx/_config.py:31-40` 默认用 `certifi.where()` 创建 trust context。
- 新 `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx2/_config.py:31-40` 默认通过 `truststore.SSLContext` 使用系统 trust store。

两者各自在自己的 connection pool 中持有 SSL context，不会互相覆盖；但是同一目标在企业 CA、自签 CA 或容器证书环境下可能出现“一边成功、一边失败”。这需要作为迁移行为差异验证，而不能当成 package conflict。显式传入的 `ssl.SSLContext` 也必须交给对应栈自己的 transport／client，不能假设 HTTPX 类型对象跨栈等价。

### 4.3 禁止在共存方案中调用 `alias_httpx()`

`/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx2/_alias.py:58-71` 的 `alias_httpx()` 会把进程级 `import httpx`／`import httpcore` 都改指向 `httpx2`／`httpcore2`，而且要求在任何旧包 import 前调用。它适合“一次性把仍写旧 import 的依赖整体重定向”这一类应用迁移，不适合“自己的出站 client 用 HTTPX2，而 `httpx-ws` 继续用真实旧 HTTPX”的双栈方案。调用 alias 后，所谓旧路径已经不再是真实旧栈，不能再据此主张共存。

### 4.4 可行的阶段性折中

可以采用以下边界清晰的阶段状态：

1. 普通出站请求、OpenAI client、Anthropic client 使用 `httpx2.AsyncClient`。
2. `httpx-ws` 路径继续持有独立的 `httpx.AsyncClient`，不把 HTTPX2 client 传进去。
3. tracing 同时启用两个 instrumentor。
4. 两套 pool 分别关闭，不跨栈复用 transport、exceptions 或 response 类型。
5. 随后尽快把 WebSocket 路径切到 HTTPX2 native WebSocket，删除阶段性的旧 pool 和旧依赖。

这个折中没有已知技术硬冲突，但会暂时增加一个连接池、一套 TLS 默认值、一套异常类型和一套 tracing patch，属于迁移成本而非长期理想架构。

## 5. 生态成熟度与行动倾向

### 5.1 HTTPX2 是正式发布，不是未发布过渡物；但它仍然年轻

正式性证据：

- [PyPI `httpx2`](https://pypi.org/project/httpx2/) 当前为 `2.12.0`，2026-08-18 发布，classifier 是 `Development Status :: 5 - Production/Stable`，维护者为 Pydantic Services Inc.。
- `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python3.14/site-packages/httpx2-2.12.0.dist-info/METADATA:1-17` 给出相同版本、维护者和 Production/Stable classifier。
- 同一 metadata 的 `:62-67` 将 HTTPX2 定义为原 HTTPX 工作的 continuation，理由是旧 HTTPX 活跃度有限，由 Pydantic 接手 stewardship、维护稳定演进和及时更新。
- PyPI release JSON 的实查结果是：`2.0.0` 首次上传于 2026-05-12，`2.6.0`／`2.7.0` 于 2026-07-14，`2.10.0` 于 2026-08-09，`2.12.0` 于 2026-08-18。

成熟度判断：它不是 beta 或临时占位包，但正式历史只有约三个月，三个月内从 2.0 到 2.12，WebSocket 又是 7 月才加入、8 月仍有协议正确性修复。这个发布速度同时说明维护活跃与接口周边仍在快速收敛。故不能仅凭 Production/Stable classifier 推导所有扩展工具都成熟。

### 5.2 主流跟进呈“核心 SDK 和 tracing 已到位，外围测试／mock 工具仍不齐”

已经发布的跟进：

- OpenAI：3.0.0 默认 HTTPX2，3.3.1 继续带临时 legacy runtime path。
- Anthropic：1.0.0 强制 HTTPX2。
- OpenTelemetry：0.65b0 已正式提供独立 `HTTPX2ClientInstrumentor`。
- Sentry：[`sentry-python #6448`](https://github.com/getsentry/sentry-python/issues/6448) 已由 PR #6463 关闭，HTTPX2 支持进入 2.62.0。
- HTTPX2 自身：原生 vendored `httpx-ws`，避免等待外部插件处理双包与循环依赖。

仍在过渡的例子：

- `pytest-httpx` 的 HTTPX2 支持仍是开放 PR [`#239`](https://github.com/Colin-b/pytest_httpx/pull/239)。
- RESPX 原项目没有直接证明现有 `respx` 对 HTTPX2 等价支持；其作者另有 [`pytest-httpx2`](https://github.com/lundberg/pytest-httpx2) 项目。OpenAI migration guide也把 RESPX 仅 patch 旧 HTTPX列为保留 legacy escape hatch 的典型原因。
- HTTPX2 maintainer 在 2026-05-23 的 [discussion #980](https://github.com/pydantic/httpx2/discussions/980) 中称 MCP、Starlette “are moving to httpx2”，Stainless 也已参与协调，但当时明确仍有 compatibility 和 typing concern。这是迁移意向证据，不应误写成当时已经发布。

上述抽样足以说明生态方向已经明确，但不足以证明任意 transitive integration 都完成了 HTTPX2 适配。实际迁移应按本项目真实使用的 integrations 逐项核对；本次给定依赖中，唯一需要改路线的是 `httpx-ws`，唯一会静默失效的是 tracing 初始化仍只启用旧 instrumentor。

### 5.3 现在迁移与钉死等待的代价

**现在迁移的代价：**

- 全项目大量 `httpx` 类型、exception、transport、MockTransport、ASGITransport 和 response annotations 都要逐步改到新家族；仅改 import 名不等于验证了语义。
- TLS 默认从 certifi 变为系统 trust store，需要在真实部署证书环境验证。
- WebSocket 必须切 native API，不能把成功 happy path 当作 `httpx-ws+httpx2` 的完整兼容证明。
- tracing 初始化必须同步迁移；测试／mock 工具若依赖 patch 旧 `httpx`，需另行确认。
- HTTPX2 仍年轻，后续小版本更新频率可能较高，应保留普通的 dependency update review，而不是无上限漂移。

**先钉死等待的代价：**

- 至少要明确钉住 `anthropic<1`；否则自建旧 `httpx.AsyncClient` 注入已经在 1.0.0 构造阶段失败。OpenAI 若要彻底避免 HTTPX2 默认路径，也要钉 `openai<3`，尽管 3.3.1 目前仍有 runtime-only legacy escape hatch。
- 这会放弃两个 SDK 的后续功能、修复和 API 演进，并把迁移压力推迟到临时兼容层可能删除之后。
- 等待 `httpx-ws` 本身跟进缺少公开 issue／PR 支撑，而且 HTTPX2 maintainers 已选择 vendoring，不存在强信号表明外部包会提供双栈版本。
- 等待不会消除 TLS、类型、异常和 tracing 的迁移差异，只会延后处理。

### 5.4 最终倾向

**倾向：现在迁移，但按双栈过渡而不是一次性全局替换；最终目标是纯 HTTPX2。** 理由按权重排序如下：

1. Anthropic 1.0.0 已经把 HTTPX2 变成强制 client 合同，这是立即存在的兼容压力。
2. OpenAI 3.x 默认 HTTPX2，legacy 支持明确只是可能删除的迁移 aid。
3. OpenTelemetry 0.65b0 已有正式双 instrumentor，trace 不需要等待上游。
4. 最大疑点 `httpx-ws` 已由 HTTPX2 原生 vendoring 解掉，而且内置版本比 0.9.0 多后续修复。
5. 双栈在 package、core、pool 和 async backend 层面实测可共存，允许把迁移拆成可控小片，而不是赌一次性替换。
6. 继续等待的收益主要是外围工具再成熟一些，但本项目给定生产依赖已经没有必须等待的上游；与之相对，钉旧 Anthropic／OpenAI 的维护成本和未来迁移风险是确定的。

最终“阻断项”表述应保持两层：**直接把整个项目的 `httpx` import／client 原地换成 `httpx2`、同时原样保留 `httpx-ws 0.9.0`，有阻断项；采用 HTTPX2 native WebSocket 并切换 OTel instrumentor 的整体迁移，没有不可绕过的阻断项。**

## 附录：本次实际探针

所有命令均从 `/home/xp/src/ghc-api-proxy-py` 显式绑定目录运行，解释器为 `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/bin/python`，未修改仓库代码。报告本身是唯一新建文件。

### SDK client 接受性

核心操作：分别创建 `httpx.AsyncClient()` 与 `httpx2.AsyncClient()`，传给 `openai.AsyncOpenAI` 和 `anthropic.AsyncAnthropic`，记录构造成功／异常及 SDK `_client` 实际类型；随后构造三种 SDK default wrapper 并执行 `isinstance`。

输出已完整摘录在第 1 节。

### WebSocket 兼容性

核心操作：启动绑定 loopback 随机端口的 FastAPI／Uvicorn echo WebSocket，在同一 asyncio loop 中依次运行 `aconnect_ws(..., httpx.AsyncClient())`、`aconnect_ws(..., httpx2.AsyncClient())`、`httpx2.AsyncClient().websocket(...)`，每条路径发送一条文本并读取 echo。

输出已完整摘录在第 2 节。这个探针只证明成功路径；错误类型不匹配由源码与 exception identity 探针否决，未把 happy path 过度推广成完整兼容。

### OpenTelemetry 分辨性

核心操作：启动 stdlib `ThreadingHTTPServer`，安装 in-memory span exporter；第一轮只启用 `HTTPXClientInstrumentor`，第二轮再启用 `HTTPX2ClientInstrumentor`；每轮各发送一条旧 HTTPX 和 HTTPX2 请求并统计 exported spans。

输出已完整摘录在第 3 节。

### 双栈对象身份

核心操作：同时 import `httpx`、`httpx2`、`httpcore`、`httpcore2`，检查 client class、network exception class、transport class 与 pool class identity。

输出已完整摘录在第 4 节。
