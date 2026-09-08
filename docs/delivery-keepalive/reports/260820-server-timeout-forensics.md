# 服务端取证：2026-08-20 客户端 256.9s 超时

调查时间：2026-08-20 07:57 ~ 08:00（本地时区 UTC+0，`date` 与 `ps` 输出一致）。
调查方式：只读。未修改任何源码、未触碰运行中的进程、未写入 `history.db`（复制到 `/tmp/hist-forensics.db` 后查询）。

被调查对象：

```
PID 169963  PPID 169960  TTY pts/49
启动 Thu Aug 20 07:44:42 2026
cmdline: /home/xp/src/ghc-api-proxy-py/.venv/bin/python3 /home/xp/src/ghc-api-proxy-py/.venv/bin/ghc-api-proxy start --port 4141
cwd     : /home/xp/src/ghc-api-proxy-py
exe     : ~/.local/share/uv/python/cpython-3.14.2-linux-x86_64-gnu/bin/python3.14
```

父进程 169960 是 `uv run ghc-api-proxy start --port 4141`，其父是 VS Code 集成终端的 bash（pts/49）。当前无 tmux server（`no server running on /tmp/tmux-1000/default`），因此 pts/49 的回滚缓冲无法取证。

---

## 1. 这个进程用的是哪份配置

### 1.1 加载路径（代码事实）

`start` 子命令走的是 `src/app/cli.py:_load_spec_config` → `app.config.loading.load_proxy_config`，即**新的 `ProxyConfig`**，不是 `app.config.loader.load_settings` 那份旧的 `AppSettings`。证据：`src/app/cli.py:104`、`src/app/cli.py:289`、`src/app/cli.py:340` 一带；`start` 最终调用 `run(partial(_serve_pipeline, proxy_config, options))`。

`load_proxy_config` 的五层优先级（低到高）：schema 默认值 → 随包 `bundled-config.yaml` → 用户配置文件 → `GHC_` 环境变量 → CLI 覆盖。

用户配置文件的定位顺序（`resolve_config_path`）：`--config` 显式路径 → `GHC_CONFIG` 环境变量 → `$CWD/config.yaml` → `spec_config_file_path()`，即 `platformdirs.user_data_path("ghc-api-proxy")/config.yaml`。

实测（在同一 cwd、同一解释器下调用同一个函数）：

```
resolved config path: /home/xp/.local/share/ghc-api-proxy/config.yaml
```

`--config` 未传（cmdline 只有 `start --port 4141`）；`GHC_CONFIG` 不在进程环境里；仓库根目录**没有** `config.yaml`。所以生效的用户配置文件就是 `/home/xp/.local/share/ghc-api-proxy/config.yaml`（1674 字节，mtime 2026-08-20 07:03，早于进程启动，因此进程读到的就是当前这一份）。

### 1.2 环境变量层为空

```
$ tr '\0' '\n' < /proc/169963/environ | grep -c '^GHC_'
0
```

进程环境里**一个 `GHC_` 前缀的变量都没有**。环境层对本次运行不贡献任何值。

### 1.3 各层实际提供了什么

```
BUNDLED top-level keys: ['default_model_provider', 'model_mappings', 'model_providers']
USER FILE top-level keys: ['model_mappings', 'model_translation']
```

`client_delivery`、`upstream_request_timeouts`、`upstream_transport` 这三节，**bundled 与用户文件都没有写**。CLI 只覆盖了 `server.port = 4141`。因此下面每一个值的来源层都是 **schema 默认值**（`src/app/config/schema.py`）。

### 1.4 实际生效值（用真实 loader 算出，非人工推导）

复算方式：`.venv/bin/python3 -c "from app.config.loading import load_proxy_config; load_proxy_config(cli_overrides={'server': {'port': 4141}})"`，cwd 与进程一致。

| 键（新 schema 的真实名字） | 生效值 | 来源层 |
|---|---|---|
| `client_delivery.sse_ping_interval` | **15** | bundled（schema 默认，`schema.py:194`） |
| `client_delivery.synthesized_response_headers_after_sec` | **240** | bundled（schema 默认，`schema.py:193`） |
| `client_delivery.buffering_policy` | **`block`** | bundled（schema 默认） |
| `client_delivery.client_request_deadline` | **3600** | bundled（schema 默认） |
| `client_delivery.buffer_cap_bytes` | 16777216 | bundled（schema 默认） |
| `client_delivery.hedge` | `threshold_sec=300, max_secondary_candidates=1` | bundled（schema 默认） |
| `upstream_request_timeouts.stream_idle` | **0** | bundled（schema 默认） |
| `upstream_request_timeouts.stream_idle_overrides` | **`{}`** | bundled（schema 默认） |
| `upstream_request_timeouts.response_header` | 0 | bundled（schema 默认） |
| `upstream_request_timeouts.response_header_overrides` | `{}` | bundled（schema 默认） |
| `upstream_request_timeouts.upstream_request_deadline` | **1200** | bundled（schema 默认） |
| `upstream_transport.tcp_keepalive_interval` | **15** | bundled（schema 默认） |
| `upstream_transport.http2_ping_interval` | **15** | bundled（schema 默认） |
| `server.host` / `server.port` | `127.0.0.1` / **4141** | host=schema 默认；**port 来自 CLI `--port 4141`** |
| `proactive_rate_limiter.max_inflight` | 50 | bundled（schema 默认） |
| `history.enabled` | `True` | bundled（schema 默认） |
| `graceful_cleanup_timeout` | 60 | bundled（schema 默认） |
| `default_model_provider` | `ghc` | **bundled 文件**（`bundled-config.yaml`） |

术语对照，必须点明：任务里写的 `timeouts.stream_idle`、`upstream.transport.*` 是**旧 `AppSettings`（`src/app/config/settings.py`）的键名**。运行中的进程走的是新 `ProxyConfig`，对应的节名是 `upstream_request_timeouts` 与 `upstream_transport`。旧 `AppSettings` 里 `timeouts.stream_idle` 的默认是 **300**（`settings.py:67`），与新链路生效的 **0** 不是同一件事，不要混用。

### 1.5 这几个值里，有几个在运行的链路上根本没人读

这是本次调查里权重最高的发现之一，**强到可以直接据此行动**（判据是全仓 `rg` 加上从 `cli.py start` 顺着 `build_chain` / `create_pipeline_app` 读完的调用路径，两条独立证据一致）。

- `upstream_request_timeouts.stream_idle` / `stream_idle_overrides`：全仓唯一的消费点是 `src/app/streaming/idle_timeout.py:resolve_stream_idle`，唯一调用者是 `src/app/routes/anthropic.py:217`——那是**旧链路**（`app_factory` 挂载），而且它拿的参数是旧 `AppSettings` 的 `TimeoutConfig`。新链路（`pipeline_app.build_router()` + `ops_router`）不挂 `app/routes/*`。**结论：本次运行中，上游空闲超时机制没有被接线，`stream_idle` 的取值无论是 0 还是 300 都不影响行为。**
- `src/app/streaming/keepalive.py` 同理：唯一导入者是 `src/app/streaming/sse.py`，而 `sse.py` 只被 `app/routes/{azure,gemini,openai,anthropic}.py` 使用，全属旧链路。**新链路完全不经过 `keepalive.py`。**
- `upstream_request_timeouts.upstream_request_deadline` 是被读的（`src/app/server/handler.py:99-104`），但注意它取 override 表时用的是 `timeouts.response_header_overrides` 而不是自己的 override 表——这看着像个错配，本次两张表都是空的，所以生效值就是标量 1200。**这条列为「倾向性观察，需要再确认设计意图」，不足以直接据此改代码。**
- `upstream_transport.*` 被 `src/app/server/composition.py:66 transport_options` 读，映射为 httpx 的 `http2=(http2_ping_interval > 0)` 与 `limits.keepalive_expiry=float(tcp_keepalive_interval)`。**注意这是「用间隔值当作开关和过期时长」，并不是真的每 15 秒发一次 TCP keepalive 或 HTTP/2 PING。** httpx/httpcore 没有暴露 PING 间隔；`keepalive_expiry=15.0` 的语义是「空闲连接池里的连接 15 秒后回收」。这条同样是代码事实，强度足够。

### 1.6 与本次超时直接相关的交付时序（代码事实）

读 `src/app/server/pipeline_app.py:_dispatch` 与 `src/app/pipeline/delivery/stream.py:stream_delivery`：

1. `await handle_bounded(...)` 返回时，上游的**响应头**已经到了（`response.http_version`、`response.request.content` 在这里被读），此时才构造 `_AccountedStreamingResponse`。Starlette 会在开始迭代 body 之前先把 HTTP 响应头发给客户端。所以客户端能拿到状态行和头。
2. 之后 body 的每一个字节都来自 `stream_delivery`。它的循环是：`if event is None:`（心跳/合成时刻）→ 只有当 `response_headers_deadline` 到点且 `not response_started` 时才 `yield message_start(...)`；**否则 `elif started:` 才发 `: ping\n\n`**。
3. `started` 只有在第一个完整 block 提交、或合成 `message_start` 发出之后才变 True。

**因此：在第一个完整 Anthropic block 完成之前，客户端收到的 body 字节数是 0，`sse_ping_interval = 15` 在这一段时间里不发出任何字节。** 第一次有 body 字节，要么是第一个完整 block（`buffering_policy = block`，即一个块整体交付），要么是第 **240** 秒的合成 `message_start`。

这条与「耗时约 256.9s 的客户端超时」在数量级上吻合（240s 合成点之后 16.9s），但**我没有该次请求的任何服务端记录，所以不能断言这就是同一次请求的因果链**。这一段只作为机制描述，权重是「可据此设计下一步验证」，不是「已证实的根因」。

`client_request_deadline = 3600` 只包住 `handle_bounded`（`handler.py:208-215`），而流式 body 的迭代发生在 `handle_bounded` 返回**之后**，所以这 3600 秒并不约束流式交付阶段。这条同样是代码事实。

---

## 2. 这个进程跑的是哪个版本的代码

### 2.1 安装形态：editable

`.venv/lib/python*/site-packages/_editable_impl_app.pth` 存在（mtime 2026-08-19 21:08）。即进程在 07:44:42 导入时读的是**工作树 `src/app/` 的磁盘字节**，不是某个 commit 的快照。

### 2.2 启动时的 HEAD

reflog 全是 `commit:` 条目，没有 checkout/reset，所以按时间夹逼即可：

```
a6c0f20 HEAD@{2026-08-20 07:39:40}  fix: stop the ordinary case being louder than untouched text
                     ← 进程在 07:44:42 启动
3193880 HEAD@{2026-08-20 07:46:45}  fix: say what is actually true about the order and the exception
```

**pid 169963 启动时的 HEAD = `a6c0f20f7bdf8c0b45def5eea2faf93f001c3e1c`。** 当前 HEAD 已经推进到 `319388052068bd3d6c1cc133f0fc4ac24b000ffb`（07:46:45），比进程启动晚 2 分钟。

### 2.3 工作树脏，但脏的部分在启动前就已定型

`git status --porcelain` 中被改过的已跟踪文件及其 mtime：

| 文件 | mtime | 是否早于 07:44:42 |
|---|---|---|
| `src/app/auth/providers.py` | 2026-08-20 05:44:28 | 是 |
| `src/app/cli.py` | 2026-08-20 06:59:06 | 是 |
| `src/app/config/bundled-config.yaml` | 2026-08-18 17:22:20 | 是 |
| `src/app/model_provider/github_copilot.py` | 2026-08-20 05:50:11 | 是 |
| `tests/unit/test_model_provider.py` | — | 与运行无关 |

并且：

```
$ find src -newermt '2026-08-20 07:44:42' -type f -name '*.py'
（无输出）
```

**`src/` 下没有任何 `.py` 在进程启动之后被改过。** 所以「当前磁盘上的 `src/app/`」就是「进程 07:44:42 导入的那份」，可以直接读当前工作树来推断运行行为——上文第 1 节的所有代码引用因此成立。

### 2.4 `stream.py` 与 `keepalive.py`

```
src/app/pipeline/delivery/stream.py    mtime 2026-08-20 07:30:59   最后一次提交 7a51902 @ 07:39:27
src/app/streaming/keepalive.py         mtime 2026-08-07 23:42:18   最后一次提交 ae84aa9 @ 2026-08-07
```

两者都**没有**出现在 `git status` 的修改列表里，且 `git log -- <path>` 显示它们在 `a6c0f20` 之后没有新提交（`stream.py` 最新的是 `7a51902`，早于 `a6c0f20`）。

**结论：`stream.py` 和 `keepalive.py` 在进程启动之后都没有被改动过；当前磁盘上的这两份，就是运行中的那两份。**

注意时间戳的一个小陷阱：`stream.py` 的 mtime（07:30:59）早于提交它的 commit 时间（07:39:27）。这不矛盾——commit 不改 mtime，写盘在 07:30:59，提交在 07:39:27，进程在 07:44:42 读到的正是这份内容。

### 2.5 `synthesized_response_headers_after_sec` 何时引入、当前进程有没有

`git log -S` 结果（三条，时间升序读）：

```
ff15129  2026-08-15T23:00:29  feat: add the config schema from the human-controlled spec
a1913cc  2026-08-16T15:45:44  feat: deliver blocks off the live upstream stream
7bfafdd  2026-08-17T05:41:01  feat: synthesize a headers block when upstream stays silent
```

- 配置键本身随 human-controlled spec 的 schema 一起进来（`ff15129`，08-15）。
- **机制的实现是 `7bfafdd`（2026-08-17 05:41），只动了 `src/app/pipeline/delivery/stream.py` 与 `tests/unit/test_stream_delivery.py`。**
- `a6c0f20`（进程启动时的 HEAD）远晚于 `7bfafdd`。

**结论：pid 169963 里有这个机制，且已接线。** 接线点：`src/app/server/handler.py:362-369 stream_settings()` 把 `client_delivery.synthesized_response_headers_after_sec` 传给 `StreamSettings`，`pipeline_app._dispatch` 在构造流式响应时调用它。生效值 240（第 1.4 节）。

还有一处相关演进值得记下：`stream.py` 里合成的内容在 08-20 被从「占位 text block」改成了「只发 `message_start`」，代码注释自述的实测日期是 2026-08-20——即 242 秒的等待曾把 `{"type":"text","text":""}` 写进会话历史，导致下一次请求被上游以 `messages: text content blocks must be non-empty` 拒绝。这一改动包含在进程运行的版本里（`e82e9a5` @ 06:50 与 `7a51902` @ 07:39，都早于 07:44）。

---

## 3. 这次请求在服务端留下了什么记录

### 结论：没有。运行中的链路完全不落盘请求历史。

三条互相独立的证据：

1. **组装根里没有 history。** `src/app/server/composition.py` 的 `Chain` dataclass 与 `build_chain()` 里没有任何 `HistoryStore`。全仓 `rg 'client_delivery|HistoryStore'` 显示 `HistoryStore` 只被 `src/app/server/app_factory.py:75-77`（**旧链路**）与测试构造。`cli.py start` 走的是 `build_chain` + `create_pipeline_app`，不经过 `app_factory`。
2. **进程没有打开任何数据库文件。** `/proc/169963/fd` 里非 socket 的 fd 只有：`0/1/2 → /dev/pts/49`、`3 → /dev/urandom`、`4 → python3.14 可执行文件`、以及若干 `/dev/ptmx`（TUI footer 用）。**没有任何一个 fd 指向 `history.db`。** 另有 8 个 socket。
3. **`history.db` 里根本没有 Anthropic Messages 的记录。** `~/.local/share/ghc-api-proxy/history.db`（2.4 MB，mtime 07:48）共 8326 条，跨 2026-07-16 至 2026-08-20，endpoint 只有 9 种：`openai-responses-websocket`、`openai-chat-completions`、`openai-responses`、`openai-embeddings`、`gemini-{generateContent,streamGenerateContent}`、`azure-{chat-completions,responses,embeddings}`。**一条 `anthropic` / `messages` 的都没有。**

07:44 之后确实有 32 条新记录（07:46:09 ~ 07:48:06），但全部是合成测试流量：model 是 `gpt-test` / `gemini-test` / `deployment`，payload 是 `{"model":"gpt-test","input":"hi","stream":true}`，`ended_at - started_at` 全部为 0.0 秒。这些 endpoint 名字来自 `src/app/routes/responses_ws.py:46` 等**旧链路**路由，说明是某次跑测试/旧链路的短命进程写进了真实的用户数据目录，与 pid 169963 无关。

**因此，本次 256.9s 的请求在服务端没有任何持久化记录：没有 model、没有耗时、没有状态、没有上游协议、没有收发字节数。**

顺带一提（不是本次任务的裁决项，只是记下来）：`history.enabled` 生效值是 `True`，但新链路没有 history store 可开——这个开关在当前运行路径上是无效的。`tests/smoke/test_systemd_units.py:307` 里已经有一句自述承认「`history.db` presumes a history store the pipeline chain does not have」，说明这是已知状态而非新发现。

### 这些字段本来会出现在哪里

`src/app/server/pipeline_app.py` 的 `_Trace` / `RequestLine` / `_log_completion` 确实收集了任务想要的全部字段：`upstream_protocol`、`client_protocol`、`bytes_in`（实际发往上游的字节，取自 httpx 真正发出的 request content）、`received`（自上游收到的字节）、`duration_s`、`status_code`、`model` / `requested_model`、`attempts`、`usage`、`stop_reason`。

**但它们只被写成一行日志，而这行日志只去了 stdout。** 见下一节。

---

## 4. 服务端是否有可读的日志文件

### 结论：没有。一个字节都没有落盘。

- `src/app/observability/logging.py:setup_logging` 里，处理器只有 `handler = logging.StreamHandler()`（无参数，即 stderr），随后 `root_logger.handlers.clear()` + `addHandler(handler)`。**全仓没有任何 `FileHandler` / `RotatingFileHandler` / 日志文件路径配置**（`rg 'log_file|logfile|FileHandler|RotatingFile'` 只命中 `setup_logging` 自身的导入）。
- `cli.py:235` 调用 `setup_logging(log_format="text", log_level="DEBUG" if verbose else "INFO")`，且两条 serve 路径都给 uvicorn 传 `log_config=None`，即 uvicorn 也不另开日志文件。
- `/proc/169963/fd` 里 0/1/2 全部指向 `/dev/pts/49`，没有任何常规文件 fd（见第 3 节）。
- 没有 systemd unit：`systemctl --user list-units` 里没有 ghc 相关条目，因此 journald 里也不会有。
- 在 `/home/xp/src/ghc-api-proxy-py`、`~/.local/share/ghc-api-proxy`、`/tmp` 三处按 mtime > 07:00 搜索 `*.log` / `*.jsonl` / `*log*`，命中的全部是其他 agent 的产物，与本服务无关：

```
07:05:27  /tmp/mrev2/lint.log
07:08:26  /tmp/agent-a4c420-typecheck.log
07:11:15  docs/tmp/260820-review-request-log-colouring.md
07:11:22  /tmp/agent-a4c420-backend.log
07:37:17  tests/unit/test_request_log.py
```

- pts/49 的回滚缓冲不可取证：宿主是 VS Code 集成终端的 bash（pid 2375843），当前机器上**没有运行中的 tmux server**，没有第三方缓冲可读。

**所以，那一行本来会说清楚 model / 耗时 / 状态 / 上游协议 / 收发字节的完成日志，已经随终端滚出而不可恢复。**

---

## 汇总：哪些问题有答案，哪些没有

| 问题 | 状态 |
|---|---|
| 生效配置来源与各项取值 | **已确定**，用真实 loader 复算，见 1.4 |
| 启动时 HEAD | **已确定** `a6c0f20`，editable 安装读工作树 |
| `stream.py` / `keepalive.py` 启动后是否变动 | **已确定：都没有** |
| `synthesized_response_headers_after_sec` 引入时间与是否在跑 | **已确定** `7bfafdd` @ 08-17 05:41；在跑，值 240 |
| 该次请求的服务端历史记录 | **没有。** 新链路不落盘 |
| 该次请求的服务端日志 | **没有。** 只有 stdout，终端缓冲不可取证 |
| 256.9s 超时的根因 | **未确定。** 只有机制层面的候选（首个 block 完成前 body 字节为 0，240s 才合成 `message_start`），没有该次请求的任何一手数据 |

## 若要把根因坐实，缺的是什么

按代价从低到高（仅供裁决，未执行）：

1. 客户端侧的 transcript（`~/.claude/projects/.../*.jsonl` 及其 `subagents/`）能给出请求发起时刻、model、以及客户端观察到的 256.9s——这是目前唯一还存在的一手记录。
2. 让服务的 stdout 落一份文件（当前形态下需要重启，与「不干扰运行中服务」冲突，属于用户裁决项）。
3. 新链路补一个 history 落盘点（现状已知缺失，见 `tests/smoke/test_systemd_units.py:307` 的自述）。
