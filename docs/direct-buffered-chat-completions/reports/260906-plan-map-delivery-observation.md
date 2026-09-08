# Direct buffered Chat Completions：delivery／observation 实施计划前置源码地图

日期：2026-09-06

调查范围：只覆盖 buffered collector、post-header delivery、response observation、TUI／JSONL 投影，以及这些路径直接依赖的 SSE parsing、replay、deadline、keepalive、buffer cap、accounting 和测试 harness。本文不修改源码、tests 或 living docs，也不展开 provider capability／provider boundary 的完整实施计划；这些内容只在它们构成当前 delivery 接口或迁移前置时出现。

权威输入：`CLAUDE.md`、`.claude/rules/00-development-workflow.md`、`.dev/docs/direct-buffered-chat-completions/design.md`、`.dev/docs/direct-buffered-chat-completions/decisions.md`、`.dev/docs/direct-passthrough/spec.md` §5.4／§9.3／§10、`.dev/docs/tui/spec.md` 的 Chat provider observation schema、`.dev/docs/error-envelope/spec.md` §8／§10.2。源码快照取自 2026-09-06 主工作树 `/home/xp/src/ghc-api-proxy-py` 的当前文件内容；本文的行号是该快照坐标。

## 1. 先给实施者的核心结论

1. 当前 direct Chat `stream:true` 已越过 `DirectDriver.run()` 的 success frontier，随后由 `inference._dispatch_after_body()` 选择 `framer is None` 分支，经过 `with_idle_timeout → with_deadline_at → _counted_upstream → with_client_deadline_at → one_shot_delivery → _tracked_delivery → _AccountedStreamingResponse`。`one_shot_delivery()`只累积字节并在 EOF 一次 yield；异常时先 yield partial 再重抛。它没有 SSE 完整性判断、`ReplaySupport`、keepalive、cap 或 candidate promotion。
2. 当前 block-aware 路径已经具备最接近目标的 post-header replay 骨架：`ReplaySupport`、request-scoped `RetryLedger`、`replay_prepared()`、局部 `_reopen()`、绝对 attempt/client deadline、idle guard、`UpstreamSource` 正向 provenance、`_counted_upstream()`、cleanup 排序、`_StreamAccounting` 和 ASGI send frontier。新 runner 应复用这些接口及其顺序，不应复制一套 retry、deadline 或 response owner。
3. 当前 SSE parser 只产出解码后的 `SseEvent(event, data)`，`iter_frames()`会删除 frame separator，`read_events()`还会把 EOF 剩余 tail 当 event 解析。它不能提供 raw frame 的完整字节、separator、全流 offset 或“error frame 截止位置”。新 Chat reader 不能只挂在现有 `SseEvent` 上；必须先补一层保留 raw bytes 与边界的 framing primitive，同时保持既有 `read_events()` 行为不回归。
4. 当前 `ChatCompletionsAssembler` 是 translated Chat→Anthropic 的 block assembler，不是 direct buffered transaction state。它把全部 choices 混到一个 `_text`／`_thinking`／`_tools` 状态，看到任一 choice 的 `finish_reason` 就令 `Terminal.seen=True`，bad tool index 会回落到 0，EOF `close()` 会把 draft 当可交付块冲出。它只能复用新的纯 Chat event decoding；不能充当 multi-choice aggregation、`[DONE]` 完整性或 final provider observation 的 authority。
5. 当前 provider observation 是 Responses-only：`Attempt.response_observer: ResponsesObserver | None`，`RequestContext.begin_attempt()`只为 `OPENAI_RESPONSES`建 observer，`ResponseObservation`没有 Chat 槽，`RequestTrace.absorb_response()`只投影 Responses，`request_completion._response_dict()`只序列化 Responses，`request_log.format_response_observation()`遇到非 Responses 直接返回空。Chat 实施必须打通这整条链，不能只加 reader 或 formatter。
6. 当前 `_absorb_response_observation(context, trace)`从 `context.current_attempt`取 snapshot。这对“replacement 一开始旧 observer 就作废”的现有 Responses replay成立，却与新设计的“replacement 建立成功前保留旧 candidate；replacement headers 失败时发布旧 fallback”冲突。Chat runner必须显式发布最终 candidate snapshot；不能让 request-level projection隐式追随 `current_attempt`。
7. 当前 `RateLimiter.observe_success()`在 response headers到达后、body 消费前执行。对 buffered Chat，HTTP 200 headers不能提前推进 limiter recovery；event rate limit还缺少独立入口。这个 seam虽然主要在 driver／provider slice落地，但 collector与 post-header runner必须返回足够的 typed verdict，让唯一 owner在 body verdict 后调用 limiter。
8. 测试应先实现生产行为，再新增高分辨率 unit／component／integration tests。`tests/int/test_pipeline_app.py` 的 `make_client()`已经是最合适的 production-entry mock upstream harness；它跑真实 ASGI app、真实 provider SDK client 和 `httpx2.MockTransport`。它证明本代理的接线、重试、wire、accounting、observation 与持久化，不证明真实 provider 会产生测试中构造的 shape。CodeBuddy `stream:false` capability仍是未运行 P6 的 compatibility 假设，不能被 fake 测试升级成真实 upstream 事实。

## 2. 规格压缩：本范围内必须守住的合同

### 2.1 Transaction 与 retry owner

- 两类 SSE-buffered transaction共享同一 Chat event reader、同一 `[DONE]` 完整性判据、同一 single-attempt collector和同一 request `RetryLedger`。
- Client `stream:false` 的 streaming-upstream adaptation在 response headers 尚未提交时由 `DirectDriver` attempt loop唯一重试；client `stream:true` 的 post-header body由 delivery runner唯一重试。
- 一个 failure只能由一个 owner消费 ledger。Collector只返回 facts／ending／verdict，不消费 ledger、不发布 attempt event、不打开replacement。
- Replacement response成功建立后才能原子替换 candidate；此前旧candidate保留作fallback。被成功替换的 attempt不能向客户端或最终 observation泄漏任何 semantic bytes／facts。

### 2.2 Raw、semantic 与 terminal

- Streaming Chat成功必须见第一条合法 `data: [DONE]`。`finish_reason`只是 native stop fact，不是完整性证明。
- Reader需要完整 raw SSE frame及其 attempt-buffer起止 offset。第一条 `[DONE]` 后冻结全部 semantic state，但继续收 raw tail。
- Direct `stream:true` 的最终成功 body逐字来自一个 attempt。Reader只能观察，不能重写 wire；不能拼接两轮。
- Pre-`[DONE]` transport tear、idle timeout、attempt deadline、clean EOF和已知瞬时流内 error按合同尝试 replay。Unknown／malformed／冲突 error不retry，并在 direct streaming最终 carrier中只保留到 error frame结束 offset。
- Post-`[DONE]` clean EOF提交全部 raw body；tear／idle／attempt deadline／client deadline停止 tail并提交已收 body；cap在越界前截尾；后续 semantic event不反转 success，也不污染 frozen observation。
- Client cancellation／downstream write failure没有读者，不提交 body。Local tail failure在 `[DONE]` 完整时仍可提交 body，但必须保留 operator-side failure事实。

### 2.3 Observation 与展示

- Chat provider observation属于 attempt draft；request-level最终值必须来自实际提交或 fallback交付的candidate。
- `ResponseObservation`增加独立 `chat` payload，不把Chat choice塞进Responses `status`／`output_items`。
- Durable schema保留全部合法 choices，按 `choice.index`排序；tools按 `tool.index`排序，重复与无名调用保留。Console只展开最小 choice，多个 choice追加 `choices=<n>`。
- Streaming `done_seen`为 bool；native non-stream JSON为 null。`tail_ending`只记录 post-terminal结束，不反转成功。
- Console精确词汇是 native finish reason、`reason(txt:1)`、`tool_calls(Bash,?,Bash)`／`called(Bash,?,Bash)`、`choices=<n>`和可选 `tail(<code>)`。Unknown finish reason经 `inert_token()`保留且不着色。

## 3. 当前生产调用顺序

### 3.1 Direct Chat `stream:true` 当前顺序

入口是 `src/app/server/routes/inference.py::_dispatch_after_body(request, chain, trace, completion, *, client_deadline_at)`。

1. `build_context()`建立 `RequestContext.stream=True`。
2. `handle_bounded()`进入 `driver.handle()`／`_drive()`，`DirectDriver.run()`建立 attempt、发布 `attempt.prepare`、admission、limiter acquire、provider send，拿到 response headers后立即执行 limiter header verdict，再发布 `attempt.succeeded`和`request.succeeded`。
3. 回到 `_dispatch_after_body()`，`framer_for()`因 inbound Chat 返回 `None`。
4. 进入 one-shot 分支，建立 `_StreamAccounting(assembler=None)`。
5. Body iterator从内到外为：`response.aiter_bytes()` → `with_idle_timeout(..., timeout_seconds=stream_idle_seconds(chain))` → `with_deadline_at(..., deadline_at=attempt.deadline_at)` → `_counted_upstream(..., attempt=context.attempt_count)` → `with_client_deadline_at(..., deadline_at=client_deadline_at)` → `one_shot_delivery(..., on_complete=completion_delivery.offer)` → `_tracked_delivery(..., accounting)`。
6. `_AccountedStreamingResponse`负责 ASGI response start/body send、disconnect、content/response cleanup、`accounting.settle()`与最终 `completion.publish()`。
7. `one_shot_delivery()`正常 EOF时调用 `on_complete()`并 yield一个完整 `bytes(body)`；异常时若已有bytes则先yield partial，再原样raise。`_tracked_delivery()`只在完整 one-shot offer对应的 chunk send返回后把 `completion_delivery`标为accepted。

这里的关键 frontier是：headers已提交，但 raw body尚未语义提交。新 runner替换第5步里的 `one_shot_delivery()`，保留第1～4与第6～7步的 response owner和 ASGI send accounting。

### 3.2 Block-aware post-header replay当前顺序，可直接借鉴

同一函数的 `framer is not None` 分支先建立 `UpstreamSource(with_deadline_at(with_idle_timeout(response.aiter_bytes(), ...), ...))`，再建立 assembler、buffer、accounting和局部 `_reopen()`，最后调用：

```python
stream_delivery(
    with_client_deadline_at(
        _counted_upstream(upstream_side, chain, trace.request_id, trace, attempt=context.attempt_count),
        deadline_at=client_deadline_at,
    ),
    assembler,
    upstream=upstream_side,
    buffer=delivery_buffer(chain),
    settings=settings,
    framer=framer,
    replay=ReplaySupport(ledger=ledger_for(context, chain), eligible=replay_reason, reopen=_reopen),
    continuation=continuation,
    on_tear_after_terminal=accounting.note_tear_after_terminal,
    on_runtime_failure=accounting.note_runtime_failure,
    observe_event=_observe_response_event,
    passthrough=not context.translation_required,
)
```

`stream_delivery()`包装 `_deliver()`并只在 downstream send返回后更新 `_LastWrite.at`。`_deliver()`使用 `_events_with_ping()`并在语义bytes尚未提交时调用 `decide_stream_ending()`；若 verdict为 `REPLAY`，调用 `ReplaySupport.reopen()`，成功后同时替换 `chunks／upstream／assembler／buffer`，重建 `DeliverySession`，从而丢弃旧 attempt draft。

局部 `_reopen(replacing: Exception) -> Attempt | None` 的顺序是：先拒绝 draining；断言 captured `replay_payload`与`replay_admission`；调用 `replay_prepared()`；依据 `context.attempt_count`更新 trace attempt和replaced failure；若 replacement response存在且仍streaming，则建立 fresh assembler和 fresh `UpstreamSource`，并返回带同一个绝对 client deadline、fresh attempt deadline、fresh byte counter与fresh buffer的 tuple。

新 buffered transaction runner应复用这套 reopen callback形态，但不能直接复用 block commit predicates：Chat terminal-only transaction在 `[DONE]`前即便已发keepalive也未提交 semantic body，而 block-aware `_deliver()`把实际 block send作为frontier。

### 3.3 Client `stream:false` 当前顺序及迁移边界

Direct driver把 `context.stream`直接传给 provider。GitHub Copilot和Xingchen可按该mode发送；CodeBuddy provider内部无条件改成 upstream `stream:true`，并在 `CodebuddyClient.aggregate_stream()`消费SSE、合成新的 `httpx2.Response`。因此 driver在 provider返回前已经失去 raw response身份，body tear发生在 provider内部且没有进入 shared driver retry语义；clean EOF无 `[DONE]`仍会生成成功，identity／created／model可由本地随机值、当前时钟和 `unknown`补齐。

本范围内需要给计划标明的迁移边界是：shared collector及Chat state应在 pipeline层可由 Chat driver body phase调用；collector返回 raw exchange facts和独立 client projection，不能再用 synthetic `httpx2.Response`冒充 upstream exchange。具体 provider capability建模及payload default迁移属于相邻实施切片，不在本文展开。

## 4. 精确源码地图与当前签名

### 4.1 SSE parsing 与 raw frame边界

文件：`src/app/pipeline/delivery/sse_source.py`。

```python
@dataclass(frozen=True, slots=True)
class SseEvent:
    event: str
    data: str

    def json(self) -> dict[str, Any]: ...


def parse_frame(raw: bytes) -> SseEvent | None: ...

def iter_frames(buffer: bytearray) -> Iterator[bytes]: ...
def encode_frame(event: str, data: str) -> bytes: ...

async def read_events(chunks: AsyncIterator[bytes]) -> AsyncIterator[SseEvent]: ...
```

当前行为：`_FRAME_SEPARATOR`支持 CRLF／LF／bare CR及混合空行；`parse_frame()`支持multi-line `data:`并用 `\n`连接；comment被忽略；UTF-8错误替换；`SseEvent.json()`对malformed或non-object统一返回 `{}`；`iter_frames()`返回separator之前的frame body并从buffer删除整个frame＋separator；`read_events()`在EOF时对任何非空tail调用 `parse_frame()`。

对新设计的缺口：

- `SseEvent`没有raw bytes、frame separator、start/end offset或ordinal。
- `{}`无法区分合法空object、malformed JSON与non-object JSON，无法实现明确error carrier优先、malformed error终局、unreadable observation和标准aggregation失败路径。
- `iter_frames()`丢掉separator，不能从event重构原始frame；`encode_frame()`只能生成语义等价SSE，不是原字节。
- `read_events()`的EOF-tail兼容行为不能自动等价为“完整raw frame”。Buffered transaction需要明确区分完整frame、unterminated tail与raw bytes保留策略。

建议保留现有接口给所有既有 assembler，并在同文件增加底层 raw primitive，例如：

```python
@dataclass(frozen=True, slots=True)
class RawSseFrame:
    raw: bytes
    body: bytes
    start: int
    end: int
    terminated: bool

async def read_raw_frames(chunks: AsyncIterator[bytes], *, cap_bytes: int = 0) -> AsyncIterator[RawSseFrame]: ...
```

这里的 `raw`必须包含原separator，`start/end`以attempt raw stream为坐标且采用半开区间 `[start, end)`；`terminated=False`只用于EOF剩余tail，不应悄悄升级为合法terminal frame。`parse_frame(frame.body)`可继续供Chat reader复用，但Chat reader必须另用严格JSON decoder区分 malformed／non-object／empty object。实际命名可以调整，语义不能退化。

Cap必须同时约束已提交到candidate raw buffer的bytes和raw reader为未闭合frame暂存的bytes。否则一个永不结束的单帧可以在“append完整frame前检查”这一句看似正确的实现下无限占内存。正确顺序是先计算新增chunk会令“raw buffer＋partial frame staging”达到多少，绝不让持有量超过cap；只有完整frame出现时才产生frame boundary与semantic facts。若首个 `[DONE]` frame自身跨cap，仍按pre-terminal cap失败，不能为了验证内容先超限持有。

### 4.2 当前 one-shot delivery

文件：`src/app/pipeline/delivery/stream.py:295-320`。

```python
async def one_shot_delivery(
    chunks: AsyncIterator[bytes], *, on_complete: Callable[[], None] | None = None
) -> AsyncGenerator[bytes]: ...
```

状态只有局部 `bytearray body`。正常EOF：如果body非空或提供了`on_complete`，先调用callback再yield完整body。普通`Exception`：若body非空先yield partial，再raise。`CancelledError`和`GeneratorExit`不进入except。它不解析SSE、不看`[DONE]`、不设cap、不发keepalive、不retry，也不区分pre/post-terminal failure。

建议不要在这个函数里逐项堆参数。新增 `BufferedTransactionRunner`后，保留 `one_shot_delivery()`作为无协议one-shot primitive或在无其它调用者时删除；direct Chat production入口改调用runner。Runner应由明确的candidate／collector records驱动，不应长成带十几个bool callback的函数。

### 4.3 Replay、source provenance 与 reopen

文件：`src/app/pipeline/delivery/stream.py`。

```python
class UpstreamSource:
    def __init__(self, source: AsyncIterator[bytes]) -> None: ...
    def __aiter__(self) -> AsyncIterator[bytes]: ...
    async def __anext__(self) -> bytes: ...
    def tear_is_unmodified(self, error: Exception) -> bool: ...
    async def aclose(self) -> None: ...

Attempt = tuple[AsyncIterator[bytes], UpstreamSource, BlockAssembler[Any], BlockBuffer[Any]]

@dataclass(frozen=True, slots=True)
class ReplaySupport:
    ledger: RetryLedger
    eligible: Callable[[Exception], RetryReason | None]
    reopen: Callable[[Exception], Awaitable[Attempt | None]]
```

注意这里的 `Attempt` 是delivery replacement tuple，与 `app.pipeline.request.Attempt`同名但完全不同。新代码不要再扩大这个歧义。建议把tuple改名为具名 `DeliveryAttempt`／`BufferedCandidateSource` dataclass；至少新runner不要导入裸 `Attempt`。

文件：`src/app/pipeline/retry.py`。

```python
class RetryReason(StrEnum):
    GITHUB_TOKEN_EXPIRED = "githubTokenExpired"
    NETWORK = "network"
    SERVER_ERROR = "serverError"

@dataclass(slots=True)
class RetryLedger:
    config: UpstreamRequestRetryConfig
    total_spent: int = 0
    per_reason: dict[RetryReason, int] = field(...)
    def consider(self, reason: RetryReason) -> RetryVerdict: ...
    def take(self, reason: RetryReason) -> RetryVerdict: ...

def decide_stream_ending(
    *,
    terminal_seen: bool,
    downstream_opened: bool,
    committed_blocks: int,
    ledger: RetryLedger,
    reason: RetryReason,
) -> EndingVerdict: ...
```

`decide_stream_ending()`会在选择 `REPLAY`时消费ledger。它的position输入以block commit为语义，不能直接拿来判断Chat terminal-only候选，除非新增明确的通用predicate，例如 `semantic_committed: bool`，并保持唯一消费点。不要先调用它再让runner第二次`ledger.take()`。

文件：`src/app/pipeline/driver.py`。

```python
def ledger_for(context: RequestContext, chain: Chain) -> RetryLedger: ...

async def replay_prepared(
    chain: Chain,
    context: RequestContext,
    route: Route,
    prepared_payload: Mapping[str, Any],
    reused_admission: TokenAdmissionObservation,
    on_routed: Callable[[RequestContext], None] | None = None,
) -> HandledRequest: ...
```

`replay_prepared()`会重用route snapshot、deep-copy final payload、构造新的DirectDriver，并由 `DirectDriver.begin_attempt()`建立真正的attempt record；`prepared_payload`跳过 `attempt.prepare`，`reused_admission`走 `reuse_token_admission()`。

文件：`src/app/server/routes/inference.py:837-916` 的局部函数：

```python
async def _reopen(replacing: Exception) -> app.pipeline.delivery.stream.Attempt | None: ...
```

这个callback已实现draining前置拒绝、frozen payload／admission复用、attempt计数、replacement failure记录、fresh guards／counter／assembler／buffer重建。新Chat runner应提取或参数化“打开prepared replacement并包装body source”的共用部分，避免复制约80行局部逻辑。Chat replacement不需要 `BlockAssembler`／`BlockBuffer`，所以更合适的复用层是“prepared response + guarded counted source + attempt metadata”，而不是强行把Chat candidate塞进现有tuple。

### 4.4 Deadline、idle、keepalive、cap 与 accounting

文件：`src/app/streaming/deadline.py`。

```python
class StreamDeadlineError(TimeoutError): ...
class ClientDeadlineError(TimeoutError): ...

def with_deadline_at[T](stream: AsyncIterator[T], deadline_at: float | None) -> AsyncIterator[T]: ...
def with_client_deadline_at[T](stream: AsyncIterator[T], deadline_at: float | None) -> AsyncIterator[T]: ...
```

两者共用 `_bounded()`，只在自己的 `asyncio.timeout_at()`确实expired时重标异常，并在finally关闭下层stream。Attempt deadline取自 `RequestContext.current_attempt.deadline_at`，client deadline取自request入口固定的绝对instant；replacement必须继续使用原client instant，并使用fresh attempt instant。

文件：`src/app/streaming/idle_timeout.py`。

```python
class StreamIdleTimeoutError(TimeoutError): ...

async def with_idle_timeout[T](stream: AsyncIterator[T], timeout_seconds: float) -> AsyncIterator[T]: ...
```

它按每次source item重置相对timeout，0关闭，并在finally关闭source。当前production把它放在attempt deadline内侧。

文件：`src/app/pipeline/delivery/stream.py`。

```python
PING_FRAME = b": ping\n\n"

async def _events_with_ping(
    chunks: AsyncIterator[bytes],
    interval: int,
    *,
    last_write: _LastWrite,
) -> AsyncGenerator[_Pull]: ...
```

现有keepalive scheduler基于“最后一次真正写给client的时间”，而不是upstream activity；这是必须保留的方向。它目前直接驱动 `read_events()`，因此不能原样供raw collector使用。建议提取一个协议中立的“pull source while offering keepalive cue” primitive，或者让 `BufferedTransactionRunner`实现同样的schedule并复用 `_keepalive_due()`。不能按upstream chunk到达重置client keepalive；那会把守卫装反。

文件：`src/app/pipeline/delivery/blocks.py`。

```python
class BufferCapExceeded(DeliveryError):
    def __init__(self, held: int, cap: int) -> None: ...

class BlockBuffer[UnitT: DeliveryUnit = CompletedBlock]:
    def __init__(self, policy: BufferingPolicy = "block", cap_bytes: int = 0) -> None: ...
    def add_many(self, blocks: Iterable[UnitT]) -> tuple[UnitT, ...]: ...
    def finish(self) -> tuple[UnitT, ...]: ...
    def enforce_cap_over(self, held_elsewhere: int) -> None: ...
```

Chat raw transaction不应假造 `DeliveryUnit`；可复用 `BufferCapExceeded`异常与配置值，但collector应维护精确raw byte count。当前 `BlockBuffer`只适合物化units，且 `_enforce_cap()`按 `held_bytes + incoming`解释；如果拿“整个raw buffer长度”反复传给 `enforce_cap_over()`会重复计数。

文件：`src/app/server/routes/inference.py`。

```python
async def _counted_upstream(
    chunks: AsyncIterator[bytes],
    chain: Chain,
    request_id: str,
    trace: RequestTrace,
    *,
    attempt: int,
) -> AsyncGenerator[bytes]: ...
```

它累计真实upstream body bytes到 `trace.received`和active registry，并为latest attempt记录pull timing；finally沿owner chain关闭source。Mode-adapted synthetic JSON不能经过这层覆盖 raw SSE count。Direct streaming replacement仍应让每个attempt的raw bytes进入request-wide upstream accounting，同时最新attempt timing按现状重置；final candidate observation则只取winner。

```python
@dataclass(slots=True)
class _StreamAccounting:
    chain: Chain
    request_id: str
    trace: RequestTrace
    completion: RequestCompletionCoordinator
    status_code: int
    context: RequestContext | None = None
    assembler: BlockAssembler | None = None
    response_loss_assembler: BlockAssembler | None = None
    passthrough: bool = False
    handed_over: bool = False
    handed_over_error: str | None = None
    completion_delivery: _CompletionDelivery = field(default_factory=_CompletionDelivery)
    tore_after_terminal: BaseException | None = None
    done: bool = False
    drained: bool = False
    failure: BaseException | None = None
    failure_provenance: Callable[[Exception], bool] | None = None

    def settle(self) -> None: ...
    def note_runtime_failure(self, error: Exception, upstream: bool, provenance: Callable[[Exception], bool] | None = None) -> None: ...
    def note_tear_after_terminal(self, error: Exception) -> None: ...
```

新Chat runner可以继续由 `_tracked_delivery()`和 `_AccountedStreamingResponse`承载ASGI send／cleanup，但 `_StreamAccounting.settle()`目前把 `assembler is None`解释为legacy one-shot，且 partial failure没有新tail ending／final candidate snapshot。建议给accounting增加协议中立的明确 completion/result callback或一个 `BufferedTransactionAccounting` adapter，而不是伪造 `BlockAssembler`。最终body成为一个 completion unit，仍应在该chunk的ASGI send返回后才accepted。

### 4.5 `ChatCompletionsAssembler` 当前状态

文件：`src/app/pipeline/delivery/formats/openai_chat_completions.py`。

```python
class ChatCompletionsAssembler:
    def __init__(self) -> None: ...

    @property
    def terminal(self) -> Terminal: ...

    @property
    def failure(self) -> StreamFailure | None: ...

    def close(self) -> tuple[CompletedBlock, ...]: ...

    @property
    def queued_bytes(self) -> int: ...

    @property
    def cut_mid_block(self) -> bool: ...

    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]: ...
```

内部状态是 `_next_index`、一个全局 `_open`、一个全局 `_text`、一个全局 `_thinking`、按tool index的 `_tools`、一个 `Terminal`和一个可空 `StreamFailure`。它的当前行为与新direct state有这些不可混用点：

- `push([DONE])`直接设 `terminal.seen=True`并flush。
- 任一choice的nonempty `finish_reason`都会flush全部draft、映射为Anthropic stop reason，并设 `terminal.seen=True`；这与“必须见 `[DONE]`”相反。
- 多choice共享同一个text／reasoning／tool namespace，会混合choices。
- 非法tool index回落到0；direct schema要求记issue且不得伪造call。
- bare error只在top-level `error`且没有`choices`时识别；新carrier规则要求top-level error即优先，即使同时含choices，并覆盖event名和flat `type:error`。
- `SseEvent.json()`的 `{}`让malformed与empty object同形。
- `close()`在EOF把开放draft flush成block；direct buffered transaction的EOF完整性由`[DONE]`决定。
- Usage被立刻转换成Anthropic keys且raw usage没有保留；Chat provider observation需要normalized／raw／exact分槽。

迁移建议：让assembler调用新的 `ChatEventReader`获得已解码字段，减少字段拼写重复；但保留它自己的translated single-projection state和既有外部签名。本切片不得把它改成direct multi-choice projection，也不得借TUI最小choice规则暗改translated delivery。现有deferred已经登记其multi-choice混合缺陷。

### 4.6 Observation 模型与 attempt生命周期

文件：`src/app/pipeline/response_observation.py`。

核心公开类型：

```python
@dataclass(frozen=True, slots=True)
class FrozenJsonObject:
    items: tuple[tuple[str, FrozenJson], ...]

@dataclass(frozen=True, slots=True)
class FrozenJsonArray:
    items: tuple[FrozenJson, ...]

type FrozenJson = JsonScalar | FrozenJsonObject | FrozenJsonArray

class JsonAvailability(StrEnum):
    OBSERVED = "observed"
    ABSENT = "absent"
    EXPLICIT_NULL = "explicit_null"
    UNREADABLE = "unreadable"
    NOT_APPLICABLE = "not_applicable"

class ResponseAvailability(StrEnum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"

@dataclass(frozen=True, slots=True)
class ObservationIssue:
    code: str
    field_path: str | None = None
    detail: str | None = None

@dataclass(frozen=True, slots=True)
class JsonObservation:
    availability: JsonAvailability
    value: FrozenJson | None = None

@dataclass(frozen=True, slots=True)
class UsageObservation:
    normalized: NormalizedUsage
    raw: JsonObservation
    exact: ExactUsage | None
    issues: tuple[ObservationIssue, ...] = ()

@dataclass(frozen=True, slots=True)
class ResponseObservation:
    availability: ResponseAvailability
    source_protocol: str
    terminal_event_type: str | None
    terminal_seen: bool | None
    status: str | None
    incomplete_reason: str | None
    error: JsonObservation
    error_summary: ProviderErrorSummary | None
    model: str | None
    service_tier: str | None
    output_items: tuple[OutputItemSummary, ...] | None
    usage: UsageObservation | None
    provider_usage: JsonObservation
    tool_usage: JsonObservation
    issues: tuple[ObservationIssue, ...] = ()
```

```python
@dataclass(slots=True)
class ResponsesObserver:
    def observe_event(self, event: ResponseEvent) -> None: ...
    def observe_response(self, body: Mapping[str, Any]) -> None: ...
    def observe_body_bytes(self, body: bytes) -> None: ...
    def snapshot(self) -> ResponseObservation: ...
```

可复用接口与约定：`FrozenJson*`／`freeze_json()`／`thaw_json()`；五态 `JsonObservation`；`ObservationIssue`；`NormalizedUsage`／`ExactUsage`／`UsageObservation`；public mutator no-throw、observer failure变issue而不改变delivery；provider-controlled整数用stdlib JSON decoder保留任意精度；detail在issue中有界。

建议新增Chat typed records到同一模块或相邻 `chat_response_observation.py`，然后让 `ResponseObservation`增加 `chat: ChatObservation | None`。为了不让Responses-only字段在Chat上伪装“缺席”，现有顶层Responses字段应保持其既有语义，Chat producer把它们放在not-applicable／null状态，并只写 `chat`。如果为减少构造参数改成两个payload union，必须同步所有现有tests和serializer；最小风险是保留顶层兼容字段并加独立槽。

文件：`src/app/pipeline/request.py`。

```python
@dataclass(slots=True)
class Attempt:
    index: int
    endpoint: ModelEndpoint | None = None
    payload: dict[str, Any] = field(...)
    status_code: int | None = None
    error: str = ""
    deadline_at: float | None = None
    response_observer: ResponsesObserver | None = None
    token_admission: TokenAdmissionObservation | None = None

@dataclass(slots=True)
class RequestContext:
    ...
    attempts: list[Attempt] = field(...)
    reply: Terminal | None = None
    response_observation: ResponseObservation | None = None
    retry_ledger: RetryLedger | None = None

    def begin_attempt(self, *, payload: dict[str, Any] | None = None) -> Attempt: ...
    @property
    def current_attempt(self) -> Attempt | None: ...
```

当前 `begin_attempt()`会先清空request-level observation，只在target为Responses时建立observer。建议把字段类型提升为一个窄 `ResponseObserver` protocol，或明确union `ResponsesObserver | Chat... | None`；Chat target在attempt开启时建立独立state／observer。由于Chat state同时驱动verdict与aggregation，它更适合由Chat attempt adapter建立并挂到Attempt的明确字段，例如 `chat_state: ChatAttemptState | None`，而不是塞进“side-only、绝不参与delivery”的 `response_observer`。最终 `ResponseObservation` snapshot仍由state投影。这样不会违反现有Responses observer不参与控制流的合同。

### 4.7 RequestTrace、RequestLine、JSONL serializer 与 formatter

文件：`src/app/observability/request_trace.py`。

```python
@dataclass(slots=True)
class RequestTrace:
    ...
    received: int = 0
    received_known: bool = False
    usage: dict[str, Any] = field(...)
    terminal_seen: bool = False
    stop_reason: str = ""
    terminal_status: str = ""
    client_actions: tuple[ClientAction, ...] = ()
    client_action_classification_complete: bool = False
    blocks: int = 0
    tools: tuple[str, ...] = ()
    thinking: tuple[str, ...] = ()
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    response_observation: ResponseObservation | None = None

    @property
    def upstream_response_body_bytes(self) -> int | None: ...
    def absorb(self, reply: Terminal) -> None: ...
    def absorb_response(self, observation: ResponseObservation) -> None: ...
```

`absorb_response()`目前仅在 `source_protocol == "openai-responses"` 时重建legacy fields。Chat接入时应新增Chat branch，从Chat snapshot投影legacy usage／minimum choice finish reason／tools／thinking和`ReplyDialect.CHAT_COMPLETIONS`，但console主路径仍优先读取rich observation，避免legacy projection变成第二套authority。`request_line_from_trace()`当前不携带rich observation；rich object直接由`trace.response_observation`传给formatter，并单独进入`FinalizedRequest.response`。

文件：`src/app/observability/request_log.py`。

```python
@dataclass(frozen=True, slots=True)
class RequestLine:
    ...
    bytes_in: int | None = None
    bytes_out: int | None = None
    usage: dict[str, Any] = field(...)
    terminal_seen: bool = False
    stop_reason: str = ""
    terminal_status: str = ""
    client_actions: tuple[ClientAction, ...] = ()
    client_action_classification_complete: bool = False
    blocks: int = 0
    tools: tuple[str, ...] = ()
    thinking: tuple[str, ...] = ()
    dialect: ReplyDialect = ReplyDialect.ANTHROPIC
    ...

def inert_token(value: str, *, limit: int = 120) -> str: ...

def format_response_observation(
    observation: ResponseObservation,
    *,
    color: bool = False,
) -> list[str]: ...

def format_completion_line(
    line: RequestLine,
    *,
    status: LogStatus,
    unicode: bool = True,
    color: bool = False,
    response_observation: ResponseObservation | None = None,
) -> str: ...
```

`format_completion_line()`的优先级是count provider → rich response observation → legacy terminal status → legacy stop reason → pending tools。`format_response_observation()`当前只处理Responses。建议保留单一dispatch入口，在其中按 `source_protocol`分派到 `format_responses_observation()`和新 `format_chat_observation()`，以继续保证rich observation压过legacy projection。Chat renderer复用 `inert_token()`、`paint()`、`_painted_tools()`和既有 `REASON_COLOURS`，但需扩展native Chat颜色白名单：`stop`绿、`length`黄、`content_filter`红、`tool_calls`无色，unknown无色。

文件：`src/app/observability/request_completion.py`。

```python
@dataclass(frozen=True, slots=True)
class FinalizedRequest:
    status: LogStatus
    at: str
    legacy: FrozenJsonObject
    response: ResponseObservation | None
    delivery: DeliveryObservation
    timings: TimingObservation
    body_bytes: BodyBytesObservation
    token_admissions: tuple[TokenAdmissionObservation, ...] = ()
    interruptions: tuple[InterruptionObservation, ...] = ()

    def request_line(self) -> RequestLine: ...
    def to_record_dict(self) -> dict[str, JsonValue]: ...

@dataclass(slots=True)
class RequestCompletionCoordinator:
    ...
    def settle(..., completion_unit: str | None = None) -> None: ...
    def publish(self) -> FinalizedRequest: ...
```

`FinalizedRequest.to_record_dict()`写 `schema_version: 2`，并把 `response`交给私有 `_response_dict()`。当前 `_response_dict()`只有Responses字段。Chat schema可在同一个 `observation.response`对象下新增 `chat`，保持version 2只在已有schema允许加字段时成立；如果既有消费者把shape当封闭集合，则应升version。living spec当前明确说“schema v2”并要求增加Chat payload，因此计划可按v2 additive字段实施，但必须用现有serializer tests确认没有其它固定shape oracle。

文件：`src/app/observability/request_log_file.py`。

```python
def write_request_record(line: RequestLine, *, status: str) -> Path | None: ...
def write_finalized_record(record: dict[str, JsonValue]) -> Path | None: ...
```

当前production完成路径使用 `write_finalized_record()`，严格 `allow_nan=False`且不做`default=str`。旧 `write_request_record()`仍存在兼容路径。Chat typed objects必须全部在 `FinalizedRequest.to_record_dict()`转成JSON值，不能依赖旧writer的string fallback。

### 4.8 当前 observation 发布顺序的关键缺口

文件：`src/app/server/routes/inference.py`。

```python
def _absorb_response_observation(context: RequestContext, trace: RequestTrace) -> None:
    attempt = context.current_attempt
    observer = attempt.response_observer if attempt is not None else None
    if observer is None:
        return
    observation = observer.snapshot()
    context.response_observation = observation
    trace.absorb_response(observation)
```

Streaming block路径的 `_observe_response_event()`同样每次从 `context.current_attempt`取observer。现有 `_reopen()`一旦 `replay_prepared()`调用 `begin_attempt()`，current attempt立刻切换；replacement headers前失败时，`_StreamAccounting.settle()`最终 `_absorb_response_observation()`会发布新attempt的unavailable observation，而不是旧candidate。现有test `test_a_replacement_that_opens_but_never_gets_a_response_cannot_leak_the_old_observation`就是钉这个Responses规则。

新Chat合同不同：旧candidate在replacement成功建立前仍是fallback，replacement headers失败后要发布旧snapshot并另记replacement failure。因此必须新增显式接口，例如：

```python
def _publish_response_observation(
    context: RequestContext,
    trace: RequestTrace,
    observation: ResponseObservation,
) -> None: ...
```

Runner final result携带winner／fallback candidate的snapshot，accounting在final action确定后调用这个接口。不要改写Responses现有current-attempt规则来迁就Chat；两种candidate lifecycle不同，混成一个隐式规则会让其中一边失真。

## 5. 建议新增／修改文件

### 5.1 建议新增生产文件

1. `src/app/pipeline/delivery/chat_facts.py`
   - `ChatEventReader`：从完整 `RawSseFrame`生成不可变 `ChatEventFacts`，严格区分 `[DONE]`、JSON object、non-object、malformed、ordinary event与三类error carrier；保存ordinal和raw offsets。
   - `ChatAttemptState`：按choice/tool index维护状态，第一次`[DONE]`冻结semantic snapshot；提供 transaction verdict、§9.3 aggregation input／result、Chat observation snapshot。
   - Chat typed records：choice、tool call、error facts、issue、tail ending。可复用 `JsonObservation`／`FrozenJsonObject`／`UsageObservation`，避免复制availability和JSON freezing。
2. `src/app/pipeline/delivery/buffered_transaction.py`
   - `BufferedAttemptCollector`：只读取一个attempt，拥有raw buffer、partial-frame staging、cap、source close与ending分类；不碰ledger、不发event、不打开replacement。
   - `BufferedCandidate`／`BufferedAttemptResult`：明确分槽raw body、semantic state、ending、failure provenance、raw metadata和可选client projection。
   - `BufferedTransactionRunner`：只负责post-header direct streaming candidate replacement、keepalive、shared ledger、draining、deadline结果、commit callback和final candidate选择。

如果实现发现两个文件互相形成循环，可把纯records放入 `chat_facts.py`，collector/runner只依赖protocol。不要把它们塞进现有1400行以上的 `stream.py`；该文件已经同时承担block scheduling、replay、continuation、framing、keepalive和failure carrier。

### 5.2 建议修改生产文件

- `src/app/pipeline/delivery/sse_source.py`：增加保留raw separator／offset的底层frame primitive；既有 `SseEvent`／`read_events()`继续工作。
- `src/app/pipeline/delivery/stream.py`：复用或提取keepalive scheduler、`UpstreamSource`和prepared replacement contract；direct Chat不再走legacy `one_shot_delivery()`。避免扩大旧 `Attempt` tuple名称。
- `src/app/server/routes/inference.py`：framer-none的Chat streaming分支接 `BufferedTransactionRunner`；提取prepared reopen body-source builder；按runner最终candidate显式发布observation；继续使用 `_counted_upstream`、`_tracked_delivery`、`_AccountedStreamingResponse`和send frontier。
- `src/app/pipeline/request.py`：attempt增加Chat state／observer槽，或把observer抽象为protocol；不要让Chat verdict依赖标注为side-only的Responses observer。
- `src/app/pipeline/response_observation.py`：增加Chat typed DTO与 `ResponseObservation.chat`，复用JSON availability、frozen JSON和usage records。
- `src/app/observability/request_trace.py`：Chat rich observation到legacy compatibility fields的单向投影；增加显式publish入口的消费方。
- `src/app/observability/request_completion.py`：`_response_dict()`序列化Chat payload、tail ending、choices、tools、unknown和issues；not-applicable shape同步新增 `chat: None`。
- `src/app/observability/request_log.py`：rich observation dispatcher和Chat精确formatter；复用`inert_token()`、颜色与tool-name rendering。
- `src/app/pipeline/delivery/formats/openai_chat_completions.py`：只把字段解码委托给新reader；保持translated assembler现有投影边界，不切换到multi-choice delivery state。
- `src/app/pipeline/delivery_policy.py`：若assembler构造需要reader dependency，在 `assembler_for()`保持默认无参外观或显式注入factory；不改变 `delivers_blocks()`的Chat client判定，direct Chat仍是terminal-only whole-body交付，不是假装有block framer。

### 5.3 本范围相邻但不应在本切片擅自完成的文件

- `src/app/model_provider/types.py`、各provider catalog／descriptor构造：Chat capability algebra属于计划的capability slice。
- `src/app/model_provider/codebuddy_client/client.py`、`src/app/model_provider/codebuddy.py`、`src/app/model_provider/xingchen/client.py`：移除provider内容适配与修复CodeBuddy `extra_headers`属于provider boundary slice。
- `src/app/pipeline/direct_driver/base.py`／`openai_chat_completions.py`：body-phase prepared retry seam与limiter body verdict属于non-stream adaptation slice。Shared collector应先提供这些接口需要的typed result，但不要在post-header runner里替driver消费其ledger。

## 6. 可复用接口清单

### 6.1 直接复用，不复制

- `ledger_for(context, chain)`：request级唯一 `RetryLedger`。
- `replay_prepared(...)`：route／payload／admission冻结后的重发入口。
- `UpstreamSource`：transport tear正向标记及source close。
- `with_idle_timeout()`、`with_deadline_at()`、`with_client_deadline_at()`：三种guard及异常身份。
- `_counted_upstream()`：真实upstream bytes与timing。
- `_tracked_delivery()`、`_AccountedStreamingResponse`、`RequestCompletionCoordinator`：ASGI send frontier、cleanup、最终发布。
- `BufferCapExceeded`：本侧cap failure类型。
- `freeze_json()`／`thaw_json()`、`JsonObservation`、`ObservationIssue`、`UsageObservation`：durable事实语义。
- `inert_token()`、`paint()`、`_painted_tools()`、`REASON_COLOURS`：console安全拼法和颜色语义。
- `tests/int/test_pipeline_app.py::make_client()`：production-entry fake upstream harness。
- `tests/int/recorded/` cassette infrastructure：只有当判据依赖真实upstream shape／chunk boundaries时使用。

### 6.2 需要先抽薄 seam再复用

- `inference._reopen()`：抽出“prepared response + guarded counted source”；当前返回block-specific tuple。
- `_events_with_ping()`：抽出协议中立pull／cue scheduler；当前绑定 `read_events()`。
- `_absorb_response_observation()`：拆成“从当前Responses attempt取snapshot”和“发布一个已选定snapshot”两步。
- `RateLimiter.observe_failure()`：新增event rate-limit入口，复用同一状态转换但不伪造HTTP 429／502或Retry-After。
- `_StreamAccounting`：新增terminal-only candidate结果输入，不伪造BlockAssembler。

## 7. 生产代码先行的实施顺序

以下顺序遵守“先运行行为，后补关键测试”，也让每一步形成可独立集成的语义切片。测试写在对应生产slice跑通之后，不以变绿本身决定commit边界。

### P1：raw SSE frame primitive

在 `sse_source.py`增加保留raw separator、EOF tail状态和offset所需的primitive；让既有 `read_events()`基于它适配回原 `SseEvent`接口。先用简单probe确认现有LF／CRLF／bare CR／mixed separator、multi-line data和trailing tail行为不变。不要在这一层解释Chat或error taxonomy。

### P2：Chat reader与attempt state

新增 `ChatEventReader`／`ChatAttemptState`。Reader严格解析一个完整raw frame，先认error carrier，再分类code/type，最后读普通chunk。State按choice/tool index累计、保留unknown、issues和raw offsets；第一个合法 `[DONE]`冻结semantic snapshot，后续只接raw tail。实现标准multi-choice aggregation投影和Chat observation投影，但translated `ChatCompletionsAssembler`只复用reader的字段解码。

### P3：single-attempt collector

新增 `BufferedAttemptCollector`，把raw framing、state、source provenance、cap和deterministic close组合起来。返回typed ending，不消费ledger。先跑单attempt happy path和各类ending的直接probe，确认每个source恰好close一次、primary／cleanup排序沿用现有helper。

### P4：post-header transaction runner

新增 `BufferedTransactionRunner`：接initial candidate、shared ledger、draining predicate、prepared reopen callback、client deadline状态、keepalive callback和commit callback。Pre-terminal按verdict尝试replacement；replacement建立前保留旧candidate；成功建立后原子切换并释放旧candidate。Post-terminal按§5.4 precedence停止tail并选择成功commit，不replay。最终只产出一次semantic body；comments可跨attempt先行yield。

### P5：production wiring与accounting

在 `inference.py` 的 `framer is None` Chat branch接runner，保留guard顺序、raw counting、ASGI owner和completion frontier。提取block与Chat共用的prepared reopen source builder。Runner final result显式发布winner／fallback Chat snapshot到context与trace。`_StreamAccounting`记录Chat completion unit、preterminal failure、tail ending及operator-side local tail failure；synthetic或partial body不能误标whole completion。

### P6：observation、durable schema与console

扩展 `ResponseObservation`／RequestTrace projection／`FinalizedRequest.to_record_dict()`／formatter。先接streaming final candidate，再接native non-stream whole-body和mode-adapted SSE state；三者都产同一Chat schema。Console只从rich snapshot展开最小choice，durable保留全部choice。完成production入口证据后，living TUI deferred第0条由主实施会话按Spec要求关闭；本调查不改living docs。

### P7：non-stream adaptation复用collector

由Chat driver body-phase seam调用同一个collector/state，driver作为唯一retry owner消费ledger并发布attempt events。Raw response metadata、SSE byte count和synthetic JSON body分槽。该步骤属于相邻计划slice，但必须复用P2／P3，不得另写parser或retry loop。

## 8. 后补测试地图

### 8.1 建议新增test文件

- `tests/unit/pipeline/delivery/test_chat_facts.py`：严格frame decoding、error carrier、multi-choice state、freeze、aggregation与observation snapshot。
- `tests/unit/pipeline/delivery/test_buffered_attempt_collector.py`：raw offsets、chunk切分、cap、source close、ending与cleanup排序。
- `tests/unit/pipeline/delivery/test_buffered_transaction.py`：candidate replacement、ledger single-owner、keepalive、pre/post-terminal precedence与fallback。
- `tests/unit/observability/test_chat_response_observation.py`：DTO availability／ordering／unknown／issues／serializer。
- 继续扩展 `tests/unit/observability/test_request_log.py`：Chat exact console rendering与颜色。
- 继续扩展 `tests/unit/observability/test_request_completion.py`：Chat v2 JSONL、body bytes、completion unit、tail/post-delivery failure。
- 继续扩展 `tests/int/test_pipeline_app.py`：真实ASGI production入口三条Chat路径、retry、wire、observation、JSONL和console。

不要把只服务这组测试的setup塞进全局 `tests/conftest.py`。优先把Chat-specific fixture放在新test模块或 `tests/int/test_pipeline_app.py`邻近helper处。

### 8.2 已有test可以直接扩展或作为回归保护

- `tests/unit/pipeline/delivery/test_sse_assembly.py`：现有SSE LF／CRLF／bare CR／mixed endings、multi-line data、chunk split、trailing tail、encode roundtrip。
- `tests/unit/pipeline/delivery/test_one_shot_delivery.py`：当前one-shot byte fidelity、one write、empty body send frontier、partial-on-error。新contract会有意推翻partial-on-first-error，故对应tests应迁移／改写为runner final carrier，不应简单删除不留替代。
- `tests/unit/pipeline/delivery/test_chat_completions_assembler.py`：translated assembler行为边界。新增reader复用后继续保护text／reasoning／tool assembly，但不把这些tests当direct multi-choice合同。
- `tests/unit/pipeline/test_direct_driver.py`：attempt events、retry budget、prepared payload、cleanup、cancellation、headers。
- `tests/unit/pipeline/test_timeout_enforcement.py`：attempt/header deadline各自命名和absolute instant。
- `tests/unit/pipeline/test_rate_limiting.py`：limiter mode、default／Retry-After等待、recovery。
- `tests/unit/pipeline/test_response_observation.py`：JSON freeze、availability、usage、observer no-throw、attempt reset。
- `tests/unit/observability/test_response_observation_projection.py`：旧attempt projection清理。
- `tests/unit/observability/test_request_completion.py`：single immutable finalized record、sink isolation、send frontier、one-shot empty body、post-delivery cleanup。
- `tests/int/test_pipeline_app.py::test_chat_completions_streams_are_delivered_whole_and_verbatim`：direct Chat happy-path baseline。
- `tests/int/test_pipeline_app.py::test_a_torn_stream_the_client_never_saw_is_replayed_end_to_end`及其prepared payload／attempt／deadline／draining邻近tests：复用post-header replay harness与断言风格。
- `tests/int/test_pipeline_app.py` 的 Responses observation tests：复用production-entry、JSONL `_records()`与console capture模式，不复用Responses字段oracle。
- `tests/int/recorded/`：真实shape／chunk boundary证据；目前是Responses语料，不能冒充Chat provider语料。

## 9. 每条非平凡判据的正确样本与单变量缺陷控制

下表中的“同一入口”指正确样本和缺陷控制必须走相同production或component入口。缺陷控制应只改变一项机制，并核对失败落在目标断言，不得由fixture解析错误、setup失败或旁路断言代打。实现阶段可以用受控mutation验证，恢复必须基于修改前快照，不能用`git checkout`抹掉未提交工作。

| 判据 | 正确样本控制 | 单变量缺陷控制 | 应变红的目标断言 | 证据边界 |
|---|---|---|---|---|
| Raw frame边界和offset精确 | 同一raw stream含LF、CRLF、multi-line data、两个frame同chunk和跨chunkframe；断言每个`raw`拼回输入、offset首尾连续、terminal frame结束offset精确 | 只把separator从frame raw中丢掉，或只把end offset设为body end | 完整bytes相等与offset区间断言 | 证明本地parser，不证明provider使用这些分隔组合 |
| `[DONE]`而非finish reason决定完整 | frame含`finish_reason:"stop"`后继续有usage并最终`[DONE]`，应成功且usage取终局前最后值 | 只把状态机改成见finish reason即success | 无`[DONE]`对照必须失败／retry；post-finish usage不得丢 | Fake shape只证明判据，不证明真实provider会省略`[DONE]` |
| Semantic freeze与raw tail共存 | `[DONE]`后追加第二个choice update、error、第二个`[DONE]`和raw comment，body逐字保留tail，snapshot保持首terminal前facts | 只移除freeze guard，让post-terminal event更新finish／usage／error | snapshot完整对象相等，raw bytes仍相等 | 本地构造不冒充真实post-DONE行为 |
| Error carrier优先于choices和EOF | top-level`error`与`choices`同object，或`event:error`＋flat payload；断言立即终局且截止error frame | 只恢复当前`"error" in data and "choices" not in data`条件 | calls不应因EOF taxonomy多开；final raw截止offset | Fake证明本地carrier precedence |
| Known transient只花一次ledger | 首attempt `server_error`，次attempt完整；断言calls=2、`ledger.total_spent=1`、client只见次attempt | 只让collector先`ledger.take()`，runner再take一次 | total/per-reason精确值与calls | Fake不证明provider真的发该code |
| Replacement建立前保留fallback | initial收partial，replacement在headers前失败；断言final carrier与observation来自initial，并另记replacement failure | 只让`begin_attempt()`立刻清空candidate | response bytes／Chat snapshot应仍等于initial | 证明candidate lifecycle，不证明生产网络failure provenance |
| Replacement成功后旧attempt完全不可见 | 首attempt含唯一marker `discarded-A`后tear，次attempt含`winner-B`和完整`[DONE]` | 只保留旧raw前缀或让旧state继续观察 | response、durable snapshot、console中A出现0次，B恰好1次；calls=2 | `MockTransport`证明代理接线，不证明真实upstream tear形状 |
| Final成功body来自单一attempt且逐字 | 两attempt使用不同line endings、comments与未知fields，次attempt成功 | 只拼接旧partial＋新body，或重新encode新events | response bytes与第二attempt预置bytes完整相等，唯一markers顺序／次数精确 | 不用产品serializer生成expected；expected为独立literal bytes |
| Keepalive不关闭replay窗口 | 首attempt等待超过interval、产出comment后tear；次attempt成功 | 只把comment send设置semantic committed | 仍calls=2且body semantic部分只含winner；comment允许先出现 | 时间控制只证明本地schedule；不证明真实client耐受性 |
| Keepalive读client write时钟 | upstream持续小chunk但不形成完整frame／terminal，等待超过interval；应仍发comment | 只在每次upstream chunk重置deadline | 捕获到至少一条comment | Fake pacing不冒充真实provider pacing |
| Pre-terminal cap不越界且不retry | cap小于next完整frame或partial staging；断言held peak≤cap、calls=1、partial carrier≤cap | 只在append后检查cap | peak／body长度断言 | 需要测试可观察held peak，不能只看最终body |
| Post-terminal cap成功截尾 | 完整`[DONE]`在cap内，下一tail frame跨cap；断言成功、body截止DONE、tail=`buffer_cap` | 只把cap一律判preterminal failure或先append越界tail | 成功status、exact body、tail_ending、peak≤cap | 本地cap机制证据 |
| Post-terminal client deadline成功提交 | `[DONE]`后source挂住直到client deadline；断言成功body、`tail(client_deadline)`、无replay | 只保留当前client-deadline优先分支，把完整回复降成failure | status、body、calls=1、tail字段和console | loopback timeout只证明本地deadline路径，不证明真实provider会挂住 |
| Client cancellation不写 | 已收`[DONE]`但downstream取消发生在body send前；断言没有accepted completion unit | 只在cancel branch强行commit buffered body | ASGI send trace／delivery state | 测试cancel机制，不冒充用户真实断开原因 |
| Raw SSE accounting不被synthetic JSON覆盖 | mode adaptation的raw SSE和synthetic JSON刻意长度不同 | 只用synthetic response length写`upstream_response_body_bytes` | JSONL `body_bytes.upstream_response`等于raw输入总bytes，downstream等于JSONbytes | Fake足以证明本代理分槽 |
| Observation只来自最终candidate | 首attempt和winner使用不同finish／tools／usage，response只交付winner | 只让observer继续跟`current_attempt`错误切换，或合并两attempt | durable完整Chat对象与console精确尾段 | Fake证明promotion wiring |
| Fallback observation不被failed replacement覆盖 | initial有可读Chat facts，replacement headers前失败 | 只调用当前 `_absorb_response_observation(context, trace)` | final Chat snapshot是initial，另有replacement failure | 与现有Responses lifecycle不同，需独立test |
| Choice/tool排序、重复、无名保持 | choice输入反序0/1；choice0 tools按2/0/1到达，name为Bash/Bash/absent；断言schema按0/1和0/1/2，重复保留 | 只按arrival order输出，或按name去重，或过滤无名 | durable完整对象和console `tool_calls(Bash,?,Bash) choices=2` | 不以列表包含断言，必须完整对象相等＋顺序 |
| finish缺席时只说called | 同样tools但finish absent；断言`called(Bash,?,Bash) choices=2` | 只从有tools反推`tool_calls` finish | console exact suffix | 证明presentation不发明终局 |
| absent／null／unreadable区分 | reasoning分别缺席、null、string、错误类型；usage分别缺席、null、zero、malformed | 只用`None`合并状态 | durableavailability/value完整对象 | Fake足以证明本地schema语义 |
| Unknown保存且formatter inert | unknown finish reason和unknown字段含空格、括号、ANSI/control | 只原样插入console或丢unknown | durable原值保留，console含escaped inert token且无控制字节 | 不需要真实provider样本来证明本地转义 |
| Chat不污染Responses槽 | Chat production response形成observation | 只把finish reason写到Responses `status`或choices写到`output_items` | `chat`非null且Responses-specific槽按合同null／not-applicable | 完整对象断言，不只断言`chat`存在 |
| JSONL与console读同一finalized事实 | production入口得到final Chat snapshot；捕获active store、JSONL和console | 只让formatter从legacy fields重推或serializer从synthetic body重推 | 三个presentation的identity／tools／usage／tail一致，且各自按schema裁剪 | 一致不等于真实provider shape；只证明single-source wiring |
| Source恰好关闭一次且cleanup不盖primary | source记录`aclose`次数，主pull抛A、close抛B | 只双close，或让B替换A | close count=1；primary identity=A且cleanup链含B | 本地resource contract |
| Cancellation不进普通retry | collector／runner处注入`CancelledError` | 只把catch扩大到`BaseException`并交给taxonomy | calls=1、ledger=0、cancel identity保留 | 本地控制流证据 |
| Mutable prepare与admission不重跑 | 首次prepare把payload变B并admit；post-header replay后断言两次final bytes相同、prepare/admission各1，第二attempt标reused | 只改reopen走`handle_bounded()` | counters、sent bytes、admission records | 复用现有integration pattern |
| Event rate-limit走limiter但不伪造HTTP事实 | 首attemptHTTP 200内rate-limit carrier，次attempt成功；fake clock记录默认等待 | 只调用`observe_failure(429,{})`并把status写成429，或先`observe_success()` | limiter mode／wait／HTTP raw status仍200／ledger serverError一次 | Fake证明本地映射，不证明真实provider发过该event |

普通正向字段拼接、简单getter和已经由现有red→green TDD证明过的非关键性质不需要额外mutation campaign。上表要求双控制的是正确性关键不变量、不可逆candidate选择和第一次即绿的非平凡性质。

## 10. Mock upstream、cassette与真实provider的证据边界

### 10.1 现有production-entry fake harness

`tests/int/test_pipeline_app.py`文件头写“真实ASGI app，upstream是SDK下的MockTransport”。精确入口：

```python
def make_provider(
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    disabled: list[str] | None = None,
    catalog: dict[str, Any] | None = None,
) -> tuple[GithubCopilotProvider, httpx2.AsyncClient]: ...


def make_client(
    handler: Callable[[httpx2.Request], httpx2.Response],
    *,
    mappings: dict[str, str] | None = None,
    tokenization_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
    configure_chain: Callable[[Chain], None] | None = None,
) -> tuple[TestClient, list[httpx2.Request]]: ...
```

它适合验证：HTTP入口、routing、driver、provider SDK调用、attempt/replay、body iterator、ASGI response、accounting、console、active registry与JSONL接线。可用async iterator制造tear、hang、chunk slicing和cleanup failure。`seen`精确记录实际upstream request bytes和calls。

它不能证明：CodeBuddy／Xingchen／Copilot真实服务会发某个error carrier、post-DONE tail、multi-choice组合、chunk boundary、id变化、deadline failure或header；也不能证明某项provider capability。测试docstring和计划证据描述必须逐条写“fake只证明本代理处理与接线”。

### 10.2 Provider component harness

CodeBuddy component tests用 `httpx2.MockTransport`直接驱动 `CodebuddyClient`；当前tests明确钉住provider强制stream和内部aggregation，迁移后应改为原样payload/mode、extra_headers和raw response。Xingchen unit tests也用MockTransport，已覆盖签名、owned headers、显式stream defaults和non-stream不注入。它们证明provider adapter本地行为，不证明upstream capability。

### 10.3 Recorded upstream

`tests/int/recorded/`能保留真实capture的chunk boundaries、认证presence和请求判别字段。当前现成cassette及`test_responses_observation_cassettes.py`主要覆盖Responses，不可拿来替Chat provider shape作证。若未来取得Chat真实capture，可用于reader／collector重放和fake oracle校准；历史录制仍只证明录制时的样本，不是本轮实况。用户已经决定本次不运行CodeBuddy P6，所以计划不得把P6列为当前验收前置，也不得用fake P6替代。

## 11. 排除方案及理由

1. **直接扩写 `one_shot_delivery()`成为大状态机。** 排除。它当前是协议中立的byte collector；把reader、ledger、reopen、keepalive、candidate、tail matrix和observation都塞进一个generator会制造浅接口，并与block replay重复owner逻辑。
2. **直接把 `stream_delivery()`的BlockAssembler／BlockBuffer路径用于Chat。** 排除。它的commit frontier是block send，Chat本次合同是terminal-only raw body；伪造blocks会错误关闭replay窗口，也会重写wire。
3. **让 `ChatCompletionsAssembler`兼任direct state。** 排除。它是translated Anthropic block projection，当前single-projection状态、finish_reason terminal和EOF flush都与direct合同冲突；本次还明确不暗改translated multi-choice行为。
4. **两条路径各扫描一次 `[DONE]`。** 排除。会复制frame parser、error taxonomy、freeze、usage和issues，并让aggregation与observation漂移。
5. **从synthetic non-stream JSON重建provider observation。** 排除。Aggregation已经发生信息裁剪，且会把本代理合成的role／object等冒充provider事实；最终attempt state才是authority。
6. **继续让request observation自动跟随 `context.current_attempt`。** 对Chat排除。Replacement headers前失败时current attempt不是实际交付candidate；显式final candidate promotion是必要状态，不是“额外防护”。
7. **在collector中消费ledger或打开replacement。** 排除。会与DirectDriver／delivery runner形成双owner，使一个failure花两次预算。
8. **把stream error伪造成HTTP 500／429以复用现有分类。** 排除。真实headers是200；需要typed upstream-event failure和limiter event入口。
9. **用重新编码的SSE event比较“逐字保真”。** 排除。`encode_frame()`会规范化空格、line ending和field布局；oracle必须是独立literal raw bytes或recorded capture。
10. **用body总长度证明不重不丢不乱序。** 排除。顺序交换、丢一补一都可能同长；必须用唯一markers、exact bytes和完整对象相等。
11. **把fake upstream通过标为“provider已验证”。** 排除。Fake只能验证本代理；真实shape需要cassette或获授权的live probe。CodeBuddy P6当前明确未执行。
12. **为这些判据建立manifest、hash gate或新proof framework。** 排除。复用现有pytest、MockTransport、cassette、JSONL和简单mutation controls即可；项目规则禁止把实现扩大成验证控制平面。

## 12. 计划撰写时应显式列出的风险与停线条件

- 如果实现中发现raw frame primitive无法在不改变既有 `read_events()` EOF-tail行为的情况下复用，应保留两个明确API，不得为“统一”而改变既有translated路径。
- 如果 `ResponseObservation`的additive `chat`字段会破坏已存在的schema v2消费者，必须回到TUI living Spec确认versioning，而不是在serializer里静默改shape。当前Spec明确要求schema v2增加Chat槽，故默认按additive实施。
- 如果post-header runner需要知道provider capability或重新route，说明边界错了；它只能使用captured route／payload／admission／capability snapshot和prepared reopen。
- 如果某个test必须断言真实provider会发某shape，应改用相符cassette；没有cassette就把该claim标为未验证，不得由MockTransport补位。
- 如果为了实现Chat fallback准备修改Responses replacement lifecycle，应停下拆开两个projection规则；现有Responses test明确要求failed replacement不泄漏old observation，而Chat Spec要求old candidate作为fallback，两者并非同一合同。

## 13. 可直接转入实施计划的文件级依赖顺序

```text
sse_source.py raw frame primitive
    ↓
chat_facts.py reader + attempt state + projection
    ↓
buffered_transaction.py collector
    ↓
buffered_transaction.py post-header runner
    ↓
inference.py prepared reopen extraction + Chat wiring + accounting
    ↓
request.py / response_observation.py attempt and DTO wiring
    ↓
request_trace.py / request_completion.py / request_log.py durable + console projection
    ↓
openai_chat_completions.py translated assembler decoder reuse
    ↓
non-stream Chat driver adapter reuses the same collector/state in its own retry owner slice
```

横切复用边是 `RetryLedger／replay_prepared`、absolute deadlines、`UpstreamSource`、`_counted_upstream`、ASGI completion frontier、frozen JSON／usage DTO和现有integration harness。不得复制的三个authority分别是：SSE semantic facts在 `ChatAttemptState`，final candidate选择在对应orchestration owner，presentation在TUI formatter／durable serializer。