# Dynamic capture v20 final acceptance review

## 评审范围

本次只读评审针对当前工作树中 raw capture v20 相关最终状态：`debug_capture` SQLite store/HTTP CRUD、`raw_capture` CBOR/zstd writer/reader/quotas/poison/ack/completion warnings、inference/composition/Chain wiring、direct/count drivers、GHC/OpenAI-compatible/CodeBuddy/Xingchen error normalizers、one-shot/stream cleanup、request completion/log/trace、`ResponseObservation`、相关测试与 active 文档。

明确不评审工作树中无关的协议迁移、Docker、实验目录和其他模型功能；不修改被检对象，不读取或输出真实 capture 正文、token、header、credential 或数据库内容，不操作 4141。

## 总体 verdict

`fail`。`blocker=0`，`major=0`，`minor=1`；另有 3 条未定级的测试接线/契约冲突，见末尾说明。

## 判据来源

1. `.dev/docs/raw-capture/spec.md`，ACTIVE v20；它是 raw capture 选择规则、管理接口、文件格式、路径、配额、可读性、安全边界和失败诊断的权威来源。
2. 用户本轮条件式 raw capture 合同：逐条核对 provider/model-id/resolved session/optional agent exact rule、未命中不持久化正文、命中后的真实 wire body 与 attempt status/bytes/complete、cleanup 与边界状态、CodeBuddy aggregate 分离、COUNT buffered attempt projection、安全 ordinary projection、legacy JSON rejection inactive、v20 文档同步。
3. `docs/.human-controlled/api.md` 的 capture-rules 端点与精确匹配约束。
4. `docs/.human-controlled/config.example.yaml` 的 raw capture 默认关闭、CBOR Sequence + 独立 zstd frame、SQLite 规则库、路径和配额配置说明。

## 验证方法

先独立读取上述判据，再建立实现地图；随后读取最终代码、集成接线、测试和 active 文档，运行最小相关测试以及必要的 Ruff/Pyright。所有输出均避免真实 capture 内容、凭据和数据库内容。

## 已闭合发现

### F-001 · minor · COUNT buffered attempt projection 未通过 Pyright

- `primary_location`: `src/app/observability/request_trace.py:335-378`
- `related_locations`: `src/app/server/routes/inference.py:750-766`、`src/app/pipeline/driver.py:539-565`
- 证据：对本次承重路径运行 `uv run pyright ...` 时，Pyright 报告该函数 22 个 `reportUnknownVariableType`、`reportUnknownMemberType` 和相关参数类型错误；排除 `request_trace.py` 后同一承重路径为 `0 errors`。问题集中在 `raw` 经过 `isinstance(raw, dict)` 后仍以 `dict[Unknown, Unknown]` 参与 `raw.get(...)`，正是 v20 新增的 buffered COUNT attempt projection。
- 影响：COUNT 的 attempt projection 运行时测试可以通过，但项目要求的静态验证不绿，且该投影的类型边界没有被声明，后续变更可能把不安全字段写入最终记录而不被类型检查发现。
- 建议：在读取前把每个条目收窄为 `Mapping[str, Any]` 或显式 `cast(dict[str, Any], raw)`，然后重新运行该承重路径的 Pyright。

## 其他验证冲突（未冒充为 raw-capture 规格发现）

组合运行 `tests/int/test_pipeline_app.py` 相关承重集合时得到 `645 passed, 3 failed`。三项失败都没有由本次固定判据解决，因此没有把实现或测试期望反推成产品结论：

1. `test_a_request_that_raised_on_its_way_out_still_writes_its_one_line` 期待 dispatch failure detail 保留 `RuntimeError` 类型名；当前实现保留了 proxy-owned exception message，但 fixed raw-capture criteria 没有规定这一类异常 detail 的具体拼写。
2. `test_delivery_replay_reuses_the_normal_attempt_that_produced_the_stream` 期待 `attempt.failed` subscriber 对 `context.payload` 的改写进入 replay；当前 `app.pipeline.driver.replay_prepared` 的显式行为是复用产生当前 stream 的 source payload。这里是测试期望与实现契约的冲突，需由对应 request-pipeline 规格裁决。
3. `test_a_replacement_that_never_opened_an_attempt_is_not_recorded_as_one` 试图 monkeypatch `app.server.routes.inference.replay_prepared`，但当前符号位于 `app.pipeline.driver`，测试在注入点先以 `AttributeError` 失败，未执行产品路径。这是测试接线漂移。

## 逐条核对结论

1. **规则选择与未命中隔离：通过。** `DebugCaptureRuleStore` 对 provider、resolved model-id、session-id 和可选 agent-id 做规范化后的精确匹配；缺失 agent 使用独立 capture 分组；inference 只在路由回调命中后创建 capture 并补录已读取 body。SQLite/HTTP CRUD、wildcard 与 agent-specific unit test，以及 unmatched integration test 均通过。
2. **命中后的 wire body 与 attempt evidence：通过运行时关键路径，静态门控除 F-001 外通过。** CBOR/zstd、request/upstream/client body、retry status/body、poison、writer ack、quota 和 count capture 的 targeted tests 通过；F-001 是 COUNT projection 的静态类型缺陷。
3. **status-body-read、partial/zero-body、cleanup、pre-first-pull、direct discard：通过代码与现有 targeted lifecycle/provider tests 核对。** provider error-wire tests、CodeBuddy/OpenAI-compatible/Xingchen tests、direct-driver tests 和 one-shot/stream cleanup tests通过；未读取真实 upstream。
4. **CodeBuddy aggregate raw SSE 与 synthetic response：通过。** aggregate response 的 extension 保存真实 raw upstream body，capture 读取该 extension 而不是 synthetic JSON；component test 和 provider wire-capture test 通过。
5. **COUNT buffered attempt projection：运行时通过，静态验证由 F-001 阻断。** count retry、measured zero body、local fallback 和 request logging tests 通过；`request_trace.py` 的新增投影没有通过 Pyright。
6. **ordinary projection 安全边界：通过固定判据。** ResponseObservation error/message sentinel、provider error summary bounds、usage issue 的稳定 code/fixed field path/exception type，以及 completion/FailureSummary/InterruptionObservation 的 upstream status/type projection tests 通过；dispatch failure detail 的具体 proxy-owned wording 属于未由本次固定判据解决的测试冲突。
7. **legacy JSON rejection inactive：通过。** rejection shim 不持久化，unmatched refusal integration test 未生成 capture 或 legacy rejection file。
8. **v20 Spec 与 active docs：通过。** Spec header/revision 为 ACTIVE v20；`api.md`、`config.example.yaml` 同步 capture-rules、SQLite、CBOR Sequence、独立 zstd frame、hashed path 和 quota 语义；active raw-capture 文档未发现旧 JSONL persistence 规则。

## 搜索面与验证命令

已读取：`.dev/docs/raw-capture/spec.md`、`docs/.human-controlled/api.md`、`docs/.human-controlled/config.example.yaml`；`debug_capture.py`、`raw_capture.py`、`request_completion.py`、`request_log.py`、`request_trace.py`、`response_observation.py`、`inference.py`、`composition.py`、`chain.py`、`ops.py`、direct/count drivers、四类 provider normalizer/client、rejection shim，以及对应 unit/component/integration tests。

已运行并通过：`uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py tests/unit/observability/test_response_observation_projection.py tests/unit/pipeline/test_response_observation.py`（128 passed）；provider/direct-driver 集合（82 passed）；completion/log 集合（266 passed）；CRUD/error/provider integration 集合（111 passed）；capture-focused integration selection（4 passed）；相关路径 `uv run ruff check ...`（0 errors）；排除 `request_trace.py` 的相关路径 `uv run pyright ...`（0 errors）。

已运行但未全绿：包含 `tests/int/test_pipeline_app.py` 的组合承重集合（645 passed, 3 failed）；三项均为上文未定级的契约/测试接线冲突。对当前承重路径运行的完整 Pyright 报告 F-001 的 22 个类型错误。

未覆盖：真实 upstream、真实 capture/database 内容、生产 4141、用户明确排除的协议迁移、Docker、实验目录和其他模型功能。

## 边界判断

本次是最终验收报告边界，但不执行开发 closeout：用户明确要求只读、不修改任何被检对象，也没有提交或发布要求；本报告是唯一需要持久化的交付物。
