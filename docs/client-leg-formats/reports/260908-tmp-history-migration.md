# tmp 历史材料迁移

迁移日期：2026-09-08

## 路径与完整性

| 材料 | Source（迁移前） | Destination（迁移后） | SHA-256 |
|---|---|---|---|
| `260827-fix-responses-stop-reason.md` | `.dev/docs/tmp/260827-fix-responses-stop-reason.md` | [`../history/260827-fix-responses-stop-reason.md`](../history/260827-fix-responses-stop-reason.md) | `76d8be63e070985ea2d6c32be8386e0187bc7aae1404b9e12a769789e2f2d1fc` |

迁移前已在 source 计算 SHA-256；迁移后在 destination 重新计算，值相同。复核时 source 不存在，destination 存在。

## 权威边界

该文件记录 Anthropic 上游到 `/responses` 客户端腿的 `stop_reason` 修复、边界表与验证，是历史实施材料而不是 current authority。完整索引与使用边界见 [`../history/README.md`](../history/README.md)；判断当前格式行为应以本主题现行文档和代码为准。
