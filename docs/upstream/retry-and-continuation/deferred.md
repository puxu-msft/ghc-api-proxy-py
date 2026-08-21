# 未闭合、待查、与明确不做

本文件只列**需要用户裁决**或**已知未闭合**的项。已经定下来的在 `status.md`。

## 已知未闭合

### 1. 上下文超限的 400，其 `error.code` / `error.type` 字面量未查清

人写文档原本写的是 `SSE stop_reason = model_context_window_exceeded`。**该判据已被实测证伪**：Responses 腿的值空间里根本没有这个东西（`incomplete_details.reason` 20/20 全是 `max_output_tokens`），Anthropic 腿 13 万次请求零观测。

正面形态是 **HTTP 400**，`error.message` 匹配 `prompt token count of N exceeds the limit of M`——但这一条目前只有**旁证**（本项目 `src/app/tokenization/limits.py:10-13` 已经抄了这对正则，两份参考实现也都只匹配 message 文本）。

**未查清的是 `error.code` 与 `error.type` 的字面量。** 有一个已知的读反陷阱：`copilot-api-js` 里的 `context_length_exceeded` 是它**合成给下游**的值，不是从上游读到的。

调查进行中，结果将落到 `reports/`。

### 2. reasoning item 被截断时没有任何信号

`message` 与 `function_call` 的 `output_item.done` 带 `status`，被截断的是 `"incomplete"`。**reasoning item 没有这个字段**——已用正样本对照确认：正常收尾的 reasoning item 与被截断的，键集逐字相同（`content, encrypted_content, id, summary, type`），`summary: []` 在两侧都出现，也不是信号。

response 层有信号（`response.incomplete`），但它晚于 item 关闭到达，要用就得把块扣住——那是延迟提交，会往交付路径塞状态。

**用户 2026-08-21 裁决：历史里没有信号就保持悬念，暂不特殊处理。** 于是 20 例样本里有 6 例（只有 reasoning 中途撞顶）的半截 thinking 块会照常交付。哪天它造成可观测的麻烦，再考虑延迟提交。

### 3. `model_context_window_exceeded` 在 Anthropic 腿仍是可能的

两条腿的权重不同，别混为一谈：

- **Responses 腿**：结构性不存在，值空间里没有。权重强，可据此行动。
- **Anthropic 腿**：Anthropic 枚举里**有**这个值，只是 13 万次请求零观测。这是「未观测」，不是「不可能」。

所以分类表里不要把它写成已排除。

### 4. 上游 SSE 中途的 `error` 帧：零观测

134336 个 operation、约 3000 万根帧里，`response.failed`、`response.cancelled`、上游 `error` 帧**各 0 次**。参考实现枚举过的完整词表（含 Copilot 专有的嵌套 `{"type":"error","error":{code,message}}`）只有旁证。

现状的处置是坏的：这些帧被 `push` 静默丢弃，`terminal.seen` 保持 False，最终发出一条**与「连接被掐断」完全同形**的 `incomplete_responses_stream`。G1（分支 `fix/upstream-error-events`）正是在补这个。

### 5. 已交付之后的两条失败路径行为不一致

- 上游干净 EOF 但无终止事件 → 发 SSE `error`（`stream.py:279-288`）。
- 上游撕流 / idle / deadline / 缓冲超限 → **不发任何错误帧**，异常上抛截断连接，只进服务端日志（`pipeline_app.py:590-591`）。

人写文档要求这两种都走同一个裁决点，所以后者现在连「有机会合成工具调用」都做不到。归 D 组。

### 6. 流式与非流式对同一事实给出不同答案

非 `max_output_tokens` 的 `incomplete_details.reason`：流式路径读进局部变量后**不写任何地方**；非流式路径（`translation_driver/responses.py:114-130`）会记进 `conversion.losses` → `handler.py:425-426`。流式那条还违反 `../../anthropic-responses-bridge/spec.md:264-265`。归 C 组。

### 7. 孤儿件与死配置项的处置

`decide_stream_ending()` 之外，还有 5 组零生产调用点的件与 4 个无人读取的配置项：`RetryBudget`、`buffered_retry.py`、`delayed_commit.py`、`continuation.*`、`streamReplay.max_retries`、`max_tokens_as_retryable`、`hedge`。

**用户 2026-08-21 裁决：只删代理内续写机制，其他未接线的功能不要动。** 所以除 `continuation.*` 外一律保留。其中 `delayed_commit.py` 的形状恰好对得上第 2 条将来可能需要的延迟提交，`streamReplay.max_retries`（默认 100）在 D 组接线后会生效。

## 明确不做

- **发真实请求向上游补证。** 用户 2026-08-21 明确禁止：只查历史，历史没有就保持悬念。调查报告里那条「最低成本补证是发个超长 prompt 触发 400」的建议**不采纳**。
- **代理内续写。** 已裁决放弃，见 `archive-proxy-side-continuation/`。
- **MCP-driven 续写的次数上限。** 已裁决不设，理由在 `status.md`。
- **为非 anthropic-messages 客户端合成工具调用。** 用户接受当前只支持这一种；将来用上别的 harness 再补。这是范围边界，不是遗漏。

## 方法学警告（给后来查 history 的人）

`from_history.py` 的「只取变换图的根」判据，在 **2026-07-17 19:41 之前的 366 个 operation 上恒真失效**——那批完全没有 transform 记录，代理自造帧与上游帧无法区分。涉及那段时间窗的样本必须标注这个限制，否则会把代理改写过的帧当成上游事实。
