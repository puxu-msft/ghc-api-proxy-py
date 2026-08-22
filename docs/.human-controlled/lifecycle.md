# `app.lifecycle` 生命周期管理：部署、关闭流程与重启流程

generation id 与 release id 的解析被 `tokenization` 快照等模块共用，宜置于跨域的 `core/`，不随 rolling 一起移动（可用 `rg -l 'generation_identity|release_identity' src` 复算消费者范围）。

支持如下几种部署方式：

- 直接运行：`uv run ghc-api-proxy`
- systemd-managed 服务：`systemctl start ghc-api-proxy`

## `app.lifecycle.standalone` 直接运行

关闭信号语义：

- SIGINT/SIGTERM 表示“来自正常关闭”；
- SIGUSR2 表示“来自平滑重启”；
- SIGKILL 表示“来自强制退出”。

关闭流程：

1. 收到 SIGINT/SIGTERM/SIGUSR2 信号，开始优雅关闭：停止 accept 新请求，正常等待现有请求清空（使用内置的请求超时机制）；
2. 又收到 SIGINT/SIGTERM 信号，中断现有请求，仍然等待请求清空；
3. 又收到 SIGINT/SIGTERM 信号，不再等待请求清空，执行状态持久化、资源清理等，然后退出。

注意，SIGUSR2 信号不会中断优雅关闭。

无论如何，不直接 `sys.exit` 等无防护强制退出。用户可选择 SIGKILL 强制退出。

如何实现平滑重启？

对于请求，

1. 进程通过 `SO_REUSEPORT` 监听同一端口；
2. 新进程通过 `uv run ghc-api-proxy start --restart` 启动，监听端口与旧进程一致，向旧进程发送 SIGUSR2 信号；
3. 旧进程收到 SIGUSR2 信号，开始优雅关闭；

对于持久化状态，

TODO

## `app.lifecycle.systemd` systemd-managed 服务

在 systemd service 中通过 `uv run ghc-api-proxy start --systemd` 作为启动命令。

使用 *socket activation* 保持监听端口连续：listener 由 systemd 持有，进程可以被替换而端口不中断。新请求会被新进程接收，旧进程仍然处理已接收的请求。

不追求所谓的“完整的零停机迁移”，该概念要求迁移已被旧进程 accept 的连接，但 socket activation 不这么做。我们也不需要。

为什么不直接用 `uvicorn.Server.serve()`？

它会安装自己的 TERM/INT handler、立即开始 accept、并在 shutdown 时消费既有的 graceful timeout，因此无法作为「停止 accept 但保住 listener」的路径。适配器自己安装 USR1/USR2/TERM/INT。

关闭流程：（TODO systemd 是否支持三级处理？）

1. 收到 SIGINT/SIGTERM/SIGUSR2 信号，开始优雅关闭：停止 accept 新请求，正常等待现有请求清空（使用内置的请求超时机制）；
2. 又收到 SIGINT/SIGTERM 信号，中断现有请求，不再等待请求清空，执行状态持久化、资源清理等，然后退出。

### 退出时限

systemd 要求提供 `TimeoutStopSec`，uvicorn 要求提供 graceful cap、lifespan cleanup。因此，不能像直接运行那样自动等待请求完成，应该把 `client_request_timeout` 与一个相对宽容的收尾超时（30s）之和作为上限使用，推导给出各值。

### 资源用量限制

要求使用单独的 cgroup 以限制 CPU 和内存用量。

### 代（generation）生命周期

2026-08-16：整个“代生命周期”与“滚动更新”的概念是对已经实现的功能的“追认”，该模块并非由用户设计，是 agent 拓展的功能。

一次滚动替换中，同时存在的每个服务进程称为一个 **generation**。

定义 `GenerationPhase`：

```
STARTING → READY_ACCEPTING → QUIESCING → DRAINED_STANDBY → STOPPING
                                                    ↘ FAILED
```

运行时信号语义：

- `QUIESCE` 停止 accept 但保住 listener；
- `RESUME` 从同一 fd 恢复；
- `TERMINATE` 在 operation 与 durability 清零后才执行 lifespan shutdown。

`DRAINED_STANDBY` 状态不仅是业务 operation 归零，还需要 durability barrier 确认（如 history）。

模块划分建议：

- `app.lifecycle.rolling` —— 控制器、持久状态、id 前沿、generation 进程入口
- `app.lifecycle.rolling.generation` —— 相位生命周期、准入、控制面服务端与客户端
