# 2026-09-08 repair current execution entry refresh

## 范围与判据

- **范围**：仅刷新 `.dev/docs/dotdev-repository-repair/README.md`，使它从迁移前 runbook 变为可审计的 current execution entry；本报告只记录本次核对与该刷新本身。
- **不在范围内**：不移动或删除任何候选、`tmp/` 或历史原件；不改任何其它主题或 subtopic ledger；不执行 `git add`、commit、push、dotdev checkpoint、re-root 或 worktree 挂载。
- **判据**：调用方给出的 current-state 要求，以及 `260908-inventory-review.md`、`260908-merged-state-review.md`、`260908-final-retirement-readiness-review.md`、repair subtopic ledgers 与全部现有 `260908` 迁移／状态报告。

## 已核对事实

1. 原 77 项 `tmp` ledger 已完整实施：72 份进入唯一 canonical history、4 份按 ledger 删除、1 份先提炼为 retained `interaction-context` living Spec 再保真归档原稿。此项不等于顶层 `tmp/` 已清空。
2. FRR-01 仍未以独立、可审计的 disposition 记录闭合：final readiness review 的点时快照发现顶层 `tmp/` 新增且未进入原 77 项 ledger 的 `260908-reasoning-encrypted-include-review.md`，并要求先确定唯一 retained owner 或可追溯删除理由。刷新时该同名原件已不在顶层 `tmp/`，而位于 `reasoning-carrier/history/`，且 history index 已将其标为点时评审原件；现有 ledger／migration reports 没有把该位置变化登记为 FRR-01 的完成 disposition，也没有给 `include-01` 的 `should-fix` 指定 current follow-up owner。因此不得把 filesystem 位置或 `tmp=0` 当作 FRR-01 已关闭。
3. 15 个候选都已关闭 topic-level living authority／link gate，但仍有 219 份 residual 原件未逐份 disposition；因此当前没有候选目录可删除。
4. `httpx2-migration` 仍是 current living residual owner；步骤 4 与 `httpx2`／`httpcore2` logger 筛噪验证未闭合，且 `pyproject.toml` 仍正确指向其 Plan。
5. `systemd-runtime` 仍保留：S3、S4 已落地，S7 已交给 `systemd-rolling`，但 S5 的真实 user-manager/delegated-cgroup runtime smoke 仍 blocked。
6. `reasoning-carrier` 与 `timeout-408` 的状态刷新已完成，且两页均已将 SHA 表述限制为 2026-09-08 审计基线，而不是持续的 current HEAD 声称。
7. 刷新时顶层 `tmp/` 的 direct regular-file count 为 0；这只是当前 filesystem observation，不覆盖 FRR-01 的未登记 disposition。
8. retained living safe superset 对 15 个候选目录及具体顶层 `tmp/<file>` 的 direct Markdown links 复扫为 0；点时报告、history/archive provenance 与 repair control-plane 的旧路径不应反算为 current consumer。

## 尚未做

- 未闭合 FRR-01：核定并记录 reasoning review 当前 history 位置是否为其唯一 canonical disposition，并登记 `include-01` 的 current follow-up owner；不得把 source 已离开 tmp 误称为处置已完成。
- 未为 219 份 residual 原件建立或实施逐份 canonical-history／删除 disposition。
- 未删除候选目录，未复扫最终删除门，未创建 dotdev checkpoint，也未执行 re-root 或 worktree 挂载。

## 刷新实施与验证

- 已阅读全文读取 refresh 前的 repair README、inventory review、merged-state review、final retirement readiness review、repair 下 5 份 `260908` subtopic ledger，以及刷新开始时已存在的 35 份 `.dev/docs/**/reports/260908-*.md`；后者包含全部 migration、status-refresh、residual-audit、extraction、relink/cleanup 与运行时 observation 证据。
- README 已重写为 current-state 汇总，链接到点时审阅、subtopic ledger、迁移／状态报告；不再将原 77 项、reasoning/timeout status refresh、已改链的 authority gate 或已经完成的 interaction-context extraction 写成待执行。
- README 的 38 个本地 Markdown links 全部解析到存在文件；README 与本报告未发现 trailing whitespace。
- 本次未移动、删除或修改任何候选、`tmp` 或历史原件；未修改其它主题或 subtopic ledger；未执行 `git add`、commit、push、dotdev checkpoint、re-root 或 worktree 挂载。
