# Task 3A implementation brief 限定复核

> 转录说明：reviewer因自动隔离无法写入active `.dev`路径，主会话按其完整最终回传正文转录；除本说明外，不改写原报告内容。

- `report_id`：`task3a-brief-rereview-gpt-sonnet`
- `attempt_id`：`260907-task3a-brief-rereview-gpt-sonnet-01`
- `reviewed_at_rev`：brief SHA-256 `f2db75d3dad687f762387142407cafd8c2ae5f2649754c6e794f18b090a7f2cd`；Spec SHA-256 `2644ad9a44a9b0b06f072513dfb82834f8512f5b3fc6272a435b45a8a8445834`；plan SHA-256 `ab7da5a2f0c5c292824ec14f52fbc5657c91fabf5f264428a493042821e3ab68`；dotdev amendment `fabd0d0`；source base `a2779b644844dcf6cc36454c12b85f4e9f09c2e8`
- 原评审：`task3a-brief-review-gpt-sonnet`
- 交付方式：自动worktree隔离阻止写入共享main的指定报告路径，故按fallback完整内联回传；未覆盖初审报告。

## 评审范围

本轮严格限于原Major 01、原Major 02、对应整改及直接相邻合同。读取了：

- `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`的§6.0、A8、A32-P、revision record及visual生产终态相邻条款
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md`的Task 3A、Task 8、cross-task evidence与amendment
- 初审中已经固定的exact source base接口事实

没有重新进行broad source survey，也没有运行tests。三个fixed SHA在开始和交付前各复算一次，两次均严格相等，未发生moving snapshot。

## 总体 verdict

**APPROVED**

- Blocker：0
- Major：0
- Minor：1
- 原findings addressed：2
- 原findings open：0
- Implementer dispatch：允许

## 原findings逐项复核

### `task3a-brief-review-gpt-sonnet-01`：ADDRESSED

原问题是`PredictionRecord`可接受represented exact或cold-start champion为false，导致错误selection或持久化错误的点时eligibility事实。

整改现状：

- Brief `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:47`明确represented exact与cold-start champions必须`eligible_for_selection=True`，只有prefix／profile允许按点时状态为false。
- 同一条款明确拒绝exact／cold false，cold-only record必须含eligible cold champion，selected仍按四method顺序取首个eligible represented champion。
- Brief `:90`要求exact-false、cold-false分别作为DTO负控，且要求prefix／profile false正控继续合法。
- Brief `:95`要求selected／champion／eligibility的independent persistent corruption coverage；`:98`新增删除exact／cold unconditional eligibility validator的目标mutation。
- Spec `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md:268`把同一规则写入behavior authority，并明确即使selected暂时不变，cold-false仍属于corruption。
- Spec A8 `:558`同时包含cold-only正控、exact／cold恒true、prefix／profile可变及exact-false／cold-false mutation。
- Spec A32-P `:582`要求all-epoch private validator拒绝represented exact／cold false，并保留cold-only与older-evaluation allowed controls。
- Plan `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:357-362`同步DTO、persistent validation、tests和mutation，不再只依赖predictor producer正确赋值。

反例现已可判否：exact false＋cold true＋selected cold会被DTO和persistent validator拒绝；profile true＋cold false＋selected profile即使selection值暂时不变，也会因错误cold eligibility被拒绝。Cold-only cardinality与四method selected order没有回归。

结论：**ADDRESSED**。

### `task3a-brief-review-gpt-sonnet-02`：ADDRESSED

原问题是Task 3A只定义raw-dimension patch grid，却没有明确其阶段性性质，也没有给Task 8扩展resize／limit representation的owned file与接力合同。

整改现状：

- Brief `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:61`把首版formula明确命名为synthetic／unresized variant，并禁止Task 3A把它接入production catalog。
- 同一条款把Task 3A source review的批准面限制为A18分槽、presence、pickle、per-item unresized arithmetic和V1 persistence，明确不得冒充真实descriptor formula已闭合。
- Brief明确Task 3A不猜resize数值、PDF或其它provider formulas。
- Plan `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:352-358`同步该阶段边界。
- Task 8 owned files已在plan `:515`显式加入`src/app/tokenization/types.py`。
- Task 8接口 `:524`要求先按已核provider事实扩展同一closed formula union，使其能表达descriptor resize／limit／visual formula，并增加estimator generation，之后production catalog adapter才可生成该variant。
- Task 8行为项 `:530`要求以official／recorded provider facts固定并测试参数、边界和公式，且禁止把Task 3A synthetic formula冒充production visual count。
- Spec §4.2的最终生产目标仍保持“descriptor immutable snapshot执行resize／limit／visual formula”，没有被阶段性Task 3A实现改写或降级。

因此Task 3A现在只是明确标注的内部mechanics切片；Task 8拥有补齐生产representation与catalog wiring的文件和前置条件。A18的29＋6、6-vs-8、presence和V1 persistence可先实现，同时不会把未核resize／PDF规则写进生产行为。

结论：**ADDRESSED**。

## New findings

### `task3a-brief-rereview-gpt-sonnet-01`：实施报告仍写“五个mutation”，但当前任务实际要求六个

- `severity`：Minor
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:118`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-3A-brief.md:98`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/plan.md:362`
- `evidence`：整改为Major 01新增了“删除exact／cold unconditional eligibility validator”mutation。Brief `:98`和plan `:362`现在都明确枚举六项：candidate-method collapse、exact／cold eligibility guard删除、evaluation PK少variant、visual塞known、visual column缺失、intent入candidate。Brief的最终报告要求仍写“包含五个mutation的目标失败与恢复证据”。
- `counterexample`：Fresh implementer按报告段的数字只收集五项证据时，可能遗漏新增加的eligibility mutation，但最终报告仍满足字面“五个”，造成报告层false-green。
- `impact`：前文逐项清单和plan都完整，implementer有明确绕行，不影响production实现或测试合同，因此不升级为Major。
- `minimal_fix`：把`:118`的“五个mutation”改为“六个mutation”，最好同时要求按`:98`逐项列名，避免以后增加mutation时只同步数字。
- `conclusion_strength`：confirmed。

除此之外，本限定范围内未发现新Blocker或Major。

## 新增被否路线

无。整改只是明确Task 3A synthetic seam与Task 8 production ownership，没有新增需要写入living Spec §11的方案否决。

## 我最没把握的三个判断

1. 新finding定为Minor，置信度高。逐项mutation清单与plan已经给出唯一执行路径，所以它只影响报告完整性提示，不阻断核心实现。
2. Task 3A synthetic formula与最终Spec不冲突，置信度高。成立条件是brief规定的“绝不接production catalog”以及Task 8必须先完成closed production representation；这两个条件现在均已明写。
3. Eligibility mutation是否应拆成exact与cold两个独立source mutation，置信度中等。当前DTO和persistent tests要求两个反例分别判红，删除共同validator的一次mutation足以证明共同guard接线；本轮没有依据要求把一个semantic guard强拆成两次mutation。

## 执行本契约时遇到的摩擦

自动worktree隔离阻止本leaf将报告写入 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-brief-rereview-gpt-sonnet.md`。本轮未修改任何文件，完整正文在此回传供coordinator原样转录。

## 交付声明

- `delivery_complete`：true
- `completed_at`：2026-09-07
- `finding_total`：1
- `blocker_count`：0
- `major_count`：0
- `minor_count`：1
- `original_findings_addressed`：2
- `original_findings_open`：0
- `verdict`：**APPROVED**
- `implementer_dispatch_allowed`：true
