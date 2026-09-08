# Readiness stream facts 定向复评

## 评审范围与总体 verdict

- **评审范围**：只复核 `docs/agents/service-cutover/readiness.md` 的 exact SHA-256 `f758a33d6ea03c990d452f5b20f172fb3aedc388a037fbd3bd887bc154f3867a`，仓库基线固定为 `/home/xp/src/ghc-api-proxy-py` 的 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28`。本轮核对 43 条 readiness 矩阵、current-main 备用端口关键主路径 R2、stream History request-facts 缺口与候选边界、P0／P1 状态、S3／S4 main 拓扑、S5 user-manager／cgroup 阻断、旧 Bun 双栈 `4141` owner、整体 `NO_CUTOVER` 以及 `cc-daemon` 只读不变量；不重新评审候选代码，不执行测试、checkpoint、合并、安装、manager 操作、服务切换或数据动作。
- **总体 verdict**：**可进入下一阶段；该 exact Readiness bytes 可 checkpoint。** Blocker：0。Major：0。Minor：1。唯一 minor 是 stream request-facts 候选的终审状态已有后继证据，而 Readiness 仍将 final review 与限定 verification 一并写成待办；该保守陈旧不会诱导越权合入或 cutover，不阻断当前 living 文档 checkpoint。
- **blocker 数**：0。
- **major 数**：0。
- **checkpoint 边界**：本结论只允许稳定这份 living Readiness 的当前 bytes。它不表示 `4fa7a87…` 已进入 main，不表示限定 verification 已完成，不把 P0 从 `PARTIAL` 升级为 `PASS`，也不授权安装 unit、操作生产 `4141`、触碰 `cc-daemon` 或执行 cutover。

## 双视角覆盖证据

### 机械核对

- 在每个承载结论的 shell 调用内验证物理 cwd、Git top-level、`main` 分支与完整 HEAD；用 `sha256sum` 和 Python `hashlib.sha256` 交叉确认 Readiness SHA-256 为指定的 `f758a33d…`。
- 以两个独立的标题边界解析方法清点矩阵：Python 与 AWK 均得到 P0 10 条、P1 8 条、P2 11 条、P3 12 条、`cc-daemon` 2 条，总计 43 条。文件物理行数为 180；本文所称“43 行”严格指 readiness 表数据条目，而不是文本物理行。
- 对账 `docs/tmp/260807-final-backup-port-smoke-r2.md:3-8,12-25,44-54,89`：`main@e9fb277…` 的固定 `4142` app＋`4143` fake 关键主路径 verdict 为 `PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`；nonstream、stream withholding、Anthropic SSE、唯一 success terminal、cancel cleanup、SIGTERM cleanup、wait／reap、备用端口释放与旧 Bun 零 signal／incarnation 不变均通过。该 PASS 明确不覆盖 retry、quota／resident backpressure、真实 socket partial-write／RST、完整 Acceptance、systemd 或 cutover。
- 对账同一 smoke 的 facts 缺口：nonstream History 有 typed request conversion fact，stream History 缺失该 fact；因此 Readiness 把 stream 主路径保持为 scoped `PASS_CURRENT_LAYER`、把 P0 域保持为 `PARTIAL`，没有把局部 PASS 外推成完整产品 PASS。
- 用 Git 祖先关系确认 S3 `c53849e2b5103c6426a67a8cbab687f2e45c1fa0` 与 S4／current main `e9fb2771d6e040c761bb4074e3fcf2547caece28` 均已在 current main；确认 facts 候选 `4fa7a87728376f14bd84b4b5853f8212d5bc786b` 不是 current main 祖先，故“候选尚未 main”准确。
- 对账 `docs/tmp/260807-systemd-user-manager-diagnosis.md:3-31,42-50`：当前 VS Code 调用进程位于 root 所有且不可写的 `/init.scope`，独立 `systemd --user` 在 private control socket 创建前以 `rc=1` 退出；真实 manager／activation／cgroup／unit 生命周期未验证。Readiness 正确保持 S5 `BLOCKED`，下一入口为具备独立 login session、user manager 与 delegated cgroup v2 的可销毁 VM 或 container，而不是复用宿主 user manager。
- 对账旧 Bun 与 `cc-daemon` 边界：smoke 只读确认旧 Bun 同一 incarnation 继续持有 `127.0.0.1:4141` 与 `[::1]:4141` 且本轮 signal 数为零；Readiness 始终保持 `NO_CUTOVER`，禁止停止、重启、reload、发信号、改 endpoint／环境或清理 `cc-daemon` 相关 cgroup、runtime 与 socket。
- 对账 stream-facts 后继证据：`docs/tmp/260807-review-stream-request-facts-r2.md:3-10,38-47,65` 已对 exact `4fa7a87…` 给出 `0 blocker／0 major／1 minor，可以 squash`；定向搜索没有找到绑定该候选的 `260807-verify-*.md`，且候选尚未 main。

### 第一人称执行模拟

1. **作为 Readiness checkpoint 执行者**：先冻结 exact SHA `f758a33d…` 与 `main@e9fb277…`，只形成 living 文档 checkpoint；不会把 checkpoint 解读为 stream-facts 合入、P0 完成、unit 安装、部署或切换授权。
2. **作为下一条 P0 工作线执行者**：我会识别 current-main 备用端口关键主路径已经 scoped PASS，同时保留 stream History request-facts 缺口。`4fa7a87…` 的 final review 已完成，但限定 verification 与 main-side 关闭尚无证据；完成这些门后仍继续 semantic reorder、usage／terminal／History、retry、quota／backpressure 与真实 partial-write 矩阵，不会把一个 facts 修复冒充完整 P0。
3. **作为 P1／S5 执行者**：我会接受 S3 graceful 与 S4 installer 代码已 main，但停在 S5 `BLOCKED`；不会再次在当前 `/init.scope` 上变换环境硬试，也不会连接宿主 user manager。下一步移到可销毁 VM／container，在 private control socket 门成立后才执行隔离 `systemctl --user` 与真实 activation／cgroup probe。
4. **作为 cutover 操作者**：我会停在 `NO_CUTOVER`。旧 Bun 仍是双栈 `4141` owner，P0 完整 Acceptance、P1 manager／双 fd／双栈／cgroup、P2 disposition 与 backup／restore、P3 rollback／时间门／观察窗口均未闭合；因此不会释放或抢占 `4141`。
5. **作为外部不变量观察者**：每个后继 smoke 只会在前后只读比较 `cc-daemon.service` 与 `cc-daemon-calib.service` 的 active state、MainPID、`InvocationID`、cgroup 与 socket；任何变化都停止相关阶段并调查，不把 `cc-daemon` 当作 canary、切流或 rollback 工具。

## 事实性发现

[minor] `docs/agents/service-cutover/readiness.md:6,9,42,53,55,72,124,150,159,180` — `4fa7a87…` 的 final review 状态陈旧，仍与限定 verification 一起写成“待 final review／限定 verification” — 后继终审 `docs/tmp/260807-review-stream-request-facts-r2.md:3-10,47,65` 已给出 `0 blocker／0 major／1 minor，可以 squash`，但没有找到绑定该候选的独立 verification 文档，且 Git 祖先检查确认它尚未进入 `main@e9fb277…`。按现文执行最多会重复一次已经完成的保守 review，不会跳过 verification、提前合入或触发 cutover，故不升级为 major — 下次 Readiness fresh update 将状态拆成“final review 已完成；限定 verification 与 main-side 关闭待完成”，并保持候选尚未 main、P0 `PARTIAL` 与完整未验证矩阵不变。

除上述 non-blocking minor 外，未发现事实性问题。特别是未发现 43 条口径漏项或重复、backup-port scoped PASS 被外推、facts 缺口被洗成全 PASS、P0 被错误升级、S3／S4 未 main、S5 被误写为完成、VM／container 路线丢失、旧 Bun `4141` owner 被候选取代、`NO_CUTOVER` 被弱化或 `cc-daemon` 被列为可操作对象。

## 主观建议

无。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `docs/agents/service-cutover/readiness.md:6,9,42,53,55,72,124,150,159,180` | 同一易变候选状态在摘要、矩阵、阻塞链、怪味登记与实时结论重复，后继 review 落地后容易部分陈旧 | 本轮只登记上述 minor，不修改被评审对象；下次 fresh update 统一替换为“review 已完成，verification／main 待完成”，并在更新后重新绑定 SHA 复评。 |
| `docs/agents/service-cutover/readiness.md:42,53-61,72-79` | scoped stream PASS、P0 域状态与 P1 运行态分层较多，执行者可能把一个绿灯拼成完整服务绿灯 | 当前通过 `PASS_CURRENT_LAYER`、P0 `PARTIAL`、P1 `FOUNDATIONS_ONLY` 与 `NO_CUTOVER` 四层边界正确消歧，本轮无需修改。 |

## 方法复盘

1. **更好的内部替代方案**：当前 living matrix 直接链接 smoke、候选和运行诊断，比另建 readiness 数据库或状态生成器更适合现有工作流；后继更新应减少同一瞬时状态的全文复述，但不能牺牲页首、表格与最终结论三个执行入口。
2. **判据判别力**：只 grep 文末“43 行”会假绿；本轮用两个独立、按章节终点截断的解析器实际清点 43 条。只确认旧 Bun 仍监听会漏掉“是否被本轮 signal／换代”；本轮对账 smoke 的 PID、starttime、cwd、cgroup、cmdline shape、双栈 listener inode 与零 signal 边界。反方向也检查了正确状态是否会被误判：缺少完整 Acceptance 不应推翻已经限定范围的 backup-port 主路径 PASS，候选终审完成也不应被误写为候选已 main。
3. **成熟第三方方案**：本轮是 Git 拓扑、Markdown 状态与运行证据对账，Git 原生 ancestor 检查、SHA-256、AWK／Python 表解析已经足够；无需自造 checkpoint 或证据基础设施。

## 最终结论

Readiness SHA-256 `f758a33d6ea03c990d452f5b20f172fb3aedc388a037fbd3bd887bc154f3867a` 在 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28` 上为 **0 blocker／0 major／1 non-blocking minor，明确可 checkpoint**。43 条口径经两种独立方法一致核对为 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2。Current-main backup-port 关键主路径保持 scoped PASS，stream History request-facts 缺口候选 `4fa7a87…` 已完成 0-major 终审但限定 verification 与 main 合入仍待完成；P0 保持 `PARTIAL`。S3 graceful 与 S4 installer 已 main；S5 因当前 `/init.scope` 无可用 delegated cgroup 而保持 `BLOCKED`，下一入口为可销毁 VM／container。旧 Bun 继续持有双栈 `4141`，整体继续 `NO_CUTOVER`，`cc-daemon` 继续只读且禁止触碰。
