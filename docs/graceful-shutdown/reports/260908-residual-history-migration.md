# residual ledger：graceful-shutdown canonical-history 迁移

## 范围与执行规则

- 日期：2026-09-08。
- 依据：`.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md` 的 `lifecycle-reorg` `history` 表。
- 仅执行 disposition 为 `canonical history` 且 destination 位于 `.dev/docs/graceful-shutdown/` 的四行。
- 只移动 ledger 指定的 exact source；不覆盖 destination，不编辑原件正文；`delete` 行未处理。
- 未修改源码、测试、配置或其它文档；未执行 `git add`、commit、push。

## 逐项结果

| # | exact source | exact destination | SHA-256（迁移后） | source | destination | basename unique |
|---:|---|---|---|---|---|---|
| 1 | `.dev/docs/lifecycle-reorg/reports/260816-lifecycle-code-review.md` | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260816-lifecycle-code-review.md` | `e9c4e7590db68a6ebcf2dae2930b579bea977626479867dc4f2a3667a57382a1` | absent | regular file | 1 |
| 2 | `.dev/docs/lifecycle-reorg/reports/260816-lifecycle-reorg-review.md` | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260816-lifecycle-reorg-review.md` | `3f7f1c3d1d0ab8299427d27f20f3ee6cc6fd9255252080fa7bf810beadbf74b9` | absent | regular file | 1 |
| 3 | `.dev/docs/lifecycle-reorg/reports/260817-entry-switch-review.md` | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260817-entry-switch-review.md` | `6434458abd38ef24b8f6dc2cd4534ea856de08b0a7990f398dbf0f7fe926bae9` | absent | regular file | 1 |
| 4 | `.dev/docs/lifecycle-reorg/reports/260824-standalone-process-test-transient-failure.md` | `.dev/docs/graceful-shutdown/history/lifecycle-reorg/reports/260824-standalone-process-test-transient-failure.md` | `b77fe35705c7f226013c6261ed6899aef083247528df05aed0ec18a1d9578e6d` | absent | regular file | 1 |

## 验证方法与结果

1. 迁移前对四个 destination 做了 collision check；均不存在，因此没有覆盖。
2. 四个 source 按 ledger 顺序逐行 `mv` 到 exact destination；迁移后四个 source 均 absent。
3. 对四个 destination 重新计算 SHA-256，与移动前记录逐项一致。
4. 对 `.dev/docs/` 的 active tree 按 basename 检查，四个 basename 各只出现一次；没有产生重复 canonical 原件。
5. `history/README.md` 已新增，列明四份原件的 source、日期、证据边界与 current carrier；本报告链接可解析。

结论：四行 canonical-history 迁移 `PASS`。本次没有处理 ledger 中任何 `delete` 行，也没有进行候选目录删除或 dotdev re-root。
