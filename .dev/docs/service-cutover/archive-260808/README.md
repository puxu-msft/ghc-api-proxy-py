# Service cutover 本会话终态记录

## 文档性质

本文是 2026-08-08 收尾时的历史终态记录，不是cutover当前状态、inventory或下一动作的第二状态源。生产接管顺序、数据disposition、时间门、rollback与观察要求以live [Service cutover Plan](../plan.md)为准；每项实时readiness及整体结论以live [Readiness](../readiness.md)为准；bridge实现状态以 [Implementation](../../anthropic-responses-bridge/implementation.md)为准。

本记录不移动、不改写原始report，也不授权任何生产动作。

## 本会话完成与未执行的事项

- Bridge foundations、happy／usage、semantic／route／block、capability／History／stream、retry／resident wiring与Copilot identity修复已按live Implementation记录进入main；真实Copilot备用端口canary取得当前层正向证据。
- Systemd M1、S3 graceful timeout与S4 rootless installer已进入main并保留reviewed-source archive refs。
- S5本机隔离诊断已执行，但独立user manager未创建private control socket，真实activation／effective cgroup／restart／manager stop保持`BLOCKED`。
- 本会话没有停止或signal旧Bun，没有释放、绑定或接管生产双栈`localhost:4141`，没有安装unit，没有执行`daemon-reload`／enable／start／restart，没有迁移／删除数据，也没有触碰`cc-daemon`生命周期。

## 真实canary与证据上限

2026-08-08独立复跑在隔离`127.0.0.1:4142`、`main@fb4272b5752bd8439c1ee5a098960f31d4ea70f1`上取得readiness 200、模型目录32／10、真实`gpt-5.3-codex` non-stream 200与stream 200；stream事件顺序为合法Anthropic终态序列。成功窗口内旧Bun incarnation不变，向旧Bun发送signal数为0，清理后`4142`无listener。

该canary只把non-stream与stream当前实测层提升为scoped正向证据，不证明完整tool／reasoning、quota／backpressure、kernel partial write、真实systemd manager／cgroup、数据disposition、rollback或生产接管。

关键point-in-time证据：

- [Real Copilot canary independent rerun](../../../tmp/260807-verify-real-copilot-canary.md)
- [Current main real Copilot path review](../../../tmp/260807-review-main-real-copilot-path.md)
- [S5 user-manager／cgroup smoke](../../systemd-runtime/reports/260807-systemd-user-manager-smoke.md)
- [S5 private manager diagnosis](../../../tmp/260807-systemd-user-manager-diagnosis.md)
- [Current service cutover inventory](../reports/260807-current-service-cutover-inventory.md)

## `NO_CUTOVER`

收尾时整体状态是`NO_CUTOVER`。以下范围未闭合，任何一项都足以阻止生产接管：

- 完整P0 Acceptance，包括真实tool／reasoning、完整quota／backpressure、kernel partial write与其余fault矩阵。
- P1真实user-manager／cgroup、双fd／IPv4＋IPv6 activation、manager graceful／force stop与运行态资源限制。
- P2 inventory＝ledger、全部data／credential disposition、唯一writer、backup／restore与refresh合同。
- P3旧`--restart` supervisor／listener／writer fence、cutover与rollback时间门、隔离rollback演练及observation baseline。
- 当次用户明确cutover授权。

旧Bun继续是生产双栈`4141` owner；历史inventory中的PID、内存、fd、writer与unit事实均为point-in-time数据，任何未来动作前必须重新采集。`cc-daemon.service`与`cc-daemon-calib.service`继续是禁止触碰的外部不变量，不得把重启、reload、改endpoint或发signal当作canary、修复或rollback步骤。

## Current live carriers

- [Service cutover Readiness](../readiness.md)：P0～P3、`cc-daemon`不变量与整体`NO_CUTOVER`的实时真相源。
- [Service cutover Plan](../plan.md)：inventory、数据disposition、fence、cutover、rollback、观察与退役的live执行合同。
- [Bridge Implementation](../../anthropic-responses-bridge/implementation.md)：current main、已落地切片、真实canary与未闭合产品范围。
- [Systemd runtime Plan](../../systemd-runtime/plan.md)：S3／S4主线状态、S5阻塞与S7后续的live计划。
- [Bridge关键证据索引](../../anthropic-responses-bridge/archive-260808/evidence-index.md)：少量point-in-time报告入口，不承担current状态。
