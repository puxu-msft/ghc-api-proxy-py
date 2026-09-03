# HTTP 499 retry implementation notes

- status: current
- requirement_authority: `docs/.human-controlled/upstream-retry-and-continuation.md` 中的 `499 Client Closed Request` 可重试条目
- implementation: 2026-09-04 `fix: retry upstream HTTP 499 responses`
- status_and_evidence: `status.md`
- review_disposition: `review-disposition.md`

## 文档边界

用户于 2026-09-04 接受 HTTP 499 retry 的需求修订，并把用户控制需求文档收敛为一条 `499 Client Closed Request`。用户同时明确：此前候选中的详细解释本身正确，但不应放入该需求文档。因此，需求层只承载“499 可以继续／重试”；本文件承载实现机制、观测依据、边界和未采用方案，不把这些派生细节冒充为用户裁决。

## 生产观测与结论强度

2026-09-03 的 rejected capture 显示：上游在单次请求约 123.1 秒后返回空体 HTTP 499，本代理已经向上游发送 2,859,854 bytes、请求含 624 个 input item，但尚未向下游交付响应，最终记录 `attempts=1`。

这些事实足以支持两项行动：当前 499 是上游对本代理请求作出的 HTTP 响应，不是本代理观察到下游客户端已经断开；修复应落在 upstream SDK error normalization 边界。它们不支持断言 GitHub Copilot 为什么产生 499。请求体大小与约 123 秒延迟是相关观测，不作为 retry 条件或成因结论。

## 当前实现

`src/app/model_provider/ghc_client/errors.py` 的 `RETRYABLE_STATUSES` 包含 499。OpenAI SDK 抛出的 `APIStatusError(499)` 经 `normalize_upstream_error()` 成为 `UpstreamError(status_code=499)`，而不是确定性的 `UpstreamRejected`。

`classify()` 因而返回 `Disposition.RETRY`，`reason_for()` 将该有状态瞬时失败归入 `RetryReason.SERVER_ERROR`。重试沿用 `upstream_request_retry.strategies.serverError.max_retries` 与共享 `max_total`，不新增 499 专用计数器、配置或冷却间隔。SDK 自身 retry 仍关闭，重试由 `DirectDriver` 统一驱动。

HTTP status exception 在 driver 返回 downstream response 之前产生，因此首个 499 没有已交付的语义事件需要去重。既有 client request deadline、attempt deadline 与 draining gate 继续约束重试；本次变更没有新增并发状态或绕过这些门。

## 预算耗尽后的错误呈现

预算耗尽或 draining 拒绝 retry 时，`PipelineAbort.cause` 保留最后一次 upstream 499。通用 error edge 随后保留 499 status 与可转发响应头，并按既有 direct/translated contract 呈现 body：仅在 direct 且 upstream source bytes 非空时原样传递 body；translated 路径或 observed empty body 写客户端格式的 error envelope。

本实现不为 499 增加第二套 error-body passthrough 规则。这样 status classification、retry exhaustion 与所有其它 upstream failure 继续共用一个 wire contract。

## Capture 与 observability

`capture_rejection()` 只接收 `UpstreamRejected`。499 改为 `UpstreamError` 后，不再作为确定性请求拒绝写入 rejected request capture。

请求记录保留最终 attempt 总数，但 header-stage retry 被成功替换时，不会把首次 499 failure category 单独写入 `replaced_failures`。本次没有扩展这一 observability 面，因为它不是 499 retry 控制流正确性的前置条件；若以后需要逐 attempt 失败原因，应单独修订 observability Spec、trace 投影与判别测试。

## 回归边界

`tests/unit/model_provider/ghc_client/test_http_499_retry.py` 覆盖：

- 499 normalization 为 `UpstreamError`、classification 为 retry、reason 为 `serverError`。
- 首个 499 后第二次 attempt 成功。
- `serverError.max_retries=1` 时第二个 499 终止流程，最后 499 保留为 cause 与最终 status。
- 相邻且未列入集合的 498 仍为 `UpstreamRejected`，避免把全部 4xx 泛化为 retryable。

旧实现正控会在首个 `isinstance(..., UpstreamError)` 断言处得到 `UpstreamRejected` 并失败。完整运行命令、结果和覆盖范围记录在 `status.md`。

## 未采用的方案

- 不把 499 放入 `network`。`network` 处理 timeout、连接失败与其它无状态失败；499 已经有 HTTP status，沿用 `serverError` 保持分类一致。
- 不新增 `http499` 配置。现有 per-reason 与 shared total budget 已表达次数上限。
- 不在 driver 中特判 `status_code == 499`。SDK error normalization 是 upstream vocabulary 进入 pipeline closed set 的唯一边界；在 driver 特判会让 classification、capture 与 error passthrough 分裂。
- 不为 499 建独立 body 透传规则。通用 error envelope 已表达 direct/translated 与 source bytes 边界。
- 不在本次顺带增加 header-stage failure-category persistence。该能力有独立的 observability contract 与测试面。

## 评审记录

- 初评：`reports/260904-http-499-review-general-opus.md`
- 限定复评：`reports/260904-http-499-rereview-general-opus.md`
- closeout review：`reports/260904-http-499-closeout-review-general-sonnet.md`
- 用户裁决整合评审：`reports/260904-http-499-user-ruling-integration-review-general-opus.md`
- 用户裁决整合限定复评：`reports/260904-http-499-user-ruling-integration-rereview-general-opus.md`

所有 finding 的终态、未采用路线与仍 open 的外部动作以 `review-disposition.md` 为权威。
