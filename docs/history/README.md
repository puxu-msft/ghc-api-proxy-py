# History 文档入口

- 行为权威：[`spec.md`](spec.md)
- 当前实现边界：[`status.md`](status.md)
- 长期候选：[`deferred.md`](deferred.md)
- 共享 review disposition：[`../observability/review-disposition.md`](../observability/review-disposition.md)

History 是跨重启查询的 request projection；它不是 raw capture stream，也不是 RequestJournal。实现状态不得反向修改 Spec 的行为合同，已接受的当前限制写在 `status.md` / `deferred.md`。
