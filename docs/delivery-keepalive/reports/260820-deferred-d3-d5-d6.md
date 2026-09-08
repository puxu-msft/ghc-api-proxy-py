# D-3 / D-5 / D-6 复查：上游侧保活旋钮、`response_header_overrides` 错配、`_send` docstring 对流式为假

调查时间：2026-08-20。只读调查，未修改仓库任何源码、未执行任何 git 写操作。

**读的是哪一份代码**：主工作树 `/home/xp/src/ghc-api-proxy-py`，`refs/heads/main` = `4511aa3b362e7107141e55834d4c42766c9840b3`。该仓库有并行会话在提交，本文所有源码行号以此 commit 为准。`deferred.md` 与 `spec.md` 读的是隔离工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`（HEAD `68a50e7`），仅作参考。

**落盘位置说明**：任务指定的路径是 `/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-deferred-d3-d5-d6.md`，但本会话被 harness 隔离在 worktree 内，向共享 checkout 写入被拒绝。因此本文落在 worktree 的同名相对路径下，需要时由主会话搬运。

**证据强度标注**：
- 【读码】= 直接读了源码或第三方库源码，给出文件与行号；
- 【实测】= 本次跑了可复现的探针，附输出；
- 【读文档】= 引自项目文档，其中用户亲笔件逐字引用；
- 【推断】= 由前三者推出，未直接观测。

---

## 摘要（先看这个）

| 条目 | 结论 | 是否需要用户裁决 |
|---|---|---|
| **D-3** | 四个旋钮的真实状态各不相同，不能合并成一句「都不产生保活」。真正的岔路只有一个：`tcp_keepalive_interval` 要不要实现成真的 `SO_KEEPALIVE` | **需要**，且只需裁决这一个点（见 §1.6） |
| **D-5** | 纯 bug，正确写法唯一，且在当前部署下改了行为不变（两张覆盖表都是空的）。同节的 `response_header` 无消费方是另一件事：一道**从未实现的守卫**，不是岔路 | **不需要** |
| **D-6** | 不是纯文档缺陷。docstring 说的正是用户亲笔文档要求的语义，**实现漏了**；单独改 docstring 等于用实现去判用户亲笔件的负。同一个病 `handle_bounded` 也有一份 | **不需要** |

---

## 1. D-3：上游侧「四个旋钮」

### 1.1 逐个体检

deferred.md 原文把四个旋钮并列成「都不产生保活」，这句话结论正确、对处置无用——四个的处境完全不同。

| 旋钮 | 定义处 | 默认值 | 名字承诺什么 | 代码实际拿它做什么 | 有无消费方 |
|---|---|---|---|---|---|
| `upstream_transport.tcp_keepalive_interval` | `src/app/config/schema.py:92` | 15 | 「TCP 保活间隔（0 = 禁用）」 | `src/app/server/composition.py:69,73` 把它换算成 `httpx.Limits(keepalive_expiry=float(n) if n > 0 else None)`，落地在 `composition.py:82` | **有**，但做的是另一件事 |
| `upstream_transport.http2_ping_interval` | `src/app/config/schema.py:97` | 15 | 「HTTP/2 PING 保活间隔（0 = 禁用）」 | 什么都不做。原先它兼职决定协议（`http2 = interval > 0`），2026-08-20 已被独立的 `upstream_transport.http2`（`schema.py:95`）取代 | **无**。全仓唯一提及它的非注释处是 `tests/unit/test_http_client_build.py:39`，那条测试正是钉住「它不再影响协议」 |
| `TimeoutConfig.upstream_keepalive` | `src/app/config/settings.py:73` | 15 | 「上游 TCP keepalive 首次探测延迟秒数」（`docs/2604-rewrite/streaming-resilience.md:287`） | 什么都不做 | **无**，`src/` 内除定义外零引用 |
| `TimeoutConfig.upstream_h2_ping` | `src/app/config/settings.py:74` | 15 | 「上游 HTTP/2 PING 心跳间隔秒数」（同上 `:288`） | 什么都不做 | **无**，同上 |

【读码】依据：`rg 'tcp_keepalive_interval|http2_ping_interval|upstream_keepalive|upstream_h2_ping|keepalive_expiry' src tests docs` 的全部命中已逐条核对。

**后两个还死得更彻底一层**：它们所在的 `AppSettings`（`src/app/config/settings.py`）是 legacy 配置面。`src/app/cli.py` 的 `start` 只服务 `create_pipeline_app`（`cli.py:23,144,155,169`），走的是新的 `ProxyConfig`。所以就算有人把它们接上，也是接在一条不被服务的链路上。【读码】

**同时更正 `spec.md` §3 的一处已过时表述**：那里说 `http2_ping_interval`「只被用作 `http2 = interval > 0` 的布尔开关」——在 `4511aa3` 上这已不成立，协议开关是独立的 `upstream_transport.http2`。这是并行会话按 `.dev/docs/upstream/h2-goaway/findings.md:53-55` 落的修复。【读码 + 读文档】

### 1.2 `httpx.Limits(keepalive_expiry=...)` 的准确语义

一句话：**它是「连接池里一条空闲连接可以躺多久才被回收」，与网络上是否有字节流动无关，也完全不在请求进行期间生效。**

【读码】链条（已安装版本 httpx 0.28.1 / httpcore 1.0.9，根路径 `/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/`）：

1. `httpx/_config.py:170` 的 docstring：`**keepalive_expiry** - Time limit on idle keep-alive connections in seconds.`；构造签名在 `httpx/_config.py:178`，默认 `5.0`。
2. `httpx/_transports/default.py:304` 把 `limits.keepalive_expiry` 原样交给 `httpcore.AsyncConnectionPool`。
3. `httpcore/_async/connection_pool.py:75` 的参数文档同样是 idle 语义；值经 `:106` 存下、`:178` 下发给每条连接。
4. 真正被使用的地方只有两处，且**都在响应结束、连接转入 IDLE 的那一刻**：
   - HTTP/1.1：`httpcore/_async/http11.py:246-248`，在 `_response_closed()` 里 `self._expire_at = now + self._keepalive_expiry`；判定在 `:274-286` 的 `has_expired()`。
   - HTTP/2：`httpcore/_async/http2.py:418-420`，同样在 `_response_closed()` 里、且要求没有在飞流；判定在 `:524`。
5. 谁读 `has_expired()`：`httpcore/_async/connection_pool.py:288-291`，池在重排请求时把过期连接摘掉并关闭。

**推论（均属【读码】）**：

- 它**从不往 socket 上写任何字节**，因此在任何意义上都不是「保活」。
- 请求在飞期间 `_expire_at` 是 `None`（`http11.py:56,76`、`http2.py:57,99`），所以它对「上游 adaptive thinking 静默几十秒」这个场景**完全不发生作用**。
- **`0 = 禁用` 这个承诺在实现里是反的**：`composition.py:73` 把 0 映射成 `keepalive_expiry=None`，而 `None` 让 `has_expired()` 的时间分支恒假（`http11.py:276`），即**空闲连接永不因超时被回收**。用户在 `config.example.yaml:270-273` 写的「0 = 禁用」，落到实现上成了「关掉空闲回收」——语义翻了个面。这一条 deferred.md 里没有，是本次新发现。

**顺带一处同源缺陷**（不属 D-3，但由同一行造成）：`composition.py:82` 是 `httpx.Limits(keepalive_expiry=options.keepalive_expiry)`，没有传 `max_connections` / `max_keepalive_connections`，于是这两个是 `None`；`httpcore/_async/connection_pool.py:94-101` 把 `None` 换成 `sys.maxsize`。也就是说**出站连接数与保活连接数当前无上限**，而 httpx 自己的默认是 100 / 20（`httpx/_config.py:247`），我方设计文档 `docs/2604-rewrite/streaming-resilience.md:245` 写的也是 100 / 20。【读码】这与 `upstream-h2-goaway/findings.md:66` 在建的「每连接流数上限」是相邻话题。

### 1.3 技术可行性 (a)：能不能设 `SO_KEEPALIVE` 及 idle / interval / count

**能，接口是公开的，本次已实测。**

【读码】口子：`httpx.AsyncHTTPTransport(..., socket_options=...)`（`httpx/_transports/default.py:279,292`）→ `httpcore.AsyncConnectionPool(socket_options=...)`（`default.py:310`；`httpcore/_async/connection_pool.py:61,116,178`）→ `AsyncHTTPConnection`（`httpcore/_async/connection.py:50,67,121,130`）→ backend 的 `connect_tcp`。类型别名 `SOCKET_OPTION` 在 `httpcore/_backends/base.py:7-11`，就是 `setsockopt` 的参数元组。落地那一行是 `httpcore/_backends/anyio.py:121-122`：

```python
for option in socket_options:
    stream._raw_socket.setsockopt(*option)
```

【实测】探针 `/tmp/probe_sockopt.py`（loopback HTTP/1.1，带反向对照组），用仓库自己的 `.venv` 运行：

```
status: 200 ok
pool connections: [<AsyncHTTPConnection ['http://127.0.0.1:36827', HTTP/1.1, IDLE, Request Count: 1]>]
socket: <asyncio.TransportSocket fd=8, family=2, type=1, proto=6, laddr=('127.0.0.1', 54868), raddr=('127.0.0.1', 36827)>
SO_KEEPALIVE 1
TCP_KEEPIDLE 15
TCP_KEEPINTVL 15
TCP_KEEPCNT 4
CONTROL SO_KEEPALIVE 0
CONTROL TCP_KEEPIDLE 7200
```

对照组（不传 `socket_options` 的普通 `httpx.AsyncClient`）读回 `SO_KEEPALIVE 0` / `TCP_KEEPIDLE 7200`——即 Linux 默认的两小时。**所以这条探针有分辨力：它区分得开「设了」和「没设」。**

【读码】两条必须一起说的补充：

- **TLS 与 HTTP/2 不影响它**。选项是在 `connect_tcp` 阶段设在裸 socket 上的，`start_tls`（`httpcore/_backends/anyio.py:55-80`）只是把已有 stream 包一层 `TLSStream`，底层 fd 不变，协议协商更在其后。所以对 `https://` + h2 同样成立。这一步是读码推断，未在真实 TLS 上复测。
- **有一个真实的接线陷阱，会让「顺手实现一下」变成回归**。当前 `composition.py:79-83` 是 `httpx.AsyncClient(proxy=..., http2=..., limits=...)`，没有自建 transport。一旦改成传 `transport=`：
  - `httpx/_client.py:1442-1443`：`_init_transport` 见到 `transport is not None` 就**原样返回**，`http2` / `limits` / `verify` 全部失效，必须一并搬到 `AsyncHTTPTransport(...)` 上；
  - `httpx/_client.py:1399`：`allow_env_proxies = trust_env and transport is None`——**自建 transport 会静默关掉 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量支持**。而用户亲笔的 `docs/.human-controlled/config.example.yaml:255-257` 明写了优先级「1. CLI `--proxy` flag 2. `HTTP_PROXY`/`HTTPS_PROXY` env vars 3. This setting」，仓库里也没有任何自己解析这两个环境变量的代码（`rg -i 'HTTPS_PROXY|trust_env' src` 零命中）；
  - `httpx/_client.py:1412-1421`：显式 `proxy=` 走的是 `_init_proxy_transport`，那个函数**不接受 `socket_options`**。要既走代理又设 socket 选项，必须自己构造 `httpx.AsyncHTTPTransport(proxy=..., socket_options=..., http2=..., limits=...)` 作为唯一 transport 传入，并自己复现环境变量代理的解析。

  这段是「实现 `SO_KEEPALIVE`」这个选项的**真实成本**，deferred.md 里没有，是本次新发现。

### 1.4 技术可行性 (b)：能不能按间隔主动发 HTTP/2 PING

**在 httpx / httpcore 的公开接口上不能。缺这个能力的是 httpcore 那一层，不是 h2。**

【读码】：

- h2 这一层**有**：`h2/connection.py:1030` 就是 `def ping(self, opaque_data)`，事件侧 `h2/events.py:407,424` 有 `PingReceived` / `PingAckReceived`。
- httpcore 这一层**完全不用它**：`httpcore/_async/http2.py` 全文没有任何 `ping` 调用（`rg -i 'ping'` 的命中全是 `typing`）。h2 状态机对象是私有的 `self._h2_state`，写出口是私有的 `_write_outgoing_data`（`http2.py:461`），且受 `self._state_lock`（`http2.py:60`）保护。
- httpcore 的 HTTP/2 连接**没有后台读循环**：只有某条请求流需要数据时才去读网络（`http2.py:433 _read_incoming_data`）。所以就算把 PING 帧写出去，PING ACK 也没有人在读；要做成真正的心跳（发了要能发现对端不回），得再造一个后台任务，还要和 `_state_lock` 及现有的按流读取协调。
- httpx 这一层只是把参数透传给 httpcore，没有任何 ping 概念。

**推论**：实现 h2 PING = 依赖 httpcore 私有属性（`_h2_state` / `_write_outgoing_data` / `_state_lock`）或分叉一份连接实现，并自建后台任务。这不是「接一个参数」，是把传输层的一块接管过来，且每次 httpcore 升级都要重新验证。【推断，基于上述读码】

`docs/2604-rewrite/streaming-resilience.md:264-280` 当年写的伪代码 `await connection.ping()`，后面跟了一句「httpx/httpcore 的 h2 连接对象需支持显式 ping」——**那个前提不成立**，这是本次可以给它下的定论。

### 1.5 不做的后果：这个风险在本项目有多现实

先把两份文档的原始意图摆出来。

用户亲笔 `docs/.human-controlled/config.example.yaml:269-277`，逐字：

```yaml
upstream_transport:
  # TCP 保活间隔（0 = 禁用）。
  # TCP keepalive interval in seconds (0 = disable).
  #
  tcp_keepalive_interval: 15

  # HTTP/2 PING 保活间隔（0 = 禁用）。
  # HTTP/2 PING keepalive interval in seconds (0 = disabled).
  http2_ping_interval: 15
```

注意：**用户亲笔件只写了「是什么」，没有写「为了防谁」**。动机全部来自我方的 `docs/2604-rewrite/streaming-resilience.md:234`（【读文档】，非用户亲笔）：

> 上游连接（httpx 经 httpcore 建立）应配置 TCP 层 keepalive，防止 NAT/防火墙/负载均衡器的空闲连接回收器在长时间静默期间（如上游 adaptive thinking 静默数十秒）切断底层 TCP 连接

以及同文件 `:262`：

> TCP keepalive 只解决 L4 层「连接是否还在」，但部分中间层（GHC 边缘节点或中间代理）按**应用层静默时长**判断连接是否空闲，纯 TCP 层探测无法阻止这类连接级回收。

**我的判断：作为「防中间设备掐断」的动机，这个风险在当前部署形态下低，不足以支撑投入。** 依据四条：

1. **部署形态里没有被证实存在的、我们控制之外的中间设备**。监听是 `127.0.0.1`（`schema.py:62`），出站直连 GitHub Copilot API；`proxy` 默认空（`schema.py:297`），当前机器上也没有 `HTTP_PROXY` / `HTTPS_PROXY`（`env | grep -i proxy` 仅命中 `PWD`）；`/home/xp/.local/share/ghc-api-proxy/config.yaml` 没有写 `upstream_transport` 节（`docs/tmp/260820-server-timeout-forensics.md:50-54`，那份是用真实 loader 复算出来的）。【读码 + 读文档】
2. **静默尺度对不上**。要防的静默是「数十秒」，而 Linux 默认 `TCP_KEEPIDLE` 就是 7200 秒（上面实测的对照组），NAT 侧 established 连接的回收窗口通常是几百秒量级。数十秒的静默离任何一档回收窗口都还差一个数量级。【实测 + 推断】
3. **唯一一次实际观测到的上游连接死亡，keepalive 挡不住**。`.dev/docs/upstream/h2-goaway/findings.md:10-22`：2026-08-20 15:01:59 四条流被同一帧 `GOAWAY(NO_ERROR, last_stream_id=2^31-1)` 一起打掉。那是应用层的 graceful shutdown，TCP keepalive 与 h2 PING 都不能阻止对端主动发 GOAWAY。而且用户已裁决（同文件 `:41`）：**发 GOAWAY 的是什么我们不可能知道，不能据此分析**——所以也不能把 GOAWAY 反过来当作「需要保活」的证据。【读文档】
4. **`streaming-resilience.md:258` 的 15 秒本身是抄来的经验值**：「上游参考项目默认值为 15 秒（其运行时 undici 默认是 60 秒……）」。那是 Node/undici 连接池行为的约束，不是对我们这条链路测出来的。【读文档】

**但有一条动机成立，而且和上面那条不是一回事**：`SO_KEEPALIVE` 的另一半价值是**探测对端已死**（half-open 连接：对端进程没了、WSL2 的 NAT 状态被丢弃、笔记本睡眠恢复、VPN 抖动）。而当前 bundled 默认下，上游侧三道守卫是 `response_header: 0`（禁用）、`stream_idle: 0`（禁用）、`upstream_request_deadline: 1200`——**前两道都关着，第三道又因为 D-6 对流式请求不生效**。也就是说，一条流式请求撞上 half-open 连接时，我方**没有任何机制**会发现，只能等客户端自己放弃（实测约 300s 天花板）。在这个前提下，`SO_KEEPALIVE`（15s idle / 15s interval / 4 count ≈ 75 秒内失败）是这条腿上**唯一一个默认开启的活性探测**。

这一条我标为「足以据此行动」的强度：它不依赖任何关于中间设备的猜测，只依赖「TCP 层能发现对端不回 ACK」这个确定行为，而「三道守卫当前全关或失效」是读码可验证的事实。

### 1.6 互斥可执行选项

**旋钮 A：`upstream_transport.tcp_keepalive_interval`（唯一真正的岔路）**

| | 动作 | 代价 | 后果 |
|---|---|---|---|
| A1 | **实现成真的 `SO_KEEPALIVE`**：`composition.py` 改为自建 `httpx.AsyncHTTPTransport(proxy=..., http2=..., limits=..., socket_options=[SO_KEEPALIVE, TCP_KEEPIDLE=n, TCP_KEEPINTVL=n, TCP_KEEPCNT=k])`，**同时**自己解析 `HTTP_PROXY`/`HTTPS_PROXY` 以补回 §1.3 那个静默回归；另给连接池过期时长一个自己的键（现在这一个值被一键两用） | 中。一处构造改写 + 环境变量代理解析 + 一个新配置键（新键在用户亲笔文件里，需用户点头）+ 一条 socket 层断言测试（探针已现成） | 名字与行为对齐；上游腿获得当前唯一的默认活性探测；顺带可以把 §1.2 末尾那个「连接数变成无上限」一起修掉 |
| A2 | **只改注释，承认它是连接池过期时长**：schema 与用户亲笔件都改成 `upstream_pool_idle_expiry` 之类的名字 | 低，但**改的是用户亲笔文件**，只能由用户做 | 名实相符；上游腿继续没有任何活性探测；`0 = 禁用` 的语义反转（§1.2）仍需单独修 |
| A3 | **保留现状 + 标注**：像 `http2_ping_interval` 现在那样，在 schema 注释里写明「当前实现为连接池空闲过期，非 socket keepalive」 | 极低 | 最省事，但一个键继续同时承载两个不相干的语义，下一个读它的人还会再撞一次 |

**我的偏好：A1**，理由只有一条——**不是为了防中间设备（那条我判低），而是因为上游腿的三道守卫当前全部失效，`SO_KEEPALIVE` 是唯一一个成本可控、默认开启、不依赖任何猜测的活性探测**。如果用户不接受 A1 的接线成本（尤其是环境变量代理那半），A2 也完全站得住。我不认为 A3 可接受——它把一个已知的错误命名再冻结一轮。

**旋钮 B：`upstream_transport.http2_ping_interval`**

我不认为这里有真岔路。**维持现状（保留键 + `schema.py:96` 已有的「NOT IMPLEMENTED」标注），不实现。** 理由：§1.4 已证明实现它要接管 httpcore 的私有连接实现；它挡不住已观测到的 GOAWAY；而「按应用层静默回收」这个它唯一能防的场景，本项目一次都没有观测到。唯一值得做的增量是把 `docs/2604-rewrite/streaming-resilience.md:264-280` 那段伪代码改写成结论：httpcore 1.0.9 不提供该接口，实现代价是分叉传输层。

**旋钮 C / D：`settings.py` 的 `upstream_keepalive` / `upstream_h2_ping`**

| | 动作 | 代价 | 后果 |
|---|---|---|---|
| C1 | 从 `settings.py:73-74` 删掉这两行 | 极低。零引用、非用户亲笔（只出现在我方 `streaming-resilience.md:287-288`）、且 `AppSettings` 整体是不被服务的 legacy 面 | 少两个假旋钮 |
| C2 | 保留 | 零 | 下一次做上游侧工作的人还要再花一轮确认它们是死的 |

**我的偏好：C1**。这两个既不是「已实现的功能」，也不在用户亲笔件里，删除不触碰任何已裁决的东西。若用户对 legacy 面整体另有清理计划，就并进那次做。

**文档侧（无岔路，属顺手修正）**：`docs/2604-rewrite/streaming-resilience.md:284-288` 的配置表用的是旧 `AppSettings` 键名（`timeouts.upstream_keepalive` 等），与新链路的 `upstream_transport.*` 对不上；`:286` 的 `upstream.keepalive_expiry = 30` 也不是新链路的生效值。这张表应按实际重写。

---

## 2. D-5：`response_header_overrides` 被拿去覆盖 `upstream_request_deadline`

### 2.1 `resolve_timeout` 的语义

`src/app/pipeline/timeouts.py:41-62`【读码】：`resolve_timeout(model, scalar, overrides)` 在 `overrides` 里找命中 `model` 的键，按具体度排序（literal 子串 > glob > `*`，同类取键最长；`_classify` / `_matches` 在 `:25-38`），命中就返回该键的值（**包括 0**，`:48-49` 明说 0 是决定而非缺席），没命中返回 `scalar`。它对三个参数的含义一无所知，纯粹是「标量 + 覆盖表 → 值」。**所以错配不会报错，也不会有任何症状，直到有人往覆盖表里写东西。**

### 2.2 这一节各字段的设计意图（用户亲笔，逐字）

`docs/.human-controlled/config.example.yaml:279-314`：

```yaml
upstream_request_timeouts:
  # 单次尝试上游，从请求发起到开始收到 HTTP 响应头的最大秒数（0 = 不超时）。
  #
  # 用户冻结的不变量是绝不误杀合法长思考：活连接上的静默没有可证明安全的 wall-clock 上界，因此 bundled defaults 全部禁用此类终止器。
  # 运维可显式配置非零值以选择有界等待，但那是对该不变量的主动覆盖。
  #
  # Each upstream attempt: Max seconds from request start to receiving HTTP response headers (0 = no timeout).
  #
  # The frozen invariant is never to false-kill legitimate thinking: silence on a live connection has no provably safe wall-clock bound, so bundled defaults disable these terminators.
  # Operators may explicitly configure nonzero values to choose bounded waiting, which is an intentional override of that invariant.
  #
  response_header: 0

  # 按模型覆盖的 response_header，键规则同 stream_idle_overrides。无内置值。
  # Per-model response_header override, same keying as stream_idle_overrides. No built-in value.
  response_header_overrides: {}

  # 单次尝试上游，SSE 活动之间的最大间隔秒数（0 = 不超时）。适用于所有流式路径。
  # Each upstream attempt: Max seconds between SSE events (0 = no timeout). Applies to all streaming paths.
  stream_idle: 0

  # 按模型覆盖 stream_idle，键为模型名子串（或 glob `*`/`?`）；"*" = 所有模型。
  # Per-model stream_idle override, keyed by model-name substring (or glob `*`/`?`); "*" = all models.
  #
  # 命中项优先于上面的标量 stream_idle；0 = 禁用（无空闲超时）。多键命中时具体度：literal 子串 > glob > "*"（同类再按键长最长胜）。
  # A match wins over the scalar stream_idle above; 0 = disabled (no idle timeout). Key specificity when multiple match: literal substring > glob > "*" (then longest key).
  #
  stream_idle_overrides: {}

  # 单次上游尝试的最大存活秒数（0 = 禁用）。
  # 与另外两个上游守卫互补：response_header 只管首字节前，stream_idle 只管帧间空档，两者都拦不住「一直滴水但永不结束」的尝试。
  #
  # Max seconds ONE upstream attempt can live (0 = disabled).
  # Complements the two phase-scoped guards: response_header covers only the pre-header wait and stream_idle only the gap between frames — neither bounds an attempt that trickles forever.
  #
  upstream_request_deadline: 1200
```

三个量的分工被写死了：`response_header` 管**首字节之前**，`stream_idle` 管**帧间空档**，`upstream_request_deadline` 管**整次尝试的存活**。而 `response_header_overrides` 明确是「按模型覆盖的 **response_header**」。

### 2.3 正确写法

`src/app/server/handler.py:114-119` 现状【读码】：

```python
    timeouts = chain.config.upstream_request_timeouts
    attempt_deadline = resolve_timeout(
        route.model_id,
        timeouts.upstream_request_deadline,
        timeouts.response_header_overrides,
    )
```

正确写法唯一：

```python
    attempt_deadline = timeouts.upstream_request_deadline
```

依据：

- **不存在 `upstream_request_deadline_overrides`**。用户亲笔件里没有；`src/app/config/schema.py:100-111` 的 `UpstreamRequestTimeoutsConfig` 里也没有（只有 `response_header` / `response_header_overrides` / `stream_idle` / `stream_idle_overrides` / `upstream_request_deadline`）。所以这个量本来就没有按模型覆盖表，`resolve_timeout` 这一层调用本身就是多余的。【读码】
- **`response_header` 这个基值为什么没有消费方**：因为「响应头阶段的超时」这道守卫**根本没有实现**。全仓对它的引用只有 `schema.py:104`（定义）与 `src/app/config/compat.py:52`（旧键 `fetch_timeout` 迁移到它的映射）。这不是「基值被弃用」，是**整道守卫缺席**，而它的覆盖表被误接到了另一个量上。【读码】
- 参照写法就在同一个文件里：`handler.py:429-437` 的 `stream_idle_seconds` 用的是 `resolve_timeout(model, timeouts.stream_idle, timeouts.stream_idle_overrides)`——标量与覆盖表配对。

### 2.4 结论与影响面

**这是一个没有岔路的纯 bug，不需要用户裁决。**

影响面（【读码】+【读文档】）：

- **当前部署下行为不变**。`docs/tmp/260820-server-timeout-forensics.md:71` 用真实 loader 复算过：`response_header_overrides` 的生效值是 `{}`。空表时 `resolve_timeout` 直接返回标量（`timeouts.py:60-61`），所以 `attempt_deadline` 现在是 1200，改后还是 1200。
- **只有当运维往 `response_header_overrides` 里写东西时行为才会变**。当前：写 `{"gpt-*": 60}` 会把 gpt 系模型的**整次尝试上限**从 1200 砍到 60，而运维以为自己配的是响应头等待上限——这正是一个可能误杀合法长回答的静默陷阱。修复后：该键回到无消费方状态，等 `response_header` 守卫实现后才生效。
- **测试面**：`tests/unit/test_config_schema.py:26,39` 只断言默认值 1200；`tests/unit/test_timeout_enforcement.py` 直接给 driver 传 `attempt_deadline`，不经过 handler。所以这处修改**不会碰红任何现有测试**——也说明现有测试对这个错配没有分辨力。

**两件需要与它区分开、不要打包进这个修复的事**：

1. `response_header` 守卫本身要不要实现，是一个独立工作项，不是岔路（用户亲笔件已定义其语义）。默认值 0（禁用），所以实现它对 bundled 部署是零行为变化。
2. 要不要**新增** `upstream_request_deadline_overrides`——那是往用户亲笔配置文件里加键，**那个才需要用户裁决**，应单独进 deferred。

---

## 3. D-6：`direct_driver/base.py` 的 docstring 对流式请求为假

### 3.1 逐字引用与为什么不成立

`src/app/pipeline/direct_driver/base.py:216-241`【读码】：

```python
    async def _send(
        self,
        context: RequestContext,
        payload: dict[str, Any],
    ) -> httpx.Response:
        """Send one attempt, bounded by the attempt deadline when one is configured.

        The deadline bounds the whole attempt rather than a phase of it, which is what catches an
        upstream that trickles forever without ever finishing.
        """
        send = self._provider.send(
            self._endpoint,
            payload,
            model_id=context.resolved_model,
            stream=context.stream,
            extra_headers=context.client_headers or None,
        )
        if self._attempt_deadline <= 0:
            return await send
        try:
            async with asyncio.timeout(self._attempt_deadline):
                return await send
        except TimeoutError as error:
            raise UpstreamTimeout(
                f"attempt exceeded {self._attempt_deadline}s"
            ) from error
```

`asyncio.timeout` 只包住 `await send`。而 `await send` 何时返回，取决于 `stream`：

- **`stream=False`**：`ghc_client/client.py:155-169 send_responses` → openai SDK `_base_client.py:1604-1608` 以 `stream=False` 调 `httpx.AsyncClient.send` → `httpx/_client.py:1636-1637` 的 `if not stream: await response.aread()` **把整个 body 读完**才返回。**docstring 对非流式成立。**
- **`stream=True`**：同一条链路走 httpx 的 `stream=True` 分支，`aread()` 不执行，**拿到响应头就返回**。body 在哪消费？`src/app/server/pipeline_app.py:283-307`：`handle()` 返回之后才构造 `_AccountedStreamingResponse`，body 的每个字节来自 `response.aiter_bytes()`（`pipeline_app.py:289`），由 Starlette 在 `_send` 的 `asyncio.timeout` 上下文**早已退出之后**迭代。**docstring 对流式为假**——deferred.md 的诊断核实无误。

【读码】补充：现有测试对此**没有分辨力**。`tests/unit/test_timeout_enforcement.py:40-51` 的 `SlowProvider.send` 是 `await asyncio.sleep(delay)` 后 `return httpx.Response(200, json={})`——一个 body 已经在手的完整响应。这个替身把「流式下 body 在 await 之外」这件事整个抹掉了，所以四条测试全绿说明不了什么。

### 3.2 结论：不是纯文档缺陷

**docstring 描述的才是本意，实现漏了。这一条不需要用户裁决。**

依据是用户亲笔的 `config.example.yaml:308-314`（§2.2 已逐字引用），它给 `upstream_request_deadline` 写的职责是：

> 与另外两个上游守卫互补：response_header 只管首字节前，stream_idle 只管帧间空档，两者都拦不住「一直滴水但永不结束」的尝试。

「一直滴水但永不结束」**只可能发生在 body 阶段**。所以用户亲笔件要求的正是「deadline 覆盖到 body」。docstring 与它一致；实现与两者都不一致。**单独改 docstring 就等于用实现去判用户亲笔件的负——那才是需要裁决的动作，而修实现不需要。**

### 3.3 修实现会不会砍断合法长回答，与「绝不误杀合法长思考」冲突吗

**不冲突。** 三条依据：

1. **那条不变量的适用对象是「静默类终止器」，不是总时长上限**。原文（`config.example.yaml:282-283`）写在 `response_header` 名下：「活连接上的静默没有可证明安全的 wall-clock 上界，因此 bundled defaults 全部禁用此类终止器」。而用户自己给 `upstream_request_deadline` 设的默认是 **1200，不是 0**——用户亲手为「整次尝试的总时长」选了一个非零上限，并在同一段注释里说明它就是用来拦滴水不止的尝试的。两者不是同一类守卫。【读文档，用户亲笔】
2. **1200s 这个阈值实际上够不着**。客户端侧实测天花板约 300s（`deferred.md` D-2 的更正段），`client_delivery.client_request_deadline` 是 3600。一次流式尝试要跑满 1200 秒还没结束，客户端早就走了。所以补上这道守卫，在当前默认值下**几乎不会先于客户端放弃而触发**。【读文档 + 推断】
3. **中途终止流式请求这件事已有先例，不需要新设计**。`src/app/streaming/idle_timeout.py:36-49` 的 `with_idle_timeout` 就是在 body 迭代中途抛 `StreamIdleTimeoutError` 并关闭底层流，已接在生产路径上（`pipeline_app.py:288-291`）；而「没有合法终止事件的 EOF 该怎么告诉客户端」也已裁决并落地为 Anthropic SSE `error` 事件（`upstream-h2-goaway/findings.md:57`）。所以实现者有现成形状可依，没有新的岔路要开。【读码 + 读文档】

需要提醒的实现要点（不是岔路，是工作量）：deadline 要从 `_send` 移到「整次尝试」的尺度上，意味着它得跨越 driver 与 `pipeline_app` 的流式交付两段。最自然的落点是在 body 迭代那一层再加一道总时长守卫（与 `with_idle_timeout` 同层、同形状），而不是想办法把 `asyncio.timeout` 拉长——后者跨不过 `handle()` 的返回边界。

### 3.4 同一个病还有一份：`handle_bounded`

`src/app/server/handler.py:236-249`【读码】：

```python
async def handle_bounded(chain: Chain, context: RequestContext, on_routed: ... = None) -> HandledRequest:
    """Run a request under the client deadline.

    Measured from admission and never reset by a retry, so it bounds the whole client-visible
    operation rather than any one attempt.
    """
```

它的 `asyncio.timeout(client_request_deadline)` 同样只包住 `await handle(...)`，同样在流式下拿到响应头就退出。而用户亲笔的 `config.example.yaml:384-386` 写的是：

> 一次客户端请求的最大存活秒数（0 = 禁用）。从受理开始计，任何重试都不重置它，所以它是整个请求的外层上限。
> Max seconds one CLIENT request can live (0 = disabled). Measured from admission and never reset by retries, so it bounds the whole client-visible operation.

**完全相同的性质：文档（含用户亲笔）说「整个请求的外层上限」，实现在流式下只覆盖到响应头。** 建议与 D-6 合成同一个 slice 修，因为两者的修法落在同一处——都需要在 body 迭代那一层落一道时限。

---

## 4. 建议写回 deferred.md 的形状

- **D-3**：改写成「四个旋钮，一个真岔路」。岔路只有 A（`tcp_keepalive_interval` 实现 / 改名 / 标注），且要连带说明 A1 的接线成本（环境变量代理会静默失效）。B / C / D 给出处置建议，不作为裁决项。另新增两条本次发现的事实：`0 = 禁用` 的语义反转、连接池上限被改成无限。
- **D-5**：从「待裁决」改为「缺陷，正确写法唯一，可直接修，当前部署零行为变化」。同时拆出两个独立条目：`response_header` 守卫未实现（工作项）、要不要新增 `upstream_request_deadline_overrides`（这个才是裁决项）。
- **D-6**：从「docstring 为假」改为「实现缺陷：deadline 未覆盖流式 body」，并把 `handle_bounded` 并进来。明确写出「不需要裁决」的依据是用户亲笔件本身。
- 另需更正 `spec.md` §3 / §4 的两处已过时表述：`http2_ping_interval` 不再兼职协议开关；`upstream_request_timeouts.stream_idle` 现在**有**消费方（`handler.py:429-437` + `pipeline_app.py:288-291`）。

## 附：本次用到的探针

`/tmp/probe_sockopt.py`（loopback，含反向对照组），用 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python3` 运行。它不触碰仓库，也不发起任何外部网络请求。若要固化成回归测试，它已具备分辨力（对照组读回 `SO_KEEPALIVE 0` / `TCP_KEEPIDLE 7200`）。
