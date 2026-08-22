# 模型与响应的消息格式的翻译

采用“输入格式 <-> 中间表示 <-> 上游模型格式”的方式。

提供 `translation_driver`，用于在“输入格式 <-> 中间表示 <-> 上游模型格式”之间做转换。每个受支持的翻译格式都可以注册为翻译器（translator），如 `inbound.from-anthropic-messages`、`outbound.to-anthropic-messages`、`inbound.from-openai-responses`、`outbound.to-openai-responses` 等。不要求能力等价，尽可能提供翻译能力，在没有唯一的翻译路径之处提供配置选项。

## anthropic-messages <-> openai-responses

### 如何提供系统提示词？

anthropic-messages 通过顶层的 `system` 字段，形如：

```json
{
  "system": [
    {
      "type": "text",
      "text": "You are Claude Code, Anthropic's official CLI for Claude.",
      "cache_control": {
        "type": "ephemeral"
      }
    },
    {
      "type": "text",
      "text": "\nYou are an interactive agent that helps users with software engineering tasks.\n\n...\n\nDo not call the AgentTool unless the user requested it\nDo not use workflows or deep-research unless the user requested it",
      "cache_control": {
        "type": "ephemeral"
      }
    }
  ]
}
```

openai-responses 通过顶层的 `instructions` 字段，形如：

```json
{
    "instructions": [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": "You are Claude Code, Anthropic's official CLI for Claude.",
                    "cache_control": {
                        "type": "ephemeral"
                    }
                },
                {
                    "type": "text",
                    "text": "\nYou are an interactive agent that helps users with software engineering tasks.\n\n...\n\nDo not call the AgentTool unless the user requested it\nDo not use workflows or deep-research unless the user requested it",
                    "cache_control": {
                        "type": "ephemeral"
                    }
                }
            ]
        }
    ]
}
```

可见 `instructions` 具有更丰富的语义，只是目前我们用不到这层灵活性。

### 如何转换对话？

anthropic-messages 的对话位于顶层的 `messages` 字段，形如：

```json
{
    "messages": [
        {
            "id": "msg_1",
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Hello, Claude!"
                }
            ]
        },
        {
            "id": "msg_2",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Hello! How can I assist you today?"
                }
            ]
        }
    ]
}
```