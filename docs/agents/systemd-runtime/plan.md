# systemd runtime living 实施计划

> 状态：`LIVING`，Plan 可继续。候选 `49fb198…` 的 code R4 已达到 `0 blocker／0 major` 并明确可 squash；Plan R4 的唯一 major 是 current 状态尚未消费已落盘的 R4 结论，本次修订已按其清单同步状态、证据与下一动作。M1 integration squash 已准备完成，下一动作是先清理主树 Anthropic Responses bridge README／Implementation WIP，再回放 `fe9c203…`；不等待后续强化。
> 文档同步基线：本次修订在 `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1` 完成；后续每次 shell 以当次 `main` current HEAD 为门，不把该点时 hash 当作永久执行基线。候选实现仍以 `ed77c9d191df81c451c25161420515cca52ce6a4` 为代码 base。
> 候选实现：`feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`；提交链为候选 base → `66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`（骨架）→ `1a220e04a99c6ce07b4bdd6bb0876b4180d4c489`（R1／可行性 findings 修复）→ `49fb1988621bba4356e7a5039a6994c2e6d19604`（code R2 权限 major 与扩展 smoke 修复）。
> 评审输入：两份初始 systemd 报告 `docs/tmp/260807-review-code-systemd-runtime.md`、`docs/tmp/260807-systemd-socket-feasibility.md`，code R2／R3／R4 `docs/tmp/260807-review-code-systemd-runtime-r2.md`、`docs/tmp/260807-review-code-systemd-runtime-r3.md`、`docs/tmp/260807-review-code-systemd-runtime-r4.md`，以及 Plan R2／R3／R4 `docs/tmp/260807-review-systemd-runtime-plan-r2.md`、`docs/tmp/260807-review-systemd-runtime-plan-r3.md`、`docs/tmp/260807-review-systemd-runtime-plan-r4.md` 均已消费。code R4 精确绑定 `49fb198…`，verdict 为 `0 blocker／0 major／1 non-blocking minor`、明确三提交可 squash；Plan R4 为 `0 blocker／1 major／0 minor`，唯一 major 即本文件仍停留在“R4 进行中／code R3 current”的旧状态，本次修订只关闭该状态同步项，不把它冒充为新 bytes 的独立复评 verdict。
> integration 准备：clean `integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef` 是 `main@ec5e8f5…` 的直接子提交，已把候选三提交 squash 为单一 `feat: add systemd socket activation runtime`。本次修订现场在该 exact HEAD 与正确 import oracle 下复验全仓 pytest `301 passed`，并以独立 collect-only node ID 计数交叉核对为 301；全仓 Ruff、全仓 Pyright 与 `tests/smoke/test_systemd_units.py` fd smoke 均通过，验证后 integration worktree clean。
> 当前边界：本计划只规划仓库内实现、测试、文档与 rootless probe；不得安装、启用、启动、停止或替换任何 system／user unit，不得触碰当前运行中的 `copilot-api-js`。
> 计划位置：`docs/agents/systemd-runtime/plan.md`。

## 1. 目标与完成定义

本计划把候选提交中的 systemd socket activation、Uvicorn inherited fd 与 cgroup v2 骨架逐步收敛为可评审、可 rootless 验证、可由用户显式安装的运行方案。开发节奏遵循本项目当前约定：骨架与 happy path → 真实 fd smoke → current candidate 独立代码复评达到 0 blocker／0 major → living Plan 同步 current 证据与下一动作 → squash／回并 → 在已回并基座上继续 timeout、install helper、cgroup observability 与 rolling 强化。候选 `49fb198…` 已通过 code R4，integration squash `fe9c203…` 已准备并通过 main-side 回放前全量 gate；当前不再等待代码或 Plan R4，先完成主树 Anthropic Responses bridge README／Implementation WIP 清理，再把该 squash 回放到届时的 `main` current。计划在每个切片后动态更新，不以“计划尚未批准”为由停工，也不把传统 test-first／强制 TDD 设为流程门。

首次回并里程碑 M1 完成不等于已经部署，也不等于 long-term systemd runtime 全部完成。M1 的 squash／回并门只包含：

1. current candidate 保留 inherited fd、`.socket/.service/.slice`、部署说明与快速静态测试骨架。
2. R1 与可行性报告的 findings 已由 code R2 正式关闭：`Type=exec`、`KillMode=control-group`、`StateDirectory=ghc-api-proxy` 加显式 History／tokenization 状态路径，以及 `--fd` 下界 1；readiness 继续由 `/health/readiness` 独立判定，不能由 `Type=exec` 或 process active 冒充。code R2 新发现的权限 major 也已由 `49fb198…` 的 `StateDirectoryMode=0700`、`UMask=0077`、覆盖目录最小权限文档和真实 writer mode 回归修复，由 code R3 首次关闭并由 code R4 在最终 bytes 上复核确认。
3. 无需 root、无需安装 unit 的真实 fd smoke 已证明预连接 backlog 请求可由应用处理，并在 `HOME=/nonexistent` 时成功启动；扩展 smoke 还使用受控 generic upstream 验证 readiness 200、真实 Anthropic 请求、History 与 tokenization 落盘、EnvironmentFile 等价覆盖目录，以及状态目录／数据库／WAL／SHM／临时与最终文件均无 group／other 权限。activation happy path 与 listener continuity probe 的 harness 职责继续分开。
4. 文档严格区分 listen／queued-unaccepted continuity 与旧进程 accepted connection drain，不使用“无缝重启”或“零停机”替代可验证语义。
5. current candidate HEAD 的 code R4 已达到 0 blocker／0 major，并记录定向测试、Ruff、Pyright 与适用于当前骨架的 rootless smoke 通过。原始模板的 `systemd-analyze verify` 唯一诊断仍是安装前约定路径 `/opt/ghc-api-proxy/.venv/bin/python` 不存在，未发现 unit 语法或字段诊断；不得把该预期非零写成原模板 verify 通过。
6. integration squash `fe9c203…` 已基于 `main@ec5e8f5…` 准备并在本次修订现场通过全仓 pytest 301 项、Ruff、Pyright 与 fd smoke；301 同时由 pytest 执行汇总和 collect-only node ID 计数核对。M1 下一动作只等待主树 `docs/agents/anthropic-responses-bridge/README.md` 与 `implementation.md` 的 WIP 清理／提交边界闭合，随后重新读取 `main` current 并回放该 squash；不等待 graceful timeout、install helper、完整 cgroup observability 或 rolling。

回并后的 M2 强化保持完整范围，但不反向扩大 M1：对齐 graceful timeout；实现默认 dry-run 的 rootless user install helper；建立 cgroup declared／effective／runtime 三层读取和观测；最后另开双实例／rolling 切片。每片独立提交、验证、评审并更新本 living plan。

## 2. 固定事实、已知可行性与能力边界

### 2.1 基线与候选事实

以下候选事实锚定到代码 base `ed77c9d191df81c451c25161420515cca52ce6a4` 与 current candidate `49fb1988621bba4356e7a5039a6994c2e6d19604`；文档状态则锚定本次修订时的 `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1`，执行时必须重新读取 `main` current：

- 候选包含三个提交：`66551e45… feat: add systemd socket activation runtime`、`1a220e04… fix: harden systemd runtime contract` 与 `49fb198… fix: restrict systemd state permissions`。第三个提交消费 code R2 的权限 major 及非阻断 smoke 覆盖项。
- CLI 候选增加 `--fd`，拒绝与显式 `--host`／`--port` 混用，并把 inherited fd 传给 `uvicorn.run(..., fd=fd)`。
- `--fd` 的 Typer 下界已由 0 收紧为 1，并有精确 `--fd 0` 拒绝测试；Uvicorn 0.40.0 不会把 0 解释为 inherited socket 的旧合同缺陷已修。
- socket 候选使用 `ListenStream=127.0.0.1:4141`、`Accept=no`、`Backlog=1024`、`FileDescriptorName=http`，service 以 `--fd 3` 消费 listener。
- service 候选当前明确使用 `Type=exec`、`KillMode=control-group`、`TimeoutStopSec=330s`、`Restart=on-failure`，并挂到 `ghc-api-proxy.slice`。两份报告对旧 `KillMode=mixed` 的严重级别判断不同，但纠偏方向一致；该分级差异不再构成实施分叉。
- 默认状态目录启动 major 与后续最小权限 major 均已修：service 使用 `StateDirectory=ghc-api-proxy`、`StateDirectoryMode=0700` 与 `UMask=0077`，并把 `GHC_HISTORY__DB_PATH` 与 `GHC_TOKENIZATION__STATE_PATH` 显式绑定到 `/var/lib/ghc-api-proxy/` 下。候选 smoke 在 `HOME=/nonexistent` 下通过真实 fd 启动路径验证 readiness 200、真实请求、SIGTERM cleanup、History／tokenization 落盘与覆盖目录写入；真实 writers 的权限回归验证目录为 `0700`，数据库、WAL／SHM、tokenization 临时及最终文件为 `0600`。这说明修复已进入候选并通过 code R4 终审，不代表 system unit 已安装或 systemd 已创建真实 `/var/lib` 目录。
- slice 候选当前声明 `MemoryHigh=1G`、`MemoryMax=2G`、`CPUQuota=200%` 与 `TasksMax=256`。
- 候选现有 smoke 已超出纯静态字段自证：父进程创建真实 TCP listener，预先建立 backlog 连接，把 fd 3 交给真实 CLI／Uvicorn，在无可写 HOME 环境通过受控 generic upstream 验证 readiness、真实 Anthropic 请求、History／tokenization 与覆盖路径写入，并验证真实 writers 的最小权限。它仍未证明真实 systemd manager 传递 fd、service gap 中同一 listener identity、旧 accepted connection drain、超时升级或 effective cgroup limits。
- R1 代码／部署报告为 0 blocker／1 major／2 minor，可行性报告为 0 blocker／1 major／2 minor；code R2 绑定 `1a220e04…`，关闭旧 findings 后发现 0 blocker／1 权限 major／1 minor；`49fb198…` 修复该 major并补齐 non-blocking smoke 覆盖，code R3 首次达到 0 blocker／0 major，code R4 在最终 bytes 上独立确认 `0 blocker／0 major／1 文档 minor` 并明确可 squash。Plan R2／R3 均指出旧 Plan 状态滞后；Plan R4 的唯一 major 仍是 R4 结论未回写，本次修订已消费其精确同步清单，Plan living 可继续。
- clean integration `fe9c203…` 是 `ec5e8f5…` 的直接子提交，tree 内容是候选三提交的单提交 squash。现场 gate 绑定该 exact HEAD、integration branch、clean worktree 与该树下的 `app` import oracle；全仓 pytest 执行汇总和 collect-only node ID 两种方法均得到 301，全仓 Ruff、全仓 Pyright 与 systemd fd smoke 通过。该证据只放行仓库回放，不表示 unit 已安装或运行态已切换。
- 候选尚未进入 `main`，尚未执行任何 system／user 安装或运行态替换。

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
| M1 首次 squash／回并 | **integration squash 已准备，Plan living 可继续** | clean `fe9c203…` 直接基于 `ec5e8f5…`；全仓 pytest 301 项、Ruff、Pyright、fd smoke 通过；Plan R4 状态同步 major 已由本次修订消费 | 先清理主树 Anthropic Responses bridge README／Implementation WIP，再读取 `main` current 并回放 `fe9c203…`；不等待 S3～S7 |
| S3 graceful timeout 对齐 | **回并后切片** | unit 当前为 `330s`；尚无与 Uvicorn／app cleanup 同源的完整时间模型 | 在已回并基座上建立真实时间模型与超时执行测试 |
| S4 user install helper | **回并后切片** | 当前只有 system-level 模板文档 | 实现 rootless render／check／默认 dry-run／显式 install；绝不自动 reload／enable／start |
| S5 cgroup v2 reader／observability | **回并后切片** | slice 已声明 4 项 limits；effective files 与 runtime metrics 尚未实现 | 先做 typed reader＋fake-tree，再经 API 评审接 metrics；可选 delegated probe |
| S6 M2 组合复核 | **后续** | 等待 S3～S5 分片落地 | 每片独立评审，组合后做 merged-state review；不追溯阻塞已完成的 M1 |
| S7 双实例／rolling | **后续独立切片，未设计、不可冒充已支持** | 单实例 socket activation 只提供 listener continuity | 冻结拓扑、readiness 切流、状态隔离、drain、回滚和并发规则，再实施 overlap smoke |

每个切片完成后立即更新本表、对应阶段的“实际结果”和“证据”字段，并写明候选 HEAD、测试命令与评审 verdict。不得等待所有切片结束后一次性补记。

## 4. 统一执行纪律

### 4.1 shell 与树身份 gate

主树不是固定旧 HEAD。规划、取证、Plan R4 消费与回并准备的每次 shell 都必须在同一次调用内验证物理主树、`main` 分支并读取当次 current HEAD：

```bash
ROOT=/home/xp/src/ghc-api-proxy-py
cd "$ROOT"
test "$(git rev-parse --show-toplevel)" = "$ROOT"
test "$PWD" = "$ROOT"
test "$(git symbolic-ref --short HEAD)" = main
MAIN_CURRENT=$(git rev-parse HEAD)
printf 'SHELL_GATE_MAIN_CURRENT root=%s branch=main head=%s\n' "$ROOT" "$MAIN_CURRENT"
```

候选取证仍必须在同一次 shell 验证候选物理 root、分支与 exact HEAD `49fb1988621bba4356e7a5039a6994c2e6d19604`，并证明代码 base `ed77c9d…` 是候选 HEAD 的祖先；不得把 `git -C` 指向主树的单条命令误当作当前 shell 位于候选树的证明。回并前再次读取 `main` current，记录主树漂移并在重放后的主树状态运行 M1 gates。切片开始与结束都记录 `git status --short`，只提交本切片精确 pathspec。

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

**M1 门**：current candidate code R4 已达到 0 blocker／0 major，三提交已在 integration 上 squash 为 `fe9c203…`；Plan R4 的唯一状态同步 major 已由本次修订消费，Plan living 可继续。先清理主树 Anthropic Responses bridge README／Implementation WIP，再读取 `main` current、回放该 squash并重跑 main-side M1 gates。M1 不等待以下强化：`systemd-socket-activate` 环境验证、service-gap listener identity、旧 accepted connection drain／timeout、main＋child manager-level stop、install helper、effective cgroup limits、metrics 或 rolling。

**回并后 continuity 强化**：

- 用 `systemd-socket-activate` 单独证明真实 activation 环境与 fd 3 happy path；不让它承担 child 换代 supervisor 职责。
- 用测试父进程持续自持并复制同一个 listener fd，分别启动旧／新 child，在 service gap 建立新连接，验证 listener identity 与 queued／unaccepted continuity。若改用临时 user manager，必须自动销毁且不写真实 manager 持久状态。
- 另建已被旧进程 accept 的长请求／流，验证它由旧进程 drain 或在 deadline 后中断，新进程不接管；关闭 listener owner 和客户端自动重连分别作为判别力对照。
- 覆盖 fd 不存在、非 stream listener、queue 满与客户端先超时等错误路径；使用动态端口或临时 Unix socket。

**风险与回滚**：CI 可能没有 systemd 工具或 user manager。可移植 direct inherited-fd smoke 始终运行；systemd-specific probe 能力不足时显式 skip／unsupported，不能伪装通过，也不反向阻塞已通过 code R4 的 M1 基座回并。

### M1：清理 living docs WIP 后回放 integration squash

**状态**：骨架、findings／权限修复与扩展真实 fd smoke 已在 `49fb198…`；code R4 为 0 blocker／0 major并明确可 squash。Plan R4 的唯一 major 是状态滞后，本次修订已消费。clean integration `fe9c203…` 已将三提交 squash 为一个直接基于 `main@ec5e8f5…` 的语义提交，并通过全仓 pytest 301 项、Ruff、Pyright 与 fd smoke；Plan living 可继续。

**动作**：先完成主树 `docs/agents/anthropic-responses-bridge/README.md` 与 `docs/agents/anthropic-responses-bridge/implementation.md` 的 WIP 清理／提交边界闭合，确认不会在回放时夹带现有 `AM` 状态；随后重新读取当时 `main` current，把 `fe9c203…` 回放到目标主树，重跑同一组 M1 gates并回并。若主树漂移导致冲突，按当前内容修复并完整复验，不重做已经由 code R4 接受的候选设计，也不把 timeout、helper、cgroup 或 rolling 塞入 M1。回并代码不等于安装或部署，不授权 unit copy、daemon-reload、enable、start、restart 或现服务 cutover。

**不得扩大门**：S3 graceful timeout、S4 install helper、S5 cgroup reader／observability、完整 continuity 强化及 S7 rolling 都是已保留的后续切片，不是 M1 squash 前置。

### S3：graceful timeout 单一时间模型

**状态**：M1 回并后实施；不阻塞首次 squash／回并。

**目标**：消除候选 `TimeoutStopSec=330s` 与实际应用运行态之间的无证据对应关系。

**当前差距**：

- `docs/2604-rewrite/shutdown.md` 描述 `60s` graceful wait、`120s` abort wait 与四阶段设计，但旧设计文档不能证明生产已接线。
- `src/app/shutdown.py` 当前只按顺序 await 可选 callbacks；`src/app/server.py` 的 lifespan cleanup 未创建或消费 `ShutdownManager`。
- CLI 候选只传 `fd`，没有显式固定 Uvicorn graceful timeout。
- 因此，`330s` 目前只是候选模板值，不得写成“60＋120＋余量”的已实现合同。

**实施顺序**：

1. 从真实 signal handler、Uvicorn config、FastAPI lifespan 与 cleanup 调用链建立当前时间线，先证明谁拥有 stop deadline。
2. 冻结一个单一公式：`systemd stop deadline > application graceful／abort／finalize upper bound + process-manager margin`。所有组成项必须来自生产配置或显式内部常量，禁止从历史文档抄值。
3. 若要新增或公开 shutdown 配置键，先完成配置兼容性与公共合同评审；本计划不自行决定新 public schema。
4. 把 Uvicorn 的 graceful cap 与应用 cleanup 上界显式接线，避免一个无界、另一个先超时。
5. 由同一个真相源生成／验证 unit deadline 或至少在测试中机械对账，防止代码默认值改变后 unit 常量漂移。

**执行测试**：

- 使用毫秒／低秒级测试值启动本地应用，构造立即完成、在 graceful 期完成、超过 graceful 但可 abort、以及 finalize 卡住四类请求／cleanup fixture。
- 发送 SIGTERM，记录 readiness、listener accept、accepted request、lifespan cleanup 与进程退出时点。
- 证明正常 drain 在 systemd deadline 前完成；超时路径由预期 owner 终止，不出现 systemd 先杀进程导致 cleanup 没有机会运行的倒置。
- 再次发送终止信号时，若四阶段升级尚未生产接线，明确记录 unsupported，不以类存在宣称支持。

**验收**：unit、CLI／Uvicorn 与 app lifecycle 共享可复现时间模型；`330s` 要么由证据保留，要么在独立提交中改为经验证值；文档不再引用未接线设计充当运行态事实。

**风险与回滚**：修改 timeout 可能放大 stop 延迟或过早切断 SSE／WebSocket。先以缩短时间的隔离测试验证状态机，再改变模板；回滚只恢复 timeout 对齐提交，不回退 socket activation。

### S4：rootless user install helper

**状态**：M1 回并后实施；不阻塞首次 squash／回并，本计划不执行真实安装。

**目标**：让普通用户能把仓库路径、Python 解释器、配置文件、监听地址和 limits 渲染为 user units，且整个过程可预览、可检查、可逆，不需要 sudo。

**合同草案，须在 helper 评审中冻结具体 CLI 名称**：

- 默认动作固定为 dry-run：只 render 到临时／显式输出目录、运行校验并展示 diff，不写 `~/.config/systemd/user`，也不改变 user manager 状态。
- 显式 install 动作才可原子写入 `$XDG_CONFIG_HOME/systemd/user/` 或其规范 fallback；写前打印目标、拒绝符号链接逃逸、保留可恢复备份或生成精确卸载 manifest。
- helper 不创建系统用户，不写 `/etc`／`/opt`，不调用 sudo，不自动 `daemon-reload`、enable、start 或 restart。
- `--check` 对渲染结果运行 `systemd-analyze --user verify` 或无需 manager 的等价 verify，并检查所有路径存在、解释器可执行、环境文件权限建议和 socket 地址合法。
- user service 不保留 system unit 的 `User=`／`Group=`；路径、WantedBy target、slice 名称与资源控制按 user manager 语义渲染，不能机械复制系统模板。
- secrets 不写入生成日志或 world-readable unit；环境文件只引用路径，helper 不采集 token。

**测试**：临时 `XDG_CONFIG_HOME` 下覆盖 render、check、explicit install、重复运行幂等、已有文件冲突、备份／uninstall manifest、路径含空格、缺解释器、恶意 symlink 和权限错误。所有测试使用临时 HOME，不调用真实 user manager。

**验收**：rootless helper 的默认 dry-run 没有持久副作用；测试中的显式 install 只写临时 `XDG_CONFIG_HOME`；仓库文档把 dry-run／render、install、reload、enable 与 start 分成用户分别主动发起的步骤。本计划实施和验收阶段不执行真实安装。

**风险与回滚**：user 与 system unit 语义不完全相同。采用共享模板数据＋两套明确渲染合同，避免字符串替换 `User=` 等脆弱做法；helper 提交可独立 revert。

### S5：cgroup v2 effective limits 与 observability

**状态**：M1 回并后实施；不阻塞首次 squash／回并。

**目标**：既能验证 slice 模板声明，也能让运行实例报告自己真正受到的 cgroup v2 限制与压力信号。

**涉及文件建议**：在 `src/app/observability/` 下增加职责单一的 cgroup reader，并从现有 telemetry setup 注册 metrics；对应增加 unit tests 与 rootless smoke。最终文件名由实现者按当前模块结构选择并回写本计划。

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
- 可选 rootless probe 在 transient delegated user scope 中设置较小但安全的 `MemoryHigh`／`CPUQuota`／`TasksMax`，只读取 effective files，不制造 OOM、不压测共享主机。
- `.slice` 声明与 user／system 渲染结果分别通过静态 verify，不把 system template 数值强套到 user 环境。

**验收**：声明值、effective 值与动态事件三者可区分；fake-tree tests 在所有 CI 环境运行；rootless live probe 可用时对账真实 cgroup v2，不可用时有明确报告。

**风险与回滚**：scrape 热路径频繁读 procfs／cgroupfs 可能增加开销。先 profile 采样成本并采用 observable callback／有界缓存；若 metrics 接线需回滚，保留 unit limits 与 reader tests，不影响服务启动。

### S6：M2 强化组合验证与复核

**状态**：等待 S3～S5 分片完成；只复核 M2 强化，不追溯扩大 M1 回并门。

**目标**：证明回并后强化分片各自通过后，组合状态没有在 unit、CLI、shutdown、helper 与 metrics 接缝重新引入矛盾。

**验证矩阵**：

| 层级 | 必跑内容 | 不证明的事项 |
|---|---|---|
| 静态 unit | parser tests、`systemd-analyze verify`、路径与依赖对账 | fd 真传递、进程 readiness、effective limits |
| CLI unit | `--fd` 接线、bind 冲突、错误 fd | systemd lifecycle |
| rootless activation smoke | 真实 inherited fd、HTTP health、listener restart window | accepted connection 迁移、生产容量 |
| shutdown integration | SIGTERM、drain、deadline、cleanup | crash／OOM 时连接不中断 |
| cgroup fake-tree | 解析、metric mapping、错误语义 | 宿主机实际 controller delegation |
| optional user-scope probe | effective limits、进程归属、cleanup | system unit 账户与 `/opt` 部署 |
| full project gates | Ruff、Pyright、全量 pytest | 已安装或生产可替换 |

**评审**：S3、S4 与 S5 每片做定向独立评审；组合后再做 M2 merged-state review，两个方向都检查：错误状态是否可能假绿，正确环境是否被过严 gate 误报。每片达到 0 blocker／0 major 后可独立回并，不要求攒齐所有强化；M2 组合复核也不得推翻已通过 code R4 并完成的 M1，除非发现直接影响 M1 正确性的新事实。

**回并边界**：每个强化切片回并前记录 reviewed HEAD、基线、提交序列、主树漂移与重放结果；回并后在 main-side 重新运行该片 gate。worktree／branch 清理属于后续动作，不在本计划自动执行。

### S7：双实例／rolling 后续切片

**状态**：M1 与 M2 后的独立切片；明确保留，当前不实施、不伪装成 S0～S6 的自然副作用。

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
| M1 squash／回并 | **integration squash 已准备，Plan living 可继续** | `fe9c203…` 为 `ec5e8f5…` 直接子提交；全仓 pytest 301 项经执行与 collect-only 计数交叉核对，Ruff、Pyright、fd smoke 通过 | 先清理 Anthropic Responses bridge README／Implementation WIP，再回放 `fe9c203…`；不等待后续强化 |
| activation／service-gap／accepted-drain 深化 | **回并后开放** | `systemd-socket-activate` 与父进程 listener-owner probe 分工；accepted connection 单独验证 drain／timeout／不迁移 |
| shutdown owner／deadline | **回并后开放** | 从生产接线冻结 Uvicorn、应用 manager 与 systemd 的时间模型；历史四阶段文档不能替代证据 |
| user install helper | **回并后开放** | 冻结 CLI、默认 dry-run、原子写入、冲突／备份／卸载策略；不自动 reload／enable／start |
| cgroup 三层与 metric API | **回并后开放** | 先做 typed reader／fake-tree，再冻结 metric names、types、units、unavailable、采样频率与 cardinality |
| 平台兼容 | **回并后开放** | 明确 systemd 版本下限、user manager／delegation 要求，以及非 systemd／非 Linux 的 unsupported 行为 |
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

integration `fe9c203…` 的本次实际 gate 绑定 `/home/xp/src/ghc-api-proxy-py-integrate-systemd`、分支 `integrate/260807-systemd-runtime`、exact HEAD、clean worktree 与该树下的 `app` import oracle：全仓 pytest 自报 `301 passed`，collect-only 输出中的 node ID 独立计数同为 301；全仓 Ruff 为 `All checks passed!`，全仓 Pyright 为 `0 errors, 0 warnings, 0 informations`，`tests/smoke/test_systemd_units.py` 为 6 passed，结束状态 clean。首次全量尝试受共享终端外部 `Ctrl-C` 在 13 项后中断，已废弃且不作为证据；上述有效结果来自忽略外部 INT、隔离进程组并等待真实子进程退出的重跑。

回并后新增的 continuity、shutdown、helper 与 cgroup 测试路径在各切片落地时再加入本节；不存在的 `tests/smoke/test_systemd_socket_activation.py` 与 `tests/unit/test_cgroup_observability.py` 不作为 current M1 已通过命令。optional user-scope probe 必须由测试 harness 创建临时状态并自动清理；不允许手工 `systemctl --user` 改变真实用户 manager 来补证据。

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

### 为测试安装 user unit

未采纳。安装与 manager 持久变更超出当前验证边界，也会污染用户环境。测试使用临时 harness、fake tree 与可自动销毁 scope。

### 通过制造 OOM 验证 `MemoryMax`

未采纳。它会给共享开发机造成不可接受风险。使用 effective file 对账、safe pressure threshold 与 fake `memory.events`；真实 OOM 行为只在专用隔离环境另行执行。

### 在单实例模板上直接叠加 templated services 实现 rolling

未采纳。单 socket 的 service 归属、readiness 切流和共享状态并发都未冻结。S7 先做拓扑与状态隔离设计，再写实现。

## 9. 结构怪味与处置

| 位置 | 怪味 | 处置 |
|---|---|---|
| `src/app/shutdown.py` 与 `src/app/server.py` | 设计类存在但生产 lifespan 未消费，容易把“类已实现”误写成“四阶段运行态已接线” | S3 本轮核对真实 signal／lifespan 调用图；未接线前文档明确降级，不以 helper 存在证明支持 |
| `contrib/systemd/ghc-api-proxy.service` 候选 | `330s` 与应用 runtime timeout 非同源常量 | S3 建立单一时间模型与机械对账 |
| `tests/smoke/test_systemd_units.py` 候选 | 静态 unit tripwire、真实 writer 权限与 inherited-fd／upstream smoke 同文件，且 direct harness 尚不能证明 manager-level activation／service-gap | M1 保留 code R4 已复核并在 `fe9c203…` 再次通过的可移植纵向 smoke；回并后把 activation、listener-owner continuity 与 accepted-drain probe 按能力边界拆分 |
| `contrib/systemd/ghc-api-proxy.service` 的 EnvironmentFile | 兼容配置与 secret 传递边界混在同一机制，文件 mode 不能消除环境经 D-Bus／进程树暴露的风险 | 记录 code R4 non-blocking minor；回并后优先评估 systemd credentials 与现有 token-file 接线，不反向阻塞 M1 |
| system 与未来 user units | 若复制两份全文，路径、targets、账户字段和 limits 会漂移 | S4 使用共享 typed render inputs 与两套明确模板合同；避免脆弱字符串替换 |
| cgroup 声明与 metrics | unit 配置和应用观测分属两处，可能一边改 limits、一边继续解释旧阈值 | S5 把 declared／effective／runtime 三层写入同一测试矩阵和部署文档 |

## 10. 每轮反思门

每个切片结束后把以下三项的实际结论写回本节或对应阶段，不能只写“当前方案最佳”：

1. **内部替代方案**：是否可用 Uvicorn 已有 fd／shutdown 能力、systemd 原生 unit 语义或现有 telemetry setup，避免重复造 lifecycle owner。
2. **判据判别力**：静态 verify、执行 smoke、continuity probe 与 timeout test 是否分别能让目标缺陷变红，也是否允许正确的无 systemd CI 环境以明确 unsupported／skip 通过。
3. **成熟方案**：user unit 渲染、cgroup metrics 读取和 socket activation harness 是否已有维护良好的库／systemd 工具可复用；采用前核对当前版本文档与项目兼容性，不凭记忆锁版本。

发现更优方案但本轮不切换时，记录到第 8 节并说明前置条件；不得静默丢弃。

## 11. 实施 kick-off

在 `feat/systemd-cgroup-runtime` 候选 worktree 与 `integrate/260807-systemd-runtime` integration worktree 继续本计划。候选代码 base 为 `ed77c9d191df81c451c25161420515cca52ce6a4`，current candidate 为 `49fb1988621bba4356e7a5039a6994c2e6d19604`，已准备的 integration squash 为 `fe9c20315b0137ca5b2253fdbd86a30d504255ef`；主树每次 shell 都以当次 `main` current 为门，不把本文件记录的点时 HEAD 当作永久 expected。每次 shell 都在同一次调用内验证物理 root、分支、current HEAD 和所用候选／integration exact HEAD，不依赖前一调用的 cwd；记录开始／结束 status，只提交当前语义切片的精确 pathspec。

先消费两份初始 systemd reports、code R2～R4 与 Plan R2～R4。已确认 `49fb198…` 的 `Type=exec`、`KillMode=control-group`、StateDirectory＋显式 History／tokenization 路径、`--fd >= 1`、`StateDirectoryMode=0700`、`UMask=0077`、覆盖目录文档、真实 writer 权限回归，以及无 HOME 的 inherited-fd／backlog／readiness／真实请求／History＋tokenization smoke；code R4 为 0 blocker／0 major、明确三提交可 squash。保持 `/health/readiness` 为独立 oracle；不得把 `Type=exec` 写成应用 ready。

Plan R4 已落盘并指出唯一状态同步 major；本次修订已消费其实际 verdict 与精确清单，Plan living 可继续。三候选提交已 squash 为 clean integration `fe9c203…`，且该 exact HEAD 上的全仓 pytest 301 项、Ruff、Pyright 与 fd smoke 已通过。下一动作不是等待更多代码或强化：先清理主树 `docs/agents/anthropic-responses-bridge/README.md` 与 `implementation.md` 的 WIP／提交边界，再重新读取 `main` current、回放 `fe9c203…`、运行 main-side M1 gates并回并；不要等待 graceful timeout、install helper、完整 continuity、cgroup observability 或 rolling。

M1 回并后再按独立切片继续强化：先分开 `systemd-socket-activate` happy path 与父进程自持 listener 的 service-gap probe，并单独验证旧 accepted connections 的 drain／timeout／不迁移；S3 从 Uvicorn、signal handler、FastAPI lifespan 与 cleanup 真实调用链重建 shutdown 时间模型；S4 实现 rootless user install helper，默认固定 dry-run，只有显式 install 才写临时测试目录，绝不自动 reload／enable／start；S5 先实现 cgroup v2 typed reader 与 fake-tree，再经观测 API 评审接入 declared／effective／runtime 三层 metrics。每片独立提交、验证、评审和回并，不攒成一个大候选。

始终区分 listener continuity、queued／unaccepted connections 与旧进程 accepted connections；单实例 socket activation 不得称为双实例／rolling 或 accepted connection zero-downtime。双实例／rolling 留到 S7，先冻结稳定 listener／proxy 拓扑、readiness 切流、状态隔离、drain 与回滚，再实施。

完成每个切片后立即更新本文件的状态看板、实际 HEAD、测试证据、评审 verdict、结构怪味和下一动作。任何仓库内 gate 全绿都不等于已部署；系统安装、运行态替换和发布由用户另行明确发起。
