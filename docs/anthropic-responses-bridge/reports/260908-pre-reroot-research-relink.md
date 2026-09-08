# PRR-02：pre-reroot research relink

日期：2026-09-08
范围：仅 `.dev/docs/anthropic-responses-bridge/research.md` 的「目标仓当前事实与能力缺口」第 6 条，以及本报告。

## 改动

- 将已迁入的 `.dev/docs/hosted-web-search/history/2604-tool-use.md:3-12` 改为引用的 canonical historical source。
- 明确该 source 只提供 historical provenance，不能作为 current behavior oracle。
- 移除了已按 ledger 删除、且没有 canonical original 的 `docs/2604-rewrite/request-pipeline.md` 引用；没有伪造替代路径、复活原文，或把其内容表述为用户裁决。
- 将当前 server-tool no-revive／无专用降级 retry 的依据改为 research 本节已核验的目标现状与当前正式 Spec：`.dev/docs/anthropic-responses-bridge/spec.md:148-149`。

## 权威边界

| 材料 | 本次可承担的角色 | 不可承担的角色 |
|---|---|---|
| `.dev/docs/hosted-web-search/history/2604-tool-use.md` | 已迁移旧文的历史来源与当时范围的 provenance | current bridge 行为 oracle、当前 Spec 的替代品 |
| `.dev/docs/anthropic-responses-bridge/research.md` | 固定目标 HEAD 的已核验研究事实与其推导 | 取代正式行为规格 |
| `.dev/docs/anthropic-responses-bridge/spec.md:148-149` | 当前基础 bridge 的 server-tool no-revive 行为边界 | 已删除 `request-pipeline.md` 的 canonical original 或其内容的证明 |
| 已删除的 `docs/2604-rewrite/request-pipeline.md` | 无；本次未复原或重建其内容 | 当前或历史权威来源 |

## 核对

- 已确认 `.dev/docs/hosted-web-search/history/2604-tool-use.md` 存在。
- 已确认主工作树（排除隔离的 `.claude/worktrees/`）不再出现 `docs/2604-rewrite/tool-use.md` 或 `docs/2604-rewrite/request-pipeline.md`。
- 隔离工作树中仍可存在其各自快照的旧路径引用；它们不属于本次严格所有权范围，未作修改。
