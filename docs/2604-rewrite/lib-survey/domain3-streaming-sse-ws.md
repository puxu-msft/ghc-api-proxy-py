# 域3：流式 / SSE / WebSocket 传输

## 概览结论表

| 自研点(模块/文件) | 候选库 | 匹配度 | 威胁硬约束? | 推荐 | 理由 |
|---|---|---|---|---|---|
| 出站 SSE 响应构建 `streaming/sse.py` | `sse-starlette`（`EventSourceResponse`） | 高 | 否 | **部分替换**（借用响应构建 + 内建 ping，事件格式化自行保留） | 逐 event 直通、无整体缓冲，内建可配置 ping，但 `ping` 是裸 `event: ping`，不满足本项目 `empty_text` 语义 keepalive 的需求，仍需自建 keepalive 帧生成逻辑接到生成器里 |
| 上游 SSE **解析**（累积器读上游流） | `httpx-sse`（`aconnect_sse`/`EventSource`） | 低 | **是**（与"原始字节直通转发+旁路累积"冲突） | **保留自研** | `iter_sse()`/`aiter_sse()` 只产出解析后的 `ServerSentEvent`，不提供原始字节旁路钩子；采用会强制走"先解析再重新序列化转发"，破坏保真度（未知字段可能被吞），且与当前"原始字节直通、累积器旁路只读"的架构相悖 |
| `streaming/idle_timeout.py` | `anyio.fail_after` / 标准库 `asyncio.timeout` | 高 | 否 | **部分替换**（用 `anyio.fail_after` 或 `asyncio.timeout` 替代手写 `asyncio.wait_for` 循环，逻辑结构基本不变） | 语义等价，`anyio` 版本可选（多后端），标准库 `asyncio.timeout`（3.11+）已够用；本项目 Python 3.14，两者皆可，无需引入 `anyio` 仅为这一处 |
| `streaming/keepalive.py` | sse-starlette 内建 `ping` | 低 | 否（不威胁，但功能不匹配） | **保留自研** | sse-starlette 的 ping 只支持固定字符串 payload 的裸 `event: ping`，无法实现 `empty_text` 模式（block-aware 的 `content_block_delta`/`thinking_delta` 空 delta）——这正是本项目验证过唯一能压住 300s no-real-content watchdog 的方案，库能力覆盖不了业务需求 |
| `streaming/delayed_commit.py` | 无直接候选，`asyncio.wait_for`/`asyncio.shield`（标准库）已是最小实现 | 高（本来就是标准库用法） | 否 | **保留自研**（本质是编排逻辑，非通用机制） | 这是本项目特有的"窗口内 settle 与否决定 HTTP 状态码转发方式"的业务编排，不存在对应的现成库抽象；标准库 `asyncio.wait_for`+`shield` 已是恰当工具，无需引入第三方库 |
| `streaming/buffered_retry.py` | 无直接候选 | 高 | 否 | **保留自研** | all-or-nothing 缓冲重试语义、`buffer_cap_bytes` 熔断退化为 live 直写，属业务特定编排，无通用库覆盖 |
| Responses WS transport（`routes/responses.py`，服务端） | FastAPI/Starlette 内建 `WebSocket` | 高 | 否 | **维持内建**（非第三方库，FastAPI 已含） | 服务端 WS（`@router.websocket`）已是 Starlette/FastAPI 一等公民，无需引入额外库；当前设计已经这样用 |
| 上游侧 WS 客户端（代理→上游 Responses WS 变体） | `httpx_ws`（`aconnect_ws`） | 高 | 否 | **推荐采用** | 与 httpx 生态原生协调（接受 `httpx.AsyncClient`，走同一 transport/代理配置），提供逐消息异步迭代（非整体缓冲）、内建可配置 keepalive ping/timeout，比手写 `websockets`/`wsproto` 客户端更省代码且行为一致 |
| 上游侧 WS 客户端（备选） | `websockets` | 中 | 否 | **不采用**（次选） | 成熟度最高（16.1，5700★），但是独立于 httpx 的连接/代理/TLS 配置体系，会造成"HTTP 用 httpx 连接池 + WS 用另一套连接管理"的双轨维护成本，除非 `httpx_ws` 出现阻塞性缺陷否则不采用 |
| 上游侧 WS 客户端（备选） | `wsproto` | 低 | 否 | **不采用** | 纯协议状态机（sans-I/O），需要自己接 I/O 循环，`httpx_ws` 内部就是构建在 `wsproto` 之上（见下）——直接用 `httpx_ws` 收益更高，没必要绕过它直接用底层协议库 |

## 逐项详述

### 出站 SSE StreamingResponse 构建（`streaming/sse.py`）

**现状**：[streaming.md](../streaming.md#sse-流式处理) 描述 `create_sse_response()` 手写 `StreamingResponse` 包装，`format_sse_event()` 手写 SSE 帧格式化（`event:`/`data:` 行 + 双换行终止符）。项目结构见 [project-structure.md](../project-structure.md#streaming--流式处理) `sse.py` 职责为"SSE StreamingResponse 构建工具，逐事件直通"。

**候选库：`sse-starlette`**
- 版本：3.4.5（PyPI，2026-06-20 发布）；GitHub `sysid/sse-starlette`，838★，最近 push 2026-07-12，活跃维护。
- 许可证：BSD-3-Clause。
- 依赖：`starlette>=0.49.1`、`anyio>=4.7.0`；`requires-python>=3.10`（3.14 兼容，纯 Python 无 C 扩展）。
- 类型注解：参数表带类型标注（`ContentStream`、`anyio.Event`、`float` 等）。
- 异步原生：核心基于 async/await，支持多事件循环、线程安全（README 明示）。
- 能力核对：
  - `EventSourceResponse(content: AsyncGenerator | Iterable, ...)`：逐 `yield` 推送，无整体缓冲；文档特别提示的"缓冲"风险是**下游 Nginx** 累积（约 16KB 阈值），非库本身行为，解法与本项目已用的 `X-Accel-Buffering: no` 头一致。
  - 支持三种 payload 形态：`ServerSentEvent(data=..., event=..., id=..., retry=...)`、`JSONServerSentEvent`、直接 yield dict（`{"data":..., "event":..., "id":...}`）。`sep` 参数可控制换行符风格。
  - 内建 `ping`（默认 15 秒，可设 0 禁用）+ `ping_message_factory` 自定义 payload；但自定义仅限于"裸 ping 帧内容"，不支持"生成一个匹配当前打开 block 类型的 `content_block_delta`"这种依赖流式上下文状态的逻辑——这必须在业务生成器层面自己插入。
  - 内建客户端断连检测（`request.is_disconnected()` 循环 + `CancelledError`），本项目当前手写实现可省略。

**是否威胁 P1/P6/保真度**：不威胁。零缓冲逐 event 直通，且是本项目已经追求的默认行为，二者语义一致。

**推荐：部分替换**。用 `EventSourceResponse` 替代手写 `create_sse_response`/`StreamingResponse` 包装，省掉响应头模板与断连检测的手写代码；但 `streaming/keepalive.py` 的 `empty_text` 模式逻辑必须保留自研（在业务生成器内产出该帧，而不依赖 sse-starlette 的 `ping` 参数），因为这是唯一被验证能压住 300s no-real-content watchdog 的机制，库的 ping 能力覆盖不了。`format_sse_event()` 的手写格式化函数可保留或替换为 `ServerSentEvent`/dict yield 形式，两者等价，选哪个是代码风格问题，不影响结论。

### 上游 SSE 解析（累积器读上游流）

**现状**：[streaming.md](../streaming.md#stream-accumulator) 描述各协议 accumulator（`AnthropicStreamAccumulator` 等）在**转发的同时**旁路累积完整响应用于 History，`process_event(event_type, data)` 接口暗示上游 SSE 已被解析为结构化事件后再喂给累积器。核心诉求（见 briefing 硬约束）是"原始字节直通转发 + 旁路累积"——即转发路径**不应**因为需要累积而被迫先完整解析再重新序列化。

**候选库：`httpx-sse`**
- 版本：0.4.3（PyPI，2025-10-10 发布）；GitHub `florimondmanca/httpx-sse`，210★，最近 push 2025-12-13（对比之下比其他候选更新慢半年，但项目本身 API 面很小，稳定不等于不活跃）。
- 许可证：MIT。`requires-python>=3.9`，纯 Python，3.14 兼容。
- 官方文档自称 **beta software**，建议 pin 到 `httpx-sse=="0.4.*"`——成熟度信号偏弱。
- 类型注解完整（`ServerSentEvent` 字段带类型，`event: str`/`data: str`/`id: str`/`retry: str | None`，附 `.json()` 方法）；异步原生（`aconnect_sse` + `aiter_sse()` 配合 `httpx.AsyncClient`）。
- 能力核对：`EventSource(response: httpx.Response)` 包装 httpx 响应，`iter_sse()`/`aiter_sse()` **解码响应内容并产出解析后的 `ServerSentEvent`**——这是它唯一的消费入口，没有暴露"边解析边拿原始字节"的双通道 API。README 及源码均未提供在解析同时旁路获取未修改字节流的机制。

**是否威胁 P1/P6/保真度**：**威胁保真度**（P6 相邻约束）。采用 `httpx-sse` 意味着转发路径必须先把上游字节完全解析为 `ServerSentEvent` 对象，再从字段重新构造转发给客户端的 SSE 帧——这是一次"解析→重编码"往返，而非本项目要求的"原始字节直通、累积器只读旁路"。重编码路径上，任何 `httpx-sse` 未识别或未覆盖的字段（如 thinking signature、server_tool 块的嵌套结构、未来上游新增的事件类型）都可能在重建时丢失或被规范化改写，与 briefing 明确要求的"SSE 未知字段/未知块不能被库擅自吞掉或重编码破坏"直接冲突。此外它不支持流内同时读取原始字节，若要保留直通字节，代码必须绕开 `iter_sse()`，直接用 `response.aiter_bytes()` 自行解析——等于放弃了这个库的核心价值。

**推荐：保留自研**。当前架构需要的是"一份原始字节流，同时喂给：(a) 直通转发 (b) 累积器解析"，`httpx-sse` 的设计前提是"我是唯一的消费者，直接产出结构化事件"，与此不兼容。自研的轻量 SSE 逐行解析器（拆 `event:`/`data:`/空行分帧）足够简单、可控，且天然保留原始字节转发路径不被库接管。若未来重构成"先转发原始字节，再单独起一个只读的 `httpx-sse` 解析流水线消费同一份内容"（例如通过 `anyio` 内存流 tee 成两路），可以重新评估，但当前不建议为此改变数据流架构。

### `streaming/idle_timeout.py`

**现状**：[streaming.md](../streaming.md#流空闲超时) `with_idle_timeout()` 用 `asyncio.wait_for(stream.__anext__(), timeout=...)` 包装迭代器，超时抛 `StreamIdleTimeoutError`；支持 per-model 覆盖（`resolve_stream_idle`），流开始时解析一次。

**候选库：`anyio`（`fail_after`）/ 标准库 `asyncio.timeout`**
- `anyio` 版本 4.14.2（PyPI，2026-07-12 刚发布），GitHub `agronholm/anyio` 2505★，push 2026-07-14，非常活跃；MIT 许可证；`requires-python>=3.10`；类型注解完整、原生 async（asyncio + trio 双后端）。项目已通过 FastAPI/Starlette 间接依赖 `anyio>=4.7`，属于"已在依赖树里"的库。
- `anyio.fail_after(delay)` 是一个 async context manager，超时抛 `TimeoutError`（3.11+ 与标准库 `asyncio.TimeoutError` 统一），可包裹 `await stream.__anext__()` 单次调用，语义与当前 `asyncio.wait_for` 完全等价；也可用标准库 `asyncio.timeout(delay)`（3.11 引入，3.14 项目下必然可用）。
- 二者均是"包裹单次 await 加超时"的通用机制，不是"流式 idle timeout"专用库——没有现成的"迭代器加空闲超时"包装器可以整体替换 `with_idle_timeout` 函数体，本质还是需要自己写这层 `async for` + `try/except TimeoutError: raise StreamIdleTimeoutError` 的循环。

**是否威胁 P1/P6/保真度**：不威胁，纯超时控制，不缓冲、不改变事件内容。

**推荐：部分替换**（保留自研的迭代器包装函数结构，只把内部超时原语从手写 `asyncio.wait_for` 换成 `asyncio.timeout`/`anyio.fail_after`）。是否引入 `anyio.fail_after` 而非直接用标准库 `asyncio.timeout`，取决于项目是否已决定在其他地方系统性采用 `anyio` 的跨后端抽象（比如若上游侧 WS 客户端采用 `httpx_ws`，`httpx_ws` 本身依赖 `anyio`，届时 `anyio` 已在依赖树，用 `anyio.fail_after` 保持一致风格是合理选择）；仅为这一处则标准库 `asyncio.timeout` 已经足够，无需为此单独引入 `anyio` 作为直接依赖。**结论对整体设计不构成阻塞，两种写法均可，建议主会话统一风格决策**。

### `streaming/keepalive.py`

**现状**：[streaming-resilience.md](../streaming-resilience.md#2-keepalive-心跳-采纳) 描述三种模式（`empty_text` 默认/`ping`/`enveloped_ping` 已拒绝），核心是 `empty_text` 模式需要感知"当前打开的 content block 类型"（`thinking`/`text`/`tool_use`），动态构造匹配类型的空 delta 帧，且延迟提交窗口耗尽后需要"懒注入合成 message_start + 空 text 锚点块"。

**候选库：sse-starlette 内建 ping**：见上一节分析，`ping_message_factory` 只能定制**固定内容的裸 ping 帧**，不能实现依赖运行时状态（当前打开块类型、是否已注入过锚点）的动态 keepalive 逻辑，也不满足"必须是能被客户端识别为内容事件的 delta 帧"这一核心诉求（sse-starlette 的 ping 本质仍是协议层 `event: ping`）。

**是否威胁 P1/P6/保真度**：不威胁（这不是"库会不会破坏约束"的问题，而是"库能力覆盖不了业务需求"）。

**推荐：保留自研**。`empty_text` 模式与"合成帧的可观测性约定"（转发轨标记 `synthetic`、上游轨绝不包含合成物、块索引重映射）是本项目独有的、深度耦合 Anthropic 协议语义与 Claude Code 客户端 watchdog 行为的机制，没有通用库覆盖这类协议特定的状态机。sse-starlette 的 ping 可作为**逃生舱模式**（对应文档中已规划的 `ping` 模式）的底层实现参考，但不能替代整个 keepalive 子系统。

### `streaming/delayed_commit.py` 与 `streaming/buffered_retry.py`

**现状**：见 [streaming-resilience.md](../streaming-resilience.md#1-延迟提交窗口delayed-commit-上游稳定采纳) 与 [同文档第3节](../streaming-resilience.md#3-缓冲重试buffered-retry-上游实验采纳默认关见-p6)。前者用 `asyncio.ensure_future` + `asyncio.wait_for(asyncio.shield(task), timeout=...)` 实现"窗口内等待 settle，超时后转交后台继续等待"；后者是"整响应缓冲直到终止帧再一次性 flush，遇 transport-close 丢弃重试，超 `buffer_cap_bytes` 熔断退回 live 直写"的 all-or-nothing 状态机。

**候选**：未找到覆盖这两种业务编排的现成库。`asyncio.shield`/`asyncio.wait_for` 本身就是标准库最小原语，无需第三方库。`anyio` 提供 `CancelScope(shield=True)` 是等价能力（`anyio` 的 shield 语义与 `asyncio.shield` 基本对应），若项目决定统一用 `anyio` 抽象可以替换，但不改变"这是业务编排代码，不是可替换的通用机制"这一结论。

**是否威胁 P1/P6/保真度**：`buffered_retry` 本身是 P6 认定的高风险机制（briefing 已明确其内存代价），但这是**设计层面的已知取舍**（默认关、opt-in、16MB 硬顶），不是"库引入的新风险"——因为压根没有候选库可替换它。

**推荐：两者均保留自研**。

### Responses API 的 WebSocket transport

**现状**：[streaming.md](../streaming.md#websocket-transport) 描述服务端 `@router.websocket("/v1/responses")`，复用 HTTP pipeline，SSE 事件→WebSocket JSON 帧桥接；[config-system.md](../config-system.md) `upstream_ws`（默认 `False`）配置项表明**上游**也存在 WebSocket 变体（`ws:/responses`，见 `refs/available_models.json` 中部分模型 `supported_endpoints` 含 `ws:/responses`）。这里拆成两段分别评估：

#### (a) 服务端侧：客户端 ↔ 代理

**候选**：FastAPI/Starlette 内建 `WebSocket`/`WebSocketDisconnect`（已在用，见 [streaming.md](../streaming.md#websocket-transport) 示例代码 `@router.websocket` + `websocket.accept()`/`receive_json()`/`send_json()`）。

**是否需要额外库**：不需要。这属于"FastAPI 自带能力"，不在本次调研的第三方库替换范围内，仅确认现状合理——继续使用内建实现。

#### (b) 上游侧：代理 → 上游 Responses WS 变体（关键调研点）

这是 briefing 明确要求的重点：**代理作为 WS 客户端去连接上游**。

**候选库 1：`httpx_ws`**
- 版本：0.9.0（PyPI，2026-03-28 发布）；GitHub `frankie567/httpx-ws`，151★，push 2026-06-22。维护者 François Voron 是 FastAPI 生态活跃维护者（`fastapi-users` 等），贡献者列表含 httpx 作者 Tom Christie 与 anyio 作者 Alex Grönholm——生态位可信度高，虽 star 数不算大但定位精准（httpx 官方生态圈内的 WS 补完）。
- 许可证：MIT（PyPI classifiers 确认）。`requires-python>=3.10`，3.14 兼容性：纯 Python + 依赖 `wsproto`（纯 Python sans-I/O 库），无 C 扩展阻塞因素，理论兼容，但**未见到官方 3.14 wheel/CI 矩阵的直接确认，建议实装前跑一次真实环境验证**（标记待验证）。
- 依赖：`anyio`、`httpcore`、`httpx`、`wsproto`（源码 `_api.py` import 列表确认）。**与 httpx 生态原生协调**——`aconnect_ws(url, client: httpx.AsyncClient | None, **kwargs)` 直接接受项目已用于上游连接的 `httpx.AsyncClient` 实例，`**kwargs` 透传给 httpx 的 `stream()` 方法，意味着复用同一套连接池/代理/TLS/超时配置，不需要为 WS 连接单独维护一套传输层配置（这对应 briefing 关注的"与 httpx 生态是否协调"）。
- 能力核对：
  - `aconnect_ws()` 返回异步上下文管理器包装 `AsyncWebSocketSession`，逐消息收发（`receive_text()`/`receive_bytes()`/`receive_json()`），非整体缓冲——契合 P6 零缓冲直通精神在 WS 场景下的等价要求。
  - 内建自动 ping/pong（`keepalive_ping_interval_seconds` 默认 20s，`keepalive_ping_timeout_seconds` 默认 20s，可各自设 `None` 禁用），呼应上游保活需求（对应 streaming-resilience.md 第4节的"上游保活"关切，但那节讨论的是 HTTP/2 层，WS 场景下 `httpx_ws` 内建 ping 是独立的等价机制）。
  - `max_message_size_bytes`（默认 65536）、`queue_size`（默认 512，接收队列背压参数）——有界队列，避免无限内存增长，与本项目 P1 类"有界队列防 OOM"的设计哲学一致。
  - 类型注解完整（`_api.py` 大量 `typing` 标注），异步原生（`asyncio`/`trio` 双后端，经 `anyio`）。

**候选库 2：`websockets`**
- 版本：16.1（PyPI，2026-07-10 发布）；GitHub `python-websockets/websockets` 5700★，push 2026-07-14，是该生态**采用度最高、最活跃**的库，且已确认提供 cp314 wheel（含 free-threaded `cp314t` 变体）。许可证 BSD-3-Clause。
- 能力：既可做客户端也可做服务端，功能完备度业界公认最高。
- **不采用理由**：作为纯 WS 库，它有自己独立的连接/TLS/代理配置模型，与 httpx 的 `AsyncClient`/连接池/`upstream.proxy` 配置是两套体系——引入它意味着上游连接管理出现"HTTP 走 httpx，WS 走 websockets"的双轨维护，配置项（超时、代理、TLS 校验）需要分别对齐两套 API，增加长期维护面。除非 `httpx_ws` 出现具体的功能缺口或稳定性问题，`websockets` 只作为**次选/逃生舱**记录在案。

**候选库 3：`wsproto`**
- 版本：1.3.2；GitHub `python-hyper/wsproto` 303★，push 2026-05-23。MIT 许可证。
- 定位是 **sans-I/O** 协议状态机（只处理帧编解码/握手逻辑，不管理实际 socket/事件循环），需要调用方自己接一个 I/O 循环——事实上 `httpx_ws` 的 `_api.py` 就是在 `wsproto` 之上构建的（`import wsproto` 直接出现在其源码里）。
- **不采用理由**：直接用 `wsproto` 相当于重新实现 `httpx_ws` 已经做好的那层 I/O 编排（连接管理、ping/pong 循环、队列背压），没有收益，除非 `httpx_ws` 本身不满足需求且需要更底层的控制粒度。

**是否威胁 P1/P6/保真度**：`httpx_ws` 不威胁——逐消息处理、有界队列、无整体缓冲行为；且与 briefing 关注的"与 httpx 生态协调"高度吻合。

**推荐：采用 `httpx_ws` 作为上游侧 WS 客户端**，替代手写基于 `websockets`/`wsproto` 的自研实现。理由：(1) 原生接受同一 `httpx.AsyncClient`，避免维护第二套连接/代理/TLS 配置；(2) 内建 keepalive ping 覆盖 [streaming-resilience.md](../streaming-resilience.md#4-上游保活补充非应用层-idle) 关注的"上游连接保活"诉求在 WS 场景下的等价物；(3) 有界接收队列、逐消息迭代，符合项目一贯的"有界内存"设计哲学；(4) 类型/异步/许可证均达标。**待验证项**：3.14 环境下的实际安装与运行验证（源码层面无阻塞因素，但未见官方对 3.14 的明确 CI confirmation），建议在选型确认后立即跑一次最小 PoC（连接一个 mock WS echo 服务）作为验收。

## 遗留疑问 / 需主会话或用户裁决的点

1. **sse-starlette 采用范围**：是采纳 `EventSourceResponse` 替代 `create_sse_response`/`StreamingResponse` 手写包装（收益：省样板代码 + 内建断连检测），还是保持现状全部自研（收益：避免引入额外抽象层，`StreamingResponse` 已是 Starlette 一等公民、足够薄）？两者性能与保真度均无差异，是纯粹的"代码组织偏好"决策，建议主会话/用户拍板，不构成阻塞。若采用，需确认 `format_sse_event()` 的输出格式（含未知字段透传）与 `ServerSentEvent`/dict-yield 形式在**跨协议翻译场景**（如 anthropic→responses SSE 帧）下是否等价——因为翻译后的帧可能不是纯 Anthropic 协议标准形态，需要验证 sse-starlette 的字段是否会对非常规内容做隐式处理（如强制 `json.dumps` 某些字段）。
2. **上游 SSE 解析架构是否值得重构以引入 httpx-sse**：当前结论是"保留自研"，因为现有架构是"一份字节流同时喂给直通转发和累积器"。如果未来决定用 `anyio` 内存对象流（`anyio.create_memory_object_stream`）把上游响应体 tee 成两路——一路原始字节直通、一路喂给基于 `httpx-sse` 的独立解析管道——理论上可行，但这是一次不小的数据流重构，且 `httpx-sse` 本身标注 beta、pin 到 `0.4.*`，成熟度不算特别高。建议本次调研范围内不推进此重构，仅记录为未来可选路径。
3. **idle timeout 是否引入 `anyio` 作为直接依赖**：若上游 WS 客户端采用 `httpx_ws`（依赖 `anyio`），`anyio` 事实上已进入依赖树；届时 `streaming/idle_timeout.py` 用 `anyio.fail_after` 还是标准库 `asyncio.timeout` 只是风格统一问题，建议交给主会话在敲定 `httpx_ws` 采用与否后一并决定，不单独作为决策点。
4. **`httpx_ws` 的 3.14 兼容性需要一次实测**：调研阶段只能确认"无 C 扩展、纯 Python 依赖链条"这一间接证据，未找到官方对 Python 3.14 的直接 CI 确认。建议采用前跑一个最小 PoC（`uv add httpx-ws` + 连接本地 mock WS 服务收发一条消息）作为验收，属于常规的"引入新依赖前验证安装可用性"步骤，不构成设计层面的阻塞。
