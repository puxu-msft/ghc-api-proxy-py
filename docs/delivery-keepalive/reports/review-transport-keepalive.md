# Transport keep-alive 独立证伪评审

## 结论

**不能按当前形态合入。** 默认直连和 HTTP／HTTPS proxy 路径上的真实 socket 已证明会收到 `SO_KEEPALIVE=1`、`TCP_KEEPIDLE=配置值`、`TCP_KEEPINTVL=配置值`、`TCP_KEEPCNT=4`，但产品明确支持的 SOCKS proxy 路径会静默丢掉全部 `socket_options`；我用一个真实的本地 SOCKS5 连接从客户端 fd 读回了 `SO_KEEPALIVE=0`。这正是本 slice 要消灭的“看着接线、实际没落到 socket”失效，只是被挪到了 SOCKS 分支。

此外还有四个需要处置的语义差异：既有非默认 `tcp_keepalive_interval` 配置的旧 pool expiry 没有被保持；`NO_PROXY` 虽然路由正确，却把原生共用的直连 pool 拆成每条规则一个 pool；跨平台降级是静默的且漏掉 macOS 的 `TCP_KEEPALIVE`；新键未进入用户亲笔配置文档且实际不是热重载。前两项会改变运行行为，不能用“默认值一样”或“路由目标一样”覆盖过去。

## 评审锚点与证据强度

评审对象是 `1a2daacf06f55eea08cac1c65863c02aee33ca53`。当前 worktree HEAD 是仅更新文档的 `efe25d3069874715825d0090b85852a9135b5549`；`1a2daac..HEAD` 没有再改本次四个被评文件，因此运行探针测到的仍是被评实现。

源码解析探针输出为 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/server/composition.py`。运行环境为 Linux 6.18.33.2 WSL2、Python 3.14.2、httpx 0.28.1、httpcore 1.0.9。

下文中“高把握”表示已有真实 fd、被评 commit 的源码或依赖版本源码直接裁决，强到足以据此行动；“中把握”表示事实已确认，但严重度取决于项目是否明确收窄平台或接受兼容性变化。

## 发现

### F-1：SOCKS proxy 上的 TCP keep-alive 完全不生效

**严重度：阻断。把握程度：高。**

`build_http_client()` 对 direct、HTTP proxy、HTTPS proxy 和 SOCKS proxy 都构造同一种 `httpx.AsyncHTTPTransport(socket_options=...)`，表面上像是全路径覆盖；但 httpx 0.28.1 的 `AsyncHTTPTransport` 只在 `AsyncConnectionPool` 与 `AsyncHTTPProxy` 构造时传递 `socket_options`。它在 SOCKS 分支构造 `httpcore.AsyncSOCKSProxy` 时根本不传该参数，见已安装依赖的 `_transports/default.py:340-354`。这不是我方 pool 私有字段的投影问题，我起了一个最小 SOCKS5 server，让被评 `build_http_client()` 通过 `proxy: socks5://127.0.0.1:<port>` 建立真实 HTTP 连接，并从响应的 `network_stream` 取出客户端真实 fd：

```text
pool_type AsyncSOCKSProxy
pool_socket_options None
client fd 8 {'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
```

用户亲笔 `docs/.human-controlled/config.example.yaml:252-269` 明确宣称 `proxy` 支持 `socks5://` 和 `socks5h://`，因此不能把这条路径视为未支持的旁支。当前新增单测只使用 HTTP proxy，且 `socket_options_of_transport()` 对 SOCKS pool 读取不到 `_socket_options`；它既看不见这个失败，也无法保护这条路径。

**处置要求：** 在合入前明确解决 SOCKS 路径。若 httpx／httpcore 1.0.9 的公共接口无法给 `AsyncSOCKSProxy` 传 socket options，应在“支持 SOCKS”与“所有上游腿都有本键承诺的 keep-alive”之间作显式裁决，不能继续静默声称两者同时成立。

### F-2：“连接池行为不变”只对默认配置成立，既有自定义值会变化

**严重度：中。把握程度：高。**

改前的生产代码把 `tcp_keepalive_interval=N` 直接映射为 `httpx.Limits(keepalive_expiry=float(N))`，`N=0` 映射为 `None`。改后 `pool_idle_expiry` 无条件取独立默认值 15。因此默认配置确实保持 15，且默认值不是退回 httpx 自己的 5；但任何既有非默认配置都改变 pool 行为。例如旧配置只写 `tcp_keepalive_interval: 300` 时，改前 idle pool 保留 300 秒，改后只保留 15 秒。旧配置写 0 时，改前 pool 不因年龄过期，改后变成 15 秒过期。

所以 commit message 和 `deferred.md` 中“不让任何人的连接池行为变化”是全称过强。当前实现只保证“没有自定义旧键的默认部署仍为 15 秒”。用户裁决 A1 确实允许旧键获得新的 socket 语义，但它不自动裁决是否同时放弃旧键曾产生的自定义 pool 行为；这里需要把兼容范围说准，或者提供省略新键时的迁移／回退规则。

新语义本身已实测正确：`pool_idle_expiry=1` 时，两次间隔 1.2 秒的请求建立了 2 条连接；`pool_idle_expiry=0` 时只建立 1 条并复用，证明 `0 → None → 不因年龄过期` 已走到真实连接池。schema 注释“0 means it is never closed for age”是准确限定；新增测试名“keeps connections indefinitely”略强，因为对端关闭、连接错误和数量上限仍会回收连接。

### F-3：`NO_PROXY` 的目的路由等价，但连接池拓扑不等价

**严重度：中。把握程度：高。**

我在清空环境后逐组设置 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、大小写变量、`NO_PROXY=*`，以及组合的域名、子域、IPv4、带端口 localhost 规则；对原生 `httpx.AsyncClient()` 和被评 `build_http_client()` 比较了 mounts 顺序与 10 个 URL 的 `_transport_for_url()` 结果。六组场景的代理／直连目的地逐项一致，`ALL_PROXY → all://` 有效，`NO_PROXY` 的 `None` 没有被丢弃，具体域名规则也先于 broad proxy 规则。此部分足以确认路由语义正确。

但原生 httpx 对所有 `NO_PROXY` 的 `None` mount 都返回同一个 `client._transport`；被评 `_proxy_mounts()` 每见一个 `None` 就调用一次 `transport(None)`，创建一套新 pool。三条 `NO_PROXY` 规则的实测结果是原生 1 个直连 transport，被评实现 3 个，每个各自拥有 100／20 上限。于是连接复用被规则分区，且“100 条最大连接”会按 `NO_PROXY` 规则数倍增，而不是保持原生拓扑。路由结果相同不足以证明资源与限流行为相同。

**建议修法：** 创建并复用一个 direct transport，把所有值为 `None` 的 mount 指向同一个对象；代理 URL 仍各自构造 proxy transport。应补一条身份／pool 复用断言，而不只断言 URL 能匹配到某个非空 transport。

### F-4：跨平台降级会安静发生，并且 macOS 的首探延迟没有被设置

**严重度：中。把握程度：高。**

`getattr(socket, name, None)` 的行为是缺哪个常量就少 append 哪个 tuple，不会日志、告警或启动失败。因此注释所说“degradation worth noticing”与实现相反：这是安静地少设几项。`SO_KEEPALIVE` 仍会打开，但首探时间、间隔或次数可能留在系统值。

更具体地，Python 官方 `socket` 文档说明 macOS 使用 `TCP_KEEPALIVE` 表达 Linux `TCP_KEEPIDLE` 的同一语义。当前循环只找 `TCP_KEEPIDLE`，没有退回 `TCP_KEEPALIVE`，所以 macOS 上即使 Python 暴露了正确常量，也不会把配置值写入首探延迟。Windows 的 `TCP_KEEPIDLE`／`TCP_KEEPINTVL`／`TCP_KEEPCNT` 又是“when available”，旧环境还可能只有 `SIO_KEEPALIVE_VALS`；当前同样只会静默退化。

“系统默认 2 小时”在本次 Linux 主机上实测为 `TCP_KEEPIDLE=7200`，但它不是跨平台或不可变合同，管理员也能通过 sysctl 改掉。注释应至少收窄成 Linux 常见默认，不能把它写成所有降级平台的确定值。鉴于项目部署目标是 systemd／cgroup 管理的 Linux 服务，这项可由用户明确收窄平台后降为非阻断；在未收窄前，当前注释宣称的跨平台行为不成立。

### F-5：新配置键与用户亲笔文档及热重载合同尚未闭合

**严重度：中。把握程度：高。**

用户亲笔 `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/config.example.yaml:275-283` 只有 `tcp_keepalive_interval` 与 `http2_ping_interval`，没有 `pool_idle_expiry`。这不是与某个现有值直接矛盾，而是新公共键缺席；`deferred.md:27` 已正确记录“需要你在人写文档里补一个键”。因此当前 `schema.py` 顶部“matching config.example.yaml”的描述在这个键上不成立，不能把 schema 注释反过来当作用户文档已经裁决过。

还有一项直接的行为冲突：用户文档第 24 行说“除非另有说明，所有设置均支持热重载”，新键没有 restart-only 说明；但 `build_http_client()` 只在 `cli.py:139／161` 启动时运行，`NOT_HOT_RELOADABLE` 又不含 `upstream_transport.pool_idle_expiry`、`tcp_keepalive_interval` 或 `http2`。若 reload 表面接受新值，现存 client 的 pool 与 socket options 不会改变。即使当前 ConfigProvider 尚未接入生产入口，这也是新键一接入既有 reload 合同就会出现的假生效。

**处置要求：** 人写文档由用户更新；实现侧应把 transport 构造期设置列入 restart-only，或真正重建并安全替换 client。当前 slice 没有实现后一条。

### F-6：显式 `proxy` 与环境变量的优先级仍和用户文档冲突，但不是本 commit 新引入的回归

**严重度：中，非本 slice 新增。把握程度：高。**

用户亲笔文档 `config.example.yaml:252-267` 写的是 CLI `--proxy` > `HTTP_PROXY／HTTPS_PROXY` > 配置文件 `proxy`。但 `load_proxy_config()` 把 CLI、`GHC_PROXY`、YAML proxy 都压平成同一个 `ProxyConfig.proxy`，不保留来源；只要它非空，改前的 `AsyncClient(proxy=...)` 与改后的 `_proxy_mounts(configured is not None) → {}` 都会完全忽略环境 proxy 与 `NO_PROXY`。因此 `test_a_configured_proxy_still_shuts_the_environment_out` 与 httpx 原生构造器等价，却不是产品文档对“配置文件 proxy”的优先级。

这项在 `1a2daac^` 已存在，不能归罪于自建 transport；但新增测试把它表述成应永久保持的行为，容易封死之后按用户文档修正的空间。建议测试名和注释至少限定为“传给 httpx 的 explicit proxy”，并另开产品优先级修复；若 CLI 与 YAML 必须不同优先级，配置加载后不能再丢掉 provenance。

### F-7：现有环境代理单测不足以证明本次要求的等价性

**严重度：低。把握程度：高。**

`test_environment_proxies_are_still_honoured` 只设置一个 `HTTPS_PROXY`，随后断言任意非空 transport 能匹配 HTTPS URL；它不检查实际 proxy URL，不隔离 `ALL_PROXY／NO_PROXY`，不检查 direct mounts，不覆盖 SOCKS，也不比较原生 httpx。代码当前在我构造的 HTTP／HTTPS／ALL／NO_PROXY 场景里确实路由正确，是外部对照探针证明的，不是该单测证明的。

关于私有 helper 的失效方式，结论是“会响亮失败”，但原因比测试注释更直接。我通过 `sitecustomize` 在导入 `app.server.composition` 前删除 `httpx._utils.get_environment_proxies`，先确认 mutation 已生效，再运行该测试文件；pytest 在 collection 阶段以 `ImportError` 退出 2。恢复正常环境后 12 tests 仍全绿。若在 `composition` 已经导入后才 monkeypatch 删除 helper，模块绑定仍可调用，测试不会红；真实依赖升级会启动新进程，所以前一种 fresh-import 变异才与目标命题对齐。结论可以写成“应用导入即失败，因而不会静默失去代理”，不应声称该测试的业务断言本身验证了私有 API 的存在。

## 已确认没有问题的部分

### 真实 direct socket 的正反对照

**把握程度：高，强到足以确认 Linux direct 路径可用。**

我起本地 TCP HTTP server，让被评 client 实际连接，并从 `response.extensions['network_stream']` 取得客户端 fd；服务端 accepted fd 作为独立反向观察。结果如下：

```text
interval=25
  client fd 8 {'SO_KEEPALIVE': 1, 'TCP_KEEPIDLE': 25, 'TCP_KEEPINTVL': 25, 'TCP_KEEPCNT': 4}
  server fd 9 {'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
interval=0
  client fd 8 {'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
  server fd 9 {'SO_KEEPALIVE': 0, 'TCP_KEEPIDLE': 7200, 'TCP_KEEPINTVL': 75, 'TCP_KEEPCNT': 9}
```

这同时证明三点：设置确实落到客户端真实 socket，不只是存在 pool 私有字段；`TCP_KEEPCNT=4` 也生效；`tcp_keepalive_interval=0` 不传 options 后保留系统默认并关闭 `SO_KEEPALIVE`。服务端 fd 不会继承客户端选项，保持默认正是合理反向对照。

### HTTPX 自建 transport 的其余构造参数

**把握程度：高。**

读 httpx 0.28.1 `_client.py:1399-1472` 与 `_transports/default.py:279-354` 后逐项对账：提供 `transport=` 会让 `AsyncClient` 的 `verify`、`cert`、`trust_env`、`http1`、`http2`、`limits` 不再用于构造主 transport。被评 factory 已显式补回 `http2` 与完整 `limits`；其余参数在双方当前调用中都是默认值，factory 的 `AsyncHTTPTransport` 也采用同样默认，因此没有第二个值差异。尤其 `trust_env=True` 仍进入 transport 的 `create_ssl_context()`，所以 `SSL_CERT_FILE`／`SSL_CERT_DIR` 没被关掉；被关掉并重建的只有 client 层 env proxy mounts。

mounts 在合并后仍由 `AsyncClient` 排序，匹配优先级与原生相同。HTTP proxy transport 能收到 `socket_options`；SOCKS 是 F-1 所述的依赖分支遗漏。`verify／cert／trust_env` 的当前等价依赖双方默认保持一致，未来若 `build_http_client()` 新增非默认 TLS 参数，必须同时传给 main 与每个 mounted transport。

### 连接数上限

**把握程度：高。**

httpx 0.28.1 的 `DEFAULT_LIMITS` 是 100／20／5 秒；`httpx.Limits(keepalive_expiry=15)` 的另外两项确实是 `None`，httpcore 1.0.9 在 connection pool 构造时把这两个 `None` 变成 `sys.maxsize`。改前生产代码正是后一种构造，所以“此前无上限”成立。归档后的 `streaming-resilience.md:245` 也明确写 100／20。

在没有用户需求要求调节连接数、且目标只是恢复 httpx 与既有设计文档共同给出的上限时，硬编码 100／20比顺手再扩两个公共配置键更合理。需要修的是 F-3 的多 pool 倍增，而不是为了它立即增加配置面。

## 验证结果与基线复核

- `uv run python -c "import app.server.composition as m; print(m.__file__)"`：解析到本 worktree 的 `src/app/server/composition.py`。
- `uv run pytest tests/unit/test_http_client_build.py`：12 passed。
- `uv run ruff check src tests`：All checks passed。
- 当前 HEAD 全量 pytest：49 failed、1455 passed、3 skipped。
- 我把 `1a2daac^` 以 `git archive` 解到 `/tmp/delivery-keepalive-parent`，用同一 venv 且先确认 import 解析到该归档的 `src/app/server/composition.py` 后跑全量 pytest：49 failed、1450 passed、3 skipped。现有 49 个实际失败与 parent 相同；当前 `.pytest_cache` 另残留一个已经不存在的旧 test node，不是本轮失败。新增 5 个通过数与 commit 的测试增量一致。因此“49 failures 与本 slice 无关”已独立确认。
- `uv run pyright`：7 errors。用户前提中的数量仍对，但位置已因并行 driver 重构推进而变化：当前是 `handler.py` 5 个、`pipeline_app.py` 2 个，不再是 7 个全在 `pipeline_app.py`。四个被评文件没有 Pyright error，这仍支持其与本 slice 无关。

## 合入判据

至少 F-1 必须修复或经用户明确收窄 SOCKS 支持／keep-alive 承诺后才能合入。F-2 的既有自定义值迁移语义需要明确接受或修正；F-3 应恢复原生 shared direct pool，否则新加的 100／20 上限并非文案声称的单一 client 上限。F-4 可在明确 Linux-only 交付边界后降级，F-5 中的人写文档更新仍归用户，但实现的 restart-only 真值应在代码侧闭合。

## 来源

- [Python `socket` 官方文档](https://docs.python.org/3/library/socket.html)：macOS `TCP_KEEPALIVE` 与 Linux `TCP_KEEPIDLE` 的对应关系，以及 Windows keep-alive 常量的条件可用性。
