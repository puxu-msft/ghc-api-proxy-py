# Copilot item identity 定向终审 R2

## 结论

- **评审范围**：候选 `fix/copilot-item-identity@f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`，基线 `0e66cab5ffd636e40a0f378d6017326603a3196a`。定向复核默认 strict、Copilot relaxed item ID 漂移、present empty 拒绝、missing／null 既有合同、`output_index`／`content_index` 关联、`type`／`call_id`／`name` 独立严格性，以及 generic route 不回归。
- **总体 verdict**：**可进入 squash**。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对

- 对账 `0e66cab5ffd636e40a0f378d6017326603a3196a..f171fa05bc0a2afcdd1dab12d3010cf09ce978ab` 的全部 5 个变更路径，并读取最终文件而非只看 diff。
- 核对默认值仍为 strict：`ResponsesStreamParser.__init__` 的 `require_stable_item_id=True` 位于 `src/app/openai/responses_stream_parser.py:149-156`；adapter 同样默认为 `True`，位于 `src/app/delivery/responses_anthropic_stream.py:159-167`。
- 核对 provider 分界：`src/app/routes/anthropic.py:229-246` 仅在 `settings.upstream.type == "copilot"` 时把 response／item 两个稳定性开关设为 relaxed；generic 仍把两者设为 strict。基线已存在 Copilot response ID relaxed，本提交只把同一 provider 边界传递给 item ID，并未额外扩大 response ID 范围。
- 核对字段合同：`src/app/openai/responses_stream_parser.py:915-959` 只跳过 relaxed 模式下跨事件 item ID 相等性；present `item_id` 仍须为非空字符串，nested item `id` 仍须为非空字符串。`output_index`／`content_index` 仍负责定位 item／content draft（`535-548`、`915-927`），`type`、`call_id`、`name` 的原有一致性校验仍位于 `290-296` 与 `618-632`，未被条件化。
- 核对测试判别力：`tests/unit/test_responses_stream_parser.py:95-281` 同时包含正确样本与错误样本；`tests/smoke/test_anthropic_responses_stream_route.py:1449-1562` 分别覆盖 Copilot relaxed 成功和 generic strict 失败。
- `git diff --check 0e66cab5ffd636e40a0f378d6017326603a3196a..f171fa05bc0a2afcdd1dab12d3010cf09ce978ab` 通过，评审树在测试后保持干净。

### 第一人称执行模拟

- **默认 strict**：以 `msg_added` 打开 `output_index=0`，随后给同一 index 发送 `item_id=msg_other`，执行路径在 `_require_item` 后进入 `_validate_event_item_id` 并得到 `item_id_mismatch`；done item 改 ID 同样在 `_validate_item_id` 失败。
- **Copilot relaxed 漂移**：依次模拟 `output_item.added → content_part.added → output_text.delta → output_text.done → content_part.done → output_item.done → response.completed`，每层使用不同但非空 item ID；关联始终由 `output_index=0` 与 `content_index=0` 保持，最终成功产生 `message_stop`。
- **present empty**：event-level `item_id=""` 在 strict／relaxed 下都进入 `item_id_mismatch`；done item 的 nested `id=""` 在两种模式下都由 `_require_string` 拒绝为 `invalid_event`。
- **missing／null**：event-level `item_id` 缺失或显式 `null` 均沿既有合同视为未提供，在 strict／relaxed 下继续关联到相同 `output_index`，不产生误拒绝。
- **其他身份维度**：模拟未知 `output_index`、错 `content_index`、done item 改 `type`、function call 改 `call_id` 或 `name`；relaxed item ID 不改变对应的 `unknown_output_item`、`message_content_mismatch`、`item_type_mismatch`、`function_call_identity_mismatch`。
- **generic route**：模拟 generic upstream 的跨帧 item ID 漂移，路由仍传 `require_stable_item_id=True`，在首个漂移事件前置失败为 HTTP 502／`item_id_mismatch`，未误走 Copilot relaxed 分支。

## 最小测试

测试均在 `/home/xp/src/ghc-api-proxy-py-item-identity`、候选完整提交 `f171fa05bc0a2afcdd1dab12d3010cf09ce978ab` 上运行，使用主树 `.venv` 与候选树 `PYTHONPATH`。项数由实际执行结果和独立 `--collect-only` 选择口径交叉核对。

- `tests/unit/test_responses_stream_parser.py -k 'item_identity or item_id'`：15 passed，45 deselected，退出码 0。
- `tests/smoke/test_anthropic_responses_stream_route.py -k 'copilot_route or generic_route'`：2 passed，17 deselected，退出码 0。
- 按要求未扩展测试矩阵，未运行全量测试、Ruff 或 Pyright；这些不属于本次定向终审的声明范围。

## 事实性发现

未发现问题。

## 主观建议

无。

## 最终裁决

候选在本次指定范围内为 **0 blocker／0 major／0 minor**。默认 strict、Copilot-only relaxed、present empty 拒绝、missing／null 兼容、索引关联及其他身份字段严格性形成了互补的正反测试闭环；generic route 未回归。**可 squash。**
