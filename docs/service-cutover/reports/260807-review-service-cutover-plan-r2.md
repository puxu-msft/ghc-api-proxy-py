# service cutover living plan 独立复评 R2

- **评审范围**：稳定快照 `docs/agents/service-cutover/plan.md` 的 current bytes；仅复核上一轮四项 major：non-TDD 骨架节奏、inventory 资产逐项 disposition 集合门、`--restart` parent／child／listener／open-writer fence、配置化 cutover／rollback 时间与状态门。忽略可能读取旧快照的联合 R2 泛化结论；未执行运行态变更。
- **总体 verdict**：**可进入下一阶段**。四项 major 均已关闭；只允许 living plan 继续下一 implementation 切片，不表示计划收口、候选 `PASS`、服务已部署或生产 cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **稳定快照记录**：连续两次采样各自通过 `main@ed77c9d191df81c451c25161420515cca52ce6a4` shell gate，SHA-256 均为 `ab840f2a37407877bc1c6c9526ff811ab7364e795012ffad0596927f3a3a4765`，大小均为 59,810 bytes；第二次机械断言一致，复核与写入前再次确认 hash 未变化。
- **双视角覆盖证据——机械核对**：逐项对账上一轮 major 与 current plan 的 living 协议、切片表、Inventory、ledger、冻结顺序、替代验收、时间门、cutover／rollback、观察门及 kick-off；current inventory 点名的 History 代际、archive、telemetry、quarantine、三个状态 JSON、`history-search/`、`system-prompts/` 均有对应行。机械扫描得到 19 个唯一 ledger ID，七个时间／状态符号均接入定义及执行或观察路径。
- **双视角覆盖证据——第一人称执行**：模拟骨架→happy path→真实 smoke→squash 未集成探索历史→边界／fault，并模拟新增资产、ledger 遗漏、`PENDING_DECISION`、parent 复拉 child、listener／writer 复活、deadline 未裁决／超限、rollback 超限及观察样本不足。错误状态均被 `UNVERIFIED`／`NO_CUTOVER`、稳定窗重置、冻结回滚、恢复失败标记或延长观察拦截。

## 上一轮 major 关闭情况

### 1. non-TDD 骨架节奏——已关闭

`plan.md:52,79` 明确采用“可运行骨架→happy path→真实入口 smoke→尽快 squash 稳定纵向切片→边界／fault／正反控制”，允许已有骨架或 probe 直接补强，不把先写失败测试设为普遍准入条件；状态提升前仍要求可区分正误的自动测试或真实 probe。`plan.md:111-117,519,525` 将同一节奏落实到 Inventory、下一动作与 kick-off，无旧强制措辞残留。

### 2. inventory 逐项 disposition 集合门——已关闭

`plan.md:282` 要求从 current inventory 生成 ID 并比较 `inventory_asset_ids == ledger_asset_ids`；任何新增、消失、拆分或合并都会使数据门回到 `UNVERIFIED`。`plan.md:286-304` 的 19 个唯一 ID 覆盖点名资产，逐项包含 disposition、producer／consumer、writer fence、备份／恢复 probe 与状态，SQLite 集合含 WAL／SHM。`plan.md:72,309` 要求 `PENDING_DECISION` 全部收敛且 probe 完整，否则保持 `NO_CUTOVER`。

### 3. parent／child／listener／writer fence——已关闭

`plan.md:102,105,116` 要求记录 restart parent／supervisor、child、open fd／锁／transaction／WAL 及精确停止／恢复原语，明确一次空 `ss` 或只停 child 不算 fenced。`plan.md:312-313,374-375` 固定先 fence parent，再停 admission／child，并在稳定窗持续证明 parent、child、双栈 listener、全部 inventory writer 及 WAL／SHM／mtime不复活。`plan.md:330-331,399-400` 将完整 fence 与受控恢复纳入验收和 rollback；只停 listener 或遗漏独立 writer 均不能通过。

### 4. 配置化时间与状态门——已关闭

`plan.md:353` 要求 manifest 绑定 candidate、unit、inventory 与单调时钟，未裁决、未实测或超过客户端预算即保持 `NO_CUTOVER`。`plan.md:357-365` 定义旧释放、稳定窗、新 listener、readiness＋canary、cutover 总门、rollback 恢复、观察状态门及超限动作；`plan.md:375-402,423` 将其接入 cutover、自动回滚、旧服务恢复和观察。分段门、总门、恢复门或样本不足均不能按墙钟假绿。

## 事实性发现

未发现问题。

## 主观建议

无。

## 结论

本轮为 `0 blocker／0 major／0 minor`。该正式 living plan 可继续下一 implementation 切片，但仍保持 `NO_CUTOVER`；本报告不是计划封存、产品符合性、部署完成或生产 cutover 授权。
