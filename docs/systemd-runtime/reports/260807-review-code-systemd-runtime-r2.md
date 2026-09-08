# systemd cgroup runtime 定向复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-systemd` 分支 `feat/systemd-cgroup-runtime`、HEAD `1a220e04a99c6ce07b4bdd6bb0876b4180d4c489` 相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的最终合并态。定向复核上一轮 `docs/tmp/260807-review-code-systemd-runtime.md` 与 `docs/tmp/260807-systemd-socket-feasibility.md` 的状态目录、fd 下界、`Type=`、`KillMode=`、运行态 smoke、文档和测试发现；未安装、启动、停止或 reload 任何 unit，未操作生产 `4141` listener。
- **总体 verdict**：**修复 major 后可进入**。前序两项 major 与三项去重后的 minor 的目标行为均已在最终实现中关闭，但状态目录修复引入／暴露了新的文件权限 major：system systemd unit 默认 `UMask=0022`、`StateDirectoryMode=0755`，候选真实 writer 因而创建 world-readable 的 History 与 tokenization 文件。当前 **不可 squash**；关闭该 major 并复验后，若仍为 `0 blocker／0 major`，即可 squash。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：1。该项是非阻断测试覆盖缺口。
- **双视角覆盖证据——机械核对**：逐行对账最终 service／socket／slice、CLI、部署 README、unit 与 smoke 测试；逐项映射前序状态目录、`fd=0`、`Type=simple`、`KillMode=mixed` 发现；扫描旧合同残留；读取配置加载、History startup、tokenization flush、readiness 条件和本机 systemd 255 语义；用目标树 import oracle 确认 `app` 与 `app.cli` 均从候选 worktree 加载；运行原始模板 `systemd-analyze verify`，唯一解析诊断是安装前约定路径 `/opt/ghc-api-proxy/.venv/bin/python` 尚不存在，没有 unit 语法、依赖、`StateDirectory=`、`Type=` 或 `KillMode=` 诊断；另核对 systemd 255 明确规定 system unit 默认 `UMask=0022`、`StateDirectoryMode=0755`，并用候选真实 `HistoryWriter` 与 `TokenizationStateStore` 交叉探测出目录 `0755`、两文件 `0644`；定向 pytest／Ruff／Pyright与全仓 pytest／Ruff／Pyright均以 0 退出，`git diff --check` 通过，候选树验证前后 clean。
- **双视角覆盖证据——第一人称执行**：模拟管理员采用默认 `/var/lib/ghc-api-proxy` 状态目录、通过 EnvironmentFile 覆盖到其他目录、无可写 HOME、fd 3 backlog、liveness／readiness、SIGTERM、未来主进程＋协作子进程、缺失解释器和日常仅重启 service 等路径；执行最终 smoke 的真实 listener／预连接 backlog／无可写 HOME／History 落盘／SIGTERM lifespan 路径；另省略两条显式状态路径运行负样本，仍在 `/nonexistent` 处触发原 `PermissionError`，证明新增正向路径确实覆盖了上一轮 major，而不是无关测试全绿。

## 前序发现关闭矩阵

| 前序发现 | 最终状态 | 证据与边界 |
|---|---|---|
| 默认启用 History，但无确定可写状态目录 | **关闭** | `contrib/systemd/ghc-api-proxy.service:12-13` 使用 `StateDirectory=ghc-api-proxy` 创建并授权 `/var/lib/ghc-api-proxy`，并显式设置 History 与 tokenization 路径。`tests/smoke/test_systemd_units.py:42-66` 对账 unit→settings，`tests/smoke/test_systemd_units.py:87-152` 在 `HOME=/nonexistent` 的真实 fd 进程中验证 History 文件落盘。省略显式路径的负样本仍复现原权限失败。 |
| `--fd 0` 被 CLI 接受，但 Uvicorn 不按继承 fd 处理 | **关闭** | `src/app/cli.py:53` 将下界收紧为 1；`tests/unit/test_cli.py:91-103` 断言 fd 0 以 CLI usage error 拒绝且不调用 Uvicorn。 |
| `Type=simple` 弱化 exec 前启动错误可观测性 | **关闭** | `contrib/systemd/ghc-api-proxy.service:9` 改为 `Type=exec`；`docs/agents/deployment-systemd/README.md:19` 与 `:53` 明确 `exec` 成功不等于 FastAPI lifespan 完成或 readiness，未误写成 `sd_notify`。 |
| `KillMode=mixed` 只在超时强杀阶段覆盖子进程，却被描述为防逃逸长期合同 | **关闭** | `contrib/systemd/ghc-api-proxy.service:19` 改为 `KillMode=control-group`；`docs/agents/deployment-systemd/README.md:62` 准确说明整个 service cgroup 共享 SIGTERM graceful 窗口，随后才由超时强制清理。 |
| 旧 smoke 只做字符串自洽，不能证明真实 listener、无 HOME startup、落盘和 SIGTERM | **关闭主要缺口** | `tests/smoke/test_systemd_units.py:87-152` 由父进程建立真实 TCP listener 与预连接 backlog，把 fd 3 交给真实 CLI／Uvicorn，观察 liveness 200、History 文件、shutdown 日志和进程退出。该测试不冒充已连接真实 systemd manager。 |

## 事实性发现

[major] `contrib/systemd/ghc-api-proxy.service:12-13`、`src/app/history/sqlite/writer.py:32-34`、`src/app/tokenization/state_store.py:89-97` — 新状态目录可写但默认权限过宽，system-level 部署会让同机非特权用户读取完整 History 与 tokenization 状态 — systemd 255 明确规定 system unit 默认 `UMask=0022`，`StateDirectoryMode=` 默认 `0755`；service 未覆盖任一设置。以该默认 umask 运行候选真实 writer，现场得到状态目录 `0755`、`history.db` `0644`、`tokenization.json` `0644`；`/var/lib` 通常可遍历，History schema 又持久化完整 request payload、response、usage 与 error，因此这不是抽象加固建议，而是适用于通用 system-level 模板的本地数据暴露 — 在 service 中增加 `UMask=0077` 与 `StateDirectoryMode=0700`；对 EnvironmentFile 覆盖到自管目录的文档要求从“可写”收紧为服务账户独占或等价最小权限；增加真实 writer 权限测试，至少断言默认目录不可被 group／other 遍历，数据库、WAL／SHM、tokenization 临时文件与最终文件均无 group／other 权限。修复后重跑 `systemd-analyze verify`、无 HOME fd smoke、权限探针及全仓门；达到 `0 major` 后可 squash。

[minor] `tests/smoke/test_systemd_units.py:142-152`、`docs/agents/deployment-systemd/README.md:36-43` — 无 HOME 运行态 smoke 对 readiness 明确断言 `503 Service Unavailable`，且只断言 `history.db` 已创建，没有驱动 tokenization state 发生 revision 并断言 `tokenization.json` 真正落盘，也没有自动化执行 EnvironmentFile 覆盖默认状态路径的场景 — 当前实现本身没有错误：unit 已显式设置两条路径，systemd 的 EnvironmentFile 后置覆盖 `Environment=`，应用配置把 environment 合并在 YAML 之后，tokenization store 只在状态发生变化时写盘；但测试名和部署说明容易让后续读者把“路径接线已静态核对＋History 已真实写入”读成“readiness 成功且两类状态都已真实写入” — 增加一个提供受控 generic upstream／认证状态的正向 readiness 200 smoke；让 tokenization state 产生一次可持久化 revision，SIGTERM 后断言覆盖目录内的 `tokenization.json`；另以与 EnvironmentFile 等价的覆盖环境值指向第二个临时目录，断言 effective settings 和两类实际写入都落在覆盖目录。该项不改变上述文件权限 major，也不是额外 squash blocker。

未发现 blocker；发现 1 项 major。

## 已核对的实际保证措辞

- 文档准确把 socket activation 的保证限制为：`.socket` 保持 active 时，有限 backlog 中尚未 accept 的连接可等待新进程；已 accept 的 HTTP／SSE／WebSocket 不迁移，backlog 可能满，客户端可能超时，同时重启 socket 会失去保护。
- 文档准确说明单 service restart 是 stop-old 后 start-new，不是 rolling／双实例，也没有声称 accepted connection 无损迁移或 zero-downtime。
- `Type=exec` 只提高解释器、用户和 exec setup 错误的启动作业可观测性；文档继续要求以 `/health/readiness` 判应用可用，没有把 `active` 当 ready。
- `KillMode=control-group` 的“共享 graceful shutdown 窗口”与 systemd 255 语义一致；没有沿用 mixed“防未来子进程逃逸”的错误理由。
- `TimeoutStopSec=330s` 只给 graceful cleanup 上限，超时后会中断剩余连接；`Restart=on-failure` 只能恢复后续服务，不能恢复已断连接。
- 文档明确 EnvironmentFile 可覆盖 unit 默认状态路径，并把“管理员预先创建并授权覆盖目录”作为覆盖时的前置条件；默认路径则由 `StateDirectory=` 建立和授权。但当前“授权／写权限”措辞没有保证最小读取权限，须随 major 修订。
- 文档明确没有 `ExecReload`／SIGHUP 热重载合同，日常只重启 service，不同时停止 socket。

## 未安装 unit 的证据边界

- 本轮没有安装或启动任何候选 unit，因此没有声称 service 真实进入 `ghc-api-proxy.slice`，也没有声称 `memory.high`、`memory.max`、`cpu.max` 或 `pids.max` 已在真实 cgroup 生效。
- 原始模板在本机 systemd 255 的 `systemd-analyze verify` 唯一失败是 `/opt/ghc-api-proxy/.venv/bin/python` 尚不存在。这符合文档的安装前路径假设，但意味着“安装后路径与 service 用户均可解析”仍属于部署阶段 gate，不能由仓库态验证替代。
- 仓库 smoke 使用真实 TCP listener、真实 CLI／Uvicorn、真实 FastAPI lifespan 与 SIGTERM，但不是 systemd manager 发信号，也没有创建 main＋child cgroup。因此它证明应用侧 fd、落盘和 cleanup 接缝，不证明真实 `KillMode=control-group` 运行态施加；后者仍应在隔离 transient unit／VM 或受控目标机验证。
- 当前模板只有一个 activation socket，固定 fd 3 合同成立。若未来增加第二个 listener，必须在扩展前引入 `LISTEN_PID`／`LISTEN_FDS`／`LISTEN_FDNAMES` 数量与名称校验，不能继续依赖裸顺序猜测。

## 主观建议

[建议] `tests/smoke/test_systemd_units.py` — 保留当前无 root smoke，并在后续隔离 systemd 环境补 main＋child 的真实 stop 测试 — 预期影响是把 `KillMode=control-group` 从手册与字符串合同提升为可观察运行态证据 — 推荐使用非生产端口和临时 unit，在 stop 后断言主、子进程均先收到 SIGTERM，再用拒绝退出的子进程验证超时 SIGKILL 清场；不要安装或占用生产 `4141` unit。

[建议] `contrib/systemd/ghc-api-proxy.service:13` — 后续可直接消费 systemd 自动提供的 `$STATE_DIRECTORY`，减少 `/var/lib/ghc-api-proxy` 的重复硬编码 — 预期影响是 root prefix、portable service 或未来目录重命名时减少 StateDirectory 与应用路径漂移 — 推荐先用本项目目标 systemd 版本验证 specifier／环境展开方式，再决定是否替换；当前绝对路径在 system-level unit 上正确，不需要为本轮 squash 改动。

## 结构怪味扫描与处置

- `tests/smoke/test_systemd_units.py:42-66` — **实现常量与测试 oracle 部分同源** — 静态测试只能证明模板与 settings 接线，不能证明 manager 建目录；本轮已有真实临时目录／应用写入 smoke 补强主要接缝，剩余 tokenization／readiness 覆盖列为 minor。
- `contrib/systemd/ghc-api-proxy.service:12-13` — **状态所有权只闭合可写性，未闭合保密权限** — 当前 `StateDirectory=` 与显式路径解决了 startup major，却继承 systemd 的 `0755`／`0022` 默认，真实文件为 `0644`；本轮列为 major，须用 `StateDirectoryMode=0700` 与 `UMask=0077` 在编排层闭合。
- `contrib/systemd/ghc-api-proxy.service:12-13` — **同一目录名以 systemd 声明与绝对路径重复表达** — 当前两者一致且有测试保护；将 `$STATE_DIRECTORY` 作为后续可维护性建议，不替代本轮权限 major。
- `contrib/systemd/ghc-api-proxy.service:15` 与单一 `.socket` — **裸 fd 顺序耦合** — 当前仅一个 activation socket，fd 3 是 systemd 合同且运行态 smoke 已通过；在第二 listener 出现前必须升级为名称／数量校验，本轮不提前扩张实现。
- 扫描范围还包括 Environment／EnvironmentFile→Pydantic settings、StateDirectory→History／tokenization、socket→CLI→Uvicorn、SIGTERM→Uvicorn→FastAPI lifespan、service→slice 与 README→实际行为。除上述已处置项外，未发现新的重复实现、职责错位、抽象泄漏或不必要自研机制。

## 方案反思

1. **更好的内部替代方案**：`StateDirectory=`＋显式应用路径的方向正确，但完整状态所有权还必须包含 `StateDirectoryMode=0700`＋`UMask=0077`，否则只闭合“能写”而没有闭合“谁能读”。`Type=exec`、`KillMode=control-group` 和独立 readiness 分别承载 exec setup、cgroup 停止和应用可用；未来可考虑 `$STATE_DIRECTORY` 消除路径重复。
2. **判据判别力**：正向 smoke 能区分“显式可写路径＋真实 fd 3 可启动”与“无显式路径＋无 HOME 在 startup 失败”；`fd=0` 也有明确负样本。它仍不能区分真实 manager 是否创建目录、真实 cgroup 是否向 main＋child 发信号，报告已保持这条边界；readiness／tokenization 的剩余正向覆盖列为 minor，而未把通过范围外推。
3. **成熟第三方方案**：无需新增库。systemd 的 `StateDirectory=`、socket activation、`Type=exec`、`KillMode=control-group` 和 slice controls 已覆盖编排需求；Python 侧继续使用 Uvicorn 原生 `fd` API。后续多 fd 时优先采用成熟 systemd daemon API binding或小而完整的协议解析层，不散落手写环境变量猜测。

## 结论

候选 `1a220e04a99c6ce07b4bdd6bb0876b4180d4c489` 已关闭前序报告点名的状态目录可写性、fd 下界、`Type=exec` 与 `KillMode=control-group` 问题，但真实权限探针发现新的状态数据暴露 major。当前为 **`0 blocker／1 major`，不可 squash**。增加 `UMask=0077`、`StateDirectoryMode=0700`，收紧覆盖目录文档并补权限回归后，应执行定向复评；若结果为 `0 blocker／0 major`，届时明确可 squash。readiness 200、tokenization 实际落盘和 EnvironmentFile 覆盖路径仍是 1 项非阻断 minor。真实 unit 安装、cgroup controls、main＋child 信号和生产 cutover继续留在后续受控阶段独立验收。
