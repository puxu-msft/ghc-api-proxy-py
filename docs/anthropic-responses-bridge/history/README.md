# Bridge 历史原件

本目录保存 `anthropic-responses-bridge` 的历史证据原件，供追溯设计沿革与事实来源。

[`2604-history-system.md`](2604-history-system.md) 是从已退役的 `archived-2604-rewrite` 移入的 2604 目标设计。它记录当时提出的 History 设计与“轻量终态一次写入”背景，**不能**当作用户裁决或 current authority。当前 bridge 架构的持久化约束以 [`../architecture.md`](../architecture.md) 为准；用户可观察行为仍以 [`../spec.md`](../spec.md) 为准。

## 从顶层 `tmp/` 迁入的 260807–260824 证据

下列原件均从 `.dev/docs/tmp/` 原路径迁入。它们是绑定固定 SHA、评审范围、探针或当时 living checkpoint 的 point-in-time 证据，不得被读取为 current authority；“current carrier”列仅指出当前状态或产品行为应回到哪里，而不是将历史 verdict 外推。

| 原件 | 来源 | 点时性质 | current carrier |
|---|---|---|---|
| [`260807-final-review-current-main.md`](260807-final-review-current-main.md) | `tmp/260807-final-review-current-main.md` | merged-state 独立评审；强证据，但受固定 SHA 与范围限制 | 无；仅由 bridge archive 与已退役迁移账本提名。 |
| [`260807-resume-audit-systemd-bridge-overlap.md`](260807-resume-audit-systemd-bridge-overlap.md) | `tmp/260807-resume-audit-systemd-bridge-overlap.md` | 跨切片只读预检；路径／hunk 证据强 | 无。 |
| [`260807-review-backup-r3-living-checkpoint.md`](260807-review-backup-r3-living-checkpoint.md) | `tmp/260807-review-backup-r3-living-checkpoint.md` | living checkpoint 独立复评；强但为时点结论 | bridge 与 `service-cutover` 的 living 文档。 |
| [`260807-review-identity-living-checkpoint.md`](260807-review-identity-living-checkpoint.md) | `tmp/260807-review-identity-living-checkpoint.md` | bridge identity checkpoint 复评；强但为时点结论 | 无；仅由已退役的 `docs-tmp-migration` README 提名。 |
| [`260807-review-living-after-main-replay-r2.md`](260807-review-living-after-main-replay-r2.md) | `tmp/260807-review-living-after-main-replay-r2.md` | main replay 后 living 状态复评；强但为时点结论 | 无；仅由 bridge 历史 report 提名。 |
| [`260807-review-main-foundations-systemd.md`](260807-review-main-foundations-systemd.md) | `tmp/260807-review-main-foundations-systemd.md` | foundations＋systemd merged-state 评审；强但为时点结论 | 无；仅由 bridge archive 与退役材料提名。 |
| [`260807-review-reservation-wiring-living.md`](260807-review-reservation-wiring-living.md) | `tmp/260807-review-reservation-wiring-living.md` | resident quota／wiring living 复评；强但为时点结论 | 无；仅由 bridge 历史 report 提名。 |
| [`260807-review-resident-living-checkpoint.md`](260807-review-resident-living-checkpoint.md) | `tmp/260807-review-resident-living-checkpoint.md` | resident primitive checkpoint 复评；强但为时点结论 | bridge `implementation.md` 与 `service-cutover` readiness。 |
| [`260807-verify-main-foundations-systemd.md`](260807-verify-main-foundations-systemd.md) | `tmp/260807-verify-main-foundations-systemd.md` | 独立验收；scoped PASS，强且边界明确 | 无；该 scoped PASS 不能作为当前整体验收。 |
| [`260824-defer-loading-responses-leg-investigation.md`](260824-defer-loading-responses-leg-investigation.md) | `tmp/260824-defer-loading-responses-leg-investigation.md` | `defer_loading` 翻译腿 400 调查；源码＋探针强证据，状态为调查稿 | 无；仅由 bridge tool-whitelist 历史 report 提名。 |
| [`260824-tool-search-beta-400-investigation.md`](260824-tool-search-beta-400-investigation.md) | `tmp/260824-tool-search-beta-400-investigation.md` | tool-search beta 400 调查；源码／参考客户端证据强，状态为 `in-review` | 无；仅由 bridge tool-whitelist 历史 report 提名。 |

## 202607–202608 residual evidence families

下列三个 family 按 `260908-candidate-residual-disposition.md` 的 canonical-history 精确 destination 原样迁入。每个 family 的原件只保存当时可复核的证据；表中的 current carrier 指向应判断当前行为、约束或后续状态的位置，不使历史结论成为 current authority。

| family | 原始来源 | 点时边界 | current carrier |
|---|---|---|---|
| early verification | `.dev/docs/early-verification/archive-260715-phase3/` 的 Phase 3 report／runner，以及 `.dev/docs/early-verification/archive-260716-final/` 的 Phase 0–8 report、manifest、summary 与 probes。 | 260715 Phase 3 的黑盒验收记录 2 blocker、1 major；260716 final 的 10/11 结论明确保留 Responses WebSocket skip。runner/probe 固定的是当时方法、端口与项目根，不能作为 current runbook。 | 无 direct carrier；current verification 以根规则与当前 `tests/` 为准，bridge 当前产品合同以 [`../spec.md`](../spec.md) 与 [`../implementation.md`](../implementation.md) 为准。 |
| legacy History bridge | `.dev/docs/history/archive-260807-legacy-chain/reports/` 的 source-squash 审计、capability/History 与 History/stream integration review、History facts R1–R4、scoped verification。 | 260807 staged/squash candidate 与 exact source tip 的评审、验收链；其中的 WIP、固定 commit range、PASS 和 finding closure 都仅覆盖各自报告写明的范围。 | 无 direct carrier；当前 bridge 架构持久化约束以 [`../architecture.md`](../architecture.md) 为准，用户可观察行为以 [`../spec.md`](../spec.md) 为准。 |
| pipeline rewrite parity | `.dev/docs/pipeline-rewrite-parity/reports/` 的 260818–260819 cache-control、ops、retry、traffic-feature gap 与 Copilot API JS IR architecture 调查。 | 固定源码、数据库、reference project 与真实 GHC probe 的差异调查；记录的是当时 rewrite parity 判断与可采纳边界，不是待执行的 current plan。 | 无 direct carrier；bridge current design/implementation 以 [`../architecture.md`](../architecture.md)、[`../implementation.md`](../implementation.md) 与 [`../spec.md`](../spec.md) 为准；ops/retry 的 current ownership 另由各自 living topic 承接。 |

### early verification contents

- [`early-verification/archive-260715-phase3/`](early-verification/archive-260715-phase3/)：Phase 3 acceptance report 与可复现 runner。
- [`early-verification/archive-260716-final/`](early-verification/archive-260716-final/)：final manifest、README、complete report、summary、8 个 probes 与 orchestrator；保留完整矩阵和 WS skip 的限定。

### legacy History bridge contents

- [`history-legacy-chain/reports/`](history-legacy-chain/reports/)：260807 source-squash、History facts、capability/History 与 stream-integration 的完整 review／verification 链。

### pipeline rewrite parity contents

- [`pipeline-rewrite-parity/reports/`](pipeline-rewrite-parity/reports/)：260818–260819 的五份跨协议与 reference-architecture 调查原件。
