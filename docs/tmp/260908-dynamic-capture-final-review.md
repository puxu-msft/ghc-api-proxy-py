# 动态条件式 raw capture 最终只读验收报告

## 评审范围
基准是 `/home/xp/src/ghc-api-proxy-py` 当前工作树相对 `HEAD` 的条件式 raw capture 相关状态。审查范围包括 SQLite `DebugCaptureRuleStore`、`/api/debug/capture-rules` CRUD、Chain/composition/config path/schema、路由解析后的规则匹配与入站 body 补录、`RawCaptureStore` 的 CBOR/zstd 与配额/poison/ack 接线、direct driver 与 count_tokens 的失败 wire evidence 和 attempt 编号、请求完成 `complete=false` 诊断、对应测试，以及 `.dev/docs/raw-capture/spec.md`。

本报告不评价同一工作树中与上述合同无关的 Responses 形状、协议目录迁移、Docker、实验目录及其他未提交改动。未编辑源文件；没有读取、输出或依赖任何真实 capture 正文、认证信息或真实数据库内容。为验证失败路径，使用了不落盘的 synthetic probe，只输出事件类型、长度和布尔结果。

## 总体 verdict
**needs-fix**

## Blocker 数
0

## Findings

### RC-001 — major — 未命中规则的 4xx 仍通过 legacy rejection capture 落盘正文，绕过条件式选择与二进制格式

- `finding_id`: `RC-001`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:795-827`
- `related_locations`: `src/app/observability/rejection_capture.py:46-85`、`.dev/docs/raw-capture/spec.md:23、33、50`
- **判据**：用户合同要求只有命中 `provider + resolved model-id + session-id + optional exact agent-id` 的请求才记录正文；ACTIVE raw-capture Spec §2.1 和 §4 要求未命中请求不记录原始 body，并规定新 capture 文件使用 CBOR/zstd。
- **证据**：inference 的两个 upstream failure 分支无条件调用 `capture_rejection(context, error, ...)`，没有检查 `completion.raw_capture` 或规则命中状态。`capture_rejection()` 对任意 `UpstreamRejected` 把 `context.payload`、`error.body` 和 `error.sent` 写入 `user_data_path()/rejected/*.json`。因此一个没有 debug capture rule 的确定性 4xx 也会创建正文文件，而且不是 `.cborseq.zst`。
- **影响**：条件式 raw capture 的选择边界被绕过；未命中请求仍会产生原始 request/response 内容的持久化副本，且落盘格式与本轮二进制合同不一致。该路径不需要认证信息或真实数据库即可由静态调用链确认，定为 `major`。
- **修复方向**：明确把 legacy rejection capture 从本合同中移除或改为仅由同一规则命中状态驱动，并禁止它另建 JSON 正文文件；若产品确实要保留独立的 always-on 4xx 证据机制，则必须由用户在 raw-capture Spec 中明确写出例外及其独立安全/配额合同，不能让现有实现默认为例外。

### RC-002 — major — read-timeout 失败会丢失已经实际发出的 upstream request body

- `finding_id`: `RC-002`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/upstream_errors.py:151-152`
- `related_locations`: `src/app/pipeline/direct_driver/base.py:176-192`、`src/app/pipeline/driver.py:526-548`、`.dev/docs/raw-capture/spec.md:33、50`
- **判据**：命中规则后，每个实际 upstream attempt 必须保留实际发送/收到的 body 与 attempt 边界；失败 attempt 不能只剩一个边界标记。
- **证据**：`httpx2.ReadTimeout` 可以携带已构造的 request；当前 `normalize_upstream_error()` 将所有 timeout 转成没有 `sent` 字段内容的 `UpstreamTimeout`。`capture_failed_upstream_attempt()` 只有在 `UpstreamError/UpstreamRejected.sent` 非空时才写 `upstream.request.body`，所以 direct driver 与 count_tokens 的 timeout except 分支最终只写 `upstream.attempt.end(complete=false)`。不落盘 synthetic probe 使用带 request 的 `ReadTimeout`，确认规范化后的 sent 长度为 0，capture helper 记录的 wire event 数为 0；probe 没有输出 request body。
- **影响**：一个请求已经进入 response-read 阶段但上游超时的命中请求，无法用 capture 重放实际发送的 request body；count_tokens 与普通 direct path 共用该缺口。它直接违反失败 wire evidence 合同，定为 `major`。
- **修复方向**：在 provider error normalization 到 capture helper 的边界安全地传递 request-attached wire bytes，并区分 connect-before-send 与 read-after-send，避免把“未发送”错误地记录成已发送，也避免把正文写入普通日志。

### RC-003 — major — 普通 completion log 与请求完成记录会复制 upstream error body 中的任意 message

- `finding_id`: `RC-003`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/error_classify.py:105-126`
- `related_locations`: `src/app/server/routes/inference.py:819-827`、`src/app/observability/request_log.py:814-816`、`src/app/observability/request_completion.py:969`、`.dev/docs/raw-capture/spec.md:52、70-72`
- **判据**：用户合同与 Spec §4.2、§6 要求普通日志和请求完成记录不得复制 raw request/response body、headers、token 或原始 identity，只能记录安全诊断元数据和固定原因/事件/complete 信息。
- **证据**：`_from_upstream()` 从 upstream response body 的 `error.message` 构造 `ErrorInfo.message`；inference 将它写入 `trace.detail`，completion line 直接渲染 `line.detail`，structured request record 也直接写入同一个 `detail`。不落盘 synthetic formatter probe 只输出布尔结果，确认任意输入的 response-body message 会同时出现在 completion line 和 completion record 的 detail 中；没有输出该 message 本身。
- **影响**：上游错误 body 若回显 prompt、工具输入或其他敏感内容，会进入普通 console/structured completion observability，绕过 raw capture 的显式规则和安全 warning 合同。该路径不需要真实 upstream 或真实 capture 文件即可确认，定为 `major`。
- **修复方向**：普通日志与请求完成记录只保留固定安全原因/类型/状态元数据；上游原始错误 body 仅在规则命中的 capture 中保存，客户端错误响应是否继续携带 upstream 内容应与日志记录路径分离。

### RC-004 — minor — raw-capture Spec 头部仍标为 ACTIVE v5，但修订记录已经进入 v6

- `finding_id`: `RC-004`
- `severity`: `minor`
- `status`: `open`
- `primary_location`: `.dev/docs/raw-capture/spec.md:4`
- `related_locations`: `.dev/docs/raw-capture/spec.md:78-83`
- **判据**：项目工作流要求 Spec 是当前唯一权威、修订记录与正文状态同步；本轮验收必须按包含 request_incomplete、缺失 agent sentinel、失败/丢弃 attempt 与 count retry wire evidence 的 v6 合同判断。
- **证据**：文件头写着 `ACTIVE v5`，但同一文件的修订记录已经列出 2026-09-08 的 v6，并明确加入本轮要验收的失败诊断和 count retry 要求。读者按头部版本工作时会误以为 v6 条款尚未生效。
- **影响**：实现、测试和后续评审可能采用不完整的规范版本；不会直接改变运行时行为，但会削弱本功能的验收与交接可信度，定为 `minor`。
- **修复方向**：在 Spec 自身修订记录中同步头部 ACTIVE 版本，并确保对应测试/实现引用当前版本；本次只读验收未修改 Spec。

## 上轮 finding 完成度

- 非重试 4xx wire evidence 与返回后 discard：**closed in the reviewed paths**。direct driver 已有 `capture_failed_upstream_attempt()` 与 `capture_returned_upstream_response()`；规则命中的拒绝集成测试通过，并覆盖 request/response event 的存在。
- count_tokens retry attempt 编号：**closed for the covered retry path**。三次 count upstream call 的 capture attempt start 为 `0, 1, 2`，对应 response status 证据为两次失败后一次成功；集成测试通过。
- count_tokens 异常 wire evidence：**closed for the covered normalized response-error path**。count except 分支复用失败 evidence helper，相关集成测试通过；RC-002 记录了 timeout 类仍未闭合的独立缺口。
- `request_incomplete`：**closed for the no-earlier-drop path**。writer 成功而 request `complete=false` 时会产生一次安全完成 warning，包含 `reason=request_incomplete`、首个缺失 event、response body completeness 和 `forensic_replay_complete=false`。
- 空白 API 条件：**closed**。Pydantic 请求校验在 strip 后拒绝空白条件并返回 422。
- 缺失 agent sentinel：**closed**。缺失 agent 使用独立 tagged identity，和真实 agent 字符串分组分离；对应单元测试通过。

## 验证结果

- `uv run pytest -q tests/unit/observability/test_debug_capture.py tests/unit/observability/test_raw_capture.py tests/int/test_pipeline_app.py -k 'raw_capture or capture_rules'`：17 passed，279 deselected。
- `uv run pytest -q tests/unit/config/test_config_schema.py -k raw_capture`：1 passed，58 deselected。
- `uv run pytest -q tests/unit/pipeline/test_direct_driver.py`：41 passed。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'rule_selected_count_capture or rule_selected_rejection_capture'`：2 passed，277 deselected。
- `uv run pytest -q tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py tests/unit/observability/test_request_log_file.py tests/unit/observability/test_response_observation_projection.py`：157 passed。
- `uv run pytest -q tests/unit/pipeline/delivery/test_stream_delivery.py -k 'attempt or counted'`：2 passed。
- scoped `uv run ruff check ...`：通过。
- scoped `uv run pyright ...`：0 errors，0 warnings，0 informations。
- 为了确认路由/模块边界，额外运行 `tests/unit/pipeline/test_model_resolution.py tests/unit/test_module_boundaries.py`：61 passed，1 failed。唯一失败是 `test_the_archived_chain_is_not_importable_at_all`，因为当前共享工作树中存在与本轮 raw capture 无关的 `app.protocols` 迁移状态；该失败不用于否定本报告的 raw-capture 结论。

## 搜索面与未覆盖面

已读当前 raw-capture Spec、候选文档、API/config 说明、debug capture store、raw capture store、inference routing、direct/count driver、completion/log projection、composition/Chain 和对应单元/集成测试；检查了所有 raw capture 规则匹配、事件写入、attempt 和完成诊断调用点。未运行真实 upstream、真实端口、真实磁盘故障或多进程 SQLite 压力；未读取或输出真实 capture 文件、认证信息或真实数据库内容。
