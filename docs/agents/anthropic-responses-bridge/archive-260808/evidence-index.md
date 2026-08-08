# 2026-08-08 关键证据索引

## 使用边界

本索引只为本会话收尾提供最短证据路径，不枚举全量 `docs/tmp` 报告，也不替代任何原报告或live文档。每个链接都是 point-in-time artifact，只对报告正文绑定的commit、候选HEAD、文档hash、运行窗口与评审范围成立；较晚报告可以补充或推翻较早结论，但不会改写较早报告本身。

要判断“现在是什么状态”，请读取 [Implementation](../implementation.md)、[Readiness](../../service-cutover/readiness.md)、[Systemd runtime Plan](../../systemd-runtime/plan.md)与[Service cutover Plan](../../service-cutover/plan.md)。要判断行为expected或验收方法，请分别读取 [Spec](../spec.md)与[Acceptance](../acceptance.md)。

## Spec／architecture

- [Spec carrier final review](../../../tmp/260807-review-spec-carrier-final.md)：固定最终双carrier合同与Spec `FINALIZED`内容身份；只证明Spec可作为行为oracle，不证明产品实现通过。
- [Architecture decision matrix review](../../../tmp/260807-review-architecture-decision-matrix.md)：确认唯一用户裁决面收敛为`D-ARCH`／`D-MIGRATION`；0 blocker／0 major不等于用户已经接受Architecture。
- [Architecture final-state review](../../../tmp/260807-review-architecture-final-state.md)：核对Architecture继续是非规范提案，并保持技术正文与裁决矩阵身份。
- [Acceptance empty-reasoning R2 review](../../../tmp/260807-review-acceptance-empty-reasoning-r2.md)：固定current Acceptance oracle及one-empty-item／one-bare-block合同；明确完整产品继续`UNVERIFIED`。
- [Current Spec／Acceptance joint review](../../../tmp/260807-review-spec-acceptance-current.md)：对账Spec与Acceptance的权威关系、内容身份和产品未通过边界。

## Foundations／happy path

- [Bridge foundations merged-state review R2](../../../tmp/260806-review-code-bridge-foundations-r2.md)：reasoning cardinality、session liveness与request converter基础组合态的定向代码复评。
- [Bridge foundations verification R2](../../../tmp/260806-verify-bridge-foundations-r2.md)：对应foundations声明范围的独立复验；范围外不得外推。
- [Current main foundations＋systemd review](../../../tmp/260807-review-main-foundations-systemd.md)：确认foundations与systemd runtime进入当时main后的组合接缝；只绑定该历史main。
- [Current main happy／usage review](../../../tmp/260807-review-main-happy-usage.md)：non-stream、carrier、stream parser、route policy与usage进入当时main后的合并态复核。
- [Bridge successor merged-state review](../../../tmp/260807-review-code-bridge-successor.md)：semantic parity、route happy与block delivery successor组合态代码评审。
- [Bridge successor verification](../../../tmp/260807-verify-bridge-successor.md)：对应successor声明范围的独立verification；报告明确保留完整stream与完整产品`UNVERIFIED`。
- [Current main successor review](../../../tmp/260807-review-main-successor-resume.md)：三片进入main后的最终合并接缝复核，并识别后续capability／History缺口。
- [Current main successor verification](../../../tmp/260807-verify-main-successor-resume.md)：对已实现语义、non-stream route与block skeleton作scoped `PASS`，同时明确不覆盖production stream、retry、quota与partial write。

## Stream真实兼容

- [Stream route final code review R3](../../../tmp/260807-resume-review-stream-route-r3.md)：stream route候选最终0 blocker／0 major评审，放行该切片而非完整Acceptance。
- [Stream route final verification R3](../../../tmp/260807-resume-verify-stream-route-r3.md)：绑定同一stream候选的限定范围验收。
- [Backup-port happy smoke execution](../../../tmp/260807-resume-backup-port-smoke-execution.md)：在`4142` app＋`4143` fake拓扑上取得`PASS_HAPPY_BACKUP_PORT_SMOKE`，并明确列出未执行矩阵。
- [Backup-port smoke R3](../../../tmp/260807-final-backup-port-smoke-r3.md)：在后继main上复验关键主路径与History request facts，不替代真实upstream或完整Acceptance。
- [Stream facts main review](../../../tmp/260807-final-review-stream-facts-main.md)：关闭backup smoke暴露的stream request-facts定向缺口，保留retry／quota／partial-write未验证边界。
- [Real Copilot canary summary](../../../tmp/260807-real-copilot-canary.md)：记录`main@fb4272b…`的真实upstream结果；其首份摘要曾缺少可访问原始输出。
- [Real Copilot canary evidence-gap review](../../../tmp/260807-review-real-copilot-canary.md)：明确指出首份摘要的provenance major，防止以同源复述冒充独立证据。
- [Real Copilot canary independent rerun](evidence/real-copilot-canary.md)：2026-08-08独立复跑，实际取得readiness 200、目录32／10、non-stream 200、stream 200及合法Anthropic事件序列，并记录隔离与清理。
- [Current main real Copilot path review](evidence/current-main-real-copilot-path-review.md)：把真实canary与current代码／正反测试对账，限定范围为0 blocker／0 major；明确未执行完整Acceptance与真实故障矩阵。

## Runtime／cutover

- [Systemd S3＋S4 new-main review](../../../tmp/260807-resume-review-systemd-rebuild.md)：graceful timeout S3与rootless installer S4的new-main组合评审；只授权仓库内逐片收敛，不授权安装或manager操作。
- [Systemd S3＋S4 independent verification](../../../tmp/260807-resume-verify-systemd-rebuild.md)：验证S3／S4代码与静态／direct runtime合同；明确不覆盖真实manager、effective cgroup、生产端口或cutover。
- [Current-main capability／History／stream／S3／S4 review](../../../tmp/260807-final-review-current-main.md)：记录五片进入当时main后的组合状态，并发现随后由stream request-facts切片关闭的History major；不得把该历史major当成current状态。
- [S5 user-manager／cgroup smoke](../../../tmp/260807-systemd-user-manager-smoke.md)：helper、临时apply、unit verify与direct inherited-fd路径通过，但独立manager未创建private control socket，真实activation／effective cgroup／restart／manager stop统一为`BLOCKED`。
- [S5 private manager diagnosis](../../../tmp/260807-systemd-user-manager-diagnosis.md)：确认当前VS Code调用上下文位于不可写`/init.scope`且缺少可用delegated cgroup链；建议转可销毁VM／container，不退回宿主user manager。
- [Current service cutover inventory](../../../tmp/260807-current-service-cutover-inventory.md)：旧Bun、双栈`4141`、数据资产与`cc-daemon`隔离边界的历史现场快照；PID、listener与writer信息必须在任何未来动作前重取。
- [Service cutover Plan R3 review](../../../tmp/260807-review-service-cutover-plan-r3.md)：确认living cutover计划在其内容身份上为0 blocker／0 major，并继续保持`NO_CUTOVER`、数据fence、rollback与`cc-daemon`禁触碰边界。

## 解释规则

- 报告标题中的`PASS`、`0 blocker／0 major`或“可进入下一阶段”只适用于该报告声明的对象和范围，不能拼接成完整产品`PASS`。
- 候选评审、main-side测试、fake upstream smoke、真实Copilot canary、真实manager probe与生产cutover是不同证据层级，彼此不能替代。
- 原报告与live载体冲突时，先区分行为oracle、验收oracle、point-in-time证据与易变状态；易变状态以live `Implementation`／`Readiness`／`Plan`为准，历史报告保持原样。
