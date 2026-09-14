# Replay 文档入口

- 行为权威：[`spec.md`](spec.md)
- 当前实现边界：[`status.md`](status.md)
- 长期候选：[`deferred.md`](deferred.md)
- 共享 review disposition：[`../observability/review-disposition.md`](../observability/review-disposition.md)

Replay 是独立 process/CLI，不接入主程序 request path，也不自动复用 source headers/credentials。
