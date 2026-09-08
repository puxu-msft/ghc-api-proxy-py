# TUI 内部设计

状态：living design。行为合同以 [`spec.md`](spec.md) 为权威；本文件解释实现机制，不另立一套可观察行为。

## Responses completion display projection

### 目标与边界

Responses provider observation 按 `output_index` 保留每个 output item 的原始类型、名称、reasoning facts、client-action requirement、重复与顺序。完成行把这些 rich facts 投影成紧凑的可见 segment，再合并可合并的相邻 segment，最后渲染文本。显示归约不得回写、删减或重排 durable observation。

本机制只负责 Responses terminal status、reasoning 和 client actions 的 completion-line projection。它不改变 `ResponseObservation` schema、action 分类、delivery policy、ending precedence、Chat Completions projection、Anthropic stop reason、pending tools 或 footer layout。

可观察行为的权威条款位于 [`spec.md`](spec.md)“描述回复的用词跟随上游”和“验收”第 7 条。Spec 于 2026-09-06 明确“durable facts 逐项保留，display projection 相邻归约”，`abdfd54` 已同步 production projection 与 unit／integration 转录。后续变更必须继续让这三类载体保持一致，不能按修订前的逐项 oracle 反向修改 Spec，也不能让本设计取代 Spec。

### 结构根因

`45e7cfb` 用 action accumulator 合并相邻调用；`b233751` 为保持 reasoning 与 action 的顺序，再加入 reasoning accumulator。两个 pending run 依靠同一个 imperative loop 在每个分支手工 flush。Merge commit `f97d243` 删除了整套 action accumulator，却保留 reasoning accumulator并继续正常运行；同一次 merge 又把最终字符串测试改为逐项显示，回归因此被写成了新的 oracle。

缺失的结构不是一个局部变量，而是一个可独立观察和测试的“visible segments → adjacent reduction”层。实现必须让 item selection、barrier、merge identity 与 rendering 分槽，避免新增或删除一种 segment 时靠分散的 `flush_*()` 调用维持正确性。

调查、设计比较与处置见 [`history/260906-function-call-grouping-structure-review.md`](history/260906-function-call-grouping-structure-review.md) 和 [`history/260906-function-call-grouping-structure-review-disposition.md`](history/260906-function-call-grouping-structure-review-disposition.md)。

### Typed segment

`request_log.py` 内部定义 immutable private segment types；它们是 presentation model，不进入 provider observation 或 durable schema。

```python
@dataclass(frozen=True, slots=True)
class _NamedAction:
    raw_type: str | None
    raw_names: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class _Reasoning:
    kind: Literal["enc", "txt"]
    count: int

@dataclass(frozen=True, slots=True)
class _UnknownAction:
    raw_type: str | None

@dataclass(frozen=True, slots=True)
class _AnonymousAction:
    raw_type: str | None

type _ResponseDisplaySegment = _NamedAction | _Reasoning | _UnknownAction | _AnonymousAction
```

Atomic projection 先用单个 raw name 构造 `_NamedAction`；相邻归约后，`raw_names` 可以包含多个名称。Raw values 保留到 renderer 边界，分组 identity 因而不会误用被截断或转义后的 display label。

`_UnknownAction` 与 `_AnonymousAction` 独立成型，使“可见但不合并”成为数据形状。任何未来新增的可见 segment variant 默认也是 barrier，除非 reducer 显式增加它自己的 merge rule。

### 投影、归约与渲染

`_response_display_segment(item)` 只把一个 `OutputItemSummary` 投影成一个 atomic segment 或 `None`：

1. Reasoning 含 readable summary 时返回 `_Reasoning(kind="txt", count=1)`；否则含 encrypted content 时返回 `_Reasoning(kind="enc", count=1)`。
2. 没有可见 reasoning 且 requirement 为 `NOT_REQUIRED` 时返回 `None`。这类 item 不显示，也不制造伪边界。
3. Requirement 为 `UNKNOWN` 时返回 `_UnknownAction(raw_type=item.type)`。
4. Requirement 为 `REQUIRED` 且 name 为 `None` 或空字符串时返回 `_AnonymousAction(raw_type=item.type)`。
5. 其余 required action 返回单名 `_NamedAction(raw_type=item.type, raw_names=(item.name,))`。

`_coalesce_response_display_segments(segments)` 是纯 pairwise fold。它只查看结果尾项和当前项：

- 两个相邻 `_NamedAction` 的 `raw_type` 相等时，按顺序拼接 `raw_names`；不去重。
- 两个相邻 `_Reasoning` 时，无论 `txt`／`enc` 是否相同，合并成单个字段并按各 kind 累加计数——一段内部交错 `txt`／`enc` 的连续推理 run 归约成一个 `reason(...)`，而不是一行重复的 `reason(txt:N) reason(enc:N)...`。
- 其它组合直接追加当前 segment，因此不同 action type、可见 reasoning（对 action 而言）、unknown、anonymous 和未来新增 variant 都自然断开两侧。

`_render_response_display_segment(segment, *, color)` 只负责 console grammar：

- `_NamedAction` 先分别对 raw type 和每个 raw name 调用 `inert_token()`，再把 encoded names 交给 `_painted_tools()` 添加 renderer 自己的逗号和颜色。
- `_Reasoning` 渲染为 `reason(enc:N)`／`reason(txt:N)`，混 kind 的连续 run 渲染为固定的 `reason(enc:N,txt:M)`（enc 在前），与 `format_thinking` 的顺序一致。
- `_UnknownAction` 渲染为 `client_action?(<type-or-unknown>)`。
- `_AnonymousAction` 渲染为裸 `<type-or-client_action>`。

`format_response_observation()` 保持 public interface，只按顺序编排 status projection、atomic segment projection、adjacent reduction 与 rendering。

### Status 与 display segment 相互独立

`completed` 是否为绿色必须直接读取完整 `ResponseObservation.output_items` 与 snapshot availability：只有 `output_items` 可用且其中没有 `REQUIRED` 或 `UNKNOWN` action 时才是 clean completed。它不得从 visible segments 是否为空、是否合并或最终文本反推。

这一边界保证 presentation trim 不会改变 terminal status 语义。未来隐藏一种 segment、改变合并规则或修改 grammar，都不能把仍需客户端行动的 `completed` 涂绿。

### Legacy compatibility path

`format_terminal_status()` 在 rich observation unavailable 时渲染同一 Responses client-action grammar。`ClientAction` 已携带 requirement、raw type、raw name 与顺序，因此 legacy path 通过 adapter 生成相同 action segment，并复用同一个 adjacent reducer 与 renderer。

这次复用只统一 presentation seam，不改变 `ClientAction` producer、legacy fallback 的优先级、classification completeness、delivery control 或 durable schema。Legacy carrier 没有 reasoning facts，因此不合成 reasoning segment。

### 测试责任

测试按责任分层：

1. Atomic projection 测试直接比较 typed segments，覆盖 visible reasoning、named required、unknown、anonymous，以及不可见 `NOT_REQUIRED` item 返回 `None`。
2. Reducer 测试直接比较完整 segment tuple，覆盖相邻同 raw type 合并并保留重复、不同 raw type、reasoning、unknown 与 anonymous barrier、transparent item 不制造边界、reasoning 同 kind 计数，以及 raw-type truncation collision。
3. Renderer 测试验证每个 raw name 先 inert、renderer 后加逗号；颜色仍由 `_painted_tools()` 按名称 run 处理。
4. Public formatter 测试硬编码完整尾段，同时独立断言 `ResponseObservation.output_items` 的逐项 index、raw type、raw name、reasoning facts、重复与顺序。
5. Legacy fallback 测试验证相同 action grouping rule，同时保持 contextual completed 与 fallback precedence。
6. 既有 production-entry mock integration 测试把两个相邻 `function_call(Bash)` 精确断言为一个 `function_call(Bash,Bash)`，并保留无名 `custom_tool_call` barrier 与 completed 不着色断言。该测试证明本代理的接线和 projection，不冒充真实 upstream shape。

删除 named-action merge arm时，reducer tuple、public formatter tail 和 production-entry integration tail 必须同时改变。一次性受控缺陷检查可以确认这些 oracle 对 `f97d243` 的失效形状有鉴别力；本项目不为此建立 mutation framework 或新的机械 gate。

### 未采用方案

- **恢复双 accumulator：**能恢复输出，却保留依赖 scattered flush calls 的结构根因。
- **通用 callback reducer：**当前只有一个领域调用者；把 skip、barrier、identity 与 merge 参数化会把组合约束重新藏进 callback contract。
- **渲染后合并字符串：**raw identity 已丢失，provider 字符、renderer delimiter 与 ANSI 无法可靠区分。
- **重写 `ResponseObservation` schema：**现有 facts 足够；扩大 schema 不会降低 display reducer 再次被删的概率。
- **排除 legacy fallback：**会让同一 Responses display contract 随 observation availability 分叉。
