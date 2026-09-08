# 当前 Claude 入口服务与可回滚 cutover 清单

## 结论

截至 `2026-08-07T07:02:27Z`，Claude 本机入口 `localhost:4141` 仍由 `/home/xp/src/copilot-api-js` 中的裸 Bun 进程提供，而不是由独立 systemd unit 托管。监听进程为 PID `1271974`，同时绑定 `127.0.0.1:4141` 与 `[::1]:4141`，命令行为 `/home/xp/.local/volta/tools/image/packages/bun/bin/bun run ./packages/cli/src/main.ts start --restart`，工作目录为 `/home/xp/src/copilot-api-js`，cgroup 为 `/init.scope`。同一时点 `VmRSS=4473036 kB`，约 `4.27 GiB`；`VmHWM=6145880 kB`，约 `5.86 GiB`。

当前状态**不具备可直接声称的零停机、原子切换或已验证回滚能力**。执行 cutover 前必须先把候选实例、端口所有权、完整启动输入、SQLite 一致性备份、数据格式兼容性、验收门与回滚门准备成可机械执行的方案。`cc-daemon.service` 是另一套活跃 user service，并持有 Claude 会话资源；它不属于 4141 服务的切换范围，禁止把重启或停止它当成 4141 cutover 步骤。

## 复核范围与证据边界

- 仓库基线：每次用于本报告的有效 shell 采集都在同一次调用内验证物理根目录与当前目录均为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。
- 动态证据：使用只读的 `ss`、`/proc`、cgroup、`systemctl`、`systemctl --user`、进程枚举和文件元数据查询。未执行服务修改、进程信号、网络请求、配置写入、数据复制或数据库事务。
- 时间口径：监听、PID、RSS、父进程、cgroup、systemd 与打开文件属于瞬时快照，主要锚定 `2026-08-07T07:02:27Z`；cutover 前必须重新采集，不得把本文 PID 当成永久身份。
- 本轮没有向 `localhost:4141` 发应用层探测，因此只证明 socket 正在监听，不证明 readiness、认证、上游连通性、请求语义或端到端健康。
- 用户提供的既有调查事实“重启 `cc-daemon` 会杀活会话”本轮未以破坏性操作复测；本轮只读证据确认该 unit 活跃并存在 player、shim、`bg-pty-host` 与 `bg-spare` 会话相关进程，足以把“不触碰 `cc-daemon`”设为 cutover 硬边界。

## 当前运行清单

| 项目 | 当前事实 |
|---|---|
| 客户端入口 | `localhost:4141`；内核监听实际为 `127.0.0.1:4141` 与 `[::1]:4141`，未观察到非 loopback bind |
| socket owner | 单一 PID `1271974`，进程名 `bun`，监听 fd 分别为 `22` 与 `23` |
| 启动命令 | `/home/xp/.local/volta/tools/image/packages/bun/bin/bun run ./packages/cli/src/main.ts start --restart` |
| executable | `/home/xp/.local/volta/tools/image/packages/bun/lib/node_modules/bun/bin/bun.exe` |
| 工作目录 | `/home/xp/src/copilot-api-js` |
| 父进程 | PID `1271972`，命令 `bun run ./packages/cli/src/main.ts start --restart`；父子二者均位于 `/init.scope` |
| 进程启动时间 | `2026-08-07T06:04:30.710000+00:00`，由 `/proc` boot time 与进程 start ticks 推导 |
| 当前内存 | `VmRSS=4473036 kB`，约 `4.27 GiB`；`VmHWM=6145880 kB`，约 `5.86 GiB`；`24` threads |
| cgroup／托管归属 | `0::/init.scope`；这证明当前监听进程不在 `cc-daemon.service` 或已知 copilot service cgroup 内 |
| PID 文件 | `~/.local/share/copilot-api/copilot-api.pid` 是 JSON，观测到字段 `pid=1271974`、`port=4141`、`bootTime=1786082672388`；PID 与端口同当前监听者相符。不得把该文件当作 supervisor 或进程存活证明 |
| systemd 扫描 | system scope 的 loaded／installed unit 清单未命中 `copilot-api`、`copilot.*4141` 或 `cc-daemon`；user scope 只命中 `cc-daemon.service` 与 `cc-daemon-calib.service`。已知名称 `copilot-api.service`、`copilot-api-js.service`、`copilot-api-proxy.service` 在 system／user scope 均为 `not-found` |

“没有独立 systemd unit”的精确含义是：当前 4141 owner 位于 `/init.scope`，且 system／user unit 清单及已知服务名扫描没有建立其与 unit 的关联。本文不声称已穷举所有可能使用无关名称的 unit 文件。

## `cc-daemon` 隔离边界

`cc-daemon.service` 当前为 user unit，`loaded / active / running / enabled`，MainPID 为 `1669096`，命令为 `python3 -m ccd.daemon`，自 `2026-08-03 12:51:17 UTC` 启动后 `NRestarts=0`。其 unit 文件位于 `/home/xp/.config/systemd/user/cc-daemon.service`，cgroup 为 `/user.slice/user-1000.slice/user@1000.service/app.slice/cc-daemon.service`。这与 4141 owner 的 `/init.scope` 是两个独立资源域。

只读枚举同时观察到 daemon 的 player，以及多个使用 `/tmp/cc-daemon-1000/...` socket 的 Claude `bg-pty-host`／`bg-spare` 进程。由此得到 cutover 不变量：

- 不停止、不重启、不 reload `cc-daemon.service` 或 `cc-daemon-calib.service`。
- 不向 daemon、player、shim、Claude host／spare 进程发送信号。
- 不清理 `/run/user/1000/cc-daemon`、`/tmp/cc-daemon-1000` 或相关 socket。
- 4141 切换的进程发现与终止范围必须按精确 PID、start time、socket owner 和 cgroup 四项共同限定，不能使用宽泛的 `pkill bun`、`pkill claude` 或服务名模糊匹配。

## 环境变量名清单

本轮只读取并记录变量名，没有记录任何值。PID `1271974` 的环境变量名为：

`ARTIFACTS_CREDENTIALPROVIDER_MSAL_ALLOW_BROKER`、`BUN_INSTALL`、`CARGO_HOME`、`CONDA_DEFAULT_ENV`、`CONDA_EXE`、`CONDA_PREFIX`、`CONDA_PROMPT_MODIFIER`、`CONDA_PYTHON_EXE`、`CONDA_ROOT`、`CONDA_SHLVL`、`DBUS_SESSION_BUS_ADDRESS`、`DEBUGINFOD_URLS`、`DISPLAY`、`DOTMY`、`DOTMY_ENV_LOADED`、`DOTMY_PROFILE`、`DOTNET_ADD_GLOBAL_TOOLS_TO_PATH`、`DOTNET_BUNDLE_EXTRACT_BASE_DIR`、`DOTNET_CLI_TELEMETRY_OPTOUT`、`DOTNET_CLI_UI_LANGUAGE`、`DOTNET_NOLOGO`、`GCC_COLORS`、`HOME`、`HOMEBREW_CELLAR`、`HOMEBREW_PREFIX`、`HOMEBREW_REPOSITORY`、`HOSTTYPE`、`INFOPATH`、`IS_LINUX`、`IS_WSL`、`LANG`、`LC_ALL`、`LESSCLOSE`、`LESSOPEN`、`LOGNAME`、`LS_COLORS`、`MANPATH`、`MANPATH_OLD`、`NAME`、`NODE`、`NODE_ENV`、`NODE_PATH`、`NUGET_CREDENTIALPROVIDER_FORCE_CANSHOWDIALOG_TO`、`NUGET_CREDENTIALPROVIDER_MSAL_ALLOW_BROKER`、`NUGET_NETCORE_PLUGIN_PATHS`、`OLDPWD`、`OPENCODE_HOME`、`PAGER`、`PATH`、`PATH_OLD`、`PNPM_HOME`、`PULSE_SERVER`、`PWD`、`RUSTUP_HOME`、`SHELL`、`SHLVL`、`SHRC_DIR`、`SSH_AUTH_SOCK`、`TERM`、`USER`、`VOLTA_HOME`、`WAYLAND_DISPLAY`、`WSL2_GUI_APPS_ENABLED`、`WSLENV`、`WSL_DISTRO_NAME`、`WSL_INTEROP`、`WT_PROFILE_ID`、`WT_SESSION`、`XDG_DATA_DIRS`、`XDG_RUNTIME_DIR`、`_`、`_CE_CONDA`、`_CE_M`、`_CONDA_EXE`、`_CONDA_ROOT`、`_VOLTA_TOOL_RECURSION`、`npm_command`、`npm_config_local_prefix`、`npm_config_user_agent`、`npm_execpath`、`npm_lifecycle_event`、`npm_lifecycle_script`、`npm_node_execpath`、`npm_package_json`、`npm_package_name`、`npm_package_version`。

Cutover 前应从 `/proc/<current-pid>/environ` 重新生成变量名清单，而不是依赖本文快照。环境值可能包含凭证、socket、路径和行为开关，不能写入普通报告或命令历史；但若没有受控、权限收紧且可销毁的值快照，就不能声称新进程与旧进程启动输入等价。

## 数据目录与运行中占用

权威运行数据根为 `~/.local/share/copilot-api`，即 `/home/xp/.local/share/copilot-api`。目录当前为用户 `xp:xp` 所有、mode `0755`。顶层观察到以下类别：

- 配置与身份材料：`config.yaml`、`github_token`、`learned-limits.json`、`negotiation-states.json`、`request-telemetry.json`、`system-prompts/`。报告只记录路径名，不读取或披露内容。
- 运行日志：`copilot-api.log` 及轮转文件、`logs/`。
- 进程标识：`copilot-api.pid`。
- History：`history-v3.db` 及 `-wal`／`-shm`、其他历史版本与归档数据库、`history-search/`。
- 其他 SQLite 状态：`archive.db` 及 WAL／SHM、`telemetry.db`、`thinking-quarantine.db`。

PID `1271974` 在复核时直接打开了 `history-v3.db`、`history-v3.db-wal` 与 `history-v3.db-shm`。因此：

- 运行中直接复制单个 `.db` 文件不能作为一致性备份，也不能把仅复制主文件称为可回滚快照。
- 必须在切换方案中选定并验证一种一致性方式：SQLite online backup／等价一致性快照，或在确认 writer 已完全停止、fd 已关闭后复制完整所需文件集合。
- 候选版本若会迁移 schema、重写状态格式或更新配置，必须先证明旧版本可读取新状态；否则 rollback 必须绑定切换前的一致性数据快照，并明确恢复会舍弃哪些切换后写入。
- 数据根、owner、mode、敏感文件权限和磁盘余量都要在 cutover 前后复验；不得让新 unit 或新用户隐式改写所有权。

## 切换不变量

1. **入口不变量：** 客户端仍通过 loopback `localhost:4141` 访问；若 IPv4 与 IPv6 loopback 都属于现有合同，新实例必须同时保持 `127.0.0.1:4141` 与 `[::1]:4141`，不能只验证其中一个。
2. **单 owner 不变量：** 任一时点不得出现两个未经设计的 4141 listener。当前未观察到 socket activation、继承 fd、`SO_REUSEPORT` 协调或前置代理，因此不能假设新旧进程可无冲突重叠绑定。
3. **身份不变量：** 操作对象由 PID＋start time＋cmdline＋cwd＋cgroup＋socket owner 联合确认；PID 文件只作辅助，不能单独授权信号或终止。
4. **启动输入不变量：** 固定候选代码 revision、Bun 可执行文件、工作目录、argv、配置文件、数据根和实际所需环境值。仅有变量名清单不足以复现现状。
5. **数据不变量：** History、telemetry、archive、quarantine、negotiation 与 token／config 的 ownership 和格式必须有明确 producer／consumer；迁移、写入 fencing、备份与恢复顺序不能靠“同目录所以兼容”推断。
6. **会话隔离不变量：** `cc-daemon` 与其 player／Claude 会话树保持运行，相关 cgroup 和 socket 不被 cutover 触碰。
7. **验收不变量：** socket bind 只是第一层。候选必须在正式接管前通过独立端口或隔离环境的 liveness、readiness、认证、上游调用、Claude 协议关键路径、History 写读与资源基线验收。
8. **失败闭环不变量：** 每个不可逆动作之前都已有可执行的回滚动作与机械 abort 条件；切换中发现 PID 漂移、端口 owner 异常、数据 writer 未收敛、schema 不兼容或 `cc-daemon` 状态变化时立即停止，不自行扩大操作范围。

## 不可声称边界

基于本轮只读证据，当前不得声称：

- 4141 服务由 systemd 监督、会自动拉起、具备 watchdog、readiness gate 或声明式环境恢复。
- `--restart` 参数等价于 systemd restart policy，或证明进程崩溃后会恢复。
- 当前监听即应用健康、Claude 请求可用、上游认证有效或数据路径无错误。
- 可以在同一 4141 端口零停机重叠启动，或切换动作对客户端原子可见。
- 停止旧进程后，新进程一定能用相同环境、配置和数据启动。
- WAL 文件存在就代表数据已 durable、一致或可由旧版本读取。
- 当前 `VmRSS` 是稳定容量需求；它只是一个瞬时样本，capacity 需要时间序列与峰值口径。
- PID `1271974`、fd、thread 数、RSS、父进程或 `cc-daemon` PID 在未来仍不变。
- `cc-daemon` 重启不会影响会话；既有调查结论恰好相反，本轮也未授权破坏性复测。
- rollback 已演练、schema backward-compatible、切换后新增写入可无损回退，或恢复时间目标已经满足。

## 可回滚 cutover 前置门

只有以下各项全部有证据后，才具备进入实际 cutover 的前置条件；本文不授权执行这些动作：

- [ ] **冻结候选：** 记录候选代码 commit、依赖锁、Bun 版本／绝对路径、启动 argv、cwd、配置 digest 和预期数据 schema；在隔离环境证明实际导入／执行的是该候选，而不是共享依赖或另一 worktree。
- [ ] **准备受控 launcher：** 明确由哪个 supervisor 持有进程、stdout／stderr、restart policy、cgroup、resource limits 和 stop timeout。若采用 systemd，先在非 4141 端口验证 unit 的实际 `ExecStart`、`WorkingDirectory`、`EnvironmentFile` 权限、启动／失败／重启语义；不得在切换时顺手把 `cc-daemon` 纳入同一 unit。
- [ ] **安全捕获启动输入：** 在权限收紧、不会进入仓库或普通日志的介质中保存旧实例所需环境值与敏感文件引用；报告和评审材料只保留变量名与 digest。验证候选没有依赖旧 shell 的隐式 `PATH`、Volta、Conda 或 session bus 状态。
- [ ] **候选旁路验收：** 在独立 loopback 端口、独立 PID 文件及不会写生产数据的隔离数据根启动候选，完成应用层与 Claude 关键路径验收；确保测试不会与生产 writer 竞争同一 SQLite／WAL。
- [ ] **定义端口接管模型：** 在“维护窗口内先停旧后启新”“预先部署稳定前置代理／socket owner”或经 PoC 证明的 fd handoff 中明确选择一种。当前事实只支持把维护窗口视为保守默认，不能假装已有原子交换能力。
- [ ] **建立写入 fence：** 列出所有会写 `~/.local/share/copilot-api` 的进程和后台 worker，规定何时停止接纳新请求、何时确认 in-flight 收敛、何时确认数据库 fd／事务达到可备份状态。不能只停监听者而忽略独立 writer。
- [ ] **生成并验证一致性备份：** 使用 SQLite online backup／经验证的文件系统快照，或在 writer 完全关闭后复制所需状态；对备份执行打开、integrity、关键查询和恢复演练。备份位置、权限、容量与保留期限必须明确。
- [ ] **冻结兼容矩阵：** 逐项确认候选对 config、History、archive、telemetry、quarantine、negotiation 和 PID 文件的读写兼容性，并确认旧版本对切换后状态的兼容性。任何单向迁移都必须把“恢复切换前快照并丢弃切换后写入”写成显式代价。
- [ ] **准备旧实例重启件：** 保留旧代码 revision、旧 Bun executable／依赖、旧 argv、cwd、受控环境值和旧数据快照；在隔离端口演练从这些材料启动，而不是仅保存一条历史命令。
- [ ] **定义机械验收门：** 至少覆盖 IPv4／IPv6 bind、单一 socket owner、目标 cgroup／unit、应用 readiness、Claude 协议请求、认证／上游、History 写读、日志错误、RSS／fd／task 增长和 `cc-daemon` 连续存活。每项给出明确通过值与观察窗口。
- [ ] **定义机械 rollback 门：** 启动失败、端口未接管、应用 gate 失败、错误率越界、数据写入失败、schema 不兼容、资源失控、`cc-daemon` 或活会话状态异常时立即回滚；禁止边观察边临时发明阈值。
- [ ] **定义回滚顺序：** 停止新 admission，收敛／终止候选 writer，保存诊断，按兼容矩阵决定保留新数据还是恢复一致性旧快照，确认 4141 无 owner，再用冻结的旧启动件恢复，最后执行同一套验收门。任何信号前重新核对 PID＋start time＋cgroup＋socket owner。
- [ ] **cutover 前最后复核：** 在实际动作所在 shell 中重新 gate 目标仓库／commit，并重新采集 `ss`、`/proc`、cgroup、systemd、打开数据库 fd、磁盘空间与 `cc-daemon` 活状态。本文快照只用于设计，不是执行授权。

## 本轮处置与结构观察

本轮唯一写入是本报告文件。没有修改服务、配置、数据目录、systemd、进程或 socket，也没有发送信号。

结构怪味：当前 4141 服务由交互环境衍生的 `/init.scope` 裸进程持有，启动输入依赖 shell／Volta／Conda 环境，而 PID 文件、数据 writer 与服务监督没有统一 owner。这使“服务身份”“重启语义”“环境重放”“数据库 quiesce”和“回滚”分散在不同机制中。长期修复方向是为 4141 服务建立独立 supervisor／cgroup 和显式 secret／environment 注入，同时让 SQLite backup／migration、readiness 与 rollback gate 成为该服务自己的运维合同；不得通过复用或重启 `cc-daemon` 来解决。
