# 第一轮文档治理评审（提交态复核版）

## 评审范围

- 文档对象：`.dev/README.md`、`observability/`、`history/`、`raw-capture/`、`replay/`，以及 `dotdev-repository-repair/README.md` 规定的结构、生命周期和归档约束。
- 代码基准：提交 `30384269377cfd5f8f848ef92bb3654afda2196a` 的 committed tree；不以共享工作树 `status`、暂存删除或物理缺失作为代码证据。
- 文档基准：`/home/xp/src/ghc-api-proxy-py/.dev` 当前 living docs；另扫描 `.dev/docs` 文件名、Markdown links 和直接相连的 human-controlled 入口。

## 总体 verdict

**needs-fix**。blocker = 0。

## 复核纠错（不计 finding）

先前以 stale working copy 为依据的“Replay/RequestJournal/History 查询与 archive 实现缺失”不成立：committed HEAD 明确包含 `src/app/replay/`、`src/app/observability/request_journal.py`、History writer/routes/archive，以及对应 unit tests。以下 findings 不再把这些路径的“缺失”当作问题；问题改按当前文档、真实提交态实现和 authority 边界重判。

## Major findings

### DG-01 · major · current inventory 漏列六个仍在工作的主题目录

- `primary_location`: `.dev/README.md:33-67`；`related_locations`: `.dev/docs/{history,observability,raw-capture,replay,commandcode-provider,sub2api-provider}/`。
- 当前 inventory 列 29 个目录，`.dev/docs` 有 35 个；上述六个目录均有 2026-09-13 的 living `spec.md`/`README.md`，不是 history/archive。
- 影响：入口隐藏活跃合同，新接手者可能漏读或误判为退役材料；repair README 要求的最终 inventory 复扫也尚未闭合。
- 建议：登记或明确处置六个目录，并在 re-root 前重跑 repair owner 指定的 inventory/link/path 复扫。

### DG-02 · major · human-controlled authority 入口存在当前断链

- `primary_location`: `docs/.human-controlled/README.md:18`；链接 `observability.md` 在当前文档树不存在；`related_locations`: `.dev/docs/observability/spec.md`。
- 该 README 是用户控制需求入口，却无法到达可观测性一手约束；当前 `.dev` Spec 不能替代一个缺失的用户控制源而不留下来源边界。
- 影响：接手者无法判断哪些 observability 条款是用户约束、哪些是 agent-derived living contract，authority 归属与可追溯性中断。
- 建议：恢复真实 user-controlled source，或按用户控制流程补齐/重定向；不得仅把 `.dev` Spec 当作替代来源。

### DG-03 · major · implementation ledger 仍承载第二份合同权威

- `primary_location`: `.dev/docs/observability/implementation-ledger.md:11-16`；`related_locations`: 四个 current `spec.md` 与 committed `src/app/{history,observability,replay}/`。
- ledger 的“最近操作”重复 archive state、query/export、credential-bearing transport、journal freeze、replay selector 等 Spec-level 事实，并将其压成 `done`；这超出状态/证据索引职责。
- 影响：即使 committed HEAD 确实有实现，读者仍可能绕过 current Spec，以 ledger 的摘要/状态判断合同已满足，形成可漂移的双 authority。
- 建议：保留 task/status/commit/test 锚点；把行为合同细节和边界只留在各 current Spec，并从入口显式链接二者。

### DG-04 · major · Observability Spec 与提交态实现仍在同一边界上冲突

- `primary_location`: `.dev/docs/observability/spec.md:19-43,85-89`；`related_locations`: committed `src/app/observability/request_journal.py`, `request_completion.py`, `request_log_file.py`。
- Spec 要求至少覆盖 route/attempt/block/delivery/history-finalization 等 typed events，且 JSONL 只能是临时 shadow/export；提交态 journal 只有 8 类 event，`publish()` 仍无条件写入 always-on、14-day durable `requests-*.jsonl`。
- 影响：ledger #5 的 `done` 不能证明完整 lifecycle journal 或唯一事实源已成立，JSONL 仍可被当作第二个 durable truth。
- 建议：补齐/修订 Spec 与 event owner 的实际边界，并明确 JSONL 的 shadow/export 身份、生命周期和不得拥有独立语义的验收条件。

### DG-05 · major · Capture capability 与 History safe projection 的权威边界未收敛

- `primary_location`: `.dev/docs/raw-capture/spec.md:64-70`；`related_locations`: `.dev/docs/history/spec.md:25-32,48-56`、committed `capture_observation.py`, `history/entry.py`, `history/writer.py`。
- Specs 要求 per-attempt `upstream_attempts[]` capability；提交态 `RawCaptureObservation`/`CaptureCapabilities` 只有 aggregate booleans。Raw capture 又禁止普通 History list/detail 暴露原始 session/agent，而 History Spec 与 `HistoryIndexEntry.as_dict()` 明确返回它们。
- 影响：Replay gate 无法从 durable projection 判断指定 attempt 的证据完整性，且同一 list/detail 的身份安全边界存在相互冲突的合法解释。
- 建议：在一个 current owner 中定义 per-attempt capability/reference，并由 raw-capture、History、Replay 共用；同时由用户/Spec 明确 session/agent 是否可出现在 ordinary projection。

### DG-06 · major · 点时报告没有绑定 committed HEAD 或 current disposition

- `primary_location`: `.dev/docs/observability/reports/260914-round1-{contract,authority}-review.md`、`.dev/docs/raw-capture/reports/`；`related_locations`: `.dev/docs/observability/implementation-ledger.md`、`raw-capture/deferred.md`。
- 两份 260914 报告把 stale working copy 的“代码缺失”写成当前断言，而 committed HEAD 已有相应模块/测试；raw-capture 仍并列保留 v21 pass、v22 needs-fix、v23 With-fixes 等报告，没有 current closure map。
- 影响：报告原件虽保留，却没有 reviewed-commit/disposition 入口，读者可能把时点报告当 current truth，重复修复或错误阻断。
- 建议：保留原件不改写；在主题根增加 current review-disposition/status，绑定 reviewed commit、后续证据和 superseded 状态。

## Minor / 牛角尖 / 点时证据

- 全 `.dev/docs` 共有 1,573 个本地 Markdown link occurrences；164 个不存在目标全部来自 history/archive/reports，living docs、root README、repair README 和四个 current topics 的 links 均通过。按生命周期约束不回写历史原件。
- `.dev/human-controlled-docs-candidates/raw-capture.md` 仍写旧目录总量配额和 `sub2api` 示例；候选目录明确不是 current，记录为用户控制流程的后续清理项，不阻塞本轮。

## 搜索面与限制

- 已读 workflow、root/repair README、四个 current specs、implementation ledger、raw-capture reports/deferred、current human-controlled README；扫描全部 `.dev/docs` 文件名和 Markdown links。
- 代码只以 committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a` 的 `git show/grep/ls-tree` 核验；未使用共享工作树 status 或物理缺失作为代码证据，未运行测试。
- 本轮仅覆盖文档治理与直接相连的 contract 接缝；未评 provider、translation、deployment 或真实 upstream。未修改、删除或创建除本报告外的仓库文件，未执行 `git add`/`commit`。
