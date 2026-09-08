# tmp 历史材料迁移

迁移日期：2026-09-08

## 路径、关联与完整性

| 材料 | Source（迁移前） | Destination（迁移后） | SHA-256 |
|---|---|---|---|
| `260822-cli-and-module-move-closeout.md` | `.dev/docs/tmp/260822-cli-and-module-move-closeout.md` | [`../history/260822-cli-and-module-move-closeout.md`](../history/260822-cli-and-module-move-closeout.md) | `ec92f0bc3cff3cb2bee6bc4ae6209e329ffc9fc0f9fb222e441d2787dae71cb1` |
| `260822-review-closeout-facts.md` | `.dev/docs/tmp/260822-review-closeout-facts.md` | [`../history/260822-review-closeout-facts.md`](../history/260822-review-closeout-facts.md) | `d8678ffe94909230b28d808de2d75739e8fc67d16e1485ddc877e6304d14c1fb` |
| `260822-review-closeout-omissions.md` | `.dev/docs/tmp/260822-review-closeout-omissions.md` | [`../history/260822-review-closeout-omissions.md`](../history/260822-review-closeout-omissions.md) | `9be7ec98fbe900540716489085846133e94d31e7bb9ce14639be1a4d8460c40d` |

迁移前已在三个 source 文件上计算 SHA-256；迁移后在对应 destination 重新计算，三组值逐一相同。复核时三个 source 均不存在，三个 destination 均存在。

该组的关联不可拆开：`cli-and-module-move-closeout` 是会话 closeout，`review-closeout-facts` 是其独立 facts review，`review-closeout-omissions` 是其独立 omissions review。完整索引与历史使用边界见 [`../history/README.md`](../history/README.md)。

## 权威边界

这些均是历史实施或评审的时点材料，不能作为 current authority。材料正文中保留的 `.dev/docs/tmp/` 位置仅为历史事实；应从其 `history/` destination 读取，并以本主题的现行文档和代码判断当前状态。
