# 运行时取证评审处置

状态：closed。

评审原文：`260904-runtime-forensics-review-general-opus.md`。

被评点时报告：`260904-runtime-forensics.md`。

| 发现 | 级别 | 裁定 | 处置 |
|---|---|---|---|
| Major 1：`1151.0s` 与 `1148.5s` 的两个 request id 映射颠倒 | C | 采纳 | 不改写点时报告正文；在报告顶部增加勘误，规定正确映射为 `1151.0s → 362cc93c… /v1/messages`、`1148.5s → e628c955… /v1/responses`，并说明映射依据是 monotonic residual 而不是 wall registration 顺序。Living status 只采用纠正后的口径。 |
| Major 2：已确认最小链错误纳入 client-level reissue | C | 采纳 | 不改写点时报告正文；在报告顶部增加勘误，把已确认链收窄为“pre-response disconnect 未被读取 → detached request 继续 dispatch/retry → active 数超过 live H1 connections、age 继续增长”。客户端是否另发请求保留为候选，不作为现场 accumulation 的必要步骤。Living status 与最终结论采用收窄后的口径。 |

没有驳回或暂定发现。原 reviewer 在勘误与 living status/spec 同步后只读复核，结论为 `pass`，无剩余 blocker/major。