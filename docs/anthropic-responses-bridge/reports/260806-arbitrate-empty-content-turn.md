# 空 content-list turn 合同裁决

- **评审范围**：current Spec request matrix、主树 `src/app/models/anthropic.py` 的 `MessagesRequest`／`AnthropicMessage`、integration commit `614cacde72568d53170be714ea5c9a9b4d889a05` 的 Anthropic→Responses request converter、merged-state review `docs/tmp/260806-review-code-bridge-foundations.md`，以及 2026-08-07 读取的 Anthropic Messages API 官方语义。只裁决 message-level `content=[]`；不重开空 text block、空 tool result 或 response-side zero-content 合同。
- **总体 verdict**：**可按唯一最小动作进入修复：`REJECT`。** 不采用 `PRESERVE`，不采用 `DEGRADE`，也不注入占位文本。
- **blocker 数**：0。
- **major 数**：1，即 integration commit 的 silent drop；本裁决给出关闭它的唯一合同。
- **基线**：主树 `main@ed77c9d191df81c451c25161420515cca52ce6a4`；current Spec SHA-256 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`；integration 分支 HEAD `614cacde72568d53170be714ea5c9a9b4d889a05`。三者均在每次本轮 shell 调用前作为门禁；并行实现工作树可有未提交 WIP，但不作为裁决 oracle。

## 双视角覆盖证据

### 机械核对

- Spec 的 request matrix 把“user／assistant turn 与同 turn block 顺序”冻结为 `PRESERVE`，把 silent drop 排除在合法状态之外；`DEGRADE` 只允许矩阵明确列出的项目，empty content-list 没有这项授权。
- `src/app/models/anthropic.py:27-29` 的 `AnthropicMessage.content` 是 `str | list[ContentBlock]`，没有 `min_length`，因此当前 Pydantic 模型确实接受 `[]`。
- integration commit 的 `_convert_messages()` 把 list content交给 `_convert_blocks()`；空 list返回零 items，随后 `extend()` 无声消掉整个 turn。Merged review 已以 `user("first") → assistant([]) → user("second")` 复现 wire 只剩两个相邻 user message items且 `facts == ()`。
- Anthropic Messages API 官方文档写明：每个输入 message 有 `role` 与 `content`，`content` 可以是 string 或 content-block array；同一文档还写明 consecutive `user` 或 `assistant` turns 会被合并。官方 schema 页面未给 content array 声明非空下界，因此不能把本地已接受的 `[]` 当成“上游肯定已拒绝”的无害输入。
- 并行实现 WIP 已采用同一方向：converter guard 的拟议错误为 `code="invalid_content"`、`field_path="messages[i].content"`，并覆盖 user／assistant 两种空 turn。本裁决与其方向**不冲突**；WIP 是否最终通过测试仍由实现评审决定。

### 第一人称执行模拟

- 执行 `user("first") → assistant([]) → user("second")`：若 drop 中间 turn，Responses 收到两个相邻 user items；后续 normalization／provider 可把它们合并，原 turn boundary不可恢复。
- 执行镜像序列 `assistant("first") → user([]) → assistant("second")`：同样会制造两个相邻 assistant items；最后 assistant 的 prefill／continuation语义尤其不能由代理猜测合并。
- 执行 `PRESERVE` 方案：要么发一个零 content parts 的 Responses message，但当前规格与已核验实现没有冻结该 wire 形状的合法性；要么造空 text part／占位文本，这会凭空增加语义。因此当前不能声称无损 preserve。
- 执行 `DEGRADE` 方案：drop、merge或占位都会改变 turn boundary，而且 empty content-list 不在 Spec 的 `DEGRADE` allowlist；记录一个 fact也不能把不可逆语义变化变成合规。
- 执行 `REJECT` 方案：在任何 upstream 调用前返回稳定 typed request-conversion error，原始 message index仍在，错误可定位，且不会形成相邻 same-role wire items。这是 strict compatibility 下唯一不猜测语义的行为。

## 裁决

**`content=[]` 固定 `REJECT`。**

理由不是“数组在 Anthropic 一定非法”——现有官方 schema文本没有提供这个结论，而本地 Pydantic 明确接受它。理由是 direct bridge 当前没有已冻结、已验证的 Responses 等价表达；silent drop 会删除 turn boundary并可能让相邻 same-role items被合并；占位内容会伪造语义；`DEGRADE` 又没有矩阵授权。Strict bridge 在无法证明无损表达时必须 fail closed。

## 唯一最小动作

只在 Anthropic→Responses converter 的 message 遍历边界增加一个前置 guard：当 `message.content` 是空 list 时，在调用 `_convert_blocks()` 之前抛 `RequestConversionError`。

- **code**：`invalid_content`。
- **field_path**：`messages[i].content`，其中 `i` 是原始 request message index。
- **message**：稳定说明 message content list must not be empty；不要包含完整用户内容。
- **时点**：conversion 阶段、upstream 调用前、任何 Responses input item产生前。
- **禁止顺带动作**：不修改共享 `AnthropicMessage` Pydantic 类型，不把 `list[ContentBlock]` 改成全局 `min_length=1`，不 drop turn，不合并邻居，不生成空 text／空白／sentinel占位，不记录 `DEGRADE` 后继续，也不改 direct Messages leg。

最小回归门只需参数化 user／assistant 两种角色：空 turn夹在相反角色的两个非空 turns之间，断言同一 typed error 的 `code` 与精确 `field_path`；另保留一个非空 list 正样本，防止 guard 误拒合法内容。测试不应断言 converter输出相邻 same-role items，因为正确行为是在产生 wire前失败。

## 事实性发现

[major] `src/app/protocols/anthropic_responses.py` 的 message conversion 边界 — integration commit 对 `content=[]` 返回零 items并静默删除 turn — 删除后可产生两个相邻 same-role Responses items，原边界不可恢复，且没有 `ConversionFact`或 typed error — 按上述唯一动作以 `invalid_content @ messages[i].content` 在转换前拒绝。

## 主观建议

无。`PRESERVE` 只有在未来取得 Responses 空 message 的正式 schema／真 wire oracle、并证明它跨 provider不会被删除或合并后才值得重裁；这不是当前最小修复的并行选项。

## 结构怪味与方案反思

- `src/app/models/anthropic.py:27-29` — **接受域宽于某一 transport adapter 的可表达域** — 本轮不收紧共享模型；在 converter边界做 protocol-specific reject，避免误伤 direct Messages leg。
- `src/app/protocols/anthropic_responses.py` 的 `_convert_messages()`／`_convert_blocks()` 接缝 — **空集合被当成“没有输出”而非“无法表达”** — 本轮用显式 guard修复；同类 converter应继续审计“合法输入→零 items”路径。
- **更好的内部替代方案**：全局 Pydantic `min_length=1`更早失败，但会改变所有 Anthropic legs 的公共接受域，超出本裁决；占位或 preserve 未有 wire oracle。Converter-local reject是当前边界最准确的方案。
- **判据判别力**：双角色负样本能抓 silent drop；非空 list 正样本防 false-red；精确 error path保证错误仍指向原 turn，而非后续相邻 item。
- **成熟第三方方案**：这是跨协议语义政策，不是缺少 parser／validator库；Pydantic可表达非空约束，但不能替项目决定该约束应作用于共享入站模型还是仅 Responses leg。因此没有应引入的第三方替代。
