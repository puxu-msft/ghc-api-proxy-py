# 动态条件式 raw capture ACTIVE v8 只读验收报告

## 评审范围

评审对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树中与 ACTIVE v8 dynamic raw capture 直接相关的实现、测试与 `.dev/docs/raw-capture/spec.md`。范围包括 SQLite 条件规则与 HTTP CRUD、路由后的精确匹配、CBOR Sequence + zstd writer/reader、配额与 shared-path poison、writer acknowledgement、request completion 诊断、所有 provider 的失败 attempt wire evidence、普通日志安全投影，以及 RC-006/RC-007 的当前修复状态。

判据来源是用户本轮合同与 `.dev/docs/raw-capture/spec.md` ACTIVE v8；没有从实现反推判据。没有读取、输出或依赖真实 capture 正文、认证信息、token、header 或真实数据库内容；合成探针只观察事件类型、长度、异常类型和布尔结果。

## 总体 verdict

**needs-fix**

## Blocker 数

0

## 高置信发现

### RC-008 — major — CodeBuddy 非流式聚合阶段的 timeout/transport failure 仍未进入失败 attempt capture

- `finding_id`: `RC-008`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/codebuddy_client/client.py:88-101`
- `related_locations`: `src/app/pipeline/direct_driver/base.py:176-192`、`src/app/model_provider/upstream_errors.py:152-154`、`tests/component/model_provider/codebuddy_client/test_codebuddy_client.py:157-175`、`.dev/docs/raw-capture/spec.md:50、82`
- **判据**：ACTIVE v8 要求所有 provider 的失败 attempt，包括 CodeBuddy 的 timeout/transport failure，保留实际已经发送的 upstream request bytes；失败 attempt 必须继续保留 attempt 边界与已观察的 response evidence。
- **证据**：CodeBuddy client 为了聚合非流式响应，仍以 `stream=True` 发出 upstream request，然后在 `aggregate_stream(response)` 内读取 response body。当前 `try/except` 只包住了 `_http.send(request, stream=True)`；聚合阶段抛出的 request-attached `httpx2.TimeoutException` 或其他 transport error 直接离开 client，没有转换成带 `sent` 的 `UpstreamTimeout`/`UpstreamError`。随后 direct driver 的 `capture_failed_upstream_attempt()` 只接受 `UpstreamError`/`UpstreamRejected`，因此不会写 `upstream.request.body`。
- **合成验证**：使用带 request 的 `httpx2.ReadTimeout` 作为非流式聚合 body 的失败，client 向外抛出原始 `ReadTimeout`，没有 `sent` 字段；送入生产 `capture_failed_upstream_attempt()` 后事件列表为空。探针没有输出 request body 内容。
- **影响**：命中规则的 CodeBuddy 非流式请求在 headers 已返回、body 读取阶段 timeout/transport failure 时，capture 无法重放实际发送的 request bytes，且原始异常不在 pipeline closed error set 中，不能按正常 upstream timeout/transport 失败路径处理。这直接违反 v8 的失败 attempt wire evidence 合同，定为 `major`。
- **修复方向**：把 CodeBuddy 的非流式聚合读取也纳入 provider wrapper 的 upstream-error normalization，在保留原始异常链的同时从异常或已持有的 request 提取 `sent_body_from_error`；为 body-read timeout 与 transport failure 增加 capture-level regression test，至少验证 `upstream.request.body`、失败 attempt 边界和不向普通日志输出正文。

## 上轮 finding 完成度

- RC-006：**已关闭原 finding 覆盖的路径，但系统级合同仍被 RC-008 重新打开**。CodeBuddy/OpenAI-compatible 的 429/5xx response normalizer 现在保留 request bytes；CodeBuddy 在 `_http.send()` 阶段的 timeout/transport wrapper 也保留 request bytes。新发现只涉及 CodeBuddy 非流式聚合 body 阶段的后续失败。
- RC-007：**closed**。生产 `rejection_capture` 已是无持久化兼容 shim；未命中 4xx 的 active integration test 改为检查没有 capture 文件和 legacy rejection 文件，命中拒绝测试改为读取 CBOR wire evidence。

## 其余合同核对

- SQLite 规则 CRUD、规范化后的 provider/model/session/optional-agent 精确匹配、缺失 agent 的独立分组、路由后且第一次 upstream attempt 前启动 capture、命中后补录完整 inbound body，当前实现与 ACTIVE v8 一致。
- 新 capture 使用 schema version 2 的 CBOR map，每条 item 单独压缩为 zstd frame；旧 `.jsonl.zst` 不参与新格式读取但计入 total quota。
- writer reservation、ack、request completion 等待、partial-write shared-path poison、跨 store 首次 reader validation、`request_incomplete` 与安全完成 warning 的当前直接测试通过；未发现新的高置信问题。
- 普通 completion/response observation 的 upstream error 投影只保留安全状态信息或固定的 message-present 标记，未发现把 upstream error body/message 写入普通日志的当前高置信路径。
- `.dev/docs/raw-capture/spec.md` 当前头部与修订记录均为 `ACTIVE v8`，本轮没有发现版本标记不同步。

## 验证结果

- `uv run pytest -q tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/openai_compatible/test_provider.py -k 'wire_capture or upstream_error or timeout or transport or rejection or sent_body or preserves_upstream'`：36 passed，28 deselected。
- `uv run pytest -q tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/openai_compatible/test_provider.py`：31 passed。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture or capture_rules or unmatched_refusal or rule_selected_rejection'`：5 passed，273 deselected；包含未命中 4xx 无持久化与命中拒绝 CBOR wire evidence。
- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/observability/test_rejection_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py tests/unit/observability/test_response_observation_projection.py -k 'raw_capture or debug_capture or rejection_capture or writer or poison or quota or completion or provider_error or response_observation or log'`：168 passed。
- `git diff --check -- <相关 raw-capture/provider/test 路径>`：通过。
- 额外 synthetic probe 证明 RC-008：CodeBuddy 非流式聚合的 request-attached `ReadTimeout` 以原始异常离开 client，生产失败 capture helper 没有写入事件；probe 只输出异常类型、事件列表与长度，不输出正文。

## 搜索面与未覆盖面

已阅读 ACTIVE v8 Spec、raw capture/debug rule store、HTTP ops 与 inference 路由、provider-specific 与 shared upstream normalizer/client wrapper、direct/count driver、request completion/response observation/request log，以及对应 unit/component/integration tests。未运行真实 upstream、真实 4141/4142 端口、真实磁盘故障、多进程并发压力或真实数据库流量；这些未覆盖面不削弱 RC-008 的静态调用链与 synthetic probe 证据。未修改生产实现、现有测试或 Spec。
