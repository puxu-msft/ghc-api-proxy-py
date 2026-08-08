# Thinking 块处理管道

## 背景

Anthropic Extended Thinking 会在 assistant 消息中返回 `thinking` / `redacted_thinking` 块，其 `signature` 字段是加密签名——服务端用它验证「这段 thinking 内容在回传时没被篡改」。GHC（GitHub Copilot 的 Anthropic 直连端点）对**被修改过的**、或**堆叠**（两个 thinking 块相邻）的历史 thinking 块会报 `HTTP 400`：`"thinking blocks cannot be modified"`。

**关键实证结论（本项目立论基础）**：thinking `signature` 是**自包含**的——它加密的是 thinking 内容本身，上游解密重建校验，**不绑定周围上下文或数组位置**（针对 opus-4.6 系列实测验证）。换言之，只要 thinking 块的**内容逐字不变、相对顺序不变、不被丢弃**，其前后可以清理孤儿 client-tool 块或其他非-thinking 内容；相邻性由 destack 单独处理。

这一实证结论直接决定了本文档的核心设计：保护粒度是**块级（block-level）**，而不是像旧文档写的那样是**消息级（message-level）**布尔开关。旧文档的 `immutable_thinking`（布尔）或某些实现中出现过的三值策略，本质上是把整条包含 thinking 的 assistant 消息「冻结」——这在语义上过度保守（挡住了消息内可以安全做的清理），在实现上也不必要。本项目采用块级保护原语 `thinking_block_message_policy`，见下节。

> 参见 [DESIGN.md](DESIGN.md) 的「性能设计原则」P5——本管道 L3 会话隔离的内存化重设计是本项目相对上游参考项目最重要的性能改造之一。

## Responses reasoning carrier

Anthropic `/v1/messages` 选择 OpenAI Responses upstream 时，所有 outbound Responses 请求都显式设置 `include: ["reasoning.encrypted_content"]`。该字段不是为了向客户端暴露 Responses opaque wire，而是为了让 response converter取得可回传状态：每个Responses reasoning item各自生成一个Anthropic `thinking` block，visible summary进入`thinking`，非空`encrypted_content`进入本项目版本化v1 `signature` carrier；缺失或空payload使用项目bare marker并保持一item一block。

客户端下一轮原样回传该 `thinking` block时，Responses request converter恢复对应的reasoning item与opaque payload。项目producer只输出`ghc-api-proxy:synthetic-reasoning:v1` namespace；consumer另兼容已冻结的`copilot-api-js` v1合法主路径。Direct Messages leg不消费该synthetic状态，会在上游发送前剥离整个项目／兼容carrier block，避免把Responses专属opaque状态误发到Anthropic原生leg。

这一合同独立于客户端是否显式设置顶层`thinking`：模型可能在普通Responses请求中返回reasoning item，因此不能只在显式thinking请求中条件化`include`。完整双格式wire、malformed最小止血、encrypted-only与multi-item合同以[Anthropic Responses bridge Spec](../agents/anthropic-responses-bridge/spec.md)为权威。

## 管道总览（分层防御）

```
                    ┌─────────────────────────────────────────┐
                    │  L3 会话隔离（内存 dict + 滑动 TTL）        │
                    │  poisoned_thinking_quarantine            │
                    │  命中 → 主动剥离全部 thinking，跳过 L1     │
                    └─────────────────┬─────────────────────────┘
                                      │ 未命中 / 关闭
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │  空块清洗                                 │
                    │  thinking_block_sanitize                 │
                    └─────────────────┬─────────────────────────┘
                                      ▼
                    ┌─────────────────────────────────────────┐
                    │  L1 去堆叠（destack，终末 pass）           │
                    │  thinking_destack_strategy                │
                    └─────────────────┬─────────────────────────┘
                                      ▼
                              发送到 Copilot 上游
                                      │
                          ┌───────────┴────────────┐
                          │                        │
                       成功                    400「cannot be modified」
                          │                        │
                          ▼                        ▼
                       完成                 ┌───────────────────────┐
                                            │ L2 拒绝后剥离（一次重试） │
                                            │ strip_thinking_on_reject│
                                            └──────────┬─────────────┘
                                                       │ 成功
                                                       ▼
                                            ┌───────────────────────┐
                                            │ 记入 L3 隔离表（内存）   │
                                            │ (session_id, agent_id) │
                                            └───────────────────────┘
```

每层各自独立可关（config gate），组合起来形成一套「先预防（L1/L3）、再兜底（L2）、再固化学习结果（L3 写回）」的自愈闭环。

## 1. 块级保护（`thinking_block_message_policy`）

### 配置

| 配置项 | 取值 | 默认 | 说明 |
|--------|------|------|------|
| `anthropic.thinking_block_message_policy` | `preserve` / `stripped` | `preserve` | 决定清洗管道能否重排/删除历史 assistant 消息中的 thinking 块 |

> **重要更正**：本项目**不采用**旧文档描述的 `immutable_thinking`（布尔）或三值消息级策略。该描述已过时，见「相关文档」章节的更正说明。

### 语义

- **`preserve`（默认）**：assistant 消息若包含 `thinking` / `redacted_thinking` 块，则该消息在合并（如相邻同角色消息合并）、去重、system-role 消息转换等 **会重排/删除消息** 的清洗步骤中被**跳过**——避免把 thinking 块所在的消息与相邻消息合并、或整条移除导致 thinking 顺序被打乱。
- **`stripped`**：放开这一限制，允许清洗管道自由合并/重排/删除包含 thinking 块的消息（用于用户明确知晓風险、或该会话已确定不再需要 thinking 连续性的场景，例如已通过 L3 隔离主动剥离过 thinking 的会话）。

### Leg sanitizer 之后的不变量（Invariant）

协议 leg 专属 sanitizer 先处理不属于该 leg 的状态：Direct Messages leg定向剥离proxy-owned项目／兼容synthetic carrier blocks，同时保留native Anthropic thinking与其他内容；Responses leg则保留并恢复这些carrier blocks。完成这一步后，无论`preserve`还是`stripped`，**只要仍属于当前leg的thinking块还存在于payload中**，就必须满足：

1. **内容逐字（verbatim）**——不得修改 `thinking` 文本或 `signature` 字段的任何字节；
2. **相对顺序（relative order）**——多个 thinking 块之间的先后顺序不得颠倒；
3. **不丢弃（no-drop）**——不能静默丢弃某个仍属于当前leg的thinking块。合法删除路径只有上述Direct Messages synthetic carrier定向剥离、下一节按显式配置执行的损坏空块清洗，或L2／L3明确执行的整体thinking剥离；除此之外必须保留。

**相邻性明确不受保护**——两个 thinking 块相邻本身不违反上述不变量，但会触发上游「不允许相邻」规则的 400，这是 destack（L1）要解决的独立问题。

### Python 实现要点

```python
THINKING_TYPES = {"thinking", "redacted_thinking"}

def has_thinking_blocks(msg: dict) -> bool:
    """assistant 消息是否含有签名 thinking 内容。"""
    if msg.get("role") != "assistant":
        return False
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(block.get("type") in THINKING_TYPES for block in content)


def should_preserve_thinking_blocks(msg: dict, policy: Literal["preserve", "stripped"]) -> bool:
    """该消息中的 thinking 块本轮清洗是否需要保护（不参与合并/重排/删除判定）。"""
    return policy != "stripped" and has_thinking_blocks(msg)
```

清洗管道中所有**可能重排/删除消息**的步骤（相邻同角色合并、system-role 消息转换后的合并、Phase 1 去重等）在决定是否对某条消息执行结构性操作前，先调用 `should_preserve_thinking_blocks()`；命中则该消息原样跳过。**块内部**（例如过滤同一消息内的孤儿 tool_use/tool_result、清理空 text 块）不受此保护约束，因为它们不触及 thinking 块本身。

## 2. 空块清洗（`thinking_block_sanitize`）

某些上游/客户端交互路径可能产生「损坏的空 thinking 块」——例如 `{"type": "thinking", "thinking": "", "signature": ""}`。这类块既无实际思考内容、签名也为空，回传给上游只会造成噪音甚至触发校验错误，应当被安全丢弃（不受块级保护约束，因为它们本来就不携带任何需要保护的签名内容）。

### 配置

| 配置项 | 取值 | 默认 | 说明 |
|--------|------|------|------|
| `anthropic.thinking_block_sanitize` | `false` / `all_empty` / `signature_empty` / `thinking_empty` / `any_empty` | `all_empty` | 丢弃空 thinking 块的触发条件 |

### 触发条件语义

| 值 | 丢弃条件 |
|----|----------|
| `false` | 禁用，不做任何空块清洗 |
| `all_empty` | `thinking` 文本为空 **且** `signature` 为空——两者都为空才丢弃（默认，最保守） |
| `signature_empty` | 仅 `signature` 为空即丢弃（不管 thinking 文本是否有内容——通常意味着签名从未被正确写入，回传必然被拒） |
| `thinking_empty` | 仅 `thinking` 文本为空即丢弃（保留有签名但无文本的块，如 `redacted_thinking`） |
| `any_empty` | 只要 `thinking` 或 `signature` 任一为空即丢弃（最激进） |

### Python 实现

```python
def is_empty_thinking_block(block: dict, mode: str) -> bool:
    if block.get("type") not in THINKING_TYPES:
        return False
    thinking_empty = not block.get("thinking") and not block.get("data")  # redacted_thinking 用 data
    signature_empty = not block.get("signature")
    if mode == "false":
        return False
    if mode == "all_empty":
        return thinking_empty and signature_empty
    if mode == "signature_empty":
        return signature_empty
    if mode == "thinking_empty":
        return thinking_empty
    if mode == "any_empty":
        return thinking_empty or signature_empty
    raise ValueError(f"unknown thinking_block_sanitize mode: {mode}")
```

`redacted_thinking` 块没有 `thinking` 字段而是 `data`（加密数据），实现时需分别判空。

## 3. L1 去堆叠（Destack，`thinking_destack_strategy`）

### 问题

Copilot 上游要求「**任意两个 thinking 块不得相邻**」（同一条 assistant 消息内的 `content` 数组中）。堆叠常见于：多轮对话历史被截断/合并后，两个原本被其他块分隔的 thinking 块变得相邻；或客户端在合成消息时直接拼接了多段 thinking。

### 配置

| 配置项 | 取值 | 默认 | 说明 |
|--------|------|------|------|
| `anthropic.thinking_destack_strategy` | `passthrough` / `insert_text` / `move_blocks` | `move_blocks` | 去堆叠策略 |

### 策略语义

| 策略 | 行为 |
|------|------|
| `passthrough` | 不做任何处理，直接透传（用于调试/对照，或已知上游不校验相邻性的场景） |
| `insert_text` | 保持所有块原地不动，仅在检测到「两个 thinking 块相邻」处**插入**一个合成分隔符文本块 |
| `move_blocks`（默认） | 用消息内**真实存在的非-thinking 块**交错插入到相邻 thinking 块之间（保序），只有当可用的真实块数量不足时，才退化为插入合成分隔符 |

`move_blocks` 优于 `insert_text` 之处：优先复用真实内容作分隔符，减少合成噪音注入模型上下文；仅在不得已时才插入人工标记。

### 合成分隔符

```python
SYNTHETIC_THINKING_SEPARATOR = "[ghc-api-proxy: thinking separator]"
```

必须是**可辨识的、非空白**文本（上游会剥离纯空白/空文本块，用空白做分隔符等于没插入，起不到分隔作用）。选用固定、易识别的字符串，便于日志排查与后续（L2 剥离全部 thinking 时）识别并一并清除其残留的孤儿分隔符。

### 算法（`move_blocks`）

```python
def is_thinking(block: dict) -> bool:
    return block.get("type") in THINKING_TYPES

def is_real_separator(block: dict) -> bool:
    """可用作真实分隔符的非-thinking 块：text 类型要求非空白，其余类型（tool_use 等）直接视为可用。"""
    if is_thinking(block):
        return False
    if block.get("type") == "text":
        return bool(block.get("text", "").strip())
    return True

def move_blocks_strategy(content: list[dict]) -> tuple[list[dict], DestackStats]:
    """交错插入真实非-thinking 块，不足时退化为合成分隔符。保序、幂等。"""
    thinks = [b for b in content if is_thinking(b)]
    others = [b for b in content if not is_thinking(b)]
    real_seps = [b for b in others if is_real_separator(b)]
    non_sep_others = [b for b in others if not is_real_separator(b)]  # 空 text 等，追加到末尾，不作分隔符

    out: list[dict] = []
    si = 0
    stats = DestackStats()
    for i, t in enumerate(thinks):
        out.append(t)
        if i < len(thinks) - 1:  # 不是最后一个 thinking，需要在它和下一个之间插分隔
            if si < len(real_seps):
                out.append(real_seps[si]); si += 1
            else:
                out.append({"type": "text", "text": SYNTHETIC_THINKING_SEPARATOR})
                stats.inserted_markers += 1

    out.extend(real_seps[si:])       # 剩余真实分隔符按原序追加
    out.extend(non_sep_others)       # 非分隔符的其余块（如空 text）追加，保序
    stats.reordered_blocks += len(content)
    return out, stats


def has_adjacent_thinking(content: list[dict]) -> bool:
    return any(is_thinking(content[i]) and is_thinking(content[i - 1]) for i in range(1, len(content)))


def destack_adjacent_thinking(
    messages: list[dict],
    strategy: Literal["passthrough", "insert_text", "move_blocks"],
) -> tuple[list[dict], DestackStats]:
    """终末 pass：确保 payload 中任意 assistant 消息都没有相邻的 thinking 块。幂等——
    没有相邻 thinking 的消息原样返回（零拷贝，字节级不变）。"""
    if strategy == "passthrough":
        return messages, DestackStats()

    stats = DestackStats()
    out = []
    changed = False
    for msg in messages:
        if msg.get("role") != "assistant" or not isinstance(msg.get("content"), list):
            out.append(msg)
            continue
        if not has_adjacent_thinking(msg["content"]):
            out.append(msg)
            continue
        stats.destacked_messages += 1
        changed = True
        new_content = (
            insert_text_strategy(msg["content"], stats)
            if strategy == "insert_text"
            else move_blocks_strategy(msg["content"], stats)[0]
        )
        out.append({**msg, "content": new_content})
    return (out if changed else messages), stats
```

### 关键性质

- **幂等**：没有相邻 thinking 块的消息不受影响、按引用直接透传（Python 中体现为不重建该消息的 dict）。
- **终末 pass**：destack 必须是清洗管道的**最后一步**——因为它的输出结构（真实块位置被交错）不应再被后续清洗步骤（如孤儿过滤）打乱，否则可能重新造成相邻。
- **执行顺序关键约束**：L3 会话隔离的剥离动作必须发生在 destack **之前**（见「管道整体执行顺序」一节）。

## 4. L2 拒绝后剥离（`strip_thinking_on_reject`）

### 触发场景

即便有 L1 destack 预防，某些「thinking cannot be modified」400 仍然可能发生（非相邻性原因，例如客户端本身对 thinking 块做了字节级改动、或上游对某次请求的历史 thinking 有其他未知校验失败）。此时唯一可行的补救是**整体剥离**——不再尝试保留任何 thinking 内容，换取请求能够成功。

### 配置

| 配置项 | 取值 | 默认 | 说明 |
|--------|------|------|------|
| `anthropic.strip_thinking_on_reject` | `bool` | `true` | 收到匹配的 400 时是否剥离全部 thinking 后重试一次 |

### 匹配条件

必须**同时**满足以下两点，避免误伤无关的 400：

1. 错误消息包含短语 `cannot be modified`；
2. 错误消息包含 `thinking` 或 `redacted_thinking` 关键词。

```python
def is_thinking_modified_rejection(message: str) -> bool:
    lower = message.lower()
    if "cannot be modified" not in lower:
        return False
    return "thinking" in lower or "redacted_thinking" in lower
```

### 处理逻辑

这是[请求执行管道](request-pipeline.md)重试策略体系中的一个具体策略（`poisoned_thinking` 策略），**每请求一次性（one-shot）**：

```python
def strip_all_thinking(messages: list[dict]) -> tuple[list[dict], int]:
    """移除所有 thinking/redacted_thinking 块，以及 destack 插入后成为孤儿的合成分隔符。
    返回 (处理后消息, 移除的块数)。移除数为 0 时按引用返回原数组（零拷贝）。"""
    stripped_count = 0
    out = []
    for msg in messages:
        if msg.get("role") != "assistant" or not isinstance(msg.get("content"), list):
            out.append(msg)
            continue
        kept = [b for b in msg["content"] if not is_strippable_block(b)]
        removed = len(msg["content"]) - len(kept)
        if removed == 0:
            out.append(msg)
            continue
        stripped_count += removed
        out.append({**msg, "content": kept})
    return out, stripped_count


def is_strippable_block(block: dict) -> bool:
    """thinking/redacted_thinking 块，或 destack 留下的孤儿合成分隔符。"""
    if block.get("type") in THINKING_TYPES:
        return True
    return block.get("type") == "text" and block.get("text") == SYNTHETIC_THINKING_SEPARATOR
```

**为什么要一并清除合成分隔符**：L1 destack 在两个 thinking 块之间插入的分隔符，其存在意义仅仅是「隔开两段 thinking」；一旦 thinking 本身被整体剥离，这个分隔符就成了毫无意义的孤儿文本块，若不清除会原样泄漏给客户端/下游，故 `strip_all_thinking` 在同一遍中一并处理。

策略骨架（对接 [request-pipeline.md](request-pipeline.md) 的 `RetryStrategy` 协议）：

```python
class PoisonedThinkingRetryStrategy:
    name = "poisoned_thinking"

    def __init__(self) -> None:
        self._attempted = False  # per-request one-shot guard

    def can_handle(self, error: ApiError) -> bool:
        if self._attempted or not settings.anthropic.strip_thinking_on_reject:
            return False
        return is_thinking_modified_rejection(error.message)

    async def handle(self, error: ApiError, payload: dict, ctx: RequestContext) -> RetryAction:
        self._attempted = True
        messages, stripped_count = strip_all_thinking(payload["messages"])
        if stripped_count == 0:
            # 无 thinking 可剥离——这个 400 不是"回传 thinking 被拒绝"能解释的，中止而非空转重试
            return RetryAction(should_retry=False, modified_payload=payload, modifications=[])
        return RetryAction(
            should_retry=True,
            modified_payload={**payload, "messages": messages},
            modifications=["strip_all_thinking"],
        )

    def on_resolved(self, ctx: RequestContext) -> None:
        """本策略产出的重试最终成功时被管道回调——触发 L3 写入隔离表（见下节）。"""
        if not settings.anthropic.poisoned_thinking_quarantine:
            return
        key = to_quarantine_key(ctx.session_id, ctx.agent_id)
        if key is None:
            return
        get_quarantine_store().record(key, error_sample=ctx.last_error_message)
```

## 5. L3 会话隔离（`poisoned_thinking_quarantine` + `poisoned_thinking_ttl_hours`）

### 目的

L2 是**反应式**兜底——每次命中都要付出一次「发送 → 400 → 剥离 → 重试」的完整往返代价。如果同一个会话（`session_id` + `agent_id`）已经确认「回传 thinking 会被拒绝」，没有理由让它在**每一轮**对话中都重新交一次学费。L3 把这个结论**记住**，让后续同一会话的请求**在发送前**就主动剥离全部 thinking，从源头避免命中该 400。

### 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.poisoned_thinking_quarantine` | `true` | L3 隔离开关（master switch） |
| `anthropic.poisoned_thinking_ttl_hours` | `72` | 隔离条目的滑动 TTL（小时）——每次命中都会刷新过期时间 |

### 会话键：`(session_id, agent_id)`

- `session_id` 来自 `x-claude-code-session-id` 等请求头识别（详见 [history-system.md](history-system.md) 的 session 识别机制）；没有可用的 `session_id` 时**无法**跨轮记忆，L3 直接短路为 no-op。
- `agent_id` 区分同一会话内的主 agent 与子 agent（Task 工具派生的子 agent 携带独立的 `x-claude-code-agent-id`）；主 agent 请求没有该请求头，规整为空字符串 `""`，与任何真实子 agent id 都不冲突。

```python
@dataclass(frozen=True)
class QuarantineKey:
    session_id: str
    agent_id: str  # 主 agent 规整为 ""

def to_quarantine_key(session_id: str | None, agent_id: str | None) -> QuarantineKey | None:
    if not session_id:
        return None
    return QuarantineKey(session_id=session_id, agent_id=agent_id or "")
```

### 性能重设计（P5，关键——对照 [DESIGN.md](DESIGN.md) 性能设计原则表）

**上游参考项目的做法**：把隔离表实现为一个磁盘 SQLite sidecar 数据库，**每一个请求**在发送前都要同步查一次盘判断「这个会话是否已知中毒」。即便命中率极低（多数会话从未中毒），这个查询仍然长期挂在每请求的热路径上，属于 P5 明确点名的性能反模式。

**本项目的对策**：L3 隔离表**常驻内存**——一个进程内的 `dict[(session_id, agent_id), float]`（键 → 过期时间戳，或直接存最近命中时间 + 惰性比较 TTL），**热路径零磁盘 I/O**。可选异步持久化仅用于「进程重启后恢复隔离记忆」，不出现在请求处理的同步路径上。

#### 内存实现设计

```python
import time
import threading
from dataclasses import dataclass


class ThinkingQuarantineStore:
    """常驻内存的 (session_id, agent_id) 中毒会话隔离表，滑动 TTL，惰性过期。

    P5 重设计核心：无论 isPoisoned 命中与否，都不触碰磁盘。可选的异步持久化
    仅用于优雅关闭时快照 + 启动时恢复，绝不出现在请求路径的同步调用链上。
    """

    def __init__(self, ttl_hours_getter: Callable[[], float], max_entries: int = 1000) -> None:
        self._cache: dict[tuple[str, str], float] = {}   # key -> last_seen_at (monotonic 或 wall clock 秒)
        self._ttl_hours_getter = ttl_hours_getter          # 实时读取配置（支持热重载）
        self._max_entries = max_entries
        self._lock = threading.Lock()   # asyncio 单线程场景下可选，但兼容线程池调用路径更稳妥

    def is_poisoned(self, key: QuarantineKey, *, now: float | None = None) -> bool:
        """O(1) 读，纯内存查询，永不阻塞、永不触发 I/O。"""
        now = now if now is not None else time.time()
        with self._lock:
            last_seen = self._cache.get((key.session_id, key.agent_id))
        if last_seen is None:
            return False
        ttl_seconds = self._ttl_hours_getter() * 3600
        return (now - last_seen) <= ttl_seconds

    def record(self, key: QuarantineKey, error_sample: str, *, now: float | None = None) -> None:
        """L2 成功回传（on_resolved）时调用：登记该会话为已中毒，滑动 TTL 窗口起点。"""
        now = now if now is not None else time.time()
        with self._lock:
            self._cache[(key.session_id, key.agent_id)] = now
            self._prune_locked(now)
        # 可选：异步落盘（fire-and-forget，不阻塞调用方）供进程重启恢复，见下方"可选持久化"。

    def touch(self, key: QuarantineKey, *, now: float | None = None) -> None:
        """L3 命中时调用：刷新 TTL——只对已存在的键生效，touch 不会创建新记录。"""
        now = now if now is not None else time.time()
        with self._lock:
            if (key.session_id, key.agent_id) in self._cache:
                self._cache[(key.session_id, key.agent_id)] = now

    def _prune_locked(self, now: float) -> None:
        """惰性过期 + 容量上限：只在 record() 时机顺带清理，不设独立后台定时器。"""
        ttl_seconds = self._ttl_hours_getter() * 3600
        cutoff = now - ttl_seconds
        expired = [k for k, last_seen in self._cache.items() if last_seen < cutoff]
        for k in expired:
            del self._cache[k]
        overflow = len(self._cache) - self._max_entries
        if overflow > 0:
            oldest_first = sorted(self._cache.items(), key=lambda kv: kv[1])[:overflow]
            for k, _ in oldest_first:
                del self._cache[k]
```

**设计要点**：

- **惰性过期（lazy expiry）**：不设独立的后台清理定时任务，只在 `record()`（每次真正命中新的中毒会话时）顺带执行一次修剪。`is_poisoned()` 的读路径永远是纯内存字典查询，不承担清理职责，保持读路径尽可能轻量。
- **有界增长**：`max_entries` 防止长期运行下 dict 无限膨胀（超限按最旧命中优先淘汰，与 TTL 淘汰独立叠加）。
- **单例，进程级**：作为 FastAPI 依赖注入的单例对象持有，或挂在 `app.state` 上；不是每请求构造一个新实例。
- **热重载友好**：`ttl_hours_getter` 是一个可调用对象（读取当前 `AppSettings`），而不是构造时固化的常量——配置热重载后 TTL 立即生效，无需重建整个 store。
- **可选异步持久化**：如果需要「进程重启后恢复隔离记忆」，将 `record()`/`touch()` 的写入通过 `asyncio.Queue` 投递给一个专用的后台 writer 协程，由它异步、批量地把 `(session_id, agent_id, last_seen_at)` 写入 SQLite（复用 [history-system.md](history-system.md) 描述的「异步单层 SQLite」基础设施，同样遵循 P1 off-event-loop 原则）；**读路径（`is_poisoned`）永远只查内存**，从不因为持久化层的存在而退化为同步查盘。这与上游「每请求同步查盘」有本质区别：持久化在本项目中是**旁路的、fire-and-forget 的、可完全禁用的**能力，而不是热路径的必经步骤。

### 使用逻辑（每请求，作为 L3 主动剥离）

```python
def strip_all_thinking_if_quarantined(
    messages: list[dict],
    session_id: str | None,
    agent_id: str | None,
    store: ThinkingQuarantineStore,
) -> tuple[list[dict], bool]:
    """若 (session_id, agent_id) 命中隔离表，则主动剥离全部 thinking 并滑动 TTL。"""
    if not settings.anthropic.poisoned_thinking_quarantine:
        return messages, False
    key = to_quarantine_key(session_id, agent_id)
    if key is None:
        return messages, False
    if not store.is_poisoned(key):
        return messages, False
    stripped, stripped_count = strip_all_thinking(messages)
    store.touch(key)  # 命中即续期——即使本轮巧合无 thinking 也要保持隔离状态存活
    if stripped_count == 0:
        return messages, False
    return stripped, True
```

`touch()` 必须在 `stripped_count == 0` 判断**之前**调用：一个已被隔离的会话哪怕这一轮碰巧没有携带任何 thinking 块，也仍然是「活跃的中毒会话」，不应让它的隔离状态因为这一轮没有触发实际剥离而悄悄过期。

## 6. Signature 兼容 shim（`thinking_signature_compat`）

### 问题背景

某些 Copilot 上游在流式响应中，会把「带签名的 thinking 块」压缩成**单帧**发出：

```
content_block_start { type: "thinking", thinking: "", signature: "<...>" }
content_block_stop
```

**没有**中间的 `signature_delta` 事件。而标准 Anthropic 客户端（含 Claude Code、官方 SDK）的累积器实现是：在 `content_block_start` 时**创建**一个空的 thinking 累积块，但**忽略**该事件里直接携带的 `signature` 字段——它们只从后续的 `signature_delta` 事件里取签名。结果是标准客户端最终得到一个 `{thinking: "", signature: ""}` 的块，在下一轮把它原样回传时，自然会被上游拒绝（「每个 thinking 块必须包含内容」）。

这不是要「修正」上游模型/协议本身的行为——上游怎么发帧是它的权威决定；这是一个**面向客户端的兼容 shim**，只在**转发给客户端的流**上重塑这一帧，让标准客户端的累积路径能拿到签名。**历史记录中保留原始上游帧不变**。

### 配置

| 配置项 | 取值 | 默认 | 说明 |
|--------|------|------|------|
| `anthropic.thinking_signature_compat` | `false` / `signature_delta` / `redacted_thinking` | `signature_delta` | 面向客户端流的帧重塑方式 |

### 匹配条件

只匹配「`content_block_start` 中 `content_block.type == "thinking"` 且直接携带非空 `signature`」这一种特定形状。正常流式 thinking 块的起始帧是 `{thinking: "", signature 缺失}`，靠后续 delta 逐步填充——不会被此 shim 误伤。`redacted_thinking`（携带 `data` 而非 `signature`）也不属于此 shim 的目标。

```python
def is_embedded_signature_thinking_start(event: dict) -> bool:
    if event.get("type") != "content_block_start":
        return False
    cb = event.get("content_block") or {}
    if cb.get("type") != "thinking":
        return False
    sig = cb.get("signature")
    return isinstance(sig, str) and sig.strip() != ""
```

### 两种重塑模式

| 模式 | 行为 |
|------|------|
| `signature_delta`（默认） | 拆成两帧：① `content_block_start` 携带 `signature` 被清空的空 thinking 块（让客户端照常起步累积）；② 紧跟一个合成的 `content_block_delta { delta: { type: "signature_delta", signature } }`——这正是标准客户端期望的签名来源 |
| `redacted_thinking` | 把这一帧直接改写为 `redacted_thinking` 块（`data` = 原 `signature`），语义上表达为「加密、无明文的 thinking」；后续的 `content_block_stop` 帧原样透传 |

```python
def apply_thinking_signature_compat(event: dict, mode: str) -> list[dict] | None:
    """返回 None 表示无需重塑（原样转发）；否则返回按序转发的替换事件列表。"""
    if mode == "false":
        return None
    if not is_embedded_signature_thinking_start(event):
        return None

    cb = event["content_block"]
    signature = cb["signature"]
    thinking_text = cb.get("thinking", "") if isinstance(cb.get("thinking"), str) else ""

    if mode == "redacted_thinking":
        return [{
            "type": "content_block_start",
            "index": event["index"],
            "content_block": {"type": "redacted_thinking", "data": signature},
        }]

    # signature_delta
    return [
        {
            "type": "content_block_start",
            "index": event["index"],
            "content_block": {"type": "thinking", "thinking": thinking_text, "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": event["index"],
            "delta": {"type": "signature_delta", "signature": signature},
        },
    ]
```

## 7. Thinking 形状强制转换（`coerce_adaptive_thinking`）

Anthropic 的 thinking 参数有两种互斥形状：

- **`enabled`**（预算式）：`{"type": "enabled", "budget_tokens": int}`——适用于较早的 Claude 世代
- **`adaptive`**（自适应式）：`{"type": "adaptive"}` + `output_config.effort`——适用于仅支持自适应思考的模型（如 Opus 4.6 及更新世代）

一个模型只接受其中一种形状，发错形状是硬 400。当模型元数据表明「仅支持 adaptive」时，`coerce_adaptive_thinking` 在请求准备阶段**主动**把客户端传来的 legacy `{"type": "enabled", ...}` 强制转换为 `{"type": "adaptive"}`（`budget_tokens` 按启发式映射到 `effort` 档位：`low` / `medium` / `high`）。

这是**预测式**转换，与 [request-pipeline.md](request-pipeline.md) 中作为反应式兜底的重试策略（当模型元数据缺失、预测式转换未命中，导致上游报「`thinking.type.enabled` 不被支持」400 时才触发）互补而不重复——预测式转换命中时，反应式重试策略见到的 payload 已是 `adaptive` 形状，直接判定「无需转换」跳过。

## 管道整体执行顺序

```
请求进入 Anthropic 请求准备
    │
    ▼
[L3 主动剥离]  strip_all_thinking_if_quarantined()
    │   命中隔离表 → 剥离全部 thinking（本轮之后 destack 对该消息组是 no-op）
    │
    ▼
[空块清洗]  filter_empty_thinking_blocks()
    │   按 thinking_block_sanitize 模式丢弃损坏的空块
    │
    ▼
[常规清洗（Phase 2）]  详见 sanitize-pipeline.md
    │   process_tool_blocks / filter_empty_text_blocks 等
    │   —— 期间所有可能重排/删除消息的步骤都尊重 thinking_block_message_policy
    │
    ▼
[L1 去堆叠]  destack_adjacent_thinking()  ← 终末 pass
    │   确保没有两个 thinking 块相邻
    │
    ▼
[signature 兼容 shim]（仅作用于响应流，不影响请求侧顺序）
    │
    ▼
发送到 Copilot 上游
    │
    ├─ 成功 → 完成
    │
    └─ 400「thinking cannot be modified」
         │
         ▼
    [L2 拒绝后剥离]  strip_all_thinking() + 重试一次
         │
         ├─ 成功 → on_resolved() 写入 L3 隔离表（record）
         │
         └─ 仍失败 / 本无 thinking 可剥离 → 中止，交由上层错误处理
```

**为什么 L3 必须排在 destack（L1）之前**：如果顺序颠倒——先 destack 后 L3 剥离——那么 destack 会先为一个「即将被整体剥离」的会话插入合成分隔符（浪费计算，且这些分隔符本无必要存在），随后 L3/L2 的剥离逻辑还要额外识别并清除这些孤儿分隔符（`is_strippable_block` 中包含的合成分隔符判定分支正是为此设计）。让 L3 先行，能让 destack 在已经没有 thinking 块的消息上直接判定「无相邻 thinking」而跳过，是真正的空操作（no-op），既节省计算又避免产生孤儿标记。

## 数据结构小结

```python
@dataclass
class DestackStats:
    destacked_messages: int = 0
    inserted_markers: int = 0
    reordered_blocks: int = 0

@dataclass(frozen=True)
class QuarantineKey:
    session_id: str
    agent_id: str
```

## 相关代码（目标模块路径）

- `anthropic/thinking/protection.py` — 块级保护原语（`has_thinking_blocks` / `should_preserve_thinking_blocks`）
- `anthropic/thinking/destack.py` — L1 去堆叠（`insert_text` / `move_blocks` 策略）
- `anthropic/thinking/strip_all.py` — 全量剥离原语（L2/L3 共用）
- `anthropic/thinking/quarantine.py` — L3 内存隔离表（`ThinkingQuarantineStore`）+ 会话键规整
- `anthropic/thinking/signature_compat.py` — signature 兼容 shim
- `anthropic/thinking/coercion.py` — `enabled` ↔ `adaptive` 形状转换
- `pipeline/strategies/poisoned_thinking.py` — L2 重试策略

## 相关文档

- [设计文档总纲](DESIGN.md)（性能设计原则 P5）
- [消息清洗管道](sanitize-pipeline.md)（Phase 1/2 清洗与本管道的集成点）
- [请求执行管道](request-pipeline.md)（重试策略框架、`poisoned_thinking` 策略的挂载方式）
- [Anthropic 兼容性](anthropic-compat.md)（beta headers、adaptive/interleaved thinking 特性检测）
- [历史存储系统](history-system.md)（session 识别机制、异步 SQLite 基础设施——L3 可选持久化复用）
