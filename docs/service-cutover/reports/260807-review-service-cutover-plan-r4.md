# service cutover living Plan 快速复评 R4

- **评审范围**：current `docs/agents/service-cutover/plan.md`，SHA-256 `6644126a9aee556ef7fc8a3993d822220f4390227cc8e276984c6d7b4b8a2c8a`；对照 `docs/tmp/260807-review-service-cutover-plan-r3.md`，并只核对 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 后 Plan 的 main／集成状态陈述是否同步。未重新展开 R3 已覆盖的 non-TDD living 节奏、data disposition、supervisor／listener／writer fence、配置化时间门或 `cc-daemon` 边界，也未执行任何服务、manager、unit、进程、端口或数据动作。
- **总体 verdict**：**可进入下一阶段。** Plan 内容相对 R3 完全未变，R3 的 `0 blocker／0 major` 结论可直接沿用；current living implementation／准备切片可继续。Plan 的 main 状态快照尚未同步到 `80bc8f2…`，构成一项非阻断 minor，应在下一次 Plan 更新时修正；这不表示完整产品 `PASS`、Plan 收口、unit 安装／部署完成或 `localhost:4141` cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **稳定快照记录**：本轮 shell gate 确认物理 root `/home/xp/src/ghc-api-proxy-py`、分支 `main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。`sha256sum` 与 Python `hashlib.sha256` 对 Plan current bytes 的计算均为 `6644126a9aee556ef7fc8a3993d822220f4390227cc8e276984c6d7b4b8a2c8a`，与 R3 绑定快照精确相同。
- **双视角覆盖证据——机械核对**：逐项核对 Plan current SHA-256、R3 的绑定 hash／verdict／计数、current main 完整 HEAD、`cf53334… → 80bc8f2…` 提交序列及 happy 四片 `a0d807f… → cdc080e… → a815948… → d913a03…`、usage `80bc8f2…` 对 current main 的 ancestry；再扫描 Plan 的作者基线、当前事实快照、bridge 产品状态、下一最小动作与 Kick-off 中所有 main／happy／usage 陈述，并与 current readiness 的 `main@80bc8f2…` 状态对账。
- **双视角覆盖证据——第一人称执行模拟**：按 Plan 的“未来 main 前进后必须先更新本文”规则，从文首作者基线进入当前事实快照，再执行“下一最小动作”与 Kick-off。模拟发现实施者会先读到 `main@cf53334…`，随后被告知 happy／usage 尚未进入 main，并可能按旧顺序继续准备或回放已经进入 main 的切片；但所有有副作用动作仍受 `NO_CUTOVER`、完整产品 `UNVERIFIED`、真实 manager／cgroup未验收、数据与 rollback 门约束，因此状态漂移不放大为执行授权或 major。

## 事实性发现

[minor] `docs/agents/service-cutover/plan.md:8,30,39,519,521,526` — main／happy／usage 状态快照未同步到 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` — Plan 仍把作者基线和主仓快照写为 `cf53334…`，并在 bridge 状态、下一动作和 Kick-off 中称 happy `7e4b642…`／usage `aca3ced…` 尚未进入 main；独立 Git ancestry gate确认 happy pure-path 四提交 `a0d807f…`、`cdc080e…`、`a815948…`、`d913a03…` 与 usage `80bc8f2…` 均已进入 current main，current readiness 也已同步该事实。失败场景是后继实施者照 Kick-off 把已落地主树的 happy／usage继续当作未集成依赖，造成重复准备、错误排序或 living 状态对账漂移；现有 `NO_CUTOVER` 与完整候选门仍阻止生产动作，故为 minor而非 major。— 修复建议：下一次更新 Plan 时统一刷新作者基线、主仓快照、bridge 产品状态、下一最小动作与 Kick-off；明确 happy pure-path／usage已进入 main，但完整 route／block delivery／retry组合候选及完整 Acceptance仍未闭合，整体继续 `NO_CUTOVER／FOUNDATIONS_ONLY`。

## 主观建议

无。

## 结构怪味扫描

- **扫描范围**：Plan 的文档状态、当前事实快照、总体切片状态、下一最小动作和 Kick-off，并对照 R3、current main ancestry与current readiness。
- **判据**：同一易变状态在多个位置重复硬编码、旧集成状态驱动后继步骤、局部 main checkpoint 被误升为完整候选、准备动作泄漏为运行态授权。
- **处置**：发现一处“易变 main／集成状态多点复述”怪味，即上述 minor；本轮按用户要求只写评审报告，不修改 Plan。长期可在 Plan 的稳定章节只保留状态真相源链接，在“当前事实快照／下一动作／Kick-off”更新时采用一次性同源生成或机械一致性检查，减少再次漂移。

## 结论

Plan current bytes 与 R3 绑定快照完全一致，R3 的 `0 blocker／0 major` 可直接沿用。Current living implementation 与准备切片明确可继续；唯一需同步的是 Plan 内已过期的 main／happy／usage状态陈述。整体继续严格保持 `NO_CUTOVER`，本报告不授权安装 unit、改变 manager 状态、启动备用实例、迁移数据、停止旧 Bun、触碰 `cc-daemon` 或接管 `localhost:4141`。
