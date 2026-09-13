# Dynamic capture v17 最终只读验收

## 评审范围

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态。判据来源为用户给出的 ACTIVE v17 条件、`.dev/docs/raw-capture/spec.md`、项目开发工作流，以及相关 HTTP API、SQLite、capture、attempt completeness、普通 observability 和模块文档契约。本次未修改实现、测试或配置，未操作现有 4141，未读取、输出或持久化 capture 正文、认证信息、token、credential 或秘密。

## 总体 verdict

**pass：未发现高置信度 defect。**

## Blocker 数

0。

## 验收结论

- 条件式 HTTP API 与 SQLite 规则已按 provider、解析后的 model-id、session-id 和可选 agent-id 精确匹配；命中时机早于第一次 upstream attempt，并补录已读取的入站 body。
- 未命中请求不创建正文 capture；legacy rejection persistence 保持 inactive。命中请求使用 CBOR Sequence、每 item 独立 zstd frame、hashed path，并保留真实 upstream/client wire bytes。
- provider、status、partial、cleanup、count、retry、CodeBuddy aggregate、pre-first-pull 和 direct discard 路径均保留 attempt boundary、bytes 与 completeness；partial boundary 会触发一次安全 completion warning。
- COUNT 的 buffered attempt projection 已进入普通 structured record 与 completion metadata；ordinary upstream projection 使用安全 metadata，proxy-owned message 与 upstream failure provenance 保持区分；ResponseObservation error event 不保留 provider 原始 message。
- active module 文档已同步 retired rejection persistence 的现状，并指向条件式 CBOR capture。

## 最小相关验证

- `uv run pytest -q --disable-warnings --tb=no --basetemp ... tests/unit/observability/test_raw_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_response_observation_projection.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py tests/unit/observability/test_rejection_capture.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：322 passed。
- `tests/int/test_pipeline_app.py` 的 capture、rule API、COUNT、unmatched refusal、one-shot 与 response-error 选择集：59 passed，219 deselected。
- DYN boundary 与安全投影选择集：8 passed。
- 不落盘 boundary probe 确认 pre-first-pull 与未观测 status response 都写入 `response.end(false)` 及 `attempt.end(false)`；probe 只输出事件类型和布尔结果。

## 搜索面与未覆盖面

已读 raw-capture Spec、debug capture store、HTTP ops route、inference lifecycle、direct driver、COUNT driver、request trace/completion/log、Responses observation、provider normalizers、OpenAI-compatible 与 CodeBuddy client、rejection shim 及相关测试。未运行完整 regression、Ruff、Pyright、真实 upstream、真实磁盘故障、多进程 append 压力或部署验收；这些未覆盖面不构成当前 ACTIVE v17 条件下的高置信度 defect。
