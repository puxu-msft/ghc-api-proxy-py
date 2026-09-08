---
report_id: function-call-grouping-design-review-260906-2
attempt_id: function-call-grouping-design-review-260906-a2
status: in-review
target_rev: f97d243f9431d836861ce5e9938605df56b37478
reviewed_at_rev: f97d243f9431d836861ce5e9938605df56b37478
role: independent_design_reviewer
artifact: /home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md
checklist: /home/xp/src/ghc-api-proxy-py/.dev/docs/tui/reports/260906-function-call-grouping-design-review-checklist.md
---

# Responses completion display projection 独立设计评审

## 评审范围

本轮只评审 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md` 中“Responses completion display projection”设计是否满足核查清单 C1～C9，重点核对 merge-time partial deletion 的结构根因、现有数据形状、rich／legacy grammar seam、Spec 权威归属及测试分层。范围内源码为目标 revision 的 `src/app/observability/request_log.py`、`src/app/pipeline/response_observation.py`、`src/app/pipeline/delivery/assembling.py`、`src/app/pipeline/response_action.py`、legacy producer `src/app/pipeline/delivery/formats/openai_responses_actions.py` 及相关 unit／integration tests。范围外是实现、源码／测试／Spec／设计正文修改、整个 TUI 或 schema 重写、production cutover 与提交。

## 基线与读取方式

目标源码与测试从隔离 worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a1cca44412648de76` 读取；`git rev-parse HEAD` 得到 `f97d243f9431d836861ce5e9938605df56b37478`，故 `reviewed_at_rev` 与目标 revision 相同。历史形状通过同一 object database 的 `git show` 与 `git diff` 读取。开发文档从主工作树的绝对路径读取；本轮快照 SHA-256 分别为 checklist `3a43fecdd306e36305dfad9502aa6632958eaf471b577db6ce69aff324a2ddad`、design `568edf4e78b24417c2c6efb1d0be3dc5801b81055cafe7407080f8c32ebed775`、spec `76ab4dea3e50328709b898444d10cb3d079f3c12dd4a5c5aa0eef5c3d92161c1`。CodeGraph MCP 无法识别隔离 worktree 的索引，因此在首次尝试后依其返回要求改用绝对路径 `Read`、`rg` 与 revision-bound Git 命令。

## 判据来源与决定归属

用户本轮裁决的是可观察行为边界：只合并连续、同 raw item type、具名且 `REQUIRED` 的 actions；可见 reasoning、不同 raw type、unknown 与无名 action 是 barrier；不可见且 `NOT_REQUIRED` 的 item 不制造 barrier。用户把内部技术裁决委托给 coordinator。Typed segment 的具体 union、pairwise reducer、private helper 边界及 legacy adapter 形状均是 agent 在受委托范围内作出的设计判断，不是用户亲自选择；本报告按长期正确性重新判断这些技术选择，不把历史实现或 agent rationale 冒充用户裁决。

## 整体判定

`needs-fix`。Typed visible segments → adjacent reduction → rendering 的内部结构能够把 selection、barrier、raw identity 与 rendering 分槽，适配目标 revision 的 rich facts，并可让 rich 与 legacy 路径共用 action grammar 的 reducer／renderer；但设计一面声明现行 `spec.md` 是唯一行为权威，一面提出与该 Spec 精确 oracle 相反的 grouping 行为，却没有把“先在同一 change 修订 Spec、验收转录与修订记录”写进自身边界。该缺口会直接允许实现再次绕过 Spec，故有 1 条 major。

## Blocker 数

0。

## 发现

### function-call-grouping-design-review-260906-2-01：设计没有显式承接现行 Spec 中与 grouping 相反的精确 oracle

- finding_id: function-call-grouping-design-review-260906-2-01
- severity: major
- conclusion_strength: confirmed
- criteria: C1、评审要求 6；并影响 C8 的 Spec transcription 闭包
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md:3,13,55-76,90-101`
- related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:151-163,210-220,230-237`；`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md` 的 Spec-first 与 transcription 同步规则；`tests/unit/observability/test_request_log.py:785-855,1070-1241`；`tests/int/test_pipeline_app.py:5396-5426`
- evidence: `design.md` 第 3 行声明 `spec.md` 是行为权威，第 13 行又把“描述回复的用词跟随上游”和验收第 7 条作为本机制的权威条款；同一设计第 55～76 行要求连续同 raw type 的 `_NamedAction` 合并，第 94～101 行要求 grouped reducer／public／integration oracle。当前 Spec 第 161 行仍描述 terminal output 中“同一类型的每个调用保留重复”，更有判别力的是第 218 行精确要求 `completed function_call(Bash) function_call(Bash) custom_tool_call`；修订记录第 235～237 行继续把逐项 action 展示称为现行合同。目标 revision 的 unit 与 production-entry integration tests 与该精确 oracle 同形，本轮在 revision-bound worktree 运行 5 个相关 unit tests 与 `test_terminal_output_drives_both_action_list_and_completed_colour`，结果 `6 passed`。Design 全文没有指出这是一处当前已知冲突，也没有写明必须在同一 change 先修订 Spec 的 display grammar、验收第 7 条与修订记录，再同步生产代码和测试转录。
- impact: 用户本轮的新行为裁决决定冲突方向应当是修订 living Spec，而不是保留旧逐项 grammar；但在 Spec 尚未修订时，设计当前写法让实施者只能把设计正文当作事实上的新行为权威，或先改代码／测试再追补 Spec。两条路径都违反项目明确的 Spec-first 与“转录同 change 同步”义务，并使后续读者继续引用一份作者已知不准确的权威源。这是公共行为合同与实施顺序缺陷，定为 major。
- recommendation: 在设计的目标／边界或迁移顺序中明确记录当前冲突，并规定同一 change 的第一步修订 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md`：把 durable observation 的逐项、重复、顺序保留与 display projection 的相邻 grouping 分开；同步改写验收第 7 条的精确尾段及修订记录；只有随后才实现 typed segment、更新 unit／integration 转录。该修订的行为边界来自用户本轮裁决；typed segment 的具体形状和 helper 分层仍应标为 coordinator 在授权范围内采用的 agent 设计判断。
- bearing premise: 前提是用户本轮已改变可观察 grouping 边界，而项目规则指定 living Spec 为唯一行为权威。它支撑“设计必须显式安排 Spec-first 同步修订”的结论；若前提为假，grouping 本身就不能实施，typed reducer 与 grouped tests 也应撤回，而不是让 design 覆盖 Spec。

## C1～C9 对账

| ID | 结论 | 依据 |
|---|---|---|
| C1 | 不通过 | `design.md:3,13` 正确命名 Spec 为唯一行为权威，但 `design.md:55-76,94-101` 的 grouped grammar 与现行 `spec.md:218` 精确逐项 oracle 冲突，且设计没有承接同 change 的 Spec-first 修订，见 finding `function-call-grouping-design-review-260906-2-01`。 |
| C2 | 通过，但收窄“raw”声称 | Rich carrier 的 `OutputItemSummary` 在 `response_observation.py:157-165,372-379,705-735` 保留 `output_index`、`str | None` type／name、reasoning facts 与 requirement，足够支撑 projection。Legacy `ClientAction` 在 `assembling.py:41-48` 保留 requirement、顺序及 display-relevant type／name，但 producer `openai_responses_actions.py:17-38` 已把 missing／empty／non-string type 归一成 literal `"unknown"`，把 missing／empty／non-string name 归一成 `""`，所以它并不保留这些 raw absence distinctions。该损失不阻断当前设计：legacy 中两种 type 情形都带 `UNKNOWN` requirement、不得合并并按同一 `client_action?(unknown)` grammar 渲染；两种 name 情形都属于 anonymous。Adapter 必须按 requirement 选 segment variant，把存储的 `"unknown"` 当 label，而不能仅凭该字符串猜测 requirement。无需改 schema。 |
| C3 | 通过 | `design.md:55-61` 先识别有 readable／encrypted facts 的 reasoning，再跳过其余 `NOT_REQUIRED`，与 `response_action.py:49-59`、`request_log.py:306-313,382-408` 的实际分类／可见性相容。由此 visible reasoning 进入 segment sequence 成为 barrier，而不可见 message、server action 与空 reasoning 在 reduction 前消失。 |
| C4 | 通过 | `design.md:28-47,63-67` 把 named、reasoning、unknown、anonymous 分成 closed union 中的不同 variant，reducer 只允许 `_NamedAction` 同 raw type及 `_Reasoning` 同 kind 两个显式 merge case；其余当前与未来可见 variant 走 append，默认是 barrier。相比 `b233751` 的两个 pending accumulator 与 scattered flush，这把完整 atomic sequence 先落成值，再做 total pairwise fold，消除了新增／删除一个 accumulator 时必须同步维护多处分支 flush 的结构耦合。它不能也不声称阻止有人同时改坏实现与 oracle；C8 的异层测试负责识别这种回归。 |
| C5 | 通过 | `design.md:49,65,69-74` 明确以 raw type 比较 identity，之后才逐个 `inert_token(raw_name)`，最后由 `_painted_tools()` 加 delimiter 与 ANSI。目标源码 `request_log.py:279-303,434-455` 证明空白字符会成为显式 `\\uXXXX`，不会被 renderer 吞掉；raw name 为 `None` 或精确空字符串才 anonymous，与 rich 及 legacy producer 的现有具名判据一致。该内部边界足够，无需新增用户行为合同。 |
| C6 | 通过 | `design.md:78-82` 明确 contextual `completed` 直接读取完整 `ResponseObservation.output_items` 与 snapshot availability，不读 segments。它保持目标源码 `request_log.py:328-363` 的三态判读：`output_items is None` 不完备，任何 `REQUIRED`／`UNKNOWN` action 阻止绿色，只有已观察且 action-free 才绿色。 |
| C7 | 通过 | `design.md:84-88` 把 legacy 限定为 rich observation unavailable 时的现有 fallback，要求 adapter 生成同一 action segment并复用同一 reducer／renderer，不改 producer、优先级或 durable schema。目标代码 `request_log.py:620-640` 证明该 fallback 是同一 completion ending slot；`ClientAction` 数据足以兑现当前显示合同。把 variant 选择再收成共享 `_action_display_segment(requirement, raw_type, raw_name)` helper 会更明确，但 typed union 加 shared reducer／renderer 已建立足够的 grammar seam，未发现需要扩大为 schema 改造的 major。 |
| C8 | 通过（设计层） | `design.md:90-101` 分别给出 atomic projection、reducer tuple、renderer、public formatter、legacy fallback 与 production-entry integration oracle，并限定一次性删除 named merge arm的受控检查，不建立 proof framework。现行基线的 5 个相关 unit tests与 1 个 production-entry integration test实跑为 `6 passed`；这只确认 `f97d243` 当前逐项 oracle 与接线，不冒充尚未实现的 grouped candidate。实现后仍须执行设计指定的受控 deletion 才能证明新 oracle 对本次失效形状有分辨力。 |
| C9 | 通过 | `design.md:103-109` 完整记录并说明不采用双 accumulator、callback 通用 reducer、渲染后字符串合并、schema 重写及排除 legacy fallback；这些理由分别对准结构耦合、浅抽象、raw identity 丢失、无关扩大与 source-availability-dependent 分叉。 |

## 对根因与数据形状的总判断

在目标 revision 下，`b23375165ae0a72d7a5e6271f6d48c3236e55666` 的 formatter 同时维护 action run 与 reasoning run，并靠多个 `flush_tool_run()`／`flush_reason_run()` 分支保持顺序；`f97d243f9431d836861ce5e9938605df56b37478` 相对第二父提交的 diff 删除完整 action-run 状态与所有 action flush，只留下 reasoning run，同时把 unit oracle 改成逐项输出。推荐设计把“先得到完整 atomic visible sequence”和“再对相邻 pair 归约”变成两个可直接观察的阶段；删除 action merge arm不会再留下半套 pending-state protocol，也会使 direct reducer oracle 与 public／integration tails 同时改变。该结构足以针对已观察根因行动，且没有扩成整个 TUI 或 schema 重写。

现有数据形状也足够。Rich path 保留逐项事实且按 `output_index` 排序；legacy path 虽已归一化 absence，但当前 grammar 不需要恢复被归一掉的区别。Whitespace-only name 在两个 producer 路径都仍是具名字符串，默认 `inert_token(limit=120)` 会逐字符输出 `\\u0020` 等显式转义，因而不会形成空白不可读槽。结论限于当前 requirement 与 display grammar；不把 legacy carrier 称为逐字 raw 的通用事实仓。

## 未采用建议

1. **不要求为 legacy missing type 与 literal `"unknown"` 改 schema。** 该区别已在 producer 边界归一化，但两者在当前 contract 中都是 `UNKNOWN` barrier 且呈现相同；恢复它不会改变本轮 grouping 正确性。若未来要把 provenance 本身展示出来，应先修改 Spec，再另行扩展 carrier。
2. **不把“必须新增共享 `_action_display_segment()` helper”升级为 finding。** 让 rich 与 legacy adapter 都显式调用一个 action-only projector会进一步收紧 seam，但设计已经要求它们产出同一 typed variants并共用唯一 reducer／renderer；目前没有可复现的行为分叉。Coordinator 可把 helper 形状作为实现选择，不应被写成用户裁决。
3. **不要求把 `_response_status_parts()` 抽成独立函数。** 独立 status helper 能进一步减少同文件 merge overlap，但承重义务是 status 直接读取完整 observation、display pipeline 通过显式 reducer 调用；现有设计已写清这两点。把具体 helper 数量升级为公共设计义务没有足够证据。
4. **不要求真实 upstream cassette 或新的 mutation framework。** 本轮裁决的是 presentation reduction，对 upstream shape 的依赖已由现有 carrier tests覆盖；production-entry mock适合证明本代理接线。一次性删除 merge arm的受控检查足够验证 oracle，不应扩成长期 proof infrastructure。

## 搜索面与证据边界

按规定顺序先读 coordinator checklist，再读设计，随后读现行 TUI Spec及目标 revision 的三个必读源码文件。为核对数据形状与真实调用链，额外读取 `src/app/pipeline/response_action.py`、`src/app/pipeline/delivery/formats/openai_responses_actions.py`、`src/app/observability/request_completion.py:1139-1153`，以及 `tests/unit/observability/test_request_log.py`、`tests/unit/pipeline/test_response_observation.py`、`tests/unit/pipeline/delivery/test_responses_passthrough.py`、`tests/unit/observability/test_request_completion.py`、`tests/unit/observability/test_request_log_file.py` 与 `tests/int/test_pipeline_app.py` 的相关区段。还读取了结构评审 `260906-function-call-grouping-structure-review.md` 及其 disposition，并用 Git object重新核验 `45e7cfb972b6f9df5874a8455d9961d692f2bba2`、`b23375165ae0a72d7a5e6271f6d48c3236e55666`、`f97d243f9431d836861ce5e9938605df56b37478` 的 formatter 与 merge-parent diff；引用前一报告只作线索，本报告的结论以本轮独立读取为准。

在目标 worktree 上使用主工作树既有 Python 3.14.2 virtualenv，并以目标 worktree 的 `PYTHONPATH` 运行 5 个相关 unit node和 `tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour`，结果为 `6 passed`、`1 warning`。该运行证明这些既有 tests在 `f97d243` 上确实认证逐项输出；它不能证明尚未实现的 typed design，也不能证明真实 upstream shape。本轮没有执行 full suite、Ruff 或 Pyright，因为没有 implementation candidate；没有做 mutation，因为评审边界禁止修改被评源码／测试，而设计已把受控 deletion 明确安排到实现后。

## 我最没把握的三个判断

1. **是否应把缺少共享 action-only projector 单列 major。** 最终没有单列，置信度中等。最强反对理由是 rich projector 与 legacy adapter仍可能复制 requirement→variant 规则；支持当前设计的理由是两者已经被要求产出同一 closed segment union，并共用 reducer 与 renderer，且现有数据形状下没有能导致可观察分叉的反例。若实施 diff 出现两套独立的 unknown／anonymous／named 分支，应在 code review 时重新升级。
2. **Typed segment 是否“消除”而不只是“降低”原 merge 风险。** 判为满足当前根因，置信度中等偏高。它确实消除了两个 pending runs与 scattered flush 的局部协议，并使归约成为单独可观察的 total fold；但任何结构都不能阻止一次 merge 同时错误修改实现与所有 oracle。这里的结论只覆盖已观测的 partial deletion 机制，不宣称对任意错误 merge 形式完备。
3. **Spec 冲突定为 major 而非 blocker。** 判为 major，置信度高。它阻止设计直接进入实施，但不阻止本轮评审完成，也不要求用户重新裁行为；在同一 change 先修订 living Spec即可解除。若 coordinator 的下一阶段会跳过 Spec 修订直接实现，则该流程状态应被 gate 阻断，但不改变本发现的产品影响定级。

## 执行本契约时遇到的摩擦

1. 首次 `Read` checklist 时误传空 `pages` 参数，工具拒绝且未读取任何内容；随后用合法参数读取，因此仍满足“先 checklist、后设计”的顺序。
2. Shell 可见隔离 worktree 根部存在 `.codegraph` 路径，但 CodeGraph MCP 判定该 worktree 未索引，并要求本会话不要再次调用；后续改用绝对路径 `Read`、`rg` 与 revision-bound Git 命令。该限制不影响 revision 绑定或结论。
3. Worktree isolation 阻止 `Write` 直接写主工作树报告。报告先增量写入 `/tmp/260906-function-call-grouping-design-review-2.md`，再仅精确复制到用户授权的新路径；未创建或覆盖原尝试路径，未修改源码、测试、Spec 或设计正文。
4. 一次试图用 heredoc运行数据形状探针的 Bash 调用被 worktree guard在执行前拒绝；所需事实随后直接由 producer／carrier 源码与既有 tests闭合，没有把未执行命令算作证据。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-06T11:25:59+00:00
- finding_total: 1
- confirmed: 1
- likely: 0
- inconclusive: 0
- refuted: 0
- blocker: 0
- major: 1
- minor: 0
- nit: 0
- source_files_modified: 0
- test_files_modified: 0
- spec_files_modified: 0
- design_files_modified: 0
- report_files_created: 1

## 复评 2026-09-06

### 复评范围与读取方式

按 coordinator 指示先重读本报告，再仅检查 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md`“目标与边界”及相邻权威声明，没有重开 C2～C9 或扩成全量评审。修订后 design 的 SHA-256 为 `83c0e717e60ab73d87095801134cd9241f0defffd0acc7793291cc0b1a8a68ad`；目标代码基线仍为 `f97d243f9431d836861ce5e9938605df56b37478`，本轮未重新评价代码。

### function-call-grouping-design-review-260906-2-01 复评

- status: closed
- evidence: `design.md:3` 继续明确 `spec.md` 是唯一行为权威，`design.md:13` 现已逐项写明现行 Spec 的逐项 action oracle 与 2026-09-06 用户行为裁决冲突、旧 oracle 不授权 design 取代 Spec，并规定 implementation change 必须先修订 Spec 的行为条款、验收第 7 条与修订记录，再同步修改 production projection 及 unit／integration 转录；最后一句明确三类载体必须在同一 change 内一致。
- assessment: 整改完整覆盖原 finding 的三个承重缺口：已知冲突被显式化，Spec-first 顺序被写成实施前置，Spec／production／tests 的同 change 状态闭包被写明。相邻的 `design.md:3` 与新增第 13 行没有争夺权威：第 3 行仍将可观察行为归于 living Spec，第 13 行只记录当前冲突与修订工序，没有把 typed segment 形状提升为用户行为合同。用户裁决仍只覆盖 grouping 行为边界；typed segment、reducer 与 adapter 继续是 coordinator 受委托范围内的 agent 技术判断。
- result: 原 major 已关闭，没有残留 blocker 或 major。

### 复评后的整体判定

`pass`。唯一 major 已按原 recommendation 关闭；限定复评范围内没有新发现。根据 coordinator 的停止条件，本轮不因可能存在的 minor wording preferences继续拖长评审。

### 复评未采用建议

无新增建议。Coordinator 已采纳原 finding，没有驳回项；本轮不重新打开原报告中已明确不采用的 schema 扩展、额外 helper 强制或 proof framework 建议。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-06T11:29:03+00:00
- review_round: 2
- verdict: pass
- finding_total: 0
- historical_finding_total: 1
- closed_finding_total: 1
- blocker: 0
- major: 0
- source_files_modified: 0
- test_files_modified: 0
- spec_files_modified: 0
- design_files_modified_by_reviewer: 0
- report_files_created: 1
- report_files_appended: 1
- count_basis: `finding_total`、`blocker` 与 `major` 统计本轮复评后仍未关闭的发现；历史唯一 finding 由 `historical_finding_total` 与 `closed_finding_total` 保留。
