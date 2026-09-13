# 条件式 raw capture 最终只读验收

## 评审范围

评审对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树相对 `HEAD` `c0fadf8d` 的条件式 raw capture 及其安全修复。范围包括 SQLite 规则存储、HTTP CRUD、路由后 provider/model-id 绑定、session/agent 分组、CBOR Sequence + zstd writer、失败与 timeout attempt 证据、rejection capture 退役、普通 completion/response observation 安全投影、配置兼容行为和 `.dev/docs/raw-capture/spec.md`。

判据来源是用户本轮合同与 `.dev/docs/raw-capture/spec.md` 当前内容（`ACTIVE v7`）。没有把实现反推成判据。

本次只读检查没有读取、输出或依赖真实 capture 正文、token、header 或数据库内容。合成探针只输出事件类型、布尔值和测试结果；没有运行真实 upstream、真实端口或真实数据库流量。

## 总体 verdict

**needs-fix**

## Blocker 数

0

## 高置信发现

### RC-005：major — 429 与 request-attached transport failure 丢失 upstream request wire body

- `finding_id`: `RC-005`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/upstream_errors.py:161-194`
- `related_locations`: `src/app/pipeline/exceptions.py:78-107`、`src/app/pipeline/direct_driver/base.py:176-193`、`src/app/pipeline/driver.py:535-543`、`.dev/docs/raw-capture/spec.md:50、83`

命中规则的 capture 要保留每个实际 upstream attempt 的 request/response body。当前 `_sent_body()` 已能从异常自身或其 response 取 request，且 `ReadTimeout` 分支已经把结果传入 `UpstreamTimeout.sent`，但 status `429` 分支构造 `UpstreamRateLimit` 时没有传入 `sent`，`UpstreamRateLimit` 也没有接收该字段；无响应的 transport failure 分支同样直接构造 `UpstreamError`，没有传入 `_sent_body(error)`。

`capture_failed_upstream_attempt()` 只有在 `upstream_error.sent` 非空时才写 `upstream.request.body`。因此一个带 request 的 429 failure capture 只会得到 response start/body/end，不会得到 request body；一个带 request 的 transport failure capture 则完全没有 request body。合成探针确认：`ReadTimeout` 路径保留了 request event，而 429 路径事件只有 `response-start,response-body,response-end`；带 request 的 `ConnectError` 归一化后 `sent` 仍为空。探针没有输出任何 body 内容。

影响是命中规则的失败请求无法用 capture 重放实际发送的 request wire bytes，且不能区分“请求已发送但上游返回 429/连接失败”和“请求尚未发送”。这直接违反 v7 对失败 attempt 的完整 wire 证据要求，定为 `major`。

修复方向：让 `UpstreamRateLimit` 与其他 upstream failure 统一携带 `sent`，在 429 与 response-less transport 分支传入 `_sent_body(error)`，并为这些分支补充只检查事件存在和布尔结果的回归测试。若产品要区分“实际发送了零长度 body”和“没有可取得的 request”，还需要单独的 observed 标记，而不能继续用空 bytes 兼任两种状态。

## 逐条完成度

- 未命中请求通过 legacy `rejection_capture` 落盘正文：**closed**。当前 `rejection_capture` 只是无持久化兼容 shim，生产 `src/app` 中没有其他调用点；对应单元测试通过。
- `ReadTimeout` 的 request-attached body 没有进入 capture：**closed for the requested timeout path**。`_sent_body()` 先读取异常的 request，归一化后的 `UpstreamTimeout.sent` 被 `capture_failed_upstream_attempt()` 写入；合成 probe 和现有 normalization 测试均通过。
- 普通 completion/response observation 复制 upstream error body/message：**closed in the reviewed response paths**。`_safe_failure_detail()` 对 upstream exception 只保留 status/固定阶段信息；`ResponsesObserver` 只保留 type、code 和固定的 `upstream error message present`，不保留原 message；缓冲错误的 structured record 与 completion line 使用安全 detail。
- safe error projection 改变 provider-failure 状态判断：**closed**。`ResponseObservation.provider_failed` 依据 terminal/status/error 的结构化存在性判断，不依赖被安全替换的 message；现有 provider-failure projection 测试通过。
- partial-write 后共享 path 继续被当作完整：**closed in the reviewed implementation**。当前 store 对 partial frame 登记 path poison，后续同 path capture 得到 `path_poisoned`，新 store 首次 append 前使用生产 reader 校验；对应测试通过。
- Spec 版本与修订记录：**closed**。`.dev/docs/raw-capture/spec.md` 头部是 `ACTIVE v7`，修订记录最后一项也是 v7，并包含本轮 rejection、timeout 和安全投影修复内容。

## 其余合同核对

- SQLite 规则表、唯一约束与 HTTP `GET/POST/DELETE /api/debug/capture-rules` 均已接线；POST 是按四元组幂等，DELETE 缺失规则返回 404。
- 匹配在路由解析出 provider 与 resolved model-id 后、第一次 upstream attempt 前发生；规则值经过 strip 后按 provider、model-id、session-id 精确比较，agent-id 非空时精确匹配，空 agent-id 表示该 session 下任意 agent。
- 没有匹配规则时不会启动 request capture，也不会创建 capture 文件或记录原始 inbound body；旧 `enabled: true` 被 `RawCaptureConfig.enabled: Literal[False]` 拒绝，不能重新开启全量 capture。
- 命中后使用 `.cborseq.zst`，每个 CBOR map 独立压缩为 zstd frame；inbound body、成功 attempt、rejected attempt、client response 和 retry 边界均有接线。当前唯一未闭合的是 RC-005 指出的部分失败类型 request body。

## 验证结果

- `uv run pytest -q --basetemp=... tests/unit/observability/test_raw_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_completion.py -k 'raw_capture or rejection_capture or timeout or provider_error or provider_failure or finalized_request or response_observation'`：96 passed，77 deselected。
- `uv run pytest -q --basetemp=... tests/int/test_pipeline_app.py -k 'raw_capture or capture_rules or buffered_responses_status_error or streamed_responses_completed_with_error or successful_header_attempt'`：6 passed，273 deselected。
- `uv run pytest -q --basetemp=... tests/int/test_error_envelope.py -k 'direct_leg or translated_path or upstreams_status'`：5 passed，44 deselected。
- scoped `uv run ruff check`：通过。
- scoped `uv run pyright`：0 errors，0 warnings，0 informations。
- `git diff --check`：通过。

## 搜索面与未覆盖面

已读当前 raw-capture Spec、规则 store、raw capture store、rejection shim、配置 schema、composition、inference 路由、direct/count attempt 接线、upstream error normalization、error response writer、response observation、request completion 和相关单元/集成测试。没有运行真实 upstream、真实磁盘故障、多进程同时 append、真实端口或真实数据库压力测试；这些不改变 RC-005 的静态证据与合成探针结论。
