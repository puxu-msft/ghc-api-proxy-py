# Anthropic Messages ↔ OpenAI Responses bridge 文档索引

## 权威边界

本目录按职责分层，文档不能互相替代：

| 文档 | 角色 | 权威范围 |
|---|---|---|
| [spec.md](spec.md) | 唯一行为 oracle | 用户可观察行为、兼容策略、字段处置、路由、buffering、retry、usage、error、lifecycle 与非功能不变量 |
| [acceptance.md](acceptance.md) | 验收 oracle | 如何把 Spec 转成可执行验收；不能自行增加 Spec 未定义的 expected |
| [architecture.md](architecture.md) | 非规范架构提案 | 内部组件、owner、typed facts 与迁移方式；未经用户接受前不是 ADR，也不能覆盖 Spec |
| [research.md](research.md) | 可追溯证据来源 | 参考实现、固定 commit、可移植机制、反例和不可照搬项；不产生产品行为合同 |
| [implementation.md](implementation.md) | 易变实施状态真相源 | Current main、已回并切片、活动候选、评审状态和下一动作；保持 living，不因开始实施或一次 checkpoint 而收口 |

发生冲突时，行为回到 Spec，验收方式回到 Acceptance，架构选择回到用户对 Architecture 的裁决，易变进度回到 Implementation，外部实现事实回到 Research。

## 阅读顺序

1. 完整阅读 [spec.md](spec.md)，先确定不可由实现重新选择的行为。
2. 阅读 [research.md](research.md)，理解来源、反例与兼容边界。
3. 完整阅读 [architecture.md](architecture.md)，再分别裁决 `D-ARCH` 与 `D-MIGRATION`。
4. 阅读 [acceptance.md](acceptance.md)，确认如何证伪实现。
5. 最后阅读 [implementation.md](implementation.md)，核对 current main、活动切片与下一动作。

不要只读 Architecture 的推荐结论或 A／B／C 对比表后直接裁决。Spec 已裁决的产品行为不是 Architecture 的附加投票项。

## 当前状态入口

易变状态只维护在 [implementation.md](implementation.md) 与部署侧的 [service-cutover/readiness.md](../service-cutover/readiness.md)。本索引不复制 current commit、测试数量、canary verdict、候选清单或部署状态；替换当前前门仍须以 Readiness 和用户对当次 cutover 的明确指令为准。

## 用户架构裁决

Architecture 的全部待决面只保留两项：

- `D-ARCH`：选择长期目标内部架构。当前提案推荐方案 B，即 typed semantic kernel＋single driver＋protocol／transport legs；方案 A 只作受约束迁移形态，方案 C 拒绝。
- `D-MIGRATION`：若选择 B，决定一次建立完整骨架，还是以受约束 adapter 分阶段迁移。当前提案推荐分阶段迁移，并要求每个 adapter 有边界和退出条件。

`ADR-BRIDGE-02`～`06` 只记录 Spec 已决行为如何被架构承载，不是隐藏的用户投票项。

## 历史证据

本轮开发与真实 canary 的关键历史入口位于 [archive-260808/README.md](archive-260808/README.md) 与 [archive-260808/evidence-index.md](archive-260808/evidence-index.md)。归档内容是 point-in-time 记录，不取代本目录的 live 文档。
