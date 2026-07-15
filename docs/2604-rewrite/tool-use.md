# Tool Use 机制

## Anthropic API 的两类工具

### 用户定义工具（User-defined tools）

- 客户端在请求的 `tools` 数组中定义（带 `input_schema`）
- Assistant 生成 `tool_use` 块调用工具
- User 返回 `tool_result` 块提供结果
- `tool_use` 在 assistant 消息中，`tool_result` 在 user 消息中

### 服务端工具（Server-side tools）

- Anthropic 后端内置（真正由服务端执行的只有 `web_search`、`web_fetch`、`code_execution` 三类）
- 请求中以 `type: "web_search_20250305"` 形式发送（无 `input_schema`）
- Assistant 生成 `server_tool_use` 块
- 后端执行并在**同一条 assistant 消息**中返回结果（如 `web_search_tool_result`）
- 客户端不参与执行过程

> **概念澄清**：带 `type` 字段**不等于**服务端执行。`memory` / `computer` / `text_editor` / `bash` 这几类同样带 `type` 后缀（如 `memory_20250818`），但它们由**客户端执行**（产出普通 `tool_use` 块 + `caller: {type: "direct"}` 标记），本质上是「内置 client tool」而非「server tool」。判据不是「有没有 type 字段」，而是「Anthropic 是否把这个具体工具划为服务端执行」——目前只有 `web_search_` / `web_fetch_` / `code_execution_` 三个前缀是真·server tool。本项目沿用这一更精确的三分类，`text_editor_` / `computer_` / `bash_` / `memory_` 等前缀虽然共享同一个「API 定义的 typed tool」判定函数（`is_api_defined_tool_type`），但**不应**在日志/文档中被称为「server tool」。

已知的 API 定义 typed tool 前缀（来源：`@anthropic-ai/sdk` + 实测）：

| 前缀 | 执行方 | 说明 |
|------|--------|------|
| `web_search_` | **服务端** | 网页搜索（真·server tool） |
| `web_fetch_` | **服务端** | URL 内容获取（真·server tool） |
| `code_execution_` | **服务端** | 代码沙箱执行（真·server tool） |
| `text_editor_` | 客户端 | 内置文本编辑器（client tool，`caller:{type:"direct"}`） |
| `computer_` | 客户端 | 计算机控制 / Computer Use（client tool） |
| `bash_` | 客户端 | Bash 命令执行（client tool） |
| `memory_` | 客户端 | Memory 工具（client tool，透传声明供上游驱动） |
| `advisor_` / `agent_toolset_` | — | Claude Code 生态相关声明（透传） |
| `tool_search_` | 服务端（Copilot 特有） | 见下节「tool_search 机制」，闭环发生在服务端 |

### Server tool 识别（Duck-typing）

```python
def is_server_tool_use_block(block: dict) -> bool:
    """通过 type 前缀识别 server tool use 块。"""
    return block.get("type") == "server_tool_use"

def is_server_tool_result_block(block: dict) -> bool:
    """通过 type 后缀识别 server tool result 块（排除普通 tool_result）。"""
    block_type = block.get("type", "")
    return block_type.endswith("_tool_result") and block_type != "tool_result"
```

使用 duck-typing 而非硬编码列表，泛化处理所有 `server_tool_use` / `*_tool_result` 对——这两个判定函数只依据**块自身产出的类型标记**（真实 server 执行的产物一定是 `server_tool_use`/`*_tool_result`），与「哪些工具算 server tool」这个更易混淆的概念判断（`is_api_defined_tool_type`）相互独立，不应混用。

## Tool Use/Result 配对要求

**核心原则：Anthropic API 要求 `tool_use` 和 `tool_result` 必须配对存在。**

- 每个 `tool_use` 块必须有对应的 `tool_result` 块（通过 `id` 和 `tool_use_id` 匹配）
- 孤立的 `tool_use`（没有 `tool_result`）会导致 HTTP 400 错误
- 孤立的 `tool_result`（没有 `tool_use`）同样会导致错误
- Server tool 的配对由后端自动处理，不在此约束内

详见 [消息清洗管道](sanitize-pipeline.md) 中的 Tool Blocks 处理。

## CC 官方工具注入（`tool_inject_claude_code`）

### 问题

Claude Code 客户端在多轮会话中，有时会出现**历史消息里的 `tool_use` 块引用了官方内置工具**（如 `Bash`、`Read`），但**当前请求的 `tools` 数组里缺失**该工具声明的情况——上游看到一个「没有匹配声明」的历史 `tool_use` 引用，直接以 400 拒绝整个请求。这不是配对问题（`process_tool_blocks` 处理的是 `tool_use`/`tool_result` 之间的配对），而是「工具引用 vs. 工具声明」的缺失问题。

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.tool_inject_claude_code` | `true` | 是否为缺失的 CC 官方工具注入 stub 声明 |

### CC 官方工具清单（16 个）

```python
CLAUDE_CODE_OFFICIAL_TOOLS = [
    "Task", "TaskOutput", "Bash", "Glob", "Grep", "Read", "Edit", "Write",
    "NotebookEdit", "WebFetch", "TodoWrite", "KillShell", "AskUserQuestion",
    "Skill", "EnterPlanMode", "ExitPlanMode",
]
```

启用时，请求准备阶段会对这 16 个官方工具名逐一做**大小写不敏感**的存在性检查（避免把小写 `read` 误判为缺失而重复注入一个大小写不同的 `Read`），凡是当前 `tools` 数组中不存在（不区分大小写）的，注入一个空 schema 的 stub 声明：

```python
EMPTY_INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}

def inject_claude_code_stubs(tools: list[dict]) -> list[dict]:
    existing_lower = {t["name"].lower() for t in tools}
    stubs = [
        {"name": name, "description": f"Claude Code {name} tool", "input_schema": EMPTY_INPUT_SCHEMA}
        for name in CLAUDE_CODE_OFFICIAL_TOOLS
        if name.lower() not in existing_lower
    ]
    return [*tools, *stubs]
```

**适用范围的取舍**：非 Claude Code 客户端（原生 SDK 调用方、自定义集成）没有理由在每次请求中收到 16 个用不上的 stub 工具——这既浪费 prompt 预算，也可能诱导模型倾向于「工具调用」而非纯问答。因此该注入通过 `anthropic.tool_inject_claude_code` 可关闭。

### 独立机制：任意历史引用工具的 stub 注入

上述 CC 官方工具清单是一个**已知的固定名单**；但历史记录还可能引用**任意** MCP 工具（例如某个 MCP server 提供的自定义工具），这些工具在早前的对话轮次中曾出现在 `tools` 数组，但当前请求未携带（例如客户端更新了工具列表、或该 MCP server 本轮未连接）。这是一个**独立于** CC 官方工具清单的、**始终生效**（不受 `tool_inject_claude_code` 开关影响）的安全网：

```python
def collect_history_tool_names(messages: list[dict]) -> set[str]:
    """收集历史 assistant 消息中出现过的所有 tool_use 名称。"""
    names = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content", []):
            if block.get("type") == "tool_use":
                names.add(block["name"])
    return names

def inject_history_referenced_stubs(tools: list[dict], messages: list[dict]) -> list[dict]:
    """对历史引用但当前 tools 数组缺失的任意工具（含 MCP 工具）注入最小 stub。"""
    history_names = collect_history_tool_names(messages)
    existing_names = {t["name"] for t in tools}
    stubs = [
        {"name": name, "description": "Stub for tool referenced in conversation history", "input_schema": EMPTY_INPUT_SCHEMA}
        for name in history_names
        if name not in existing_names
    ]
    return [*tools, *stubs]
```

两套机制的关系：CC 官方工具清单是**已知名单驱动**（可通过配置关闭，专门服务于 Claude Code 客户端的已知痛点）；历史引用 stub 注入是**名单无关、面向任意工具**的通用安全网（无法关闭，因为它防止的是任何配对完整性以外的、更底层的「引用不存在的声明」400，属于协议正确性范畴而非风格取舍）。二者在同一预处理阶段（早于 [消息清洗管道](sanitize-pipeline.md) 的 `process_tool_blocks`）依次执行，须**先于**清洗——清洗阶段的 `process_tool_blocks` 依赖当前 `tools` 数组来判断 tool_use 引用是否有效，若清洗先跑，会误判尚未被 stub 补齐的历史工具引用为「孤儿」而错误过滤。

## tool_search 机制（Copilot 特有）

`tool_search`（`tool_search_tool_regex`）是 GHC/Copilot 特有的**工具发现**机制，不是标准 Anthropic API。

### 工作原理

当工具列表太长时，代理将不常用的工具标记为 `defer_loading: true`，同时注入一个 `tool_search_tool_regex` 工具。模型可以通过调用此工具来"搜索并加载"需要的 deferred 工具。

```
请求前处理 (message_tools.py processToolPipeline)
    │
    ▼
[1. 确定哪些工具需要 defer]
    ├─ 内置的 non-deferred 工具列表（如 Read、Edit、Bash、Write 等核心工具）
    ├─ 配置的 tool_search_non_deferred 追加
    └─ 其余工具标记 defer_loading: true
    │
    ▼
[2. 注入 tool_search_tool_regex]
    {
        "name": "tool_search_tool_regex",
        "type": "tool_search_20250501",
        ...
    }
    │
    ▼
请求发送到 Copilot
    │
    ▼
模型调用 tool_search_tool_regex（如果需要某个 deferred 工具）
    │
    ▼
响应中包含:
    {
        "type": "server_tool_use",
        "name": "tool_search_tool_regex",
        "input": { "pattern": "Glob" }
    }
    {
        "type": "tool_search_tool_result",
        "tool_references": ["Glob"]
    }
    │
    ▼
客户端（Claude Code 等）解析 tool_references
    → 后续请求中将这些工具从 deferred 切换为 active
```

### tool_search vs web_search 对比

| | `tool_search` | `web_search` |
|---|---|---|
| **本质** | Copilot 特有的工具发现机制 | 标准 Anthropic 网页搜索功能 |
| **目的** | 让模型按需搜索并"加载" deferred tools | 让模型获取最新网络信息 |
| **结果消费者** | **客户端** — 需解析 `tool_references` | **模型自身** — 搜索结果在同一消息内被消费 |
| **协议** | `server_tool_use` + `tool_search_tool_result` | `server_tool_use` + `web_search_tool_result` |
| **执行方** | 服务端（本项目内） | 服务端（Anthropic 后端）——本项目**不冒充** |

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.tool_search` | `true` | 是否为**支持的模型**注入 tool_search 工具（master switch） |
| `anthropic.model_capabilities.tool_search_overrides` | `{}` | per-model 强制覆盖表（`{model_substring: true/false}`），优先级高于内置默认允许表 |
| `anthropic.tool_search_non_deferred` | `[]` | 额外的不延迟工具名称（追加到内置列表） |

### 决策优先级（per-model 覆盖）

`tool_search` 的最终生效结果按以下顺序逐级判定，命中即短路：

```
1. anthropic.tool_search（master switch）为 false → 全局禁用，不再往下判断
2. anthropic.model_capabilities.tool_search_overrides 命中该模型（最具体匹配 / "*" 通配）→ 使用该值（true/false 均可强制覆盖）
3. 内置 default-allow 匹配器 → Claude ≥ 4.5 世代默认允许，Haiku 与 4.5 之前世代默认拒绝
```

```python
def model_supports_tool_search(model_id: str, family: str | None = None) -> bool:
    if not settings.anthropic.tool_search:
        return False
    override = find_most_specific(model_id, settings.anthropic.model_capabilities.tool_search_overrides)
    if override is not None:
        return override
    return tool_search_default_allow(model_id, family)


def tool_search_default_allow(model_id: str, family: str | None = None) -> bool:
    """内置默认允许表：Claude >= 4.5 世代允许，Haiku 与更早世代拒绝。
    新出现的 Claude 世代（未来的 4.7/4.8 等）自动被判定允许，无需逐一加白名单。"""
    def check(raw: str) -> bool:
        n = normalize_for_matching(raw)
        if not n.startswith("claude"):
            return False
        if n.startswith("claude-haiku"):        # Haiku 全系不支持
            return False
        is_pre_45 = (
            n.startswith(("claude-1", "claude-2", "claude-3", "claude-instant"))
            or n in ("claude-sonnet-4",) or n.startswith("claude-sonnet-4-2")
            or n in ("claude-opus-4",) or n.startswith(("claude-opus-4-1", "claude-opus-4-2"))
        )
        return not is_pre_45
    return check(model_id) or (family is not None and check(family))
```

**这一「内置 default-allow + per-model 覆盖表」结构相对旧文档描述的「模型硬编码支持列表」是一次重要演进**：旧列表需要为每个新发布的 Claude 世代手工加白名单；default-allow 匹配器基于世代号规则自动覆盖未来模型，`tool_search_overrides` 仅用于处理例外（某个特定型号实测不支持、或运营侧临时强制关闭）。

## Server Tool 处理（`strip_server_tools`）

`anthropic/message_tools.py` 中的 `strip_server_tools()` 控制 server tools 的处理方式：

| 配置值 | 行为 |
|--------|------|
| `false`（默认） | Server tools 原样透传，响应中的 `server_tool_use`/`*_tool_result` 也原样转发 |
| `true` | Server tools 从请求 `tools` 数组中移除（上游不支持时使用） |

当 `strip_server_tools: true` 时，`server_tool_filter.py` 作为安全网在响应侧激活，过滤可能残留的 server tool 块。此外，[请求执行管道](request-pipeline.md) 中的 `server_tool_rejection` 重试策略提供**反应式自愈**：首次遇到上游针对某个 server tool 类型前缀的拒绝（如 `"the use of the web search tool is not supported"`），即学习记录该 `(endpoint, model, type_prefix)` 组合并在后续请求中主动剥离，同时对**当前这次**重试也携带一次性的剥离提示，不依赖学习缓存是否已经写入。

## Server Tool 结果过滤（响应侧常驻）

`anthropic/server_tool_filter.py` 在响应流（含 SSE 流式与非流式）中过滤 server tool 相关的 content blocks。

### 常驻而非可选

与旧文档「仅在 `strip_server_tools: true` 时激活」的描述不同——**本项目的 server tool 响应过滤是响应侧常驻能力，始终生效，不受任何 config 开关门控**。这与 vscode-copilot-chat 的实际行为对齐：它无条件拦截 `server_tool_use` 与 `*_tool_result` 块，因为这些是服务端产物（如本项目自己注入的 `tool_search`），标准客户端既不期望收到、多数 SDK 也无法校验/解析这类未知块类型。若放任透传，反而可能造成客户端侧解析失败。

```python
def is_server_tool_block(block: dict) -> bool:
    """匹配 server_tool_use（任意 name）与所有 server tool result 类型
    （web_search_tool_result / tool_search_tool_result / code_execution_tool_result 等）。"""
    if block.get("type") == "server_tool_use":
        return True
    return is_server_tool_result_block(block)
```

### 流式过滤 + 块索引重映射

SSE 流中过滤掉的 block 会在原始索引序列中留下空洞（例如索引 2 被过滤后，索引 3、4 若不重映射会让客户端看到不连续的 index），因此过滤器在转发前维护一张「上游 index → 客户端 dense index」映射表，保证客户端侧看到的 `content_block_*` 事件索引始终从 0 开始连续递增：

```python
class ServerToolBlockFilter:
    """常驻响应侧过滤器：剔除 server_tool_use / *_tool_result 块，重映射剩余块索引保持 dense。"""

    def __init__(self) -> None:
        self._filtered_indices: set[int] = set()
        self._client_index_map: dict[int, int] = {}
        self._next_client_index = 0

    def _get_client_index(self, upstream_index: int) -> int:
        if upstream_index not in self._client_index_map:
            self._client_index_map[upstream_index] = self._next_client_index
            self._next_client_index += 1
        return self._client_index_map[upstream_index]

    def rewrite_event(self, event: dict) -> dict | None:
        """返回 None 表示该事件应被抑制（不转发给客户端）；否则返回（可能重映射了 index 的）事件。"""
        if event["type"] == "content_block_start":
            block = event["content_block"]
            if is_server_tool_block(block):
                self._filtered_indices.add(event["index"])
                return None
            return self._remap_index(event)

        if event["type"] in ("content_block_delta", "content_block_stop"):
            if event["index"] in self._filtered_indices:
                return None
            return self._remap_index(event)

        return event

    def _remap_index(self, event: dict) -> dict:
        if not self._client_index_map and not self._filtered_indices:
            return event  # 尚无任何过滤发生，零拷贝直通
        client_index = self._get_client_index(event["index"])
        if client_index == event["index"]:
            return event
        return {**event, "index": client_index}
```

非流式响应的过滤更直接——一次性从 `content` 数组中剔除匹配的块：

```python
def filter_server_tool_blocks_from_response(response: dict) -> dict:
    filtered = [b for b in response["content"] if not is_server_tool_block(b)]
    if len(filtered) == len(response["content"]):
        return response  # 零拷贝：无过滤发生
    return {**response, "content": filtered}
```

### web_search 双跳机制已退役——本项目不实现

**上游参考项目历史上实现过 web_search「双跳」编排**：即代理自己冒充 Anthropic 服务端，接管客户端发来的原生 `web_search_*` server tool 声明，代为执行搜索、合成一个 `server_tool_use` + `web_search_tool_result` 响应回填给客户端。这套机制已在上游被正式退役（ADR：`server_tool` 定位与 web_search 双跳退役，2026-07-13），本项目**从设计伊始就不实现**这套双跳编排，原因直接采纳该 ADR 的结论：

1. **零真实流量**——对上游真实语料（15GB History 库）的扫描显示，从未观测到任何客户端发送过原生 Anthropic server tool 声明（`web_search_2025*` / `web_fetch_2025*` / `code_execution*` 等）。
2. **真实客户端结构性地自己执行等价能力**——Claude Code 的 `WebSearch`/`WebFetch` 是**client tool**（`tool_use` 块，客户端自行发起 HTTP 请求并在下一轮回传 `tool_result`），不依赖代理冒充服务端。
3. **server tool 有一条服务端签名的结果通道，代理无法伪造**——真·server tool 的结果（如 `web_search_tool_result` 携带的 `encrypted_content`）由 Anthropic 后端加密签名，上游会校验其为真实非空 string；代理自己合成的结果只能填空字符串占位，属于「永远不彻底的冒充」。

因此本项目对 server tool 的策略保持极简：**默认透传**（客户端若发送原生 server tool 声明，原样转发给 Copilot 上游，由上游决定是否支持），**不支持时反应式自愈**（`server_tool_rejection` 重试策略学习并剥离，见上节），**响应侧常驻过滤**保证代理自身注入的 server tool 产物（如 `tool_search`）不泄漏给客户端。不额外实现任何「代理代为执行 server tool」的编排逻辑。

若未来出现真实客户端发送原生 server tool 的场景，现有的反应式自愈网（学习缓存 + per-attempt hint 剥离）已能兜底：不会硬失败，只是降级为剥离，行为退化为「该功能对该模型不可用」而非「代理试图冒充执行」。

## 会话续接与工具集变化

在 Claude Code 等客户端中，会话续接时可能出现工具集变化（客户端更新了 tool 定义列表）。

**关键原则：Anthropic API 不要求历史 `tool_use` 引用的工具必须在当前 `tools` 数组中。**只要 tool_use/tool_result 配对完整，API 就接受历史记录——但如上文「CC 官方工具注入」一节所述，实践中 Copilot 上游确实会对某些**已知固定工具集**（CC 16 个官方工具）及任意历史引用工具的**缺失声明**报错，因此本项目在 tool 预处理阶段主动补齐 stub 声明，早于 `process_tool_blocks` 执行。`process_tool_blocks()` 本身只关心配对完整性，不检查工具是否在当前 `tools` 数组中定义。

## Cache Control 的 tool 断点

Auto cache control（自动注入 Anthropic prompt caching breakpoint）作为一个横跨 tools/system 的整体机制，**统一归入** [anthropic-compat.md](anthropic-compat.md) 的 Cache 模式一节描述，本文档仅在此简述与 tool 相关的部分，避免重复维护同一段逻辑：

- 断点总量上限：`CACHE_CONTROL_BREAKPOINT_LIMIT = 4`（Anthropic 协议硬限制）。
- tools 侧的断点固定锚定在**最后一个非 deferred（`defer_loading` 不为 `true`）的 function 工具**上——因为 deferred 工具在本轮请求中大概率不会被模型实际使用，把断点花在它们身上没有缓存收益。
- **typed 工具排除在锚点候选之外**：`tool_search_*`、`memory` 等带 `type` 字段的 API 定义 typed 工具不参与「最后一个非 deferred 工具」的选取——它们的 schema 由 Anthropic 预定义、内容高度模板化，锚定缓存断点收益低，且部分实现下这类工具的 `cache_control` 字段可能触发额外校验分支。
- 完整的锚点选取算法、system 侧断点注入逻辑、以及 `cache_control` 四值模式（`disabled` / `passthrough` / `sanitize` / `proxied`）见 [anthropic-compat.md](anthropic-compat.md)。

## Deferred Tool 重试策略

当模型尝试调用一个 deferred 的工具但失败时（因为工具未加载），[请求执行管道](request-pipeline.md) 中的 `deferred_tool` 重试策略可以调整 tool 配置（把该工具切换为 sticky 非-deferred）后重试，并将这一决策持久化，使同一模型的后续请求不再需要重新踩坑。

## 相关文档

- [设计文档总纲](DESIGN.md)
- [消息清洗管道](sanitize-pipeline.md)（Tool blocks 配对处理、命名迁移）
- [Thinking 块处理管道](thinking-pipeline.md)（thinking 与 tool 块共存时的清洗交互）
- [Anthropic 兼容性](anthropic-compat.md)（Feature 检测、anthropic-beta headers、Cache 模式与 Auto cache control 完整算法）
- [Model 解析](model-resolution.md)（`normalize_for_matching`、模型世代判定）
- [请求执行管道](request-pipeline.md)（`server_tool_rejection` / `deferred_tool` 重试策略）
