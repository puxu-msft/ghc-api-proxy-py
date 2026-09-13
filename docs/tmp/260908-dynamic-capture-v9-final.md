# Dynamic capture v9 final review

## 评审范围

评审对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树的最终候选状态，基线为 `main@c0fadf8d` 加上当前未提交改动；范围覆盖 `.dev/docs/raw-capture/spec.md` ACTIVE v9、SQLite/HTTP 条件选择、CBOR/zstd writer/reader、request/attempt capture wiring、普通日志与 structured observation 安全边界、provider error normalization，以及 RC-008 的 CodeBuddy 非流式聚合错误路径。未把其他与 raw capture 无关的翻译、协议迁移和工作树脏改动当作本次验收对象。

## 总体 verdict

**不通过。** 发现 1 项 `major`，0 项 `blocker`。ACTIVE v9 的 CBOR/zstd、SQLite 条件匹配、writer acknowledgement、poison recovery、未命中不持久化和 RC-008 已覆盖路径总体成立，但 provider 在读取非 200 响应正文时仍可把 `ReadTimeout`/transport error 原样逃出，导致该失败 attempt 没有完整 wire evidence。

## Blocker 数

`0`

## 判据来源

- `.dev/docs/raw-capture/spec.md`，尤其是 §2.1、§3、§4、§5、§6 以及 v9 修订记录。
- `.claude/rules/00-development-workflow.md` 的 Spec 优先、最终状态评审和最小相关验证要求。
- 用户本轮给出的补充判据：HTTP API + SQLite 条件式全量 raw capture；未命中不持久化正文；所有 provider 的每个 attempt request/response、429/5xx/ReadTimeout/transport、CodeBuddy non-stream aggregation body errors 和 count retry wire evidence；普通日志/structured observation 不含 raw error body/message；不以 legacy JSON rejection persistence 作为 active gate；RC-008 的 aggregate-stream timeout/httpx normalization 与 sent-byte 修复。

## Findings

### `raw-capture-provider-body-read-failure` — `major`

- `primary_location`: `src/app/model_provider/codebuddy_client/client.py:89-93`
- `related_locations`: `src/app/model_provider/codebuddy_client/client.py:96-109`、`src/app/model_provider/openai_compatible/client.py:128-133`、`src/app/pipeline/direct_driver/base.py:176-193`
- CodeBuddy 在收到 429/5xx 后直接执行 `await response.aread()`；这个读取动作不在 RC-008 新增的 `TimeoutException`/`HTTPError` 包装范围内。若 error response 的 body 读取抛出 `httpx2.ReadTimeout` 或 transport error，异常以原始 httpx2 类型逃出，既不是 `UpstreamTimeout`/`UpstreamError`，也没有 `sent` request bytes。
- 同一结构还存在于 CodeBuddy non-stream 分支的 `finally: await response.aclose()`：cleanup 阶段的 httpx error 会越过前面的 `except`。OpenAI-compatible client 的非成功 response body `aread()` 也位于 normalization try 之外，故不是 CodeBuddy 独有的偶发现象。
- 只读探针用一个 status `500`、body 阶段抛 `httpx2.ReadTimeout` 的 response 复现得到原始 `httpx2.ReadTimeout`，`is_upstream_timeout=False` 且 `is_upstream_error=False`。把同一错误交给现有 `capture_failed_upstream_attempt()` 后，capture event 只有 `request.start`、`upstream.attempt.start`、`upstream.attempt.end`、`request.end`，缺少 `upstream.request.body`；探针没有输出正文、header、credential 或 session/agent identity。
- 这直接违反 ACTIVE v9 §3、§4、§6 以及用户判据中“所有 provider 的 ReadTimeout/transport failure 和每个 attempt request/response 必须保留”的要求。命中规则的请求会丢失实际已发送 upstream request body，且客户端/普通完成诊断可能把 upstream timeout 误归类为未识别内部异常；这不是仅影响诊断文案的 minor。
- 修复方向：把 status-body read、non-stream aggregate cleanup 和同类 provider response cleanup 纳入统一 upstream error normalization；从 exception 或 attached response/request 提取 sent bytes，并在 normalized pipeline error 到达 `capture_failed_upstream_attempt()` 后保留该 attempt 的 request/response evidence。RC-008 已通过的 aggregate-stream body exception 路径不要回退。

## 已核对且未发现高置信问题的面

- `GET/POST/DELETE /api/debug/capture-rules`、SQLite unique rule、provider/resolved model/session/optional agent exact match、规范化和下一次查询生效。
- 命中前不创建 capture；命中后补录原始 inbound body；缺失 agent 使用独立 `None` capture 分组，未使用可由客户端提交的普通字符串作为 capture sentinel。
- `.cborseq.zst` 路径 hash、CBOR map、native byte string、每 item 独立 zstd frame、reader 的 truncated tail / extra item / non-map 检查，以及 legacy `.jsonl.zst` 只计入 total quota。
- bounded queue、实际压缩 frame reservation、per-request writer acknowledgement、writer error rollback、shared-path poison 和新 store 首次 reader validation。
- 429/5xx/status rejection、GHC SDK timeout/transport、OpenAI-compatible/Xingchen normalizer 的 sent-byte 传递；count_tokens retry 的 attempt start/status/request/response 记录。
- `rejection_capture` 已成为 no-op，未命中请求不再落 legacy rejection body；这次验收没有把 legacy JSON rejection persistence 当作必须保留的 active 行为。
- Response observation 的 provider error message 使用固定的 `upstream error message present`，未发现其把 raw error body/message 写入 structured observation；raw capture completion warnings 也只使用固定 reason/event/request ID/completeness 元数据。

## 验证记录

通过：

```text
uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/int/test_pipeline_app.py -k 'raw_capture or rule_selected_count_capture or rule_selected_rejection_capture'
19 passed, 316 deselected
```

其中 RC-008 的 CodeBuddy `aggregate_stream` body `ReadTimeout` component test 通过，并确认从 attached request 保留 sent bytes。

通过：

```text
uv run ruff check src/app/observability/raw_capture.py src/app/observability/debug_capture.py src/app/model_provider/codebuddy_client/client.py src/app/model_provider/codebuddy_client/errors.py src/app/model_provider/openai_compatible/errors.py src/app/model_provider/upstream_errors.py src/app/pipeline/direct_driver/base.py src/app/pipeline/driver.py src/app/server/routes/inference.py tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/test_provider_error_wire_capture.py
All checks passed!

uv run pyright src/app/observability/raw_capture.py src/app/observability/debug_capture.py src/app/model_provider/codebuddy_client/client.py src/app/model_provider/codebuddy_client/errors.py src/app/model_provider/openai_compatible/errors.py src/app/model_provider/upstream_errors.py src/app/pipeline/direct_driver/base.py src/app/pipeline/driver.py src/app/server/routes/inference.py tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/test_provider_error_wire_capture.py
0 errors, 0 warnings, 0 informations

git diff --check -- src/app/observability/raw_capture.py src/app/observability/debug_capture.py src/app/model_provider/codebuddy_client/client.py src/app/model_provider/codebuddy_client/errors.py src/app/model_provider/openai_compatible/errors.py src/app/model_provider/upstream_errors.py src/app/pipeline/direct_driver/base.py src/app/pipeline/driver.py src/app/server/routes/inference.py src/app/server/routes/ops.py tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/int/test_pipeline_app.py
通过
```

另一个最小 observability 选择器得到 `7 passed, 1 failed, 327 deselected`。失败项是 `tests/int/test_pipeline_app.py::test_a_count_upstream_could_not_answer_is_reported_as_an_estimate` 的旧行尾断言：实际 completion line 带有 `retries=2`，而断言仍要求以 `provider(ghc-failed,local)` 结束；该失败与 raw capture、RC-008 和本 finding 的 status-body read path 无关，未在只读验收中修改。

## 搜索面与未覆盖面

已读最终实现和测试中的 raw capture、debug capture、request completion/trace/log、response observation、rejection capture、inference/ops/composition/config wiring、direct driver、generic driver、count_tokens、CodeBuddy/GHC/OpenAI-compatible/Xingchen error normalization，以及 ACTIVE v9 Spec。未运行完整 pytest、完整 Ruff/Pyright 或 real upstream canary；本轮按用户要求只运行最小相关测试，且没有修改产品文件。
