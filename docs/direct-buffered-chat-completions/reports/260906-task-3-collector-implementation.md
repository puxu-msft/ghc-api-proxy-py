# Task 3 collector implementation report

## 状态与基线

- 状态：实现与本任务验证已完成，等待上级会话独立评审与集成。
- 权威source base：`92ac5643985d0b28fb1d94bbce3d5eb24abcfc44`。
- 实现commit：`c712e86400c463b8ae32809b28eaa9e8d711eb33`（`feat: collect buffered upstream attempts`）。
- 分支：`worktree-agent-a1f635178f07a0b7b`。
- 隔离worktree：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a1f635178f07a0b7b`。
- Worktree证明：repository top-level与物理路径均为上述目录，metadata dir为主仓`.git/worktrees/agent-a1f635178f07a0b7b`，common metadata dir为主仓`.git`，初始HEAD精确等于权威base。

## 实现范围

1. `src/app/pipeline/delivery/sse_source.py`新增`RawFrameProposal`与`RawSseFrameDecoder.propose_one_bounded()`。每次最多返回一个完整frame，未返回suffix仍由caller持有；chunk末尾歧义CR继续staging，`feed_bounded()`仅作为legacy／`read_events()`兼容wrapper。
2. 新增`src/app/pipeline/delivery/buffered_transaction.py`，定义typed `BufferedProtocolState`、`BufferedEnding`、mutable `BufferedMemoryAccount`、`BufferedAttemptResult`与single-attempt `BufferedAttemptCollector`。Collector逐frame执行read once→measure→reserve→apply，每次state增长后重算capacity；不引用或消费`RetryLedger`，不打开replacement，不发布attempt event。
3. Collector统一计量raw、decoder staging、protocol state、projection与observation槽；cap失败保持account事务性不变。Raw frame bytes由frame列表持有，最终`bytes` body以逻辑ownership transfer建立，避免采集期把每个frame再复制进`bytearray`。
4. Collector按正向`UpstreamSource.tear`对象identity区分transport tear与local error；显式映射idle、attempt、client deadline；使用既有cleanup helper保留primary＋cleanup异常图，并确保source close一次。`CancelledError`与`GeneratorExit`在cleanup后传播。
5. `src/app/pipeline/chat_completions/state.py`新增`BufferedAction`、`ChatAttemptDecision`、typed stream event／unterminated errors与`decide_chat_attempt()`。它只返回intent：pre-`[DONE]` network类ending建议`NETWORK` retry，known event error沿用state显式reason，unknown／unassemblable／local／cap／client deadline失败；post-`[DONE]` tail ending提交并保留具体ending。没有ledger、sleep、reopen或send。
6. 同一`ChatAttemptState`实例供decision、标准Chat projection和observation使用；projection／observation都先通过共享`BufferedMemoryAccount`预留`reservation.total_bytes`，materialize后再缩到`output_bytes`。
7. 为公共Chat接口更新`src/app/pipeline/chat_completions/__init__.py`导出；未改translated projection、provider或production wiring。

## Production-object probe

在最终candidate上使用真实`UpstreamSource`与本地async iterator执行，不访问真实provider：

- clean EOF：`ending=clean_eof`，`peak=217`，`body=127 bytes`，`done_seen=True`，close count 1。
- transport tear：`ending=transport_error`，已收20-byte partial frame保留，error identity为原`RuntimeError`，close count 1。
- cap：`ending=cap_exceeded`，未越界保留，error为`BufferCapExceeded`，close count 1。
- close failure：`ending=local_error`，完整127-byte body与`done_seen=True`保留，close count 1。

该probe证明collector ownership、ending类型、partial raw保留与close行为；不冒充ASGI wiring或真实upstream证据。

## 验证

- Brief精确pytest：`uv run pytest tests/unit/pipeline/delivery/test_buffered_attempt_collector.py tests/unit/pipeline/chat_completions/test_events.py tests/unit/pipeline/delivery/test_sse_assembly.py -q` → `112 passed in 4.38s`。
- Brief精确Ruff：`uv run ruff check src/app/pipeline/delivery/buffered_transaction.py src/app/pipeline/delivery/sse_source.py src/app/pipeline/chat_completions/state.py tests/unit/pipeline/delivery/test_buffered_attempt_collector.py tests/unit/pipeline/chat_completions/test_events.py tests/unit/pipeline/delivery/test_sse_assembly.py` → `All checks passed!`。
- Brief精确Pyright：同一文件集合 → `0 errors, 0 warnings, 0 informations`。
- 额外Chat state回归：`uv run pytest tests/unit/pipeline/chat_completions/test_state.py -q` → `31 passed in 3.56s`。

覆盖包含：所有`BufferedEnding`、partial staging、`[DONE]`本身跨cap、同chunk `[DONE]`＋tail、同chunk A state增长后B不再fit、raw＋state联合越界、post-terminal guard矩阵、close exactly once、primary＋cleanup identity、cancellation／`GeneratorExit`传播、2,000,000-byte projection reservation、deep unknown、5,000-choice observation reservation，以及one state／one reader跨decision、aggregation、observation复用。

## 缺陷注入controls

在最终candidate上以进程内monkeypatch运行8项单变量control，均命中目标判据并输出`FIRED`：

- `pre_reject_whole_chunk`
- `zero_state_bytes`
- `append_before_check`
- `reserve_only_output`
- `fixed_64k_working`
- `zero_observation_working`
- `double_close`
- `replace_primary`

这些control证明对应本地判据能拒绝指定mutation；不冒充真实provider、ASGI接线或Task 4+ orchestration证据。

## 未做与边界

- 未实现Task 4+的driver seam、non-stream adapter、provider migration、transaction runner、replacement或observation发布。
- 未改translated projection。
- 未访问真实provider，未触碰现有4141服务，未push。
- Collector源码检索未发现`RetryLedger`、budget take、reopen、replacement、event publish或sleep调用。

## Concerns与handoff

- 按任务指令，本agent是叶子执行单元且不得派subagent，因此没有自行完成独立review；上级会话必须对commit `c712e86400c463b8ae32809b28eaa9e8d711eb33`做最终candidate review后再集成。
- Worktree中的`?? .dev`是指向主工作树`/home/xp/src/ghc-api-proxy-py/.dev`的预置symlink，只用于按指定路径更新progress／report，未进入source commit。
- 任务内没有发现需要修改Spec的新事实；实现保持在现有§5.4／§8／§9.3.1合同内。
