# Effort translation 实施计划 R4 定向复评

- review_id：effort-translation-plan-260903-r4
- attempt_id：effort-translation-plan-gpt-opus-a4
- source_report：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan-r3.md`
- 复评范围：R3-M1、Task 2 spy-only source-header证据、Task 3 production consumers→test consumers／pre-delete collect→definitions删除→post-delete rg／collect的严格顺序及直接相邻接口；不重开已关闭轴。
- 源码观察点：`/home/xp/src/ghc-api-proxy-py` current working tree；production implementation尚未开始。

## 整体判定

**needs-fix。** Task 2证据边界和Task 3迁移／删除的相对顺序已经修正，但Step 6用全仓、通用函数名`resolve()`做零命中门，必然命中无关代码，留下1条major。当前共0 blocker、1 major、0 minor、0 nit。

## R3发现处置核验

| R3 finding | R4结论 | 定向核验 |
|---|---|---|
| R3-M1 Task 2证据越界且Task 3 pre-delete检查排在删除后 | 仍有major（R4-M1） | Task 2第378行已固定spy／monkeypatch reader，真实per-message归Task 3；Task 3第523～564行也已严格写成production consumers切换→test consumers迁移→pre-delete collect／consumer检索→definition删除→post-delete检索／collect。剩余缺陷是两次检索把通用`resolve()`扩到整个`src tests`并要求最终零命中，门本身不可通过。 |

## P1～P15 定向回应

| ID | 结论 | 本轮范围内的依据 |
|---|---|---|
| P1 | PASS | R3范围内的Task owner与证据位置已经明确；本轮缺陷是验证命令的选择器，不是owner缺失。 |
| P2 | PASS | Task 2保持旧production可运行并用spy证明header；Task 3先切production、跑probe，再迁移tests和删除definitions，未倒置为TDD。 |
| P3 | MAJOR（R4-M1） | consumers与definitions的删除顺序已正确，但用于证明consumer归零的命令无法区分目标`reasoning.resolve()`与无关`Path.resolve()`／model resolver。 |
| P4 | PASS | 不在R4重开范围；整改未改变import或startup compile方向。 |
| P5 | PASS | 不在R4重开范围。 |
| P6 | PASS | Task 2第378行现在只允许spy／monkeypatch reader，并同时断言send／count收到清空前header且Responses upstream不含该header。 |
| P7 | PASS | 真实per-message header证据明确归Task 3，不再倒流进Task 2。 |
| P8 | PASS | production consumers先切换，旧resolver definitions直到pre-delete检查后才删除，语义顺序已闭合。 |
| P9 | PASS | 不在R4重开范围。 |
| P10 | PASS | pure nested边界维持R3已确认状态。 |
| P11 | PASS | 不在R4重开范围；R3已关闭profile facts链。 |
| P12 | PASS | 不在R4重开范围。 |
| P13 | MAJOR（R4-M1） | post-delete“零命中”门会被无关符号稳定触发，不能证明目标consumer是否归零，属于开错方向的false-red。 |
| P14 | MAJOR（R4-M1） | 语义步骤顺序已正确，但Task 3会在无关`resolve()`命中处被阻断，仍不可按计划完整执行与提交。 |
| P15 | MAJOR（R4-M1） | probe／collect本身可运行；全仓`rg`的零命中expected不可能成立，因此Task 3仍含不可执行步骤。 |

## Blocker／Major findings

### R4-M1［major，R3-M1未完全闭合］旧consumer的`rg`门把通用`resolve()`扩到全仓，post-delete零命中不可能成立
- 计划第562、564行运行 `rg -n '...|\bresolve\(' src tests`，并在删除reasoning definitions后要求零命中；该pattern同样匹配成员调用和别的局部函数。
- 当前直接探针已命中无关的`Path(...).resolve()`、`src/app/transform/model_resolver.py:64`、`tests/unit/transform/test_model_resolver.py`多处调用，以及`tests/unit/pipeline/test_model_resolution.py:39`的本地`resolve()`。
- 即使目标effort symbols全部正确删除，输入这条post-delete命令仍输出上述路径并以匹配状态结束；执行者只能错误修改无关模块、放宽“零命中”声明或卡在Step 6，三种结果都不能关闭consumer迁移。
- 将检索限制到本Task确切production／test路径，并对通用`resolve`使用能排除attribute及无关local helper的目标谓词；pre／post两轮必须使用同一精确选择面。

## 我最没把握的三个判断

1. **R4-M1定为major而非minor，置信度高。** 它不是输出噪声：计划明确要求零命中，当前稳定存在多类无关命中，Task 3按文档无法越过该步骤。
2. **不把“只允许reasoning.py／semantic.py definitions”读成隐含过滤器，置信度高。** 文字是在解释输出，实际命令仍扫描全仓且Step 5明确要求同一`rg`零命中；不能假定执行者手工忽略命令刚要求消失的结果。
3. **Task 3严格顺序判PASS，置信度中高。** Step 4只切production consumers并保留definitions，Step 6先迁移tests、pre-collect、检索consumer，再删definitions并post-collect；除检索谓词外，R3指出的时序倒置已消失。

## 执行摩擦

- R1已确认`my-agents:as-reviewer`在本harness不可用；R4继续沿用该已记录能力事实。
- 为核验post-delete门的可达性，本轮只读运行了计划中的`\bresolve\(`选择面；它稳定返回多条与effort translation无关的`Path.resolve()`、model resolver和测试helper命中。
- `plan-effort-translation.md`仍未有可比较的Git parent；本轮以R3报告、current plan、Implementation活动行和plan disposition逐项对账。
- 本轮未运行尚未实现的production probes／tests；只验证计划命令的静态选择面，不冒充代码验收。
- 唯一写入为本R4报告；未修改checklist、plan、Implementation、disposition、源码或tests。
- 边界判断：不执行整体closeout；可观察依据是仍有1条major待计划作者修正，coordinator需要继续处置。

## 交付声明

delivery_complete:true
completed_at:2026-09-03T11:23:24Z
finding_total:1
blocker_count:0
major_count:1
minor_count:0
nit_count:0