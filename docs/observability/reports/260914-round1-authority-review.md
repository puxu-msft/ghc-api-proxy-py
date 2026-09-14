# Round 1 authority review（复核版）

## 复核更正

上一版把共享主树 CAS 后的 stale working copy 当成代码事实，错误地报告了 Replay、RequestJournal 和 History query/archive/transport 缺失。本版不使用共享主树 `git status` 或物理路径判断；所有代码证据均来自 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 的 tree（`git show <SHA>:<path>`），文档证据来自当前 `.dev` living docs。上一版的“文件缺失” findings 全部撤销。

## 评审范围

评审对象为 observability/history/raw-capture/replay 的 current `spec.md`，observability `implementation-ledger.md`，`.dev/README.md`，raw-capture `deferred.md`，以及直接相连的 current 实现、测试和 `docs/.human-controlled/README.md` 入口。`history/archive/reports` 只作为 provenance，不作为 current authority；未修改、删除或创建其他仓库文件。

## 总体 verdict

**needs-fix**；阻断性问题：0。真实问题为 5 条 major、1 条 minor：ledger 越权承载合同事实，History archive 跨重启引用失效，RequestJournal 事件合同未覆盖，Replay result boundary 不完整，以及四个 topic 无法从入口发现。

## C1：authority 唯一性与 ledger 边界

判据侧是清楚的：`observability/spec.md:5,17`、`history/spec.md:5`、`raw-capture/spec.md:5`、`replay/spec.md:5` 声明各自 authority/边界；`.dev/README.md:24-31` 区分 living、history/archive、reports。  
但 `implementation-ledger.md:5,11-16` 在声明“以 spec 为准”后，仍把 full-header、archive state machine、query filters/cursor、credential-bearing transport、journal freeze、replay executor 等合同级事实写进“最近操作”，并将其标成 done。  
结论：**C1 不通过**，见 MAJOR-AUTH-001；ledger 应只保留状态、索引、commit/test 证据和 Spec 链接。

## C2：1–6 slices 与状态、措辞、边界

- raw capture full-header 与 v24 对齐：`raw-capture/spec.md:48-76`；committed `raw_capture.py:40-62,190-192,551-628` 保存 request/upstream/client headers，committed `test_full_header_capture.py:11-53` 覆盖未列出的 header。
- History 的 query/export、transport envelope、异步 archive 在 committed HEAD 均存在；但 `HistoryArchiveStore` 没有恢复既有 segment 的 size/编号，见 MAJOR-HISTORY-002。
- RequestJournal 与 Replay 本体存在，但分别没有实现 Spec 要求的完整事件 taxonomy/result boundary，见 MAJOR-JOURNAL-003、MAJOR-REPLAY-004。

## C3：design-only、v23、旧路径或“当前未实现”说法

未发现把历史状态直接冒充 current 合同的 major：`replay/spec.md:108` 的 design-only 在 revision record，`raw-capture/spec.md:109` 与 `raw-capture/deferred.md:3` 明确是 v23 历史，`history/spec.md:5` 明确标注 `src/.archived/` 为旧实现；定向 `rg` 只命中这些带限定语的 provenance/current-boundary 句子。  
但 `observability/spec.md:118-120` 未随已提交的 RequestJournal/History handoff 更新当前实现边界，列举仍停在旧对象集合；此项作为 minor M-001 记录，不改变 current Spec 的 authority。

## C4：living/history/archive/reports 角色与接手入口

角色定义本身清楚：`.dev/README.md:24-31`；但 inventory `.dev/README.md:33-69` 完全没有 observability、history、raw-capture、replay 四个 current topic，且规定的 topic-level `README/status/plan` 也不存在。命令输出为：`observability: spec.md implementation-ledger.md`、`history: spec.md`、`raw-capture: spec.md deferred.md`、`replay: spec.md`。  
结论：**C4 不通过**，见 MAJOR-ENTRY-005；新接手者按 README 入口无法定位本轮四份 current 合同。

## Major findings

### MAJOR-AUTH-001 — implementation ledger 承载 Spec-level truth

- `implementation-ledger.md:11-16` 不只是状态/索引，而是重复 archive/query/transport/journal/replay 的行为合同并给出 done 结论。
- 这与项目 workflow 的“Spec-level fact 只能落在 Spec”冲突，且会让读者把 ledger 当成第二份 authority。
- 影响：ledger 的“最近操作/已完成”可绕过 current Spec，掩盖实现仍有边界或缺口。
- 修复边界：保留 task、状态、commit/test 证据和 Spec 链接；合同细节移回对应 Spec。

### MAJOR-HISTORY-002 — HistoryArchiveStore 跨重启后生成错误引用

- `history/spec.md:89-113` 要求可重启、可校验的 cold segment/reference；committed `archive.py:55-59` 只在内存保存 `_segments`，初始化不扫描既有 segment。
- committed `archive.py:85-95` 每次 append 用内存 `segment.size` 生成 offset，却以 append 模式写入既有文件；重启后新引用仍从 offset `0` 记录。
- 后续 `archive.py:104-124` 按错误 offset 读并校验 digest/entry_id，History query/transport 会读到旧 frame 或报 mismatch。
- committed `test_archive.py:10-85` 只覆盖同一 store 实例的 round-trip/rollover/tamper，没有 reopen/restart case；这是 durable History 的 correctness major。

### MAJOR-JOURNAL-003 — RequestJournal 未覆盖 ACTIVE Spec 的事件合同

- `observability/spec.md:23-43,110-116` 要求 request/route/attempt/block/terminal/history projection 等 typed facts，并要求每个 attempt event 带 identity。
- committed `request_journal.py:16-24` 只有 8 个 kind；`git grep RequestJournalEventKind.` 只命中 response/delivery/upstream-response/interruption/failure/finalized，缺少 `route.selected`、attempt、block、terminal、history accepted/rejected 等。
- committed `request_journal.py:27-32` 也没有独立 attempt identity；`request_completion.py:676-681` 先记录 `FINALIZED` 并 freeze，随后 `:840-882` 才提交 History，无法再记录 Spec 要求的 projection receipt。
- 因此 slice 5 的 bounded journal/freeze 已存在，但不能标成已满足当前 RequestJournal 行为合同。

### MAJOR-REPLAY-004 — Replay result boundary 缺少 Spec 要求的 provenance facts

- `replay/spec.md:83-101` 要求 execution policy、deadline/cancel facts、outcome/delivery/client actions 及 result History entry/reference。
- committed `replay/process.py:72-107` 的 `ReplayResult` 只有 started/finished、outcome、actions、output/diagnostic；没有 execution policy、delivery、deadline/cancel 或 result History reference。
- `replay/process.py:193-250` 只把 executor output 原样放进 `output`；timeout 有结果，取消/其他 executor failure 没有统一 result/provenance boundary。
- 所以 source gate、三种 mode 和 deadline skeleton 已实现，但 ACTIVE v2 的结果合同仍未闭合。

### MAJOR-ENTRY-005 — current topic 不可从入口发现

- `.dev/README.md:33-69` 宣称 inventory 列出当前保留话题，却漏掉 observability、history、raw-capture、replay；`:71-75` 又要求接手者先从该入口定位 topic。
- 当前 topic 根目录命令输出只有：`observability: spec.md implementation-ledger.md`、`history: spec.md`、`raw-capture: spec.md deferred.md`、`replay: spec.md`，没有 README/status/plan 入口。
- `docs/.human-controlled/README.md:18` 还链接不存在的 `docs/.human-controlled/observability.md`（命令输出 `MISSING .../observability.md`）。
- 影响：living/history/archive/reports 角色虽有说明，但新接手者无法沿规定入口确认四份 current 合同。

## 可记录不修

### M-001 — observability current-boundary prose 滞后

`observability/spec.md:118-120` 仍只列 `RequestTrace`、`FinalizedRequest`、`ActiveRequestRegistry` 等旧对象，并把事实 owner/projection 接线写成后续工作；committed HEAD 已有 `RequestJournal` 与 History handoff。由于该段同时明确“当前只覆盖其中一部分”，没有制造第二 authority 或直接改变用户可观察合同，记录为 minor，下一次 Spec 修订时刷新。

## 搜索面与未覆盖面

已读取当前 `.dev` living docs、相关 History/raw-capture/observability/Replay 实现与 committed unit tests；代码核对使用 `git cat-file`、`git show`、`git grep` 针对 `30384269377cfd5f8f848ef92bb3654afda2196a`，没有使用共享主树状态或物理缺失路径作为证据。未把 history/archive/reports 当作 current authority；未操作 4141、未执行写入性仓库命令、未评 provider/translation/CommandCode 等无直接关联主题。
