# 模块划分与职责错位独立体检

> 审计对象：`/home/xp/src/ghc-api-proxy-py`；基准：用户指定的 `main` / `44471c6ceedd8a06a7e0cca480314f8fc205e7c0`。本次仅完成轴线 1：`anthropic/`、`openai/`、`protocols/`、`delivery/`、`streaming/`、`transform/` 的职责边界。未读取被排除的 bridge 架构与实施文档。

## 结论摘要

- 边界最需要收敛的是 Anthropic Messages 与 OpenAI Responses 的双向桥接：转换、流式编排和共享 tool-name 映射目前横跨 `protocols/`、`delivery/`、`openai/`。
- `protocols/anthropic_responses.py` 和 `protocols/responses_anthropic.py` 的命名虽可按源→目标猜测，但未表达 request、complete-response、stream 三种不同职责；后者反向导入前者的 `ToolNameMapper`，使方向边界不闭合。
- `delivery/responses_anthropic_stream.py` 实际承担完整协议桥接，而非仅下游投递，宜移到同一个方向性 bridge 包；`delivery/` 只保留可复用的下游提交与投递抽象。
- `streaming/translator.py` 是 OpenAI Chat→Responses 的协议映射而非 SSE framing；`transform/translator.py` 又存放 OpenAI↔Anthropic payload 映射。两个同名概念分散，且当前仅由测试导入。
- `openai/responses_stream_parser.py` 的语义事实与下游投递解耦声明清楚；`streaming/sse.py` 与 `streaming/openai_sse.py` 的 framing/HTTP streaming 职责也清楚。本轮这两处无边界发现。

## 发现表（轴线 1）

| 位置（file:line） | 怪味类型 | 证据 | 严重度（blocker/major/minor） | 建议处置 |
|---|---|---|---|---|
| `src/app/protocols/responses_anthropic.py:14`、`src/app/protocols/anthropic_responses.py:109-146` | 双向 bridge 的共享状态放在单向模块，方向边界泄漏 | Responses→Anthropic 的 `_convert_function_call()` 通过 `ToolNameMapper.restore()` 还原名称；该 mapper 定义在 Anthropic→Responses 文件，且同文件 `to_wire()` 用于反方向输出。调用者须知道两个文件不是独立转换器。 | major | 新建 `protocols/messages_responses/`：`request.py`（Messages→Responses）、`response.py`（Responses→Messages）、`tool_names.py`（每请求映射会话）；公开 API 使用完整方向名。 |
| `src/app/delivery/responses_anthropic_stream.py:9-31`、`src/app/delivery/responses_anthropic_stream.py:186-298` | 协议桥接错放在 delivery 层 | 该模块同时实例化 Responses parser、解析上游 SSE、派生 Anthropic message id 与 stop reason，并驱动 Anthropic SSE renderer/commit；这是一条 Responses→Anthropic 流式协议适配链，不是通用下游投递。 | major | 移为 `protocols/messages_responses/stream.py`，让它依赖 `delivery` 的投递原语；`delivery/` 不再直接成为 Responses 上游语义的入口。 |
| `src/app/delivery/anthropic_sse.py:11-24` | delivery 对特定上游协议模型的反向依赖 | 通用名称的 `delivery` 实现直接导入 OpenAI Responses 的 `CompletedBlock`、`ResponsesTerminal` 等九个语义类型，同时调用 Anthropic reasoning carrier 和 SSE formatter。 | major | 在下一轮按 giant-file 切分时，将跨协议的语义事件契约下沉至上述 bridge 包，并令 `delivery` 接收其自身定义的投递 DTO/Protocol 或只保留 Anthropic 出站 renderer；不要把 Responses parser 类型作为 delivery 公共边界。 |
| `src/app/streaming/translator.py:5-22` | 协议转换混入 streaming 包 | 函数将 Chat completion 的 `choices/delta/finish_reason` 改写为 `response.*` 事件；未处理字节分帧、SSE 行或背压。`rg` 消费者检查仅命中其单元测试。 | minor | 移至 `protocols/openai_chat_responses.py` 或 `transform/openai_chat_responses.py`，名称明确为 `chat_event_to_responses_event`；若保留为兼容实验，应移至测试 fixture/明确的 compatibility 包。 |
| `src/app/transform/translator.py:6-109`、`src/app/streaming/translator.py:5-22` | 同一“translator”概念跨层、命名不区分输入粒度 | 前者转换完整 Chat/Anthropic payload，后者转换单个 Chat streaming event；两者当前消费者均为测试，生产路由未导入。 | minor | 以“协议对 + 数据粒度”命名模块：例如 `openai_chat_messages.py` 与 `openai_chat_responses_events.py`；先确定哪些是受支持的生产转换，再决定生产包或测试 fixture 归属。 |

## 重构候选（轴线 1）

1. **收拢 Messages↔Responses bridge**：将两个 `protocols/*_responses.py`、`delivery/responses_anthropic_stream.py` 的桥接编排收至 `protocols/messages_responses/`，按 request、complete response、stream、tool-name session 切分。它是最低共同层，因为非流式转换与流式转换都需要相同的方向语义、message-id 与 tool-name 还原；上移到 route 会重复，下沉到 `delivery` 会继续倒置上游依赖。验证：运行 `uv run pytest tests/unit/test_anthropic_responses_request.py tests/unit/test_responses_anthropic_nonstream.py tests/unit/test_responses_stream_parser.py tests/smoke/test_anthropic_responses_stream_route.py`，再运行用户指定 Ruff/Pyright。
2. **确立 delivery 的窄边界**：保留已提交前沿、单 writer、reservation 与 Anthropic SSE 出站投影；将 Responses SSE 解析、terminal usage/stop-reason 派生、上游事件→下游事件驱动移到 bridge stream adapter。最低共同层是所有“上游 Responses→下游 Anthropic”流，而非所有 downstream delivery。验证：现有 `tests/smoke/test_anthropic_block_delivery.py` 加上 stream route smoke 在不改变下游字节和不确定投递状态下通过。
3. **消除 translator 的层名歧义**：把事件级 Chat→Responses 映射与完整 payload 映射按协议对和粒度归档。最低共同层是协议转换，不是 SSE transport；后者仍留在 `streaming/openai_sse.py`。验证：`tests/unit/test_openai_sanitize_accumulators.py` 与 `tests/unit/test_translator.py` 保持通过，并新增一次路由/生产 import 检查或将测试专用代码迁至 fixture。

## 扫描范围与判据（轴线 1）

- 扫描 `src/app/anthropic/`、`openai/`、`protocols/`、`delivery/`、`streaming/`、`transform/` 的文件列表、绝对 `app.<package>` import 图、包 `__init__.py`、关键 bridge 调用链与现有消费者；判据是“模块是否只依赖相邻抽象、文件名是否表达协议方向和数据粒度、协议转换是否与 transport/delivery 责任分离”。
- 使用 Python `ast` 枚举跨顶层包 import，并以 `rg -n --glob '*.py'` 查消费者；AST 图显示 `delivery → anthropic/openai/protocols/streaming`，绝对 import 图另有 `anthropic/history/hooks/pipeline/protocols/upstream` 强连通分量。后者标记 **out-of-axis：依赖环**，本轮不展开。
- 已读 `README.md`、`docs/2604-rewrite/project-structure.md`、以上六包相关源码；未读禁止的 `docs/agents/anthropic-responses-bridge/architecture.md` 与 `implementation.md`。
- 扫了 `openai/responses_stream_parser.py`，判据为“是否渲染 Anthropic wire、推进 delivery frontier 或执行 retry”；其 docstring `src/app/openai/responses_stream_parser.py:142-147` 明确排除这些职责，未发现该局部边界问题。
- 扫了 `streaming/sse.py` 与 `streaming/openai_sse.py`，判据为“是否仅处理 HTTP/SSE framing 与 stream lifecycle”；前者的 `format_sse_event()`、`StreamingResponse` 封装和后者的 `parse_sse_json()` 符合该判据，除 `streaming/translator.py` 外无发现。

## 已执行的独立验证

- `cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src tests`：退出 0。
- `cd /home/xp/src/ghc-api-proxy-py && uv run pyright src tests`：输出 `0 errors, 0 warnings, 0 informations`。

## 未覆盖面

- 顶层散落模块的归属、rolling/generation 部署生命周期包化、巨型文件按职责切分、`pipeline/`/`upstream/`/`routes/` 的边界均按协调者指示留待后续轴线。
- 未对重构后的目标布局实施或验收；本报告提出的是结构候选，不是行为验收结论。


## 轴线 2：顶层散落模块的归属

### 依赖聚类与目标位置

| 内聚组及实际依赖 | 单一职责 | 目标位置与最低共同层 |
|---|---|---|
| `rolling_controller.py:11-24` 依赖 control client、state/frontier store、systemctl 与 tokenization snapshot；`rolling_runtime.py:17-26` 依赖 lifecycle、control server、listener adapter、socket activation、systemd notify。 | 管理 generation 的创建、就绪、接流、quiesce 与停止。 | `deployment/rolling/`：controller、runtime、state、frontier；下一个复用者要实现/运维 rolling generation 会从 deployment 的 rolling 子域找全部编排与持久状态。 |
| `generation.py:53-62` 定义并维护 admission/state machine；`generation_control.py:22-40` 将其以 Unix socket 暴露；`generation_control_client.py:42-73` 消费该协议。 | 以 generation lifecycle 为真相源，提供本地进程控制协议。 | `deployment/generation/`：lifecycle、control_server、control_client；它是 controller 与 generation runtime 共同依赖的最低共同层，而不是 Web route 或 systemd 适配器。 |
| `socket_activation.py:32-103` 验证并复制 systemd listener；`server_adapter.py:44-59` 用其接管 Uvicorn；`systemd_notify.py:12-46` 和 `systemctl_adapter.py:28-82` 是 systemd 两个方向的适配。 | 将 systemd socket/notify/unit API 适配成应用可用的 listener 与控制端口。 | `deployment/systemd/`，其中 `uvicorn_listener.py` 仍是 systemd socket activation 的消费者；下一个 platform adapter 复用者应从同一 infrastructure boundary 找到，而非根包。 |
| `server.py:53-163` 装配生命周期与服务；`runtime.py:23-56` 是其每 app 状态容器；`deps.py:4-15` 用 FastAPI `Depends`/`HTTPConnection` 读取该容器。 | FastAPI composition root、per-app runtime state 与 HTTP dependency adapter。 | `web/`：`app_factory.py`、`runtime.py`、`dependencies.py`；这是 HTTP framework integration 的最低共同层，非业务服务或通用 DI。`cli.py` 保持顶层进程入口，但改为只路由到该包与 `deployment/`。 |
| `errors.py:1-...` 被 models、pipeline、streaming、routes、协议 adapter 消费；`wire_json.py:15-61` 被 OpenAI/Anthropic、streaming、history、tokenization 消费；`generation_identity.py:12-22`、`release_identity.py:12-15` 同时为 rolling、systemctl/control client 与 tokenization snapshot 使用。 | 跨域错误分类、wire JSON 规则与规范化标识符。 | `core/`：`errors.py`、`wire_json.py`、`identifiers.py`；这些均是上层模块的叶子依赖，下一个非领域消费者不会去 `rolling/` 或 `config/` 寻找。 |

### 事实性发现（轴线 2）

| 位置（file:line） | 怪味类型 | 证据 | 严重度 | 建议处置 |
|---|---|---|---|---|
| `src/app/rolling_controller.py:11-24`、`src/app/rolling_runtime.py:17-26` | 一个 deployment 子系统被切成根包平级文件 | 两个入口分别汇聚 generation、control、state、socket、systemd adapter，且 CLI 同时从根导入 controller/runtime（`src/app/cli.py:16-20`）。 | major | 如上建立 `deployment/rolling/`、`deployment/generation/`、`deployment/systemd/` 三层；保留显式 import，不用宽泛 re-export 掩盖依赖。 |
| `src/app/generation_identity.py:12-22`、`src/app/release_identity.py:12-15`、`src/app/tokenization/snapshot_store.py:12-13` | 通用标识符错误归属为 root 的部署邻居 | 两类 parser 既被 generation control/systemctl 使用，也被 tokenization snapshot store 使用；将其放入 `rolling/` 会使 tokenization 反向依赖编排层。 | major | 合并为 `core/identifiers.py`，或等价的无上层依赖 identity 包；保持两个公开函数，避免为移动而改变 ID contract。 |
| `src/app/server.py:53-163`、`src/app/runtime.py:23-56`、`src/app/deps.py:4-15` | FastAPI composition root 与框架 DI 散在根包 | server 的 lifespan 写入 `RuntimeState`；deps 直接依赖 FastAPI/Starlette 并返回该状态。三者实际是一组 Web adapter，而非独立 app-level utilities。 | major | 收拢到 `web/`，并让 routes 只依赖 `web.dependencies`；`server.py` 可保留临时 compatibility facade 后再迁移测试。 |
| `src/app/socket_activation.py:32-103`、`src/app/server_adapter.py:44-59`、`src/app/systemd_notify.py:12-46` | 底层平台适配器与业务编排同级 | listener 从 systemd env 构建，Uvicorn adapter 消费该 listener，notify 直接向 `NOTIFY_SOCKET` 发送 datagram；三者都是 platform boundary。 | major | 归入 `deployment/systemd/`；`rolling_runtime` 作为上层协调者注入/调用，不能反过来由 adapter 知道 rolling policy。 |
| `src/app/graceful_timeout.py:1-5`、`src/app/config/settings.py:8` | 配置默认值置于无语义的根模块 | `AppSettings` 导入默认 graceful timeout；同模块另含 systemd stop margin，概念上混合应用配置与 unit 预算。 | minor | `config/shutdown.py` 持有应用 drain 默认；`deployment/systemd/timeouts.py` 从它派生 unit stop timeout。 |
| `src/app/shutdown.py:12-38`、`src/app/repetition_detector.py:10-41` | 顶层生产模块没有生产消费者 | 本轮 `rg` 范围为 `src/` 与 `tests/`：两者仅命中各自定义和 unit tests，未见 `src/` 非自身消费者。 | minor | 先由用户裁决“将接入生产路径”或“明确为测试支持代码”；前者按真实生命周期/流处理域安置，后者移到 tests support，勿保留伪生产 root API。 |

### 扫描范围与判据（轴线 2）

- 用 Python `ast` 枚举根模块间的 `from app.<root> import`，并用 `rg -n --glob '*.py'` 在 `src/`、`tests/` 交叉查消费者；关键 import 段已逐条打开复验。判据是“高层编排依赖低层 adapter，跨域叶子不依赖编排，下一复用者能由包名定位责任”。
- 扫了 `cli.py`、`server.py`、`runtime.py`、`deps.py`、rolling/generation/systemd 全部列名模块，以及 `errors.py`、`wire_json.py`、`repetition_detector.py`、`graceful_timeout.py`、`shutdown.py`；未发现 `errors.py`、`wire_json.py` 自身的职责混合，建议移动仅为建立显式 core 层，不是正确性缺陷。
- **out-of-axis：** `rolling_controller.py` 同时含 rollout 编排、environment materialization 与 tokenization canonical snapshot 发布（`src/app/rolling_controller.py:307-451`）；这是巨型文件职责切分，留给轴线 3。


## 轴线 3：巨型文件职责切分

### `delivery/anthropic_sse.py`

- AST 分布：sink contracts `152-184`，闭合 source prefix 排序 `187-264`，accepted/uncertain delivery frontier `267-400`，Anthropic SSE projection `403-588`，single-writer session/lease/ack lifecycle `591-1029`。这些对象分别维护不同状态集合，不能以“都在 delivery”视为同一职责。
- 建议切为 `delivery/contracts.py`（`DeliveryWriter`、`DeliverySink`、`RenderedBatch`、`TerminalUsage`；职责是描述下游写入与批次，消费者为 renderer、session、测试）、`delivery/frontier.py`（`DeliveryFrontier`、`CommittedBlock`；职责是记录已接受/不确定的下游可见性，消费者为 session 和 `ResponsesAnthropicStreamState`）、`delivery/anthropic_renderer.py`（`AnthropicSseRenderer`；职责是把一个完成 block 或 terminal 投影为 Anthropic SSE，消费者为 session）、`delivery/session.py`（`DeliverySession`；职责是单 writer 下原子协调 render/write/ack/lease）。
- `ContinuousPrefixSequencer`（`187-264`）的消费者应是 Messages↔Responses stream bridge，而不是通用 delivery：它以 Responses `SourceOpened`/`CompletedBlock` 为输入。这个边界稳定，因为“closed upstream source 的连续前缀”是上游协议完成性规则；它不应随 Anthropic SSE wire 格式、下游 ack 或 resident accounting 改动。
- 不建议再拆 `DeliverySession:591-1029`：其 pending batch、writer、frontier、lease、close 状态由同一 lock 和相同 ack 原子性约束，拆开会将单 writer/uncertain-delivery 不变量变成跨对象协调。

### `openai/responses_stream_parser.py`

- AST 显示所有可变字段在 `ResponsesStreamParser.__init__:149-166`；事件分派 `173-223`、三类 item draft 的增量/完成处理 `225-616`、从 item done 回填 message `674-764`、identity/terminal/open-block 校验 `766-970`、低层 shape validator `973-1027` 都读写同一 attempt-local draft 集合。
- 结论：**不应按当前方法群切成多个 parser。** `text`、`function_call`、`reasoning` handlers 共享 `_items`、source/completion order、terminal 与 open-block snapshot；拆成独立 parser 会要求外部重建 event ordering 和 item identity 不变量。文件长但核心状态机内聚，且类 docstring `142-147` 已明确不承担 render、delivery frontier、retry。
- 可做的窄提取：将 `BlockIdentity` 至 `ResponsesSemanticEvent`（`11-76`）和 `ResponsesStreamProtocolError`（`79-83`）移至 `openai/responses_stream_contract.py`；职责是定义 parser 输出事实，消费者为 parser、Messages↔Responses stream bridge 与 delivery-facing adapter。边界稳定，因为这些不可变 DTO 不拥有 drafts 或 wire rendering。
- 可选同文件私有整理：保留单一 parser，但将 `_require_*`/`_optional_*`/`_fail`（`973-1027`）提取为私有 `validation.py`，职责仅为 Responses event shape 断言；消费者仅 parser。不要把 per-item completion 逻辑拆走。

### `protocols/anthropic_responses.py`

- AST 分布：转换 facts/capability/tool-name DTO 与 mapper `53-160`，orchestrating converter `163-215`，reasoning policy `251-351`，message/content-block lowering `353-532`，tools/tool-choice/metadata lowering `534-611`，field whitelist/validation/fact recording `623-665`。
- 建议在轴线 1 的 `protocols/messages_responses/` 中按稳定协议子域切为 `contract.py`（facts、capability、converted request、errors，消费者为 request converter、client、tests），`tool_names.py`（mapper，消费者为 request 及 reverse response converter），`request.py`（入口和 `_RequestConverter` orchestration），`reasoning.py`（`251-351`，职责是 Anthropic thinking capability→Responses reasoning wire），`content.py`（`353-532`，职责是 messages/blocks→Responses input items），`tools.py`（`534-595`，职责是 tool declaration/choice→Responses tools）。
- 该切法不是按大小：reasoning 仅依赖 capability facts，content 仅处理 message/block 表达，tools 仅处理 tool namespace；三者的共同消费者是 `request.py`。新增 block 类型不应迫使 reasoning 或 tool choice 改动，反之亦然。field validation `623-665` 保持 request 私有，因其错误路径与 converter facts 绑定。

### `pipeline/executor.py`

- AST 分布：result/error contracts `40-60`，non-stream wire validation `63-79`，failure finalization（context、hooks、history）`82-123`，hook-aware preparation `126-193`，主执行器 `196-513`；主执行器内部还混合 approval `219-235`、retry/attempt transport `242-345`、non-stream body/hook/normalization `358-435`、success/failure observer/history finalization `436-512`。
- 建议切出 `pipeline/preparation.py`（`_hook_context`、`_prepare_with_hooks`；职责是将 request hooks、sanitize、route preparation 产出 prepared request，消费者为 executor），`pipeline/finalization.py`（`_finalize_failure` 及成功完成 observer/history 代码；职责是一次性结算 `RequestContext` 与 observers/history，消费者为 executor），`pipeline/nonstream_response.py`（`63-79` 与 `358-435`；职责是读取、response-hook、验证和归一化成功的非流式 body，消费者为 executor）。
- 保留 `execute_anthropic_pipeline:196-513` 为唯一 orchestration/retry owner：它持有 attempt、rate limiter、approval、retry strategy 和状态转移的顺序契约；把这些拆成互相调用的“handlers”会分散失败路径和 retry ownership。稳定边界是 stream 与 non-stream 的响应处理已经由 `request.stream` 在 `360` 分叉，而 preparation/finalization 的调用方始终是同一 executor。

### 轴线 3 扫描范围、判据与未覆盖面

- 对四个指定文件以 Python `ast` 读取顶层类/函数及 `lineno-end_lineno`，并逐段打开源码复验；判据是“是否共享同一可变状态、不变量或协议子域”，不是物理行数。
- 三轴合计已扫：顶层协议/streaming/delivery/transform 边界；根模块 rolling、generation、systemd、web、core 归属；以上四个巨型文件。用户列明但本轮未切分的 `rolling_controller.py` 与 `delivery/responses_anthropic_stream.py` 保留为未覆盖的巨型文件职责切分。
- 未做行为修改、目标布局迁移或迁移后验收；建议的消费者是按当前 import/call graph 推导，实施时需先保留兼容 import 或同步迁移生产与测试 import。


### 事实性发现（轴线 3）

| 位置（file:line） | 怪味类型 | 证据 | 严重度 | 建议处置 |
|---|---|---|---|---|
| `src/app/delivery/anthropic_sse.py:152-1029` | 四个独立状态域共置 | sink、source sequencer、delivery frontier、Anthropic renderer、session/lease 生命周期分别拥有不同可变状态与消费者。 | major | 按 contracts/frontier/renderer/session 拆分；Responses prefix sequencer 随 bridge 移动。 |
| `src/app/openai/responses_stream_parser.py:149-1027` | 长但内聚的单状态机 | 所有 event handler 共享 item/text/function/reasoning drafts、order、terminal 与 open-block snapshot。 | minor | 不拆 parser；仅抽不可变 contract 与可复用 shape validation。 |
| `src/app/protocols/anthropic_responses.py:251-611` | 三个独立协议子域搭车 | reasoning、content block、tools/tool-choice 的输入模型与变更原因独立，仅由 request converter 聚合。 | major | 按 contract/tool_names/request/reasoning/content/tools 拆分。 |
| `src/app/pipeline/executor.py:63-512` | 编排器混入 preparation、response body normalization、finalization | approval/retry loop 与 hook/sanitize、non-stream body、observer/history 的状态和变化轴不同。 | major | 提取 preparation、nonstream_response、finalization；保留 executor 为唯一 retry/state-transition owner。 |


## 三轴合并结论

- `Messages↔Responses` 应成为方向明确的 bridge 子域，不能散落在 `protocols/` 与 `delivery/`。
- rolling/generation/systemd 与 web composition 是两个不同的基础设施边界，应从根模块收拢为包；errors、wire JSON、identity 应下沉为无编排依赖的 core。
- 巨型文件中，delivery、request conversion、pipeline executor 有可验证的独立职责域；Responses parser 则是应保留整体的内聚状态机。
- 结构重构须先冻结公开 import 迁移表，并针对 bytes-level SSE、stream terminal、retry/finalization、rolling lifecycle 运行各自现有聚焦测试，再跑 Ruff、Pyright 与完整回归。
