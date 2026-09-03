# Effort translation 实施计划 R3 定向复评

- review_id：effort-translation-plan-260903-r3
- attempt_id：effort-translation-plan-gpt-opus-a3
- source_report：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/reports/260903-review-effort-translation-plan-r2.md`
- 复评范围：R2-M1／R2-M2、pure nested Task 2边界、Task 3全部旧test consumer迁移、Task 5 profile facts producer与exception-copy snapshot mutation及直接相邻接口；不重开R2已关闭轴。
- 源码观察点：`/home/xp/src/ghc-api-proxy-py` current working tree；Implementation `implementation.md:18`明确production implementation尚未开始。

## 整体判定

**needs-fix。** R2-M2已关闭；R2-M1的两项核心整改已经写入，但执行顺序和Task 2 source-header integration分支仍留下一条major。当前共0 blocker、1 major、0 minor、0 nit，计划尚不能按现有checkbox顺序直接执行。

## R2发现处置核验

| R2 finding | R3结论 | 定向核验 |
|---|---|---|
| R2-M1 Task 2 nested证据越界、Task 3旧test consumers未闭合 | 仍有major（R3-M1） | pure nested代表测试已改为只构造`SemanticRequest`，后继精确sibling test已明确移到Task 4；旧test symbol清单、`rg`与collect也已补上。但Task 3的pre-delete迁移／collect写在执行删除的Step 4之后，Task 2还保留一个只有Task 3实现后才有意义的“真实per-message输入”选项。 |
| R2-M2 Task 5缺profile facts producer及异常mutation恢复 | 关闭 | Task 5 Files已加入`anthropic_messages.py`；成功／拒绝writer facts、JSONL exact断言、driver WIP snapshot、捕获test rc、无论非零／零都先恢复、binary diff比较及恢复后正样本均已写明。 |

## P1～P15 定向回应

| ID | 结论 | 本轮范围内的依据 |
|---|---|---|
| P1 | MAJOR（R3-M1） | facts持久化owner已补齐；Task 2／3交界仍没有一条可按文档顺序执行的consumer迁移链。 |
| P2 | MAJOR（R3-M1） | Task 2 pure production与pure nested probe已成立，但其integration测试仍给出尚未实现的真实per-message分支；Task 3则在迁移test consumer前先删production symbols。 |
| P3 | MAJOR（R3-M1） | 新符号owner未变；旧test consumers虽已枚举，却在消费者迁移／collection之前被Step 4删除。 |
| P4 | PASS | 本轮整改未改变R1／R2已确认的import方向和startup compile边界。 |
| P5 | PASS | 不在R3重开范围；R2已确认strict bool、merge顺序与selector证据闭合。 |
| P6 | MAJOR（R3-M1） | header capture生产步骤仍正确，但Task 2允许用尚不读取header的真实per-message reader作integration证据，不能证明两入口把清空前header交给reader。 |
| P7 | PASS | 逐消息candidate／shape／field path helper仍由Task 3完整定义；本轮只指出它不能倒流充当Task 2证据。 |
| P8 | PASS | 一次切换后的目标终态仍删除旧resolver；问题仅是删除与consumer迁移的步骤顺序。 |
| P9 | PASS | 不在R3重开范围；profile映射与manual budget终态未被本轮整改改变。 |
| P10 | PASS | Task 2第361～374行现在只验证pure `nested_extensions_for()`，Task 4第376行接管effort sibling精确loss，owner边界已修正。 |
| P11 | PASS | Task 5第772～893行现在覆盖producer→exception／success copy→RequestContext→RequestTrace／RequestLine→JSONL，并让`lossless`继续只看losses。 |
| P12 | PASS | direct bypass轴未被整改重开，profile writer新增facts不改变route guard。 |
| P13 | MAJOR（R3-M1） | exception-copy mutation已安全闭合；但Task 2“真实per-message输入”在该切片中对source header不敏感，会成为不具分辨力的可选证据。 |
| P14 | MAJOR（R3-M1） | Task 5路径／commit边界已闭合；Task 3按当前Step 4→Step 6顺序会经历test collection破损状态，仍不是可直接执行的独立切片。 |
| P15 | MAJOR（R3-M1） | 没有新增未定义helper或`ruff format`；剩余问题是互相矛盾的执行时序与Task 2无效二选一测试路径。 |

## Blocker／Major findings

### R3-M1［major，R2-M1未完全闭合］Task 2仍允许后继语义充当证据，Task 3又把pre-delete检查排在删除之后
- Task 2第378行仍写“monkeypatch reader或使用真实per-message输入”；但第262、307行冻结该Task reader为旧行为，逐消息header／control解析直到Task 3第420～500行才存在，因此真实输入在Task 2对`source_headers`变化不敏感，不能证明header接线。
- Task 3第523～525行的Step 4已经删除`ReasoningIntent／resolve`等symbols，迁移全部旧test consumers及“删除production symbols前”的`rg`／`pytest --collect-only`却写在后面的Step 6第556～558行。
- 按checkbox顺序执行时，Step 4后当前`tests/unit/pipeline/translation_driver/test_reasoning.py:7-178`仍import／调用已删除symbols，进入Step 6前即处于collection `ImportError`状态；Step 6声称的pre-delete检查在时间上已不可执行。
- Task 2固定只用monkeypatch reader验证header；Task 3把旧test consumer迁移、`rg`与collect移到删除动作之前，再删除production symbols并至少再collect一次确认最终状态。

## 我最没把握的三个判断

1. **把Task 3步骤倒序定为major，置信度高。** 若把checkbox标题只当无序目标，可人为先做Step 6的一半；但计划开头明确要求task-by-task、checkbox tracking，且本轮复评条件专门要求“删symbols前collection闭合”，不能靠执行者重排来补正。
2. **把Task 2的“真实per-message输入”判为无效证据，置信度中高。** 它在Task 3后当然有效，但Task 2明确保留旧reader且该切片必须独立评审；唯一闭合做法是该Task使用自建／monkeypatch reader，真实per-message测试留在Task 3。
3. **R2-M2判关闭，置信度中等。** 结论依赖profile rendering继续位于新增到Task 5清单的`anthropic_messages.py`；计划第867行已明确这个producer归属，若实现者另移renderer，应同步调整Task 5路径，而那会是执行偏离而非当前计划缺口。

## 执行摩擦

- R1已确认`my-agents:as-reviewer`在本harness不可用；R3沿用该已记录能力事实，没有重复发起必然失败的skill调用。
- `plan-effort-translation.md`仍是`.dev` repo中的untracked文件，无法取得Git parent diff；本轮按R2报告、current plan、current disposition和Implementation活动行逐项对账整改。
- CodeGraph在前轮已对主树明确报告无`.codegraph/`；本轮不重复调用，直接使用已读current源码入口与更新后的文档行号完成定向复评。
- 本轮未运行尚未实现的plan tests／mutations；只审查步骤能否在未来按顺序执行，不把静态复评冒充候选代码证据。
- 唯一写入为本R3报告；未修改checklist、plan、Spec、Acceptance、Implementation、disposition、源码或tests。
- 边界判断：不执行整体closeout；可观察依据是仍有1条major待计划作者修正，coordinator需要继续处置并决定下一轮复评。

## 交付声明

delivery_complete:true
completed_at:2026-09-03T11:18:52Z
finding_total:1
blocker_count:0
major_count:1
minor_count:0
nit_count:0