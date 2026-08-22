# 候选：既有实现与用户文档的相容性对照

> 本文是候选素材，无效力。
>
> 依据 `docs/.human-controlled/README.md:3` 的规则：**已经存在的内容，如果与本系列文档相违背，都需要用户再次裁决；不矛盾的内容，都继续使用，用户将按需追认。** 本文逐条对照，把「需再次裁决」的项挑出来。
>
> **2026-08-22 更新**：原对照基准 `MAIN.md` 已在提交 `2afa0c4` 里被拆成 `module-org.md` / `api.md` / `request-pipeline.md` / `message-translation.md` 等多份，`model-translation.md` 也已更名为 `message-translation.md`。本文所有指针相应重指；同时按 `.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md` 撤下了因 rolling 删除而失效的条目。
>
> 现对照基准：`docs/.human-controlled/` 下的 `README.md`、`api.md`、`module-org.md`、`request-pipeline.md`、`message-translation.md`、`lifecycle.md`、`config.example.yaml`。

## 一、需要用户再次裁决（与文档相违背）

### C-3 平滑重启机制在两条路径上的取向相反

**文档（`lifecycle.md:28-35`，standalone）**：平滑重启用 `SO_REUSEPORT`，新进程 `--restart` 启动后向旧进程发 SIGUSR2。

**现状**：standalone 侧已实际使用 `SO_REUSEPORT`（`src/app/lifecycle/listener.py` 的 `bind_listener`）；systemd 路径按 `lifecycle.md:44` 走 socket activation，仍不使用它，当时的 PoC 结论是该路径**明确不使用**它——那条路径要求「复制同一个 fd 得到同一 listener identity」，而 `SO_REUSEPORT` 双 bind 得到的是**不同的** socket。

**这不一定是冲突**：两条路径要的语义本就相反——standalone 要两个进程各自监听（新旧并存），systemd 要同一 listener 被交接。但两者都叫「平滑重启」，容易在后续被误当成同一机制去「统一」。

**待裁决**：是否确认两条路径各用各的机制、且不做统一？（`lifecycle.md` 至今未就此表态。）

## 二、文档要求但当前尚不存在（缺口，非冲突）

| 项 | 文档出处 | 现状 |
|----|---------|------|
| `--systemd` 参数 | `lifecycle.md:42`，写法已定为 `start --systemd` | **仍不存在**：`src/app/cli.py` 的 `start` 只有 `--fd`（`cli.py:202`），systemd 路径目前走 `start --fd 3`。仍等 C-2——新建该入口必须决定它的关闭语义 |
| `history` 的五字段与 `observability` 一节 | `api.md:17-18` 列了它们的端点，`config.example.yaml` 无对应配置 | **用户 2026-08-17 裁决先切入口、这些暂时失效**。旧 `AppSettings` 侧的实现都还在，只是新路径没有配置去驱动它们；`--verbose`／`--manual`／`--rate-limit`／`--github-token`／`--account-type` 现在会打印一条「本路径无效」的警告而非静默忽略。**2026-08-22 收窄**：原文写的是四节，其中 `approval` 与 `tokenization` 的端点已在 `api.md:20-21` 被用户划掉标注「暂不支持」，不再算缺口。逐项细目见 [config-migration-gaps.md](config-migration-gaps.md) 第一节 |
| 持久化状态的平滑重启交接 | `lifecycle.md:36-38` 标记为 TODO | 未定义 |

**2026-08-22 撤下的一行：cgroup 资源限制的「rolling 一侧」。** 原文记「单进程 systemd 服务已具备，缺的只是 rolling 一侧的 `ghc-api-proxy-rolling.slice`」。rolling 已于 2026-08-19 整体删除（见 [rolling-removal.md](rolling-removal.md)），`git ls-files contrib/systemd` 现在只剩 `ghc-api-proxy.service`、`.slice`、`.socket` 与 `install-user.py`，不存在 rolling slice，缺口随之消失。`lifecycle.md:61-63` 要求的单独 cgroup 限制已由 `contrib/systemd/ghc-api-proxy.slice` 满足（`MemoryHigh=1G`／`MemoryMax=2G`／`CPUQuota=200%`／`TasksMax=256`），service 以 `Slice=` 加入（`contrib/systemd/ghc-api-proxy.service:29`），覆盖测试在 `tests/systemd/test_systemd_units.py:288-292`——原文引的 `tests/smoke/` 目录已不存在，测试现在在 `tests/systemd/`。

## 三、已解决的历史问题

下表混着两种来源，**逐条标注**：`文档` = 写在 `docs/.human-controlled/` 里，可自行复核；`会话` = 用户在对话中直接口头裁决，仓库内没有一手出处，转述如有出入以用户为准。日期见「裁决」列，目前跨 2026-08-16 与 2026-08-17 两天。

**记录裁决时，用户裁到哪里就写到哪里，实施选择必须分开写明。** 一条实证：随包配置那行原先把我自己起的文件名写在裁决里，一位评审据此认定「用户指定了该文件名、代码必须改回去」——它读到的是我掺进去的东西，不是用户说的话。转述掺进实现选择，下游就会把它当成不可动的约束。

| 原问题 | 用户裁决 | 来源 |
|--------|----------------------|------|
| 订阅者抛异常触发控制流，是否需要限定为闭集 | **采纳闭集**：已知异常（`UpstreamError`、`UpstreamTimeout`、`UpstreamRateLimit`、`PipelineRetry`、`PipelineAbort`）按内置逻辑处理；**未知异常总是中止** | 文档（`request-pipeline.md:19`） |
| Responses WebSocket 的运行时处置 | 代码与测试**均保留**，**不最终接线**；陈旧处可适当注释 | 文档（`api.md:8,12`、`ghc-api.md:28,31`） |
| generic 上游是否保留 | 以 `app.model_provider` 抽象层承载：GHC 只是提供方之一，未来可有其他提供方 | 文档（`module-org.md:15`） |
| 部署子系统的归属 | 已写入 `lifecycle.md`，模块名定为 `app.lifecycle`（非候选文档建议的 `app.deployment`） | 文档（`lifecycle.md:1`） |
| standalone 三级关闭 | 已按文档实现于 `app.lifecycle.standalone`，不再是缺口 | 文档（`lifecycle.md:18-22`） |
| `client_request_timeout` 的定名 | 定为 `client_delivery.client_request_deadline`，默认 3600 | 会话 ＋ 文档（`config.example.yaml:377`） |
| `app.model_provider` 抽象层 | 已建为 `src/app/model_provider/`，不再是缺口 | 文档（`module-org.md:15-16`） |
| `ghc-api-proxy` 命令入口 | 已加 `[project.scripts]`，不再是缺口 | 文档（`lifecycle.md:7`） |
| `--restart` 参数 | 已实现于 `start --restart`，走 pidfile ＋ SO_REUSEPORT | 文档（`lifecycle.md:33`） |
| keepalive `empty_text` 模式 | **退役**。依据：`copilot-api-js` 侧已确认最新版 Claude Code 修复了该类问题，不再需要这个变通 | 会话 |
| pm2 部署 | **暂不实现**。注意 `config.example.yaml:238,241` 仍在 `graceful_cleanup_timeout` 注释里提到 pm2 `kill_timeout`，两者并不冲突：不实现的是 pm2 集成，不是那条时限关系 | 会话 |
| `config.example.yaml` 中被注释掉的配置项 | **暂不实现**——用户尚未决定 | 会话 |
| 入口切换与运维配置节 | **先切入口**（2026-08-17）：`cli.py` 的 `start` 改走新 `ProxyConfig` ＋ `create_pipeline_app`，接受 `history` 的五个字段、`approval`、`observability`、`tokenization` 四项**暂时失效**。我曾建议先纳入这四节，用户重裁为先切。**2026-08-22 追记**：其中 `approval` 与 `tokenization` 的端点此后被用户在 `api.md:20-21` 标注「暂不支持」，所以现在只剩 `history` 与 `observability` 两节算缺口 | 会话 ＋ 文档（`api.md:20-21`） |
| 无配置文件时启动不了 | **现在就做随包配置**（2026-08-17）。**用户裁决到此为止**——「包里预置一份可用配置，安装即可用」。以下是实施选择、不是用户裁决，可自由更改：文件名沿用 `app.config.loading` 早已期待的 `bundled-config.yaml`；它作为**每份用户配置的基底层**（不是缺省回退）；只写「没有它起不来」的项；`--generate-config` 产出该文件 | 会话 |
| C-1 退出时限公式 | **基数为单次上游上限、收尾时限 60s**（2026-08-17）。`TimeoutStopSec = upstream_request_deadline(1200) + graceful_cleanup_timeout(60) + 余量`。`config.example.yaml:243` 的 60 是对的；`lifecycle.md:59` 正文的「（30s）」与基数措辞 `client_request_timeout` 待用户改（见 [systemd-shutdown.md](systemd-shutdown.md) 第五节） | 会话 |
| C-2 systemd 侧的关闭级数 | **只做两级**（2026-08-17）。理由：systemd 无法原生驱动三级——`systemctl stop` 只发一次可处理信号，此后是不可捕获的 SIGKILL。故 `lifecycle.md:52-55` 现有的两级流程即为定案，**不引入时间驱动**。调研与被否决的三级方案留在 [systemd-shutdown.md](systemd-shutdown.md) 备查 | 会话 |
| C-4 平滑重启命令不可执行 | **改文档**（2026-08-17）：`lifecycle.md:33` 已改为 `uv run ghc-api-proxy start --restart`，顶层 CLI 不新增无子命令入口。同一裁决顺带定下 `--systemd` 的写法：`lifecycle.md:42` 为 `start --systemd` | 文档（`lifecycle.md`） |
| TLS 模式不匹配时的行为 | **让协议自然失败**（2026-08-17）：纯 TLS 端口收明文即 TLS 握手失败，纯明文端口收 ClientHello 按非法 HTTP 字节处置，**不为不匹配另写特例**。推论：首字节判别只在 `mode: both` 时进行 | 会话 |
| pidfile 的目录与命名 | **改为目录语义**（2026-08-22）：配置项由 `pidfile`（文件）改为 `pidfile_dir`（目录），默认文件名 `standalone-<端口>.pid`。同日另裁决三条实现行为，细目与仍未裁决的 `GHC_API_PROXY_PORT` 拼写见 [pidfile-port-scoping.md](pidfile-port-scoping.md) | 文档（`config.example.yaml:227-235`） |
| 代（generation）生命周期与滚动更新 | **删除**（2026-08-19）：保留优雅退出与无缝重启，不再提供回退机制。代码已删，归档分支 `archive/260819-rolling`。`lifecycle.md:65-89` 的对应整节仍在，等用户追认删除或改写为历史记录，见 [rolling-removal.md](rolling-removal.md) | 会话 |

### keepalive `empty_text` 退役的实际成本：零

该机制**从未接线**，退役不需要改动任何生产路径。三项复算：

- `rg -c 'stream_keepalive_mode|stream_keepalive_ping_sec' src`（排除 `settings.py`）→ 0，两个配置项除定义外无人读取
- `rg -n 'keepalive_stream|session_liveness_stream' src`（排除 `keepalive.py` 自身）→ 无命中，模块零生产调用者
- `src/app/streaming/keepalive.py` 只接受通用的 `heartbeat: bytes` 参数，**代码中不存在 `empty_text` 模式的实现**

`lib-survey/domain3` 把它记为「唯一能压住 300s watchdog 的机制、必须保留自研」，那是**设计裁决与实测记录，实现未落地**。本目录此前将其列为「重构不得动的红线」，属误判，已更正。

`keepalive.py` 本身**不随之退役**：它实现的通用心跳原语正是新规格 `client_delivery.sse_ping_interval` 所需要的，是待接线而非待废弃。

## 四、继续有效的既有裁决（与文档不矛盾）

以下与本系列文档无冲突，按 `README.md:3` 的规则继续使用，重构时必须承载：

块级缓冲与首块前不下发字节、capability fail-closed、reasoning carrier 的载体与基数规则、手动审批闸、自适应限流与 poisoned-thinking L2/L3 重试、post-commit 不得透明重放、双端点时默认 Messages、流式与非流式共享同一语义映射核心。

最后一条与 `message-translation.md:3`（原 `model-translation.md`，2026-08-22 更名）的「输入格式 <-> 中间表示 <-> 上游模型格式」同向，且中间表示的设计**强化**了它。
