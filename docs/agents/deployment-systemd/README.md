# systemd socket activation 与 cgroup 运行模板

## 目标与边界

`contrib/systemd/` 提供一组 system-level 模板，用 systemd 持有 TCP 监听 socket，并把继承的文件描述符 3 交给 `ghc-api-proxy start --fd 3`。服务进程重启时，`.socket` 单元继续持有监听 socket；重启窗口中新建立但尚未被应用接受的连接可留在 listen backlog，待新进程启动后接受。

`--fd` 模式下监听地址完全由 socket 的创建者决定，因此 CLI 会拒绝同时传入 `--host` 或 `--port`。修改监听地址应编辑 `.socket` 的 `ListenStream`，而不是修改应用配置中的 host/port。

这不是双实例 rolling restart，也不承诺所有连接 zero-downtime：

- 已被旧进程接受的 HTTP、SSE 或 WebSocket 连接仍归旧进程所有。SIGTERM 后 Uvicorn 会停止接受新连接并等待现有连接完成，然后执行 FastAPI lifespan 清理。
- systemd 的单个 `.service` 重启是先停旧进程、再启动新进程。模板把 Uvicorn graceful timeout 显式设为 `300s`，并把 `TimeoutStopSec=330s` 设为严格更大的 manager deadline；若旧连接和 lifespan cleanup 未能在该窗口内结束，systemd 会终止该 cgroup 中的剩余进程，这些连接会中断。
- listen backlog 只能覆盖尚未 accept 的连接，并且容量有限。过载或重启时间过长时，客户端仍可能连接失败或超时。
- 真正让已有长连接跨版本无损迁移，或让新旧应用实例重叠服务，需要后续实现双实例／rolling 编排、readiness 切流和共享状态并发规则；本模板没有伪装成该能力。

## 文件

- `ghc-api-proxy.socket`：默认监听 `127.0.0.1:4141`，`Accept=no`，由 systemd 持有 socket。
- `ghc-api-proxy.service`：以 `Type=exec` 启动单个 Uvicorn 进程。`Type=exec` 能让解释器不存在、无执行权限等 `execve()` 前后的启动错误直接表现为 start 失败，但不等待 FastAPI lifespan 完成，也不代表应用已 ready。当前应用没有实现 `sd_notify(READY=1)`，因此不能使用 `Type=notify`。
- `ghc-api-proxy.slice`：为服务建立专属 cgroup v2 资源边界。模板使用 `MemoryHigh=1G`、`MemoryMax=2G`、`CPUQuota=200%` 和 `TasksMax=256`，部署前应按主机容量和负载调整。

## 安装前准备

模板假定：

- 仓库部署到 `/opt/ghc-api-proxy`。
- 虚拟环境解释器为 `/opt/ghc-api-proxy/.venv/bin/python`。
- 服务账户与组均为 `ghc-api-proxy`。
- 可选环境文件为 `/etc/ghc-api-proxy/ghc-api-proxy.env`。

如果实际路径或账户不同，复制模板后先修改 `User`、`Group`、`WorkingDirectory`、`ExecStart` 和 `Documentation`。不要直接安装未经本机调整的模板。

环境文件采用逐行 `NAME=value` 格式，可设置项目已有的 `GHC_` 配置，例如：

```text
GHC_CONFIG=/etc/ghc-api-proxy/config.yaml
GHC_OBSERVABILITY__LOG_LEVEL=INFO
GHC_HISTORY__DB_PATH=/var/lib/ghc-api-proxy/history.db
GHC_TOKENIZATION__STATE_PATH=/var/lib/ghc-api-proxy/tokenization.json
```

应用 graceful timeout 的配置键是 `shutdown.graceful_timeout`，环境变量形式为 `GHC_SHUTDOWN__GRACEFUL_TIMEOUT`，CLI override 为 `--graceful-timeout`。它直接传给 Uvicorn 的 `timeout_graceful_shutdown`，约束 SIGTERM 后等待在途任务完成的应用窗口；FastAPI lifespan cleanup 仍由 Uvicorn 随后的 shutdown 生命周期执行。Systemd 模板在 `ExecStart` 中显式传入 `--graceful-timeout 300`，因此该 CLI 值优先于环境文件中的同名设置；模板没有把 `GHC_SHUTDOWN__GRACEFUL_TIMEOUT` 放进环境文件示例，以免制造一个看似可覆盖、实际被 CLI 固定值遮蔽的旋钮。部署者若调整模板 timeout，必须同时保持 `TimeoutStopSec > --graceful-timeout`；仓库 smoke 会把 CLI 值、Python 默认常量和 `TimeoutStopSec` 的 `30s` manager 余量机械对账，任一处漂移都会失败。

`HistoryConfig.db_path` 与 `TokenizationConfig.state_path` 在应用配置中允许为空，此时会回退到用户数据目录。system service 不应依赖服务账户具有可写 HOME，因此模板通过 `StateDirectory=ghc-api-proxy` 创建并授权 `/var/lib/ghc-api-proxy`，同时用 `Environment=` 把这两个路径显式设置到该目录。`StateDirectoryMode=0700` 让默认状态目录仅服务账户可遍历，`UMask=0077` 让应用创建的 History 数据库、SQLite WAL／SHM、tokenization 原子写临时文件与最终文件不带 group／other 权限；当前 writer 在该模板下创建的这些文件 mode 均为 `0600`。

上面的 EnvironmentFile 示例写出了相同值；需要改用其他目录时，可以在环境文件中覆盖 unit 默认值。覆盖目录必须由管理员预先创建、归服务账户独占并设为 `0700` 或等价的最小权限，已有数据库、WAL／SHM、tokenization 临时文件与最终文件也必须保持 `0600` 或等价的无 group／other 权限。`UMask=0077` 只约束服务进程新建的文件，不会自动收紧既有目录或文件。

机密 token 也可经该文件提供，但应限制文件权限并只允许服务账户读取。模板中的 `EnvironmentFile=-...` 前缀表示文件缺失时仍允许启动。

## 安装与启动

以下步骤由管理员在目标主机执行；仓库本身不会自动安装或启动 unit：

1. 创建服务账户、部署目录、虚拟环境及配置文件，并确保服务账户能读取配置。默认状态目录由 `StateDirectory=ghc-api-proxy` 在 service 启动时以 `0700` 创建为 `/var/lib/ghc-api-proxy`；若在环境文件中覆盖状态路径，则另行创建归服务账户独占的 `0700` 目录，并确认其中既有状态文件不带 group／other 权限。
2. 将三个模板复制到 `/etc/systemd/system/`，按本机情况调整资源值和路径。
3. 让 systemd 重新加载 unit，并启用、启动 `ghc-api-proxy.socket`。启用 socket 即可按首个连接拉起 service；若希望预热应用，可另外显式启动 service。
4. 用 `/health/liveness` 和 `/health/readiness` 验证应用，而不是只检查进程状态。`Type=exec` 的 service 显示 active 不能替代 readiness。

启动顺序必须保证 `.socket` 已 active。日常应用重启只重启 `ghc-api-proxy.service`，不要同时停止 socket，否则会丢失由 systemd 持有监听端口这一层保护。修改 `.socket` 的监听地址则必然需要重启 socket，并形成监听窗口。

当前应用没有配置热重载合同，unit 也不提供 `ExecReload`。配置或代码变更只支持 restart；不要用 SIGHUP 或伪 reload 绕过上述 socket activation 与 readiness 流程。

## 关闭与故障恢复语义

- `KillSignal=SIGTERM` 触发 Uvicorn 的 graceful shutdown 和 FastAPI lifespan 清理。当前清理会拒绝待审批、刷新 tokenization 状态、关闭 History、关闭 upstream clients，并取消后台任务。
- `--graceful-timeout 300` 传给 Uvicorn 的 `timeout_graceful_shutdown`。超过该应用窗口仍未完成的在途任务会被 Uvicorn 取消，随后继续执行 FastAPI lifespan cleanup；当前没有把历史四阶段 `ShutdownManager` 接入生产信号路径，也不宣称支持重复信号升级。
- `KillMode=control-group` 向该 service cgroup 中的所有进程发送 SIGTERM，让主进程与未来可能出现的协作子进程共享 graceful shutdown 窗口；`TimeoutStopSec=330s` 比应用 timeout 多 `30s`，为 Uvicorn 结束 server lifecycle、执行 lifespan cleanup 和进程退出保留 manager 余量。超过 systemd deadline 后，systemd 强制清理剩余进程。
- `Restart=on-failure` 会在异常退出后重启；正常停止不会形成重启循环。socket 保持 active 时，新连接也可再次激活 service。
- `.slice` 的限制作用于该 slice 下的工作负载。`MemoryHigh` 是回收压力阈值，`MemoryMax` 是硬上限；触及硬上限可能触发 cgroup OOM，随后由 `Restart=on-failure` 恢复进程，但在途连接仍会中断。

## 无需 root 的仓库验证

`tests/smoke/test_systemd_units.py` 解析模板并核对 socket fd 接线、状态目录、最小权限、关闭合同与 cgroup 关键字段；它从 `ExecStart` 反解 application timeout，并与 Python 默认常量、`TimeoutStopSec` 和 `30s` manager 余量机械对账。它还以 unit 声明的 mode／umask 运行真实 History 与 tokenization writer，核对状态目录、数据库、WAL／SHM、原子写临时文件和最终文件的实际 mode。运行态 smoke 由父进程创建真实 TCP listener 和预连接 backlog，在无可写 HOME 的环境中把 listener 交给应用 fd 3，并连接受控 generic upstream，验证 readiness 200、真实 Anthropic 请求、EnvironmentFile 等价路径覆盖、SIGTERM 清理，以及 History 与 tokenization 状态均落到覆盖目录。独立短 timeout probe 使用 `--graceful-timeout 1` 阻塞一个真实在途请求，发送 SIGTERM，并断言 Uvicorn timeout 分支、lifespan cleanup 和进程退出均发生。`tests/unit/test_cli.py` 核对 `--fd` 与 graceful timeout 被传给 Uvicorn，并拒绝 fd 0。测试不安装 unit、不连接 systemd，也不需要 root。
