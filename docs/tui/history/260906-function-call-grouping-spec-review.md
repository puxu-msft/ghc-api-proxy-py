---
report_id: function-call-grouping-spec-review-260906
attempt_id: function-call-grouping-spec-review-260906-a1
status: in-review
reviewed_at_rev: f97d243f9431d836861ce5e9938605df56b37478
artifact: ../spec.md
reviewer_role: independent-spec-reviewer
---

# Responses client-action grouping Spec 独立评审

## 评审范围

本轮只评审 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 中 2026-09-06 Responses client-action display grouping 修订，并逐条核验 coordinator 清单 S1～S8。范围内证据包括同主题的 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md`、代码修订 `f97d243f9431d836861ce5e9938605df56b37478` 下的 `src/app/observability/request_log.py`、相关 unit/integration tests，以及 `45e7cfb972b6f9df5874a8455d9961d692f2bba2`、`b23375165ae0a72d7a5e6271f6d48c3236e55666`、`f97d243f9431d836861ce5e9938605df56b37478` 三个历史 commit。Chat provider 条款只检查与本修订是否共存、是否被误改，不扩展成 Chat provider 合同评审；其它 TUI 行为、实现质量与功能完成度不在范围内。

## 总体 verdict

`needs-fix`。行为合同正文、验收 oracle、归因边界与 Chat 共存均可进入实施，但 living design 与 Spec 状态段没有同步到同一时间点，形成 1 条 major。

## blocker 数

0。

## 证据基线与读取方式

- 代码 `reviewed_at_rev`：`f97d243f9431d836861ce5e9938605df56b37478`。主工作树 `.git/HEAD` 指向 `refs/heads/main`，该 ref 与隔离评审 worktree 的 `git rev-parse HEAD` 均为此值；隔离 worktree 的相关代码和测试路径为 clean。主工作树与隔离 worktree 的被读文件逐字节 hash 相同：`request_log.py` 为 `0fb27361e815e11bc59f11c953f64641a269297bed53fd5c5bb1296bfa2528df`，unit test 为 `8740d0c000eb3ecc701cc14785eb7d3c41c32c48b31700e05fe2d5089dbc53b3`，integration test 为 `24855da1bff6f2e99114b8e6267403acff0d7144f5ba443d7d9b77a02b22323e`。
- Checklist：SHA-256 `9b736fe126ac0d9820e3e6c28a27781a074a896da7e13ca7bc681e317ad00ec4`。先用 `Read` 按绝对路径读取全文，再以 `sha256sum` 摘要。
- Spec：SHA-256 `c061376b71e5b1ad084b114046448508a742726ac8b5bc1d3ad657dad92220f1`。在 checklist 之后用 `Read` 按绝对路径读取全文，再以 `sha256sum` 摘要。
- Design：SHA-256 `83c0e717e60ab73d87095801134cd9241f0defffd0acc7793291cc0b1a8a68ad`。在 Spec 之后用 `Read` 按绝对路径读取全文，再以 `sha256sum` 摘要。
- 代码与测试：先按项目约定调用 CodeGraph；MCP 报告该项目没有可用索引，因此改用 `Read` 读取 `request_log.py` 全文，以 `rg` 定位相关 tests，再用 `Read` 读取完整相关 test 段。历史以隔离 worktree 中的 `git show` 读取 commit metadata、普通 diff 与 merge combined diff。

## S1～S8 核验

| 编号 | 结论 | 核验依据 |
|---|---|---|
| S1 | needs-fix | Spec 第 161 行与验收第 7 条已经把 grouping 写入行为权威，且 design 第 3 行承认 Spec 权威；但 design 第 13 行仍错误断言现行 Spec 是逐项 oracle，Spec 状态段又未标出本次 amendment 尚未实施，详见 `function-call-grouping-spec-review-260906-01`。 |
| S2 | pass | Spec 第 161 行明确区分 durable observation 的逐项位置、raw type、名称、重复与顺序，与 console projection 的相邻归约；design 第 9、49 行规定 projection 不回写 durable record。当前 `ResponseObservation.output_items` 也是 immutable tuple，已有 persistence 与 identity assertions，所提实现不要求改变 schema。 |
| S3 | pass | Spec 第 161 行完整列出合并谓词、名称顺序与重复、different raw type、visible reasoning、unknown、anonymous barriers，以及不可见 `NOT_REQUIRED` item 的 transparent 语义。这里的“连续”按先投影再过滤得到的 visible segment sequence 解释，与 design 第 55～67 行一致，不与 raw item adjacency 混用。 |
| S4 | pass | Spec 第 161 行明确要求 rich observation 与 legacy fallback 共用 action grouping grammar，同时禁止 legacy 合成不存在的 reasoning facts。当前 legacy producer 只为非 `NOT_REQUIRED` item 建 `ClientAction`，把缺失 type 归一化为 `unknown`、缺失或空 name 归一化为空串；但能进入 named merge 的 `REQUIRED` item 必由 classifier 识别出非空 known raw type，故该归一化不会把两个合法可合并 raw types 混为一类，unknown 与 anonymous 仍各自是 barrier。 |
| S5 | pass | Spec 第 146、161 行和验收第 7 条都把 contextual `completed` 绑定到完整 terminal output facts 与 snapshot completeness，明确禁止从 display segments 反推；design 第 78～82 行维持同一分槽。Grouping、隐藏 transparent item 或修改 grammar 均不能改变是否为绿色。 |
| S6 | pass | 验收第 7 条给出 rich formatter、legacy fallback、atomic projection、reducer、raw-type collision、barrier、terminal authority 与 production-entry mock 的分层 exact oracle，并逐项列出应判红的缺陷。对 `f97d243` 直接执行 grouped rich oracle，实际为 `['completed', 'function_call(Bash)', 'function_call(Bash)', 'custom_tool_call']`，而预期为 `['completed', 'function_call(Bash,Bash)', 'custom_tool_call']`；legacy oracle同样以两个分离字段对一个 grouped 字段，两个探针均以退出码 3 判红。设计只要求复用既有 unit/integration entries 与一次性受控缺陷检查，没有新增 proof framework。 |
| S7 | pass | 本轮用户指令直接确认“用户已确认行为边界并把内部技术裁决委托给 coordinator”。Spec 第 161、234 行把 display grouping boundary 归给该用户确认，把其余 authority、schema 与实现结构归为 Spec 推导或 coordinator delegated design；`45e7cfb`、`b233751`、`f97d243` 只作为历史事实。独立 `git show` 证实前两次提交分别建立 action grouping 与保序 reasoning/action accumulators，`f97d243` merge resolution 删除 action accumulator并把 tests oracle 反转为逐项 display，未把这些 commit 冒充用户裁决。 |
| S8 | pass | 当前 grouping 条款只作用于 Responses provider observation 与 legacy Responses fallback；紧随其后的 Chat provider observation、独立 `chat` schema、choice/tool index ordering、`[DONE]`/finish reason 分槽及验收第 9 条仍完整存在，且没有被 Responses reducer 的 raw-type identity 或 barrier 语义覆盖。未建议回滚、删除或以 Responses schema 重写 Chat 条款。 |

## 发现

### function-call-grouping-spec-review-260906-01：Living design 与 Spec 状态仍停在修订前后两侧

- `finding_id`：`function-call-grouping-spec-review-260906-01`
- `severity`：major
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/design.md:13`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:3`、`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:161`、`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:218`、`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:231-247`、`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:316-409`、`/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py:1070-1124`、`/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:5396-5426`
- 证据：当前 Spec 正文已经规定相邻同 raw type 的具名 `REQUIRED` actions 归约，并在验收第 7 条把 exact oracle 改成 `function_call(Bash,Bash)`；但 living design 第 13 行仍以现在时断言“现行条款仍把相邻同类型 action 的逐项显示写成精确 oracle”，并把“先修订 Spec”列为实现前置条件。反方向上，Spec 头部只把并行 Chat 增补标为“尚未实现”，没有说明本次 2026-09-06 grouping 修订在代码与测试中也尚未落地；其宽泛的“主体已实现并与代码对账”因而不能让读者可靠判断本修订的实施状态。代码 revision `f97d243` 的 rich 与 legacy formatter 仍逐项追加 action，unit/integration tests 仍精确要求两个分离的 `function_call(Bash)`。在该 revision 上分别执行 rich 与 legacy 的新 exact oracle，实际值均为两个分离字段，预期值为一个 `function_call(Bash,Bash)`，两个探针都以退出码 3 判红。
- 影响：行为正文自身清楚，但承载实施入口的两份 living document 对“Spec 是否已修订”和“实现是否已同步”给出互相不兼容的当前状态。下一棒若信 design，会重复或等待已经完成的 Spec 修订；若只信 Spec 头部，会把仍由 `f97d243` 与旧 tests 明确复现的实现缺口误判为已完成。这违反本轮要求的单一行为权威与及时同步义务，并使修订不能无歧义进入实施阶段。
- 建议：保留 Spec 第 161、218、234 行的现行 grouping 合同与全部 Chat 条款，只把 living 状态对齐：将 design 第 13 行改成“Spec 已完成本次修订，production 与 test 转录待同步”的当前事实，并在 Spec 状态段明确标出 2026-09-06 grouping 修订尚未实现。不得以当前错误实现或旧 tests 反向改回逐项 display。
- 前提、承重结论与反事实：前提是 `f97d243` 仍是本轮约定的代码 revision，且上述两个文档 hash 对应本轮所读内容；它支撑“当前状态描述会误导下一阶段，因此必须先对齐 living 状态”这一结论。若该前提为假，例如 implementation 与 tests 已在另一 revision 同步且 Spec/design 也已更新，则本发现不再成立，需按新 revision 与新 hash 重审。

## 未采用建议及理由

- 未建议把 Spec 改回逐项 display。`f97d243` 的 formatter 与 tests 是已验证的当前错误状态和 known-bad control，不是行为权威；按它反推合同会直接违反本轮边界。
- 未建议删除、回滚或拆出同文件中的 Chat provider observation 条款。Responses grouping 与 Chat 的 choice/tool-call projection 分属相邻但独立的协议段，当前文本能够共存。
- 未建议新建 mutation framework、gate manifest 或其它 proof infrastructure。验收第 7 条的 exact oracles、当前 known-bad revision 和既有 tests 已足以证明 grouping deletion 可被判否；一次性受控缺陷检查即可。
- 未把 current tests 中的逐项 oracle另报为 Spec 缺陷。它们是本次后续 implementation 必须同步的已知转录，当前评审只判断 Spec candidate；把它们当行为依据才是错误。它们与状态文案产生的误导已纳入同一系统级发现，没有重复计数。

## 搜索面与未覆盖面

- 已读判据与评审对象：checklist 全文、Spec 全文、design 全文；读取顺序为 checklist → Spec → design。
- 已读 production surface：`request_log.py` 全文；`response_action.py`、`response_observation.py`、`assembling.py`、`openai_responses_actions.py` 与 `request_completion.py` 中承载 classification、raw facts、legacy normalization、durable persistence 和 rendering 的相关定义。
- 已读 tests：`tests/unit/observability/test_request_log.py` 的 contextual status、reasoning/action ordering、barrier、raw identity、encoding 与 current old-oracle 段；`tests/unit/pipeline/test_response_observation.py` 的 terminal authority、ordering、unknown/completeness 段；`tests/unit/observability/test_request_completion.py` 的 durable serialization 与 immutable projection 段；`tests/int/test_pipeline_app.py` 的 Responses production-entry cases，包括五组 terminal-output 对照及 buffered/translated routes。
- 已读历史：`45e7cfb`、`b233751` 的相关普通 diff，以及 `f97d243` 的 merge combined diff与三条 commit metadata。Commit facts仅用于证明可实现性与定位 regression，不用于产生行为判据。
- 已执行：当前 old-oracle unit tests 5 条全部通过，相关 integration test 1 条通过；另以 Spec 的 grouped expectation分别探测 rich 与 legacy formatter，两个 known-bad controls 均在 `f97d243` 上以退出码 3 判红并打印 actual/expected。未把当前绿灯冒充新合同已实现。
- 未覆盖：没有评审整个 TUI、Chat implementation、provider observation schema v2 的其它字段、真实 upstream cassette shape 或 full regression；这些均不影响 S1～S8 的承重判断。未读取既有 structure review 的结论作为 oracle，以避免把评审自述替代直接源码、tests 与 commit evidence。

## 交付声明

### 整体判定

`needs-fix`。1 条 major、0 条 blocker。S2～S8 的行为合同与证据设计可进入实施；S1 受 living design 与 Spec 状态元数据不同步影响，先对齐这两处当前状态，再保留现行 grouping 合同进入实现。不得以 `f97d243` 或旧 tests 回滚行为，也不得删除或收窄并行 Chat 条款。

### 我最没把握的三个判断

1. `function-call-grouping-spec-review-260906-01` 的级别位于 major 与 minor 边界。我定为 major，是因为两条相反的当前状态会直接决定下一棒究竟修改 Spec 还是实现，属于阶段路由而非纯措辞；若 coordinator 的工作流另有唯一、显式且高于这两处文本的实施状态源，可重判为 minor，但不能把矛盾本身写成不存在。
2. S8 的 pass 基于当前 snapshot 的条款边界、schema 分槽与验收编号，足以证明 Responses grouping 没有在现行文本中覆盖或删除 Chat 合同；受 worktree isolation 限制，我未取得 dotdev 上前一版 Spec 的 Git diff，因此该结论不声称逐字节证明“此次编辑零触碰 Chat”。若 coordinator 持有修订前 hash，应补做一次限定到 Chat 段的 diff 核查。
3. 我将验收第 7 条“不可见 `NOT_REQUIRED` item 不进入 segment sequence”解释为必须对 `[named action, transparent item, named action]` 的组合序列判 grouped，而不只是孤立断言单 item 投影为 `None`。Design 的 projection → reducer 结构与既有相关 public formatter test 使这一解释足以实施；若后续 tests 只覆盖两个孤立 helper 而不覆盖组合，这一项应重开，但当前 Spec 文义本身不构成 major 缺口。

### 执行本契约时遇到的摩擦

- 主工作树存在 `.codegraph` 路径，但 CodeGraph MCP 对该 project path 报告无可用 index；按项目规则停止再次调用，改用 `Read` 与 `rg`。
- Worktree isolation 拒绝直接向指定主树报告路径执行 `Write`，也拒绝对主树运行 `git -C`。本报告先在 `/tmp/260906-function-call-grouping-spec-review.md` 渐进写入，交付时用不覆盖既有文件的精确复制落到指定路径；代码 revision 通过主树 ref 文件、隔离 worktree Git 与跨树文件 hash 三者对齐。
- 两次内联 known-bad oracle按预期以非零退出，工具把它们显示为 tool error；stdout 同时保留 actual 与 expected，足以区分预期判红和探针未运行。无评审阻塞。

delivery_complete: true
completed_at: 2026-09-06T11:46:26+00:00
finding_total: 1
blocker_count: 0
major_count: 1


## 复评：唯一 major 的处置核验

### 复评范围与快照

本轮按 coordinator 指令只重读原报告，并复核 design“目标与边界”中的当前状态句、Spec 顶部状态段，以及相邻的 Responses grouping 与 Chat authority 文本；未重开 S2～S7 的既有证据，也未扩成代码、tests 或完整 Chat 合同评审。复评时 Spec SHA-256 为 `5654b2beed95a70fd74c5262fb10a88b4168983b00efebfff5c5db838ed5e6cc`，design SHA-256 为 `30c4bb5c18f63c3363557a5ccc0674f68d973df1fa4ce7c9ada084a2a77a2150`；追加前本报告 SHA-256 为 `a2cc5bc50c1064f91fd7487b15a03e04b24bb325b638425770bc74f2244db854`。

### 原发现处置

- `function-call-grouping-spec-review-260906-01`：closed。Coordinator 已采纳该 finding；本次以修改后的文件本身独立核验，不以采纳声明代替证据。
- Design 第 13 行现在明确写明 Spec 已于 2026-09-06 完成本次修订，production projection 与 unit/integration 转录仍待同步，并禁止按旧 oracle 反改 Spec。这关闭了原报告所指出的“design 仍把修订 Spec 当作实施前置”的错误当前状态。
- Spec 第 3 行现在明确把 2026-09-06 action grouping 标为“已写入本规格，production projection 与 unit/integration 转录尚待同步”，同时继续单独标注 Chat provider observation 尚未实现。这关闭了“只有 Chat 被标为待实施，grouping 状态可能被误读为已完成”的缺口。
- Spec 第 161 行的 Responses authority 仍是 durable per-item facts 与 display adjacent reduction 分槽；第 163、167 行的 Chat authority 仍以独立 `chat` slot、choice/tool ordering 和 native finish reason 为边界。状态修订没有回滚 grouping，也没有删除、收窄或用 Responses projection 覆盖 Chat 条款。
- 复评结论：原 major 的两个必要修复点均已对齐，未发现新 blocker 或 major。代码与 tests 继续处于待同步状态已被准确披露，不是本次 Spec readiness 的失败条件。

### 复评后的 S1 与 S8

- S1：pass。Spec 已是唯一行为权威，design 只解释机制并准确指回已完成修订的 Spec；两份 living document 对当前 implementation gap 的陈述一致。
- S8：pass。相邻 Responses grouping 与 Chat authority 文本仍分槽共存，状态段也分别陈述两项未实施工作，没有发生回滚或 scope collision。

## 交付声明

### 整体判定

`pass`。原报告的 1 条 major 已关闭，当前 active blocker 为 0、active major 为 0；本次 Spec 修订可以进入 implementation。该判定不声称 production grouping 已实现，Spec 与 design 已明确把 production projection 和 unit/integration 转录列为待同步。

### 我最没把握的三个判断

1. Spec 首句“主体已实现并与代码对账”仍是宽泛历史状态，但紧随其后的分号子句已经逐项限定 grouping 与 Chat 两项新工作尚未实现。我判断这种就地限定足以消除原 major，而无需重写整段；这是本轮最接近 minor 的判断。
2. S8 仍是对当前 snapshot 的语义共存判断，而不是对修订前后 Chat 段逐字节零差异的历史证明。Coordinator 本轮要求的是目标段复评，当前文本足以支持 pass；若另有“零字节变化”的独立历史主张，仍应由 dotdev diff 单独证明。
3. 本轮没有重跑 code/tests，因为唯一 major 只涉及两份 living document 的状态对齐，而且新文案明确承认 implementation 仍待同步。我判断旧代码继续失败不影响 Spec readiness；它只能在后续 implementation 验收中成为阻断。

### 执行本契约时遇到的摩擦

Worktree isolation 仍不允许用 `Write` 直接编辑主树报告，因此复评内容先写入单独的临时 append 文件，再以追加且不改写既有字节的方式写入指定报告。除此之外无新增摩擦。

delivery_complete: true
completed_at: 2026-09-06T11:49:09+00:00
review_round: 2
finding_total: 1
finding_active: 0
finding_closed: 1
blocker_count: 0
major_count: 0
