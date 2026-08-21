# `project-review-principles` skill 评审报告

## 结论

**Verdict：needs-fix。** 当前文本的召回面总体合格，也没有暗装门禁；但两组“怎么查”均不能完整回答自己声称的问题，第二条原则的归属与核心判别句有实质问题，退役通则不可操作，且存在两处会误导复查者的项目事实表述。上述问题会直接妨碍该 skill 达成“定期发现项目怪味并可迭代退役”的目标。

发现计数：`major=7`，`minor=2`，`nit=0`。

本次评审基线：仓库 `HEAD=5968067a324f4c11f7d8560b7c3c1baaa040b304`；被评文件 SHA-256 为 `04271cf0a2e60ed11cfa6bb4fe8c953921ebd866cae2816a87c40d8cbe9f64b8`。工作树有用户已说明的并行改动，因此所有代码与测试观察均只对该快照下当前工作树成立。

运行时未注册 `my-skills:as-reviewer`；本次按等效的只读、发现先行流程执行，并加载了 `evolving-skills` 与 `running-a-procedure-as-written`。除本报告外未修改任何文件。

## 发现

### 1. [major] 第二条原则的核心判据是通用方法学，项目级正文重复了既有 user 级覆盖

**位置：** 被评文件第 74～121 行。

**依据：** `evidence-source-must-match-what-the-assertion-depends-on` 的核心问题是“断言依赖什么，以及哪个 oracle 能裁决它”，这不依附 Python、本仓目录或 cassette 实现。`/home/xp/.claude/skills/verifying-authoritative-claims/SKILL.md` 第 60～75 行已规定“按命题选择 ground truth”，并在第 69 行明确将外部协议／API 合同路由到上游规范、官方 reference implementation／SDK、真实 counterpart，而不是我方 mock；同文件第 29 行还直接把“协议行为只来自我方 mock”列为黄灯。`/home/xp/.claude/skills/trusting-a-green-result/SKILL.md` 第 21～31 行覆盖 same-source oracle 与真实／独立基准。项目规则 `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md` 第 21～22 行又已经把本项目的具体做法写死为 cassette、recorded integration、`from_history.py` 及其边界。

**权重：强到足以要求修复。** 这是对现有 skill 正文与项目规则的逐段对账，不是仅凭主题名猜重叠。

**影响：** 目前形成“三个家”：user 级 oracle 选择方法、always-on 项目 cassette 约定、项目复查 skill 中的通用三档法。它们会独立演化；而且把通用方法放进项目 skill，违反“依附于本项目结构才进入”的自定门槛。

**建议：** 项目 skill 只保留本仓专有的复查问题，例如“哪些断言依赖 Copilot 实际 wire，哪些测试仍只有手写 fixture，以及应落到本仓哪一个 cassette／recorded test”。通用的“证据来源必须匹配命题”引用现有 user 级 skill，不在这里重写。若认为既有 user skill 缺少“手写 fixture 与录制 counterpart”的明确分支，应提出对既有 skill 的增补；按 `evolving-skills`，user 级归属变更属于需第三方评审和用户裁决的 B 级动作，不应由本次评审直接搬迁。

### 2. [major] 第一条原则对交付拓扑的表述过宽，且缓冲路径箭头与实际调用顺序相反

**位置：** 被评文件第 32～35 行。

**依据：** 当前 CLI 确实把正常上游回复在 `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py` 第 268～319 行分成 `context.stream` 的 block-level delivery 分支与 whole-body 分支，因此“当前 `pipeline_app` 的正常回复有两种 body 处理模式”有代码依据。但“本项目只有两条交付路径”没有这个限定：仓库仍保留并实现 `/home/xp/src/ghc-api-proxy-py/src/app/routes/anthropic.py` 与 `/home/xp/src/ghc-api-proxy-py/src/app/delivery/responses_anthropic_stream.py` 的 legacy delivery；`pipeline_app` 自身也另有 count、错误与无响应分支。更直接的事实错误是“缓冲经 `handler.reply_summary` → `translation_driver/responses.py`”：实际顺序是 `pipeline_app.py:313` 先调用 `response_payload`，`handler.py:319-329` 再通过 translator registry 执行 response translation，之后 `pipeline_app.py:316` 才调用 `reply_summary`；`reply_summary` 自身调用的是 `terminal_from_anthropic`，不会向 `translation_driver/responses.py` 下行。

**权重：强到足以要求修复。** 调用顺序来自当前入口的逐行源代码；“只有两条”则只能在明确限定为当前 CLI 的正常回复分支后成立。

**影响：** 复查者会把原则错误地扩到整个仓库，或者沿反向调用链查重；这正是项目级 skill 最不该提供的错误地图。

**建议：** 改为限定语句，例如“当前 CLI 使用的 `pipeline_app` 对正常上游回复有两种处理模式：live upstream 上的 block-level delivery 经 `assembler.py`，whole-body 回复先经 response translation，再由 `reply_summary` 汇总”。若原则有意覆盖 legacy chain，就必须把 legacy 路径纳入事实清单与命令，而不能继续声称只有两条。

### 3. [major] 第一条原则的三条 `rg` 命令没有枚举它们声称的生产者、消费者和重复判定点

**位置：** 被评文件第 36～47 行。

**实际运行结果：** 三条命令均退出 0。第一条打印 `Terminal` 第 44～58 行；第二条打印 12 个构造／赋值点；第三条打印 7 行读取相关命中。

**依据：** 第二条标注为“谁写入这些事实”，但输出不含 `Terminal.record` 的三个调用点，也不含 `record` 内的 `self.tools.append` 与 `self.thinking.append`，因此最关键的 `tools`／`thinking` 分类完全不可见。第三条标注为“谁读这些事实”，却漏掉 `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:96-105` 的 `_Trace.absorb` 全字段读取，也漏掉同文件第 349 行的 streaming `trace.absorb(terminal)`；输出里出现的是 buffered `trace.absorb(context.reply)`，两条路径无法据此并排。更严重的是，“同一语义有两处独立表达式”这一核心违背项没有对应查询：例如 stop reason 分别在 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/assembler.py:319-337` 与 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/responses.py:113-156` 判定，现有命令不会把后二者同时展示。第一条 `-A 14` 当前恰好覆盖六个字段，但字段前的注释或新增字段多几行就会静默截断，不能稳定承担“事实清单”。

**权重：强到足以要求修复。** 这是按正文原命令实跑后，把输出与当前符号调用点逐项对账的结果。

**影响：** 复查者照做会看不到当前统一点，也看不到最应比较的重复表达式；空缺会被误读为“没人写／没人读”，或让实际漂移逃过复查。

**建议：** 让命令围绕稳定符号与目标事实工作，而不是围绕局部变量拼写：至少同时列出 `Terminal` 字段、`Terminal.record` 定义与调用、`terminal_from_anthropic`、`_Trace.absorb` 两条调用、`dialect_for`／`assembler_for`，并单独检索 translation driver 与 assembler 中的 stop reason／usage 分类。命令应输出足以人工比较的 `file:line`，但不要把它升级成扫描器、结构测试或 CI 门禁。

### 4. [major] 第二条原则的 `rg` 输出混入明显噪声并有漏检，Python heredoc 只打印了截断的伪 JSON

**位置：** 被评文件第 84～103 行。

**实际运行结果：** `rg -ln ... tests/` 退出 0，打印 19 个文件，其中包含 5 个 `tests/cassettes/*.json`；Python heredoc 退出 0，只打印：

```text
"usage":{"input_tokens":56919,"input_tokens_details":{"cached_tokens":55680}
```

**依据：** `rg` 注释声称查“哪些测试里手写了上游结构”，却扫描整个 `tests/` 并把真实 cassette 本身列为命中；它还按“文件”而不是手写点输出，无法让读者对“每个手写点”逐一提问。反向漏检也已存在：`/home/xp/src/ghc-api-proxy-py/tests/unit/test_streaming_sse.py:35-42` 手写了 `response.created` wire，但不含四个选定 token，现有命令完全不显示它；Anthropic SSE 手写结构同样不在四个 Responses／usage token 的覆盖面。heredoc 的正则只处理有限嵌套并在 `input_tokens_details` 后提前结束；同一 cassette 的完整 `usage` 还含 `output_tokens`、`output_tokens_details.reasoning_tokens` 与 `total_tokens`，所以输出既不是完整对象，也不是合法 JSON。

**权重：强到足以要求修复。** 这是逐条原样运行后的直接输出，并用结构化 JSON 解析同一 `response.completed` 事件作了异原理对照。

**影响：** 查询结果同时 false-positive 与 false-negative；heredoc 最容易让读者以为“已从录制读出 usage”，实际只看见第一个嵌套字段。它不能支撑正文要求的逐点裁决。

**建议：** `rg` 至少限定 Python 测试并输出具体行，同时覆盖本项目实际出现的 Anthropic／Responses 事件与 usage 结构；更稳妥的是把它定位为“候选点”而非“哪些手写点”的完备清单。cassette 读取应按 SSE frame 解出 `data:` JSON，再打印完整 `event["response"]["usage"]`；这里已有完整外部 oracle，不应再用正则解析 JSON。仍应保持为一段一次性可读探针，不建议新建永久 scanner。

### 5. [major] “连续两次没违背且期间有实质改动”既不可操作，也不能推出原则已经内化

**位置：** 被评文件第 26 行、第 135～142 行。

**依据：** 第 26 行明确规定“没违背的条目不必留痕”，第 139 行却要求知道连续两次复查均没违背以及两次之间该区域发生过“实质改动”。没有最小记录就无法判定连续性、区域范围或期间改动；“实质”也没有可观察谓词。即使这些事实被记录，两次干净快照只支持“这两次查询没有发现当前违背”，不支持“防线已经内化进代码结构或既有测试”这个因果结论，尤其在本文件的查询本身存在漏检时更不能支持退役。

**权重：强到足以删除或重写该退出判据。** 不可达性来自正文内部的记录协议矛盾；因果强度问题来自两次观测与“结构已内化”之间缺少独立证据。

**建议：** 退役应由可证伪的结构事实触发，例如重复推导已因路径合并而结构上不可产生、相应职责已迁移到具名现役机制、或原则已由更好的现存条目完整覆盖并完成召回面对账。若仍想利用复查历史，只能把“两次干净”降为“发起退役复核的弱信号”，不能直接作为退出条件。不要为此建立评分、投票、注册表或状态机。

### 6. [major] 第二条原则的入口问句与退役条件混淆了“oracle 归属”和当前 cassette 实现

**位置：** 被评文件第 76～83 行、第 117～121 行。

**依据：** “这个断言换一个上游还成立吗”不能可靠决定证据来源。正文自己把“路由分支”列为只依赖本方逻辑的例子，但路由结果完全可能随上游能力或配置变化；它仍然可由本项目规范和本方逻辑裁决，不因此必须录制上游。真正的轴是“expected truth 由本项目合同／逻辑拥有，还是断言在声称外部 counterpart 实际会发／会接受什么”。退役条件“cassette 基建被替换”也只说明证据载体变了：若 cassette 换成另一种真实录制格式，方法与复查问题仍成立，应更新项目探针而非退役原则。“上游契约稳定到项目不再需要录制”没有命名谁作出该裁决、依据哪个合同或可观察事实，因而当前不可证伪。

**权重：强到足以要求修复。** 路由反例直接来自该表自身；“替换载体不等于方法失效”正是必读 `separate-what-will-be-fixed-from-what-will-not` 的分界。

**建议：** 若按发现 1 收缩为项目专有条目，原则应写“当测试的 expected value 声称 Copilot／外部 wire 的实际行为时，必须有 recorded counterpart；本方合同与本方分支可用手写输入”。cassette 被替换时只更新命令；只有项目不再对外部 wire 作这类断言，或该职责整体消失，才是条目退役候选。

### 7. [major] 经验性判断没有给出 `state-decisiveness` 要求的权重档位

**位置：** 被评文件第 9 行、第 64～70 行、第 111～119 行、第 144～146 行。

**依据：** 两段“凭什么在这里”给出了同一场内三次命中的具名依据，最后又说两条“都还没被复查验证过”。这些是有价值的 provenance，但文本没有说明它们当前能支持到哪一层：是“强到足以作为暂定项目复查原则执行”，还是“仅为倾向，需要更多独立任务”，以及“未被复查验证”具体禁止得出什么结论。`/home/xp/.claude/rules/00-user/01-core-principles.md` 的 `state-decisiveness` 明确要求经验观察同时写权重档位与依据；仅写免责声明不够。

**权重：强到足以要求修复。** 这是用户点名的评审标准，当前正文只有样本与免责声明，没有决断档位。

**建议：** 在每条实证后给出简短、可行动的档位，例如“权重：足以把它列为暂定复查项，因为同一机制在三处独立代码点造成了具名缺陷；不足以证明当前检索命令有召回力，需由首次真实复查证伪”。不要把档位做成评分表或毕业流程。

### 8. [minor] description 声明“不管绿灯可信度”，正文却直接给出 mutation-control 操作结论

**位置：** 被评文件第 2 行、第 60～62 行。

**依据：** description 将“绿灯可信度”明确路由到 `trusting-a-green-result`，但正文随后规定断言形状，并对“两处保护冗余时必须同时移除才能确认判据抓得住原缺陷”作具体 positive-control 指导。这不是仅说明项目结构，而是在裁决测试绿灯的分辨力。

**权重：强到足以做局部边界修订。** 这是一处正文与 description 的直接范围不一致，但不影响整个第一原则成立，故为 minor。

**建议：** 项目正文只保留本仓事实：“该不变量跨两条路径，回归测试应比较两者”；mutation-control 的一般做法改成带时机的指针，要求此时加载 `trusting-a-green-result`。若保留“两处冗余”的本仓实例，也应明确它只是该 skill 在本结构上的实例，而不是本 skill 接管绿灯可信度。

### 9. [minor] 用“流式路径”命名交付语义，与项目冻结的 block-level delivery 口径冲突

**位置：** 被评文件第 32～34 行、第 51 行、第 58 行。

**依据：** 项目规则 `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md` 第 44 行明确规定下游不提供 token／event-level live streaming，完整 Anthropic content block 才是交付单位。当前代码也在 `pipeline_app.py:268-270` 称其为“Block-level delivery over the live upstream”。被评文本用“请求走流式还是缓冲”“流式经 `assembler.py`”容易把 `stream=true` 的 wire envelope 误写成下游交付语义。

**权重：强到足以局部改词。** 这是项目既定术语与当前入口注释共同支持的文本缺陷，不是架构错误，故为 minor。

**建议：** 使用“live upstream 上的 block-level delivery”与“whole-body／buffered reply”区分两种处理模式；可以在首次出现时注明前者对应请求的 `stream=true`，但不要把 SSE envelope 简称为语义上的“流式交付”。

## 未发现问题的重点项

### 触发面

**判断：总体合格。** description 直接表达“本项目定期复查原则”的意图，并覆盖用户点名的四类入口：定期复查、用户主动说复查／清理／走歪、大块工作合并后、接手半成品。它明确说“不在每次改动时触发”，没有把普通实现、普通测试或任意重构列作入口，因此没有明显退化为 always-on。

**权重：倾向足以接受当前 description，但不是实际召回测量。** 依据是 description 与四个正向场景、三个反向路由场景的文本模拟；没有 selector 日志或真实漏召回样本，不能声称已验证召回率。

三个“不管”的边界中，共享工作树纪律与会话收尾边界清楚；绿灯可信度边界有发现 8 的局部正文冲突，修正后可接受。“有没有什么该清理的”本身很宽，但 description 随即限定为拿本项目原则查代码怪味，并把会话收尾路由出去；按 `recall-over-precision`，不建议为了减少一次白跑而删掉该入口。

### `the-body-holds-criteria-not-chronicle`

**判断：通过。** 两段“凭什么在这里”都是一句或两句带日期、具名故障形态与来源目录的实证摘要，没有按“先 A、再 B、评审后改 C”的时间顺序展开返工史。它们帮助读者判断为何要保留条目，属于判据的证据而非 chronicle。发现 7 要补的是权重档位，不是删除实证。

**权重：强到足以保留这些段落。** 依据是逐段结构判断；对应的 `.dev/docs/tui/archive-request-log/`、`.dev/docs/tui/archive-token-accounting/` 与 `.dev/docs/tui/deferred.md` 当前均存在。

### 已抽样核实的项目事实

- `assembler_for` 确实基于 `dialect_for` 的结果分派：`/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py:368-401`。**权重：已由当前源码直接确认。**
- `Terminal.record` 当前是 active pipeline 汇总 `tools`／`thinking` 的共同分类点，并由两个 assembler 与 whole-body 构造共三处调用：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/assembler.py:58-67,89-91,182-184,315-317`。这不支持把它说成整个仓库所有 reply facts 的唯一分类点；stop reason、usage、dialect、seen 仍在别处产生。**权重：已由当前源码直接确认，结论限定到 `tools`／`thinking` 汇总。**
- 当前五份 cassette 的每个 response chunk 都是只含 `text` 键的 object；被评 heredoc 对 `history_responses_stream.json` 的这一结构假设成立。**权重：已对当前 `tests/cassettes/*.json` 全量结构化枚举，足以描述当前 fixture，不保证未来 schema 不变。**
- `from_history.py` 的重复事件陷阱及 history 在 2026-08-15 后不再存帧，均与项目规则 `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:22` 一致。**权重：沿用项目权威约定；本评审未重新读取外部 history DB，因此只确认文本一致性，不独立重证运行历史。**

### 门禁／证明基础设施

**判断：没有隐含门禁。** 正文的逐条检索、人工判断、候选工作项与退役复核都是“人读文本并执行”的步骤，没有程序扫描 schema、注册条目、抽标签、阻断提交或令 CI 失败。建议写路径间对等断言属于普通回归测试方向，不自动构成项目规则禁止的 proof infrastructure。第 13 行还明确禁止接入失败机制。

**权重：强到足以判定当前文本没有门禁。** 依据是全文控制流与产物检查；没有发现 hook、CI、registry、manifest 或机械放行条件。

## 不建议采纳的改法

1. **不建议把这份 skill 接入 hook、CI、pre-commit、结构测试或周期任务。** 当前问题是文本判据与命令质量，不是“缺一个强制执行器”；机械化会违反项目第 26 行的 proof-infrastructure 边界。
2. **不建议删除第一条原则或把其中的项目符号抽象掉。** `Terminal`、`assembler_for`、`reply_summary` 与两种 body 处理模式正是它作为项目级 skill 的价值；应修正范围与查询，不应把它改成泛泛的“避免重复逻辑”。
3. **不建议因“凭什么在这里”带日期就移入 reference。** 现有段落是简短 provenance，不是返工史；删除会让条目失去依据。应补权重，不应删实证。
4. **不建议用永久 scanner 取代当前 `rg`／Python 探针。** 修成可读、能回答原子问题的命令即可；语义裁决仍应由复查者完成。
5. **不建议为“连续两次复查”补一套评分、投票、状态表或毕业协议。** 更好的修法是撤销其直接退役效力，改用结构性退出事实；若保留历史信号，只需最小的人类可读记录。
6. **不建议为了减少误触发而删掉“清理”“走歪了”或“接手半成品”等入口。** 当前召回面的主要问题不是过宽，而是正文边界与判据质量。

## 建议的修复优先级

1. 先裁第二条原则的归属：项目正文只保留 cassette／recorded-upstream 的本仓复查面，通用 oracle 方法回指既有 user skill。
2. 修正第一条的范围、调用顺序与 block-level delivery 术语。
3. 重写两组“怎么查”，逐条在仓库根目录复跑并核对输出是否真的展示判据需要比较的对象。
4. 删除或降级“两次干净即退役”，把每条退役条件改成可观察的结构事实。
5. 给两段经验依据补 `state-decisiveness` 权重档位，并清理与 `trusting-a-green-result` 的边界冲突。

---

## 处置记录（2026-08-20，作者补记）

**9 条全部采纳，技能已重写。** 修改前逐条自查，三条最要命的事实断言我独立复现确认评审无误：

- `response_payload`（`pipeline_app.py:313`）确在 `reply_summary`（`:316`）之前，`reply_summary` 调用 `terminal_from_anthropic` 而非下行到 `translation_driver/responses.py`——**我原文的箭头写反了**。
- legacy 交付链确实存在（`src/app/delivery/anthropic_sse.py`、`responses_anthropic_stream.py`、`routes/anthropic.py`），「本项目只有两条交付路径」过宽。
- `tests/unit/test_streaming_sse.py:35` 手写了 `response.created`，原命令四个 token 全部不命中。

### 逐条

| # | 严重度 | 处置 |
|---|---|---|
| 1 | major | 采纳。第二条收窄为本仓复查问题（哪些断言声称外部 wire、有没有落到 cassette），一般方法引用 `verifying-authoritative-claims` 不重写。 |
| 2 | major | 采纳。范围限定到当前 CLI 的 `pipeline_app`，写明真实调用顺序，legacy 链具名并明确排除。 |
| 3 | major | 采纳。事实清单改为 dataclass 内省（不再依赖 `-A 14` 行窗口）；生产者命令补进 `.record(` 与两处 `append`；消费者命令补进两条 `absorb`；新增「重复判定热点」命令。 |
| 4 | major | 采纳。手写点检索限定 `--type py`、换用只在上游载荷出现的结构键、按文件计数排序，并声明它给的是**候选点**；cassette 提取改为按 SSE 帧解 `data:` 行。 |
| 5 | major | 采纳。删除「连续两次没违背即退役」，改为只由可证伪的结构事实触发；两次干净降为「发起退役复核的弱信号」。 |
| 6 | major | 采纳。判别轴从「换个上游还成立吗」改为**期望值归谁所有**；退役条件改为「不再对外部 wire 作此类断言」，并写明换录制格式不是退役条件。 |
| 7 | major | 采纳。两处实证后补权重档位，并分别写明**不足以**支撑什么（命令召回力、判别轴的完备性都未经真实复查检验）。 |
| 8 | minor | 采纳。mutation control 改为带时机的指针（「此时加载 `trusting-a-green-result`」），本条只声明不变量跨两种模式。 |
| 9 | minor | 采纳。术语改为 block-level delivery / whole-body reply，并注明 SSE 只是信封。 |

### 顺带发现（评审未提，作者自查）

新增的「重复判定热点」命令打出 `translation_driver/responses.py:65-67` 有一处 usage 原样拷贝。查证为**误报**：它在 `from_anthropic_response` 里，读的是 Anthropic 载荷，键本就正确。这个例子已写进技能正文，用来说明「命令给候选、判断留给人」。

### 自查发现的第四个错（评审只指出了症状）

F4 说那段正则提取「只打印了截断的伪 JSON」。核实后确认：旧脚本对三份 cassette 都会在 `input_tokens_details` 处提前结束，`output_tokens`、`reasoning_tokens`、`total_tokens` 全部丢失——**而我当时看了输出没发现它不合法**。这与本技能第二条要防的失败同源，已作为实证写进正文。

### 验证

技能正文两个 bash 块按原样执行：block 0 输出 71 行、block 1 输出 21 行（18 个手写点文件 + 3 份 cassette 的完整 usage），均 rc=0。
