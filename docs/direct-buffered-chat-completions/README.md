# Direct buffered Chat Completions

本话题描述 direct OpenAI Chat Completions 的两条缓冲路径如何共享完整性判读、透明重试与 provider-side observation，同时保持 model provider 只声明能力并执行原样 HTTP 发送。

## 权威与阅读顺序

1. [`decisions.md`](decisions.md) 记录用户在 2026-09-05～06 直接作出的范围与行为裁决，以及代理依据既有合同作出的派生判断。
2. [`design.md`](design.md) 记录获用户确认的架构、数据流、错误处理、实施切片与验证范围。
3. [`plan.md`](plan.md) 把设计拆成八个有序语义任务，并定义接口、验证与提交边界。
4. [`.dev/docs/direct-passthrough/spec.md`](../direct-passthrough/spec.md) 是 direct streaming Chat 交付、commit frontier 与 replay 的行为权威。
5. [`.dev/docs/error-envelope/spec.md`](../error-envelope/spec.md) 是最终失败 carrier 的行为权威。
6. [`.dev/docs/tui/spec.md`](../tui/spec.md) 是 console 与 durable response observation 的行为权威。
7. [`status.md`](status.md) 记录当前实施状态；[`deferred.md`](deferred.md) 只保存本次范围外仍未闭合的P6与translated multi-choice事项，两者都不替代上述Spec。

调查、独立评审与逐项处置原件均位于 [`reports/`](reports/)；其中 `260905-*` 与 `260906-provider-content-boundary-addendum.md` 是设计前调查。它们都是时点记录，不是当前行为权威。
