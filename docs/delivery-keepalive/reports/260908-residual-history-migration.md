# delivery-keepalive residual canonical-history migration

- **日期**：2026-09-08
- **工作目录**：`/home/xp/src/ghc-api-proxy-py`
- **范围**：仅执行 residual ledger 中 destination 属于 `delivery-keepalive` 的 `canonical history` 行。
- **执行边界**：未处理任何 `delete` 行；未删除目录；未执行 `git add`、commit 或 push。

## 逐项结果

| # | exact source | canonical destination | SHA-256（迁前/迁后） | 结果 |
|---:|---|---|---|---|
| 1 | `.dev/docs/empty-text-block/reports/260820-empty-text-block-copilot-api-js.md` | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-copilot-api-js.md` | `8708e49e327931777064cdba4636911fc3197a8a4571429fca336cbcb5ad4bfd` / 同值 | 已移动；source absent，target present |
| 2 | `.dev/docs/empty-text-block/reports/260820-empty-text-block-inbound-trace.md` | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-inbound-trace.md` | `1630b7d7ebde975f995465e57022c18455b4defd19f9781c9cf0553c8aaa9ab0` / 同值 | 已移动；source absent，target present |
| 3 | `.dev/docs/empty-text-block/reports/260820-empty-text-block-response-side.md` | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-response-side.md` | `916ee85da84beb1cf9d5117c4aad619c5957c61c5de1c3070e0f13b169464b50` / 同值 | 已移动；source absent，target present |
| 4 | `.dev/docs/empty-text-block/reports/260820-empty-text-block-synthesis.md` | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-empty-text-block-synthesis.md` | `5855c8fae75c82d5b000f098ac9116aa47b83b993c70d3c0f4c754769bf4bc54` / 同值 | 已移动；source absent，target present |
| 5 | `.dev/docs/empty-text-block/reports/260820-review-blank-text-subscriber.md` | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-review-blank-text-subscriber.md` | `d43c1ae6c541842fcade185daafc3c9b038605ab2496302a8e947aa894db2c7b` / 同值 | 已移动；source absent，target present |
| 6 | `.dev/docs/empty-text-block/reports/260820-review-final-and-probe.md` | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-review-final-and-probe.md` | `e866887b5cad2be6bcf4f38fbbad4218067b282e74f7dcbe59dc2dfd7d747b54` / 同值 | 已移动；source absent，target present |
| 7 | `.dev/docs/empty-text-block/reports/260820-review-unconditional-blank-strip.md` | `.dev/docs/delivery-keepalive/history/empty-text-block/reports/260820-review-unconditional-blank-strip.md` | `03400a4f2775de61b8d02695a6b64b3ce0efe07b7ac0e6240d6a012675ea7b79` / 同值 | 已移动；source absent，target present |

## 验证

- 迁移前逐项确认 source 存在、destination 不存在，因此没有覆盖既有文件。
- 迁移后逐项确认 source 不存在、destination 存在，并以 SHA-256 复核字节不变。
- `history/README.md` 已新增 `empty-text-block` evidence family 索引及 provenance/current-authority 边界。
- 本次没有执行测试；本操作仅涉及文档原件移动与索引/报告写入。
