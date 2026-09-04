# Service cutover Plan／Readiness current 稳定快照联合终审 R2

- **评审范围**：current `docs/agents/service-cutover/plan.md` SHA-256 `ab840f2a37407877bc1c6c9526ff811ab7364e795012ffad0596927f3a3a4765` 与 current `docs/agents/service-cutover/readiness.md` SHA-256 `9d1a13edddcd3075f695ff8a14aad42daa5ba90bb469100be52de3e0ee1e44c0` 的联合稳定快照。复核上一联合评审的两项 major，联合对账 current bridge Spec／Acceptance／Implementation、同一 Plan bytes 的 Plan R2、current inventory、systemd `49fb198…` R4、43 行 readiness 矩阵、`REL-06` owner／next smoke、`NO_CUTOVER／FOUNDATIONS_ONLY` 与 inventory／cutover 边界；未执行服务、socket、systemd、数据、认证、网络、进程或 cutover 操作。
- **总体 verdict**：**修复 major 后可进入**。上一轮 `REL-06` 行级缺口已经关闭，但 current 状态链仍未闭合：systemd R4 已对 `49fb198…` 给出 `0 blocker／0 major` 并允许 squash 回并，Plan／Readiness 却仍把 R4 或更早候选写成 current；Readiness 绑定的 Implementation SHA-256 也不是现场 current bytes。因此本轮不能给出“两份 living docs 可继续”的 0-major 放行结论。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **稳定快照证据**：最终两轮有效 shell 均在同一次调用内验证物理 root 与当前目录为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、`HEAD == refs/heads/main == ec5e8f5240c6a587544e022b449aa7b392ba7ca1`。Plan／Readiness、Spec／Acceptance／Implementation、inventory 与 systemd R4 的 SHA-256 均由 `sha256sum` 和 Python `hashlib.sha256` 两种实现交叉复核一致；写入前目标路径不存在。
- **双视角覆盖证据——机械核对**：完整读取 Plan 与 Readiness；对账 Plan R2、上一联合评审、current inventory、bridge Spec／Acceptance／Implementation 和 systemd R4；复核 current Spec 为 `FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`、Acceptance 为 `FINALIZED_ACCEPTANCE_ORACLE@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`、Implementation current SHA-256 为 `fe051644c793e3fc57e35b2f1b2d20b285af1eb9bbb08825114300b5f9943fee`。Readiness 行数以 Python 分节解析和独立 `awk` 计数交叉验证，均为 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43；现有 P0 buffering 行明确包含 `REL-06`、request／global quota owners、配置化 `0 < request_budget < global_budget`、有限 queue、charge-before-read、release 归零、global-only 与 single-block／16 MiB 两种单侧缺陷控制。
- **双视角覆盖证据——第一人称执行**：模拟实施者从 Readiness 的 current 输入身份进入 P0→P1→P2→P3，并依次消费 systemd checkpoint、备用端口 user manager、inventory＝ledger、旧 supervisor／listener／writer fence、rollback、观察与生产授权。容量路径会保持 `UNVERIFIED` 并导向正确 owner／smoke；生产路径会被 `NO_CUTOVER`、同一候选原则、P0～P3 门与用户当次明确授权拦截。但 systemd 路径会先执行已经完成的 R4，Plan 路径还会等待已经完成的 Plan／Spec 复评，且输入身份栏会让执行者把旧 Implementation bytes 当作 current，故状态链仍会误导下一动作。

## 事实性发现

[major] `docs/agents/service-cutover/plan.md:10,36,39,322`；`docs/agents/service-cutover/readiness.md:9,72` — 联合 living 状态链仍未消费 current 评审与内容身份，上轮“状态链陈旧” major 只部分关闭 — 同一 Plan bytes 的 Plan R2 已是 `0 blocker／0 major`，但 Plan 仍写 `READY_FOR_REREVIEW`、仍绑定 systemd `66551e45…`、仍声称 current Spec 需要 targeted rereview；现场 Spec／Acceptance 已分别是 finalized `5e362822…`／`224b020d…`。Readiness 已同步 Plan R2、finalized oracle、systemd `49fb198…` 与 `REL-06`，但其输入身份栏仍把 Implementation current SHA-256 写为 `16b10e69…`，现场 current bytes 为 `fe051644…`；其 systemd 行仍写“R4仍待”并把“先完成并消费 R4”列为 next smoke。与此相对，`docs/tmp/260807-review-code-systemd-runtime-r4.md:4-6,50` 已明确绑定 `49fb1988621bba4356e7a5039a6994c2e6d19604`，结论为 `0 blocker／0 major`，精确三提交可 squash 回并，且只保留 1 项非阻断 credentials 文档 minor。照 current 文档执行会重复已经完成的 R4／Plan／Spec 评审并跳过真正下一动作，也会让 readiness 真相源绑定错误的 Implementation 内容身份；这不会绕过 `NO_CUTOVER`，故不是 blocker，但破坏两份 living docs 的核心用途 — 将 Plan 评审状态改为已消费 Plan R2 0／0，重绑 current finalized Spec／Acceptance、systemd `49fb198…` 与 R4 0／0；将 Readiness 的 Implementation 身份更新为现场 current bytes并按 living 规则同步受影响切片，消费 R4 后把 systemd next smoke推进到 squash／准备回并及隔离 user-manager／双 fd／双栈／真实 manager／cgroup gate。修订后重新做 current-byte 联合复评；不得把 R4 0／0外推为真实 manager、安装、部署、完整产品或 cutover `PASS`。

## 上一轮 major 关闭情况

1. **状态链陈旧——未关闭。** Readiness 已消费 Plan R2、finalized Spec／Acceptance、systemd `49fb198…` 与较新的 Implementation 快照，属于有效进展；但 current Implementation bytes再次前进，systemd R4也已完成，而 Plan／Readiness没有继续同步。Living 文档允许更新并不等于允许自称 current 的身份与 next smoke滞后；本项保留为上述 1 major。
2. **`REL-06` 行级缺失——已关闭。** `readiness.md:54` 在原有43行口径内把 P0 行扩展为“Block-level buffering／delivery frontier／resident budgets与backpressure”，状态为`UNVERIFIED`；owner包含`runtime/memory-quota`与`pipeline/admission`，next smoke包含配置化request／global预算、多resident owner、有限queue、charge-before-read、容量恢复、终态release归零、拒绝新admission、global-only与single-block／16 MiB两种相反变异。该行能够区分缺失per-request aggregate与错误single-block特例，不再只靠P0汇总引用隐藏required limits域。

## 已通过的联合轴

- **Plan R2 范围**：通过。Plan SHA-256仍为`ab840f2a…`，同一bytes的Plan R2为`0 blocker／0 major`；其non-TDD骨架节奏、19项data disposition集合门、旧supervisor／listener／writer三重fence及配置化cutover／rollback时间门结论仍成立。该范围内0／0不覆盖随后产生的联合current身份漂移。
- **Spec／Acceptance身份**：通过。现场Spec与Acceptance hashes分别为`5e362822…`与`224b020d…`，状态分别是`FINALIZED`与`FINALIZED_ACCEPTANCE_ORACLE`，Acceptance继续绑定同一Spec并完成route／request／response／buffering／retry／lifecycle／limits七域对账；两文档均明确完整产品仍为`UNVERIFIED`。
- **Implementation边界**：语义边界通过，current身份绑定未通过。Readiness正确说明Implementation是持续更新且不收口的living document，不得当成finalized产品证据；问题只在其“current SHA-256”与现场bytes不一致，并且未消费后续R4事实。
- **Systemd边界**：证据层级通过，状态消费未通过。R4 0 major只放行`49fb198…`三提交squash回并；它明确不授权安装unit、改变manager状态或切换生产`4141`。Readiness继续把真实user manager、双fd／双栈、cgroup与生产运行态保持为后续门，没有把R4冒充部署完成。
- **43行与`REL-06`**：通过。两种独立计数均得到43行，P0容量行具有current status、owner与可判别next smoke；不需要机械增加第44行。
- **`NO_CUTOVER／FOUNDATIONS_ONLY`**：通过。Readiness总状态、P0／P1局部checkpoint语义与P3生产动作均保持保守；局部review、integration PASS、文档定稿或systemd R4没有被拼成完整候选`PASS`。
- **Inventory／cutover边界**：通过。Inventory SHA-256绑定为`1f72038d…`并明确是过期运行态快照；后续必须重取listener、PID、cgroup、writer、资产和`cc-daemon`身份。Inventory只读、数据ledger集合相等、`PENDING_DECISION`硬阻塞、旧supervisor／listener／writer稳定窗、rollback与观察门均未被一次`ss`空结果或单PID操作替代。
- **授权边界**：通过。`readiness.md:122`明确0 blocker／0 major只表示技术门可继续，实际切换必须由用户对当次动作明确授权；Plan与Readiness均不授权停止旧服务、抢占`4141`、安装／启动unit、迁移／删除数据或触碰`cc-daemon`。

## 主观建议

无。本轮唯一发现由current文件hash、明确行文与已经存在的R4报告直接支持，不需要以主观偏好扩大或缩减范围。

## 结论

本轮为`0 blocker／1 major／0 minor`。因此当前**不能**明确宣告两份living docs可继续；先同步current Implementation身份并消费systemd R4，同时把Plan的Plan R2、Spec／Acceptance与systemd状态链更新到current，再对新bytes做联合复评。若复评达到`0 blocker／0 major`，届时应明确：两份living docs可继续动态实施、无副作用inventory、仓库内实现、备用端口与rootless／隔离runtime验证；这只放行下一living implementation切片，**不代表文档封存、完整bridge产品`PASS`、unit已安装、服务已部署、`localhost:4141` cutover获授权或`cc-daemon`可被操作**。
