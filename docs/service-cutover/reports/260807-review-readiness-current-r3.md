# Service cutover readiness current 独立复评 R3

- **评审范围**：主树 current `docs/agents/service-cutover/readiness.md`，连续两次读取 SHA-256 均为 `14c510b1e9bbe56c7c9d5ae2b2e924926f99fc81893c9e4d6fa31516adedcddd`，复制到只读临时快照后及最终取证时仍为同值；固定 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮定向复核 R2 semantic major、43 行矩阵、route successor `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`、block `e506bf87318424e4075b6422772ee0c7e9b8694a`、semantic `f5bca39ac582911b61d278fd678ec9298ad0c08e`、bridge-next hooks major、systemd-next `0a93e7f18f197bf8a2395eaaf20afda446f92d6b`、current Acceptance 身份、`NO_CUTOVER／FOUNDATIONS_ONLY`、生产 `4141` 与 `cc-daemon` 边界；不重审候选代码，不执行测试、安装、manager 写操作、service／socket／进程变更、数据动作或 cutover。
- **总体 verdict**：**修复 major 后可进入。** R2 的 semantic major 已关闭，43 行、block、semantic、bridge-next 旧组合 major、systemd-next ready、`NO_CUTOVER／FOUNDATIONS_ONLY`、生产 `4141` 与 `cc-daemon` 边界均成立；但 route successor 已形成精确提交 `dd376d6…`，Readiness 仍只写“正在修复”且继续把旧 `44808b7…` 当 current route identity；同时 current Acceptance 已变为 `READY_FOR_TARGETED_REREVIEW@a4b9e31f…` 并取得绑定该 bytes 的 0／0 定向复评，Readiness 仍绑定旧 `FINALIZED_ACCEPTANCE_ORACLE@224b020d…`。作为 living truth source，current bytes 尚不能取得 0 major checkpoint。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **checkpoint 边界**：**当前不可 checkpoint。** 同步 route successor 的精确身份与执行阶段，并在 Acceptance 完成仅状态／provenance 同步后重新读取其 current 身份与状态、回写 Readiness；若新 bytes 定向复评达到 **0 blocker／0 major**，Readiness **可 checkpoint、可继续 living 实施**。该 checkpoint 不表示文档封存、完整 bridge `PASS`、候选已进入 `main`、unit 已安装、真实 user manager／cgroup 已验收、生产 `localhost:4141` 可接管或 `cc-daemon` 可被操作。

## 双视角覆盖证据

### 机械核对视角

- 每次采纳为证据的 shell 调用均在同一次调用内验证物理 root 与 cwd 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。首轮旧快照在并发更新后立即作废；最终 current Readiness 连续两次 SHA-256、快照 SHA-256 与复制后重读均为 `14c510b1e9bbe56c7c9d5ae2b2e924926f99fc81893c9e4d6fa31516adedcddd`，`HASH_STABILITY=PASS`。
- 用 Python Markdown 表格解析与独立 `awk` 状态机两种原理交叉计数，均得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43 行。`REL-06` 的 block-level buffering／delivery frontier／resident budgets／backpressure 仍为独立 P0 行，没有被汇总状态吞并。
- R2 唯一 major 已关闭：`docs/tmp/260807-review-code-semantic-parity-r2.md` 精确绑定 `f5bca39…`，结论为 `0 blocker／0 major／0 minor`、明确可 squash；`docs/tmp/260807-verify-semantic-parity-r2.md` 对同一 HEAD 判定 `PASS`。Readiness 已在页首、总览、P0 stream／retry 行、授权行、阻塞链和怪味登记同步该状态，且仍明确候选未进入 main、完整 stream 与产品保持 `UNVERIFIED`。
- Route 父提交 `44808b7…` 的 R2 code review 为 `0 blocker／0 major／0 minor`、明确可 squash，独立 verification 为 `PASS`；但 Git ref 已前进到其直接子提交 `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`，subject 为 `fix: finalize pre-attempt hook failures`，修改 executor、component test 与真实 route smoke。当前没有绑定 `dd376d6…` 的独立 code review／verification，因此只能写“修复 successor 已形成，待用它重建 integration并复评／复验”，不能沿用 `44808b7…` verdict或把 commit 存在写成 `PASS`。
- `docs/tmp/260807-review-code-bridge-next.md` 与 `docs/tmp/260807-verify-bridge-next.md` 精确绑定旧组合 `a23081c…`，共同确认 pre-attempt typed reject 漏发 hooks `ERROR／FINALIZE` 的一项 major，code verdict 为 `0 blocker／1 major／0 minor`、verification 为 `FAIL`。该 verdict 仍正确裁定旧组合不可回放，但修复动作已从“形成 successor”推进到“固定 `dd376d6…`、后接 block `e506bf8…` 重建 bridge-next并重新 review／verify”。
- Block `e506bf8…` 的 R2 为 `0 blocker／0 major／0 minor`、可 squash；systemd-next `0a93e7f…` 的 merged-state review 为 `0 blocker／0 major`、独立 verification 为 `PASS`，final replay gate同样为 0 major。Readiness 正确写明 systemd-next 可按 `91f95f7… → 0a93e7f…` 逐片回放但尚未回放，且不外推为 unit 已安装、真实 manager／cgroup、双 fd／双栈或 P1 已通过。
- Current Spec 仍为 `FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。Current Acceptance 已是 SHA-256 `a4b9e31fd1d237ca8038573320809305e0ac567eb2d56d5c967716cc8cdbfac8`、状态 `READY_FOR_TARGETED_REREVIEW`；`docs/tmp/260807-review-acceptance-empty-reasoning.md` 精确绑定该 bytes并给出 `0 blocker／0 major／0 minor`，允许在只同步状态／评审 provenance 后恢复 `FINALIZED_ACCEPTANCE_ORACLE`。Readiness 当前仍声称旧 `224b020d…` 已 finalized，与现场不符。
- 只读运行面复核显示 `127.0.0.1:4141` 与 `[::1]:4141` 仍由同一 Bun `start --restart` 进程监听。Canonical user `ghc-api-proxy.service`／`.socket` 为 `not-found`；`ghc-api-proxy.slice` 仅为无 fragment、inactive／dead 的 synthetic loaded slice，六个 canonical user／system unit 文件路径均不存在，因此没有 canonical 安装／运行证据。`cc-daemon.service` 与 `cc-daemon-calib.service` 均为 loaded／active／running且位于各自 user service cgroup；本轮只读观察，未对它们执行任何修改。

### 第一人称执行视角

- 从 P0 route 路径执行时，现文只给出已评审父提交 `44808b7…` 和“successor 正在修复”。实际 route branch 已是 `dd376d6…`；执行者无法从 Readiness 机械确定该 commit 是当前输入，可能重复实现 hooks 修复、继续在错误 HEAD 上操作，或把父提交 `PASS` 误套到 successor。正确路径应固定 `dd376d6…`，明确它尚待独立复评／复验，再与 block `e506bf8…` 重建 bridge-next。
- 从 Acceptance oracle 路径执行时，现文会让执行者消费旧 `FINALIZED_ACCEPTANCE_ORACLE@224b020d…`；current bytes 实际为 `READY_FOR_TARGETED_REREVIEW@a4b9e31f…`。虽然后者已取得 0／0 定向评审并可在仅状态／provenance 同步后恢复 finalized，但同步动作尚未落入 Acceptance current bytes，Readiness 不能预先把未来状态写成当前事实。
- 从 semantic／block 路径执行时，`f5bca39…` 与 `e506bf8…` 的 exact verdict、可 squash、未进入 main与范围边界均清楚；执行者会推进组合而不是重复实现，也不会把局部绿灯拼成完整 product `PASS`。
- 从 systemd 路径执行时，执行者会先按 final replay gate处理共享 WIP／preflight，再按 `91f95f7… → 0a93e7f…` 逐片回放；之后仍须在隔离真实 user manager与备用端口验证 activation、双 fd／双栈、effective cgroup和 graceful。文档不会把 synthetic loaded slice、静态 unit或 helper `PASS`误作安装态／运行态。
- 从生产接管路径执行时，P0完整候选、P1真实运行面、P2 disposition、P3 supervisor／listener／writer fence、时间门、rollback与观察均未闭合；旧 Bun继续持有双栈`4141`，整体保持`NO_CUTOVER／FOUNDATIONS_ONLY`。实际切换仍要求全部技术门及用户对当次动作的明确授权。
- 从外部不变量路径执行时，`cc-daemon.service`／`cc-daemon-calib.service`只允许前后只读比较；stop、restart、reload、signal、endpoint／环境修改和runtime清理均不在 next smoke或rollback路径中，该边界可安全执行。

## 事实性发现

[major] `docs/agents/service-cutover/readiness.md:6,9,40,51-55,122,147,157` — route current identity与执行阶段落后于 Git ref — Route父提交`44808b7…`的0 major／`PASS`仍有效但只绑定父提交；current branch已经形成直接successor `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`，commit明确修改统一pre-attempt hook终结路径与回归，且尚无绑定该HEAD的独立review／verify。Readiness只写“successor正在修复”，仍把`44808b7…`列为current route候选并把“完成修复”作为下一动作；按现文执行会重复实现、在错误HEAD操作或错误沿用父提交verdict — **修复建议**：统一把current route identity写为`dd376d6…`，明确parent `44808b7…`、hooks fix successor已形成但尚待独立复评／复验；把下一动作改为固定`dd376d6…`、后接block `e506bf8…`重建bridge-next并重新执行merged-state review／verification，禁止沿用旧`a23081c…`或父提交verdict。同步页首、输入身份、总览、P0 route／non-stream／stream／block／retry行、独立评审行、阻塞链与结构怪味登记。

[major] `docs/agents/service-cutover/readiness.md:9,122` — Acceptance oracle identity与状态已漂移，Readiness仍把旧bytes写成current finalized oracle — Readiness绑定`FINALIZED_ACCEPTANCE_ORACLE@224b020d…`；现场current Acceptance为`a4b9e31fd1d237ca8038573320809305e0ac567eb2d56d5c967716cc8cdbfac8`且正文状态为`READY_FOR_TARGETED_REREVIEW`，旧0／0 verdict明确不覆盖该修订。新的`260807-review-acceptance-empty-reasoning.md`已经绑定`a4b9e31f…`并给出0 blocker／0 major／0 minor，只授权在不改其他expected的前提下同步状态／review provenance后恢复`FINALIZED_ACCEPTANCE_ORACLE`；该状态同步当前尚未发生。按现文执行会绕过Acceptance自己的hash漂移fail-closed规则并消费旧oracle身份 — **修复建议**：先在Acceptance仅同步current状态与本次review provenance，再重新读取其最终SHA-256／状态；随后把Readiness的输入身份与独立评审行更新为那个current identity，明确oracle checkpoint不等于产品`PASS`。若Acceptance尚未同步，Readiness必须如实写`READY_FOR_TARGETED_REREVIEW@a4b9e31f…`及“定向review 0／0，待状态／provenance同步”，不得预写finalized。

除上述两项major外，未发现blocker、minor或其他事实性问题。

## 已通过的定向轴

1. **稳定输入**：通过。最终Readiness current bytes连续两次hash、快照及复制后重读均一致；首轮发生并发漂移的旧快照已明确作废。
2. **43行矩阵**：通过。Python与awk两种独立方法均得P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43。
3. **R2 semantic major**：关闭。`f5bca39…`精确code R2为0／0／0、可squash，verify R2为`PASS`。
4. **Block与bridge-next边界**：通过。Block `e506bf8…`为0／0／0且可squash；旧bridge-next `a23081c…`仍为1 major／`FAIL`，不得回放，且其verdict不外推到successor。
5. **Systemd-next**：通过。`0a93e7f…`已取得merged-state 0 major、verify `PASS`与final replay 0 major；尚未回放、未安装、未做真实manager／cgroup smoke。
6. **生产与外部边界**：通过。整体持续为`NO_CUTOVER／FOUNDATIONS_ONLY`；旧Bun仍持有双栈`4141`；`cc-daemon`只读且不进入操作范围。

## 结构怪味扫描

- `readiness.md:6,9,40,51-55,122,147,157`｜**volatile route identity在多个章节重复**｜本轮作为route major一并同步；长期应以单一current candidate表作为身份源，其余章节只引用，避免每次successor都产生全文件漂移。
- `readiness.md:9,122`｜**稳定oracle身份被复制进living汇总，但缺少对上游状态漂移的即时传播**｜本轮作为Acceptance major处理；更新时先消费上游current bytes与review，再写汇总，不能只刷新旧hash或预写未来状态。
- `readiness.md:41,71-77,149,158-159`｜**systemd代码、prepared integration、安装态与真实运行态容易被压成单一“ready”**｜current bytes已明确拆分，且真实现场未提供canonical service／socket安装证据；本轮无需修改。

## 主观建议

无。两项major均是可复现的current-state漂移，不是措辞偏好；其余范围已保留完整产品、运行面、数据、rollback与授权门。

## 结论

**0 blocker／2 major／0 minor；当前不可形成0 major living checkpoint。** 同步route successor `dd376d6…`与current Acceptance最终身份／状态后，对新Readiness bytes重新定向复评；若达到**0 blocker／0 major**，应明确写为：**Readiness可checkpoint、可继续living实施**。该结论仍不表示完整产品`PASS`、unit已安装、真实manager／cgroup已验收、生产`4141`可接管或`cc-daemon`可被操作。
