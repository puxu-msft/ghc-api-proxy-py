# 七轴线综合：缝、冲突与修复层次

- 审计基准：`44471c6ceedd8a06a7e0cca480314f8fc205e7c0`。
- 裁决资格：本报告作者未参与七份输入审计，独立读取当前源码与执行只读探针裁决。
- 方法：只把能够穿透七条既有轴线的具体缺陷列为“缝”；每个冲突与高优先级处置均以当前源码或独立 AST／运行时探针复验。报告中的严重度不按来源权威性加权。

## 1. 轴线之间的缝

（核验进行中；每项在独立证据确认后写入。）

## 2. 冲突裁决表

| 位置 | 轴线 A 判断 | 轴线 B 判断 | 裁决 | 独立证据 | 裁决不了则说明缺什么 |
|---|---|---|---|---|---|
| `src/app/routes/anthropic.py:102-117` | 类型化：`major`，可变持久化 projection 且写者不唯一。 | 生命周期：`minor`，不旁路 delivery，不是第二个 History 发布者。 | 待独立核验。 | 待写入。 | — |

## 3. 按修复层次归并的处置建议

（核验进行中；本节按最低共同层归并，不按报告来源或严重度罗列。）

## 4. 抽样复验记录

（核验进行中。）

## 5. 最该先动的三件事

（核验进行中。）

## 2A. 冲突裁决增量（本轮）

| 位置 | 轴线 A 判断 | 轴线 B 判断 | 裁决 | 独立证据 | 裁决不了则说明缺什么 |
|---|---|---|---|---|---|
| `src/app/routes/anthropic.py:102-117` | 类型化：`major`，称 `committed_response` 的写者不唯一。 | 生命周期：`minor`，称它不旁路交付且并非第二个 History 发布者。 | **支持生命周期轴线的严重度（minor）**；同时采纳类型化轴线的结构事实，但不采纳“当前已构成 major 级多写者缺陷”。 | 生产 AST 全量枚举只找到一处 `committed_response` 读取：route `:104`；唯一三处 mutation 是 `:109-117`。state 在 `responses_anthropic_stream.py:97-138` 先生成／缓存 projection，stream `finally` 在 `:181` 冻结；route 随后补全尚未包含的 usage、estimated、error 元数据。`HistoryConsumer.finalized()` 仅在 `history/consumer.py:35-48` 将同一 dict 赋给新 `HistoryEntry` 并 submit／flush，不再写该 dict；`HistoryStore.finalize()` 仅提交 writer（`history/store.py:30-34`）。除测试读取外，没有第二个生产 reader。前端 bytes 在 route `:48-50` 已 yield，frontier 从未被 route 写入。 | 无。当前证据足以裁定现状；未来若把 state 暴露给 observer／并发 history reader，结论应重审。 |

**处置边界**：把 route 的三项补全改为复制后交给 History，或令 state 产出显式 History projection，能防止未来 alias；这是可维护性／类型收敛的 `minor`，不是修复一个当前 delivery 或 History 一致性故障。

| `src/app/streaming/anthropic_usage.py:13-41` 的 usage tap 与 `src/app/streaming/openai_sse.py:6-48` 的解析器 | 重复轴线：两份手写 SSE parsing，建议可考虑 `httpx-sse`／`sse-starlette`。 | 库轴线：不采用 `httpx-sse`，仅条件评估 `sse-starlette` 的普通 response wrapper；原始字节直通与 delayed-start 不能由它们替换。 | **支持库轴线，收窄重复轴线的库建议**：确有 parser 语义分叉，`AnthropicSSEUsageTap` 只识别 `data: `，而 `parse_sse_json` 也接受 `data:`；但外部库不是这处同步 tap 的可替换最低层。应共享项目内的增量 SSE framing/tokenization 原语，tap 在其上抽 usage；`sse-starlette` 只能另行评估普通出站 response。 | `anthropic_usage.py:13-27` 是同步 `feed(bytes)`，自行持有跨 chunk buffer，且 `:21` 硬匹配 `b"data: "`；`openai_sse.py:6-25,44-48` 是异步 `AsyncIterator[bytes] -> JsonValue`，接受可选空格。两者接口与数据所有权不相同；`streaming/sse.py:45-63,206-230` 显示 `sse-starlette` 所能替代的候选位置是 HTTP response 包装，非入站 tap。 | 无。这里的分歧是“用库收敛”这一处置建议，不是否认现有解析语义漂移。 |

| `tokenization/state_store.py:98-109` 及同类 durable replace | 库轴线：把可比 atomic-write 收窄成 snapshot／state 两处，并建议本轮不合并。 | 用户指出该计数少报；重构判别要求六处同类 replace 建在共享 durable-write 原语上，state store 缺父目录 `fsync`。 | **两者皆误（计数与抽象层均不对）**：不是把 no-replace snapshot create 与 replace 混成一个 API；应抽共享的“temp write + file fsync + replace + parent-directory fsync”原语，并保留 snapshot 的 `link` no-replace／CAS 等领域语义在其上层。`state_store` 是已确认漏 directory fsync 的一处。 | 独立 AST／源码复验了 6 个 replace 发布点：state `state_store.py:98-109`；snapshot live-head `snapshot_store.py:190-211`；controller tokenization `rolling_controller.py:434-451`；controller generation env `:412-428`；frontier copy `rolling_frontier.py:108-122`；rolling state `rolling_state.py:125-143`。后五者均在 replace 后 fsync parent；state store 仅 fsync temporary file 后 replace，缺该步骤。snapshot object create 在 `snapshot_store.py:169-187` 使用 `link`，必须仍是不同语义。 | 无。 |

### 其余交叉提及的排查结果

- `rolling_state.py`：类型轴线主张以受限工厂／discriminated variant 排除非法 `GenerationRecord`，库轴线主张不引入 FSM library；两者回答的是不同命题，**不冲突**。应采纳前者的建模修复，不采纳“以库取代并发编排”的方案。
- `delivery/anthropic_sse.py`：模块轴线主张拆 contracts/frontier/renderer 并保留 `DeliverySession` 的 lock-bound 原子性；生命周期轴线确认现有 parser→frontier→ASGI 未旁路。一个是结构处置，一个是当前行为核验，**不冲突**。
- 测试轴线的“内容质量高”不反驳重复轴线已经复现的 stream/non-stream 漂移：前者没有声称覆盖二者的语义等价。独立复验显示同一 `incomplete/max_output_tokens` body 经 non-stream converter 在 `responses_anthropic.py:80-88` 抛 `unsupported_response_status`，而 `pytest ...::test_max_output_tokens_incomplete_is_successful_max_tokens_terminal` 通过并断言 stream 为 200；这是测试覆盖缝，不是报告判断冲突。
- 依赖图“34 个孤岛”不是模块轴线“生产无消费者”的反例：独立重算显示其中 **18/34** 是隐式执行的 package `__init__.py`，仅 **16/34** 是非 initializer；该图只能支持“显式 AST 入度为零”，不能作为未执行或可删除的证据。模块轴线没有据此提删除，因此无跨轴线冲突。

## 3A. 按修复层次归并的处置建议（本轮）

### R1. `protocols/messages_responses/`：方向明确的 Messages↔Responses bridge 与唯一终态／usage 事实

- **目标层**：新建方向性 bridge 子域，至少有 `request`、`response`、`stream`、`tool_names`、`terminal`、`usage`；stream adapter 消费 parser typed facts，delivery 只接收下游 delivery DTO。
- **归并发现**：模块 M1-M3（`protocols/{anthropic_responses,responses_anthropic}.py`、`delivery/responses_anthropic_stream.py`、`delivery/anthropic_sse.py`）；重复 D1-D7、D12、D14（usage、terminal、block projection、tool argument、tool-name、terminal event）；类型 `responses_anthropic_stream.py:64-156`；测试的 stream/non-stream 语义缺口。
- **最低共同层**：它覆盖同一 Responses→Messages 规则的完整 body 与 SSE 路径；放 route 会再复制，放通用 delivery 会重新引入上游 Responses 依赖，再低的 parser 不应知道 Anthropic 语义。
- **验证**：正向：同一 fixture 经 stream／non-stream 产出同一 content、usage、terminal 分类与 tool-name；反向：`incomplete/max_output_tokens`、空 content、坏 usage details、坏 tool JSON、未知 terminal 各自得到同一预期 error/成功语义，且 mutate 任一 shared classifier 会同时使两条路径红。

### R2. 共享 incremental SSE framing 原语

- **目标层**：在 `streaming/` 建跨 chunk 的 byte→frame／data-line 原语，明确接受 CRLF/LF、`data:` 可选空格、多 data 行、`[DONE]`；`parse_sse_json()` 与 `AnthropicSSEUsageTap` 均建立在它上面。
- **归并发现**：重复 D8（`streaming/openai_sse.py:6-48`、`streaming/anthropic_usage.py:13-41`）；库 SSE 选型的“不以 `httpx-sse` 替代 raw bytes tap”；验收脚本的 SSE CRLF false-red。
- **最低共同层**：两个消费者共享的是 framing，不是 JSON event iterator 或 HTTP response；提高到库／route 会丢失 tap 的同步 byte ownership，降低到各消费方会再出现可选空格、分块 CRLF 分叉。
- **验证**：正向：同一拆块组合在 parser 与 usage tap 得相同 event/usage；反向：去掉可选空格、拆行或 `[DONE]` 处理时对应 fixture 红，且 raw passthrough bytes 完全不变。

### R3. durable publication 原语，保留 immutable-create/CAS 上层语义

- **目标层**：共享 `durable_replace(path, bytes, mode)` 实现 temp write、file fsync、replace、parent fsync；snapshot 的 `link` no-replace、content-address、revision/CAS 与 locks 保持在 `TokenizationSnapshotStore`。
- **归并发现**：库 atomic-write；类型持久化边界；state `tokenization/state_store.py:98-109`；snapshot `snapshot_store.py:169-211`；controller `rolling_controller.py:412-451`；frontier `rolling_frontier.py:108-122`；state `rolling_state.py:125-143`。
- **最低共同层**：六处 replace 都需要同一 crash-durability序列；再低无法复用，抽成“所有 atomic 操作”会错误吞并 snapshot create 的 no-replace/CAS 合同。
- **验证**：正向：六个 caller 经 spy／fault-injection 证明 replace 后均 fsync parent；反向：在 replace 或 directory fsync 注入异常时不报告成功／不推进 revision，snapshot existing-object 仍不得覆盖。

### R4. 上游 exchange contract：统一 SDK exception→`httpx.Response`／`ApiError` 边界

- **目标层**：`upstream/base.py` 的共享六种 exchange 模板，子类仅给 headers/options；在模板单点归一 SDK `APIStatusError`、transport error、Responses headers-pending。
- **归并发现**：重复 D9（`upstream/{copilot,generic}.py:25-176` 的 12 个手抄方法）；类型外部 transport boundary；依赖图的 client/executor coupling；重复报告 out-of-axis 的 10 条 non-2xx exception path。
- **最低共同层**：两 upstream、OpenAI/Anthropic/Responses/embeddings 都由 SDK 调用并承诺 `httpx.Response`；在 route 补 catch 会漏掉下一调用形态，在 SDK wrapper 以下又会混入各协议错误 policy。
- **验证**：正向：MockTransport 返回 429，六种 method 都向 caller返回带原 status 的 response 或指定 `ApiError`；反向：SDK 抛 `RateLimitError`／transport error 时不得泄为 FastAPI 500，headers-pending 分支仍只在其合同下 retry。

### R5. Pipeline 的 immutable stage facts 与 typed strategy outcome contract

- **目标层**：`pipeline/` 内部建立 `OriginalMessagesRequest → PreparedAnthropicWire → AttemptPayload` 的不可变阶段值、typed hook record；`Retry | DoNotRetry` union 替代 `RetryDecision.should_retry + payload + owner`，approval 结果改 discriminated union。
- **归并发现**：类型 `pipeline/context.py:70-91`、`approval.py:13-30,133-146`、`strategies/__init__.py:10-120`、models；生命周期唯一 retry owner／approval owner；模块 `pipeline/executor.py:63-512` 应提 preparation/nonstream/finalization 但保留 executor 为唯一 retry orchestration；测试 `component/test_pipeline_executor.py` harness。
- **最低共同层**：context、approval、hook、retry 都传递同一请求 attempt；只修 strategy 会继续把可变 wire 从 approval/hook 泄入 retry，只修 executor 会令下一个 strategy 仍能构造非法 outcome。下沉至 Pydantic ingress 会把插件开放 JSON 边界误封闭。
- **验证**：正向：approved、modified、rejected、retry、no-retry 均只能以合法 variant 构造并维持 executor 单次预算扣减；反向：构造无 retry 却带 modified payload／错误 approval payload、复用旧 attempt payload 均在 type/constructor boundary 被拒，真实 hook 仍只拿到其 explicit mutable copy。

### R6. Delivery→History 的 immutable finalized projection contract

- **目标层**：在 bridge/delivery 交界定义 frozen `StreamPending | StreamDeliveredSuccess | StreamFailed` 与 immutable `AnthropicHistoryResponse`／`UsageSummary`；route 完成最后 metadata projection 后一次性交给 History，History 只持久化 DTO。
- **归并发现**：类型 `responses_anthropic_stream.py:64-156`、`delivery/anthropic_sse.py:122-395`、`history/{types,consumer}.py`；生命周期 transport/finalize/history 多分支与 `routes/anthropic.py:102-117`；重复 D6/D13（block projection/error envelope）。
- **最低共同层**：frontier 的 accepted/uncertain 事实与 history 的 client-visible record 必须同源；只在 History copy dict 仍让 renderer/state 暴露可变 projection，只在 route copy 则会漏失败／usage 投影。进一步下沉 parser 会让它拥有 delivery receipt。
- **验证**：正向：successful、uncertain、error 三种流结束各生成一次不可变 record，前端 bytes、frontier、persisted history 相互一致；反向：尝试在 finalized DTO 后写 usage/error 或令 terminal/error batch 混搭必须失败，且 mutation 不会改变已排队/已持久化 record。

### R7. Protocol projector primitives：block、tool argument、Gemini function call 与 error envelope

- **目标层**：各协议 direction module 内保留一个 typed `CompletedBlock → Anthropic content` projector、一个 `function arguments → JsonObject` parser，以及公共 `anthropic_error_payload(ApiError)`；Gemini stream/non-stream 都调用 `protocols/gemini.py` 的同一 functionCall/usage projector。
- **归并发现**：重复 D5-D7、D11、D13；类型 models/protocol JSON boundary；模块 `routes/gemini.py:30-98` 职责错位；测试 reasoning 同源断言与 raw JSON boundary。
- **最低共同层**：这些都是协议 wire 投影规则，不是 renderer／route 的控制流；放 delivery 会漏历史 JSON，放 route 会漏非流式 Gemini，抽成无方向 JSON utility 则抹掉严格对象／error wire contract。
- **验证**：正向：tool name mapping、合法 object arguments、Gemini streaming/non-stream functionCall、四个 error 出口都产生同构 payload；反向：malformed/non-object arguments 与 mapping enabled 时所有出口同码失败/还原，任一 projector mutation 令对应的两种模式红。

### R8. Generation lifecycle model 与 transition authority

- **目标层**：在 deployment generation domain 以 role-specific discriminated `GenerationRecord` variants、受限工厂和可审计 transition table 表达合法持久状态；runtime/controller 只调用 transition API，store 只 decode/validate/persist。
- **归并发现**：类型 `rolling_state.py:16-29,146-215`；库状态机评估；模块 rolling/generation 文件群与 `rolling_controller.py` 职责混杂；测试 rolling runtime 的真实 lifecycle 测试。
- **最低共同层**：role/phase/ready/accepting/pid 的关系由持久 record 和 runtime 共同使用；只加 store validator仍可构造非法状态，直接上通用 FSM 又会吞并 lock、systemd side effects、CAS recovery。
- **验证**：正向：每个合法 generation transition 可恢复、revision 单调、controller/runtime 的真实测试通过；反向：`committed+reserved`、`accepting+pid=0`、非法 phase jump 不能构造/解码，取消或 systemctl 失败不发布半迁移状态。

### R9. Physical architecture：core、web、deployment 与 explicit ports

- **目标层**：按依赖方向建立 `core/`（errors, wire_json, identifiers）、`web/`（app factory/runtime/dependencies）、`deployment/{systemd,generation,rolling}/`；以 Protocol/constructor injection 打断 `anthropic.client ↔ pipeline.executor` runtime cycle，composition root 装配 concrete services。
- **归并发现**：模块顶层归属 M4-M8（rolling/generation/systemd/web/core、graceful timeout）；依赖图唯一 runtime SCC `anthropic.client ↔ pipeline.executor` 与 type-only `runtime ↔ upstream.bootstrap`；模块 bridge/delivery boundary；类型 mutable module constants。
- **最低共同层**：这些是 consumers 能定位职责及高层编排依赖低层 adapter 的架构层；只移动单文件会保留 root 邻居和 cycle，只将 identifier 放 rolling 又迫使 tokenization 反向依赖 deployment；比 package 更低的 import 改名则不能表达 port direction。
- **验证**：正向：AST runtime graph 无 client/executor SCC，core 不 import web/deployment，routes 仅经 web dependency 获取 runtime；反向：在 core 或 systemd adapter 引入 rolling policy、在 pipeline 再直接 import concrete client 的架构测试必须红。保留 type-checking 边不当作 runtime cycle。

### R10. Test taxonomy 与显式共享 harness

- **目标层**：`tests/README.md` 定义 unit/component/http/integration/smoke 的一句话准入；`tests/support/` 提供显式 import 的 recording/harness/stream constructors，绝不引入 autouse fixture。
- **归并发现**：测试 L1-L4、D1-D4、F1-F2、巨型文件；`create_app` 横跨 13 个文件/4 目录；0 `conftest.py`、0 fixture；模块／生命周期的 delivery、pipeline、route critical-path tests。
- **最低共同层**：层级判据决定下一测试放哪里，shared support 消除已经逐字节重复的 harness；只移动现有文件仍会再放错，只做 fixture 会把显式构造变成隐藏耦合。support 不应吞并同名但有意不同的 stream variants。
- **验证**：正向：93 个 pytest 文件仍收集并运行，`RecordingHistory`/`RecordingApproval` 只有一份 authority，ASGI/real I/O tests 落入声明层；反向：尝试在 unit 放 `create_app`／真 socket，或用 autouse fixture 隐式注入，taxonomy check 报告违规；保持正确纯函数 tests 可进入 unit。

### R11. 语义契约测试与验收载体的 authority split

- **目标层**：为跨模式语义建 shared fixture/oracle（Messages↔Responses 的 R1），并把根 `verification/` 定义为可执行、版本化的独立验收入口或迁移/归档其有效不变量；pytest 仍为常规回归 authority，历史 `.pyc` 不作为测试载体。
- **归并发现**：测试 S1、D5、A1、P1/P2、V1、未测 coverage/parametrize/`verification/`；重复 D1-D4 已复现 stream/non-stream drift；验收 `phase3_acceptance.py` 当前 13/17、其中多个因旧 import/API false-red；旧 Phase3 报告宣称文件缺失而当前源存在。
- **最低共同层**：同源 expected 与跨模式差异只能由独立 literal/fixture oracle 捕获；单个 unit test 或单份过时验收报告均无法裁其余入口。把 verification 简单塞进 pytest 会失去独立运行方式，保留未定义第二 authority 则持续产生假红。
- **验证**：正向：shared semantic corpus 同时驱动 stream/non-stream，reasoning signature 使用 literal anchor；verification 的每项有当前 spec/commit/provenance 且在正确样本绿。反向：mutate carrier line format、terminal classifier、route registration 或 old API spelling，目标 oracle 分别红且失败归因于该机制；`sleep(1.1)` 改为 timer-state predicate 后仍能抓未取消 timer。

### R12. 小而稳定的共享 protocol/route seams

- **目标层**：提取 `ResponsesTerminalEvent` 常量、OpenAI/Azure `_response` history-stream helper，以及 protocol-specific translator modules（按协议对＋事件/完整 payload 粒度命名）。
- **归并发现**：重复 D10/D12；模块 `streaming/translator.py:5-22`、`transform/translator.py:6-109`；依赖图显示这些 translator 显式生产入度为零。
- **最低共同层**：常量和 helper 的所有实际 callers 必须同源；translator 的自然边界是 protocol conversion 而非 SSE framing。上移到 generic web 会混入 endpoint policy，下沉到单一路由仍保留双写。
- **验证**：正向：OpenAI/Azure 响应、HTTP/SSE cleanup 与 history 相同，两个 translator 在其明确生产入口可达；反向：新增 terminal event 或故意改变一条 route helper 的 status/close，所有消费者的集中测试红。对于当前无生产 consumer 的 translator，不先移动为“修复”，先完成 R13 的产品裁决。

### R13. “未接线生产 API”的产品归属裁决，不以孤岛删除代替设计

- **目标层**：在 live spec/roadmap 明确 `shutdown.py`、`repetition_detector.py`、Chat translators、`pipeline.manager`、`buffered_retry`、`delayed_commit` 等是计划接入的产品能力还是测试/compat 支持；裁定后才把它们接入对应 domain 或迁到 tests support。
- **归并发现**：模块 `shutdown.py`／`repetition_detector.py` 无生产消费者；module translator findings；依赖图的 16 个非-init 显式零入度模块；测试 verification 的无后继 deletion guard。
- **最低共同层**：是否存在产品 contract 不是 import graph 或目录移动能决定的；先删或强行接入都可能推翻既有用户取舍。更高层的泛化“删除孤岛”会误伤动态／未来功能。
- **验证**：正向：每个保留模块有可达生产入口与黑盒行为，或每个测试 support 有显式 consumer；反向：删掉/断开声明保留的 capability 时对应 contract test 红。没有一手 spec/用户裁决前，此组**不能自行实施**。

## 1. 轴线之间的缝（最后一轮）

### G1. 共享但不完整的行为 oracle：FINALIZED spec 未进入任何审计的裁决输入

- **构造的缺陷场景**：开发者看到 non-stream 对 `incomplete/max_output_tokens` 返回 502、stream 返回 `max_tokens`，自行选择“严格失败”；或把空 content 的两侧都改成失败。局部代码／测试可能收敛，却违背已冻结产品合同。
- **独立 ground truth**：`docs/agents/anthropic-responses-bridge/spec.md:255` 要求两模式同一语义核心；`:263` 规定 output-token-limit incomplete → `max_tokens`；`:266` 要求合法空成功生成空 text；`:363-370` 规定 usage 校验和 stream/non-stream 一致。这已裁决重复报告 D1-D4 的正确方向，故“方向未裁定”被推翻。
- **为何七轴皆漏**：模块、重复、生命周期、类型、测试、库、依赖图都以当前代码／测试／局部文档为 oracle；派活只排除了 architecture/implementation，却没有把 FINALIZED spec 列为必须读的行为 authority。它们可各自正确地发现漂移，却共同缺少判断哪侧正确的基准。

### G2. 跨进程 generation ID 分配竞争：两 controller 同时 reserve 得到同一 ID

- **构造的缺陷场景**：两个 CLI/controller process 同时执行 `RollingFrontierStore.reserve_next()`。两者在 `rolling_frontier.py:23-37` 都先读同一 `high_watermark()+1`，均生成 `g000…1`，再 append/replace；该 store 没有 file lock 或 CAS。`frontier.initialized` 的 `O_EXCL` 只可能让其中一个在**已 append fact 后**失败，不能保护 ID 分配。
- **为何七轴皆漏**：模块轴只看归属；重复轴明确未过 `rolling_*` 语义；生命周期轴只覆盖 Anthropic request delivery；类型轴只审 record 的非法字段组合，不证明 reserve 的跨进程原子性；测试轴只分类测试结构且没有多进程 race oracle；库轴讨论 snapshot locks/atomic write而非 frontier allocation linearizability；依赖图不能表达进程共享文件语义。
- **所需 oracle**：两个独立 process 以 barrier 同时 reserve，断言 generation ID、allocation fact sequence 与两份 frontier copy 均严格唯一／单调；反例必须在无 inter-process lock 时稳定暴露。该结论指向 `RollingFrontierStore` 的 allocation transaction/lock，而非在 controller caller 加 asyncio lock。

### G3. “SDK 返回 `httpx.Response`”这一共享 fake 前提掩盖 non-Responses 429

- **构造的缺陷场景**：Generic/Copilot OpenAI、Anthropic 或 embeddings upstream 返回 429。`upstream/{generic,copilot}.py` 的普通 `send_*` 直接 await SDK post，而 `OpenAIClient`／route contract 随后把结果当 `httpx.Response` 读取 `.is_success`／`.status_code`。真实 SDK 会在 return 前抛 `RateLimitError`，使本该转发的 upstream status 漏为未处理异常／500。
- **独立 ground truth**：本轮 MockTransport 对 openai 与 anthropic SDK 各返回 429，均输出 `RateLimitError True 429`；源码仅 `send_responses_headers()` 在 `generic.py:76-92`、`copilot.py:148-165` 捕 `APIStatusError`，普通 `send_openai()` 等没有。`openai/client.py:44-65` 的 Protocol 仍承诺 response return。
- **为何七轴皆漏**：重复轴记录了这条为 out-of-axis，却未验证 route result；类型轴把它作为外部宽边界；测试轴测试结构而非 fake/SDK 协议保真；其余四轴不测真实 non-2xx SDK 行为。所有现有 mock 若直接返回 response，会共同确认错误前提。应以真实 SDK MockTransport probe 校准 fake，并在 R4 的 exchange boundary 修复。

### G4. pytest 与 standalone verification 的双验收面可同时给出相反结论

- **构造的缺陷场景**：常规 `uv run pytest tests -q` 全绿，发布前却执行根 `verification/phase3_acceptance.py` 并判 3 blocker；维护者把它误当产品回归并修改正确实现，或反过来永远忽略真正独立验收失败。
- **独立 ground truth**：测试审计已实跑 808 pytest green；本轮独立运行 standalone script 得 `13/17`、3 blocker、1 major。失败包括旧 `AppSettings(github_token=...)`、已不存在的 `app.routes.config`、过时的 `format_sse_event(event_type=...)`，表明至少该三项是 script drift，不是当前产品缺陷；旧 `PHASE3_ACCEPTANCE_REPORT.md` 还声称当前存在的 sanitize/accumulator 文件缺失。
- **为何七轴皆漏**：测试轴明确未评估根 `verification/`；其它六轴都不定义验收 carrier 的 authority、spec/commit freshness 或执行入口。因此每条轴内的绿都不能说明第二套验收是否适用，第二套红也不能说明实现错。R11 必须先定义 carrier、oracle 与过期处置，之后才可让任何一侧承重。
