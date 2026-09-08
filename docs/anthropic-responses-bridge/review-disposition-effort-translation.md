# Effort translation Spec 评审处置

- status：closed
- scope：本文件只记录实施前的Spec评审；原“下一步”已执行，current implementation／code review终态见[代码评审处置](review-disposition-effort-translation-code.md)
- source_reports：[R1](reports/260903-review-effort-translation-spec.md)；[R2](reports/260903-review-effort-translation-spec-r2.md)；[R3](reports/260903-review-effort-translation-spec-r3.md)；[R4](reports/260903-review-effort-translation-spec-r4.md)
- received_at：2026-09-03
- R1 counts：blocker=0，major=6，minor=0，nit=0；verified=yes
- R2 counts：blocker=0，major=2，minor=2，nit=0；`finding_total=4`与分档和相等，verified=yes
- R3 counts：blocker=0，major=2，minor=1，nit=0；`finding_total=3`与分档和相等，verified=yes
- R4 counts：blocker=0，major=0，minor=0，nit=0；`finding_total=0`与分档和相等，reviewed content hashes逐项复算相等，verified=yes
- reviewed_content_identity：checklist=`0d25e6f…`，spec=`c993a7a…`，acceptance=`d89ffd1…`，implementation=`165b752…`；与报告头逐项相等

## 处置表

| Finding | 陈述类型与成立度 | 裁定级别 | 处置 | 理由与实际修法 |
|---|---|---|---|---|
| EFFORT-M01 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，经R2-M01／R3-M01／R3-M02在R4关闭 | 官方 schema／model-specific 事实成立，采纳并纠正文案。但不删除活路径已实现的 `auto`、缺 budget `enabled` 与正整数低 budget兼容输入；它们改为 translated-path compatibility extension并明确不是 Anthropic 官方形状。逐消息 effort 在直连腿仍由官方 model gate，翻译腿按用户已批准的 bridge能力与 target effort capability执行，不冒充每个 Claude model官方支持。 |
| EFFORT-M02 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，R2确认关闭 | Enabled 候选包含 `none` 会翻转启用状态，违反用户裁决。正向 enabled 对齐排除 `none`；只剩 `none` 时稳定拒绝并补同入口控制。 |
| EFFORT-M03 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，effort总函数及thinking profile均在R4关闭 | “按 catalog 对齐”不足以让反向实现收敛。补 exact／downward／floor／missing／empty／unrankable 的发送值、loss 与拒绝／继续终态，并在 REQ-05A 写静态 expected 和单缺陷控制。 |
| EFFORT-M04 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，R2确认机制级控制成立 | 验收分母缺控制成立；按机制类别补 reverse alignment、siblings merge、count header、direct bypass、null／absent 和future-only control。不会为每个枚举值复制控制或建设新 mutation framework。 |
| EFFORT-M05 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，R2确认major关闭 | Spec摘要与 current CAL-04 确实仍写首块前零headers／ping。同步 Spec restatement，并把 current grammar升为v2：headers不属于body grammar且可先提交，initial body state允许独立ping batch，`message_start`仍须与首块同batch。旧评审只留点时报告。 |
| EFFORT-M06 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，R3经R2-M02确认关闭 | Implementation多处仍把旧Spec／Acceptance hash称为current。全部改成指向live authority和本轮复核状态；旧hash只留在明确历史段，不再作为current放行依据。 |

## R2 新发现处置

| Finding | 陈述类型与成立度 | 裁定级别 | 处置 | 理由与实际修法 |
|---|---|---|---|---|
| R2-M01 | `fact`：`confirmed`；`decision`：`user-selected-from-proposal` | A | `adopted`，split到R3-M01／R3-M02后由R4关闭 | 官方model thinking modes与catalog信息缺口成立。用户裁定capability只取`model_translation.to_anthropic_messages.thinking_profiles`配置；bundled默认配置是官方表的resolved-model正则转录，用户配置覆盖。Profile冻结modes、can_disable、disabled effort上限及可选manual budget；unknown、always-on disabled、extended-only缺budget、budget与`max_tokens`不相容均拒绝，不从effort推budget。 |
| R2-M02 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，R3确认关闭 | 逐处改写执行表／开发线／怪味表中把`c1de6bf…`称为current的单元；历史身份带2026-08-08／当时限定，未限定current统一由`git rev-parse HEAD`读取。 |
| R2 minor汇总 | 报告按契约未展开，不能形成可核验独立finding | D | `no_change_needed` | 两项minor不阻断且无finding_id／场景／位置，不能伪造处置；若后续报告展开再登记。 |

## R3 新发现处置

| Finding | 陈述类型与成立度 | 裁定级别 | 处置 | 理由与实际修法 |
|---|---|---|---|---|
| R3-M01 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，R4确认关闭 | 第六条regex越界认领官方未列的Sonnet／Haiku 4.1与Haiku 4。改为官方family精确alternation；六条regex各要求正样本与邻近负样本，已用14个正样本及三个目标负样本检查唯一命中。 |
| R3-M02 | `fact`：`confirmed`；`judgment`：`concurred` | C | `adopted`，R4确认关闭 | “首个可渲染”与“enabled不可渲染即拒绝”冲突。冻结为按modes顺序扫描：单项不可渲染继续，全部不可渲染才拒绝；`[enabled,adaptive]`有合法budget用manual，无／不相容budget回退adaptive；`[enabled]`同条件拒绝。 |
| R3 minor汇总 | 报告按契约未展开，不能形成可核验独立finding | D | `no_change_needed` | 一项minor不阻断且无finding_id／场景／位置；若后续报告展开再登记。 |

## 承重测试

- 前提：报告中的官方 API 与当前文档矛盾事实成立。
- 支撑动作／结论：采用 M01～M06 并修订 current Spec、Acceptance、Implementation。
- 若前提为假：M01 的官方／compatibility 分界及 M05／M06 的同步修订会失去依据，文档不应据此更改。独立读取官方 Effort／Messages／Extended thinking、报告绑定hash、当前CAL-04和Implementation restatement后，前提均已确认；M01 的兼容保留和 M04 的控制粒度是协调者判断，须交原 reviewer 明确复评。

## 后续执行结果

1. 用户已审阅并批准当时的current Spec；实施计划随后形成并经独立R5以0 findings关闭。
2. Tasks 1～5已从保留的effort worktree实施，生产代码另经逐Task review、whole-branch review、唯一fix wave与scoped R2，不复用本轮文档pass；reviewed source已归档且净语义进入main。Current证据见[Implementation](implementation.md)与[代码评审处置](review-disposition-effort-translation-code.md)。

## Closeout

- consensus：R4对R3-M01／R3-M02及其合并来源给出0 blocker／0 major／0 minor／0 nit；全部有效finding均为`adopted`或无可处置正文的`no_change_needed`，无`open`、无`disputed`、无待回应标注。
- current authority：[spec.md](spec.md)；Acceptance只转录判据，Implementation只报告实现状态；本处置账只记录本轮评审结论。
- evidence boundary：本轮文档pass在当时不证明任一路由、wire、配置或测试已经实现；后续实现证据由[代码评审处置](review-disposition-effort-translation-code.md)独立承载，不能反向扩大本轮R4的评审范围。
