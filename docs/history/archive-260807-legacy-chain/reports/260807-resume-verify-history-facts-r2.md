# Responses History facts 独立定向验收 R2

## 判定

**PASS**。

候选为 `/home/xp/src/ghc-api-proxy-py-history-facts`，分支 `fix/responses-history-facts`，验收 HEAD 为 `b1df8f910c590033e83d5cafcd5e514f12bab937`。候选工作树在定向 tests 与独立 spy 前后均保持干净。本报告只覆盖用户指定的当前失败机制与关键主路径，不代表 Anthropic Responses bridge 完整矩阵通过。

## 冻结规格与验收矩阵

行为 oracle 为候选树的 FINALIZED `docs/agents/anthropic-responses-bridge/spec.md`，本轮只采用其中以下已冻结合同：失败 attempt 不得污染成功 calibration；response hooks 与 token observers 只观察 normalized Anthropic facts；History 在成功时保存最终 Anthropic response、usage 与 conversion facts；hook failure 不得产生重复 finalize。

| 验收项 | 独立判据 | 结果 |
|---|---|---|
| Throwing success strategy | `on_success()` 抛错后，成功 `RESPONSE` observer 与 calibration 均不得发布；失败 `ERROR`、`FINALIZE` 与 History finalize 各发生一次；History 不得保存成功 response/usage | PASS |
| 合法成功主路径 | 成功 `RESPONSE` observer、calibration 与 History finalize 各发生一次；History response 必须是 hook 后最终 body，usage 必须是最终 normalized usage，conversion facts 必须同时保留 request/response provenance | PASS |
| Invalid response hook | hook 产出的 final body 未通过 strict validation 时，成功 `RESPONSE` observer 与 calibration 均不得发布；失败 lifecycle 各发生一次；History 不得保存成功 response/usage | PASS |

## 实现接缝

- `src/app/pipeline/executor.py:391-410`：strategy 与 limiter success callback 先完成，之后才发布 `ObserverEvent.RESPONSE` 并 transition 到成功状态。
- `src/app/pipeline/executor.py:68-103`：callback 异常进入统一 failure finalizer；已进入终态时不会重复 finalize。
- `src/app/pipeline/executor.py:422`：non-stream 成功只在完成 transition 与成功 `FINALIZE` observer 后写 History。
- `src/app/history/consumer.py:32-34`：仅完成态写入 `final_response_payload` 与 `_usage_summary(context)`。
- `src/app/history/consumer.py:56,67-129`：History request 保留 original Anthropic payload，usage summary 投影最终 conversion facts。

## 现有定向 tests

执行环境显式绑定候选源码：`PYTHONPATH=/home/xp/src/ghc-api-proxy-py-history-facts/src`，并设置 `PYTHONDONTWRITEBYTECODE=1`、禁用 pytest cache provider，避免写候选树。执行以下 selectors：

- `test_throwing_success_strategy_publishes_only_failure_lifecycle`
- `test_success_callbacks_precede_response_commit_once`
- `test_valid_final_response_calibrates_once_after_success_facts`
- `test_responses_success_persists_hooked_response_and_exact_facts`
- `test_invalid_hooked_responses_body_persists_no_success_facts`

结果：pytest 报告 `5 passed in 3.91s`，退出码为 `0`。selector 清单与 pytest 收集/通过数相等；关键行为另由下节不同实现方式的独立 spy 交叉验证。候选 `git status --porcelain=v1 -z` 的 SHA-256 在测试前后均为干净树摘要 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

## 独立简单 spy

Spy 不导入现有测试 helper，直接使用 production `execute_anthropic_pipeline()`、`AnthropicClient`、builtin token calibration、`HooksExecutor`、`HistoryConsumer` 与 `HistoryStore`。数据库和 tokenization state 只写入 `TemporaryDirectory`。

### Throwing strategy

实际结果为：`RuntimeError`；context 为 `failed`；`response_observer=0`；`calibration_samples=0`；`error_observer=1`；`finalize_observer=1`；`history_finalize=1`；History `status=failed`、`response=null`、`usage=null`；strategy `on_success()` 调用一次。

该结果与现有 throwing-strategy test 使用不同 harness，但得到同一 lifecycle 结论，满足失败零 calibration/observer 且单失败 finalize。

### 合法成功

实际结果为：无异常；context 与 History 均为 `completed`；`response_observer=1`；`calibration_samples=1`；`finalize_observer=1`；`history_finalize=1`。History response 的最终 text 为 response hook 写入的 `spy-final`，最终 body usage 为 `input_tokens=37`、`output_tokens=3`。

History normalized usage 为 `input_tokens=8`、`cache_read_input_tokens=2`、`cache_creation_input_tokens=1`、`output_tokens=3`、`reasoning_tokens=1`、`total_tokens=14`。Conversion facts 同时包含 request-side `system[0].cache_control`、`metadata.tenant` 与 response-side `response_id_transformed`，全部属于最终成功 attempt `0`。

### Invalid hook final body

实际结果为：`ApiError`；context 为 `failed`；`response_observer=0`；`calibration_samples=0`；`error_observer=1`；`finalize_observer=1`；`history_finalize=1`；History `status=failed`、`response=null`、`usage=null`。

Spy 总退出码为 `0`。候选状态摘要在 spy 前后同样保持干净树 SHA-256。三组 spy 结果与对应定向 tests 构成不同 harness 的交叉验证。

## 未验证范围

本轮按用户要求未扩完整矩阵，未运行全量 pytest、ruff、pyright、streaming、真实 upstream、retry 多 attempt、History 持久化失败或其他 callback/observer 抛错组合。这些项目均为**未验证**，不是本轮 PASS 的隐含组成部分。

## 结论

用户指定的三组行为均有实际运行证据：throwing strategy 不发布成功 calibration/observer 且只产生一次失败 finalize；合法成功只发布一次成功事实，并由 History 保存最终 body、usage 与 conversion facts；invalid response hook 保持零成功 facts。未发现本轮范围内的偏差或阻断缺陷，故 verdict 为 **PASS**。
