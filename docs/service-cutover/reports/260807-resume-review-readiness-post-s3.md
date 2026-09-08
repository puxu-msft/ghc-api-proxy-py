# Readiness post-S3 独立定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 working-tree `docs/agents/service-cutover/readiness.md`，精确 SHA-256 `441a73c063a15bd10cbd47249eb45eaa7174a980b61c0c9b41a404b3930a8eb0`；固定 `main@c53849e2b5103c6426a67a8cbab687f2e45c1fa0`。定向核对五张 readiness 表共 43 行、`main` 状态、`main@ae84aa9…` 的备用端口 happy PASS 及未验证边界、S3 已进入 main／S4 待进入 main、真实 manager／effective cgroup 未验证、整体 `NO_CUTOVER／FOUNDATIONS_ONLY`、旧 Bun 双栈 `4141` owner，以及 `cc-daemon` 禁触碰边界。不重新评审候选代码，不执行测试、服务请求、进程信号、unit／manager 生命周期操作、端口接管、数据动作、Git ref／index 变更或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。0 blocker／0 major／0 minor，当前 exact bytes 可以 checkpoint。** 该 checkpoint 只放行本 exact Readiness bytes 继续作为 living readiness 真相源，不表示完整产品、运行面、数据 disposition或 cutover gates 已通过。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：承载结论的 shell 均在同一次调用内验证物理 cwd、Git top-level、`main` 与完整 HEAD。目标 SHA-256 由 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉一致。被测边界声明为 P0、P1、P2、P3 与 `cc-daemon` 五张表的数据行；Python 章节切片解析与独立 `awk` 状态机均得到 `10＋8＋11＋12＋2＝43`。Git 图确认 `c53849e…` 的直接 parent 为已 main 的 stream commit `ae84aa9…`，S3 archive 精确指向 reviewed source `865a5b7…`；S4 tip `d3fabfa…` 的 parent 为 `8cae6c2…`，且 `d3fabfa…` 不是 current main 的祖先。原始 stream 定向复核为 `0 blocker／0 major`，原始备用端口执行记录只对 `main@ae84aa9…` 给出 `PASS_HAPPY_BACKUP_PORT_SMOKE`，并明确保留 semantic reorder、完整 usage／terminal／History、retry、quota／backpressure、真实 socket partial-write／RST、真实 manager／effective cgroup及完整 Acceptance 为未验证。只读 `ss` 与 `/proc` 独立对账确认当前同一 Bun incarnation PID `818465`、starttime `2138402` 仍同时持有 `127.0.0.1:4141` 与 `[::1]:4141`，cwd 为 `/home/xp/src/copilot-api-js`、cgroup 为 `/init.scope`。只读 `systemctl --user show` 重取了 `cc-daemon.service` 与 `cc-daemon-calib.service` 的当前身份；该动态值未被外推为 readiness PASS。
- **双视角覆盖证据——第一人称执行**：作为 Readiness checkpoint 执行者，我会据全文先复验 current `c53849e…` 的备用端口 happy slice，再处理 S4 main-side gate，而不会把 `ae84aa9…` 的历史 happy PASS外推到后继 S3 commit。作为 systemd 执行者，我会把 S3 视为已 main且不再回放，只在 fresh-main identity／preimage／tests gate 后处理 S4；S4 完成后仍须另行执行隔离真实 user manager／effective cgroup、双 fd／双栈 activation／restart smoke。作为 P0 实施者，我会继续补 semantic reorder、完整 usage／terminal／History、retry、request／global quota与resident backpressure、真实 socket partial-write／delivery uncertainty，而不会把 scoped review或 happy smoke当作完整 Acceptance。作为 cutover 操作者，我会被 P0～P3未闭合、`NO_CUTOVER／FOUNDATIONS_ONLY` 与当次明确授权门阻止接管 `4141`。任何后续 smoke、rollback或观察只允许比较 `cc-daemon` 身份；停止、重启、reload、signal、改 endpoint／环境或清理其 runtime均不是合法步骤。

## 事实性发现

未发现问题。

Readiness 当前内容在所有关键执行入口保持一致：

- `readiness.md:6-10,40-43,122,147-151,178` 均把 capability、History、stream 与 S3 写为已 main，把 S4 写为待 main，并保持完整产品与运行态边界未闭合。
- `readiness.md:6,9,40-41,51-60,70-75,148-149,178` 均将 `PASS_HAPPY_BACKUP_PORT_SMOKE` 绑定 `ae84aa9…`，明确不覆盖后继 `c53849e…`、retry、quota／backpressure、真实 partial-write、真实 manager／cgroup或完整 Acceptance。
- `readiness.md:15-18,25-34,43,76-81,107-130,151,162,166-178` 一致保持 `NO_CUTOVER／FOUNDATIONS_ONLY`，禁止把 checkpoint、局部 PASS或仓库 gate升级为生产 `4141` 接管授权，并保持 `cc-daemon` 只读不变量。

## 主观建议

无。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `readiness.md:6-10,40-43,122,147-151,178` | Current identity、证据上限与下一动作在多处复述，living 更新时存在局部漂移风险 | **本轮不改。** 当前 exact bytes 在所有入口一致，且每次新 bytes均要求新 hash复评；多入口摘要分别服务快速判读、逐域执行与最终边界，去重反而可能削弱执行可见性。 |
| `readiness.md:40-41,51-60,70-77,122` | Bridge、backup smoke、systemd仓库 gate与运行态证据分层，局部绿灯容易被拼成完整候选假绿 | **文档已正确处置。** 同一候选原则、逐行状态和 Next smoke均阻止外推；继续保持 `FOUNDATIONS_ONLY／UNVERIFIED`，直到 current candidate取得对应真实入口与 fault证据。 |
| `readiness.md:15,77,124-131,176` | `cc-daemon` 是外部活会话边界，但其动态身份会随时间漂移 | **文档已正确处置。** 当前表项为 `UNVERIFIED` 且明确只读重取；后续每轮运行 smoke前后重新比较身份，不把本轮 PID／InvocationID固化为长期事实。 |

## checkpoint 结论

**0 blocker／0 major；精确绑定 `main@c53849e2b5103c6426a67a8cbab687f2e45c1fa0` 与 Readiness SHA-256 `441a73c063a15bd10cbd47249eb45eaa7174a980b61c0c9b41a404b3930a8eb0`，可以 checkpoint。** 43 行口径为 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2。该 checkpoint不表示 `ae84aa9…` 的 happy PASS已覆盖 `c53849e…`，不表示 S4 已进入 main、unit已安装、真实 manager／effective cgroup已验证、完整 retry／quota／partial-write矩阵已闭合、P0～P3已 PASS、生产 `localhost:4141`可接管或 `cc-daemon`可被操作。整体继续为 **`NO_CUTOVER／FOUNDATIONS_ONLY`**。
