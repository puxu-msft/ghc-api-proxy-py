---
report_id: token-counting-spec-review-2026-09-07-gpt-high-3
attempt_id: token-counting-spec-rereview-20260907-gpt-high-03
status: in-review
review_scope: original-findings-02-03-only
reviewed_at_rev:
  README.md: sha256:56573075dd2843ead7dd9c0f1208fd9455e5cf018093ef94b065c01a35776add
  spec.md: sha256:cf83b6ad1bd0de5f2f5c0768a667a93f5c4e7219cc57038cd07bde2f8e932382
  plan.md: sha256:d1a71db01e2442d9fb3566c1558430bf8a1a773347ac5280b237cbdf2eb73608
  status.md: sha256:b7b8de0ab4685903dc736945da2a943207b89c37d8843c8233c87d76f216b812
criteria_at_rev:
  original_review: sha256:d68b43dc060f7b3be849e4f9088e80599a60bc10a0bc55f5d46bed3ec6a335e4
  blocked_rereview: sha256:522a4840578560737cb4f56891b88259ed0b264c763b472788ad8f77cfd21e5b
  disposition: sha256:1cfa9bec5fb069bb5bec2697e3a21ca88fdf5187fe3847d090ab5360acac8288
  user_source_research: sha256:ed095957eb833d38898ce36e8ff9c4d2c13adb744bff290ce16728fd0982a2fb
  special_token_research: sha256:7d25af6917db5d65b09087caebc0f346253cafd675054d6bcebebfc50610afae
revision_diff:
  base: ec292d52ec5061bbfd2a525ad8b84ca90fb9ef78
  review_gap_fix: 7fb43f416ac2d61d0729a2ca896fc184a458f0ca
  heading_follow_up: c281b29e7b983b2d910100d0faaefd253987a9d4
---

# Token-counting Spec 限定复审

## 评审范围

本轮只复审原报告`token-counting-spec-review-2026-09-07-gpt-high`的finding 02与finding 03、从`ec292d52ec5061bbfd2a525ad8b84ca90fb9ef78`到`c281b29e7b983b2d910100d0faaefd253987a9d4`中与两项finding相关的修订，以及README／plan／status中的相邻来源与实施门合同。

被评对象是主工作树`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/`下README、spec、plan、status四文件的frontmatter所列SHA-256快照。评审开始前四值全部匹配冻结预期；交付前再次核对的结果见“最终快照复核”。

明确不在本轮范围内的是重新打开原review已通过的其它条款、完整Spec新评审、production实现验收、测试执行、live upstream调用和provider账单精度判断。`status.md`只作为相邻状态投影检查，不作为finding已修复的证据。

## 总体判定

`pass`。Blocker为0；本轮未发现blocker、major、minor或nit。原finding 02与finding 03均为`closed`，当前冻结Spec可以进入implementation；本轮没有因未清点范围外minor而延迟放行。

这个判定只说明两项原major及其相邻合同已在Spec层闭合，不声称production实现已经符合Spec，也不声称local tokenizer数值等于Anthropic、OpenAI或Copilot的provider billing usage。

## 原finding逐项verdict

### token-counting-spec-review-2026-09-07-gpt-high-02

- `verdict`：closed。
- `previous_severity`：major。
- `current_finding`：none。
- `ordinary spelling与surface`：`spec.md` §4.3第213～219行具名字面`<|endoftext|>`、`<|endofprompt|>`及configured tokenizer当前或未来声明的全部special-token spellings，并逐项覆盖Anthropic top-level `system`／messages／tool schema与Responses `instructions`／messages／tool schema／function-call arguments／function-call output；同段明确这些拼写不得取得control-token semantics或改变known／opaque／media／unknown分类。
- `可判否unit oracle`：`spec.md` §12.2 A24第463行要求枚举全部configured spellings并显式包含`<|endoftext|>`，以不同源ordinary oracle比较token sequence或exact delta；default guard与`allowed_special`是两次独立目标变异，前者必须因异常判红，后者即使返回正数也必须因sequence／delta差异判红。该判据同时要求classification不变，并在证据边界中明确不证明provider billing accuracy。
- `production两路径`：`spec.md` §12.2 A25第464行覆盖direct Anthropic local-only和Anthropic→Responses local两条真实ASGI入口，要求HTTP 200、严格完整对象、local worker一次及remote provider transport零次；两侧default `encode()`各有独立反向控制，endpoint catch不得代偿。
- `被否路线`：`spec.md` §11第411～417行逐项否决default guard、`allowed_special`、endpoint catch／fallback、Responses-only patch、one-spelling denylist、one-message-position patch和保留旧failure expectation，理由与点时special-token调查一致。
- `转录`：`spec.md` §13第472～482行分别把classification、Anthropic surface、Responses surface、worker synthetic failure、local counter与两条ASGI路径落到planned test transcriptions；没有把尚未创建或尚未修改的测试写成已通过证据。
- `修订记录`：`spec.md` §15第501行记录事故、完整surface、两种encoding mutation、两条ASGI path、被否路线、test transcription及本finding来源。
- `README／plan同步`：`README.md`第23、35、56行与`plan.md`第53、66、179～180、249～250、423、443行均维持同一ordinary-text范围、oracle、两路径和精度边界。
- `剩余问题`：无。

**承重前提检查：** 前提是ordinary-text成功必须能区别于把字面拼写编码成special control token，而不能只检查“非500／返回正数”。它支撑“finding 02可以关闭”的结论，因为A24同时具备不同源ordinary oracle、正确样本与default guard／`allowed_special`两种能判红的控制。若该前提为假，A25的非500断言本可单独满足；但`tiktoken 0.14.0`点时调查已观察ordinary encoding与`allowed_special`产生不同sequence，且当前Spec明确规定客户端string没有control-token语义，因此不能把这个前提撤掉。

### token-counting-spec-review-2026-09-07-gpt-high-03

- `verdict`：closed。
- `previous_severity`：major。
- `current_finding`：none。
- `R1／R3来源类型与稳定锚`：`spec.md` §2.2第35～42行把R1与R3准确标为`user-selected-from-proposal`，同时记录共同transcript绝对路径、assistant proposal UUID、tool id、paired user-role tool-result UUID和双方timestamp；表内保留被选proposal的完整description，并明确description由assistant撰写、用户拥有选择行为。
- `R1／R3完整scope`：`spec.md` §2.3第48、50行保留R1的Responses opaque／media／unknown场景、排除opaque bytes、估可见／结构部分、`estimated:true`与near-cap undercount取舍，以及R3的exact优先、append-only longest-prefix actual＋suffix、无prefix的provider／model／profile calibration与分阶段交付。未被proposal覆盖的upstream-no-counter、configured-tokenizer identity、new-identity cold-start和细化eligibility／drift／bounds被明确拆出。
- `R2／R4真实原话与稳定锚`：`spec.md` §2.2第40、42行逐字保留两条human queued-command prompt，并记录attachment UUID、source UUID、`origin.kind=human`和timestamp。直接解析原始JSONL确认全部UUID、tool id、配对、时间、原句与Spec一致，没有用取证报告转述替代原始source anchor。
- `四个长句不再冒充用户逐字`：旧§2.2的四个完整长句已从修订中删除。当前§2.2只把R2／R4引号内原句称为exact user text；R1／R3的proposal description明确归assistant撰写，§2.3第53行再次禁止把proposal之外内容或长解释冒充用户原话。
- `implementation-derived边界`：`spec.md` §2.3第48～51行把cold-start、persistence、single global multiplier否决、configured-tokenizer identity、new-identity cold-start、详细eligibility／drift／bounds、八类算法与持久化机制，以及method不可删除／不可改序，逐项归为implementation judgment或implementation decisions；`spec.md` §2.4继续把算法常量与编排列为实施者派生决定。
- `README／plan同步`：`README.md`第13～16行以R1／R3 proposal selection、R2／R4 direct user text和implementation-derived additions分层；`plan.md`第38～47行保留相同anchors、授权scope与派生边界，没有再次把四个长句称为用户逐字。
- `剩余问题`：无。

**承重前提检查：** 前提是AskUserQuestion的paired tool-result证明用户选择了assistant写出的完整proposal，但不把proposal文字改写成用户亲笔原话；human-origin queued-command attachment则可逐字归于用户。它支撑“finding 03可以关闭”的结论。若任一anchor无法解析、配对tool id不一致或attachment不是human origin，本结论会重新打开major；本轮直接解析原始transcript后，八个UUID／source UUID全部命中，两个tool id一一配对，两条attachment均为`origin.kind=human`，所以该前提强到足以行动。

## 修订diff与相邻合同

`7fb43f416ac2d61d0729a2ca896fc184a458f0ca`在四份active文档中完成来源重标、ordinary special-spelling合同、A24／A25、§11被否路线、§13转录与§15记录，并同步README、plan和status。后续`c281b29e7b983b2d910100d0faaefd253987a9d4`只把special-spelling后重复的“4.3 Opaque、media与unknown”标题改为“4.4”，没有改变本轮行为合同。

独立于原finding清单重看当前限定系统状态后，未发现修订在这两项相邻合同中引入新的blocker、major、minor或nit。`status.md`的`fix-authored`自报没有被用作通过依据；通过依据是当前四文件内容、修订diff、special-token机制调查和原始transcript anchors。

`spec-review-disposition.md`当前仍把DISP-01与DISP-02记为`fix: open`并保持implementation gate关闭。它描述的是复审前流程状态，与本轮读取时的新证据不冲突；本报告交付后，coordinator需要按处置账职责将两项转为终态并更新gate。该待更新属于后续状态记账，不是当前Spec质量finding。

## 被否路线

### Finding 02

1. 只恢复configured tokenizer default guard：会把合法ordinary text重新变成500。
2. 使用`allowed_special`：能避开异常，却把客户端字面字符赋成control token，独立oracle必须判红。
3. 在endpoint catch encoding error后fallback：隐藏共享estimator根因，且可能伪造成功。
4. 只修Responses：Anthropic local使用同一ordinary-text不变量，点时ASGI已复现两边故障。
5. 只移除`<|endoftext|>`一个denylist成员：漏掉`<|endofprompt|>`与未来configured spellings。
6. 只修事故中的一个message position：漏掉其余Anthropic／Responses text surfaces。
7. 继续以special spelling触发worker failure metrics：把产品缺陷钉成期望行为；应改用synthetic estimator exception。

### Finding 03

1. 因四个旧长句都不是user-natural-language逐字稿而把四项整体降为“用户未裁决”：否决。R1／R3有confirmed proposal selection，R2／R4有confirmed human queued-command原话。
2. 把R1／R3的proposal description或harness wrapper称为用户亲笔原话：否决。用户拥有选择行为，文字生产者仍是assistant／harness。
3. 把cold-start、single multiplier、configured-tokenizer identity、八类机制或method不可删除／不可改序塞回用户逐字scope：否决。这些是proposal与委托边界内的implementation-derived closure。
4. 只在Spec修正来源、让README或plan继续保留旧归因：否决。当前两份相邻文档已同步同一来源边界。

## 搜索面与未覆盖面

已逐字读取冻结README、spec、plan、status，原review报告、上次因旧快照而blocked的rereview报告、review disposition、user-rulings source research全文至queued-command erratum结尾，以及special-token investigation。已直接解析共同transcript中R1～R4的assistant proposal、paired tool-result和queued-command attachments，并检查`ec292d5…c281b29`修订diff及两个相关commit。

未运行production测试、mutation、live upstream或完整Spec review；这些不是本轮Spec限定复审的证据义务。没有检查范围外原round-1 findings，也不对未来implementation是否满足A24／A25作预判。

## 我最没把握的三个判断

1. **A24把“不同源ordinary oracle”规定得是否足够具体，信心中高。** 它没有预先钉死测试helper名称，但已经钉死独立来源、sequence／exact-delta相等、两种目标变异及各自失败形态；这足以约束实施而不把测试架构写死。若实现阶段把oracle与production helper接到同一函数，应由实施review重新判红，不能反推本Spec当前缺少语义。
2. **R1的“功能连续”是否完整保留，信心高。** §2.2保留proposal原description中的“功能连续”，§2.3以“返回低置信估算而非unavailable”的合同实现同一scope；虽然授权scope段没有再次使用这四个字，语义没有被缩窄。
3. **处置账`fix: open`是否构成当前不一致，信心高。** 它在本报告产生前准确表达“等待复审”，所以不是被检文档缺陷；本报告成为新证据后才需要coordinator更新。若处置账在采纳本报告后仍长期保持open，届时是状态账不一致，不应回溯改变本次Spec verdict。

## 执行本契约时遇到的摩擦

- 首次批量`Read`误传空`pages`参数，工具在读取任何内容前拒绝；随后用合法参数完整重读，user-source报告确实读到第424行queued-command erratum结尾。
- 当前agent位于隔离worktree，harness拒绝把版本库命令以`-C`重定向到共享主树。主工作树被评文件仍按绝对路径读取与算SHA；修订diff改在本agent自己的隔离worktree读取，且该worktree四文件SHA与主工作树冻结值逐一相同，因此diff没有拿旧`.dev`快照替代active对象。
- 完整四文件diff输出过大，被harness自动持久化到会话tool-results目录；本轮随后用关键词限定命令读取F02／F03相关hunks，并单独核对heading follow-up。该自动tool result不在仓库内，也不是本reviewer创建的项目文件。
- Dedicated `Write`工具因agent位于隔离worktree而拒绝主工作树中的指定REPORT_FILE；按用户对唯一报告路径的明确授权，改用`Path.open("x")`排他创建，没有覆盖既有报告，也没有创建中间文件。
- 除指定REPORT_FILE外，本轮没有修改任何仓库文件，没有执行版本库写操作。

## 整体判定

原finding 02与finding 03均已按本轮明确判据关闭，且限定相邻合同未出现新finding。当前冻结Spec达到0 blocker／0 major，可进入implementation。后续只需由coordinator更新处置账与状态门；这不是要求再修改Spec，也不是再次复审的前置条件。

## 最终快照复核

交付声明追加前再次核对主工作树四文件，结果与frontmatter逐项一致：README为`56573075dd2843ead7dd9c0f1208fd9455e5cf018093ef94b065c01a35776add`，spec为`cf83b6ad1bd0de5f2f5c0768a667a93f5c4e7219cc57038cd07bde2f8e932382`，plan为`d1a71db01e2442d9fb3566c1558430bf8a1a773347ac5280b237cbdf2eb73608`，status为`b7b8de0ab4685903dc736945da2a943207b89c37d8843c8233c87d76f216b812`。因此本报告没有把启动时旧快照或交付前已变化的active对象冒充冻结对象。

## 交付声明

delivery_complete: true
completed_at: 2026-09-07T02:45:35+00:00
finding_total: 0
blocker_count: 0
major_count: 0
minor_count: 0
nit_count: 0
