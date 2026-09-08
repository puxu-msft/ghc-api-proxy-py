# Effort translation Spec 定向复评 R2

- status：NEEDS_FIX
- attempt_id：effort-translation-spec-gpt-opus-a2
- review_started_at：2026-09-03T09:35:21+00:00
- review_scope：首轮 EFFORT-M01～M06、整改 diff 及整改触及的相邻合同
- r1_report_sha256：`f8beddc60d33d2988bd5d32342b323ed326bc3de168c103ce9f58b32363f143d`
- checklist_sha256：`e32456e3b475504c3cf8c8e2171de25970bf3f483c57efa4d6c490044f184d89`
- spec_sha256：`78e6c0af11470353c8862915cfb15c764c6be643171eb98e32f00ea01eeaf408`
- acceptance_sha256：`e79d947e4cb211fd64cae866a87e6c1ffeb4484e434922380f0edb22b5ac113e`
- implementation_sha256：`d892cac24e03328ecf95f479846abdc93ef70e5f22a3eb540e981efba8c8496e`
- disposition_sha256：`119cd530c5215298d693a7c084135f0b5f0a2b700ad177d0f2ac78ff042be897`

## 范围与方法

本轮不重新全量发散；逐条复核首轮六条 major 的处置是否由 current working tree 实际关闭，再检查这些整改直接碰到的相邻合同是否自洽。历史报告只作为原发现身份，不作为 current verdict。

## 复核依据与六项原发现状态

- M01：部分关闭。保留 translated-path compatibility extension 的判断站得住：它保全已实现接受面，明确区别于 Anthropic 官方 shape，并保持 direct path 原样交给目标 model；但整改触及的反向 Anthropic writer 仍没有 target thinking-type capability 闭包，见 R2-M01。
- M02：已关闭。Enabled 对齐先排除 `none`，只剩 `none` 时稳定拒绝，Acceptance 同入口控制也能使旧缺陷变红。
- M03：effort 档位对齐部分已关闭。反向 exact／downward／floor／missing／empty／unrankable 的发送值与 loss 已成为总函数；其相邻 thinking wire shape 缺口并入 R2-M01。
- M04：已关闭，且按机制类别补控制的做法站得住。REQ-05A 现按 reader／优先级、正向 capability、逐消息／header、反向 mapping、residual／生产接线五个机制族布置单侧变异；同一路径的一组枚举值不需要复制同构 mutation，也没有建设新的常驻 mutation framework。
- M05：major 已关闭。Spec current restatement 与 `CAL-04-GRAMMAR-v2` 一致允许首块前独立 `ping`，同时保持 `message_start` 与首块同 batch；旧裁决只留 point-in-time report。
- M06：未关闭。Implementation 仍有多处把历史 `main@c1de6bf…` 直接称作 current，见 R2-M02。

Anthropic 当前《Thinking troubleshooting》在 2026-09-03 本轮复核：Claude Opus／Sonnet／Haiku 4.5 是 extended-only，拒绝 `adaptive`；Fable／Mythos 5／5.1 与 Mythos Preview always-on，拒绝 `disabled`；Opus 5 的 `disabled` 还受 effort 上限约束。该 model-specific 表是 R2-M01 的外部合同依据。

## C1～C12 逐条结论

- C1：PASS。八项用户裁决仍在字段矩阵、Reasoning 正文、验收行为与冻结摘要中同向记录。
- C2：FAIL，见 R2-M01。官方 schema 与 translated-path extension 的分界已明显改善且保留 extension 本身成立，但 target Anthropic thinking-type model gate及 manual budget 完整约束尚未闭合。
- C3：PASS。Responses nullable 七值集合与 OpenAI SDK 3.3.1 类型保持一致。
- C4：PASS。`ThinkingEffortIntent | None` 仍能表达清单要求的 source intent／enabled／effort／source 区分，budget 未重新成为档位输入。
- C5：FAIL，见 R2-M01。两向 effort 档位 exact／downward／floor／unknown 已闭合，但 Responses→Anthropic 的最终 thinking wire shape仍可能被目标 model拒绝，故终态尚非全域。
- C6：PASS。兼容扩展明确只作用 translated path，两个 direct leg仍原样转发。
- C7：PASS。Header 在 path policy 清空前认领的义务未被整改削弱，send／count仍要求共用源 fact。
- C8：PASS。两向 sibling 重建、跨格式精确 loss 与已翻译 effort 不重复计 loss均保持。
- C9：PASS。M04 按机制类别补控制站得住；五个机制族覆盖原缺口，同源枚举值不需复制同构 mutation，且 expected／证据层边界未退化。
- C10：PASS。REQ-05B 未混入 request-level effort，carrier 合同未被本轮整改改写。
- C11：FAIL，见 R2-M01、R2-M02。Effort 表／正文之间的 target thinking capability仍有缺口，Implementation 的 current／historical restatement也仍冲突。
- C12：PASS，按 effort 切片窄范围判断。活动行仍只声明文档已改、代码未改、待复核，并明确旧 canary不覆盖本轮；R2-M02是相邻 current identity缺陷，不是 canary 外推。

## Blocker 与 major

本轮没有 blocker；发现 2 条 major。另有 minor 2、nit 0，按契约只计数而不展开。

### R2-M01
- severity：major
- primary_location：`spec.md:277-282`
- related_locations：`spec.md:212-214`；Anthropic 官方《Thinking troubleshooting》《Extended thinking》；`src/app/model_provider/types.py:79-89,106-132`
- 失败场景与证据：保留 translated-path compatibility extension 本身成立，但 reverse writer固定用 `adaptive`／`disabled`：`reasoning.effort=low` 写给 extended-only Claude 4.5 会 400，`reasoning.effort=none` 写给 always-on Fable／Mythos会 400；同时 official manual shape摘要仍未写 `budget_tokens < max_tokens`及 interleaved exception，超界正整数也未归入 extension或拒绝。
- 建议：把 target thinking modes／disable support与 budget bounds纳入 TranslationTarget 和总函数；adaptive-only、extended-only、always-on及unknown各给唯一 wire／reject终态，manual budget必须独立于 effort选择；保留已明确标注的 translated-path extension。

### R2-M02
- severity：major
- primary_location：`implementation.md:104`
- related_locations：`implementation.md:10,18,113,252,298,303`
- 失败场景与证据：顶部虽声明所有 `main@c1de6bf…` 都是历史锚点，正文仍把同一值写作 `current main`、`current main@c1de6bf…` 及“本轮同步 current”；接棒者按执行表／开发线／怪味登记读取时仍会把 2026-08-08 快照当现行主线，原 EFFORT-M06未全域关闭。
- 建议：逐处把这些可变 restatement改成明确历史日期／阶段，或改为动态 current authority引用；不能用一条总括声明去覆盖同文档中仍然写反的具体 current 单元格。

## 整体判定

结论为 `needs-fix`。M02～M05 的原核心缺陷已关闭，M01 的 compatibility extension与 M04 的机制级控制粒度均可保留；但 R2-M01 仍可生成目标 Anthropic model必拒的 wire，R2-M02 仍把历史主线写成 current，故尚不可定稿。两个 minor不单独阻断；若两条 major关闭且未引入相邻矛盾，可按“只剩 minor即可定稿”处理。

## 我最没把握的三个判断

1. R2-M01 中应选择“为 extended-only model提供独立 budget”还是“无独立 budget事实即拒绝”不是本 reviewer可代用户裁定的部分；我有高把握的是当前无条件 `adaptive` 不能成立，修法分叉应由既有配置／用户裁决解决。
2. R2-M02 的严重度受顶部总括声明缓解，但具体表格仍以 `current` 标注陈旧 hash，且这些表格本来就是执行入口；我因此维持 major，而不是把它降为纯措辞 minor。
3. M04 的 PASS 是机制覆盖判断，不声称每个未来 malformed shape已有单独 mutation；现有正确样本、五类单侧变异与失败原因核对足以让本轮要求收敛，若后续实现暴露新的独立 validator分支，再增加对应控制即可。

## 执行本契约时遇到的摩擦

- `my-agents:as-reviewer` 在 R2 再次返回 `Unknown skill`；我未派生 agent，按 reviewer契约与已加载的 claim qualification方法执行。
- 并行 `Read` 的工具回执顺序与派发顺序不同；我用文件标题、连续行号与末行逐份确认 checklist、Spec、Acceptance、Implementation及处置账均已完整读取，没有把回执顺序当文件身份。
- 本轮没有运行产品测试、mutation或真上游调用，因为范围是文档整改定向复评；外部事实只复核官方当前文档，代码只读用于确认 capability fact可承载，不把它们冒充实现验收。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-03T09:38:19+00:00
- finding_total: 4
- blocker_count: 0
- major_count: 2
- minor_count: 2
- nit_count: 0
