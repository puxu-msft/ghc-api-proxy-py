# Real Copilot canary 独立快速复核

## 评审摘要

- **评审范围**：只复核 `docs/tmp/260807-real-copilot-canary.md` 在 `main@fb4272b5752bd8439c1ee5a098960f31d4ea70f1` 上的事实可追溯性；定向检查认证根因、response／item identity fixes、HTTP 200 状态、stream event sequence、清理、旧 Bun 边界与未验证范围。未重跑网络，未扩展矩阵，未修改被评文档或运行态。
- **总体 verdict**：**修复 major 后可归纳。** 当前不能归纳为 0 major。
- **blocker 数**：0。
- **major 数**：1。

## 双视角覆盖证据

### 机械核对

- 每次 shell 均在同一调用内验证物理 cwd、Git top-level、分支 `main`、`HEAD == refs/heads/main`，并固定完整 HEAD 为 `fb4272b5752bd8439c1ee5a098960f31d4ea70f1`。
- 完整通读目标文档并逐项对账认证根因、三个修复提交、readiness／non-stream／stream 状态、event sequence、临时根与进程清理、旧 Bun 成功窗口边界及 scope-not-claimed。
- 直接核对 `c188165`、`0e66cab`、`fb4272b` 的提交内容和现有独立 review／verification：四个 token-exchange identity headers及动态 `Authorization` 合同有代码与测试输出支持；response／item ID放宽均为 Copilot-only，generic默认 strict，且 output/content indexes、item type、`call_id`、function name等约束保留。
- 搜索当前会话资源、debug log、持久 shell history、`/tmp`／Git目录的非敏感日志候选及本地 session index。未找到最终成功 canary 的原始 stdout／状态摘要；唯一命中的最终事实载体是目标文档及其后续复述。早期 token identity 独立验收反而明确记录 `REAL_AB=SKIP reason=no_noninteractive_token body_recorded=no`，不能作为目标文档所述真实 403→200 A/B 的输出证据。

### 第一人称执行模拟

- 作为后续读者，仅凭现有可访问输出可以确认：current main身份正确，三个修复已进入main，默认严格与 Copilot-only兼容边界成立。
- 作为 canary 结果采用者，沿“认证 A/B→readiness/catalog→non-stream 200→stream 200→六事件序列→SIGTERM/reap→端口与 Bun 不变”顺序执行时，在首个真实运行断言处就无法跳转到原始命令输出；继续采用会把文档自述当成自身证据。
- 反方向模拟正常的限定结论时，`UNVERIFIED`、`NO_CUTOVER`及未覆盖 quota／backpressure、partial-write、tool／reasoning、systemd manager／cgroup等范围足够保守，没有把单次 canary 外推成完整产品或部署 PASS。

## 事实性发现

[major] `docs/tmp/260807-real-copilot-canary.md:5-12,21-23,29-45` — 报告的核心真实运行事实没有现有可访问命令输出作为独立支持 — 当前可访问证据能证明 `main@fb4272b` 与三个修复的代码／测试合同，但不能证明这次成功窗口中的 readiness 200、32／10 catalog、non-stream 200、stream 200、六事件精确顺序、同一 token 的 403→200 A/B、临时 HOME／XDG 删除、Python exact-handle SIGTERM＋reap、`4142` 零 listener、旧 Bun 零 signal及 PID／starttime／cwd／cgroup／listener 不变。当前会话资源、debug log、shell history、非敏感日志候选与本地 session index均未检出最终 canary原始输出；后续 living docs只是同源复述，不能交叉支持。早期 `docs/tmp/260807-verify-token-exchange-identity.md` 的真实 endpoint项明确为 SKIP，也不能补足认证 A/B。由于这些断言共同构成“critical real-upstream path passed”的主要依据，缺失不是纯引用 nit — 若原始输出仍存在，补入其稳定路径／命令标记并逐项映射这些断言；若已不可恢复，则把上述 live-run事实明确标为“执行者报告、当前未独立复核”，仅保留有代码／测试输出支持的 identity修复合同与保守未验证边界。按用户要求，本轮不以重跑网络修复该缺口。

## 已确认且不构成 finding 的范围

- `c188165` 的 token-exchange identity headers、动态认证头覆盖，以及 `0e66cab`／`fb4272b` 的 Copilot-only response／item identity兼容边界有现有提交、测试和独立评审输出支持。
- `docs/tmp/260807-real-copilot-canary.md:15-17,49-59` 保持完整产品 `UNVERIFIED`、部署 `NO_CUTOVER`，并明确排除生产切换、零停机迁移、真实 systemd manager／cgroup、完整 retry／quota／backpressure、kernel partial-write及完整 reasoning／tool／Acceptance；这些边界与现有证据强度一致。
- `docs/tmp/260807-real-copilot-canary.md:47` 把外部 `--restart` wrapper导致的早期 Bun incarnation变化与成功 canary窗口分开，没有把窗口外变化误写成 canary副作用；但成功窗口内“不变”的正向声明仍受上述 major约束。

## 主观建议

无。
