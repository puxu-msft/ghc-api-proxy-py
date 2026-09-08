# Service cutover readiness current 定向独立复评 R6

- **评审范围**：current `docs/agents/service-cutover/readiness.md`，精确绑定 SHA-256 `941e6259b059a71f5b1063286ee99601f7894640efb5ee91f62a48dd8bde44e2`；主树固定为 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮核对 43 行矩阵、bridge successor `c43db35…` 的 review／verification／待回放边界、semantic／route／block current 状态、Acceptance finalized 状态、systemd-next readiness、`NO_CUTOVER／FOUNDATIONS_ONLY`、旧 Bun `4141` owner 与 `cc-daemon` 隔离边界；不重新评审候选代码，不执行 checkpoint、回放、测试、unit 安装、manager 操作、服务切换或数据动作。
- **总体 verdict**：**修复 major 后可进入。** Bridge、Acceptance、矩阵口径与 cutover 安全边界均准确；但 systemd 下一动作仍引导执行者直接回放 old integration `91f95f7… → 0a93e7f…`，与更新且更具体的重建审计所冻结的唯一安全策略冲突，会在 Plan 上产生确定冲突并可能回退 current living 状态。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **checkpoint 结论**：**该 exact bytes 当前不可 checkpoint。** 用户给定的规则是“状态略旧但不导致错误动作”为 living minor；本次 systemd 漂移会直接改变执行命令与冲突处置方式，故必须按 major。修订并取得绑定新 bytes 的 `0 blocker／0 major` 复评后，才可明确该 exact bytes 的后继版本可 checkpoint。该文档 checkpoint 即使成立，也不表示完整 bridge `PASS`、unit 已安装、真实 manager 已验证、生产 cutover 获授权或 `cc-daemon` 可操作。

## 双视角覆盖证据

### 机械核对

- 完整通读指定 Readiness bytes，并把 SHA-256 固定为 `941e6259b059a71f5b1063286ee99601f7894640efb5ee91f62a48dd8bde44e2`；本报告不等待或替换为其他 Readiness hash。
- 逐表清点得到 P0 10 行、P1 8 行、P2 11 行、P3 12 行、`cc-daemon` 2 行，总计 **43 行**。Readiness 的独立评审行也明确保留 `10＋8＋11＋12＋2＝43` 口径，没有缺表、重复表或把退出门文字误算成 readiness 行。
- Bridge successor `integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f` 精确由 semantic `04bdfcb…`、route `088d66d…`、block `c43db35…` 三个线性 integration commits 组成；`docs/tmp/260807-review-code-bridge-successor.md` 为 `0 blocker／0 major／0 minor`，`docs/tmp/260807-verify-bridge-successor.md` 为 scoped `PASS`，且两者均明确完整 Responses stream 仍为 `UNVERIFIED`。Readiness 正确写成“形成本文 checkpoint 后逐片回放”，没有把候选存在或 scoped `PASS` 写成已经进入 main。
- 三个 source current 状态一致：semantic `f5bca39ac582911b61d278fd678ec9298ad0c08e` 的 R2 code review 为 `0／0／0`、verification 为 `PASS`；route `dd376d6f1e9dc2997bc2f95d03a352fed4df1412` 的 R3 code review 为 `0／0／0`、verification 为 `PASS`；block `e506bf87318424e4075b6422772ee0c7e9b8694a` 的 R2 code review 为 `0／0／0`，其 parser→delivery 轴由 successor verification 覆盖。Readiness 对 source 与 merged successor 的身份层级没有混写。
- Current Acceptance 明确标记 `FINALIZED_ACCEPTANCE_ORACLE@6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`，同时把候选产品与完整 bridge 保持为 `UNVERIFIED`；Readiness 对该状态与边界的复述准确。
- Old systemd-next `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 本身确有 merged-state review `0 blocker／0 major／1 minor` 与独立 verification `PASS`，因此 Readiness 把它写成“实现证据 ready”并非错误。错误发生在把 old commit objects 继续写成可直接回放载荷。
- 更新的 `docs/tmp/260807-audit-systemd-next-rebuild.md` 已机械否定 direct replay：第一片与 current Plan 三方合并产生 11 个冲突区，第二片产生 10 个冲突区；其唯一 0-major 策略是 four-docs checkpoint 后，从 actual new main 重建 S3、S4 两个 code squash，排除 old Plan patch，并在每片 gate 后 fresh forward-update Plan。报告明确写明禁止直接 cherry-pick `91f95f7…` 或 `0a93e7f…`。
- Readiness 保持 `NO_CUTOVER／FOUNDATIONS_ONLY`。Current inventory 只读快照仍把双栈 `127.0.0.1:4141`／`[::1]:4141` owner 识别为 `/init.scope` 中的旧 Bun parent／child，并明确没有应用层健康探测；文档没有把 listener 存在外推为 readiness 或切换授权。
- `cc-daemon` 边界完整且一致：不停止、不重启、不 reload，不发送信号，不改 endpoint／环境，不清理 cgroup、runtime directory 或 socket；每次后续 runtime smoke 只能前后只读比对 active state、MainPID、`InvocationID`、cgroup 与 socket。未发现把 `cc-daemon` 作为 canary、rollback 或 4141 切换工具的残留措辞。

### 第一人称执行

- 作为 bridge 回放执行者，我会先形成 Readiness checkpoint，再按 semantic `04bdfcb…` → route `088d66d…` → block `c43db35…` 逐片重验 preimage、回放并执行 main-side gate；任一片失败即停。文档不会让我回放旧 bridge-next `a23081c…`，也不会让我把 parser／delivery typed core 冒充真实 ASGI stream 已完成。
- 作为 systemd 执行者，我从总览、P1 两个 readiness 行、独立评审行和“当前阻塞链与下一最小序列”都会读到“按 `91f95f7… → 0a93e7f…` 逐片回放”。若照做，第一片就在 current Plan 上进入 11 个冲突区；继续采用 old postimage或 `theirs` 会回退 living 状态，人工拼接也没有 current bytes 完全保留的机械 oracle。这不是仅少写了一个较新 commit hash，而是把已被否决的执行路线继续列为下一动作。
- 作为修订后的 systemd 执行者，正确路径应是：先完成 four-docs current-byte 0-major checkpoint；从 checkpoint 后 actual new main 重建 S3 code squash并排除 old Plan patch；S3 gate 后 fresh 更新／checkpoint Plan；再从当时 main 重建 S4 code squash、执行 S4 gate并 fresh 更新 Plan；随后对 rebuilt identities重新取得适用的 merged-state review／verification。Old `0a93e7f…` 继续作为 reviewed组合语义与 provenance 证据，但不再作为 direct replay payload。
- 作为 cutover 操作者，我仍会停在 `NO_CUTOVER`：完整 P0、真实 P1 manager／双栈／cgroup、P2 disposition、P3 rollback／时间门都未闭合，旧 Bun 仍持有 4141；任何文档 checkpoint或代码重建都不允许触碰生产 listener、数据或 `cc-daemon`。

## 事实性发现

[major] `docs/agents/service-cutover/readiness.md:9,41,72,75,122,149` — systemd-next current 下一动作仍把 old integration `91f95f7… → 0a93e7f…` 写成可直接逐片回放，与更新审计冻结的唯一安全重建策略冲突 — `docs/tmp/260807-audit-systemd-next-rebuild.md:4,17,64-69,85` 明确禁止 direct cherry-pick，并以两种三方合并实现证明第一片有 11 个、第二片有 10 个 Plan 冲突区；按现文执行会进入错误路线，采用 old postimage会回退 current living Plan，人工解冲突也缺少机械保真 oracle — **修复建议**：同步所有 systemd 状态与 next-action 副本，保留 old `0a93e7f…` 的 `0 major／PASS` 作为实现与 provenance 证据，但把执行路线统一改为“four-docs checkpoint → 从 actual new main 重建 S3 code squash并排除 old Plan patch → S3 main-side gate → fresh Plan update／checkpoint → 重建 S4 code squash并排除 old Plan patch → S4 main-side gate → fresh Plan update／checkpoint → 对 rebuilt identities重新 review／verify”；不得继续指示 direct replay old commits。

除上述 major 外，未发现其他 blocker、major、minor。特别是 43 行口径、bridge successor current 身份与待回放状态、semantic／route／block source verdict、Acceptance finalized、`NO_CUTOVER／FOUNDATIONS_ONLY`、旧 Bun 4141 owner及 `cc-daemon` 只读不变量均准确。

## 主观建议

无。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| Readiness 中 systemd 状态的页首、总览、P1 行、独立评审行与阻塞链 | 同一易变执行动作多处复述，更新审计改变路线后产生强弱不一致 | 本轮 major 要求一次性同步所有副本；后续可把 canonical systemd next action 收敛为单一引用，但不得因此删除各 readiness 行所需的状态与边界。 |
| Bridge successor 与完整产品状态 | scoped `PASS` 与完整 stream `UNVERIFIED` 并存，存在局部绿灯被外推风险 | Current bytes 已正确区分，保持 `FOUNDATIONS_ONLY`；本轮无需改。 |
| 旧 Bun、4141 与 `cc-daemon` | listener owner、supervisor、数据 writer和外部会话服务属于不同身份域 | Current bytes 已以 `NO_CUTOVER`、精确 owner 重取和 `cc-daemon`只读不变量分隔；本轮无需改。 |

## 结论

本轮为 **0 blocker／1 major／0 minor**。指定 SHA-256 `941e6259b059a71f5b1063286ee99601f7894640efb5ee91f62a48dd8bde44e2` 的 Readiness **当前不可 checkpoint**。唯一 major 是 systemd direct replay 指令已落后于更具体的新重建裁决并会引导错误动作；它不能降为 living minor。修订全部 systemd next-action 副本并取得绑定新 bytes 的 `0 blocker／0 major` 复评后，方可明确允许 checkpoint。完整产品继续为 `UNVERIFIED`，部署状态继续为 `NO_CUTOVER／FOUNDATIONS_ONLY`。
