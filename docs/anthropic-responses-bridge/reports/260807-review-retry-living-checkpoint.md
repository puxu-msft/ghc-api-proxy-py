# Network retry living checkpoint 联合定向复评

- **评审范围**：联合复评 `docs/agents/anthropic-responses-bridge/implementation.md` SHA-256 `397f41f6711cd31bcbcf9c88eb376b406fdc648297fc70907503fa985f67aa57`、`docs/agents/service-cutover/readiness.md` SHA-256 `0a90155c1fe7d232c12bd4254b2d1246b6a7daa741786169f048a5a112361217`，以及主树 `main@080105b54614e1320a5c193d7206dcaa584c9b41`。范围仅核对 network retry＋exhaustion 已 main、resident candidate 仍未 main、backup scoped PASS、quota／真实 partial-write／真实 manager 未验证、`LIVING／UNVERIFIED／NO_CUTOVER` 边界与 readiness 43 行口径。
- **总体 verdict**：**可进入下一阶段，可形成 living checkpoint。** 请求范围内未发现 blocker 或 major；发现 1 项并发推进造成的 minor 状态陈旧，不改变“resident candidate 仍未 main”或 checkpoint 放行结论。
- **Blocker 数**：0。
- **Major 数**：0。
- **Minor 数**：1。

## 双视角覆盖证据

- **机械核对**：现场验证物理仓库根、`main` 分支、`HEAD == refs/heads/main == 080105b54614e1320a5c193d7206dcaa584c9b41`；验证 `fb5c027b38cc72910dd4495979a26a57fbbaa99b` 与 `080105b…` 均为 main 祖先，提交主题分别为 network retry 实现与 exhaustion 回归测试；核对 retry archive 精确指向 reviewed source `584e63ba3724a7b6999d2163266d3daf8e731221`；读取 exhaustion 测试对两次 exchange、两个失败 attempt、零 success facts、History 单次 finalize 与零 `RESPONSE` hook 的断言；核对 backup R3 报告绑定祖先 `d903d726…` 并给出 `PASS_KEY_BACKUP_PORT_SMOKE_R3`；核对 S5 报告为真实 manager／cgroup `BLOCKED`。Readiness 行数以 `awk` 与独立 Python 状态机两种原理交叉计数，均得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43。
- **第一人称执行模拟**：按两份 living 文档的“当前状态→下一步”顺序执行判断：不会把祖先 backup PASS 外推到 retry 后主树，不会把 resident 候选误写为已 main，不会把 scoped retry 绿灯升级为 quota／partial-write／manager PASS，也不会据此执行 cutover。反向分支同样核对：若把 backup PASS 当 current-main 运行证据、把 resident candidate 当已 main、把静态 systemd 证据当真实 manager PASS，文档中的范围限定会阻止这些错误升级。

## 事实性发现

[minor] `docs/agents/anthropic-responses-bridge/implementation.md:17`、`:114`、`:122`、`:262`；`docs/agents/service-cutover/readiness.md:6`、`:9`——两份精确内容仍把 resident 分支描述为“与 main 同点／尚无实现提交”，但现场 ref 已是 `feat/resident-byte-budget@63db675b59a659d8c1f06ee9bc0c7bf945bac161`，相对 `main@080105b…` 为 ahead 1、behind 0，并包含 4 路径的 resident reservation 候选改动。该 tip 的 `RESIDENT_TIP_IN_MAIN=no`，所以本轮要求核对的“resident candidate 仍未 main”仍正确；陈旧的是更细的候选阶段描述。建议下一次 living 更新将其同步为“candidate 已形成但仍未 main”，并以候选自身 review／gate 决定后续动作；本轮不改被评审文档。

除上述 minor 外，未发现问题。以下定向结论均成立：

1. Network retry 实现 `fb5c027…` 与 exhaustion 永久回归门 `080105b…` 已进入 main；原 retry review 的唯一 major 已由 committed regression test 关闭。
2. Resident candidate 当前存在，但仍未进入 main；因此 quota／resident backpressure 不能升级为已 main 或已验证。
3. Backup R3 的 scoped verdict 为 `PASS_KEY_BACKUP_PORT_SMOKE_R3`，且只绑定祖先 `d903d72…`，不得外推到 retry 后 current main。
4. Quota／resident backpressure、真实 socket partial-write／delivery uncertainty与真实 systemd manager／cgroup／unit 运行态仍未验证；manager 当前证据为 `BLOCKED`，不是 `PASS`。
5. Implementation 保持 `LIVING`，完整产品保持 `UNVERIFIED`，部署保持 `NO_CUTOVER`；Readiness 43 行口径精确成立。

## 主观建议

未提出额外主观建议。
