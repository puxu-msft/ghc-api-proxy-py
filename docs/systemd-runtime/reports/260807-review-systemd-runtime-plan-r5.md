# systemd runtime living Plan 定向复评 R5

- **评审范围**：稳定读取 current `docs/agents/systemd-runtime/plan.md` SHA-256 `6646cb727e1bc92ce02ec2bd76f825bb8c9b7d190dbd907ed9f9a6e776f156e6`，只核对 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 已进入 `main`、归档 provenance、M1 checkpoint 已完成、Plan 继续 living，以及后续 graceful timeout／rootless install helper／真实 user-manager 与 cgroup／rolling 顺序；不重审 M1 代码、测试质量、部署状态或后续切片的具体设计。
- **总体 verdict**：**可进入下一阶段，明确可 checkpoint。** current Plan 已关闭 R4 的唯一 major，M1 仓库 checkpoint 已完成且 Plan 继续 living；本 R5 verdict 可作为 Plan 状态复核 checkpoint，不要求也不授权再次 replay、安装、部署或 cutover。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：每次 shell 均在同一次调用内验证物理 root、`main` 分支和当次 current HEAD；稳定读取前后 Plan 哈希一致。Git 证明 current `main@cf53334…`，且 `archive/260807-systemd-runtime` 精确指向 reviewed source `49fb198…`。逐项扫描页首状态、living 看板、M1 段、disposition 和 kick-off，确认 M1 均写为已完成，Plan 均写为继续 living，后续动作不含再次 replay，并按 S3 timeout、S4 helper、S5 user-manager／cgroup、S7 rolling 排列。
- **双视角覆盖证据——第一人称执行**：模拟实现者从 current Plan 继续工作时，会从 current `main` 直接进入 S3 graceful timeout 合同，随后推进 S4 默认 dry-run helper、S5 真实 user-manager／cgroup smoke，最后进入独立的 S7 rolling；不会返回旧 source／integration worktree，不会等待或重复 M1 replay，也不会把仓库 checkpoint 误读为 unit 已安装或运行态已切换。

## 事实性发现

未发现问题。

## 已核对结论

- `cf53334…` 是 current `main` 的 M1 单一语义提交；`archive/260807-systemd-runtime` 保留 reviewed source `49fb198…`，两者职责区分清楚。
- M1 checkpoint 已完成，main-side gate 与 archive provenance 已回写；后续不再重复 M1 replay。
- Plan 明确保持 `LIVING`，M1 完成不表示 Plan 收口，也不表示安装、真实 manager／cgroup 验证、部署或 cutover 已完成。
- 后续顺序明确且完整：S3 graceful timeout owner／deadline／升级合同，S4 默认 dry-run 的 rootless install helper，S5 真实 user-manager／cgroup smoke 与 declared／effective／runtime 对账，最后才是 S7 双实例／rolling 独立切片。

## 主观建议

未新增主观建议。

## 结论

current Plan 已准确反映 `main@cf53334…`、archive provenance、M1 checkpoint 完成和 living 后续路线。R4 的状态同步 major 已关闭；本轮为 `0 blocker／0 major／0 minor`，**Plan R5 明确可 checkpoint，并可从 current main 继续 S3**。
