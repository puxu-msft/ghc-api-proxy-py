# Observability / History / Raw Capture / Replay 第一轮对抗性契约评审（复核版）

## 评审范围与证据校正

评审对象仍是当前 living docs 中的：

- `.dev/docs/observability/spec.md`
- `.dev/docs/history/spec.md`
- `.dev/docs/raw-capture/spec.md`
- `.dev/docs/replay/spec.md`
- `.dev/docs/observability/implementation-ledger.md`

按需对照了 `src/app/observability/`、`src/app/history/`、`src/app/replay/`、`src/app/server/routes/history.py` 与相关 tests。**代码事实全部按 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 的 tree 核验；不使用共享主树的 working-copy status 或物理缺失文件作为证据。文档事实按 `/home/xp/src/ghc-api-proxy-py/.dev` 当前 living docs 核验。**

初版报告的 `OBS-CONTRACT-01` 至 `OBS-CONTRACT-05` 建立在 stale working copy 上，错误地把 committed Replay、RequestJournal、History transport/archive 接线判成缺失；这些初版 findings 全部撤回，不计入本复核 verdict。以下使用新的 finding ID，避免复用已撤回的含义。

判据来源为调用方给出的 C1–C5、`.claude/rules/00-development-workflow.md`、`docs/.human-controlled/README.md` 及其中与 API、请求管线、生命周期、测试组织相关的文档。README 列出的 `docs/.human-controlled/observability.md` 在当前树中不存在，因此没有把它当作额外权威来源。

## 总体结论

**VERDICT: needs-fix**

**blocker 数：0。major 数：5。**

Committed HEAD 已包含 Replay、RequestJournal、History query/export、transport envelope 和 archive state 的主体实现；但仍有五处会改变用户可观察行为或使不同读者选择不同安全/持久化语义的 major。以下不是成本或 ROI 建议。

## 主要发现

### OBS-CONTRACT-R1-01 — Replay process 已存在，但 CLI 与 result/provenance contract 仍未达到 ACTIVE v2

- **severity:** major
- **primary_location:** `.dev/docs/replay/spec.md:5,61-97,107`
- **related_locations:** `src/app/replay/__main__.py:18-42`; `src/app/replay/process.py:46-106,118-250,253-348`
- **涉及清单:** C3、C5

**证据**

1. committed tree 确实包含 `app.replay`、`ReplayProcess`、capture-required source gate、显式 selector、wire/semantic/live executor、target policy、deadline 和新 replay identity；初版“模块缺失”判断撤回。
2. CLI parser 只接受 `--capture`、`--entry`、`--attempt`、`--deadline` 和 `--max-deadline`，`_run()` 硬编码 `UPSTREAM_ATTEMPT`、`WIRE_DIAGNOSTIC` 和 `CURRENT_ROUTE`。ACTIVE v2 所写的 semantic/live mode、`client_request` selector、original target 和对应执行策略不能由 CLI 选择。
3. `ReplayResult` 及 `as_dict()` 只记录 replay/source/target、started/finished、outcome、error、client actions、output 和 diagnostic records；没有 Spec 要求的 `delivery`、execution policy、明确 deadline/cancel facts 或 result History entry/reference。
4. `ReplayProcess` 只按调用方传入的 `max_deadline_s` 与 request deadline 比较；CLI 默认 `60.0`，没有把它绑定到全局 `upstream_request_deadline`。process 本身也没有 cancel fact/result 字段。注入 executor 不接收 source headers/credentials，这一项 current-auth 不复用边界本身是成立的，问题在于其余 result contract 没有闭合。

**影响**

“独立 process/CLI 已实现”会让调用方误以为所有 ACTIVE v2 mode 和 provenance 都可从产品面使用；实际 CLI 只能运行 wire diagnostic，而 semantic/live 的 deadline 上限、delivery/cancel 结果及新的 History provenance 仍依赖调用方隐式补齐。对高风险 live replay 而言，无法从 result 判断是否发生取消、交付为何终止、结果是否已有 History reference。

**闭合要求**

逐项让 CLI、process API、result schema 和全局 deadline/cancel 语义对齐 ACTIVE v2；或明确把未暴露部分标成未接线，不能用“process/CLI 已实现”覆盖缺口。

### OBS-CONTRACT-R1-02 — `HistoryArchiveStore` 首次重启后追加会生成不可读 reference

- **severity:** major
- **primary_location:** `.dev/docs/history/spec.md:74-113`
- **related_locations:** `.dev/docs/observability/implementation-ledger.md:12,21-23`; `src/app/history/archive.py:44-59,61-102,153-169`; `src/app/history/writer.py:483-529`
- **涉及清单:** C2、C5

**证据**

1. History Spec 把 History 定义为跨重启可查询，并要求可校验的 cold source；ledger 执行顺序明确写出“可重启、可校验的 durable source”。
2. `HistoryArchiveStore.__init__()` 只初始化进程内的空 `_segments`。`_segment_for()` 在新实例中没有现有 segment 记录时固定选择 `history-000000.history.cborseq.zst`、`number=0`、`size=0`。
3. 若该 segment 已由上一进程写过，下一次 `append()` 仍以 `offset = segment.size`（即 `0`）打开同一文件的 append stream；文件实际旧数据不会被扫描，reference 却记录新 frame 的 digest/length。随后 `read(reference)` 从文件偏移 0 读取旧 frame，必然得到 digest mismatch（或错误 entry）。

**影响**

服务重启后第一条新的 History projection 可能被标成 durable，但其 cold reference 不可读；这直接破坏跨重启 History、transport/full export 和 archive receipt 的持久化合同。现有 same-process rollover/round-trip 测试不能证明该状态，因为它们没有重新构造 `HistoryArchiveStore`。

**闭合要求**

让 archive store 在新实例首次 append 前恢复每个现有 segment 的真实编号和 size，并把尾部完整性/损坏状态纳入启动与追加合同；在此之前不能把该 source 描述为可重启 durable。

### OBS-CONTRACT-R1-03 — RequestJournal 存在，但 required event vocabulary 与 History handoff 顺序不符合 Spec

- **severity:** major
- **primary_location:** `.dev/docs/observability/spec.md:19-43,104-116`
- **related_locations:** `.dev/docs/observability/implementation-ledger.md:15`; `src/app/observability/request_journal.py:16-105`; `src/app/observability/request_completion.py:338-479,676-729,840-878`; `src/app/observability/request_log_file.py:1-75`
- **涉及清单:** C4、C5

**证据**

1. committed HEAD 已有 bounded `RequestJournal`，初版“文件不存在”判断撤回；但 `RequestJournalEventKind` 只有 `response_ready`、delivery started/finished、upstream response started/finished、interruption、failure、finalized 八类。
2. 当前 enum/recording path 没有 Spec 所列的 `request.received`/`approved`、`route.selected`、`attempt.started`/`completed`/`failed`、`transport.opened`、`conversion.warning`、block assemble/commit、`upstream.terminal`、`delivery.partial`/`uncertain`、`client.aborted` 或 `history.projection_accepted`/`rejected`。少数 attempt 字段出现在 upstream response payload 中，不能替代缺失的 event kind 与生命周期边界。
3. `publish()` 在记录 `FINALIZED` 后立即 `journal.freeze()`；随后 `_emit()` 才调用 `_submit_history_projection()`。因此 History queue accepted/rejected 不可能成为 journal 中的 request-local fact，而 Spec 又把这两类 event 列为至少应存在的事实。
4. `_emit()` 仍无条件调用 `write_finalized_record()`；`request_log_file.py` 将 JSONL 描述为 always-on 的 “Durable structured records”，按日期保留 14 天。可观测性 Spec 只允许兼容 writer 作为 History projection 的临时 shadow/export，不允许它拥有独立 durable truth。

**影响**

C4 的边界只完成了“冻结一个受限 journal”，没有完成 Spec 所要求的 route/attempt/block/handoff 事实链；读者无法从 RequestFacts 判断 History projection 是 accepted 还是 rejected。与此同时，独立 JSONL 的长期 retention 又提供了第二个持久化事实面，容易让不同 consumer 把它当作 History 的替代 truth。

**闭合要求**

补齐或明确裁定 required event vocabulary 与 handoff/freeze 顺序，并让 JSONL writer 的身份明确是临时 shadow/export 或移除其独立 durable 语义；不能以 `FinalizedRequest = RequestFacts` 或“journal 已接线”概括未覆盖的事件。

### OBS-CONTRACT-R1-04 — safe History projection 与 identity contract 在 living docs 之间互相冲突，Committed API 选择了较宽的一侧

- **severity:** major
- **primary_location:** `.dev/docs/raw-capture/spec.md:60`
- **related_locations:** `.dev/docs/history/spec.md:21-34,48-56`; `.dev/docs/observability/spec.md:85-89`; `src/app/history/writer.py:73-123,878-969`; `src/app/history/entry.py:112-148`; `src/app/server/routes/history.py:64-69,124-152`
- **涉及清单:** C1、C5

**证据**

1. raw-capture Spec 明确说 ordinary request log、History 普通 list/detail 不得复制原始 session/agent identity；History 普通 projection 只返回 metadata、semantic summary、capability 和 reference。
2. History Spec 又把 `session/agent identity` 列为每个 HistoryEntry 的稳定 identity/time projection。
3. committed `HistoryIndexEntry.as_dict()` 直接返回 `session_id`、`agent_id`；list/detail route 直接把该 dict 返回给客户端。它们不是 hash prefix 或仅用于内部 join 的 opaque key，而是 `HistoryWriter` 从 request facts 接收并持久化的原始值。
4. ordinary request log 的文本 projection 不返回这些字段，因此同一产品面确实存在“log safe、History identity-bearing”的两种边界，而不是单纯的字段命名差异。

**影响**

一个读者可以按 raw-capture Spec 认为 History list/detail 不含 raw identity，另一个读者可以按 History Spec/实际 API 认为 identity 是公开 metadata；部署层没有额外 app-level auth/RBAC 时，这会直接改变敏感数据暴露面。该冲突也使 transport/full 与 ordinary History 的 credential-sensitive boundary 无法由文档唯一推出。

**闭合要求**

必须由一条 living contract 明确定义 session/agent identity 是否属于 safe History metadata，并同步 History Spec、raw-capture Spec、History index/detail API 与 ordinary log；不能用“metadata”一词同时承载互斥的两种安全语义。

### OBS-CONTRACT-R1-05 — Capture capability 仍是 aggregate-only，Replay 的 attempt gate 还漏检 boundary completeness

- **severity:** major
- **primary_location:** `.dev/docs/raw-capture/spec.md:64-70`
- **related_locations:** `.dev/docs/history/spec.md:58-72`; `.dev/docs/replay/spec.md:20-40`; `src/app/observability/capture_observation.py:14-22`; `src/app/history/entry.py:38-46,158-170`; `src/app/history/writer.py:73-123`; `src/app/replay/process.py:110-116,276-348`
- **涉及清单:** C1、C2、C3

**证据**

1. raw-capture、History、Replay Spec 都要求 `upstream_attempts[]`，每个 attempt 独立表达 request/response/boundary completeness；History 的 stable capability matrix 也明确要求该字段。
2. committed `RawCaptureObservation` 和 `CaptureCapabilities` 仍只有 request/client-response、wire/semantic/live 的 aggregate booleans；`HistoryIndexEntry` 没有 `upstream_attempts[]`。Replay 虽然从 raw capture 临时解析 attempt records，但这个能力没有进入 History attachment/reference contract。
3. `ReplayProcess._attempt_complete()` 只检查 `upstream.request.body`、`upstream.response.start`、至少一个 `upstream.response.body` 和 `upstream.response.end(complete=true)`；它不检查该 attempt 的 `upstream.attempt.start/end` boundary，更不检查 `upstream.attempt.end(complete=true)`。因此“attempt boundary 明确为 incomplete、但 response end 恰好为 complete”的证据形态会被错误放行。
4. 这与 raw-capture Spec 对失败 attempt 与 request-level `upstream_incomplete` 的区分不等价：Spec 要保留每个 attempt 的可取证性，当前 replay gate 只用一组事件存在性近似它。

**影响**

调用方无法仅凭 History capability 判断应选择哪个 `upstream_attempt(attempt_id)`；而 Replay 对某些有显式 incomplete attempt boundary 的 source 可能返回 wire diagnostic success。这会把 aggregate “eligible” 误读成 per-attempt proof，并绕过 Spec 明确要求的 source evidence gate。

**闭合要求**

让 capture observation、History attachment/reference 和 Replay selector 共用 per-attempt capability/provenance；Replay gate 必须把 attempt boundary 纳入完整性判定，而不是只检查 response body 事件。

## Minor / nit（不计入 verdict）

无。没有把可由上述 major 自然涵盖的格式或命名问题另列为 minor。

## C1–C5 覆盖

| 清单 | 对应发现 |
|---|---|
| C1 | OBS-CONTRACT-R1-04、OBS-CONTRACT-R1-05 |
| C2 | OBS-CONTRACT-R1-02、OBS-CONTRACT-R1-04、OBS-CONTRACT-R1-05 |
| C3 | OBS-CONTRACT-R1-01、OBS-CONTRACT-R1-05 |
| C4 | OBS-CONTRACT-R1-03 |
| C5 | OBS-CONTRACT-R1-01、02、03、04 |

## 搜索面与验证

- 已重新读取五份当前 living docs，并从 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 核验 Replay、RequestJournal、raw capture、History archive/writer/entry/routes、composition wiring、相关 tests 与生命周期接线。
- 已用 committed tree 的 `git ls-tree`/`git grep`/`git show` 核验：Replay 与 RequestJournal 确实存在，History query/export/archive/transport 接线确实存在；初版关于这些文件“物理缺失”的证据已撤回。
- 本复核没有把共享主树 working-copy status、stale 文件或上一轮测试结果当作 committed HEAD 的代码证据；未执行 4141 操作，未执行 `git add` 或 `git commit`。
