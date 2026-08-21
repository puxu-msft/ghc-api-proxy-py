# PoC：续写请求能否原样回传加密 reasoning

**日期**：2026-08-21。**性质**：调查结论转录（原调查 agent 受 harness 限制未能建档，本文由主会话落盘）。**结论**：**可以回传**，G2 最大的未知项已消除。
**上级文档**：`.dev/docs/tmp/260821-plan-g2-wire-stream-ending.md` 的第 5 项。

## 问题

G2 的 continuation 要把已交付给客户端的块当作一个 assistant turn 发回上游。事故请求 req=d3b7f5ba 里已交付的两块中有一个是 `think(enc:1)`——加密 reasoning，`thinking` 文本为空、只有不透明 `signature`。`continuation_messages` 直接把 `CompletedBlock.payload` 塞进 `content`，于是发出去的会是 `{"type":"thinking","thinking":"","signature":"…"}`。

**空串会不会被上游拒掉？** 这个担心有具体来由：项目已实测过 `{"type":"text","text":""}` 被上游直接拒绝（`messages: text content blocks must be non-empty`），242 秒等待期间合成的空文本块因此毒化了一整个会话的历史。

## 结论与证据

**可以。** 只要 `signature` 非空且**原样保留**，`thinking: ""` 是合法的加密 thinking 形状。

| 主张 | 来源 | 强度 |
|---|---|---|
| 真实 Copilot `/v1/messages` 接受 `{"type":"thinking","thinking":"","signature":"<原签名>"}` 的 assistant 续轮，返回 200 | `~/src/copilot-api-js/exp/anthropic-responses-direct/FINDINGS.md:106-130`，真实上游探针 | **强实测** |
| 签名改动一个字符即 400 | 同上 | 强实测 |
| 该探针用的是 `claude-opus-4.8`，**不是**本次事故的 `claude-opus-5` | 同上 | 已知限制 |
| 现有 cassettes 无法提供 body 证据（请求侧只存 `digest`/`model`/`stream`） | `tests/int/cassettes/` | 确凿 |

**限制要照实说**：模型不同。当前 API 合同与参考实现的 sanitizer 都佐证该形状通用，但严格讲这是从 opus-4.8 外推到 opus-5。**足以据此开工，不足以写成「已在 opus-5 上验证」。**

## 两条腿的构造形状

- **Anthropic 腿**：原样追加 `assistant.content = [{"type":"thinking","thinking":"","signature":sig}, …已交付的其余块]`，再追加 continuation 的 `user` turn。
- **Responses 腿**：必须构造成顶层 `input` 的 reasoning item——`{"type":"reasoning","summary":[],"encrypted_content":"<output_item.done 的最终值>"}`，其后是 assistant 的 `output_text` message item 与 user 的 `input_text` message item。项目的 carrier 已能完成这一往返，见 `src/app/pipeline/translation_driver/reasoning_carrier.py` 与 `src/app/pipeline/translation_driver/openai_responses.py:561-597`。

这印证了 G2 方案第 4 项：`continuation_messages` 现在只写了 Anthropic 那一种形状，Responses 腿需要另一套构造，不能套用。

## 边界

- **原生 Claude 的 signature 不得改写，也不得拿项目自己的 carrier 重编码。** 项目 carrier 只用于 Responses 的 `encrypted_content`。
- 若签名缺失、损坏，或要跨到不兼容的腿，最小替代是**丢弃 reasoning 块、只回传已交付的文本块**，代价是丢失隐藏的续接状态。
- 参考实现的 continuation 当前主动丢弃 thinking——**那是它的产品政策，不是协议拒绝的证据**，不要当作「上游不接受」来引用。
