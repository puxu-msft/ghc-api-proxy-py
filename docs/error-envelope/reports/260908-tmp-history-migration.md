# tmp 历史材料迁移

迁移日期：2026-09-08

## 路径与完整性

| 材料 | Source（迁移前） | Destination（迁移后） | SHA-256 |
|---|---|---|---|
| `260827-fix-inference-accounting.md` | `.dev/docs/tmp/260827-fix-inference-accounting.md` | [`../history/260827-fix-inference-accounting.md`](../history/260827-fix-inference-accounting.md) | `a887f9123a0db4d426b2963ec32d6a506fd19e4e11df5cc6c25ac4fef71c18f6` |

迁移前已在 source 计算 SHA-256；迁移后在 destination 重新计算，值相同。复核时 source 不存在，destination 存在。

## 权威边界

该文件记录 `inference.py` / `stream.py` 记账修复及复核，是历史实施材料而不是 current authority。它含 retry 交叉项，但 error-envelope 是其最终 archive owner。完整索引与使用边界见 [`../history/README.md`](../history/README.md)；判断当前错误信封行为应以本主题现行 `spec.md`、`status.md`、`deferred.md` 及代码为准。
