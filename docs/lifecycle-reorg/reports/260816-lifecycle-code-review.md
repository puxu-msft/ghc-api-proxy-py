# Lifecycle code review

## 评审范围

评审 HEAD `7a157293b277d19b0a75789de921a4bd7aca8f4e` 的 `src/app/lifecycle/shutdown.py`、`listener.py`、`standalone.py`、`src/app/server_adapter.py` 的新增方法，以及指定的两份测试；行为 oracle 仅采用 `docs/.human-controlled/lifecycle.md`，未采用 `.dev/human-controlled-docs-candidates/`。

## 已读取／执行的证据

- 阅读上述实现、`src/app/cli.py`、`src/app/rolling_runtime.py`、既有 adapter 测试和 oracle；`git diff HEAD^ HEAD` 显示 adapter 仅新增两个方法，既有 `shutdown_lifespan` 未改。
- 全量执行 `uv run pytest`：`1167 passed in 41.83s`；`uv run ruff check src tests` 通过；`uv run pyright` 为 `0 errors, 0 warnings, 0 informations`。
- 对 C2 做了不落盘的进程内变异：将 `_descend` 换成“按精确下一 rung 顺序等待、循环内 `clear()`”的实现后，三次同步 SIGTERM 在 0.5 秒内超时；当前实现恢复后未留下源码改动。
- 对 C5 用 Python AST 扫描 `src/app/lifecycle/**/*.py`，`sys.exit`／`os._exit` 调用命中为空；已检查运行时安装的 Uvicorn 0.40.0 中 `H11Protocol.shutdown()` 的实际行为。

## 总体 verdict

存在 blocker，不能进入下一阶段。blocker：3；major：0。

## 当前状态断言核验

- C1：通过。`ShutdownLadder.receive()` 的 SIGINT／SIGTERM 上升、SIGUSR2 仅从 RUNNING 进入 DRAINING 的实现位于 `src/app/lifecycle/shutdown.py:60–73`；独立序列探针和单元测试均通过。
- C2：通过。上述进程内变异确实使突发三信号路径卡住，当前 `src/app/lifecycle/standalone.py:87–110` 每轮重读 rung 的实现避免该问题。
- C3：通过。`bind_listener()` 在 `src/app/lifecycle/listener.py:47–78` 设置 `SO_REUSEPORT`；两种二次 bind 情形由 `tests/unit/test_lifecycle_shutdown.py:100–118` 覆盖并在全量测试中通过。
- C4：通过，但仅限既有 systemd 行为未被本提交改动。adapter diff 只增加 `interrupt_connections`／`abandon_requests`，而 `RollingRuntime` 仍单独安装其信号处理器；当前 composition 没有将两个 runtime 放入同一事件循环。若未来同进程共置，两个 `add_signal_handler(SIGUSR2, ...)` 会互相覆盖，不能假定可共存。
- C5：通过。AST 结果为零调用。
- C6：超时位置的断言通过：`_descend()` 以无 timeout 的 `wait_drained()` 排空，`asyncio.timeout` 只在 `_finalize()`；但这不保证超时前清理完成，见 blocker 3。
- C7：通过，结果如上。

## 事实性发现

[blocker] `src/app/cli.py:121–136` — 直接运行入口仍直接调用 `uvicorn.run()`，没有构造 `bind_listener()`、`UvicornListenerAdapter` 或 `StandaloneServer`。
`lifecycle.md:18–24` 要求直接运行时由三层信号语义驱动，但生产入口不会抵达本提交新增的代码，仍使用 Uvicorn 的默认 listener／signal 生命周期。
失败场景是操作者按现有直接启动入口运行服务后发送 SIGUSR2 或重复 TERM：新增 ladder 根本不参与，平滑重启和三级关闭均不可用。
修复应在直接运行 composition root 接入该 server，并添加从真实 CLI 入口到 SIGUSR2、二次和三次 TERM 的端到端测试。

[blocker] `src/app/server_adapter.py:147–158`、`tests/integration/test_standalone_lifecycle.py:160–180` — 第 2 级没有中断正在执行的 HTTP 请求，违反 oracle 的“中断现有请求，等待请求被中断”。
当前锁定的 Uvicorn 0.40.0 中 `H11Protocol.shutdown()` 对未完成 response 只设 `cycle.keep_alive = False`，不会取消仍在 `await hold.wait()` 的 handler；测试第 170–172 行反而把该错误行为写成预期。
将 `interrupt_connections` 进程内变异为“仅返回连接数、不调用 shutdown”后，`test_a_second_signal_interrupts_without_abandoning` 仍通过，因此该判据无法证明第 2 级实际动作；第 3 级测试不弥补此缺口。
应提供真正作用于当前 request task 的第 2 级中断，并断言 handler 收到取消或客户端连接被实际终止；第 3 级再只承担“不再等待”的区别。

[blocker] `src/app/lifecycle/standalone.py:113–124`、`src/app/server_adapter.py:172–190` — `_finalize()` 的 timeout 会取消仍在执行的 lifespan cleanup，随后还静默吞掉 `close_masters()` 的异常。
进程内 fake adapter 在 `cleanup_timeout=1` 时得到 `timed_out=True, cleanup_completed=False, cleanup_cancelled=True, close_error_suppressed=True`；这与 oracle 第 21 行“执行状态持久化、资源清理等，然后退出”冲突。
因此第 3 级可能在持久化或 ASGI lifespan teardown 未完成、甚至 listener master 未关闭时仍返回成功报告，现有测试只断言 `cleanup_timed_out is False`，没有覆盖失败路径。
应将 cleanup 放入可等待的 shielded task，timeout 只记录预算耗尽而不把其取消，并将 close／lifespan 错误显式聚合或上抛；补充超时与 close failure 的回归测试。

## 主观建议

无。


## 复评（89e4ab5）

### 评审范围

复评 HEAD `89e4ab53189a2100f3b8698888bb69dd164b2125` 中 `626e9a9`、`1243b5b`、`89e4ab5` 对上一轮 B1～B3 的修复，并审查新增 standalone entry、pidfile 与真实子进程测试。行为 oracle 仍为 `docs/.human-controlled/lifecycle.md`；C-2 仅作为 systemd 路径尚待用户裁决的证据，而非行为 oracle。

### 已读取／执行的证据

- 阅读 `src/app/cli.py`、`src/app/lifecycle/{standalone,entry,pidfile,listener}.py`、`src/app/server_adapter.py`、新增和关联测试，以及 `.dev/human-controlled-docs-candidates/existing-rulings.md`。
- 运行 `python -m pytest -q tests/unit/test_lifecycle_pidfile.py tests/unit/test_lifecycle_cleanup.py tests/unit/test_cli.py tests/integration/test_standalone_lifecycle.py tests/integration/test_standalone_process.py`，结果为 `61 passed`；运行两份 systemd smoke，结果为 `11 passed`。
- 对 B2 做仅进程内变异：运行时将 `UvicornListenerAdapter.cancel_requests` 替换为只计数、不调用 `Task.cancel()` 的函数，先打印确认 `mutation-active: __main__ count_only`，再运行 standalone lifecycle 集成测试，得到恰好 `3 failed`。
- 对 B3 用实际 `anyio.run` composition root 探针：输出依次为 `cleanup-started`、`ShutdownReport(... cleanup_timed_out=True, cleanup_completed=False ...)`、`cleanup-cancelled`、`runner-returned`。另以目录作为 pidfile 的受控失败探针得到 `PidfileError` 后同端口仍返回 `200 OK`。

### 总体 verdict

存在 blocker，不能进入下一阶段。blocker：2；major：2。

### 上轮处置核验

- B1：直接 `start` 的无 `--fd` 分支已构造 `StandaloneOptions` 并调用 `run_standalone`；真实子进程 SIGTERM 测试已证明 `_signal_handlers()` 实际安装并接收信号。保留 `--fd → uvicorn.run` 的取舍成立：C-2 明确将三级关闭对 systemd 的适用性留待用户裁决，且现有 systemd 关闭合同未被改动；`adopt_listener()` 因此暂无生产调用者只是有意保留的未接线路径，不构成 blocker 或 major。
- B2：已关闭。第 2 级现在取消 request task，handler 的 `CancelledError` 观察和上述变异的三条失败共同证明它不再只关闭连接；第 3 级对拒绝取消的 handler 只承担“不再等待”，两级可区分。
- B3：即时的 lifespan／`close_masters()` 异常会进入 `ShutdownReport.cleanup_error`，并未静默吞掉；但 timeout 后的 cleanup 无法跨越 CLI runner 的事件循环退出，故 B3 的“继续运行”要求仍未满足，见 blocker 2。

### 事实性发现

[blocker] `src/app/lifecycle/pidfile.py:106–125` — `/proc/<pid>/stat` 的 starttime 比较是 check-then-use，不是可持有的进程身份。前任可在第 112 行校验后、123 行 `os.kill` 前退出并让 PID 被复用，SIGUSR2 将发给无关新进程，恰违背本模块的核心防护目标；`/proc` 缺失时又静默退化为不交接。应在支持的平台用可持有的 pidfd 进行“校验后向同一对象发信号”，不支持时明确拒绝 smooth restart／不发送信号，并补受控 race 与非 Linux 行为测试。

[blocker] `src/app/lifecycle/standalone.py:138–157`、`src/app/cli.py:147` — `asyncio.shield()` 只挡住 `wait_for` 的取消；`serve()` timeout 返回后，`anyio.run` 结束事件循环仍会取消悬挂 cleanup。实际 probe 已观察到 `cleanup-cancelled`，而 `tests/unit/test_lifecycle_cleanup.py:110–134` 只在同一仍存活的测试 loop 中检查“尚未完成”，没有验证 composition root。不要让 standalone runner 在必须完成的 cleanup task 悬挂时返回；应由生命周期 owner 保持 loop 存活直至任务完成并取得其异常，或调整合同使退出前完成清理成为显式不变量。

[major] `src/app/lifecycle/entry.py:72–87`、`src/app/lifecycle/standalone.py:87–97` — listener 已 `arm()` 后，`write_pidfile()` 或 `signal_restart()` 抛错会直接逃出 `serve()`；`finally` 只删 pidfile，不执行 lifespan shutdown 或关闭 masters。受控的 pidfile 写失败探针捕获 `PidfileError` 后，同一端口仍能返回 `200 OK`；若前任仍存活而发送失败，它还会失去刚被覆盖后又删除的 pidfile。应为 startup／announce 失败走统一 teardown，并为 pidfile 覆盖与前任信号失败定义可恢复的状态转换。

[major] `docs/.human-controlled/lifecycle.md:33`、`src/app/cli.py:56–83`、`pyproject.toml:45–46` — 人类权威文档指定的 `uv run ghc-api-proxy --restart` 不是当前 Typer 多命令 CLI 的合法调用；实际执行退出码为 `2`，报 `No such option: --restart`，有效形式是 `ghc-api-proxy start --restart`。这使文档规定的平滑重启入口不可执行；因文档受用户控制，需由用户在“修正文档命令”与“让顶层 CLI 接受该选项”之间裁决，评审倾向前者以保持现有 `start` 子命令合同。

### 主观建议

无。


## 第三轮

### 评审范围

复评 HEAD `3c4c85b10ca614a521b738ca657252a2e60b266c` 对 B-1、B-2、M-1 的修复，并检查由修复引入的 pidfile rollback、startup teardown 与 failed-lifespan 接缝。`docs/.human-controlled/lifecycle.md` 继续作为 standalone 行为 oracle。

### 已读取／执行的证据

- 阅读本提交修改的 `src/app/lifecycle/{pidfile,standalone,entry}.py`、关联测试、C-4 记录，以及前两轮报告。
- 自行运行 `python -m pytest -q`，结果为 `1204 passed`；运行 `python -m ruff check src tests` 通过；另行运行 pidfile 与 lifecycle 聚焦测试通过。
- 实测项目解释器无 `signal.pidfd_send_signal`，但 ctypes fallback 对以 `O_DIRECTORY` 打开的 `/proc/self` fd 发送 signal 0 成功；真实子进程 SIGUSR2 测试亦通过。Linux 文档确认这类 fd 的操作不会作用到 PID 复用后的新进程，而是对原进程失败；它不阻止 PID 数字本身复用。[kernel procfs](https://www.kernel.org/doc/html/latest/filesystems/proc.html)；[pidfd_send_signal(2)](https://man7.org/linux/man-pages/man2/pidfd_send_signal.2.html)。
- 受控探针分别观察到：startup hook 与三个 release 同时失败时，调用方仅收到 `RuntimeError: announce failure`，无 cause／context；lifespan cleanup 抛错时报告虽含错误，但 `masters_closed=False`；以原有 PID 重写 pidfile 会把错误 token 替换为当前占有者 token，`live_predecessor()` 随后接受该无关进程。

### 总体 verdict

存在 blocker，不能进入下一阶段。blocker：1；major：2。

### 上轮处置核验

- B-1 的主路径已关闭：`/proc/<pid>` directory fd 可作为稳定的进程引用，`dir_fd` 读取与 pidfd signal 针对同一原始进程；原注释中“PID 数字不会被回收”不准确，但实现依赖的正确保证是“复用后旧 fd 不会操作新进程”。signal 0 自检不足以单独证明所有语义，但真实 SIGUSR2 子进程正控补足了当前平台的调用验证。
- B-2 已关闭：超预算会先置 `cleanup_timed_out=True`，随后仍等待 cleanup 完成，故不会遗留会被 `anyio.run` 取消的 task。无限等待是 oracle 已明确留给 SIGKILL 的操作员选择；该字段仍可区分“超过预算后最终完成”与预算内完成，但不再是强制退出 deadline。
- C-4 仍是用户 A 级裁决，不能由代码作者抢先选择顶层兼容。当前多命令 CLI 的既有合同支持优先修正文档为 `start --restart`，但在用户裁决前不应添加默认顶层入口。

### 事实性发现

[blocker] `src/app/lifecycle/entry.py:89–95`、`src/app/lifecycle/pidfile.py:94–108` — announce 后的失败 rollback 丢弃 `predecessor.start_token`，改以数值 PID 重算 token。若前任在失败前退出且 PID 被复用，写回的 pidfile 会认证无关新进程，下一次 restart 可向它发送 SIGUSR2，重新打开 B-1 所防的事故；受控探针已得到“wrong token → `write_pidfile(pid)` → `live_predecessor` 接受当前无关 owner”。应原样、原子地写回原 `PidfileEntry`，或先以该 entry 的 token 重新安全验证；不匹配则删除／拒绝恢复，绝不能按 PID 重新取 token。

[major] `src/app/lifecycle/standalone.py:105–117` — `_abandon_startup()` 对 `stop_accepting`、lifespan shutdown、`close_masters` 的所有 `Exception` 均无记录地 suppress。受控探针让三者均抛错，调用方只看见原 hook 的 `RuntimeError` 且 `__cause__`／`__context__` 都为空，因此资源释放失败不可诊断，也无法满足先前对关闭错误“不得吞掉”的修复目标。保留原启动错误，但以 `ExceptionGroup`、异常链或结构化日志／结果携带所有 cleanup failure，并为三种 release failure 加回归测试。

[major] `src/app/lifecycle/standalone.py:175–184` — lifespan cleanup 失败后，`cleanup_error` 非空使 `close_masters()` 完全不被尝试。探针的 `shutdown_lifespan()` 抛 `RuntimeError` 后报告包含该错误而 `masters_closed=False`；这违反第三级仍应尽力释放 listener 的资源清理语义，并会使嵌入式调用者在 `serve()` 返回后继续持有 master。应在 lifespan 成败两侧都尝试 `close_masters()`，把两项错误聚合进报告，并断言 failed-lifespan 时 master 仍被关闭。

### 主观建议

无。


## 第四轮

### 评审范围

复评 HEAD `a21403c6ca77d74be0181f57afca040d16ad6fad` 对 B-3、M-3、M-4 的修复，并检查 pidfile writer 分工、startup failure notes 与终止 cleanup 的错误载体。

### 已读取／执行的证据

- 阅读 `src/app/lifecycle/{pidfile,entry,standalone}.py`、所有直接 `write_entry`／`write_pidfile` 调用点及新增测试。
- 自行运行 `python -m pytest -q`，结果为 `1207 passed`；运行 `python -m ruff check src tests` 通过；生命周期聚焦套件为 `47 passed`。
- 以两个同为 `RuntimeError("same failure")` 的 fake teardown 运行 `_finalize`，得到精确输出 `RuntimeError: same failure; RuntimeError: same failure`，其中没有任一错误的来源标签。

### 总体 verdict

修复 B-3、M-3 后只剩 1 个 major，修复该项后可进入下一阶段。blocker：0；major：1。

### 上轮处置核验

- B-3：已关闭。`entry.py` rollback 唯一使用 `write_entry(pidfile, predecessor)`，保留原 token；全仓生产调用点中 `write_pidfile` 仅用于新进程首次记录，未发现另一条 rollback／恢复路径会重铸身份。
- M-3：已关闭。`_abandon_startup()` 逐项具名收集异常，`serve()` 用原异常的 `__notes__` 交付；嵌入式调用方能检查 release 失败，但 note 表示“释放操作失败”，不能独立证明资源必然仍泄漏，这一强度与实际可观察事实相符。
- M-4：已关闭其“必须尝试关闭 master”的部分；lifespan 成败两侧均调用 `close_masters()`，但新的聚合载体仍缺少错误来源，见 major。

### 事实性发现

[major] `src/app/lifecycle/standalone.py:181–195` — `cleanup_error` 把 lifespan 与 `close_masters` 错误只按 `"; "` 拼接，没有标明产生阶段。若两侧同为同类、同文本异常，实际输出就是 `RuntimeError: same failure; RuntimeError: same failure`，调用方无法判断 listener 是否未释放，也无法将修复路由到 lifespan 或 listener；现有双失败测试只用不同文本，未覆盖该歧义。应改为具名／结构化字段，例如 `lifespan_error` 与 `listener_close_error`，或至少拼接 `shutdown_lifespan:`、`close_masters:` 前缀，并加入同类同文本的反例测试。

### 主观建议

无。


## 第五轮

### 评审范围

复评 HEAD `5fd9c166f24bdd770a2e87aebd8fbfd6528be4eb` 对 M-5 的阶段标签修复，以及 `cleanup_error` 的消费者和相关 lifecycle 回归。

### 已读取／执行的证据

- 阅读 `src/app/lifecycle/standalone.py`、`tests/unit/test_lifecycle_cleanup.py`，并搜索全仓 `cleanup_error` 的生产消费点。
- 自行运行 lifecycle 聚焦测试，结果为 `48 passed`；运行针对修改范围的 Ruff 检查通过。
- `_finalize()` 对两侧均为 `RuntimeError("same failure")` 的 probe 现在产生两个不同的阶段前缀；新增测试精确断言这一反例。

### 总体 verdict

可进入下一阶段。blocker：0；major：0。

### 上轮处置核验

- M-5：已关闭。`shutdown_lifespan:` 与 `close_masters:` 前缀在保留既有单一可读 `cleanup_error` 字段的同时，足以让当前仅转发该字符串的调用方区分错误来源；未发现现有消费者需要按来源进行程序分支，因此没有必要为臆测消费者扩大 `ShutdownReport` 的字段形状。
- 本轮未发现 blocker 或 major；C-4 仍按既有 A 级结论等待用户裁决，不构成本轮代码回归。

### 事实性发现

未发现问题。

### 主观建议

无。
