# 五条项目复查原则与待办优先级复查

- `report_id`：`project-principles-backlog-review-260903`
- `attempt_id`：`260903-backlog-principles-gpt-opus-1`
- `status`：调查主体已完成，必读 checklist 缺失导致契约性阻塞
- `reviewed_at_rev`：`e1b2baa99637349d2f552343c57769a311bfb179`
- `.dev` 快照说明：所有 `.dev/**` 路径与其中的报告锚都指本次读取时的当前工作树快照，而不是 `reviewed_at_rev` 的内容；`.dev` 是独立仓库，不受主仓 revision 跟踪，读取到的 `.dev` 分支为 `dotdev`、HEAD 为 `019b36be32a961b402c320b7f0af1ede4b90cca3`，但本次因隔离边界未取得其工作树是否含未提交改动的证明。
- 调查边界：只读检查主仓实现、测试、Spec、活文档与全部 11 份 `.dev/docs/**/deferred.md`；唯一主动写入主工作树的是本报告。一次 `uv run` 在本调查的隔离 worktree 自动创建了 `.venv`，未触及主工作树，详见“执行本契约时遇到的摩擦”。

## 整体判定

**没有发现比 `direct-passthrough/deferred.md` D-5 更应优先、同时无需用户裁决的根因修复项。结论强度：足以据以排序，但不是不可推翻的绝对结论。**

D-5 仍由当前真实入口直接证实：`src/app/pipeline/delivery_policy.py:57-72` 的 `carries_upstream_natively()` 只放行 `OPENAI_RESPONSES`，Anthropic 直连腿仍走 `AnthropicAssembler` + `AnthropicFramer` 的解析与重成帧；该腿又是 Claude 系模型当前可达的主路径。D-5 已有用户裁决，修复形态也已确定，且它是 D-6 的前置依赖、D-7 的同片载体。与之相比，本轮找到的最强竞争项 F-01 已在当前 `/responses` 直连腿上可达，但失败后果限于可观测侧把“出现过 reasoning”误报成缺席，不改变客户端拿到的原生事件；既有计划也把可观测迁移列在接线之后。用户给定的排序轴——真实入口、已有裁决、失败后果、依赖顺序与根因闭合度——共同支持 D-5 保持第一。

这不是说其余候选可以忽略。F-01 是当前真实违背，适合紧随 D-5 的同主题后续；`upstream/retry-and-continuation/deferred.md` §16 是当前 served 次要路径上的语义缺陷，适合独立排在观测清理之前；D-6 必须在 D-5 后立即接上；D-7 应并入 D-5，而不是作为 D-5 之后才发现的补丁。

## 五条原则逐条复查

### 1. `one-reply-fact-one-answer-across-both-reply-modes`

**新增违背：F-01。既存结构违背：F-02。退役条件：不成立。** 当前不但没有把两种模式合成一条，反而新增了 native passthrough 这一种处理模式；原则的重要性上升而非下降。

Skill 原命令在当前 revision 不能完整运行：`src/app/pipeline/delivery/assembler.py` 与 `src/app/server/handler.py` 已不存在，`Terminal` 迁至 `delivery/assembling.py`，whole-body reader 迁至 `pipeline/reply.py`，真实 HTTP 入口迁至 `server/routes/inference.py`，吸收器在 `observability/request_trace.py`。原命令的失败输出已人工追到当前符号后重跑数据流检索。

#### F-01

- `finding_id`：`PPR-260903-01`
- `severity`：`major`
- `primary_location`：`src/app/pipeline/delivery/passthrough.py:164-201`，主仓 `e1b2baa99637349d2f552343c57769a311bfb179`
- `related_locations`：`src/app/pipeline/delivery/assembling.py:28-59`、`src/app/pipeline/delivery/formats/openai_responses.py:492-514,566-683`、`src/app/observability/request_trace.py:182-193`、`.dev/docs/direct-passthrough/spec.md:661-667`、`.dev/docs/direct-passthrough/plan.md:68-72,89-91`；`.dev` 引文版本按报告头的快照说明。
- 证据：`PassthroughAssembler` 在 item `done` 时只做 `self._terminal.blocks += 1` 与 `_saw_client_action = True`，从不调用 `Terminal.record()`，也没有等价的 native item 分类器。因此 `Terminal.thinking` 与 `Terminal.tools` 留在类默认值。`RequestTrace.absorb()` 随后把这些默认值当实际摘要复制到完成记录。用 `tests/int/cassettes/anthropic_to_responses_stream.json` 与 `history_responses_stream.json` 的录制帧分别喂给 `ResponsesAssembler` 和 native `PassthroughAssembler`，两份录制上 translating 侧均得到 `thinking=['enc']`，native 侧均得到 `thinking=[]`；terminal、usage 与 item 数其余部分一致。该结果不是手写 upstream fixture 推断。
- 当前失败场景：同一份真实 Responses 回复经 Anthropic 翻译腿时，完成行能显示 `reason(enc:1)`；经当前已上线的 `/responses` native 直连腿时，完成行把同一 reasoning 事实呈现为缺席。客户端原生事件仍完整，错误发生在 operator-facing 记录；一条“没有 reason”记录与“native reader 没有读 reason”同形。
- 根因层：native item 的 typed observable facts 没有进入统一摘要模型；实现为了避免把 `CompletedBlock` 强加给 native wire，正确地拆开了交付载体，却把“旁路分类”一起遗漏，只留下 block 计数和一个布尔值。根因不是缺一条日志，而是两种模式没有共用同一个事实判定入口。
- 建议：落实现有 Spec §10 与 plan 的可观测迁移，给 native dialect/item 建 typed side facts，并让 `Terminal` 或其替代摘要类型拥有唯一分类入口；共享事实的回归测试应对同一录制输入比较 translating 与 native 两侧摘要，而不是各自钉字面量。不得从摘要反推或改写 native wire。
- 结论强度：**足以直接行动。** 两份独立录制给出同一反例，源代码解释了确定性机制，且 Spec 已规定目标行为。优先级低于 D-5 的理由只来自影响面与既有依赖顺序，不削弱缺陷成立性。

#### F-02

- `finding_id`：`PPR-260903-02`
- `severity`：`minor`
- `primary_location`：`src/app/server/routes/inference.py:217-260`，主仓 `e1b2baa99637349d2f552343c57769a311bfb179`
- `related_locations`：`src/app/observability/request_trace.py:169-193`、`.claude/skills/project-review-principles/SKILL.md` 的 C2 判据。
- 证据：`count_tokens` 成功出口仍直接执行 `trace.usage = {"input_tokens": tokens}`，不经过 `Terminal` 或任何同形 reply record；更新后的检索只得到这一处 `trace.<reply-field> =`。这是 skill 首次真实复查已识别的结构形状，在当前 revision 仍成立，只是位置从旧 `pipeline_app.py` 移到了 `routes/inference.py`。
- 当前失败场景：今天的 `format_tokens` 对这一个键仍能正确渲染，因此没有复现即时错误；失败面是下一次给统一 reply usage 增加键、换算或来源标记时，count 出口不会被类型或调用图要求同步，继续以“当前恰好够用”的局部字典绕开共同入口。
- 根因层：token-counting 被当作“没有 reply”后直接写展示记录，领域事实与展示载体耦合，统一摘要没有表达 count response 的构造入口。
- 建议：在不伪装为完整上游 reply 的前提下，为 count response 建具名、同源的 usage observation 构造器，再让 `RequestTrace` 吸收；不要仅把这一行换成另一行赋值。若设计确认 count 的事实所有权与 reply 本就不同，则应修订原则的定义域与 C2，而不是保留“明知违背但无害”的永久例外。
- 结论强度：**结构事实足以排期，运行危害只是趋势。** 它不应抢在 D-5 前面。

### 2. `assertions-about-copilot-wire-need-a-recorded-counterpart`

**新增违背：none。退役条件：不成立。** 仓库仍对 Copilot wire 作断言，录制基建职责仍在本仓。

当前候选计数依次集中在 `tests/int/test_pipeline_app.py`、`tests/unit/protocols/test_responses_anthropic_nonstream.py`、`tests/unit/pipeline/delivery/test_stream_delivery.py`、`tests/unit/pipeline/delivery/test_sse_assembly.py`、`tests/unit/pipeline/translation_driver/test_translation_driver.py` 等。人工分诊按“期望值归谁所有”而不是按键名：这些手写结构绝大多数验证本项目的转换、缓冲、拒绝、frame parsing 与兼容 reshape；涉及 Copilot 真实 id 漂移、web search item、usage 结构与 event order 的断言已有 `tests/int/cassettes/` 对应物，且现有测试明确区分手写合同夹具与录制事实。Skill 的 cassette 解析脚本在本次 revision 实跑，三份 terminal usage 分别为 `history_responses_stream.json` 的 56919/637、`responses_web_search_stream.json` 的 4693/112、`anthropic_to_responses_stream.json` 的 12/19，并保留各自 details；本报告不把这些点时数字外推为频率或全集。

没有采纳的可疑候选包括：`test_responses_passthrough.py` 中的 hand-written `response.completed`，因为断言对象是本项目的 grouping/reshape 合同，测试还明确把未被录制的 `done` without `added` 标成开放问题；`test_responses_stop_reason.py` 的 `output` fixture，因为 expected status mapping 归本项目 Spec；`tests/e2e/claude/_upstream.py` 的结构，因为它是 mock provider 输入而非“Copilot 实际发什么”的证据。未发现靠印象替代已有 cassette 的新期望。

### 3. `declined-and-adopted-findings-can-share-one-blind-spot`

**新增违背：none。退役条件：不成立。** `.dev/docs` 仍广泛使用逐条“采纳／不采纳”处置，A 侧本次有大量命中，结构前提仍存在。

本次 A/B 配对的 B 侧仍主要集中在 graceful-shutdown 的 `refused_requests`／`severed_connections` 事故及其复盘；活 README 已把 `severed_connections` 明写为下界，并逐字写出零不意味着没人受损。`hooks-subscription-migration/reports/260822-session-closeout.md` 的 beta flag 计数盲区也已在当次处置中补上边界。没有找到一个新的组合，其中新增量声称覆盖某片领地、而同轮明确放弃的代价又落在其结构盲区却未被写在量旁边。

不采纳的候选包括 `direct-passthrough/plan.md` 的作废 v1、各 topic 对方案的“不采纳”与 graceful-shutdown 的历史重复命中：前两类没有与 B 侧当前观测量形成同一领地的配对；后一类是原则的成因及已写清边界的既知实例，不是当前新洞。没有把“再加一个计数器”当修法。

### 4. `a-broken-test-needs-its-scenario-and-expectation-rechecked`

**新增违背：none。退役条件：不成立。** 自上次真实复查锚 `61f06a1` 至 HEAD，仍有 74 个“改生产源码且修改既有测试文件”的候选提交，其中 17 个按原模式删除了同步 `def test_...`；改写既有测试的做法显然没有消失。

人工先分诊删除整条 test 的 17 个高风险提交，再检查 assertion 不动而 fixture/helper 变化的候选。高风险样本中，`1fb37cd` 把“unknown item 应拒绝”反转成“native 腿原样交付”，同时新增 translating/native 两侧守卫并在 test docstring 写清旧场景为何不再是合同；`bc46776` 的三条旧 Device Flow 场景分别被 provider-aware 场景替代；`c4216f7` 的两条旧 502 断言被 direct/translated 两种 error carrier 测试替代；`0ebdfd0`、`62a457f` 明确重塑了 h2 guard 的可见命题；`2248a69` 把“旧链不被新链拖入”替换成“归档链不可 import”。未发现“夹具换干净后原层守卫归零”的当前实例。

本轮没有把 74 个提交逐一做 mutation；结论来自 diff、替代测试集合与当前真实调用层的人工对账，因此只支持“本轮未发现新违背”，不支持“所有改写测试都具备完备分辨力”。命令本身还有 `async def test_...` 漏检，详见摩擦；补扫找到的 `c796396` 正是上一轮已经修好的正例，它把只走 SDK 自动折叠 header 的 Anthropic 腿改为双腿参数化，并在 docstring 记下旧绿来自 SDK 而非修复。

### 5. `explanation-does-not-belong-on-a-surface-that-is-read-as-a-promise`

**新增违背：none。既存未清项：F-03。退役条件：不成立。** 本仓仍自己产出 operator/client-facing 字符串与 callable contract docstring。

Skill 指定的三条命令均实跑。旧的 `composition.py` SOCKS 命中已不在当前候选中；另外三处既有真违背仍保留。`docs/.human-controlled/` 已经进入主仓历史，旧前提“未被 git 追踪，故只查实现端”不再成立；补扫得到 10 个因为／实测类候选，人工判断均为用户亲笔文档中的裁决理由、可行动配置说明或模块归属说明，没有把它们列为我方可改项。即使其中某句未来需要调整，也因权威与修改边界而需要用户处理，不符合本任务的“无需用户裁决”筛选。

#### F-03

- `finding_id`：`PPR-260903-03`
- `severity`：`minor`
- `primary_location`：`src/app/pipeline/delivery/blocks.py:23-24`，主仓 `e1b2baa99637349d2f552343c57769a311bfb179`
- `related_locations`：`src/app/pipeline/subscribers/server_tools.py:266-271`、`src/app/pipeline/subscribers/blank_text.py:111-114`、`src/app/model_provider/ghc_client/errors.py:30-57`。
- 证据：`DeliveryError` docstring 仍说 upstream failure “is retryable”，但当前 `RETRYABLE_STATUSES` 只覆盖具名集合，是否真的 retry 还由 budget 与 position 决定；这正是 skill 自带的正样本。两个 runtime log string 仍分别说“upstream would have rejected them”与“which upstream accepts”，同源解释已经在紧邻代码注释中完整保留，端点字符串却继续替外部上游作结局断言。
- 当前失败场景：调用方从 `DeliveryError` docstring 推出“非 delivery failure 都会 retry”，或运维从日志把一次本代理改写读成稳定 upstream guarantee；上游契约或 retry policy 改变时，真正拥有结局的代码已经变了，这三个承诺面仍可独立过期。当前没有证据表明它们已导致客户端行为错误。
- 根因层：rationale 被从中间带复制到承诺面，且以不拥有该结局的主语写成断言；事实本身有价值，落点错误。
- 建议：只撤回端点上的越权结局，保留邻近注释中的依据；`DeliveryError` 只陈述 delivery-side identity，不替 retry policy 下结论；日志只陈述本模块实际执行的 flatten/empty 动作。不要因此删除测量或上游事实。
- 结论强度：**足以做低风险清理。** 这是既知未清项，不是比 D-5 更高的根因工作。

## 候选排序与未采纳理由

| 顺位 | 候选 | 是否需要用户裁决／真实样本 | 当前可达性与失败后果 | 根因闭合度 | 本轮结论 |
|---|---|---|---|---|---|
| 1 | `direct-passthrough/deferred.md` D-5 + 同片 D-7 | 不需要；用户已裁形态 | Anthropic 直连主路径可达；不先解决就不能在保持续写的同时启用 native | 高，机制与候选 2 已定 | 保持第一；D-7 并入本片 |
| 2 | F-01：native passthrough side facts | 不需要 | `/responses` direct 当前可达；误报 reasoning/tool 缺席，wire 不受影响 | 高，Spec §10 与两份 cassette 已闭合 | 不抢 D-5；排在同主题后续，不能降格成“加日志” |
| 3 | `upstream/retry-and-continuation/deferred.md` §16 | 不需要 | `/responses` client + Anthropic upstream 当前 served；`refusal` 被写成 `completed`，`max_tokens` 丢原因 | 高，修法与反向已有切片同构 | 有现实语义错误，但属于次要方向，未超过 D-5 的主路径与用户裁决权重 |
| 4 | `direct-passthrough/deferred.md` D-6 | 不需要 | Anthropic native 腿接线前不可达，接线后可重试失败会漏掉 replay | 高，但硬依赖 D-5 | D-5 后立即做，不能提前冒充 D-5 的替代 |
| 5 | `auto-mode-classifier/deferred.md` D-1 | 不需要 | auto mode 命中时可达；完成记录虚构 upstream protocol／bytes | 中高，`synthesized` carve-out 已有 | 当前环境 auto mode 不命中，且仅观测面；低于 D-5 |
| 6 | `tui/deferred.md` 0 与 0.5 | 0 不需裁；0.5 的承载方式仍有设计岔路 | 非 Anthropic 入站摘要缺失；usage inconsistency 或 parse error 无记录 | 0 高，0.5 中 | 次要入口或观测信号，均不高于 D-5 |
| 7 | F-02、F-03 | 不需要 | 当前主要是漂移风险与误导性承诺 | 中高 | 小片清理，不因工作量小而前移 |
| 8 | `ghe-device-flow/deferred.md` D-2、`multi-provider-routing/deferred.md` D-1、auto-mode D-3 | 不需要 | 分别是重复构造的未来漂移、fail-closed 配置卫生、失实注释／fixture 能力 | 中高 | 都是合理候选，失败后果与入口权重不足以超过 D-5 |

以下候选明确不参与“无需裁决、现在可根因闭合”的竞赛，但仍记录未采纳理由：

- `direct-passthrough` D-3／D-4、error-envelope E-1／E-2／E-3／E-9、delivery-keepalive 的错误帧时机、multi-provider D-3／D-4、server-layout D-B、h2-goaway 1／2 等都触及用户已拥有的产品取舍，排除。
- `direct-passthrough` D-2／D-9、error-envelope E-10／E-12、h2-goaway 4／5、auto-mode D-2 等等待真实样本；其中 D-9 已把“重复 done”降到 warning 观测，直接过滤会改变 native 承诺，排除。
- retry-and-continuation §17、multi-provider D-2、retry §8g 等当前不可达且没有近期解锁条件；不因修法看起来小而提前。
- retry-and-continuation §21 的 silent-drop 清单有用户“已知不处理不能静默”的裁决，但它提出的是观测处理，不是丢失内容的根因修复；本任务明确禁止把加日志当作根因闭合，因此不提升。
- direct-passthrough Spec §9.1 的响应头工作有当前行为价值，但 O-1 仍由用户裁黑名单对 Responses 客户端的定义域，且既有 plan 把它作为独立后续；本轮不把“裁决前取并集”的过渡规则扩张成“无需裁决即可宣告最终闭合”。
- `client-leg-formats/deferred.md` D-5 是历史完成声明与当前源码不符的文档对账，不是当前产品根因；另一条启动探测行为也需先核后续裁决来源，均不与直连 D-5 争优先级。

## 我最没把握的三个判断

1. **F-01 仍排在 D-5 后。** 证据对缺陷成立性很强，对优先级只有中高：本轮没有 `/responses` 与 Anthropic direct 的真实流量占比。若当前运营事实是 `/responses` direct 远高于 Claude 直连，排序可能反转；现有项目优先级与用户对“所有直连路径”的裁决使 D-5 暂时胜出。
2. **retry §16 不超过 D-5。** 它是 current served 的错误 terminal semantics，单次失败后果比 F-01 重；我把它排后只因它是反方向次要路径，而没有当前流量基线。这一判断是“足以暂排”，不是“无需再看”。
3. **原则 4 本轮为 none。** 我人工深查了 74 个候选中的 17 个删除 test 场景与 fixture-only 高风险形状，并补扫 `async def`，但没有对全部改写测试逐个做 mutation。这个证据足以说“未发现新违背”，不足以说“每条测试都有分辨力”。

## 执行本契约时遇到的摩擦

1. 必读 checklist `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-checklist.md` 在两次独立存在性检查中均为缺失，`fd` 对 `.dev/docs` 搜索 `project-principles|backlog-review|review-checklist` 也零命中。用户陈述“已落盘”与文件系统当前事实冲突；我无法逐条读取并满足 coordinator 的额外核查要求。这是本次 `VERDICT: blocked` 的唯一契约性阻塞。
2. 原则 1 的命令路径已腐坏，原样运行以 `ModuleNotFoundError` 与两个 `No such file` 失败；人工追到当前真实符号后才完成判定。Skill 应更新 `assembler.py → assembling.py`、`handler.py → reply.py/request_trace.py`、`pipeline_app.py → routes/inference.py`，否则下一次会把空输出误读成干净。
3. 原则 4 文本说 `SINCE` 可填 commit，但给出的命令使用 `git log --since="$SINCE"`，该选项接收日期而不是 revision range；本次使用已知真实复查锚 `61f06a1..HEAD` 做等价扫描。隔离 harness 又拒绝执行包含循环的复杂 git Bash，即使 cwd 是本 worktree，因此用 Python `subprocess` 在精确 checkout `e1b2baa...` 上复现同一筛选。
4. 原则 4 的模式只匹配同步 `def test_`，漏掉 `async def test_`。补扫确实找到 `c796396` 对 async test 场景的改写；它是已修好的正例，不改变本轮结果，但证明漏检不是理论问题。
5. 原则 3 的命令当前输出 51 KiB，包含原则报告对自身命令的自指命中与大量历史报告噪音；仍可人工配对，但“命令给候选”已接近需要先按 topic／时点分诊的边界。
6. 首次为 F-01 使用真实 cassette 做只读探针时，`uv run` 在隔离 worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a082bdaa6a35b6a87/.venv` 自动创建并安装了环境。它不在主工作树，也没有改 source/test/Spec/deferred/status/report 之外的主树文件；由于任务只授权写报告且没有授权删除，我没有自行清理该隔离产物。

7. 作为 leaf executor，本会话不得派生 reviewer；本报告尚未获得独立的 0 blocker／0 major 评审。用户指定 coordinator 在返回后逐项核查，因此这道门移交 HANDOFF；尾部完成标记只表示本 attempt 的报告已经封口，不表示调查合同为 pass。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-03T08:53:14+00:00`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 1`
- `minor_count: 2`
- `contract_blocker_count: 1`

## 合同补核与追加更正

本节于 fallback checklist `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-checklist.md` 当前工作树快照读到后追加；该文件位于 harness job scratch，不受主仓 `reviewed_at_rev` 或 `.dev` revision 跟踪。前文作为首次交付的点时原文保留；与本节冲突的称谓、依赖顺序与契约状态，以本节及文末最新一份交付声明为准。

### 两处称谓与依赖顺序更正

1. **同意 coordinator 对主产品路径的纠正。** 项目 `CLAUDE.md` 的权威原文是“主产品路径是 Anthropic Messages input served through an OpenAI Responses upstream”。前文把 Anthropic direct 称为“主路径”不成立，特此撤回。准确说法是：Anthropic direct 是 Claude 模型的关键可达 route；它因 `claude-sonnet-5` 等模型不支持 Responses API 而承载重要真实流量，但它不是项目定义的 primary product path。这一更正作用于前文“整体判定”、候选排序第 1 行及所有据“主路径”给 D-5 加权的句子。
2. **同意 coordinator 对 D-6 顺序的纠正。** D-6 可以在 D-5 的基础设施完成后作为独立 semantic commit 实施，不需要与 D-5 压成一个提交；但它必须在 D-5 被宣告对外完成、尤其在 Anthropic native selector 启用之前闭合。前文“D-5 后立即做”若读成“D-5 已对外完成之后再做”就是错的，现更正为：`D-5 infrastructure → D-6 mapping → enable Anthropic native selector / declare D-5 externally complete`。D-7 仍属于 D-5 自身的续写合同，不能留到 selector 启用后。

两处更正降低了 D-5 的“primary path”权重，也把 D-6 从 successor 调整为 pre-enable dependency，但没有翻转总体排序。F-01 仍只改变 `/responses` direct 的 operator-facing side record，不改变 client wire；retry §16 仍是 served 的反方向次要 route。D-5 则已有用户明确裁定、关系到 Claude 模型关键可达 route 上 native 与续写能否同时成立，并且是 D-6／D-7 收口序列的载体。**在当前缺少各 route 流量占比的条件下，结论仍是“未发现足以排在 D-5 之前的无需裁决根因项”，但理由不得再写成“D-5 位于主产品路径”。**

### Checklist 逐项补核

| Checklist 项 | 补核结果 | 依据／需更正处置 |
|---|---|---|
| 机械 1：报告、尾部声明与计数 | pass | 报告存在；本节之后追加新的尾部声明。三条 finding 为 F-01 major、F-02 minor、F-03 minor，故 `finding_total=3`、`blocker=0`、`major=1`、`minor=2`，人工反算为 3；调查只读，三条均保持 open |
| 机械 2：revision 与跨报告 provenance | pass | 实际代码检查的 exact checkout 与主仓 ref 当时均为 `e1b2baa99637349d2f552343c57769a311bfb179`；报告头已明确全部 `.dev` 引文不受主仓 revision 跟踪，并记录读取到的 dotdev HEAD 与工作树状态限制；fallback checklist 的非 Git 身份在本节首段补明 |
| 机械 3：五项命令、当前命中、人工判定、退役 | pass | 五项均有当前运行与人工判定，补充当前命中数如下；每项均明确退役条件不成立 |
| 机械 4：事实／判断／用户裁决分离 | pass | 三条 finding 分列证据、失败场景、根因、建议与结论强度；候选表单列是否需裁决／样本。D-5 形态源自用户裁决，D-6 源自 Spec 推导层，F-01 源自 Spec §10，retry §16 源自既有双向 terminal contract |
| 机械 5：首选的失败场景、入口、根因、射程与时机 | pass after correction | F-01 完整覆盖这些字段，但总体首选仍是既有 D-5。前文错误的 primary-path 理由由本节撤回，改为 Claude 模型关键可达 route + 已裁合同 + pre-enable 依赖闭包 |
| 机械 6：至少三个未选候选与理由 | pass | 排序表列出 F-01、retry §16、D-6、auto-mode D-1、TUI 0／0.5 等；其后另按需裁决、等样本、不可达三类排除，并明确日志不是根因闭合 |
| 机械 7：只改自己的报告 | pass with disclosed isolated side effect | 主工作树唯一主动写入是本报告；未改实现、测试、Spec、deferred/status 或既有报告。`uv run` 在 agent 隔离 worktree 自动建立 `.venv`，已在摩擦中披露，未触及主工作树被评审对象 |
| 内容 1：纳入 count-tokens | pass | F-02 点名 `routes/inference.py:238` 的直接 `trace.usage` 出口 |
| 内容 2：按期望值归属分诊 wire fixture | pass | 原则 2 明确按 owner 分诊，列出三个不采纳候选与理由，没有把全部 hand-written fixture 判错 |
| 内容 3：A/B 人工配对 | pass | 当前保存输出为 A 121 行、B 35 行；人工跳过 self-reference，剩余 B 主要归 graceful-shutdown 既知事故与 hooks-subscription 已闭合实例，没有找到新配对洞 |
| 内容 4：从真实复查锚扫描 broken tests | pass | 使用 `.dev` 报告给出的 `61f06a1..HEAD`，得到 74 个候选提交、17 个同步 `def test_` 删除提交；另补出原命令漏掉的 `async def` 改写，并人工判定 |
| 内容 5：两条件 + tracked human docs | pass | 原则 5 按“可行动 + 主张归属”判；`git ls-tree HEAD docs/` 非空，补扫 human-controlled 文档并明确我方不可改边界 |

机械 3 的当前命中补充如下，均来自首次扫描保存的输出或当时直接输出，未在本次合同补核中重跑五项扫描：

- 原则 1：旧命令因两条路径迁移失败；当前符号追踪得到两个 `trace.absorb(...)`、一个 count 直接写出口，以及 F-01 所述 passthrough 与 translating 两套摘要生产者。人工判定为一条新 major 与一条既存 minor，退役否。
- 原则 2：候选文件行数依次为 18、12、12、8、6、2、2、1、1；cassette 解析得到三份各自的 current terminal usage。人工判定 `none`，退役否。
- 原则 3：A 121 行、B 35 行。人工配对后 `none`，退役否。
- 原则 4：真实锚范围 74 个候选提交，17 个同步 test 删除提交，另有原模式漏掉的 async test 改写。人工判定 `none`，退役否。
- 原则 5：实现端命令一 17 行、命令二 30 行、命令三 19 处，tracked human docs 补扫 10 行。人工判定新增 `none`、既存 F-03，退役否。

### 合同状态更新

原交付声明中的 `contract_blocker_count: 1` 是 checklist 缺失时的点时状态，fallback 文件现已读取并逐项补核，故该 blocker 已关闭。报告仍含 3 条未修 finding；这是只读调查的预期结果，不是调查合同的 open item。独立采纳／驳回与最终优先级处置仍由 coordinator 按 checklist 的“独立对账”执行，不影响本调查 attempt 由 blocked 更新为 pass。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-03T08:55:49+00:00`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 1`
- `minor_count: 2`
- `open_count: 3`
- `contract_blocker_count: 0`
- `contract_open_count: 0`
- `supersedes_completed_at: 2026-09-03T08:53:14+00:00`

## 独立复审后的追加更正

本节依据独立复审 `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-general-sonnet.md` 与 coordinator 处置账 `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-disposition.md` 追加；两者都是本次读取时的 harness job scratch 快照，不受主仓 `reviewed_at_rev` 或 `.dev` revision 跟踪。处置账已采纳原报告三条 finding 与复审三条 finding，且无被否决建议。前文与本节冲突时，以本节及文末最新交付声明为准；历史文字不覆写。

### 更正一：Anthropic native selector 的完成前置还包括现行 signature reshape

此前补核把 D-7 与 D-6 纳入 selector 前置，却把 direct-passthrough D-4 整体归入“需用户裁决”，因而漏掉了其中已经裁定的一半。**当前 `signature_delta` reshape 的保留无需再等用户裁决。** `direct-passthrough/spec.md` §2.7 已要求 native 接线不得改变今天生效的 reshape 默认值；当前默认仍开启，并由 `AnthropicFramer` 执行。若 selector 切到 passthrough 而未在该路径保留等价、具名的 reshape，Anthropic direct 会在 selector 首次启用时发生回归。

准确的完成边界是一组前置集合，而不是强行压成一个 commit：D-5 的 continuation carrier／terminal ordering 与同片 D-7、D-6 的 Anthropic failure mapping、以及当前 signature reshape preservation 都必须在 **enable Anthropic native selector／宣告 D-5 对外完成** 之前闭合；它们可以在基础设施之后按语义分别提交，彼此没有证据支持的全序不在本报告中制造。**D-4 仍待用户裁的只是长期合同**——保持“默认开、可关”，还是改成“常驻、不可关”；该长期分叉不构成这次保留现行默认所需的新授权。

### 更正二：候选全集补入 hosted web search D6 与 `empty_result`，D-5 只保留条件性首选

原候选表遗漏了 primary product crossing 上两项已经裁定但未实现的 hosted web search backlog，因而“没有比 D-5 更优先项”的写法过强。

- **hosted web search D6**：用户已裁定把 Responses `web_search_call` 还原为 Anthropic `server_tool_use` + `web_search_tool_result` 块对；当前 streaming 与 non-streaming 仍把它降成 text。它位于项目定义的 primary product crossing，feature 默认关闭会降低当前权重，但显式启用是 served path，启用即给出错误 carrier，不能从候选全集删除。
- **`empty_result`**：用户已裁定这一种约束失败策略，但当前 schema 仍只有 `error`／`drop_fields`，实现也把其余值落入 drop 行为。它尚不可配置，因此当前失败射程弱于 hosted web search D6，但仍是已裁未做项。

修订后的排序不是无条件全序：**在没有已记录的近期 hosted-search rollout／启用计划时，D-5 是中等置信的暂定首选。** 理由是 D-5 有更新且明确的用户裁决，关系到 Claude 模型关键可达 route，并承载 selector 前的 continuation／failure mapping／signature reshape 依赖闭包；F-01 只错 operator-facing side record，retry §16 属反方向次要 route，而 hosted web search 当前默认关闭。若 coordinator 掌握近期启用 hosted web search 的运营事实，应立即重比 hosted D6 与 D-5；在那种条件下，D6 位于 primary product crossing 且启用即错 carrier，完全可能升到 D-5 之前。`empty_result` 因当前不可选暂排其后。

因此，前文“足以据以排序”“共同支持 D-5 保持第一”以及任何可读成无条件全集否定的句子全部收窄为上述条件命题。本报告支持的是中等置信偏好，不支持在缺 route traffic 与 rollout 事实时锁死全序。

### 更正三：F-01 的 cassette 证据只实证 reasoning parity

两份 cassette 的经验覆盖应逐项说准。`anthropic_to_responses_stream.json` 与 `history_responses_stream.json` 都只含 reasoning item 与 message item，没有 function／custom／client-action tool item。它们直接实证的是：同一 recorded response 在 translating producer 上得到 `thinking=['enc']`，native producer 上得到 `thinking=[]`，所以 reasoning parity 失败。

`Terminal.tools` 的缺口同样成立，但证据来源不同：当前 `PassthroughAssembler` 对 done item 只增加 `Terminal.blocks` 并更新 `_saw_client_action`，不调用 `Terminal.record()`，也没有等价的 native item observation 写入口；`RequestTrace.absorb()` 又无条件复制默认空 `tools`。这是源码控制流证明，不是上述两份 cassette 的经验对照。前文“Spec §10 与两份 cassette 已闭合”现收窄为：**两份 cassette 闭合 reasoning 反例；源码控制流同时证明 tool classification 入口缺失。** 不据未出现于录制的 item 类型扩大 cassette 权重。

### 本轮复审处置状态

原报告三条 finding 均被 coordinator 采纳，但本任务只调查与订正文档，没有实施修复，因此它们仍是 `open`：PPR-260903-01 major、PPR-260903-02 minor、PPR-260903-03 minor。`adopted` 表示处置方向获采纳，不等于实现已闭合。复审提出的三条报告 finding 已全部由本节回应；是否达到复评终态由独立 reviewer／coordinator 继续核验。没有新的合同 blocker。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-03T09:04:48+00:00`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 1`
- `minor_count: 2`
- `open_count: 3`
- `closed_count: 0`
- `adopted_count: 3`
- `contract_blocker_count: 0`
- `contract_open_count: 0`
- `review_correction_total: 3`
- `review_correction_addressed_count: 3`
- `supersedes_completed_at: 2026-09-03T08:55:49+00:00`
