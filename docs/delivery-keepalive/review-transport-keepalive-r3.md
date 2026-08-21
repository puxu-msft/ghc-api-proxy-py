# Transport keep-alive 独立复评 R3

## 结论

`12a65ed` 的 HTTP／HTTPS proxy workaround **在当前锁定的 httpx 0.28.1／httpcore 1.0.9 上实现正确**。我复跑了真实 direct、`NO_PROXY`、显式及环境 forward proxy、HTTPS CONNECT 建连 trace，并额外跑通一个带 proxy Basic auth、自签 CA 验证和完整 TLS 隧道的 HTTPS 请求；所有非 SOCKS 路径的客户端真实 fd 都读回 `SO_KEEPALIVE=1／TCP_KEEPIDLE=25／TCP_KEEPINTVL=25／TCP_KEEPCNT=4`，关闭对照仍为 `0／7200／75／9`。没有找到第九处运行态假接线。

但候选仍不能无条件合入：**SOCKS 连接依然没有 A1 承诺的 keep-alive，且没有用户裁决允许把支持的 SOCKS 路径降级成“只 warning”**。协调消息再次声称这个待裁项已经写入 `deferred.md`，实际 commit tree 与工作树都没有这项，上一轮 F-2 的旧配置迁移范围也仍未落盘。技术实现已经把可实现的 direct／HTTP／HTTPS 路径闭合；剩下的是不能由实现者自行授权的产品范围裁决与尚未产生的文档 artifact。

## 发现

### R3-F1：SOCKS 仍未满足 A1，warning 方案尚缺用户裁决

**严重度：阻断。把握程度：高。**

真实显式 SOCKS 与环境 `ALL_PROXY=socks5://...` 探针均仍读回：

```text
{'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
```

这与当前实现和 warning 文案一致，不再是静默缺陷。显式 SOCKS 会 warning，环境 SOCKS 也会 warning；带 `user:hunter2@` 的 URL 只记录 `socks5://host:port`，实测日志不再含用户名或密码。因此 R2 的 warning 覆盖与凭据泄露都已修。

但“可见地未实现”仍不是“已经实现”。用户原裁决 A1 是让 `tcp_keepalive_interval` 成为真正的 socket keep-alive，用户亲笔配置又支持 SOCKS5／SOCKS5h。把该组合降级为只 warning 是新的产品行为选择，协调者消息不能代替用户授权。若用户明确接受，这一项可从阻断改为已知受限路径；在那之前，评审不能替用户缩小 A1 的适用面。

### R3-F2：协调消息声称的 `deferred.md` 记录仍不存在

**严重度：中。把握程度：高，commit tree 与工作树状态直接裁决。**

`12a65ed` 只改 `composition.py` 和目标测试。当前 `docs/agents/delivery-keepalive/deferred.md` 没有 SOCKS 自建 network backend／pool 的待裁项，没有“proxy 路径允许只 warning 吗”的产品岔路，也没有产品 proxy 优先级 provenance 缺口。该文件仍在第 27 行声称默认 15 是为了“不让任何人的连接池行为变化”，没有把第一轮 F-2 收窄成“只保持未自定义旧键的默认部署”，也没有旧 `tcp_keepalive_interval: N` 的迁移规则。

`git status` 在写本报告前只列两份既有评审报告，不含 `deferred.md`。所以“记在 `deferred.md` 等用户裁”连续第二轮没有对应 artifact。它必须真正落盘，尤其 SOCKS 是否允许降级正是当前合入岔路，不能只存在于代理消息中。

### R3-F3：primary HTTPS tunnel 已实证正确，但提交内的 fd 回归只守 forward 分支

**严重度：中。把握程度：高。**

`_KeepAliveHTTPProxy.create_connection()` 有两个独立分支：HTTP origin 走 `AsyncForwardHTTPConnection`，HTTPS origin 走 `AsyncTunnelHTTPConnection`。提交内新增的 fd 参数化测试只请求 `http://example.invalid/`，因此只咬 forward 分支。生产主路径是 HTTPS 上游，而这又是复制第三方私有 `create_connection()` 的维护性 workaround；未来只漏掉 tunnel 的 `socket_options` 时，现有 22 tests 仍会全绿。

当前代码本身没有 tunnel bug。我做了两层独立验证：

1. 本地 CONNECT proxy 回复 200 后，在 `connection.connect_tcp.complete` 回调内读取刚连接的 fd，得到 `1／25／25／4`。
2. 生成临时 localhost CA，起 TLS origin 与会转发字节的 CONNECT proxy，以 `http://alice:secret@proxy` 发起完整 `https://localhost/...` 请求。结果 `status=200`、body 为 `OK`、proxy 收到正确 Basic auth、客户端 fd 仍为 `1／25／25／4`。这同时验证 `_ssl_context` 与 proxy auth headers 没在换 pool 时丢失。

因此这里要求的是把已经证明的 primary branch 固化成简单的 tunnel fd 回归，不是修改生产逻辑。鉴于该 workaround 明确依赖 private classes，forward 测试不能替代 tunnel 测试。

## 参数复制审计

**结论：当前 builder 没有漏掉 `AsyncHTTPProxy` 的构造语义。把握程度：高。**

我以同一份配置分别构造 `tcp_keepalive_interval=0` 的原生 `AsyncHTTPProxy` 与值为 25 的 `_KeepAliveHTTPProxy`，逐字段比较。二者一致的是：

- `_proxy_url`：同一 HTTP origin。
- `_proxy_headers`：均含相同的 `Proxy-Authorization: Basic ...`；httpcore 确实已把 `proxy_auth` 折进该字段，复制 headers 足以携带 auth。
- `_max_connections=100`、`_max_keepalive_connections=20`、`_keepalive_expiry=17.0`。
- `_http1=True`、`_http2=True`、`_retries=0`、`_local_address=None`、`_uds=None`。
- SSL 语义：远端 `_ssl_context` 和 proxy `_proxy_ssl_context` 从旧 pool 原样传入；完整自签 CA HTTPS tunnel 成功，证明远端 context 没丢。当前配置入口只能给 proxy URL 字符串，不能携带自定义 `httpx.Proxy.ssl_context`，所以 proxy context 在这条产品路径上本来就是 `None`，复制结果一致。

唯一有意差异是 class 变为 `_KeepAliveHTTPProxy`，且 `_socket_options` 从 `None` 变成 `((SO_KEEPALIVE, 1), (KEEPIDLE, 25), (KEEPINTVL, 25), (KEEPCNT, 4))`。旧 pool 在 transport 构造后、任何请求前立即被替换，没有连接、请求或需关闭的外部资源，未发现 pool swap 泄漏。

`create_connection()` 两个分支与 httpcore 1.0.9 原实现逐项相同，只分别增加 `socket_options=self._socket_options`。私有字段或签名若随依赖升级变化会在 import／构造或 fd 测试处响亮失败；lockfile 当前固定为 httpx 0.28.1 与 httpcore 1.0.9。

## 其余复核

### Direct、HTTP forward、HTTPS tunnel 与关闭对照

**把握程度：高，均为真实 fd。**

- Direct 开启：`1／25／25／4`；关闭：`0／7200／75／9`。
- `NO_PROXY` 命中 shared primary transport：`1／25／25／4`。
- 显式 HTTP forward proxy：`1／25／25／4`。
- 环境 HTTP forward proxy：`1／25／25／4`。
- HTTPS CONNECT 建连：`1／25／25／4`。
- 完整认证 HTTPS tunnel：HTTP 200、body `OK`、fd `1／25／25／4`。
- 显式与环境 SOCKS：仍为系统默认，并各有不含凭据的具名 warning。

这证明 R2-F1、R2-F2 的可实现部分已经真正修掉，而不是又停在 pool 参数投影。

### Shared direct transport 生命周期

上一轮实测三条 `NO_PROXY` 规则会让同一 direct transport 被 enter／exit／aclose 四次。固定依赖中 entry 是 no-op，pool close 先清空连接，重复关闭空列表，当前无竞态或泄漏；这轮没有新证据要求把它升级成缺陷。

若要完全复刻 native httpx 并消掉冗余，具体位置是 `composition.py:249-251`：对 `url is None` 返回 mount value `None`，让 `_transport_for_url()` 自然回退到主 direct transport，而不是把 direct 对象本身放进每个 mount。这个收敛不影响本轮放行判断，也不值得和 proxy fd 修复绑在一起。

### Warning 文案与普通部署

缺少 `TCP_KEEPCNT` 时已不再打印“configured 15s”，而统一说明 named option 使用系统值；单位错误已修。当前 Linux direct、HTTP proxy 与 keep-alive 关闭配置均无误报；只有常量缺失或实际 SOCKS 路径会 warning。

## 测试与闸门

- `uv run pytest tests/unit/test_http_client_build.py`：22 passed。
- `uv run ruff check src tests`：All checks passed。
- `uv run pyright src/app/server/composition.py tests/unit/test_http_client_build.py`：0 errors。
- 全量 pytest：49 failed、1465 passed、3 skipped；既有 failure 集未增加。
- 我把 `12a65ed` 的新测试放入 `12a65ed^` 的隔离归档并确认 import 指向归档源码后，单跑 proxy fd、环境 SOCKS warning、password 三条正控：分别红于 `SO_KEEPALIVE 0 != 1`、无 warning、日志含 `hunter2`。当前提交三条均绿，分辨力成立。

## 最终裁决

HTTP／HTTPS proxy fix 可以通过技术复评，没有发现第九处运行态假接线。整体 slice 仍是 `needs-fix`：先由用户明确裁决 SOCKS 是否允许只 warning；把该待裁项、F-2 兼容范围和迁移规则真正写入 `deferred.md`；并为 primary HTTPS tunnel 补提交内 fd 回归。若用户接受 SOCKS 降级且后两项落盘，当前生产 workaround 本身没有剩余阻断。
