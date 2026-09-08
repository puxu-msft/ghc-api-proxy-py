# 合入后 upstream keep-alive 传输层独立评审

## 结论

**结论：需要后续修复。发现 1 项应立即补的中等严重度缺陷、1 项低严重度回归缺口、1 项低严重度日志格式缺陷。** 核心运行路径在常规配置下成立：当前顺序确实把 TCP keep-alive 与 stream cap 叠加起来；直连、HTTP forward proxy、HTTPS CONNECT tunnel 的真实客户端 fd 均读回 `SO_KEEPALIVE=1`、`TCP_KEEPIDLE=7`、`TCP_KEEPINTVL=7`、`TCP_KEEPCNT=4`，关闭对照三者均为 `SO_KEEPALIVE=0`。但是 `cap_streams_per_connection()` 会按 mount 次数反复包装同一个 direct transport；这在普通 `NO_PROXY` 列表中不改变限流值，却会随合法列表长度线性加深递归，并能在建立连接前触发 `RecursionError`。这一项应立即去重修复。

评审锚点是提交 `e12003aa559ab8930d5ccf4ffd841dd1e93525c4`。当前 worktree HEAD 为 `1a9b8544fd081a4e500d35188a62cd94113b744a`；`git diff e12003a HEAD --` 对本轮生产文件与对应回归文件无差异，因此真实网络探针验证的是目标提交相同字节。运行版本为 httpx 0.28.1、httpcore 1.0.9、h2 4.3.0、Linux。

严重度含义：中等表示需要有效但非默认的配置即可使请求失败；低表示当前默认运行不坏，但行为、可维护性或诊断输出存在确定缺口。把握程度均由当前源码、已安装依赖源码和独立运行探针交叉支持。

## 发现

### F1 `[中等] [把握程度：高，强到足以立即修复] [本提交引入]` 同一个 direct pool 按 `NO_PROXY` mount 数反复包装，足够长的合法列表会触发 `RecursionError`

位置：`src/app/upstream/stream_cap.py:100-104`。

`cap_streams_per_connection()` 先对 `client._transport` 调用 `_cap_one()`，随后又逐个处理 `client._mounts.values()`，却不按 transport 身份去重。`_proxy_mounts()` 有意让所有 `NO_PROXY` 规则共享同一个 direct transport，因此每条规则都会再给同一个 `pool.create_connection` 套一层闭包。

普通规模下限流数值没有改变。独立真实 HTTP/2 探针配置 `ALL_PROXY`、两个 `NO_PROXY` 规则、`max_streams_per_connection=2`，测得同一 direct transport 在 mounts 中出现 2 次，生成的每条连接有 3 层 `StreamCappedConnection`，5 个并发请求仍形成 3 条真实 TCP 连接，server 端分布为 `[2, 2, 1]`。原因是 pool 只把 request 赋给最外层 wrapper：最外层按自身身份得到正确计数，内层计数为 0，只继续委托，不会把 2 改成 4 或 6。

但这种冗余并非无害。独立正反对照使用 1100 条合法 `NO_PROXY` host 规则，字符串约数十 KiB，低于 Linux 单个环境变量上限。`max_streams_per_connection=0` 时 `pool.create_connection(...)` 正常返回；设为 2 时，同一 direct transport 被 mount 引用 1100 次，递归调用 1101 层 `create_connection` 闭包，在任何网络 I/O 前稳定抛出 `RecursionError: maximum recursion depth exceeded`。另以 `client.get("https://h0.example.test/")` 走忠实入口验证，`_transport_for_url()` 确认选中了 direct transport，请求同样在联网前抛出该 `RecursionError`。这支持“包装次数导致故障”的因果结论，而不只是相关性。

建议修复：在 `cap_streams_per_connection()` 中先按对象身份收集唯一 transport，再对每个唯一对象调用一次 `_cap_one()`。回归应至少断言 default transport 同时出现在多个 mounts 时只包装一层，并保留一个真实 pool 的并发连接数断言。不要只提高 recursion limit；那不会消除重复 wrapper，也只是移动失败阈值。

### F2 `[低] [把握程度：高，强到足以补回归] [本提交引入]` 两个 monkeypatch 的顺序是正确但未由 proxy seam 回归锁定，反序会静默删除 cap

位置：`src/app/server/composition.py:133-153`。

当前顺序是先执行 `_keep_proxy_connections_alive()`，再执行 `cap_streams_per_connection()`。后者保存当时的 `pool.create_connection` 为 `inner_create`，所以新连接是 `StreamCappedConnection(keepalive_create(origin), ...)`，两种行为确实叠加。直连 pool 不是 `AsyncHTTPProxy`，keep-alive helper 对它是 no-op，socket options 由原生 direct pool 处理。

反序的结果不是对称的。对 HTTP proxy pool，先安装 cap、再调用 `_keep_proxy_connections_alive()` 会直接把 `pool.create_connection` 赋成 keep-alive closure，先前 cap closure 不再可达。真实 CONNECT 对照最有分辨力：当前顺序在先预热一条 H2 tunnel 后发 5 个并发请求，得到 4 条真实 tunnel，batch 分布 `[2, 1, 1, 1]`，wrapper depth 为 1；反序后只得到 1 条 tunnel，5 个请求全落在同一 H2 connection，分布 `[5]`，wrapper depth 为 0，而 socket keep-alive 仍为 1。直连反序不受影响，因为 keep-alive helper 不改 direct pool。HTTP forward path 在 httpcore 1.0.9 中使用 HTTP/1.1 proxy connection，本身每连接只能承载 1 个并发请求，因此反序后连接数仍是 5，但 wrapper depth 从 1 变成 0；这个路径的协议上限会掩盖 cap 丢失，不能拿连接数相同当作 cap 仍在。

当前代码没有运行时错误，但现有回归没有同时在 proxy path 上开启 keep-alive 与 cap，因此不会阻止以后把两行看似独立的调用调换。建议加入一条 proxy seam 回归，至少断言同时开启两项时 proxy pool 生成的是 wrapper，并用可复用 H2 CONNECT fixture 断言每连接 batch 请求数不超过 cap。该项不是当前生产修复的 blocker，但与 F1 一并补最合算。

### F3 `[低] [把握程度：高，强到足以顺手修复] [本提交引入]` SOCKS IPv6 warning 输出的不是合法 origin

位置：`src/app/server/composition.py:222-224`。

`_origin_of()` 使用 `parsed.host` 拼接字符串；httpx 对 IPv6 host 返回不带方括号的 `::1`。实测 `_origin_of("socks5://user:secret@[::1]:1080")` 返回 `socks5://::1:1080`，无端口时返回 `socks5://fe80::1`，两者都不是可无歧义解析的 URL origin。凭据确实没有进入输出，这不是凭据泄漏，但 warning 声称打印 origin 而实际格式错误。

建议使用能保留 IPv6 bracket 的 URL 序列化方式，仅清除 userinfo、path、query、fragment；或显式检测冒号并给 host 加 `[]`。补一条带凭据 IPv6 SOCKS URL 的日志断言即可。

## 必须优先攻击的三处

### 1. 两处 `create_connection` 补丁的叠加、反序和真实连接数

结论强度：**已确认，足以作为当前实现事实；不外推到其他 httpx/httpcore 版本。**

当前顺序确实叠加，反序会在 proxy pool 上让 keep-alive closure 覆盖 cap closure。真实网络结果如下；每组为 5 个同时开始的请求，cap 为 2，keep-alive interval 为 7 秒。

| 形态 | 当前顺序的真实连接行为 | 真实客户端 fd | 反序行为 |
|---|---|---|---|
| 直连 HTTPS/H2 | 3 条 TCP，server batch 分布 `[2, 2, 1]`，wrapper depth 1 | 所有请求读回 `SO_KEEPALIVE=1`、idle 7、interval 7、count 4 | 仍为 3 条和 `[2, 2, 1]`；keep-alive helper 对 direct pool 是 no-op，cap 未被覆盖 |
| HTTPS proxy 上的 HTTP forward | 5 条 proxy TCP，每条 1 个请求，wrapper depth 1 | 所有请求读回相同 keep-alive 值 | 仍为 5 条，但 wrapper depth 0，cap 已丢失；httpcore 的 forward connection 固定为 HTTP/1.1，因此一连接一并发请求掩盖了差异 |
| HTTP proxy 上的 HTTPS CONNECT/H2 | 预热后 batch 使用 4 条 tunnel，server batch 分布 `[2, 1, 1, 1]`，wrapper depth 1 | 所有请求读回相同 keep-alive 值，所读 socket 的 peer 是 proxy hop | 只使用 1 条 tunnel，batch 分布 `[5]`，wrapper depth 0，keep-alive 仍在而 cap 已丢失 |

CONNECT 当前得到 4 条而不是数学最少值 3，不是超过 cap。第一条预热 tunnel 可接收 2 个请求；新建 tunnel 在 CONNECT 与 TLS/H2 建立前，其内部还是面向 proxy 的 HTTP/1.1 connection，暂时不能接收第二个并发请求，所以其余 3 个请求各自新建 tunnel。这是保守过分配，单连接 batch 仍不超过 2。冷启动直接发 5 个请求时会建立 5 条 tunnel，原因相同。

HTTP forward path 无法独立证明“cap 导致了连接数变化”：httpcore 1.0.9 的 `AsyncForwardHTTPConnection` 构造内部 `AsyncHTTPConnection` 时不传 `http2=True`，即使 proxy TLS ALPN 支持 H2，客户端仍发 HTTP/1.1。这里能确认的是 wrapper 存在、真实 pool 开 5 条连接、每条承载 1 个并发请求且 socket options 同时生效；不能把这个协议自身的更严格上限误写成 cap 的因果效果。

### 2. 同一个 pool 多次 `_cap_one`

结论强度：**已确认，普通规模下不改变数值，但不是无害冗余；F1 的递归故障必须修。**

在两个 `NO_PROXY` direct mounts 的实测中，direct transport 同时是 `client._transport` 与两个 mount 的值，wrapper depth 为 3。pool 的 `request.connection` 指向最外层 wrapper，所以外层看到 `[2, 2, 1]` 的正确占用，内层因身份不同始终计 0；内层只会继续调用 inner availability，不会把 cap 相乘或相加。这直接回答了数值疑问。重复层数随规则数增加，1100 条时触发 F1。

### 3. `_keep_proxy_connections_alive` 的逐参数比对

结论强度：**已确认，在 httpcore 1.0.9 上没有漏传或错传。**

已对照安装文件 `.venv/lib/python3.14/site-packages/httpcore/_async/http_proxy.py` 的 `AsyncHTTPProxy.create_connection` 源码与两个 connection constructor signature。

| 分支 | httpcore 原方法传入 | 本提交传入 | 结论 |
|---|---|---|---|
| HTTP forward | `proxy_origin`、`proxy_headers`、`remote_origin`、`keepalive_expiry`、`network_backend`、`proxy_ssl_context` | 原六项逐项取自同一 pool，再加 `socket_options` | 完整且对象来源一致 |
| HTTPS CONNECT tunnel | `proxy_origin`、`proxy_headers`、`remote_origin`、`ssl_context`、`proxy_ssl_context`、`keepalive_expiry`、`http1`、`http2`、`network_backend` | 原九项逐项取自同一 pool，再加 `socket_options` | 完整且对象来源一致 |

`retries`、`local_address`、`uds` 不是原生 `create_connection()` 向 forward/tunnel constructor 传的独立参数。它们在 `AsyncHTTPProxy.__init__()` 调用基类时用于创建和配置 pool 的 `_network_backend`，补丁继续传同一个 `_network_backend`，因此没有像旧版“替换 pool”方案那样丢失它们。`max_connections`、`max_keepalive_connections` 也是 pool 调度属性，不属于单连接 constructor 参数。

## 其余复核

### 4. `SO_KEEPALIVE` 与关闭对照

结论强度：**已确认，强到足以说明当前 Linux/httpcore 版本的真实 fd 性质。**

开启 interval 7 时，直连、HTTPS forward proxy、HTTPS CONNECT tunnel 的真实响应 `network_stream` socket 均读回 `{SO_KEEPALIVE: 1, TCP_KEEPIDLE: 7, TCP_KEEPINTVL: 7, TCP_KEEPCNT: 4}`。关闭 `tcp_keepalive_interval: 0` 时三者均读回 `{SO_KEEPALIVE: 0, TCP_KEEPIDLE: 7200, TCP_KEEPINTVL: 75, TCP_KEEPCNT: 9}`。后一组是本机 Linux 系统默认，只作为“7/7/4 不是系统原值”的反向对照，不外推为其他平台默认。

### 5. 环境变量代理路由

结论强度：**已确认，在 httpx 0.28.1 与当前进程环境解析规则下等价。**

独立矩阵比较我方 client 与原生 `httpx.AsyncClient(http2=True)` 的 `_transport_for_url()` 路由，共 9 组环境组合、每组 8 个目的地，合计 72 个目的地判定；覆盖无变量、单独 `HTTP_PROXY`、单独 `HTTPS_PROXY`、单独 `ALL_PROXY`、三者同时存在、`NO_PROXY` exact host／subdomain／localhost／IPv4／CIDR／IPv6、`NO_PROXY=*`、小写变量、大小写同时存在的优先级。72 项全部一致。另测显式 config proxy 与环境 proxy 同时存在，我方与原生显式 `proxy=` 均完全忽略环境，路由一致。

该等价性的根因也成立：我方直接复用同版本 httpx 的 `get_environment_proxies()` 生成相同 pattern/url map，再交回 httpx 的 mounts 排序和 `_transport_for_url()`；不是自行复刻 `NO_PROXY` matcher。

### 6. 不传 `limits` 的后果

结论强度：**已确认。**

直连 transport 与环境生成的 HTTP proxy transport 均读回 `_max_connections=100`、`_max_keepalive_connections=20`、`_keepalive_expiry=5.0`。同时启用 `max_streams_per_connection=2` 后这些值不变；cap 只包装 `create_connection`，没有改 pool 的三个限制。两者含义也不冲突：100 是 pool 连接总上限，20 是 idle connection 保留上限，5.0 是 idle expiry，2 是单连接并发请求上限。

### 7. 删除 `timeouts.upstream_keepalive` / `upstream_h2_ping`

结论强度：**已确认，无悬空 Python 引用；旧配置会显式失败而非静默忽略。**

对目标提交执行源码与测试搜索，旧名字在 `src/` 中只剩 `schema.py` 注释里的说明，没有属性读取、构造参数或测试代码引用。分别设置 `GHC_TIMEOUTS__UPSTREAM_KEEPALIVE=17` 与 `GHC_TIMEOUTS__UPSTREAM_H2_PING=17`，直接构造 `AppSettings()` 和经旧 `load_settings()` 两条路径均得到对应 nested field 的 `extra_forbidden` `ValidationError`。这与 `extra="forbid"` 一致：删除后的旧键不会悬空生效，也不会悄悄被接受。

### 8. SOCKS warning

结论强度：**配置来源与环境来源覆盖已确认；凭据不入 warning 已确认；畸形 URL 的异常边界已收窄；IPv6 格式缺陷见 F3。**

显式 config `proxy=socks5://user:secret@proxy.test:1080`、环境 `ALL_PROXY` 的同值、环境 `HTTP_PROXY=socks5h://...` 均产生 warning，日志只含 `socks5://proxy.test:1080` 或 `socks5h://proxy.test:1080`，不含 username/password。interval 为 0 时不告警，符合“功能未请求则不提示缺口”。

`_origin_of()` 在坏 port `socks5://host:notaport` 与坏 IPv6 bracket `socks5://[::1` 上会抛 `httpx.InvalidURL`。原生 `httpx.Proxy()` 对同一输入也抛同类型同原因异常，因此这不会把一个原本可用的 proxy 配置变成不可用，只是 warning helper 比最终 transport construction 更早触发同一拒绝。`socks5://` 被两者接受为无 host URL，warning 输出 `socks5://`，真正连接时才会失败；本提交没有额外吞错。带 path/query 与凭据的合法 URL 只记录 scheme/host/port。IPv6 合法输入的 bracket 丢失是单独的 F3。

## 回归与静态检查

- `uv run pytest -q tests/unit/server/test_http_client_build.py tests/unit/upstream/test_stream_cap.py`：`39 passed`。
- `uv run pytest -q --ignore=tests/e2e`：在当前 HEAD、且目标生产文件与目标回归文件逐字等于 `e12003a` 的 worktree 中，`1550 passed, 3 skipped`。
- `uv run ruff check src tests`：通过。
- 对 `e12003a^` 与 `e12003a` 分别从 git object 解包后运行同一 Pyright 配置：父提交 94 errors，目标提交 95 errors。集合差异为旧 `client._transport` 诊断换行移位后仍存在，并新增 `src/app/upstream/stream_cap.py:102` 的 `client._mounts` private-usage 诊断，净增 1，与已知描述完全一致；不把既有 94 项归到本提交。
- 对 `e12003a^` 与 `e12003a` 的独立 git archive 均运行 `pytest -q tests/e2e --collect-only`：两者都在 `tests/e2e/claude/conftest.py:15` 因 `ModuleNotFoundError: No module named 'harness'` 退出 2，确认是父提交已有红灯。
- 在 git archive 中尝试目标提交全量回归时有 1531 passed、3 skipped、19 failed；19 项全部是 archive 不包含该历史状态所依赖的外部／未追踪 `tests/cassettes` 与 `tests/refs` 资产而产生的 `FileNotFoundError`，不是目标代码失败。权威全量结果采用用户指定 worktree 命令的 1550 passed，不拿缺资产的 archive 结果评价提交。

## 修复优先级

1. **立即修 F1**：按 transport identity 去重后再 `_cap_one()`，并加入重复 direct mounts 的回归。这是本轮唯一会让合法配置直接请求失败的发现。
2. **同一补丁补 F2 seam 回归**：锁定 keep-alive patch 先、cap wrapper 后的 proxy 组合行为，尤其是 CONNECT/H2；当前代码不需调整顺序。
3. **可顺手修 F3**：让 SOCKS IPv6 warning 保留 host brackets。

除 F1 外，未发现必须立刻改动的 socket option 转发、proxy 路由、pool defaults、legacy 配置删除或凭据日志问题。F1 修复前，不能把这轮结论表述为“所有合法 `NO_PROXY` 配置都安全”；常规规模配置的核心传输性质已经由真实 fd 与真实 pool 证实。
