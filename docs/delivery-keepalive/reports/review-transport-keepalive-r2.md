# Transport keep-alive 独立复评 R2

## 结论

**仍不能合入。** `09f75dd` 确实修复了 `NO_PROXY` 的多 pool 问题、补上 macOS idle option 回退、把三个 transport 构造期设置改成 restart-only，也让显式 SOCKS 缺口可见；但真实 fd 复测发现更大的同形缺口：**HTTP proxy 与 HTTPS CONNECT proxy 也没有收到 socket options**。httpx 表层 pool 的 `_socket_options` 有值，httpcore 真正创建 proxy connection 时却没把它继续传下去。显式 HTTP proxy、环境 HTTP proxy与 HTTPS CONNECT 三个真实连接均读回 `SO_KEEPALIVE=0`，而新增的“HTTP proxy 反向对照”只断言没有 SOCKS warning，所以把这个失败当成了正确静默。

此外，环境变量提供的 SOCKS proxy 仍不发 warning；显式 SOCKS warning 会把 `user:password@host` 原样写进日志。即使用户未来裁决“proxy 路径只 warning、不真正实现 keep-alive”可以接受，当前 warning 覆盖也还不完整且会泄露 proxy 凭据。

评审对象为 `09f75ddc45cada54c0aa644f7efcee4ff959e03b`，当前 HEAD 正是该提交。源码解析到 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/server/composition.py`。

## 发现

### R2-F1：不只是 SOCKS，HTTP／HTTPS proxy 的真实 socket 也没有 keep-alive

**严重度：阻断。把握程度：高，已有三条真实 proxy 连接的客户端 fd 与 httpcore 产生点源码交叉证明。**

我用本地 HTTP proxy 接受被评 client 的真实请求，分别走显式 `proxy: http://...` 与环境 `ALL_PROXY=http://...`。两条路径的被选 pool 都是 `AsyncHTTPProxy`，客户端 fd 结果相同：

```text
explicit AsyncHTTPProxy {'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
environment AsyncHTTPProxy {'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
```

主产品上游是 HTTPS，所以我又起本地 CONNECT proxy，在 `connection.connect_tcp.complete` trace 回调内、TLS 握手失败之前直接读取刚连接到 proxy 的真实 fd，结果仍为：

```text
{'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
```

根因可在 httpcore 1.0.9 一步定位。`httpx.AsyncHTTPTransport` 的确把 `socket_options` 传给 `httpcore.AsyncHTTPProxy`，后者的父 pool 也把它存进 `_socket_options`；但 `httpcore/_async/http_proxy.py:146-166` 的 `create_connection()` 构造 `AsyncForwardHTTPConnection` 和 `AsyncTunnelHTTPConnection` 时都漏传 `self._socket_options`。这两个下层构造器明明各自有 `socket_options` 参数，却收到默认 `None`。因此原单测读取 proxy pool 的 `_socket_options` 仍会绿，而真正的 fd 是 0——与第一轮要消灭的假接线完全同形。

`test_a_direct_proxy_says_nothing_of_the_sort` 不是 HTTP proxy keep-alive 的反向对照；它只证明没有包含 “SOCKS” 的 warning。当前“没有 warning”恰恰是错误结果。应至少加入真实 HTTP proxy fd 正控；如果现阶段裁决是 proxy 路径不实现，则 HTTP／HTTPS proxy 也必须和 SOCKS 一样明确报告缺口，不能继续声称 socket options 能到达 HTTP proxy。

关于协调者提出的“warning 是否足以解除阻断”，我的结论是：**在现有产品合同下不足。** 用户裁决 A1 是把键实现成真正的 `SO_KEEPALIVE`，用户亲笔文档又明确支持 HTTP、HTTPS、SOCKS5 与 SOCKS5h proxy；warning 只能让未实现变得可见，不能把未实现变成已实现。只有用户再明确裁决“proxy 路径允许不生效，只需告警”后，warning 方案才可能解除功能阻断；而当前 warning 尚未覆盖 HTTP／HTTPS 与环境 SOCKS，所以即使按这条待裁方案也未完成。

### R2-F2：环境变量 SOCKS 仍静默失效，显式 SOCKS warning 又泄露 proxy 密码

**严重度：高。把握程度：高，均已运行复现。**

warning 只检查 `options.proxy`：

```python
if options.socket_options is not None and _is_socks(options.proxy):
```

环境 proxy 是随后在 `_proxy_mounts()` 内从 `get_environment_proxies()` 读取并逐项构造的，因此不经过这个检查。我用 `ALL_PROXY=socks5://127.0.0.1:<local-server>` 建立真实 SOCKS5 连接；所选 pool 是 `AsyncSOCKSProxy`，客户端 fd 为 `SO_KEEPALIVE=0`，捕获的 warning 列表是空：

```text
selected_pool_type AsyncSOCKSProxy
client fd 8 {'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
warnings []
```

这说明新增测试只覆盖配置字段 SOCKS，没有覆盖本 slice 专门重建的环境 mount 分支。warning 判断应位于 transport factory 接受具体 proxy URL 的位置，或在环境映射构造时逐项判断，不能只看顶层 `options.proxy`。

显式 warning 还直接格式化完整 proxy URL。用户亲笔配置示例明确支持 `socks5h://user:pass@proxy.example.com:1080`；实测构造 `socks5h://alice:secret@127.0.0.1:1080` 会输出：

```text
proxy socks5h://alice:secret@127.0.0.1:1080 is SOCKS, ...
```

这里有具体受保护资产——proxy password——以及明确泄露路径——startup warning／服务日志。warning 不需要 URL 即可说明缺口；若要保留目标，应先用 URL parser 去掉 username／password，不能做字符串替换猜测。

### R2-F3：协调消息声称的 `deferred.md` 处置尚未落盘，F-2 兼容范围仍写成错误全称

**严重度：中。把握程度：高，commit tree 与工作树状态直接裁决。**

`09f75dd` 只改了 `schema.py`、`composition.py` 与测试，`deferred.md` 不在 commit stat 中，工作树也没有该文件的未提交改动。当前 `deferred.md:27` 仍写“默认值取 15……是不让任何人的连接池行为变化”，没有第一轮要求的准确限定“只保证没有自定义旧键的默认部署”；也没有旧配置 `tcp_keepalive_interval: N` 的迁移规则。文件内不存在 SOCKS 自建 backend／pool 的待裁项，也没有记录产品 proxy 优先级的 provenance 缺口，尽管新测试 docstring 声称后者已记录。

因此 F-2 不是“已处置但待用户选择”，而是运行行为未迁移、文档范围也未修正。协调消息里的“已作为待裁项记入 `deferred.md`”和“会把兼容范围写准”都没有对应 artifact。复评不能把未来动作算作当前提交的一部分。

### R2-F4：shared direct transport 在当前依赖上安全，但同一对象会被重复进入与关闭

**严重度：低。把握程度：高。**

三条 `NO_PROXY` 规则现在确实共用主 transport；真实请求命中 `NO_PROXY` 时 `selected is client._transport` 为真，fd 正确读回 `1／25／25／4`。F-3 的功能缺陷已修。

生命周期上，httpx 会先处理 `_transport`，再逐项处理所有非 `None` mount。因为同一个 direct transport 同时是主 transport 和三条 mount value，三条规则的实测调用次数是：

```text
context_direct_enter_calls 4
context_direct_exit_calls 4
explicit_direct_close_calls 4
```

在固定版本中没有功能问题：`AsyncHTTPTransport.__aenter__()` 最终是 no-op，httpcore pool 的 `aclose()` 先取出并清空连接，后续重复关闭空列表，所以最后状态正确。这回答了协调者的问题——**当前没有关闭竞态或资源泄漏**。不过原生 httpx 的 `NO_PROXY` mount value 是 `None`，语义是回退到主 transport，因而只进入／关闭一次。这里也可直接返回 `None`，既保留 socket options，又完全复刻原生生命周期；当前写法依赖第三方 close 的幂等性，属于可消除的低级维护债，不单独阻断。

### R2-F5：缺失 `TCP_KEEPCNT` 时 warning 报错了值与单位

**严重度：低。把握程度：高。**

macOS 回退本身有效：模拟删除 `TCP_KEEPIDLE`、提供 `TCP_KEEPALIVE` 后，options 包含 `(IPPROTO_TCP, TCP_KEEPALIVE, 15)`。当前 Linux 正常 direct 和 `tcp_keepalive_interval=0` 都没有 warning，未发现正常直连误报。

但同一个 warning 模板把所有缺失项都描述为“system's own timing applies rather than the configured 15s”。只删除 `TCP_KEEPCNT` 时实测得到：

```text
TCP keep-alive is on but TCP_KEEPCNT is unavailable on this platform, so the system's own timing applies rather than the configured 15s
```

`TCP_KEEPCNT` 的配置值是 4 probes，不是 15 秒。建议统一写成“kernel defaults apply for the named options”，或为每项同时记录准确的期望值与单位。现有测试只删除 idle 常量，捕捉不到 count 分支的错误文案。

## 已确认修复的部分

### Direct 与 `NO_PROXY` 真实 socket

**把握程度：高，足以据此行动。**

原 direct 正反探针复跑结果未回归：配置 25 时客户端 fd 为 `SO_KEEPALIVE=1／KEEPIDLE=25／KEEPINTVL=25／KEEPCNT=4`；配置 0 时为 `0／7200／75／9`。服务端 accepted fd 仍保持系统默认。

在 `ALL_PROXY=http://127.0.0.1:1`、`NO_PROXY=127.0.0.1,localhost` 下连接真实本地 server，路由选择的正是主 direct transport，客户端 fd 为 `1／25／25／4`。这同时证明 shared pool 与 socket options 都走到真实 `NO_PROXY` 连接。

### Restart-only

**把握程度：高。**

`upstream_transport.http2`、`pool_idle_expiry` 与 `tcp_keepalive_interval` 已进入 `NOT_HOT_RELOADABLE`。用三项都改变的 candidate 调用 `pin_restart_only()`，effective config 恢复为 `True／15／15`，`restart_required` 精确列出三条路径。F-5 的代码侧假生效已修；用户亲笔文档补键仍按既定边界归用户。

### 路由测试与三条正控

**把握程度：高。**

新环境路由测试清空大小写 proxy 变量，逐项与原生 httpx 比较四个目的地，并要求结果中同时存在 direct 与 proxy；它比第一版有分辨力。它验证的是目的路由，不验证 transport 真把 socket options 用到 fd，不能替代 R2-F1 所需的 proxy 连接正控。

我把 `09f75dd` 的新测试文件放进 `09f75dd^` 的隔离归档，并先确认 import 解析到该归档源码，再运行协调者点名的三条正控；三条分别以“3 个 direct pool”“没有 SOCKS warning”“没有 platform warning”红掉。当前提交同一文件 16 tests 全绿，因此三条修复测试确实能咬住各自声称的旧缺陷。

## 验证结果

- `uv run pytest tests/unit/test_http_client_build.py`：16 passed。
- `uv run pytest tests/unit/test_config_schema.py tests/unit/test_config_loading.py`：32 passed、1 skipped；skip 原因仍是本 worktree 没有用户亲笔 config 文件。
- `uv run ruff check src tests`：All checks passed。
- `uv run pyright src/app/config/schema.py src/app/server/composition.py tests/unit/test_http_client_build.py`：0 errors。
- 全量 pytest：49 failed、1459 passed、3 skipped；49 个既有 failure 仍集中在并行 driver 重构相关路径，没有本次 transport 新失败。
- `git status --short` 在写本报告前只列第一轮评审报告；被评代码没有工作树修改。写本报告后新增的也只有两份按要求落盘的评审报告。

## 最终裁决

`09f75dd` 不是可合入候选。最低处置是先由用户裁决 proxy 路径是否必须真正支持 A1；若必须，HTTP／HTTPS 与 SOCKS 都要在真实 fd 上实现并设正控。若用户接受 proxy 路径只告警，则告警必须覆盖显式及环境 HTTP／HTTPS／SOCKS、不得泄露凭据，并把这一产品降级写入权威合同；当前提交两边都未达到。另需把协调消息承诺的 F-2 兼容范围与待裁项真正写入 `deferred.md`，不能只存在于对话中。
