# systemd runtime living 实施计划

> 状态：`LIVING`，Plan 继续且不收口。M1 仓库 checkpoint 已以 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 进入 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。S3 graceful source `865a5b71210e2436b36786b5de67146939d1e0f5` 与 S4 installer source `e16c2a700f23f66535e7347ab7357518eb8e56bd` 均已取得独立代码评审 `0 blocker／0 major`、明确可 squash；两片已按顺序重建为 code-only integration `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316` 的两个线性非 merge 提交 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` → `2ec0cb81832691685bfe8d98ad03071d2d5e5316`。两条代码提交均明确排除 `docs/agents/systemd-runtime/plan.md`，不会携带或回退 living Plan bytes。该 exact integration 已取得独立 merged-state code review `0 blocker／0 major` 与独立 verify `PASS`；固定集成树全仓 pytest 执行与 collect-only 两种方法均为 440 项。Current living 文档 checkpoint 形成后，立即按 `862f4cfa…` → `2ec0cb8…` 逐片回放并逐片执行 main-side gate，每片 gate 后都从当时 Plan checkpoint bytes fresh 向前更新本 Plan。上述 checkpoint 不表示两片已进入 main、unit 已安装或运行态已切换。
> 文档同步基线：本次修订在 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 完成；后续每次 shell 仍以当次 `main` current HEAD 为门，不把该点时 hash 当作永久执行基线。
> M1 provenance：reviewed source 为 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`，原始代码 base 为 `ed77c9d191df81c451c25161420515cca52ce6a4`；source 提交链为 `66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff` → `1a220e04a99c6ce07b4bdd6bb0876b4180d4c489` → `49fb1988621bba4356e7a5039a6994c2e6d19604`。归档引用 `archive/260807-systemd-runtime` 精确指向 reviewed source `49fb198…`，而 current main checkpoint 是语义等价的 squash 回放提交 `cf53334…`。
> 评审输入：两份初始 systemd 报告 `docs/tmp/260807-review-code-systemd-runtime.md`、`docs/tmp/260807-systemd-socket-feasibility.md`，code R2／R3／R4 `docs/tmp/260807-review-code-systemd-runtime-r2.md`、`docs/tmp/260807-review-code-systemd-runtime-r3.md`、`docs/tmp/260807-review-code-systemd-runtime-r4.md`，Plan R2～R6，旧 systemd-next merged-state review／verify／replay gate，以及重建审计 `docs/tmp/260807-audit-systemd-next-rebuild.md`、code-only merged-state review `docs/tmp/260807-review-systemd-code-only.md`、独立验收 `docs/tmp/260807-verify-systemd-code-only.md` 均已消费。重建审计否决携带旧 Plan patch 的直接 cherry-pick；code-only review 精确绑定 `2ec0cb8…`，verdict 为 `0 blocker／0 major／2 non-blocking minor`，明确允许按 `862f4cfa…` → `2ec0cb8…` 逐片回放；独立 verify 对同一 exact tip 给出 `PASS`。本次修订关闭 current 路线同步项，但不把本文件自述冒充为新 Plan bytes 的独立复评 verdict。
> M1 checkpoint：prepared integration `fe9c20315b0137ca5b2253fdbd86a30d504255ef` 已作为单一语义提交回放到后续 `main`，形成 `cf53334… feat: add systemd socket activation runtime`。回放后的 main-side gate 为全仓 pytest `375 passed`、Ruff 与 Pyright 通过；`archive/260807-systemd-runtime` 已在 gate 后固定到 reviewed source `49fb198…`。这些是仓库 checkpoint 证据，不是安装、真实 manager／cgroup 或运行态切换证据。
> M2 current code-only integration：`862f4cfa55b124ef9ad21ff2ded2b944ee3307bc feat: configure graceful shutdown timeout` 的 parent 是 current `main@80bc8f2…`，`2ec0cb81832691685bfe8d98ad03071d2d5e5316 feat: add rootless systemd user installer` 的 parent 是 `862f4cfa…`；范围内恰有两个非 merge 提交，且两片均不含本 Plan。Exact tip 的 merged-state review 已为 `0 blocker／0 major`，独立 verify 已为 `PASS`。Current living 文档 checkpoint 后按 `862f4cfa…` → `2ec0cb8…` 逐片回放 main，每片 main-side gate 通过后立即 fresh 更新并 checkpoint 本 Plan，再进入下一片。旧 `integrate/260807-systemd-next@0a93e7f…` 及 `91f95f7…` → `0a93e7f…` 仅保留为历史组合语义、路径适配与重建 provenance，禁止作为 current 回放载荷，也禁止采用其 Plan postimage。回放不等待 installer atomicity、S3 配置测试判别力或其他后续 helper hardening。
> 当前边界：本计划只规划仓库内实现、测试、文档与 rootless probe；不得安装、启用、启动、停止或替换任何 system／user unit，不得触碰当前运行中的 `copilot-api-js`。
> 计划位置：`docs/agents/systemd-runtime/plan.md`。

## 1. 目标与完成定义

本计划把已进入 main 的 systemd socket activation、Uvicorn inherited fd 与 cgroup v2 骨架逐步收敛为可评审、可 rootless 验证、可由用户显式安装的运行方案。开发节奏遵循本项目当前约定：骨架与 happy path → 真实 fd smoke → current candidate 独立代码复评达到 0 blocker／0 major → squash／回放并完成 M1 checkpoint → 在 main 基座上继续 graceful timeout、rootless install helper、真实 user-manager／cgroup smoke 与 rolling 强化。M1 已完成；S3／S4 source review 均已达到 0 blocker／0 major，重建后的 code-only integration `2ec0cb8…` 也已取得 merged-state review `0 blocker／0 major` 与独立 verify `PASS`。Current living 文档 checkpoint 后立即按 `862f4cfa…` → `2ec0cb8…` 逐片回放 main；每片 gate 后都 fresh 更新本 Plan，不重复 M1 回放或重开已闭合评审，也不为非阻断后续强化延迟回放。计划在每个切片后动态更新，不以“计划尚未批准”为由停工，也不把传统 test-first／强制 TDD 设为流程门。

首次回并里程碑 M1 完成不等于已经部署，也不等于 long-term systemd runtime 全部完成。M1 的 squash／回并门只包含：

1. current candidate 保留 inherited fd、`.socket/.service/.slice`、部署说明与快速静态测试骨架。
2. R1 与可行性报告的 findings 已由 code R2 正式关闭：`Type=exec`、`KillMode=control-group`、`StateDirectory=ghc-api-proxy` 加显式 History／tokenization 状态路径，以及 `--fd` 下界 1；readiness 继续由 `/health/readiness` 独立判定，不能由 `Type=exec` 或 process active 冒充。code R2 新发现的权限 major 也已由 `49fb198…` 的 `StateDirectoryMode=0700`、`UMask=0077`、覆盖目录最小权限文档和真实 writer mode 回归修复，由 code R3 首次关闭并由 code R4 在最终 bytes 上复核确认。
3. 无需 root、无需安装 unit 的真实 fd smoke 已证明预连接 backlog 请求可由应用处理，并在 `HOME=/nonexistent` 时成功启动；扩展 smoke 还使用受控 generic upstream 验证 readiness 200、真实 Anthropic 请求、History 与 tokenization 落盘、EnvironmentFile 等价覆盖目录，以及状态目录／数据库／WAL／SHM／临时与最终文件均无 group／other 权限。activation happy path 与 listener continuity probe 的 harness 职责继续分开。
4. 文档严格区分 listen／queued-unaccepted continuity 与旧进程 accepted connection drain，不使用“无缝重启”或“零停机”替代可验证语义。
5. current candidate HEAD 的 code R4 已达到 0 blocker／0 major，并记录定向测试、Ruff、Pyright 与适用于当前骨架的 rootless smoke 通过。原始模板的 `systemd-analyze verify` 唯一诊断仍是安装前约定路径 `/opt/ghc-api-proxy/.venv/bin/python` 不存在，未发现 unit 语法或字段诊断；不得把该预期非零写成原模板 verify 通过。
6. `cf53334…` 已把 reviewed M1 范围作为单一语义提交回放到 current main；main-side 全仓 pytest 375 项、Ruff 与 Pyright 均通过，归档引用已固定到 reviewed source `49fb198…`。M1 checkpoint 已完成，不再有待回放动作，也不等待 graceful timeout、install helper、真实 user-manager／cgroup smoke 或 rolling 才承认该 checkpoint。

M1 后的强化保持完整范围，但不反向改写已完成 checkpoint：graceful timeout 与默认 dry-run 的 rootless user install helper 已完成 source review，并已重建为排除 Plan bytes 的两提交 code-only integration，merged-state review 为 `0 blocker／0 major`、独立 verify 为 `PASS`。Current living 文档 checkpoint 形成后先逐片回放，每片 gate 后 fresh 更新并 checkpoint 本 Plan；随后在备用端口和隔离状态根上执行真实 user-manager／cgroup smoke，并在该切片内对账 declared／effective／runtime 三层事实；最后另开双实例／rolling 切片。Installer 的逐文件 atomic 故障恢复、S3 配置测试判别力与其他 helper hardening 保留为后补，不扩大本次回放门。每片独立提交、验证、评审并更新本 living Plan；后续强化均不阻断已经满足的逐片回放门，也不使 Plan 收口。

## 2. 固定事实、已知可行性与能力边界

### 2.1 基线与候选事实

以下 M1 reviewed source 事实锚定到代码 base `ed77c9d191df81c451c25161420515cca52ce6a4` 与 source `49fb1988621bba4356e7a5039a6994c2e6d19604`；current main 状态锚定本次修订时的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`，执行时必须重新读取 `main` current：

- 候选包含三个提交：`66551e45… feat: add systemd socket activation runtime`、`1a220e04… fix: harden systemd runtime contract` 与 `49fb198… fix: restrict systemd state permissions`。第三个提交消费 code R2 的权限 major 及非阻断 smoke 覆盖项。
- CLI 候选增加 `--fd`，拒绝与显式 `--host`／`--port` 混用，并把 inherited fd 传给 `uvicorn.run(..., fd=fd)`。
- `--fd` 的 Typer 下界已由 0 收紧为 1，并有精确 `--fd 0` 拒绝测试；Uvicorn 0.40.0 不会把 0 解释为 inherited socket 的旧合同缺陷已修。
- socket 候选使用 `ListenStream=127.0.0.1:4141`、`Accept=no`、`Backlog=1024`、`FileDescriptorName=http`，service 以 `--fd 3` 消费 listener。
- service 候选当前明确使用 `Type=exec`、`KillMode=control-group`、`TimeoutStopSec=330s`、`Restart=on-failure`，并挂到 `ghc-api-proxy.slice`。两份报告对旧 `KillMode=mixed` 的严重级别判断不同，但纠偏方向一致；该分级差异不再构成实施分叉。
- 默认状态目录启动 major 与后续最小权限 major 均已修：service 使用 `StateDirectory=ghc-api-proxy`、`StateDirectoryMode=0700` 与 `UMask=0077`，并把 `GHC_HISTORY__DB_PATH` 与 `GHC_TOKENIZATION__STATE_PATH` 显式绑定到 `/var/lib/ghc-api-proxy/` 下。候选 smoke 在 `HOME=/nonexistent` 下通过真实 fd 启动路径验证 readiness 200、真实请求、SIGTERM cleanup、History／tokenization 落盘与覆盖目录写入；真实 writers 的权限回归验证目录为 `0700`，数据库、WAL／SHM、tokenization 临时及最终文件为 `0600`。这说明修复已进入候选并通过 code R4 终审，不代表 system unit 已安装或 systemd 已创建真实 `/var/lib` 目录。
- slice 候选当前声明 `MemoryHigh=1G`、`MemoryMax=2G`、`CPUQuota=200%` 与 `TasksMax=256`。
- 候选现有 smoke 已超出纯静态字段自证：父进程创建真实 TCP listener，预先建立 backlog 连接，把 fd 3 交给真实 CLI／Uvicorn，在无可写 HOME 环境通过受控 generic upstream 验证 readiness、真实 Anthropic 请求、History／tokenization 与覆盖路径写入，并验证真实 writers 的最小权限。它仍未证明真实 systemd manager 传递 fd、service gap 中同一 listener identity、旧 accepted connection drain、超时升级或 effective cgroup limits。
- R1 代码／部署报告为 0 blocker／1 major／2 minor，可行性报告为 0 blocker／1 major／2 minor；code R2 绑定 `1a220e04…`，关闭旧 findings 后发现 0 blocker／1 权限 major／1 minor；`49fb198…` 修复该 major并补齐 non-blocking smoke 覆盖，code R3 首次达到 0 blocker／0 major，code R4 在最终 bytes 上独立确认 `0 blocker／0 major／1 文档 minor` 并明确可 squash。Plan R2／R3 指出早期状态滞后，Plan R4 的唯一 major 是 code R4 结论未回写；Plan R6 的唯一 major 是旧 systemd-next merged-state review／verify 已完成却仍被写成待执行。后续重建审计进一步确认旧提交携带的 Plan patch 已被 current bytes 超越，必须改走 code-only integration。本次修订已消费该重建结论，Plan living 可继续，但新 bytes 仍须形成稳定文档 checkpoint。
- 历史 prepared integration `fe9c203…` 是 `ec5e8f5…` 的直接子提交，tree 内容是候选三提交的单提交 squash。回放前 gate 绑定该 exact HEAD、integration branch、clean worktree 与该树下的 `app` import oracle；全仓 pytest 执行汇总和 collect-only node ID 两种方法均得到当时口径的 301，全仓 Ruff、全仓 Pyright 与 systemd fd smoke 通过。该历史证据只放行当次仓库回放；current main 证据以 `cf53334…` 的 375 项 gate 为准，两者都不表示 unit 已安装或运行态已切换。
- M1 仓库范围已进入 `main`；尚未执行任何 system／user 安装、真实 user-manager 激活或运行态替换。
- S3 reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5` 基于 `80bc8f2…`，独立代码评审为 `0 blocker／0 major／1 minor`、明确可 squash；唯一 minor 是配置优先级测试不能独立证明 YAML／env 中间层均被消费，不是运行时错误，不阻塞回放。
- S4 reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd` 同样基于 `80bc8f2…`，独立代码评审为 `0 blocker／0 major／1 minor`、明确可 squash。Atomicity 裁决确认 helper 只承诺逐文件原子替换，不承诺三文件 all-or-nothing；该 minor 可后补措辞和第二／第三文件替换失败后的重跑收敛回归，不要求 squash 前修。
- Historical integration `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 从 `main@80bc8f2…` 依次包含 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` 与 `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 两个线性非 merge 提交；其固定 clean tree 全仓 pytest 与 collect-only 均为 440 项，merged-state review 为 `0 blocker／0 major`、独立 verify 为 `PASS`、final replay gate 为 `0 blocker／0 major`。这些证据继续证明组合语义与路径适配，但两个提交都携带过时 Plan patch，因此只作历史 provenance，禁止直接回放或采用其 Plan postimage。
- Current code-only integration `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316` 从 `main@80bc8f2…` 依次包含 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` 与 `2ec0cb81832691685bfe8d98ad03071d2d5e5316` 两个线性非 merge 提交；第一片只含 9 个 S3 非 Plan paths，第二片只含 3 个 S4 非 Plan paths，Plan blob 与 base 相同。它与 historical integration 的所有非 Plan bytes 相同，独立 merged-state review 为 `0 blocker／0 major`、独立 verify 为 `PASS`，全仓 pytest 与 collect-only 均为 440 项。Current living 文档 checkpoint 后按该链逐片回放，每片 gate 后 fresh 更新本 Plan。

规划环境已确认存在 `systemd-analyze`、`systemd-run`、`systemctl` 与 `curl`，systemd 为 255，用户 bus 与 `XDG_RUNTIME_DIR` 可用，`/sys/fs/cgroup` 为 cgroup v2。它们只说明 rootless probe 在当前环境可行，不构成其他 Linux 主机必然具备同样条件的兼容性保证；测试必须对缺失工具给出显式 skip／unsupported 结果，不能静默假绿。

### 2.2 listen continuity

listen continuity 的被测对象是“监听 socket 本身在应用进程换代期间是否持续存在并可接收新的连接尝试”。当前目标合同只在以下条件同时成立时适用：

- `.socket` unit 保持 active，监听地址与 socket 配置不变。
- 运维动作只停止／重启 `.service`，不停止或重启 `.socket`。
- systemd 继续持有 listener，应用通过 inherited fd 使用同一个监听对象。
- backlog 和宿主机队列未耗尽，等待时间没有超过客户端 deadline。

满足这些条件时，未被应用 accept 的连接可以留在内核队列中，等待服务再次可用；这消除了“先关闭旧 listener、再 bind 新 listener”的端口空窗，但不承诺无限容量、不承诺所有客户端不超时，也不覆盖修改 `.socket` 配置所需的 socket 重启。

验收必须探测 listener identity 或等价的可观察连续性，并在旧应用退出到新应用就绪的窗口主动发起连接。只断言 unit 文件含 `Accept=no`、端口仍可 bind 或进程最终恢复，不足以证明 listen continuity。

### 2.3 accepted connection continuity

accepted connection continuity 的被测对象是“已经由旧应用进程 accept 的 HTTP、SSE 或 WebSocket 连接能否在进程换代后继续由新进程服务”。systemd socket activation 不转移这类连接；它们仍属于旧进程。

当前单实例合同是 drain，而不是连接迁移：

- SIGTERM 后，旧进程在自身 graceful deadline 内尽力完成已接受请求和连接。
- 旧连接自然完成后才退出是成功 drain；达到 Uvicorn 或 systemd deadline 后被关闭是有界失败，不得写成 continuity。
- crash、OOM kill、手工强制终止或 stop deadline 到期都会中断旧进程持有的 accepted connections。
- 新连接可在 listener backlog 中等待新进程，但新进程不会继承旧进程已经 accept 的连接状态。
- 单个 `.service` 的 restart 是 stop-then-start，不提供新旧应用进程重叠服务。

因此，仓库文档只允许使用“listener continuity”“queued／unaccepted connection continuity”“accepted connection graceful drain”等精确术语。只有未来双实例／rolling 切片通过 readiness 切流和 drain 验收后，才可讨论应用实例重叠；即使届时也不宣称把既有连接从旧进程迁移到新进程。

### 2.4 cgroup v2 limits 与 metrics

unit 声明、内核运行态与 Prometheus 观测必须分三层：

1. **Declared limits**：`.slice` 中的 `MemoryHigh`、`MemoryMax`、`CPUQuota` 与 `TasksMax`。静态测试证明模板意图，但不证明内核已采用。
2. **Effective limits**：运行进程所属 cgroup 中的 `memory.high`、`memory.max`、`cpu.max` 与 `pids.max`。rootless smoke 在 delegated user cgroup 可用时对账；不可用时必须报告环境限制，不能把 unit 文本值冒充 effective 值。
3. **Runtime metrics**：至少评估并覆盖 `memory.current`、`memory.events` 中的 `high`／`max`／`oom`／`oom_kill`、`cpu.stat` 中的 `usage_usec`／`nr_throttled`／`throttled_usec`、`pids.current` 与 `pids.events` 中的 `max`。exact Prometheus metric names、labels 与 unavailable 语义在 observability 评审中冻结，避免计划擅自新增不稳定的公共 metric API。

读取实现必须以当前进程真实 cgroup 为边界，区分 cgroup v2、非 v2、文件缺失、`max`、权限不足与瞬时消失。单元测试使用注入式 cgroup root／fake file tree，不依赖测试机实际内存压力，不尝试制造宿主机 OOM。

## 3. Living 状态看板

| 里程碑／切片 | 状态 | 当前证据／review disposition | 下一动作 |
|---|---|---|---|
| S0 候选骨架 | **已实现、已完成 R1／可行性评审** | `66551e45…`；两报告均为 0 blocker／1 major／2 minor | 作为历史骨架保留，不再重复评审旧 HEAD |
| S1 findings 与权限修复 | **已实现并由 code R4 终审关闭** | `1a220e04…` 的 R1 findings 由 code R2 关闭；`49fb198…` 的 `0700／0077`、覆盖目录文档与真实 writer mode 回归关闭 code R2 权限 major；code R4 为 0 blocker／0 major | 不重开已关闭代码 findings；credentials minor 留作回并后部署强化 |
| S2 M1 真实 fd smoke | **已扩展并由 code R4 复核通过** | 真实 inherited fd、预连接 backlog、readiness 200、真实 Anthropic 请求、SIGTERM cleanup、无 HOME 启动、History＋tokenization、覆盖目录及权限 smoke 已覆盖；`fe9c203…` 上 fd smoke 再次通过 | 更完整的 activation／service-gap／accepted-drain probe 留在回并后，不扩大 M1 |
| M1 首次 squash／回放 checkpoint | **已在 main 完成，Plan 继续 living** | `cf53334…` 已是 current `main@80bc8f2…` 的祖先；M1 main-side 全仓 pytest 375 项、Ruff、Pyright 通过；`archive/260807-systemd-runtime` → `49fb198…` | 不重复回放，不外推为部署或 cutover |
| S3 graceful timeout 合同 | **source review 与 code-only 组合门均通过，待第一片回放** | `865a5b7…` review 为 0 blocker／0 major／1 non-blocking minor；code-only 集成提交 `862f4cfa…` 对齐 Uvicorn `300s` 与 systemd `330s`，不含 Plan patch；exact tip review 0 major、verify `PASS` | Living 文档 checkpoint 后立即作为第一片回放 main；该片 main-side gate 通过后 fresh 更新并 checkpoint 本 Plan，配置测试判别力后补不阻断 |
| S4 rootless install dry-run helper | **source review 与 code-only 组合门均通过，待第二片回放** | `e16c2a7…` review 为 0 blocker／0 major／1 non-blocking atomic minor；code-only 集成提交 `2ec0cb8…` 不含 Plan patch，exact tip 全仓 pytest 与 collect-only 均为 440 项；review 0 major、verify `PASS` | 第一片 gate 与 fresh Plan checkpoint 完成后作为第二片回放；第二片 gate 后再次 fresh 更新 Plan，atomicity 与其他 helper hardening 后补不阻断 |
| S5 真实 user-manager／cgroup smoke | **S4 后切片** | direct inherited-fd smoke 已有；真实 user manager 传 fd、service lifecycle 与 effective cgroup 尚未证明 | 在备用端口、隔离状态根与可回收 user-manager fixture 中验证 activation、graceful、真实 cgroup 归属及 declared／effective／runtime 三层事实 |
| S6 M2 code-only 组合复核 | **current code-only review 0 major、verify `PASS`，待 living 文档 checkpoint 后逐片回放** | `2ec0cb8…` 恰含 `862f4cfa…` → `2ec0cb8…` 两个线性非 merge 提交并排除 Plan bytes；source reviews 均为 0 major；code-only merged-state review 0 major、verify `PASS` | 文档 checkpoint 后按 current code-only 链逐片回放；每片 gate 后 fresh 更新并 checkpoint Plan。旧 `91f95f7…`／`0a93e7f…` 仅作历史 provenance，不可回放 |
| S7 双实例／rolling | **后续独立切片，未设计、不可冒充已支持** | 单实例 socket activation 只提供 listener continuity | 冻结拓扑、readiness 切流、状态隔离、drain、回滚和并发规则，再实施 overlap smoke |

每个切片完成后立即更新本表、对应阶段的“实际结果”和“证据”字段，并写明候选 HEAD、测试命令与评审 verdict。不得等待所有切片结束后一次性补记。

## 4. 统一执行纪律

### 4.1 shell 与树身份 gate

主树不是固定旧 HEAD。后续规划、取证与强化实施的每次 shell 都必须在同一次调用内验证物理主树、`main` 分支并读取当次 current HEAD：

```bash
ROOT=/home/xp/src/ghc-api-proxy-py
cd "$ROOT"
test "$(git rev-parse --show-toplevel)" = "$ROOT"
test "$PWD" = "$ROOT"
test "$(git symbolic-ref --short HEAD)" = main
MAIN_CURRENT=$(git rev-parse HEAD)
printf 'SHELL_GATE_MAIN_CURRENT root=%s branch=main head=%s\n' "$ROOT" "$MAIN_CURRENT"
```

后续强化以 current main 为实施基座。需要追溯 M1 时，在同一次 shell 验证 `archive/260807-systemd-runtime` 精确指向 `49fb1988621bba4356e7a5039a6994c2e6d19604`，并证明代码 base `ed77c9d…` 是该 reviewed source 的祖先；归档只作 provenance，不作为后续切片的开发 HEAD。不得把 `git -C` 指向主树的单条命令误当作当前 shell 位于目标树的证明。切片开始与结束都记录 `git status --short`，只提交本切片精确 pathspec。

### 4.2 渐进开发与测试节奏

本线按用户已定的“骨架＋happy path → 冒烟测试 → 尽快形成可回并切片 → 后补错误处理与完整测试”推进，不把传统 test-first 当作阻塞条件。每个补强切片仍必须包含能区分正确／错误状态的回归测试；阻断 gate 同时做正样本与目标缺陷注入，确认失败来自目标机制。

计划与实现并行：已经没有未决架构分叉的阶段直接执行；评审提出修改时，先记录 finding 与证据，再修订实现和本计划并复评，不额外等待批准。涉及公共 metrics 合同、双实例拓扑或既有运行时 shutdown 合同的新选择时，先形成明确评审／裁决，不把选择藏进实现细节。

### 4.3 禁止安装与外部变更

计划实施期间禁止运行任何会写入 `/etc/systemd/system`、`~/.config/systemd/user` 或 user／system manager 持久状态的安装动作；禁止 `systemctl enable`、`systemctl start`、`systemctl restart`、`systemctl daemon-reload` 及其 `--user` 变体；禁止创建系统账户、修改当前服务、占用生产端口或替换 `copilot-api-js`。

允许的验证边界是：解析仓库 unit、`systemd-analyze verify`、临时目录 fixture、直接运行测试进程、`systemd-socket-activate` 或测试 harness 自持 listener、以及能够在进程退出时自动销毁的 transient／delegated user scope。若某 probe 会改变 manager 状态或需要安装 unit，改用临时 harness；不能改用 sudo 绕过。

## 5. 分阶段实施

### S0：候选骨架与两份 R1 级报告

**状态**：`66551e45…` 已实现；代码／部署评审与 socket 可行性报告均已完成并由本计划消费。

**已确认事实**：

- fd 3、`Accept=no`、listen backlog、CLI→Uvicorn inherited fd 主路径可行。
- 旧候选存在默认状态目录 major、`--fd 0` 与 `Type=simple` minor；可行性报告另把 `KillMode=mixed` 判为 major，而代码评审将其判为建议。两报告对纠偏方向没有分歧：采用 `Type=exec` 与 `KillMode=control-group`。
- `Type=exec` 只证明进程成功跨过 `execve()`，不证明 FastAPI lifespan 已完成；唯一应用 readiness oracle 仍是 `/health/readiness`。
- 两报告都否定 accepted connection migration、无限 backlog 与单实例 rolling。

**处置**：S0 作为历史骨架保留，不重写提交；所有 finding disposition 见 S1。候选未安装、未部署、未切换运行态。

### S1：R1 findings 修复

**状态**：R1／可行性 findings 已由 `1a220e04a99c6ce07b4bdd6bb0876b4180d4c489` 实现并由 code R2 关闭；code R2 新发现的权限 major 及其 non-blocking smoke minor 已由 `49fb1988621bba4356e7a5039a6994c2e6d19604` 修复，code R3 首次以 0 blocker／0 major 关闭，code R4 在最终 bytes 上再次确认无 blocker／major并明确可 squash。

**已完成**：

1. `Type=simple` → `Type=exec`，同步 unit、静态测试与部署文档；部署文档明确 exec ≠ readiness，继续禁止无 `sd_notify` 接线的 `Type=notify`。
2. `KillMode=mixed` → `KillMode=control-group`，让 service cgroup 中主进程与未来协作子进程在 graceful 阶段共同收到 SIGTERM。两份报告只在旧缺陷分级上不同，方向一致，已直接实施。
3. 增加 `StateDirectory=ghc-api-proxy`，并显式设置 `GHC_HISTORY__DB_PATH=/var/lib/ghc-api-proxy/history.db` 与 `GHC_TOKENIZATION__STATE_PATH=/var/lib/ghc-api-proxy/tokenization.json`。R1 在 `HOME=/nonexistent` 复现的默认 History `PermissionError` 已按候选实现修复。
4. 把 `--fd` 下界由 0 收紧为 1，增加精确 `--fd 0` 拒绝测试；保留 fd 与显式 host／port 互斥。
5. 保留 `Requires=`／`After=`／`.socket Service=` 与仅支持 restart、无伪 reload 的当前合同；日常 service restart 不得停止 socket。
6. 增加 `StateDirectoryMode=0700` 与 `UMask=0077`，收紧 EnvironmentFile 覆盖目录及既有资产的最小权限文档；真实 `HistoryWriter`／`TokenizationStateStore` 回归证明目录为 `0700`，数据库、WAL／SHM、tokenization 临时与最终文件为 `0600`。
7. 扩展真实 smoke：在受控 generic upstream 下取得 readiness 200，执行真实 Anthropic 请求并产生 tokenization revision，SIGTERM 后确认 History 与 tokenization 只写入 EnvironmentFile 等价覆盖目录。

**code R4 结果**：在 code R3 已关闭 code R2 权限 major和 non-blocking smoke minor的基础上，逐项复核最终 bytes 并确认旧 findings 无回归；最终 verdict 为 0 blocker／0 major、明确三提交可 squash。唯一 minor 是 EnvironmentFile 传 secret 的文档边界：现有兼容路径不阻塞 M1，后续部署强化应优先 systemd credentials，并在应用尚不能直接消费 credentials 时明确兼容风险。

**回滚**：`1a220e04…` 是独立 hardening 提交，`49fb198…` 是独立权限与 smoke 修复提交；若重放发生冲突，应修复并重新执行 gates，不得恢复已证实会失败的默认 HOME 状态目录合同，也不得恢复 world-readable 状态合同。

### S2：M1 真实 inherited-fd smoke

**状态**：已在 `1a220e04…` 建立并由 `49fb198…` 扩展；code R4 已复核通过，`fe9c203…` integration 上再次执行通过，不再把全部后续 continuity 强化塞进首次回并门。

**M1 已有证据**：

1. 父进程在动态本地端口创建真实 TCP listener，并在应用启动前建立 backlog 连接。
2. harness 将 listener 复制为 fd 3，执行真实 `python -m app start --fd 3`；预连接请求从 `/health/liveness` 获得 HTTP 200。
3. 环境固定 `HOME=/nonexistent`；受控 generic upstream 先完成模型刷新，再从继承 fd 取得 readiness 200，并通过生产 `/v1/messages` 路径执行真实 Anthropic 请求。
4. EnvironmentFile 等价环境覆盖默认状态路径，response observer 产生 tokenization revision；应用完成 SIGTERM／lifespan cleanup 后，History 与 tokenization 文件只落在覆盖目录。
5. unit 声明的 `0700／0077` 作用于真实 writers 后，目录、数据库、WAL／SHM、tokenization 临时与最终文件均无 group／other 权限。
6. smoke 不安装 unit、不连接真实 manager、不使用生产端口、不依赖真实 token或外部 upstream；静态 unit 测试继续作为字段 tripwire，但不冒充运行态证明。

**M1 门结果**：current candidate code R4 已达到 0 blocker／0 major，reviewed 范围已经 squash 并以 `cf53334…` 进入 main；main-side pytest 375 项、Ruff 与 Pyright 通过，归档引用已固定到 `49fb198…`。M1 checkpoint 完成但 Plan 继续 living。M1 没有证明以下强化：真实 manager activation、service-gap listener identity、旧 accepted connection drain／timeout、main＋child manager-level stop、install helper、effective cgroup limits、runtime metrics 或 rolling。

**回并后 continuity 强化**：

- 用 `systemd-socket-activate` 单独证明真实 activation 环境与 fd 3 happy path；不让它承担 child 换代 supervisor 职责。
- 用测试父进程持续自持并复制同一个 listener fd，分别启动旧／新 child，在 service gap 建立新连接，验证 listener identity 与 queued／unaccepted continuity。若改用临时 user manager，必须自动销毁且不写真实 manager 持久状态。
- 另建已被旧进程 accept 的长请求／流，验证它由旧进程 drain 或在 deadline 后中断，新进程不接管；关闭 listener owner 和客户端自动重连分别作为判别力对照。
- 覆盖 fd 不存在、非 stream listener、queue 满与客户端先超时等错误路径；使用动态端口或临时 Unix socket。

**风险与回滚**：CI 可能没有 systemd 工具或 user manager。可移植 direct inherited-fd smoke 始终运行；systemd-specific probe 能力不足时显式 skip／unsupported，不能伪装通过，也不反向阻塞已通过 code R4 的 M1 基座回并。

### M1：main checkpoint 已完成，Plan 继续 living

**状态**：**checkpoint 已完成，Plan 继续 living。** 骨架、findings／权限修复与扩展真实 fd smoke 已从 reviewed source `49fb198…` 经冻结 squash 回放到 `main@cf53334…`。回放后的 main-side gate 为全仓 pytest 375 项、Ruff 与 Pyright 通过；`archive/260807-systemd-runtime` 精确指向 `49fb198…`。

**下一动作**：不再清理旧回放前 WIP、不再回放 `fe9c203…`，也不重复 code R4。S3／S4 已完成 source review，并形成排除 Plan bytes 的 current code-only integration `integrate/260807-systemd-code-only@2ec0cb8…`；exact tip 已取得 merged-state review `0 blocker／0 major` 与 verify `PASS`。Living 文档 checkpoint 形成后立即按 `862f4cfa…` → `2ec0cb8…` 逐片回放 current main；每片后执行 main-side gate，随后从当时 checkpoint bytes fresh 更新并再次 checkpoint 本 Plan。旧 `91f95f7…`／`0a93e7f…` 链只作历史 provenance，禁止回放或用于 Plan 冲突解决。Current 回放不等待 installer atomicity、S3 配置测试判别力或其他 helper hardening；随后进入 S5，最后才是 S7 rolling，Plan 全程保持 living。

**证据边界**：M1 完成只表示仓库 checkpoint 已进入 main。它不表示 unit 已安装、user manager 已激活、真实 cgroup limits 已施加、现有服务已替换、部署完成或 cutover；不授权 unit copy、daemon-reload、enable、start、restart 或任何运行态切换。

### S3：graceful timeout 单一时间模型

**状态**：reviewed source `feat/systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5` 已完成并取得独立代码评审 `0 blocker／0 major／1 non-blocking minor`、明确可 squash；其语义已作为 current code-only integration 第一提交 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` 落在 `80bc8f2…` 之上，该提交明确不含本 Plan，尚未进入 main。

**目标**：消除候选 `TimeoutStopSec=330s` 与实际应用运行态之间的无证据对应关系。

**基线差距与已完成处置**：

- `docs/2604-rewrite/shutdown.md` 描述 `60s` graceful wait、`120s` abort wait 与四阶段设计，但旧设计文档不能证明生产已接线。
- `src/app/shutdown.py` 当前只按顺序 await 可选 callbacks；`src/app/server.py` 的 lifespan cleanup 未创建或消费 `ShutdownManager`。
- 基线 CLI 只传 `fd`，没有显式固定 Uvicorn graceful timeout；S3 已增加 `shutdown.graceful_timeout`、YAML／env／CLI 优先级并把 effective 值传给 Uvicorn。
- 基线 `330s` 只是模板值；S3 已冻结 `300s` application timeout＋`30s` process-manager margin＝`330s` systemd deadline，并以共享常量、unit 反解、严格不等式负控和真实短 timeout probe 对账，不再引用“60＋120＋余量”。

**已完成实施**：

1. 从真实 signal handler、Uvicorn config、FastAPI lifespan 与 cleanup 调用链确认 Uvicorn 拥有 SIGTERM／graceful cap，FastAPI lifespan 拥有 cleanup；未接线的 `ShutdownManager` 不产生第二个 owner。
2. 冻结 `systemd stop deadline = Uvicorn graceful timeout + positive process-manager margin`；默认值为 `300s＋30s=330s`，余量不是第二套 cleanup timer。
3. 增加正值 `shutdown.graceful_timeout` 配置、自然环境变量映射和 CLI override，沿用既有 default→YAML→env→CLI 优先级。
4. 两条 Uvicorn 启动路径均传入 effective `timeout_graceful_shutdown`；不新增 signal handler、重复信号升级或历史四阶段接线。
5. 共享 Python 常量与 smoke 机械对账 unit 的 `--graceful-timeout 300`、`TimeoutStopSec=330s` 和 `30s` 余量。

**已执行测试**：

- CLI unit 覆盖 settings 默认值和 `--graceful-timeout` override 均传入 Uvicorn；配置 loader 覆盖现有 YAML／env／CLI 优先级用例，其对中间层的判别力缺口已记录为 non-blocking minor。
- Unit smoke 从 service `ExecStart` 反解应用值，与共享默认常量、`TimeoutStopSec` 和 manager 余量机械对账，并以相等 deadline 负控证明 systemd deadline 必须严格更大。
- 真实短 timeout probe 使用动态 listener、受控 generic upstream 和 `--graceful-timeout 1`，阻塞一个 accepted request 后发送 SIGTERM；已观察 Uvicorn timeout 分支、FastAPI lifespan shutdown completion 与进程有界退出。
- 现有真实 fd smoke 继续覆盖未阻塞请求的正常 SIGTERM／lifespan cleanup、History 与 tokenization 落盘。再次发送终止信号的四阶段升级仍明确 unsupported，不以 helper 类存在宣称支持。

**验收与评审结果**：unit、CLI／Uvicorn 与 app lifecycle 已共享可复现时间模型；定向 pytest 30 项通过，全仓 pytest 执行与 collect-only 两种方法均为 437 项，全仓 Ruff 与 Pyright 通过，临时替换未安装 `/opt` 解释器路径后的 `systemd-analyze verify` 返回 0。独立代码评审确认 `865a5b7…` 为 0 blocker／0 major、可以 squash。唯一 minor 是 shutdown 专属配置优先级测试只断言最终 CLI 值，不能独立证明 YAML／env 中间层均被消费；独立 runtime probe 已确认产品行为正确，该测试增强不阻塞集成或回放。

**风险与回滚**：修改 timeout 可能放大 stop 延迟或过早切断 SSE／WebSocket。先以缩短时间的隔离测试验证状态机，再改变模板；回滚只恢复 timeout 对齐提交，不回退 socket activation。

### S4：rootless user install dry-run helper

**状态**：reviewed source `feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd` 已完成并取得独立代码评审 `0 blocker／0 major／1 non-blocking minor`、明确可 squash；其语义已作为 current code-only integration 第二提交 `2ec0cb81832691685bfe8d98ad03071d2d5e5316` 接在 `862f4cfa…` 之后，该提交明确不含本 Plan，尚未进入 main。本计划不执行真实安装。

**目标**：让普通用户能把仓库路径、Python 解释器、配置文件、监听地址和 limits 渲染为 user units，且整个过程可预览、可检查、可幂等重跑，不需要 sudo。当前切片不承诺备份／卸载意义上的完整可逆。

**已冻结合同**：

- 默认动作固定为 dry-run：只向 stdout render 三份 unit；可选 `--check` 使用临时目录运行文本检查及可用时的 `systemd-analyze --user verify`，不写 `~/.config/systemd/user`，也不改变 user manager 状态。
- 只有显式 `--apply` 才写入 `$XDG_CONFIG_HOME/systemd/user/` 或其规范 fallback。实现按固定顺序对三份 unit 逐文件原子替换，相同内容报告 `UNCHANGED` 且不改 mtime；不承诺三文件 all-or-nothing。
- helper 不创建系统用户，不写 `/etc`／`/opt`，不调用 sudo，不自动 `daemon-reload`、enable、start 或 restart。
- `--check` 对渲染结果运行内置合同检查，并在工具可用时运行 `systemd-analyze --user verify`；工具缺失时明确报告 parser unavailable，不伪称 verify 通过。Helper 检查项目目录与解释器，但不读取可选 EnvironmentFile 内容。
- user service 不保留 system unit 的 `User=`／`Group=`；路径、WantedBy target、slice 名称与资源控制按 user manager 语义渲染，不能机械复制系统模板。
- secrets 不写入生成日志或 world-readable unit；环境文件只引用路径，helper 不采集 token。

**测试与实际结果**：临时 HOME／XDG 根覆盖 dry-run 零写、check、explicit apply 精确三文件、重复运行幂等、路径含空格、secret 不泄露、parser 缺失时诚实降级、真实 `systemd-analyze --user verify` 和零 `systemctl`；所有测试不调用真实 user manager。Source exact HEAD 全仓 pytest 执行与 collect-only 均为 437 项，Ruff 与 Pyright 通过。已有文件冲突、备份／uninstall manifest、恶意 symlink 与权限错误属于后续 helper hardening，不冒充 current slice 已覆盖，也不阻塞 code-only integration 回放。

**验收**：rootless helper 的默认 dry-run 没有持久副作用；测试中的显式 install 只写临时 `XDG_CONFIG_HOME`；仓库文档把 dry-run／render、install、reload、enable 与 start 分成用户分别主动发起的步骤。本计划实施和验收阶段不执行真实安装。

**评审 minor、风险与回滚**：独立评审与后续裁决确认 apply 只保证逐文件原子替换，第二／第三文件替换失败会显式非零、无临时残留，修复外部故障后重跑可收敛；不保证整组事务。后补只需统一“逐文件原子替换；整组不承诺 all-or-nothing”措辞，并增加一个参数化故障恢复回归，不引入 generation staging、整组 rollback 或 manager orchestration。该 minor 与冲突备份／卸载／symlink hardening 不推翻已完成的 merged-state review／verify，也不阻塞逐片回放。User 与 system unit 语义不完全相同，继续保留两套明确 renderer 与共享 facts 机械对账；helper 提交可独立 revert。

### S5：真实 user-manager／cgroup smoke

**状态**：S4 helper 的 render／check／默认 dry-run 合同关闭后实施；不触碰生产端口或现有服务。

**目标**：在备用端口、隔离状态根和可回收 fixture 中，由真实 user manager 加载渲染后的 socket／service／slice，证明真实 fd activation、service lifecycle、graceful／force timeout 边界和 cgroup v2 effective limits；同时让运行实例能够区分 declared limits、effective limits 与 runtime pressure facts。

**涉及文件建议**：为 user unit 渲染结果增加独立 smoke harness；在确需产品内观测时，于 `src/app/observability/` 下增加职责单一的 cgroup reader，并从现有 telemetry setup 注册 metrics。对应增加 fake-tree unit tests 与 capability-gated live smoke。最终文件名由实现者按当前模块结构选择并回写本计划。

**实现要求**：

- 从 `/proc/self/cgroup` 与挂载信息解析当前进程的 cgroup v2 路径，不能假设固定 system slice 路径或 unit 名称。
- reader 接受可注入 root，便于 fake-tree 测试；把 `max` 表达为 typed unlimited，而不是解析失败。
- 每次采样读取 current／events／stat，配置 limits 可低频读取或启动时缓存，但要处理 unit reload／cgroup move；具体刷新策略由性能评审决定。
- 指标不可带 PID、完整 cgroup path 或 request id 等高基数 labels。解析错误使用有界状态 metric／日志，不在每次 scrape 产生噪音洪水。
- 非 Linux、cgroup v1、权限不足和文件瞬时消失时应用继续服务，并明确暴露 unavailable；不能返回伪造的 0 让监控误判无压力。
- `MemoryHigh` 是回收压力阈值，`MemoryMax` 是硬上限；`memory.events.high`、`max`、`oom` 与 `oom_kill` 分开观测。CPU quota 与 throttling 分开，TasksMax 与 current／max events 分开。

**测试与 probe**：

- fake cgroup tree 覆盖 numeric、`max`、缺文件、权限错误、counter 增长、cgroup path escape 和文件在读取间消失。
- metric collector 测试证明 counter／gauge 类型、单位、低基数与 unavailable 语义；exact 名称在评审后冻结。
- capability gate 先确认隔离 user manager、runtime directory、cgroup v2 delegation 与所需 controllers 可用；缺任一能力时必须报告 `unsupported`／skip 原因，不能回退为只读模板后宣称 live smoke 通过。
- 真实 rootless probe 使用备用动态端口与隔离状态根，加载 S4 渲染产物，证明 manager 传递 listener、应用 readiness、service restart 前后 listener continuity、SIGTERM graceful 路径、受控 force-timeout 路径、进程真实 cgroup 归属和退出后 unit／cgroup 清理。
- 在 transient delegated user scope 中设置较小但安全的 `MemoryHigh`／`CPUQuota`／`TasksMax`，以 systemd 属性、`/proc/<pid>/cgroup` 与对应 cgroupfs 文件交叉对账；不制造 OOM、不压测共享主机。
- `.slice` 声明与 user／system 渲染结果分别通过静态 verify，不把 system template 数值强套到 user 环境。

**验收**：同一渲染候选在真实 user manager 下完成 activation、readiness、restart、graceful／force timeout 与 cleanup；声明值、effective 值与动态事件三者可区分；fake-tree tests 在所有 CI 环境运行；live smoke 前后只读证明生产 listener、现有服务与 `cc-daemon` 身份不变。能力不可用时有明确 unsupported 报告，不得把静态 verify 冒充真实 manager／cgroup 通过。

**风险与回滚**：scrape 热路径频繁读 procfs／cgroupfs 可能增加开销。先 profile 采样成本并采用 observable callback／有界缓存；若 metrics 接线需回滚，保留 unit limits 与 reader tests，不影响服务启动。

### S6：M2 强化组合验证与复核

**状态**：S3＋S4 已形成 current code-only integration `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`，exact range 相对 current `main@80bc8f2…` 恰有 `862f4cfa…` → `2ec0cb8…` 两个线性非 merge 提交，且两片都排除 `docs/agents/systemd-runtime/plan.md`。固定 clean tree 的全仓 pytest 执行与 collect-only 均为 440 项；该 exact tip 的 merged-state review 为 `0 blocker／0 major`、独立 verify 为 `PASS`。S5 仍是回放后的后续切片，本阶段不追溯改写已完成的 M1 checkpoint。

**目标**：证明回并后强化分片各自通过后，组合状态没有在 unit、CLI、shutdown、helper 与 metrics 接缝重新引入矛盾。

**验证矩阵**：

| 层级 | 必跑内容 | 不证明的事项 |
|---|---|---|
| 静态 unit | parser tests、`systemd-analyze verify`、路径与依赖对账 | fd 真传递、进程 readiness、effective limits |
| CLI unit | `--fd` 接线、bind 冲突、错误 fd | systemd lifecycle |
| 真实 user-manager activation smoke | 真实 inherited fd、HTTP health、listener restart window、unit cleanup | accepted connection 迁移、生产容量或 cutover |
| shutdown integration | SIGTERM、drain、deadline、cleanup | crash／OOM 时连接不中断 |
| cgroup fake-tree | 解析、metric mapping、错误语义 | 宿主机实际 controller delegation |
| user-manager／cgroup live probe | effective limits、进程归属、graceful／force timeout、cleanup | system unit 账户、`/opt` 部署或生产接管 |
| full project gates | Ruff、Pyright、全量 pytest | 已安装或生产可替换 |

**评审**：S3 source `865a5b7…` 与 S4 source `e16c2a7…` 的定向独立评审均已达到 0 blocker／0 major。Current `2ec0cb8…` 两提交 code-only 组合已从假绿与假红两个方向检查并取得 merged-state review `0 blocker／0 major`；独立 verify 为 `PASS`，并确认 Plan bytes 相对 base 未改变、system／user deadline drift 正控按目标原因转红。Living 文档 checkpoint 后，不等待 installer atomicity、配置测试判别力或其他 helper hardening，直接按 `862f4cfa…` → `2ec0cb8…` 逐片回放 main。每片回放后重跑该片 main-side gate，任一片失败即停止；通过后 fresh 更新并 checkpoint 本 Plan，再进入下一片。旧 `0a93e7f…` 的 review／verify／replay gate 继续作为历史组合语义与路径适配证据，但其 commit identity 与 Plan postimage 不可用于 current 回放。M2 组合复核不得推翻已完成的 M1，除非发现直接影响 M1 正确性的新事实。

**回并边界**：回放前重新验证 current main、`integrate/260807-systemd-code-only@2ec0cb8…` exact tip、两个 parent、恰好两个非 merge 提交、两片 pathset 均不含本 Plan，以及 clean worktree；若 main、Plan checkpoint bytes 或 code-only identity 已前进，则先重建适用性 gate，不盲用旧 verdict。按顺序逐片回放，并在每片 main-side gate 与 fresh Plan checkpoint 通过后才进入下一片；不得把两片压成一个无法独立回滚的提交。两片成功后的 source archive targets 仍为 `865a5b7…` 与 `e16c2a7…`，不改指 rebuilt commits；worktree／branch 清理与 archive ref 更新属于回放后动作，不在本计划自动执行。

### S7：双实例／rolling 后续切片

**状态**：S3～S6 后的独立切片；明确保留，当前不实施、不伪装成 M1 或真实 user-manager smoke 的自然副作用。

**目标**：在不迁移 accepted connections 的前提下，让新旧应用实例短时间重叠，先把新连接切到 ready 的新实例，再 drain 旧实例，并支持失败回切。

**设计前置**：

- 冻结拓扑：前置 reverse proxy／稳定 listener 加两个后端 socket、两个独立 socket endpoint，或经验证的共享 listener 方案。`Accept=no` 的单 socket → 单 service 关系不能未经 PoC 直接推广为双实例。
- 冻结 readiness 与切流 owner，明确何时新实例可接流、旧实例何时进入 draining、切流失败由谁回滚。
- 盘点并隔离 History SQLite、tokenization state、缓存、临时文件、端口、环境文件与 cgroup；禁止两个实例在没有并发合同的情况下共享单 writer 状态。
- 明确 migration／schema compatibility、配置兼容窗口、最大 overlap 时间与资源预算。
- accepted SSE／WebSocket 继续由旧实例 drain；达到 deadline 后中断属于有界失败，不写成连接迁移。

**后续验收意图**：新实例 readiness 失败时旧实例保持服务；切流后新连接只进入新实例；旧 accepted connections 在 deadline 内完成；回滚不重放已提交响应；双实例并发不会损坏 History／tokenization；listener、切流与 drain 分别有可观察事件。

## 6. 评审 disposition 与开放项

| 项目 | 状态 | 证据／下一动作 |
|---|---|---|
| `Type=exec` | **已采纳、实现并由 code R2～R4 关闭** | R1 与可行性报告方向一致；`1a220e04…` 已同步 unit、测试与文档，`49fb198…` 无回归。readiness 继续独立 |
| `KillMode=control-group` | **已采纳、实现并由 code R2～R4 关闭** | 两报告对旧问题仅分级不同，方向一致；不再作为架构分叉重复讨论 |
| StateDirectory 与显式状态路径 | **启动 major 已由 code R2 关闭** | `StateDirectory=ghc-api-proxy`；History／tokenization 指向 `/var/lib/ghc-api-proxy/`；无 HOME 真实 fd smoke 已落地 |
| 状态最小权限 | **code R2 major 已由 `49fb198…` 修复并由 code R4 关闭** | `StateDirectoryMode=0700`、`UMask=0077`、覆盖目录最小权限文档和真实 writer mode 回归已完成 |
| `--fd 0` | **R1 minor 已由 code R2～R4 关闭** | Typer `min=1` 与精确拒绝测试已落地且无回归 |
| M1 真实 fd smoke | **已扩展并由 code R4 复核，integration 再次通过** | inherited fd、预连接 backlog、readiness 200、真实请求、无 HOME、History＋tokenization、覆盖目录、状态权限与 cleanup 已覆盖；`fe9c203…` 上 smoke 6 项通过 |
| EnvironmentFile secret 边界 | **code R4 non-blocking minor，后续部署强化** | 现路径仅作兼容且不阻塞 M1；后续优先评估 `LoadCredential=`／`LoadCredentialEncrypted=` 与现有 `auth.token_file` 接线 |
| M1 squash／回放 checkpoint | **已在 main 完成，Plan living 继续** | `cf53334…` 已是 current `main@80bc8f2…` 的祖先；M1 gate 为全仓 pytest 375 项、Ruff、Pyright 通过；archive ref → `49fb198…` | 不重复回放；S3＋S4 code-only 组合门已闭合，当前等待 living 文档 checkpoint 后逐片回放，不外推安装、部署或 cutover |
| activation／service-gap／accepted-drain 深化 | **S5 真实 user-manager smoke 范围** | `systemd-socket-activate` 与父进程 listener-owner probe 继续作为可移植分层证据；真实 manager 下单独验证 drain／timeout／不迁移 |
| shutdown owner／deadline | **S3 source review 0 major，code-only integration 第一片** | `865a5b7…` 冻结 Uvicorn `300s` graceful cap、FastAPI lifespan cleanup owner 与 systemd `330s` deadline；review 0 blocker／0 major，配置中间层测试 minor 后补；current 集成提交为 `862f4cfa…`，不含 Plan patch |
| rootless install dry-run helper | **S4 source review 0 major，code-only integration 第二片** | `e16c2a7…` 默认 dry-run、显式 apply、诚实 check、幂等、零 manager 操作；review 0 blocker／0 major。Atomic minor 已裁决为后补逐文件故障恢复合同，不阻塞 current 集成提交 `2ec0cb8…`，该提交不含 Plan patch |
| S3＋S4 current code-only integration | **merged-state review 0 major／verify `PASS`，待 living 文档 checkpoint 后回放** | `integrate/260807-systemd-code-only@2ec0cb8…` 恰含 `862f4cfa…` → `2ec0cb8…` 两提交；全仓 pytest 与 collect-only 均为 440 项；两片排除 Plan bytes。文档 checkpoint 后逐片回放并在每片 gate 后 fresh 更新 Plan，不等待后续 hardening |
| 旧 S3＋S4 integration | **仅历史 provenance，不可回放** | `integrate/260807-systemd-next@0a93e7f…` 与 `91f95f7…` → `0a93e7f…` 的非 Plan 语义、review／verify／replay 证据继续保留；其 Plan patch已过时 | 禁止 cherry-pick、禁止采用 old Plan postimage、禁止把旧 commit identity写成 current 执行路线 |
| 真实 user-manager／cgroup 三层与 metric API | **S5 开放** | 使用备用端口和隔离状态根验证真实 manager lifecycle 与 effective cgroup；typed reader／fake-tree 支撑 declared／effective／runtime 对账，再冻结 metrics 合同 |
| 平台兼容 | **S4～S5 开放** | 明确 systemd 版本下限、user manager／delegation 要求，以及非 systemd／非 Linux 的 unsupported 行为 |
| rolling | **后续独立设计** | readiness 切流、状态隔离、drain、回滚与并发规则先冻结 |

## 7. 验证命令与 rootless 证据边界

所有命令都从经过第 4.1 节身份 gate 的目标 worktree 运行。M1 当前实际存在、无需 root 且不安装 unit 的路径为：

```bash
python -m pytest -q tests/unit/test_cli.py tests/smoke/test_systemd_units.py
systemd-analyze verify contrib/systemd/ghc-api-proxy.socket contrib/systemd/ghc-api-proxy.service contrib/systemd/ghc-api-proxy.slice
python -m ruff check src tests
python -m pyright --pythonpath .venv/bin/python src tests
python -m pytest -q tests
```

仓库模板的 `ExecStart=/opt/ghc-api-proxy/.venv/bin/python` 在未安装环境中可能使直接 `systemd-analyze verify` 因目标路径不存在而非零；M1 应使用受控临时副本替换为真实可执行 fixture，或由测试封装该前置后再 verify，不能屏蔽其他错误，也不能把路径替换后的绿误称为已安装模板可运行。`systemd-analyze verify` 只证明 unit 可解析和部分引用一致，不证明真实 manager 已传 fd、unit 已安装或 cgroup limits 已施加。

M1 回放后的实际 gate 绑定 `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 与主树自身 import oracle：全仓 pytest 自报 `375 passed`，全仓 Ruff 与全仓 Pyright 通过；归档引用随后固定到 reviewed source `49fb1988621bba4356e7a5039a6994c2e6d19604`。这些结果的口径是回放时 current `tests`、`src` 与主树环境，不是永久测试数阈值；后续执行时重跑并记录当时数量。该 gate 没有连接真实 user manager、安装 unit、验证 effective cgroup 或操作生产 listener。

S3 已把 graceful timeout 检查加入 `tests/unit/test_cli.py`、`tests/unit/test_config_loader.py` 与 `tests/smoke/test_systemd_units.py`；短 timeout probe 直接运行真实 CLI／Uvicorn，但不连接真实 manager。S4 已增加 `tests/smoke/test_systemd_user_install.py`，只在临时 HOME／XDG 根验证 helper，不连接真实 manager。Current code-only integration `2ec0cb8…` 的全仓 pytest 执行汇总为 440 passed，同一 `tests` 范围的 collect-only 独立计得 440 个 node IDs；该数字绑定 `integrate/260807-systemd-code-only@2ec0cb8…`，不是永久阈值。Merged-state review `0 blocker／0 major` 与独立 verify `PASS` 均已完成，但不替代未来逐片 main-side gate与每片后的 fresh Plan update。Verify 还确认 base／candidate／worktree 的 Plan blob未变化；这证明代码集成排除 Plan bytes，不证明 current main working-tree Plan 已 checkpoint。不存在的 `tests/smoke/test_systemd_socket_activation.py` 与 `tests/unit/test_cgroup_observability.py` 不作为 current 已通过命令。User-manager smoke 必须由测试 harness 创建隔离 runtime／状态并自动清理；不允许手工改动常驻用户 manager 来补证据。

任何测试数量、耗时或性能数据都在实际运行后记录命令、HEAD、路径范围与环境，并用不同原理交叉核对；本计划不预填数字。

## 8. 未采纳或暂不采纳的方案

### 把 socket activation 写成 accepted connection 无缝迁移

未采纳。systemd 持有 listener 不等于持有旧应用已经 accept 的连接；后者只能由旧实例 drain 或在 deadline 后中断。

### 保留 `Type=simple` 或 `KillMode=mixed`

未采纳。两份报告共同支持 `Type=exec`，也共同推荐 `KillMode=control-group`；对后者只是严重级别不同，不是方向分歧。`1a220e04…` 已实施纠偏，code R2～R4 已关闭并确认无回归，不重开已决选择。

### 使用 `Type=notify` 表达 readiness

未采纳。当前应用没有 `sd_notify(READY=1)` 接线；`Type=exec` 只改进 exec 成功判定，不能冒充应用 ready。未来若引入 notify，需单独规格和 readiness smoke。

### 以 `TimeoutStopSec=330s` 直接绑定历史 `60s + 120s`

未采纳。当前生产 lifespan 未消费历史文档描述的四阶段 manager，数字没有运行态同源关系。S3 从真实接线重建时间模型。

### 直接回放旧 `systemd-next` 提交链

未采纳。旧 `91f95f7…` 与 `0a93e7f…` 都携带已被 current living bytes 超越的 Plan patch，三方模拟会产生冲突；人工采用 old postimage 会回退 current 状态。Current 唯一路线是回放排除 Plan bytes 且已取得 review `0 blocker／0 major`、verify `PASS` 的 `862f4cfa…` → `2ec0cb8…`，并在每片 main-side gate 后 fresh 更新本 Plan。

### 为测试安装 user unit

未采纳。安装与 manager 持久变更超出当前验证边界，也会污染用户环境。测试使用临时 harness、fake tree 与可自动销毁 scope。

### 通过制造 OOM 验证 `MemoryMax`

未采纳。它会给共享开发机造成不可接受风险。使用 effective file 对账、safe pressure threshold 与 fake `memory.events`；真实 OOM 行为只在专用隔离环境另行执行。

### 在单实例模板上直接叠加 templated services 实现 rolling

未采纳。单 socket 的 service 归属、readiness 切流和共享状态并发都未冻结。S7 先做拓扑与状态隔离设计，再写实现。

## 9. 结构怪味与处置

| 位置 | 怪味 | 处置 |
|---|---|---|
| `src/app/shutdown.py` 与 `src/app/server.py` | 设计类存在但生产 lifespan 未消费，容易把“类已实现”误写成“四阶段运行态已接线” | S3 已确认并保持 Uvicorn／lifespan ownership；四阶段 helper 仍未接线且明确不在本切片范围，不以 helper 存在证明支持 |
| `contrib/systemd/ghc-api-proxy.service` | 静态 unit 无法直接导入 Python 常量，`300s` 与 `330s` 仍以文本值存在 | `src/app/graceful_timeout.py` 统一声明默认值、正余量与计算结果；smoke 从 unit 反解两个文本值并与常量机械对账，任一侧漂移即红 |
| `tests/smoke/test_systemd_units.py` | 静态 unit tripwire、真实 writer 权限与 inherited-fd／upstream smoke 同文件，且 direct harness 尚不能证明 manager-level activation／service-gap | M1 保留 code R4 已复核并在 `fe9c203…` 再次通过的可移植纵向 smoke；S5 把 activation、listener-owner continuity 与 accepted-drain probe 按能力边界拆分 |
| `contrib/systemd/ghc-api-proxy.service` 的 EnvironmentFile | 兼容配置与 secret 传递边界混在同一机制，文件 mode 不能消除环境经 D-Bus／进程树暴露的风险 | 记录 code R4 non-blocking minor；后续部署强化优先评估 systemd credentials 与现有 token-file 接线，不反向改写 M1 |
| system templates 与 user-unit renderer | 两套合同独立表达，公共 shutdown／resource 数值仍可能漂移 | S4 避免从 system unit 做字符串替换；current code-only review／verify 已机械对账 timeout facts并以 deadline drift 正控验证判别力，resource facts 留到 S5，不把全文模板强行合一 |
| `tests/unit/test_config_loader.py` 的 shutdown 优先级用例 | 只断言最终 CLI 值，YAML／env 同时失效时仍可能假绿 | 记录 S3 review non-blocking minor；后补拆分或参数化 `300／11／12／13`，不阻塞当前集成评审与回放 |
| `contrib/systemd/install-user.py` 的 apply 路径 | 单文件原子替换容易被误读为三文件 all-or-nothing；现有仓库测试未固化第二／第三文件失败后的恢复合同 | 记录 S4 review／裁决 non-blocking minor；后补统一逐文件原子措辞并增加“显式失败、无临时残留、重跑收敛”参数化回归，不为本轮引入整组事务，也不阻塞回放 |
| rootless helper 错误路径 | 冲突备份／卸载 manifest 与 symlink hardening 尚未实现 | 保留后续 helper hardening；不把现有 happy-path 测试外推到这些路径，也不让其延迟已获 0 major 的两片回放 |
| cgroup 声明与 metrics | unit 配置和应用观测分属两处，可能一边改 limits、一边继续解释旧阈值 | S5 把 declared／effective／runtime 三层写入同一测试矩阵和部署文档 |
| 旧 integration commits 中的 `docs/agents/systemd-runtime/plan.md` patch | 高频 living 状态与可复用代码语义耦合，导致代码仍适用而提交对象不可安全回放 | Current code-only commits 排除 Plan bytes；每片 gate 后从当时 checkpoint fresh 更新 Plan。旧链仅保留 provenance，长期可再拆分 volatile execution state 与稳定设计，但不删减本 Plan 的 living 信息 |

## 10. 每轮反思门

每个切片结束后把以下三项的实际结论写回本节或对应阶段，不能只写“当前方案最佳”：

1. **内部替代方案**：是否可用 Uvicorn 已有 fd／shutdown 能力、systemd 原生 unit 语义或现有 telemetry setup，避免重复造 lifecycle owner。
2. **判据判别力**：静态 verify、执行 smoke、continuity probe 与 timeout test 是否分别能让目标缺陷变红，也是否允许正确的无 systemd CI 环境以明确 unsupported／skip 通过。
3. **成熟方案**：user unit 渲染、cgroup metrics 读取和 socket activation harness 是否已有维护良好的库／systemd 工具可复用；采用前核对当前版本文档与项目兼容性，不凭记忆锁版本。

发现更优方案但本轮不切换时，记录到第 8 节并说明前置条件；不得静默丢弃。

## 11. 实施 kick-off

从 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 继续本 living Plan。M1 已以 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 进入 main，回放时全仓 pytest 375 项、Ruff 与 Pyright 通过；`archive/260807-systemd-runtime` 精确指向 reviewed source `49fb1988621bba4356e7a5039a6994c2e6d19604`。不要重放 `fe9c203…`。每次 shell 都在同一次调用内验证主树物理 root、`main` 分支和当次 current HEAD，不依赖前一调用的 cwd；记录开始／结束 status，只提交当前语义切片的精确 pathspec。

先消费两份初始 systemd reports、code R2～R4、Plan R2～R6、旧 systemd-next 证据，以及 `docs/tmp/260807-audit-systemd-next-rebuild.md`、`docs/tmp/260807-review-systemd-code-only.md`、`docs/tmp/260807-verify-systemd-code-only.md`。M1 已确认 `Type=exec`、`KillMode=control-group`、StateDirectory＋显式 History／tokenization 路径、`--fd >= 1`、`StateDirectoryMode=0700`、`UMask=0077`、覆盖目录文档、真实 writer 权限回归，以及无 HOME 的 inherited-fd／backlog／readiness／真实请求／History＋tokenization smoke。保持 `/health/readiness` 为独立 oracle；不得把 `Type=exec` 写成应用 ready，也不得把仓库 checkpoint 写成 unit 已安装或运行态已切换。

S3 source `865a5b71210e2436b36786b5de67146939d1e0f5` 与 S4 source `e16c2a700f23f66535e7347ab7357518eb8e56bd` 均已独立评审为 0 blocker／0 major、可以 squash，后续 source archive targets 保持这两个 exact HEAD 不变。Current integration 是 `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`，相对 `main@80bc8f2…` 恰含 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` → `2ec0cb81832691685bfe8d98ad03071d2d5e5316` 两个线性非 merge 提交；两片均排除本 Plan bytes，固定 clean tree 的全仓 pytest 与 collect-only 均为 440 项，exact tip merged-state review 为 `0 blocker／0 major`、独立 verify 为 `PASS`。Living 文档 checkpoint 形成后按上述顺序逐片回放 current main：第一片 gate 通过后 fresh 更新并 checkpoint Plan，第二片只在该 checkpoint 后回放，第二片 gate 后再次 fresh 更新 Plan。旧 `integrate/260807-systemd-next@0a93e7f…` 及 `91f95f7…` → `0a93e7f…` 只作历史 provenance，绝不可回放或用于恢复 Plan postimage。不要等待 installer atomicity、配置测试判别力、冲突备份／卸载或 symlink hardening；这些均已明确记录为后补，不得偷偷升级为本轮回放门。

两片进入 main 后继续 S5：使用 S4 渲染结果在备用动态端口、隔离状态根与可回收 user-manager fixture 中执行真实 activation、restart、graceful／force timeout、cgroup 归属与 cleanup smoke，并以 typed reader／fake-tree 支撑 declared／effective／runtime 三层对账。S5 与后续 rolling 仍各自独立实施、验证和评审；本 living Plan 不因 S3／S4 回放而收口。

始终区分 listener continuity、queued／unaccepted connections 与旧进程 accepted connections；单实例 socket activation 和真实 user-manager smoke 都不得称为双实例／rolling 或 accepted connection zero-downtime。双实例／rolling 留到 S7，先冻结稳定 listener／proxy 拓扑、readiness 切流、状态隔离、drain 与回滚，再实施。

完成每个切片后立即更新本文件的状态看板、实际 HEAD、测试证据、评审 verdict、结构怪味和下一动作。任何仓库内 gate 或备用 user-manager smoke 全绿都不等于已部署或已 cutover；系统安装、运行态替换和发布由用户另行明确发起。
