# service cutover living Plan 独立定向复评 R3

- **评审范围**：稳定快照 `docs/agents/service-cutover/plan.md`，SHA-256 `6644126a9aee556ef7fc8a3993d822220f4390227cc8e276984c6d7b4b8a2c8a`。本轮只复核 Plan R2 `0 blocker／0 major／0 minor` 后的 current 增量：foundations／systemd 已进入 `main`，happy／usage 尚待进入 `main`，生产 `4141` 仍由旧 Bun 持有，`NO_CUTOVER` 下的下一动作改为“只准备备用端口”和“只准备真实 manager dry-run”；同时检查 R2 已关闭的 non-TDD living 节奏、data disposition、supervisor／listener／writer fence、配置化时间门及 `cc-daemon` 禁触碰边界有无回归。未执行任何备用实例、manager、unit、进程、端口或数据动作。
- **总体 verdict**：**可进入下一阶段。** Current Plan 为 `0 blocker／0 major／0 minor`，可形成 checkpoint 并继续 living implementation／准备切片；这不是 Plan 收口、完整产品 `PASS`、unit 安装／部署完成或 `localhost:4141` cutover 授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **稳定快照记录**：两次独立 shell 采样均在同一调用内通过物理 root `/home/xp/src/ghc-api-proxy-py`、分支 `main`、`HEAD == refs/heads/main == cf53334a10a717a3a3d30d6c0e8a297f5000d90c` gate；两次 SHA-256 均为 `6644126a9aee556ef7fc8a3993d822220f4390227cc8e276984c6d7b4b8a2c8a`。写入前再次通过同一 main gate 与 hash gate。
- **双视角覆盖证据——机械核对**：全文对账 current Plan、Plan R2、current Implementation 与 readiness；把 HEAD→current Plan diff 逐项归类为身份／状态同步、`Type=exec` 事实修正、结构怪味更新及下一准备顺序。独立 Git 事实核验确认 foundations 三提交 `d274f584…`、`798ba3e765…`、`1c13fda4…` 均为 current `main` 祖先，happy `7e4b642…` 与 usage `aca3ced…` 均不是 current `main` 祖先；四个 reviewed-source archive ref 精确指向声明 HEAD。Current systemd／CLI 源码仍为单 IPv4 `ListenStream=127.0.0.1:4141`、单 `--fd 3`、`Type=exec` 及 system-level `User=`／`Group=`／`/opt`／`multi-user.target`，与 Plan 的“已进 main 但未安装、未完成真实 manager／双 fd／双栈验收”表述一致。按限定章节解析得到 19 个唯一 disposition ledger ID及 7 个配置化时间／状态门；首次全文件表格扫描曾错误把其他表首列计入 ledger，已判定为查询过宽并改为只解析“数据 disposition ledger”至“冻结写入顺序”，修正查询通过。
- **双视角覆盖证据——第一人称执行模拟**：模拟实施者依次走两条 current 路径。备用端口路径在 happy／usage 尚未进入 `main` 时只能产出 config／manifest／probe／expected，不得声称完整候选或启动实例；manager 路径只能准备 user unit render／check 与默认 dry-run 合同，不得写真实 unit 目录、执行 `daemon-reload`／enable／start／restart或占用 `4141`，后续真实执行必须另获运行态授权。再模拟未来切换前置：任一 ledger `PENDING_DECISION`、inventory 集合漂移、旧 parent 复拉、listener／writer 复活、七个时间门未裁决／超限、happy／usage／完整 Acceptance 未闭合，均继续被 `NO_CUTOVER`、稳定窗失败或冻结回滚门拦截。两条准备路径前后均保留旧 Bun 前门与 `cc-daemon` active state／PID／`InvocationID` 不变量，未出现把 `cc-daemon` 当作 canary、修复或 rollback 工具的分支。

## R2 边界与 current 增量复核

### 1. non-TDD living 节奏——无回归

`plan.md:3-57` 仍将本文定义为持续更新的 living Plan，并明确默认节奏不是普遍 TDD 门，而是可运行骨架→happy path→真实入口 smoke→及时 squash 未集成探索历史→边界／故障／正反控制。状态升为 `PASS`、进入有副作用阶段或声称可切换前，仍要求能区分正确与错误状态的自动测试或真实 probe。Current 下一动作只收窄到无执行准备，没有把后续边界、fault 或 Acceptance 范围删除。

### 2. data disposition 与 writer ownership——无回归

`plan.md:267-314` 保留完整 disposition 词汇、19 个逐项 ledger ID、`inventory_asset_ids == ledger_asset_ids` 精确集合门、SQLite WAL／SHM 复合资产、producer／consumer、备份／恢复 probe与唯一 writer要求。`PENDING_DECISION`、缺 writer 观测点或恢复 probe仍保持 `NO_CUTOVER`；`ABANDON`仍不等于删除。冻结顺序仍先 fence旧 `--restart` supervisor，再停 admission／listener，并持续验证全部 writer 与 WAL／SHM／mtime无增长。

### 3. supervisor／listener／writer fence——无回归

`plan.md:306-314,316-333,367-410` 仍要求 parent／supervisor、双栈 listener和全部 inventory writer三道 fence同时通过；kill单一 PID、只停 listener child或一次 `ss` 空结果均不能放行。旧 owner在稳定窗内复活会重置窗口并阻止 bind，新 owner失败则按冻结顺序恢复旧 supervisor／child／writer，未出现以临时手启 child绕过 supervisor的路径。

### 4. 配置化时间门与观察门——无回归

`plan.md:351-365` 保留 `D_OLD_RELEASE_MAX`、`W_OLD_FENCE_STABLE`、`D_NEW_LISTENER_MAX`、`D_NEW_READY_CANARY_MAX`、`D_CUTOVER_TOTAL_MAX`、`D_ROLLBACK_RECOVERY_MAX` 与 `W_POST_CUTOVER_MIN` 七个门，并要求绑定 candidate、unit、inventory与单调时钟。值未裁决、未实测或超过客户端预算时继续 `NO_CUTOVER`；分段门、总门、rollback恢复门和观察状态门均已接入后续动作及失败路径，未把墙钟到点或低样本“无报错”写成 `PASS`。

### 5. current main／后继切片与两项准备顺序——一致且可执行

`plan.md:27-39,515-526` 正确区分四层事实：foundations与systemd代码已进入 current `main`；systemd unit仍未安装且真实 user manager／cgroup未验收；happy `7e4b642…` 与 usage `aca3ced…`仍未进入 `main`；完整 bridge继续 `UNVERIFIED`。因此下一动作先做 Plan current-byte复评，再保留 archive、只准备备用端口与 manager dry-run，bridge产品线并行按 happy四片→usage→route wiring推进。该顺序不会误导实施者重复回放 foundations／systemd，也不会把准备产物误当可运行完整候选。

### 6. `cc-daemon` 禁触碰——无回归

`plan.md:13-23,515-526` 继续禁止停止、重启、reload、修改或向 `cc-daemon.service`／`cc-daemon-calib.service`及其进程发送信号；manager dry-run不得建立依赖传播，所有后续真实 probe仍须另获授权，并在前后机械比较 active state、PID和 `InvocationID`。Cutover与rollback序列只操作本项目精确 unit及旧 Bun supervisor，不含 `cc-daemon` 生命周期动作。

## 事实性发现

未发现问题。

## 主观建议

无。

## 结构怪味扫描

- **扫描范围**：current Plan 的文档状态、事实快照、living协议、切片矩阵、data ledger、替代验收、cutover／rollback、下一动作、kick-off及 HEAD→current diff；并对 current CLI／systemd 模板与 Git ancestry／archive refs做独立事实核验。
- **判据**：重复或冲突状态源、checkpoint冒充部署态、单 fd／单地址族冒充目标合同、准备动作泄漏为真实执行、writer owner分叉、时间门未接入失败路径、`cc-daemon`被纳入依赖或回滚。
- **处置**：未发现新增结构怪味。Plan 已登记 single-fd、system-level unit、shutdown生产接线、双写与 shadow副作用等现有怪味，并将其留在后续准备／验证门中，没有误写为已解决。

## 结论

本轮为 `0 blocker／0 major／0 minor`。稳定快照 `6644126a…` 可作为 checkpoint 继续 living implementation与无执行准备；整体严格保持 `NO_CUTOVER`。本报告不授权安装 unit、改变真实 manager状态、启动备用实例、停止旧 Bun、迁移数据、触碰 `cc-daemon`或接管 `localhost:4141`。
