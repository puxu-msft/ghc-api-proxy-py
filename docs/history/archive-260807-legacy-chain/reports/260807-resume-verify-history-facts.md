# History facts 独立验收报告

## 判定

**PASS**。

候选：`/home/xp/src/ghc-api-proxy-py-history-facts`，分支 `fix/responses-history-facts`，验收 HEAD `864cfa30e291768cbc7b080fce80d9be4cbf2d83`。候选 worktree 在验收前后均为干净状态。本报告只覆盖本轮指定的 History／observer／calibration／strict validator 关键失败机制，不代表 Anthropic Responses bridge 完整矩阵通过。

## 验收矩阵

| 验收项 | 独立判据 | 结果 |
|---|---|---|
| Hook invalid final body | final body 未通过 strict validation 时，`RESPONSE` observer 为 0，success calibration 为 0，History 为 failed 且无 response | PASS |
| Upstream body read failure | body read 抛错时，`RESPONSE` observer 为 0，success calibration 为 0，History 为 failed 且无 response | PASS |
| 合法 hook final body | strict validation 通过后，`RESPONSE` observer 恰好 1 次，success calibration 恰好 1 个 sample，二者观察 final hook body | PASS |
| History facts 与最终 attempt | History 保留 original Anthropic request；request／response conversion facts 同时存在；retry 后只投影最终成功 attempt | PASS |
| History 客户端 bytes | 客户端最终 body bytes 与 History response 使用同一 final payload；独立 spy 再编码后逐字节一致 | PASS |
| Strict validator | 接受 6 类合法 SDK block；拒绝代表性非法 envelope、缺字段、混合字段、unknown block 与后续非法 block | PASS |

## 规格依据

- 冻结 Spec 的 Hooks 合同要求 response hooks 接收转换后的 Anthropic body，observer 只观察规范化 Anthropic facts，hook failure 不得制造成功事实。
- 冻结 Spec 的 History 合同要求 original payload 保持 Anthropic 语义，并保存 attempts、request／response conversion facts、usage 与终止原因；只有最终成功 attempt 可贡献成功 usage／calibration。
- 冻结 Spec 的 non-stream 合同要求完整 body 经 response hooks、strict validation 与 limits 后才可提交成功 body。

## 实现接缝核对

- `src/app/pipeline/executor.py:303-400`：先读取 body、运行 response hooks、执行 strict wire validation，再写入 `normalized_response`、`final_response_payload`、conversion facts 与 response usage；之后才发布 `ObserverEvent.RESPONSE`。
- `src/app/pipeline/executor.py:305-322`：body read failure 会关闭 response 并走统一失败 finalizer，不经过成功 observer。
- `src/app/history/consumer.py:18-33`：完成态只从 `context.final_response_payload` 写 History response，并从最终 context 生成 usage／conversion facts。
- `src/app/history/consumer.py:37-53`：History request payload 使用 `context.original_payload`。
- `src/app/history/consumer.py:55-114`：conversion facts 保留 request／response provenance 与 attempt number。
- `src/app/anthropic/response_validation.py:9-42`：先由官方 SDK `Message` 类型校验，再拒绝与已判定 block 类型不兼容的混合字段。

## 现有定向测试

执行时显式绑定候选源码：`PYTHONPATH=/home/xp/src/ghc-api-proxy-py-history-facts/src`，并使用 `PYTHONDONTWRITEBYTECODE=1` 与 `pytest -p no:cacheprovider`，避免候选树产生 cache／bytecode 写入。

执行范围：

- `tests/component/test_pipeline_executor.py::test_responses_success_persists_hooked_response_and_exact_facts`
- `tests/component/test_pipeline_executor.py::test_invalid_hooked_responses_body_persists_no_success_facts`
- `tests/component/test_pipeline_executor.py::test_failed_final_response_publishes_no_success_callbacks`
- `tests/component/test_pipeline_executor.py::test_body_read_failure_publishes_no_success_callbacks`
- `tests/component/test_pipeline_executor.py::test_failed_final_response_does_not_calibrate_builtin_success_observer`
- `tests/component/test_pipeline_executor.py::test_body_read_failure_does_not_calibrate_builtin_success_observer`
- `tests/component/test_pipeline_executor.py::test_valid_final_response_calibrates_once_after_success_facts`
- `tests/component/test_pipeline_executor.py::test_history_preserves_request_and_response_conversion_provenance`
- `tests/component/test_pipeline_executor.py::test_history_projects_only_final_success_attempt_conversion_facts`
- `tests/unit/test_anthropic_response_validation.py::test_strict_wire_validator_accepts_sdk_messages`
- `tests/unit/test_anthropic_response_validation.py::test_strict_wire_validator_rejects_invalid_messages`

结果：`32 passed in 2.35s`，退出码 `0`。候选状态摘要前后均为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，即空 porcelain status。

首次执行未显式设置 `PYTHONPATH`，`.venv` 的 editable import 指向另一 worktree，collection 以 `ModuleNotFoundError: app.anthropic.response_validation` 退出。该轮未运行测试、未修改候选树，且不计入验收证据。随后探针确认 `app` 与 validator 均从候选绝对路径导入，再取得上述有效结果。

## 独立 spy

临时 spy 仅写入 `TemporaryDirectory`，不导入现有测试 helper，直接使用公开的 `execute_anthropic_pipeline()`、`HistoryConsumer`、`HistoryStore`、hook registry 与 calibration state。

结果：

- Hook invalid body：`response_observer_count=0`，`calibration_samples=0`，History `status=failed`，`response=null`。
- Body read failure：`response_observer_count=0`，`calibration_samples=0`，History `status=failed`，`response=null`。
- 合法 final body：`response_observer_count=1`，`calibration_samples=1`，History text 为 hook 后的 `spy-final`；facts provenance 为 `request` 与 `response`，facts attempt 集合为 `{0}`。
- 独立 exact-byte spy：客户端最终 JSON bytes 与 `orjson.dumps(entry.response)` 完全相等，输出 `EXACT_BYTES_EQUAL=true`；两侧均包含 hook 后文本 `exact-byte-final`。

两次 spy 均退出码 `0`，候选状态摘要前后不变。

## Strict validator 样本

合法 SDK block 六类均通过：`text`、`tool_use`、`thinking`、`redacted_thinking`、`server_tool_use`、`web_search_tool_result`。另有多 block 组合样本通过。

代表性非法均被拒绝：缺失／错误顶层 `type` 或 `role`，text 缺字段或混入 `id`，tool 缺 `id`／`name`／`input` 或混入 text 字段，thinking 缺 signature，unknown block，以及第二个 block 才出现混合字段。

## 结论

本轮指定的六类关键行为均有实际运行证据，没有发现偏差或阻断缺陷，故 verdict 为 **PASS**。未执行完整 bridge 验收矩阵、全量 pytest、ruff、pyright、streaming 或真实 upstream 校准；这些不在本次授权范围内，不应从本报告推断为已通过。
