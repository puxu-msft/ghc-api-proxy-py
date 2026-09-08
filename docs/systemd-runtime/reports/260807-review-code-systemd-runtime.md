# systemd cgroup runtime 独立代码／部署评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-systemd` 分支 `feat/systemd-cgroup-runtime`、HEAD `66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff` 相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的最终合并态。覆盖 CLI `--fd`、socket／service／slice units、部署文档、单元与 smoke 测试，以及 Uvicorn 0.40.0 和 systemd 255 的真实运行语义。
- **总体 verdict**：**修复 major 后可进入**。socket activation 主路径可用，fd 3、listen backlog、后续连接和 SIGTERM lifespan 清理均已实跑成立；但模板没有为默认启用的 History 提供确定可写的状态目录，常见无 home 的 system account 会在应用 startup 阶段直接失败。因此当前不可 squash；关闭 major 并复验后才可 squash。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：2。
- **双视角覆盖证据——机械核对**：逐行对账 `src/app/cli.py`、三个 systemd unit、部署 README 与新增测试；检查 `fd=3`、`LISTEN_FDS` 固定起点、`Accept=no`、host／port 排他、`TimeoutStopSec`、`EnvironmentFile`、slice controls 和文档保证；读取已安装 Uvicorn 0.40.0 的 `Config.bind_socket()` 与 signal capture 源码；读取 systemd 255 的 `Type=`、`KillMode=`、clean signal 和 `Restart=on-failure` 语义；用 `systemd-analyze verify` 解析 unit，其中原模板只因本机不存在目标部署路径 `/opt/ghc-api-proxy/.venv/bin/python` 报错，在 `/tmp` 副本仅把 `ExecStart` 替换为 `/bin/true` 后其余 unit 配置通过；隔离快照中定向 pytest 为 `12 passed`，Ruff 通过，Pyright 为 `0 errors, 0 warnings, 0 informations`，并确认目标 worktree 始终干净。
- **双视角覆盖证据——第一人称执行**：模拟管理员按文档创建典型无 home 的 system account 后启动 service，复现默认 History 在 `/nonexistent/.local/share/ghc-api-proxy/history.db` 建目录时 `PermissionError`，进程以非零状态退出；再在隔离提交快照中由父进程创建真实 TCP listener 作为 fd 3，先于应用启动建立 backlog 连接，再运行真实 `python -m app start --fd 3`，backlog 请求和启动后新连接均获得 `/health/liveness` 的 HTTP 200，SIGTERM 后日志依次出现 shutdown、lifespan cleanup 和 finished server；同时模拟 `--fd 0`、显式 host／port 冲突、socket 地址修改、service-only restart、超时强杀和可选 EnvironmentFile 缺失分支。

## 事实性发现

[major] `contrib/systemd/ghc-api-proxy.service:7-18`、`docs/agents/deployment-systemd/README.md:43-48` — 模板没有建立确定可写的应用状态目录，但应用默认启用 History，常见 system account 会在 startup 直接失败 — `HistoryConfig.enabled` 在 `src/app/config/settings.py:45-51` 默认为 `True`；lifespan 在 `src/app/server.py:63-81` 使用 `user_data_path()/history.db`，`HistoryWriter.start()` 在 `src/app/history/sqlite/writer.py:32-34` 同步创建父目录。以 `HOME=/nonexistent` 且不设置 XDG 变量运行候选真实 fd 3 入口时，默认数据路径解析为 `/nonexistent/.local/share/ghc-api-proxy`，随后抛出 `PermissionError: [Errno 13] Permission denied: '/nonexistent'`，Uvicorn 报 `Application startup failed` 并以非零状态退出。文档只要求“确保服务账户能……写入项目所需的数据目录”，却没有指出实际路径，也没有让 unit 创建它，因而执行者无法按模板获得可复现的可启动部署 — 建议在 service 中使用 `StateDirectory=ghc-api-proxy`，并在 unit 的 `Environment=` 或环境文件中把 `GHC_HISTORY__DB_PATH` 与 `GHC_TOKENIZATION__STATE_PATH` 明确指向 `/var/lib/ghc-api-proxy/history.db` 与 `/var/lib/ghc-api-proxy/tokenization.json`；或者由安装步骤创建并授权另一个固定目录。增加一个无可写 home 的真实 startup smoke，要求 readiness 成功且状态文件落在预期目录。

[minor] `src/app/cli.py:53`、`src/app/cli.py:111-114` — CLI 接受 `--fd 0`，但 Uvicorn 0.40.0 不会把 0 当继承 socket — Typer 声明使用 `min=0`，而该版本 `Config.bind_socket()` 的分支是 `elif self.fd:`。独立探针显示 `fd=3` 调用 `socket.fromfd`，`fd=0` 则进入新建 socket 分支并尝试默认 `127.0.0.1:8000`；这与 CLI 表面合同不一致，也可能让误配悄悄监听错误端口 — 将 CLI 下界改为 1，并补 `--fd 0` 拒绝测试。systemd 主路径固定 fd 3，不受此边界影响。

[minor] `contrib/systemd/ghc-api-proxy.service:9`、`tests/smoke/test_systemd_units.py:21` — `Type=simple` 会在 `execve()` 前就把 service 视为 started，弱化了模板对部署路径、用户和可执行文件错误的即时报告 — systemd 255 手册明确推荐长驻服务使用 `Type=exec`，以便追踪 process setup、missing user 与 missing executable 等失败。这里不是 major：socket backlog 仍由 `.socket` 持有，文档也明确要求用 readiness endpoint 而不是进程状态判断应用就绪；`Type=exec` 同样不会等待 FastAPI startup 完成。因此问题是启动状态可观测性较弱，而不是 socket activation 或 readiness 合同失效 — 改为 `Type=exec`，同步测试与文档；继续保留 `/health/readiness` 作为唯一应用就绪判据，勿把 `Type=exec` 描述成 readiness。

## 已核对且不构成 major 的争议项

- `contrib/systemd/ghc-api-proxy.service:18` 的 `KillMode=mixed` **不是 major**。当前入口是单 Uvicorn 主进程，仓库扫描未发现 workers／reload／multiprocessing 子进程；stop 时主进程收到 SIGTERM 并完成 Uvicorn 与 FastAPI lifespan cleanup，超时后 cgroup 剩余进程仍会被 SIGKILL 清理。它与默认 `control-group` 在当前主进程路径上的用户可观察结果一致。
- `contrib/systemd/ghc-api-proxy.service:19` 的 `TimeoutStopSec=330s` 与项目默认 300 秒 upstream／stream idle 边界有 30 秒余量，但不保证所有 accepted HTTP／SSE／WebSocket 连接自然结束。部署文档已准确说明 330 秒后会中断剩余连接，没有冒充 zero-downtime。
- `contrib/systemd/ghc-api-proxy.socket:4-9` 与 `ExecStart=... --fd 3` 的接线成立。systemd 的 socket activation 描述符从 3 起排布，该 service 只有一个 activation socket；Uvicorn 0.40.0 对 fd 3 直接使用 `socket.fromfd`。`Accept=no` 也与单 service 接收共享 listener 相符。
- 文档对 backlog 的保证是准确的：实测应用启动前已经 connect 并发送请求的连接在 Uvicorn 接管 fd 3 后得到 HTTP 200；文档同时明确 accepted connection 不会迁移、新旧实例不重叠、backlog 有限，没有把 listener 保留夸大成连接无损迁移。
- `EnvironmentFile=-/etc/ghc-api-proxy/ghc-api-proxy.env` 的可选文件语义与文档一致，示例 `GHC_CONFIG` 和 `GHC_OBSERVABILITY__LOG_LEVEL` 也符合项目 `GHC_` 前缀与 `__` 嵌套分隔符。major 所指的是默认状态目录未被该示例或 unit 闭合，不是 EnvironmentFile 语法错误。
- `.slice` 中 `MemoryHigh=1G`、`MemoryMax=2G`、`CPUQuota=200%` 与 `TasksMax=256` 均为有效 cgroup v2 controls，文档也要求部署前按主机容量调整；未发现把软阈值、硬上限或 OOM 恢复语义写反。

## 主观建议

[建议] `contrib/systemd/ghc-api-proxy.service:18` — 将 `KillMode=mixed` 改回默认的 `control-group` — 预期影响是未来若引入协作子进程，所有 cgroup 成员会一起收到 SIGTERM，获得相同的 graceful shutdown 窗口，而不是子进程只在超时后收到 SIGKILL — 推荐删除显式 `KillMode` 或写成 `KillMode=control-group`，并把测试从固定某个非默认值改为验证“停止时整个 cgroup 先收到 graceful signal，超时后不留残进程”的行为合同。若未来确实需要主进程独占 SIGTERM，再以具体子进程协议说明为何选择 `mixed`。

[建议] `tests/smoke/test_systemd_units.py:14-38` — 当前测试主要把 `Type=simple`、`KillMode=mixed` 和若干常量自证为期望值，没有覆盖真实启动失败、状态目录、backlog 接管与 graceful stop 接缝 — 预期影响是配置文字全绿但目标机不可启动的 false-green — 推荐保留快速静态测试，同时新增 `/tmp` 隔离的无 root 集成 smoke：父进程创建 fd 3、无可写 home 启动 service command、读取 readiness、发送 SIGTERM、验证 cleanup 与状态目录；`systemd-analyze verify` 则使用安装后路径或受控替代路径验证完整 unit。

## 结构怪味扫描与处置

- `contrib/systemd/ghc-api-proxy.service:7-18` — **部署资源所有权缺口** — unit 管理进程与 cgroup，却把持久化目录隐式交给服务账户 home；本轮列为 major，要求在 unit 或确定配置中闭合。
- `src/app/cli.py:53` 对比 Uvicorn 0.40.0 `Config.bind_socket()` — **包装层合同比依赖更宽** — CLI 接受依赖不会按同义解释的 fd 0；本轮列为 minor，收紧边界。
- `tests/smoke/test_systemd_units.py:14-38` — **实现常量与测试 oracle 同源** — 测试能抓字段被改，却不能证明这些字段能启动真实应用；本轮不改代码，建议增加跨层 smoke。
- 扫描范围还包括 CLI→Uvicorn、socket→service→slice、EnvironmentFile→Pydantic Settings、SIGTERM→Uvicorn→FastAPI lifespan，以及文档→真实行为。除上述三处外，未发现重复实现、职责错位、抽象泄漏或可由成熟第三方机制替代而自行重造的部署逻辑；socket activation 和 cgroup 均直接使用 systemd／Uvicorn 现成机制。

## 方案反思

1. **更好的内部替代方案**：状态目录应由 systemd `StateDirectory=` 管理并由应用配置显式消费；相较依赖服务账户 home，这能把创建、所有权和生命周期放回部署编排层。`Type=exec` 优于 `simple`，但仍不能替代 readiness。
2. **判据判别力**：现有静态测试无法区分“unit 字段齐全但应用因目录不可写而失败”。本轮用真实 fd 3 HTTP smoke 作为正确样本，并用 `HOME=/nonexistent` 作为目标缺陷样本，分别得到启动成功与 startup failure；`fd=3`／`fd=0` 也用 Uvicorn 分支探针验证一绿一红。尚未在真实 PID 1 manager 中安装 unit，因此 cgroup controller 的运行时施加只由 `systemd-analyze verify`、有效字段语义和 unit 接线共同支持，不能冒充已做 root 级部署验收。
3. **成熟第三方方案**：无需新增库。systemd 的 `StateDirectory=`、socket activation、slice resource controls 与 `Type=exec` 已覆盖所需机制；CLI 继续使用 Uvicorn 原生 `fd` API 即可。

## 收口条件

1. 为 History 与 tokenization 提供确定可写、由 unit 或明确安装步骤创建并授权的状态目录。
2. 新增无可写 home 的 startup／readiness smoke，证明默认模板可启动且状态落盘位置正确。
3. 拒绝 `--fd 0` 并补回归测试。
4. 将 `Type=simple` 改为 `Type=exec`，同步测试和文档，但继续明确它不等于 readiness。
5. `KillMode=mixed` 可独立改为 `control-group`；该项不是关闭 major 的必要条件，但推荐在 squash 前一并整理。
6. 重跑定向 pytest、Ruff、Pyright、`systemd-analyze verify` 和真实 fd 3 backlog／SIGTERM smoke。达到 `0 major` 后可 squash。
