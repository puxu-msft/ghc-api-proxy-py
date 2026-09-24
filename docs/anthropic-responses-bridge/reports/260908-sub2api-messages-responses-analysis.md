# sub2api：Messages 入站到 Responses 上游的桥接分析

## 结论

**可行，且 sub2api 已实现该完整路径。** 对适用的 OpenAI-compatible 账号，`POST /v1/messages` 经 `OpenAIGatewayService.ForwardAsAnthropic()` 直接把 Anthropic Messages 请求转换为 OpenAI Responses 请求，上游消费 Responses SSE 后再转换为 Anthropic JSON 或 Anthropic SSE。实现不是经 `/v1/chat/completions` 的必经中转。

入口与主转换调用见参考项目 `backend/internal/service/openai_gateway_messages.go:24-136`：解析 `apicompat.AnthropicRequest` 后调用 `apicompat.AnthropicToResponses()`，并强制 `responsesReq.Stream = true`。`backend/internal/service/openai_gateway_forward.go:1343-1383` 负责将普通 OpenAI API Key 请求发送到 `/v1/responses`。

这项判断足以作为本项目现有 Anthropic Messages → OpenAI Responses bridge 的外部实现佐证，但不能把 sub2api 的字段取舍直接视为本项目合同。本项目唯一行为 oracle 仍是同主题的 [`../spec.md`](../spec.md)。

## 请求侧转换

`backend/internal/pkg/apicompat/anthropic_to_responses.go:9-69` 构造 Responses 请求，默认包含：

- `model` 与 JSON 编码的 `input`；
- `store: false`、`parallel_tool_calls: true`、`include: ["reasoning.encrypted_content"]`；
- `text.verbosity: "medium"` 和 `reasoning.summary: "auto"`；
- `max_tokens` 到 `max_output_tokens` 的转换，最小值被钳制为 `128`；
- 对非 `gpt-5*` 模型才发送 `temperature` 与 `top_p`。

主要语义映射由同文件以下区段实现：

| Anthropic 内容 | Responses 内容 | 证据 |
|---|---|---|
| `system` 字符串或 text block | `developer` message 的 `input_text` | `116-175` |
| user text | `user` message 的 `input_text` | `190-254` |
| base64 image | data URI `input_image` | `229-243`、`352-363` |
| `tool_result` | `function_call_output` | `204-224` |
| assistant text | `assistant` message 的 `output_text` | `257-308` |
| `tool_use` | `function_call` | `311-330` |
| 带有效 signature 的历史 `thinking` | `reasoning.encrypted_content` | `281-299` |

工具定义由 `convertAnthropicToolsToResponses()` 转为 Responses `function`，以 `strict: false` 表达，并把 `web_search*` 转为原生 `web_search`；`tool_choice.any` 转为 `required`，指定工具转为指定的 `function`。见 `anthropic_to_responses.go:83-113`、`442-506`。

## 回包与流式策略

虽然客户端的原始 `stream` 偏好会被保存，sub2api 始终请求流式 Responses 上游。客户端要求非流式时，它读取并缓冲终止的 Responses SSE，再用 `ResponsesToAnthropic()` 返回 Anthropic JSON；客户端要求流式时，则以 `ResponsesEventToAnthropicEvents()` 的状态机逐事件渲染 Anthropic SSE。证据分别为：

- 强制上游流式：`backend/internal/service/openai_gateway_messages.go:63-72`、`127-136`；
- 非流式回转：`backend/internal/service/openai_gateway_messages.go:560-649` 与 `backend/internal/pkg/apicompat/responses_to_anthropic.go:14-95`；
- 流式状态机：`backend/internal/pkg/apicompat/responses_to_anthropic.go:211-293`、`332-710`。

Responses `reasoning`、`output_text`、`function_call` 和 `web_search_call` 分别可回转为 Anthropic `thinking`、`text`、`tool_use` 和服务器工具块。终态将 `max_output_tokens` 不完整原因映射为 `max_tokens`，有工具调用的正常完成映射为 `tool_use`，其余映射为 `end_turn`，见 `responses_to_anthropic.go:121-145`。

## 条件旁路与有损边界

这不是对任何账号无条件生效的路由：原生 Anthropic 或 adaptive-Anthropic 账号会原协议直通；固定或探测为不支持 Responses 的账号会改走 Chat Completions。两项分流均发生在直接转换前，见 `backend/internal/service/openai_gateway_messages.go:46-59` 与 `backend/internal/service/openai_gateway_forward.go:1324-1341`。

sub2api 的 converter 还明确包含若干不可照搬的语义取舍：

- `thinking.type`、`budget_tokens` 不直接控制 Responses reasoning；默认 `effort` 为 `medium`，只读取 `output_config.effort`，并把 `max` 转为 `xhigh`，见 `anthropic_to_responses.go:58-69`。
- 历史 thinking 仅保留有效 provider signature，不转送可见 thinking 文本；assistant 内容还会归并 text 并将 reasoning、text、tool call 重排序，见 `anthropic_to_responses.go:257-330`。
- `stop_sequences`、`document`、`redacted_thinking` 和 `tool_result.is_error` 没有对应映射分支，见 `anthropic_to_responses.go:229-243` 与 `backend/internal/pkg/apicompat/types.go:16-35`、`78-81`。
- `cache_control` 不维持逐 block 的 Anthropic 缓存语义；服务层最多从请求派生稳定的 `prompt_cache_key`，见 `backend/internal/service/openai_gateway_messages.go:94-108`。
- web search 回转只产生空的 `web_search_tool_result`，因为该实现认为上游没有逐条结果可映射，见 `responses_to_anthropic.go:62-80`。

## 实现可信度

转换层测试覆盖文本、system、tools、thinking/signature、图片、tool result、tool choice、usage、不完整终态和 SSE 生命周期，位于 `backend/internal/pkg/apicompat/anthropic_responses_test.go:15-1501` 与 `backend/internal/pkg/apicompat/anthropic_to_responses_stream_test.go`。服务层还覆盖 Responses 正常路径、Chat Completions fallback 和原生 Anthropic 直通，见 `backend/internal/service/openai_gateway_messages_chat_fallback_test.go:130-164`、`433-479` 与 `backend/internal/service/openai_gateway_messages_anthropic_native_test.go:194-213`。

以上是**足以指导比较与借鉴的强证据**：核心路径、映射与测试在一手源码中一致。它不证明特定第三方 Responses 提供商接受全部载荷字段；该兼容性仍应由本项目的目标 upstream 实测决定。
