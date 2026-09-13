# 流式响应体 ReadTimeout 日志改进报告

## 任务与安全边界

- 目标：让一次请求在收到一个或多个上游 HTTP 成功响应头后，若读取流式响应体发生 `ReadTimeout`，能够从完成行和持久化 request record 判断每次 body attempt 是否收到字节、收到多少、以及失败发生在请求开始后的何时。
- 不记录请求或响应正文，不记录 headers、URL query、认证信息或配置敏感值；新增证据只允许包含状态码、计数、monotonic 相对时间、异常 module/type 和完成状态。
- 原始捕获在目标请求开始时已达到单文件配额，因此不把 raw capture 当作该请求 body 的证据，也不尝试绕过配额。
- 工作树起始时已有大量用户脏改动；本任务只会触碰直接相关实现、测试与本报告，并在收尾逐项核对 diff。

## 已读依据与现状

- living spec：`docs/.human-controlled/upstream-retry-and-continuation.md` 规定未向客户端交付完整块时，网络中断和请求超时可透明重放；因此一次客户端请求可对应多个均已收到 HTTP 200 headers 的上游 body attempt。
- 架构说明：`docs/.human-controlled/request-pipeline.md` 将每次上游尝试建模为 `UpstreamAttempt`，重试与上游收发归 `app.pipeline` 所有。
- 生产计数边界：`src/app/server/routes/inference.py::_counted_upstream` 位于 `response.aiter_bytes()` 外层，能够观察解码后 body chunk、pull 开始、EOF/异常和 attempt ordinal；这是不读取正文而区分“headers-only/zero bytes”和“收到过 body bytes”的正确 seam。
- 当前完成行只给出 request-wide `bytes_out` 总数以及 `retries=N after ReadTimeout('')`；它无法把总字节映射回某一次 HTTP 200。
- 当前 schema v2 record 的 `observation.timings` 只保留 latest body attempt 的 timing，新的 replay 会调用 `RequestTrace.begin_upstream_body_timing()` 覆盖前一次 timing；`observation.body_bytes.upstream_response` 与顶层 `bytes_out` 都是 request-wide 累加值。因此历史 attempt 是否为 0 bytes、各自在何时失败会丢失。
- 当前 raw capture 能逐 attempt 写 body event，但它是有配额的可选诊断面，且本次事故已明确没有该请求的可用 capture；完成记录不能依赖它。

## 可证伪假设（实现前）

1. **首要假设：信息在 replay 时被聚合/覆盖，而不是 transport 没有提供观察点。** 预测：构造 attempt 1 收到少量 bytes 后 `ReadTimeout`、attempt 2 在首字节前 `ReadTimeout`、attempt 3 完成的真实 ASGI 路径，现有 record 只能给出总 bytes 和 attempt 3 timing，完成行不能区分前两次；在 `_counted_upstream` 保留逐 attempt 安全元数据后，同一路径可完整区分。
2. **次要假设：只扩充 `replaced_failures` 字符串不足。** 预测：即使把当时总 bytes 拼到异常文本，第二次 attempt 看到的是跨 attempt 累加值，且持久化数据仍不可结构化查询；因此需要 attempt-local counter，而不是只在 `_reopen` 包装异常。
3. **次要假设：HTTP 200 日志不证明 body 已到达。** 预测：让 async body iterator 在第一次 pull 立即抛出 `ReadTimeout` 时，httpx 仍已记录 200；`_counted_upstream` 的 attempt-local bytes/chunks 应为 0。
4. **已排除为修复方向：提高或绕过 raw capture 配额。** 这只能改善另一条可选证据链，不能修复完成行/持久化记录，而且会扩大正文与敏感信息保留面。

## 计划中的最小设计

- 在 `RequestTrace` 上保留有界于 retry budget 的逐 body attempt 结构化 observation；每项只含 attempt ordinal、HTTP status、body bytes/chunks、body pull/first/last/end 的 monotonic 相对时间、结束状态与异常 module/type。
- `_counted_upstream` 在实际消费 body 的同一层更新 attempt-local observation；不检查、不缓存也不渲染 chunk 内容。
- request record 在 `observation` 下新增逐 attempt 数组，保留所有 attempt；现有 request-wide 和 latest-attempt 字段继续保留，避免破坏既有读者。
- 完成行只在存在多个 body attempts 或 body attempt 失败时增加紧凑逐 attempt 摘要；既有普通成功行不增长。摘要给出 ordinal/status/bytes/failure elapsed，异常类型仍由已有 `after ...` 提供。

## 实现结果

### 数据模型与采集

- `src/app/observability/request_log.py` 新增 immutable `UpstreamBodyAttempt`，只保存安全元数据：
  - `attempt`、`status_code`
  - `body_started_s`、`first_byte_s`、`last_byte_s`、`final_pull_started_s`、`ended_s`
  - `final_pull_s`、`tail_gap_s`
  - `body_bytes`、`chunks`
  - `outcome`（`open` / `complete` / `error`）
  - `exception_module`、`exception_type`
- `src/app/observability/request_trace.py` 在继续维护原有 request-wide/latest-attempt 字段的同时，append 并更新每个 immutable attempt snapshot。新的 replay 不再覆盖旧 attempt 的 bytes/timing/outcome。
- `src/app/server/routes/inference.py::_counted_upstream` 在三个生产接线点接收该 response 的 HTTP status，并在实际 body pull 边界：
  - 第一次 pull 前建立 attempt；
  - 每个 decoded chunk 增加 attempt-local bytes/chunks；
  - 普通 EOF 标成 `complete`；
  - 普通 body 异常标成 `error`，只提取异常 class 的 module/qualname，不提取 message、request 或 response。
- 现有 `received`、`upstream_chunks`、latest-attempt timing 保持原语义，因此既有 footer、顶层 JSONL 字段和读者不需要迁移。

### 持久化记录

- `FinalizedRequest` 冻结 `tuple[UpstreamBodyAttempt, ...]`，避免 publish 后再受 mutable trace 影响。
- schema v2 的 `observation` 新增 additive 数组 `upstream_body_attempts`。没有改动既有顶层 v1-compatible keys，也没有删除/改名既有 v2 字段。
- 每个数组项完整保留“第几次、哪个 HTTP status、是否 0 bytes、chunk 数、首/末字节相对时间、失败/完成相对时间、最后一次 pull 等待、异常 class”。
- 数组项没有 body/content/message/header/URL/token/config 字段；测试对 key set 做封闭断言，并确认合成 body marker 不出现在序列化 attempt observation 中。

### 完成行

- `format_completion_line` 接收 finalized attempt tuple。
- 仅在 body attempt 多于一个，或唯一 body attempt 以 error 结束时添加 `body-attempts=...`；普通单 attempt 成功行保持原宽度。
- 每项为紧凑的 `<ordinal>:<status>/<decoded-body-bytes>/<outcome>@<request-relative-time>`。这使已有按顺序输出的 `retries=N after <exceptions>` 可以与每次 HTTP 200 的 0/nonzero bytes 及失败时刻一一对应；完整的精确 timing 仍在 JSONL。

## 验证结果

- 已建立紧反馈环：`uv run pytest -q tests/int/test_pipeline_app.py::test_each_successful_header_attempt_records_its_body_progress_before_read_timeout`。
- 红灯已确认：真实 ASGI + SDK/`MockTransport` 路径依次制造“HTTP 200 + 收到一个不完整 chunk 后 `ReadTimeout`”、“HTTP 200 + 首字节前 `ReadTimeout`”、“HTTP 200 + 完整响应”。客户端最终收到第三次响应，三次上游调用均发生；当前 record 在读取 `observation.upstream_body_attempts` 时以 `KeyError` 失败。捕获到的现有完成行只有 request-wide `↓386B` 和 `retries=2 after ReadTimeout(''); ReadTimeout('')`，正好复现无法把 bytes/time 映射到每次 200 的报告症状。
- 该反馈环约 4 秒、确定性、无人值守，直接穿过生产 `_counted_upstream`、透明 replay、finalization、console logger 与 JSONL writer，不依赖 raw capture。
- 绿灯：
  - 新增端到端回归：`1 passed`。
  - 聚焦 replay + logging suite：`144 passed`。
  - 直接相关 observability + stream delivery suite：`217 passed`。
  - `ruff check`（本任务涉及文件）：通过。
  - `pyright`（本任务涉及文件）：`0 errors, 0 warnings, 0 informations`。
  - `git diff --check`：通过。

## 回归测试的判别力

新增测试不是只断言“不抛错”：

1. 验证三次 upstream call 和最终第三次完整交付，确保透明 replay 真实发生。
2. 验证 attempt 1 为 `200 / nonzero bytes / 1 chunk / error / ReadTimeout`。
3. 验证 attempt 2 为 `200 / 0 bytes / 0 chunks / error / ReadTimeout`，且首/末字节时间为 `None`。
4. 验证 attempt 3 为 `200 / complete`，并精确核对累计 body bytes。
5. 验证 error attempt 的 `ended_s`、`body_started_s`、`last_byte_s` 关系，证明记录能回答失败发生在何时。
6. 验证完成行同时出现三个 attempt 的 status/bytes/outcome/time，且保留原有 ordered `ReadTimeout` retry cause。
7. 验证持久化 attempt schema 不含正文或动态异常 message。

## 工作树纪律

- 起始工作树已包含多处 staged/unstaged/untracked 用户改动，其中 `request_log.py`、`inference.py`、`test_pipeline_app.py` 已经是 dirty；这些既有 hunks 均保留，没有 reset、checkout、stash、format 或批量重写。
- 本任务实际编辑范围仅为：
  - `src/app/observability/request_log.py`
  - `src/app/observability/request_trace.py`
  - `src/app/observability/request_completion.py`
  - `src/app/server/routes/inference.py`
  - `tests/int/test_pipeline_app.py`
  - `tests/unit/observability/test_request_completion.py`
  - 本报告
- 会话过程中共享工作树又出现了不属于本任务的其它 dirty paths；未对它们做任何修改或回退。

## 结论与边界

- 首要假设得到证实：缺口来自 request-wide 聚合和 latest-attempt 覆盖，transport/body iterator 本身已有足够的无正文观察点。
- 现在 raw capture 即使关闭、达到配额或不可用，完成行与常规 request JSONL 仍能独立回答每次已消费的流式 body attempt 是否收到 bytes、收到多少、何时结束、是否因 `ReadTimeout` 类异常结束。
- 计数是 `httpx2.Response.aiter_bytes()` 交给应用的 decoded body bytes，不是 TLS/HTTP framing wire bytes；时间均为相对请求开始的 monotonic offset，不是 wall-clock timestamp。
- 只有实际开始消费的 body 才会产生 attempt observation；收到 headers 后若 response body 从未被任何调用方 pull（例如更早的下游中止），不会伪造一个“0 bytes timeout”结论。目标事故中的透明 replay 必须 pull body 才能观察并处理 `ReadTimeout`，因此每个被重试的 HTTP 200 都在覆盖范围内。
