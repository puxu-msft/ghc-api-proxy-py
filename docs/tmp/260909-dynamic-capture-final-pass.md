# Dynamic capture final read-only review

## 评审范围

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树的 raw capture v20 最终实现、Spec、active docs、相关 focused tests 与静态检查。判据来源是 `.dev/docs/raw-capture/spec.md` ACTIVE v20、用户条件式 raw capture 合同、`docs/.human-controlled/api.md`、`docs/.human-controlled/config.example.yaml` 和 `.claude/rules/00-development-workflow.md`。覆盖规则选择与管理 API、未命中隔离、CBOR/zstd reader/writer、配额与 poison、provider wire evidence/completeness、safe ordinary projection、CodeBuddy/Xingchen cleanup、pre-first-pull/direct discard、COUNT projection、legacy rejection cleanup 与 active docs。未读取、输出或持久化真实 capture 正文、认证信息、token、credential 或数据库内容，未操作 4141。

## 总体 verdict

**needs-fix：发现 1 个高置信度 minor 规格偏差，不能报告 pass。**

## Blocker 数

0。

## Finding

### F-002 · minor · agent capture path 没有按 ACTIVE v20 对原始 agent ID 直接计算 SHA-256

- `finding_id`: `F-002`
- `severity`: `minor`
- `status`: `open`
- `primary_location`: `src/app/observability/raw_capture.py:101-109`
- `related_locations`: `.dev/docs/raw-capture/spec.md:13-19`、`tests/unit/observability/test_raw_capture.py:168-215`
- **判据**：ACTIVE v20 §2 规定 session 与 agent 两个 path prefix 都是对应原始 ID 的 SHA-256 前 24 个十六进制字符；缺失 agent-id 可以使用与真实字符串不可碰撞的独立 tagged identity，但不能改变真实 agent-id 的规定哈希。
- **证据强度**：高。当前实现对 session 使用 `sha256(session_id)`，但对非空 agent-id 使用 `sha256(b"agent-id:" + agent_id)`。对合成值 `agent-1`，实现路径名的 prefix 与 `sha256("agent-1")` 的规范 prefix 不相同。现有测试只验证路径不泄漏 identity 与缺失 agent 分组不碰撞，没有验证 ACTIVE Spec 的精确 hash 公式。
- **影响**：capture 仍能按 `(session_id, agent_id)` 稳定分组且不泄漏 identity，但按 Spec 或外部取证工具从原始 agent-id 推导路径时会定位不到该文件，属于路径合同不一致。
- **修复方向**：真实非空 agent-id 直接使用其 UTF-8 原始值计算 SHA-256；仅为缺失 agent-id 使用独立、不可与真实值碰撞的 tagged identity，并补充精确 path-hash 回归断言。

## 上轮 finding 完成度

- **F-001：closed。** `RequestTrace.absorb_buffered_upstream_attempts` 已将条目显式收窄为 `dict[str, Any]`；当前 `uv run pyright src tests` 为 `0 errors, 0 warnings, 0 informations`。COUNT/observation 相关 focused tests 与本文列出的完整 focused unit 集合均通过。

## 逐项核对结论

1. **规则选择与管理 API：通过。** SQLite 规则对 provider、resolved model-id、session-id 和可选 agent-id 做规范化后的精确匹配；wildcard agent、agent-specific 匹配、唯一约束、CRUD 和下一次匹配生效均有实现与测试。
2. **未命中隔离与 legacy cleanup：通过。** capture 只在路由解析出 provider/model-id 后且早于第一次 upstream attempt 的命中回调中创建；未命中请求不保存正文；retired rejection capture 是无持久化副作用的 compatibility shim。
3. **CBOR/zstd、reader、quota、ack 与 poison：通过。** 当前实现使用 schema v2 的 CBOR map、native byte string、每 item 独立 zstd frame、`.cborseq.zst` 路径、压缩后字节 reservation、writer acknowledgement、partial-write poison 和新 store 首次 reader validation；相关 unit tests 通过。
4. **provider wire evidence 与 completeness：通过。** GHC、OpenAI-compatible、CodeBuddy、Xingchen 的 status-body read、transport、timeout、cleanup、retry、partial/zero-body、returned-response discard 和 response/attempt boundary 接线均与当前 Spec 对齐；CodeBuddy aggregate 使用真实 upstream SSE body extension，不以 synthetic response 替代。
5. **safe ordinary projection：通过。** completion、FailureSummary、InterruptionObservation、ResponseObservation error/usage issue 和 body-attempt projection 只保留安全状态、稳定 code、固定 field path、exception module/type、status、byte/count 与 completeness metadata，不复制 provider raw error message 或 raw body。
6. **pre-first-pull/direct discard：通过。** prepared streaming response 的 owner cleanup 与 direct-driver returned-response discard 都写入不完整 response/attempt boundary，且 boundary 写入幂等。
7. **COUNT projection：通过。** buffered COUNT attempt 的 request/response bytes、status、complete/outcome、timing 和 retry 顺序进入 ordinary structured observation；F-001 的 typing 缺陷已闭合。
8. **active docs：除 F-002 外通过。** Spec 为 ACTIVE v20；API/config 文档同步 SQLite rule API、CBOR Sequence、独立 zstd frame、hashed path、quota 和 ordinary-log 安全边界。F-002 是实现对 Spec 精确 agent hash 公式的偏差，不是文档漂移。

## 验证命令与结果

- `PYTHONDONTWRITEBYTECODE=1 uv run pytest -q --disable-warnings --tb=short --basetemp=.../pytest-final-unit tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/observability/test_response_observation_projection.py tests/unit/pipeline/test_response_observation.py tests/unit/pipeline/test_direct_driver.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/xingchen/test_client.py`：**186 passed**。
- `PYTHONDONTWRITEBYTECODE=1 uv run pytest -q --disable-warnings --tb=short --basetemp=.../pytest-final-int tests/int/test_pipeline_app.py -k 'raw_capture or count_tokens or unmatched_refusal or response_observation or one_shot or provider_failure'`：**26 passed，252 deselected**。
- `uv run pyright src tests`：**0 errors，0 warnings，0 informations**。
- `uv run ruff check src tests`：**All checks passed**。
- `git diff --check`：通过。
- 只读 hash probe 证明真实 agent-id 的实现 prefix 与 ACTIVE v20 规定的 `sha256(raw_agent_id)` prefix 不同。

## 搜索面与未覆盖面

已读取 raw-capture Spec、API/config active docs、debug capture store、raw capture writer/reader、composition/Chain、ops/inference lifecycle、request completion/trace/log、direct/count drivers、Responses observation、GHC/OpenAI-compatible/CodeBuddy/Xingchen clients and normalizers、rejection shim，以及相关 unit/component/integration tests。未运行真实 upstream、未读取真实 capture/database 内容、未做多进程 append 压力或部署验收；未操作现有 4141。这些未覆盖面没有被冒充为已验证，也不改变 F-002 的代码与 Spec 直接证据。

## 边界判断

本次交付是只读最终复核报告；用户明确要求不修改被检实现、不操作 4141，且当前存在未闭合 F-002，因此不执行实现 closeout、提交或发布。

---

# Final-pass addendum — 2026-09-09

## 评审范围

本次只读最终复核针对当前工作树的 raw capture ACTIVE v20 合同：条件式 raw capture 与未命中隔离、真实 agent-id 的原始 SHA-256 路径及缺失 agent 独立命名空间、CBOR/zstd、SQLite/HTTP exact rules、wire evidence 与 completeness、safe ordinary projection、COUNT projection、legacy JSON capture inactive，以及相关 active 文档和测试接线。未读取、输出或持久化真实 capture 正文、认证信息、token、credential 或数据库内容，未操作 4141。

## 总体 verdict

**pass：未发现高置信度 defect。**

## Blocker 数

0。

## Findings

无。

## 逐项核对结论

1. **F-002 已闭合。** `RawCaptureStore._path_for()` 对真实非空 agent-id 直接计算原始 UTF-8 值的 SHA-256 前 24 个十六进制字符；缺失 agent 使用 `agent-missing-<sha256("missing-agent-id")-prefix>` 独立命名空间。只读 hash probe 与 ACTIVE v20 公式一致。
2. **条件式选择与管理接口：通过。** SQLite 规则按 provider、resolved model-id、session-id 和可选 agent-id 做规范化后的精确匹配；命中发生在第一次 upstream attempt 前并补录已读取入站 body；未命中不创建正文 capture。
3. **文件格式与写入诊断：通过。** 当前实现保持 schema v2 的 CBOR Sequence、每 item 独立 zstd frame、native byte string、hashed path、legacy `.jsonl.zst` 只计入配额、不参与新格式读取，以及 reservation、ack、partial-write poison、restart validation 和安全 completion warning 合同。
4. **wire evidence、completeness、ordinary projection 与 COUNT：通过。** 相关 provider、retry、status/partial/cleanup、pre-first-pull/direct discard、CodeBuddy aggregate、COUNT buffered attempt 和安全投影路径均保持 ACTIVE v20 语义；legacy rejection persistence 仍 inactive。
5. **active 文档：通过。** `spec.md` 为 ACTIVE v20；API/config 文档与条件式 SQLite/CBOR capture 合同保持同步。

## 验证命令与结果

- `PYTHONDONTWRITEBYTECODE=1 uv run pytest -q --disable-warnings --tb=short --basetemp=<project-local-review-dir> tests/int/test_pipeline_app.py -k 'opt_in_raw_capture_records_client_and_upstream_bodies or raw_capture_keeps_both_failed_account_switch_attempts or raw_capture_is_selective_and_rule_api_is_persistent or rule_selected_count_capture_keeps_each_upstream_retry or rule_selected_rejection_capture_keeps_upstream_wire_evidence or buffered_responses_status_error or response_observation or error_message or count_tokens'`：**21 passed，257 deselected**。
- `uv run ruff check src tests`：**All checks passed**。
- `uv run pyright src tests`：**0 errors，0 warnings，0 informations**。
- `git diff --check`：通过。
- 不落盘 hash probe：真实 agent-id 与缺失 agent 的路径公式均通过。

## 搜索面与未覆盖面

已读取 ACTIVE v20 raw-capture Spec、项目开发工作流、debug capture SQLite store、HTTP ops routes、raw capture reader/writer、inference lifecycle、request completion/trace/log、provider error normalization、direct/count drivers、Responses observation、rejection shim、active API/config 文档及相关测试。未运行真实 upstream、未读取真实 capture/database 内容、未做多进程压力或部署验收；这些未覆盖面没有被冒充为已验证，也没有发现足以阻断本次 pass 的高置信度问题。

## 边界判断

本 addendum 仅记录 F-002 修复后的最终复核结论；除本报告追加内容外未修改被检对象、未提交或发布。
