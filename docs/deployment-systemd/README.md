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

## Rootless user unit helper

`contrib/systemd/install-user.py` 为当前用户渲染独立的 `.service`、`.socket` 与 `.slice`，不机械复制 system-level 模板。默认动作固定为 dry-run，只把三份 unit 打印到 stdout，不创建目录、不写 unit，也不连接 user manager：

```bash
python contrib/systemd/install-user.py --check
```

`--check` 始终先执行内置文本合同检查；能找到 `systemd-analyze` 时，再执行 `systemd-analyze --user verify`。工具缺失时会明确报告只完成文本检查，不会把它伪装成 systemd verify 通过。该检查不需要运行中的 user manager。

只有显式传入 `--apply` 才会把精确三份文件原子写入 `$XDG_CONFIG_HOME/systemd/user/`；未设置 `XDG_CONFIG_HOME` 时目标为 `~/.config/systemd/user/`：

```bash
python contrib/systemd/install-user.py --apply --check
```

重复 apply 相同内容会报告 `UNCHANGED`，不重写文件。helper 在 dry-run 和 apply 下都绝不调用 `systemctl`，不会执行 `daemon-reload`、enable、start、restart 或 stop；这些 manager 状态变更必须由用户在审阅生成文件后另行显式执行。helper 也不会创建或读取 EnvironmentFile，不会采集、复制或打印其中可能存在的 token。

默认使用 helper 所在仓库为 `WorkingDirectory=`，使用运行 helper 的 Python 解释器为 `ExecStart=`，显式传入与 system template 相同的 `--graceful-timeout 300`，并只引用 `$XDG_CONFIG_HOME/ghc-api-proxy/ghc-api-proxy.env` 作为可选 EnvironmentFile。可分别用 `--project-dir`、`--python` 与 `--environment-file` 传入其他绝对路径；路径中的空格、`%` 与非 ASCII 字符会按 systemd unit 语法转义。

user service 不含 system service 的 `User=`／`Group=`，也不使用 `/opt`、`/etc` 或 `/var/lib`。systemd 255 的 `systemd.exec(5)` 明确支持 user service 的 `StateDirectory=`：user manager 会在其 `%S` 状态根，即 `$XDG_STATE_HOME` 语义下创建 `ghc-api-proxy`；未显式设置 XDG 状态根时通常回退到 `~/.local/state`。生成的 service 因此保留 `StateDirectory=ghc-api-proxy` 与 `StateDirectoryMode=0700`，并把 History 和 tokenization 路径分别设置为 `%S/ghc-api-proxy/history.db` 与 `%S/ghc-api-proxy/tokenization.json`。helper 本身不创建该状态目录；它只会在 user manager 真正启动 service 时由 systemd 创建。

生成的 socket 仍监听 `127.0.0.1:4141`，并保留 `Accept=no` 与 fd 3 合同；其 `[Install]` 目标为 user manager 的 `sockets.target`。service 故意没有 `[Install]`，避免把“复制 unit”误解为“启用或启动 service”。资源限制仍由独立 user slice 声明，但 user manager 只能在自身被授予的 cgroup 和资源上限内施加这些限制；静态 verify 不证明 effective limits 已由内核采用。

## 关闭与故障恢复语义

- `KillSignal=SIGTERM` 触发 Uvicorn 的 graceful shutdown 和 FastAPI lifespan 清理。当前清理会拒绝待审批、刷新 tokenization 状态、关闭 History、关闭 upstream clients，并取消后台任务。
- `--graceful-timeout 300` 传给 Uvicorn 的 `timeout_graceful_shutdown`。超过该应用窗口仍未完成的在途任务会被 Uvicorn 取消，随后继续执行 FastAPI lifespan cleanup；当前没有把历史四阶段 `ShutdownManager` 接入生产信号路径，也不宣称支持重复信号升级。
- `KillMode=control-group` 向该 service cgroup 中的所有进程发送 SIGTERM，让主进程与未来可能出现的协作子进程共享 graceful shutdown 窗口；`TimeoutStopSec=330s` 比应用 timeout 多 `30s`，为 Uvicorn 结束 server lifecycle、执行 lifespan cleanup 和进程退出保留 manager 余量。超过 systemd deadline 后，systemd 强制清理剩余进程。
- `Restart=on-failure` 会在异常退出后重启；正常停止不会形成重启循环。socket 保持 active 时，新连接也可再次激活 service。
- `.slice` 的限制作用于该 slice 下的工作负载。`MemoryHigh` 是回收压力阈值，`MemoryMax` 是硬上限；触及硬上限可能触发 cgroup OOM，随后由 `Restart=on-failure` 恢复进程，但在途连接仍会中断。

## TLS（2026-08-22 加入，提交 `fb06150`）

> 本节是当日核实过的现状。**本文件其余部分含大面积过期内容**，见文末「已知过期」。

在此之前 `serve_inherited` **完全不读 `server.tls`**——没有 `ssl_certfile`／`ssl_keyfile`，也没有首字节路由。于是用出厂 `config.example.yaml`（`tls.mode: both`）跑 socket activation 的人得到的是纯明文，而且没有一行提示。项目的部署目标正是 systemd，所以这条影响的恰好是主路径。

现在证书对会交给 uvicorn：

| `server.tls.mode` | 继承监听器上的行为 |
|---|---|
| `false` | 明文，与之前完全一致（uvicorn 拿到 `None`） |
| `true` | HTTPS |
| `both` | **HTTPS，并打一行 `[WARN]` 说明降级** |

`both` 在这条路径上无法兑现：同端口双协议要读每个已接受连接的第一个字节再决定交给谁，那需要拥有 accept，而这条路上 accept 归 uvicorn（standalone 路径用 `FirstByteRoutingAdapter` 做这件事，它由 `StandaloneServer` 驱动，与这里不是同一套）。答 HTTPS 并说清丢掉了哪一半，好过两边都不答。

未指定 `cert`／`key` 时材料是自签名的，生成到 `tls_material_dir()`。**用户裁决（2026-08-22）：只要能接受 HTTPS 输入即可，不要求实际的安全验证。**

### 验证方式

`tests/systemd/test_systemd_pipeline_unit.py::test_an_inherited_listener_serves_the_real_api_over_https` 真起进程、真继承 fd、真握手，并且走的是 `POST /v1/messages` 而非健康检查——健康检查答在 headers 上、只回几个字节，证明不了请求体被读取、链被进入、流被写回，而那正是 TLS 之下会变的部分。

这需要一个比 `_CopilotFake` 更完整的上游：后者只手写了协议的两个 GET 部分。新增的 `_CassetteUpstream` **回放** `tests/int/cassettes/anthropic_to_responses_stream.json`，而不是手写第三部分——手写的替身编码的是「我们以为上游会发什么」，而那个信念正是藏缺陷的地方；回放还保住了录制时的块边界，这对块级交付有意义。

一个容易踩的点：入站模型必须落在支持 `/responses` 的上游模型上（cassette 目录里有 12 个，录制用的是 `gpt-5.5`）。用 `claude-*` 会走 Anthropic 透传，打到上游的是 `POST /v1/messages`，根本不经过 Responses 路径。

`test_systemd_units.py:303-318` 那两个 skip 的退出条件是「教它 `POST /v1/messages`」——这个能力现在有了，把它们的断言移过去并删掉旧的，尚未做。

## 已知过期（2026-08-22 实测，未修）

本文件写于早期，以下内容与当前代码不符，接手前请勿直接采信：

- 环境变量前缀已是 `GHC_API_PROXY_`，不是文中的 `GHC_`。文中示例 `GHC_CONFIG` / `GHC_OBSERVABILITY__LOG_LEVEL` / `GHC_HISTORY__DB_PATH` / `GHC_TOKENIZATION__STATE_PATH` 都不再成立，后两个对应的配置节也已不在 schema 里。
- graceful timeout 的配置键是 `graceful_cleanup_timeout`，不是文中的 `shutdown.graceful_timeout`。
- 测试路径是 `tests/systemd/`，不是文中的 `tests/smoke/`。
- 自 2026-08-22 起 `--fd` 拒绝的选项不止 `--host` / `--port`，还包括 `--restart` / `--pidfile-dir` / `--force-write-pidfile`；`--manual` / `--rate-limit` / `--github-token` 则改为播报警告而非拒绝。

## 无需 root 的仓库验证


`tests/smoke/test_systemd_units.py` 解析 system 模板并核对 socket fd 接线、状态目录、最小权限、关闭合同与 cgroup 关键字段；它从 `ExecStart` 反解 application timeout，并与 Python 默认常量、`TimeoutStopSec` 和 `30s` manager 余量机械对账。它还以 unit 声明的 mode／umask 运行真实 History 与 tokenization writer，核对状态目录、数据库、WAL／SHM、原子写临时文件和最终文件的实际 mode。运行态 smoke 由父进程创建真实 TCP listener 和预连接 backlog，在无可写 HOME 的环境中把 listener 交给应用 fd 3，并连接受控 generic upstream，验证 readiness 200、真实 Anthropic 请求、EnvironmentFile 等价路径覆盖、SIGTERM 清理，以及 History 与 tokenization 状态均落到覆盖目录。独立短 timeout probe 使用 `--graceful-timeout 1` 阻塞一个真实在途请求，发送 SIGTERM，并断言 Uvicorn timeout 分支、lifespan cleanup 和进程退出均发生。`tests/smoke/test_systemd_user_install.py` 使用临时 HOME／XDG 根验证 rootless helper 的 dry-run 零写入、apply 精确三文件、幂等、路径转义、真实 `systemd-analyze --user verify`、与 system template 相同的 graceful／manager deadlines，以及零 `systemctl` 调用。`tests/unit/test_cli.py` 核对 `--fd` 与 graceful timeout 被传给 Uvicorn，并拒绝 fd 0。测试不安装真实 unit、不连接 systemd manager，也不需要 root。
