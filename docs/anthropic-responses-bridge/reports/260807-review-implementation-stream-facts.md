# Implementation stream facts 定向复评

## 评审摘要

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 working-tree `docs/agents/anthropic-responses-bridge/implementation.md`，精确 SHA-256 `a9c020602fd234e811a95179e91e6f476d3ce0354e811bc624ea6a9ca87ce835`；固定 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28`。只核对 `fix/stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b` 的 clean candidate 身份、Spec 窄裁决、final review 与 main 状态、备用端口 smoke 唯一缺口、systemd S3／S4／S5、`LIVING／UNVERIFIED／NO_CUTOVER` 和 current 下一步。未评审候选代码的完整正确性，未重跑产品测试，未修改 Implementation、代码、Git refs或运行态；唯一写入为本报告。
- **总体 verdict**：**修复 major 后可进入。当前不可 checkpoint。** Implementation 对多数目标状态的记录正确，但把已经完成 final review、达到 `0 blocker／0 major` 且明确“可以 squash”的 `4fa7a87…` 继续写成“待 final review／限定 verification”，并据此把重复终审列为第一下一步。该 current action 漂移必须先修订。
- **blocker 数**：0。
- **major 数**：1。
- **双视角覆盖证据——机械核对**：用 `sha256sum` 与 Python `hashlib.sha256` 两种方法交叉确认 Implementation 内容身份均为 `a9c0206…`；现场确认主树为 `main@e9fb277…`；确认 `4fa7a87…` 是其单提交子候选、候选 worktree／branch／HEAD 精确且 `git status --porcelain --untracked-files=all` 为空，并以 `git merge-base --is-ancestor` 确认候选尚未进入 main。逐项对账 Spec 窄裁决、stream facts R2 终审、current-main 备用端口 R2 smoke 和 S5 执行记录；扫描 Implementation 顶部状态、major 处置表、总体进度、开发线、文档复评、逐片收敛、下一步、结构怪味及末尾实时结论的重复状态。
- **双视角覆盖证据——第一人称执行**：模拟维护者从顶部 current-state 入口进入，先判断候选是否可收敛，再按总体进度、活动开发线、逐片收敛门和“下一步”执行。按 current 文本会再次安排 exact `4fa7a87…` 的 final review，而 `docs/tmp/260807-review-stream-request-facts-r2.md:6-10` 已对该 exact HEAD 给出 `0 blocker／0 major／1 minor`、工作树干净并明确“可以 squash”；正确执行路径应转入 candidate squash／main-side gate，同时保持“尚未 main、非产品 PASS”。另模拟 systemd 执行者路径，确认 S3／S4 不会被重复回放，S5 会转到受控容器或虚拟机而不会退回宿主 user manager或触碰生产 `4141`；模拟产品状态读取，确认局部绿灯不会把完整产品或部署升级为 `PASS`。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md:16,54,91,93,110,118,223,235,238,257,259,275,290` — `4fa7a87…` 的 current final-review 状态与下一动作已陈旧 — `docs/tmp/260807-review-stream-request-facts-r2.md:3-10` 精确绑定 `fix/stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b` 相对 `e9fb277…`，结论为 `0 blocker／0 major／1 minor`、原 major 已按 Spec 裁决关闭、候选可以 squash且终审前后工作树干净；本轮 Git 探针再次确认候选 worktree clean且该提交尚未被 main 包含。Implementation 却在所有 current 状态入口继续声称“待 final review／限定 verification”“未关闭 major”，并把重复 final review 设为第一下一步；执行者会重复已完成 gate，而不会进入应有的 squash／main-side gate。— 将这些 current 复述统一更新为“Spec 裁决保持候选；exact `4fa7a87…` final review 为 `0 blocker／0 major／1 minor`，原 major 已关闭、可以 squash，但候选尚未 main且不构成候选整体或产品 `PASS`”；把下一最小动作改为按 current main 执行 identity／preimage／声明范围 gate 后 squash、main-side 验证与 reviewed-source 归档。R2 的测试判别力 minor 保持非阻断登记，后续 stream 未验证矩阵继续独立推进。

除上述 current-state 漂移外，定向范围内未发现其他事实性问题：

- `4fa7a87…` 的 branch、base、单提交身份与 clean worktree 记录成立；候选确实尚未进入 main。
- Spec 窄裁决被正确保持为“completed、post-commit partial failure与 delivery-uncertain 均保留最终 selected attempt 的 request conversion observations”，没有被外推为完整候选或产品 `PASS`。
- `main@e9fb277…` 的备用端口 R2 smoke 被正确限定为 `PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`；其唯一已识别 facts 缺口正是 stream History request conversion fact，未被洗成完整 History、完整 stream或完整 Acceptance `PASS`。
- Systemd S3 `c53849e…` 与 S4 `e9fb277…` 已 main并归档；S5 真实 manager／effective cgroup 保持 `BLOCKED`，下一入口正确转为具备独立 user manager与 delegated cgroup v2 的可销毁容器或虚拟机，未冒充安装、部署或 cutover 证据。
- Implementation 继续保持 `LIVING`，完整产品保持 `UNVERIFIED`，部署保持 `NO_CUTOVER`；其余 stream 边界、完整 Acceptance与 S5 运行态证据仍明确未闭合。

## 主观建议

无。

## checkpoint 判定

当前内容身份 **不满足 0 major checkpoint 门**。修订上述状态与执行顺序后，应对新的 Implementation SHA-256 做同范围定向复评；若达到 `0 blocker／0 major`，可形成 living checkpoint。该 checkpoint 仍不表示 `4fa7a87…` 已进入 main、完整产品 `PASS`、S5 已完成、Implementation 收口或部署／cutover 获授权。
