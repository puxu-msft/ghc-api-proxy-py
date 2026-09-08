# Responses semantic parity 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-semantic-parity`，branch `fix/responses-semantic-parity`，固定 `HEAD=1cde3d58338eeefb3cf8040f970c3612d451668b`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。只读评审候选最终代码与测试；唯一写入为本报告。重点复核主线评审的两项 major：空 reasoning 的 stream／non-stream 一致性，以及 function arguments／reasoning 多层 authoritative done 冲突的 typed reject；同时对账 current finalized Spec、合法 done-only、错误类型、测试与正控。
- **总体 verdict**：**修复 major 后可进入。当前不可 squash。** 上一轮两项 major 的目标场景均已关闭，但发现新的 stream／non-stream parity major：stream 接受未知 reasoning summary part type，而 non-stream 以 `invalid_reasoning` typed reject。修复并定向复评至 `0 blocker／0 major` 后方可 squash。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：1。
- **双视角覆盖证据——机械核对**：固定并复验目标 root、branch、HEAD、base 与 clean 状态；完整阅读最终 `responses_stream_parser.py`、`responses_reasoning.py` 及相关单测；逐项对账 current Spec 的 unknown content part `REJECT`、stream／non-stream 等价、一 reasoning item 一 thinking block、空 `encrypted_content` 等同 absent、authoritative done 与 malformed lifecycle 合同。核对 function 三层值来源、reasoning summary part 边界、稳定 error code／event type 与合法无 delta 路径。可信定向 gate 在候选导入路径上得到 `28 passed`，口径为 `tests/unit/test_responses_stream_parser.py` 与 `tests/unit/test_responses_reasoning.py`。全仓 pytest、Ruff、Pyright 与 mutation 正控被共享终端中其他并行会话的命令／`SIGINT` 串扰，未形成可信完成标记，不计为通过。
- **双视角覆盖证据——第一人称执行**：模拟空 reasoning 的 absent／空字符串 payload、encrypted-only、summary-only、function delta→arguments.done→item.done、无 delta authoritative done、reasoning summary done→item done 一致／冲突、part 边界改变，以及 malformed unknown summary part。独立真实探针对 `summary=[{"type":"future_summary","text":"accepted?"}]` 得到 stream `CompletedBlock`／`ReasoningBlock(summary="accepted?")`，而 non-stream 得到 `ResponseConversionError(code="invalid_reasoning", field_path="output[0]")`。

## 上一轮两项 major 关闭复核

1. **空 reasoning stream／non-stream 一致性：已关闭。** Current Spec 冻结的是“一 Responses reasoning item → 一 Anthropic thinking block”；空 `encrypted_content` 与 absent 相同，而不是丢掉整个空 item。`src/app/openai/responses_stream_parser.py:493-511` 现生成 `ReasoningBlock("", None)`；`src/app/anthropic/thinking/responses_reasoning.py:43-80` 的 non-stream producer 生成带项目 bare marker 的空 thinking block。`tests/unit/test_responses_stream_parser.py:268-302` 同时覆盖 absent 与空字符串并对账两条路径。该方向符合 current Spec，不能沿用上一轮基于旧 oracle 的“零 block”建议。
2. **function arguments／reasoning authoritative done 冲突：已关闭。** `src/app/openai/responses_stream_parser.py:524-550` 将 delta、`arguments.done` 与 `output_item.done` 的 arguments 统一核对，冲突抛 `authoritative_arguments_mismatch`；`src/app/openai/responses_stream_parser.py:552-602` 按 summary index 核对 part done 与 item done，文本或 part 边界冲突抛 `authoritative_reasoning_mismatch`。`tests/unit/test_responses_stream_parser.py:153-187,305-395` 覆盖 function mismatch、reasoning mismatch 与 part-boundary mismatch，并精确断言 error code／event type。
3. **合法 authoritative-only 不 false-red：实现成立，function 最强回归缺一条。** `src/app/openai/responses_stream_parser.py:513-540` 允许 `output_item.done` 自身携带完整 arguments；`tests/unit/test_responses_stream_parser.py:238-265` 覆盖 reasoning 仅靠 item done。Function 正样本仍先发送 `arguments.done`，详见 minor。

## 事实性发现

[major] `src/app/openai/responses_stream_parser.py:552-581` — stream authoritative reasoning summary 未校验 part `type`，与 non-stream 和 current Spec 的 unknown content part `REJECT` 不一致 — `_reasoning_summary_parts()` 只检查 object 与字符串 `text`，不检查 `type == "summary_text"`；`src/app/anthropic/thinking/responses_reasoning.py:56-64` 则明确要求该类型。真实候选探针中，未知 `future_summary` 被 stream 成功转换，却被 non-stream 以 `invalid_reasoning` 拒绝，违反 Spec `docs/agents/anthropic-responses-bridge/spec.md:185,255,297`，并会让同一响应仅因 `stream` 开关不同而从错误变成成功 thinking block — 在 shared reasoning item normalizer 中精确要求 `summary_text`，未知类型抛稳定 typed protocol error；增加同一 malformed fixture 同走 stream／non-stream 的 parity 回归，并断言两侧都失败且分类一致。

[minor] `tests/unit/test_responses_stream_parser.py:126-150` — “without deltas”正样本仍发送 `response.function_call_arguments.done`，没有锁住真正 item-done-only 分支 — 若未来误删 `src/app/openai/responses_stream_parser.py:524-540` 从 item body 补齐 arguments 的逻辑，该测试可能仍绿。增加只发送 `output_item.added` 与携带完整 arguments 的 `output_item.done` 的测试，并断言精确 `FunctionCallBlock`；保留现有双 done 正样本，因为两者守不同入口。

## 主观建议

[建议] `src/app/openai/responses_stream_parser.py:552-602` 与 `src/app/anthropic/thinking/responses_reasoning.py:43-80` — 两条路径重复实现 reasoning summary schema 校验，已出现一严一松的实际漂移 — 预期可减少未来 Responses schema 演进时的 parity 回归 — 推荐提取共享 typed parser／normalizer；协议专属状态机继续项目内实现合理，未发现适合替换它的成熟第三方库。

## 测试、正控与结构怪味

- **可信绿色**：固定候选导入路径的定向 pytest为 `28 passed`。
- **可信负样本**：unknown reasoning summary part 的 stream accept／non-stream typed reject 已真实复现。
- **正控状态**：已核对测试与目标机制映射，但运行时 mutation 被共享终端串扰中断，不能声称 red→restore→green 已完成。修复后复评必须在隔离进程移除空 reasoning 构造、function mismatch 校验、reasoning mismatch 校验，分别确认目标测试因预期机制转红，再恢复为绿。
- **未完成 gates**：全仓 pytest、Ruff、Pyright没有可信完成标记，squash 前须在固定 HEAD、候选 `PYTHONPATH` 与隔离进程补齐。
- **结构怪味**：`responses_stream_parser.py:552-581` 与 `responses_reasoning.py:43-80` 为重复实现／同一语义一严一松，本轮作为 major 根因；`test_responses_stream_parser.py:126-150` 的测试名称覆盖范围强于真实事件序列，本轮记 minor。

## 结论

当前为 **0 blocker／1 major／1 minor**。上一轮两项 major 的目标修复方向正确，但 unknown reasoning summary part 仍造成可复现的 stream／non-stream 分叉。修复 major、补 function item-done-only 回归并完成全仓 gates与正控后，定向复评达到 **0 blocker／0 major** 时可明确判定可 squash。
