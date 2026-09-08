# Deployment living docs 联合复评 R3

- **评审范围**：稳定快照 `docs/agents/systemd-runtime/plan.md` SHA-256 `02c315d5677052b6fb29236598d0081e2ce2f42c2b76cc2443dce6090d8d6b97`、`docs/agents/service-cutover/plan.md` SHA-256 `cdb95ea1d21e1f35060913886e278d10eddacf7dde5e50a0a47419f651c55cad`、`docs/agents/service-cutover/readiness.md` SHA-256 `84b012e8f003616879cb2b675c4aeff5bd96b1ec4efc57147a6e51f73c6da957`。只核对 latest source candidate `49fb1988621bba4356e7a5039a6994c2e6d19604`、code R4、prepared squash `fe9c20315b0137ca5b2253fdbd86a30d504255ef`、living／non-TDD、`NO_CUTOVER`、43 行／`REL-06` 及 `localhost:4141`／`cc-daemon`／data／cutover 边界；未执行安装、部署、服务、socket、manager、数据、认证、网络、进程或 cutover 操作。
- **总体 verdict**：**可进入下一阶段。三份文档可作为 living checkpoint 提交。** Current bytes 未发现 blocker 或 major；上一轮 Systemd Plan 与 Service Plan／Readiness 的状态链 major 均已关闭。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **稳定快照证据**：两次独立哈希采样完全一致；每次有效 shell 均在同一次调用内验证物理 root `/home/xp/src/ghc-api-proxy-py`、`main` 分支与 HEAD `ec5e8f5240c6a587544e022b449aa7b392ba7ca1`。Current bridge Implementation SHA-256 为 `4ace302283e2b4b539c8195e55a2a23020f692d40fe0df868546dd58312036e2`，Plan／Readiness 均消费该 current identity。
- **双视角覆盖证据——机械核对**：完整读取三份 current 文档；对账 code R4、Systemd Plan R4、Service Plan R2、上一轮联合 R2、current Implementation、Spec／Acceptance、inventory 及 Git integration。Source `49fb198…` 相对 `ed77c9d…` 的三提交净补丁与 `fe9c203…` 相对 `ec5e8f5…` 的单提交 squash 具有相同 stable patch-id、binary diff SHA-256 及 8 个变更路径；`fe9c203…` 是 `ec5e8f5…` 的直接子提交且 worktree clean。Readiness 分节口径为 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43。
- **双视角覆盖证据——第一人称执行**：模拟实施者从 Systemd Plan 的 M1 看板进入，会直接消费 code R4 与 prepared `fe9c203…`，先闭合主树文档 WIP／回放前身份门，再执行 main-side gate，不再重复 R4；从 Service Plan／Readiness 进入，会保持 `FOUNDATIONS_ONLY`，继续隔离备用端口、user-manager、双 fd／双栈、真实 manager／cgroup、data disposition 与 rollback 准备；模拟生产路径时，`NO_CUTOVER`、同一候选、P0～P3、supervisor／listener／writer fence、配置化时间门、观察门和用户当次明确授权会持续阻止未经授权的 `4141` 接管或 `cc-daemon` 操作。

## 事实性发现

未发现问题。

## 上一轮 major 关闭情况

1. **Systemd Plan 状态滞后——已关闭。** Current Plan 已消费 code R4 `0 blocker／0 major／1 non-blocking minor` 与 Plan R4 的唯一状态同步 finding，明确 `Plan 可继续`；看板、M1、disposition 与 kick-off 均把下一动作推进到 prepared `fe9c203…` 的主树 WIP 清理、回放与 main-side gate，不再等待 R4。
2. **Service Plan／Readiness 状态链漂移——已关闭。** 两文档已同步 Spec `5e362822…`、Acceptance `224b020d…`、Implementation `4ace3022…`、systemd source `49fb198…`、code R4 与 prepared squash `fe9c203…`；没有把文档定稿、局部 review 或 integration checkpoint 外推为完整产品 `PASS`。
3. **`REL-06` 行级门——保持关闭。** Readiness 的容量行仍为 `UNVERIFIED`，owner 包含 `runtime/memory-quota` 与 `pipeline/admission`；next smoke 保留 per-request aggregate＋global reservation、有限 queue、charge-before-read、各终态 release、拒绝新 admission，以及 global-only 与 single-block／16 MiB 两种单侧缺陷控制。

## 已通过的联合轴

- **Latest candidate／R4／squash**：通过。`49fb198…` 是 reviewed source，code R4 为 0 blocker／0 major；`fe9c203…` 是已准备、尚未进入 `main` 的等价单提交 squash。Current 文档不把 prepared、reviewed、merged、installed、deployed 或 runtime-verified 混为一层。
- **Living／non-TDD**：通过。三份文档保持动态更新；开发节奏为骨架→happy path→真实 smoke→尽快形成 checkpoint→补边界／fault，不把传统 test-first 设为普遍阻塞门，同时要求 gate 前具备可判别测试、正反控制和真实执行证据。
- **`NO_CUTOVER／FOUNDATIONS_ONLY`**：通过。完整 bridge 仍未形成同一候选 P0 证据，P1 真实运行、P2 disposition 与 P3 cutover／rollback／observation 均未闭合，故总状态保持保守。
- **43 行与 `REL-06`**：通过。43 行口径完整，容量合同没有被 P0 汇总行或单 block 特例替代。
- **`localhost:4141`／`cc-daemon`**：通过。双栈生产前门仍由旧 Bun 持有；文档禁止停止、重启、reload、改 endpoint 或向 daemon 及其子进程发信号。任何隔离 runtime smoke 都必须前后核对 daemon 身份，变化即停止。
- **Data／cutover**：通过。Inventory＝ledger 资产集合、`PENDING_DECISION` 硬阻塞、唯一 writer、backup／restore、旧 supervisor／listener／writer 连续稳定窗、配置化 deadline、rollback 与观察门均保持 fail closed；一次空 `ss`、单 PID 或单项 checkpoint 不能替代这些门。
- **证据边界**：通过。Systemd R4／`fe9c203…` 只放行仓库 checkpoint 与回放准备；真实 manager／cgroup、user unit、双 fd／双栈、graceful、安装、部署和生产运行仍是后续独立门。

## Living checkpoint 与授权边界

本轮 `0 blocker／0 major／0 minor` 明确允许把三份 current 文档作为 **living checkpoint 提交**，并继续无副作用 inventory、仓库内实现、备用端口、rootless／隔离 runtime 验证及 `fe9c203…` 回放准备。

该结论**不表示**文档封存、完整 bridge 产品 `PASS`、`fe9c203…` 已进入 `main`、unit 已安装、manager 状态已改变、服务已部署、数据可迁移／删除、`localhost:4141` cutover 获授权或 `cc-daemon` 可被操作。实际部署或 cutover 仍须所有技术门绑定同一候选闭合，并由用户对当次动作明确授权。

## 结构怪味扫描

- `docs/agents/systemd-runtime/plan.md:3-7,88-90,188-190,320-324,405-409` — **阶段状态在页首、看板、里程碑、disposition 与 kick-off 多处复述** — 本轮已同步一致；后续每次状态改变必须原子更新这些 current 复述，避免再次停在旧评审门。
- `docs/agents/service-cutover/plan.md:29-40` 与 `docs/agents/service-cutover/readiness.md:9,40-43,70-77` — **source、prepared squash、main、安装和真实运行五层状态容易被压成“systemd 已完成”** — Current 文本已明确分层并以 `FOUNDATIONS_ONLY` 与后续 smoke 守护，本轮无需修改。

## 主观建议

无。现有文档已把后续强化、credentials minor 及运行态门保留在正确阶段；本轮不扩大 M1 或 cutover 范围。

## 结论

本轮为 **`0 blocker／0 major／0 minor`**。三份文档可作为 living checkpoint 提交；该 checkpoint 只记录 current 计划与 readiness 状态并放行下一实施准备，绝不构成部署或 cutover 授权。
