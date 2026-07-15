# 消息清洗管道

## 概述

消息清洗分为两个阶段（`anthropic/sanitize.py`），确保发送到 Anthropic API 的消息符合协议要求。

**Python 优化**：JS 版本的清洗函数直接操作 JavaScript 对象。Python 版本使用 Pydantic 模型进行结构化验证，清洗结果通过 `SanitizationResult` dataclass 记录统计。

> **本文档不重复描述 thinking 块相关清洗逻辑**——块级保护（`thinking_block_message_policy`）、空块清洗、去堆叠（destack）、L2/L3 剥离与隔离，均已迁出并详述于 [thinking-pipeline.md](thinking-pipeline.md)（新增文档）。本文档只在集成点处引用它。旧版本文档中出现过的 `immutable_thinking`（消息级布尔开关）已确认过时，**不再采用**——参见 thinking-pipeline.md 的「背景」章节说明。

## 两阶段设计

### Phase 1: 预处理（`preprocess_anthropic_messages`）

一次性幂等操作，在请求进入 routing/retry pipeline 前执行**一次**。Auto-truncate 重试后**不需要**重新执行，因为截断不会引入新的重复或新的 system-reminder 标签。

| 步骤 | 操作 | 控制项 | 默认 |
|------|------|--------|------|
| 1 | `strip_read_tool_result_tags` — 剥离 Read 工具结果中所有注入的 `<system-reminder>` 标签 | `anthropic.tool_strip_read_result_tags` | 关闭 |
| 2 | `deduplicate_tool_calls` — 去重重复的 tool_use/tool_result 对，保留最后出现的 | `anthropic.tool_dedup_calls` | 关闭 |

> **配置键更名**（相对旧文档）：`strip_read_tool_result_tags` → **`tool_strip_read_result_tags`**；`dedup_tool_calls` → **`tool_dedup_calls`**。语义不变，仅统一到 `tool_*` 命名前缀下，与 `tool_search`、`tool_inject_claude_code` 等同族配置项风格一致（详见 [tool-use.md](tool-use.md)）。

### Phase 2: 可重复清洗（`sanitize_anthropic_messages`）

每次 auto-truncate 重试后**必须重新执行**，因为截断可能打破 tool_use/tool_result 配对并产生空块。

| 步骤 | 操作 | 控制项 | 默认 |
|------|------|--------|------|
| 1 | `sanitize_system_prompt` — 清理 system prompt 中的 `<system-reminder>` 标签 | 始终执行 | - |
| 2 | `sanitize_inline_system_messages` — 处理消息数组中混入的 `role: "system"` 消息 | `anthropic.system_default_mode` / `anthropic.system_reject_mode` | 见下节 |
| 3 | `remove_system_reminders` — 重写/移除消息中的 `<system-reminder>` 标签 | `anthropic.system_rewrite_reminders` | 保留 |
| 4 | `process_tool_blocks` — 修复 tool name 大小写 + 过滤孤儿 tool_use/tool_result 块 | 始终执行 | - |
| 5 | `filter_empty_text_blocks` — 安全网：移除任何来源产生的空 text 块 | 始终执行 | - |

> **配置键更名**：`rewrite_system_reminders` → **`system_rewrite_reminders`**（归入 `system_*` 命名族，与新增的 `system_default_mode` / `system_reject_mode` / `system_reject_models` 并列，见下节）。

### 执行时机

```
请求进入
    │
    ▼
[Phase 1: 预处理] ← 仅执行一次
    │
    ▼
[路由决策 + 请求准备]
    │   （含 anthropic/thinking/ 管道：L3 隔离剥离 → 空块清洗 → destack，见 thinking-pipeline.md）
    │
    ├─────────────────────────────────┐
    │                                 │
    ▼                                 │
[Phase 2: 可重复清洗] ← 每次执行      │
    │                                 │
    ▼                                 │
[发送到上游]                           │
    │                                 │
    ├─ 成功 → 完成                     │
    │                                 │
    └─ 限制错误 → Auto-truncate       │
         │                            │
         ▼                            │
    [截断 payload]                     │
         │                            │
         └────────────────────────────┘
         ↑ 重新执行 Phase 2（不重复 Phase 1）
```

## Tool Blocks 处理

`process_tool_blocks()` 是清洗管道中最关键的步骤，确保 Anthropic API 的 tool 配对要求被满足。

### 职责

1. **保留所有配对完整的 tool_use/tool_result** — 不管工具是否在当前 `tools` 数组中
2. **只过滤孤立的块** — 没有 `tool_result` 的 `tool_use`，没有 `tool_use` 的 `tool_result`
3. **修正工具名大小写** — 如果工具在 `tools` 数组中但大小写不同，修正为正确的大小写

### 配对检查算法

```python
def process_tool_blocks(messages: list[dict], tools: list[dict]) -> ProcessResult:
    """处理 tool blocks：配对检查、孤儿过滤、name 修正。"""

    # 1. 收集所有 tool_use id → name 映射
    tool_use_ids: dict[str, str] = {}
    for msg in messages:
        if msg["role"] == "assistant":
            for block in msg.get("content", []):
                if block.get("type") == "tool_use":
                    tool_use_ids[block["id"]] = block["name"]

    # 2. 收集所有 tool_result 的 tool_use_id
    tool_result_ids: set[str] = set()
    for msg in messages:
        if msg["role"] == "user":
            for block in msg.get("content", []):
                if block.get("type") == "tool_result":
                    tool_result_ids.add(block["tool_use_id"])

    # 3. 识别孤儿
    orphan_tool_uses = set(tool_use_ids.keys()) - tool_result_ids
    orphan_tool_results = tool_result_ids - set(tool_use_ids.keys())

    # 4. 过滤孤立块
    cleaned = filter_orphans(messages, orphan_tool_uses, orphan_tool_results)

    # 5. 修正工具名大小写
    cleaned = fix_tool_name_casing(cleaned, tools)

    return ProcessResult(
        messages=cleaned,
        orphaned_tool_uses=len(orphan_tool_uses),
        orphaned_tool_results=len(orphan_tool_results),
    )
```

> **与 thinking 块保护的交互**：过滤孤儿块属于「块内部」操作，不触及 thinking 块本身，因此不受 [thinking-pipeline.md](thinking-pipeline.md) 的 `thinking_block_message_policy` 约束——即便某条 assistant 消息同时含有 thinking 块与孤儿 tool_use 块，孤儿 tool_use 仍可被正常清理，只要 thinking 块本身保持逐字、顺序、不丢弃。

### 孤儿产生的常见场景

| 场景 | 说明 |
|------|------|
| 中断的 tool call | 流式传输中断，assistant 生成了 `tool_use` 但 client 没发送 `tool_result` |
| Auto-truncate | 截断消息后 tool_use 和 tool_result 分布在不同侧 |
| 会话续接 | 历史记录不完整，缺少配对 |
| 客户端错误 | 客户端发送了格式不正确的消息 |

## System 消息处理

Anthropic Messages API **不接受**消息数组中出现 `role: "system"`——会被拒绝为 `Unexpected role "system"`；system 提示词只能通过顶层 `system` 参数传递。但一些习惯 OpenAI 风格的客户端、或 Claude Code 在对话中途注入的上下文（hook 输出、规则提醒等）可能会产生内联的 `role: "system"` 消息。`sanitize_inline_system_messages()` 负责按配置把这些内联 system 消息转换为合法形态或丢弃。

### 全局默认模式（`system_default_mode`）

| 配置项 | 取值 | 默认 | 说明 |
|--------|------|------|------|
| `anthropic.system_default_mode` | `false` / `drop_invalid` / `merge` / `as_user` / `as_assistant` | `false` | 对**不在** `system_reject_models` 中的模型生效的处理模式 |

| 值 | 行为 |
|----|------|
| `false`（默认） | 不处理，内联 `role: "system"` 消息原样透传（交由上游拒绝或容忍，取决于模型） |
| `drop_invalid` | 直接从消息数组中移除所有 `role: "system"` 消息 |
| `merge` | 提取内联 system 消息的纯文本内容，追加合并进顶层 `system` 参数，原消息位置移除。非文本块（图片等）会被丢弃并记录警告（顶层 `system` 只能是纯文本） |
| `as_user` | 把 `role: "system"` 改写为 `role: "user"`，空内容消息直接丢弃（避免发送空内容消息触发上游 400），随后与相邻同角色消息合并 |
| `as_assistant` | 同 `as_user`，但改写为 `role: "assistant"`；若转换后消息位于数组开头（Anthropic 要求首条消息必须是 `user` 角色），需丢弃开头非法消息 |

### 拒绝模型专属模式（`system_reject_mode` + `system_reject_models`）

某些模型（实测例如特定账户类型下的 `claude-sonnet-4.6` / `claude-haiku-4.5`）对内联 `role: "system"` 的容忍度与其他模型不同——上游会**主动拒绝**这些模型收到内联 system 消息（不是简单地容忍或忽略），因此需要一套**更激进**的默认处理模式，与全局默认模式区分开：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.system_reject_mode` | `as_user` | 对命中 `system_reject_models` 的模型生效的处理模式（取值范围同 `system_default_mode`） |
| `anthropic.system_reject_models` | `["claude-sonnet-4.6", "claude-haiku-4.5"]` | 已知会拒绝内联 `role: "system"` 的模型名单（子串匹配，规整化后比较） |

### 模式解析优先级

```python
def resolve_system_sanitize_mode(model: str) -> SystemMessagesSanitizeMode:
    """解析某个已解析模型名应使用的内联 system 消息处理模式。

    命中 system_reject_models（含配置项 ∪ feature negotiation 学习到的拒绝记录）
    的模型使用 system_reject_mode；否则回退到 system_default_mode。
    """
    if is_system_reject_model(model):
        return settings.anthropic.system_reject_mode
    return settings.anthropic.system_default_mode


def is_system_reject_model(model: str) -> bool:
    normalized = normalize_for_matching(model)
    if any(normalized.find(normalize_for_matching(m)) != -1 for m in settings.anthropic.system_reject_models):
        return True
    return is_system_reject_model_learned(model)  # feature negotiation 缓存，见 feature-negotiation.md
```

`system_reject_models` 的成员判定是**反应式症状记录**（「这个 outbound 模型拒绝内联 system」），而非对具体上游账户类型/后端实现的断言；配置项与 feature negotiation 学习结果取并集，二者共同决定最终的拒绝名单。

### 幂等性

一旦某轮清洗把所有 `role: "system"` 消息转换/丢弃完毕，消息数组中不再含有该角色，后续重复调用（例如 auto-truncate 触发的 Phase 2 重跑）会在开头检测到「消息数组已无 `role: "system"`」而直接短路返回，不会重复处理。

### 与 thinking 块的交互

`merge` / `as_user` / `as_assistant` 模式在合并相邻同角色消息时，同样遵循 [thinking-pipeline.md](thinking-pipeline.md) 的 `thinking_block_message_policy`——凡是任一侧消息 `should_preserve_thinking_blocks()` 返回真，就不执行合并，改为原样保留两条独立消息。

## System Reminder 处理

### 标签格式

```xml
<system-reminder>
这里是系统注入的提醒内容
</system-reminder>
```

### 处理模式

由 `anthropic.system_rewrite_reminders` 控制：

| 值 | 行为 |
|----|------|
| `false`（默认） | 保留所有 system-reminder 标签不变 |
| `true` | 移除所有 system-reminder 标签 |
| `list[RewriteRule]` | 按规则数组逐条匹配重写 |

### 重写规则

规则数组按顺序评估，首次匹配生效：

```yaml
anthropic:
  system_rewrite_reminders:
    - from: "sensitive keyword"
      to: ""                    # 空字符串 → 移除该标签
      method: line
    - from: "old prompt (\\w+)"
      to: "new prompt \\1"
      method: regex
      model: "opus.*"          # 可选：仅对匹配的模型生效
```

- 如果替换结果与原内容相同 → 保持标签不变
- 如果替换结果为空字符串 → 移除整个标签
- 否则 → 替换标签内容

### Read Tool Result 标签剥离

`tool_strip_read_result_tags` 专门处理 Read 工具结果中的 system-reminder 标签。Claude Code 等客户端在 Read tool 结果中注入大量 system-reminder（CLAUDE.md 内容、hooks 提醒等），这些标签在多轮对话中不断累积，占用大量上下文。

启用后，Phase 1 预处理会遍历所有 `tool_result` 块，移除其中的 `<system-reminder>` 标签。

## Tool Call 去重

由 `anthropic.tool_dedup_calls` 控制，在 Phase 1 中执行。

### 去重模式

| 模式 | 匹配条件 | 说明 |
|------|----------|------|
| `false` | - | 禁用去重 |
| `"input"` | `(tool_name, input)` 相同 | 相同工具+相同输入视为重复，即使结果不同 |
| `"result"` | `(tool_name, input, result)` 相同 | 工具+输入+结果都相同才视为重复 |

### 去重算法

```python
def deduplicate_tool_calls(
    messages: list[dict],
    mode: Literal["input", "result"],
) -> list[dict]:
    """去重重复的 tool_use/tool_result 对，保留最后出现的。"""

    # 从后向前扫描，收集唯一的 tool call 签名
    seen_signatures: set[str] = set()
    keep_ids: set[str] = set()

    for msg in reversed(messages):
        for block in reversed(msg.get("content", [])):
            if block.get("type") == "tool_use":
                sig = compute_signature(block, mode)
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    keep_ids.add(block["id"])

    # 过滤消息：保留 keep_ids 中的 tool_use 及其配对的 tool_result
    return filter_by_ids(messages, keep_ids)
```

去重同样受 `thinking_block_message_policy` 约束：若某条 assistant 消息因 `should_preserve_thinking_blocks()` 为真而被保护，即便它携带的 tool_use 未命中 `keep_ids`，该消息也不会被整体移除（详见 [thinking-pipeline.md](thinking-pipeline.md)）。

## 消息映射

`anthropic/message_mapping.py` 维护原消息与清洗后消息的索引对应关系。当 auto-truncate 需要报告截断了第 N 条原始消息时，需要此映射进行反向查找。

## 清洗结果记录

```python
@dataclass
class SanitizationResult:
    orphaned_tool_uses_removed: int
    orphaned_tool_results_removed: int
    empty_blocks_removed: int
    system_tags_stripped: int
    tool_names_fixed: int
    tool_calls_deduplicated: int
    read_tool_tags_stripped: int
    inline_system_messages_converted: int
```

此结果记录在 `RequestContext` 和 `HistoryEntry` 中，用于审计和调试。

## 相关代码

- `anthropic/sanitize.py` — 2 阶段管道入口
- `anthropic/sanitize/` — 各步骤独立模块（含 `system_messages.py` — 内联 system 消息处理）
- `anthropic/thinking/` — Thinking 块处理管道（保护 / destack / L2 剥离 / L3 隔离，见 [thinking-pipeline.md](thinking-pipeline.md)）
- `anthropic/message_mapping.py` — 消息映射

## 相关文档

- [设计文档总纲](DESIGN.md)
- [Thinking 块处理管道](thinking-pipeline.md)（**新增**——原本内嵌于本文档的 thinking 保护描述已迁出并重新设计）
- [Tool Use 机制](tool-use.md)
- [Anthropic 兼容性](anthropic-compat.md)
- [请求执行管道](request-pipeline.md)
