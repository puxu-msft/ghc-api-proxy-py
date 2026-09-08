---
report_id: token-task3a-prediction-contract-rereview-claude
attempt_id: task3a-prediction-contract-rereview-claude-1
status: in-review
reviewed_at_rev: "spec-sha256:c81d9046425fef155a20bfa666e396ba15196fbfb596941abbbe883bebd4f440; plan-sha256:866c8643530d31ebd5f70ca50bcc8d1a2004fd2ad1b9837b36f2ea445f77deb7; prior-report-sha256:53ece694e1cdf6f05243988f49fa722b2e434f0f3788a33caff6cb8e47aba75f; dotdev-amendment:143e077"
reviewed_at: 2026-09-07
reviewer_role: Token Task 3A prediction-contract re-reviewer
---

# Token Task 3A prediction contract re-review

## 评审范围

本轮只复核原报告 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-prediction-dto-gap-review-claude.md` 的 Findings 01～03、由 dotdev amendment `143e077`产生的当前合同内容及其直接相邻restatements。行为权威绑定 `.dev/docs/token-counting/spec.md` SHA-256 `c81d9046425fef155a20bfa666e396ba15196fbfb596941abbbe883bebd4f440`，实施计划绑定 `.dev/docs/token-counting/plan.md` SHA-256 `866c8643530d31ebd5f70ca50bcc8d1a2004fd2ad1b9837b36f2ea445f77deb7`，原报告绑定 SHA-256 `53ece694e1cdf6f05243988f49fa722b2e434f0f3788a33caff6cb8e47aba75f`。

检查面包括：closed candidate variants／keys、point-in-time method champion＋eligibility、global selected key、七种合法pair、candidate-key evaluations与每key最近128 diagnostics、V1 visual／selected／champions／variant columns／PK／CHECK／graph、Task 3A ownership、presence-aware visual slot与capability producer排序、ephemeral `PredictionDecision`到Task 5的owner chain、V1 in-place前提和原报告被否路线的持久记录。明确不重审Task 3 cancellation、migration、revision、thread provenance等已闭合且与本轮整改无直接关系的合同，也不评Task 3A尚未开始的source implementation。

## 总体 verdict

**NEEDS FIXES。Blocker 数：1。** 三个原finding的核心方向均已进入current Spec／Task-specific plan；Finding 02已完整关闭。Finding 01仍被“所有method都必须有champion”与候选缺席语义的矛盾阻断，Finding 03仍被plan上层旧接口restatement保持open。另有一条被否tuple carrier路线未进入living authority。当前不可批准Task 3A source启动。

## 原 Findings 01～03 逐项状态

| 原finding | 状态 | 复核结论 |
|---|---|---|
| `token-task4a-prediction-dto-gap-review-claude-01` | **OPEN** | Candidate key、四variants、七种pair、selected key、method champion／eligibility、evaluation method＋variant PK／CHECK、per-candidate-key 128 diagnostics、V1 graph和Task 3A ownership主体均已写入；但Spec要求每个method都有champion且champion key必须存在，无法表达cold-only等合法candidate缺席状态；Spec／plan另有method-level旧restatement。见新findings 01～02。 |
| `token-task4a-prediction-dto-gap-review-claude-02` | **ADDRESSED** | `capability_visual_tokens: int | None`与known／components／FeatureVector分槽，dedicated nullable V1 column、per-item immutable capability snapshot、29＋6及same-pixels 6-vs-8 oracle、estimator generation和Task 8 producer seam均闭合；V1 in-place前提有当前项目证据支持。 |
| `token-task4a-prediction-dto-gap-review-claude-03` | **OPEN** | Spec §8.5、A36和Task 3A／4A／5 specific sections已正确分离ephemeral `PredictionDecision`与durable record／codec，并禁止prequential challenger冒充use；但plan上层Strategy／orchestration与旧Task 3条款仍说predictor返回`TokenPrediction`／直接返回`AnchorUseIntent`。见新finding 02。 |

## New findings

### token-task3a-prediction-contract-rereview-claude-01

- `severity`: blocker
- `statement_kind`: contract fact
- `conclusion_strength`: confirmed，存在一个由Spec自身构造的合法反例
- `primary_location`: `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:264-270`
- `related_locations`:
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:272-305`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:339-345`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:557,569,581,589`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:348-355,372-381`

#### 事实证据

Spec §6.0同时要求：一，record只保存“当时存在”的candidates；二，“每个method恰好一个”champion；三，每个champion key必须存在于同一record。§6.1又明确new identity／无history时选择cold-start，因此首个prequential record可以且应当只有`cold-start/deterministic` candidate。该record没有合法的`history-exact`、`history-prefix`或`profile-calibrated` candidate，却按字面必须为这三个method各保存一个指向existing candidate的champion，三个条件不能同时满足。A20重复了“每method恰有一个”，Task 3A test要求中的“missing champion全部拒绝”也未限定为represented method。

相邻§7.3仍写“每种method／ProfileKey分别维护error sequence”。Variant selection需要每candidate-key error sequence，demotion／drift才使用record冻结的method-champion sequence；把两者压成method sequence会重新制造原Finding 01的same-method collapse。

#### 最小修法

1. 把§6.0、A8、A20、A32-P／A39和plan Task 3A统一改成：**每个在该record中至少有一个candidate的represented method恰有一个`MethodChampion`；没有candidate的method必须没有champion。** Missing champion只对represented method判错，多出的champion或指向absent candidate仍判corrupt。
2. Global `selected_key`从represented champions中按四个既有`PredictionMethod`顺序选择第一个`eligible_for_selection=true`的champion；cold-start candidate始终提供最终fallback。四个public methods的名称、集合与顺序不变。
3. 把§7.3 error sequence拆成两个槽：每candidate key的prequential evaluation sequence用于variant comparison／diagnostic retention；record中point-in-time method champion的evaluation sequence用于method demotion／recovery／drift。不得用当前算法事后重选champion。
4. 添加最小判否样本：empty snapshot产生仅含cold-start candidate＋cold-start champion的合法record；若validator要求absent exact／prefix／profile champions则必须红。另分别验证represented method missing champion、absent method extra champion和champion指向wrong-method／missing key均被拒。

#### 受影响位置

只需修living Spec、plan Task 3A／4A的DTO invariants与planned tests；随后Task 3A source按修正后的cardinality实施。V1七种pair、method＋variant columns／PK／CHECK、per-candidate-key bounds和public method集合无需改变。

#### 承重前提与反事实

- 前提：candidate minimum／anchor miss使某些methods在一个point-in-time record中合法缺席。
- 它支撑的结论：champion cardinality必须按represented method量化。
- 若前提为假：若合同强制为所有四method无条件产生counterfactual candidates，则全method champion可成立；但这直接违反§6.1、§6.2／§6.3的candidate existence门槛和“缺席candidate不制造0 error”，所以当前反例足以阻断。

### token-task3a-prediction-contract-rereview-claude-02

- `severity`: major
- `statement_kind`: contract consistency fact
- `conclusion_strength`: confirmed，current plan同一文件内存在相反接口／retention指令
- `primary_location`: `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:101-149`
- `related_locations`:
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:311-315`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:329-359`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:361-381`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:424-440`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:409-420,447-463`

#### 事实证据

Task-specific整改条款是正确的：Task 3A要求candidate-key V1、`PredictionDecision`和per-key 128；Task 4A返回`PredictionDecision`并单独构造durable record；Task 5只消费request decision intent。然而同一living plan的上层架构和旧Task 3 restatements仍保留整改前合同：

- Continuous improvement第6项仍写diagnostics“每method／ProfileKey／identity／epoch”最近128。
- Strategy／orchestration boundary仍写`TokenPredictor`输出`TokenPrediction`，exact／prefix的intent“在result中携带”。
- Learning lifecycle仍写Task 4直接产出`AnchorUseIntent`，没有区分request decision与prequential selection。
- Task 3 bounds仍写evaluation rows按method最近128，anchor-use条款仍写Task 4 predictor直接返回`AnchorUseIntent`。

这些不是点时历史记录，而是plan当前Architecture、continuous loop、boundary和active Task条款；它们会分别把Task 3A实现拉回method-level evaluation budget或把intent塞进durable `TokenPrediction`，与Spec及本计划后段直接冲突。Plan开头没有新增Task 3A amendment note或其它明确supersession来解除冲突。

#### 最小修法

- Plan line 110和Task 3 line 313改成每candidate key／`ProfileKey`／identity／epoch最近128 matching samples，同method variants各有独立budget。
- Strategy boundary改成request-side predictor返回ephemeral `PredictionDecision`，prequential builder返回`PredictionRecord`；`TokenPrediction`只表示durable candidate fact。
- Lifecycle和Task 3 anchor-use条款改成Task 4 request decision产生intent、Task 5只排request decision intent；prequential challenger不排use。
- 在plan review-amendment header登记Task 3A为何supersede这些旧restatements。Recommended data model可顺带补`capability_visual_tokens`专槽，但当前省略本身不构成相反行为。

完成后，原Finding 01除新finding 01外的candidate-key persistence面可关闭，原Finding 03可关闭。

#### 承重前提与反事实

- 前提：living plan的Architecture／boundary／continuous-loop条款仍会指导implementer，不是不可执行的历史记录。
- 它支撑的结论：同文件相反restatement是major且必须在source前同步。
- 若前提为假：若plan明确把这些段落标为superseded point-in-time history，冲突可降为文档噪声；当前没有该标记，且plan header称本文拥有实施顺序与接口，所以不能这样解释。

### token-task3a-prediction-contract-rereview-claude-03

- `severity`: minor
- `statement_kind`: documentation completeness fact
- `conclusion_strength`: confirmed against the prior report’s rejected-route list
- `primary_location`: `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:506-529`
- `related_locations`:
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:168,198,270,409-420,449,632`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task4a-prediction-dto-gap-review-claude.md`

#### 事实证据

原Finding 01的champion-only、ordinal identity、variant-as-public-method路线已由§11 row 526保留；JSON-only／事后重选champion由§6.0／§8.2明确否决。原Finding 02的FeatureVector double-weight理由已进入§4.1，visual-in-known和aggregate-pixel进入§11 row 527，immutable descriptor snapshot进入§4.2。原Finding 03的intent-in-candidate进入§11 row 528。

仍缺一条原报告明确比较后不采用的路线：`tuple[TokenPrediction, AnchorUseIntent | None]`。Current authority选择`PredictionDecision`，但没有记录tuple为何不采用——它没有跨字段validation owner，且后续增加offer facts会继续堆位置槽。Revision record line 632把理由指回点时review reports；依项目规则，报告不能成为该internal decision的唯一living source。

#### 最小修法

在§11 row 528追加tuple carrier，或新增一行“untyped tuple carrier”：承认它可传递两个值，但否决其缺少method／kind／identity／epoch cross-field constructor validation与可演进的named owner。无需改变`PredictionDecision`行为、schema或Task 3A source范围。

## V1 in-place 前提复核

结论：**SUPPORTED，不阻断。** 当前repo的`.git/HEAD`指向`refs/heads/main`，该ref当前值为`e4edc6ebebb91427654c8ce86f88b6c9b57bbd08`；main working tree中`learning_schema.py`、`learning_store.py`、`learning.py`和`prediction.py`均不存在，对`TokenLearningStore`、`tokenization-learning.sqlite3`及`record_anchor_use(`的`src/app`搜索退出1。Current status SHA-256 `ff9817b00abada9ccdd1d54d41ca9460119b3d7675b4e8236328273ff59d3296`又明确记录Task 3 integration candidate基于该main、尚未ff，Task 5 lifecycle pending，Task 4A source未启动。

这些证据足以支持当前项目边界内“旧V1尚未集成main、learning lifecycle尚未部署”，因此Task 3A可在集成前原地修订V1 manifest。它不构成任意外部私有copy从未运行过的全称证明；但项目没有给出这种外部兼容面，且plan Task 3A已写明一旦实施时发现外部V1 database就停止并改为新version＋migration。缺少对臆测外部copy的证明不构成当前阻断。

## 被否路线完整性结论

**PARTIAL。** 所有会改变行为／schema的原Finding 01～03被否路线均已在Spec normative clauses或§11中保留，未把variants变成public methods，也未把visual塞known／FeatureVector或把intent持久化。唯一缺口是上述tuple carrier的internal-interface rationale；定级为minor，不单独阻断Task 3A，但按`record-what-not-adopted`应在本轮修正。

## 当前批准条件

1. 修正new finding 01的represented-method champion cardinality和candidate-key／method-champion双error sequences。
2. 修正new finding 02列出的四处active plan restatements。
3. 记录new finding 03的tuple carrier否决理由。
4. 重新计算完整Spec／plan SHA并做本scope复核；达到0 Blocker／Major后才可给出`APPROVED`并启动Task 3A source。Task 4A仍等待Task 3A reviewed source。

## 搜索面与证据边界

- 重新计算并在报告完成前复算Spec／plan完整SHA；两次均与coordinator给定值一致，没有moving authority。
- 对照原报告三个finding逐段读取current Spec §4、§6～§8、§11～§13及revision record，读取plan top-level data model／continuous loop／strategy boundary、Tasks 2／3／3A／4A～4C／5／8和current status。
- 用exact pattern扫描current Spec／plan中的method-level retention、direct `TokenPrediction`／`AnchorUseIntent` carrier和champion cardinality措辞；逐条读完整子句后才判冲突。
- V1 in-place证据只覆盖当前repo main ref／working tree与living status；不冒充对未知外部copy的全世界否定。
- 未运行source tests，因为本轮整改只有contract且Task 3A source尚未开始；未重审Task 3 cancellation／migration等无关合同；未修改Spec、plan、status或source。

## 总体判定

**NEEDS FIXES。** Current amended authority已正确解决原Finding 02，并解决原Findings 01／03的大部分核心设计，但仍有1 Blocker、1 Major、1 Minor。Task 3A source在前两项修正并完成scoped复核前不可启动；因此也不能启动Task 4A source。

## 我最没把握的三个判断

1. **把“每个method”解释为所有四method而非represented methods。** 置信度高：同句要求champion key存在，cold-only record给出直接矛盾；若作者认为前文“当时存在”语法上同时限定methods，只需把该限定写显式即可关闭。
2. **New finding 02定为major而非blocker。** Task-specific sections已给出正确实现方向，因此问题不是无法推导唯一修法；但plan上层active contract会把实现拉回两个原缺陷，按关键实施接口缺陷定major。
3. **未知外部V1 copy不阻断in-place修订。** 证据充分覆盖项目当前main与计划中的production lifecycle，但不能证明任意私有copy不存在；依据用户的trusted environment风险判断和plan的fail-stop触发器，不把无观察依据的外部部署假设升级为门。

## 执行本契约时遇到的摩擦

Harness不允许isolated agent从shared main执行read-only git命令，所以无法直接`git show 143e077`。本轮以coordinator给定amendment short SHA作provenance，并以current Spec／plan完整SHA作为实际被审bytes；main ref通过`.git/HEAD`及`refs/heads/main`直接读取，模块／symbol存在性通过普通filesystem和`rg`核验。该限制不影响current contract verdict。

## 交付声明

- `delivery_complete`: true
- `completed_at`: 2026-09-07
- `finding_total`: 3
- `blocker`: 1
- `major`: 1
- `minor`: 1
- `nit`: 0
- `verdict`: NEEDS FIXES
