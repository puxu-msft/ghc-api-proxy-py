# Direct buffered Chat Completions：driver／capability／pre-success retry 实施计划前置源码地图

report_id: `dbc-plan-map-driver-capability`
attempt_id: `agent-a28c403335a3eb9e9-260906`
status: `in-review`
reviewed_at_rev: `f97d243f9431d836861ce5e9938605df56b37478`
reviewed_tree: `/home/xp/src/ghc-api-proxy-py` 主工作树当前文件快照
reviewed_at: `2026-09-06`

## 1. 范围、权威与结论强度

本报告只调查 capability／provider／pre-success retry 一侧，覆盖 `ModelDescriptor` 与三个provider descriptor构造点、`ProviderError` hierarchy与error mapping、`OpenAIChatCompletionsDriver`／`DirectDriver`的prepare／send／run／ledger／admission／events／deadlines／limiter、CodeBuddy与Xingchen payload／headers／aggregation、raw response与server handoff，以及相关unit／component／integration tests。Post-header direct streaming runner和Chat observation/TUI只记录对本侧接口的约束，不展开实现。

权威依次为人控合同、`.dev/docs/direct-passthrough/spec.md` §5.4／§9.3、`.dev/docs/error-envelope/spec.md` §5.1／§8、已确认的`design.md`与`decisions.md`。源码签名和调用顺序是revision `f97d243f9431d836861ce5e9938605df56b37478`的直接观察，强到足以据此编写计划；文件边界和切片是高置信建议；未实施、未运行测试，因此不证明未来候选可编译或符合Spec。

关键主树文件SHA-256：`model_provider/types.py`=`decc247b542090487eb92401913417837e9b1b4ac195010d735e3840033cd24f`；`direct_driver/base.py`=`110669bb19004588ec8bf1395ad0c0899123bdb6e5ec328036209f54c0707980`；`codebuddy_client/client.py`=`458fae45936909ce5bff29322415f0f2d3a43651fcaf16a240a81af86d2f8fe7`；`xingchen/client.py`=`d04c6fb2a5c4f160a73ce42282f330db9451de0b9ce2b023f2b675001036eb97`；`server/routes/inference.py`=`d86277be792837242230efdfcc341b5b665fe788f14c05ce6c7149bbcf1ada28`。

## 2. 当前调用顺序

`server.routes.inference._dispatch_after_body()`深拷贝inbound payload → `handle_bounded()`施加request-level client deadline → `handle()`调用`shape_request()`／`decide_route()`并把immutable `Route.descriptor`写入`RequestContext.model_descriptor` → 可选request translation → 把resolved model写入`context.payload` → `_drive()`按`DRIVERS[route.endpoint]`构造`OpenAIChatCompletionsDriver` → `DirectDriver.run()`循环 → `RequestContext.begin_attempt()` → 设置唯一`Attempt.deadline_at` → `_run_attempt()` → `_prepare_and_send()` → `attempt.prepare` subscribers → private deep copy成为`Attempt.payload`并覆盖resolved model → fresh或reused token admission → `RateLimiter.acquire()` → `_send()` → `ModelProvider.send()` → response headers返回 → limiter按HTTP status观察failure或立即观察success → `attempt.succeeded` → `request.succeeded` → `HandledRequest`回server。

Server handoff后，`context.stream=True`且Chat client leg无framer时，把live `response.aiter_bytes()`套idle／attempt／client deadline和byte accounting，再交`one_shot_delivery()`；`context.stream=False`时直接用`response.content`计量和parse JSON，经`response_payload()`后构造`JSONResponse`。当前只有一个`DriverOutcome.response`槽，既可能是live raw response、buffered raw response，也可能是CodeBuddy聚合出的synthetic response。

CodeBuddy造成一个关键例外：`DirectDriver._send()`的`response_header_timeout`包围整个`CodebuddyProvider.send()` coroutine，而CodeBuddy client在caller `stream=False`时会消费完整SSE、聚合、关闭raw response后才返回synthetic response。因此当前CodeBuddy聚合虽发生在success events前并位于attempt/client deadline内，却也错误地落在header timeout内，且raw SSE metadata／byte count已在provider seam内丢失。

目标调用顺序应为：final private payload → capability解释与attempt-local `ChatSendPlan` → admission → limiter acquire → provider按独立`upstream_stream`原样发送并只等headers → 需要adaptation时由pipeline collector在同一个whole-attempt deadline内消费body → raw exchange facts与client projection分槽 → body verdict成功后才limiter success与attempt／request success。Known transient body failure回同一个driver loop和ledger，并仅为下一attempt复用本attempt的frozen final payload／admission／capability，跳过mutable prepare与fresh admission。

## 3. 当前精确签名与数据结构

### 3.1 ModelDescriptor与route snapshot

`src/app/model_provider/types.py:138-163`：

```python
@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    id: str
    endpoints: frozenset[ModelEndpoint]
    unknown_endpoints: tuple[str, ...] = ()
    request_headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    reasoning_efforts: tuple[str, ...] | None = None
    adaptive_thinking: bool = False
    provider_name: str = ""
    catalog_generation: int = 0
    catalog_refreshed_at: str = ""
    prompt_token_limits: PromptTokenLimits | None = None

    def supports(self, endpoint: ModelEndpoint) -> bool: ...
```

当前无Chat response-mode capability。`Route`是`@dataclass(frozen=True, slots=True)`，字段为`provider_name`、`model_id`、`endpoint`、`target_format`、`inbound_format`、`translation_required`、`reason`、`resolution`、`descriptor: ModelDescriptor | None = None`、`provider_origin="default"`。`decide_route()`只取一次`provider.describe()`，`apply_route()`把同一descriptor写入context，`replay_prepared()`接收原Route；所以capability放进frozen descriptor即可天然成为route/replay snapshot，无需attempt间重查provider。

生产descriptor构造点只有三处：`GithubCopilotProvider.replace_catalog(raw)`、`CodebuddyProvider.replace_catalog(raw)`、`XingchenProvider.__init__(name, client, config)`。生产与tests共有18个repo-relative文件、34处`ModelDescriptor(...)`。建议新增`chat_endpoint_capabilities: ChatEndpointCapabilities | None = None`并用`__post_init__`强制“含Chat endpoint就必须显式给capability；不含Chat endpoint时为None”，从而不迫使非Chat fixture填写无关字段，又不让手写Chat descriptor绕过§9.3。

建议新类型形状：`ChatResponseMode(StrEnum)`成员`STREAMING="streaming"`、`NON_STREAMING="non_streaming"`；`@dataclass(frozen=True, slots=True) class ChatEndpointCapabilities`含非空`frozenset[ChatResponseMode] response_modes`、`Literal[True] | None stream_options_include_usage_default`、`Literal[True] | None tool_stream_default`、非空`str provenance`。这是建议签名，不是当前源码。

### 3.2 Provider protocol与clients

`src/app/model_provider/base.py:24-93`：

```python
class ModelProvider(Protocol):
    def describe(self, model_id: str) -> ModelDescriptor | None: ...
    async def send(
        self,
        endpoint: ModelEndpoint,
        payload: Mapping[str, Any],
        *,
        descriptor: ModelDescriptor,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response: ...
```

`GhcApiClient.send_chat_completions(self, payload, *, stream=False, extra_headers=None) -> httpx2.Response`只把`dict(payload)`交给OpenAI SDK raw post并透传mode／headers，没有Chat内容注入或聚合，可作为中性control。

`CodebuddyProvider.send(...)`签名符合protocol，但当前最后调用`self._client.send_chat_completions(payload, stream=stream)`，丢掉`extra_headers`。`CodebuddyClient.request_headers(*, extra_headers=None)`和`CodebuddyCredentials.request_headers(*, extra_headers=None)`已经具备case-insensitive owned-header保护，可直接复用。`CodebuddyClient.send_chat_completions(self, payload, *, stream=False) -> httpx2.Response`当前无条件写`body["stream"]=True`、缺席时补`stream_options.include_usage=true`、总以`http.send(..., stream=True)`发出；caller要求non-stream时调用`aggregate_stream(response) -> httpx2.Response`并finally关闭raw response。该aggregator忽略malformed／non-object／unknown event、混合choice、缺identity时造UUID／当前时间／unknown model、缺finish reason时补stop/tool_calls、clean EOF无`[DONE]`也成功。

`XingchenProvider.send(...)`已透传`extra_headers`。`XingchenClient._prepare_payload(payload, *, stream) -> dict`当前在stream mode下注入缺席的`stream_options.include_usage=true`和`tool_stream=true`，保留显式值；`send_chat_completions(self, payload, *, stream=False, extra_headers=None) -> httpx2.Response`先序列化`_prepare_payload`结果，再对同一bytes签名，合并headers后发送。迁移必须删除内容defaulting，但保留“pipeline最终bytes → sign → send”的顺序。

### 3.3 ProviderError hierarchy与mapping

`src/app/model_provider/types.py`当前直接定义`ProviderError`、`UnknownModel(provider, model_id, target="")`、`CapabilityMissing(provider, model_id)`、`EndpointNotSupported(provider, model_id, endpoint)`、`EndpointNotImplemented(provider, endpoint)`、`DescriptorProviderMismatch(expected, actual, model_id)`；另有`registry.py`的`ProviderNotConfigured(name)`和CodeBuddy auth state的`AuthStateMissing`／`AuthStateInvalid`／`AuthRefreshFailed`。

`error_classify.py`的`_PROVIDER_ROWS: tuple[tuple[type[ProviderError], ErrorCategory], ...]`只携带category；`describe(error, *, source_format="") -> ErrorInfo`命中后调用`_proxy_error(category, str(error))`。新增`ResponseModeNotSupported`只加入该表会得到CLIENT／400，却仍是通用`invalid_request` code，违反§5.1。应把row扩成携带code的typed record，或在generic loop前显式映射到`unsupported_response_mode`。`tests/unit/pipeline/test_error_classify.py::test_the_provider_error_subclasses_are_all_classified`断言`set(ProviderError.__subclasses__())`，新增类必须同步该集合和case表。

`server.http_errors.error_response(source, *, inbound_format, translated=True) -> Response`已经能把无upstream raw bytes的pre-network provider error交给现有方言writer；无需新建server错误出口。

### 3.4 Attempt与handoff

```python
@dataclass(slots=True)
class Attempt:
    index: int
    endpoint: ModelEndpoint | None = None
    payload: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    status_code: int | None = None
    error: str = ""
    deadline_at: float | None = None
    response_observer: ResponsesObserver | None = None
    token_admission: TokenAdmissionObservation | None = None
```

`RequestContext.begin_attempt(self, *, payload: dict[str, Any] | None = None) -> Attempt`会先清空request-level`response_observation`，再建立attempt并append。当前没有`ChatSendPlan`、Chat state、raw exchange snapshot或client projection。

```python
@dataclass(slots=True)
class DriverOutcome:
    context: RequestContext
    response: httpx2.Response | None = None
    error: BaseException | None = None
    attempts: int = 0
    events: list[str] = field(default_factory=lambda: list[str]())

@dataclass(slots=True)
class HandledRequest:
    context: RequestContext
    route: Route
    outcome: DriverOutcome
    synthesized: bool = False

    @property
    def response(self) -> httpx2.Response | None: ...
```

单一response槽使server无法区分raw和synthetic。建议保留`response`作为raw response owner并新增`ClientBodyProjection(body: bytes, status_code: int, headers: Mapping[str,str]) | None`，或在collector关闭raw前形成独立`RawExchangeSnapshot`再handoff。实现可二选一，但必须保证raw request bytes／status／headers／HTTP version／connection／SSE byte count从raw槽读，JSON body从projection读，且只有一个response close owner；不能再构造synthetic `httpx2.Response`冒充raw exchange。

### 3.5 DirectDriver

```python
class DirectDriver:
    def __init__(
        self,
        endpoint: ModelEndpoint,
        provider: ModelProvider,
        subscribers: FrozenSubscribers[RequestContext],
        *,
        budget: Budget,
        descriptor: ModelDescriptor | None = None,
        admission: AdmissionPolicy | None = None,
        prepared_payload: Mapping[str, Any] | None = None,
        reused_admission: TokenAdmissionObservation | None = None,
        attempt_deadline: int = 0,
        response_header_timeout: int = 0,
        rate_limiter: RateLimiter | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None: ...
```

内部精确签名为`_publish(event, context, outcome) -> None`、`_raise_if_deadline_elapsed(attempt) -> None`、`_prepare_and_send(context, outcome, attempt) -> httpx2.Response`、`_run_attempt(context, outcome, attempt) -> httpx2.Response`、`run(context) -> DriverOutcome`、`_handle_failure(error, context, outcome) -> bool`、`_send(context, payload) -> httpx2.Response`。`OpenAIChatCompletionsDriver.__init__`与base参数同形，只绑定Chat endpoint，没有override。

现有prepare顺序：若非prepared replay则发布`attempt.prepare`；深拷贝source到`Attempt.payload`并覆盖descriptor model；fresh admission或`reuse_token_admission()`；limiter acquire；`_send()`。现有success顺序：记录status；HTTP limit判断；立即`observe_success(headers)`；发布attempt／request success。新增Chat body hook必须位于headers取得后、limiter success与success events前，并处于`_run_attempt()`的whole-attempt timeout内；`response_header_timeout`只包provider取得headers。

### 3.6 Ledger、admission、deadline、limiter

`RetryReason`只有`GITHUB_TOKEN_EXPIRED`、`NETWORK`、`SERVER_ERROR`。`RetryLedger`精确方法为`limit_for(reason) -> int`、`spent(reason) -> int`、`consider(reason) -> RetryVerdict`、`take(reason) -> RetryVerdict`。`LedgerBudget.take_for(error)`先检查draining，再`reason_for(error)`，最后`ledger.take(reason)`。Known transient stream error必须进入closed retry disposition且让`reason_for()`直接读其显式`RetryReason`，不能伪造未收到的HTTP 500。

`TokenAdmissionObservation`是frozen record；`reuse_token_admission(source, *, attempt) -> TokenAdmissionObservation`生成`outcome=REUSED`并保留`reused_from_attempt`／`reused_outcome`。现有`prepared_payload`／`reused_admission`是构造driver时的外部replay seam，只供`replay_prepared()`；同一driver loop的普通retry仍每轮重新prepare和admit。Body-phase retry必须新增attempt-local“下一轮prepared snapshot”，不能把所有retry改成prepared。

Deadline三层：`handle_bounded(..., deadline_at)`是request client deadline；每attempt在`run()`只计算一次`Attempt.deadline_at`，`_run_attempt()`以`asyncio.timeout_at()`覆盖prepare/send；`_send()`另用`response_header_timeout`。Pipeline body collector必须继续位于`_run_attempt()`内，而不位于`_send()`的header guard内。

`RateLimiter`精确入口为`acquire() -> float`、`observe_success(headers=None) -> None`、`observe_failure(status_code, headers=None) -> bool`。当前只有HTTP 429／502进入limited mode，无event入口。建议新增`observe_event_rate_limit(*, retry_after: float | None = None) -> None`并抽共享limited-state transition；无可信Retry-After用现有configured retry interval。不要假调用`observe_failure(429,{})`。

## 4. 可复用与不可直接复用

可直接复用：`Route.descriptor` snapshot；`Attempt.payload` final authority和private deepcopy；`TokenAdmissionObservation`／`reuse_token_admission()`；`RetryLedger`／`LedgerBudget`的draining-before-spend；existing attempt/request events；`_finish_response_cleanup()`的primary／cleanup排序；`RateLimiter.acquire()`；`error_response()`与OpenAI writer；GitHub／CodeBuddy owned-header merge；Xingchen签名与transport normalization；`sse_source`已修正的LF／CRLF／bare CR、multi-line data和chunk split grammar。

不可直接当目标实现：`read_events()`丢raw frame bytes／offsets／comments，并把EOF partial tail尝试解析；`SseEvent.json()`把malformed、non-object和empty object折成同一个`{}`；`ChatCompletionsAssembler`面向translated Chat→Anthropic，混合choices、finish reason即可terminal、只认部分error shape并把坏tool arguments变成空dict；`one_shot_delivery()`异常时先交partial再抛出，无retry／keepalive／cap／`[DONE]`判据；`collect_with_limit()`append后才查cap且不按frame boundary；CodeBuddy `aggregate_stream()`应删除，不应修成pipeline之外的第二实现。

## 5. 建议新增／修改文件

必改生产文件：

- `src/app/model_provider/types.py`：capability enum／frozen record／validation、ModelDescriptor字段、`ResponseModeNotSupported`。
- `src/app/model_provider/__init__.py`：导出新types与exception。
- `src/app/model_provider/github_copilot.py`：Chat descriptor显式双mode、两个None defaults、provenance。
- `src/app/model_provider/codebuddy.py`：streaming-only compatibility capability并传`extra_headers`。
- `src/app/model_provider/xingchen/provider.py`：双mode、两个true defaults、provenance。
- `src/app/model_provider/codebuddy_client/client.py`：接收extra headers；删除force stream、defaulting、aggregation；按upstream mode返回raw response。
- `src/app/model_provider/xingchen/client.py`：删除`_prepare_payload`内容defaulting，保留对最终输入bytes签名。
- `src/app/pipeline/error_classify.py`：CLIENT／400／`unsupported_response_mode`。
- `src/app/pipeline/request.py`：attempt-local Chat plan／state与必要raw snapshot typed槽，不复制payload。
- `src/app/pipeline/direct_driver/base.py`：pre-success response hook、body-phase prepared retry、deferred success observation/events、cleanup ownership。
- `src/app/pipeline/direct_driver/openai_chat_completions.py`：capability解释、payload defaults、独立upstream mode、native non-stream与SSE adaptation。
- `src/app/pipeline/retry.py`：显式reason的typed upstream-event failure及`reason_for()`入口。
- `src/app/pipeline/rate_limiting.py`：event-rate-limit入口。
- `src/app/pipeline/driver.py`与`src/app/server/routes/inference.py`：raw／projection typed handoff与分别计量。

建议新建`src/app/pipeline/chat_completions/`：`events.py`放raw-aware `ChatEventReader`／`ChatEventFacts`；`state.py`放per-attempt state和标准multi-choice facts；`buffered.py`放single-attempt collector、raw buffer／ending／cleanup／result types；`adaptation.py`或`types.py`放`ChatSendPlan`和defaulting。Pure facts不能importserver、concrete provider或retry orchestration。目录名是建议；若落在`pipeline/delivery/formats/`也必须保持该依赖方向。

## 6. 每个语义切片的生产代码先行步骤与后补测试入口

### C1：closed capability与typed rejection

生产先行：定义capability algebra／validation／exception；三个descriptor构造点显式填值和provenance；error mapping给专用code；Chat driver只按context client mode与descriptor snapshot选mode，不按provider name。

测试后补：`tests/unit/model_provider/test_model_provider.py`钉frozen、nonempty、closed values、provenance及Chat endpoint成对校验；`test_codebuddy.py`／`xingchen/test_provider.py`／GitHub descriptor tests钉三种矩阵；`tests/unit/pipeline/test_error_classify.py`更新subclass闭集并明确断言400＋`unsupported_response_mode`。

### C2：provider content transparency与CodeBuddy header seam

生产先行：CodeBuddy删除force-stream／default injection／aggregation并传extra headers；Xingchen删除defaulting但保持serialize→sign→send；GitHub保持为neutral control。

测试后补：CodeBuddy component tests改为payload／mode／raw response／headers原样；旧aggregation cases迁入pipeline；Xingchen client tests改为“传入已defaulted bytes被精确签名”和“缺席字段不被provider补”；provider unit tests钉capability。C2在C3/C4接线前会让CodeBuddy production non-stream失去旧聚合，所以可以作为语义commit，却不能单独宣称feature完整。

### C3：shared Chat facts与single-attempt collector

生产先行：实现raw-frame-aware reader、event facts、per-choice state、standard multi-choice projection与collector；collector只读一个attempt、关闭source并返回raw／facts／ending，不读ledger、不发events、不replacement。Existing translated assembler最多复用reader解码，不改变其projection。

测试后补：新建`tests/unit/pipeline/chat_completions/test_events.py`、`test_state.py`、`test_buffered.py`，覆盖chunk split、三种line ending、offset、carrier优先、`[DONE]`、multi-choice、unassemblable、close exactly once、cleanup chaining和cancellation；保留`test_chat_completions_assembler.py`为translated control。

### C4：ChatSendPlan、defaults与pre-success adaptation

生产先行：final private payload形成后生成attempt-local plan，只在upstream streaming且字段缺席时改`Attempt.payload`；provider call读plan独立mode，不改`RequestContext.stream`。Native non-stream仍交raw response；streaming-only路径在success events前形成client projection。

测试后补：新建`tests/unit/pipeline/test_openai_chat_completions_driver.py`，覆盖四格capability matrix、explicit false／nonmapping stream_options、中性GitHub、CodeBuddy／Xingchen defaults、标准aggregation和unassemblable；`tests/int/test_xingchen_provider.py`继续从真实pipeline入口断言defaults与签名。

### C5：body-phase prepared retry与event limiter

生产先行：把body hook纳入whole-attempt timeout但移出header timeout；known transient body failure回`_handle_failure()`；仅此phase把`attempt.payload`／admission作为下一attempt prepared source；下一轮仍begin attempt、acquire、deadline、events，但跳过mutable prepare／fresh admission；event rate limit驱动limiter；body success后才observe success并发success events；raw response唯一close。

测试后补：Chat driver unit精确断言upstream calls=2、ledger只花1、两次payload逐字相同、prepare=1、admission为admitted→reused、acquire=2、attempt.failed一次、success只在第二轮完整body后；覆盖tear、EOF无`[DONE]`、server error、event rate limit、unknown／malformed／unassemblable不retry、draining不花budget、cleanup failure与cancellation。保留`test_prompt_admission_driver.py::test_retry_rechecks_payload_and_rejects_before_second_limiter_and_send`作为普通retry仍fresh的反向control。

### C6：raw exchange／client projection handoff与production entry

生产先行：扩`DriverOutcome`／`HandledRequest` typed handoff；collector close前快照raw metadata；server从raw槽记request bytes／protocol／connection／headers／SSE bytes，从projection构造JSON；native non-stream保持现状。Adaptation终局错误走error-envelope §8并保留nested／flat／malformed原值。

测试后补：component断言raw SSE长度与synthetic JSON长度各落正确槽；`tests/int/test_pipeline_app.py`覆盖GitHub neutral path、首轮body tear次轮成功、最终只见次轮、calls=2、错误status/body；`tests/int/test_xingchen_provider.py`覆盖职责迁移后行为不变；建议新增`tests/int/test_codebuddy_provider.py`走真实composition＋mock transport，覆盖non-stream adaptation、retry和extra headers，并明确mock不证明P6。

## 7. 现有测试资产映射

- `tests/unit/pipeline/test_direct_driver.py`已有generic events、retry、draining-before-spend、headers、cancellation和cleanup；保留generic control，不塞Chat字段表。
- `tests/unit/pipeline/test_prompt_admission_driver.py::test_prepared_replay_reuses_payload_and_observation_without_prepare_or_policy`钉prepared seam；`::test_retry_rechecks_payload_and_rejects_before_second_limiter_and_send`钉普通retry重新prepare／admit。
- `tests/unit/pipeline/test_retry_strategies.py`已钉per-reason与shared total；新event failure只需reason正反例。
- `tests/unit/pipeline/test_rate_limiting.py`已有HTTP 429／502、configured interval、Retry-After和recovery。
- `tests/unit/pipeline/test_timeout_enforcement.py`已有attempt deadline、header timeout和同一deadline instant。
- `tests/unit/pipeline/delivery/test_one_shot_delivery.py`当前钉“异常时partial先交付”；接新runner后必须按新transaction合同替换，不能保留旧断言又称transparent replay。
- CodeBuddy component tests当前明确钉provider内force-stream／aggregation，是应迁移的旧职责。
- Xingchen client tests当前钉provider注入和注入后签名，应拆为pipeline defaults与provider exact-byte signing。
- `tests/int/test_pipeline_app.py::test_chat_completions_endpoint_is_served`是GitHub native non-stream control；`::test_chat_completions_streams_are_delivered_whole_and_verbatim`只证明完整one-shot字节，不证明`[DONE]`或retry。
- `tests/int/test_xingchen_provider.py`已有真实composition、signed endpoint、native non-stream和stream defaults。
- 当前无CodeBuddy inference production-entry integration，只有wiring unit、provider unit和client component。
- `tests/int/test_pipeline_app.py::test_delivery_replay_reuses_the_normal_attempt_that_produced_the_stream`可借用prepared payload／admission断言形状，但它是Responses post-header路径，不能冒充Chat pre-success覆盖。

## 8. 排除方案及理由

1. 不用provider-wide布尔capability：route已有per-model descriptor，模型／账号未来可能不同。
2. 不按provider name分支：只是移动特例，新增provider仍改控制流。
3. 不保留provider force-stream／defaulting／aggregation：会继续隐藏raw exchange、误包header timeout、复制parser／retry owner。
4. 不全Chat强制streaming：会无依据改变GitHub／Xingchen native non-stream fidelity和失败时点。
5. 不把所有retry变成prepared：现有普通pre-header retry允许subscriber改变payload并重新admit；只有body-phase冻结。
6. 不复用`CapabilityMissing`：它精确表示endpoint集合为空，且不能给专用wire code。
7. 不用synthetic `httpx2.Response`冒充raw：当前CodeBuddy已经证明会覆盖raw计量／metadata。
8. 不用`observe_failure(429,{})`伪造event limit：未收到HTTP 429，应有独立event入口。
9. 不直接用`ChatCompletionsAssembler`做standard multi-choice：目标、choice模型、terminal和loss行为不同。
10. 不让collector花ledger、发events或重开：否则出现两个retry owner和double spend。
11. 不扩大response-header timeout到body：whole-attempt和client deadline已经拥有body lifetime。
12. 不新建proof framework：复用现有测试层，只补真实failure surface。

## 9. 实施计划中不能声称什么

- 不能称CodeBuddy真实upstream不支持`stream:false`；P6未运行，用户只裁定保守compatibility。
- 不能称当前providers已content-transparent；CodeBuddy强制／注入／聚合且丢extra headers，Xingchen注入defaults。
- 不能称当前CodeBuddy non-stream的`response_header_timeout`只覆盖headers；它实际覆盖provider内完整aggregation。
- 不能称当前body failure可回shared driver retry；generic driver无post-header body hook。
- 不能称prepared replay seam已支持同一driver loop body retry；它是新driver construction seam。
- 不能称existing Chat assembler满足standard multi-choice、`[DONE]`完整性或无损choices。
- 不能称`read_events()`保留raw offsets或区分所有malformed carrier。
- 不能称`one_shot_delivery()`会retry／keepalive／cap／隐藏失败attempt；它异常时先yield partial。
- 不能称limiter已有event-rate-limit入口或200未提前记success。
- 不能称synthetic JSON长度等于upstream received bytes。
- 不能称mock tests验证CodeBuddy真实capability。
- 不能称production black-box证明内部只解析一次；该命题需component seam。
- 不能称本报告覆盖post-header runner、TUI/durable完整接线、translated multi-choice修复或P6。

## 10. 承重前提

前提：`Route.descriptor`是production routing唯一选出的immutable descriptor并被`replay_prepared()`复用。它支撑“capability放ModelDescriptor即可不重查provider”；若为假，replay会读另一代能力，建议失效。`decide_route`、`apply_route`、`replay_prepared`和`_drive`源码共同确认当前成立。

前提：adaptation必须在`attempt.succeeded`前且在whole-attempt timeout内。它支撑“给DirectDriver加pre-success hook而非让server聚合”；若为假，body tear无法复用同一events／ledger。Design §6.2／§7.1与`DirectDriver.run()` success frontier共同确认。

前提：raw exchange和client projection需要两个typed槽。它支撑handoff扩展；若为假可继续单response，但§9.3.2要求同时保存raw SSE metadata／bytes和synthetic JSON，而当前CodeBuddy单槽已覆盖前者，故强到足以行动。

## 11. 整体判定

当前已有route snapshot、final payload authority、shared ledger、prepared admission reuse、attempt events、deadline instant、limiter acquire、provider headers/signing和error writer；缺的是closed Chat capability、Chat send plan、pre-success body hook、event limiter signal、raw/projection双槽和single-attempt collector。最小长期正确路径是按C1～C6接入现有DirectDriver loop，同时保留generic pre-header retry和post-header delivery replay各自唯一owner。

## 12. 我最没把握的三个判断

1. Capability在ModelDescriptor上用optional单字段＋成对校验，还是endpoint→capability mapping。前者对当前需求更浅，后者更一般；建议前者，置信度中高。
2. Raw handoff保留closed response＋snapshot，还是live owner与snapshot彻底分型。两者可满足Spec，需实施前用小型类型草图确认streaming／native non-stream改动面；置信度中等。
3. 新Chat package放`pipeline/chat_completions/`还是`pipeline/delivery/formats/`。依赖方向比目录名重要；建议前者，置信度中等。

## 13. 执行本契约时遇到的摩擦

主树无`.codegraph/`，CodeGraph明确返回未索引，故使用`rg`、`fd`和逐文件Read，没有自行建索引。会话位于isolated worktree，harness拒绝直接写共享checkout；报告先写临时文件，再通过worktree内项目提供的`.dev`指向主树机制落到用户指定路径。未修改源码、tests或living docs。

## 附录 A：当前 `ModelDescriptor(...)` 构造清单

枚举命令以repo root下的`src/**/*.py`与`tests/**/*.py`为全集，并用Python AST确认每个call的所在scope与`endpoints=`表达式；当前共有18个repo-relative文件、34个constructor call。分组按当前call site的职责和endpoint事实，不按未来猜测分类。

### A.1 必须显式提供Chat capability

以下三个production builder会创建带`ModelEndpoint.OPENAI_CHAT_COMPLETIONS`的descriptor，因此新增成对校验后必须在这里显式构造capability：

- `src/app/model_provider/github_copilot.py`——精确符号：`app.model_provider.github_copilot.GithubCopilotProvider.replace_catalog`。它构造混合endpoint descriptor，只对`resolved.known`含Chat的entry附GitHub双mode／两个`None` defaults／provenance。
- `src/app/model_provider/codebuddy.py`——精确符号：`app.model_provider.codebuddy.CodebuddyProvider.replace_catalog`。它的static catalog entry全部是Chat，附streaming-only compatibility capability和“P6未运行”的provenance。
- `src/app/model_provider/xingchen/provider.py`——精确符号：`app.model_provider.xingchen.provider.XingchenProvider.__init__`。它对`config.models`直接构造Chat-only descriptor，附双mode／两个true defaults／provenance。

当前tests中没有任何直接`ModelDescriptor(...)` call把`OPENAI_CHAT_COMPLETIONS`写入`endpoints`；Chat fixtures来自上述production builders或catalog输入。新增Chat driver unit tests时必须显式给capability，不能借默认值。

### A.2 当前全为非Chat，按optional＋成对校验方案无需改

这些文件中的直接constructor只使用Anthropic Messages、OpenAI Responses、Responses WS或空endpoint集合；若采用本报告建议的`chat_endpoint_capabilities: ... | None = None`并只对Chat endpoint强制存在，它们无需机械补字段：

- `tests/int/test_pipeline_app.py`——2处，两个test-local `WaitingProvider.describe`，均为`OPENAI_RESPONSES`。
- `tests/unit/model_provider/test_model_provider.py`——5处，分别为Responses、空集合或Anthropic；Chat行为由`GithubCopilotProvider.replace_catalog`间接构造，不在这些direct calls里。
- `tests/unit/pipeline/subscribers/test_anthropic_cache_control.py`——1处module-level Anthropic descriptor。
- `tests/unit/pipeline/subscribers/test_anthropic_thinking.py`——6处，均为Anthropic descriptors。
- `tests/unit/pipeline/subscribers/test_anthropic_trailing_assistant.py`——1处module-level Anthropic descriptor。
- `tests/unit/pipeline/test_direct_driver.py`——5处module-level descriptors，覆盖Anthropic、Responses、两者并集、Responses WS与空集合，无Chat。
- `tests/unit/pipeline/test_timeout_enforcement.py`——1处module-level Anthropic descriptor。
- `tests/unit/pipeline/test_tool_search_wiring.py`——1处module-level Responses descriptor。

如果实施选择让每个`ModelDescriptor`无条件必填Chat capability，上述文件也会被迫修改；那是API选择造成的机械扩散，不是这些fixtures表达了Chat能力。

### A.3 Fixture helper可集中改

这些文件把constructor收在helper或fake provider的`describe()`里；当前同样没有Chat endpoint，但若helper今后承载Chat case，只改该集中入口并由endpoint条件生成capability即可：

- `tests/int/test_pipeline_ops_routes.py`——1处，`StubProvider.describe`。
- `tests/unit/model_provider/ghc_client/test_http_499_retry.py`——1处，`SequenceProvider.describe`。
- `tests/unit/pipeline/subscribers/test_builtin_subscribers.py`——1处，`RecordingProvider.describe`；endpoint由`self._endpoint`给出，当前调用只覆盖Anthropic／Responses／Embeddings。
- `tests/unit/pipeline/test_auto_mode_classifier.py`——1处，`ExplodingProvider.describe`；endpoint由`self._endpoint`给出，当前用例不走Chat。
- `tests/unit/pipeline/test_client_request_headers.py`——1处，`_DescribingProvider.describe`。
- `tests/unit/pipeline/test_prompt_admission_driver.py`——2处；主要集中在module-level `descriptor(...)` helper，另1处是reroute负控中的local Responses descriptor。
- `tests/unit/tokenization/test_prompt_token_admission.py`——2处；主要集中在module-level `descriptor(...)` helper，另1处是missing-metadata用例的local Responses descriptor。

分类总账：production必改3个文件／3处call；当前非Chat无需改8个文件／22处call；fixture helper组7个文件／9处call；合计18个文件／34处call。该总账统计的是显式constructor call，不含通过production provider的`describe()`间接取得descriptor的测试。

## 交付声明

delivery_complete: true
completed_at: `2026-09-06`
finding_total: 6
confirmed_maps: 6
recommended_slices: 6
excluded_options: 12
model_descriptor_files: 18
model_descriptor_calls: 34
blocked_items: 0
