# 独立评审：`0ca87b9` 的 h2 分类与归因、`a00f5a2` 的死链路归档

评审日期：2026-08-23。评审对象严格限定为 `0ca87b9cf0f66d5ef208ffe1ca0b6121d442460b` 与 `a00f5a2606e54a636860f7e98dd80fccfcd33013`；夹在两者之间的 `2402a85` 以及评审期间后来落到 `main` 的 `2cd7951` 不在范围内。工作树有并行改动，本报告的提交事实均从 Git object 读取；运行提交态测试时使用由 `git archive <sha>` 生成的 `/tmp` fixture，没有用工作树覆盖提交态。

## Verdict

**needs-fix**。发现共 6 条：**1 blocker、2 major、2 minor、1 nit**。

最先要处理的是 `a00f5a2` 并未把 live `transport.py` 及其 test 从提交中删掉；提交自己的 module-boundary test 在提交态必红。即使补上这两处已暂存但未提交的删除，`0ca87b9` 仍有两个独立的 major：`H2Error` 族级规则把本方 h2 API 误用也命名为可重放的上游网络故障；`hand_back_block` 的 `UPSTREAM` 兜底依赖的“`not ours` 即非本侧错误”只在语法上成立，语义上已被本侧 SSE reader 失败的探针反例推翻。

## Findings

### B1．blocker：`a00f5a2` 是 copy，不是 archive；提交态保留 live module 与 live test，并由提交自己的守卫打红

**结论权重：强到必须在接受提交前修。** 这是 exact commit tree 与 exact commit test 的直接结果，不受当前工作树的 staged deletion 影响。

`git ls-tree -r a00f5a2` 同时列出以下四条：

```text
src/.archived/app/model_provider/ghc_client/transport.py
src/app/model_provider/ghc_client/transport.py
tests/.archived/unit/model_provider/ghc_client/test_pre_header_retry.py
tests/unit/model_provider/ghc_client/test_pre_header_retry.py
```

因此 `src/.archived/README.md:31-43` 的“Three things arrived here together”“One test came with them”、提交信息的“moved whole”“Eleven tests left the sweep”，以及 `tests/unit/test_module_boundaries.py:49-50` 的“Archived”都不是 `a00f5a2` 的提交事实。工作树当前恰有这两个文件的 staged deletion：

```text
D  src/app/model_provider/ghc_client/transport.py
D  tests/unit/model_provider/ghc_client/test_pre_header_retry.py
```

但 index 不属于 `a00f5a2`。从 exact commit 解包后运行 module-boundary test 的结果为：

```text
fixture=/tmp/ghc-review-a00f5a2.GzxRAb
FAILED tests/unit/test_module_boundaries.py::test_the_archived_chain_is_not_importable_at_all
E assert ['app.model_provider.ghc_client.transport'] == []
1 failed, 2 passed in 2.21s
```

这也解释了为什么当前工作树的受影响子集可以是绿的，而提交本身仍是红的：当前工作树已经叠加了未提交的删除。已知的“1540 passed”与“少 11 条”只能证明叠加态，不能证明 `a00f5a2`；在 exact commit 里 archived test 被 pytest 忽略，但 live test 仍会收集，所以那 10 条并未从提交态测试集合离开。

### M1．major：`H2Error` 不表示“对端发来的帧”；10 个 concrete exception 可由本方 public h2 API 调用触发，族级映射违反模块自己的 closed-set 原则

**结论权重：强到需要修改分类边界或收窄契约。** h2 4.4.1 源码逐类核对与实际 public API 探针给出同一答案。已观测的 GOAWAY 裸 `ProtocolError` 确属上游输入；从这一例推到整个 `H2Error` 族则不成立。

`src/app/model_provider/ghc_client/errors.py:40` 写道：“An h2 exception is the HTTP/2 state machine's account of frames the peer sent; it is upstream's failure by construction”。h2 自己的类型定义直接反驳这一全称判断：`h2/exceptions.py:18-20` 对 `ProtocolError` 的定义是“An action was attempted in violation”，没有限定 action 来自对端；`RFC1122Error` 更明确写成“users attempt to do something”（`h2/exceptions.py:164-172`）。其两个 raise site 都是本方 outbound API：server 调 `send_headers(..., priority_*=...)`（`h2/connection.py:795-823`）或 `prioritize()`（`h2/connection.py:1211-1280`）。

以下是 h2 4.4.1 全部 15 个类的触发方核对。表里的“本方”指调用 h2 public API 或 h2/httpcore 本地状态推进；“对端”指解析 `receive_data()` 收到的帧。双向类说明**类型本身不携带归因**。

| 类 | h2 4.4.1 的触发位置与方向 | 是否能由族级类型单独判成 upstream/network |
|---|---|---|
| `H2Error` | base class；包内没有直接 raise site | 不能；还会自动吞进未来新增的未知 subclass |
| `ProtocolError` | 双向。本方例：非法 priority 参数，`h2/connection.py:2070-2079`；对端例：错误 preamble，`h2/frame_buffer.py:43-58`；connection/stream state machine 也同时处理 `SEND_*` 与 `RECV_*` | 不能 |
| `FrameTooLargeError` | 双向。接收超长帧见 `h2/frame_buffer.py:65-71`；本方 `send_data()` 发送超过 `max_outbound_frame_size` 见 `h2/connection.py:893-898` | 不能 |
| `FrameDataMissingError` | 对端 frame body 缺失或非法，`h2/frame_buffer.py:145-154` | 作为当前实现的具体类可以，但无须因此纳入整个 base class |
| `TooManyStreamsError` | 双向。本方超出 remote advertised limit 见 `h2/connection.py:795-801`；对端超出 local limit 见 `h2/connection.py:1599-1606` | 不能 |
| `FlowControlError` | 双向。本方发超 window 见 `h2/connection.py:893-895`；对端 DATA 消耗使 inbound window 低于零见 `h2/windows.py:35-50`；WINDOW_UPDATE/settings 也可触发 | 不能 |
| `StreamIDTooLowError` | 双向。统一产生点是 `_begin_new_stream()`，`h2/connection.py:473-497`；它既由本方 `send_headers()` 调用，也由接收 HEADERS/PUSH_PROMISE 调用 | 不能；这正是用户点名的反例之一 |
| `NoAvailableStreamIDError` | 本方 `get_next_available_stream_id()` 的 connection-local stream-id exhaustion，`h2/connection.py:650-683`；httpcore2 当前在 pre-header 路径显式捕获并转为 `ConnectionNotAvailable`，`httpcore2/_async/http2.py:116-123` | 不能称为“peer sent frames”；是否换连接重试是位置策略，不是 upstream attribution |
| `NoSuchStreamError` | 双向。统一产生点 `_get_stream_by_id()`，`h2/connection.py:626-648`；本方 `end_stream/reset_stream/local_flow_control_window` 与对端 naked CONTINUATION/PUSH_PROMISE 等都会调用 | 不能；这正是用户点名的另一反例 |
| `StreamClosedError` | 双向。stream state machine 明列 `recv_on_closed_stream()` 与 `send_on_closed_stream()`，`h2/stream.py:348-370` | 不能 |
| `InvalidSettingsValueError` | 双向。local `Settings.__init__/__setitem__` 与 received setting validation 都抛，`h2/settings.py:128-153,275-307` | 不能 |
| `InvalidBodyLengthError` | 对端 body 与 `Content-Length` 不一致，`h2/exceptions.py:136-149`、`h2/stream.py:1390-1409` | 作为当前实现的具体类可以 |
| `UnsupportedFrameError` | h2 4.4.1 包内除定义外零引用、零 raise site；docstring 把它描述为 remote peer，`h2/exceptions.py:152-160` | 当前 dormant，不能拿它为 base-class widening 背书 |
| `RFC1122Error` | 仅本方 user action；定义见 `h2/exceptions.py:164-172`，raise site 见 `h2/connection.py:823,1280` | 明确不能 |
| `DenialOfServiceError` | 对端 oversized HPACK header block，`h2/connection.py:2096-2111` | 作为当前实现的具体类可以 |

实际探针 `/tmp/probe_h2_local_exceptions.py` 只调用 h2 public API，成功制造了 10 个本方 action 产生的 concrete exceptions；当前 `normalize_upstream_error` 将 10/10 全部转为 `UpstreamError`，`reason_for` 全部为 `network`：

```text
StreamIDTooLowError -> StreamIDTooLowError normalized= UpstreamError reason= network
NoSuchStreamError -> NoSuchStreamError normalized= UpstreamError reason= network
FrameTooLargeError -> FrameTooLargeError normalized= UpstreamError reason= network
FlowControlError -> FlowControlError normalized= UpstreamError reason= network
InvalidSettingsValueError -> InvalidSettingsValueError normalized= UpstreamError reason= network
NoAvailableStreamIDError -> NoAvailableStreamIDError normalized= UpstreamError reason= network
ProtocolError -> ProtocolError normalized= UpstreamError reason= network
TooManyStreamsError -> TooManyStreamsError normalized= UpstreamError reason= network
StreamClosedError -> StreamClosedError normalized= UpstreamError reason= network
RFC1122Error -> RFC1122Error normalized= UpstreamError reason= network
```

`tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py:115-123` 不只是没有防住这个副作用，反而把它钉成契约：测试明确把仅本方触发的 `RFC1122Error` 断言为 `NETWORK`。该测试名为“whole h2 family”，但三个构造样本没有逐类回答触发方；base-class `isinstance` 让它绿，不构成对 15 个语义的审查。

需要保留的限定是：本次真实故障的裸 `ProtocolError` 从 `httpcore2/_async/http2.py:425` 的 `self._h2_state.receive_data(data)` 冒出，的确由对端字节触发；分开读取时的 `RemoteProtocolError` 与同读时的裸 `ProtocolError` 应同命运，这个目标成立。当前 httpcore2 也会在 pre-header 路径把其他 `ProtocolError` 分成 remote 与 local（`httpcore2/_async/http2.py:145-167`）。因此更稳妥的修复方向是**在能看到来源的 body-read 边界保留 provenance，再翻译为 pipeline error**，而不是把一个双向 exception hierarchy 全局定义成 upstream。至少不能继续保留 `errors.py:40` 与 family test 的无条件语义。

### M2．major：`not ours` 的语法门存在，但它没有正向识别本侧所有代码；现有调用点已经能把本侧 SSE reader bug 交接成 upstream

**结论权重：强到需要修正跨模块契约。** 代码直读给出缺口，一次隔离运行期变异给出当前调用链上的反例。

当前调用关系本身已核清：带 error 的 `_hand_over(...)` 生产调用只有 `src/app/pipeline/delivery/stream.py:382-386`，它确实在 `if not ours` 下；`stream.py:427-429` 的另一调用传的是 `error=None` 的 stop-reason ending。`ContinuationSupport.synthesize` 由 `src/app/server/routes/inference.py:419-437` 构造，唯一落到 `hand_back_block()` 的 closure 在 `inference.py:288-297`。没有第二个 production caller，也没有 entry point、registry、Protocol lookup、`getattr` 或字符串 dynamic import 接线。

但“只有 `not ours` 到达”不等于“到达的不是本侧错误”。`raised_here` 只标记 `assembler.push`、`_commit` 和 `framer.keepalive`（`stream.py:294-327`）；同一个 outer `try` 还执行本侧 `_events_with_ping`、`read_events`、scheduler、`pull.claim()` 与 cleanup（`stream.py:100-177,282-329`），这些位置抛出的普通 `Exception` 都进入 `torn`，却不可能与 `raised_here` identity 相等。`stream.py:279` 的“all three places this side runs code inside the loop”、`stream.py:357` 的“anything raised out of this side's own code”、`stream.py:361` 与 `hand_over.py:260` 的“by construction”因此都是过强断言。

探针 `/tmp/probe_unmarked_local_path.py` 在隔离 Python 进程中让本侧 `read_events` wrapper 在正常产出一个完整 block 后抛 `LocalParserBug`，其余生产接线不变。结果为：

```text
handed count: 1
handed local bug: True bug in this side's SSE reader
delivery returned cleanly after hand-over: True
```

这不是“未来新增 caller”才会出现的形状：它走的是当前唯一 caller，只是把当前 parser 的潜在 coding error 具体化。进入 `hand_back_block()` 后，fallback 无 provenance 参数，只能把它写成 `upstream`。同样地，如果将来直接增加第二个 `hand_back_block(error=local_bug, ...)` caller，**没有任何东西会出声**：签名不携带 origin/category，函数内无 assertion，module-boundary test 不限制 caller count，现有 integration test只证明 `DecodingError` 得到 `upstream`，不能拒绝 local error。

建议方向不是再扩大一份易漏的 marker 清单，而是把异常的来源作为显式数据从真正区分 upstream pull 与 local processing 的 catch boundary 传入 `ContinuationSupport`／`hand_back_block`。至少应让 `hand_back_block` 的 API 无法仅凭“某个 caller 目前先做了判断”自行推断责任方；否则这正是项目已记录过的“结构上不可达”形态。

### m1．minor：`CopilotUpstream` 三件套的死链判定成立，但 live `copilot.py` 还留着两个 production-zero header wrappers，archive docstring 对它们的“live”断言为假

**结论权重：对仓内 production reachability 强到可据此清理；对未知 external importer 不作全称判断。** 项目只发布 CLI entry point，未找到这两个 helper 的 public compatibility contract。

对 `a00f5a2` 的全 tracked-tree 搜索、provider registry、package exports、`pyproject.toml` entry point 与 dynamic import 机制核对结果如下：

- `CopilotUpstream` 在改前没有实例化点；没有注册表、Protocol runtime lookup、字符串类名、entry point 或 dynamic import。其目标 `UpstreamTarget` 已在 archive。三件套的静态链“`CopilotUpstream` → `GhcApiClient.send_responses_headers` → transport classifier”成立，未发现 over-archive。
- `GitHubTokenSourceAdapter` 确实 live：`src/app/server/composition.py:57,312-329` import 并构造它。
- `build_copilot_identity_headers` 在 `a00f5a2` 的 `src/` 与 `tests/` 中除定义外零 caller。
- `build_copilot_headers` 在 `src/` 中零 caller，唯一 caller 是 `tests/unit/upstream/test_upstream_client.py:6,39-58`。live client 直接调用下层 `build_request_headers`（`src/app/model_provider/ghc_client/client.py:12,46-59`），composition 直接调用下层 `build_identity_headers`（`src/app/server/composition.py:37,474`）。

所以 `src/.archived/app/upstream/copilot_upstream.py:2` 的“The rest of that file is live … the two header builders are used by the live client”只有前半句的 adapter 成立；两个 wrapper 都不是 production-live。`build_copilot_headers` 有 test consumer 只能说明测试在保它，不能证明产品接线。应当一并归档／删除，或明确写出保留它们的 external/public contract；当前文本把未观测的 live consumer 写成了事实。

### m2．minor：新增测试咬住 `_commit` marker 与 hand-over fallback，却没有咬住 keepalive marker

**结论权重：强到可据此补一条 targeted regression；不否定当前 keepalive 实现本身。** 变异已在 exact `0ca87b9` 的 `/tmp` fixture 中确认实际加载。

现有 framing tests 用 `_FramerWithABug.block()`，能咬住包住整个 `_commit` 的 marker；作者报告的 narrow-marker 变异与断言形状一致。hand-over fallback 也有真实 integration discrimination：在 `/tmp/ghc-review-fallback-mutation.sYCFmk` 把 fallback 改回 `INTERNAL`，先用 `inspect.getsourcefile/getsource` 确认加载的是变异文件，再跑单测，得到：

```text
FAILED tests/int/test_pipeline_app.py::test_a_failure_the_taxonomy_cannot_name_is_still_upstreams
E AssertionError: assert 'internal' == 'upstream'
1 failed in 2.71s
```

H2 mapping 的缺失变异同样有分辨力：runtime plugin 打印 `H2Error_present_after_mutation=False` 后，`test_one_goaway_has_one_fate_whichever_shape_it_arrives_in` 在 `assert isinstance(bare, UpstreamError)` 红；未变异 control 为 `1 passed`。

keepalive 则没有同等保障。在 `/tmp/ghc-review-keepalive-mutation.rHG5TM` 只移除 `framer.keepalive()` 外的 `try/except raised_here`，保留先命名再 `yield`；runtime probe 输出：

```text
resolved= /tmp/ghc-review-keepalive-mutation.rHG5TM/src/app/pipeline/delivery/stream.py
keepalive_marker_present= False
```

随后 `tests/unit/pipeline/delivery` 仍为 `141 passed in 22.78s`。这证明当前 suite 没有区分“keepalive 自己抛错被标为 ours”与“该错按 upstream 处理”。建议新增一个只在 `keepalive()` 抛错的 framer case；不需要扩成证明体系。

### n1．nit：archive rationale 的“唯一记录”是未计数的全称词

**结论权重：事实性措辞应收窄，不影响运行行为。** `src/.archived/README.md:41` 与 `a00f5a2` commit message 都称 `transport.py` 是“the only place in the tree”记录 httpcore 只保护 socket read、裸 h2 error 会逃出的依赖缺陷。对 `0ca87b9^` 的 tracked tree 搜索至少还有两处逐字记录同一机制：`src/app/model_provider/ghc_client/client.py:190-191` 和 `tests/unit/model_provider/ghc_client/test_pre_header_retry.py:47-53`。`transport.py` 可以说是承载该 classifier 的 module，不能说是树中唯一写下知识的地方。

## 重点问题逐项裁定

### 1．方案 (a) 的副作用面

**裁定：观测到的裸 GOAWAY 应归 network/replay，这一窄结论成立；`H2Error` 族级规则不成立。** 15 类逐项结果见 M1。尤其 `StreamIDTooLowError`、`NoSuchStreamError`、`StreamClosedError` 都是双向，`RFC1122Error` 是明确的本方-only，`NoAvailableStreamIDError` 是本方 connection-local exhaustion。故 `(a)` 以全局 base class 实现，违反 `errors.py:0-5,100-104` 自己“unknown/local bug must not read as retryable”的原则。

### 2．`raised_here` 标记区与 consumer `athrow()`

**裁定：`_commit` 与 keepalive 的写法本身安全，没有把 consumer throw 误标为 `raised_here`。** `_commit` 的签名是 `-> list[bytes]`，实现先 `session.offer`，再把 `framer.preamble/block` 全部 `extend` 进 list，最后返回（`stream.py:504-521`）；调用点 `stream.py:302-315` 在离开 narrow `try` 后才 yield。keepalive 在 `stream.py:323-328` 先执行 `cue = framer.keepalive()`，离开 narrow `try` 后才 yield。

`/tmp/probe_stream_athrow.py` 同时测 public `stream_delivery` 与 private `_deliver` 的 commit/keepalive suspension point：

```text
public commit first event: event: message_start
public commit raised identity: True ConsumerThrown
public commit handed: []
private commit first event: event: message_start
private commit athrow returned: event: content_block_start
private commit handed identity: 1 True ConsumerThrown
public keepalive first: : ping
public keepalive raised identity: True ConsumerThrown
private keepalive first: : ping
private keepalive classified upstream: True
private keepalive next raised identity: True ConsumerThrown
```

public consumer 实际停在 `stream_delivery` 唯一的 outer yield（`stream.py:251-254`），`athrow()` 原样向外抛且通过 `aclosing` 用 `GeneratorExit` 关闭 inner，根本不进入 `raised_here`。直接向 private `_deliver` 注入普通 `Exception` 时，outer try 会接住并按 upstream 走，但仍没有误标为 `raised_here`；`_deliver` 只有 public wrapper 一个生产 caller。这个 private 结果也再次说明“未标记”不等于“确属 upstream”，但不推翻窄 marker 的 yield-safety 论证。

### 3．`UPSTREAM` fallback 的跨模块不变量

**裁定：**（i）“只有 `not ours` 调用 hand-over”这一语法事实成立；“所以 error 不是本侧造成”这一语义不变量不成立，M2 的 SSE reader probe 是当前调用链反例。（ii）没有第二个 production `hand_back_block` caller，但当前 caller 已可带入未标记的本侧错误；另一 `_hand_over` 调用只传 `error=None`。（iii）未来新增 caller 不会触发任何现有 guard、类型错误或 test failure；只有注释会被违反。

### 4．22之三的 reachability 与剩余符号

**裁定：三件套确实 dead，未发现 dynamic wiring，也没有多归档；`a00f5a2` 却漏提交两处 deletion，且剩余三个符号只有 adapter 真 live。** 详情见 B1 与 m1。

### 5．测试鉴别力

- H2 mapping：有鉴别力，独立移除 `H2Error` 后目标 test 按预期红；control 绿。
- `_commit` marker：新增 framing tests 的 mechanism 对得上，且不是恒真断言。
- keepalive marker：无鉴别力，移除 marker 后 141 条 delivery unit tests 全绿，见 m2。
- hand-over fallback：integration test 有鉴别力，独立变异后按 category 红。
- archive boundary：test 本身有鉴别力，正是它在 exact `a00f5a2` 把漏删 module 打红；问题是此前 green 跑在带 staged deletion 的工作树，不是提交树。
- `DecodingError` carrier：不是手写 stand-in；h2 当前环境的 `httpx2/_decoders.py` 有 9 个 `raise DecodingError`，且 inheritance 判断成立。前提断言会在 classifier 学会命名它时出声。
- 没有发现新增断言因空 body 或同源 expected 而恒真；framing error-frame test 先断言具体 `proxy_delivery_failed` 与 `INTERNAL`，再断言不含 `UPSTREAM`，不会因空输出假绿。

### 6．新增注释、docstring、archive README 的事实核对

重复断言按事实命题合并如下；每个新增事实性主张都落在其中一行。

| 新增事实命题 | 裁定 | 证据 |
|---|---|---|
| httpcore2 body path 的 `receive_data` 在 socket-read `try` 外，httpx2 对未知 exception 原样抛 | 已确认 | `httpcore2/_async/http2.py:401-427`、`:537-552`；调查报告与 h2 GOAWAY PoC |
| 同一 GOAWAY 的分读形态为 `RemoteProtocolError`，同读且 GOAWAY 在后续 DATA 前时为裸 `ProtocolError` | 已确认并保留条件 | `260820-h2-goaway-poc.md:15,19,155-174`；不能删掉“同读且帧序如此”的条件 |
| 全部 h2 exception 都是 peer frame 的 account | 已推翻 | M1；10 个 local public-API trigger |
| `_commit` 返回 list，framer 调用早于第一个 yield；keepalive 先命名再 yield | 已确认 | `stream.py:301-328,504-521`；`athrow` probe |
| marker 覆盖本侧在 loop 中运行的所有代码 | 已推翻 | `_events_with_ping/read_events/claim/cleanup` 在 marker 外；M2 probe |
| only `not ours` reaches error hand-over | 语法上已确认 | `stream.py:382-386`；唯一 production call chain |
| 因此 hand-over error by construction 不是本侧错误 | 已推翻 | M2 probe；provenance 没进入 API |
| `httpx2.DecodingError` 有 9 个 raise site，继承 `RequestError` 而非 `TransportError` | 已确认 | installed `httpx2/_decoders.py:124,130,147,153,196,210,250,256,274`；class MRO |
| `CopilotUpstream` 无实例化点，目标 `UpstreamTarget` 已归档，live provider 直接用 `GhcApiClient` | 已确认 | exact-commit grep、provider registry 与 `src/app/model_provider/github_copilot.py:139-173` |
| `send_responses_headers` 与 transport classifier 的唯一调用链 | 已确认 | exact-commit symbol search；未发现 dynamic wiring |
| 三件套与 10 条 archived tests 已从 `a00f5a2` live tree 离开 | 已推翻 | B1 的 `git ls-tree` 与 exact-commit pytest |
| `transport.py` 是整棵树唯一记录 dependency defect 的地方 | 已推翻 | n1 的两个反例 |
| `GitHubTokenSourceAdapter` 与两个 header wrappers 都被 live client 使用 | adapter 已确认；两个 wrappers 已推翻 | m1 的 caller inventory |
| `GhcApiClient._in_pipeline_terms` 当前没有 send method opt out | 已确认 | `client.py` 各 public send method 均经该 helper；删除的 headers variant 是唯一旧例外 |
| archive 默认不在 import path，只有主动加 `src/.archived` 才进入解析面 | 已确认 | `pyproject.toml:54-68` 与 module-boundary probe；但 archive 是记录，不据此声称每个切片可独立运行 |

## 验证记录

当前工作树的用户指定子集：

```text
uv run pytest tests/unit/pipeline/delivery tests/unit/model_provider tests/int/test_pipeline_app.py tests/unit/test_module_boundaries.py -q --no-cov
329 passed in 48.68s
```

这条绿只证明当前叠加态；B1 的 exact-commit fixture 独立证明 `a00f5a2` 自己不绿。未重跑用户已给出的全量、Ruff 或 Pyright。

本次只写本报告与 `/tmp` 探针／fixture；未修改源代码、测试、Git index 或两个被评提交。评审期间主工作树已有 staged deletion 与其他并行文件，本报告没有接管或归因那些改动。

## 第二轮：`1b733bc` 与 `62a457f`

第二轮评审日期：2026-08-23。对象限定为 `1b733bc5e23f6178a08620195a188406f3d02e99` 与 `62a457fe238b22b9ca4631a64b56475b00ab9572`，只回答协调者指定的 `_UpstreamSource` 关闭／取消、反转后 `ours` 的双向归因、以及 `H2Error` 两个成立条件与守卫覆盖面。

### 第二轮 verdict

**needs-fix**。第二轮新增发现为 **0 blocker、2 major、0 minor、1 nit**。B1 已确认闭合；但 M2 的正向识别边界放在 production local wrappers 之外，仍会把本侧 `_counted_upstream` bug 交接成 upstream；M1 所依赖的第二个条件也不是事实，且新 AST guard 有可运行的等价 import 绕法。

### R2-M1．major：`_UpstreamSource` 正向识别的是整条 composite iterator，不是 raw upstream；production `_counted_upstream` bug 仍被标成 upstream、被 hand-over 吞成 clean return

**结论权重：强到需要继续修 M2。** 反转方向是对的，但边界放高了一层。`_deliver` 在 `src/app/pipeline/delivery/stream.py:307-318` 包住收到的 `chunks`；production 传入的 `chunks` 不是 `response.aiter_bytes()` 本身，而是 `with_client_deadline_at(_counted_upstream(with_deadline_at(with_idle_timeout(response.aiter_bytes()))))`（`src/app/server/routes/inference.py:445-459`）。因此 `_UpstreamSource.__anext__` 看见的不只有 raw upstream exception，也包括这些本侧 wrappers 自己抛出的 coding error。

`_counted_upstream` 明确是本侧代码：它在 `inference.py:609-632` 更新时间、`RequestTrace` 与 `ActiveRequestRegistry` 后才 yield。探针 `/tmp/probe_upstream_source_round2.py` 使用真实 `_counted_upstream` production function，让 `active_requests.add_bytes` 在第 4 个 upstream chunk 抛 `LocalCounterBug`；前三个 chunk 已形成并交付一个完整 block，所以 hand-over gate 可达。结果为：

```text
local wrapper handed over: 1 True
local wrapper returned cleanly: True
```

即，本侧计数 wrapper 的 bug 被 `_UpstreamSource.tear` 正向标成 upstream，随后进入 continuation，调用方既拿不到原异常，也不会留下 proxy failure。新增 SSE reader 与 keepalive tests 都在 `_UpstreamSource` **上方**制造本侧错误，所以会绿；它们没有覆盖 raw source 与 production wrappers 的 seam。

反方向也做了正样本：raw source 在一个完整 block 后抛出同一个 `ConnectionError`，经过真实 `_counted_upstream` 后 hand-over 收到的仍是同一 object：

```text
raw upstream handed identity: 1 True
raw upstream returned cleanly: True
```

因此第二轮没有发现“正常 raw upstream `Exception` 被误判 ours”的反例；坏掉的是 local wrapper → upstream 这一向。修复应把正向标记放到 raw response source 的真实边界，或让每个有意代表 upstream condition 的 guard 显式携带 provenance；不能把整条含本侧处理的 composite iterator 当成 peer。

### R2-M2．major：`H2Error` 族级映射仍建立在一个假条件与一个可绕过守卫上

**结论权重：强到需要继续修 M1。** 当前 app tree 确实只 import `h2.events` 与 `h2.exceptions`，这一个当前态事实成立；但 `errors.py:40-45` 的第二条件“request phase converts local h2；one gap is body `receive_data`”没有覆盖 httpcore body 上其他本地 h2 API 调用。

`httpcore2/_async/http2.py:286-300` 在 response body 里对每个 `DataReceived` 调 `self._h2_state.acknowledge_received_data(amount, stream_id)`；它不在 request-phase `except ProtocolError`（`:125-167`）内，也不在 `_read_incoming_data` 的 socket-read `try` 内。用真实 `AsyncHTTP2Connection._receive_response_body`、真实 h2 state 与一个故意不一致的 httpcore event ledger 构造 dependency-local state bug，得到：

```text
body_local_h2_escape= h2.exceptions NoSuchStreamError '3'
traceback_functions= ['main', '_receive_response_body', 'acknowledge_received_data', '_get_stream_by_id']
normalized= UpstreamError network
```

这不是正常 traffic 频率的证据，而是对全称条件的反例：**在 app 不驱动 h2 的前提下，bare local `H2Error` 仍能从 httpcore body bookkeeping 冒出，而且当前 normalizer 会把 dependency/local invariant bug 写成 network retry。** `AsyncHTTP2Connection.aclose()` 也在 request-phase converter 外调用 `_h2_state.close_connection()`（`:392-397`）；当前 h2 对已关闭连接的这一调用可正常返回，所以本轮没有把它登记为独立缺陷，但它进一步说明 `receive_data` 不是唯一 h2 interaction。

新 AST guard 同样不能承担“未来 app 一旦 drive h2 就必响”的承诺。它只拒绝五个 exact module strings，既漏 `from h2 import connection`，也漏 `h2.settings`、`h2.utilities`、dynamic import，以及不 import h2 而经 httpcore private object 调 `_h2_state`。在 exact `62a457f` 的 `/tmp` fixture 中加入真实 driver：

```python
from h2 import connection as _guard_bypass_connection
_guard_bypass_driver = _guard_bypass_connection.H2Connection()
```

独立 presence probe 确认 AST 中同时存在该 import 与 `H2Connection()` call，守卫仍绿：

```text
fixture= /tmp/ghc-review-h2-guard-bypass.lfJ9Nw
bypass_imports= [('h2', ['connection'])]
h2_driver_calls= ['_guard_bypass_connection.H2Connection']
1 passed in 0.36s
```

所以 M1 的族级映射目前仍没有与模块 docstring 的 closed-set 原则相称的来源判据。即使继续保留 architecture guard，也应至少按 allowlist 检查全部 `h2.*` import spellings，而不是列五个 module；但这个守卫本身仍证明不了 httpcore body 中每个 h2 call 的归因。

### R2-N1．nit，可 deferred：两处新 rationale 又把“可这样写”写成了“只能这样写”

`_UpstreamSource` 采用 class 的实现本身安全，但 `stream.py:222` 的“a generator would put the tagging try around a yield”不是必然：async generator 可以只把 `await source.__anext__()` 放在 narrow `try` 中，离开 `try` 后再 yield，和第一轮确认过的 `_commit`／keepalive 写法同理。另有 `tests/unit/pipeline/delivery/test_stream_delivery.py:1241-1244` 称 framing 修后 keepalive 又“was left out”；`0ca87b9` 的 production marker 已包含 keepalive，第一轮 m2 找到的是**缺 regression test**，不是 production marker 仍遗漏。两项都不影响当前行为，可 deferred 到下一次触碰这些 docstrings 时修正。

### 指定三问的直接答复

1. **关闭与取消语义：通过。** `_UpstreamSource` 保存 `source.__aiter__()` 返回的实际 iterator，`aclose()` 委托给同一个对象；`read_events` 的 `finally` 关闭它（`sse_source.py:64-86`）；`finish_stream_cleanup` 先 cancel-and-observe in-flight pull，再关闭 reader，避免 active `__anext__` 与 `aclose` 并发（`streaming/keepalive.py:68-134`）。`CancelledError` 不被 `except Exception` 标记。直接探针输出 `cancel tagged as tear: False`、`cancel closed source: [True]`。四条既有 close/cancel tests 与两条新增归因 tests、本轮 module-boundary/normalization tests 合计 `11 passed in 5.16s`。未发现委托链、重复关闭或 `finish_stream_cleanup` 交互的 blocker/major。
2. **反转后 `ours` 双向：一向通过，一向仍错。** raw upstream `Exception` 穿过 production wrapper 后 identity 保持并正确交接；本侧 SSE reader、framer、keepalive 也正确判 ours。反例是 `_UpstreamSource` 下方的本侧 wrapper：真实 `_counted_upstream` bug 被误判 upstream 并 clean hand-over，见 R2-M1。
3. **M1 两条件与守卫：不足以支撑。** 当前 app 不 drive h2 是事实，但 AST guard 可绕；“body 只有 `receive_data` 一处裸 h2 gap”被真实 `_receive_response_body → acknowledge_received_data` 的 bare local `NoSuchStreamError` 反例推翻，见 R2-M2。

### 原六条处置复核

- **B1 已闭合。** `git ls-tree -r 1b733bc` 在四个相关 path 中只剩 `src/.archived/.../transport.py` 与 `tests/.archived/.../test_pre_header_retry.py`；exact commit fixture `/tmp/ghc-review-b1-round2.NHkTNZ` 跑 `tests/unit/test_module_boundaries.py` 为 `3 passed in 2.27s`。
- **m1 处置可接受。** 两个 header wrappers 的现状已改成实测措辞并登记待裁，没有擅自扩大既有归档裁决。
- **m2 的缺测试已补。** keepalive 与 SSE reader 两条新 tests 本身有鉴别力；R2-M1 是它们未覆盖的 production seam，不是否定这两条测试。
- **n1 已闭合。** “only place in tree”已收窄为唯一 handler，并明确列出另外两处 prose record。
- **M1、M2 未闭合。** 原因分别是 R2-M2 与 R2-M1。

第二轮未重跑全量、Ruff 或 Pyright；沿用协调者给出的 `1543 passed, 2 skipped` 与 Ruff 绿作为工作前提。那条 `test_session_liveness_preserves_upstream_order_after_silence` 单次失败有明确墙钟竞态形状，且与本轮路径无共享状态；本轮没有用它支持或否定任何归因结论，也没有扩大为本轮 finding。

## 第三轮：`9c4ba6c` 与 `.dev@d230bde`

第三轮评审日期：2026-08-23。对象是主仓 `9c4ba6c7e05be10b68cd758f24fb0133e4f3630f` 与 `.dev` 仓 `d230bdede7f2e649b03805d7f89501749be336ca`。本轮专门复核“R2-M1 不是回归”、收窄后的全部事实性理由、h2 白名单守卫，以及第二轮两个 major 是否可以登记待裁而不立即改 API／行为。

### 第三轮 verdict

**needs-fix**。第三轮发现为 **0 blocker、2 major、2 minor、0 nit**。第 1 点“不是反转引入的回归”已由 exact pre-inversion commit 实测确认；R2-M1 的行为修复可以登记待用户裁决。未通过的是 h2 的唯一保留理由与守卫能力：dependency-local `H2Error` 在已交付 block 后不会“花预算然后浮出来”，而会零预算 hand-over 并 clean return；白名单也允许本仓直接构造／抛出 allowlisted `H2Error`，守卫仍绿。

### R3-M1．major：`errors.py` 保留族级映射的唯一理由“spends the budget and then surfaces”被真实 hand-over 路径反例推翻

**结论权重：强到必须先改正理由，再把行为取舍交给用户；不要求本提交擅自改 API。** `errors.py:45` 与 `deferred.md` §22之七把 dependency-local h2 invariant bug 和本仓 bug 区分开的依据写成：前者映射为 network 后会“spends the budget and then surfaces”，后者若装成 retryable 会“never surfaces”。控制流没有这个区别。

`decide_stream_ending()` 只在 `downstream_opened=False` 时调用 `ledger.take()`（`src/app/pipeline/retry.py:138-143`）；一旦完整 block 已交付，直接 `ABANDON`，**不花预算**（`:145-158`）。随后 `ours=False` 进入 hand-over；只要 continuation 可用且 `committed_count>0`，delivery 返回 clean，原异常既不上抛，也不留 proxy failure。这与 R2-M1 本侧 counter bug 的结局逐字同形。

本轮把第二轮的真实 `AsyncHTTP2Connection._receive_response_body → acknowledge_received_data → NoSuchStreamError` 反例延长到一个已提交 block 的 production delivery ending：先让真实 body method 产出三个合法 Anthropic SSE frames，再破坏 dependency event/h2 ledger，使第四个 `DataReceived` 在 `acknowledge_received_data` 抛本地 `NoSuchStreamError`。结果：

```text
handed_count= 1
handed_type= h2.exceptions NoSuchStreamError
returned_cleanly= True
contains_proxy_failure= False
```

因此“then surfaces”并非只是措辞略松，而是保留族级 mapping 的唯一比较理由不成立。在 client 尚未收到 block、replay budget 最终耗尽且 hand-over gate 不开时，异常的确会浮出；这只是一种位置条件，不能写成该类错误的命运。反过来，本仓 bug 若被同样标成 network，在相同位置也会走相同预算／hand-over 分支，并不存在“dependency bug 会浮出、ours 永不浮出”的结构差别。

行为是否接受仍是产品裁决：dependency-local invariant bug 与本仓 bug 的责任边界确实不同，用户可以决定把第三方 transport 内部 bug 视为 network；但当前代码和 `.dev` 文档必须如实写出代价是“可能透明 replay，也可能被 hand-over 吞成 upstream”，不能用已被控制流推翻的“最终会浮出”替它下结论。

### R3-M2．major：白名单只约束 static import module，连 allowlisted exception 的本地构造／抛出都看不见；“新拼法默认失败”与限定范围仍过头

**结论权重：强到需要修守卫或收窄守卫承诺。** 四种已测 import spelling 的确都会红，但守卫允许 `h2.exceptions`，并没有分析 allowlisted symbol 被如何使用。于是本仓无需 import `h2.connection`、无需碰 httpcore private `_h2_state`，只要用已经允许的 `H2Error` 造一个本地异常，就立即破坏“bare H2Error 不可能来自本仓”的第一条件。

在 exact `9c4ba6c` fixture `/tmp/ghc-review-h2-allowlist-bypass.WK7LYu` 的 live `errors.py` 追加：

```python
def _guard_bypass_local_h2_bug() -> None:
    raise H2Error("our local h2-shaped bug")
```

独立 AST presence probe 确认 raise 已存在；`test_no_live_module_drives_h2_itself` 仍为 `1 passed in 0.28s`。实际调用该函数后，当前 normalizer 的结果为：

```text
local_error= h2.exceptions H2Error
normalized= UpstreamError network
```

这不是 docstring 已披露的“经 httpcore private `_h2_state`、不 import h2”盲区，而是**经 allowlisted import 直接使用 h2 exception**。另有 `importlib.import_module("h2.connection")`／`__import__` 等 dynamic import 同样不产生 `ast.Import`／`ast.ImportFrom`，也不在现有限定里。故 `tests/unit/test_module_boundaries.py:101-115` 的“new spelling fails by default”与 test 名称“no live module drives h2 itself”都强于实际能力。

可以选择两种处理之一：增强判据以覆盖 allowlisted symbols 的值级使用并明确 dynamic/private 盲区；或更诚实地把 test 改名、改 docstring 为“静态 import 只允许这三个 type modules”，不再声称它 pin 住“本仓不驱动／不产生 H2Error”。后者不建新证明系统，也足以保留这道廉价 architecture signal；但不能继续拿它当族级 mapping 的完整成立条件。

### R3-m1．minor，可 deferred：production wrapper 数量与“唯一修法”仍写得过满

`_UpstreamSource` 新 docstring 称 production raw response “under three wrappers: two guards … and `_counted_upstream`”。实际 production expression 是 `with_client_deadline_at(_counted_upstream(with_deadline_at(with_idle_timeout(response.aiter_bytes()))))`（`inference.py:445-459`）：**三个 guards 加一个 counter，共四层**。其中 attempt deadline 与 idle timeout 表示 upstream condition；client deadline 有自己的优先分支，确实不靠 `ours` 决定，但它仍是 `_UpstreamSource` 包住的 wrapper。

同一 docstring 与 `deferred.md` §22之六把“caller 指出 raw source、改变 `stream_delivery` signature、再认定两个 guard types”写成 closing seam 的正确做法。它是合理候选，不是结构上唯一做法：例如 `_counted_upstream` 自己把本侧 coding error 包进明确 local provenance，或把带 marker 的 source record 穿过 wrappers，都可保留现有外层入口。此项不改变当前行为，可 deferred；在给用户方案比较时应写成“候选及代价”，不要写成唯一必要路径。

### R3-m2．minor，建议随本轮文档一起改：`internal` 时间线又把“写下时就错”转述成“写下时为真”

第一轮已查定：`internal`“结构上不可达”那句话是在前提被 `78be0d4` 拆掉**之后**才由 `a8862e6` 写下，故“文档写下时就已经错了”。`9c4ba6c` 与 `d230bde` 的 commit message 却称两次都是“a sentence that was true when written”；`.dev` README 新段末尾又说一天内“两次让一份『刚核实过』的描述失效”。第一次不是失效，也不是写下时为真；只有第二次“四值都可达”是后来被 fallback 改动使其过期。

README 中间对两次时间线的详细叙述本身是正确的，错误在总结句与两个 commit message。运行契约“error category 当前只有 `network`／`upstream`／`auth`，`internal` 不再可发”已核对成立。此项不影响行为，但主题正在把这段时间线当方法学教训保存，建议现在修 summary，避免把教训反向改写。

### 第 1 点：“不是回归”的独立复核

**确认成立，强到可据此把 R2-M1 记作 pre-existing seam，而不是 attribution inversion regression。** 本轮从 exact `0ca87b9` 解包到 `/tmp/ghc-review-pre-inversion.gmecK1`，presence probe 确认加载的 `_deliver` 含 `raised_here` 且不含 `_UpstreamSource`。随后以真实 `_counted_upstream` 让 `active_requests.add_bytes` 在第 4 个 chunk 抛 `LocalCounterBug`，结果为：

```text
handed_count= 1
handed_local_counter_bug= True
returned_cleanly= True
contains_upstream_error_frame= False
```

在当前 `9c4ba6c` 对同一探针复跑，四行逐值相同。原因也与代码直读一致：反转前 `LocalCounterBug` 既不是 `DeliveryError`，也不可能等于只在 assembler／commit／keepalive 内赋值的 `raised_here`，所以 `ours=False`；反转后它从 composite iterator 的 `__anext__` 冒出，与 `upstream.tear` identity 相同，仍是 `ours=False`。反转改变了 marker 方向，没有改变这条接缝的结局。

### 第二轮两个 major 是否可以登记而不立即修行为

- **R2-M1：可以。** 它不是本次反转引入的回归，完整修复会改变 provenance contract；将真实后果、候选修法与取舍登记给用户裁决，符合不擅自扩 scope。前提是不得再把现有 `ours` 描述成双向精确；`9c4ba6c` 已做到，除 R3-m1 的数量／唯一修法措辞外不阻断。
- **R2-M2 的行为：也可以等待用户裁决。** 用户可以接受“第三方 transport 内部 invariant bug 也按 network”这一边界。但**当前理由与守卫不能原样通过**：R3-M1 证明它未必浮出，R3-M2 证明第一条件没有被该 test pin 住。修正这两项不要求现在改族级 mapping；只是把尚待用户裁决的选择写成尚待裁决，而不是已经证明 sound。

### 第三轮验证记录

- exact pre-inversion `0ca87b9` counter probe与当前 probe：四项结果逐值相同，确认“不是回归”。
- exact `9c4ba6c` allowlist bypass：本地 `raise H2Error(...)` 已确认存在，守卫仍绿，调用后被 normalize 为 `UpstreamError/network`。
- current targeted tests：module-boundary 全文件、H2 normalization case、keepalive 与 SSE reader attribution cases，共 `7 passed in 6.73s`。
- 沿用协调者给出的 Ruff、全量 `1543 passed, 2 skipped`、exact-commit affected subset `332 passed`，本轮未重复全量。

本轮仅追加本报告并创建 `/tmp` fixture／探针；未修改主仓、`.dev` living docs、Git index 或被评提交。

## 第四轮：`1a34042` 与 `.dev@f7dff22`

第四轮评审日期：2026-08-24。对象是主仓 `1a34042411a5c5593317d1677e3f86066f464422` 与 `.dev` 仓 `f7dff223efa4693efadc7d3e15e7c2b1895551b9`。本轮按协调者指定范围复核 marker 四层位置、公开 `UpstreamSource` 生命周期、`Attempt` 契约、两条新测试与忠实变异、以及 private-index hunk 切分。

### 第四轮 verdict

**needs-fix**。第四轮发现为 **0 blocker、2 major、1 minor**。marker 的归因层位与 fresh-per-replay identity 正确，两条新测试都有鉴别力，`Attempt` 没有漏实现方，exact commit 也没有夹带同伴的 error-envelope hunks；但 production close chain 在 `_counted_upstream` 处中断，client close 后 raw upstream 不会被关闭；此外 h2 residue 只在 hand-over 位置新增了 cause，transparent replay 成功时仍只留下 `retries=1`，`.dev` 所称“这类失败会在完成行留下类型与消息”不成立。

### R4-M1．major：production composite 的关闭链在 `_counted_upstream` 截断，`UpstreamSource.aclose()` 与 raw response 在 client close 后都无人调用

**结论权重：强到需要修复并新增 production-layering close regression。** 这不是 `1a34042` 新引入的行为回归——对 parent commit 的同形探针结果相同——但公开 marker、跨 replay 传递之后，生命周期审查明确暴露了一个当前存在的 release defect，不能用“关闭语义没动”当作已验证。

生产组合是：

```text
with_client_deadline_at(
    _counted_upstream(
        UpstreamSource(
            with_deadline_at(with_idle_timeout(raw_response))
        )
    )
)
```

`read_events` close outer composite；client deadline 的 `_bounded.finally` close `_counted_upstream`。但 `_counted_upstream` 只有 bare `async for`，没有 `aclosing`／`finally` 委托 close（`inference.py:609-632`）。关闭到这里停止，marker 下方的 attempt deadline、idle timeout 与 raw response 都没有收到 `aclose()`。现有 close tests 通过 `delivering(...)` 把 marker 与 composite 设为同一对象，结构上看不见 production 的这一层。

在 exact `1a34042` fixture `/tmp/ghc-review-round4-exact.SJZygg` 中，本轮用真实四层组合、真实 `_counted_upstream`，让 raw source 产出一个完整 block 后保持一个外部强引用，随后关闭 delivery。结果：

```text
before_close= []
immediately_after_close= []
after_one_tick= []
after_explicit_raw_close= [True]
```

所以这不是“collector 晚一 tick”——只要 owner 仍持有 source，它就一直开着。对 exact parent `1a34042^` 运行旧 API 的同形组合，四行结果相同，说明是 pre-existing close seam；但 `UpstreamSource.aclose()` 的 docstring“read_events closes the byte stream under it”在 production 不成立。

取消路径要区分：client deadline 真正触发时，`asyncio.timeout` 的 cancellation 会沿 counted → marker → guards → raw 传播，因此本轮 probe 得到 `marker_tear_is_none=True`、`client_deadline_frame=True`、`raw_closed=[True]`。坏的是普通 client early-close／GeneratorExit：它关闭每层自身，却没有 cancellation 穿过 counted 的当前 `anext`，而 counted 又不委托 close。

建议最小方向是让 `_counted_upstream` 像相邻 wrappers 一样显式关闭它消费的 iterator，或由 delivery 在 composite settle 后显式 close 每次 attempt 的 marker；必须保证先 settle in-flight pull 再 close。修后应把 production 四层 close case放在 integration 或真实组合 unit test中，不能再只测 `marker is composite` 的 fixture。

### R4-M2．major：h2 residue 仍可经 transparent replay 静默消失；`handed_over_error` 只修 hand-over，不支持“这类失败都会在完成行留下类型与消息”

**结论权重：强到需要修行为或收窄 `.dev` 的完成声明。** `handed_over_error` 对已交付 block 后的 hand-over 生效，测试也有鉴别力；但 network-classified `H2Error` 在 client 尚未见到 block 时会透明 replay。若新 attempt 成功，既不 hand-over，也不 re-raise：`accounting.handed_over_error` 与 `failure` 都保持 `None`，完成行只有 attempt count，没有原异常的类型／消息。

exact `1a34042` 已有的 `test_a_replay_is_reported_on_the_request_line` 展示这一机制：第一次 `RemoteProtocolError`，第二次成功，完成行是：

```text
[ OK ] H1/H1 200 anthropic-messages/claude-model … end_turn retries=1
```

本轮再用 bare `h2.exceptions.ProtocolError("local dependency ledger broke")` 走同一个真实 served replay，得到：

```text
status= ok
attempts= 2
record_contains_h2_cause= False
```

因此 `f7dff22` §22之七的“这类失败……会在完成行上留下它的类型与消息”、README 的“交接是唯一会吞掉异常的结局”、commit message 的“h2 residue … no longer silent”都只对**hand-over 位置**成立。transparent replay 本来就以 client 无痕为目标，但“client 无痕”不等于“operator completion record 不记 cause”；是否要记录 replay cause 是产品／观测取舍，至少不能把只覆盖 hand-over 的改动写成整个 h2 residue 已有类型与消息。

另一个反例是 terminal 已见后的 tear：`stream.py:366-372` 直接 `break`，也不 re-raise；项目此前已把它登记为 post-terminal failure 无痕。所以 hand-over 不是“唯一吞异常的结局”。这不否定新增字段的价值，只否定其覆盖面的全称描述。

### R4-m1．minor：private-index 没夹带 error envelope，但漏了 predicate 旁两段属于本次的旧注释

exact `1a34042^..1a34042` 的 `inference.py`／`test_pipeline_app.py` changed lines只涉及 marker layering、`Attempt`、hand-over accounting、对应 tests／helpers；没有 `error_body`、dialect envelope、upstream error bytes等同伴语义。相邻的 envelope 工作分别完整落在 `249c894`、`3533386` 与之后的 `c4216f7`，本提交没有把它们的 hunk 重新记入自己。30 个 test-side `stream_delivery(...)` 旧调用均被迁移；commit tree 只剩 3 个 direct calls，全部显式传 `upstream=`。

但 `src/app/pipeline/delivery/stream.py:375-378` 仍写着已经不存在的 `_UpstreamSource`，并称“converse does not hold yet”“`_counted_upstream` still reads as upstream”“deferred §22之六”。`1a34042` 已把这条 seam 修掉，`.dev@f7dff22` 也把 §22之六 标为已修；这是 private-index 切分中漏掉的本次自有同步 hunk。行为不受影响，但应随修复更正。

### 指定五问的直接答复

1. **marker 层位：归因上正确。** attempt deadline 与 idle timeout 的异常按既有 `replay_reason` 代表 upstream condition，放在 marker 下；`_counted_upstream` 是本侧记账，放在 marker 上；client deadline 是整轮本地 lifetime，放最外且由 `ClientDeadlineError` 早退分支处理。本轮实测 client deadline 不设置 `upstream.tear`。如果未来删除专门分支，它会因 `torn is not upstream.tear` 落 `ours=True`、不 replay／不 hand-over并 re-raise，归因上 fail-local；现有两条 client-deadline tests 会为 wire 行为变化出声。生命周期另见 R4-M1。
2. **公开 API 生命周期：identity 正确，close ownership 不正确。** 调用方构造 marker 后，production composite确实迭代同一对象；replay 返回 fresh marker，`_deliver` 同时替换 `chunks, upstream, assembler, buffer`，不会把上一 attempt 的 `tear` 当成下一次。问题是 composite close 到不了 marker，raw response 会漏，见 R4-M1。
3. **`Attempt` 实现方：未漏。** 全仓 `ReplaySupport` provider 只有 production `_reopen`、unit `_replay_over`、以及一个永远返回 `None` 的 test reopen；前两者都返回四元组并各造 fresh marker，后者无 tuple。全仓 direct `stream_delivery` calls也全部显式传 marker。
4. **测试鉴别力：两条都通过。** 本轮 runtime monkeypatch重做两种 marker 变异：错误构造 `marker=UpstreamSource(composite)` 但仍迭代原 `composite` 时，marker 从未执行、`tear` 恒空，integration test 为 `1 passed`并记录 FAIL 行——协调者所说“第一次变异构造错了”成立。忠实变异改为同时迭代并传入同一个 whole-composite marker，测试按预期红，日志为 `turn handed back … after LookupError(...)`。删除 `accounting.handed_over_error = error` 后，第二条测试在 `RemoteProtocolError` 断言红，印出旧 completion line。两条 green 均有分辨力；它们未覆盖 R4-M1/R4-M2 的相邻路径。
5. **private-index：无同伴 error-envelope 夹带，`Attempt`／call-site 迁移无漏；有一处自有注释漏同步。** 详见 R4-m1。

### 第四轮验证记录

- exact `1a34042` targeted：marker unit、served placement、hand-over cause、replay、close、pull-in-flight、两条 client-deadline，共 `8 passed in 2.30s`。
- faithful whole-composite marker mutation：placement integration test红，打印 `turn handed back … after LookupError(...)`；uniterated-marker 错误 mutation 同 test 绿，确认首次变异为何无鉴别力。
- 删除 hand-over error assignment：cause test按预期红并印出旧行。
- production 四层 close probe：raw source在 delivery close 后仍未关闭；parent commit 同形，确认非本次新回归。
- bare h2 transparent replay probe：请求成功、attempts=2、completion record不含 cause。
- 沿用协调者给出的全量 `1634 passed, 2 skipped` 与 Ruff 结果；本轮未重跑全量。

本轮仅追加本报告并创建 `/tmp` exact-commit fixture／探针／runtime mutation plugin；未修改主仓、`.dev` living docs、Git index 或被评提交。

## 第五轮：`93c4bab`、`0062b67` 与 `.dev@494c68f`

第五轮评审日期：2026-08-24。对象是主仓 `93c4babc3e7eea35c9b9a10898a165dc4a6626d7`、`0062b6753f571bc9202a86100085a8077391455b` 与 `.dev` 仓 `494c68fc7f1f217911daba151c6c5aa25411d694`。主仓运行证据全部来自 `git archive 0062b67` 解出的 `/tmp/ghc-review-r5-0062b67.05G57T`，没有读取工作树叠加态作为提交事实；文档逐格核对来自 `.dev@494c68f` 的 `/tmp/ghc-review-r5-dotdev-494c68f.bjk9Fb`。

### 第五轮 verdict

**needs-fix**。第五轮发现为 **0 blocker、2 major、1 minor、1 nit**。R4-M1 的普通 early-close 漏释放已经闭合，取消时也确实先让在飞 pull 退栈再关闭，真实完整组合只关闭 raw 一次；但新 `finally` 没有沿用本文件已有的 primary-before-cleanup 规则，一旦 `aclose()` 自己失败就会改写原异常，真实组合里甚至能让 byte-counter bug 从 exception chain 完全消失。R4-M2 的单次透明重放也已留下 cause；但只留第一条使第二次及后续不同失败继续无痕，且 replacement attempt 自己失败时会出现「实际发了两次、record 仍是 `attempts=1` 且 `replaced_failure=None`」。文档把这一位置写成已经覆盖，仍然过头。

### R5-M1．major：`_counted_upstream.finally` 在 close 失败时会改写 primary；真实 wrapper 组合可把原异常从 chain 完全抹掉，取消也会变成普通 close error

**结论权重：强到需要修正异常优先级；不否定 close delegation 本身。** `inference.py:661-680` 在 `finally` 里直接 `await close()`，没有保存 `sys.exception()`。这与同文件 `_AccountedStreamingResponse.__call__` 明写并实现的「原退出优先，close failure 作 cause」（`:638-645`），以及 `finish_stream_cleanup` 的「primary、cleanup cancellation、cleanup failure」顺序（`streaming/keepalive.py:50-67,69-115`）相反。

直接 iterator 探针先给出基线：close 成功时原异常 identity 保持；close 失败时 Python 用 close error 替换原异常：

```text
pull_error_close_ok raised=PrimaryError same_primary=True close_calls=1
pull_error_close_fails raised=CloseError same_close=True context_is_primary=True close_calls=1
```

更关键的是 production 形状。`/tmp/probe_r5_close_rewrites_counter_bug.py` 使用 `with_client_deadline_at(_counted_upstream(UpstreamSource(with_deadline_at(with_idle_timeout(raw)))))`；raw 先交出一个 chunk，真实 `_counted_upstream` 的 registry call 抛 `CounterError`，随后 raw 的 `aclose` 抛 `CloseError`。结果不是带 cause 的替换，而是原 counter bug 从 chain 彻底消失：

```text
raised=CloseError same_close=True counter_in_context=False context_chain=['CloseError', 'GeneratorExit'] raw_close_calls=1 marker_tear=None
```

原因是 lower async generator 收到 `aclose()` 注入的 `GeneratorExit` 后在自己的 `finally` 抛出 `CloseError`；这个新异常带的是那一层的 `GeneratorExit` context，而不是外层正在传播的 `CounterError`。于是完成行、分类和调用方都只见 close error，恰好违背本文件 `:638-645` 已经写明的优先级。

取消路径也不是「`finally` 中的 await 会立即再次被取消」。一次 `task.cancel()` 到达后，`await close()` 正常运行；探针让 close 故意阻塞，task 在 close 完成前保持未完成，close 观察到 inner pull 已经退栈。close 成功后原 `CancelledError` 继续传播；close 失败时取消被 `CloseError` 替换，task 不再是 cancelled：

```text
cancel_during_close task_done_while_close_blocked=False close_calls=1 close_saw_pull_active=[False]
cancel_after_close raised=CancelledError task_cancelled=True close_calls=1
cancel_close_fails raised=CloseError context_is_cancelled=True task_cancelled=False close_calls=1
```

所以「取消会沿链传播」只能在 cleanup 成功的条件下成立，`93c4bab` commit message 与 `_counted_upstream` docstring 的无条件说法过强。修法应与本文件已有的 `_AccountedStreamingResponse`／`finish_stream_cleanup` 同序保留 primary，并把 close error 链在其下；不是撤掉委托关闭。

### R5-M2．major：第一条 cause 不能代表多次重放，且失败的 replacement attempt 连「发生过」都读不出来；`None` 与覆盖面文档的语义均过强

**结论权重：强到需要改记录行为或明确收窄契约与文档。** `inference.py:423-429` 只在 `_reopen` 已经拿到一份成功的 streaming response 后写字段，且 `if trace.replaced_failure is None` 永远保留第一条。默认 network budget 允许 9 次、总 budget 允许 20 次（`config/schema.py:142-151`）；代码没有保证后续失败与第一次同类型、同消息或同责任方，所以 `0062b67` 注释的「later attempt failing the same way says nothing new」只是未检查的假设。

真实 served 三次尝试探针把第二次失败设成这一节正在追踪的 bare `h2.exceptions.ProtocolError`，第三次成功。结果是成功记录只留下第一次 `RemoteProtocolError`，第二次 h2 residue 仍完全无痕：

```text
[ OK ] ... retries=2 after RemoteProtocolError('first peer closed')
status=200 calls=3 attempts=3 replaced_failure="RemoteProtocolError('first peer closed')" contains_first=True contains_second_h2=False contains_h2_type=False
```

这直接反驳 `.dev@494c68f` `README.md:50` 对「透明重放成功」整个位置的完成表述，以及 `deferred.md:354,360` 所称该格／前三格已不再不可见。第一条可以解释**第一次** replacement，不能解释 `retries=2` 中第二次为何发生；若第二次正是 h2 residue，本轮文档宣称可见的对象仍不可见。

另一个真实入口探针让第一次 body tear 触发 replay，第二次新 upstream request 在 response headers 处得到 400。确实发出了两个 upstream request，但 `_reopen` 在写 `trace.attempts`／`replaced_failure` 之前返回 `None`（`inference.py:413-429`），最终记录为：

```text
calls=2 raised=RemoteProtocolError attempts=1 replaced_failure=None detail='stream failed before a terminal event: first body tore'
```

因此恒在 key 的**结构选择是对的**：`RequestTrace → RequestLine → asdict` 让每条新 record 都显式带 `replaced_failure`（`request_trace.py:153-155,202-246`、`request_log_file.py:31-41`），`None` 比缺 key 可读。但它不能无条件定义成「没重放过」；当前最多表示「没有一份成功 replacement 被安装并记录」。这不是反对恒在字段，而是要求字段注释、attempt count 与实际 replay lifecycle 对齐。

### R5-m1．minor：新增 replay test 只咬住 structured storage，console rendering 与 `0062b67` 的长度接线都可被删掉而指定测试集全绿

**结论权重：足以补两条小而直接的 regression，不否定当前实现输出。** 删除 `trace.replaced_failure = one_line(repr(replacing))` 后，`test_a_replay_is_reported_on_the_request_line` 确实按 cause 断言变红；所以 storage 路径有鉴别力。但测试只读 `_records()`（`test_pipeline_app.py:3143-3147`），没有读它名称所称的 request line。隔离 fixture 中删除 `format_completion_line` 的 `after {line.replaced_failure}` 分支，runtime presence probe 确认加载的函数已无该分支，用户指定三组测试仍为：

```text
373 passed in 50.33s
```

`0062b67` 的长度接线同样未被现有 helper test 与 integration test 的组合覆盖。把 production assignment 从 `one_line(repr(replacing))` 忠实变异回 `repr(replacing)`，runtime probe 输出 `bounded_assignment_present=False`、`unbounded_assignment_present=True`；用户指定三组再加 `tests/unit/pipeline/test_hand_over_message.py` 仍为：

```text
399 passed in 54.77s
```

实现本身经 10,029-character 输入探针是正确的：`one_line` 输出 260 characters、无换行、尾部明确写 `(+9789 more chars)`。缺的是把长 cause 从 `_reopen` 一直钉到 structured record／console line 的一条测试；只测 helper 与只测短 cause 是 seam 两边各绿、接线可断。

### R5-N1．nit：close regression 抓得到本次缺陷，但「composes what production composes」不是提交事实——它漏了最外层 client deadline

`test_stream_delivery.py:1348-1353` 实际组合是 `_counted_upstream(UpstreamSource(with_deadline_at(with_idle_timeout(raw))))`；production 在 `inference.py:490-500` 还以 `with_client_deadline_at(...)` 包在 counter 外。故新 test docstring `:1325-1330` 与 `93c4bab` commit message 的「Production stacks four」「new one composes what production composes」写得过满。它仍忠实击中本次机制：删除 counter 的 close delegation 后，前提断言继续通过、最后 `assert closed == [True]` 以 `[]` 变红。完整 production 组合则由本轮独立探针验证通过，所以这是 coverage／事实措辞，不是又一条当前 leak。

### 指定六问的直接答复

1. **`_counted_upstream.finally`：普通 close 修复成立；异常优先级不成立。**（i）close 成功时原异常不吞不改；close 失败时会替换原异常，真实 wrapper 组合还可把原异常完全移出 chain，见 R5-M1。（ii）一次取消到达后，`finally` 里的 await 会跑完；完整组合中 close 只在 inner pull 已退栈后开始，不与「先 settle pull 再 close」冲突。cleanup 失败会改写 cancellation，仍属 R5-M1。（iii）完整生产组合经 `finish_stream_cleanup` 取消、随后再显式 close composite 与 marker，raw `aclose` 总计只调用 1 次；这些 async-generator wrappers 的重复 `aclose` 是幂等的，未发现生产重复关闭缺陷。
2. **`reopen` 契约实现方无漏；第一条取舍不足以支持当前表述。** exact tree 中唯一三个 provider 是 production `_reopen`、unit `_replay_over.reopen`、terminal test 的 counting `reopen`；五个 `ReplaySupport(...)` construction 里另两个复用前者，唯一消费点以 `replay.reopen(torn)` 传参。373 条目标测试通过。多次 replay 的不同后续 cause 会丢，见 R5-M2。
3. **恒在字段与「缺席不可读」原则一致，但 `None` 的解释要收窄。** JSON `null` 明确表达「本字段未记录 successful replacement cause」，优于 key 缺席；它不等于「没有新 upstream attempt」，两请求／`attempts=1`／`None` 的反例见 R5-M2。
4. **close test 的主判据有鉴别力，前提断言不是恒真 oracle。** 删除 close delegation 后，`assert closed == []` 仍通过而最终 `[True]` 断言红，说明它只是确认「close 动作前仍开着」，真正 discriminator 是动作后的状态。若 source 提前关闭，前提本身会红；若 source 根本未运行，最终断言会红。测试未覆盖外层 client deadline，见 R5-N1。Replay test 对 storage assignment 有鉴别力，但不覆盖 rendering／长度，见 R5-m1。
5. **`.dev` 两行与四格：两格成立、一格需限定、一格成立但总括句过头。** README `:50` 的 hand-over 与**第一次 successful replay cause**成立，但「两处都留下原因」不能覆盖同一位置的后续 replay；`:51` 的 post-terminal tear 仍无痕成立。`deferred.md:353` 交接格成立；`:354` 单次 replay 成立，多次只留第一条；`:355` 原 failure 上抛成立，failed replacement 自己及真实 attempt count仍不可读；`:356` post-terminal 无痕成立。`:360`「前三格已经不再是看不见的问题」因此仍过头。
6. **新增事实性断言不是全都已确认。** 逐类裁定见下表；未列出的纯设计取舍与历史复述不冒充运行事实。

| `93c4bab`／`0062b67` 新增事实命题 | 裁定 | 证据 |
|---|---|---|
| bare counter 截断 close chain；委托后 ordinary early-close 同 tick 释放 raw | 已确认 | close regression 的忠实删除变异由 `[True]` 退为 `[]`；本轮完整组合 probe |
| cancellation 始终传播，所以 client-deadline path 从不受此类问题影响 | **已收窄** | cleanup 成功时成立；close failure 时 `CloseError` 替换 `CancelledError`，见 R5-M1 |
| `finally` 委托与「先 settle in-flight pull 再 close」相容 | 已确认 | `close_saw_pull_active=[False]`；cleanup 阻塞时 pending 未 done，close 完成后才 settle |
| 多层委托不会重复关闭 production raw | 已确认 | cancellation + finish cleanup + repeated explicit close 后 `raw_close_calls=1` |
| new close test composes production 的完整 stack | **已推翻但仅影响测试表述** | test 漏 `with_client_deadline_at`，见 R5-N1 |
| 单次 transparent replay success 此前只有 count；现在 record 与 line 有 first cause | 已确认 | assignment 删除变异红；真实两次尝试输出 cause；rendering 代码直读与直接运行 |
| 第一条 failure 解释全部 retry count，后续失败「same way」无新增信息 | **已推翻** | 三次尝试里第二条 bare h2 cause 不同且无痕，见 R5-M2 |
| `None` 表示没重放过 | **已收窄** | 只能表示没有 successful replacement cause 被安装；真实 `calls=2, attempts=1, replaced_failure=None` |
| `one_line` 给 replay cause 与 hand-over link 同一字符上限并写明裁掉多少 | 已确认 | 10,029 → 260 characters、无 newline、`(+9789 more chars)`；`hand_over.py:56-71` |
| 新 tests 覆盖 close 与 replay completion-line 行为 | **部分确认** | close 与 storage assignment mutation 红；删除 rendering 仍 373 绿，移除 bound 仍 399 绿，见 R5-m1 |

### 第五轮验证记录

- exact `0062b67` 用户指定三组：`tests/unit/pipeline/delivery`、`tests/int/test_pipeline_app.py`、`tests/unit/observability`，`373 passed in 50.17s`。
- close delegation 忠实删除变异：目标 test 在最后 `assert [] == [True]` 红；`assert closed == []` 前提通过。
- replay storage assignment 删除变异：目标 integration test 在 `record["replaced_failure"] is None` 红。
- replay console-render branch 删除变异：runtime 确认加载 mutation，三组 `373 passed`，证明 presentation seam 未被钉住。
- replay bound 改回 raw `repr`：runtime 确认加载 mutation，三组加 hand-over message tests `399 passed`，证明长度接线未被钉住。
- close／cancel probe：close 成功保留 primary；close failure 替换 primary/cancellation；完整组合先 settle pull、raw close 一次。
- multi-replay probe：三次 upstream call，第二次 bare h2 cause，最终成功 record 只含第一条 cause。
- failed replacement probe：两次 upstream call，第二次 400，最终 `attempts=1`、`replaced_failure=None`。
- 未重跑全量、Ruff 或 Pyright；沿用协调者给出的全量 `1635 passed, 2 skipped` 与 21 条无关 pyright errors 作为工作前提。

本轮只追加本报告并创建 `/tmp` exact-commit fixtures／探针／mutations；未修改主仓源代码、测试、Git index 或 `.dev` living docs。
