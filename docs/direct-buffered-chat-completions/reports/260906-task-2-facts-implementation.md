# Task 2：Raw SSE frames 与 authoritative Chat attempt facts 实现报告

## STATUS

READY_FOR_REVIEW。Task 2已在隔离worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-afc6e2ab44a22bc36` 实现、验证并提交；因本implementer被明确禁止派subagent，独立评审留给主会话。未触碰4141、未调用真实provider、未推送，也未实现collector／retry、provider migration或TUI。

## Base／Head

- Base：`5995bbe0ac1885482e4976975c3b74d196cb7b11`
- Head：`364e3a490714c3613f7d47f149377fd069433684`
- Branch：`worktree-agent-afc6e2ab44a22bc36`
- Commit：`364e3a490714c3613f7d47f149377fd069433684 feat: model buffered Chat stream facts`

## Exact files

- `src/app/pipeline/chat_completions/__init__.py`
- `src/app/pipeline/chat_completions/events.py`
- `src/app/pipeline/chat_completions/state.py`
- `src/app/pipeline/delivery/sse_source.py`
- `src/app/pipeline/delivery/formats/openai_chat_completions.py`
- `tests/unit/pipeline/chat_completions/test_events.py`
- `tests/unit/pipeline/chat_completions/test_state.py`
- `tests/unit/pipeline/delivery/test_chat_completions_assembler.py`

`tests/unit/pipeline/delivery/test_sse_assembly.py`仅作为指定回归套件运行，未修改。

## Baseline literal probe

Production修改前运行：

`uv run --project /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-afc6e2ab44a22bc36 python /home/xp/.claude/jobs/3db40195/tmp/task2_baseline_probe.py`

Literal oracle及当时结果：

- `b"event: a\r\ndata: 1\r\n\r\nevent: b\r\ndata: 2\r\n\r\n"` → `[('a', '1'), ('b', '2')]`
- `b"event: a\rdata: one\r\revent: b\ndata: two\n\n"` → `[('a', 'one'), ('b', 'two')]`
- `b"event: x\ndata: first\ndata: second"` → `[('x', 'first\nsecond')]`

修改前输出为三组逐项相等且`literal baseline: PASS`。修改后同一literal oracle再次通过，新decoder的所有`RawSseFrame.raw`拼接逐字等于原输入。LF-only separator控制与drop-EOF-tail控制都在byte equality处按预期判红；该证据只证明本地parser兼容性，不冒充provider行为。

## Production behavior

- `RawSseFrameDecoder`在`memoryview`上逐frame查找，输出immutable `RawSseFrame`／`RawFrameFeed`，保留原始separator、half-open offsets、ordinal与terminated状态；bounded feed只接受`consumed`前缀，越界frame不留在decoder staging中，`finish()`至多交付一个unterminated EOF remainder并清空buffer。
- `read_events()`改为适配raw decoder输出，保留既有CRLF／LF／CR、multiline data及EOF-tail行为。
- `ChatEventReader`使用stdlib strict JSON路径，按event name `error`、top-level `error`、flat `type == "error"`的顺序先识别carrier，再解释普通chunk；known transient code／type仅在同一transient class时产生`RetryReason.SERVER_ERROR`，unknown／conflict／malformed均保留为terminal nonretry facts。
- `ChatAttemptState`按choice index及`(choice index, tool index)`维护同一份decision／aggregation／observation事实；第一条合法`[DONE]`冻结semantic state，后续frame不再改变snapshot或projection。
- 标准non-stream projection保留所有choices并按index排序；实现first identity／conflict、closed last-explicit-wins集合、content／refusal／reasoning／legacy function arguments／tool arguments连接、tool排序、finish consistency、last usage、logprobs数组连接、unknown same-value retention与conflict `unassemblable`，不合成id／created／model，不输出SDK helper字段或stream-only tool index。
- `held_bytes`及prospective `additional_held_bytes()`覆盖累计字符串、frozen structured values与retained issues；projection／observation提供独立size方法。
- Existing translated `ChatCompletionsAssembler`维持原public signature与single-projection state，只复用`ChatEventReader`的decoded facts；它没有采用direct multi-choice state、`[DONE]` success contract或TUI projection。Error carrier即使同时含`choices`也不再落入普通chunk。

## Tests／commands／results

- Production-only probe先于新增tests运行：标准两choice／tool／usage projection、semantic freeze、error-carrier precedence及size接口通过。
- 在reader-specific tests加入前先跑existing translated assembler suite：`11 passed in 0.35s`。
- `uv run pytest tests/unit/pipeline/chat_completions/test_events.py tests/unit/pipeline/chat_completions/test_state.py tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_chat_completions_assembler.py -q`：`96 passed in 2.15s`。
- `uv run ruff check src/app/pipeline/chat_completions src/app/pipeline/delivery/sse_source.py src/app/pipeline/delivery/formats/openai_chat_completions.py tests/unit/pipeline/chat_completions tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_chat_completions_assembler.py`：`All checks passed!`。
- `uv run pyright src/app/pipeline/chat_completions src/app/pipeline/delivery/sse_source.py src/app/pipeline/delivery/formats/openai_chat_completions.py tests/unit/pipeline/chat_completions tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_chat_completions_assembler.py`：`0 errors, 0 warnings, 0 informations`。
- 四个single-variable mutation controls均判红并以SHA-256核对恢复：移除freeze guard使post-`[DONE]` snapshot equality失败；恢复`error and not choices`使carrier-with-choices在`ERROR` kind断言失败；从`RawSseFrame.raw`删除separator使literal raw equality失败；只输出choice 0使完整two-choice object equality在choices集合处失败。

## Self-review

- Raw fidelity与translated projection依赖方向分离：decoder不解释Chat；reader/state不改raw；translated assembler只读取facts并维持既有block state。
- Error precedence逐项复核：event-name error优先于`[DONE]`文本；nested error优先于choices；flat error被识别；unknown、malformed与conflicting transient classes均不会产生`NETWORK`或retry reason。
- Semantic freeze逐项复核：`DONE`与error carrier均终止semantic mutation；post-terminal raw保留职责留给后续collector，不进入本Task state。
- Projection逐项复核§9.3.1：identity、object、closed last-explicit fields、choice／tool排序、role synthesis、three string accumulators、legacy function call、logprobs、finish reason、usage及各层unknown均有实现与focused tests；semantic-equal unknown object不因key order不同误判冲突。
- Scope复核：提交只含Task 2列出的八个实际变更文件；`.dev` symlink未提交；未改变translated multi-choice projection。

## Concerns

- 本Task只产出facts与projection；`ChatEventFacts.error_values`保留rate-limit spelling，而event-rate-limit limiter入口及typed failure由后续Task 3／5／6消费，本提交未越界实现。
- `projection_size_bytes()`与`observation_size_bytes()`给出最终serialized／frozen logical size；后续collector仍必须在materialization前用同一个memory account预留并按ownership transfer释放，才能兑现整体cap合同。
- 用户明确禁止本implementer派subagent，因此本报告只有self-review与mutation controls，没有独立agent review；主会话应按既定计划安排独立review。

## 未采用路线

- 未用重构后的`read_events()`互相比对作为oracle；保留修改前literal table为独立authority。
- 未用OpenAI SDK accumulator生成production输出；SDK不是行为authority。
- 未让`ChatCompletionsAssembler`兼任direct state；两者terminal、multi-choice与loss语义不同。
- 未在SSE decoder解释Chat，也未从synthetic completion body重解析observation。
- 未把server error与rate-limit spelling仅因共享`RetryReason.SERVER_ERROR`预算而视为同一transient class；混合值仍为conflict且不retry。
- 未实现collector、retry orchestration、provider migration、TUI或任何真实provider调用。

## Fix round 1／5 — 2026-09-06

### STATUS

READY_FOR_REREVIEW。以下记录追加并取代上文对candidate HEAD与未闭合concerns的描述；原始实现记录保留为reviewed revision的点时证据。

### Base／Head／commit

- 原始base：`5995bbe0ac1885482e4976975c3b74d196cb7b11`。
- 被评revision：`364e3a490714c3613f7d47f149377fd069433684`。
- Fix-round HEAD：`b417bf6508e65eb72195ebb71fbc79550dcf33d3`。
- 新commit：`b417bf6508e65eb72195ebb71fbc79550dcf33d3 fix: preserve exact buffered Chat facts`。

### Review disposition

评审`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/reports/260906-task-2-facts-review.md`中的2 blocker／11 major／1 minor全部采纳并处理：

1. `task-2-facts-review-01`（blocker）：chunk末歧义CR延迟到下一byte或EOF判定；全量长度0～8 one-byte split oracle通过。
2. `task-2-facts-review-10`（blocker）：`ChatEventFacts.value`改为显式`JsonObservation`；null、observed non-object与unreadable不再共享裸`None`。
3. `task-2-facts-review-02`（major）：所有retained unknown mapping统一计入UTF-8 key bytes与recursive FrozenJson value size；100000-byte top/tool/function keys均进入prospective与held计量。
4. `task-2-facts-review-03`（major）：移除`deepcopy`与size阶段的projection／snapshot materialization；prospective sizing使用只复制被触及mutable metadata且共享payload values的sizing view，projection与observation size均直接递归计数。
5. `task-2-facts-review-04`（major）：FrozenJson改为递归value equality，对象key order无关，不经过受64-bit限制的serializer；重复`10**100`保留成功且delta为0。
6. `task-2-facts-review-05`（major）：projection size与最终bytes共用stdlib `JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))`语义；`1e-7`、Unicode、escaping与big integer同Starlette `JSONResponse.body`逐字／长度一致。
7. `task-2-facts-review-06`（major）：`logprobs.content`／`refusal`各自维护absent／null／array；only-null、null→empty-array与array→null均按合同投影。
8. `task-2-facts-review-07`（major）：state与snapshot保存首个semantic terminal的`semantic_end_offset`、`error_values`及`error_retry_reason`，后续frame不覆盖。
9. `task-2-facts-review-08`（major）：新增immutable `ChatUnattributedFact`，非法choice／tool index保存完整可读value、ordinal、half-open offsets与field path；exception带对应provenance。
10. `task-2-facts-review-09`（major）：snapshot把`choice_unknown`／`message_unknown`及`tool_unknown`／`function_unknown`分槽；choice-level reserved `message` collision在observe阶段记issue并使adaptation unassemblable，两层raw facts均保留。
11. `task-2-facts-review-11`（major）：usage区分absent、explicit null、empty object、zero、wrong standard field type与inconsistent；null不清除last-object projection，conversion issues带稳定code与frame-qualified path。
12. `task-2-facts-review-12`（major）：error carrier与taxonomy在whole-value freeze前识别；包含`1e400` future字段的known error仍保留ERROR、spellings与retry reason，whole value记UNREADABLE；ordinary对应输入成为unassemblable。
13. `task-2-facts-review-14`（major）：`RawSseFrame`只持有`raw` bytes，`body_end`与`memoryview`提供parse范围；near-cap测试断言`body.obj is raw`。
14. `task-2-facts-review-13`（minor）：增加installed OpenAI `ChatCompletionStreamState`标准known-field differential正例，覆盖logprobs null与tool calls；比较边界显式排除SDK-only `parsed`／`parsed_arguments`及stream-only tool `index`，production不依赖SDK accumulator。

### Exact files changed in fix round

- `src/app/pipeline/chat_completions/__init__.py`
- `src/app/pipeline/chat_completions/events.py`
- `src/app/pipeline/chat_completions/state.py`
- `src/app/pipeline/delivery/sse_source.py`
- `src/app/pipeline/delivery/formats/openai_chat_completions.py`
- `tests/unit/pipeline/chat_completions/test_events.py`
- `tests/unit/pipeline/chat_completions/test_state.py`

### Verification

- 更新后的production-only probe：all-byte CRLF、JSON availability、carrier-before-freeze、recursive big integer、large unknown-key sizing、two-phase stdlib sizing、invalid-index provenance、logprobs tri-state与usage states全部通过。
- 独立穷举probe：长度0～8、字母表`x/CR/LF`、逐byte transport chunks与完整输入separator oracle一致。
- Task 2 exact pytest：`121 passed in 2.42s`（committed HEAD复跑）。
- Task 2 exact Ruff：`All checks passed!`（committed HEAD复跑）。
- Task 2 exact Pyright：`0 errors, 0 warnings, 0 informations`（committed HEAD复跑）。
- 18项mutation controls全部在目标断言判红并以SHA-256核对恢复：ambiguous CR、single frame bytes、freeze、error-with-choices、raw separator、all choices、prospective allocation、unknown-key size、big-int equality、stdlib float size、carrier-before-freeze、JSON null availability、layered unknown、error reason、error end、invalid-index provenance、logprobs null与usage null。

### Self-review／concerns

- Task 2提供facts与两阶段size→materialize接口，不实现Task 3 collector的account owner；后续collector必须先reserve返回的size，再调用`to_completion_payload()`／`to_completion_bytes()`或`observation_facts()`。
- Rate-limit与server-error共用现有`RetryReason.SERVER_ERROR`预算，但原始spellings完整保留，后续owner可据spellings触发独立limiter signal。
- `finish()`在EOF把此前因歧义而延迟的terminal bare CR判为separator时会返回`terminated=True`；普通EOF remainder仍为`terminated=False`。这是chunk-invariant SSE语义所必需，且由exhaustive oracle覆盖。
- 本implementer不得派subagent，因此修订candidate仍需原评审者复评；未执行merge、push、worktree清理或临时文件删除。

### 本轮未采用路线

- 未把cap遗漏交给Task 3补偿，也未保留`deepcopy`／whole-projection预量。
- 未用orjson做FrozenJson equality或final projection size。
- 未把unknown层级压入共享mapping，也未丢弃invalid-index raw facts。
- 未让OpenAI SDK进入production依赖或决定unknown／conflict行为。
- 未改变translated multi-choice projection，未实现collector／retry、provider migration或TUI。

## Fix round 2／5 — 2026-09-06

### STATUS

READY_FOR_REREVIEW。Fix round 1复评关闭原14项中的13项；唯一未关闭的`task-2-facts-review-03`已在新commit处理。

### Commit

- `e42fc7660a656bc53a1ee7ea06e920b555d2a1f5` — `fix: reserve Chat materialization memory`

### Finding 03处置

- `additional_held_bytes()`不再clone retained state。它只从incoming facts建立独立incoming-state ledger，再把该ledger与current field ledger逐字段合并计量；existing choice／tool的字符串、FrozenJson与容器均不复制，跨state的first-value／concat／unknown／usage规则由同一字段语义直接计算delta。
- 新增immutable `MaterializationReservation(working_copy_bytes, output_bytes)`及`total_bytes`。`projection_reservation()`和`observation_reservation()`均不调用payload／snapshot materializer或whole repr。
- `to_completion_bytes(reservation)`校验reservation仍匹配当前state，并通过incremental chunk writer直接从state生成最终bytes；不构造completion mapping，不连接2,000,000-byte content string，也不构造完整JSON string。Working reservation覆盖预分配writer buffer及其有界结构开销，output reservation覆盖返回bytes；Task 3可按`reserve total → materialize → release working`接入。
- 保留`to_completion_payload()`供既有component接口使用，但cap-aware路径的两阶段契约是`projection_reservation()`→reserve→`to_completion_bytes(reservation)`。Observation对应为`observation_reservation()`→reserve→`observation_facts(reservation)`。

### Evidence

- 2,000,000-byte content：`state=2000088, working=2065703, output=2000167, total=4065870, tracemalloc peak=4007960`，reservation total覆盖实测peak。
- 2,000,000-byte reasoning observation：`state=2000098, working=0, output=2000214, total=2000214, tracemalloc peak=2696`，reservation total覆盖实测peak。
- Materializer sentinel tests证明`additional_held_bytes()`、`projection_reservation()`与`observation_reservation()`在预量阶段不调用`deepcopy`、`thaw_json`、payload builder或snapshot builder。
- 200-case deterministic projection probe逐字对照Starlette `JSONResponse.body`通过；prospective delta fuzz 500步逐次满足`before + delta == after`。
- Task 2 exact pytest：`123 passed in 10.08s`。Ruff：clean。Pyright：0 errors。
- 19项mutation controls全部按目标判红并恢复；其中把`projection_reservation().working_copy_bytes`归零后，2,000,000-byte probe以`peak=4028968 > reserved total=2000180`判红。

### Concerns

- 本round严格只处理finding 03及其测试面，未改动已关闭13项的语义，也未扩大到Task 3 collector。
- Tracemalloc数字绑定当前CPython 3.14.2与本worktree；它证明本地materializer peak被reservation覆盖，不外推其它runtime。
- 仍等待原评审者对`b417bf6..e42fc76` scoped复评；未合并、未推送、未清理worktree或job scratch。

## Fix round 3／5 — 2026-09-06

### STATUS

READY_FOR_REREVIEW。Fix round 2 scoped review确认13／14项已关闭且无新Critical／Important；本轮只处理仍未关闭的`task-2-facts-review-03` residual A／B。

### Commit

- `0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f` — `fix: account Chat materialization structure`

### Residual A：prospective delta

`additional_held_bytes()`现在使用`_ProspectiveSizer`直接读取current field ledger与incoming FrozenJson，并按同一event内choice／tool出现顺序更新稀疏overlay。它不创建fresh/collapsed `ChatAttemptState`，不复制retained choice／tool metadata，也不调用`thaw_json`、payload或snapshot materializer。新增三组`current=B; incoming=A,B`回归，分别覆盖choice finish、tool id/name与unknown value，均逐项断言`before + delta == after`及目标conflict数量。500-step deterministic delta fuzz继续通过。

### Residual B：two-phase materialization reservation

新增并导出`MaterializationReservation(working_copy_bytes, output_bytes)`，以及`projection_reservation()`／`observation_reservation()`。两者以递归logical encoded-byte counter计算，不构造payload、snapshot或whole repr；working reservation不再使用fixed 64KiB或zero guess，而与对应output的完整结构、keys、punctuation、nesting及record count同量增长。

`to_completion_bytes(reservation)`先核对reservation与当前state一致，再直接从state通过incremental stdlib-compatible chunks写入预定尺寸buffer；不构造completion mapping、不连接整段content／reasoning／arguments，也不生成whole JSON string。Task 3可按`reserve total → materialize → release working`顺序接入。`observation_facts(reservation)`同样支持reservation一致性校验。

Ruling口径已落实：这些数字是与`DeliveryUnit.size_bytes`一致的同时存活representation logical encoded bytes，不声称CPython allocator或tracemalloc上界。此前Fix round 2报告中的tracemalloc叙述由本段取代。

### Evidence

- 2,000,000-byte content：projection reservation `working=2000167, output=2000167, total=4000334`，两份同时存活logical representation均被计入。
- 100层nested unknown：projection reservation total由shallow `378`增长为deep `778`，证明不是fixed overhead。
- 5000个small choices：observation reservation total由single-choice `318`增长为`218060`，证明不是zero／fixed working。
- Reservation与materializer sentinel测试证明预量阶段不调用`deepcopy`、`thaw_json`、payload builder或snapshot builder。
- 22项mutation controls均按目标判红并逐次SHA-256恢复；本轮新增same-event overlay collapse、only-output reservation、fixed 64KiB projection working与zero observation working controls。
- Task 2 exact pytest：`127 passed in 4.44s`。Ruff：clean。Pyright：0 errors。

### Concerns

- 本轮只改`src/app/pipeline/chat_completions/state.py`及`tests/unit/pipeline/chat_completions/test_state.py`，其余13项已关闭行为未改。
- Logical reservation依据2026-09-06用户ruling，不再以tracemalloc allocator peak作为验收或对外声称。
- 等待原评审者对`e42fc76..0a7c9ce` scoped复评；未合并、未推送、未清理worktree或job scratch。

## Fix round 4／5 — 2026-09-06

### STATUS

READY_FOR_REREVIEW。Fix round 3 scoped review确认Residual B已关闭、Residual A只剩current retained `FrozenJsonObject.items` mapping metadata copy；本轮仅处理该剩余项。

### Cherry-pick lineage／commit

- 当前主线base：`abdfd5493a5532197a642a60e4d4a7cd6dc564b5`。
- Source Task 2 lineage：`364e3a490714c3613f7d47f149377fd069433684` → `b417bf6508e65eb72195ebb71fbc79550dcf33d3` → `e42fc7660a656bc53a1ee7ea06e920b555d2a1f5` → `0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f`。
- Local cherry-pick lineage：`8c3e33c` → `44b5458` → `14c82df` → `9dc8611`；四次cherry-pick均无冲突，未修改peer的observability文件。
- 新commit：`bfd9c2d952e89ee77d3c8daade19d5c2640eb4a3` — `fix: avoid cloning retained Chat JSON metadata`。

### Residual A处置

`_same_frozen_json(left, right)`的所有state merge与prospective sizing call site均以current／retained值为`left`、incoming值为`right`。Object comparison现在只把incoming `right.items`建成lookup index，先比较tuple长度，再直接迭代current `left.items`并递归维持相同方向；current side不再创建`dict`或其它完整mapping metadata副本。Array仍按原顺序逐项比较；bool仍不得与number相等；stdlib保留的arbitrary-size integer仍直接递归比较；object key order仍不参与semantic equality。

新增deep/wide control构造24层、每层24个siblings的current unknown object，收集所有retained `FrozenJsonObject.items` identity，并在prospective sizing期间以sentinel拦截任何针对这些tuple的`dict(...)`。Incoming对象逐层反转key order但value相同时delta为0；deep bool `True`→`1`与array `[1,2]`→`[2,1]`各只新增一个unknown conflict issue，每一步均断言`before + delta == after`。既有choice finish、tool id/name、unknown三组`current=B; incoming=A,B`顺序回归未改并继续通过。

### Evidence

- 正向focused equality／delta suite：`6 passed`。
- 单变量反向变异：临时恢复原`left_items = dict(left.items)`后，新增control在`current retained FrozenJsonObject.items copied`目标sentinel判红；随后从预先保存的快照恢复，恢复前后SHA-256同为`815907ec12318371d169d2f03b84afa764c79a7abe4e29d4483316b841aa03dd`。
- Committed HEAD `bfd9c2d952e89ee77d3c8daade19d5c2640eb4a3` Task 2 exact pytest：`128 passed in 4.50s`。
- Task 2 exact Ruff：`All checks passed!`。
- Task 2 exact Pyright：`0 errors, 0 warnings, 0 informations`。

### Concerns

- 本轮只修改`src/app/pipeline/chat_completions/state.py`与`tests/unit/pipeline/chat_completions/test_state.py`，没有重开其余13项已关闭finding，也没有实现Task 3。
- 等待原评审者对`0a7c9ce..bfd9c2d` scoped复评；未合并、未推送、未清理worktree或scratch。
