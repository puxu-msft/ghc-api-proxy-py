# 转换系统

## 概述

转换系统（`transform/`）负责请求和响应在代理内部的所有变换处理，包含四个子模块：

- **模型解析器**（model_resolver）：模型名称标准化与别名映射
- **格式翻译器**（translator）：Anthropic ↔ OpenAI 双向格式转换
- **消息清洗器**（sanitizer）：消息结构修复与清理
- **系统提示词处理器**（system_prompt）：系统提示词定制

## 模型解析器 (model_resolver.py)

### 解析流程

```
用户输入模型名
    │
    ▼
[1. 精确匹配] 在可用模型列表中直接查找
    │ 匹配 → 返回
    │ 不匹配 ↓
    ▼
[2. 别名映射] 查找配置中的别名表
    │ 匹配 → 返回映射后的模型
    │ 不匹配 ↓
    ▼
[3. 破折号标准化] 将 "-" 分隔的版本号转为 "."
    │ 如 "claude-opus-4-6" → "claude-opus-4.6"
    │ 匹配 → 返回
    │ 不匹配 ↓
    ▼
[4. 日期后缀剥离] 移除 YYYYMMDD 后缀
    │ 如 "claude-sonnet-4-5-20250514" → "claude-sonnet-4-5" → 再标准化
    │ 匹配 → 返回
    │ 不匹配 ↓
    ▼
[5. 优先级列表] 对短名匹配优先级列表中的第一个可用模型
    │ 如 "opus" → 按顺序尝试 ["claude-opus-4.6", "claude-opus-4.5", ...]
    │ 匹配 → 返回第一个可用的
    │ 不匹配 ↓
    ▼
[6. 透传] 原样传递，让上游判断
```

### 别名配置

```yaml
model_mappings:
  aliases:
    opus: claude-opus-4.6
    sonnet: claude-sonnet-4.5
    haiku: claude-haiku-4.5

  preferences:
    opus:
      - claude-opus-4.6
      - claude-opus-4.5
    sonnet:
      - claude-sonnet-4.5
      - claude-sonnet-4
    haiku:
      - claude-haiku-4.5
```

### 接口

```python
class ModelResolver:
    def __init__(self, mappings: ModelMappingsConfig, available_models: list[ModelInfo]):
        ...

    def resolve(self, model: str) -> str:
        """解析模型名称，返回标准化后的模型 ID。"""
        ...

    def is_available(self, model: str) -> bool:
        """检查模型是否在可用列表中。"""
        ...

    def get_model_info(self, model: str) -> ModelInfo | None:
        """获取模型详细信息。"""
        ...
```

## 格式翻译器 (translator.py)

### Anthropic → OpenAI 翻译

将 Anthropic Messages 格式的请求转换为 OpenAI Chat Completions 格式。

#### 消息转换规则

| Anthropic | OpenAI |
|-----------|--------|
| `system` (顶级字段) | `messages[0]` with `role: "system"` |
| `role: "user"` | `role: "user"` |
| `role: "assistant"` | `role: "assistant"` |
| content block `type: "text"` | `content: "text"` (简化为字符串) |
| content block `type: "tool_use"` | `tool_calls: [{type: "function", function: {name, arguments}}]` |
| content block `type: "tool_result"` | 独立消息 `role: "tool"`, `tool_call_id`, `content` |
| content block `type: "thinking"` | 移除（OpenAI 不支持） |

#### 工具定义转换

```
Anthropic:                          OpenAI:
{                                   {
  "name": "search",                   "type": "function",
  "description": "Search...",         "function": {
  "input_schema": {                     "name": "search",
    "type": "object",                   "description": "Search...",
    "properties": {...}                 "parameters": {
  }                                       "type": "object",
}                                         "properties": {...}
                                        }
                                      }
                                    }
```

#### tool_choice 转换

| Anthropic | OpenAI |
|-----------|--------|
| `{"type": "auto"}` | `"auto"` |
| `{"type": "any"}` | `"required"` |
| `{"type": "tool", "name": "X"}` | `{"type": "function", "function": {"name": "X"}}` |
| `{"type": "none"}` | `"none"` |

#### 工具名称截断

OpenAI 限制工具名称最长 64 字符。超长名称处理：

```
1. 截断为 64 字符
2. 记录原始名称 → 截断名称的映射
3. 在响应翻译时恢复原始名称
```

#### 其他字段映射

| Anthropic | OpenAI |
|-----------|--------|
| `max_tokens` | `max_tokens` |
| `temperature` | `temperature` |
| `top_p` | `top_p` |
| `stream` | `stream` |
| `thinking.type: "enabled"` | 不映射（OpenAI 无等价物），thinking 内容在翻译时移除 |
| `thinking.type: "adaptive"` | 不映射（OpenAI 无等价物），thinking 内容在翻译时移除 |
| `thinking.budget_tokens` | 不映射 |

### OpenAI → Anthropic 翻译

将 OpenAI 格式的响应转换回 Anthropic 格式。

#### 响应转换规则

```
OpenAI Response:                    Anthropic Response:
{                                   {
  "choices": [{                       "content": [
    "message": {                        {"type": "text", "text": "..."}
      "content": "...",               ],
      "tool_calls": [...]            "stop_reason": "end_turn",
    },                               "usage": {
    "finish_reason": "stop"            "input_tokens": ...,
  }],                                  "output_tokens": ...
  "usage": {                         }
    "prompt_tokens": ...,           }
    "completion_tokens": ...
  }
}
```

#### finish_reason 映射

| OpenAI | Anthropic |
|--------|-----------|
| `stop` | `end_turn` |
| `length` | `max_tokens` |
| `tool_calls` | `tool_use` |
| `content_filter` | `end_turn` |

#### tool_calls 转换

```
OpenAI tool_calls:                  Anthropic content blocks:
[{                                  [{
  "id": "call_xxx",                   "type": "tool_use",
  "type": "function",                 "id": "call_xxx",
  "function": {                       "name": "search",
    "name": "search",                 "input": {"query": "..."}
    "arguments": "{\"query\":\"...\"}"  }]
  }
}]
```

注意：OpenAI 的 `arguments` 是 JSON 字符串，需要 `json.loads()` 解析为 Anthropic 的 `input` 字典。

### 翻译接口

```python
def translate_anthropic_to_openai(
    payload: dict,
    endpoint: str = "/chat/completions",
) -> tuple[dict, TranslationContext]:
    """
    Anthropic 请求 → OpenAI 请求。
    返回翻译后的 payload 和翻译上下文（含工具名称映射等）。
    """
    ...

def translate_openai_response_to_anthropic(
    response: dict,
    translation_ctx: TranslationContext,
) -> dict:
    """OpenAI 响应 → Anthropic 响应。"""
    ...

@dataclass
class TranslationContext:
    tool_name_mapping: dict[str, str]  # 截断名 → 原始名
    original_model: str
    had_thinking: bool
```

## 消息清洗器 (sanitizer.py)

### 清洗规则

按以下顺序执行：

#### 1. 孤立 tool 块检测与移除

检查 tool_use 和 tool_result 的 1:1 配对关系：

```
扫描所有消息：
    收集所有 tool_use 的 id
    收集所有 tool_result 的 tool_use_id

    孤立 tool_use = id 不在 tool_result 集合中
    孤立 tool_result = tool_use_id 不在 tool_use 集合中

    移除所有孤立块
```

特殊情况：
- `server_tool_use` 和对应的 `{name}_tool_result` 不视为孤立块（它们是内联的）
- 最后一条 assistant 消息中的 tool_use 允许没有对应的 tool_result（正在等待执行）

#### 2. 空内容块移除

```
对每条消息的 content 数组：
    移除 {"type": "text", "text": ""} 空文本块
    移除 {"type": "text", "text": null} 空文本块
    如果 content 数组变空且非最后一条消息，移除整条消息
```

#### 3. system-reminder 标签清理

```
对每个 text 类型的 content block：
    使用正则移除 <system-reminder>...</system-reminder> 标签
    包括嵌套的和多行的
```

#### 4. 工具名称大小写修复

```
收集 tools 定义中的名称集合
对所有 tool_use 块：
    如果 name 不在定义集合中，但忽略大小写后能匹配
    → 修复为定义中的正确大小写
```

#### 5. 双重序列化修复

```
对所有 tool_use 块的 input 字段：
    如果 input 是字符串而非字典
    → 尝试 json.loads() 反序列化
    → 成功则替换为字典
```

### 接口

```python
class MessageSanitizer:
    def sanitize(
        self,
        payload: dict,
        endpoint: Literal["openai-chat-completions", "openai-responses", "anthropic-messages"],
    ) -> tuple[dict, SanitizationResult]:
        """
        清洗请求 payload。
        返回修改后的 payload 和清洗结果统计。
        """
        ...

@dataclass
class SanitizationResult:
    orphaned_blocks_removed: int
    empty_blocks_removed: int
    system_tags_stripped: int
    tool_names_fixed: int
    double_serialized_fixed: int
```

## 系统提示词处理器 (system_prompt.py)

### 处理流程

```
原始系统提示词
    │
    ▼
[1. Override 规则] 应用替换规则（按顺序）
    │
    ▼
[2. Prepend] 在前面插入文本
    │
    ▼
[3. Append] 在后面追加文本
    │
    ▼
处理后的系统提示词
```

### Override 规则

支持两种匹配方式：

#### 行匹配 (line)

精确匹配完整行并替换：

```yaml
system_prompt_overrides:
  - from: "You are a helpful assistant."
    to: "You are an expert coding assistant."
    method: line
```

#### 正则匹配 (regex)

正则表达式匹配并替换，支持捕获组：

```yaml
system_prompt_overrides:
  - from: "temperature:\\s*(\\d+\\.?\\d*)"
    to: "temperature: 0.3"
    method: regex
  - from: "(You must follow these rules:).*?(End of rules)"
    to: "\\1 Custom rules here. \\2"
    method: regex
```

### Prepend/Append

```yaml
system_prompt_prepend: |
  <custom_context>
  You are operating in a controlled environment.
  All actions are logged and audited.
  </custom_context>

system_prompt_append: |
  Remember to follow the organization's coding standards.
```

### 接口

```python
class SystemPromptProcessor:
    def __init__(self, settings: AppSettings):
        self._prepend = settings.system_prompt_prepend
        self._append = settings.system_prompt_append
        self._overrides = settings.system_prompt_overrides

    def process(self, system_prompt: str | None) -> str | None:
        """处理系统提示词，应用所有规则。"""
        if system_prompt is None:
            if not self._prepend and not self._append:
                return None
            system_prompt = ""

        # 应用 override 规则
        for rule in self._overrides:
            if rule.method == "line":
                system_prompt = self._apply_line_override(system_prompt, rule)
            elif rule.method == "regex":
                system_prompt = self._apply_regex_override(system_prompt, rule)

        # Prepend 和 Append
        parts = []
        if self._prepend:
            parts.append(self._prepend)
        parts.append(system_prompt)
        if self._append:
            parts.append(self._append)

        return "\n\n".join(parts)
```

### Anthropic vs OpenAI Chat Completions vs Responses 系统提示词位置

- **Anthropic**：`system` 是顶级字段（字符串或 content block 数组）
- **OpenAI Chat Completions**：`system` 是 messages 数组的第一条消息（`role: "system"`）
- **OpenAI Responses**：`instructions` 是顶级字段（字符串）

处理器在路由层应用，格式翻译之前。针对不同格式提取和回写系统提示词：

```python
# Anthropic 格式
system = payload.get("system", "")
processed = processor.process(system)
payload["system"] = processed

# OpenAI Chat Completions 格式
system_msg = next((m for m in payload["messages"] if m["role"] == "system"), None)
if system_msg:
    processed = processor.process(system_msg["content"])
    system_msg["content"] = processed

# OpenAI Responses 格式
instructions = payload.get("instructions", "")
processed = processor.process(instructions)
payload["instructions"] = processed
```

## Responses API 翻译

### Responses ↔ Chat Completions 翻译

同为 OpenAI 生态的两种格式，字段之间有清晰的映射关系。

#### 请求翻译：Responses → Chat Completions

| Responses 字段 | Chat Completions 字段 | 转换规则 |
|----------------|----------------------|----------|
| `input` | `messages` | 遍历 input items 转换（见下表） |
| `instructions` | `messages[0]` (role: system) | 插入为首条 system 消息 |
| `max_output_tokens` | `max_tokens` | 直接映射 |
| `temperature` | `temperature` | 直接映射 |
| `top_p` | `top_p` | 直接映射 |
| `tools` (type: function) | `tools` | 复用 function 定义 |
| `tools` (type: web_search 等) | 不映射 | 内置工具 Chat Completions 不支持，跳过 |
| `tool_choice` | `tool_choice` | 直接映射 |
| `stream` | `stream` | 直接映射 |
| `previous_response_id` | 不映射 | 无状态，需展开为完整消息 |
| `store` | 不映射 | Chat Completions 无此概念 |
| `truncation` | 不映射 | 需由代理自行实现 |
| `reasoning` | 不映射 | Chat Completions 不支持 |

#### Input 条目转换：Responses → Chat Completions

| Responses Input Item | Chat Completions Message |
|----------------------|--------------------------|
| `{role: "user", content: "..."}` | `{role: "user", content: "..."}` |
| `{role: "assistant", content: [...]}` | `{role: "assistant", content: "..."}` + `tool_calls: [...]` |
| `{role: "system", content: "..."}` | `{role: "system", content: "..."}` |
| `{role: "developer", content: "..."}` | `{role: "system", content: "..."}` |
| content: `input_text` | content: `text` (或直接字符串) |
| content: `input_image` | content: `image_url` |
| `{type: "function_call_output", call_id, output}` | `{role: "tool", tool_call_id: call_id, content: output}` |

#### 响应翻译：Chat Completions → Responses

| Chat Completions Response | Responses Response |
|---------------------------|---------------------|
| `choices[0].message.content` | `output[0].content[0] = {type: "output_text", text}` |
| `choices[0].message.tool_calls` | 多个 `{type: "function_call", call_id, name, arguments}` output items |
| `choices[0].finish_reason: "stop"` | `status: "completed"` |
| `choices[0].finish_reason: "length"` | `status: "incomplete"` |
| `choices[0].finish_reason: "tool_calls"` | `status: "completed"`（output 含 function_call items） |
| `usage.prompt_tokens` | `usage.input_tokens` |
| `usage.completion_tokens` | `usage.output_tokens` |

### Responses ↔ Anthropic 翻译

跨供应商格式翻译，两种 API 在概念上有较多对应关系。

#### 请求翻译：Responses → Anthropic

| Responses 字段 | Anthropic 字段 | 转换规则 |
|----------------|---------------|----------|
| `input` (user/assistant) | `messages` | 角色和内容块格式转换 |
| `instructions` | `system` | 直接映射 |
| `input` (developer role) | `system` | 合并到 system 字段 |
| `max_output_tokens` | `max_tokens` | 直接映射 |
| `temperature` | `temperature` | 直接映射 |
| `tools` (function) | `tools` | function → Anthropic tool 格式 |
| `tool_choice` | `tool_choice` | 格式转换（同 Chat→Anthropic） |
| `reasoning.effort` | `thinking` | effort → thinking 模式映射（见下方） |
| `previous_response_id` | 不映射 | 需展开为完整消息 |

#### Reasoning → Thinking 模式映射

| 条件 | 翻译结果 |
|------|---------|
| 模型支持 `adaptive_thinking` | `{"thinking": {"type": "adaptive"}}` |
| 模型支持 `thinking` + effort 指定 | `{"thinking": {"type": "enabled", "budget_tokens": N}}`，N 根据 effort 和模型限制估算 |
| 模型不支持 thinking | 忽略 reasoning 字段 |

#### Input 条目转换：Responses → Anthropic

| Responses | Anthropic |
|-----------|-----------|
| content: `input_text` | content block: `{type: "text", text}` |
| content: `input_image` | content block: `{type: "image", source: {type: "url", url}}` |
| `function_call_output` | `{role: "user", content: [{type: "tool_result", tool_use_id, content}]}` |

#### 响应翻译：Anthropic → Responses

| Anthropic Response | Responses Response |
|--------------------|--------------------|
| `content[i].type: "text"` | `output[0].content[i] = {type: "output_text", text}` |
| `content[i].type: "tool_use"` | `output[i+1] = {type: "function_call", call_id: id, name, arguments}` |
| `content[i].type: "thinking"` | `output[0] = {type: "reasoning", summary: [{type: "summary_text", text}]}` |
| `stop_reason: "end_turn"` | `status: "completed"` |
| `stop_reason: "max_tokens"` | `status: "incomplete"` |
| `stop_reason: "tool_use"` | `status: "completed"`（output 含 function_call items） |
| `usage.input_tokens` | `usage.input_tokens` |
| `usage.output_tokens` | `usage.output_tokens` |

### 翻译接口扩展

```python
def translate_responses_to_chat(
    payload: dict,
) -> tuple[dict, TranslationContext]:
    """Responses 请求 → Chat Completions 请求。"""
    ...

def translate_chat_response_to_responses(
    response: dict,
    translation_ctx: TranslationContext,
) -> dict:
    """Chat Completions 响应 → Responses 响应。"""
    ...

def translate_responses_to_anthropic(
    payload: dict,
) -> tuple[dict, TranslationContext]:
    """Responses 请求 → Anthropic 请求。"""
    ...

def translate_anthropic_response_to_responses(
    response: dict,
    translation_ctx: TranslationContext,
) -> dict:
    """Anthropic 响应 → Responses 响应。"""
    ...
```

### previous_response_id 处理

Responses API 的 `previous_response_id` 实现了服务端会话状态。翻译到无状态格式时：

1. 如果上游支持 `/responses` 端点，直接透传 `previous_response_id`
2. 如果需要翻译到 Chat Completions 或 Anthropic，**必须**从历史存储中查找之前的请求/响应，展开为完整的 messages 数组
3. 如果历史中找不到对应的 response_id，返回错误

## 相关文档

- [整体架构概览](architecture.md)
- [请求执行管道](request-pipeline.md)
- [流式处理](streaming.md)（流式翻译）
- [核心数据模型](data-models.md)（Pydantic 模型定义）
- [配置系统](config-system.md)（提示词和映射配置）
