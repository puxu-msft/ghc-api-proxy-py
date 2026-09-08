# Direct buffered Chat Completions 技术可实施性独立评审

日期：2026-09-06

结论：**有条件可实施，但当前设计不应直接进入编码。存在 1 项 blocker、8 项 major、4 项 minor。** 根本方向正确：per-model endpoint capability 可以落在现有 immutable `ModelDescriptor`；pipeline 可以在不破坏 Xingchen 签名的前提下接管 payload／mode；同一 Chat facts 可以服务 retry、aggregation 与 observation；现有 production harness 足以验证真实入口。阻断点是 retry orchestration 的 ownership：当前文档同时让通用 runner和 `DirectDriver`拥有同一 pre-success retry，按现有 API 无法既保持单一 ledger owner，又复用 frozen payload／admission／deadline／events。

## 1. 评审快照与范围

- 源码快照：`f97d243f9431d836861ce5e9938605df56b37478`。评审结束前重新读取主树 `refs/heads/main`，仍为该提交。
- 设计文档：`.dev/docs/direct-buffered-chat-completions/decisions.md`，SHA-256 `894c4a7f3f837071ec55a21a2cac17481b1410d30bd481ab8f2863f668316bee`。
- 设计文档：`.dev/docs/direct-buffered-chat-completions/design.md`，SHA-256 `8a26858a28b2342c1ff8a694c19ef3d9c5b147bf10e2dc1005d04887287710b7`。
- 已按要求读取根 `CLAUDE.md`、`.claude/rules/00-development-workflow.md`，以及 direct-passthrough、error-envelope、TUI、Xingchen 的全部根层 living docs和设计直接引用的人控合同。
- CodeGraph CLI 在评审工作树明确返回“no `.codegraph/` index exists”，因此按项目规则回退到 `rg`／`Read`。
- 只读基线：`test_chat_completions_assembler.py`、`test_one_shot_delivery.py`、`test_timeout_enforcement.py`、CodeBuddy provider tests、Xingchen client／provider tests共 `44 passed in 11.24s`。该结果只证明当前基线稳定，不证明待实现设计正确。
- 未修改源码、tests、Spec 或 living docs；本文件是唯一交付物。

## 2. 关键可实施性结论

### 2.1 Per-model endpoint capability 的最小正确落点

最小且正确的落点是 `src/app/model_provider/types.py::ModelDescriptor` 上一个 frozen Chat capability值，而不是 `ModelProvider` 上的 provider-wide布尔值，也不需要再建一份 route capability对象。

现有链路已经具备完整承载面：

- `ModelDescriptor` 是 `@dataclass(frozen=True, slots=True)`，并携带 `provider_name`、`catalog_generation` 与 `catalog_refreshed_at`。
- `src/app/pipeline/routing.py::decide_route()` 只调用一次 `provider.describe()`，把同一 descriptor放入 frozen `Route.descriptor`。
- `src/app/pipeline/routing.py::apply_route()` 把该 descriptor放入 `RequestContext.model_descriptor`。
- `src/app/pipeline/driver.py::_drive()` 把同一 descriptor交给 `OpenAIChatCompletionsDriver`。
- `src/app/pipeline/driver.py::replay_prepared()` 复用同一 `Route`，因此 delivery replay天然复用同一 capability snapshot。

建议最小字段集合：`supports_streaming_response`、`supports_non_stream_response`、`stream_options_include_usage_default`、`tool_stream_default`、`provenance`。后两项应建模为“pipeline default”，不能写成“required”后又允许显式 client值覆盖；那两个词表达的是不同合同。

当前三个 provider的来源可以明确落地：CodeBuddy descriptor显式声明 streaming-only并标记 compatibility assumption；Xingchen descriptor显式声明双 mode及两个 streaming defaults；GitHub Copilot descriptor显式声明 neutral双 mode。不要用 `None` 静默表示 neutral，否则“没有事实”和“支持两种 mode”会再次同形。

### 2.2 Payload、签名与 provider边界

迁移方向可行。

- `src/app/model_provider/xingchen/client.py::send_chat_completions()` 在序列化最终 mapping后，以同一 `body` 同时计算 SHA-256／HMAC并作为 HTTP content发送。只要 pipeline先形成最终 payload，Xingchen client仍只调用一次 `app.wire_json.dumps()`，签名不会被破坏。
- `src/app/model_provider/codebuddy_client/client.py::send_chat_completions()` 当前的 `body["stream"] = True`、`stream_options`注入和 `aggregate_stream()`可以删除，raw response可以原样返回。
- `DirectDriver`当前已经在 subscribers之后对 payload做 private deep copy，并把实际发送 payload放在 `Attempt.payload`；这正是最终 mode／payload plan应写入的位置。

但不能把客户端 mode与上游 mode混成一个字段，详见 M-01。

### 2.3 Deadline、response-header timeout与 cleanup

现有层次可以复用，但 adaptation必须插在正确的控制面：

- `src/app/pipeline/direct_driver/base.py::DirectDriver._send()` 中的 `response_header_timeout`只包围 `provider.send()`。当 streaming-only adaptation以 `stream=True`向 provider请求时，provider在 headers到达后返回 raw response，body collector放在 `_send()`之外即可避免把 body时间误算为 header timeout。
- `DirectDriver._run_attempt()` 的 `asyncio.timeout_at(attempt.deadline_at)`当前只覆盖 `_prepare_and_send()`。若 Chat subclass让 `_prepare_and_send()`一直执行到 body adaptation结束，则 whole-attempt deadline可以正确覆盖 body；若在 `_run_attempt()`返回后才 aggregate，则会漏掉该 deadline。
- 外层 `src/app/pipeline/driver.py::handle_bounded()`继续提供不随 retry重置的 client deadline。
- `src/app/pipeline/direct_driver/base.py::_finish_response_cleanup()`和 `app.streaming.keepalive.finish_async_cleanup()`已经能保留 primary failure与 cleanup failure。新的 collector必须复用同一语义，不能用裸 `finally: await response.aclose()`覆盖主失败。

## 3. Findings

### Blocker

#### B-01：当前 `BufferedTransactionRunner` ownership 与 `DirectDriver` 的 attempt loop冲突，会造成双重 retry或绕过既有生命周期

**位置**：

- `.dev/docs/direct-buffered-chat-completions/design.md` §3.4、§6.2、§7.1。
- `src/app/pipeline/direct_driver/base.py::DirectDriver.run()`、`DirectDriver._handle_failure()`。
- `src/app/pipeline/retry.py::RetryLedger.take()`、`decide_stream_ending()`。
- `src/app/pipeline/driver.py::replay_prepared()`。
- `src/app/server/routes/inference.py::_reopen()`。

**事实**：设计中的 `BufferedTransactionRunner`自己接收 shared ledger、replacement callback并决定 `retry`；同一设计又要求 non-stream adaptation产生 typed failure后“由现有 `DirectDriver`关闭 response、消费 ledger并重发”。当前 `DirectDriver._handle_failure()`已经是 pre-success attempt的唯一 ledger owner。两者若都执行，会为一个失败消费两次预算并可能发出第三次请求；若 runner在 driver内部自行调用 provider replacement，则会绕过 `RequestContext.begin_attempt()`、attempt events、admission、rate limiter、per-attempt deadline以及现有 cleanup ownership。

**第二层冲突**：把 body failure简单抛回现有 `DirectDriver.run()`也不完全符合设计。当前 driver retry会重新发布 `attempt.prepare`并重新做 token admission；而设计 §6.2要求 body replacement复用第一次 attempt的 final payload、admission与 capability snapshot，不重跑 mutable shaping。现有代码只有 delivery侧 `replay_prepared()`具备这项能力，driver内部 body failure尚无对应 seam。

**结论**：`BufferedAttemptCollector`、Chat facts和 verdict可以同时服务两条路径；一个“自行消费 ledger并自行重开”的 runner不能按当前 API同时服务两条路径。

**必须先修正的设计**：把“收集／协议 verdict”与“attempt orchestration”拆开。Pre-success路径每个 `DirectDriver` attempt只运行一次 collector，由 driver作为唯一 owner消费 ledger并用 frozen `Attempt.payload`／reused admission打开下一 attempt；post-header路径由 delivery runner作为唯一 owner消费 ledger并调用现有 `_reopen()`。必须写下不变量：**任何组件不得先消费 ledger，再把同一失败抛给另一个 retry owner。** 若坚持单一 runner，则需先把 `DirectDriver.run()`本身重构成该 runner的 attempt backend；不能在现有 loop外再套一层。

### Major

#### M-01：客户端 `stream` 与 upstream `stream` 当前是同一个变量；mode adaptation不能修改 `RequestContext.stream`

**位置**：

- `src/app/pipeline/request.py::RequestContext.stream`。
- `src/app/pipeline/direct_driver/base.py::DirectDriver._send()`，当前以 `stream=context.stream`调用 provider。
- `src/app/server/routes/inference.py::_dispatch_after_body()`，当前以 `if context.stream`选择对客户端的 streaming／buffered response分支。

**问题**：对 client `stream:false`、endpoint streaming-only的请求，pipeline必须向 upstream发送 `stream:true`，但 server仍必须走 non-stream JSON交付。若实现直接改 `context.stream=True`，客户端会被错误送进 `_AccountedStreamingResponse`路径；若只改 payload中的 `"stream"`而 provider仍收到 `stream=False`，CodeBuddy／Xingchen 的 HTTP行为、`Accept` header和是否预读 body都会与 payload矛盾。

**要求**：建立 attempt-local immutable Chat send plan，至少同时给出 `client_stream`、`upstream_stream`与 final payload。`Attempt.payload`必须保存真正发送的最终 payload，provider的 `stream=`参数必须读同一 plan，`RequestContext.stream`只保留 client contract。还须定义 capability矩阵中“client要求 streaming但endpoint仅支持non-stream”的行为；当前设计只定义反方向 adaptation。

#### M-02：SSE→JSON adaptation若只返回 synthetic `httpx2.Response`，会把 downstream JSON冒充成 upstream body并丢失原 headers／connection；cleanup ownership也会悬空

**位置**：

- `src/app/server/routes/inference.py::_dispatch_after_body()`：`trace.upstream_request_body_bytes = len(response.request.content)`、`snapshot_upstream_connection(response)`、`trace.received = len(response.content)`。
- `src/app/pipeline/direct_driver/base.py::DirectDriver.run()`：rate limiter读取返回 response的 headers，成功后才 hand off response。
- `src/app/model_provider/codebuddy_client/client.py::aggregate_stream()`：当前构造一个只带 synthetic content、content-type与原 request的新 response。

**问题**：mode-adapted attempt实际从 upstream读取的是 Chat SSE，交给 client的是聚合 JSON。若 runner只把 synthetic response交回现有 server：

- `upstream_response_body_bytes`会记录 synthetic JSON长度，而不是实际读取的 upstream SSE字节。
- `snapshot_upstream_connection()`会失去原 response的 extensions／socket identity。
- rate limiter会看到 synthetic headers而非 upstream headers。
- response-header相关语义头会丢失。
- 若 aggregation在 `_run_attempt()`内部抛出，`DirectDriver.run()`尚未取得局部 `response`，现有 outer `finally`无法关闭它；collector必须成为 raw response的明确 owner并按既有 primary／cleanup异常顺序释放。

**要求**：transaction结果必须分槽携带 raw upstream exchange metadata与 client-facing synthetic body，或把这些事实写入 `Attempt`后再返回 synthetic response。不能让一个 `httpx2.Response`同时冒充两者。至少要保留原 request bytes、status、headers、HTTP version、connection snapshot与实际 SSE byte count，并证明每个失败／成功 response恰好关闭一次。

#### M-03：流内 rate-limit无法通过现有 limiter seam表达；当前 header时点还会把失败 transaction先记成 success

**位置**：

- `src/app/pipeline/direct_driver/base.py::DirectDriver.run()` lines 369–395附近：拿到 response headers即调用 `RateLimiter.observe_success()`。
- `src/app/pipeline/direct_driver/base.py::DirectDriver._handle_failure()`：只从 exception的 HTTP status／response读取 limiter信号。
- `src/app/pipeline/rate_limiting.py::RateLimiter.observe_failure()`：只接收 status与 headers。
- `.dev/docs/direct-buffered-chat-completions/design.md` §8。

**问题**：typed stream-event failure按设计不得伪造成实际 HTTP 429／500，因此 `_upstream_status()`会得到 `None`，现有 limiter不会进入 limited mode。另一方面，direct `stream:true`路径在 body被读取前已经对 HTTP 200调用 `observe_success()`；若随后收到流内 `rate_limit_exceeded`或 `server_error`，一个最终失败的 transaction可能先推进 recovery success计数。

**要求**：给 limiter增加明确的 event-rate-limit入口，或给 post-header transaction提供一个不依赖伪 status的 callback；它必须使用默认 retry interval并让下一 attempt的现有 `acquire()`真正等待。还要定义 terminal-only Chat的 success observation时点：对这两条 buffered transaction，成功应在 body verdict后，而不是仅在 headers 200时。测试必须断言 limiter mode／wait和 attempt数，不只断言最终响应。

#### M-04：attempt observation在 replacement建立前后的 reset／promotion规则尚未闭合

**位置**：

- `src/app/pipeline/request.py::RequestContext.begin_attempt()`：每次 attempt开始立即把 `context.response_observation`清为 `None`，旧 observer仍留在旧 `Attempt`上。
- `.dev/docs/direct-buffered-chat-completions/design.md` §3.5、§6.2、§10。
- `.dev/docs/direct-passthrough/spec.md` §5.4、§10。
- `src/app/server/routes/inference.py::_observe_response_event()`与 `_reopen()`。

**问题**：Spec与设计一方面要求旧 raw buffer和 side facts保留到 replacement response成功建立，另一方面设计 §10写“Replacement开始时当前request observation清空”。两句可以兼容，但必须增加显式 promotion规则：request-level projection可以在 `begin_attempt()`清空，旧 attempt state不能销毁；replacement失败且最终 carrier回退到旧 partial bytes时，究竟恢复旧 snapshot，还是把最终 observation标为 unavailable，当前没有答案。直接沿用 `context.current_attempt`会选择一个从未拿到 response的 replacement，并永久丢掉实际交付 carrier对应的旧 facts。

**要求**：区分 attempt draft保留、request projection reset与final promotion三个时点。最自然且与 §5.4一致的规则是：旧 state保留；replacement headers成功建立后才作废旧 state；若 replacement未建立且旧 bytes成为最终 carrier，则发布旧 snapshot并另记 replacement failure。若产品要 observation unavailable，也必须由 Spec明确，而不能由 `current_attempt`偶然决定。

#### M-05：未知／畸形 error carrier会被误归为“无 `[DONE]` 网络截断”，而 aggregation可能在丢内容后仍合成成功

**位置**：

- `.dev/docs/direct-buffered-chat-completions/design.md` §5.1、§8。
- `src/app/pipeline/delivery/formats/openai_chat_completions.py::ChatCompletionsAssembler.push()`与 `chat_failure_from()`。
- `src/app/pipeline/delivery/sse_source.py::SseEvent.json()`、`read_events()`。

**问题**：设计说 malformed／unknown event只成为 observation issue且 reader不抛；closed-set retry只看 `error.code`／`error.type`。现有 assembler只识别“payload顶层有 `error`且没有 `choices`”这一种 carrier。若 upstream发送 `event: error`加 flat object、同时含 `choices`与 `error`、或 payload不是 object，reader可能只记 issue，随后 EOF无 `[DONE]`又被当作 `NETWORK`透明重试。这违反 D-2：未知 stream error应不重试。另一方向，streaming→JSON adaptation若忽略一个 malformed content event，之后仍见 `[DONE]`，会把缺内容的 synthetic completion当成功返回；direct raw路径可以容忍 unknown event，因为原字节仍在，aggregation路径不能。

设计还没有规定 `error.code`与 `error.type`同时存在却指向不同类别时的优先级。例如 `code=server_error`、`type=rate_limited`会因实现分支顺序不同而决定是否激活 limiter。Closed set必须定义字段优先级或把冲突判为 unknown non-retry，不能让遍历顺序决定行为。

**要求**：先独立判定“这是 error carrier”，再做 code taxonomy；任何明确 error carrier即使 shape／code未知也必须终止 transaction且不重试。为 non-stream client定义 flat／non-object carrier如何进入合法 `{"error":...}` envelope并保存原 raw value。还要给 aggregation policy一个 `unassemblable` verdict；“issue only”只适用于仍能原样交付 raw wire的路径。

**精确字节边界**：设计要求 direct streaming在不可重试 error时只交付“截至 error event”的 raw SSE。若 collector先把一个含多个 frames的 chunk整体 append，再解析出中间的 error，buffer会包含 error之后的 bytes。新 reader／collector必须保留 raw frame offsets或产出 `(raw_frame, facts)`，不能只复用当前丢失 raw边界的 `SseEvent`。

#### M-06：`[DONE]` 后继续读的语义状态、timeout与cap优先级未定义完整

**位置**：`.dev/docs/direct-buffered-chat-completions/design.md` §7.2、§9；`.dev/docs/direct-passthrough/spec.md` §5.4、§8。

**已确认正确的部分**：为了 byte fidelity，见 `[DONE]` 后继续读到 EOF是可实施的；transport tear发生在 `[DONE]` 后时提交已缓冲 body且不retry也正确。

**未闭合部分**：

- reader是否继续解释 `[DONE]` 后的 JSON／error。若继续，一个尾随 error会把已完成 transaction改判失败；正确实现应在 `[DONE]` 后冻结语义 state，只继续收 raw bytes和post-terminal transport事实。
- idle timeout与attempt deadline发生在 `[DONE]` 后是否按 post-terminal tear提交。按同一语义应提交，但文档只点名 transport tear。
- client deadline发生在 `[DONE]` 后但 EOF前如何处理。人控合同把 client deadline视为整个请求的硬终点；设计没有说明它是否仍压过已见 `[DONE]`。
- trailing bytes会令 cap超限时，究竟提交截至 `[DONE]` 的完整语义 body、按 cap fallback裸断，还是把 transaction判失败。当前 §9只定义 append前拒绝 chunk，没有定义 post-terminal例外。

这些不是实现细节，因为四种选择会改变客户端收到的字节与完成行 verdict。应先在 Spec补齐 ending表，再编码。

#### M-07：多 choice的 typed state可实现，但 translated `ChatCompletionsAssembler`投影没有定义；当前实现会把 choices混在一起

**位置**：

- `src/app/pipeline/delivery/formats/openai_chat_completions.py::ChatCompletionsAssembler`。
- `.dev/docs/direct-buffered-chat-completions/design.md` §5.2、§10、§12.1。

**当前实现事实**：assembler只有一份 `_text`、一份 `_thinking`，工具只按 `tool index`键控，没有 `choice index`维度；`_push_choice()`甚至不读取 `choice.index`。两个 choice会把文本、finish reason和相同 tool index混入同一 Anthropic block序列。

**设计缺口**：新的 `ChatAttemptState`按 choice index保存全集没有问题，native non-stream JSON也可输出全部 choices，durable observation亦可保存全集；但 translated Chat→Anthropic path只能交付一条回复。设计说“assembler复用 reader facts并保持现有 translated block delivery语义”，却没有定义选择 `choice 0`、最小 index、拒绝多 choice，还是继续混合。继续混合不是可接受的“保持”；选择其中一个则是 observable behavior，需要 Spec条款。

**要求**：state内部键必须是 `(choice_index, tool_index)`；每个 choice独立保存 finish reason、reasoning和tool drafts。缺失、负数、布尔、重复或类型错误的 choice／tool index也必须定义 issue与排序／覆盖规则。TUI可按已裁定规则显示最小 choice；translated delivery必须另行明确定义投影，不能从 TUI规则反推。

#### M-08：测试计划总体方向正确，但尚不足以判别 double retry、timeout分层、raw accounting与真正的 shared-facts接线

**位置**：`.dev/docs/direct-buffered-chat-completions/design.md` §12；`tests/int/test_pipeline_app.py`；`tests/unit/pipeline/test_timeout_enforcement.py`。

**可复用能力**：`tests/int/test_pipeline_app.py::make_client()`可记录每个真实 outbound request，文件内已有 body-phase `AsyncIterator` tear、production replay、frozen payload／reused admission、discarded observation、cleanup与completion record测试。无需新测试框架。

**必须补的判别断言**：

1. Non-stream adaptation首轮失败、次轮成功时必须精确断言 upstream calls `== 2`、`ledger.total_spent == 1`、两个 request payload逐字相同、第二 attempt admission为 reused；只断言最终 200无法发现 double retry或 mutable shaping重跑。
2. 同一用例必须断言 client request仍 `stream:false`、upstream两次均为 `stream:true`、客户端 content-type／body为 JSON，才能判红误改 `RequestContext.stream`。
3. Body延迟超过 `response_header_timeout`但低于 attempt deadline应成功；body超过 attempt deadline应按 network预算retry；stream idle与client deadline各自应报告自己的原因且client deadline不得被retry重置。现有 `test_timeout_enforcement.py`只覆盖 provider call到返回的阶段，未覆盖 mode-adapted body。
4. 每个失败 raw response必须关闭；cleanup failure与主 failure同时保留；`CancelledError`不得进入普通 retry。设计 §12.2提到“旧response先关闭”，但需要直接断言 owner行为。
5. Raw SSE byte count、HTTP version／connection与synthetic JSON长度必须分别断言，防止 M-02。
6. Event-level rate limit必须断言 limiter进入 limited mode、下一 attempt确实等待默认间隔且只花一次 server-error预算。
7. Unknown error carrier必须从 production入口断言 calls `== 1`、不因无 `[DONE]`而retry，并检查完整 unknown fields进入最终 JSON。
8. `[DONE]` 后尾随 bytes逐字保留；尾随 semantic frame不改变 frozen facts；post-terminal tear／idle／attempt deadline不retry；client deadline与cap按补订合同分别断言。

**production入口能证明什么**：能证明 capability选择、payload／mode、attempt数、最终 bytes、observation promotion与schema／console接线。它不能仅凭黑箱输出证明“内部只解析一次”；两份完全一致的 parser会给出同一输出。该结构要求应由构造 seam钉住，例如同一 `ChatAttemptState`实例同时传给 collector／assembler／snapshot，配一个 reader调用计数的 component test，再由 production test证明该 state的最终投影确实到达 response与record。不要把无法从外部辨别的实现属性写成 production test必红承诺。

### Minor

#### m-01：capability字段语义需要从“支持／要求”收敛为可执行的 mode矩阵与 defaults

`stream_options.include_usage`与 `tool_stream`当前同时被描述为“要求或支持”，又规定显式 client值优先。若显式 `false`合法，它们就是 defaults而不是 requirements。建议 capability把 response mode支持与 request defaults分开，并为四种 client／endpoint mode组合给出闭合表。否则类型名会比行为更强，后续实现者会分别读出“覆盖 false”与“保留 false”两个答案。

#### m-02：durable schema只给了语义要求，没有给 Chat字段的确切容器形状

**位置**：`src/app/pipeline/response_observation.py::ResponseObservation`、`src/app/observability/request_trace.py::RequestTrace.absorb_response()`、`src/app/observability/request_log.py::format_response_observation()`、`src/app/observability/request_completion.py::_response_dict()`。

当前四处都硬编码 Responses的 `status`／`output_items`。实现可增加 Chat专属 `choices`，但不应把 finish reason塞入 Responses `status`或把 choice伪装成 `OutputItemSummary`。建议在 `ResponseObservation`下增加独立 immutable Chat payload，schema v2输出独立 `choices`／`done_seen`／`stream_error`字段；legacy projection只取最小 choice，durable保存全部。字段名和 absent／null／unreadable语义应先进入 TUI Spec或 direct-passthrough Spec，避免 serializer先替 Spec决定合同。

#### m-03：CodeBuddy现有 `extra_headers`通路是断的，provider boundary迁移测试容易把它遗漏

**位置**：`src/app/model_provider/codebuddy.py::CodebuddyProvider.send()`接收 `extra_headers`但调用 client时未传；`src/app/model_provider/codebuddy_client/client.py::request_headers()`其实已有 merge能力。

这不是本设计新造的问题，也不阻挡 buffered transaction；但设计写“provider继续拥有 provider headers”，迁移后的 component test若只断言 auth headers，会把现有 client tracing／protocol headers丢失固化下来。建议在同一 provider boundary slice中至少记录并测试该现状，再由既有 header合同决定是否修复；不要无声宣称“原样发送”已经包含 headers。

#### m-04：`decisions.md` 对人控合同的归因有一处写宽

**位置**：`.dev/docs/direct-buffered-chat-completions/decisions.md` “既有用户合同”第一组条目中的 `client-side-block-delivery.md`转述。

人控文档明确写了首次 HTTP 200 headers、SSE ping、client deadline，以及 non-stream request天然是一次性交付；它没有逐字规定“comment不构成 semantic commit”，也没有规定 direct streaming Chat整轮 one-shot。后两项分别是现有架构推导与后续 Chat裁决。结论本身可以成立，但来源强度应拆开，避免把可由评审修订的推导标成用户亲笔合同。

## 4. 建议的可实施结构

下面的结构满足用户已确认的边界，同时避开 B-01：

1. `model_provider/types.py`定义 frozen `ChatEndpointCapabilities`，`ModelDescriptor`持有它；CodeBuddy／Xingchen／GitHub在 descriptor构造处显式填值与 provenance。
2. `OpenAIChatCompletionsDriver`从 descriptor与 client request生成 attempt-local `ChatSendPlan`，把最终 payload写回 `Attempt.payload`，另存 `upstream_stream`；不修改 `RequestContext.stream`。
3. `ChatEventReader`只做 frame→facts；`ChatAttemptState`按 choice维度累计，并独立保存 `done_seen`、error carrier、issues、usage与raw unknown facts。见 `[DONE]` 后冻结语义 state。
4. `BufferedAttemptCollector`只读取一个 attempt、按 raw frame边界计量、关闭 source并返回 raw bytes＋state＋ending；它不消费 ledger、不发 replacement。
5. Pre-success mode adaptation在 `DirectDriver`的 attempt生命周期内调用 collector。Collector verdict为 retry时抛 typed failure给唯一 driver owner；driver需新增“body已开始后的 retry”分支，复用该 attempt的 final payload／admission而不是重新发布 mutable `attempt.prepare`。
6. Post-header direct streaming由 delivery transaction runner消费同一 ledger并调用现有 `replay_prepared()`；runner保留旧 attempt state至 replacement response建立，最终再 promotion一个 snapshot。
7. Adapted result显式分开 raw upstream exchange与synthetic client body，server trace从前者取 bytes／headers／connection，从后者生成 `JSONResponse`。
8. `ResponseObservation`增加 Chat专属不可变记录；`RequestTrace.absorb_response()`与 renderer按 `source_protocol`分派，不复用 Responses status。

该结构不是新 proof framework，只是沿现有 `DirectDriver`／`ReplaySupport`／`RequestCompletionCoordinator`边界补齐必要的数据与 owner。

## 5. 审查后否决的建议及原因

以下实现捷径在本次评审后明确否决；不是待选项：

1. **把 capability放成 `ModelProvider.supports_non_stream`一类 provider-wide布尔值。** 同一 provider可按 model／account不同，且现有 route已经有 immutable per-model descriptor，另开 provider查询会让 replay得到第二个答案。
2. **为 adaptation直接修改 `RequestContext.stream`。** 它同时控制 client delivery分支，会把 non-stream client错误变成 streaming response。
3. **让 `BufferedTransactionRunner`先消费 ledger，再把 typed retryable failure抛给 `DirectDriver`。** 一个失败会被两个 owner处理，预算和 attempt数都错误。
4. **让 runner绕过 driver直接调用 `provider.send()`完成 pre-success replacement。** 会跳过 attempt events、admission、limiter、deadline与现有 cleanup ownership。
5. **把 unknown error carrier当作普通 malformed event，最后按 missing `[DONE]`重试。** 这把 D-2明确规定的 unknown error“不重试”改成 network retry。
6. **见 `[DONE]` 后停止读取 raw source。** 会丢失用户已裁定要保留的尾随原始 bytes；正确做法是冻结语义解释而继续 raw收集。
7. **用 synthetic `httpx2.Response`同时代表 upstream SSE与client JSON。** 会污染 upstream byte accounting、headers、connection identity与 limiter观察。
8. **用 Responses `status`／`output_items`承载 Chat finish reason／choices。** 两个协议事实不等价，TUI Spec已经明确要求分槽。
9. **为“证明只解析一次”新建验证框架。** Production black box本来无法证明内部 parser数量；用共享对象接缝的简单 component test加真实入口结果测试即可。

设计原 `decisions.md` §“未采用的方案”中的 provider内容特例、provider-name分支、全 Chat强制 streaming、两套 parser／retry loop、继续延后 TUI等否决项，本次评审没有发现应推翻的理由。

## 6. 最终判定

- **技术可行性**：高。现有 descriptor snapshot、shared ledger、delivery replay、attempt deadline、response-header timeout、rate limiter、cleanup helper、request completion与integration harness都能承载该功能。
- **按当前设计原文直接实施的可行性**：不足。B-01必须先改设计；M-01～M-08应在实施计划前补成可执行合同或明确 seam，否则实现者只能在关键分叉上自行猜测。
- **建议进入实施计划的条件**：先修订 retry owner／frozen replay seam；再补 mode分槽、raw／synthetic exchange分槽、error carrier、post-`[DONE]` ending矩阵与 multi-choice translated投影；最后把新增测试断言写成上述可观察结果，不把 production test冒充内部结构证明。
