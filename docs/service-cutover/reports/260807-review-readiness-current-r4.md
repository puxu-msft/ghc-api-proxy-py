# Service cutover readiness current 独立复评 R4

- **评审范围**：主树 current `docs/agents/service-cutover/readiness.md`，现场稳定 SHA-256 `1b6fcfb0cb93534683065661d2b459cceec853615140a7f95fedd2dc8c44b6b4`；固定 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮以现场 current bytes 独立复评 route `dd376d6…`、semantic `f5bca39…`、block `e506bf8…`、Acceptance current finalized identity、systemd-next ready、43 行矩阵、`NO_CUTOVER／FOUNDATIONS_ONLY`、旧 Bun `4141` 与 `cc-daemon` 边界；不沿用 R3 的旧 `14c510b1…` 内容身份，不重新评审候选代码或执行任何服务、manager、unit、进程、端口、数据或 cutover 动作。
- **总体 verdict**：**修复 major 后可进入。** Current 文档已经准确同步用户点名的五条易变状态、43 行口径与生产硬边界，但 reasoning 行仍把已由用户裁决撤销的 empty-reasoning 实现 major 写成未闭合，且多个 `Next smoke`／阻塞链把 route successor 自身 R3／verify 排到新 integration 建立之后，与 Implementation 明定的前置门顺序相反。当前 bytes 尚不可取得 0 major checkpoint。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **checkpoint 结论**：**当前不可 checkpoint。** 删除已撤销的 empty-reasoning major 复述，并把执行顺序统一为“semantic 回放 main并通过 main-side gate → route `dd376d6…` 自身 R3／verify 达到 0／0＋`PASS` → 从 semantic 新 main按完整 route范围后接完整 block范围建立新 integration → 新组合 merged-state review／verification”后，对新稳定 bytes 做定向复评；若达到 **0 blocker／0 major**，Readiness **可 checkpoint、可继续 living 实施**。该 checkpoint 不表示文档封存、完整 bridge `PASS`、候选已进入 main、unit 已安装、真实 user manager／cgroup 已验收、生产 `localhost:4141` 可接管或 `cc-daemon` 可被操作。

## 双视角覆盖证据

### 机械核对

- 在首次读取前连续两次计算 current Readiness SHA-256，结果均为 `1b6fcfb0cb93534683065661d2b459cceec853615140a7f95fedd2dc8c44b6b4`，`HASH_STABILITY=PASS`；完成评审后再次连续计算两次，仍为同值。旧 R3 的 `14c510b1…` 只作为历史报告身份出现，未被本轮 verdict 沿用。
- 每次采纳为证据的 shell 调用均在同一次调用内验证物理 root与 cwd 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- 用 Python Markdown 表格解析与独立 `awk` section state machine 两种原理交叉计数，均得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43 行；`REL-06` 的 block-level buffering／delivery frontier／resident budgets／backpressure仍是独立 P0 行。
- 直接读取 refs，确认 route `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`、semantic `f5bca39ac582911b61d278fd678ec9298ad0c08e`、block `e506bf87318424e4075b6422772ee0c7e9b8694a`、systemd-next `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 与文档一致。扫描 `docs/tmp` 未找到绑定 `dd376d6…` 的自身 R3／verify；父提交 verdict 没有被写成 successor `PASS`。
- 逐份核对精确 HEAD 报告：semantic R2 为 `0 blocker／0 major／0 minor`且可 squash，verify R2 为 `PASS`；block R2 为 `0 blocker／0 major／0 minor`且可 squash；systemd-next merged-state review为 0 major、独立 verify为 `PASS`、final replay gate为 0 major。Current Acceptance 现场 SHA-256 为 `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`，正文状态为 `FINALIZED_ACCEPTANCE_ORACLE`，与 Readiness 记录一致。
- 对账 inventory 与全文硬边界：旧 Bun仍是 `127.0.0.1:4141` 与 `[::1]:4141` 的快照 owner；Readiness 没有把 socket存在写成应用 ready，也持续禁止停止、重启、reload、改 endpoint或清理 `cc-daemon` 资源。

### 第一人称执行

- 以 bridge执行者从“当前阻塞链与下一最小序列”进入：现文会先回放 semantic，然后立即从新 main建立 route＋block integration，最后才“重做 current route R3／verify”。这会在 route successor 尚未通过自身硬门时先消费它，且让新 integration 同时承担 source review与 merged-state review，违背 Implementation `:229-230` 的明确顺序。
- 以 reasoning实施者进入 P0 reasoning 行：看到“current-main空reasoning parity major仍未在同一候选闭合”会把已经由用户裁决确认正确、并由 semantic R2／verify R2 再证实的“一 empty item一 bare block”误当作仍需修复的实现 major，存在重新引入已撤销零-block expected或无谓阻塞 semantic回放的现实风险。
- 以 cutover执行者沿 P0→P1→P2→P3 退出门推进：任一 required行未 `PASS` 时仍停在 `NO_CUTOVER／FOUNDATIONS_ONLY`；systemd-next ready只允许满足 preflight 后逐片回放，不表示 unit安装或真实 manager通过；生产 `4141` 与 `cc-daemon` 始终没有被纳入当前动作。因此这部分执行边界成立。
- 修复两项 major并取得 current-byte 0／0 后，执行者可以把 Readiness作为 living checkpoint继续技术实施；仍必须在后续 candidate、review、verification、main回放、inventory或运行态变化后重新同步，不能把 checkpoint转义为生产授权。

## 事实性发现

[major] `docs/agents/service-cutover/readiness.md:59` — P0 reasoning 行仍把“current-main空reasoning parity major”写成尚未在同一候选闭合，复活了已被最终裁决撤销的错误 finding — `docs/tmp/260807-arbitrate-empty-reasoning.md:4,41,57` 已裁定唯一合法行为是 empty item产生一个 bare carrier block，错误在旧 oracle／living expected而不在 candidate；`docs/tmp/260807-review-code-semantic-parity-r2.md:4,31,49` 与 `docs/tmp/260807-verify-semantic-parity-r2.md:5,13-14,54` 又对 `f5bca39…` 确认该合同保持、0 major且 `PASS`。把它继续称作 current-main major，会让执行者尝试删除正确 block或错误阻塞已放行 semantic切片 — **修复建议**：删除“current-main空reasoning parity major仍未在同一候选闭合”，改为只陈述真实剩余缺口，例如完整 route、stream／non-stream一 item一 block、encrypted-only no-loss与真实 client echo尚未在同一完整候选／真实入口闭合；不得把这些组合证据缺口重新命名为已撤销的 empty-reasoning实现 major。

[major] `docs/agents/service-cutover/readiness.md:51-55,122,147,157` — route successor 自身 R3／verify与新 integration的先后顺序反转 — 这些位置都要求 semantic进入 main后先应用完整 route至 `dd376d6…`、后接 block建立 integration，再“重做 route R3／verify”或取得 current review；但 `docs/agents/anthropic-responses-bridge/implementation.md:229-230` 明确规定 `dd376d6…` **只有取得自身 0／0＋`PASS` 后才进入新 integration**，随后才从 semantic新 main按完整 route→完整 block建立组合并取得 merged-state 0／0＋verification `PASS`。按 Readiness 当前顺序执行会消费尚未通过 source gate的 successor，并模糊 route source verdict与组合 verdict的不同 subject — **修复建议**：全文统一四步顺序：semantic先 main-side gate；对 clean `dd376d6…` 完整三提交范围先做自身 R3／verify；仅在其 0／0＋`PASS` 后从 semantic新 main应用完整 route范围再后接完整 block范围；最后对新 integration做组合 review／verification。同步 P0五行、P3“独立评审与最终授权”、阻塞链和结构怪味登记，避免保留弱一致性副本。

## 已核实为准确的状态

- Route current精确为 `dd376d6…`，待自身 R3／verify；父提交 `44808b7…` 的 0 major／`PASS`没有被外推。
- Semantic `f5bca39…` 已获代码 R2 0 major、独立 verify `PASS`且可 squash；block `e506bf8…` 已获 R2 0 major且可 squash。三项 P0候选仍未进入 main，完整产品继续 `UNVERIFIED`。
- Acceptance current为 `FINALIZED_ACCEPTANCE_ORACLE@6457b896…`；oracle定稿没有被写成产品 `PASS`。
- Systemd-next `0a93e7f…` 已达到 merged-state review 0 major、独立 verify `PASS`和 final replay gate 0 major，属于 ready-to-replay checkpoint；尚未回放、安装或执行真实 user manager／cgroup smoke。
- 43 行口径、`NO_CUTOVER／FOUNDATIONS_ONLY`、旧 Bun双栈 `4141` 快照 owner与 `cc-daemon`只读隔离边界均成立。

## 主观建议

无。

## 结论

本轮为 **0 blocker／2 major／0 minor**。Current Readiness 已完成主要易变状态同步，但一个被撤销的 semantic major残留与一个 route gate顺序反转都会误导实际执行，因此当前不能声明 0 major checkpoint。完成上述两项最小修订并对新稳定 bytes复评；若达到 **0 blocker／0 major**，须明确判定 **Readiness 可 checkpoint、可继续 living实施**，同时继续保持产品 `UNVERIFIED`、部署 `NO_CUTOVER`，且不产生任何生产切换或 `cc-daemon`操作授权。
