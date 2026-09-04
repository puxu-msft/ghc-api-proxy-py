# Effort translation 实施计划 R2 定向复评

- review_id：effort-translation-plan-260903-r2
- attempt_id：effort-translation-plan-gpt-opus-a2
- source_report：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan.md`
- 复评范围：R1 M1～M6、对应整改diff及直接相邻接口；不重开其余全量设计评审。
- 源码观察点：`/home/xp/src/ghc-api-proxy-py` current working tree；Implementation明确记录production implementation尚未开始。

## 整体判定

**needs-fix。** R1的M2、M3、M4、M6已按定向范围关闭；M1与M5仍各有一个major缺口。当前共0 blocker、2 major、0 minor、0 nit，尚不能把计划交给实施者执行。

## R1 M1～M6 处置核验

| R1 finding | R2结论 | 定向核验 |
|---|---|---|
| M1 Task 2无可运行中间态 | 仍有major（R2-M1） | 旧field、旧consumer与现有budget入口已保留到Task 3，但Task 2新增的nested代表测试要求Task 4才产生的Responses reasoning reader语义；Task 3删除旧symbols前的test consumer处置也未闭合。 |
| M2 `can_disable`非strict | 关闭 | 计划第57行改为`Field(strict=True)`，第179行明确字符串与0／1拒绝、YAML bool接受，符合Spec `spec.md:295`。 |
| M3 逐消息helper未定义 | 关闭 | 计划第418～498行完整定义candidate、header token、允许键、两种empty content、稳定code／field path、pending算法及过滤先于message parser的顺序。 |
| M4 未安排有限单侧控制 | 关闭 | Task 3第588～612行和Task 4第728～754行均安排正样本→单侧mutation红→snapshot恢复→binary diff相等→正样本再绿；目标文件覆盖各自列出的mutation，且未建设常驻framework。 |
| M5 异常facts可只落error detail | 仍有major（R2-M2） | JSONL exact断言已写明，但Task 5路径清单缺少产生profile facts的writer文件，且异常copy单侧mutation没有独立snapshot／恢复步骤。 |
| M6 selector漏掉代表测试 | 关闭 | 两个代表test均重命名为命中selector的名字，并分别在计划第208、383行以exact node id先执行`--collect-only -q`。 |

## P1～P15 定向回应

| ID | 结论 | 本轮范围内的依据 |
|---|---|---|
| P1 | MAJOR（R2-M1、R2-M2） | 名义Task owner已齐，但Task 2证据提前消费Task 4语义，profile facts的真实producer路径仍不在Task 5清单。 |
| P2 | MAJOR（R2-M1） | production-before-tests顺序仍在；但Task 2的新增nested test无法由该Task的production状态满足，独立切片仍不闭合。 |
| P3 | MAJOR（R2-M1、R2-M2） | 新helper签名已齐；但Task 2测试提前消费后继语义，Task 5又遗漏facts producer文件。 |
| P4 | PASS | 本轮整改没有改变R1已通过的schema→runtime profile→compiled tuple→Chain→routing→target无环方向，startup compile仍见计划第108～155行。 |
| P5 | PASS | strict bool、同pattern／不同pattern测试及exact collect均已补齐，计划第57、179、184～209行闭合R1对应缺口。 |
| P6 | PASS | source header仍在两入口调用`shape_request()`前快照并只传translator，不写回或转发，计划第308～316行未漂移。 |
| P7 | PASS | candidate以`output_config`键存在判定，错误role不会漏过；多个pending、同值override、future-only和original payload均有唯一算法，计划第418～498行。 |
| P8 | PASS | Task 3第500～523行仍明确enabled排除none、disabled要求none、缺省high、explicit优先及一次删除旧resolver。 |
| P9 | PASS | strict config与反向profile、fallback、manual budget、minimal／none映射均在Task 1／4闭合；本轮未发现与R1整改直接相邻的新冲突。 |
| P10 | MAJOR（R2-M1） | nested helper本身仍正确，但Task 2代表证据要求reader已把Responses effort从nested residual剥离，而该reader明确归Task 4。 |
| P11 | MAJOR（R2-M2） | JSONL exact槽和exception-only控制文字已修正，但产生selected／rejected facts的profile writer不在Task 5可改／可提交路径。 |
| P12 | PASS | direct两腿仍由route guard绕过translator，Task 3／4各有byte-equivalent bypass正样本与单侧控制；legacy converter／subscriber边界未被整改扩张。 |
| P13 | MAJOR（R2-M2） | Task 3／4有限控制已闭合；异常facts控制仍缺安全执行／恢复步骤，且production facts producer路径遗漏会让expected无法成立。 |
| P14 | MAJOR（R2-M1） | pathspec、`-F`及`.dev`分仓纪律未漂移，但Task 2仍不是可独立通过的语义切片。 |
| P15 | MAJOR（R2-M1、R2-M2） | 原三个未定义helper与两个selector已修；当前剩余的是可执行性缺口，不是TBD／TODO或`ruff format`问题。 |

## Blocker／Major findings

### R2-M1［major，R1 M1未闭合］Task 2的nested测试消费了Task 4语义，Task 3也未列全旧test consumers
- 计划第261、306行要求Task 2保留旧field／consumer和reader当前行为；当前Responses reader把`reasoning`留在generic extensions（`src/app/pipeline/translation_driver/openai_responses.py:48-50,86-110`）。
- 输入 `{"reasoning":{"effort":"high","summary":"auto"}}` 在Task 2状态只产生整对象`reasoning` loss，不会产生第360～374行测试要求的`reasoning.summary`精确loss；该测试所需“认领effort、只留sibling”由Task 4第641～643行才实现。
- Task 3第405、521～523行删除`ReasoningIntent／resolve`，但当前`tests/unit/pipeline/translation_driver/test_reasoning.py:7-178`仍有大量非budget import／consumer；第554～556行只明确删除budget阶梯测试，pytest会在collection阶段因残留import失败。
- 将nested代表测试移到Task 4，Task 2只钉pure residual helper与现有budget入口；Task 3则明确逐项替换或删除全部旧test consumers后再删除symbols。

### R2-M2［major，R1 M5未闭合］Task 5没有可修改的profile-facts producer，异常控制也没有安全恢复协议
- Task 5第770～780行的Files不含`translation_driver/anthropic_messages.py`或承载`render_anthropic_thinking()`的文件，但第821行要求profile writer调用`observe()`并把facts附到`TranslationRefused`；第894行又限制只提交Task 5路径。
- 例如`reasoning.effort=none`命中always-on profile时，若writer未改，异常仍使用默认`facts=()`；第849～850行复制不到任何内容，JSONL `facts`为空，第864行的exact断言无法成立。
- 第864行还要求手工切断exception copy再恢复，却没有像Task 3／4那样snapshot `driver.py`、比较before／after diff并复跑；该control不是普通pytest本身能够完成的单侧源码mutation。
- 把实际profile writer／renderer文件加入Task 5 Files与commit pathspec，并为exception-copy mutation增加当前WIP snapshot、前后binary diff相等和恢复后正样本绿的明确步骤。

## 我最没把握的三个判断

1. **R2-M1中“nested测试必须后移Task 4”，置信度高。** 唯一可能的不同读法是让Task 2提前解析Responses effort；但这直接冲突于第261、306行的“保持旧行为”和Task 4第641～643行的明确owner，因此不足以支撑隐式提前实现。
2. **R2-M1中旧test consumers定为major，置信度中等。** “更新单元与HTTP测试”可被宽读为顺手修完所有imports，但计划只点名budget阶梯，而symbol删除会让collection整体失败；按“不能靠未来实现补空白”的复评判据，我没有替计划补写该范围。
3. **R1 M4判关闭，置信度中等。** Task 4的direct Responses mutation可以修改已快照的`routing.py`而不必改未快照的`driver.py`；其余八项也各有已快照落点。若实施者改动清单外文件，当前before／after比较不覆盖，但这属于执行偏离而非计划必然缺口。

## 执行摩擦

- R1已记录`my-agents:as-reviewer`在本harness返回`Unknown skill`；R2按同一已确认能力事实继续，没有再次制造相同失败调用。
- R1使用的隔离源码worktree已不存在；Implementation明确production implementation尚未开始，因此本轮直接读取`/home/xp/src/ghc-api-proxy-py` current source作为相邻接口基线。
- 主工作树与`.dev`路径都没有`.codegraph/`，本轮`codegraph_explore`再次明确拒绝；随后使用精确`Read`与`rg`核对旧consumer及整改接口。
- `plan-effort-translation.md`、checklist、R1和plan disposition当前在`.dev` repo均为untracked，无法由`git diff`给出旧版→新版patch；本轮以R1逐条原文、current plan和disposition三方对账整改，而未伪造不存在的parent diff。
- 本轮没有运行尚未实现的plan probes／tests；结论是计划静态可执行性复评，不冒充候选代码验证。
- 唯一写入为本R2报告；未修改plan、Spec、Acceptance、Implementation、disposition或源码／tests。
- 边界判断：不执行整体closeout；可观察依据是仍有2条major待计划作者处置，coordinator还需复核并驱动下一轮定向复评。

## 交付声明

delivery_complete:true
completed_at:2026-09-03T11:12:53Z
finding_total:2
blocker_count:0
major_count:2
minor_count:0
nit_count:0