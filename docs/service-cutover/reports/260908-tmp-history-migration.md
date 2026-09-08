# tmp history migration — service-cutover

- **执行日期**：2026-09-08
- **性质**：归档迁移验证记录；不是 current cutover plan、readiness、规则或生产授权。
- **范围**：只迁移下表三份指定 `.dev/docs/tmp/` 历史原件至 `history/`；原件内容未改写。

## 验证结果

迁移前逐一计算 source SHA-256；迁移后逐一计算 destination SHA-256。每一对完全一致，且迁移后全部 source 路径不存在。

| Source（迁移前） | Destination（迁移后） | SHA-256 | Source 已不存在 |
| --- | --- | --- | --- |
| `.dev/docs/tmp/260807-review-deployment-docs-r3.md` | `.dev/docs/service-cutover/history/260807-review-deployment-docs-r3.md` | `0d3018be0360185034fcedbee524c6b00b2bf15b78be9f9b94e31f40e81674ea` | 是 |
| `.dev/docs/tmp/260807-review-deployment-plans-r2.md` | `.dev/docs/service-cutover/history/260807-review-deployment-plans-r2.md` | `ca72d4a2c6aca23adbdeac3cf7c2458723b448f000eebc3f6805eef366395deb` | 是 |
| `.dev/docs/tmp/260824-acceptance-cut-and-new-skill-review.md` | `.dev/docs/service-cutover/history/260824-acceptance-cut-and-new-skill-review.md` | `f1745dd1026c20908b32b84b93ef2e74b0a524d5f7d6ea578e7270b6f6c583f2` | 是 |

`history/README.md` 已将三件原件标为点时 checkpoint／评审证据，并明确 current 依据只来自 `plan.md` 与 `readiness.md`。

## 可复现检查

在仓库根目录执行：

```bash
sha256sum \
  .dev/docs/service-cutover/history/260807-review-deployment-docs-r3.md \
  .dev/docs/service-cutover/history/260807-review-deployment-plans-r2.md \
  .dev/docs/service-cutover/history/260824-acceptance-cut-and-new-skill-review.md
test ! -e .dev/docs/tmp/260807-review-deployment-docs-r3.md
test ! -e .dev/docs/tmp/260807-review-deployment-plans-r2.md
test ! -e .dev/docs/tmp/260824-acceptance-cut-and-new-skill-review.md
```
