---
report_id: function-call-grouping-structure-review-260906
attempt_id: function-call-grouping-structure-review-260906-a1
status: in-review
target_rev: f97d243f9431d836861ce5e9938605df56b37478
reviewed_at_rev: f97d243f9431d836861ce5e9938605df56b37478
role: independent_architecture_reviewer
---

# Responses completion action 聚合结构评审

## 评审范围

本评审仅调查 Responses completion 的 display projection 结构，比较 `45e7cfb972b6f9df5874a8455d9961d692f2bba2`、`b23375165ae0a72d7a5e6271f6d48c3236e55666` 与 merge commit `f97d243f9431d836861ce5e9938605df56b37478` 在 formatter 和测试上的状态，并评估怎样防止一次 merge resolution 静默删除一类聚合语义。范围内是清单列出的 formatter、事实模型、action 分类、单元测试、TUI Spec 与 merge-conflict 报告，以及这些对象在三个 commit 中的对应版本。范围外是整个 TUI 重写、`ResponseObservation` schema 重写、源码／测试／Spec 修改、提交和 production cutover。

## 评审基线与读取方式

首个目录核验显示隔离 worktree 的物理路径与 Git 根目录均为 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a305fd27ed103f27e`，其 `HEAD` 正是目标 revision `f97d243f9431d836861ce5e9938605df56b37478`。因此 `reviewed_at_rev` 为该完整 SHA；目标最终态源码从清单绝对路径读取并用逐字节比较确认与该 worktree 一致，历史 commit 与 path patch 通过该 worktree object database 上的 `git show`／`git diff` 读取。清单与开发报告从主工作树 `/home/xp/src/ghc-api-proxy-py/.dev/` 的绝对路径读取。

## 判据来源

当前行为合同来自用户本轮明确裁决，而不是从历史代码反推：只合并连续、同原始 item type 且具名的 required actions；可见 reasoning、不同 action type、unknown action 与无名 action断开聚合；不可见且 `NOT_REQUIRED` 的 item 不制造伪边界。用户随后明确要求根因修复与结构优化，而不是最小恢复。历史代码、测试、Spec 与报告只作为事实证据，用来说明已有实现、既有合同记录及失效机制，不能冒充本轮用户裁决。

评审判据是长期可维护性、职责边界、rich facts 不丢失、回归可识别性，以及清单要求的事实选择、相邻性、merge identity、文本编码／着色、最终拼接职责可区分。推荐方案还必须限定迁移范围，不扩展为整个 TUI 或 `ResponseObservation` schema 重写。

## 整体判定

`needs-fix`。目标 revision 的 formatter 与 unit／integration oracle 一起偏离用户当前确认的 action grouping 合同，现行 TUI Spec 也仍转录该偏离；不能直接进入完成态。未发现 blocker：事实模型已经保留实现正确 projection 所需的 raw type、raw name、requirement、reasoning facts、output order 与 duplicates，不需要重写 schema。推荐在 Spec 先行修订后采用“typed visible segments → domain-specific adjacent reduction → rendering”的局部结构，并把 legacy Responses fallback 纳入同一 action rendering seam。

## Blocker 数

0。

## 已闭合事实发现

### function-call-grouping-structure-review-260906-01：merge resolution 删除 tool-run 状态机并把回归写成新 oracle

- severity: major
- conclusion_strength: confirmed
- primary_location: `src/app/observability/request_log.py:315-408`，`f97d243f9431d836861ce5e9938605df56b37478` 的 `format_response_observation()`
- related_locations: `tests/unit/observability/test_request_log.py`；`45e7cfb972b6f9df5874a8455d9961d692f2bba2`；`b23375165ae0a72d7a5e6271f6d48c3236e55666`；merge 的第二父提交 `8ac6522896cdd3a43d796c33999595c25b8f798b`
- evidence: `45e7cfb` 引入以 raw `item.type` 为 identity 的相邻具名 action run，逐项先做 `inert_token(name)`，flush 时才由 `_painted_tools()` 加逗号和颜色；unknown、无名 required action 与 raw type 变化都会 flush。`b233751` 在此基础上增加独立的 reasoning-run accumulator，并在可见 reasoning 与 action 之间互相 flush，保留可见顺序。`f97d243` 相对第二父提交完整删除 `tool_run_type`、`tool_run_label`、`tool_run_names` 与 `flush_tool_run()`，但保留 reasoning accumulator；同一 merge 同时把测试名从 `groups...` 改成 `preserves...without_grouping`，并把 expected 从 `function_call(Read,Read,Read,Read)` 改成四个重复 segment，把跨不可见 item 的 `function_call(Read,Bash)` 改成两个 segment。目标最终态源码与主工作树所列四个文件逐字节一致。
- impact: 当前目标 revision 与用户本轮确认的 display contract 冲突；更严重的是测试不再只是漏测，而是把被删行为认证为正确，使以后简单恢复聚合会被既有 oracle 判红。这是公共显示合同与回归可识别性缺陷，故定为 major。
- recommendation: 不把修复限定为粘回局部变量。建立显式 typed display-segment projection，再以相邻 segment reducer 合并 action run；测试分别钉事实投影、相邻归约和最终渲染，使删除任一归约规则都在该责任自己的测试入口变红。

证据边界：上述是 commit object、目标最终态与完整 path diff 支撑的历史事实，强度足以据此实施结构修复；“应该恢复哪一条行为”则来自用户本轮当前裁决，不是 `45e7cfb` 或 `b233751` 自身获得权威性后反推出来的结论。

### function-call-grouping-structure-review-260906-02：现行 Spec 与当前用户裁决冲突，必须先修订再实施

- severity: major
- conclusion_strength: confirmed
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:150-160,208-216` 的“描述回复的用词跟随上游”与“验收”第 7 条
- related_locations: 同一 Spec 的 2026-09-03／2026-09-04／2026-09-05 修订记录；`tests/unit/observability/test_request_log.py`；`tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour`
- evidence: 当前 Spec 仍以逐项输出为精确 oracle，例如第 7 条要求两个相邻 `function_call(Bash)` 分别显示；目标 revision 的 unit 与 integration expected 与之同形。用户本轮随后明确把显示合同改为“连续、同 raw type、具名且 `REQUIRED` 的 actions 合并”，同时明确不可见且 `NOT_REQUIRED` 的 item 不制造伪边界。两者在 display grammar 上不能同时成立，但“ResponseObservation 逐项保留事实、重复、顺序”并未被推翻。
- impact: 项目规则要求完整行为 Spec 先于实现，且 Spec 转录到测试时同一变更同步更新。若直接改生产代码或只改测试，会再次形成一个权威源已知错误而仍被引用的 bypass。
- recommendation: 实施前先修订 Spec 的 display 段、验收第 7 条及修订记录，明确区分 durable facts 的逐项保留与 terminal display 的相邻归约；随后同一 change 更新生产 projection 及其 unit／integration 转录。

## 三个 revision 的完整对比结论

| revision | formatter 结构 | tests 的 oracle | 证据强度 |
|---|---|---|---|
| `45e7cfb972b6f9df5874a8455d9961d692f2bba2` | 引入单一 action-run accumulator。只有 `REQUIRED`、raw name 非空且 raw `item.type` 相同的相邻可见 action 才合并；unknown、无名和不同 raw type 先 flush；`NOT_REQUIRED` 直接跳过。run identity 使用 raw type，label 与 name 只在显示阶段 `inert_token`，name 逐项编码后才交给 `_painted_tools()` 加分隔符与颜色。 | 新增重复不去重、只合并相邻同 raw type、当时被 action loop 当作 non-client 的 item 不断开、unknown／无名断开且可见、bounded label 不作 identity、名称先 inert 再加逗号等精确断言；当时 reasoning 仍在尾部另行汇总，尚未成为有序可见 barrier。测试同时单独断言 `ResponseObservation.output_items` 逐项事实没有被显示聚合改写。 | confirmed，来自 commit 自身完整 path diff。 |
| `b23375165ae0a72d7a5e6271f6d48c3236e55666` | 在 action run 之外增加 reasoning run，并让两个 run 在遇到对方的可见 segment 时相互 flush；同 reasoning kind 相邻计数，不同 kind 分段；没有可见内容的 reasoning 与其它 `NOT_REQUIRED` item 被跳过，因此不制造边界。legacy `line.thinking` 仅在没有 observed output item sequence 时回退。 | 新增 reasoning／action 交错顺序、reasoning kind、可见 action barrier、不可见 item 不断开、legacy suppression 等断言，同时保留 `45e7cfb` 的 action grouping oracle。 | confirmed；`45e7cfb` 是 `b233751` 的 ancestor，来自 ancestry check 与 commit 自身完整 path diff。 |
| `f97d243f9431d836861ce5e9938605df56b37478` | merge 保留 reasoning accumulator，却相对第二父提交完整删除 action accumulator 与 `flush_tool_run()`；每个 action 立即 append 为独立字符串。它同时合入 contextual `completed` 着色、legacy fallback 等其它正确语义，这些不抵消 grouping 的删除。 | 将原 grouping tests 改名为“preserves ... without grouping”，并把 grouped expected 改成逐项 expected；integration test 也期待两个独立 `function_call(Bash)`。目标态四个相关测试实跑为 `4 passed`，说明绿灯确认的是 merge 后 oracle，而不是当前用户合同。 | confirmed；`b233751` 是 merge 第二父 `8ac6522` 的 ancestor，merge 相对第二父的完整 path diff直接显示删除与 oracle 反转。mock integration 只证明本代理接线与投影，不冒充真实 upstream shape。 |

测试执行环境为目标 worktree 的 `f97d243f9431d836861ce5e9938605df56b37478`。运行时 `uv` 因隔离 worktree 没有 `.venv` 而创建了一个环境；测试后已将该新建目录原样移动到 `/tmp/agent-a305fd27ed103f27e-venv-created-260906`，没有删除内容，也没有把它留在被评工作树中。

## 结构根因

历史上的双 accumulator 能表达正确行为，但把三类决定压进了同一个 imperative loop：哪些 item 可见、哪个可见 segment 是 barrier、pending run 在每个分支前后何时 flush。`b233751` 为加入 reasoning 顺序而把单 accumulator 扩成两个互相 flush 的 accumulator；`f97d243` 的 merge resolution 随后保留其中一套并整套删除另一套，代码仍可运行、测试也通过，因为 tests 在同一次 resolution 中被改写为新的逐项 oracle。真正缺失的不是一个局部变量，而是一个可单独看见并测试的“visible segments → adjacent runs”语义层。

另一个必须保持独立的职责是 contextual `completed`：是否绿色读取完整 `output_items` 中每一项的 `client_action.requirement` 与 snapshot 是否可用，不能从已经裁剪的 display segments 是否为空反推。否则一个被展示层省略的 `NOT_REQUIRED` item、一个未来被隐藏的 segment 或一次投影错误，都可能改变 status 语义。

## 方案比较

| 方案 | 长期可维护性与职责 | rich facts | 回归可识别性 | 判定 |
|---|---|---|---|---|
| A．恢复 `b233751` 的双 accumulator | 能恢复行为，但 item 选择、barrier、identity、flush 与 rendering 仍纠缠在一个 loop；新增第三种可见 segment 时必须修改多处分支与两个 pending state。历史已经证明其中一套可被整段删除而函数仍成立。 | `ResponseObservation` 本身不丢，但 formatter 过早把事实变成字符串，归约过程不可观察。 | 只能靠最终字符串覆盖每种 flush 组合；merge 时很容易把测试 expected 一起改成回归。 | 不采用为最终结构；可作为行为参照，不作为实现形状。 |
| B．先投影 typed display segments，再做领域专属的相邻归约 | 把事实选择、可见顺序、相邻性、merge identity 与 rendering 分开；归约只比较当前 segment 与结果尾项，不维护两套隐式 pending state。新增 segment 默认是可见 barrier，必须显式声明才能合并。 | 原始 `ResponseObservation.output_items` 不变；segment 在 render 前仍携带 raw type 与 raw names，重复和顺序均保留。 | 可分别断言 atomic projection、coalesced segment tuple 与最终字符串；删除 action merge arm 会在 reducer unit 和 production integration 的同一语义上同时变红。 | 推荐。 |
| C．通用 streaming run reducer，以 `key`／`skip`／`barrier`／`flush` callback 参数化 | 表面复用更强，实际把本领域最重要的区别——“不可见且透明”与“可见且成边界”——摊到多个 callback 的组合约束中。当前只有一个真实调用者，接口复杂度接近实现复杂度，是浅 module；错误 callback 组合会重新制造隐式状态。 | 可以保留，但 caller 往往先编码或过滤以满足 generic key，容易让 display label 反客为主。 | reducer 自身能测，领域组合仍只能在 caller 测；删除某个 callback 或错排过滤顺序仍可能全绿。 | 不采用。 |

## 推荐设计

### 数据形状

在 `src/app/observability/request_log.py` 内定义私有、immutable、typed segment union，先不新建公共 module，也不改 `ResponseObservation`：

```python
@dataclass(frozen=True, slots=True)
class _NamedActionRun:
    raw_type: str | None
    raw_names: tuple[str, ...]  # invariant: non-empty tuple; every name is truthy

@dataclass(frozen=True, slots=True)
class _ReasoningRun:
    kind: Literal["enc", "txt"]
    count: int

@dataclass(frozen=True, slots=True)
class _UnknownAction:
    raw_type: str | None

@dataclass(frozen=True, slots=True)
class _AnonymousAction:
    raw_type: str | None

type _ResponseDisplaySegment = _NamedActionRun | _ReasoningRun | _UnknownAction | _AnonymousAction
```

`_NamedActionRun` 在 atomic projection 阶段先以单个 raw name 构造，归约后才可能持有多个 names。raw type 与 raw names 一直保留到 renderer；这使 identity 与 escaping 的先后关系由数据形状表达，而不是靠注释提醒。`_UnknownAction` 与 `_AnonymousAction` 分型，是为了让“可见但永不合并”的 barrier 成为结构事实，而不是又回到 scattered `flush_*()` 调用。`ResponseObservation.output_items` 仍是逐项、按 `output_index` 排序的权威事实；display segment 是 terminal projection，不回写 durable record。

### 函数接口与职责

1. `_response_status_parts(observation, *, color) -> list[str]` 只处理 terminal event／status／error／incomplete 与 contextual `completed`。它从完整 `output_items` 计算 action presence，绝不读取 coalesced segments 来判绿色。
2. `_display_segment_for_item(item) -> _ResponseDisplaySegment | None` 只做事实到可见 atomic segment 的选择。先识别有可见内容的 reasoning；否则 `NOT_REQUIRED` 返回 `None`；`UNKNOWN` 返回 `_UnknownAction`；`REQUIRED` 且 raw name 为空返回 `_AnonymousAction`；其余返回单名 `_NamedActionRun`。这个顺序明确兑现“可见 reasoning 是 barrier，但不可见且 `NOT_REQUIRED` 的 reasoning 不是 barrier”。
3. `_coalesce_adjacent_response_segments(segments) -> tuple[_ResponseDisplaySegment, ...]` 只读 typed segments 并做相邻归约。它用结果列表尾项与当前项配对，只有两个 merge case：同 raw type 的 `_NamedActionRun` 拼接 raw names；同 kind 的 `_ReasoningRun` 累加 count。其它组合一律 append，因此任何新增的可见 segment 默认断开两边，不会因忘记调用某个 flush 而意外跨越。
4. `_render_response_display_segment(segment, *, color) -> str` 只负责 grammar、`inert_token` 与颜色。action label 从 raw type 单独编码；每个 raw name 分别 `inert_token` 后再把 encoded names 交给 `_painted_tools()`，由 renderer 加逗号与颜色；unknown、anonymous 与 reasoning 各按现行 grammar 输出。
5. `format_response_observation()` 保留现有 public interface，只编排 status parts、atomic projection、adjacent reduction 与 segment rendering，最后返回 parts。`format_completion_line()` 的 ending 优先级与最终空格拼接不变。

这不是把旧状态机换名：旧结构的状态是“当前尚未 flush 的两个 run”，正确性依赖每个分支手工 flush；推荐结构的中间结果是完整、immutable、可检查的 visible segment sequence，相邻归约是一个 total pairwise fold，新 segment 的默认语义是 barrier。删除 named-action merge case 不会留下一个看似完整的单层 formatter，因为 coalesced tuple 的直接测试会立刻显示四个 atomic action segment 未被归约。

### 精确归约规则

- `_NamedActionRun(raw_type=T, raw_names=(a,))` 与紧邻的 `_NamedActionRun(raw_type=T, raw_names=(b,))` 合成一个 run，names 为 `(a, b)`；不去重。
- raw type 比较发生在 `inert_token` 之前。两个不同 raw type 即使截断后 label 相同也不得合并；display label 从不作为 key。
- `_ReasoningRun(kind=K)` 只与紧邻同 kind reasoning run 合并；`txt` 与 `enc` 互相断开。
- `_UnknownAction`、`_AnonymousAction`、不同 raw type action、可见 reasoning 与任何未来新增的可见 segment 均是自然 barrier。
- `_display_segment_for_item()` 返回 `None` 的 item 在归约前消失，因此不可见且 `NOT_REQUIRED` 的 message、server-side action 与无可见内容 reasoning 都不制造伪边界。
- raw name 的“具名”判据沿用当前事实语义：`None` 与空字符串为无名；其它字符串包括空白字符串都是具名，后者会被 `inert_token` 明确编码而不会消失。

### 渲染与 contextual status

`completed` 的绿色判据继续直接读取未裁剪事实：`output_items is not None`，且不存在 requirement 为 `REQUIRED` 或 `UNKNOWN` 的 item。归约只影响 action segment 的呈现，不改变 action presence、unknown、snapshot completeness 或 terminal status。`_NamedActionRun` 的 renderer 输出 `encoded_type(encoded_name_1,encoded_name_2,...)`；括号、逗号与 ANSI 只由 renderer 产生。`_UnknownAction` 继续输出 `client_action?(encoded_type_or_unknown)`；`_AnonymousAction` 输出裸 `encoded_type_or_client_action`；`_ReasoningRun` 继续 dim 显示 `reason(enc:N)`／`reason(txt:N)`。

### legacy fallback 的范围判断

建议把 `format_client_actions()`／`format_terminal_status()` **窄幅纳入本切片**，但只让它们复用 action segment projection、adjacent reducer 与 renderer，不碰 producer、fallback 优先级、`ClientAction` 数据结构或 durable schema。理由不是“顺便清理”：两者渲染的是同一 Responses client-action grammar，且在 rich observation unavailable 时成为用户实际看到的 compatibility path；若主路径分组而 fallback 永远逐项，同一显示合同会随 observation availability 漂移。`ClientAction` 已保留 requirement、raw type、raw name 与顺序，足以投影同样的 action segments；它没有 reasoning facts，因此不伪造 reasoning。该纳入范围直接消除第二套 action rendering 规则，是结构根因的一部分。

不纳入 `format_stop_reason()`、`format_pending_tools()`、Chat completion rendering、footer layout 或 `ResponseObservation`／`response_action` schema。它们不是 terminal Responses output-item sequence 的另一实现，不参与本次相邻归约；改动它们不会降低 `f97d243` 同类 merge resolution 的发生概率。

## 测试入口与可判否 oracle

### Unit 入口

继续以 `tests/unit/observability/test_request_log.py` 为主，但把测试按责任分层，而不是只改最终字符串：

1. projection 测试断言 typed atomic segments：visible reasoning、named required、unknown 与anonymous各产生对应 variant；不可见 `NOT_REQUIRED` items 产生零 segment。该断言不得调用 renderer 生成 expected。
2. reducer 测试直接比较完整 segment tuple：相邻同 raw type named actions 合并并保留重复；visible reasoning、不同 raw type、unknown 与 anonymous 分别断开；不可见 `NOT_REQUIRED` item 因未进入 segment sequence 而不制造边界；reasoning 同 kind 相邻计数。raw type truncation collision 继续使用两个不同长 raw type，expected 为两个 runs。
3. renderer 测试以 raw names `Read,now` 与 `Bash)\x1b` 断言每个 name 先 inert、renderer 后加逗号；颜色开启时完整 action run 由 `_painted_tools()` 按 names 的 attention colour 分 run，但 commas 仍属于 renderer。
4. public formatter 测试硬编码完整尾段，不用 production renderer 生成 expected，并继续同时断言 `ResponseObservation.output_items` 的逐项 index、raw type、raw name、reasoning facts、重复与顺序。这样 display grouping 不能被误写成事实 deduplication。
5. legacy fallback 测试在 `format_terminal_status()` 入口加入两个相邻同 raw type 具名 action、一个 unknown／anonymous barrier 与后续同 type action，确认它与 rich path 共用 grouping rule，但 contextual complete 与 fallback precedence 不变。

关键正确样本可以沿用现有样本而改回当前合同：`function_call(Read)`、不可见 message／server action、`function_call(Bash)` 合成 `function_call(Read,Bash)`；随后可见 `reason(enc:1)` 断开；再出现的 `function_call(Read)` 开新 run。缺陷注入控制应只删除 `_NamedActionRun` 的 merge case而保留 reasoning merge，确认 reducer exact tuple、public formatter exact tail 与下述 integration assertion 都因 action 未合并而在目标字段变红。这个一次性受控检查用于证明判据能抓住 `f97d243` 的失效形状，不建立 mutation framework。

### Integration 入口

直接更新既有 `tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour`，不要另造测试基础设施。它已经从真实 production request 入口走 mock upstream、反序 `done`、terminal `output` authority、collector、`RequestTrace → RequestCompletionCoordinator → format_completion_line` 接线与 contextual green。把精确尾段改为一个 grouped function call run加一个无名 custom action barrier：

```python
assert line.endswith(
    f"completed function_call({DIM}Bash,Bash{RESET}) custom_tool_call"
)
```

该断言同时要求两个 `Bash` 恰好各出现一次、位于同一 action run，且无名 `custom_tool_call` 仍单独可见；继续保留 `completed` 不绿色断言。它证明本代理 production 接线与 display reduction，不证明真实 upstream 必然发出该 mock shape。缺陷控制为仅移除 named-action coalesce case；预期失败必须落在这个 exact tail，而不是 fixture、collector 或颜色设置。

## 迁移范围与顺序

1. 先修订 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 的 display grammar、验收第 7 条与修订记录，明确“事实逐项、显示相邻归约”及所有 barrier／transparent item 规则。该步骤来自项目的 Spec-first 规则，不是可选文档清理。
2. 在 `src/app/observability/request_log.py` 内加入私有 segment types 与 projection／reducer／renderer functions，重构 `format_response_observation()`；随后让 legacy `format_client_actions()` 复用同一 action 路径。保持 `format_completion_line()` 的 public interface、ending precedence 与 contextual status 语义。
3. 更新 `tests/unit/observability/test_request_log.py` 中被 `f97d243` 反转的 test names／expected，并补直接 segment-seam 断言；更新现有 integration exact tail。不要修改 `ResponseObservation`／`OutputItemSummary`／`ClientActionObservation` schema，也不要建立新 proof framework。
4. 实施者按项目惯例运行目标 unit 与 integration tests、Ruff、Pyright；candidate 形成后做一次受控 action-merge-case deletion，核对失败来自 exact grouped segment。完整 regression 属于实现 closeout，不是本只读报告已经执行的证据。

## 承重关系

**前提：**用户本轮当前确认的聚合边界是，只合并连续、同 raw item type、具名且 `REQUIRED` 的 actions；可见 reasoning、不同 action type、unknown action 与无名 action断开；不可见且 `NOT_REQUIRED` 的 item 不制造伪边界。

**它支撑的结论：**推荐设计必须先把 raw items 投影为 typed visible segments、丢弃 transparent items，再以 raw type 对相邻 `_NamedActionRun` 归约，并让所有其它 visible variants 自然成为 barrier；对应 unit 与 integration expected 必须是 grouped display，但 durable observation 仍逐项保留。

**若该前提为假：**如果 invisible `NOT_REQUIRED` item 应断开，则 projector 不能返回 `None`，需要显式 `_InvisibleBoundary` 或改为对 raw item stream 归约，相关“跨 invisible item 合并”测试必须反转；如果 visible reasoning 不应断开，则 reasoning 与 action 不能共用相邻 visible sequence，顺序与测试均会改变；如果 identity 不是 raw type，则 `_NamedActionRun.raw_type` 的 merge key 与 truncation-collision 测试必须改变；如果根本不应聚合，则 named-action merge case、legacy 复用与 grouped integration oracle都应删除。当前没有历史代码或报告可以替代用户对该前提的裁决；`45e7cfb`／`b233751` 只提供它曾如何实现的事实证据。

## 未采用方案与理由

1. **原样恢复双 accumulator。** 不采用，因为它恢复结果却保留了导致本次静默删除的隐式 flush 耦合，无法满足用户要求的根因修复与结构优化。
2. **抽取通用 streaming run reducer。** 不采用，因为当前只有一个 domain consumer，generic callback interface 必须重新暴露 skip／barrier／identity／merge 的全部组合，既不深也不降低误配概率。
3. **先渲染成字符串，再用相邻字符串或正则合并。** 不采用，因为 bounded `inert_token` 会让不同 raw type 产生相同 label，字符串阶段也已无法区分 provider 逗号与 renderer separator；该方案会破坏 raw identity 与 inert encoding 的承重顺序。
4. **只改 integration expected，不新增 segment seam。** 不采用，因为这正是 `f97d243` 的镜像失效：一个 merge resolution 可以同时改 formatter 与最终字符串 oracle，测试依旧绿，却没有任何中间责任告诉评审者哪种语义被删除。
5. **顺带重写 `ResponseObservation` schema 或整个 TUI。** 不采用，因为 durable facts 已足够支持正确 display projection；扩大 schema 不解决 merge 时 action reducer 被删的问题，反而扩大变更面并违反本轮边界。
6. **完全排除 legacy `format_client_actions()`。** 不采用，因为它在 observation unavailable 时渲染同一 Responses client-action grammar，排除会让 grouping 合同依赖数据源可用性。纳入仅复用私有 projection／reducer／renderer，不触碰 producer 或 schema，因此不是无依据的全局重构。

## 搜索面与未覆盖面

已逐条读取 coordinator 清单列出的四个源码／测试绝对路径、TUI Spec、merge-conflict 报告与三个指定 commit；完整检查 `45e7cfb`、`b233751` 的目标 path patch、`f97d243` 相对两个父提交的目标 path diff、commit ancestry、目标最终态文件及主工作树与目标 worktree 的逐字节一致性。额外读取了 production integration test、completion publication call site、legacy `ClientAction` 数据形状与 producer。实跑四个当前 oracle，结果为 `4 passed`。

没有执行完整 suite、Ruff 或 Pyright，因为本轮没有实现 candidate；没有进行源码 mutation，因为只读边界禁止修改被评对象；没有读取整个 TUI、Chat formatter 或真实 upstream capture，因为它们不决定本轮由用户直接给出的 grouping contract。因而本报告能确认当前回归、Spec 冲突与推荐结构的适配性，不能宣称推荐实现已经完成或通过验证。

## 我最没把握的三个判断

1. **legacy fallback 是否应与 rich path 同批迁移。** 我的推荐是纳入，置信度中等偏高，因为它显示同一 Responses client-action grammar，且所需 raw facts 已存在；不纳入会留下 source-availability-dependent 行为。主要不确定性是用户本轮“Responses completion display projection”是否只指 rich observation path。若 coordinator 有更窄的一手 scope，legacy 可以延后，但须在 Spec 明示 fallback 暂不服从 grouping，而不能默默分叉。
2. **typed segment types 应暂留 `request_log.py` 还是立即拆到新文件。** 我推荐先作为同一 module 的 private internal seam，置信度中等。当前只有一个真实主调用者，单独 module 会暴露较大的 type interface；若实施时 legacy 与未来 Chat 已形成第二个真正 adapter，再抽取才有更强 leverage。
3. **是否直接单测 private projection／reducer seam。** 我推荐测，置信度中等偏高，因为本次失效恰好是一个内部归约职责被整体删除而 public expected 同步改写；直接 segment tuple oracle 能提供异层鉴别力。代价是测试对 internal type shape 更敏感，但这正是本轮有意建立并长期维护的结构契约，不是偶然 implementation detail。

## 执行本契约时遇到的摩擦

1. Shell 能看到 worktree 根部存在 `.codegraph` 路径，但 CodeGraph MCP 对该隔离 worktree返回“未索引”，并明确要求本会话不要再次调用；随后改用绝对路径 `Read` 与带目录 gate 的 Git／rg 命令，不影响 revision 绑定。
2. Worktree isolation 拒绝 `Write`／`Edit` 直接修改主工作树下指定报告。为遵守主工作树 `.dev/` 落点，本报告先在 `/tmp/function-call-grouping-structure-review-260906-a1.md` 维护，再以精确单文件 `cp` 更新唯一授权报告；没有修改被评对象。
3. 第一次运行目标测试时，`uv` 在隔离 worktree 新建 `.venv`。该目录确定由本次命令新建，随后被原样移动到 `/tmp/agent-a305fd27ed103f27e-venv-created-260906`，没有删除或覆盖内容。worktree 的 `.dev` 在本次测试后 `git status` 中可见，但其中包含一个既有独立 repository 与大量既有材料，本轮没有把它归因于自身，也没有触碰或清理。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-06T09:32:02+00:00
- finding_total: 2
- confirmed: 2
- likely: 0
- inconclusive: 0
- refuted: 0
- blocker: 0
- major: 2
- minor: 0
- nit: 0
- source_files_modified: 0
- test_files_modified: 0
- spec_files_modified: 0
