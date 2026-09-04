# systemd runtime living Plan 联合终审 R4

- **评审范围**：current `docs/agents/systemd-runtime/plan.md` SHA-256 `ffa2d479540ef814081aaf8e01f6a919d49fd43af0625c3c05ecf5e12979ffdf`、候选 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的三提交线性范围，以及 code R4 `docs/tmp/260807-review-code-systemd-runtime-r4.md` SHA-256 `05b563128137d2c1ff50d686984b228fa4188e4b1c8034e8e577594df41a65ff`。主树取证绑定 `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1`；每次有效 shell 均在同一次调用内验证物理 root、`main` 分支和当次 current HEAD。未修改 Plan、候选代码或其他文件，未安装或操作任何 unit／manager／生产 listener。
- **总体 verdict**：**修复 major 后可进入下一阶段**。Plan 对候选身份、M1／M2 边界、living／非强制 TDD 节奏、systemd 合同和后续强化路线的技术内容成立；但 current living 状态仍把 Plan R4 写成“正在进行／报告尚未落盘”，并继续以 code R3 而非已存在的 code R4 作为当前代码门证据。按 Plan 自身的状态同步纪律，这会让执行者停在一个实际上已经完成的 gate，必须先同步 Plan 并复评。修复该 major 后，若复评达到 `0 blocker／0 major`，应明确写为 **Plan 可继续**，并按既定路线立即 squash／回并 M1，不等待后续强化。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：验证 main current、Plan／code R4 哈希、候选物理 worktree、branch、clean 状态、exact HEAD、base 祖先关系及三提交线性链；逐行对账 Plan 的页首状态、候选事实、living 看板、M1 门、disposition、kick-off 与 code R4 的 `0 blocker／0 major／1 minor／明确可 squash` verdict；核对候选最终 service／socket／slice、CLI、CLI tests、systemd smoke 与部署 README，确认 `Type=exec`、`KillMode=control-group`、`StateDirectoryMode=0700`、`UMask=0077`、fd >= 1、listener／accepted connection 边界及 cgroup 声明与代码事实一致；扫描 timeout、helper、cgroup observability、rolling 是否被保留为回并后切片。
- **双视角覆盖证据——第一人称执行**：第一条路径模拟实现者从 current Plan 看板进入 M1：候选 exact HEAD 与三提交链可定位，code R4 已明确可 squash，但 Plan 页首、看板、M1 段、disposition 与 kick-off 仍要求等待尚未落盘的 Plan R4，因此执行会被过期状态错误阻断。第二条路径模拟状态同步后的回并：先记录 code R4 与 Plan R4 实际 verdict，再 squash 三提交、读取当时 `main` current、重放并运行 M1 gates；该动作不授权安装／部署，也不等待 graceful timeout、install helper、完整 continuity、cgroup observability 或 rolling。第三条路径模拟管理员 restart：只重启 service、保持 socket active 时只主张 listener 与 queued／unaccepted continuity；旧进程已 accept 的 HTTP／SSE／WebSocket 只能 drain 或按 deadline 有界中断，不迁移给新进程。

## 事实性发现

[major] `docs/agents/systemd-runtime/plan.md:3,6,20,38,87,151,158,183-187,290,314-321,383-384,402-404` — current living 状态尚未消费已经落盘的 code R4 与本轮 Plan R4，仍反复写“Plan R4 正在进行／报告尚未落盘”，并把 current 代码门、可 squash 证据和 credentials minor 归于 code R3 — code R4 `docs/tmp/260807-review-code-systemd-runtime-r4.md:3-7,15,50` 已精确绑定同一候选 `49fb1988621bba4356e7a5039a6994c2e6d19604`，结论为 `0 blocker／0 major／1 minor` 且明确三提交可 squash；执行者照当前 Plan 会在 M1 看板与 kick-off 被一个已完成的 gate 挡住，同时无法从 living 真相源看出 code R4 已取代 code R3 成为当前代码终审证据 — 将页首状态、评审输入、候选事实、看板、M1 状态／动作、disposition、结构怪味归属与 kick-off 全部同步为 code R4 和本报告的实际状态；保留 code R4 的 credentials minor 为非阻断后续部署强化；在修订后重新进行 Plan 复评。若复评为 `0 blocker／0 major`，明确写“Plan 可继续”，并将 M1 下一动作改为立即 squash／回并，而不是继续等待 R4。

除上述 living 状态同步 major 外，未发现其他事实性问题。

## 已确认合同

- **候选身份与 code R4**：Plan `:28-39,112,400-402` 的 base、current candidate 和三提交链与 Git 对账一致；候选 worktree 为 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`、clean，base `ed77c9d…` 为祖先。code R4 精确覆盖 `66551e45… → 1a220e04… → 49fb198…`，为 `0 blocker／0 major` 并明确可 squash。
- **living／非强制 TDD**：Plan `:3,94,114-118` 正确把文档定义为随实现更新的 living plan；已决切片直接推进，不把传统 test-first／强制 TDD 设为阻塞门，但每个补强切片仍要求有能区分正确／错误状态的回归测试与正反对照。该节奏不是“免测试”，也不是等待一次性大计划批准。
- **立即回并不等于强化或部署**：Plan `:13-22,87-92,183-189` 正确把 M1 限定为候选骨架、已关闭 findings／权限修复和现有真实 fd smoke。Plan 复评达到 `0 blocker／0 major` 后立即 squash／回并，不等待 S3～S7；回并不授权 unit copy、daemon-reload、enable、start、restart、现服务 cutover，也不代表 long-term systemd runtime 完成。
- **`Type=exec` 与 readiness**：Plan `:34,135-136,145-146,314` 与候选 `contrib/systemd/ghc-api-proxy.service:9` 一致；`Type=exec` 只改善 exec 失败可见性，不证明 FastAPI lifespan 完成，`/health/readiness` 仍是独立 oracle。
- **control group shutdown**：Plan `:34,147,315` 与候选 service `:21-24` 一致，使用 `KillSignal=SIGTERM`、`KillMode=control-group`、`TimeoutStopSec=330s` 和专属 slice；现有 smoke 只证明应用侧 SIGTERM cleanup，不冒充真实 manager 对 main＋child 广播或超时升级已经验证。
- **状态权限**：Plan `:35,148-152,316-317` 与候选 service `:13-17`、真实 writer 权限测试一致，使用 `StateDirectory=ghc-api-proxy`、`StateDirectoryMode=0700`、`UMask=0077` 和显式 History／tokenization 路径；目录 `0700`、SQLite DB／WAL／SHM 与 tokenization 临时／最终文件 `0600` 的边界写清。code R4 的 EnvironmentFile secret finding被保留为后续 non-blocking 强化，不反向阻塞 M1。
- **socket continuity 分层**：Plan `:43-68,159-181,284-285,298-308,408` 正确区分 listener continuity、queued／unaccepted continuity 与 accepted connection graceful drain。保持 `.socket` active、只换代 `.service` 才有 listener 保护；backlog 有界，客户端仍可能超时；旧进程已 accept 的连接不会迁移给新进程；单实例 restart 不等于 rolling。
- **后续 timeout**：S3 `:191-221` 明确 `330s` 尚未与生产 Uvicorn／lifespan cleanup 建立同源时间模型；回并后从真实 owner 与调用链重建 deadline，测试正常 drain、超时、abort／finalize 与信号升级，不拿历史 `60s + 120s` 设计冒充已接线合同。
- **后续 install helper**：S4 `:223-242` 保留 rootless user helper，默认 dry-run；只有显式 install 才写规范 user unit 目录，测试只写临时 `XDG_CONFIG_HOME`；不调用 sudo，不自动 reload／enable／start／restart，并覆盖幂等、冲突、备份／卸载、路径和 symlink 边界。
- **后续 cgroup**：S5 `:244-270` 区分 declared limits、effective files 与 runtime metrics；typed reader 处理 numeric／`max`／非 v2／权限不足／瞬时消失，fake-tree 为常规 CI gate，可选 delegated probe 不制造 OOM，不把 unavailable 伪装成 0。
- **后续 rolling**：S7 `:294-308` 保持独立设计切片，要求先冻结 listener／proxy 拓扑、readiness 切流 owner、状态隔离、drain、回滚、schema compatibility 和 overlap 资源预算；不会把单 socket／单 service 自然推广为双实例能力。

## 主观建议

未新增主观建议。code R4 的 systemd credentials 迁移建议已经被 Plan 记录为后续部署强化，位置和严重级别合适；本轮不重复扩大 M1。

## 结论

current Plan 的技术路线、候选身份和 M1／后续强化边界成立，候选 `49fb1988621bba4356e7a5039a6994c2e6d19604` 的 code R4 已为 `0 blocker／0 major` 且明确可 squash。当前唯一 major 是 living 状态仍停留在“R4 待审／code R3 current”的旧口径。先同步 Plan 并复评；复评若达到 `0 blocker／0 major`，应明确结论为 **Plan 可继续**，立即执行既定 M1 squash／回并流程，不等待 timeout、helper、cgroup observability、完整 continuity 或 rolling，也不得把回并解释为已强化、已安装或已部署。
