# private `systemd --user` 静默退出诊断

## 结论

**判定：当前 WSL 实例中的这个 VS Code 调用上下文，不支持在“不连接现有 user manager、不使用 sudo”的约束下启动完全独立的第二个 `systemd --user`。** 这不是“WSL 没有 systemd”：PID 1 确实是 systemd，现有 `user@1000.service` manager 也确实运行在已委派的 cgroup 子树中。阻断点是当前调用进程位于 root 所有且不可写的 `/init.scope`，没有可供新 manager 管理子进程的 delegated cgroup 子树；新建 user+cgroup namespace 只改变视图，未获得 cgroup 写权限。

干净临时 XDG 树和 private D-Bus 均成功建立，但 `/usr/lib/systemd/systemd --user --unit=basic.target` 仍在创建临时 `XDG_RUNTIME_DIR/systemd/private` 前以退出码 `1` 结束。强制 console debug 日志、进程对应 journal 和 private D-Bus 日志均为空，manager 已由直接父进程 `wait` 回收。因此，**确切的 systemd 内部失败位置仍未定位**；本报告不把 cgroup 条件误写成已由错误消息或 syscall trace 直接证明的唯一内部根因。

## 诊断矩阵

| 诊断项 | 结果 | 实证与边界 |
|---|---|---|
| WSL 与 systemd 是否可用 | 是 | `uname -r` 与 `/proc/version` 均给出 `6.18.33.2-microsoft-standard-WSL2`；`/etc/wsl.conf` 含 `systemd = true`；`/proc/1/comm` 为 `systemd`。这排除“WSL 未启用 systemd”，不证明任意位置都能再启动一个 user manager。 |
| systemd 版本 | 已核对 | `systemd --version` 与 `dpkg-query -W systemd` 均给出 `255.4-1ubuntu8.16`。 |
| 当前会话必要环境 | 存在 | 宿主 shell 有 `XDG_RUNTIME_DIR=/run/user/1000` 和 `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`。private probe 未继承这两个值，而是覆盖为受控临时路径。 |
| private runtime-dir | 可建立 | 临时 `HOME`、`XDG_CONFIG_HOME`、`XDG_STATE_HOME`、`XDG_RUNTIME_DIR` 均创建为当前用户所有的 `0700` 目录。 |
| private D-Bus | 可建立 | `dbus-daemon --session --nofork` 成功创建临时 Unix socket 并打印其 private 地址；bus stderr 为空。probe 没有连接 `/run/user/1000/bus`。 |
| private manager | 失败 | 干净环境中的 `systemd --user --unit=basic.target --log-target=console --log-level=debug` 被直接 `wait`，退出码为 `1`；临时 `systemd/private` socket 不存在。 |
| 诊断输出 | 仍为空 | manager stdout/stderr 被重定向到临时 console 日志，内容为空；按短命 manager PID 查询 journal，内容为空；private D-Bus 日志也为空。首次尝试的 `SYSTEMD_LOG_TARGET=file:<path>` 不受 systemd 255 支持并产生“Failed to parse log target”，该次结果已排除，未用于静默退出结论。 |
| 当前 cgroup 是否可委派 | 否 | `/proc/self/cgroup` 给出 `0::/init.scope`；`/sys/fs/cgroup/init.scope/cgroup.procs` 为 root 所有的 `0644`，当前用户的 `-w` 检查为否。 |
| 现有 user manager 是否有委派子树 | 是，但禁止复用 | 现有 manager 的 `/proc/<pid>/cgroup` 位于 `/user.slice/user-1000.slice/user@1000.service/init.scope`；其父级 `user@1000.service` 目录和 `cgroup.procs` 为 UID 1000 所有，当前用户的 `-w` 检查为是，且 `cgroup.subtree_control` 含 `cpu memory pids`。只读取了元数据，未向现有 manager、bus 或 cgroup 写入。 |
| 无特权 namespace 能否补足委派 | 否 | `unshare --user --map-root-user --cgroup` 可执行，但 namespace 内 `/sys/fs/cgroup/cgroup.procs` 的 `-w` 检查仍为否；namespace 只能重映射当前 cgroup 视图，不能自行授予 delegated subtree。 |
| 该启动形态是否是本机 systemd 的常规契约 | 否 | 本机 `systemd(1)` 说明 user manager 通常由 `user@.service` 自动启动；`user@.service(5)` 说明 PID 1 以 `user@UID.service` 启动 user manager；`systemd.resource-control(5)` 说明 `Delegate=` 才允许被委派方管理其子树。当前 probe 刻意绕开 PID 1 和现有 `user@1000.service`，因而没有获得这条委派链。 |

## 已排除与未证明

已排除：

- 不是 WSL 未启用 systemd。
- 不是 `XDG_RUNTIME_DIR` 缺失或权限明显错误。
- 不是 private D-Bus 未创建或地址未传入。
- 不是 debug 输出只被 journald 吞掉：console 与按 PID 查询的 journal 均为空。
- 不是 `systemd --user --test` 所覆盖的 unit graph 解析问题；既有 smoke 已证明 `--test` 返回 `0`，但该模式不启动 manager。

仍未证明：

- 未取得 systemd 内部具体失败函数、errno 或 syscall；本机没有 `strace`，且不得用 sudo 安装。
- 未证明“cgroup 不可写”是静默 `rc=1` 的唯一内部触发条件。已证明的是：当前调用上下文缺少本机 systemd 文档所描述的 manager 启动与 cgroup delegation 链，并且允许的无特权手段不能补足它。
- 未验证真实 `daemon-reload`、socket activation、fd inheritance、effective cgroup limits、restart 或 graceful stop；private control socket 门未通过，因此这些项目继续保持 `BLOCKED`。

## 下一最小动作

**不要在当前 WSL 会话继续变换 env 或重试 standalone `systemd --user`。** 下一最小动作是把同一 live smoke 移到一个可销毁、以 systemd 为 PID 1 的 VM 或容器实例中，并让 PID 1 为专用测试 UID 正常创建 `user@UID.service` 与 delegated cgroup v2 子树；随后只在该隔离实例内连接这个专用测试 manager。仍应使用动态 loopback 端口，并保留“private control socket 出现后才允许 `systemctl`”的门。

如果下一轮目标只是定位本次 `rc=1` 的精确 syscall，而不是完成 live smoke，则最小动作是在上述可销毁实例中预装 `strace` 后复现；不应为了诊断而修改当前 WSL 的全局包或接管现有 manager。

## 安全与清理审计

- 未调用宿主 `systemctl --user` 或 system `systemctl`，未连接现有 user bus，未写现有 cgroup。
- 未使用 `sudo`，未访问 `127.0.0.1:4141`，未启动或发送 signal 给 Bun。
- 所有 private D-Bus 与 manager 进程均为本轮直接创建；manager 已 `wait` 为 `1`，D-Bus 收到仅针对其 PID 的 `SIGTERM` 后已 `wait` 为 `0`。
- 更正后的 `compgen` 残留扫描结果为 `LEFTOVER=none`，进程扫描结果为 `DIAG_PROCESSES=none`。此前一次 shell glob 检查把未展开的字面模式误报为残留，该错误 probe 已废弃，不作为证据。
- 所有实验日志和 runtime 树均位于 `/tmp/ghc-systemd-*` 并已删除；仓库中的唯一预期写入是本报告。

## 证据锚点

诊断绑定到仓库 `/home/xp/src/ghc-api-proxy-py` 的 `main`，HEAD 为 `e9fb2771d6e040c761bb4074e3fcf2547caece28`。HEAD 由 `git rev-parse HEAD` 与 `git log -1 --format=%H` 交叉核对一致。该提交与原 smoke 报告的锚点一致。
