# Responses → Anthropic non-stream identity 修复定向复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-response` 分支 `feat/responses-anthropic-nonstream`，固定 `HEAD=7ddf17364d97349638d44352bbd9a9b025723ccc`、base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。仅复核上一轮 `docs/tmp/260807-review-code-nonstream-response.md` 的唯一 major——public Anthropic message id 泄漏 upstream `resp_*` 且 converter 无独立 upstream identity／conversion facts——以及本次新增 `ConvertedResponse`、public `msg_` helper、`ResponseConversionFact` API 所直接引入的问题。按派活边界，不重新评审 happy-path 骨架的其他内容、usage／terminal／route／stream 等已明确留给后续切片的边界。
- **总体 verdict**：**可进入下一阶段；可 squash 回并**。上一轮唯一 major 已关闭；本轮未发现新增 blocker 或 major。
- **blocker 数**：0。
- **major 数**：0。
- **双视角覆盖证据——机械核对**：每次计入结论的 shell 读取或执行均在同一调用内验证目标 root、分支、`HEAD=7ddf17364d97349638d44352bbd9a9b025723ccc` 与 clean worktree；对比修复前后 API，逐行核对 `ConvertedResponse.message`、`upstream_response_id`、`upstream_model`、immutable facts tuple、public helper、`__all__`、硬编码 fixed-vector oracle 与两个不同 upstream id 的区分断言；对账 current Spec 的 public identity 与 upstream identity 分离要求；以 `git grep <HEAD>` 清点符号使用面，确认新增 API 当前只存在于 converter 与定向测试，尚无 production route 调用者，符合本 happy-path 骨架切片边界。固定 HEAD 的定向 pytest 执行结果为 8 passed；pytest collection 与 Python AST 两种不同原理均清点到同一文件 8 个测试；Ruff 通过；Pyright 为 0 errors／0 warnings／0 informations。执行前后目标 worktree 均 clean。共享终端中缺少本轮 nonce 的串线输出，以及一次在 pytest 自身 import 阶段收到外部 `SIGINT` 的运行，均未计入绿色证据；最终证据来自使用 `setsid --wait` 且完整返回本轮结束标记的调用。
- **双视角覆盖证据——第一人称执行**：模拟调用方分别转换同一个 upstream id 两次和另一个 upstream id 一次；同一输入得到稳定相同的 `msg_` public id，不同输入得到不同 public id。随后只序列化 `converted.message` 作为 Anthropic public JSON，确认 public body 不含原始 `resp_secret_A`、`upstream_response_id` 或 `facts`；再从 typed wrapper 读取 `upstream_response_id="resp_secret_A"`、`upstream_model="gpt-x"` 与 `response_id_transformed@id` fact，确认诊断身份仍可 value-exact 消费。最后按未来 stream／route 调用者视角检查 helper 的公开导出和返回类型：调用方不需要从 public message 反推 upstream identity，也不会因取 `message` 而把 wrapper metadata 意外序列化到 wire。

## 事实性发现

未发现问题。

上一轮 major 的关闭证据如下：

- `src/app/protocols/responses_anthropic.py:27-31,93-115` 现在返回具名 `ConvertedResponse`，public `MessagesResponse.id` 由公开的 `anthropic_message_id_from_response_id()` 生成稳定、opaque、Anthropic-compatible 的 `msg_` identity；原始 upstream id 与 model 分别保存在 `upstream_response_id`、`upstream_model`，identity transform 以独立 fact 暴露。
- `tests/unit/test_responses_anthropic_nonstream.py:28-69` 不再把 upstream `resp_123` 固化为 public id；测试以硬编码 `msg_HAGUmRojzlDCLGp3XE8QLxwLG9FislDW` 作为独立 oracle，并分别断言 stable、distinct、no raw-id exposure 与 upstream identity value-exact preservation。expected 没有调用被测 helper 生成，未形成同源自证。
- 独立 API probe 对 `resp_secret_A`／`resp_secret_B` 实跑得到两个不同 `msg_` id，并确认序列化 public message 不含 wrapper 的 upstream identity 或 facts；因此修复不仅在类型层存在，也在实际 wire serialization 接缝成立。

## 主观建议

无。按本轮定向范围，不为后续切片边界重复开项。

## 回并结论

当前为 **0 blocker／0 major**，上一轮唯一 major 已关闭，且新增 identity／facts API 未发现新的阻断问题。该 happy-path 骨架在本轮范围内**可 squash 回并**。这不表示上一轮已列出的 refusal、完整 usage、terminal／error、route lifecycle、stream 等后续边界已实现或已验收；它们继续由后续切片与 Acceptance gate 承接。
