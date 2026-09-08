# `.dev` direct-root final checkpoint 独立审阅

## 评审范围

- **目标 checkpoint**：`docs: re-root dotdev development documents`。
- **版本边界**：dotdev repository 当前 `HEAD` / `archive/260908-dotdev-pre-reroot` 的 `862b13748cefe3e27f8a95c7885cb3a4405345bc` 到当前 staged index。
- **被检对象**：当前 staged diff、staged direct-root 最终树、旧 `HEAD:.dev/` subtree、archive ref、active root README、repository-repair current entry、29 个 retained topic/机制目录、15 个 retired dirs、top-level `docs/tmp/`、multi-provider conflict snapshots/disposition，以及 `git diff --cached --check` 输出。
- **明确不在范围内**：主仓未阶段化的产品源码/测试变更、产品行为与 retained-topic 未完成工作的验收、commit/re-root/worktree attach 的执行。除写入本报告外，本轮未修改、移动或删除被检对象，未执行 `git add`、commit 或 push；本报告不加入 index。

## 总体 verdict

**NEEDS-FIX。** archive ref、staged scope、旧树内容迁移/删除账、root README links、retired dirs、multi-provider snapshots/disposition 与嵌套树清除均通过；但 staged Git tree 没有任何 `docs/tmp/` entry，故 checkpoint 在新 checkout/worktree 中不能保留 README 和 repair ledger 声称保留的第 29 个机制目录。另有 11 项 trailing whitespace 和 8 项 new blank line at EOF；其中至少若干是本轮新增的 migration/review report，而非 hash-preserved historical originals，不能把整个失败解释为历史保真。

## Blocker 数

**0**

## Findings

### DCR-01 — staged checkpoint 不包含所声明保留的 `docs/tmp/` 机制目录

- **severity**：major
- **status**：open；阻止本 checkpoint 作为可恢复的 direct-root 最终树提交
- **primary_location**：staged index（`git ls-files docs/tmp` 为空）
- **related_locations**：
  - `README.md:29,67`
  - `docs/dotdev-repository-repair/README.md` 的 Current ledger（“Top-level `tmp/`：机制保留，regular files=0”）
  - 当前 worktree `docs/tmp/`
- **claim**：worktree 当前确有空目录 `docs/tmp/`，所以 filesystem inventory 为 29；但 Git 不跟踪空目录，staged index 的 `docs/` 顶层只有 28 个目录，且 `.gitignore` 没有提供创建/保留该机制的 tracked carrier。提交后从 checkpoint 新建的 checkout/worktree 不会有 `docs/tmp/`。
- **evidence**：
  - `find docs -mindepth 1 -maxdepth 1 -type d` 得到 29 个目录，并确认 `docs/tmp/` 存在、top-level regular files=0。
  - `git ls-files | awk ...` 从 staged index 只能导出 28 个 `docs/` 顶层目录；`git ls-files docs/tmp` 无输出。
  - `git check-ignore -v docs/tmp docs/tmp/probe.md` 无输出；root `.gitignore` 只忽略 `exp/` 下的 Python/pytest 运行产物。
  - Git tree object 不保存空目录。因此 archive/ref 能恢复旧 ancestor，不会让 direct-root checkpoint 自动生成这个新空目录。
- **impact**：checkpoint 不能完整表达被审 README 的目标根树与“29 retained topics/机制目录”合同；后续 worktree attach 从该 commit materialize 后，第 29 个机制目录会消失，使用者只能看到声明存在但 filesystem 不存在的 `docs/tmp/`。
- **minimal_next_step**：在 `docs/tmp/` 下加入明确说明“目录是临时交换机制、文件须逐份 disposition”的 tracked placeholder/README，并将其纳入 staged checkpoint；随后重新计数 staged `docs/` 顶层目录为 29，并确认 top-level payload regular files 仍为 0（placeholder 是否计入“regular files=0”的口径需同步在 README/ledger 中明确，不能同时声称 Git 可恢复目录且目录内绝对零文件）。

### DCR-02 — `diff --check` 的失败不全是 hash-preserved historical originals

- **severity**：minor
- **status**：open；需在提交前分类处置并使 checkpoint 的 whitespace gate 可解释
- **primary_location**：`git diff --cached --check`
- **related_locations**：
  - `docs/anthropic-direct-request-shape/reports/260908-{historical,tmp}-evidence-migration.md`
  - `docs/anthropic-responses-bridge/reports/260908-{history,tmp}-evidence-migration.md`
  - `docs/anthropic-responses-bridge/reports/260908-pre-reroot-research-relink.md`
  - `docs/dotdev-repository-repair/reports/260908-{passthrough-provenance,tmp-governance}-evidence-migration.md`
  - `docs/server-layout/reports/260908-residual-history-migration.md`
  - `docs/token-counting/reports/260908-{historical,tmp}-evidence-migration.md`
  - `docs/dotdev-repository-repair/reports/260908-conflict-resolution-reroot-review.md`
- **claim**：当前 gate 报 19 项；历史快照/点时原件中的原始 whitespace 不应为过 gate 而改写，但至少 11 份 2026-09-08 migration/relink/review control-plane reports（合计 13 项）是 staged 新增文档，并非旧 `HEAD:.dev/` 的 hash-preserved blob，不能将其 trailing spaces/EOF blank 全部归入历史保真例外。
- **evidence**：
  - `git diff --cached --check` exit 2，共 19 项、17 个文件：11 项 `trailing whitespace`，8 项 `new blank line at EOF`。
  - 17 个文件在 rename-aware staged status 中全部为 `A`；其 staged blob 均不等于旧 `HEAD:.dev/` 的任何 blob。
  - 其中明确应保真的历史材料包括 `docs/tui/history/260906-function-call-grouping-code-review.md`（其它材料以 SHA-256 `a1553903...` 固定该原件）以及 `docs/upstream/retry-and-continuation/history/decisions-20260821*.md`（migration report 明确称逐字保留原段）。不得要求仅为 whitespace gate 改写这些原件。
  - 相反，上列 2026-09-08 migration/relink reports 是当前迁移实施记录；例如多份文件第 3/4 行在新增 metadata 上带两个尾随空格，`260908-conflict-resolution-reroot-review.md` 则新增 EOF blank。它们不是 ledger 所迁移的 canonical historical originals，也没有旧 dotdev blob identity 可保。
- **impact**：若不分类就提交，checkpoint 保留一个未经解释的 failing basic check；若机械清理全部 19 项，又会破坏明确要求逐字/hash 保真的历史原件。正确边界是保留有 provenance 约束的 originals，只修当前新增 control-plane 文档，或为确有意的 Markdown hard-break 建立逐文件证据化例外。
- **minimal_next_step**：先对 17 个文件逐一标记 `hash-preserved original` 或 `current newly-authored report`；不得修改前者。清理后者的 EOF blank 和非必要 trailing spaces（若两个空格确为 Markdown hard break，则改成不触发 whitespace gate且渲染等价的结构，或记录精确例外），再重跑 `git diff --cached --check`，报告剩余项及其逐文件 provenance。

## 已通过的承重检查

### Archive ref 与 staged scope

- 当前 `HEAD` 与 `refs/heads/archive/260908-dotdev-pre-reroot` 均为 `862b13748cefe3e27f8a95c7885cb3a4405345bc`；archive ref 是 branch ref，commit peel 结果相同。
- old `HEAD` 顶层只有 `.dev/`；其 subtree 顶层为 `.gitignore`、`README.md`、`docs`、`exp`、`human-controlled-docs-candidates`、`tools`。
- staged final top-level 仅为 `.gitignore`、`README.md`、`docs`、`exp`、`human-controlled-docs-candidates`、`tools`；没有 staged `.git`/gitlink、`src/`、`tests/`、绝对路径式文件名或其它主仓产品路径。
- staged index 内没有任何 `.dev/` path，也没有 `.dev/.dev` 残留；主仓当前未阶段化源码/测试 dirt 不属于 dotdev repository 的 staged checkpoint。

### Active docs、retirement 与 conflict preservation

- worktree `docs/` 顶层为 29 个 retained topic/机制目录；`docs/dotdev-repository-repair/README.md` 是 final/current execution entry，明确 final scan → checkpoint → re-root/worktree 顺序。
- 15 个 retired dirs 在 worktree 与 staged index 均 absent：`architecture-audit`、`archived-2604-rewrite`、`copilot-token-identity`、`count-tokens`、`docs-tmp-migration`、`documentation-restructure`、`early-verification`、`empty-text-block`、`git-housekeeping`、top-level `history`、`hooks-subscription-migration`、`lifecycle-reorg`、`pipeline-rewrite-parity`、`sync-refs`、`test-infrastructure`。
- multi-provider history 包含两份 conflict snapshots、history index 与 `reports/260908-nested-dotdev-conflict-disposition.md`；current `review-disposition.md` 已把无一手逐字锚的内容收窄为“当时转述”，没有继续冒充用户裁决来源。

### 旧 active subtree 与 staged direct-root 内容对账

- `HEAD:.dev/` 有 1,183 个 tracked blobs，staged direct-root 有 1,388 个 tracked files。
- 按去掉旧 `.dev/` prefix 的同路径比较：832 个 blob 原样保留；45 个路径有 staged current 更新；306 个旧路径不再位于同名 direct-root path，其中 267 个旧 blob 在 staged tree 的 canonical history/其它新位置仍逐字存在。
- 剩余 39 个真正不再出现的旧 blobs，全部精确落入两个已实施 deletion ledger：candidate residual 的 36 项删除与 top-level tmp 的 4 项可删除；后者中的 `260906-session-report.html` 不在旧 `HEAD`，故旧 HEAD 分母实际是 39。`removed_not_ledgered=0`。
- rename detection 得到 1,139 个 renames（其中 1,099 个 `R100`）；显示为 44 个纯 deletion 的旧路径由上述 39 个 ledgered deletion 加 5 个有 direct-root replacement/current update 的路径组成（旧 README、reasoning/timeout status、TUI spec/deferred），未观察到不可接受的数据丢失。
- staged root README 有 7 个 local link occurrences，逐一在 staged index 中存在；重复的是 repository repair entry。

## Severity 汇总

| severity | open count |
|---|---:|
| blocker | 0 |
| major | 1 |
| minor | 1 |

## 搜索面与执行记录

- Git/ref：只读执行 `rev-parse`、`show-ref`、`status --short`、`ls-tree`、`ls-files --stage`、`diff --cached --name-status --find-renames=50%`、`diff --cached --stat/--shortstat/--check`；未执行任何 ref 写入或 index 修改。
- Scope/tree：枚举 staged top-level、mode `160000` gitlink、`.git`/`.dev`/`.dev/.dev`、`src/`、`tests/`、绝对路径式文件名；枚举 worktree 与 staged `docs/` 顶层目录、15 个 retired dirs、top-level `tmp` 和 multi-provider history/disposition。
- Integrity：以 Git blob id 对账 `HEAD:.dev/` 的 1,183 个 blobs 与 staged 1,388 files；对 stripped same-path、relocated exact blob、updated path 和 truly removed blob 分组，再把 39 个 truly removed blobs 与 36+4 deletion ledgers 机械对账。
- Navigation/content：完整读取 staged root README、repair current entry、final ledger、final/pre-reroot reviews、conflict review/disposition/history index 与 tmp/retirement ledgers的承重部分；解析 staged root README 的 7 个 local links并在 index 中查存在性。
- Whitespace：保留 `git diff --cached --check` 的逐项输出，并按旧 HEAD blob identity、明确逐字/SHA provenance、2026-09-08 current migration report 三类复核。没有要求修改已明确固定 hash 或逐字保真的 historical originals。
- 未运行产品 tests、网络请求、provider canary 或主仓构建；这些不是 direct-root checkpoint tree 的 ground truth。本审阅也没有验证尚未执行的 commit object、worktree attach 或主仓 `.dev/` mount 后验行为。

## 提交门结论

当前 **不应提交** `docs: re-root dotdev development documents`。先闭合 DCR-01，使 `docs/tmp/` 机制能由 checkpoint 自身恢复；再闭合 DCR-02 中至少 11 份 current 2026-09-08 reports 的 13 项 whitespace，并对保留项留下逐文件 provenance。随后重跑 staged top-level/index directory inventory、old-tree blob reconciliation、root README links、nested `.dev` scan 与 `git diff --cached --check`；通过后才可重新给 checkpoint `pass`。

---

## 附录：DCR-01 / DCR-02 限域复审（2026-09-08）

### 限域范围与结论

本附录只复审 DCR-01、DCR-02 及委托明确要求的 staged scope/archive/nested-removal 回退门；不重开正文已经通过的 1,183 个旧 blobs 全量 disposition 对账。只读核对 staged `docs/tmp/README.md`、repair README tmp ledger 行、staged index/tree、`git diff --cached --check` 完整输出与剩余六个 diagnostics 文件的 provenance。

**DCR-01=closed；DCR-02=closed。** 两项原 finding 均已按要求修复，剩余六项 diagnostics 都来自 2026-09-06/07 的 point-in-time report originals、明确 hash-preserved history original 或明确逐字 canonical extracts，不应为追求空输出而改写。

但本次 scope 复核发现新的 **DCR-03（major）**：本报告自身已进入 staged index，违反最初委托中“该文件应在工作树写入但不加入 index”的明确边界。本附录写入前该路径状态为 `A `；追加后 staged 版本仍是旧正文、worktree 多出本附录，预期状态为 `AM`。因此当前总体仍为 **NEEDS-FIX，暂不可提交 final checkpoint**；精确从 index 移除本报告、保留 worktree 文件后，无需再改 DCR-01/02 的内容即可提交。

### DCR-01：closed

- staged index 已包含 `docs/tmp/README.md`，mode `100644`，blob `a2c3b3c54788dee153a4dff2e00e046acbfe7251`。
- 从 staged `git ls-files` 导出的 `docs/` top-level directories 恰为 29，`tmp` 是第 25 项；`git ls-files docs/tmp` 只返回 carrier `docs/tmp/README.md`，没有临时 payload。
- carrier 明确写“当前没有临时 payload”，并说明它受版本控制仅为让目录在新 checkout/worktree 中恢复；repair README staged 第 14 行相应改成“机制保留，临时 payload regular files=0”，并明确 `tmp/README.md` 是恢复 carrier。这里的 `payload=0` 排除治理 carrier，口径一致，不再声称目录内绝对零 regular files。
- `docs/tmp/README.md` 与 repair README 两个目标路径没有 unstaged drift；本结论读取的是 staged bytes，不依赖 worktree 偶然存在的空目录。

### DCR-02：closed

`git diff --cached --check` 当前 exit 2，但完整输出已从原 19 项/17 文件收窄为 **6 项/6 文件**。正文列出的 11 份 2026-09-08 current control-plane reports 与当前 diagnostics 集合交集为 0；它们原有的 13 项 trailing-whitespace/EOF-blank 问题均已关闭。剩余六项逐份 provenance 如下：

| 文件 | 当前 diagnostic | provenance 判定 | 是否应改写 |
|---|---|---|---|
| `docs/direct-buffered-chat-completions/reports/260906-task-1-capability-implementation.md` | line 128 `new blank line at EOF` | 2026-09-06 Task 1 point-in-time implementation report original；正文冻结 base/head/branch、两个 source commits、147-test/Ruff/Pyright 结果与 fix review disposition，不是 2026-09-08 re-root control-plane 新文档 | 否；保留早期 report original |
| `docs/token-counting/reports/260907-subagent-authority-repair-review.md` | line 125 `trailing whitespace` | 2026-09-07 独立 authority-repair merged-state review original；`token-counting/HANDOVER.md` 将其作为 H2 evidence locator，当前尾行是当时 READY verdict/下一门记录 | 否；保留 point-in-time review original |
| `docs/token-counting/reports/260907-task3b-merged-precommit-gate-gpt-s.md` | line 147 `new blank line at EOF` | 2026-09-07 main-side pre-commit gate original；冻结 12 staged paths、552 tests、Ruff/Pyright/index/check 输出，且被 HANDOVER、task-4a brief 与 status 作为 gate locator | 否；保留 point-in-time gate original |
| `docs/tui/history/260906-function-call-grouping-code-review.md` | line 195 `new blank line at EOF` | history original；后续 closeout review 明确固定其 SHA-256 为 `a1553903de06e1363665567c27d907e2abc8a02ea9a539927751bd7f19b16172`，与当前 staged bytes 的 SHA-256 完全相同 | 否；hash-preserved，改写会使后续证据锚失真 |
| `docs/upstream/retry-and-continuation/history/decisions-20260821-query-surface.md` | line 16 `new blank line at EOF` | canonical extract；文件头与 `260908-history-pending-migration.md` 明确说明逐字复制原 `history/decisions.md` 第五节相关段落 | 否；明确逐字保真 |
| `docs/upstream/retry-and-continuation/history/decisions-20260821.md` | line 21 `new blank line at EOF` | canonical extract；文件头与 migration report 明确说明逐字复制原 `history/decisions.md` §6 的产生背景、§6.1/§6.2 原文、理由和验证摘要 | 否；明确逐字保真 |

六个 staged blobs 均未在旧 archive ref 的 reachable objects 中出现，这只说明它们在本次大 checkpoint 相对旧 dotdev HEAD 表现为 added；不能推翻其文件内容自身、topic index、HANDOVER/closeout 锚所证明的 2026-09-06/07 point-in-time 或逐字/hash provenance。相反，当前 2026-09-08 control-plane diagnostics=0，故没有把一个新的 whitespace 问题藏进“历史保真”例外。

### Archive、scope 与 nested removal：机械门通过，但报告路径回退

- `HEAD`、`archive/260908-dotdev-pre-reroot` 与其 peeled commit 仍全部为 `862b13748cefe3e27f8a95c7885cb3a4405345bc`。
- staged top-level 仍仅为 `.gitignore`、`README.md`、`docs`、`exp`、`human-controlled-docs-candidates`、`tools`；没有 `.git`/gitlink、`src/`、`tests/`、绝对路径式文件名。
- staged index 中没有任何 `.dev/` 或 `.dev/.dev` path；rename-aware 状态仍有 1,099 个 `R100`，旧 `.dev/` 的 1,183 个 tracked paths 全部离开嵌套前缀。未观察到 nested removal 或 archive ref 回退。
- 唯一 scope 回退是本报告路径被 staged，见 DCR-03。

### DCR-03 — checkpoint review report 进入 staged index

- **severity**：major
- **status**：open；阻止当前 final checkpoint 提交
- **primary_location**：staged `docs/dotdev-repository-repair/reports/260908-checkpoint-review.md`
- **claim**：最初委托明确要求本报告只写入 worktree、不加入 index；限域复审开始时 `git status --short -- <report>` 为 `A `，证明旧正文已经 staged。
- **impact**：若现在提交，checkpoint 会包含一份明确要求排除的 review artifact，而且 staged 版本只含复审前的 NEEDS-FIX 正文，不含本附录的 closure/新 scope 结论。它既违反 scope，也冻结过期 verdict。
- **minimal_next_step**：调用方精确 unstage `docs/dotdev-repository-repair/reports/260908-checkpoint-review.md`，保留 worktree 文件；确认该路径不再由 `git ls-files --stage` 或 `git diff --cached --name-only` 返回。不要删除本报告，也不要把本附录补 stage。

### 限域复审后的有效 severity

| severity | open count |
|---|---:|
| blocker | 0 |
| major | 1 |
| minor | 0 |

### Final checkpoint 门

- **DCR-01：closed。**
- **DCR-02：closed。** 剩余六项是逐文件有 provenance 的 historical-fidelity exceptions，不要求改写，也不阻止 checkpoint。
- **Final checkpoint：当前不可提交，仅受 DCR-03 阻止。** 精确 unstage 本报告并确认其它 staged scope 不变后，可以提交 `docs: re-root dotdev development documents`；不需要为了让 `git diff --cached --check` 零输出而修改上述六份历史 originals。
