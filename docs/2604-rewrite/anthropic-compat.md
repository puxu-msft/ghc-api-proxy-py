# Anthropic API 兼容性

## 概述

Anthropic `/v1/messages` 端点直连 Copilot 的原生 Anthropic API。仅支持 Anthropic vendor 的模型（Claude 系列）——路由决策依据模型元数据的 `vendor` 字段与 `/v1/messages` 端点支持标记，非仅名称匹配。

**Python 设计取向**：JS 上游把 feature 检测、beta header 构建、请求准备编排、header 转发、feature negotiation 分散在 `features.ts`、`request-preparation.ts`、`feature-negotiation.ts`、`header-policy/` 等多个文件中，彼此通过隐式的 `ctx.wire` 就地修改传递状态。Python 版本统一到 `anthropic/` 子包中，`request_preparation.py` 用一条**固定有序的准备步骤链**编排完整流程（各步骤自行按配置/模型能力短路，不做过滤式的动态排序），并通过不可变 `PrepareContext`（`dataclass`，非就地 mutate 共享字典）在步骤间传递派生标记（如"本次是否写入了 1h TTL"）。

请求头/响应头转发的双模式设计详见 [header-forwarding.md](header-forwarding.md)；feature negotiation 学习缓存详见 [feature-negotiation.md](feature-negotiation.md)；thinking 相关的块级保护/去堆叠/L2/L3 隔离详见 [thinking-pipeline.md](thinking-pipeline.md)（本文档仅在涉及 beta header/请求体构建处简要提及，不重复展开）。

## 功能支持矩阵

| 功能 | 支持程度 | 说明 |
|------|----------|------|
| Prompt Caching | 部分支持（写入侧） | 读侧只读：`cache_read_input_tokens` 来自 Copilot 响应的 `cached_tokens`。写入侧由 `cache_control` 四模式控制（默认 **passthrough**），见下节 |
| Batch Processing | 不支持 | Copilot API 不支持批处理，无需适配 |
| Extended Thinking | 支持 | `thinking` 参数转发；支持 interleaved thinking 与 adaptive thinking；块级保护/剥离/隔离见 [thinking-pipeline.md](thinking-pipeline.md) |
| Server-side Tools | 不支持，且已实测被拒的族会在出站前剥除 | 代理不执行 web search/fetch/code execution。Anthropic 端点对 `web_search*` / `web_fetch*` 声明整条拒绝请求，故这两族的声明与历史 blocks 由 `builtin:server-tool-capability` 在出站前剥除／摊平；`memory_*` / `tool_search_*` / `text_editor_*` 等客户端执行的 typed tools 继续透传。Responses leg 的 hosted web search 支持尚未实现。见 [tool-use.md](tool-use.md) |
| Context Management | 完整支持 | 服务端上下文编辑（`clear-thinking` / `clear-tooluse` / `clear-both`），含 feature negotiation 自愈 |
| Token Counting | 支持（默认转发上游精确计数） | `use_upstream_count_tokens`（默认 `true`），见下节 |

## 模型特性检测

`anthropic/features.py` 实现基于模型名称与模型元数据的特性检测，镜像 VSCode Copilot Chat 的检测逻辑。检测统一走 `normalize_for_matching()`（小写化 + 连字符规范化，例如 `Claude-Opus-4.6` → `claude-opus-4-6`），使点号/连字符/大小写变体都能命中同一条前缀规则。

### Interleaved Thinking

支持 interleaved thinking 的模型（可在多个 assistant turn 间穿插 thinking blocks）：

| 模型 | 支持 |
|------|------|
| Claude Sonnet 4/4.5/4.6 | 是 |
| Claude Haiku 4.5 | 是 |
| Claude Opus 4.5/4.6 | 是 |
| Claude Opus 4/4.1 | **否**（不支持 interleaved） |

```python
def model_supports_interleaved_thinking(model_id: str, family: str | None = None) -> bool:
    """匹配 config 驱动的 model-name 前缀白名单（支持 config.yaml 热更新，无需改代码）。"""
    candidates = [normalize_for_matching(model_id)]
    if family:
        candidates.append(normalize_for_matching(family))
    return any(
        n == p or n.startswith(f"{p}-")
        for p in INTERLEAVED_THINKING_MODEL_PREFIXES
        for n in candidates
    )
```

前缀匹配使用"精确相等或以 `-` 分隔的前缀"规则（而非裸 `startswith`），避免 `claude-opus-4` 误匹配无关的 `claude-opus-40`。

### Adaptive Thinking

具有 adaptive thinking 的模型（如 Opus 4.6）使用 `thinking: {"type": "adaptive"}`，**不需要** interleaved-thinking beta header。检测优先级（高到低）：

1. 模型元数据 `capabilities.supports.adaptive_thinking is True` → adaptive。
2. 元数据声明 `max_thinking_budget > 0` 且未声明 `adaptive_thinking` → 判定为**预算式（enabled）**thinking，不做 name-fallback 覆盖（正向元数据信号优先于名称猜测）。
3. 元数据缺失 thinking 相关字段 → 回退到 config 驱动的模型名白名单（`adaptive_thinking_models`）。

```python
def model_has_adaptive_thinking(model_id: str, resolved_model: Model | None = None) -> bool:
    supports = (resolved_model.capabilities.supports if resolved_model else None)
    if supports and supports.adaptive_thinking is True:
        return True
    if supports and isinstance(supports.max_thinking_budget, int) and supports.max_thinking_budget > 0:
        return False
    return matches_capability_prefix(normalize_for_matching(model_id), state.adaptive_thinking_models)
```

### Context Editing

支持服务端上下文编辑的模型（比 interleaved thinking 更广）：

| 模型 | 支持 |
|------|------|
| Claude Haiku 4.5 | 是 |
| Claude Sonnet 4/4.5/4.6 | 是 |
| Claude Opus 4/4.1/4.5/4.6 | 是（**含** Opus 4/4.1，与 interleaved thinking 的排除名单不同） |

同样是"元数据优先、名称回退"：先读 `capabilities.supports.context_editing`（当前 Copilot `/models` 尚未暴露该字段，恒为 `None`），缺失时回退 `context_editing_models` 白名单。

### Tool Search

支持 `tool_search` 的模型（default-allow 策略：Claude ≥4.5 默认允许，Haiku 与 4.5 之前的世代显式拒绝，新模型自动纳入而不必等代码更新）：

| 模型 | 支持 |
|------|------|
| Claude Sonnet 4.5/4.6 | 是 |
| Claude Opus 4.5/4.6 | 是 |
| Claude Haiku（任意版本） | 否 |
| 4.5 之前的世代（Claude 1/2/3、Sonnet 4 裸版、Opus 4/4.1） | 否 |
| 其他 | 否 |

解析优先级：模型元数据 `supports.tool_search` → per-model 覆盖表（`tool_search_overrides`，支持 `"*"` 通配） → 上述 default-allow 判定。任一层给出 `False` 即强制关闭；`tool_search_enabled` 主开关独立控制**消费点**（beta header 注入 + tool 管线注入），保持"能力判断"与"是否启用"解耦。

## Anthropic Beta Headers 动态构建

`anthropic/features.py` 的 `build_anthropic_beta_headers()` 根据模型能力与请求上下文动态构建 `anthropic-beta` 请求头：

```python
def build_anthropic_beta_headers(
    model_id: str,
    resolved_model: Model | None = None,
    *,
    disable_context_management: bool = False,
    force_context_management_beta: bool = False,
    emit_extended_cache_ttl_beta: bool = False,
) -> dict[str, str]:
    betas: list[str] = []

    # 非 adaptive thinking 模型需要 interleaved-thinking beta
    if not model_has_adaptive_thinking(model_id, resolved_model):
        betas.append("interleaved-thinking-2025-05-14")

    # context editing：模型支持 + config 模式非 off，或被 force 注入（context editing 升级重试场景）
    needs_context_mgmt_beta = not disable_context_management and (
        is_context_editing_enabled(model_id, resolved_model) or force_context_management_beta
    )
    if needs_context_mgmt_beta:
        betas.append("context-management-2025-06-27")

    # tool search：主开关 + 模型能力
    if state.tool_search_enabled and model_supports_tool_search(model_id, resolved_model):
        betas.append("advanced-tool-use-2025-11-20")

    # header 与 body 呼应：cache-control 步骤实际写入 1h TTL 时才发此 beta
    if emit_extended_cache_ttl_beta:
        betas.append("extended-cache-ttl-2025-04-11")

    return {"anthropic-beta": ",".join(betas)} if betas else {}
```

### Beta Feature 一览

| Beta | 触发条件 | 说明 |
|------|----------|------|
| `interleaved-thinking-2025-05-14` | 模型不支持 adaptive thinking | 启用 interleaved thinking |
| `context-management-2025-06-27` | 模型支持 context editing 且 mode ≠ `off`（或被强制注入） | 启用服务端上下文管理；与 memory 工具共享同一 beta |
| `advanced-tool-use-2025-11-20` | `tool_search_enabled` 且模型支持 tool search | 启用 `tool_search_tool_regex` 等高级工具能力 |
| `extended-cache-ttl-2025-04-11` | 最终 wire 中实际存在 `ttl: "1h"` 断点（本代理写入或客户端 passthrough 携带） | header 必须与 body 一致，否则上游可能拒绝该 TTL |

**客户端 beta 合并**：客户端自带的 `anthropic-beta` 头（例如 Anthropic SDK 附带的其他 beta）与本地构建的 beta 集合做**并集合并**（去重、逗号拼接），不是覆盖——避免丢失代理特性检测层未知的客户端侧 beta。合并后再经 [feature-negotiation.md](feature-negotiation.md) 的学习缓存过滤已知不受支持的 token。

## Cache Control 四模式

配置项 `anthropic.cache_control`（默认 **`passthrough`**）`[采纳]`，四选一：

| 模式 | 行为 |
|------|------|
| `disabled` | 剥离 wire 中**所有** `cache_control` 字段（含嵌套的 messages/system/tools/content） |
| `passthrough`（**默认**） | 保留客户端自带的所有 cache_control 断点与 TTL 值不变；只挖掉 GHC 已知不支持的**子字段地雷**（内置黑名单 `["scope"]`，另叠加 config 与 [feature negotiation](feature-negotiation.md) 学习到的 endpoint-level 黑名单） |
| `sanitize` | 保留客户端断点位置与合法 TTL（不再无条件降级为 5m），剥离非白名单子字段，并沿 `tools → system → messages` 顺序做跨层单调化（后出现的层 TTL 不得超过前面已出现层的 TTL，满足 Anthropic 的前缀递减约束） |
| `proxied` | 剥离客户端全部 cache_control 断点，再由代理按固定策略自行注入 GHC 风格断点（消息级优先，其次 tools/system 兜底），断点总数受 `CACHE_CONTROL_BREAKPOINT_LIMIT = 4` 限制 |

四模式对比的关键点：`passthrough` 是**最小干预**（默认），信任客户端已做的精细缓存调优，代理只挡掉已知会 400 的子字段；`sanitize` 是**规范化但不重写位置**；`proxied` 是**完全接管**，客户端断点全部作废，行为对齐 GHC 官方客户端的写入策略。

### 子字段剥离（passthrough / sanitize 共用）

内置地雷（`BUILTIN_UNSUPPORTED_CACHE_CONTROL_SUBFIELDS = ["scope"]`，`scope` 属于 GHC 尚未启用的 `prompt-caching-scope` beta）与三个来源做并集：① 内置黑名单 ② config `anthropic.cache_control_strip_subfields`（per-model + `"*"` 通配） ③ [feature negotiation](feature-negotiation.md) 的 `cacheControlSubfields` 学习集（endpoint-level，一次上游 400 免疫所有模型）④ per-attempt 重试提示（feature negotiation 反应式学习触发的本次排除项）。

### Extended Cache TTL

配置项 `anthropic.extended_cache_ttl.enabled`（默认 **`false`**），主开关；开启后代理自己写入的断点 TTL 从默认 5 分钟升级为 1 小时。生效需同时满足：

- 主开关开启；
- 模型支持扩展 TTL（`model_supports_extended_cache_ttl()`，元数据优先 + `extended_cache_ttl_models` 名单回退，是比 context-editing/memory **更窄**的集合，不含裸 `sonnet-4`/`opus-4`/`opus-4.1`）；
- 请求是 agent 式调用（消息历史中存在至少一条 assistant 消息，是"非首轮/非纯单轮"的近似判据）。

每层（`tools`/`system`/`messages`）分别配置 TTL（`extended_cache_ttl.tools_system_ttl`、`extended_cache_ttl.messages_ttl`），若 `messages_ttl = "1h"` 但 `tools_system_ttl = "5m"` 则自动钳制 `messages_ttl` 降为 `5m`（Anthropic 要求更长 TTL 必须出现在前缀更靠前的层），并一次性告警。

`CACHE_CONTROL_BREAKPOINT_LIMIT = 4`：单次请求最多写入 4 个 cache_control 断点（Anthropic API 硬限制），`proxied` 模式的注入逻辑按剩余配额递减分配。

## Context Management（服务端上下文编辑）

Context management 是 Anthropic API 的服务端功能，在输入 token 过大时自动修剪旧上下文，减轻代理自身维护上下文窗口的负担。

### 编辑模式

由配置项 `anthropic.context_editing` 控制（默认 **`off`**）：

| 模式 | 行为 |
|------|------|
| `off`（默认） | 禁用。不发送 `context_management` 字段，不添加对应 beta header |
| `clear-thinking` | 清理旧的 thinking blocks，保留最近 N 个 thinking turn |
| `clear-tooluse` | 清理旧的 tool_use/tool_result 对，由 input_tokens 阈值触发 |
| `clear-both` | 同时清理 thinking 与 tool_use |

### 请求体构建

```python
def build_context_management(
    mode: ContextEditingMode,
    has_thinking: bool,
) -> dict | None:
    if mode == "off":
        return None

    edits: list[dict] = []

    if mode in ("clear-thinking", "clear-both") and has_thinking:
        edits.append({
            "type": "clear_thinking_20251015",
            "keep": {"type": "thinking_turns", "value": max(1, state.context_editing_keep_thinking)},
        })

    if mode in ("clear-tooluse", "clear-both"):
        edits.append({
            "type": "clear_tool_uses_20250919",
            "trigger": {"type": "input_tokens", "value": state.context_editing_trigger},
            "keep": {"type": "tool_uses", "value": state.context_editing_keep_tools},
        })

    return {"edits": edits} if edits else None
```

`context_management` 只在**模型支持**（`model_supports_context_editing()`）且**未被 feature negotiation 标记为不支持**且**客户端未自带 `context_management` 字段**（尊重客户端自管上下文的选择）时自动注入。

### 相关配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.context_editing` | `off` | 编辑模式 |
| `anthropic.context_editing_trigger` | `100000` | `clear_tool_uses` 触发的 input_tokens 阈值 |
| `anthropic.context_editing_keep_tools` | `3` | 清理后保留的最近 tool_use 对数 |
| `anthropic.context_editing_keep_thinking` | `1` | 清理后保留的最近 thinking turn 数 |

## Warmup 策略

配置项 `anthropic.warmup`（默认 **`allow`**）`[采纳]`，四选一：`allow` / `reject` / `drop` / `fake`。

### 检测

Claude Code 会发送特殊的"Warmup"请求预热上游 prompt cache。检测规则：首条 `user` 消息的文本内容 == `"Warmup"`（纯字符串 content，或数组 content 中第一个 `text` 类型块的文本等于 `"Warmup"`）。

```python
def is_warmup_request(payload: MessagesPayload) -> bool:
    messages = payload.messages
    if not messages:
        return False
    first = messages[0]
    if first.role != "user":
        return False
    content = first.content
    if isinstance(content, str):
        return content == "Warmup"
    if isinstance(content, list):
        for block in content:
            if getattr(block, "type", None) == "text":
                return block.text == "Warmup"
    return False
```

### 四种策略

| 策略 | 行为 |
|------|------|
| `allow`（默认） | 正常转发给上游，不做任何拦截 |
| `reject` | 直接返回 HTTP 429（拒绝预热请求，适合不希望消耗上游配额的部署） |
| `drop` | 不转发上游，返回**最小空成功响应**：非流式返回空 `content` 的 message，`usage` 全 0；流式仅发送 `message_start` + `message_stop` 两个事件（跳过 `content_block_*`/`message_delta`），是"客户端满意但代理零成本"的折中 |
| `fake` | 不转发上游，返回**逼真的假响应**：`content` 为单个 text 块 `"Cache warmed."`，`usage.cache_creation_input_tokens` 按 system prompt 长度估算（简单的 `len(text) / 4` 启发式，仅用于让客户端展示"看起来合理"的缓存创建量，不追求精确），流式响应完整走一遍 `message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop` 六事件序列 |

`drop` 与 `fake` 的取舍：`drop` 更省（连伪造 usage 的开销都不做），`fake` 更贴近真实客户端体验（部分客户端可能依据 usage 展示缓存命中提示）；运维可按需选择。

## Token Counting

配置项 `anthropic.use_upstream_count_tokens`（默认 **`true`**）：

- **默认（`true`）**：`/v1/messages/count_tokens` 转发到 Copilot 上游同名端点，使用与真实补全请求相同的 `request_preparation` 流水线构造 wire（同源，反映真实计费口径），走现成的 Copilot token（无需独立的 `ANTHROPIC_API_KEY`）。支持边界约等于账号当前 `/models` 目录（目录外模型必然 400，目录内但不支持 `/v1/messages` 的模型如 embedding 也会 400，因此需先经 `is_endpoint_supported(model, MESSAGES)` 早退，避免注定失败的往返请求）。上游非 200 或请求异常时静默降级到本地估算（不抛错、不阻塞响应），并记一条 `warn` 日志。
- **`false` 或本地估算兜底路径**：使用本地 GPT tokenizer（`tiktoken` 的 `o200k_base` 或模型元数据指定的分词器）估算。计数排除历史 assistant 消息中的 thinking 块内容（thinking 不计入下一轮 input tokens，符合 Anthropic 规范），并对每条消息追加固定 `+4` 的消息边界开销近似值。可选按学习到的校准因子（历史真实值 vs 本地估算值的比值）修正估算结果，未学习模型该因子为恒等映射。

**重要更正**：本项目**不存在** `anthropic_api_key` / `ANTHROPIC_API_KEY` 这类独立密钥配置——token counting 与所有 Anthropic 请求一样，统一使用 Copilot 认证凭据，不直连 `api.anthropic.com`。

`count_tokens` 端点**不纳入可观测性范围**（不建请求上下文、不进历史/遥测/WebSocket 推送），仅在终端渲染一条与正常请求同款格式的展示行（区分 `channel` 标注：`GHC upstream` / `local calibrated` / `unknown model`），详见 [history-system.md](history-system.md) 与 [telemetry-observability.md](telemetry-observability.md) 中"观测边界"相关说明。

## 请求准备编排流程

`anthropic/request_preparation.py` 的 `prepare_anthropic_request()` 用一条**固定有序**的准备步骤链编排完整流程（B1..Bn，声明顺序即契约，不做过滤式重排；每步骤自行按配置/模型能力内部短路）：

```
原始 payload
    │
    ▼
[B1. 构建 wire payload]
    ├─ 剥离 Copilot 不接受的字段（内置黑名单 + config 按模型配置 + feature negotiation 学习集，见 feature-negotiation.md）
    │   内置默认：["inference_geo"]
    │   payload 中会被就地修改的嵌套字段（messages/system/tools/output_config/thinking）在此深拷贝，
    │   避免重试时上一次准备结果的修改污染下一次准备（每次重试都从干净的原始 payload 出发）
    │
    ▼
[B2. Thinking 形状/预算调整]（固定子顺序：先形状后预算后 effort）
    ├─ enabled → adaptive 形状强制转换（仅当模型只接受 adaptive 形状）
    ├─ adaptive → enabled 形状强制转换（仅当模型只接受 enabled/预算式形状，互斥于上一步）
    ├─ budget_tokens 按模型 min/max 约束裁剪，且确保 budget_tokens < max_tokens
    └─ output_config.effort 按模型支持的档位白名单钳制到最接近的合法值
    │
    ▼
[B3. 剥离不受支持的 partner-model 特性]（如 Vertex 路由禁用 structured_outputs）
    │
    ▼
[B4. Cache Control 处理]（按四模式之一，见上节）
    │
    ▼
[B5. 构建请求头]
    ├─ Copilot 伪装头（editor-version 等，见 authentication.md）
    ├─ anthropic-version: 2023-06-01
    ├─ anthropic-beta（动态构建 + 客户端合并 + negotiation 过滤，见上节）
    ├─ X-Initiator: agent（消息历史含 assistant 消息）/ user
    ├─ vision 相关头（消息含 image 块且模型支持 vision）
    └─ 请求头 passthrough（按 header-forwarding.md 的双模式 + security floor）
    │
    ▼
[B6. Feature Negotiation 检查 + Context Management 自动注入]
    ├─ context_management 字段/beta 若被 feature negotiation 标记为该模型不支持 → 从 wire 与 beta 中一并剔除
    └─ 否则按配置模式构建并注入（未被客户端自带字段抢占时）
    │
    ▼
返回 { wire, headers }
```

**幂等性**：`prepare_anthropic_request()` 对 feature negotiation 学习缓存**只读**（写入仅发生在上游错误响应解析后的"学习"环节，不在准备链路内），且对输入 `payload` 不做原地修改（深拷贝隔离），因此可在同一 attempt 内被多次调用（如 count_tokens 复用补全路径的准备逻辑）而不产生副作用差异。

## 模型名翻译

系统将客户端发送的模型名翻译为匹配的 Copilot 模型：

- **短别名**：`opus` → 最佳可用 opus，`sonnet` → 最佳可用 sonnet
- **连字符版本**：`claude-opus-4-6` → `claude-opus-4.6`
- **带日期后缀**：`claude-sonnet-4-6-20250514` → `claude-sonnet-4.6`
- **修饰符后缀**：`claude-opus-4-6-fast` → `claude-opus-4.6-fast`，`opus[1m]` → `claude-opus-4.6-1m`
- **直接名称**：`claude-sonnet-4`、`gpt-4` 等直接透传
- **Model Overrides**：任意映射，支持链式解析和 family 级别重定向

详见 [Model 解析](model-resolution.md)。

## 相关文档

- [设计文档总纲](DESIGN.md)
- [Model 解析](model-resolution.md)
- [Tool Use 机制](tool-use.md)
- [消息清洗管道](sanitize-pipeline.md)
- [Thinking 处理管道](thinking-pipeline.md)
- [请求/响应头转发安全](header-forwarding.md)
- [Feature Negotiation 学习缓存](feature-negotiation.md)
- [配置系统](config-system.md)
