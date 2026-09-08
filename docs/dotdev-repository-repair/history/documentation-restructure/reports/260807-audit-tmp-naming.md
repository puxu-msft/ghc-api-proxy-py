# `docs/tmp` 今日报告命名、覆盖与重复只读审计

- **评审范围**：`docs/tmp/260807-*` 今日新报告的命名、同对象轮次保留、文件名与内容重复，以及 `docs/tmp/*~` 备份归属；另列 `260806-*` 与旧无日期前缀历史文件，但不要求改名。
- **证据基线**：仓库 `/home/xp/src/ghc-api-proxy-py`，分支 `main`，HEAD `ed77c9d191df81c451c25161420515cca52ce6a4`。每次 shell 调用均在同一调用内验证这三个条件。
- **总体 verdict**：**可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：0。
- **机械核对覆盖**：以 Python `Path.iterdir()` 和 shell glob 两种不同枚举方式交叉核对文件集合与计数；检查 `260807-` 前缀、basename 唯一性、末尾 `-rN` 轮次序列、全目录 SHA-256 重复组及 `*~` 文件时间。
- **第一人称执行视角**：未执行；本次用户明确限定为机械检查。

## 结论

1. 审计写入前共有 15 份 `docs/tmp/260807-*.md` 今日新报告，全部带 `260807-` 前缀。
2. 未发现重复 basename，也未发现 SHA-256 完全相同的内容重复组。
3. 同对象多轮报告均使用不同 `-rN` 文件名保存；`review-bridge-implementation` 的 R4、R5、R6 均在，`review-doc-migration-plan` 的 R4、R5、R6 均在，未见同轮文件名覆盖。
4. 全目录仅有一份 `~` 备份 `refs-go-bridges.md~`，其 ctime 与 mtime 均为 `2026-08-06 21:47:40 +0000`，不属于今日新建。
5. 另有 43 份 `260806-*` 历史报告和 20 份旧无日期前缀文件；本次只列示，不要求改名。

## 今日新报告清单

- `260807-audit-doc-links.md`
- `260807-audit-docs-commit-boundary.md`
- `260807-audit-integration-commits.md`
- `260807-review-architecture-decision-matrix.md`
- `260807-review-bridge-acceptance-r7.md`
- `260807-review-bridge-implementation-r4.md`
- `260807-review-bridge-implementation-r5.md`
- `260807-review-bridge-implementation-r6.md`
- `260807-review-bridge-readme-r3.md`
- `260807-review-doc-migration-plan-r4.md`
- `260807-review-doc-migration-plan-r5.md`
- `260807-review-doc-migration-plan-r6.md`
- `260807-review-docs-merged-r2.md`
- `260807-review-research-external-change.md`
- `260807-tmp-distillation-matrix.md`

## 今日同对象轮次清单

- `review-bridge-acceptance`：R7。
- `review-bridge-implementation`：R4、R5、R6。
- `review-bridge-readme`：R3。
- `review-doc-migration-plan`：R4、R5、R6。
- `review-docs-merged`：R2。

## `260806-*` 历史报告清单

- `260806-arbitrate-empty-content-turn.md`
- `260806-arbitrate-reasoning-aggregation.md`
- `260806-arbitrate-server-tool-contract.md`
- `260806-architecture-decision-reading-check.md`
- `260806-audit-docs-index-state.md`
- `260806-docs-freeze-check-pre.md`
- `260806-review-architecture-readability-r2.md`
- `260806-review-architecture-readability-r3.md`
- `260806-review-architecture-readability.md`
- `260806-review-bridge-acceptance-r2.md`
- `260806-review-bridge-acceptance-r3.md`
- `260806-review-bridge-acceptance-r4.md`
- `260806-review-bridge-acceptance-r5.md`
- `260806-review-bridge-acceptance-r6.md`
- `260806-review-bridge-architecture-r2.md`
- `260806-review-bridge-architecture-r3.md`
- `260806-review-bridge-implementation-r2.md`
- `260806-review-bridge-implementation-r3.md`
- `260806-review-bridge-implementation.md`
- `260806-review-bridge-readme-r2.md`
- `260806-review-bridge-readme.md`
- `260806-review-bridge-research-r2.md`
- `260806-review-bridge-research-r3.md`
- `260806-review-bridge-spec-r2.md`
- `260806-review-bridge-spec-r3.md`
- `260806-review-code-bridge-foundations-r2.md`
- `260806-review-code-bridge-foundations.md`
- `260806-review-code-liveness-r2.md`
- `260806-review-code-liveness-r3.md`
- `260806-review-code-reasoning-cardinality.md`
- `260806-review-code-reasoning-r2.md`
- `260806-review-code-request-converter.md`
- `260806-review-code-request-r2.md`
- `260806-review-code-request-r3.md`
- `260806-review-doc-migration-plan-r2.md`
- `260806-review-doc-migration-plan-r3.md`
- `260806-review-docs-merged.md`
- `260806-review-integration-strategy.md`
- `260806-review-tmp-distillation.md`
- `260806-verify-bridge-foundations-r2.md`
- `260806-verify-bridge-foundations.md`
- `260806-verify-request-converter.md`
- `260806-verify-request-r2.md`

## 旧无日期前缀历史文件清单

- `docs-migration-plan.md`
- `live-doc-truth-audit.md`
- `python-bridge-architecture.md`
- `refs-go-bridges.md`
- `refs-go-bridges.md~`，历史备份。
- `refs-python-bridges.md`
- `refs-typescript-bridges.md`
- `review-bridge-acceptance.md`
- `review-bridge-architecture.md`
- `review-bridge-research.md`
- `review-bridge-spec.md`
- `review-code-reasoning.md`
- `review-doc-migration-plan.md`
- `upstream-bridge-tests.md`
- `upstream-recent-changes.md`
- `upstream-request-conversion.md`
- `upstream-response-conversion.md`
- `upstream-route-decision.md`
- `upstream-stream-blocks.md`
- `verify-liveness.md`

## 事实性发现

未发现问题。

## 主观建议

无。本次范围仅限机械检查。
