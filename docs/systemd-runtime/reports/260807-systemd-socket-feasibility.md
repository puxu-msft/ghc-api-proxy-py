# systemd socket activation 与 cgroup v2 可行性复核

- **评审范围**：只读复核 `main@ed77c9d191df81c451c25161420515cca52ce6a4`、候选 `66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`、本机 systemd／cgroup v2 运行环境、项目 CLI、uvicorn 0.40.0 的继承 fd 路径，以及候选 unit、文档和测试。未安装或启动候选 unit，未停止现有监听者，未修改项目代码或系统状态。
- **总体 verdict**：**修复 major 后可进入下一阶段**。Socket activation 的基本方向可行，候选已把 `--fd 3` 接到 uvicorn；但候选当前把 `KillMode=mixed` 固化成运行合同并给出不成立的长期理由，必须改为默认的 `control-group`。同时应把 `Type=simple` 改为 `Type=exec`，但不得把 `Type=exec` 描述成 readiness 通知。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：2。
- **双视角覆盖证据**：
  - **机械核对**：固定 main HEAD、候选 HEAD 与候选 worktree；逐行对账三个 unit、部署文档、CLI 与新增测试；核对本机 systemd 255、PID 1、`cgroup2fs`、统一层级控制器、uvicorn 0.40.0 安装源码；用本机 `systemd-analyze verify` 解析候选 unit，并检查 main 与候选的 `--fd`、reload、worker、notify 表面。
  - **第一人称执行**：模拟“启用 socket→首连接激活 service→FastAPI lifespan startup→uvicorn 开始 accept→重启 service→SIGTERM drain→超时清理”路径；分别走了正常启动、可执行文件不存在、应用 startup 失败、未 accept 连接、已 accept 长连接、未来出现子进程、socket 被同时停止、修改监听地址和 OOM／异常退出分支。

## 现场基线与证据口径

### 本机运行环境

现场探针得到：本机为 WSL2，内核 `6.18.33.2-microsoft-standard-WSL2`；PID 1 的 comm 为 `systemd`；systemd 为 `255 (255.4-1ubuntu8.16)`，系统状态为 `running`。`/sys/fs/cgroup` 的文件系统类型为 `cgroup2fs`，挂载选项含 `nsdelegate`；`/proc/1/cgroup` 与本评审进程的 `/proc/self/cgroup` 均为 `0::/init.scope`，因此这是 cgroup v2 unified hierarchy，而不是 v1 混合层级。可用控制器为 `cpuset cpu io memory hugetlb pids rdma`，足以承载候选 slice 的 `MemoryHigh`、`MemoryMax`、`CPUQuota` 与 `TasksMax`。

这只证明**本机内核和 systemd 具备机制**，不证明候选 slice 已生效。本评审没有安装 `ghc-api-proxy.*` unit，也没有观察到候选 service 的真实 cgroup；当前评审会话仍在 `/init.scope`。候选资源限制只有在 unit 实际加载、服务进入 `ghc-api-proxy.slice` 后，才能通过 `systemctl show` 与对应 cgroup 文件复验。

现场 `ss` 与 `/proc` 交叉定位到：`127.0.0.1:4141` 和 `[::1]:4141` 当前由 PID `1271974` 的 Bun 进程监听，命令行为 `/home/xp/.local/volta/tools/image/packages/bun/bin/bun run ./packages/cli/src/main.ts start --restart`，cgroup 为 `0::/init.scope`。因此现 owner 不是候选 Python service，也不是 systemd socket unit；安装候选前必须做显式端口所有权切换。该 PID 是 2026-08-07 本轮现场快照，不应被后续执行者当作持久身份，cutover 时必须重取。

### 提交与实现身份

`main` 固定在 `ed77c9d191df81c451c25161420515cca52ce6a4`。候选工作树 `/home/xp/src/ghc-api-proxy-py-systemd` 固定在 `feat/systemd-cgroup-runtime@66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`，相对 main 仅增加或修改 8 个路径，共 183 行新增、1 行删除；候选工作树现场为 clean。

main 的 `src/app/cli.py` 只以 `host`／`port` 调用 `uvicorn.run`，没有 `--fd`。候选在 `src/app/cli.py:53` 暴露 `--fd`，在 `src/app/cli.py:78-79` 拒绝与显式 `--host`／`--port` 混用，并在 `src/app/cli.py:111-114` 将 fd 传入 `uvicorn.run(application, fd=fd, log_config=None)`。因此“main 未接 fd、候选已接 fd”已由两个提交的精确 blob 坐实。

本机虚拟环境实际安装 uvicorn `0.40.0`。其 `uvicorn.run` 签名含 `fd: int | None = None`；单 worker、无 reload 的 `Server.startup()` 在 FastAPI lifespan startup 完成后，以 `config.fd is not None` 创建 event-loop server。候选 CLI 没有暴露或传入 `reload`、`workers`，全仓候选启动路径只有上述两次 `uvicorn.run` 调用，因此当前运行模型是单进程、无 reload。

一次真实继承 TCP fd 探针已观察到候选 CLI／uvicorn 在继承监听 socket 上对 `/health/liveness` 返回 HTTP 200；初始测试器把项目真实响应 `{"status":"ok"}` 错写成 `alive`，故该轮最终退出为探针假红，不能记作完整 E2E 通过。随后重跑与候选 pytest 受共享终端并发会话中断，没有形成可信的最终退出码。静态接线成立，但在合并 gate 中仍须按下文步骤重跑独占的 systemd／E2E 验证。

## 保证边界

### Socket activation 真正保证的内容

候选 `.socket` 使用 `ListenStream=127.0.0.1:4141`、`Accept=no`、`Backlog=1024`。本机 systemd 255 文档确认：`Accept=no` 时，systemd 把**监听 socket**交给单个 service；`Backlog` 是“尚未 accept 的连接”队列，并受 `net.core.somaxconn` 静默上限约束。本机 `somaxconn=4096`，所以模板值 1024 在本机不会被该 sysctl 再截低，但它仍不是无限容量，也不等于 1024 个应用请求必然成功。

只要 `.socket` 保持 active，日常仅重启 `.service`，systemd 仍持有同一监听 socket。旧进程停止 accept 后、尚未被任何应用进程 accept 的新 TCP 连接，可以在有限 backlog 中等待新进程接管。这个机制减少的是监听端口消失窗口，不是完整的应用 zero-downtime。

下列内容**不在保证内**：

1. 已被旧进程 accept 的 HTTP、SSE 或 WebSocket 连接不会迁移到新进程。它们只能由旧进程 drain，或在停止超时／崩溃／OOM 时中断。
2. `Backlog=1024` 不保证所有重启窗口请求成功；队列可满，客户端也可能在应用 ready 前自行超时。TCP SYN 队列、accept 队列和应用层请求不是同一层。
3. 同时停止或重启 `.socket` 会放弃该保护；修改 `ListenStream` 本身需要重建 socket，必须另设维护或切流方案。
4. 单 `.service` 的 restart 是 stop-old 后 start-new，不是新旧实例重叠的 rolling restart。不存在 accepted-connection migration、双实例 readiness 切流或共享状态并发保证。
5. cgroup OOM、进程 crash 或 `TimeoutStopSec` 后的强杀会中断在途连接；`Restart=on-failure` 只能恢复后续服务，不能恢复已断连接。

### 启动与 readiness

当前应用没有 `sd_notify(READY=1)` 接线，候选也没有 notify 依赖或调用。因此不能使用 `Type=notify`，否则 systemd 会等待一个永远不会到达的 READY 通知。候选文档对此判断正确。

推荐 `Type=exec`，而不是候选当前的 `Type=simple`。`Type=exec` 会把 service 的启动成功至少推迟到 `ExecStart` 的 `execve()` 成功，能让错误路径、权限、不可执行解释器等失败直接表现为 start 失败；`Type=simple` 会更早把 unit 视为已启动。这里没有 shell wrapper，`ExecStart` 直接执行 Python，因此 `Type=exec` 与当前命令形态兼容。

但 `Type=exec` **仍不等于应用 ready**。Python import、配置加载、FastAPI lifespan startup、token／upstream 初始化都发生在 exec 成功之后。uvicorn 0.40 的顺序是先完成 lifespan startup，再注册继承 socket 并开始 accept；这使“开始 accept”晚于应用 startup，但 systemd 的 `active` 状态仍早于它。部署和监控必须继续以 `/health/readiness` 为应用可用 oracle，不能把 `systemctl is-active` 或 `Type=exec` 当作 readiness。

项目当前没有 reload 合同：CLI 不暴露 uvicorn reload，unit 没有 `ExecReload`，代码也没有重读配置／热替换 listener 的协议。实现与运维文档都应明确只支持 restart；不得添加一个只发 SIGHUP、却没有应用侧语义的“伪 reload”。

### 停止与 cgroup

候选用 `KillMode=mixed`，文档称其“避免未来子进程逃逸”。这不是可靠的长期合同：`mixed` 在初始停止阶段只向主进程发送 `KillSignal`，仅在超时后的最终阶段对整个 control group 执行强杀。未来若出现 worker 或辅助子进程，它们可能在整个 graceful 窗口继续运行、持有资源或与主进程清理并发；“最终会 SIGKILL”不等于“不逃逸”或“共同优雅停止”。

本项目当前确实是单 uvicorn 进程，无 worker／reload 子进程，所以 `mixed` 与 `control-group` 在**当前单进程 happy path**上没有可见差异；这恰恰意味着没有必要偏离 systemd 默认。应删除 `KillMode=mixed` 以采用默认 `control-group`，或显式写 `KillMode=control-group` 让合同可见。这样未来同一 service cgroup 内的所有进程都会在停止阶段收到 SIGTERM，并由 `TimeoutStopSec=330s` 提供统一上限。

`KillSignal=SIGTERM` 与 uvicorn graceful shutdown 相容。uvicorn 先关闭 server、停止接受新连接，再等待现有连接／任务；随后执行 FastAPI lifespan shutdown。项目 lifespan 当前会拒绝待审批请求、flush tokenization 状态、关闭 History、关闭 upstream clients，并取消 task group。由于 uvicorn 未配置内部 `timeout_graceful_shutdown`，330 秒上限来自 systemd；达到上限后剩余进程会被强杀，清理与长连接完成都不再保证。

## 事实性发现

[major] `contrib/systemd/ghc-api-proxy.service:18`、`docs/agents/deployment-systemd/README.md:55-56`、`tests/smoke/test_systemd_units.py:33` — 候选把 `KillMode=mixed` 固化成配置、文档和测试合同，并以“避免未来子进程逃逸”解释；该解释忽略 mixed 在 graceful 阶段只通知主进程的语义 — 一旦未来出现 worker／helper，子进程可在 330 秒窗口继续运行，只有最终强杀才覆盖整个 cgroup；这与“统一优雅关闭整个 service cgroup”的长期目标相反 — 改为 `KillMode=control-group`，或删除该行采用 systemd 默认；同步改文档和测试，增加一个包含 main＋child 的停止语义集成测试，断言两者均收到 SIGTERM，随后才允许以超时强杀兜底。

[minor] `contrib/systemd/ghc-api-proxy.service:9`、`docs/agents/deployment-systemd/README.md:23`、`tests/smoke/test_systemd_units.py:21` — 使用并固化 `Type=simple`，使 systemd 在 `execve()` 成功前就可把启动作业视为完成，降低了路径／权限类启动失败的可观测性 — 当前没有 notify 实现，但这不迫使使用 simple；直接 `ExecStart` 适合 `Type=exec` — 三处同步改为 `Type=exec`，并增加负向验证：将 `ExecStart` 指向不存在或不可执行文件时，start job 必须失败。文档同时明确 exec 成功不等于 readiness。

[minor] `tests/smoke/test_systemd_units.py:10-39`、`docs/agents/deployment-systemd/README.md:59-62` — 当前 smoke 只用 `ConfigParser` 对字符串做自洽断言；它没有证明 systemd 真能加载 unit、fd 3 真是 TCP listener、service 真进入目标 slice、重启窗口 backlog 真由新进程消费，也无法抓住本轮 `KillMode` 合同方向错误 — 合并 gate 增加本机 systemd transient／临时 unit 集成测试或隔离 VM 测试，见下节；保留字符串测试作为快速 tripwire，但不要把它描述为运行态验证。

## 主观建议

[建议] `contrib/systemd/ghc-api-proxy.service:14` 与 `contrib/systemd/ghc-api-proxy.socket:8` — 当前只有一个 socket，所以按 systemd 协议使用 fd 3 可工作，但 `FileDescriptorName=http` 没有被应用消费 — 若后续可能增加 metrics／admin listener，裸编号会变成脆弱的顺序合同 — 当前可保留 `--fd 3`；在引入第二个 activation fd 前，改用 `LISTEN_PID`／`LISTEN_FDS`／`LISTEN_FDNAMES` 解析并按名称选择，且拒绝数量或名称不符，而不是猜 fd 顺序。

[建议] `contrib/systemd/ghc-api-proxy.slice:4-7` — `1G／2G／200%／256` 是部署模板值，不是从现场负载推导的容量结论 — 过低会制造 cgroup reclaim、OOM 或任务上限故障，过高则失去隔离意义 — 安装前记录现服峰值 RSS、CPU、task 数和长连接压力基线，再决定余量；上线后监测 `memory.events`、`memory.pressure`、`pids.events` 与 service restart 原因。

## 结构怪味扫描与方案反思

- `src/app/cli.py:53`、`contrib/systemd/ghc-api-proxy.service:14` — **裸 fd 顺序耦合** — 当前仅一个 activation socket，保留本轮实现；在第二个 listener 进入前登记为必须消除的扩展门，改用 fd name／count 校验。
- `tests/smoke/test_systemd_units.py:10-39` — **同源自洽测试冒充集成证据** — 本轮作为 minor 修复：保留快速静态 tripwire，另补真实 systemd、listener、cgroup 与停止语义测试。
- `contrib/systemd/ghc-api-proxy.service:18` 与部署文档 — **实现、文档、测试共同固化较弱合同** — 本轮按 major 修为 `control-group`；不能因为三处一致就把选择本身当作正确。

更好的内部替代方案是保持单 service＋socket activation，但用 `Type=exec`、默认 `KillMode=control-group` 和 readiness probe 分别承载“可执行”“整个 cgroup 停止”“应用可用”三个不同事实，避免一个字段跨层冒充全部保证。现有判据的判别力不足：字符串断言能抓字段漂移，却区分不了可加载／不可加载、fd 真 listener／普通文件、未 accept／已 accept、main-only／whole-cgroup shutdown；所以上述双向运行样本必须成为 gate。成熟方案方面，systemd socket activation 与 cgroup resource control 本身就是应复用的系统机制，无需自造 supervisor；Python 侧若未来需要按 fd name 消费，应优先采用成熟的 systemd daemon API binding 或一个小而有协议测试的解析层，而不是继续散落读取环境变量。

## 实现者可执行清单

1. 将 service 改为 `Type=exec`；保持 `Type=notify` 禁用，直到应用在 lifespan startup 完成后真实发送 `READY=1`，并为失败 startup 证明不会误发 READY。
2. 将 `KillMode` 改为 `control-group` 或删除以采用默认；修正文档，不再声称 mixed 防止子进程逃逸；同步改 smoke 断言。
3. 保持 `.socket` 为 `Accept=no`、service 使用继承 listener；明确 service restart 与 socket restart 是两种不同操作，日常重启不得连带停止 socket。
4. 不实现伪 reload。当前仅声明 restart；若未来要求 reload，先定义配置可变项、listener 是否重建、失败回滚和 readiness 切换合同，再实现 `ExecReload`。
5. 在独占环境运行以下验收，而不是只解析文本：
   - `systemd-analyze verify` 对安装后路径和 service 用户均可解析的最终 unit 返回 0；模板仓库态因 `/opt/ghc-api-proxy/.venv/bin/python` 尚不存在而报告该命令不可执行是预期安装前条件，不应通过屏蔽该错误冒充部署可用。
   - 启动 `.socket` 后确认 `ss` 中 listener 的 owner 是 systemd；首个请求激活 service；检查 `LISTEN_PID／LISTEN_FDS／LISTEN_FDNAMES` 和进程实际持有 fd。
   - 在 service 启动前先建立连接，确认连接留在 accept backlog，service ready 后由新进程返回响应；同时做 backlog 满载与客户端短超时负样本，证明文档没有过度承诺。
   - 建立一个已被旧进程 accept 的长连接，再 restart service，确认它由旧进程 drain 而不是迁移；将时长拉过 `TimeoutStopSec`，确认连接会被强制中断。
   - 启动 main＋child 测试进程，stop service 后确认 control group 内两者都收到 SIGTERM；再用不退出的 child 验证超时后 SIGKILL 清场。
   - 检查 `systemctl show ghc-api-proxy.service -p Type -p KillMode -p Slice -p ControlGroup -p MainPID -p ExecMainStatus -p Result`；读取对应 cgroup 的 `memory.high`、`memory.max`、`cpu.max`、`pids.max`，确认不是只写了 unit 文本。
   - 用 `/health/readiness` 判可用；刻意制造配置或 lifespan startup 失败，确认 `Type=exec` 可以 active 片刻但 readiness 不会绿，从而钉住“exec ≠ ready”。
6. Cutover 前重新核对 `127.0.0.1:4141` 的 owner 和 cgroup；本轮快照是 `/init.scope` 中的 Bun 进程，但不得依赖快照 PID。先按既定停服流程停止旧 owner，确认端口释放，再启动 socket，避免两个 owner 争抢端口；本报告不授权也未执行该操作。准备 rollback 时保留“恢复旧 owner”路径，并承认回滚同样不能迁移已 accepted 连接。

## 结论

本机 systemd 255 与 cgroup v2 足以承载该方案，uvicorn 0.40.0 和候选 CLI 的 fd 接线也使 `Accept=no` socket activation 在技术上可行。真实保证应限定为：**socket 持有者不随 service restart 消失，有限数量的未 accept 连接可等待新进程；已 accept 连接不迁移，应用 readiness 不由 systemd active／Type=exec 保证，停止超时、OOM、崩溃和 socket 自身重启都可能中断请求。** 候选在修正 `KillMode`、采用 `Type=exec` 并补运行态集成 gate 后，才适合进入安装与受控 cutover 阶段。
