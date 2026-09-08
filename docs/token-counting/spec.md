# Spec：adaptive local token prediction

性质：normative、living。本文是 token counting 的唯一完整实施行为合同；它会随新的用户裁决、协议事实或可复核发现修订，而不是冻结为一次调查快照。实施进度不写在这里，见 [status.md](status.md)。

本文中的“必须”“不得”“仅”表示实现约束。未在本文授权的 client-visible 字段、错误状态或产品分叉不得由实现者自行增加。

## 1．范围与术语

本 Spec 约束入站 Anthropic `POST /v1/messages/count_tokens`，以及为该端点服务的 direct Anthropic counter、Anthropic Messages→OpenAI Responses local prediction、历史学习、持久化和观测。它不把 OpenAI Responses 的 standalone-field `PromptTokenAdmission` 扩张为 whole-request counter，也不允许用 local estimate 填充 Chat Completions 缺席的 upstream usage。

- **Frozen target**：路由、model mapping、翻译和 token-relevant request reshape 完成后，本次 inference 真正要使用的 actual provider、exact resolved model、endpoint／wire format 和 payload。Count provider 的选择不得改变 frozen target。
- **Actual sent payload**：某一具体 upstream attempt 在 transport 处实际发送的最终 request bytes；取得 response headers 后，以同一 `response.request.content` 冻结。它优先于从 `RequestContext`、`Attempt.payload` 或日志重建的 payload。
- **Raw total input usage**：同一 attempt 的 upstream-native、未减 cached tokens 的总 `input_tokens`。Normalized fresh input、client-shaped usage 和 output reasoning usage 都不是这个 label。
- **EstimateFeatures**：从 frozen target payload 提取的 immutable、可序列化结构信息；它由 exact categorical `ProfileKey`、quantitative `FeatureVector`、exact-conservation fixed／per-input-item deterministic contributions、fingerprints、cold-start inputs 和 low-confidence reasons组成，不包含待持久化的 raw content。
- **Input item contribution**：与Responses rolling input-prefix chain逐项对齐的非重叠visible／item framing／nested framing、per-item visual presence和released-prior residual；prefix suffix只能从anchor item count后的tuple slice求和。
- **Committed order**：store在成功sample transaction中分配的post-transition global revision；它证明一个historical base是否在longer sample的prequential snapshot前已经committed，不等于观察时间或anchor use order。
- **Prefix checkpoint**：以learning identity／epoch／canonical `ProfileKey`为key，独立于sample FK持久化的prefix eligible latest-16或demoted latest-8最小状态；sample prune不得让它静默恢复eligible。
- **ProfileKey**：只含离散类别的exact compatibility key；任一类别不同就不进入同一neighbor pool。
- **FeatureVector**：带presence state的非负定量feature；它只在同一learning identity和完全相等的`ProfileKey`内参与distance。
- **Learning identity**：决定历史是否兼容的一组版本化维度，详见§5。
- **Unscaled candidate**：exact、prefix、profile或cold-start在operator multiplier和整数化之前产生的数值。
- **Cold-start prior**：随estimator generation发布并版本化的framing表、model-capability visual formula和feature residual coefficient表；它不得退化成“所有新identity固定返回1”。
- **Local prediction**：从兼容snapshot按规定method选出的unscaled candidate，加上method、evidence、identity、profile、history revision和low-confidence reasons。
- **Public finalization**：唯一允许把prediction变成public integer的`finalize_local_prediction()`边界。

## 2．权威与决策来源

### 2.1 权威顺序

1. `docs/.human-controlled/`是需求层的最终耐久权威。当前topic另有两次`user-selected-from-proposal`决定和两句direct user-natural-language要求；§2.2用transcript UUID、tool id、source UUID和timestamp保留其一手provenance。未来人控文档或新的直接用户裁决若与其冲突，必须交用户重裁。
2. 本living Spec承载实施者在这些用户输入边界内推导的完整行为合同。Proposal或user原话没有覆盖的算法、identity、cold-start、样本准入、持久化、prequential error、drift、version migration、state bounds和fallback细节均标为实施者派生，不能借用户选择或一句委托扩写成“用户逐字裁决”。
3. [plan.md](plan.md)规定实施顺序与semantic slices；[status.md](status.md)是唯一volatile projection。它们不能另立行为合同。
4. 现有code、tests、旧docs和point-in-time reports是implementation、transcription或evidence。它们不能反向改写用户选择；code偏离正确记录的decision时，应修code或升级真实fork，不得把本Spec改成defect description。

人控依据包括`docs/.human-controlled/api.md`对`POST /v1/messages/count_tokens`的支持、`docs/.human-controlled/config.example.yaml`对ordered `providers`与`local` calibrated estimate的说明、`docs/.human-controlled/ghc-api.md`对direct Anthropic count能力面的定义，以及`docs/.human-controlled/message-translation.md`与`docs/.human-controlled/request-pipeline.md`的route／translation边界。`.dev/docs/tui/spec.md`继续拥有count request的console presentation合同；本文只定义提供给其aggregate record的facts。

### 2.2 Stable source table

下列transcript是四项decision provenance的共同一手载体：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/4f9bdf9a-5741-47f2-af2c-79b754532c73.jsonl`。UUID和timestamp是stable locator；line number不作为identity。

| ID | Provenance class | Stable source anchor | User-controlled act或exact user text |
|---|---|---|---|
| R1 | `user-selected-from-proposal` | Assistant proposal UUID `8b378b42-2843-433c-8451-9eb94e4e60cc`，tool id `call_vSmGVp2cmJGmJF2mtwXzKOj2`，timestamp `2026-09-06T19:08:40.346Z`；paired user-role tool-result UUID `42764806-9deb-4951-951d-a3584f076f88`，timestamp `2026-09-06T19:12:03.783Z` | 用户选择label `返回低置信估算`。Proposal description为：“排除 opaque bytes，只估可见／结构部分并保留 estimated:true；功能连续，但可能在 prompt cap 附近低估。”Description由assistant撰写，选择行为属于用户；不得把description或harness wrapper称为user-natural-language quote。 |
| R2 | `direct-user-natural-language` | Queued-command attachment UUID `78db73d0-10df-4e90-9207-26eb6e1cd2ca`，source UUID `cdcbf829-3e18-432b-9be4-c732a8758715`，`origin.kind=human`，timestamp `2026-09-06T19:12:33.749Z` | 用户原句：“不要逃避问题了，我们的 local tokenzier 一定要努力做到精确，要增加历史学习能力” |
| R3 | `user-selected-from-proposal` | Assistant proposal UUID `7b55326f-835a-4d47-b749-4e6eae40fdae`，tool id `call_7qflH1cK3JFKeiHInSyIMvR0`，timestamp `2026-09-06T19:13:50.128Z`；paired user-role tool-result UUID `04f71c54-bc93-4e2a-a18b-cdd998987ed2`，timestamp `2026-09-06T19:14:07.969Z` | 用户选择label `混合学习（推荐）`。Proposal description为：“Exact payload命中优先；append-only请求复用最长可信prefix的真实计数并只估suffix；无prefix时使用按provider／model／结构profile学习的校准。精度最高，分阶段实现。”Description由assistant撰写，选择行为属于用户。 |
| R4 | `direct-user-natural-language` | Queued-command attachment UUID `e0d60d1c-2593-4007-b507-af363b3dc812`，source UUID `0310b228-4c7c-4782-81e5-045ed2b4c968`，`origin.kind=human`，timestamp `2026-09-06T19:14:31.333Z` | 用户原句：“具体学习过程不要询问用户，你必须设立完善的精进机制” |

来源核验过程、初次扫描遗漏与addendum见[用户裁决来源取证](reports/user-rulings-source-research-2026-09-07-sonnet.md)；对来源归因缺口的review见[Spec独立评审](reports/spec-review-2026-09-07-gpt-high.md)，采纳范围见[review disposition](spec-review-disposition.md)。这些报告记录evidence与处置，不取代本Spec的behavior authority。

### 2.3 Authorized scope与派生边界

- **R1授权范围**：用户选择了“返回低置信估算”，即在Responses opaque reasoning／media／unknown场景排除opaque bytes、估算可见／结构部分、保留`estimated:true`，并接受prompt cap附近可能低估的已披露取舍。`upstream无count endpoint`、具体public object、cold-start和learning细节是结合route事实与其它decision推导，不是R1 proposal原文。
- **R2授权范围**：用户原话直接要求local tokenizer努力做到精确并增加历史学习能力。把低置信路径限定为cold-start、要求persistence以及否决单一global multiplier，是R1／R3与implementation judgment共同推导，不是R2逐字内容。
- **R3授权范围**：用户选择了exact优先、append-only longest-prefix actual＋suffix、无prefix按provider／model／profile学习校准并分阶段交付的proposal。Configured tokenizer作为identity key、new identity才cold-start、详细eligibility／drift／bounds均是implementation-derived。
- **R4授权范围**：用户原话把具体学习过程交给实现者闭合。算法、sample eligibility、persistence、prequential error、drift、version migration、state bounds与fallback是该委托下的implementation decisions；不得删除exact／prefix／profile或改变其优先关系，是R3已选architecture与该委托边界的派生约束，不是R4逐字原话。

R1／R3的user selection不得因其文字由assistant撰写而降为“未裁决”；同样不得把proposal之外的内容冒充被选择的原文。R2／R4只把引号内exact text归于用户；长解释留在本节派生边界。

### 2.4 实施者派生决定

| 决定 | 来源强度 | 依据与边界 |
|---|---|---|
| Responses local success维持完整对象`{"input_tokens": N, "estimated": true}`，不新增method、confidence、history或learning私有字段 | R1选择结果加向后兼容推导 | `N >= 1`；internal richness不扩张public wire。 |
| Direct Anthropic upstream count success保留标准`input_tokens`和上游存在时的`context_management.original_input_tokens` | 实施者依据“支持该端点”的人控裁决与Anthropic官方count protocol作出的派生决定 | 这是标准字段恢复，不是用户逐字裁决；不得借此增加其它client-visible字段。 |
| Provider name选择同一frozen target的counter transport，不为count另行reroute model | 实施者依据人控provider-key语义、model-specific counting和same-payload label不变量作出的派生决定 | 某provider无法对同一target计数时，该leg不得悄悄换model。 |
| `cold-start-prior-v1`、`ProfileKey`／`FeatureVector`、fingerprints、exact／prefix／profile eligibility、prequential evaluation、drift、epoch、SQLite transaction和容量常量 | R2／R4直接要求、R3选择结果与实现者在delegated scope内的决定 | 数值和分类由本Spec维护；变更时必须追加revision record，并同步transcription tests。 |
| `aiosqlite>=0.22.1`＋SQLite WAL | 批准plan中的implementation decision | 不从library thread model外推business correctness；transaction、retry、snapshot和lifecycle仍由本项目明确实现。 |
| External sequencing gate | 批准plan中的engineering orchestration decision | 它只限制何时触碰shared pipeline seam，不缩减product scope或改变behavior contract。 |

## 3．公开端点、counter选择与错误wire

### 3.1 请求塑形与frozen target

Count请求必须经过与实际inference target相同的model resolution、协议翻译和token-relevant request reshape，生成一次frozen target。Direct Anthropic count以有效的Anthropic request为目标；Anthropic Messages→OpenAI Responses count以最终Responses payload为目标。Local与所有remote counter legs都读取这同一个frozen target，不继承上一条leg的临时状态，也不因计数目的再次进行model mapping。

`providers`按配置顺序懒执行：轮到哪一腿才调用哪一腿。`local`前的remote success不得触发local analyzer；`local`排在首位时不得预问remote；remote failure或unavailable后才进入下一腿。Local tokenizer、worker或history failure不得在尚未轮到local时阻断优先remote counter。

每个非`local`名称必须解析为对应configured provider的counter transport，并以自己的实际名称进入attempt trail。它只能在能够为frozen target的exact resolved model、endpoint contract和payload计数时执行；不能把frozen model reroute成另一个该provider更容易计数的model。不能计数、transport failure、非成功状态、非法JSON、缺席count或malformed count都是该具名leg的失败，按既有retry与ordered fallback继续，不能把routed provider A的结果标成配置名B。

Responses target没有适用的upstream count endpoint时，内部原因是`no-counter`，随后按顺序执行local。Opaque reasoning、media或unknown item只降低confidence，不使有效Responses请求的local leg变成unavailable。

### 3.2 Public success shape

Responses local success的完整JSON object必须严格为：

```json
{"input_tokens": N, "estimated": true}
```

其中`N`的JSON类型是integer，且`N >= 1`。`history-exact`仍返回`estimated:true`，因为该数字来自历史同payload实测，不是本轮remote count call。Method、sample count、low-confidence reasons、operator multiplier、history revision、learning outcome和error metrics只进入内部typed facts与durable observations，不进入public response。

Direct Anthropic upstream success必须保留上游标准count response的`input_tokens`；上游返回标准可选字段时，还必须原样保留：

```json
{"input_tokens": 25000, "context_management": {"original_input_tokens": 70000}}
```

`input_tokens`是context editing后的effective count；`context_management.original_input_tokens`是editing前的original count。上游未返回该可选字段时不得合成。恢复这个标准字段是§2.4所述派生决定，不表示用户逐字裁定了字段细节。

任何local success，包括direct Anthropic fallback与Responses local，都使用现有`input_tokens`＋`estimated:true`形状。Local不得新合成`context_management`；original／effective features和provenance留在内部，直到用户另行授权client-visible变化。

Remote public count只接受`type(value) is int and value > 0`的`input_tokens`；JSON boolean、0、负数、浮点、字符串或缺席值都不是可用remote answer，必须记录具名failure并继续provider chain。Learning label的validator与public count validator分开：符合§7的raw upstream total允许整数0，但绝不允许boolean。

### 3.3 Count-specific Anthropic error contract

`.dev/docs/error-envelope/spec.md`是error category、HTTP status、carrier和cause passthrough的权威；本节完整转录count endpoint使用的子集，使实现者不必依赖“既有mapping”猜public行为。该error-envelope Spec修订时，本节必须在同一change同步，否则以前者为准并把本节视为stale transcription。

当错误由proxy生成，或translated upstream error需要由proxy写成Anthropic方言时，非流式稳定carrier为：

```json
{"type":"error","error":{"type":"<anthropic error type>","message":"<human-readable message>","code":"<stable code>"}}
```

`error.type`、HTTP status和`error.code`由下表共同决定；三者缺一都不是完整合同。`error.param`仅在非空时出现。只有translated upstream body无法解释且存在原文时，`error.upstream_error`才出现，其值保留解析后的JSON value；无法解析JSON时保留原始text，解码失败才用Latin-1作无损byte mapping。`INTERNAL`和`NOT_IMPLEMENTED`的非流式response还带`x-should-retry: false`；其它类别不由本Spec新增该header。

| Category | HTTP status | Anthropic `error.type` | Default `error.code` |
|---|---:|---|---|
| `CLIENT` | 400 | `invalid_request_error` | `invalid_request` |
| `AUTH` | 401 | `authentication_error` | `authentication_failed` |
| `PERMISSION` | 403 | `permission_error` | `permission_denied` |
| `BILLING` | 403 | `billing_error` | `billing_issue` |
| `NOT_FOUND` | 404 | `not_found_error` | `not_found` |
| `RATE_LIMIT` | 429 | `rate_limit_error` | `rate_limited` |
| `OVERLOADED` | 503 | `overloaded_error` | `overloaded` |
| `TIMEOUT` | 504 | `timeout_error` | `timeout` |
| `NETWORK` | 502 | `api_error` | `upstream_network_failure` |
| `UPSTREAM` | 502 | `api_error` | `upstream_failure` |
| `INTERNAL` | 500 | `api_error` | `proxy_internal_error` |
| `NOT_IMPLEMENTED` | 501 | `api_error` | `not_implemented` |

Count-specific roots和wrappers按下表分类：

| Failure | Required result |
|---|---|
| `CountTokensRequestError` | `CLIENT`／HTTP 400／`invalid_request_error`／`invalid_request`，使用上述nested Anthropic envelope。 |
| `CountTokensUnavailable(cause=None)` | `INTERNAL`／HTTP 500／`api_error`／`proxy_internal_error`，`message`为`no token counter succeeded: <attempt trail>`，并带`x-should-retry: false`。 |
| `CountTokensUnavailable(cause=...)` | Wrapper不覆盖成因；递归读穿到最后一个counter failure，按该cause对应行输出status、body语义、type和code。Attempts只用于human-readable trail，不改变category。 |
| `ResponseModeNotSupported` | `CLIENT`／HTTP 400／`invalid_request_error`／`unsupported_response_mode`。 |
| `RoutingError` | `CLIENT`／HTTP 400／`invalid_request_error`／`invalid_request`。 |
| `TranslationRefused` | `CLIENT`／HTTP 400／`invalid_request_error`；`error.code`取异常的stable code，`error.param`取其field path。 |
| `TranslatorNotFound` | `NOT_IMPLEMENTED`／HTTP 501／`api_error`／`not_implemented`，并带`x-should-retry: false`。 |
| `PromptTokenLimitExceeded` | `CLIENT`／HTTP 400／`invalid_request_error`／`model_max_prompt_tokens_exceeded`，message使用无伪造数字的`prompt is too long`形态，field path存在时写`error.param`。 |
| `PipelineAbort(cause=...)` | 与`CountTokensUnavailable(cause=...)`相同，wrapper递归读穿到cause。 |
| `UnknownModel` | `NOT_FOUND`／HTTP 404／`not_found_error`／`not_found`。 |
| `CapabilityMissing`、`EndpointNotSupported` | `CLIENT`／HTTP 400／`invalid_request_error`／`invalid_request`。 |
| `EndpointNotImplemented` | `NOT_IMPLEMENTED`／HTTP 501／`api_error`／`not_implemented`，并带`x-should-retry: false`。 |
| `DescriptorProviderMismatch`、`ProviderNotConfigured` | `INTERNAL`／HTTP 500／`api_error`／`proxy_internal_error`，并带`x-should-retry: false`。 |
| `AuthStateMissing`、`AuthStateInvalid`、`AuthRefreshFailed` | `AUTH`／HTTP 401／`authentication_error`／`authentication_failed`。 |
| 其它`ProviderError`基类或未列出的subclass | `CLIENT`／HTTP 400／`invalid_request_error`／`invalid_request`；新增具名subclass必须先在error-envelope authority分类。 |
| `UpstreamTimeout` | `TIMEOUT`／HTTP 504／`timeout_error`／`timeout`。 |
| 无HTTP response的`UpstreamError`／`UpstreamRejected` | `NETWORK`／HTTP 502／`api_error`／`upstream_network_failure`。 |
| 其它未识别local exception | `INTERNAL`／HTTP 500／`api_error`／`proxy_internal_error`，并带`x-should-retry: false`。 |

`CountTokensUnavailable`的cause若带真实upstream HTTP response，HTTP status保留该response的status，而不是替换成category default。Category按status分类：400和其它未列4xx为`CLIENT`；401为`AUTH`；403通常为`PERMISSION`，body的`error.type`为`billing_error`时为`BILLING`；404为`NOT_FOUND`；408和504为`TIMEOUT`；413／422为`CLIENT`；429为`RATE_LIMIT`；500／502和其它未列5xx为`UPSTREAM`；503／529为`OVERLOADED`。Anthropic `error.type`和default code仍按category表拼写。

可解释的upstream body产生`upstream returned <status>: <message>`，无message时产生`upstream returned <status>`。识别出`CONTEXT_WINDOW_EXCEEDED`时，Anthropic `error.code`覆盖为`model_max_prompt_tokens_exceeded`，message使用error-envelope Spec规定的`prompt is too long`形态，绝不合成本地token数字。无法解释的translated body按稳定carrier保留`error.upstream_error`。

Direct Anthropic counter的真实upstream failure仍受error-envelope Spec的direct passthrough裁决约束：status、原始body和允许的semantic headers原样传递，不强行改写成上述proxy envelope。上述稳定envelope适用于proxy产生的count错误和translated error；这项区分不得被`CountTokensUnavailable` wrapper抹掉。

本Spec不改变既有公开错误类别，也没有新增用户裁决。它只把当前living error-envelope authority与`error_classify.py`的count相关分支完整转录到本主题；任何未来公开error分叉仍须先在error-envelope Spec取得授权。

## 4．结构化特征与deterministic cold-start

### 4.1 `ProfileKey`、`FeatureVector`与`EstimateFeatures`

`TokenEstimator`对frozen target payload只执行pure analysis，产出immutable `EstimateFeatures`。它不得访问history、选择provider、发请求、推进epoch或执行persistence。`EstimateFeatures`必须分开以下两种数据，不能把定量值塞进categorical profile后再要求exact equality：

- `ProfileKey`只保存exact categorical facts：protocol item-kind presence集合、reasoning origin、media source-kind集合、unknown-type的排序SHA-256 digests及overflow、`previous_response_id`是否存在、context-management mode和truncation mode。它不保存token数、bytes、dimensions、pages或item counts。
- `FeatureVector`只保存非负quantitative values及每维独立presence state：known total、instructions／tools／message／function-call／function-output／reasoning-summary text tokens、各item-kind counts、opaque reasoning bytes、media count／decoded bytes／pixel count／PDF pages，以及unknown item count／JSON bytes。不可得与真实0必须分开。

`EstimateFeatures`还包含presence-aware `capability_visual_tokens: int | None`、canonical full-payload fingerprint、top-level context fingerprint、ordered rolling input-prefix fingerprint chain、raw sent-body SHA provenance、estimator generation、profile schema revision和low-confidence reasons。`capability_visual_tokens=None`表示exact resolved capability没有公式或任一所需media metadata不完整；非负integer表示公式输出，真实0不得与缺席混同。该derived visual output独立于`FeatureVector`，避免与raw pixel／page quantities重复改变profile distance；它也独立于`known_tokens`，不得塞进known-text components。Unknown type不持久化原始任意字符串，只持久化按digest bytes排序的最多8个SHA-256 digests、unknown type总数和`overflow`标志。完整原值只可在本次内存analysis中参与分类，不得进入learning store或durable log。

Responses `EstimateFeatures`还必须以非重叠contributions精确守恒。`FixedContextContribution`保存input之外instructions／tools／tool declarations的`visible_tokens`、`framing_tokens`和finite signed `prior_residual_tokens`；framing是非负integer且为4的倍数。每个top-level input item对应一个`InputItemContribution`，保存`visible_tokens`、严格为4的`item_framing_tokens`、非负且为4倍数的`nested_framing_tokens`、`capability_visual_tokens: int | None`和finite signed`prior_residual_tokens`。Per-item `known_tokens`只由visible＋两种framing派生，不另存可漂移total。

Contribution tuple与rolling prefix tuple长度相等，第i项对应item count i＋1；空input两者均为空。Whole `known_tokens`必须严格等于fixed-context known＋全部item known，也必须等于components token sum。Whole prior residual只从fixed context＋items求和。Whole `capability_visual_tokens`只从item tuple重建：任一item visual为None则whole为None，否则为sum；persisted aggregate与reconstruction不一致属于corruption。DTO不保存raw item／media／capability object。

Feature producer必须按每个input item使用独立accumulator，再合并whole components／FeatureVector。Raw string、null／number／bool等non-object、message scalar／structured parts、reasoning summary、function call、function output scalar／list、function-output text＋media和unknown shape都必须把visible、item framing与每个nested part framing恰好归属一次。调换context／item、漏算或重复nested framing即使whole total被人为凑平也必须由conservation／shape tests判否。

### 4.2 Cold-start equation

Cold-start必须从payload导出的量计算，不能对所有新identity固定返回1。版本`cold-start-prior-v1`定义以下未量化方程：

```text
known_tokens = visible_text_tokens + framing_v1
cold_start_unscaled = known_tokens + capability_visual_tokens + Σ(coefficient_v1[feature] × feature_value)
```

方程中的`capability_visual_tokens`在DTO槽为`None`时取0；`None`仍保留为持久化presence事实，不能在DTO／SQLite中先改写成0。`cold-start-prior-v1`的residual由下表features及coefficients确定，不另持久化一份可漂移的aggregate。

`visible_text_tokens`是configured tokenizer以ordinary-text模式对所有已知可见／tokenizable fields分别计数后的和，包括Anthropic top-level `system`、Responses `instructions`、两种协议的tool declarations、message role／text、function-call name／arguments、function-output、可见reasoning summary，以及Anthropic `tool_use.id`／`name`、`tool_result.tool_use_id`／`is_error`。String field直接编码原字符串；可见structured value先按canonical JSON编码，其中object key按Unicode code point升序、array保持原序、UTF-8输出且不含无意义空白，再把完整结果作为一个component编码。Components不靠人工newline拼接；边界开销只来自`framing-v1`。任何reserved spelling都作为ordinary text处理，不得让tokenizer special-token识别把合法请求变成错误。

`framing_v1`是下表各适用行的整数和。Presence指字段存在且container非空；每个opaque、media、unknown item即使没有visible text也必须贡献自己的item／block framing。

| Protocol shape | `framing-v1` contribution |
|---|---:|
| Responses non-empty top-level `instructions` container | 4 |
| Responses non-empty top-level `tools` container | 4 |
| Each Responses tool declaration | 4 |
| Each Responses `input` item，包括opaque／media／unknown与non-object item | 4 |
| Each structured content or summary part nested in a Responses item | 4 |
| Anthropic non-empty string `system`，或list中的每个system block | 4 |
| Anthropic non-empty top-level `tools` container | 4 |
| Each Anthropic tool declaration | 4 |
| Each Anthropic message | 4 |
| Each structured content block in an Anthropic message，包括thinking／media／unknown block | 4 |

`capability_visual_tokens`只从exact resolved model descriptor导出的immutable、pickle-safe tokenization capability snapshot计算，不把完整provider descriptor塞进feature core或process worker。Analyzer按每个media item分别应用snapshot中带revision的resize／limit／visual formula，再对各item结果求和；不得先聚合pixel count后回推，因为同面积不同aspect ratio及多item边界可产生不同ceil结果。Anthropic image capability当前按descriptor先执行其resize／limit规则，再对每张图使用`ceil(width / 28) × ceil(height / 28)`；PDF或其它provider由各自descriptor的公式计算。全部适用media均有公式与metadata时，`EstimateFeatures.capability_visual_tokens`保存这个非负integer sum；公式缺席或任一所需dimensions／pages不足时，该槽为`None`，方程贡献0并增加具名low-confidence reason，绝不以base64、URL、`file_id`字符串长度或aggregate pixels代替。改变visual formula或revision必须增加estimator generation；descriptor capability变化同时改变descriptor fingerprint。Full cold-start保留whole all-or-none语义：任一item visual为None时whole visual term取0并保留reason。Prefix suffix则按§6.2只切appended item contributions，每个item的visual独立value-or-zero；旧prefix的None不得抹掉新append item已知visual。这是同一per-item事实的method-specific aggregation，不是两份可独立漂移的visual source。

`cold-start-prior-v1`的additional residual coefficient table如下。所有值单位为tokens per feature unit，且只加在framing和capability formula之后；本版没有足够独立evidence为这些carrier指定非零系数，因此明确发布为0，而不是隐含遗漏。

| Feature coefficient | v1 value | Required low-confidence reason when feature is present |
|---|---:|---|
| `responses.opaque_reasoning_bytes` | 0 | `zero-prior:responses.opaque-reasoning-bytes` |
| `responses.opaque_reasoning_items_beyond_framing` | 0 | `zero-prior:responses.opaque-reasoning-items` |
| `media_without_capability_formula` | 0 | `zero-prior:media-without-capability-formula` |
| `pdf_pages_without_capability_formula` | 0 | `zero-prior:pdf-without-capability-formula` |
| `unknown_json_bytes` | 0 | `zero-prior:unknown-json-bytes` |
| `unknown_items_beyond_framing` | 0 | `zero-prior:unknown-items` |
| `anthropic.opaque_thinking_bytes` | 0 | `zero-prior:anthropic-opaque-thinking-bytes` |

未来新增quantitative feature而`cold-start-prior-v1`没有对应coefficient时，lookup结果必须显式取0，并增加`missing-prior:<feature-name>` low-confidence reason。修改framing值、visual formula selection或coefficient table必须发布新的cold-start prior revision并增加estimator generation；旧history不得静默复用。

Equation可以得到0或fractional unscaled value；只有§6.4的唯一finalization执行operator multiplier、`ROUND_CEILING`和minimum-one。Minimum-one不能提前塞进cold-start来掩盖没有使用payload features的固定1实现。

### 4.3 Ordinary-text special spellings

客户端提供的text始终是ordinary text。字面`<|endoftext|>`、`<|endofprompt|>`以及configured tokenizer当前或未来声明的**全部**special-token spellings都只表示这些普通字符；它们不得从string content获得control-token semantics，也不得改变该字段原本的known-text、opaque、media或unknown分类。

这个不变量覆盖全部本地文本计数surface：Anthropic top-level `system`、message content和tool schema；Responses `instructions`、message content、tool schema、function-call arguments与function-call output。Structured value按§4.2 canonical JSON形成普通字符串后也受同一规则约束。实现必须集中使用`encode_ordinary()`或在所有输入上产生相同ordinary-token sequence的语义等价接口。

以下实现路线全部禁止：使用configured tokenizer的default special-token guard；通过`allowed_special`把客户端字面串解释成control token；在HTTP endpoint捕获encoding error后fallback；只修Responses而保留Anthropic failure；只从denylist移除`<|endoftext|>`这一种spelling；只修某一个message position；保留“special spelling必须触发worker failure”的旧测试预期。Worker failure metrics必须改用synthetic estimator exception触发，不能继续借合法ordinary input制造failure。

### 4.4 Opaque、media与unknown

Opaque reasoning ciphertext、base64 image／PDF bytes和unknown opaque carrier不得送入ordinary text tokenizer。增大这些bytes时，visible-text term必须保持不变，对应opaque／media／unknown quantitative features必须变化；无论residual coefficient是否为0，每个item或block的framing仍计入`known_tokens`。可见reasoning summary、message text、tool name／arguments／output和其它已知文本继续按configured tokenizer计数。

排除bytes不等于忽略结构。Cold-start使用上述deterministic equation；history通过`FeatureVector`学习opaque／media／unknown contribution。即使没有兼容history，合法Responses payload仍产生由其known text、framing、可用visual formula和released prior共同决定的public estimate，并带`estimated:true`。

Unknown字段必须进入canonical identity，避免history false-hit；它不进入ordinary-text count时必须增加low-confidence reason。未知结构的默认行为是保守miss和feature-aware learning，不是整对象`dumps()`后当文本，也不是unavailable。

### 4.5 Anthropic thinking

Thinking retention必须由exact resolved model的capability和turn位置共同决定，不得只看assistant role，也不得统一“全算”或“全不算”。

- Current assistant turn的thinking始终计入input。
- Keep-all models保留并计入所有prior assistant thinking；当前官方能力族包括Claude Opus 4.5及以后Opus、Claude Sonnet 4.6及以后Sonnet，以及官方列入keep-all的Fable／Mythos系列。
- Last-turn-only models由API自动剥离更早thinking，因此更早blocks不进入effective input；当前官方能力族包括更早Opus／Sonnet和截至Claude Haiku 4.5的Haiku。
- `redacted_thinking`与`thinking`遵循同一preservation capability；opaque内容保留feature与low-confidence reason，不因不可读就贡献0 framing，也不把opaque carrier按ordinary text处理。
- Model capability缺席、未知或与payload冲突时，local仍给出低置信deterministic baseline，但必须记录reason；不得把某一代model规则外推到所有model。

### 4.6 Image、PDF与context editing

Image token语义取决于decoded dimensions、model capability和provider处理，不取决于base64 wire长度。PDF至少保留page count、media count、可得dimensions／decoded bytes与presence；不可解析或remote URL／file reference不允许靠短字符串长度伪装成visual count。历史不足时使用§4.2 equation，不能退回ciphertext-as-text。

Count与send必须共用同一effective-request transform。启用context editing时，prediction针对effective payload；original与effective各有独立features／fingerprints和内部provenance，不能把pre-edit estimate当post-edit结果。Direct Anthropic remote count按官方协议返回effective `input_tokens`，并在上游提供时保留original count。Count只是preview，不修改客户端conversation history。

## 5．Identity、`ProfileKey`与distance pool

每个history row、anchor、error window和snapshot必须绑定完整`LearningIdentity`：actual provider、exact resolved model、endpoint／wire format、configured tokenizer、token-relevant provider descriptor fingerprint、estimator generation、profile schema revision和learning epoch。任何一维变化都不得静默复用旧统计。Cold-start prior revision属于estimator generation；表或framing变化必须改变generation。

Canonical full-payload fingerprint覆盖全部token-relevant结构与unknown字段，只忽略唯一已确认与input count无关的transport字段`stream`。它基于解析后的canonical structure，而不是JSON空白或key order；raw sent-body SHA只保存provenance，不替代token identity。

Prefix context fingerprint覆盖除`input`和`stream`外的全部top-level字段。Rolling prefix hash按canonical input item原顺序串联，并与item count一起定位anchor。Instructions、tools、model capability、context management、truncation、unknown top-level字段或item顺序变化必须使不兼容prefix失配；append-only才可能命中。

每个committed sample保存positive global `committed_order`，值为其成功sample transaction的post-transition global revision。Pending sample在policy边界携None，store必须在codec前stamp；public／persistent snapshot不允许None。一次sample transaction只插入一个sample，因此base在longer的prequential snapshot中available当且仅当`base.committed_order < longer.committed_order`。`observed_at_us`只决定newer preference，不能证明happened-before；anchor `last_used_order`也不能代替commit order。Same timestamp仍可按committed order合法配对；future multi-sample transaction必须扩成`(global_revision,batch_ordinal)`。

Historical longer必须与current query具有同identity／active epoch和exact `ProfileKey`；base不要求同ProfileKey，因为append可首次引入image／function／unknown kind。Base必须strictly shorter、same context、rolling-prefix匹配且committed earlier。每个longer只选一个base：较大coverage、较大`observed_at_us`、`process_boot_id`／`request_id` UTF-8 BINARY ascending、numeric attempt ascending。保留全部bases会重复计权；仅以timestamp过滤会丢same-time合法pair。

Checkpoint logical identity是`(identity base, epoch, canonical ProfileKey JSON)`；canonical JSON以BINARY equality进入PK／UNIQUE，SHA-256 hash只作普通lookup index。Lookup还必须decode并逐字段比较ProfileKey。Test-only same-hash／different-JSON rows必须共存且各自可读；hash-only identity或silent overwrite禁止。

`ProfileKey`只含exact categorical compatibility facts：protocol item-kind presence集合、reasoning origin、media source-kind集合、unknown-type排序digests与overflow、`previous_response_id` presence、context-management mode和truncation mode。两个sample只有`LearningIdentity`相同、active epoch相同且`ProfileKey`逐字段相等，才进入同一neighbor pool。Item counts、bytes、tokens、dimensions和pages全部属于`FeatureVector`，不得参与`ProfileKey` equality。

MAD pool是当前sample进入state之前，同一`LearningIdentity`、active epoch和exact `ProfileKey`下全部仍被保留的eligible profile samples；它先于nearest-31选择，用于每个quantitative dimension的尺度计算。每一维只用presence为present的历史值，先`log1p`再求median和median absolute deviation；少于一个present值或MAD为0时scale取1。

Query与candidate某维都absent时，该维distance为0；只有一侧present时，该维distance固定为4；两侧都present时，该维distance为`abs(log1p(query) - log1p(candidate)) / scale`。总distance是所有quantitative dimensions的equal-weight L1和，不另加手调权重。Neighbor按distance升序、observation时间降序、sample id字节序升序形成全序，取前31条；当前label不得进入MAD pool、distance或neighbor selection。

## 6．Prediction与唯一finalization

### 6.0 Candidate identity、method champion与selected key

`PredictionMethod`仍只有且按优先级固定为`history-exact`、`history-prefix`、`profile-calibrated`、`cold-start`。Internal estimator variant不得伪装成第五种method。每个candidate用closed `PredictionCandidateKey(method, variant)`唯一标识；`variant`恰有`median`、`deterministic`、`additive`和`multiplicative`四个成员，V1只允许以下七种pair：`history-exact/median`、`history-prefix/deterministic`、`history-prefix/additive`、`history-prefix/multiplicative`、`profile-calibrated/additive`、`profile-calibrated/multiplicative`、`cold-start/deterministic`。

一个点时`PredictionRecord`必须保存当时存在的全部candidate keys／unscaled values、represented methods的point-in-time champions及唯一global `selected_key`。Represented method指该record中至少存在一个candidate key的method；每个represented method恰有一个`MethodChampion(candidate_key, eligible_for_selection)`，没有candidate的method必须没有champion。Candidate key在record内唯一；champion key必须存在于该record并属于同method；missing represented-method champion、absent-method extra champion、wrong-method或missing candidate key全部非法。Cold-start candidate始终存在；represented `history-exact` champion与cold-start champion必须`eligible_for_selection=true`，prefix／profile champion才可按点时demotion／promotion为true或false。Global selected key从represented champions中按§6.1顺序取第一个`eligible_for_selection=true`者；exact-false或cold-false record属于corruption，即使另一个method使selected结果暂时不变。`eligible_for_selection`不能从global selected反推：exact优先时仍要保留represented prefix是否demoted、represented profile是否promoted的点时事实；demoted prefix继续以false champion保留challenger predictions／errors。

每个`PredictionEvaluation`绑定完整candidate key而非method alone。Diagnostic retention、paired windows、offline replay、drift reconstruction和persistent graph全部以candidate key对账；method-level demotion／promotion比较使用各record明确保存的该method champion，不能事后以当前algorithm或list ordinal重选。Ordinal只验证stable candidate list order，不充当candidate identity。Candidate tuple必须是§6.0七种pair所列顺序的subsequence；method champions严格按`PredictionMethod` enum order。`evaluate()`沿candidate tuple order返回，DTO／codec必须拒绝非canonical order，不能由store单方面重排掩盖producer drift。

`sample_count`只表示该candidate自身实际使用的history evidence：exact median为1～5个actual；deterministic prefix为所选single anchor的1；learned prefix／profile为参与该variant median／neighbor计算的evidence数且至少3；cold-start为0。它不表示整个request涉及的unique rows，也不把anchor的1加到learned suffix pair count上。

### 6.1 Method顺序与exact eligibility

Predictor必须按以下顺序选择第一个合格method：

1. `history-exact`：active identity／epoch的full fingerprint命中。每个fingerprint保留最近5个actual，预测取这些值的median；允许内部actual为0。
2. `history-prefix`：exact未命中且存在符合§6.2的最长可信rolling prefix。
3. `profile-calibrated`：没有合格anchor时，按§6.3从同identity和exact `ProfileKey`的history产生并promote candidate。
4. `cold-start`：没有合格history method时，严格使用§4.2 equation。

Candidate availability与global selection分开。每次prequential record先构造当时全部available candidates，再按上述method顺序选global champion；exact命中时仍须构造strictly shorter可匹配prefix challengers，Task 4B以后也须构造available profile challengers。Historical record只保存其点时真实available candidates，不得事后回填未来variant。Request-side decision仍只携global selected method的intent。

Active-epoch exact hit始终合格，generic error comparison不得绕过它。它只在full-fingerprint miss，或exact drift已完成new epoch transition、旧anchor因而离开active epoch后停止参与。触发drift的那笔actual到来之前，本轮已交付prediction仍是exact；transition只影响随后请求。

Prefix可以按§6.2唯一的demotion规则暂时不合格；profile只有达到§6.3 promotion条件才合格。这些eligibility变化不改变exact → prefix → profile → cold-start的method顺序，也不删除任何method。

### 6.2 Prefix suffix、demotion与recovery

Prefix必须先满足同一LearningIdentity、active epoch和完全相等的top-level context fingerprint，再按以下total order选一个rolling-prefix anchor：较大`item_count`优先，较大`observed_at_us`优先，最终按`process_boot_id` UTF-8 BINARY、`request_id` UTF-8 BINARY、numeric `attempt_index`依次升序。Prediction使用这个单一anchor的actual tokens，再加一个unscaled suffix candidate；只有history-exact聚合最近5个actual并取median，prefix不得跨多个source samples聚合成无法由单一`AnchorUseIntent`表达的值。Predictor必须自行执行该total order，不能依赖`LearningSnapshot.prefix_anchors`恰好已排序。

Suffix只分析selected anchor item count之后的`input_item_contributions` tuple slice。每个appended item贡献自己的derived known tokens、visual value-or-zero和released-prior residual；它的item／nested framing已经恰好包含在item known中。`suffix_baseline_delta = Σ(item.known_tokens + visual_or_zero + item.prior_residual_tokens)`，不得重复top-level fixed context、使用常数1、做whole-request差分或literal known-only delta。旧prefix item visual为None而新item visual已知时，新item仍独立贡献；None→None＋new present、0→present、present→present与present→None都必须既不漏算也不double count。

`history-prefix/deterministic`始终等于selected single-source anchor actual加current `suffix_baseline_delta`。Historical pair按§5选择committed earlier的single base；`actual_delta = longer.actual - base.actual`，`historical_suffix_baseline_delta`从longer contributions在base item count后的slice计算。Additive evidence要求actual delta>0、baseline>=0，保存`actual_delta - baseline`；multiplicative evidence要求actual delta>0、historical baseline>0，保存`log(actual_delta / baseline)`。两种candidate各至少3条eligible pairs。

Additive candidate为`anchor actual + current baseline + median(residuals)`；multiplicative为`anchor actual + current baseline × exp(median(log ratios))`。Current baseline等于0时，只要已有3条合法历史ratio evidence，multiplicative candidate仍存在且suffix值为0；candidate availability不取决于current scalar。Literal known-only会把visual／prior重新学成residual，禁止。

Prefix variant selection只读retained `PredictionRecord` candidates＋对应sample actual，不读bounded diagnostic evaluations。Records必须属于current exact `ProfileKey`、actual>0，并在自己的prequential时点同时包含deterministic及全部当前待比较learned variants。按`observed_at_us`降序、sample key UTF-8 BINARY／numeric降序取newest 31；共同records少于8时deterministic胜。达到8后learned variant只有median APE严格低于deterministic才可胜；完全相等顺序为deterministic、additive、multiplicative。Record保留全部available prefix variants，不能只保留champion。63条older32／newest31反转fixture和`LearningSnapshot.evaluations=()`fixture必须分别判否遗漏slice与误读diagnostics。

Prefix eligibility不是从可被sample prune的records每次重放，而由`(identity, epoch, canonical ProfileKey JSON)`checkpoint拥有。Missing row表示implicit eligible empty。Eligible checkpoint保存按committed order递增的latest最多16条prefix／profile／cold point-in-time champion APE triples；demoted checkpoint保存demotion后latest最多8条recovery evidence，prefix／cold必有，profile可缺。Checkpoint不绑sample FK，sample prune后仍存；new epoch清除old active checkpoint participation。

Eligible mode只有actual>0且三方point-in-time champions齐备时追加current ProfileKey evidence。满16条且prefix median APE分别严格比profile与cold高>0.05才在处理该label后demote；等于0.05不触发，触发第16条不进入recovery。Demoted mode在prefix challenger和cold存在时维护sliding latest8；profile只有同8条全部存在才作为alternative。Latest8上prefix median APE<=最佳available alternative时恢复并显式删除checkpoint，平手恢复；8 bad后8 good必须由后8决定。Actual0、缺prefix或缺当前mode required facts都NoChange。Profile A evidence不得读取或更新Profile B。

Checkpoint policy在prediction／evaluation之后产生required logical command；store在same sample transaction应用。Task 3B只建立carrier／store mechanics，Task 4B在profile和learned prefix champions均已可用后实现上述16／8 policy。Task 4A／4B-P必须显式NoChange，不提前demote。

### 6.3 Profile distance、candidates与promotion

Profile neighbor pool严格使用§5的same identity＋active epoch＋exact `ProfileKey`；distance是§5定义的equal-weight L1，presence mismatch penalty固定为4，MAD pool和tie-break不得由实现另选。

最近31个neighbors产生`profile-calibrated/multiplicative`与`profile-calibrated/additive` candidates。Multiplicative candidate只用`actual > 0 and known_tokens > 0`样本，计算`known_tokens × exp(median(log(actual / known_tokens)))`；additive candidate使用全部非负合格样本，计算`known_tokens + median(actual - known_tokens)`。任一candidate至少有3条合格样本才存在；存在的candidate全部进入record并分别evaluation。

Profile promotion只比较同一批actual上的paired prequential errors。对当前存在的profile variants和cold-start，取各自在prequential时点全部同时存在的共同records；至少有8个共同paired samples，且profile candidate的median APE严格低于cold-start的median APE，profile method才`eligible_for_selection=true`。Multiplicative与additive在同一共同window比较；相等时additive成为profile method champion，任一与cold-start相等时profile不合格、global selection保留cold-start。Actual为0不进入ratio、APE、promotion或demotion window。

### 6.4 数值精度与operator multiplier

Exact median、prefix sum／delta、profile candidates和cold-start都保持未量化数值到唯一`finalize_local_prediction(value, multiplier)`。任何estimator、predictor、store、driver或projection不得提前floor、nearest-round、ceil后再传递，也不得在finalization后再次缩放或舍入。

Finalization严格按下列顺序执行：

1. 用`Decimal(str(value))`与`Decimal(str(multiplier))`相乘。
2. 对乘积执行`ROUND_CEILING`。
3. 将public结果限制为minimum one，即`max(1, result)`；触发时记录内部`minimum-one` reason。

`local_estimate_multiplier`默认1.0，必须是有限且`>= 1.0`的operator bias。它只作用于最终local prediction，不缩放remote count，不进入training label、candidate、prequential evaluation、champion、drift或history。旧Responses scalar calibration和0.5～3.0 clamp不得进入新predictor。

## 7．Learning sample 与 prequential 顺序

### 7.1 Actual sent-body authority

每个upstream attempt拥有immutable `SentRequestSnapshot`与独立learning offer状态。Snapshot只从该attempt的transport request `response.request.content`取得，并包含`(process_boot_id, request_id, attempt_index)`、endpoint、actual provider、exact resolved model、tokenizer、descriptor fingerprint和raw body SHA。Retry、reroute和hedge各自产生不同attempt snapshot，绝不共享actual或request-level mutable slot。

不得从`RequestContext.payload`、`Attempt.payload`、translated object重序列化、request-log adjacency或“最近一次usage”重建训练identity。日志只可辅助取证，不能替代attempt-bound sent bytes。

### 7.2 Sample eligibility

一个sample只有同时满足下列条件才可学习：

- Snapshot与usage属于同一个actual provider／resolved model／attempt／actual sent payload。
- Endpoint和wire format在本Spec允许的学习面内。Responses inference的`response.completed`，以及携带完整、consistent raw usage的`response.incomplete`可以学习；`response.failed`、cancelled、无usage或usage inconsistent不得学习。
- Raw total upstream `input_tokens`存在，`type(value) is int and not bool`，且`value >= 0`。Cached部分不得扣除；normalized fresh input不得替代。
- Upstream terminal和raw usage已成立后，即使后续client translation或delivery失败，该input sample仍可学习；学习事实与request success必须分槽，不能把“sample committed”投影成“client收到成功response”。
- Attempt-local compare-and-set只允许`offer()`一次；store的unique sample key`(process_boot_id, request_id, attempt_index)`再提供transactional exactly-once。重复必须返回typed duplicate，不得再次transition或递增revision。

Direct Anthropic count success可以用同一frozen payload与remote count形成样本；Responses inference success用actual sent payload与该attempt的raw total input usage形成样本。Output `reasoning_tokens`只描述output，不得成为未来input label；不得把累计output reasoning、另一个attempt usage或另一个provider count拼到当前payload上。

### 7.3 Prequential evaluate-before-learn

Single consumer取得sample后，必须先在尚未包含当前sample的最新committed snapshot上生成点时`PredictionRecord`：保存`history-exact`、所有当时存在的prefix variants、所有当时存在的profile variants和cold-start candidates，按§6.0保存每represented-method champion／eligibility与global selected key；随后按candidate key为每个candidate计算`PredictionEvaluation`，最后学习并提交。当前label在自身candidate generation、method champion selection或evaluation之前可见即为training leakage。

`actual > 0`时，每个candidate记录signed relative error、absolute error和absolute percentage error。`actual == 0`只进入exact history、additive evidence与absolute error；multiplicative ratio、relative error、APE、champion paired windows和drift windows全部缺席，且prefix suffix不从非正actual delta训练。

Error evidence分成两个不可互相替代的序列：每candidate key／`ProfileKey`的prequential evaluation sequence用于variant comparison与diagnostic retention；每record冻结的point-in-time method-champion／`ProfileKey` evaluation sequence用于method demotion／recovery与drift。缺席candidate不制造0 error，absent method没有champion sequence entry；rejected sample不进入任何window。所有记录携带用于prediction的history revision和active epoch，使offline progressive replay能重建“先predict／evaluate，再learn”的顺序，且不得以当前algorithm事后重选历史champion。

Checkpoint policy返回required logical command union：`NoPrefixCheckpointChange`、`ReplacePrefixCheckpoint(profile_key,mode,evidence,expected_prior_state_revision)`或`DeleteRecoveredPrefixCheckpoint(profile_key,expected_prior_state_revision)`。NoChange只表示policy确实运行并选择no-op；Replace的expected revision为None只表示row absent，Delete必须指现存revision。Task 3B synthetic transitions、Task 4A与4B-P都显式NoChange；Task 4B才产生replace／delete。Missing command不是合法default。

Logical `ReplacePrefixCheckpoint`可携带一个`PendingPrefixChampionErrorTriple`作为当前sample的pending evidence carrier。该carrier不含`committed_order`，只能出现在policy-return logical command中，且一次command最多有一个pending entry；它必须是evidence序列的唯一tail，所有历史entries都必须已有positive committed order。Multiple pending entries、non-tail pending、历史entry缺order或persistent/public checkpoint含pending carrier都属于corruption。Store计算`next_global_revision`后，必须把该唯一pending tail与当前sample同时stamp为同一positive `committed_order`，再构造persistent `PrefixChampionErrorTriple`并执行codec／row preparation；policy不得猜测该revision，store不得在stamp前encode。

Store在sample transaction后产出required `PrefixCheckpointStoreOutcome`第二事实，不能由main outcome或policy command反推。Closed families为：policy执行后的NoChange／Applied／Deleted／CapacityRejected／CapacityRolledOver；policy未进入的`NotAttempted(reason)`；policy callable已进入但transaction未commit的`NotCommitted`。NotCommitted不要求policy已经返回command，也不持久化未提交command内容。唯一main-outcome矩阵是：committed只接受五种committed results；duplicate只接受NotAttempted duplicate；rejected只接受NotAttempted sample-rejected；failed在policy前只接受NotAttempted failure-before-policy，policy entry后只接受NotCommitted；post-COMMIT cancellation仍携committed observation和实际committed result。Sample被同事务prune不改写真实checkpoint outcome。

CapacityRolledOver nested transition是唯一capacity transition authority；`TokenLearningObservation`不得另有standalone capacity field。CapacityRolledOver与drift互斥，drift存在时command和outcome都必须NoChange。CapacityRejected只允许committed、missing-row Replace及§8.5零收益global-cap分支。Applied／Deleted的ProfileKey、state revision和order必须等于logical command与final state。DTO、event codec和all-epoch graph逐矩阵拒绝missing、extra、wrong family、unknown variant和standalone transition。

Policy callable entry是attempted的唯一边界：duplicate／eligibility／queue／feature／snapshot／startup在entry前失败为NotAttempted；policy内部抛错、command validation、CAS、write、revision、event或pre-commit cancellation为NotCommitted并rollback；confirmed COMMIT成功后不得降成failed。不同phase必须在真实call sites注入，不用同一helper冒充。

### 7.4 Production learning closure

Automatic improvement必须在production dataflow闭合，而不是只让unit test预置history。每个eligible Responses inference attempt从transport冻结actual sent body，由同一attempt的final raw total input usage构造sample并恰好offer一次；writer以pre-learn snapshot计算所有candidate和errors，在同一transaction提交sample、evaluation、anchors和revision；reader随后发布包含该revision的validated snapshot。

同一frozen target的后续public count必须从该snapshot命中`history-exact`并使用已提交actual median；保持top-level context而只append input items的后续count必须命中`history-prefix`并使用anchor actual加§6.2 suffix。两条路径都必须在internal facts中保留sample provenance、pre-learn prediction／error、selected method、unscaled prediction和finalized integer，且public body仍只含`input_tokens`与`estimated:true`。

丢失inference-side offer、丢失sample→anchor transition、predictor不refresh committed snapshot，或把normalized fresh input／output reasoning usage替换成raw total label，都必须被§12的production-entry验收分别判否。Mock usage只证明本代理的接线、配对、state transition和后续selection；它不能冒充真实provider billing或真实tokenizer accuracy。

## 8．Persistence、snapshot与state bounds

### 8.1 Cancellation-safe `aiosqlite` ownership

所有会进入`aiosqlite` worker queue的动作必须经一个共享的confirmed-completion helper或语义等价机制执行；覆盖connection open、PRAGMA、`BEGIN`／`BEGIN IMMEDIATE`、execute、cursor fetch／close、`COMMIT`、`ROLLBACK`、checkpoint和connection close。Writer、reader、migration、`record_event()`、`record_anchor_use()`与`prune()`不得各自实现较弱的await包装。

Helper必须在await前登记queue action及其completion future，并在outer task收到cancellation后shield该future直到worker明确返回成功或失败。Connection lifecycle wrapper在await open前登记；open await被取消时，wrapper先shield到open结果，若connection确实创建则confirmed-close，最后才传播cancellation，因此取消不得泄漏未登记的worker thread或connection。

`BEGIN` attempt一旦enqueue，即使await被取消，也必须确认它是否执行。若BEGIN成功且COMMIT尚未enqueue，owner必须confirmed-rollback、confirmed-close所有cursor，再传播typed cancellation。Pure transition返回处或任一INSERT／read await点取消时，active transaction遵循同一rollback规则。

`COMMIT`一旦enqueue就进入不可回退阶段：必须shield到确定结果。若COMMIT成功，store先形成与已提交revision一致的durable `TokenLearningObservation`并完成cursor／connection cleanup，然后以`StoreOperationCancelled(committed_observation=<observation>)`或等价typed outcome传播cancellation；不得声称rollback。Caller重试同一sample时，由unique sample key得到duplicate。若COMMIT明确失败且transaction仍可回滚，则confirmed-rollback后返回`committed_observation=None`的typed failure／cancellation。

`StoreOperationCancelled`必须继承`asyncio.CancelledError`，并携带closed `phase`和`committed_observation: TokenLearningObservation | None`；无信息的裸`CancelledError`不得越过store API。Pre-commit cancellation的值为`None`，post-commit cancellation携带committed observation。异常传播后enclosing `asyncio.Task`仍呈cancelled semantics，调用方可按普通task cancellation处理，同时读取commit outcome。Rollback、cursor close和connection close自身也使用confirmed-completion helper；cleanup中的第二次cancellation不能中断ownership收回。

`close()` invocation在第一个await前同步登记一个close-owner ticket；取得lifecycle lock后把store从`OPEN`改为`CLOSING`。Lifecycle、reader和writer lock acquisition本身也必须使用cancellation-safe confirmed ownership：若caller在任一`LOCK_WAIT`取消，owner记录pending cancellation并shield等待当前operation释放lock，绝不进入无锁cleanup。

全store唯一lock order为lifecycle → reader → writer，release order相反。普通reader／writer operation先confirmed-acquire lifecycle、检查state为`OPEN`，再按该order取得所需connection lock并登记active operation，之后才释放lifecycle；operation完成不再反向获取lifecycle。Close owner在持有lifecycle并标记`CLOSING`后，依次confirmed-acquire reader、writer locks，等待既有operation按原transaction语义完成，再checkpoint并confirmed-close所有cursors／connections。任何路径都不得在未拥有对应reader／writer lock时调用connection close／rollback。

并发`close()`幂等：第一个ticket是唯一physical close owner；后续caller看见`CLOSING`时等待同一个close-completion future，看见`CLOSED`时直接返回。等待者发生cancellation同样先shield到shared close完成，再传播phase为`CLOSE_LOCK_WAIT`或`CLOSE_WAIT`的`StoreOperationCancelled`。Owner自身在lifecycle／reader／writer lock wait取消时，也必须取得全部locks、完成resource close、以reverse order释放locks，最后传播typed cancellation；store终态仍为`CLOSED`且没有worker／lock leak。

#### 8.1.1 Fixed confirmed-action IDs

本Spec拥有confirmed-action分母，production registry不能生成test expected。Action shape定义：`ONE`的完整ID就是base；`EC`展开成`<base>.execute`与`<base>.cursor-close`；`EFC`展开成`<base>.execute`、`<base>.fetch`与`<base>.cursor-close`。Loop可重复同一semantic ID，但每个raw await恰好映射一个expanded ID。

| Shape | Fixed semantic bases |
|---|---|
| `ONE` | `lock.start.lifecycle`、`lock.snapshot.lifecycle`、`lock.snapshot.reader`、`lock.apply.lifecycle`、`lock.apply.writer`、`lock.event.lifecycle`、`lock.event.writer`、`lock.anchor-use.lifecycle`、`lock.anchor-use.writer`、`lock.prune.lifecycle`、`lock.prune.writer`、`lock.close.lifecycle`、`lock.close.reader`、`lock.close.writer`、`lock.close.shared-completion` |
| `ONE` | `connection.inspect.open`、`connection.inspect.close`、`connection.writer.open`、`connection.writer.close`、`connection.reader.open`、`connection.reader.close` |
| `ONE` | `instrument.writer.thread-probe-install`、`instrument.writer.trace-install`、`instrument.reader.thread-probe-install`、`instrument.reader.trace-install` |
| `EC` | `tx.inspect.begin`、`tx.migration.begin`、`tx.refresh.begin`、`tx.apply.begin`、`tx.event.begin`、`tx.anchor-use.begin`、`tx.prune.begin` |
| `ONE` | `tx.inspect.commit`、`tx.inspect.rollback`、`tx.migration.commit`、`tx.migration.rollback`、`tx.refresh.commit`、`tx.refresh.rollback`、`tx.apply.commit`、`tx.apply.rollback`、`tx.event.commit`、`tx.event.rollback`、`tx.anchor-use.commit`、`tx.anchor-use.rollback`、`tx.prune.commit`、`tx.prune.rollback` |
| `ONE` | `cpu.state-decode`、`cpu.transition`、`retry.busy-sleep` |
| `EC` | `pragma.writer.foreign-keys-set`、`pragma.writer.busy-timeout-set`、`pragma.writer.synchronous-set`、`pragma.reader.foreign-keys-set`、`pragma.reader.busy-timeout-set`、`pragma.reader.synchronous-set`、`pragma.reader.query-only-set` |
| `EFC` | `pragma.writer.foreign-keys-read`、`pragma.reader.foreign-keys-read`、`pragma.writer.journal-mode-wal`、`pragma.reader.data-version`、`pragma.inspect.quick-check`、`pragma.writer.checkpoint`、`instrument.worker-probe` |
| `EFC` | `schema.objects-read`、`schema.meta-read`、`schema.table-list-read`、`schema.table-xinfo-read`、`schema.table-ddl-read`、`schema.index-list-read`、`schema.index-xinfo-read`、`schema.foreign-keys-read` |
| `EC` | `schema.create-statement`、`schema.meta-insert` |
| `EFC` | `state.schema-meta-read`、`state.identities-read`、`state.epochs-read`、`state.samples-read`、`state.prediction-records-read`、`state.evaluations-read`、`state.exact-anchors-read`、`state.prefix-anchors-read`、`state.prefix-checkpoints-read`、`state.events-read` |
| `EFC` | `apply.duplicate-read`、`identity.lookup`、`identity.insert-returning`、`global-revision.read`、`identity.revision-read`、`sample.exists` |
| `EC` | `epoch.owner-insert`、`epoch.sample-insert`、`epoch.prediction-insert`、`identity.active-epoch-update`、`sample.insert`、`prediction-record.insert`、`evaluation.insert`、`exact-anchor.insert`、`prefix-anchor.insert`、`identity.revision-update`、`global-revision.update`、`sample.delete`、`evaluation.delete`、`epoch.empty-delete`、`identity.empty-delete`、`event.insert`、`event.ids-delete`、`event.bucket-prune`、`event.global-prune`、`anchor-use.sample-update`、`prefix-checkpoint.upsert`、`prefix-checkpoint.delete` |

Task 3B V1表恰有111个semantic bases，按shape展开为211个action IDs；test literal必须同时断言这两个基数和完整set equality，不能只比较count。

Test-side `EXPECTED_ACTION_IDS`必须是人工转录上述expanded IDs的fixed literal，不能import production registry、调用production expansion helper或从runtime trace生成。Production declared ledger、`EXPECTED_ACTION_IDS`和覆盖全部scenarios的runtime confirmed-action ID trace三者的ID set必须完全相等。Runtime另记录每个raw `aiosqlite` call→confirmed action ID映射：每个raw call恰有一个registered ID，所有`EC`／`EFC` expanded IDs及raw `ONE` IDs都必须被观察；lock／CPU／sleep等non-raw `ONE` IDs由confirmed-action trace覆盖。新增／删除semantic call site时必须先修本表与test literal，再修production ledger。

### 8.2 V1 schema manifest与relational authenticity

Store-private `ValidatedPersistentState`表示一次startup／refresh read transaction中已经完成schema和全体row validation的持久状态；它可包含多个active／inactive identities／epochs、bounded events及relational validation records，但不得越过store boundary。Public `LearningSnapshot`保持Task 2 cardinality：恰好对应一个requested active `LearningIdentity`及其一个active epoch，只含该epoch的samples、exact／prefix anchors、prefix checkpoints、prediction records和evaluations；不含events、inactive epochs或其它identity。`snapshot_for_prediction(identity)`只返回这种single-identity active snapshot；没有active epoch时返回该identity的typed empty snapshot，而不是全库state。

`schema_meta`同时保存schema version与canonical V1 manifest digest。V1 manifest逐项列出table及column name／type／nullability／default／PK position、`STRICT`属性、primary／unique／ordinary indexes及其column order、全部`CHECK`表达式、foreign keys及`ON DELETE`／`ON UPDATE`动作。Digest只由这份versioned canonical manifest产生，不从待验database反向生成expected值。

每个TableManifest另保存canonical normalized table DDL digest，覆盖column-level `COLLATE`、inline／table `CHECK`、generated constraints和末尾`STRICT`。Expected DDL digest是由reviewed V1 migration DDL离线固定的literal，不从当前database、`sqlite_schema.sql`或production normalizer生成。Startup用versioned SQL-token normalization处理actual `sqlite_schema.sql`后计算actual digest，同时继续执行PRAGMA column／index／FK manifest比较；两侧缺一不可。把text column从BINARY／default collation改成`COLLATE NOCASE`，即使indexes和`schema_meta.manifest_digest`保持expected值，也必须得到`MANIFEST_MISMATCH`且original bytes不变。

Startup同时比较`schema_meta`中的version／digest和实际`sqlite_schema`／PRAGMA introspection。只有meta相同但缺table、column、`STRICT`、unique index、ordinary read／prune index、`CHECK`、FK或cascade的“fake V1”必须被拒绝。Unsupported version、manifest mismatch或结构缺失产生typed `LearningStoreStartupError`，带closed reason code，且不得先写原文件。

`epoch_state`以`(identity_key, epoch)`为unique relational owner。`samples`除global unique sample key和composite owner key外，新增positive `committed_order`、`fixed_context_contribution_json`、`input_item_contributions_json`，并继续以nullable nonnegative INTEGER专列whole `capability_visual_tokens`；`NULL`与0语义不同。Fixed context V1 shape严格为`[visible_tokens,framing_tokens,prior_residual_tokens]`；item shape严格为五位置`[visible,item_framing,nested_framing,visual_or_null,prior]`。`prefix_fingerprints_json`改为按位置排列的64-hex digest array，item count由index＋1恢复；788-item motivating shape必须低于现有65,536-byte单字段上限并可round-trip，不能放大上限掩盖verbose object encoding。

新增`prefix_checkpoints`表，以`(identity_id,epoch,profile_key_json COLLATE BINARY)`为PK／UNIQUE，`profile_key_hash`只作ordinary index；保存mode、bounded evidence JSON、positive `state_revision`和`updated_order`，FK仅指epoch owner，不指sample。Evidence与ProfileKey JSON使用fixed canonical codec。Sample prune不得cascade active checkpoint；inactive checkpoint按§8.5清理。

`prediction_records`保存selected method＋variant、closed method-champions mapping及含variant的candidate JSON；`evaluations`以sample owner＋method＋variant为primary key。`learning_events`的typed payload新增required checkpoint outcome discriminated object；standalone capacity transition字段禁止。Prediction／evaluation／anchor／sample-linked event继续使用composite sample FK；recognized events FK epoch owner，rejection-only event保持exclusive unresolved-bucket CHECK。Manifest、normalized DDL digests、column／CHECK／PK／index／FK literals必须完整覆盖上述新shape。

Retained derived graph还必须满足exact cardinality与事实一致性：

- 每个retained sample恰有一个`PredictionRecord`和一个mandatory exact anchor；零个或多于一个都属于corruption。Committed order必须positive且在single-sample transaction模型下global unique；pending None不得进入persistent／public state。
- 每个sample的fixed context、input-item contributions、whole known／components／prior／visual和prefix digest tuple必须满足§4 exact conservation、arity、framing与length alignment；compact codec任何wrong position／type／non-finite／aggregate mismatch均corrupt。
- 每个prefix checkpoint的canonical ProfileKey JSON、decoded object、hash、mode、evidence length／method keys／APE／committed-order sequence、state revision和updated order必须一致；active checkpoint不依赖sample row，inactive cleanup和capacity outcome必须符合§8.5。
- 每个sample commit必须在该transaction中为`PredictionRecord`的全部candidate keys计算完整`PredictionEvaluation`，并逐项验证selected key、method champions和eligibility，再按下述diagnostic retention决定哪些evaluation rows留存。只要sample、PredictionRecord和actual仍retained，任一candidate的signed／absolute／APE facts都必须可从candidate predicted value＋sample actual确定性重建，供variant selection、method champion、drift使用；这个reconstructable prequential fact不依赖evaluation table row。
- 每个retained evaluation row必须唯一匹配一个source record candidate key，其sample key、identity／epoch、method、variant、candidate ordinal和predicted／actual values逐字段相等；record没有candidate的extra row、非法method／variant pair或任何mismatch始终corrupt。对每个candidate key／`ProfileKey`／identity／epoch，按§8.5 canonical newest order选出的最近128个含该candidate的retained samples必须各有恰好一个evaluation row；更老matching samples允许evaluation row缺席。
- Prefix anchor存在当且仅当source full sample的input prefix chain非空。存在时恰有一个final-prefix anchor，其context fingerprint等于source features context、prefix fingerprint等于chain最后一项、item count等于final prefix coverage，owner identity／epoch／sample key和actual等于source sample；prefix chain为空时必须零prefix anchor。
- Sample-linked learning event的FK tuple必须等于observation sample key；event metadata中的actual、epoch、drift及required checkpoint outcome必须等于source sample、policy-entry phase、logical command与post-transition durable state。Main-outcome矩阵、NotAttempted／NotCommitted、capacity reject／rollover与nested transition逐字段验证；不得让event指A而payload描述B、保留standalone capacity transition或把rollback称为NoChange。
- 每个inactive epoch／identity metadata row必须被至少一个retained sample／derived row或retained recognized rejection-only event引用。Rejection-only event可以在其bounded retention期内成为metadata的唯一引用；unresolved-bucket event不创建伪identity／epoch。除此之外的unreferenced inactive epoch或identity metadata属于corruption。

Startup validation必须在一个consistent read transaction中decode全部retained active和inactive epochs、events及每一行，构造store-private `ValidatedPersistentState`。它用canonical DTO codec重算`ProfileKey` hash、event bucket、sample／identity／epoch links、anchor source links和bounded metadata shape，并逐项验证exact contributions／compact prefixes／committed order／presence-aware visual、prefix checkpoints／capacity bounds／required event outcome、mandatory record／exact-anchor cardinality、selected key、method champions／eligibility、全部retained evaluation的candidate-key match、newest-128-per-candidate-key mandatory evaluation window、prefix-anchor iff规则、sample-linked event事实一致性与metadata reference closure；older matching sample缺evaluation row是唯一允许的evaluation absence。任何inactive corruption、hash mismatch、wrong event bucket、missing／extra child、candidate／champion／eligibility mismatch、event mismatch、unreferenced metadata、dangling／cross-identity／cross-epoch link或不可decode row都产生typed startup error，原database bytes不被改写。Validation完成后才从该state为各requested identity投影public active `LearningSnapshot`。

### 8.3 Existing-store inspection与concurrent fresh migration

Path存在时，任何writer connection或mutating PRAGMA之前先用read-only inspector读取version、manifest digest和实际schema。Supported V1必须完整通过§8.2；unsupported、corrupt或partial nonempty schema立即返回typed startup error，且file hash／bytes保持不变。Missing path或经read-only inspector确认empty的path才进入fresh ownership flow。

Fresh／empty writer先通过§8.1 helper open并设置不改schema内容的connection PRAGMAs：`foreign_keys=ON`、`busy_timeout=0`、`synchronous=NORMAL`。取得`journal_mode=WAL`也可能busy，必须在async caller中nonblocking sleep后重跑完整ownership flow；不得依赖SQLite default blocking timeout或在worker thread／event loop中`sleep`。

取得WAL后，以confirmed `BEGIN IMMEDIATE`获取migration ownership，并在lock内重新读取`schema_meta`和`sqlite_schema`。仍为空才create V1 schema、写version＋manifest digest并按§8.4提交；若peer process已经完成，则完整validate manifest和rows后继续，不重复DDL；若观察到unsupported／partial state则rollback并fail-visible。两个fresh starters都必须收敛为一个creator和一个validator，而不是TOCTOU double-create。

Reader connection只在migration／validation成功并且writer transaction已确定commit后open。任何busy retry都从read-only inspection／writer ownership的正确入口重新执行完整flow，不能复用transaction外“empty”判断、stale manifest或partial connection state。

### 8.4 Atomic transition、revision与cancellation outcome

Writer sample transaction以confirmed `BEGIN IMMEDIATE`开始，先做duplicate application check，再在同一transaction读取并验证private persistent rows，为sample identity投影transaction-fresh single-active-epoch `LearningSnapshot`，只把这份public snapshot交给background CPU lane的pure transition。Inactive epochs、events和其它identity不得进入transition callback。Duplicate application check返回typed duplicate且不调用transition、不增加revision；database unique constraint是独立的最后防线，两者必须分别可判否。

一次成功sample事务的唯一顺序是：

1. Duplicate check、transaction-fresh private state、current active snapshot；duplicate不进入policy并产生NotAttempted duplicate outcome。
2. 记录policy callable entry；pure prediction／evaluation／learning返回pending sample、required checkpoint logical command和可选drift。Policy entry后的任何pre-commit failure属于NotCommitted。
3. 计算唯一`next_global_revision`和current identity `next_identity_revision`。Store把pending sample stamp为committed order，并把logical checkpoint replacement stamp为state revision／updated order；codec／row preparation只能在stamp后执行。
4. 验证checkpoint expected prior revision及drift precedence。Drift存在时command必须NoChange；触发drift的sample进入E+1，record prediction epoch仍为E，old-E checkpoint不搬迁。
5. 插入／更新sample、prediction record、evaluations、anchors及provisional checkpoint；先按§8.5删除inactive checkpoint rows。
6. 执行checkpoint capacity planner。未超cap保留结果；per-identity超cap或global超cap且current identity有pre-existing rows时current-identity rollover；global超cap且prior rows为0时撤销provisional checkpoint、sample继续commit并产生CapacityRejected。
7. 基于最终checkpoint／epoch／sample关系图计算全部victims和affected identities。Task 3B capacity只影响current identity；future drift同事务仍只计该identity一次。
8. Current identity revision和global database revision各递增一次，值必须等于步骤3 stamp。
9. 按确定性顺序执行sample cascade prune；active checkpoint不绑sample FK。Capacity rollover删除E checkpoint、把E inactive并创建empty E+1；current capacity sample仍在E，下一次prediction看E+1。
10. Store以final state形成required checkpoint outcome和post-transition learning event；sample被同事务prune不改写真实outcome。Standalone capacity transition禁止。
11. Confirmed COMMIT确定durable结果并刷新current identity cache到最终active epoch；rollback撤销sample、checkpoint、epoch、revisions和event。COMMIT cancellation按§8.1返回携带committed observation的typed outcome。

完全被prune的identity不再有identity row，但global database revision和foreign-connection `data_version`必须使reader失效该identity的旧cache。Rejection-only event transaction和explicit `record_anchor_use()`／`prune()`同样遵循“计算affected → revision → cascade／event → confirmed commit”的单一revision纪律。不得保留“prune后才决定或增加revision”的另一条顺序。

### 8.5 Exact pruning policy与anchor-use hook

每个anchor source sample持久化`last_used_order`。Evidence创建时以该次store insertion order初始化；这只是evidence creation order，绝不能称为“recent actual use”。Task 4 request-side pure selection返回ephemeral immutable `PredictionDecision(prediction, anchor_use_intent)`：selected prediction为exact时必须携`AnchorKind.EXACT` intent，为prefix时必须携`AnchorKind.PREFIX` intent，profile／cold-start时intent必须缺席；intent的identity／epoch必须与prediction一致，并包含所选anchor fingerprint和全部source sample keys。`PredictionDecision`不属于`PredictionRecord`、candidate JSON、evaluation或learning event；prequential内部计算anchor challenger也不冒充request-side actual use。Task 5／pipeline orchestrator在request critical path之外只把request decision的intent排入其owned queue，并调用Task 3 store的async `record_anchor_use(intent)`。Task 4不得调用store，store不创建queue或background task。

`record_anchor_use()`验证intent仍指向同identity／epoch／fingerprint。Source已经prune时返回typed `AnchorUseOutcome.PRUNED`且不写row／revision；仍存在时更新exact intent涉及的retained source samples或被选prefix source sample，并按§8.4 revision纪律返回`RECORDED`。Task 5 queue满、关闭或delivery失败时记录typed observation，保持last-confirmed persisted use不变；不得把未入queue或未commit的intent冒充recorded use。

Per-identity sample victim使用以下升序total order，较小者先prune：

1. Inactive epoch优先于active epoch。
2. 该sample所支持的retained anchors中，较小的maximum `last_used_order`优先；没有retained anchor时使用低于任何真实order的sentinel。
3. 较小的maximum retained prefix `item_count` coverage优先；没有prefix coverage时使用低于任何真实item count的sentinel。
4. 较小`observed_at_us`优先；该列持久化UTC Unix microseconds integer，不存timezone string。
5. Sample key按`process_boot_id` BINARY、`request_id` BINARY、`attempt_index` numeric依次升序tie-break；不得比较任意tuple JSON或locale collation。

Global sample cap先按identity total order选victim identity：没有active epoch／只含inactive evidence者优先；然后依次比较较小maximum retained-anchor `last_used_order`、较小maximum retained-prefix coverage、较小oldest retained `observed_at_us`、canonical LearningIdentity fields。Identity tie字段顺序固定为actual provider、exact resolved model、endpoint、wire format、tokenizer、descriptor fingerprint、estimator generation、profile schema revision；text字段用SQLite BINARY collation，integer revisions用numeric order。选定identity后使用上述sample order。No-anchor／no-prefix values使用同一低sentinel。所有排序字段来自transaction-fresh retained rows，不能按timezone string、locale或任意JSON tuple排序，也不能把最后sample write冒充anchor use。

Prefix checkpoint limits为4,096 active rows per identity／epoch、32,768 active rows global；eligible evidence最多16、demoted evidence最多8。Inactive rows不参与prediction，并按epoch ascending、updated order ascending、canonical ProfileKey JSON BINARY ascending在relevant transaction先删。Active checkpoint不能逐profile LRU或随sample cascade删除：删eligible window会静默延迟demotion，删demoted row会false-recover。

一次logical command最多净增一row，transaction起始state必须within caps。Capacity planner在provisional update前记录current identity／global active row counts。未超cap保留；per-identity超cap，或global超cap且current identity有pre-existing rows时，只rollover causal current identity。Current capacity sample／record留old E，删除E checkpoint rows，E inactive、E+1 empty active，next prediction从E+1开始；nested CapacityRolledOver是唯一transition authority。删除至少一条pre-existing row，故一次动作终止并恢复caps。

Global超cap且current identity prior rows为0时，rollover只会删除刚插入row而无容量收益，禁止。Store撤销该checkpoint row、不改变epoch或其它history，sample照常commit，并产生typed CapacityRejected second fact；global持续饱和时该identity可能无法建立首条checkpoint，这是显式learning degradation，不冒充成功。Future inactive cleanup释放容量后可重试。Drift transition优先：sample进入E+1、record prediction epoch E、logical command必须NoChange，清除E checkpoints，不产生capacity transition／rejection。

Capacity rolled-over cross-fields必须满足transition identity epoch＝previous E、new＝E＋1、observation sample epoch＝E、commit后active E＋1；CapacityRejected要求missing-row Replace、prior identity rows0、prior global rows恰等于global limit且epoch不变。Applied／Deleted stamp等于post revisions。Start-at-cap zero／positive prior rows、per-identity cap、drift＋wrong command、rollback／cache均有direct controls。

Limits保持：4,096 samples per identity、32,768 samples global、5 actuals per full fingerprint、128 persisted diagnostic evaluation rows per candidate key／`ProfileKey`／identity／epoch、4,096 learning events per identity、32,768 events global。Diagnostic rows为每个candidate key分别保留canonical newest 128 matching samples；一个prefix method的三个variants可各自保留至多128 rows，不能共享method-level 128-row budget。Newest order按`observed_at_us`降序，再按`process_boot_id` BINARY、`request_id` BINARY、`attempt_index` numeric降序打破同timestamp tie。Older matching sample的row可prune，但sample／record／actual保留，因此prequential error仍可按candidate key重建。Profile drift的recent 32＋紧邻reference 128共160 method-champion evidence必须从retained `PredictionRecord` candidate＋sample actual重建，绝不查询evaluation table作为完整分母。Rejection-only events计入event caps；sample prune级联records／anchors及其evaluation rows。

### 8.6 Durable reason codes与bounded metadata

Durable DTO和rows不得含free-form `detail`或`reason`。`LearningReasonCode`是closed enum，V1成员恰为`sample-committed`、`duplicate-sample`、`sample-ineligible`、`missing-usage`、`inconsistent-usage`、`queue-full`、`analysis-failed`、`operation-cancelled`、`store-unavailable`、`migration-failed`、`commit-failed`和`pruned`。`DriftReasonCode`是独立closed enum，V1只覆盖`profile-error-regression`、`exact-count-mismatch`与`identity-version-change`。`PrefixCheckpointNotAttemptedReason`只含`duplicate-sample`、`sample-rejected`、`failure-before-policy`；capacity rollover reason只含`prefix-checkpoint-capacity`。Checkpoint outcome variant、skipped reason和capacity transition metadata都是closed typed records，不复用main reason string。

每个reason variant使用自己的typed metadata record，而不是`dict[str, object]`。允许的durable primitives仅为bounded nonnegative／signed integers、bool、finite numeric metrics、closed enums、validated identity／sample-key components和fixed-size SHA-256 digests；每个variant固定field names、presence和range。任意exception text、raw prompt、system／message／tool text、opaque／media bytes、unknown raw type或调用方自由字符串都不能构造durable DTO，也不能由`record_event()`写入database。

Raw exception text只可进入§8.7的best-effort structured application warning，绝不进入SQLite。DTO construction或`record_event()`收到arbitrary text时必须在任何transaction／row insertion前返回typed validation error，event row count保持不变。

### 8.7 Reader snapshot、thread provenance与lifecycle

Reader refresh使用confirmed explicit `BEGIN`，在同一read transaction读取global revision、全部retained identities／epochs、samples、anchors、prefix checkpoints、prediction records、evaluations和bounded events，off-event-loop构造store-private `ValidatedPersistentState`并完成all-row authenticity validation后confirmed `COMMIT`。随后只为requested identity／active epoch投影public `LearningSnapshot`。任一table read、cursor close或decode阶段取消／失败时，按§8.1确认transaction state并rollback；继续服务上一validated private state和对应active snapshots。`PRAGMA data_version`只触发foreign commit refresh，不充当snapshot一致性证明；local writer用commit返回的global／identity revisions刷新或删除cache。

Foreground prediction只读`snapshot_for_prediction(identity)`返回的最后validated single-identity active `LearningSnapshot`，不等待writer retry或refresh。Store-private `ValidatedPersistentState`不得传给predictor。Store不创建sample／anchor-use queue、predictor或request-lifecycle background tasks；Task 5／pipeline orchestrator拥有queue并在critical path外调用async `record_anchor_use(intent)`。

Thread-provenance test必须通过可注入connector／factory创建`sqlite3.Connection` subclass，直接记录真实`sqlite3.connect`和override `close`的thread IDs；production store不得暴露raw connection。SQLite UDF只可证明query／apply执行thread，不能冒充open／close provenance。

Shutdown顺序是停止上层新调用后，confirmed完成在途transaction、checkpoint、cursor close和reader／writer connection close。`close()`幂等；close后新operation显式失败。Database不可打开、unsupported、corrupt、migration失败或commit持续失败时，原file不被替换；Task 5可降级到cold-start。

SQLite可写且event进入writer时，successful、duplicate、rejected和failed `TokenLearningObservation`是bounded durable rows。Database不可写或warning本身无法进入writer时，只发best-effort structured application warning；warning可含bounded exception text，但它**不叫durable observation**、不回写`RequestLine`，也不能撤销已交付client response。

## 9．Drift与learning epoch

Profile drift使用同public method的点时`MethodChampion`／`ProfileKey`／identity／epoch paired prequential errors，并从retained PredictionRecord champion candidate＋sample actual确定性重建，不依赖bounded evaluation rows。Recent window是最后至多32条；reference window是紧邻recent之前至多128条，两者必须互斥。只有同时满足以下全部条件才开启new epoch：reference至少32条、recent至少16条；recent median APE严格大于reference median APE的2倍；recent比reference高至少5个百分点；recent median signed relative error的绝对值严格大于5%。Actual为0的sample不进入这些windows。

Exact drift独立检测：同fingerprint的actual相对已有median连续3次偏离超过`max(32 tokens, 1%)`时完成new epoch transition。一次outlier、不连续mismatch或未超过严格阈值都不得触发。Active-epoch exact anchor在transition commit之前始终合格；generic champion、prefix demotion或profile evidence不得跳过它。它只因full-fingerprint miss，或已提交的epoch transition把旧anchor移出active epoch而停止参与。

开启new epoch后，旧epoch的profile统计、prefix eligibility checkpoint与anchors立即停止参与prediction；old checkpoint按§8.5清理，其它evidence保留到bounded prune。新epoch从deterministic cold-start和新anchors重新学习；profile达到普通的至少3个candidate样本与至少8个paired promotion样本条件后自动恢复。Epoch transition必须产生closed `DriftObservation`。触发drift的sample进入E+1，PredictionRecord仍声明prediction epoch E；checkpoint command和store outcome必须NoChange，old-E checkpoint不搬迁，不同时产生capacity transition／rejection。DB可写时event durable，DB不可写时只发§8.7 best-effort warning。

Estimator generation、cold-start prior revision、profile schema revision、tokenizer或token-relevant descriptor变化通过新identity隔离，不等待statistical drift。Drift阈值只决定history isolation，不是public accuracy SLO。

## 10．Observability与失败语义

Request completion和late learning拥有不同真值时点，必须使用两个不可互相冒充的载体。

- `RequestLine`只承载发布时同步已知的prediction／offer facts：method、`ProfileKey`、low-confidence reasons、history revision／epoch、operator scaling，以及`queued`、`queue-full`或attempt-level duplicate等`offer()` outcome。发布后immutable，不得由background worker回写。
- `TokenLearningObservation`是独立typed record，以sample identity关联request／attempt，记录`committed`、DB duplicate、rejected或failed、closed `LearningReasonCode`、bounded typed metadata、所有prequential errors、new revision／epoch、可选`DriftObservation`及required `PrefixCheckpointStoreOutcome`第二事实。它不得含free-form failure detail或standalone capacity transition。SQLite可写时，它按§8.6～§8.7成为bounded durable `learning_events` row；DB不可写时发出的application warning不是durable observation，不能使用durable字样。

`TokenLearningPolicy`只返回logical `LearningUpdate`，不返回或预填`TokenLearningObservation`、`PrefixCheckpointStoreOutcome`、post-transition revisions、capacity transition或durable event。Store在最终state和confirmed COMMIT后唯一构造这些facts；policy与store不得成为同一fact的两个owner。

Late commit不能把已完成request行改写成“学习成功”，late failure也不能撤销其response。Learning state与TUI display分层：本文定义typed facts，`.dev/docs/tui/spec.md`继续决定哪些同步事实被展示；本计划不新增TUI显示合同。

Local count每次都保留internal method和evidence strength，但public只用`estimated:true`区分local与remote。低置信数值不得被日志或错误文案称为账单值、容量上限oracle或upstream measurement。

## 11．被否路线

| 路线 | 结论 | 理由 |
|---|---|---|
| **Unavailable-as-default**：Responses含opaque reasoning／media／unknown且无upstream count endpoint时让local失败或返回unavailable | 否决 | 违反R1已选择proposal。合法payload必须得到best-effort正整数与`estimated:true`；低置信由内部facts表达并由R2要求的历史学习改善。 |
| **Ciphertext-as-text**：把`reasoning.encrypted_content`、signature、base64 media或整个unknown JSON交给ordinary text tokenizer | 否决 | Carrier bytes没有ordinary-text计费语义；已观测到reasoning-heavy重建体的主导高估，且media按wire长度会制造同类结构错误。 |
| **Global multiplier**：用一个跨结构scalar、旧0.5～3.0 clamp或`river`模型替代exact／prefix／profile | 否决 | 单一系数混合了方向相反的thinking漏计、ciphertext／media高估与不同profile，不能满足持续、可解释的混合学习。`river`首版还增加不必要依赖与难迁移状态；以后只能以已保存features／actual重新评估，不能预先取代规定方法。 |
| **Output reasoning_tokens as input label**：把`output_tokens_details.reasoning_tokens`或累计output reasoning当下一轮input贡献 | 否决 | Output usage没有协议保证等于未来replay input；边界、保留策略和item数量会变化。唯一监督label是同attempt raw total input usage。 |
| **Request-log adjacency pairing**：按时间相邻、request-level latest usage或同session顺序把payload与usage配对 | 否决 | Retry、reroute、hedge、并发与late terminal都会串线；pairing必须由attempt-local sent snapshot和usage建立并由exactly-once identity约束。 |
| **Saving raw prompts**：为exact／prefix或offline复查保存raw body、prompt、tool output、opaque carrier、media body或unknown原文 | 否决 | Fingerprint、bounded features、counts、provenance与errors足以支持运行时学习；raw content不属于learning state合同，且会让state无界并混淆语义与载体。 |
| **Treat reconstructed forensic evidence as exact request identity**：把8,662,058-byte candidate与921,248 usage当成已由原body hash证明的同一request | 否决 | 只有append-only边界和exact byte-length equality，缺少成功request body／hash。该证据足以工程处置但不是cryptographic identity，更不能成为普通cassette或live replay。 |
| **Default special-token guard**：继续调用会把configured special spellings列入`disallowed_special`的默认`encode()` | 否决 | 合法客户端文本会因字面`<|endoftext|>`等spelling抛错并产生500，而不是按ordinary text计数。 |
| **`allowed_special`**：把`<|endoftext|>`或其它spelling加入允许集合 | 否决 | 它虽不抛错，却把普通字符解释成control token并改变token sequence；只断言非500抓不到这个错误。 |
| **Endpoint-level catch／fallback**：在HTTP handler捕获encoding error后返回默认值或转下一腿 | 否决 | 错误发生在共享estimator语义；endpoint catch会隐藏根因、可能伪造成功，且不能修复worker和其它调用入口。 |
| **Responses-only patch**：只改Responses estimator | 否决 | Anthropic `system`／messages／tool schema使用同一错误API，production ASGI已在direct Anthropic local与translated Responses local两条路径复现500。 |
| **One-spelling denylist**：只从disallowed集合移除`<|endoftext|>` | 否决 | 合同覆盖configured tokenizer的全部special spellings，包括当前`<|endofprompt|>`与未来成员；逐名补丁必然遗漏同根输入。 |
| **One-message-position patch**：只修最初事故中的一个message field | 否决 | Ordinary-text不变量同时覆盖Anthropic system／messages／tool schema和Responses instructions／messages／tool schema／function-call arguments／output。 |
| **Retain old failure expectation**：继续让`test_real_worker_keeps_encoding_failure_and_stage_metrics`以special spelling触发failure | 否决 | 该测试把产品缺陷固定成期望行为；failure metrics应改用synthetic estimator exception，special spelling应成为成功回归。 |
| **Provider reroute for counting**：让另一个provider把frozen model重新映射成自己可数的model | 否决 | Token counts是model-specific；这会回答另一个目标的问题，并破坏同provider／model／payload identity。 |
| **Raw prompt admission代替count contract**：把Responses standalone-field guard当whole-request local prediction或用其结果训练 | 否决 | 该guard只审单个已知文本字段，不累加payload，也不使用完整history语义；它与公开count用途不同。 |
| **Collapse candidates by method／ordinal identity**：每method只保存champion、把variants改成public methods，或用list ordinal代替candidate key | 否决 | 前者丢失challenger paired facts，第二种改变R3选定的四method体系，ordinal会随candidate insertion变义；closed method＋variant key和点时method champion分别拥有两种事实。 |
| **Visual-in-known／aggregate-pixel inference**：把descriptor visual输出塞进`known_tokens`，或从总pixels反推patch tokens | 否决 | A18要求29与6分槽；同面积不同aspect ratio及多图边界产生不同ceil结果，aggregate不可逆，并会污染additive residual与neighbor semantics。 |
| **Persist anchor-use intent with candidate**：把request-side`AnchorUseIntent`塞入`TokenPrediction`／`PredictionRecord` JSON | 否决 | Request actual use与prequential challenger时序不同；codec若丢字段造成restart不等，若保留则把ephemeral command伪装成candidate事实。`PredictionDecision`只在request side绑定两者。 |
| **Unnamed tuple decision carrier**：返回`tuple[TokenPrediction, AnchorUseIntent | None]` | 否决 | 它能传递两个值，但没有named constructor拥有method／kind／identity／epoch跨字段验证；后续增加offer facts只会继续堆position slots。Immutable `PredictionDecision`以具名字段和validation拥有这一边界。 |
| **Median／derived aggregate prefix base**：对同prefix多个anchors取median、选最接近median source或新建无单一source的aggregate anchor | 否决 | 当前没有paired evidence表明其优于latest；它会重开window、lineage、partial-prune和multi-source use semantics。现合同按coverage／newest／canonical sample key选一个actual，并让数值与intent provenance一一对应。 |
| **Whole-request suffix subtraction／predictor re-analysis**：用两个whole visual totals相减，或把raw appended items／capability再传给predictor分析 | 否决 | None→None不可逆；重新分析复制feature classifier／formula owner。Prefix只切estimator已产出的per-item contributions。 |
| **Known-only suffix calibration／zero-current candidate deletion**：learned residual只对known delta，或current baseline为0时删multiplicative candidate | 否决 | 与包含visual／prior的deterministic baseline口径不同；历史ratio支持下0×factor有定义且必须进入prequential candidate set。 |
| **Timestamp／all-base historical pairing**：用`observed_at_us`证明availability，或为一个longer保留全部prefix bases | 否决 | Timestamp不是commit happens-before；all-base会按base枚举数重复计权。Global committed order＋single canonical base拥有语义。 |
| **Replay prunable records／sample-FK checkpoint**：每次从retained records重放eligibility，或让checkpoint随sample cascade | 否决 | Prune会把demoted state静默恢复eligible。Checkpoint独立于sample并保存最小16／8状态。 |
| **Silent active checkpoint eviction／zero-benefit rollover**：LRU删active row，或global cap满且current prior rows为0仍rollover | 否决 | 前者延迟demotion或false-recover；后者只删刚插入row却反复清空identity history。零收益分支必须typed capacity reject。 |
| **Checkpoint outcome conflation／dual capacity transition**：用NoChange统包未尝试／rollback，或同时保存standalone与nested capacity transition | 否决 | Policy no-op、未进入、进入后未commit是不同事实；capacity transition唯一在CapacityRolledOver outcome中。 |

## 12．证据层级与验收

### 12.1 每层证据可以与不可以证明什么

| 层级 | 可以证明 | 不可以冒充 |
|---|---|---|
| Pure unit／synthetic feature与algorithm样本 | 分类、fingerprint、distance、candidate、prequential、drift和finalization在给定数据上的确定性语义 | 不能证明真实provider如何计费，也不能证明production入口已经接线。 |
| Fake／mock upstream through production ASGI／pipeline entry | 本代理的counter order、frozen target、attempt pairing、wire projection、lifecycle和错误分流 | 不能证明真实upstream会返回该shape、usage或failure provenance。 |
| Recorded cassette | 某一历史版本真实upstream在已录payload上的chunk／protocol行为，可复现collector与translation | 不能冒充本轮live upstream、别的model／provider，或重录后仍不漂移。 |
| Reconstructed forensic evidence | 当前代码与点时日志／capture的关系，以及重大结构失真的强烈工程依据 | 不能冒充原成功body的cryptographic identity、失败request精确count、普通CI fixture或live replay。 |
| Live upstream | 指定时间、provider、exact model和实际sent payload上的当前usage／count observation | 不能外推为所有payload、未来model版本或跨provider通用公式；Anthropic count本身也可能与实际message usage有小量差异。 |
| Official protocol documentation | Anthropic count、thinking、vision和context-editing的公开合同与model-specific边界 | 不能证明本代理已实现合同，也不能替代OpenAI Responses／Copilot的实际usage。 |

未执行的层级必须标为未执行，不能折算为通过。每个关键判据在同一测试入口包含正确样本与单一目标缺陷注入；注入后必须核对失败来自目标不变量，而不是fixture解析、旁路断言或未接线。本节不创建CI gate、投票、graduation protocol或proof control plane。

### 12.2 可判否行为判据

| ID | 行为判据与正确样本 | 单一目标缺陷注入 | 证据边界 |
|---|---|---|---|
| A1 | 真实ASGI count入口分别提交含opaque reasoning、media与unknown item的合法Responses目标，完整response严格等于`{"input_tokens": N, "estimated": true}`且`N >= 1`，没有其它字段。 | 把任一类别改成unavailable／error，或增加method／confidence私有字段；同一完整对象断言必须红。 | Mock target证明public contract与fallback wiring，不证明数值接近真实provider。 |
| A2 | Direct Anthropic mock upstream分别返回只有`input_tokens`和带`context_management.original_input_tokens`的标准对象；production入口完整保留存在字段，缺席时不合成。 | 重新压成裸int后重建，或在缺席时合成`context_management`；完整对象与缺席断言必须红。 | Protocol fixture证明本方projection，不证明真实upstream每次都返回可选字段。 |
| A3 | 小型deterministic Responses与Anthropic payload只增大`encrypted_content`／base64 body时ordinary-text component不变而对应features变化；增加可见summary／message／tool text时known tokens变化。 | 临时恢复unknown／reasoning／media整段`dumps()`进入tokenizer；ordinary component断言必须因目标bytes增长而红。 | Mechanics test不证明provider对opaque／media的实际token贡献。 |
| A4 | Production count入口用独立provider spies覆盖`[ghc,local]` remote success、remote failure后local、`[local,ghc]`和两个具名provider；每腿读取同一frozen target且实际调用、trace名称和结果一致。 | 把local eager precompute放回chain前，或让provider B复用routed provider A／reroute model；调用次数、target identity或结果断言必须红。 | Stub证明本方编排，不证明真实provider可用性。 |
| A5 | 同top-level context的identical payload命中exact，append-only payload命中最长prefix；两个同context／item-count／prefix-digest anchors的actual为100／120且`observed_at_us`为1／2时，selected prefix base严格为newer 120、intent source严格为该120 sample、suffix只加一次。再以相同timestamp、只改变BINARY sample-key字段和numeric attempt 2／10逐维断言§6.2 ascending final tie；tools／instructions／unknown field／item顺序任一变化使相应anchor失配。 | 分别从full hash省略unknown字段、从prefix context省略tools、删除rolling previous digest、把matching prefix actual改取median 110，或反转／JSON-lexical比较sample key；对应identity、selected unscaled value、intent source或tie victim断言必须红。 | SHA-256／synthetic anchors证明identity和single-source total order，不证明forensic candidate与原成功body相同，也不证明latest一定比median更准。 |
| A6 | 最后subscriber与provider adapter分别改写payload，sample raw SHA、features和fingerprints必须等于mock transport的`response.request.content`，不等于预改写对象。 | 改成从`RequestContext.payload`或`Attempt.payload`重序列化；完整sent identity断言必须红。 | Mock transport证明捕获点，不证明外部provider如何tokenize。 |
| A7 | 两次retry／reroute使用不同payload与usage，只有各自eligible attempt进入对应identity；double absorb只产生一次offer和一条sample，DB duplicate不再次transition。 | 分别移除attempt CAS与DB unique key；第一种使offer count红，第二种使sample／revision完整状态红。 | Fake usage证明attempt pairing与exactly-once，不冒充真实usage provenance。 |
| A8 | Empty snapshot的首个sample在learn前只产生`cold-start/deterministic` candidate、一个eligible cold-start represented-method champion和同一global selected key；absent exact／prefix／profile没有champion。一般record按candidate key保存全部当时存在的candidates／evaluations和每represented-method champion／eligibility；represented exact与cold champions恒为true，prefix／profile可按点时状态变化。第二个sample才可使用第一笔history。Actual 0只进入exact／additive evidence与每candidate absolute error，relative／APE／promotion／demotion／drift字段缺席。 | 分别把represented exact或cold champion设为false、要求absent method伪champion、删除represented-method champion、增加absent-method extra champion、让champion指wrong-method／missing key、把learn移到candidate／champion／evaluate之前、按method覆盖variant或让0生成ratio／APE；完整record／validation／缺席断言必须红。 | 证明champion cardinality／unconditional eligibility、prequential顺序、candidate preservation与zero语义，不证明预测已经准确。 |
| A9 | 同identity和exact `ProfileKey`内，known tokens相同但opaque bytes、image dimensions、PDF pages或unknown quantities不同的样本按equal-weight L1选出不同neighbors；MAD pool使用当前sample前的全部eligible同key history，MAD 0→1，presence mismatch精确贡献4，tie按distance、newer observation、`process_boot_id`／`request_id` UTF-8 BINARY ascending和numeric `attempt_index` ascending解决。 | 分别把定量值塞进`ProfileKey`、忽略一个feature、改用L2／非等权、把presence penalty改成别值、从nearest-31先算MAD或反转tie；对应pool／distance／order完整断言必须红。 | Synthetic labels证明algorithm discrimination，不冒充真实计费函数。 |
| A10 | Profile recent 32与紧邻reference 128互斥，满足四项阈值才new epoch；exact连续3次超过`max(32 tokens, 1%)`才触发。Provider／model／tokenizer／generation变化不复用history，new epoch按普通条件恢复。 | 让窗口重叠、禁用一项阈值、把一次outlier当drift，或去掉identity一维；epoch／method／history isolation断言必须红。 | Synthetic drift证明transition合同，不是公开accuracy SLO或现实漂移频率。 |
| A11 | 两个独立SQLite connections用barrier制造同revision竞争，最终两sample与derived windows都存在，第二个evaluation看见第一笔committed revision；duplicate不增revision。 | 把锁内read→transition→insert拆成多个transaction或busy retry复用stale update；stale-window／row-set断言必须红。 | 本地交错证明SQLite transaction语义，不代表所有文件系统性能。 |
| A12 | Reader在读完revision／epoch后放行writer commit，再继续读其它表；snapshot只能完整属于旧revision或新revision。 | 移除显式read transaction；mixed epoch／anchor／window完整对象断言必须红。 | 本地SQLite snapshot test不证明跨主机共享文件系统。 |
| A13 | 以event控制background analyzer或第二connection持有write lock，event-loop heartbeat和foreground prediction仍推进，且foreground使用独立limiter和最后validated snapshot。 | 把CPU transition、raw SQLite busy loop移回event loop，或让foreground／background共享单容量limiter；heartbeat／foreground进度断言必须红。 | 确定性交错证明调度边界，不代表production负载分布。 |
| A14 | 冻结background worker直到RequestLine发布，再恢复；RequestLine字节不变，独立`TokenLearningObservation`按sample id持久化commit／duplicate／rejected／failed、errors和revision／epoch。 | 尝试回写frozen RequestLine或丢弃late event；完整对象／event query断言必须红。 | 证明两种真值时点与durability，不证明外部console已展示late event。 |
| A15 | Exact median为100.5、profile fractional candidate、负additive residual与multiplier为1及非1的样本都只经一次“Decimal乘法→ROUND_CEILING→minimum-one”，得到精确public integer。 | 在exact／profile／driver提前floor、nearest或ceil，先round再乘，或finalization后再次scale；完整值断言必须红。 | 数值测试证明quantization合同，不证明candidate准确。 |
| A16 | 官方／recorded Anthropic样本区分current、keep-all和last-turn-only thinking；同尺寸不同压缩image不因base64长度改变ordinary component；context editing count针对effective payload并保留可选original字段。 | 用assistant-role统一跳过thinking、把media source文本化，或把pre-edit count投影成effective；对应model差异、component或完整response断言必须红。 | Official／recorded evidence裁协议边界；fake只能证明本方实现，不能冒充live model行为。 |
| A17 | Queue用event控制达到32 items或64 MiB任一上限时返回`queue-full`而foreground response已完成；DB可写时该rejection成为bounded durable event，DB不可写时只产生明确标为best-effort的structured warning；shutdown停止接收后drain、commit／checkpoint、close。 | 取消drain、只限制items不限制bytes、把DB-unwritable warning称为durable、吞掉failure或用background failure撤销response；DB row、warning classification、foreground result或shutdown order断言必须红。 | Deterministic lifecycle test不代表production吞吐、磁盘故障频率或warning consumer可靠性。 |
| A18 | 用与production estimator不同源的stub tokenizer声明instructions=2、scalar-content message的role／text=7；payload含message、无summary的opaque reasoning、56×84 image、unknown四个Responses items。`framing_v1`为instructions 4＋四items各4，所以`known_tokens=2+7+4+16=29`；immutable capability snapshot的per-item visual formula给`capability_visual_tokens=6`；`cold-start-prior-v1` residual为0；multiplier 1得到unscaled／public 35，并带opaque／unknown对应zero-prior reasons。该完整`EstimateFeatures`经SQLite round-trip后仍严格保留29与6；另以同aggregate 4,704 pixels的56×84和42×112分别得到6与8，证明不是从aggregate pixels回推。 | 分别固定new identity为1、移除opaque／media／unknown item framing、把visual塞进known、丢弃nullable visual column，或改从aggregate pixels推导；exact object／29＋6／round-trip／6-vs-8断言必须在目标项变红。 | Stub tokenizer、capability snapshot和literal arithmetic证明cold-start分槽、per-item formula与persistence；不证明真实descriptor公式或provider计费准确。 |
| A19 | Production Anthropic error入口分别注入`CountTokensRequestError("invalid count request")`和无cause `CountTokensUnavailable(["ghc:0:TimeoutError"])`，完整status／body分别严格等于400＋`{"type":"error","error":{"type":"invalid_request_error","message":"invalid count request","code":"invalid_request"}}`与500＋`{"type":"error","error":{"type":"api_error","message":"no token counter succeeded: ghc:0:TimeoutError","code":"proxy_internal_error"}}`；cause与named ProviderError表逐行参数化。 | 分别把`CountTokensUnavailable`统一压成503、停止cause recursion、把任一named ProviderError落到base row或去掉nested envelope；对应完整status／body断言必须红。 | Local exception fixtures证明本方classification和carrier；mock upstream body不证明真实provider会返回该错误。Direct Anthropic raw passthrough另按error-envelope authority验收。 |
| A20 | 一个PredictionRecord同时保存prefix deterministic／additive／multiplicative、profile additive／multiplicative和cold-start七种合法candidate keys中当时存在者，每key各有evaluation；每represented method恰有一个点时champion／eligibility，absent method没有champion，global selected key按method order取得。Prefix无suffix history时champion为deterministic；learned variant少于3样本时缺席，最近至多31条全variant共同records且至少8个paired errors后仅strictly-better variant替代；16条triply-paired **method champions**中prefix同时比profile和cold-start高`>5`个百分点才demote，平手／缺样本不demote；demoted prefix以false eligibility继续留candidate并在8条subsequent paired samples达到`<=`best alternative时恢复。 | 分别按method覆盖同method candidates、只保存global selected、用ordinal作identity、一次差样本即永久demote、`>=5`即demote、非共同batch选variant、tie选learned、demoted后不再评估或7条即恢复；对应candidate keys／method champions／eligibility／selected key／window断言必须在目标分支变红。 | Synthetic errors证明candidate persistence、点时champion和状态机strictness，不证明现实prefix优于其它method。 |
| A21 | 通过production ASGI inference入口让mock transport实际发送payload并返回raw total usage；断言sent-body SHA、provider／model／attempt、pre-learn cold-start prediction和error进入一个committed sample。随后相同payload的count选择`history-exact`并返回该actual median，保持top-level context的append-only count选择`history-prefix`并返回anchor actual＋deterministic suffix。 | 两次独立mutation：丢弃inference-side `offer()`；保留offer但禁用sample→anchor transition／snapshot refresh。前者必须缺sample，后者必须使later exact／prefix method断言红。 | Mock usage证明production wiring、state transition和后续selection，不冒充真实provider billing。 |
| A22 | A21的mock response同时设置raw total input=120、normalized fresh input=20和output reasoning=777；committed actual、pre-learn error、later exact prediction都必须以120为label。 | 两次独立mutation：以normalized fresh 20替代raw total；以output reasoning 777替代raw total。两次都必须使sample provenance、actual、error和later prediction完整断言红。 | 人工区分的usage字段证明label selection，不证明120是任何真实payload的真实计费值。 |
| A23 | 超过sample／event上限后，在一个transaction结果中断言samples为4,096 per identity／32,768 global、actuals为5 per fingerprint、persisted diagnostic evaluations为每candidate key／`ProfileKey`／identity／epoch最近128 matching samples、events为4,096 per identity／32,768 global；同method多个variants各有独立128 budget，rejection-only events计数，pruned sample的anchors／evaluations级联消失，空identity metadata消失。 | 分别把evaluation cap错误共享到method、禁用anchor cascade、从event cap排除rejection-only、遗漏global cap或保留empty identity metadata；row-set与reference-integrity断言必须红。 | Local SQLite test证明bounded relational state，不证明production traffic distribution或filesystem performance。 |
| A24 | Unit matrix枚举configured tokenizer报告的全部special-token spellings，并至少显式包含`<|endoftext|>`。对Anthropic system／messages／tool schema与Responses instructions／messages／tool schema／function-call arguments／function-call output逐surface插入literal spelling；不同源ordinary oracle与被测estimator的token sequence或exact delta必须相等，且known-vs-opaque classification不变。 | 两次独立mutation分别恢复default special-token guard和启用`allowed_special`；前者必须因合法输入抛错而红，后者必须因sequence／delta不同而红，即使它返回正数。 | Independent ordinary oracle证明configured tokenizer的literal encoding mechanics，不证明Anthropic、OpenAI或Copilot的billing accuracy。 |
| A25 | Production ASGI用literal`<|endoftext|>`覆盖direct Anthropic local-only与Anthropic→Responses local两条路径；两者都返回HTTP 200和完整对象`{"input_tokens": N, "estimated": true}`，其中`type(N) is int`且`N >= 1`、没有额外字段，local worker各调用一次，remote provider transport调用0次。 | 分别恢复Anthropic侧default `encode()`和Responses侧default `encode()`；对应路径必须返回500并使完整success／call-count断言变红。不得用endpoint catch把500改成另一种fallback来通过。 | Mock ASGI证明production wiring、两条local surface和non-500 behavior，不证明返回数字等于provider billing。 |
| A26 | Tests手写111-base／211-ID `EXPECTED_ACTION_IDS` literal，逐项转录§8.1.1 expanded IDs，不import／调用production registry。Production ledger、test literal与全scenario confirmed-action trace三组ID set完全相等；独立raw-aiosqlite-call→action mapping要求每个raw call恰有一个ID并覆盖全部raw expected IDs。Cancellation matrix只从test literal参数化。 | 两类独立mutation：新增production ID而不改test literal，ledger set comparison必须红；把一个真实`aiosqlite`call改为绕过confirmed helper且不登记ID，runtime trace必须出现raw-call extra／confirmed-action missing并红。每个既有ID另有single shield mutation。 | Spec table和test literal提供独立分母；production registry不能生成expected，runtime scenario coverage仍不证明未执行的外部traffic。 |
| A27 | Independent schema oracle显式列举V1每个table的全部column、column `COLLATE`、inline／table CHECK、STRICT、PK／unique／ordinary index、FK／cascade，包括samples committed order／fixed-context／item-contribution／nullable visual columns、compact prefix JSON、prefix-checkpoint table的canonical ProfileKey JSON PK／hash index／mode／evidence／revision、required checkpoint outcome event JSON，以及prediction selected variant／champions、candidate／evaluation method＋variant CHECK／PK；以固定canonical table-DDL digests和PRAGMA结果对账，expected不能由DB或production manifest generator生成。Fake V1和inactive corruption必须typed失败且file bytes不变。 | 每个新增／既有column、CHECK、collation、DDL digest和PRAGMA guard各有独立mutation；删除任一expected或validator branch必须让对应fake schema错误通过并使oracle红。 | Independent fixed manifest裁schema authenticity，不证明future migration或外部已发布V1兼容。 |
| A28 | 两个store从同一missing／empty path并发start；test barrier明确记录两个starter都已完成complete read-only empty inspection，之后才同时释放去竞争WAL／`BEGIN IMMEDIATE` ownership。最终恰有一个creator、另一个lock内重读并validate，两者获得complete V1，reader migration后open。 | 移除test barrier、lock内schema重读、reader sequencing或完整busy retry，各自独立mutation；必须由对应double-create／ordering／partial-read断言红，不能以一次偶然串行run代替interleaving。 | Deterministic barrier证明local fresh-migration TOCTOU handling，不代表network filesystem。 |
| A29 | 用independent SQL分别尝试让prediction／evaluation／anchor／event的sample identity或epoch与source sample不一致，并尝试partial sample tuple；全部被composite FK／CHECK拒绝。合法sample-linked与rejection-only event各成功一次，cascade后无dangling rows。 | 逐个移除一种composite constraint或event exclusive-bucket CHECK；对应cross-link INSERT必须意外成功并使row／integrity断言红。 | SQLite relational oracle证明links，不证明DTO producer永不传错。 |
| A30 | 枚举所有`LearningReasonCode`／`DriftReasonCode`合法variant和typed primitive metadata round-trip；尝试用arbitrary prompt／exception text构造durable DTO或调用`record_event()`，必须在transaction前typed拒绝且DB row／revision不变。 | 恢复free-form `detail`／`reason`，或允许generic string metadata；arbitrary marker必须进入row并使absence／row-count断言红。 | 证明durable schema不能表达free text；best-effort application warning可在DB外保留bounded exception text。 |
| A31 | Pruning fixtures逐维制造active／inactive epoch、confirmed anchor-use order、prefix item-count coverage、`observed_at_us`和same-timestamp key tie；调用`record_anchor_use(intent)`后只目标source order变化。Sample tie按`process_boot_id` BINARY、`request_id` BINARY、numeric `attempt_index`；identity tie按§8.5固定LearningIdentity field order、text BINARY、integer numeric。Global cap逐维验证no-active／inactive identity、max use、coverage、oldest microseconds和canonical identity tie。 | 每个排序维度分别忽略／反向，把timestamp改成timezone string，把sample／identity key改成JSON／locale order，或把sample insertion冒充future use；对应exact victim key断言必须红。 | Synthetic capacity pressure证明deterministic victim order，不证明真实traffic的价值分布。 |
| A32-P | 从schema literal和raw fixture rows独立构造完整store-private `ValidatedPersistentState` expected，逐对象比较metadata、presence-aware visual slot、records／candidate keys、selected key、represented-method champions／eligibility、bounded candidate-key evaluation rows、anchors、events和links。Cold-only record只有eligible cold champion且合法；represented exact／cold champion为false、represented method missing champion、absent method extra champion或champion指wrong／missing key均corrupt。Evaluation fixtures另区分每candidate key newest-128 missing＝corrupt、第129及更老missing＝合法，任何extra／method／variant／ordinal／predicted／actual mismatch始终corrupt。 | 每个graph／window validator各有单变量mutation；把represented exact／cold champion设false、要求absent champion、删除represented champion、增加extra champion、交换wrong key、反转eligibility、删除visual presence或evaluation variant，对应corruption必须错误通过并红，cold-only与older-allowed controls仍须通过。Expected不得调用production decoder。 | Independent private oracle证明persistent graph与diagnostic retention，不允许predictor消费private type。 |
| A32-S | 对一个有active和inactive epochs并含events的validated store，独立从active rows构造public `LearningSnapshot` expected；`snapshot_for_prediction(identity)`必须只返回该identity的一个active epoch及samples／anchors／prefix checkpoints／prediction records／evaluations，不含events、inactive epochs或其它identity。无active epoch返回typed empty single-identity snapshot。 | 把events／inactive rows／其它identity投影进snapshot、返回`ValidatedPersistentState`，或扩张`LearningSnapshot` cardinality；exact object／type-boundary断言必须红。 | Active snapshot oracle保护Task 2 public semantics；不替代A32-P的all-store validation。 |
| A33 | Exactly-once测试分别证明application duplicate check在调用transition前返回typed duplicate，以及database unique constraint在两个connections竞态时拒绝第二insert。Identity isolation对actual provider、resolved model、endpoint、wire format、tokenizer、descriptor fingerprint、estimator generation和profile schema revision逐维单独改变，只改变一维就miss。 | 两轮独立mutation：仅删除duplicate application check，transition-call断言红但unique constraint仍守住row；仅删除unique constraint，并发row-count断言红。每个identity dimension再分别从key移除，对应isolation sample必须错误命中并红。 | Local controls区分两个exactly-once layers和每个identity dimension；不证明upstream label authenticity。 |
| A34 | Test-only connector／factory用`sqlite3.Connection` subclass直接记录真实connect constructor和override `close` thread IDs，断言二者及query／apply均不在event-loop thread；production store API和objects不暴露raw connection。 | 恢复default factory而伪用UDF结果填open／close，或从production wrapper暴露raw connection；provenance／surface断言必须红。 | Connector probe证明thread provenance；UDF结果只作为query／apply evidence，不冒充open／close。 |
| A35 | Test-only `BEFORE DELETE` trigger或独立transaction trace在每次cascade DELETE发生时读取identity／global revisions，断言二者已经递增；DELETE完成后插入的learning event携带同一post-transition identity revision。Fixture包含identity被完全删除的情况，trigger仍观察global DB revision先推进。 | 单变量把identity／global revision update移到cascade DELETE之后；最终rows可能相同，但trigger／trace必须在DELETE时看到old revision并判红。 | Test-only trigger／trace证明transaction内部顺序，不证明SQLite跨主机调度。 |
| A36 | Task 4 request-side pure predictor返回ephemeral `PredictionDecision(prediction, anchor_use_intent)`：exact／prefix分别带kind／identity／epoch／fingerprint／source keys一致的intent，profile／cold-start无intent；decision不进入`PredictionRecord`、candidate／event JSON或SQLite。Task 5只对request decision在critical path外排队并调用`record_anchor_use(intent)`，prequential challenger不算actual use。Recorded返回`RECORDED`；source已prune返回`PRUNED` no-op；queue-full／closed时记录observation且`last_used_order`保持last-confirmed值。 | 分别把intent塞进durable `TokenPrediction` codec、让prequential challenger排队、让Task 4直接await store、让store创建queue／task、在source missing时重建row，或在queue failure时预写／声称persisted use；decision invariant、DDL／JSON absence、purity、owner、row、revision和observation断言必须红。 | Fake orchestrator证明carrier、owner chain和failure semantics，不证明production traffic timing。 |
| A37 | Writer transaction和reader refresh各用barrier持有真实owner lock，使`close()`分别阻塞在lifecycle／reader／writer `LOCK_WAIT`。Cancel close task后，断言它记录cancel并等待active operation；释放barrier后active operation按自身pre／post-COMMIT语义完成，close按lifecycle→reader→writer取得locks、checkpoint／close resources、store变`CLOSED`，最后传播`StoreOperationCancelled`且task cancelled。两个并发close只执行一次physical close，另一caller等待同一completion。 | 分别在每个lock wait取消后调用无锁close、反转lock order、绕过CLOSING mark或让并发close重复physical close；operation outcome、lock trace、close count、terminal state或leak断言必须红。 | Deterministic barriers证明close ownership／deadlock-free order，不代表production close timing。 |
| A38 | Fake V1把一个text column改为`COLLATE NOCASE`，保留相同indexes和expected `schema_meta.manifest_digest`；independent fixed normalized table-DDL digest与complete CHECK／collation list必须检测`MANIFEST_MISMATCH`，并断言before／after file bytes相同。 | 从TableManifest移除DDL digest／collation，或由actual DB生成expected digest；NOCASE fixture必须错误通过并使fixed-oracle断言红。 | Fixed DDL oracle证明V1 table semantics，不证明future DDL parser。 |
| A39 | Independent raw-row fixtures验证每sample exactly one record＋exact anchor、prefix iff、event facts和metadata references。一个record同时含同method不同variants、selected key及各represented-method champion／eligibility；sample commit输入含每candidate key完整computed evaluation。Persisted rows只要求每candidate key canonical newest128 matching samples mandatory，older rows可缺；每row唯一匹配candidate key且无extra。另保留至少160个records＋actual、每candidate key只保留128 diagnostics，从点时method champion重建recent32＋preceding128 drift errors必须完整等于literal expected。 | 分别删除commit-time all-candidate-key evaluation、selected／champion／eligibility validation、per-key newest-window mandatory、retained-row match／no-extra或record＋actual reconstruction validator；对应single fixture必须红，older-row absence不得误红。 | Graph oracle区分complete reconstructable candidate facts与bounded diagnostics，不证明upstream sample真实性。 |
| A40 | Independent feature oracle逐shape断言fixed context＋items exact conservation，四种visual suffix transitions均按appended item slice得到literal值；compact 788-item prefix digest与contribution JSON各低于65,536 bytes并SQLite／worker pickle round-trip。 | 分别重复／删除nested framing、把item token算入context、恢复verbose prefix objects、用whole visual差分或交换tuple位置；exact totals、suffix value、byte bound或round-trip必须红。 | Synthetic features证明本方decomposition，不证明production visual formula。 |
| A41 | Two-process／same-timestamp samples由store stamp唯一positive committed order；historical base只在order更小时available，每longer按single canonical base选择。Revision-bound pair index先按order排序，reverse snapshot仍得到相同pairs。 | 用observed timestamp、允许future／equal order、保留全部bases或删除sort；availability／pair count／selected base必须红。 | Local SQLite order证明commit序列，不代表upstream observation时间。 |
| A42 | Per-ProfileKey checkpoint在sample prune／restart后仍保持eligible latest16或demoted latest8；trigger第16条不进recovery，8 bad后8 good按latest8恢复，Profile A不污染B。Replace／delete expected revision、NoChange、rollback与sample transaction原子。 | 绑sample FK、重放retained records、累计全部recovery、删除ProfileKey filter、漏CAS或在policy前后混outcome；mode／window／DB bytes必须红。 | Synthetic APE证明state machine与persistence，不证明现实method质量。 |
| A43 | Checkpoint caps为4,096 per identity／epoch、32,768 global。Global-at-cap＋current prior0 typed reject checkpoint但sample／epoch／history保持；prior>0或per-id cap current-identity rollover释放pre-existing rows，current sample留E、next snapshot E+1。Drift＋NoChange使sample进E+1且无capacity fact。 | 零收益仍rollover、选择另一identity、重标current sample、drift＋Replace、保留old checkpoint或错revision／cache；完整state／event断言必须红。 | Capacity fixture证明有界内部语义，不是accuracy SLO。 |
| A44 | Main outcome×required checkpoint outcome逐矩阵round-trip：committed五results、duplicate／rejected NotAttempted、failed-before-policy NotAttempted、policy-entry后rollback NotCommitted、post-COMMIT cancellation committed actual result；CapacityRolledOver nested transition唯一。另有fixture使current sample在同一transaction成为sample-cap victim，断言sample row最终缺席、checkpoint replacement／delete仍按真实command outcome保留、event携实际Applied／Deleted／其它committed result与post-transition revision。 | 用NoChange统包、漏required outcome、错skipped reason、failed误Applied、额外standalone transition、drift＋rollover、因sample被prune而跳过checkpoint或把outcome改成NoChange；DTO／raw-row startup必须红且bytes不变。 | Failure injection证明carrier和transaction truth，不代表production故障频率。 |
| A45 | Candidate tuple为七pair固定subsequence，champions按method order；sample_count exact1～5、prefix deterministic1、learned variant actual evidence count、cold0。Exact selected仍保留strictly shorterprefix challenger。Newest31用records＋actual而非diagnostics；63 older/newest反转和evaluations-empty controls判源。另有full suffix baseline fixture：historical known delta为合法的正值、visual／prior delta也为正且actual匹配完整baseline，断言residual、ratio、candidate value和sample count；fixture必须让known-only baseline与full baseline产生可观察差异，不要求违反item framing的零known delta。另有current baseline为0且至少三条positive ratio history的fixture，断言multiplicative candidate保留且suffix value为0。 | 乱序tuple、sample count换义、exact时跳prefix、移除31 slice或改读evaluation rows、把full baseline改成known-only、或恢复current-zero gate删除multiplicative candidate；record／champion／baseline完整对象必须红。 | Pure synthetic history证明candidate facts，不证明上游计费。 |

## 13．Spec transcription map

下表列出的断言在本Spec本轮修订时均为**planned transcription**，不能写成现有通过证据。实现时，修改任何被转录常量、枚举或分类必须在同一语义change同步更新本Spec与所有已存在的转录。

| Path | 建立时状态 | Transcribed authority与常量 |
|---|---|---|
| `tests/unit/tokenization/test_features.py` | existing transcription；Task 3B待扩展 | §4 exact fixed-context／input-item contributions、four visual suffix transitions、whole aggregate reconstruction、compact tuple alignment和788-item shape；candidate／decision／snapshot invariants继续保持。Store-private state不从types export。 |
| `tests/unit/tokenization/test_anthropic_features.py` | planned transcription；file尚未创建 | §4 Anthropic system／messages／tool schema的ordinary special-spelling semantics；message／block／tool framing值；current／keep-all／last-turn-only thinking；redacted thinking；tool identity fields；image patch formula和PDF／context-editing original／effective区分。 |
| `tests/unit/tokenization/test_responses_estimator.py` | planned transcription；现有file待修改 | §4.3 Responses instructions／messages／tool schema／function-call arguments／function-call output对全部configured special spellings使用ordinary-token sequence／exact delta；不接受`allowed_special`语义。 |
| `tests/unit/tokenization/test_local_token_worker.py` | existing transcription；Task 3B待扩展 | Ordinary special spelling与synthetic failure保持；Task 3B新增fixed／item contributions及compact 788-item DTO通过真实process pickle boundary。 |
| `tests/unit/tokenization/test_token_counting.py` | planned transcription；现有file待修改 | §4.3 local counter面对全部configured special spellings保持success；§3.1 lazy order确保remote-first success不因local tokenizer预计算失败。 |
| `tests/unit/tokenization/test_learning_store.py` | existing Task 3A transcription；Task 3B待扩展 | Test-owned literal更新为111 bases／211 IDs；V1 committed order、compact contribution／prefix codecs、prefix-checkpoint table／canonical JSON identity、logical command／store outcome matrix、capacity reject／rollover、drift precedence、bounds／restart／prune／rollback及A40～A44。既有candidate、diagnostic、close、migration、revision和thread contracts保持。 |
| `tests/unit/tokenization/test_prediction.py` | planned Tasks 4A／4B-P／4B／4C transcription；file尚未创建 | Task 4A cold／exact／deterministic per-item prefix／all-available record／order／sample count／evaluation／finalization；4B-P committed availability／single base／full baseline／zero multiplicative／newest31／diagnostic absence；4B profile＋checkpoint16／8／ProfileKey isolation；4C drift。Request decision与prequential intent边界保持。 |
| `tests/unit/tokenization/test_learning_service.py` | planned transcription；file尚未创建 | §7 eligibility／prequential；Task 5只从request-side `PredictionDecision`在critical path外排`anchor_use_intent`并调用store，prequential challenger不排use；queue failure记录observation且不更新last-confirmed use；32-item／64-MiB body queue、durable／best-effort split、independent limiters、failure／shutdown及late observation。 |
| `tests/unit/pipeline/test_error_classify.py` | planned transcription；现有file待扩展 | §3.3 `CountTokensRequestError`、`CountTokensUnavailable` cause／no-cause、named ProviderError、upstream status/body、Anthropic type／code和nested carrier。 |
| `tests/unit/pipeline/test_prompt_admission_driver.py`及`tests/unit/pipeline/`相关attempt tests | planned transcription；现有file待扩展 | §3 frozen target与lazy provider legs；§7 actual sent-body authority、retry／reroute pairing、attempt CAS和exactly-once offer。 |
| `tests/int/test_pipeline_app.py` | planned transcription；现有file待扩展 | §3完整public success／error wire、provider order／failure与Responses `no-counter`；§7 production inference→committed sample→later exact／prefix count闭环及raw-total label的20／120／777 controls；§12 A25 direct Anthropic local与Anthropic→Responses local的`<|endoftext|>` HTTP 200、完整object和provider-call counts；§10 RequestLine与late observation不互相改写。 |
| `tests/unit/observability/test_request_completion.py` | planned transcription；现有file待扩展 | §10同步prediction／offer facts、缺席语义、immutable RequestLine、durable event与best-effort warning分槽。 |
| `tests/unit/tokenization/test_evaluate.py` | planned transcription；file尚未创建 | §7 progressive replay严格evaluate-before-learn，以及按method／identity／`ProfileKey`聚合的error语义。 |
| `tests/systemd/test_systemd_units.py` | planned transcription；现有file待扩展 | §8.7 lifecycle shutdown先confirmed transaction／checkpoint／close，再由Task 5结束其它background tasks。 |

## 14．External sequencing gate

任何production code修改前，Task 1的独立Spec reviewer必须核验权威边界、合同完整性和可判否验收，并处置到0 blocker／0 major。该review由上级会话派发；本文作者作为Task 1 leaf implementer不自行兼任reviewer。

Task 1～5和Task 8可以在上述Spec review闭合后按 [plan.md](plan.md) 先行。Tasks 6、7、9、10、11会修改shared pipeline seam，必须等待direct buffered Chat Tasks 4～7已在main稳定`ResponseHandoff`、selected-candidate callback与attempt／request finalizer seam。进入Task 6前必须重新读取`.dev/docs/direct-buffered-chat-completions/tracking.md`和最终已集成源码，并按实际symbol更新Task 6接线说明，完成一次限定plan review。

若外部gate未闭合，暂停shared pipeline wiring，保留已完成的tokenization-local slices，不抢占direct buffered Chat owner，也不把等待解释为缩减token-counting范围。

## 15．修订记录

| 日期 | 条款 | 变化 | 触发与来源强度 |
|---|---|---|---|
| 2026-09-07 | 全文 | 建立living token-counting authority：按Task brief录入四项governing decisions；定义public count、same-target counter transport、结构化features、exact／prefix／profile／cold-start、same-attempt raw-total learning、prequential evaluation、identity／epoch、SQLite snapshot／bounds、failure／observability、acceptance evidence和transcription map。 | 2026-09-06的用户输入与选择经Task brief转录；`260906-buffered-chat-local-tokenizer-analysis.md`、transcript evidence及erratum、local-tokenizer code audit的点时技术证据；批准plan中的implementation-derived decisions。Decision provenance在本表后续修订中按一手transcript校正。 |
| 2026-09-07 | §1、§3～§10、§12～§13 | 补齐`cold-start-prior-v1` equation与exact-value oracle；拆分categorical `ProfileKey`和quantitative `FeatureVector`并固定L1／MAD／presence／tie；限定active exact eligibility；闭合prefix suffix、demotion和recovery；补齐anchor／error／event bounds与DB-unwritable warning；转录count-specific error wire；增加production inference→learn→later exact／prefix闭环及错误label controls；更新transcription map。 | Task 1独立review round 1的7项Important与1项Minor；SDD ledger逐项采纳并给出binding rulings。Behavioral outcomes与method priority保持不变。 |
| 2026-09-07 | §2、§4.2～§4.3、§11～§13 | 把R1／R3改为`user-selected-from-proposal`并记录paired tool-use／tool-result anchors与授权边界；把R2／R4替换为真实user-authored原句与queued-command anchors，详细扩写移入implementation-derived scope。新增ordinary-text special spelling合同，覆盖`<|endoftext|>`和全部configured spellings的完整Anthropic／Responses surfaces、两种encoding mutations、两条production ASGI paths、rejected routes与test transcriptions。 | 用户报告literal`<|endoftext|>`使两个local production paths返回500；cross-session Spec review findings DISP-01／DISP-02；`user-rulings-source-research-2026-09-07-sonnet.md`终态`found-partial`与`spec-review-disposition.md`的binding rulings。 |
| 2026-09-07 | §8～§10、§12～§13 | 补齐cancellation-safe `aiosqlite` queue-action ownership与post-COMMIT typed cancellation；V1 manifest authenticity、composite links、all-epoch decode和concurrent fresh migration；closed durable reason codes；exact anchor-use／prune ordering；single revision／prune／event order；cancellation、schema、migration、free-text、prune、snapshot、duplicate／identity和thread-provenance验收与转录。 | Task 3 source candidate `8b40d6a`的独立review发现1 Critical／6 Important／2 Minor；来源强度为reviewer一手code finding＋实施者在既有R4 delegated scope内闭合的implementation-derived rulings。同期纠正plan强制提交`uv.lock`这一reviewer-caught plan-mandated defect，人控`release-and-deployment.md`与`.gitignore`仍是dependency workspace contract authority。 |
| 2026-09-07 | §8、§12～§13 | 分离store-private all-epoch `ValidatedPersistentState`与single-active-identity public `LearningSnapshot`；把anchor-use owner chain改为Task 4 pure intent→Task 5 queue／orchestrator→Task 3 persistence hook；新增A35 revision-before-DELETE oracle；固定`StoreOperationCancelled`继承`asyncio.CancelledError`；canonicalize `observed_at_us`、sample-key和LearningIdentity ties；拆分A32 persistent／prediction oracles并同步transcriptions。 | Task 3 living contract scoped review round 1的2 Blocker／1 Major／2 Minor；来源强度为reviewer对合同自相矛盾／不可判否性的finding＋实施者在R4 delegated scope内闭合的implementation-derived rulings。此前T3-01／03／04／07／08／09 amendments保持不变。 |
| 2026-09-07 | §8、§12～§13 | 补齐close lifecycle／reader／writer lock-wait cancellation ownership、fixed lock order与concurrent close idempotence；认证table-column collation及fixed normalized DDL digest；定义mandatory record／exact-anchor、candidate-evaluation、prefix iff、event事实与metadata reference graph closure；把cancellation matrix改为complete named action ledger，并新增A37～A39 deterministic close／NOCASE／graph controls。 | Task 3 source fix candidate `3df0da3`的round-1 review发现0 Critical／4 Important；来源强度为reviewer一手source finding＋实施者在R4 delegated scope内闭合的implementation-derived rulings。此前T3-03／04／05／07／08／09和contract C-01～C-05保持不变。 |
| 2026-09-07 | §8～§9、§12～§13 | 分离sample／PredictionRecord／actual可重建的完整prequential facts与每method／ProfileKey／identity／epoch newest-128 bounded diagnostic evaluation rows，明确older row缺席合法且160 drift evidence从record＋actual重建；新增Spec-owned §8.1.1 fixed action-ID table、test literal／production ledger／runtime confirmed trace三方ID oracle，以及独立raw-call mapping／direct bypass mutation。 | Task 3 living contract round 3 review发现1 Blocker／1 Major；来源强度为reviewer对evaluation retention矛盾及同源action-ledger oracle的一手finding＋实施者在R4 delegated scope内闭合的implementation-derived rulings。此前所有Task 3 contracts保持不变。 |
| 2026-09-07 | §6.2 | 消除prefix数值与provenance矛盾：最长prefix全序选中单个anchor后使用该anchor的actual tokens；最近5个actual取median仍只属于history-exact。 | Task 4A派发前合同核对发现“相同长度按newer／sample id选单个anchor”与“prefix actual median”不可同时由Task 3既有`PrefixAnchor`及单source `AnchorUseIntent`表达；来源强度为实施者在R4 delegated scope内对既有derived contract作一致性修正，待独立Task 4A合同复核。 |
| 2026-09-07 | §4、§6～§9、§12～§13 | 为同method多variants新增closed candidate key、点时method champion／eligibility和global selected key；diagnostics改为每candidate key最近128 matching samples。新增presence-aware persisted `capability_visual_tokens`与immutable capability snapshot／per-item formula seam。Request-side anchor use改由ephemeral `PredictionDecision`承载，不进入durable candidates。补全single-prefix 100／120、canonical tie、candidate-key graph、visual 29＋6及对应mutations。 | Task 4A prefix contract review发现0 Blocker／2 Major／1 Minor，prediction DTO gap review发现2 Blocker／1 Major；全部采纳。来源强度为两名独立reviewer的一手contract／source findings＋实施者在R4 delegated scope内闭合的derived model。Prefix bounded median、ordinal identity、variant-as-method、aggregate-pixel inference、visual-in-known和intent-in-candidate均不采纳，理由见两份260907 Task 4A reports。 |
| 2026-09-07 | §6～§8、§11～§13 | 将method champion基数限定为record中有candidate的represented methods；cold-only record只含cold champion，absent methods不得伪造champion。分开candidate-key evaluation sequence与point-in-time method-champion sequence。补记unnamed tuple decision carrier否决理由，并同步cold-only／missing／extra／wrong champion controls。 | Task 3A prediction contract scoped re-review发现原3项中1项关闭、2项仍开，并新增1 Blocker／1 Major／1 Minor；本次修正采纳其represented-method反例与living-source要求。Prefix scoped re-review的原3项已关闭，所报plan summary Minor与同轮active-restatement修正合并处置。 |
| 2026-09-07 | §6、§12～§13 | 明确represented exact与cold-start champions均须无条件eligible，prefix／profile才允许点时false；新增exact-false与cold-false persistent corruption controls。 | Task 3A implementation brief review发现0 Blocker／2 Major中的eligibility Major；来源强度为reviewer给出的exact-false→wrong cold selection和cold-false persistent fact反例。本修正不改变§6.1既有method order，只把跨子句不变量落到DTO／V1 validator合同。 |
| 2026-09-07 | §1、§4～§13 | 新增exact-conservation fixed／per-item contributions、compact 788-item prefix codec、sample committed order、historical single-base availability、all-available candidates、canonical order／sample count、完整suffix baseline、current-zero multiplicative、newest31／diagnostic absence controls、prune-stable per-ProfileKey 16／8 checkpoint、required logical command／store outcome矩阵、capacity reject／current-identity rollover及Task 3B V1 111 bases／211 IDs。 | Task 4A brief review的2 Blocker／6 Major／1 Minor；Task 3B design及三轮amendment review终态`APPROVED DESIGN`、0 Blocker／Major／1 wording Minor。来源强度为fixed source反例、compact-size probes和实现者在R4 delegated scope内闭合的derived decisions。Task顺序改为3B→4A→4B-P→4B→4C，不删除或重排四个methods。 |
| 2026-09-07 | §6.2、§12～§13 | 修正A45 full-baseline control的不可实现fixture：`InputItemContribution`的item framing至少为4，因此合法strict append的known delta不能为0；改为使用正的known delta与正的visual／prior delta区分full baseline和known-only mutation，保留current-zero multiplicative control。 | Task 4B-P source preflight报告`260907-task4bp-implementation-gpt-m.md`发现brief C04与Task 3B carrier`InputItemContribution.__post_init__`冲突；这是agent-derived authority correction，不改变full-baseline或current-zero行为。 |
| 2026-09-07 | §7、§8、§12～§13 | 根据Task 3B authority review补齐logical policy与durable observation的owner边界、pending checkpoint evidence carrier与store stamping invariant；A44新增current-sample同事务prune control，A45新增full-baseline／current-zero candidate discrimination及对应mutations。 | `260907-task3b-authority-review-gpt-high.md`的T3B-AUTH-01、02、04与Minor05；由`260907-subagent-t3b-authority-analysis.md`复核为agent-derived correction，无新增用户行为分叉。 |

## 16．参考来源

- 主题入口与点时报告：[README.md](README.md)。
- 批准的完整实施顺序：[plan.md](plan.md)。
- 当前实施投影：[status.md](status.md)。
- 人控配置候选：[token-counting-config.md](../../human-controlled-docs-candidates/token-counting-config.md)。
- Anthropic官方Token counting：<https://platform.claude.com/docs/en/build-with-claude/token-counting>。
- Anthropic官方Thinking：<https://platform.claude.com/docs/en/build-with-claude/thinking>。
- Anthropic官方Vision：<https://platform.claude.com/docs/en/build-with-claude/vision>。
- Anthropic官方Context editing：<https://platform.claude.com/docs/en/build-with-claude/context-editing>。
