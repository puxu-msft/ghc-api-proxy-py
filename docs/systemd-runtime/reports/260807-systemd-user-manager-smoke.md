# systemd user-manager / cgroup 隔离可行性验证

## 结论

**总体判定：BLOCKED。** 在 `main` 的 `e9fb2771d6e040c761bb4074e3fcf2547caece28` 上，helper 渲染、临时目录 apply、动态 loopback 端口 unit 校验，以及不经过 systemd manager 的 inherited-fd、liveness/readiness、graceful shutdown 关键路径均通过；但完全隔离的 `systemd --user` 在创建其临时 `XDG_RUNTIME_DIR/systemd/private` control socket 前静默以退出码 `1` 结束。因此，本轮没有连接现有 user manager，也没有以宿主 user manager 代替 fixture；真实 `daemon-reload`、socket/service 启动、systemd fd inheritance、effective cgroup path/limits、systemd restart 与 graceful stop 均未执行，不能判定为通过。

这不是已证实的生产代码缺陷。阻断发生在独立 user manager fixture 启动阶段，且 manager 没有输出诊断文本；根因仍未定位。若要完成 live 验收，应换到允许启动独立 user manager、并向该 manager 委派 cgroup v2 子树的受控容器或虚拟机，而不是复用当前登录会话的 user manager。

## 冻结的验收矩阵

| 验收项 | 判定 | 实证 |
|---|---|---|
| 只使用临时 `HOME`、`XDG_CONFIG_HOME`、`XDG_STATE_HOME`、`XDG_RUNTIME_DIR` 与 private session bus | 通过 | 三轮 manager 探针均在 `/tmp/ghc-user-*` 下创建 fixture；private dbus socket 成功建立，未向宿主 bus 发控制命令。 |
| helper 渲染并 apply 到临时目录 | 通过 | `install-user.py --check --apply` 返回 `0`，写出 `ghc-api-proxy.service`、`.socket`、`.slice` 三个 `0644` 文件；输出仅含 `CHECK` 与 `APPLIED`。 |
| 动态 loopback 端口副本通过 unit 校验 | 通过 | 临时 socket unit 将固定端口替换为候选动态端口 `42701` 后，`systemd-analyze --user verify` 返回 `0`；该端口仅属于临时副本，未改仓库文件。此前独立 helper 探针使用过另一候选端口 `49673`，同样未触及 `4141`。 |
| 独立 user manager 可控，随后执行 `daemon-reload` | **BLOCKED** | private dbus fixture 可用，但 `systemd --user --unit=basic.target` 返回 `1`，且临时 `systemd/private` 不存在。安全门未通过，因此没有运行任何 `systemctl --user` 控制动作。 |
| 由独立 manager 启动 socket/service，并验证 systemd fd inheritance | **BLOCKED** | manager control socket 不存在，未启动 unit。作为非等价的支持证据，直接 inherited-fd 关键测试通过；它不能替代真实 socket activation 验收。 |
| 通过 manager 启动的实例验证 liveness/readiness | **BLOCKED** | manager 未启动 service。作为非等价的支持证据，直接 inherited-fd 测试的 liveness/readiness 路径通过。 |
| 读取 service 的 effective cgroup path 与实际 limits | **BLOCKED** | 没有 manager 启动的 service PID，故没有可读取的 service cgroup。临时 unit 的静态 `MemoryHigh=1G`、`MemoryMax=2G`、`CPUQuota=200%`、`TasksMax=256` 已确认，但静态文本不等于 effective limits。 |
| systemd restart 与 graceful stop | **BLOCKED** | manager 未启动 service，未执行 restart/stop。作为非等价的支持证据，应用直接 inherited-fd graceful shutdown 与短超时取消路径通过。 |
| 清理并 `wait/reap` fixture | 通过 | 最终探针记录 manager `wait/reap rc=1`、dbus `wait/reap rc=0`、临时根目录已删除；收尾扫描未发现 `/tmp/ghc-user-*` 残留。 |

## 实际执行与结果

### 隔离基线

- 仓库与提交：`/home/xp/src/ghc-api-proxy-py`，`main`，`e9fb2771d6e040c761bb4074e3fcf2547caece28`。开头与收尾均重新读取分支和 HEAD，结果一致。
- 宿主进程位于 cgroup v2 的 `0::/init.scope`。只读取了 `/proc/1/comm`、`/proc/self/cgroup`、namespace 与 mount 信息；未调用宿主 `systemctl --user` 或 system `systemctl`。
- 当前 shell 原有 `XDG_RUNTIME_DIR=/run/user/1000` 与宿主 session bus 地址仅用于确认风险边界；fixture 随后覆盖为 `/tmp` 下的新路径。
- 没有使用 `sudo`，没有修改全局配置，没有启动或停止现有 user/system unit，没有对旧 Bun 或任何 Bun 进程发送 signal。

### helper 与 unit

执行范围为真实 helper 加临时 XDG 树：

- `install-user.py --check --apply`：退出码 `0`。
- apply 结果：三个预期 unit，模式均为 `0644`。
- 临时 socket unit：`ListenStream=127.0.0.1:42701`。
- 动态副本 `systemd-analyze --user verify`：退出码 `0`，无错误输出。
- 关键合同同时存在：`ExecStart=... -m app start --fd 3 --graceful-timeout 300`、`Restart=on-failure`、`KillSignal=SIGTERM`、`KillMode=control-group`、`TimeoutStopSec=330s`、`Slice=ghc-api-proxy.slice`、`Accept=no`、`FileDescriptorName=http`。
- helper 和 verify 完成后，临时根目录已删除。

### 独立 manager / dbus fixture

最终探针使用新的临时 runtime/home 和 private dbus：

- 候选动态 loopback 端口：`59807`，未绑定为长期 listener，也未使用 `4141`。
- private dbus socket：成功建立；dbus PID 为该探针直接创建并持有。
- `systemd --user --unit=basic.target --log-target=console --log-level=debug`：退出码 `1`。
- 临时 `XDG_RUNTIME_DIR/systemd/private`：未创建。
- manager stdout/stderr：空。
- `strace`：环境未安装，因此没有 syscall trace；本项未验证。
- 安全门结果：未运行 `systemctl --user daemon-reload`，未 start socket/service，也未连接宿主 user manager。
- 回收：manager 已 `wait/reap`，退出码 `1`；dbus 收到仅针对其 fixture 进程组的终止信号后已 `wait/reap`，退出码 `0`；临时根目录删除成功。

另一次同构诊断中，`systemd --user --test --unit=basic.target` 返回 `0`，说明 unit graph 可离线解析；实际 manager 仍返回 `1` 且没有 private socket。`--test` 成功不能证明 manager 能启动，也不能解除本轮 `BLOCKED`。

### 关键路径测试

执行：`tests/smoke/test_systemd_user_install.py` 的全部测试，加上 `test_inherited_listener_serves_ready_generic_upstream_and_persists_overrides` 与 `test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan`。

结果：`5 passed in 8.34s`，pytest 退出码 `0`。测试数量以两种不同原理核对：pytest 实际收集并执行五项；Python AST 统计 installer 文件有三个顶层 `test_*`，再加两个显式 node ID，共五项。

这些测试支持 helper 惰性、真实 `systemd-analyze` 校验、fd 3 继承、liveness/readiness、状态路径覆盖，以及 graceful shutdown 行为，但它们没有经过本轮独立 user manager，故不用于宣称 live systemd/cgroup 项通过。

## 隔离与清理审计

- 本轮唯一仓库写入应为本报告。
- 所有实验产物均位于名称受控的 `/tmp/ghc-user-*` 目录；收尾扫描结果为无残留。
- 没有将 helper apply 到真实 `~/.config/systemd/user`。
- 没有触碰生产 `127.0.0.1:4141`；动态候选端口只用于临时 unit 副本与诊断记录。
- 没有修改、reload、start、restart 或 stop 现有 user/system manager 下的任何 unit。
- 没有向旧 Bun 发 signal；本轮未启动 Bun。

## 未验证项与后续入口

下列项目因独立 manager 启动失败而统一保持为未验证，不得从静态 unit 或直启测试外推：

1. `systemctl --user daemon-reload` 对临时 manager 生效。
2. `.socket` 激活 `.service` 并将 listener 作为 fd 3 交付。
3. manager 启动实例的 liveness/readiness。
4. service 的实际 cgroup 路径以及 `memory.high`、`memory.max`、`cpu.max`、`pids.max` effective 值。
5. `Restart=on-failure` 的真实重启行为。
6. `systemctl stop` 下 `SIGTERM`、graceful timeout、`KillMode=control-group` 与最终 inactive 状态。

建议下一次在可销毁的 systemd-nspawn 容器或虚拟机中复验，并确保测试用户拥有独立 login session/user manager 与 delegated cgroup v2 子树。仍应使用动态 loopback 端口，保留“private control socket 出现后才允许 systemctl”的安全门，并在退出路径逐个 wait/reap manager、dbus 与 service 进程。不要在当前环境退回使用宿主 user manager。
