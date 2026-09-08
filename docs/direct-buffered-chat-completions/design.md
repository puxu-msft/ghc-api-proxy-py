# Direct buffered `/chat/completions` retry 与 observation 设计

状态：用户已于2026-09-06确认设计并补裁标准multi-choice聚合、post-`[DONE]` raw tail与client deadline语义；两份独立初审finding已处置，等待修订candidate复评后进入实施计划。

## 1. 目标与权威

本设计同时覆盖两类 direct Chat Completions 缓冲事务：客户端请求 `stream:true`、代理把 upstream SSE 整轮缓冲后一次交付；以及客户端请求 `stream:false`、resolved model endpoint不支持 non-stream response而由 pipeline把 upstream SSE聚合成标准 Chat JSON。两条路径都要在语义提交前透明 retry，并从最终 attempt生成 provider-side response observation。

行为权威分别是 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md)、[`../error-envelope/spec.md`](../error-envelope/spec.md) 与 [`../tui/spec.md`](../tui/spec.md)。本设计说明如何实现，不取代它们；决策来源与强度见 [`decisions.md`](decisions.md)。人控合同仍以 `docs/.human-controlled/` 为最高权威。

## 2. 已确认问题

### 2.1 Direct streaming one-shot

`/chat/completions` 的 direct client leg没有 Chat framer，所以 `stream:true` response走 `one_shot_delivery()`。当前实现把全部 upstream bytes积进 `bytearray`，正常 EOF一次交付；任何 guard或transport异常则先交付该失败 attempt的 partial bytes再抛出。它没有 `ReplaySupport`、keepalive或buffer cap。由于 body在 response headers之后消费，这类 failure已经越过 `DirectDriver.run()`，只能由 delivery owner replay。

### 2.2 Streaming-upstream to non-stream client adaptation

当前 CodeBuddy client无条件把 Chat payload的 `stream` 改成 `true`，补 `stream_options.include_usage`，并在 provider内部解析 SSE、聚合 Chat JSON。聚合期transport exception没有归一化，clean EOF无 `[DONE]`也被补成 `finish_reason="stop"` 的成功 response。当前 Xingchen client也在 provider层补 Chat streaming字段。

这些行为不应由 provider执行。Provider可以声明 resolved model endpoint支持哪些 response mode及需要哪些请求扩展，但不得解释这些能力、改 model-protocol payload、解析 SSE或合成 JSON。内容处理归 pipeline。

### 2.3 Response observation

现有 attempt-scoped `ResponsesObserver` 只为 OpenAI Responses target建立。Direct buffered Chat的 native finish reason、reasoning、ordered tool calls与usage没有进入统一 `ResponseObservation`，所以 console与durable schema都读不到。被 retry替换的 attempt还必须不能污染最终 observation。

## 3. 设计原则

1. Provider声明 per-model endpoint capability，pipeline解释并执行；运行时不按 provider名称分支。
2. SSE缓冲事务成功必须见 `[DONE]`；单独 `finish_reason` 不是完整性证明。Native non-stream JSON不适用 `[DONE]` 判据。
3. Chat协议只解析一次。Retry判据、SSE→JSON aggregation与response observation从同一 attempt facts投影。
4. Retry预算只有一个 owner。Pre-success non-stream adaptation由 `DirectDriver`重试；post-header streaming body由delivery replay；两者共享 request的同一个 `RetryLedger`。
5. 被 replacement取代的 attempt对客户端和最终 observation完全不可见；replacement成功建立之前旧 attempt仍保留为最终 fallback候选。
6. 最终成功 attempt的 direct streaming bytes原样提交；Chat reader只观察，不重写 wire。
7. 不新增 proof framework；复用现有测试、mock upstream、ledger、limiter、deadline、cleanup与request accounting。

## 4. Capability 与 provider 边界

### 4.1 Capability 数据

`ModelDescriptor`携带 frozen `ChatEndpointCapabilities`。`response_modes` 是 `{streaming, non_streaming}` 的非空子集；streaming extension分别用 `stream_options_include_usage_default: Literal[True] | None` 与 `tool_stream_default: Literal[True] | None` 表示“字段缺席时的default”，不用“required”混写显式client值是否可覆盖。`provenance`必填，避免“没有事实”与“明确支持两种mode”同形。完整mode矩阵与defaulting规则由 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §9.3唯一所有；endpoint存在但client要求的response mode不受支持时抛新的typed `ResponseModeNotSupported`，不复用语义更窄的 `CapabilityMissing`。

Capability由 provider/catalog对上层声明，但它只是数据。Provider client收到pipeline已准备好的payload与独立 `upstream_stream` mode后原样发送，继续拥有URL、认证、provider headers、签名、transport以及transport/status exception normalization。`RequestContext.stream`只表达client contract；attempt-local `ChatSendPlan`只保存client mode、upstream mode与capability snapshot，**最终payload的唯一authority是 `Attempt.payload`**。Pipeline在该mapping上完成defaults，provider从它序列化／发送；prepared retry从它建立新的private copy，不维护第二份可独立变化的payload。Capability snapshot随route进入attempt，replay不在attempt之间重查provider。

### 4.2 当前 capability provenance

当前 CodeBuddy target保守声明 non-stream unsupported，因此 client `stream:false` 时由 pipeline改为 upstream streaming并聚合。该值只由参考实现兼容性支持，P6真实 `stream:false` 负控尚未运行；文档与可观测记录不得称其为实测 upstream事实。用户决定本次不实测。

当前 Xingchen target声明 `{streaming, non_streaming}` 与两个streaming absent-default；pipeline只在upstream streaming mode且字段缺席时补true，显式client值优先。GitHub Copilot显式声明双mode与两个 `None` defaults，现有payload与mode保持。

未来 P6若证明CodeBuddy支持 non-stream，只改 capability数据即可移除mode adaptation；若能力按model或account不同，由对应 descriptor分别声明。

### 4.3 迁移要求

删除 CodeBuddy provider client中的 `body["stream"] = True`、Chat字段注入、SSE解析与JSON aggregation。删除 Xingchen provider client中的Chat payload注入。Provider component tests改为验证原样发送、provider headers／签名与raw response；原内容测试迁入pipeline Chat adapter。CodeBuddy `send(extra_headers=...)`当前没有把参数传给已有header merge seam，本切片按provider header合同修复并测试，不把“原样发送”写成一条现状假话。

## 5. 共享 Chat 协议事实

### 5.1 `ChatEventReader`

`ChatEventReader`把一个完整raw SSE frame解析为不可变 `ChatEventFacts`，并保留该frame在attempt raw buffer中的起止offset。它先判断是否为明确error carrier，再读取error taxonomy；然后才读取普通Chat chunk。支持的error carrier是：SSE event名为 `error`、JSON object含顶层 `error` 键、或flat object的 `type == "error"`。Malformed或unknown error仍是终局且不retry，不能在EOF时退化成“缺 `[DONE]` 的network truncation”。

普通unknown event在direct raw streaming中只产生issue并保留raw；在SSE→JSON adaptation中，若无法按 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §9.3字段表无损投影，则返回具名 `unassemblable`，不跳过内容后合成成功。Reader bug保持本地异常，不包装成upstream failure。

### 5.2 `ChatAttemptState`

每个 attempt拥有独立 `ChatAttemptState`。它消费 `ChatEventFacts`，按 `(choice_index, tool_index)`维护有序choices、reasoning、tool calls、logprobs、usage、`done_seen`、finish reasons、failure与issues。第一个合法 `[DONE]` 后冻结semantic state，只继续收raw tail。它提供三种投影：buffered transaction verdict、§9.3定义的标准Chat non-stream聚合输入、[`../tui/spec.md`](../tui/spec.md) 定义的provider observation snapshot。

`ChatCompletionsAssembler`只复用纯event reader与其字段解码，不在本切片改用新的multi-choice聚合投影；现有translated Chat→Anthropic多choice混合缺陷单独登记在 [`deferred.md`](deferred.md)。这样不把direct buffered范围扩成translated delivery行为变更，也不再声称assembler已经共享同一choice state。

## 6. 通用 transactional buffered engine

### 6.1 Attempt collector

`BufferedAttemptCollector`是两条路径共享的通用引擎核心。它协议中立地读取**一个**attempt，拥有raw buffer、raw frame offsets、protocol state与容量计量；通过正向 `UpstreamSource` 标记区分transport tear与本地collector／reader问题，并在退出时确定性关闭source。它返回当前raw bytes、protocol facts与ending，**绝不消费ledger、发布attempt event或发起replacement**。

Collector把raw upstream exchange与client projection分槽：raw request bytes、status／headers／HTTP version／connection snapshot、实际SSE byte count属于attempt exchange；聚合JSON属于client body。Synthetic response不得冒充raw exchange。Cleanup沿用现有primary／cleanup exception排序，每个raw response恰好关闭一次。

### 6.2 两个 orchestration owner

Pre-success non-stream mode adaptation由 `DirectDriver` 的现有attempt loop唯一拥有retry。Collector返回retry verdict后，Chat driver抛出带明确reason的typed failure；driver消费ledger、发布attempt failed、让provider limiter观察event signal，并用本attempt已冻结的final payload／admission／capability snapshot打开下一attempt。为此要新增body-phase prepared retry seam，跳过mutable `attempt.prepare`与新token admission，但仍经过 `RequestContext.begin_attempt()`、rate-limiter acquire、attempt deadline与既有cleanup。

Post-header direct streaming由delivery `BufferedTransactionRunner`唯一拥有retry。它接受initial candidate、shared ledger、draining／deadline状态、existing prepared-replay callback与commit callback；只有replacement response成功建立后才销毁旧candidate，否则旧buffer/state仍可作为最终fallback。它为client-facing路径提供SSE comment keepalive；comment不构成semantic commit。

硬不变量是：**任何组件不得先消费ledger，再把同一failure交给另一个retry owner。** 通用的是collector、facts、verdict与candidate替换规则，不是把两个已经存在于HTTP commit frontier两侧的orchestration loop强合成一个调用栈。

## 7. 两条执行路径

### 7.1 Client `stream:false`

`OpenAIChatCompletionsDriver`在shared attempt loop内调用pipeline-owned Chat attempt adapter。Adapter从 `RequestContext.stream`与endpoint capability生成attempt-local `ChatSendPlan`，在private final payload生成之后、provider send之前决定独立的 `upstream_stream`并补default字段；它不得改写 `RequestContext.stream`。Provider原样发送。Response-header timeout只包围取得headers，whole-attempt deadline继续覆盖body adaptation。

若target原生支持non-stream，adapter不做SSE转换，现有buffered JSON路径保持。若target只支持streaming，adapter在 `attempt.succeeded`／`request.succeeded` 发布前用 `BufferedAttemptCollector`读取SSE。只有见 `[DONE]`且§9.3字段完整才聚合成功；transport tear、clean EOF无 `[DONE]`和已知瞬时流内error变成typed failure，由唯一的 `DirectDriver` owner关闭response、消费ledger、触发limiter并通过body-phase prepared retry seam重发。Provider内部和collector都没有第二套retry。

Adapter结果把raw exchange与client projection分槽。Rate limiter、response-header policy、connection trace与upstream byte accounting读取raw response；server JSON response读取synthetic body。实际SSE byte count不得被synthetic JSON长度覆盖。

### 7.2 Client `stream:true`

Provider按pipeline给出的streaming payload返回raw SSE。Server在headers提交后使用 `BufferedTransactionRunner`替代当前Chat one-shot调用。Runner按同一个Chat facts判完整性；`[DONE]`前的EOF、transport tear、idle timeout或attempt deadline在semantic body提交前可transparent replay。最终成功attempt的raw bytes一次交付；keepalive可以跨attempt出现但不关闭replay窗口。

第一个合法 `[DONE]` 后冻结semantic state并继续读取raw tail。Clean EOF提交全部raw bytes；post-terminal transport tear、idle timeout、attempt deadline或client deadline停止tail collection、提交已收body并记录具体tail ending；post-terminal cap在越界前截尾后提交。后续semantic frame只作为raw tail，不再反转success。Client cancellation／downstream write failure仍不写；本地tail collector failure在截至 `[DONE]` 的buffer完整时提交并保留operator-side failure事实。完整precedence只由 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §5.4定义。

## 8. 流内 error taxonomy

先识别carrier，再分类code。SSE event名为 `error`、JSON object含顶层 `error`键、或flat object的 `type == "error"` 均为明确error carrier；即使payload malformed或同时含 `choices`，也终止当前semantic transaction而不会在EOF时退化成network truncation。Nested carrier读 `error.code`／`error.type`，flat carrier读顶层 `code`／除字面 `error` 外的 `type`。

所有存在且非空的code／type值分别进入闭集：只有它们全部落在同一已知瞬时类时才retry。`server_error` → `SERVER_ERROR`；`rate_limited`、`rate_limit_error`、`rate_limit_exceeded`、`upstream_rate_limited` → 激活现有provider limiter并使用 `SERVER_ERROR`预算。冲突、unknown、缺值或malformed carrier一律不retry。流内没有可信 `Retry-After` 时使用limiter现有默认间隔，不合成等待值。

实现增加携带明确 `RetryReason` 与原始error facts的typed upstream-event failure，避免把流内 `server_error` 假装成实际收到的HTTP 500。Limiter需要独立的event-rate-limit入口；buffered transaction的HTTP 200 headers不能先推进success recovery，success observation延后到body verdict。下一attempt仍从现有 `RateLimiter.acquire()`等待。

Direct streaming上的非瞬时error提交最终attempt截至error frame结束offset的原始SSE并结束，不补 `[DONE]`；collector不能因一个raw chunk里还有后续frame而一并泄漏。Streaming-upstream→non-stream adapter的exact HTTP/body carrier由 [`../error-envelope/spec.md`](../error-envelope/spec.md) §8定义，不在本设计平行维护第二份映射。

## 9. Retry耗尽、carrier与资源

Retry不可用、draining拒绝、预算耗尽或replacement未建立时，direct streaming Chat继续使用现有用户裁定的pre-`[DONE]`最终carrier：仍保留的最终候选partial bytes + 裸断；此前已被replacement取代的attempt不得泄漏。Clean EOF无 `[DONE]` 在此情形合成typed `UpstreamStreamUnterminated`，使accounting记fail而不是ok。

Buffer cap按raw frame boundary在append前执行，保证持有bytes不越过配置上限。`[DONE]`前超限按本地保护失败；`[DONE]`后的tail超限停止tail collection并提交已含完整terminal frame的body。若 `[DONE]` frame本身跨cap，仍是pre-terminal failure，不越界保留。Cap不retry。

每个raw response在重开前恰好关闭一次；cleanup failure通过现有异常链与主失败同时保留。Raw exchange metadata在close前快照并与synthetic client body分槽。`CancelledError`／`GeneratorExit` 不进入普通exception retry分支。Post-terminal tail failure不重开，但不得静默吞掉operator-side事实。

## 10. Response observation、TUI 与 durable schema

Chat observation draft与attempt同寿命，但request-level projection不跟随 `context.current_attempt`自动切换。Replacement开始时旧candidate state仍保留；replacement response成功建立时才原子切换candidate并作废旧state；最终action选定时，把实际提交或fallback交付的candidate snapshot发布到 `RequestContext.response_observation` 与 `RequestTrace`。Replacement在headers前失败而旧candidate成为fallback时，发布旧snapshot并另记replacement failure。

Neutral non-stream JSON由Chat whole-body reader观察；streaming与mode adaptation由同一 `ChatAttemptState`直接投影。`ResponseObservation`下增加独立Chat payload，不复用Responses `status`／`output_items`。字段名、absent／null／unreadable、choice／tool排序、unknown保存与console精确拼法只由 [`../tui/spec.md`](../tui/spec.md) 的“Chat provider observation schema”定义，本设计不复制第二张字段表。

完成后从 [`../tui/deferred.md`](../tui/deferred.md) 移除第0条，并在TUI Spec修订记录注明production-entry证据。Translated Chat→Anthropic的multi-choice projection不在本次direct范围，当前assembler混合choices的问题登记在 [`deferred.md`](deferred.md)，不得从TUI最小choice展示规则反推其delivery行为。

## 11. 实施切片

1. Spec与capability：同步三份行为Spec、client-leg现状和retry status；在 `ModelDescriptor`定义closed Chat capability algebra及provenance。
2. Provider boundary migration：provider clients改为content-transparent并修复CodeBuddy `extra_headers`不下传的现状；内容测试迁移到pipeline，GitHub中性路径行为保持，Xingchen签名继续覆盖pipeline最终bytes。
3. Shared Chat facts与collector：实现raw-frame-aware reader、per-choice state、single-attempt collector与raw／synthetic result分槽；translated assembler只复用reader，不改变其delivery projection。
4. Non-stream adaptation：在Chat driver的shared attempt loop内完成 `ChatSendPlan`、mode adaptation、标准多choice聚合、body-phase prepared retry seam、event limiter signal和typed failure。
5. Direct streaming transaction：接入delivery-owned runner、prepared replay、keepalive、pre/post-`[DONE]` precedence、cap与最终carrier。
6. Observation与TUI：按TUI Spec接入Chat schema、candidate promotion、console、durable记录并关闭deferred。

每个切片按语义独立集成；不以测试变绿作为commit边界。

## 12. 验证设计

先实现可运行行为，再补直接覆盖新增failure surface的测试，不采用TDD，不追coverage数字。

### 12.1 Chat facts

覆盖chunk任意切分、LF／CRLF／multi-line SSE、raw frame offset、`finish_reason`后无 `[DONE]`仍不完整、`[DONE]` semantic freeze、三种error carrier形状、code／type冲突、malformed／unknown carrier不retry、ordinary unknown event在raw路径只记issue而在adaptation路径触发 `unassemblable`、标准多choice字段表、重复／无名tool calls、reasoning、logprobs以及raw／exact usage。OpenAI SDK accumulator若被采用，逐字段对照Spec并证明内部 `parsed`／stream-only index不泄漏。

### 12.2 Buffered transaction

覆盖首轮transport tear或clean EOF无 `[DONE]`、次轮完整且客户端只见次轮；budget耗尽、draining、replacement headers失败只走规定fallback；keepalive跨retry但不提交语义；pre-terminal cap、client deadline、local reader fault不retry；旧response先关闭，discarded attempt facts不进入最终observation。Post-terminal矩阵分别覆盖clean EOF、tear、idle timeout、attempt deadline、client deadline、cap、后续error／第二个 `[DONE]`、local tail failure和client cancellation，断言不replay、semantic facts冻结、raw tail按合同保留或截断。

### 12.3 Provider boundary与non-stream adapter

Provider component tests断言payload/mode原样发送、`extra_headers`、签名和raw response。Pipeline adapter tests覆盖closed capability matrix、explicit client字段优先、neutral profile不变、streaming-only profile的标准多choiceaggregation、tear、无 `[DONE]`、server error、event rate limit、unknown error、unassemblable以及shared ledger。CodeBuddy真实能力不由mock tests冒充；P6仍是后续证据项。

Non-stream adaptation首轮失败、次轮成功必须精确断言upstream calls为2、ledger只花1、两次final payload逐字相同、第二attempt复用admission且不重跑mutable prepare；client contract保持 `stream:false`，两次upstream plan均为 `stream:true`。Body慢于response-header timeout但快于attempt deadline应成功，超过attempt deadline才按network策略；idle与client deadline各保留自身原因且client deadline不随retry重置。每个raw response恰好关闭一次，cleanup failure与primary同时保留，cancellation不进普通retry。Raw SSE bytes、HTTP version／connection、headers与synthetic JSON长度分别断言。Event rate limit还要断言limiter mode、默认等待与单次server-error预算。

### 12.4 Production entry与TUI

用mock upstream走真实direct `/chat/completions` production入口：streaming首轮截断、次轮完整并逐字交付次轮；non-stream mode adaptation首轮失败、次轮聚合成功；streaming与non-stream各有最终completion line与durable observation。Unknown error从production入口断言upstream calls为1、完整raw error进入最终carrier；post-`[DONE]` tail逐字与precedence同§12.2。控制用例能判红绕过shared facts、误接discarded／fallback candidate、只检查finish reason、改写 `RequestContext.stream`、把synthetic length当upstream bytes或消费两次ledger。

Production black box不冒充“证明内部只解析一次”；共享同一 `ChatAttemptState`实例的component test以reader调用计数约束构造seam，production test只证明该state的最终投影到达response与record。

### 12.5 回归与评审

运行相关unit／component／integration tests，再运行项目规定的 `uv run ruff check src tests`、`uv run pyright src tests`、`uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80`；不运行 `ruff format`。最终candidate由独立agent评审一次，仅当candidate字节发生足以使verdict失效的变化时复评。

## 13. 完成判据

- Provider clients不再修改Chat content、强制mode、解析SSE或聚合JSON；它们只声明capability数据并原样执行pipeline准备的请求，CodeBuddy `extra_headers`与Xingchen最终bytes签名均不丢。
- 两类SSE-buffered transaction共享同一个Chat fact reader、完整性判据与single-attempt collector；pre-success与post-header各有且只有一个retry owner。
- 所有retry共享request的 `RetryLedger`，一个failure只消费一次预算，body-phase retry复用frozen payload／admission／capability且保留attempt events。
- 成功SSE transaction必须见 `[DONE]`；已知瞬时error按既定taxonomy重试，unknown／malformed error不重试，unassemblable content不伪装成功。
- 被替换attempt的semantic bytes与observation完全不可见；最终成功streaming bytes逐字来自最终attempt，raw upstream exchange与synthetic client JSON分别计量。
- Standard multi-choice聚合严格实现§9.3字段表；Console与durable schema按TUI Spec从最终provider observation读出native finish reason、reasoning、ordered tool calls与usage。
- Existing translated/block-aware paths、GitHub neutral non-stream path与direct success fidelity不回归；translated Chat multi-choice现状不被本次暗改。

## 14. 未采用方案

未采用方案及原因以 [`decisions.md`](decisions.md) 为权威；本设计不重复改写其来源强度。核心排除包括provider内容特例、pipeline按provider-name分支、全Chat强制streaming、两套局部parser／retry loop、继续延后TUI observation，以及未经P6直接宣称CodeBuddy upstream真实能力。
