# systemd「三级关闭」语义调研

## 范围、证据与结论口径

本报告回答的是 systemd 是否能自动驱动三个**可由服务代码处理并完成相应动作**的关闭层级。若把不可捕获的 `SIGKILL` 也仅按「第三个内核信号」计数，答案会不同；它不能承载规格中第三级的状态持久化和资源清理。

本机文档与探针环境是 systemd `255 (255.4-1ubuntu8.17)`。文档证据来自本机的 `man systemd.kill`、`man systemd.service` 和 `man systemctl`；段落名称和下文引号内原文均按该版本读取。项目配置与代码证据来自当前工作树。本报告没有对任何既有 systemd unit 执行 `start`、`stop`、`restart`、`kill` 或 `reload`。

## A．正常 `systemctl stop` 的停止序列

### 1．`KillSignal` 是首个终止信号，不会被自动重复发送

**已确认。** 在没有 `ExecStop=` 的当前 unit 中，`systemctl stop` 立即发送一次配置的 `KillSignal=SIGTERM`；正常路径不会在等待期间再重复 `SIGTERM`。本机 `systemd.service(5)` 的 `TimeoutStopSec=` 段明确写道：

> “If no `ExecStop=` commands are specified, the service gets the `SIGTERM` immediately.”

本机 `systemd.kill(5)` 的 `KillSignal=` 段把它定义为：

> “This controls the signal that is sent as first step of shutting down a unit … Defaults to `SIGTERM`.”

同页 `KillMode=` 段随后只规定“the termination request is repeated with the `SIGKILL` signal or the signal specified via `FinalKillSignal=`”的条件，不是重复 `KillSignal`。因此，当前默认序列中服务可处理的自动终止请求只有首次 `SIGTERM`。

严格按内核信号总数而非终止阶梯计数时还有一个细节：`systemd.kill(5)` 同一段说 systemd 在发送 `KillSignal` 后“will always send `SIGCONT`”。`SIGCONT` 不是第二级关闭请求；默认 `SendSIGHUP=no`，所以默认不额外发送 `SIGHUP`。

### 2．超时后的 `SendSIGKILL` 与 `FinalKillSignal`

**已确认。** `TimeoutStopSec=330s` 到期时，若服务仍存在，systemd 发送最终信号；当前 unit 未覆盖默认值，故为 `SIGKILL`。本机 `systemd.service(5)` 的 `TimeoutStopSec=` 段原文为：

> “If it doesn't terminate in the specified time, it will be forcibly terminated by `SIGKILL` (see `KillMode=` in `systemd.kill(5)`).”

更精确的选项关系来自 `systemd.kill(5)`：

> `SendSIGKILL=`：“Specifies whether to send `SIGKILL` (or the signal specified by `FinalKillSignal=`) to remaining processes after a timeout … Defaults to `"yes"`.”
>
> `FinalKillSignal=`：“Specifies which signal to send to remaining processes after a timeout if `SendSIGKILL=` is enabled … Defaults to `SIGKILL`.”

所以 `SendSIGKILL=yes` 是开关，`FinalKillSignal=SIGKILL` 是未覆写时实际发送的值，二者都在**首次终止请求后的超时**步骤生效。`SIGKILL` 不可被捕获、阻塞或忽略，不能运行第三级清理代码。

还有一个与本题相关的非默认分支：`TimeoutStopFailureMode=` 默认 `terminate`。`systemd.service(5)` 写明其可选 `terminate`、`abort`、`kill`，并说明 `abort` 会在 `TimeoutStopSec=` 到期时发送 `WatchdogSignal=`，再以 `TimeoutAbortSec=` 等待，最后才发送 `FinalKillSignal=`。这一分支见第 6 节；它不是当前 unit 的配置。

### 3．`KillMode` 的受信号对象，以及本项目的值

**已确认。** 本机 `systemd.kill(5)` 的 `KillMode=` 段原文说明其四个值如下。

| 值 | 首次信号与最终信号的对象 | 文档限定 |
| --- | --- | --- |
| `control-group` | 服务停止时（服务有 `ExecStop=` 则在该命令后），cgroup 中的全部剩余进程。 | 默认值。 |
| `mixed` | 首次 `KillSignal` 只给 main process；后续最终信号给 cgroup 的全部剩余进程。 | main process 退出后，剩余进程可立即收到最终信号，而不必等 `TimeoutStopSec=`。 |
| `process` | 只杀 main process，不向其余 cgroup 成员发信号。 | 文档明确列为不推荐。 |
| `none` | 不发送任何杀进程信号，只执行 `ExecStop=`。 | 剩余进程继续留在 cgroup，文档明确强烈不建议。 |

对应的本机原文是：`control-group` 为 “all remaining processes in the control group”；`mixed` 为 “the `SIGTERM` signal … is sent to the main process while the subsequent `SIGKILL` signal … is sent to all remaining processes”；`process` 为 “only the main process itself is killed”；`none` 为 “no process is killed”。

项目 unit 是 `Type=exec`、`KillSignal=SIGTERM`、`KillMode=control-group`、`TimeoutStopSec=330s`，且没有 `ExecStop=`：[/home/xp/src/ghc-api-proxy-py/contrib/systemd/ghc-api-proxy.service:9](/home/xp/src/ghc-api-proxy-py/contrib/systemd/ghc-api-proxy.service#L9)、[/home/xp/src/ghc-api-proxy-py/contrib/systemd/ghc-api-proxy.service:18-23](/home/xp/src/ghc-api-proxy-py/contrib/systemd/ghc-api-proxy.service#L18-L23)。因此首次 `SIGTERM` 和超时后的默认 `SIGKILL` 都面向这个服务 cgroup 的剩余进程，而不是只面向 Python main process。

## B．第二次和第三次终止信号的可用机制

### 4．操作者的 `systemctl kill` 可以在停止中补发信号，但不是 `stop` 的自动升级

**已确认。** `systemctl(1)` 的 `kill PATTERN...` 段定义它为“Send a UNIX process signal to one or more processes of the unit”。`--kill-whom=` 可选 `main`、`control`、`all`，省略时默认 `all`；`--signal=` 省略时默认 `SIGTERM`。故操作者可显式执行例如：

```bash
systemctl kill --signal=SIGTERM --kill-whom=main ghc-api-proxy.service
```

它是独立的发信号操作，不会把 `systemctl stop` 的状态机变成定时重发器，也不会重置或延长正在运行的 `TimeoutStopSec=`。在接收者还存在时，它可以在 unit 已处于 `deactivating` 后补发第二次或第三次可捕获信号；接收者已退出则自然无对象可送。

本机 `--user` 实测支持这一点。创建了仅供本次实测的 transient unit `probe-escalation-1786969784-358771.service`，其 Python main process 在每次 `SIGTERM` 时记录次数并继续运行，属性为 `KillSignal=SIGTERM`、`KillMode=control-group`、`TimeoutStopSec=8s`、`FinalKillSignal=SIGKILL`。先以 `systemctl --user stop --no-block` 使其进入 `deactivating`，再执行 `systemctl --user kill --signal=SIGTERM --kill-whom=main`；记录顺序为 `started\nsignal=15 count=1\nsignal=15 count=2\n`，随后超时状态为 `inactive`。这确认第一条来自 `stop`，第二条来自显式 `kill`；它只证明本机 systemd 255 的 user manager 行为，不是对生产 system manager 的运行态断言。

### 5．`EXTEND_TIMEOUT_USEC=` 只能延长 deadline，不产生级别

**已确认。** 本机 `systemd.service(5)` 的 `TimeoutStopSec=` 段规定：只有 `Type=notify` 或 `Type=notify-reload` 服务在当前 deadline 前首次发送 `EXTEND_TIMEOUT_USEC=...`，且之后在每个声明的间隔内重复发送，manager 才允许停止时间超过 `TimeoutStopSec=`。原文为：

> “the stop time [may] be extended beyond `TimeoutStopSec=`. The first receipt of this message must occur before `TimeoutStopSec=` is exceeded … [the service] repeats `EXTEND_TIMEOUT_USEC=...` within the interval specified, or terminates itself.”

它能做的是给服务自己设定的内部计时器更多外层等待预算；它**不会**生成第二次或第三次 `KillSignal`，也不会告诉服务何时从 drain 进入 interrupt/finalize。严格说，服务在原有 `TimeoutStopSec=` 内自行按时间分级不需要它；一旦使用它，边界已被延长，必须由服务自己保有总时限，不能把无限重复 extension 当作「保证在原始时限内」的证明。

当前项目 unit 是 `Type=exec`，不满足上述通知扩时前提：[/home/xp/src/ghc-api-proxy-py/contrib/systemd/ghc-api-proxy.service:9](/home/xp/src/ghc-api-proxy-py/contrib/systemd/ghc-api-proxy.service#L9)。代码虽有 `STOPPING=1` 封装：[/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/systemd/notify.py:45-46](/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/systemd/notify.py#L45-L46)，但这不改变当前 unit 的 `Type=exec` 事实。

### 6．其他路径的能力边界

**`RestartKillSignal=`：已确认不适合 stop 升级。** `systemd.kill(5)` 原文：`RestartKillSignal=` “is used in a restart job”；未设置时使用 `KillSignal=`。它替换的是 restart job 的**首次**信号，不在普通 stop job 中提供第二或第三次递进。

**`WatchdogSec=`：已确认不适合充当正常关闭的计时器。** `systemd.service(5)` 的 `WatchdogSec=` 段规定服务启动完成后必须持续 `WATCHDOG=1`；漏发时 unit 进入 failed 并以 `SIGABRT` 或 `WatchdogSignal=` 终止。它是存活检测失败，不是“收到 SIGTERM 后 N 秒”的正常关闭升级。

**`TimeoutStopFailureMode=abort`：已确认是唯一需要单列的自动中间信号分支。** 它不是提示中列出的三个选项，但本机 `systemd.service(5)` 明确规定：在 stop timeout 时设为 `abort` 会发送 `WatchdogSignal=`，适用 `TimeoutAbortSec=`，随后发送 `FinalKillSignal=`。因此它可形成 `KillSignal` → `WatchdogSignal` → `FinalKillSignal` 的自动序列。中间信号可由服务选择为可捕获的自定义信号，但它只在**第一级已经耗尽 `TimeoutStopSec=`**后到达；不是操作者随时可用的第二级。

本机第二个 transient probe `probe-escalation-abort-1786969850-360136.service` 设置 `KillSignal=SIGTERM`、`TimeoutStopSec=1s`、`TimeoutStopFailureMode=abort`、`WatchdogSignal=SIGUSR1`、`TimeoutAbortSec=2s`、`FinalKillSignal=SIGUSR2`。main process 捕获三者并保持运行，日志顺序为 `started\nsignal=15 count=1\nsignal=10 count=1\nsignal=12 count=1\n`，收到可捕获的 final signal 后 unit 仍为 `deactivating`。这验证两个事实：`abort` 确实补发中间 `WatchdogSignal`；把 `FinalKillSignal` 改成可捕获信号不会获得 systemd 文档定义的「final signal 后的第三阶段清理窗口」。为清理该自建 probe，随后仅对它执行 `systemctl --user kill --signal=SIGKILL --kill-whom=all`，状态变为 `inactive`。

**`ExecStop=`：已确认不是自动多信号机制。** `systemd.service(5)` 的 `ExecStop=` 段写道：该命令运行后，剩余进程才按 `KillMode=` 终止；没有 `ExecStop=` 才由 `KillSignal=`／`RestartKillSignal=` 终止。它可运行一个同步的服务控制命令，因而能承载命令协议层面的动作，但不自动把同一个服务重复送入第二、三级信号处理器；而且它会占用 stop timeout。当前 unit 没有 `ExecStop=`。

## C．关键判断与时间驱动条件

### 7．自动三级的结论

**已确认：当前正常自动 stop 序列不能驱动规格所说的三级关闭。** 它给服务一次可处理的 `SIGTERM`，在 330 秒 deadline 后给不可处理的默认 `SIGKILL`；缺少的是第二、第三次**可被服务处理且各自留有完成动作时间**的自动升级触发。

`TimeoutStopFailureMode=abort` 可额外产生一个超时后的 `WatchdogSignal`，所以不能笼统说 systemd 永远只会发两个不同信号；但它最多给出一个在一级预算耗尽后才到达的可处理升级，而最后的 `FinalKillSignal` 是终局动作，默认 `SIGKILL`。将 final signal 换为可捕获信号反而如上面 probe 所示会让 unit 停在 `deactivating`，没有 manager 再提供的后续 cleanup 等待阶段。因此它不满足“第三级执行持久化、资源清理后退出”的语义。

项目直接运行路径的 `ShutdownLadder` 正是三个可处理阶段：`DRAINING`、`INTERRUPTING`、`FINALIZING`，每个 `SIGINT`／`SIGTERM` 将其推进一级：[/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/shutdown.py:28-38](/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/shutdown.py#L28-L38)、[/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/shutdown.py:60-73](/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/shutdown.py#L60-L73)。相反，当前 systemd runtime 的第二次终止信号直接调用 `os._exit(128 + sig)`：[/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/rolling/runtime.py:293-298](/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/rolling/runtime.py#L293-L298)。人写规格也仍把 systemd 写成两级并保留该 TODO：[/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/lifecycle.md:52-55](/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/lifecycle.md#L52-L55)。

### 8．若采用「收到一次 SIGTERM 后内部按时间推进」

这种方案不依赖 systemd 自动重发信号，因此在当前 `Type=exec`、`KillMode=control-group` 下也可成立。systemd 侧必要条件是：保留一个有限的 `TimeoutStopSec=`，让应用 main process 在最终信号前自行退出；不得把 `SendSIGKILL=no` 当作完成保障，因为那会让残留进程继续存在。若启用 `ExecStop=`，其占用的等待也必须计入预算。

定义：`E` 为首次 `KillSignal` 前由 `ExecStop=` 消耗的实际时间（当前为 0）；`D`、`I`、`F` 分别为 drain、interrupt、finalize 的最大持续时间；`δ` 为调度抖动、信号投递、lifespan cleanup 和进程退出的保守余量；`T_stop` 为 `TimeoutStopSec`。必要的安全不等式是：

```text
E + D + I + F + δ < T_stop
```

对当前没有 `ExecStop=` 且 `TimeoutStopSec=330s` 的 unit，化为：

```text
D + I + F + δ < 330s
```

严格小于而非等于，是为了确保 main process 已退出，cgroup 中也无残留进程时，systemd 才不会在 boundary 处发最终信号。若改成 `Type=notify` 并使用 `EXTEND_TIMEOUT_USEC=`，不等式的右侧应改为服务自行设上限后的**有效 deadline**；还必须在每一当前 deadline 前发送 extension。extension 本身不提供 `D`、`I`、`F` 的上界，所以不能省略应用内部的总预算。

### 9．时间驱动的代价与失效模式

**已确认的语义代价。** 服务从唯一的 `SIGTERM` 起自行决定何时升级，操作者不能仅用第二次 `systemctl stop` 表达“现在进入第 2 级”；该命令不会自动补信号。操作者若需要加速，只能另行明确执行 `systemctl kill --signal=… --kill-whom=…`，或服务另有控制协议。这个操作与 stop job 的 timeout 相互独立，必须定义接收者如何解释它。

**已确认的时间失效模式。** 任一级耗时超过预算或调度余量不足时，systemd 的 `FinalKillSignal` 可在 finalization 仍未完成时终止 cgroup；`KillMode=control-group` 还会把残留子进程一并终止。若内部计时器只在 event loop 正常调度时运行，阻塞、死锁或进程停顿可能让内部第 2、3 级根本来不及执行，最终仍只剩 systemd 的强制终止。若使用无限或无上限的 `EXTEND_TIMEOUT_USEC=`，则把上述强制 deadline 的保证改成服务自身的承诺，manager 不再提供固定上界。

## 本机实测的隔离与清理

实测只使用 `systemd-run --user` 创建的两个唯一 transient user unit，均以 `--collect` 创建；没有触碰 `4141`、`cc-daemon.service` 或任何既有 unit。每个 probe 使用唯一的 `/tmp/<unit>.py` 和 `/tmp/<unit>.log`，结束时删除这两个精确路径，并执行 `systemctl --user stop --no-block` 与 `reset-failed`。第二个 probe 因特意捕获了 `FinalKillSignal=SIGUSR2`，额外仅对它自身发送 `SIGKILL` 以完成清理。两者最终均观测为 `inactive`。

## 复核命令与未能证实项

本次实际使用的核心只读取证命令如下；man 输出在报告的引用段落中摘录：

```bash
cd /home/xp/src/ghc-api-proxy-py && systemctl --version
cd /home/xp/src/ghc-api-proxy-py && TERM=dumb MANWIDTH=110 man -P cat systemd.kill | col -b
cd /home/xp/src/ghc-api-proxy-py && TERM=dumb MANWIDTH=110 man -P cat systemd.service | col -b
cd /home/xp/src/ghc-api-proxy-py && TERM=dumb MANWIDTH=110 man -P cat systemctl | col -b
cd /home/xp/src/ghc-api-proxy-py && nl -ba contrib/systemd/ghc-api-proxy.service
cd /home/xp/src/ghc-api-proxy-py && nl -ba docs/.human-controlled/lifecycle.md
cd /home/xp/src/ghc-api-proxy-py && nl -ba src/app/lifecycle/rolling/runtime.py
cd /home/xp/src/ghc-api-proxy-py && nl -ba src/app/lifecycle/shutdown.py
```

本报告的问题中没有保留为「未能证实」的项。限制是：实测只在本机 systemd 255 的 user manager 执行，生产 system manager 的实时状态和版本未被触碰或断言；关于其标准语义的结论以本机对应版本的 manpage 为依据。
