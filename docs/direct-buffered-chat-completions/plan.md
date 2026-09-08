# Direct buffered Chat Completions 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务执行。执行跨多个语义提交，开始前还必须读取 `my-skills:writing-handover-docs` 的progress-file协议；每个任务使用下列checkbox追踪。

**Goal:** 让direct `/chat/completions` 的两类SSE-buffered transaction共享同一Chat事实源与完整性合同，在唯一retry owner下恢复透明重试，并把最终candidate的原生Chat事实接入TUI与durable schema。

**Architecture:** Provider通过immutable `ModelDescriptor`声明per-model Chat endpoint capability，pipeline形成attempt-local send plan并拥有全部model-protocol内容处理。`RawSseFrameDecoder`与`ChatAttemptState`负责协议事实，`BufferedAttemptCollector`只读取一个attempt；pre-success adaptation由`DirectDriver`唯一重试，post-header direct streaming由delivery runner唯一重试。Raw upstream exchange、client projection、attempt draft、candidate与request observation分别建模，不让一个对象承担两种事实。

**Tech Stack:** Python 3.14、dataclasses／`StrEnum`／Pydantic、Starlette、httpx2、OpenAI Python SDK 3.8.0、orjson／stdlib JSON、pytest、Ruff check、Pyright。

**Spec:** [`.dev/docs/direct-buffered-chat-completions/design.md`](design.md)；行为authority是 [`.dev/docs/direct-passthrough/spec.md`](../direct-passthrough/spec.md) §5.4／§9.3／§10、[`.dev/docs/error-envelope/spec.md`](../error-envelope/spec.md) §5.1／§8／§10.2 与 [`.dev/docs/tui/spec.md`](../tui/spec.md)“Chat provider observation schema”。

## Global Constraints

- Spec-first已经完成。实现若需要改变可观察行为，先修对应living Spec及修订记录，再改代码；不得用plan、test或comment代替Spec。
- 项目采用verify-by-implementing：每个任务先完成production行为并运行最小probe／既有回归，再补直接覆盖新增failure surface的测试；不要写TDD红→绿步骤。
- 一个failure只能由一个orchestration owner消费`RetryLedger`。`BufferedAttemptCollector`不花预算、不发布attempt event、不打开replacement。
- `RequestContext.stream`只表达client contract；`ChatSendPlan.upstream_stream`表达实际provider mode；final payload唯一authority是`Attempt.payload`。
- Provider只声明capability并原样发送pipeline最终payload／mode；不得改Chat字段、强制stream、解析SSE或聚合JSON。
- Direct streaming最终成功body逐字来自一个attempt；不能拼接旧partial与replacement，不能用重新编码的SSE作为byte-fidelity oracle。
- 第一个合法`[DONE]`前按Spec决定retry；其后冻结semantic state，只继续收raw tail。Post-terminal ending不反转成功，client cancellation／downstream write failure仍不写。
- CodeBuddy streaming-only只是一项P6未实测的compatibility capability。MockTransport测试不能宣称真实CodeBuddy／Xingchen／Copilot会发测试shape；本计划不运行真实P6、真实Xingchen canary或任何需凭据的upstream调用。
- 本次证据分层固定为：unit/component证明本地算法与接口；MockTransport production-entry证明本代理真实接线；本地tear/timeout注入不证明生产故障provenance；现有Responses cassette不证明Chat shape；本次没有Chat cassette；P6/live未执行且不得记为pass。Task8状态记录必须逐层写明实际执行项与这些上限。
- 不触碰、停止、重启或接管生产`4141` Bun服务；不执行cutover。
- 不运行`ruff format`。每个任务使用该任务列出的精确`uv run ruff check`与`uv run pyright`命令。
- 不追coverage数字；最终完整pytest仍按项目固定命令携带现有80%下限。
- 共享工作树执行前加载`my-skills:coordinating-a-shared-git-worktree`。提交只含任务列出的exact paths，不运行`git add -A`，不撤销peer staging；commit message写入`$CLAUDE_JOB_DIR/tmp/`并用`git commit -F`，不用`-m`。不推送。
- Commit边界按产品语义，不按测试是否刚好绿色。每个任务在独立评审通过后形成一个semantic commit；最终candidate只做一次merged-state review，除非修订足以使verdict失效。
- 每条关键判据的正确样本与单变量缺陷控制走同一入口；核对失败原因落在目标断言。普通getter、字段拼接和实现后明确经历过失败→通过的简单行为不扩大成mutation campaign。

---

## File and Interface Map

### New production files

- `src/app/pipeline/chat_completions/__init__.py`：导出Chat event/state/send-plan公共类型，不放流程逻辑。
- `src/app/pipeline/chat_completions/events.py`：`ChatEventReader`与immutable event/error facts；只解释一个完整raw SSE frame。
- `src/app/pipeline/chat_completions/state.py`：per-attempt multi-choice状态、`[DONE]` freeze、标准non-stream projection与observation facts。
- `src/app/pipeline/delivery/buffered_transaction.py`：single-attempt collector、typed ending／decision／candidate records和post-header transaction runner。
- `src/app/pipeline/response_handoff.py`：`ResponseLease`、raw exchange/client projection、immutable Chat attempt snapshot和pending attempt finalizer protocol；只依赖下层records/httpx2，不导入`pipeline.driver`或`direct_driver`。

### Existing production files with focused changes

- `src/app/model_provider/types.py`、`src/app/model_provider/__init__.py`：closed Chat capability与`ResponseModeNotSupported`。
- `src/app/model_provider/github_copilot.py`、`src/app/model_provider/codebuddy.py`、`src/app/model_provider/xingchen/provider.py`：显式capability/provenance；CodeBuddy补通`extra_headers`。
- `src/app/model_provider/codebuddy_client/client.py`、`src/app/model_provider/xingchen/client.py`：删除model-protocol内容处理，保留HTTP/auth/signing/normalization。
- `src/app/pipeline/delivery/sse_source.py`：raw frame decoder；既有`SseEvent`／`read_events()`兼容不变。
- `src/app/pipeline/request.py`：attempt-local`ChatSendPlan`／Chat state与candidate字段；不把Chat state冒充side-only Responses observer。
- `src/app/pipeline/response_handoff.py`：依赖叶上的raw exchange／client projection／Chat snapshot／pending attempt finalizer／response lease contracts，避免`pipeline.driver ↔ direct_driver`导入环。
- `src/app/pipeline/direct_driver/base.py`：pre-success response hook、body-phase prepared retry、response lease ownership与body-verdict后success时点。
- `src/app/pipeline/direct_driver/openai_chat_completions.py`：capability解释、payload defaults、upstream mode与non-stream adaptation。
- `src/app/pipeline/retry.py`、`src/app/pipeline/exceptions.py`：显式reason的stream-event／unterminated／unassemblable typed failures。
- `src/app/pipeline/rate_limiting.py`：event rate-limit入口。
- `src/app/pipeline/driver.py`：让`DriverOutcome`／`HandledRequest`持有并暴露dependency-leaf `ResponseHandoff` accessors；不在本模块定义handoff records。
- `src/app/pipeline/delivery/stream.py`、`src/app/server/routes/inference.py`：prepared response/source builder、post-header runner接线、candidate promotion、accounting与ASGI frontier。
- `src/app/pipeline/delivery/formats/openai_chat_completions.py`：只复用event decoder；不改变translated multi-choice projection。
- `src/app/pipeline/response_observation.py`、`src/app/observability/request_trace.py`、`src/app/observability/request_completion.py`、`src/app/observability/request_log.py`：Chat DTO、schema v2、legacy投影与console presentation。

### New tests

- `tests/unit/pipeline/chat_completions/test_events.py`
- `tests/unit/pipeline/chat_completions/test_state.py`
- `tests/unit/pipeline/delivery/test_buffered_attempt_collector.py`
- `tests/unit/pipeline/delivery/test_buffered_transaction.py`
- `tests/unit/pipeline/test_response_handoff.py`
- `tests/unit/pipeline/test_openai_chat_completions_driver.py`
- `tests/unit/observability/test_chat_response_observation.py`
- `tests/int/test_codebuddy_provider.py`

### Existing tests to extend

- `tests/unit/model_provider/test_model_provider.py`
- `tests/unit/model_provider/test_codebuddy.py`
- `tests/unit/model_provider/xingchen/test_provider.py`
- `tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`
- `tests/unit/model_provider/xingchen/test_client.py`
- `tests/unit/pipeline/test_error_classify.py`
- `tests/unit/pipeline/test_direct_driver.py`
- `tests/unit/pipeline/test_prompt_admission_driver.py`
- `tests/unit/pipeline/test_rate_limiting.py`
- `tests/unit/pipeline/test_timeout_enforcement.py`
- `tests/unit/pipeline/delivery/test_sse_assembly.py`
- `tests/unit/pipeline/delivery/test_one_shot_delivery.py`
- `tests/unit/pipeline/delivery/test_chat_completions_assembler.py`
- `tests/unit/pipeline/test_response_observation.py`
- `tests/unit/observability/test_response_observation_projection.py`
- `tests/unit/observability/test_request_completion.py`
- `tests/unit/observability/test_request_log.py`
- `tests/int/test_pipeline_app.py`
- `tests/int/test_xingchen_provider.py`

---

## Shared Contracts Before Task Execution

### Strategy output

`ChatAttemptState` owns protocol interpretation. Orchestration reads one typed outcome and never re-parsesraw error fields：

```python
class BufferedAction(StrEnum):
    COMMIT = "commit"
    RETRY = "retry"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ChatAttemptDecision:
    action: BufferedAction
    body_end: int
    retry_reason: RetryReason | None
    error: BaseException | None
    tail_ending: str | None
```

- `ChatAttemptState` produces observations and`ChatAttemptDecision`。
- `BufferedAttemptCollector` producesraw body、ending与state；它不执行decision。
- `DirectDriver` executes pre-success`RETRY`／`FAIL` and owns attempt events、budget、limiter、admission、deadline。
- `BufferedTransactionRunner` executes post-header`RETRY`／`COMMIT`／`FAIL` and owns candidate replacement与downstream delivery。
- Budget拒绝时，protocol observations仍保留；`RETRY` proposed effect不变成“已重试”，final carrier按owner实际结果选择。

`BufferedProtocolState[FactsT]`是collector唯一可见的协议接口：`read(frame: RawSseFrame) -> FactsT`只解析一次；`additional_held_bytes(facts: FactsT) -> int`在mutation前给出state增量；`apply(facts: FactsT) -> None`提交同一facts；`held_bytes: int`报告当前state；`projection_size_bytes()`与`observation_size_bytes()`为materialization reservation提供精确逻辑字节。`ChatAttemptState`实现该protocol。Collector不得接受一个返回`None`的observer callback后自行重解析frame。

### Cross-lifecycle state

| Field | Owner | Lifetime | Update | Retry/candidate rule | Observation |
|---|---|---|---|---|---|
| `Route.descriptor.chat_endpoint_capabilities` | provider catalog | route/request-stable | immutable replace only on catalog generation | replay复用同一snapshot | durable只记provenance，不反推capability |
| `Attempt.payload` | DirectDriver | per-attempt；body replay source可引用前一attempt frozen snapshot | private deepcopy then in-place final preparation | body-phase retry复制同一final payload；ordinary pre-header retry重新prepare | request bytes从实际serialized payload计量 |
| `Attempt.chat_send_plan` | OpenAI Chat driver | per-attempt | immutable | 保存client/upstream mode与capability引用，不另持payload | attempt diagnostics |
| `ChatAttemptState` | Chat protocol adapter | per-attempt/candidate-local | monotonic until first`[DONE]`，then frozen | replacement建立后旧state作废；fallback保留旧state | final candidate投影到`ResponseObservation.chat` |
| `BufferedCandidate` | post-header runner | candidate-local | compare-and-set after replacement response opens | replacement未建立时旧candidate继续可提交 | winner/fallback决定request projection |
| `RetryLedger` | request orchestration | request-stable | only one owner calls`take()` per failure | pre-success由DirectDriver；post-header由delivery runner | attempts/replaced failures |
| `RawExchangeSnapshot` | collector/driver handoff | per-attempt immutable | created before raw response close | all attempts计raw bytes；final projection单独选winner | status/headers/version/connection/bytes |
| `ResponseLease` | `_run_attempt()` until explicit transfer/close | per-attempt mutable owner flag | transfer once or close once | hook failure/cancel closes before retry；live stream transfers toserver | no direct projection |
| `ClientBodyProjection` | Chat adapter | final successful adapted attempt | immutable | discarded attempt projection never publishes | downstream JSON only |
| `ChatAttemptSnapshot` | Chat state | per-attempt immutable | materialize once fromfrozen state | carried byadapted handoff orselected streaming candidate | Task7 projection source |
| `PendingAttemptFinalizer` | DirectDriver | per-streaming-attempt state machine | `failed`、`succeed`或`cancelled`恰好一个终态 | runner settles eachcandidate body verdict；noledger/request-terminal ownership | limiter＋attempt events |
| `PendingRequestFinalizer` | initial DirectDriver handoff，then outer runner | one perclient request afterinitialstream opens | `failed`、`succeed`或`cancelled`恰好一个终态 | replacement不得创建第二个；initial pre-header失败仍由driver直接终结 | request terminal event |
| `SelectedBufferedCandidate` | post-header runner | request-final selection | callback exactlyonce beforefinalbody yield | carrieswinner/fallback snapshot、tail、replacement failures | Task7 explicit publication |
| `ResponseObservation.chat` | finalization | request-final | publish once from actual delivered candidate | failed replacement不能覆盖fallback snapshot | JSONL/TUI authority |

---

### Task 1: Closed Chat capability and typed response-mode refusal

**Files:**
- Modify: `src/app/model_provider/types.py`
- Modify: `src/app/model_provider/__init__.py`
- Modify: `src/app/model_provider/github_copilot.py`
- Modify: `src/app/model_provider/codebuddy.py`
- Modify: `src/app/model_provider/xingchen/provider.py`
- Modify: `src/app/pipeline/error_classify.py`
- Test: `tests/unit/model_provider/test_model_provider.py`（含GitHub catalog/descriptor coverage）
- Test: `tests/unit/model_provider/test_codebuddy.py`
- Test: `tests/unit/model_provider/xingchen/test_provider.py`
- Test: `tests/unit/pipeline/test_error_classify.py`

**Interfaces:**
- Produces `ChatResponseMode`、`ChatEndpointCapabilities`、`ModelDescriptor.chat_endpoint_capabilities`。
- Produces `ResponseModeNotSupported(provider, model_id, requested_mode, available_modes)`。
- Consumers: Task 4的`ChatSendPlan`与Task 5的Chat driver。

- [ ] **Step 1: Implement the closed capability types and descriptor validation.**

```python
class ChatResponseMode(StrEnum):
    STREAMING = "streaming"
    NON_STREAMING = "non_streaming"


@dataclass(frozen=True, slots=True)
class ChatEndpointCapabilities:
    response_modes: frozenset[ChatResponseMode]
    stream_options_include_usage_default: Literal[True] | None
    tool_stream_default: Literal[True] | None
    provenance: str

    def __post_init__(self) -> None:
        if not self.response_modes:
            raise ValueError("Chat response_modes must not be empty")
        if not self.provenance:
            raise ValueError("Chat capability provenance must not be empty")
```

Add `chat_endpoint_capabilities: ChatEndpointCapabilities | None = None` to `ModelDescriptor.__post_init__` rules：Chat endpoint present requires non-null capability；Chat endpoint absent requires null。Update every production／test Chat descriptor constructor explicitly；non-Chat descriptors remain null。

- [ ] **Step 2: Implement the mode-specific typed refusal and error mapping.**

```python
class ResponseModeNotSupported(ProviderError):
    def __init__(
        self,
        provider: str,
        model_id: str,
        requested_mode: ChatResponseMode,
        available_modes: frozenset[ChatResponseMode],
    ) -> None:
        self.provider = provider
        self.model_id = model_id
        self.requested_mode = requested_mode
        self.available_modes = available_modes
        available = ", ".join(sorted(mode.value for mode in available_modes))
        super().__init__(
            f"provider {provider} model {model_id} does not support Chat response mode "
            f"{requested_mode.value}; available modes: {available or 'none'}"
        )
```

Map it to`ErrorCategory.CLIENT`／400 and explicit code`unsupported_response_mode` before the generic provider row；do not widen`CapabilityMissing`。Update the provider-subclass exhaustiveness test。

- [ ] **Step 3: Declare explicit provider capability snapshots.**

- GitHub Copilot: both modes，two defaults`None`，provenance names the provider catalog source。
- CodeBuddy: streaming only，include-usage default`True`，tool default`None`，provenance explicitly says“reference compatibility assumption; P6 not run”。
- Xingchen: both modes，both defaults`True`，provenance points to the 2026-09-04 protocol measurement。

No runtime branch may inspect provider name。

- [ ] **Step 4: Run existing provider/routing/error tests before adding new cases.**

Run: `uv run pytest tests/unit/model_provider/test_model_provider.py tests/unit/model_provider/test_codebuddy.py tests/unit/model_provider/xingchen/test_provider.py tests/unit/pipeline/test_error_classify.py -q`

Expected: existing behavior passes after all Chat descriptors are made explicit；any failure should identify an unupdated constructor，not be papered over with a neutral default。

- [ ] **Step 5: Add targeted capability and refusal tests.**

Add cases for empty modes、empty provenance、Chat endpoint without capability、non-Chat endpoint with capability、three provider profiles、frozen snapshot、and exact OpenAI 400 body code。The negative control is replacing`ResponseModeNotSupported`with`CapabilityMissing`；the exact message/code assertion must fail at`unsupported_response_mode`，not at fixture setup。

- [ ] **Step 6: Run task verification.**

Run: `uv run pytest tests/unit/model_provider/test_model_provider.py tests/unit/model_provider/test_codebuddy.py tests/unit/model_provider/xingchen/test_provider.py tests/unit/pipeline/test_error_classify.py -q`

Run: `uv run ruff check src/app/model_provider/types.py src/app/model_provider/__init__.py src/app/model_provider/github_copilot.py src/app/model_provider/codebuddy.py src/app/model_provider/xingchen/provider.py src/app/pipeline/error_classify.py tests/unit/model_provider tests/unit/pipeline/test_error_classify.py`

Run: `uv run pyright src/app/model_provider/types.py src/app/model_provider/__init__.py src/app/model_provider/github_copilot.py src/app/model_provider/codebuddy.py src/app/model_provider/xingchen/provider.py src/app/pipeline/error_classify.py tests/unit/model_provider tests/unit/pipeline/test_error_classify.py`

Expected: pytest pass；Ruff clean；Pyright 0 errors。

- [ ] **Step 7: Review and commit the capability slice.**

Review question: Can a new Chat descriptor omit capability or make an unsupported mode look like an empty endpoint set？Commit message: `feat: model Chat response capabilities`。Use exact paths listed in this task through the shared-worktree coordination procedure。

---

### Task 2: Raw SSE frames and authoritative Chat attempt facts

**Files:**
- Create: `src/app/pipeline/chat_completions/__init__.py`
- Create: `src/app/pipeline/chat_completions/events.py`
- Create: `src/app/pipeline/chat_completions/state.py`
- Modify: `src/app/pipeline/delivery/sse_source.py`
- Modify: `src/app/pipeline/delivery/formats/openai_chat_completions.py`
- Create: `tests/unit/pipeline/chat_completions/test_events.py`
- Create: `tests/unit/pipeline/chat_completions/test_state.py`
- Test: `tests/unit/pipeline/delivery/test_sse_assembly.py`
- Test: `tests/unit/pipeline/delivery/test_chat_completions_assembler.py`

**Interfaces:**
- Produces `RawSseFrameDecoder.feed_bounded()`／`.finish()`、immutable`RawSseFrame`and`RawFrameFeed`。
- Produces `ChatEventReader.read(frame)`、injectable `ChatAttemptState(reader: ChatEventReader)`、`.additional_held_bytes(facts)`、`.held_bytes`、`.observe(facts)`、`.freeze()`、`.projection_reservation()`、`.observation_reservation()`、`.to_completion_bytes()`、`.observation_facts()`and immutable`ChatAttemptSnapshot`。同一state实例必须同时服务decision／aggregation／observation；projection不得重解析synthetic body。
- Consumers: Task 3 collector、Task 5 adaptation、Task 6 runner、Task 7 observation projector。

- [ ] **Step 1: Freeze an independent literal compatibility oracle before changing `read_events()`.**

Run the current implementation against literal inputs and record the expected `(event, data)` list in the task checkpoint／`$CLAUDE_JOB_DIR/tmp` probe before changing production；do not add the test file until Step 7：

```python
CASES = [
    (
        b"event: a\r\ndata: 1\r\n\r\nevent: b\r\ndata: 2\r\n\r\n",
        [("a", "1"), ("b", "2")],
    ),
    (
        b"event: a\rdata: one\r\revent: b\ndata: two\n\n",
        [("a", "one"), ("b", "two")],
    ),
    (
        b"event: x\ndata: first\ndata: second",
        [("x", "first\nsecond")],
    ),
]
```

Before production edits，run a `$CLAUDE_JOB_DIR/tmp` probe that calls thecurrent`read_events()`and compares with these literals。Save only command/output in the task checkpoint；theoracle is the literal table，not output regenerated by the future decoder。

- [ ] **Step 2: Implement a bounded stateful raw frame decoder beneath existing `read_events()`.**

```python
@dataclass(frozen=True, slots=True)
class RawSseFrame:
    raw: bytes
    body_end: int
    start: int
    end: int
    ordinal: int
    terminated: bool

    @property
    def body(self) -> memoryview:
        return memoryview(self.raw)[: self.body_end]


@dataclass(frozen=True, slots=True)
class RawFrameFeed:
    frames: tuple[RawSseFrame, ...]
    consumed: int
    overflowed: bool
```

`RawSseFrameDecoder`公开精确接口`held_bytes: int`、`feed_bounded(chunk: bytes, *, remaining_capacity: int | None) -> RawFrameFeed`与`finish() -> RawSseFrame | None`。`feed_bounded()`在memoryview上逐frame扫描，不先复制整个chunk；只保留`consumed`前缀，next frame不能完整落入capacity时令`overflowed=True`且不保留该frame任何bytes。这样同一transport chunk内的完整`[DONE]`frame可先产出，随后的越界tail frame被拒绝，同时decoder＋candidate从未持有超过cap的副本。`RawSseFrame`只拥有一份`raw` bytes；`body_end`＋memoryview表达不含separator的parse范围，禁止再切出第二份frame-sized`body` bytes。`finish()`最多返回一个`terminated=False`的EOF remainder并清空buffer。`raw`includes original separator；offset uses half-open`[start,end)`。Refactor`read_events()`to adapt decoder output back to current`SseEvent`behavior，including existingEOF-tail parsing。Do not interpretChat here。

- [ ] **Step 3: Re-run the frozen literal oracle after the refactor.**

Run bothnew decoder andrefactored`read_events()`against`CASES`。Assertnewraw frames concatenate to theinput andlegacy events equalthe literalexpected list；do not compare twooutputs derived fromthe same decoder withoutthe literaloracle。Addone single-variable control thatrecognizes onlyLF separators andone thatdropsEOF tail；each must failthe correspondingliteral assertion，withfailure at event/byte equality rather thansetup。This probe proveslocalparser compatibility，notprovider behavior。

- [ ] **Step 4: Implement strict Chat event facts and error-carrier precedence.**

```python
class ChatEventKind(StrEnum):
    DONE = "done"
    CHUNK = "chunk"
    ERROR = "error"
    UNKNOWN = "unknown"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class ChatEventFacts:
    kind: ChatEventKind
    frame: RawSseFrame
    value: JsonObservation
    error_values: tuple[str, ...] = ()
    retry_reason: RetryReason | None = None
    issue: ObservationIssue | None = None
```

Recognition order isexact：parse withstdlib whilepreservinganexplicit`JsonObservation`availability；identifyevent-nameerror beforefreezingthewholevalue，thenobject withtop-level`error`，thenflat object`type == "error"`，thenordinaryChat chunk。JSON null is`EXPLICIT_NULL`，arrays/scalars areobservednon-object，decode failure is`UNREADABLE`；these states never sharebare`None`。All nonempty`code`／`type`values must map to the same known transient class to set`retry_reason`；conflict／unknown／malformed is terminal nonretry。A knownerror carrier containinganunfreezablevalue suchas`1e400`retainsERROR kind/retry reason andrecordswholevalue unreadable；anordinaryevent withthatvalue becomesunassemblable instead ofraisinglocal`FrozenJsonError`。Do not call`SseEvent.json()`for this decision。

- [ ] **Step 5: Implement per-choice state and standard non-stream projection.**

```python
@dataclass(frozen=True, slots=True)
class ChatUnattributedFact:
    frame_ordinal: int
    start: int
    end: int
    field_path: str
    value: JsonObservation


@dataclass(frozen=True, slots=True)
class ChatToolCallSnapshot:
    index: int
    id: JsonObservation
    type: JsonObservation
    name: JsonObservation
    arguments: JsonObservation
    tool_unknown: FrozenJsonObject
    function_unknown: FrozenJsonObject


@dataclass(frozen=True, slots=True)
class ChatChoiceSnapshot:
    index: int
    finish_reason: JsonObservation
    reasoning_content: JsonObservation
    tool_calls: tuple[ChatToolCallSnapshot, ...]
    choice_unknown: FrozenJsonObject
    message_unknown: FrozenJsonObject


@dataclass(frozen=True, slots=True)
class ChatAttemptSnapshot:
    done_seen: bool
    semantic_end_offset: int | None
    identity: FrozenJsonObject
    choices: tuple[ChatChoiceSnapshot, ...]
    usage: UsageObservation | None
    stream_error: JsonObservation
    error_values: tuple[str, ...]
    error_retry_reason: RetryReason | None
    top_level_unknown: FrozenJsonObject
    unattributed: tuple[ChatUnattributedFact, ...]
    issues: tuple[ObservationIssue, ...]


@dataclass(frozen=True, slots=True)
class MaterializationReservation:
    working_copy_bytes: int
    output_bytes: int

    @property
    def total_bytes(self) -> int:
        return self.working_copy_bytes + self.output_bytes
```

State keys are`choice_index`and`(choice_index, tool_index)`。Implementdirect-passthrough§9.3.1 field table exactly：first identity values and conflict failure；explicit knownlast-wins fields；content／refusal／reasoning／arguments concatenation；tool and choice ordering；finish reason consistency；last explicit usage；unknown same-value retention and conflict`unassemblable`；no syntheticid／time／model。First valid`[DONE]`freezessemantic state；later frames remain raw tail only。

Keepchoice-level andmessage/delta-levelunknown inseparate maps，andtool-level/function-levelunknown inanotherseparate pair；reserved names cannotoverwriteanother layer。Invalidchoice/tool indices retainfullreadableobject plusframe ordinal／offset／field path in`unattributed`andmarkadaptation unassemblable。Onfirsterror，state storesraw`stream_error`availability、allspellings、explicitretry reason anderrorframe half-openend offset；laterdecision reads these fields withoutreparsing。

Usage keepsabsent、explicit null、empty object、zero、wrong type andinconsistent distinct。Explicit null createsa`UsageObservation`raw-null fact butdoesnot eraseapriorlast-object projection；wrong standard token/detail types createboundedconversion issues andpreserveraw。`logprobs.content`and`.refusal`each keepabsent/null/array state；only-null projectsnull，arrays concatenate，laternull doesnoterasearray。

Maintainlogical`held_bytes`for every retainedstate copy：UTF-8 bytes ofallkeys andaccumulated strings plusrecursiveFrozenJson value size。FrozenJson equality isrecursivevalue equality，neverorjson serialization，soarbitrary-size integers remainvalid。`additional_held_bytes(facts)`computesdelta directly fromthecurrentfield ledger andincomingfacts；it must notcloneanyretainedchoice/tool metadata orcallpublicmaterializers。

`projection_reservation()`and`observation_reservation()`compute`MaterializationReservation`withoutbuildingpayload/snapshot/whole repr：`working_copy_bytes`countsallnewjoined strings、keys、containers’logical serialized punctuation andothercoexisting logicalcopies；`output_bytes`countsfinalstdlib JSON bytes orfrozenobservation bytes withanincremental recursivecounter。Thecounter scales withnesting depth andchoice/tool/unattributed/issue counts；fixed64KiB orzero working guesses areforbidden。AfterTask3 reserves`total_bytes`，`to_completion_bytes()`materializespayload anduses thesameincrementalstdlib JSON encoder，thenreleasesworking-copy reservation whilekeepingoutput bytes。Observation follows thesame two-phase`reserve total → materialize → release working copy`transfer。A2,000,000-byte content probe anddeep-nesting／many-small-records probes must showthelogicalsum ofcoexisting representations neverexceedsreservation；they do notclaimaCPython heap bound。Replacement/reset returnsstate held bytes tozero。

Use OpenAI`ChatCompletionStreamState`only as a differential oracle for standard known-field positive examples，including`logprobs` explicit-null。Production output must be generated from theSpec-owned state and must stripSDK helper fields such as`parsed`／`parsed_arguments`andstream-only tool`index`。

- [ ] **Step 6: Let translated `ChatCompletionsAssembler` reuse only decoding facts.**

Keep its public signature and currentsingle-projection state。It may consume decodedrole／content／reasoning／tools／finish／usage／error facts，but it must not adopt directmulti-choice state、`[DONE]` success contract orTUI minimum-choice projection。Run its existing suite before adding reader-specific tests。

- [ ] **Step 7: Add focused tests after the production state works.**

Tests must cover raw byte/offset equality、every-byte chunk splits aroundCRLF ambiguity、EOF tail、error carrier withchoices、flat event error、code/type conflict、finish without`[DONE]`、semantic freeze withraw tail、multi-choice/tool order、duplicate and unnamed calls、usage、unknown conflict and`unassemblable`。Addthree-wayJSON value tests for`null`／array／malformed；onlymalformed isUNREADABLE，bothreadablenonobjects makeadaptation unassemblable。Add100000-byteunknown keys attop-level andnestedtool/function，assertprospective/held size includeskeys；addrepeated`10**100`unknown value，assertrecursive equality without64-bit serializer failure。Addprojection byte-size equality againsttheexactfinalstdlib JSON encoder using`1e-7`、Unicode、escaping andlargeintegers。Addlogprobs tables foronly-null、null→empty array andarray→null。Addinvalidchoice/tool rawfacts withordinal/offset/path，choice-level`message`unknown collidingwithdelta unknown，andknownerror plusunfreezable`1e400`future field；assertnofact loss andcarrier classification survives。Forbyte fidelity，expected bytes are independent literals；do not generateexpected with`encode_frame()`。

Critical controls：resolvechunk-finalambiguousCR eagerly and assertall-byte-split oracle fails；allocateaseparateframe-sizedbody slice and assertnear-cappeak fails；removefreeze guard and assert snapshot changes；restorecurrent`error and not choices`predicate and assert carrier test fails；dropseparator fromraw and assert exact byte/offset test fails；changeaggregation toemitonlychoice0 and assertfulltwo-choice JSON object equality fails atmissingchoice1 rather thananother field；omitunknown key bytes fromsize and assertlarge-key delta fails；replace recursiveFrozenJson equality/stdlib size withorjson and assertbig-int／float-size controls fail；collapseJSON null toabsence and assertthree-way availability fails；mergechoice/messageunknown maps and assertbothraw values fail；dropstoredretry reason/end offset and assertdecision/body-end control fails。Fake shapes prove local handling only。

- [ ] **Step 8: Run task verification.**

Run: `uv run pytest tests/unit/pipeline/chat_completions/test_events.py tests/unit/pipeline/chat_completions/test_state.py tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_chat_completions_assembler.py -q`

Run: `uv run ruff check src/app/pipeline/chat_completions src/app/pipeline/delivery/sse_source.py src/app/pipeline/delivery/formats/openai_chat_completions.py tests/unit/pipeline/chat_completions tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_chat_completions_assembler.py`

Run: `uv run pyright src/app/pipeline/chat_completions src/app/pipeline/delivery/sse_source.py src/app/pipeline/delivery/formats/openai_chat_completions.py tests/unit/pipeline/chat_completions tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_chat_completions_assembler.py`

Expected: pytest pass；Ruff clean；Pyright 0 errors。

- [ ] **Step 9: Review and commit the protocol-facts slice.**

Review question: Doesdirect raw fidelity remain independent fromtranslated projection，and can anyunknown/malformederror fall through toNETWORK？Commit message: `feat: model buffered Chat stream facts`。

---

### Task 3: Single-attempt buffered collector without retry ownership

**Files:**
- Create: `src/app/pipeline/delivery/buffered_transaction.py`
- Modify: `src/app/pipeline/delivery/sse_source.py`
- Modify: `src/app/pipeline/chat_completions/state.py`
- Create: `tests/unit/pipeline/delivery/test_buffered_attempt_collector.py`
- Modify/Test: `tests/unit/pipeline/chat_completions/test_events.py`
- Modify/Test: `tests/unit/pipeline/delivery/test_sse_assembly.py`

**Interfaces:**
- Extends `RawSseFrameDecoder` with `propose_one_bounded()`／`RawFrameProposal`，leavingbatch `feed_bounded()` onlyforlegacy/read-events compatibility。
- Produces `BufferedEnding`、mutable `BufferedMemoryAccount`、`BufferedAttemptResult[StateT]`、`BufferedAttemptCollector.collect()`。
- Consumes typed `BufferedProtocolState[FactsT]`；the collector calls `state.read(frame)` once，then`additional_held_bytes(facts)`before`apply(facts)`。
- Does not consume `RetryLedger`; Task 4/5/6 are the onlyorchestration consumers。

- [ ] **Step 1: Add a single-frame bounded proposal API.**

```python
@dataclass(frozen=True, slots=True)
class RawFrameProposal:
    frame: RawSseFrame | None
    consumed: int
    overflowed: bool
    needs_more: bool
```

Add`RawSseFrameDecoder.propose_one_bounded(chunk: memoryview, *, remaining_capacity: int | None) -> RawFrameProposal`。It returnsat mostonecompleteframe andnevercopies/consumestheunreturned suffix；caller advancesby`consumed`andcallsagain withcapacity recomputed afterstate mutation。Ambiguouschunk-finalCR remainsstaged untilnextbyte/EOF。Keepbatch`feed_bounded()`asacompatibility wrapper forlegacy`read_events()`andTask2 tests，butcap-awarecollector mustnot useit。

- [ ] **Step 2: Implement typed ending and result records.**

```python
class BufferedEnding(StrEnum):
    CLEAN_EOF = "clean_eof"
    TRANSPORT_ERROR = "transport_error"
    IDLE_TIMEOUT = "idle_timeout"
    ATTEMPT_DEADLINE = "attempt_deadline"
    CLIENT_DEADLINE = "client_deadline"
    CAP_EXCEEDED = "cap_exceeded"
    LOCAL_ERROR = "local_error"


@dataclass(slots=True)
class BufferedMemoryAccount:
    cap_bytes: int
    raw_bytes: int = 0
    staging_bytes: int = 0
    state_bytes: int = 0
    projection_bytes: int = 0
    observation_bytes: int = 0
    peak_bytes: int = 0

    @property
    def total(self) -> int:
        return (
            self.raw_bytes
            + self.staging_bytes
            + self.state_bytes
            + self.projection_bytes
            + self.observation_bytes
        )

    def replace(
        self,
        *,
        raw_bytes: int | None = None,
        staging_bytes: int | None = None,
        state_bytes: int | None = None,
        projection_bytes: int | None = None,
        observation_bytes: int | None = None,
    ) -> None:
        values = {
            "raw_bytes": self.raw_bytes if raw_bytes is None else raw_bytes,
            "staging_bytes": self.staging_bytes if staging_bytes is None else staging_bytes,
            "state_bytes": self.state_bytes if state_bytes is None else state_bytes,
            "projection_bytes": self.projection_bytes if projection_bytes is None else projection_bytes,
            "observation_bytes": self.observation_bytes if observation_bytes is None else observation_bytes,
        }
        total = sum(values.values())
        if self.cap_bytes > 0 and total > self.cap_bytes:
            raise BufferCapExceeded(total, self.cap_bytes)
        for name, value in values.items():
            setattr(self, name, value)
        self.peak_bytes = max(self.peak_bytes, total)


@dataclass(frozen=True, slots=True)
class BufferedAttemptResult[StateT]:
    body: bytes
    state: StateT
    ending: BufferedEnding
    error: BaseException | None
    upstream_tear: Exception | None
    memory: BufferedMemoryAccount
    peak_held_bytes: int
```

Cancellation and`GeneratorExit`are not enum values；they propagate after deterministic cleanup because no final client action may be chosen。

- [ ] **Step 3: Implement the collector as a single-attempt owner.**

`BufferedAttemptCollector[StateT, FactsT]`的构造签名固定为`__init__(*, state: BufferedProtocolState[FactsT], cap_bytes: int) -> None`，读取签名固定为`collect(chunks: AsyncIterator[bytes], *, upstream: UpstreamSource) -> BufferedAttemptResult[StateT]`。Collector对每个frame严格执行`facts = state.read(frame)`一次、`delta = state.additional_held_bytes(facts)`、memory预留、`state.apply(facts)`；没有第二个observer callback。

Maintainone mutable`BufferedMemoryAccount`coveringemitted raw、decoder staging、`state.held_bytes`andanysimultaneously materializedprojection／observation。For eachtransport chunk keepa caller-owned`memoryview`cursor and loop：compute`remaining_capacity = cap - (raw + staging + state + copies)`；call`propose_one_bounded(cursor, remaining_capacity=remaining_capacity)`；forits at-most-oneframe call`facts = state.read(frame)`once，reserve`frame.raw + state.additional_held_bytes(facts)`，applythefacts，advancebyproposal.consumed，then recomputecapacity beforethe nextframe in thesamechunk。Cap-awarecollector mustnevercallbatch`feed_bounded()`。Projection materialization performs`reservation = state.projection_reservation()`、`memory.replace(projection_bytes=reservation.total_bytes)`、`body = state.to_completion_bytes(reservation)`、then`memory.replace(projection_bytes=reservation.output_bytes)`afterworking copies die。Observation uses thesame sequence with`observation_reservation()`and`observation_bytes`。Anyallocation/materializer sentinel firingbeforethefirst`memory.replace`failsTask3 tests。Ifownership transfers，releaseoldslot andreserve newslot inone documented order。`BufferedAttemptResult`carries thesame mutableaccount so laterprojection cannot escapeits cap。Close source exactly once。Map known guard exception types toending；classifylocal errors bypositive`UpstreamSource.tear`identity rather than a denylist。Use existingcleanup helper so close failure does not replaceprimary。

- [ ] **Step 4: Add the Chat decision adapter without orchestration.**

Implement`decide_chat_attempt(result) -> ChatAttemptDecision`fromSpec§5.4。Before`[DONE]`，natural/transport/idle/attempt endings requestNETWORK retry；known event errors use state’s explicit reason；unknown/unassemblable/local/cap/client deadline fail。After`[DONE]`，alltail endings exceptcancellation produceCOMMIT withfrozen observation andbody_end chosen byframe offsets。The function returnsintent；it never callsledger／sleep／reopen／send。

- [ ] **Step 5: Run a production-object probe before tests.**

Use real`UpstreamSource`and a localasync iterator to exercisehappy EOF、transport error、cap andclose failure。Print/inspectending、peak、body length、state andexception chain。This proves collector ownership and types，notASGI wiring。

- [ ] **Step 6: Add collector tests and controls.**

Cover everyending、partial frame staging undercap、`[DONE]`frame itself crossingcap、post-terminaltail crossingcap、sourceclose exactly once、primary+cleanup chain andcancellation propagation。Thecriticalcap sample puts a complete`[DONE]`frame andanoversizedtail frame in thesame transport chunk；assertbody retains exactlythrough`[DONE]`、tail isrejected、decision ispost-terminalCOMMIT andpeak≤cap。A second single-chunk sample containssemantic frame A whosefacts substantially growstate followedbyframe B；initialraw-onlycapacity fitsboth，butafterA `raw + state`leaves insufficientcapacity forB。Assertcollector accepts/appliesA，recomputescapacity，rejectsB withoutreading/applyingitsfacts andkeepsmaximumlegalprefix；a batch`feed_bounded()`mutation must failbody/state/read-count assertions。A third sample keepsraw alonebelowcap butuseslongcontent／reasoning／unknown values so`raw + state`crossescap；assertpre-terminalcap failure、peak≤cap andno projection materialization。A third2,000,000-byte content sample reachesterminal undera highercap，asserts`projection_reservation.total_bytes`coversworking payload＋final bytes；deep-nested unknown and5000-small-choice observation samples assertreservation grows withstructure andcovers theindependently computedlogical representation sum。Install sentinels onpayload/snapshot materializers toprovebothreservation methods returnbeforeallocation。Single-variable controls eitherpre-rejectthewholechunk、appendbeforechecking、zeroout`state_bytes`、reserveonly`output_bytes`、restorefixed64KiB working orzeroobservation working；each must failthe correspondingexactbody／decision／logical-peak assertion。Thecleanup control forcesdouble-close orprimary replacement and must failidentity/count assertions。

Add component test`test_one_attempt_reuses_one_state_for_decision_aggregation_and_observation`：injecta`CountingChatEventReader`intoone`ChatAttemptState`，collectNcompleteframes，then call decision；obtain`projection_reservation()`，reserve throughthe shared`BufferedMemoryAccount`，call`to_completion_bytes(reservation)`；obtain`observation_reservation()`，reserve，then call`observation_facts(reservation)`。Assertreader calls=N andallprojections carrythe same state generation／identity。Patch thewhole-body/synthetic reparse seam to raisea sentinel；ifobservation reparsessyntheticbody，the same test must failat theexplicit“reparse forbidden”assertion，not atmethod lookup orJSON fixture parsing。

- [ ] **Step 7: Run task verification.**

Run: `uv run pytest tests/unit/pipeline/delivery/test_buffered_attempt_collector.py tests/unit/pipeline/chat_completions/test_events.py tests/unit/pipeline/delivery/test_sse_assembly.py -q`

Run: `uv run ruff check src/app/pipeline/delivery/buffered_transaction.py src/app/pipeline/delivery/sse_source.py src/app/pipeline/chat_completions/state.py tests/unit/pipeline/delivery/test_buffered_attempt_collector.py tests/unit/pipeline/chat_completions/test_events.py tests/unit/pipeline/delivery/test_sse_assembly.py`

Run: `uv run pyright src/app/pipeline/delivery/buffered_transaction.py src/app/pipeline/delivery/sse_source.py src/app/pipeline/chat_completions/state.py tests/unit/pipeline/delivery/test_buffered_attempt_collector.py tests/unit/pipeline/chat_completions/test_events.py tests/unit/pipeline/delivery/test_sse_assembly.py`

Expected: pytest pass；Ruff clean；Pyright 0 errors。

- [ ] **Step 8: Review and commit the collector slice.**

Review question: Can any path spendbudget、openreplacement or classify a localbug as upstream insidecollector？Commit message: `feat: collect buffered upstream attempts`。

---

### Task 4: DirectDriver pre-success hook and body-phase prepared retry seam

**Files:**
- Modify: `src/app/pipeline/request.py`
- Create: `src/app/pipeline/response_handoff.py`
- Modify: `src/app/pipeline/driver.py`
- Modify: `src/app/pipeline/direct_driver/base.py`
- Modify: `src/app/pipeline/direct_driver/openai_chat_completions.py`
- Modify: `src/app/pipeline/exceptions.py`
- Modify: `src/app/pipeline/retry.py`
- Modify: `src/app/pipeline/rate_limiting.py`
- Create: `tests/unit/pipeline/test_response_handoff.py`
- Test: `tests/unit/pipeline/test_direct_driver.py`
- Test: `tests/unit/pipeline/test_prompt_admission_driver.py`
- Test: `tests/unit/pipeline/test_rate_limiting.py`
- Test: `tests/unit/pipeline/test_timeout_enforcement.py`

**Interfaces:**
- Produces `ChatSendPlan(client_stream, upstream_stream, capabilities)` with no payload field。
- Produces `RawExchangeSnapshot`、`ClientBodyProjection`、`ChatAttemptSnapshot`、`ResponseLease`、`PendingAttemptFinalizer`、`PendingRequestFinalizer`、`ResponseHandoff` in dependency-leaf `pipeline/response_handoff.py`；`pipeline.driver`与`direct_driver`只向下import，不能互相回import。
- Produces overridable DirectDriver hooks forattempt preparation、upstream stream mode andpre-success response completion。
- Produces event-rate-limit entry、phase-aware prepared retry anddeferred streaming attempt finalization。
- Consumers: Task 5 Chat adapter andTask 6 server handoff。

- [ ] **Step 1: Add attempt and handoff records with one payload authority.**

```python
@dataclass(frozen=True, slots=True)
class ChatSendPlan:
    client_stream: bool
    upstream_stream: bool
    capabilities: ChatEndpointCapabilities


@dataclass(frozen=True, slots=True)
class RawExchangeSnapshot:
    request_body_bytes: int
    response_body_bytes: int | None
    status_code: int
    headers: tuple[tuple[str, str], ...]
    http_version: str | None
    connection: FrozenJsonObject


@dataclass(frozen=True, slots=True)
class ClientBodyProjection:
    body: bytes
    status_code: int
    content_type: str
    headers: tuple[tuple[str, str], ...]


class PendingAttemptFinalizer(Protocol):
    async def succeed(self) -> None: ...
    async def failed(self, error: BaseException) -> None: ...
    async def cancelled(self, error: BaseException) -> None: ...


class PendingRequestFinalizer(Protocol):
    async def succeed(self) -> None: ...
    async def failed(self, error: BaseException) -> None: ...
    async def cancelled(self, error: BaseException) -> None: ...


@dataclass(slots=True)
class ResponseHandoff:
    response: httpx2.Response | None = None
    raw_exchange: RawExchangeSnapshot | None = None
    client_projection: ClientBodyProjection | None = None
    chat_snapshot: ChatAttemptSnapshot | None = None
    pending_attempt_finalizer: PendingAttemptFinalizer | None = None
    pending_request_finalizer: PendingRequestFinalizer | None = None
```

The `...` bodies above arelegal`Protocol`method declarations，not implementation placeholders。`Attempt.payload`remains solefinal payload authority；`Attempt.chat_send_plan`holds modes/capability only。`ChatAttemptSnapshot`is theimmutableTask2facts transfer，notTUI rendering。`ResponseHandoff.response`is the sole live raw response owner whennon-null；adapted success closes thelease andreturns`response=None`withimmutable raw/client/facts snapshots。Optionalrecords carryraw/client/facts/finalization state acrosslayers。Existing property accessors keepnon-Chat callers source-compatible。Captureconnection withcurrent`snapshot_upstream_connection()`andfreeze it，rather than flatteningit to a string。

`ResponseLease`also lives in`response_handoff.py`and ownsone rawresponse fromheaders acquisition untiloneof`transfer()`or`close(primary, discard_reason)`。`stream()`returnsaniterator whose`aclose()`delegates tothat sameidempotence-guarded lease close，soTask5 collector closure and`_run_attempt()`exception cleanup cannot double-close。It recordsclosed/transferred state sohook success transfers exactlyonce，whilehook failure/cancellation closes exactlyonce throughmoved/shared`_finish_response_cleanup()`semantics。

Replace`DriverOutcome.response`storage with`handoff: ResponseHandoff | None`andkeepa read-only`response`compatibility property returning`handoff.response`。`succeeded`meanshandoff exists anderror isNone，soadapted success withclosedraw response／non-nullprojection isstill success。Update synthesized outcomes in`pipeline.driver`tocreatea normal`ResponseHandoff(response=...)`；`HandledRequest`adds read-only`client_projection`、`raw_exchange`、`chat_snapshot`and`pending_finalizer`accessors，so server code never reaches acrosslayers to guessshape。

- [ ] **Step 2: Add narrow DirectDriver extension points without changing current drivers.**

Define default hooks that are no-ops for Anthropic／Responses／Embeddings：

```python
def _prepare_attempt_payload(self, context: RequestContext, attempt: Attempt) -> None:
    return None


def _upstream_stream(self, context: RequestContext, attempt: Attempt) -> bool:
    return context.stream


async def _complete_response(
    self,
    context: RequestContext,
    outcome: DriverOutcome,
    attempt: Attempt,
    lease: ResponseLease,
) -> ResponseHandoff:
    return ResponseHandoff(response=lease.transfer())


def _reuse_prepared_after_response_failure(self, error: BaseException) -> bool:
    return False


def _defer_success_until_body(self, context: RequestContext, attempt: Attempt) -> bool:
    return False
```

Call`_prepare_attempt_payload()`afterprivatecopy/model override and beforeadmission/serialization。After`_send()`returnsheaders，`_run_attempt()`createsa`ResponseLease`and calls`_complete_response()`insideitsabsolute deadline but outside`response_header_timeout`。Ifhook raisesor iscancelled beforetransfer，`_run_attempt()`must closeleasewiththeprimary/discardreason beforethe error reachesthe retry loop；ifclosealsofails，preservetheprimary identity andchaincleanup。Default hook transferslive response andkeepscurrentbehavior。When`_defer_success_until_body()`isfalse，move`RateLimiter.observe_success()`andsuccess events afterhook success。Whenit istrue，base createsoneconcrete`PendingAttemptFinalizer`forlimiter＋attempt events。Onlythe **initial successful streaming handoff** also createsone`PendingRequestFinalizer`andtransfersrequest-terminal ownership totherunner；initialpre-header failures occurbeforethat transfer andremainfully owned bytheoriginalDirectDriver，so they cannot becomeunsettled。Prepared replacementdrivers runwith`defer_request_terminal=True`and`create_request_finalizer=False`：apre-header replacement failure publishesattempt failure andreturnsits error totherunner withoutrequest terminal，asuccessfulreplacement createsonlyitsattempt finalizer。Task6 retains theinitial request finalizer acrossallcandidates andcallsitexactlyoncewhenfinalrequest action isknown。Client/downstream cancellation callsactiveattempt finalizer andtheoneouterrequest finalizer`cancelled(error)`；these settleownership withoutlimiter success/failure orretry events，leavingrequest completion toreportGONE。No finalizer spendsledger。Do not changeordinary pre-header retry semantics。

- [ ] **Step 3: Implement body-phase prepared retry inside the existing driver loop.**

Whenhook failure isknown retryable and`_reuse_prepared_after_response_failure()`returns true，storeprivatecopy of`attempt.payload`plus`attempt.token_admission`as next-attempt prepared source。The next iteration still calls`RequestContext.begin_attempt()`、computesfreshattempt deadline、calls`RateLimiter.acquire()`and publishes failure/success events，but skipsmutable`attempt.prepare`andfreshadmission through existingprepared/reuse paths。A laterordinary pre-header failure remains onthe frozen prepared path because the request already crossed the body replay frontier。

Add`defer_request_terminal: bool = False`and`create_request_finalizer: bool = False`toDirectDriver construction。Defaultfalse keepsallcurrent callers。Theinitial directChat driver uses`defer_request_terminal=False, create_request_finalizer=True`；pre-header terminal failure therefore stayswiththeoriginaldriver，whilea successfulstreaming handoff createsandtransfers theouterrequest finalizer。`replay_prepared()`forChat replacements constructsdrivers with`defer_request_terminal=True, create_request_finalizer=False`：`_handle_failure()`still publishesattempt failure andsets`outcome.error`，butdoesnot publishrequest failure；successfulreplacement handoffs carryonlyattempt finalizers。Do not call`replay_prepared()`recursively frominside`DirectDriver.run()`and do not construct aseconddriver loop。

- [ ] **Step 4: Add typed event failures and limiter entry.**

Add a retryable upstream-event error carryingexplicit`RetryReason`andraw error facts；addunterminated／unassemblable nonretry types as specified。Teach`reason_for()`to read theexplicit reason beforestatus inference。Add`RateLimiter.observe_event_rate_limit(retry_after: float | None = None)`that reuses the existinglimited transition without fabricatingHTTPstatus；defaultwait usesconfigured`retry_interval`。

- [ ] **Step 5: Run existing generic driver tests before adding Chat behavior.**

Run: `uv run pytest tests/unit/pipeline/test_response_handoff.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/test_prompt_admission_driver.py tests/unit/pipeline/test_rate_limiting.py tests/unit/pipeline/test_timeout_enforcement.py -q`

Expected: existingdrivers retainattempt events、ordinaryretry repreparation、header timeout、cleanup andcancellation behavior。

- [ ] **Step 6: Add generic hook/prepared-phase tests.**

Use a tinytest driver subclass whosehook failsafterheaders once。Assertcalls=2、ledger spent=1、prepare=1、firstadmission fresh、secondreused、acquire=2、freshattempt deadline perattempt、oneunchanged request/client deadline supplied bytheouter harness、header timeout excludesbody andsuccess events occur onlyafterbody verdict。Thefirstraw response mustclose exactlyonce **before** secondprovider send；a primary hook error plusclose error mustretainprimary identity withcleanup chained。Single-variable controls omitlease cleanup orletcleanup replaceprimary；close-order／identity assertions must fail。Negative control sendsbody failure throughordinary retry and must failprepare/admission counters。Keep existing`test_retry_rechecks_payload_and_rejects_before_second_limiter_and_send`as reverse control：ordinarypre-header retry stillreprepares。

Add exactlimiter tests。First，startNORMAL，call`observe_event_rate_limit()`withfake clock/sleep andno retry-after，assertmodeLIMITED andnext`acquire()`waitsconfigured`retry_interval`；then onehook retry consumesexactlyone`SERVER_ERROR`budget andcallsprovider twice whileraw HTTP statusremains200。Single-variable control omits theevent signal；themode/wait assertion must fail，not merelythe finalresponse。Second，putlimiter inRECOVERING one success short ofNORMAL，obtainastreaming handoff andassertheaders alone leaveRECOVERING unchanged；callpending finalizer`succeed()`andonlythenassertNORMAL。Single-variable control restoresheaders-stage`observe_success()`and must failthepre-finalizer mode assertion。

Add client-deadline reuse test aroundthe body hook：firstattempt advancesfakeclock pastpart ofone fixedrequest deadline andfails，secondattempt delays beyondremainingtime。Correct implementation timesout atthe originalabsolute instant；single-variable control recomputesdeadline perattempt andincorrectlysucceeds，so thetargetelapsed/calls/outcome assertions turnred。This is separate fromfreshattempt deadlines，which must stillrenew。

- [ ] **Step 7: Run task verification.**

Run: `uv run pytest tests/unit/pipeline/test_response_handoff.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/test_prompt_admission_driver.py tests/unit/pipeline/test_rate_limiting.py tests/unit/pipeline/test_timeout_enforcement.py -q`

Run: `uv run ruff check src/app/pipeline/request.py src/app/pipeline/response_handoff.py src/app/pipeline/driver.py src/app/pipeline/direct_driver/base.py src/app/pipeline/direct_driver/openai_chat_completions.py src/app/pipeline/exceptions.py src/app/pipeline/retry.py src/app/pipeline/rate_limiting.py tests/unit/pipeline/test_response_handoff.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/test_prompt_admission_driver.py tests/unit/pipeline/test_rate_limiting.py tests/unit/pipeline/test_timeout_enforcement.py`

Run: `uv run pyright src/app/pipeline/request.py src/app/pipeline/response_handoff.py src/app/pipeline/driver.py src/app/pipeline/direct_driver/base.py src/app/pipeline/direct_driver/openai_chat_completions.py src/app/pipeline/exceptions.py src/app/pipeline/retry.py src/app/pipeline/rate_limiting.py tests/unit/pipeline/test_response_handoff.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/test_prompt_admission_driver.py tests/unit/pipeline/test_rate_limiting.py tests/unit/pipeline/test_timeout_enforcement.py`

Expected: pytest pass；Ruff clean；Pyright 0 errors。

- [ ] **Step 8: Review and commit the driver seam.**

Review question: Is there exactly oneledger consumer，does thedependency-leaf handoff avoid`pipeline.driver ↔ direct_driver`cycles，doeshook failure closeexactlyonce，and doesdeferred finalization preserveordinaryretry semantics？Commit message: `refactor: add pre-success response completion seam`。

---

### Task 5: Provider content transparency and non-stream Chat adaptation

**Files:**
- Modify: `src/app/model_provider/codebuddy.py`
- Modify: `src/app/model_provider/codebuddy_client/client.py`
- Modify: `src/app/model_provider/xingchen/client.py`
- Modify: `src/app/pipeline/direct_driver/openai_chat_completions.py`
- Modify: `src/app/pipeline/driver.py`
- Modify: `src/app/server/routes/inference.py`
- Test: `tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`
- Test: `tests/unit/model_provider/xingchen/test_client.py`
- Create: `tests/unit/pipeline/test_openai_chat_completions_driver.py`
- Test: `tests/int/test_xingchen_provider.py`
- Create: `tests/int/test_codebuddy_provider.py`

**Interfaces:**
- Consumes Tasks1–4 capability、state、collector anddriver hook。
- Produces completepre-success adaptation andcontent-transparent provider clients。
- Produces server-readable`ResponseHandoff`withraw／projection slots。

- [ ] **Step 1: Implement capability-to-send-plan and payload defaults in the Chat driver.**

Use theSpec§9.3 four-row matrix。Forclientnon-stream＋streaming-only，setplan`upstream_stream=True`whileleaving`RequestContext.stream=False`。Set`Attempt.payload["stream"] = plan.upstream_stream`for everyChat attempt，includingwhenclient omittedthe field；pass thesame`plan.upstream_stream`to`ModelProvider.send(stream=...)`soJSON body andtransport mode cannot diverge。Apply`stream_options.include_usage`and`tool_stream`only whenupstream streaming andkey absent；copy nestedmapping before`setdefault`；explicitfalse／nonmapping value remains unchanged。Writefinal mapping only to`Attempt.payload`。

Forclientstreaming＋non-stream-only，raise`ResponseModeNotSupported`beforeprovider send。Forclientstreaming＋streaming-capable，override`_defer_success_until_body()`totrue soinitialheaders returnattempt＋request finalizers rather thanpublishinglimiter／attempt／request success；preparedreplacement returnsattempt finalizer only。Never branch onprovider name。

- [ ] **Step 2: Implement successful and failing non-stream adaptation in `_complete_response()`.**

Ifplan does not needadaptation，returnraw handoff unchanged。Ifadaptation isrequired，consume`lease.stream()`throughfresh`UpstreamSource`andthe sameidle／attempt accounting layers owned bytheattempt，run`BufferedAttemptCollector`withfresh`ChatAttemptState`，and apply`ChatAttemptDecision`：

- `COMMIT`：buildstandardmulti-choice JSON bytes andimmutable`ChatAttemptSnapshot`fromthe samefrozenstate，close thelease，thenreturn`ResponseHandoff(response=None, raw_exchange=..., client_projection=..., chat_snapshot=...)`；Task7 onlyprojects thissnapshot andmust notreparseprojection bytes。
- `RETRY`：raise typed event/transport error withtheexplicit reason；markhook asprepared-reusable。
- `FAIL`：raise thetypedunterminated／unassemblable／unknown error used byerror-envelope；do notreturnsynthetic success。

Capture rawheaders／HTTP version／connection beforeclosingraw response。Close exactlyonce throughcollector。

- [ ] **Step 3: Make provider clients content-transparent.**

CodeBuddy：remove`body["stream"] = True`、stream defaults and`aggregate_stream()`；add`extra_headers`parameter and pass it through`CodebuddyProvider.send()`toexistingowned-header merge；callhttp client withpipeline-providedmode andreturnraw response。Xingchen：remove`_prepare_payload()`defaulting，serialize/sign theexactpipeline mapping once andsend withprovidedmode。GitHub remainsunchanged asneutral control。

- [ ] **Step 4: Teach server handoff to use raw facts and client projection separately.**

Foradapted success，allow`HandledRequest`success with`handoff.response is None`only whenbothraw snapshot andclient projection arepresent；trace upstream request/response bytes、protocol、connection andsemantic headers fromraw snapshot，thenconstructanordinaryStarlette`Response`fromthealready serializedprojection bytes/status/content type/headers without calling`response.json()`or`JSONResponse`onclosedSSE response。Anyotherresponse-none success isaninvariant error。Native non-stream andallstreaming paths preserveexistinglive-response handoff。Do not publishChat observation yet；Task7 ownsprojection。

- [ ] **Step 5: Run existing provider and endpoint probes before adding new tests.**

Run: `uv run pytest tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/xingchen/test_client.py tests/int/test_xingchen_provider.py -q`

Run: `uv run pytest tests/int/test_pipeline_app.py::test_chat_completions_endpoint_is_served tests/int/test_pipeline_app.py::test_chat_completions_streams_are_delivered_whole_and_verbatim -q`

Expected changes：oldCodeBuddy“always streams”andprovider aggregation assertions must be replaced，not silently retained；Xingchen outwardrequest remains byte/signature-equivalent afterdefaults move toChat driver。Bothcommands must collectatleastonecase；zero collection isacommand defect，notpass。

- [ ] **Step 6: Add provider-boundary and Chat driver tests.**

Provider tests assertpassedpayload/mode/raw response/extra headers exactly；they do not claimrealcapability。Chat driver tests coverallfourmode rows、defaults/explicit values、native JSON control、standardmulti-choice success、unassemblable、unknown/malformed error、raw metadata andsingleclose。For everymatrix row，decode theactual serializedrequest bytes and assertits`stream`value equals theprovider`stream=`argument；forbody-phase retry assertbothactual JSON payloads arebyte-identical。UseOpenAI SDK accumulator as independent oracle only fortypedstandardpositive sample，then assertproject-specificunknown/conflict rules separately。

Addprovider-transparency controls throughthesame component entry：mutateCodeBuddy client toforce`stream=True`orinject`stream_options`，andmutateXingchen client toinject`tool_stream`；theexactserialized payload／provider`stream`assertion must failwhileauth/signing setup remainsvalid。This provesprovider ownership，notupstream support。

Adderror-carrier full-object controls：nested object、event-name flat object、flat`type:error`andmalformedraw eachassert exactHTTPstatus、exactJSON object andexplicit absenceofproxy fallbackfields whenupstreamfields areunderstood。Droponeunknownfield oradd`upstream_error`toanunderstoodcarrier as thesingle mutation；thefull-object/absence assertion must failatthatfield。

Addraw-vs-synthetic accounting control：constructraw SSEandsynthetic JSON withdistinct lengths；mutatehandoff tocopyprojection length intoraw exchange snapshot，andasserttheupstream-byte field fails whileclientbody remainscorrect。

Addthe full event-rate-limit path：HTTP 200 SSE carrier→typedrate-limit→limiterLIMITED→defaultwait→secondattempt success，withcalls=2、serverError spent=1、rawstatus still200。The single-variable control bypasses`observe_event_rate_limit()`and must failmode/wait whilethe finalresponse would otherwise staygreen。

Addpre-success client-deadline reuse：attempt1 consumespart ofone fixeddeadline andtriggersbody retry；attempt2 hangs beyondremainingtime。Assertoneunchangeddeadline instant、timeout beforea recomputeddeadline wouldallow success、calls/ledger exact。Control recomputesdeadline perattempt and must failelapsed/outcome assertions。

- [ ] **Step 7: Add production-entry mock integration for Xingchen and CodeBuddy.**

Xingchen：realcomposition＋MockTransport assertsdefaults appliedbeforeexact signing andnative non-stream unchanged。CodeBuddy：realcomposition＋MockTransport assertsclientnon-stream→upstreamstreaming、firstbody tear→secondsuccess、calls=2、client receivesJSON、extra headers survive。Addevent-rate-limit andfixedclient-deadline cases throughthis sameproduction entry，not onlydirectdriver unit tests。Docstrings must sayfake provesproxy wiring，notP6／realprovider behavior。

- [ ] **Step 8: Run task verification.**

Run: `uv run pytest tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/xingchen/test_client.py tests/unit/pipeline/test_openai_chat_completions_driver.py tests/int/test_xingchen_provider.py tests/int/test_codebuddy_provider.py -q`

Run: `uv run pytest tests/int/test_pipeline_app.py::test_chat_completions_endpoint_is_served tests/int/test_pipeline_app.py::test_chat_completions_streams_are_delivered_whole_and_verbatim -q`

Run: `uv run ruff check src/app/model_provider/codebuddy.py src/app/model_provider/codebuddy_client/client.py src/app/model_provider/xingchen/client.py src/app/pipeline/direct_driver/openai_chat_completions.py src/app/pipeline/driver.py src/app/server/routes/inference.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/xingchen/test_client.py tests/unit/pipeline/test_openai_chat_completions_driver.py tests/int/test_xingchen_provider.py tests/int/test_codebuddy_provider.py`

Run: `uv run pyright src/app/model_provider/codebuddy.py src/app/model_provider/codebuddy_client/client.py src/app/model_provider/xingchen/client.py src/app/pipeline/direct_driver/openai_chat_completions.py src/app/pipeline/driver.py src/app/server/routes/inference.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/xingchen/test_client.py tests/unit/pipeline/test_openai_chat_completions_driver.py tests/int/test_xingchen_provider.py tests/int/test_codebuddy_provider.py`

Expected: pytest selectsat leastonecase fromeachnamedfile andpasses；Ruff clean；Pyright 0 errors。Confirmraw SSE bytecount differs intentionally fromsyntheticJSON length in atleastoneintegration case andlands in theright fields。

- [ ] **Step 9: Review and commit the provider/adaptation slice.**

Review question: Areproviders content-transparent，isclient mode preserved，and cananysynthetic response overwrite rawexchange facts？Commit message: `feat: adapt buffered Chat responses in pipeline`。

---

### Task 6: Post-header transactional delivery for direct streaming Chat

**Files:**
- Modify: `src/app/pipeline/delivery/buffered_transaction.py`
- Modify: `src/app/pipeline/delivery/stream.py`
- Modify: `src/app/server/routes/inference.py`
- Modify: `src/app/pipeline/request.py`
- Modify: `src/app/observability/request_completion.py`
- Create: `tests/unit/pipeline/delivery/test_buffered_transaction.py`
- Modify/Test: `tests/unit/pipeline/delivery/test_one_shot_delivery.py`
- Modify/Test: `tests/int/test_pipeline_app.py`

**Interfaces:**
- Produces `BufferedCandidate`、`SelectedBufferedCandidate`、`BufferedReplaySupport`、`buffered_transaction_delivery(..., on_selected)`。
- Consumes collector/state、`PendingAttemptFinalizer`、theinitial`PendingRequestFinalizer`andexisting`replay_prepared()`／`RetryLedger`。
- Producesoneexplicitselected-candidate callback forTask7 observation promotion；Task7 does not read`context.current_attempt`or syntheticbody。

- [ ] **Step 1: Implement candidate, selection, and runner records.**

```python
@dataclass(slots=True)
class BufferedCandidate:
    chunks: AsyncIterator[bytes]
    upstream: UpstreamSource
    state: ChatAttemptState
    finalizer: PendingAttemptFinalizer
    attempt_index: int


@dataclass(frozen=True, slots=True)
class OpenedBufferedCandidate:
    candidate: BufferedCandidate


@dataclass(frozen=True, slots=True)
class BufferedReplacementFailed:
    error: BaseException
    attempt_index: int


@dataclass(frozen=True, slots=True)
class BufferedReopenRefused:
    error: BaseException


type BufferedReopenOutcome = (
    OpenedBufferedCandidate | BufferedReplacementFailed | BufferedReopenRefused
)


@dataclass(frozen=True, slots=True)
class SelectedBufferedCandidate:
    attempt_index: int
    chat_snapshot: ChatAttemptSnapshot
    tail_ending: str | None
    replacement_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BufferedReplaySupport:
    ledger: RetryLedger
    reopen: Callable[[BaseException], Awaitable[BufferedReopenOutcome]]
    draining: Callable[[], bool]
    request_finalizer: PendingRequestFinalizer
```

Runner accepts a`decide(result)`strategy andinterprets`COMMIT／RETRY／FAIL`。It is theonlypost-headerledger owner；collector remainsbudget-free。`on_selected(SelectedBufferedCandidate)`is invokedexactlyonce afterfinalcandidate/fallback ischosen andbeforefinalbody yield；thecallback carriesimmutablefacts，notlive state。Reopen nevercompressesfailure/refusal to`None`。

- [ ] **Step 2: Implement keepalive-aware candidate collection and replacement.**

Reuse/extracttheexistinglast-client-write scheduler；upstreamchunks must not resetclient keepalive。Yield`PING_FRAME`withoutsemantic commit。Onpre-terminal`RETRY`，firstcallcandidate.finalizer`failed(error)`exactlyonce，thencheckdraining／ledger。Ifbudget rejects，callrequest finalizer`failed(error)`once andchoosecurrent final carrier。Ifretry isfunded，calltypedpreparedreopen whilekeepingoldcandidate state/body forfallback。

Handleevery`BufferedReopenOutcome`explicitly：`OpenedBufferedCandidate`atomically switchescandidate andonlythen releasesoldstate；`BufferedReplacementFailed`retainsoldcandidate forfallback，recordsreplacement error identity/origin/attempt index，andcallsrequest finalizer`failed(replacement.error)`once；`BufferedReopenRefused`retainsoldcandidate，recordslocal refusal andcallsrequest finalizer`failed(refusal.error)`once。Replacement drivers runwithdeferredrequest terminal，so noneofthese branches hasalready publishedrequest failure。No finalizer method spendsledger。

On`COMMIT`，firstcall`on_selected`withtheimmutablewinner/fallback snapshot，thenyieldthe finalbody。Onlywhenasync-generator control resumes aftertheASGI sendreturns callcandidate attempt finalizer`succeed()`andtheoneouterrequest finalizer`succeed()`exactlyonce；this is theonlypoint thatcallsrate-limiter success andpublishesattempt/request success fordirectstreaming。Ifsendraises/cancels atyield，callboth`cancelled(error)`andnevercall`succeed()`。`on_selected`receivesoldcandidate snapshot plusreplacement failure whenfallback wins，neverreconstructs itfrom`context.current_attempt`。

- [ ] **Step 3: Implement post-`[DONE]` tail precedence and final commit.**

Freeze state atfirst`[DONE]`，continue raw collection。CleanEOF／transport／idle／attempt/client deadline／tailcap/localtailfailure chooseCOMMIT accordingSpec；latersemantic frames remainraw only。Cancellation／downstream failurecallsactivecandidate.finalizer`cancelled(error)`andrequest finalizer`cancelled(error)`thenpropagates withoutwrite。Callcompletion offer beforeyielding finalbody，but markaccepted only afterASGI sendreturns through existingtracked delivery。

- [ ] **Step 4: Extract prepared reopen source construction from `inference.py`.**

Create a helper that accepts route、frozenpayload、reusedadmission、clientdeadline context and returns a typed`OpenedBufferedCandidate`／`BufferedReplacementFailed`／`BufferedReopenRefused` outcome。It calls`replay_prepared(..., defer_request_terminal=True)`forChat，preservesexactreplacement error/attempt index，andwraps successfulhandoff asguardedcounted`UpstreamSource`＋pendingattempt finalizer＋freshstate。Forblock paths，keepits existingoutcome/candidate projection rule；shareonlyprepared response/source construction。Do not changeResponses candidate/observation lifecycle orcompressanyfailure/refusal to`None`。

- [ ] **Step 5: Wire the `framer is None` Chat branch.**

Replace`one_shot_delivery()`only fordirectChat streaming；keep genericone-shot primitive foranyothercaller untilsearch provesnone。Preserve `_AccountedStreamingResponse`owner、`_tracked_delivery()`、rawbyte accounting、disconnect andcleanup order。Adda terminal-only accounting result instead of fake`BlockAssembler`。

- [ ] **Step 6: Run the complete direct streaming path manually through the test app.**

Use existing`make_client()`withliteralSSE bytes：singlecompleteattempt、firsttear/secondcomplete、post-DONE hang toclient deadline。Inspectresponsebytes、seenrequests、completionline andrecord。This is a localproxy probe，notrealupstream validation。

- [ ] **Step 7: Add runner unit tests and migrate obsolete one-shot assertions.**

Covercandidate replacement、singleledger spend、fallback preservation、winner exclusivity、keepalive clock、preterminalcap、fullpost-terminal matrix、cancel、cleanup andsend frontier。Theold“anyexception yields partial first”test must move toexplicitpreterminalfinal-fallback case；do not simply delete theonlynegative assertion。

Addfixedclient-deadline-across-replay case：attempt1 consumespart ofthedeadline thenreplays；attempt2 hangs。Assertbothcandidate wrappers receiveoneidenticalabsolute instant andthe request endsatthatinstant。Single-variable control recomputesthedeadline in`_reopen()`and must failtheelapsed/calls/finalbody assertion。Addpost-headerevent-rate-limit case：firstHTTP 200 stream reportsrate limit，limiter entersLIMITED，nextcandidate waitsdefaultinterval，ledger spendsoneSERVER_ERROR andrawstatus remains200；control omits event signal and must failmode/wait。

Addpending-finalizer lifecycle cases。InitialChat attempt thatfailsbeforeheaders nevercreatesrequest finalizer andtheoriginaldriver publishesexactlyone request failure。Initialstreaming handoff createsoneouterrequest finalizer；a successfulreplacement createsno secondrequest finalizer。FromRECOVERING mode，afterheaders/handoff butbeforebody pull assertlimiterstillRECOVERING andsuccess eventsabsent；aftercomplete`[DONE]`body butbeforefinalbody send-return，success remainsabsent；after send-return，assertoneattempt success、onerequest success andlimiterNORMAL。Ifdownstream sendraises/cancels，assertbothfinalizerscancelledonce andsuccessneverpublished。Tear/retrycandidate publishesattempt failed butnever success；terminalfailure publishesrequest failed once。

Addreplacement-pre-header failure case throughthesame runner entry：initialcandidate hasdistinctsnapshot/body，replacement attempt beginsbutfailsbeforeheaders withadistinctexception。Assertreopen returns`BufferedReplacementFailed`withthat exacterror identity/origin/index，finalbody andChat snapshot comefrominitialcandidate，replacement failure isrecorded，andwhole request publishesexactlyone terminal event。Single-variable controls compress outcome to`None`、createasecondrequest finalizer orletreplacement driver publishrequest failure；error identity／snapshot／finalizer-count／event-count assertions must fail。Another control restoresheaders-stage success and must failthepre-body RECOVERING/event assertions。

Critical controls：spendledger incollector andassertspent/calls fail；clearoldcandidate at`begin_attempt`andassertfallback fails；resetkeepalive onupstreamchunk andassertmissingping；allowpost-DONE error tochangefacts andassertsnapshot fails；appendtailbeforecapcheck andassertpeak/body fails。

- [ ] **Step 8: Add production-entry integration tests.**

Add production tests named `test_direct_chat_buffered_stream_replays_before_commit`、`test_direct_chat_failed_replacement_uses_previous_candidate`、`test_direct_chat_replay_keeps_original_client_deadline`、`test_direct_chat_event_rate_limit_waits_before_replay`、`test_direct_chat_post_done_client_deadline_commits_complete_body` and `test_direct_chat_post_done_cap_rejects_tail_in_same_chunk`。Use rawliteralattempt markers。Assertdiscardedmarker zero occurrences、winner exactlyonce、exactwinner bytes、calls/attempts/ledger/replaced failures、clientdeadline tail success、cap behavior、draining no spend andresponse close。Thefailed-replacement case assertsoldcandidate body/snapshot，distinctreplacement error identity/origin/index andexactlyonerequest terminal event；controls collapseoutcome to`None`orallowinnerdriver terminal event。Thepreterminal two-candidate case usescombined delays exceedingclient deadline whileeachindividual delay doesnot，so resettingdeadline wouldincorrectlysucceed；theevent-rate-limit case usesfake clock mode/wait assertions。Expected bytes must not begenerated byproductSSEencoder。

- [ ] **Step 9: Run task verification.**

Run: `uv run pytest tests/unit/pipeline/delivery/test_buffered_attempt_collector.py tests/unit/pipeline/delivery/test_buffered_transaction.py tests/unit/pipeline/delivery/test_one_shot_delivery.py -q`

Run: `uv run pytest tests/int/test_pipeline_app.py -k 'direct_chat' -q`

Run: `uv run ruff check src/app/pipeline/delivery/buffered_transaction.py src/app/pipeline/delivery/stream.py src/app/server/routes/inference.py src/app/pipeline/request.py src/app/observability/request_completion.py tests/unit/pipeline/delivery/test_buffered_transaction.py tests/unit/pipeline/delivery/test_one_shot_delivery.py tests/int/test_pipeline_app.py`

Run: `uv run pyright src/app/pipeline/delivery/buffered_transaction.py src/app/pipeline/delivery/stream.py src/app/server/routes/inference.py src/app/pipeline/request.py src/app/observability/request_completion.py tests/unit/pipeline/delivery/test_buffered_transaction.py tests/unit/pipeline/delivery/test_one_shot_delivery.py tests/int/test_pipeline_app.py`

Expected: pytest selectsat leastoneChat/buffered/replay case andpasses；Ruff clean；Pyright 0 errors。

- [ ] **Step 10: Review and commit the post-header delivery slice.**

Review question: Does any comment or partialattempt close replay，and can a failedreplacement erase the actualfallbackcandidate？Commit message: `feat: replay buffered Chat streams before commit`。

---

### Task 7: Final-candidate Chat observation, durable schema, and console projection

**Files:**
- Modify: `src/app/pipeline/response_observation.py`
- Modify: `src/app/pipeline/request.py`
- Create: `src/app/pipeline/chat_completions/observation.py`
- Modify: `src/app/server/routes/inference.py`
- Modify: `src/app/observability/request_trace.py`
- Modify: `src/app/observability/request_completion.py`
- Modify: `src/app/observability/request_log.py`
- Test: `tests/unit/pipeline/test_response_observation.py`
- Create: `tests/unit/observability/test_chat_response_observation.py`
- Modify/Test: `tests/unit/observability/test_response_observation_projection.py`
- Modify/Test: `tests/unit/observability/test_request_completion.py`
- Modify/Test: `tests/unit/observability/test_request_log.py`
- Modify/Test: `tests/int/test_pipeline_app.py`

**Interfaces:**
- Produces immutable `ChatResponseObservation`、`ChatChoiceObservation`、`ChatToolCallObservation` and`ResponseObservation.chat`。
- Produces explicit`publish_response_observation(context, trace, snapshot)`forselectedcandidate。
- ConsumesTask2`ChatAttemptState.observation_facts()`fromstreaming、adaptednon-stream andnativewhole-body reader。

- [ ] **Step 1: Implement the exact Chat observation DTOs.**

ModelTUI Spec字段exactly：`done_seen`、`tail_ending`／detail、choices、stream error、top-levelunknown；choiceindex／finishreason／reasoning／tools／unknown；toolindex／id／type／name／arguments／unknown。Useexisting`JsonObservation`five-state semantics、`FrozenJson*`、`UsageObservation`andbounded`ObservationIssue`。Observedemptychoices is`()`, unavailable is`None`。

- [ ] **Step 2: Implement projection from Chat state and native non-stream JSON.**

Streaming/adapted pathsprojectthefinal`ChatAttemptState`withoutreparsingclient projection。Native non-stream usesa whole-body reader thatproduces thesameDTO；`done_seen=None`becauseSSE sentinel isnotapplicable。Malformedbody observation becomesissues andunavailable fields butdoesnotalterdelivery。

- [ ] **Step 3: Implement explicit candidate publication.**

KeepResponses current-attempt observer behavior unchanged。Adda narrowpublisher takinganexplicit`ResponseObservation`。Mode-adapted non-stream reads`ResponseHandoff.chat_snapshot`；post-header runner invokes`on_selected(SelectedBufferedCandidate)`withwinner/fallback snapshot；native non-stream whole-body reader returnsits ownsnapshot。Task7 projects onlytheseexplicit values。Failedreplacement recordsitsfailure separately。Remove anyChat path thatimplicitlyreads`context.current_attempt`atsettle time orreparsestheclient projection。

- [ ] **Step 4: Extend trace, finalized schema v2, and legacy projection.**

`RequestTrace.absorb_response()`addsChatbranch forlegacyusage、minimum-choicefinish/tools/reasoning anddialect，while richrendering remainsauthority。`_response_dict()`writesindependent`chat`payload andkeepsResponses-specific slotsnot-applicable/null perSpec。Serializealltyped objects toJSON values beforewriter；no`default=str`。

- [ ] **Step 5: Implement exact console rendering.**

Dispatch`format_response_observation()`by`source_protocol`。ForChat：renderminimumchoicefinishreason withclosedcolors；`reason(txt:1)`；`tool_calls(Bash,?,Bash)`or`called(Bash,?,Bash)`；`choices=N`；yellow`tail(<code>)`。Use`inert_token()`forprovider strings；unknownreason staysuncolored；unnamedcall is`?`andduplicatesremain。

- [ ] **Step 6: Run existing Responses observation/TUI tests before adding Chat tests.**

Run: `uv run pytest tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py -q`

Expected: Responses DTO、contextual green、serializer andformatter remainunchanged。

- [ ] **Step 7: Add complete-object Chat DTO/serializer/formatter tests.**

Usefull-object equality，explicit absence andorder assertions。Requiredsamples：twochoices inreverse arrival；choice0tools arrival2/0/1 withnamesBash/Bash/absent butschemaorder0/1/2；finish`tool_calls`exactconsole`tool_calls(Bash,?,Bash) choices=2`；finishabsentexact`called(Bash,?,Bash)`；explicitnullreasoning；unknownfinish withcontrol characters；invalidindexissues；tailclientdeadline exactsuffix。Negative controls：routeChat facts throughResponses slots；sortarrivalorder；dedupnames；dropunnamed；collapseabsent/null；readlegacyfields informatter。

- [ ] **Step 8: Add production-entry observation tests for all three paths.**

Directstreamingreplay：discardedattempt facts absent，winneronly。Native non-stream JSON：sameDTO with`done_seen=None`。Mode-adapted non-stream：state snapshot，notreparsedsyntheticbody。Captureactive store、JSONL andconsole；assertsharedidentity/tools/usage/tail andsurface-specific trimming。Fakeupstream disclaimer in eachtestdocstring。

- [ ] **Step 9: Run task verification.**

Run: `uv run pytest tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_chat_response_observation.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py -q`

Run: `uv run pytest tests/int/test_pipeline_app.py -k 'direct_chat' -q`

Run: `uv run ruff check src/app/pipeline/response_observation.py src/app/pipeline/request.py src/app/pipeline/chat_completions/observation.py src/app/server/routes/inference.py src/app/observability/request_trace.py src/app/observability/request_completion.py src/app/observability/request_log.py tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_chat_response_observation.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py`

Run: `uv run pyright src/app/pipeline/response_observation.py src/app/pipeline/request.py src/app/pipeline/chat_completions/observation.py src/app/server/routes/inference.py src/app/observability/request_trace.py src/app/observability/request_completion.py src/app/observability/request_log.py tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_chat_response_observation.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py`

Expected: pytest selectstheChat/observation/finalization cases andpasses；Ruff clean；Pyright 0 errors。This doesnot run`tests/tui/`because`src/app/observability/tui.py`is unchanged；if implementation touches thatfile，also run`uv run pytest tests/tui -q`perproject rule。

- [ ] **Step 10: Close the TUI implementation ledger and commit.**

Only afterproduction-entry tests pass，remove `.dev/docs/tui/deferred.md` item0 andupdate `.dev/docs/direct-buffered-chat-completions/status.md` withactualcommit/test facts；do not claimrealprovider shape。Persist`.dev`throughitsownbranch/worktree procedure。Source commit message: `feat: observe buffered Chat completions`。Dotdev commit message: `docs: record buffered Chat observation status`。

---

### Task 8: Merged-state integration, review, and delivery

**Files:**
- Modify/Test: `tests/int/test_pipeline_app.py`
- Modify/Test: `tests/int/test_codebuddy_provider.py`
- Modify/Test: `tests/int/test_xingchen_provider.py`
- Modify: `.dev/docs/direct-buffered-chat-completions/status.md`
- Modify: `.dev/docs/direct-buffered-chat-completions/plan.md`
- Modify as required by implementation evidence: living Spec revision records only whenfacts changed；do not rewrite behavior merely to matchbugs。

**Interfaces:**
- Consumes all prior tasks。
- Produces finalreviewedsource candidate、durable verification record andimplementation status。

- [ ] **Step 1: Run one merged-state production probe per client path.**

1. Native GitHub-style non-stream JSON control。
2. Capability-driven streaming→non-stream JSON success afteronebody retry。
3. Directstreaming firsttear→secondexactrawsuccess。
4. Directstreaming post-DONEclientdeadline→success＋tail note。
5. Unknownerror→singleattempt correctcarrier。

Recordcommands/results inplan status；do not callrealproviders。

- [ ] **Step 2: Complete discriminating integration assertions.**

Foradapted retry，assertcalls=2、ledger spent=1、prepare=1、admission admitted→reused、bothsentpayloadsexactequal、clientstreamfalse、upstreamstreamtrue、raw/syntheticbytecountseparate、finalobservationwinneronly。Forpost-header replay，assertdiscardedmarker0、winner1、exactbytes、keepalive doesnotcommit、failedreplacementfallback andpost-terminalmatrix。Eachnontrivial criterion includesonecorrectproduction sample andone single-variable defect control; verifyfailure occurs at thetarget assertion。

- [ ] **Step 3: Run targeted test groups in dependency order.**

Run:

```bash
uv run pytest \
  tests/unit/model_provider \
  tests/component/model_provider/codebuddy_client/test_codebuddy_client.py \
  tests/unit/pipeline/chat_completions \
  tests/unit/pipeline/delivery/test_buffered_attempt_collector.py \
  tests/unit/pipeline/delivery/test_buffered_transaction.py \
  tests/unit/pipeline/test_openai_chat_completions_driver.py \
  tests/unit/pipeline/test_response_handoff.py \
  tests/unit/pipeline/test_direct_driver.py \
  tests/unit/pipeline/test_prompt_admission_driver.py \
  tests/unit/pipeline/test_rate_limiting.py \
  tests/unit/pipeline/test_timeout_enforcement.py \
  tests/unit/pipeline/test_response_observation.py \
  tests/unit/observability/test_chat_response_observation.py \
  tests/unit/observability/test_response_observation_projection.py \
  tests/unit/observability/test_request_completion.py \
  tests/unit/observability/test_request_log.py \
  tests/int/test_codebuddy_provider.py \
  tests/int/test_xingchen_provider.py \
  tests/int/test_pipeline_app.py -q
```

Expected: pass。This broadtargeted run proveslocal merged behavior；it doesnotprove realprovider capability。

- [ ] **Step 4: Run repository static checks and full regression once.**

Run:

```bash
uv run ruff check src tests
uv run pyright src tests
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

Expected: Ruff clean；Pyright 0 errors；pytest pass andexistingcoverage floor met。Do not run`ruff format`。Ifsharedmainmoves inunrelatedpaths afterthis run，do not rerun merely to chaseHEAD；rerun only ifnewcommits touchthesecontracts／paths。

- [ ] **Step 5: Record evidence tiers without promoting an absent tier.**

Addthis exacttable to`status.md`withactual commands/results：

| Evidence tier | This implementation | It may not claim |
|---|---|---|
| Unit/component | Chat grammar、state、collector、driver/provider interfaces | Real provider shape、production fault provenance |
| MockTransport production entry | Real app/routing/driver/delivery/accounting/TUI wiring againstcontrolled bytes | CodeBuddy/Xingchen/Copilot actually emit thosebytes orsupport thatcapability |
| Historical cassette | **No Chat cassette used**；full suite may rununrelatedResponses cassettes | Chat shape orcurrent upstream behavior |
| Live/P6/canary | **Not executed** | Pass、compatibility confirmation、current real-account behavior |

If thefull suite reportsResponses cassette passes，recordthem onlyasunrelated regression evidence；do not listthem underthisfeature’sChat behavior。

- [ ] **Step 6: Request one merged-state independent code review.**

Load`my-skills:let-agent-review`。Reviewdimensions：Spec behavior、retry ownership、candidate lifecycle、raw/client accounting、cap/deadline/cleanup、provider boundary、schema/TUI、test discrimination。Reviewer writesreport under`.dev/docs/direct-buffered-chat-completions/reports/`；main session verifies eachfinding with`my-skills:checking-review-report`，recordsadopted/rejected reasons，andreruns onlyaffected evidence。

- [ ] **Step 7: Verify final tree and attribution.**

Checkexactsourcecommit stats andownedpaths；verifyactive`.dev`files matchtheirlocaldotdev commit；confirmmain source hasnopeer files inthisfeature commits；confirmno push andno`4141` control action occurred。Do not delete agent worktrees/reports untilsource commits arearchived perproject workflow。

- [ ] **Step 8: Update living status and close implementation tasks.**

Writeactualsourcecommit(s)、targeted/fullcheck results、review verdict andremainingdeferred D-1／D-2 into`status.md`。Removeonlycloseddeferreditems；do not removeP6 ortranslatedmulti-choice。Assesscloseout atthis boundary；load`my-skills:closing-out-work-at-a-boundary`if implementation is complete，orrecordthe observable blocker ifnot。

- [ ] **Step 9: Commit final evidence/status without reshaping source history.**

Source commit boundary isonlyifTask8 changesproduction/tests；otherwise do not createanempty“tests green”commit。Dotdev commit message: `docs: close buffered Chat implementation`。Neverpush withouta current explicit instruction。

---

## Plan Self-Review Checklist

- [x] Every normative requirement indesign §§3–13 maps toTasks1–8；capability→Task1，facts／aggregation→Task2，single-attempt collection→Task3，driver owner→Task4，non-stream adaptation→Task5，post-header replay→Task6，observation/TUI→Task7，merged acceptance/closeout→Task8。No behavior lives only inthisplan。
- [x] Every newtype name usedbylater tasks isintroduced inTasks1–4 andhasoneowner/lifetime；Task7 introducesonlyobservation DTOs consumedwithinTask7/8。
- [x] Provider clients neverinterpretcapability orChat content；pipeline neverbranches onprovider name。
- [x] Collector hasnoledger/reopen/event ownership；pre-success andpost-header ownerseachconsumea failureonce。
- [x] `Attempt.payload`is theonlyfinal payload authority；`ChatSendPlan`hasno payloadmapping。
- [x] Raw upstream exchange andclientprojection areseparate inhandoff/accounting。
- [x] `[DONE]`pre/post precedence、candidatepromotion anderrorcarrier exactly reference livingSpecs。
- [x] Criticalcriteria carrycorrectsample＋single-variable defectcontrol；fake/cassette/live evidence boundaries arestated。
- [x] No taskrequiresrealprovider、P6、canary、production`4141`ornewproofinfrastructure。
- [x] No `ruff format`、no push、no inline commit`-m`、no broad staging。
