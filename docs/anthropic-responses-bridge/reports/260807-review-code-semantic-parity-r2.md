# Responses semantic parity 独立代码复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-semantic-parity`，branch `fix/responses-semantic-parity`，固定 `HEAD=f5bca39ac582911b61d278fd678ec9298ad0c08e`、parent `1cde3d58338eeefb3cf8040f970c3612d451668b`、base `80bc8f252b46c511f428af1d97159a5980ee9dc9`，且目标 worktree clean。本轮只复核 R1 `docs/tmp/260807-review-code-semantic-parity.md` 的唯一剩余 major、R1 minor 的真正 function item-done-only 回归、空 reasoning 仲裁 `docs/tmp/260807-arbitrate-empty-reasoning.md` 要求的一个 bare block，以及 successor 提交 `f5bca39…` 引入的新问题；不重新展开 R1 已关闭的其他 semantic-parity 行为或完整 bridge 产品符合性。
- **总体 verdict**：**可进入下一阶段；可 squash。** R1 的 unknown reasoning summary part major 已关闭，真正 function item-done-only 测试已补，空 reasoning 的一个 bare block 合同保持不变；本轮未发现 successor 引入的新 blocker、major 或 minor。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **squash 结论**：目标已达到明确的 **`0 blocker／0 major`** 门，`fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` **可 squash**。本结论只覆盖本报告评审范围，不表示完整 Anthropic Responses bridge 已取得产品 `PASS`。

## 双视角覆盖证据

### 机械核对

- 每次采纳为证据的 shell 调用均在同一次调用内 gate 目标物理 root、branch、精确 HEAD、`80bc…` base 与 clean 状态；目标由 base 起两提交线性演进，successor parent 精确为 R1 HEAD `1cde3d…`。Successor 只修改 `src/app/openai/responses_stream_parser.py` 与 `tests/unit/test_responses_stream_parser.py`，`git diff --check` 通过。
- 完整阅读最终 parser 与相关测试，并对照 R1、空 reasoning 仲裁、FINALIZED Spec、non-stream `responses_reasoning_to_anthropic()` 与 response converter。`src/app/openai/responses_stream_parser.py:552-579` 现要求每个 authoritative summary part 同时满足 object、`type == "summary_text"` 与 string `text`；否则抛 `ResponsesStreamProtocolError(code="invalid_reasoning", event_type="response.output_item.done")`，与 non-stream 的 strict schema 和 Spec unknown part `REJECT` 一致。
- `tests/unit/test_responses_stream_parser.py:156-174` 新增真正 item-done-only function 正样本，没有发送 `response.function_call_arguments.done`；`tests/unit/test_responses_stream_parser.py:290-319` 用同一 malformed fixture 对账 stream／non-stream，精确断言两侧均为 `invalid_reasoning`；其后的 empty reasoning 参数化测试继续断言 absent／empty `encrypted_content` 均形成一个 `thinking=""` 项目 bare marker block。
- 可信定向 gate 固定候选 `PYTHONPATH` 与 import 路径，运行 `tests/unit/test_responses_stream_parser.py`、`tests/unit/test_responses_reasoning.py`、`tests/unit/test_responses_anthropic_nonstream.py`，结果为 **43 passed**；同一 gate 的定向 Ruff 为 `All checks passed!`，Pyright 为 `0 errors, 0 warnings, 0 informations`，结尾再次确认 HEAD 未变且 worktree clean。口径仅为上述三个测试文件和六个相关静态检查文件，不扩张为全仓 gate。
- 两次额外独立 runtime probe 与一次行号命令遭共享终端并行会话串扰，返回中没有本轮 nonce；它们均未计入证据。另有夹入输出的 `443 passed` 也未计入本轮通过数。

### 第一人称执行

- 以未知 `summary=[{"type":"future_summary","text":"accepted?"}]` 走 stream：item added 只建 attempt-local reasoning draft；authoritative item done 进入 `_reasoning_summary_parts()` 后在 block 完成和任何下游提交前 typed reject，不再像 R1 那样生成 `ReasoningBlock("accepted?", None)`。同一 fixture 走 non-stream 仍在 `output[0]` 以 `invalid_reasoning` 拒绝，两条路径结果一致。
- 以 function call 仅发送 item added，再直接发送携带完整 arguments 的 output item done：`_update_function_call_from_item()` 取得 authoritative arguments并置 `arguments_done`，随后 `_complete_function_call()` 在 item done 与 arguments 均闭合时生成精确 `FunctionCallBlock`。新测试真实经过该分支，不再由独立 arguments done 事件提前满足条件。
- 以 `summary=[]` 加 absent／empty `encrypted_content` 执行：stream 继续生成 `ReasoningBlock("", None)`，non-stream 继续生成恰好一个 `thinking=""` 加项目 bare marker 的 block；没有因修 unknown type 而回退为零 block，符合空 reasoning 仲裁。
- 以合法 `summary_text`、reasoning summary done／item done 一致和合法 authoritative-only 输入执行：新增检查只拒绝 unknown／malformed part，不拒绝已冻结的正确样本；定向测试覆盖这些正样本并保持绿色。

## R1 发现关闭复核

1. **R1 major：unknown reasoning summary part stream／non-stream 分叉——已关闭。** Stream authoritative item done 现在与 non-stream 共用同一最小 schema 语义：只接受 `summary_text` 加 string `text`。Malformed fixture 两侧均 typed reject，且 stream 拒绝发生在 semantic block 完成前。
2. **R1 minor：缺少真正 function item-done-only 正样本——已关闭。** 新测试不发送 arguments done，直接证明 item done body 可以独立补足 authoritative arguments；现有“arguments done＋item done”测试仍保留，两者分别守住不同入口。
3. **空 reasoning 仲裁——保持关闭。** Successor 未改 reasoning block cardinality；absent／empty payload 仍各生成一个 bare block，不采用已被仲裁否决的零-block解释。

## 事实性发现

未发现问题。

## 主观建议

无。

## 结构怪味与替代方案复核

- **扫描范围**：successor 改动的 parser／测试、non-stream reasoning normalizer与 response converter接缝。
- **判据**：重复 schema、职责错位、抽象泄漏、测试名称强于实际路径、同一语义一严一松，以及可由成熟第三方库替代的手写机制。
- **结果**：R1 已指出 stream／non-stream schema 重复可能漂移；本 successor 已让两侧语义对齐，未新增更弱的第三份实现。长期可提取共享 typed normalizer，但当前状态机和 non-stream converter 的错误载体／上下文不同，未提取不构成本次正确性缺陷。未发现适合替代 Responses lifecycle 状态机的成熟第三方库，也未发现新的结构怪味需要阻断或记为本轮 backlog。

## 结论

本轮为 **0 blocker／0 major／0 minor**。R1 唯一 major 与 minor 均已关闭，空 reasoning 仲裁合同未回归，定向 pytest、Ruff 与 Pyright 均通过；`fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` **可 squash**。
