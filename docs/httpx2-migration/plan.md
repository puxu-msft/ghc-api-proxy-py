# httpx → httpx2 迁移实施计划

状态：起草 2026-08-21，**第 2 稿**（第 1 稿经两份独立评审判 `needs-fix`，本稿是处置后的版本）。本文件是活文档：实施状态、已裁决事项、待裁决事项都在这里。

调研与评审依据：

- `reports/260821-httpx2-api-delta.md` —— httpx 0.28.1 → httpx2 2.12.0 的 API/行为差异。
- `reports/260821-httpx-usage-inventory.md` —— 本仓库 httpx 使用面清单，含文件:行号。
- `reports/260821-httpx2-ecosystem-compat.md` —— 周边库跟进情况。
- `reports/260821-review-httpx2-plan-a.md` —— 第 1 稿评审（机制正确性、依赖约束），含逐条处置。
- `reports/260821-review-httpx2-plan-b.md` —— 第 1 稿评审（覆盖面、可验证性、回滚、文档纪律）。
- `reports/260821-review-httpx2-plan-r2.md` —— 第 2 稿复评，只攻 D3' 与 D7，处置见 §8。

## 0. 实施状态（2026-08-21）

| 步骤 | 状态 | 落点 |
|---|---|---|
| 步骤 0：V1 TLS 实测 | **完成，通过** | §4 V1 |
| 步骤 1：可导入切片（依赖 + 机械改名 + WS + OTel + import 名单） | **完成** | `2924a8c` |
| 步骤 2：`stream_cap` 按 D3' 改 + 饱和突发判别测试 + starlette floor 修正 | **完成** | `2b20be7` |
| 步骤 3：判别性测试（OTel span 对照） | **完成** | `5aeb9d7` |
| 步骤 3：判别性测试（WS 默认实现绑定共享 client） | **完成** | `2924a8c` 内 |
| 步骤 4：散文与注释改名（约 51 处） | **进行中**，`idle_timeout.py` 那条失实注释已改，其余待做 | — |
| 步骤 5：V2 h2 GOAWAY 缝隙复测 | **未做** | §4 V2 |
| 步骤 6：全量回归 | 每步都跑了；当前 1567 passed / 2 skipped，`ruff check src tests` 干净，`pyright` 21 error 全部属于同伴未提交的 `stream_cap` 改动，本次零新增 | — |

**端到端验证（这是本次任务的原始判据）**：从 `2924a8c` 全新 `uvx --refresh --from git+file://…` 安装并 `ghc-api-proxy start --port 41411`，服务启动、向 GitHub 换取 Copilot token（HTTP/2 200）、拉到 42 个模型、正常监听，SIGTERM 后优雅排空退出。用户报的那条命令的两级失败点（starlette 私有 API、anthropic 拒收 client）都不再出现。


探针（可复跑，解释器用装了最新依赖的环境）：

- `.dev/exp/httpx2-migration/probe_cap_designs.py` —— 驱动真实连接池收发循环，对照三种 cap 设计。**这是 D3' 的判据。**
- `.dev/exp/httpx2-cap-probe/probe_tls.py` —— TLS 信任源对照，带 `expired.badssl.com` 负样本。
- `.dev/exp/httpx2-cap-probe/probe_cap.py` —— 第 1 稿用的单趟分配探针。**保留作为历史记录，但它的结论已被 `probe_cap_designs.py` 取代**：它手工把请求塞进队列再触发一次分配，测的是一个真实到达模式下罕见的状态。
- `.dev/exp/httpx2-migration/rename_imports.py` —— 步骤 2 的机械改名器（tokenize 级，只改 NAME token，跳过注释与字符串，显式保护 `opentelemetry.instrumentation.httpx` 这类属性位，遇到 `import ... as` 直接报错退出）。

## 1. 为什么迁移

不是主动升级，是上游合同变化。`anthropic==1.0.0`（2026-08-20 发布）在 `_base_client.py:1685-1688` 硬性校验 `isinstance(http_client, httpx2.AsyncClient)`，我们注入自建的 `httpx.AsyncClient` 会在构造阶段 `TypeError`。`openai==3.3.1` 还留着一层 legacy 兼容 shim（`openai/_httpx2.py`），但官方迁移指南把它定性为 temporary、runtime-only escape hatch，公开类型注解只写 httpx2。

**触发事件（历史观察，非调研报告的派生事实）**：用户执行 `uvx --refresh --from git+https://github.com/puxu-msft/ghc-api-proxy-py.git ghc-api-proxy start --port 4141 --restart`，在全新依赖解析下先死在 starlette 私有 API（用户贴出的 traceback；已由 `1d14605` 修复）。修复后本会话在同等最新依赖环境里复跑 `ghc-api-proxy start --port 41411`，死在 `composition.py:340` 构造 `AsyncAnthropic`（本会话的实际运行输出）。

httpx2 是 Pydantic 接管维护后从 `httpx 0.28.1`（commit `b5addb6`）分叉出的发行包，正式版（Production/Stable，2.12.0，2026-08-18），底层 httpcore 一并改名 `httpcore2` 并精确 pin。公共 API 68 个名字全重合（删 1 加 8），28 个公共异常类的 MRO 零差异，默认超时/连接池上限/重定向/`Headers` 语义全不变。**迁移主体是改名**，真正需要设计判断的只有 `stream_cap`（D3'）。

## 2. 已裁决事项

### D1：整体迁移，产品代码不保留旧 httpx

`httpx` 与 `httpx2` 能在同一进程共存（实测 `sys.modules`、httpcore、logger、异常表全独立），产品代码仍只用一个。

**理由（第 1 稿的理由 1、2 都被评审推翻，此处是改正后的版本）：**

1. **主产品路径已经共享一个池，双栈会把它劈开。** CLI 只服务 `create_pipeline_app`（`cli.py:144,169`），其连接池来自 `composition.py:123 build_http_client`，`cap_streams_per_connection` 与 proxy mounts 都挂在它上面。**但这不是全仓库唯一的构建点**：`upstream/client.py:21 create_http_client`（旧 `app_factory` 路径，`bootstrap.py:110` 消费）与 `auth/service.py:38`（device flow 一次性 client）是另外两个，且 `ResponsesWebSocketClient` 唯一构造点 `bootstrap.py:250` 吃的是**前者**，不是 `build_http_client`。三个构建点都要迁移，见 §3。
2. **官方迁移指南要求同一条 code path 不混用两个包。** 原文（<https://httpx2.pydantic.dev/migration/>，评审 B 抓取核对）："Whatever you choose, don't mix the two packages in one code path." 同页同时建议逐模块增量迁移、"There is no flag day"、最后再摘掉旧 pin。**这条约束的是运行期 code path 的单一性，不是安装面的单一性** —— 第 1 稿把两者混为一谈，并据此否决了一切保留 httpx 的形态，这个误读直接导致了评审 B 的 blocker。本稿只要求产品代码单一，安装面是否残留 httpx 由 D7 单独裁决。
3. **双栈的唯一技术动机已消失。** 它本来是因为 `httpx-ws` 绑在旧 httpx 上；httpx2 自 2.6.0 起已把 httpx-ws vendored 为内置 WebSocket（2.7.0 同步到上游 0.9.0，2.10.0 另有正确性修复）。

### D2：显式改名 `import httpx2`，不用 `import httpx2 as httpx`，不用 `alias_httpx()`

本仓库注释里大量出现「httpx 的某某行为」这类实测结论，保留 `httpx` 这个名字会让读者分不清说的是哪个包。`alias_httpx()` 是给「依赖链里还有别的库死抱 httpx」准备的逃生舱，与 D1 互斥（调用后进程里不再有真 httpx），且治不了 `importlib.metadata.version("httpx")`、名为 `httpx` 的 logger 和子进程。

### D3'：`stream_cap` 在发送时抛 `ConnectionNotAvailable`，`is_available()` 保留为分配时的提示

**第 1 稿的 D3（把 cap 谓词挪进 `can_handle_request()`）已撤回**，理由见下表与 `reports/260821-review-httpx2-plan-a.md` B1/M1。

httpcore2 2.3.0 把 `_assign_requests_to_connections` 重写成单趟循环（PR #974）：可复用连接集合在一趟分配开始时**快照一次**，`is_available()` 整趟只问一次。而 `StreamCappedConnection` 的全部机制就是覆盖 `is_available()`。

判据探针 `.dev/exp/httpx2-migration/probe_cap_designs.py` 驱动**真实的 `AsyncConnectionPool.handle_async_request` 循环**（第 1 稿的探针只手工调用一次 `_assign_requests_to_connections`，测不到真实到达模式）。cap=4，度量三项：`peak` = 单连接上实际同时在飞的最大请求数（cap 的全部目的：一次 GOAWAY 端掉的就是这些）、`conns` = 建立的连接数、`closed_in_use` = 池在其上仍挂着已分配请求时就关掉的连接数。

httpcore2 2.12.0 实测：

| 场景 | 设计 | peak | conns | closed_in_use |
|---|---|---|---|---|
| burst=100，max_conn=100（池不饱和） | `is_available`（现状） | 4 | 25 | 0 |
| | `can_handle`（第 1 稿 D3） | 4 | 25 | 0 |
| | `not_available`（本稿 D3'） | 4 | 25 | 0 |
| burst=100，max_conn=8（池饱和），inner 报 ACTIVE | `is_available`（现状） | **68** | 8 | 0 |
| | `can_handle` | 4 | 8 | 0 |
| | `not_available` | 4 | 8 | 0 |
| burst=100，max_conn=8（池饱和），inner 恒报 IDLE | `is_available`（现状） | **68** | 8 | 0 |
| | `can_handle` | 4 | **26** | **18** |
| | `not_available` | 4 | 8 | 0 |

读法，三条都要说清楚：

- **失效是真的，但需要池饱和。** 池不饱和时现状代码照样守得住 cap（请求逐个到达，每趟只排队一个）。只有池打满、连接释放时一次性放行多个排队请求，快照才咬人 —— 那时 peak 从 4 涨到 68。
- **第 1 稿 D3 会破坏池的 reservation 不变量**：inner 连接报 IDLE 时，`can_handle_request` 返回 `False` 把请求推进「关掉一条空闲连接腾位置」的分支，而那条连接上还挂着已分配请求（conns 26 / closed_in_use 18）。评审 A 的 blocker 成立。
- **但这个缺陷不是 D3 引入的。** 同一探针在 **httpcore 1.0.9** 上跑，**现状代码在同样条件下同样产生 conns=25 / closed_in_use=17** —— 因为 1.0.9 的 `is_available()` 逐请求求值，效果与 D3 相同。D3 是把 1.0.9 的行为连同缺陷一起搬回来。另外 `inner.is_idle()` 恒为 `True` 是夸张化构造：真实 h2 连接有流在飞时状态是 ACTIVE。

`not_available` 在**每一列、每种规模**下都是 peak=4、连接数理想、零破坏，且它用的是 httpcore 自己的表达方式 —— `AsyncHTTP2Connection.handle_async_request` 在状态不可用时就抛 `ConnectionNotAvailable`（`httpcore2/_async/http2.py:89`），池在 `connection_pool.py:222-228` 接住它、`clear_connection()` 后重新排队。因此采用它。

改法：

```python
    async def handle_async_request(self, request: Request) -> Response:
        if self.assigned_request_count() > self._max_streams:
            # The pool may assign past the cap: httpcore2 snapshots `is_available()` once per
            # assignment pass, so a pass that releases several queued requests at once can put
            # all of them here. Refusing at send time is how httpcore's own h2 connection says
            # the same thing, and the pool answers it by clearing the assignment and re-queueing.
            raise ConnectionNotAvailable()
        return await self._inner.handle_async_request(request)
```

`> self._max_streams` 而非 `>=`：调用到这里时本请求已在 `_requests` 里且 `.connection is self`，所以计数含它自己，允许的上限就是 `max_streams`。

同时补两个 httpcore2 新增的接口方法转发（现在没有，会用错基类默认值）：

- `can_multiplex()` —— 基类默认 `False`，会让池把已建立的 h2 连接当 HTTP/1.1 对待。
- `is_connected()` —— 基类默认 `not is_closed()`，对 NEW 态连接答错，让池的 garbage-connection 清理分支永不触发。

**测试要求**：现有结构守卫（点名 `pool._requests` 与 `.connection`）对这个失效没有分辨力，在 httpcore2 上照样全绿。新增一个**饱和池突发**用例（小 `max_connections` + 大 burst），断言单连接实际在飞数不超过 cap；并按 `trusting-a-green-result` 证明它能打红（删掉 `ConnectionNotAvailable` 分支应变红）。

### D4：WebSocket 改用 httpx2 公开入口 `client.websocket()`

`httpx-ws==0.9.0` 认的是真 httpx 的类，异常归一化只捕获 `httpcore.ReadError`/`WriteError`，而 httpx2 的流抛的是 `httpcore2.*`（实测 `httpcore.NetworkError is httpcore2.NetworkError` 为 `False`）。happy path 能靠 duck typing 跑通，但错误语义与测试 transport 不兼容，不采纳。vendored 的 `httpx2.websockets._api.aconnect_ws` 不在 `__all__` 里（半私有），本次迁移的起因正是依赖上游私有面，不重蹈。

评审 B 逐参数比对了 `httpx_ws.aconnect_ws` 与 `httpx2.AsyncClient.websocket`：本项目实际会受影响的默认值完全一致（`queue_size=512`、`max_message_size_bytes=65536`、两个 keepalive 均 20.0），且 `queue_size` 一路显式传，不存在默认值静默变化。差异只在 `websocket()` 多了 `params/headers/cookies/auth/follow_redirects/timeout/extensions` 而少了 `client`/`session_class`/`**kwargs`，都是我们不传的。**改法安全。**

`ResponsesWebSocketClient.__init__` 目前把 `connect: Callable[..., Any] = aconnect_ws` 做成可注入参数供测试替身用，需要改成「注入一个 `connect(url, **kw)` 可调用，默认实现包一层 `self._http.websocket(...)`」。异常类 `WebSocketDisconnect` / `WebSocketNetworkError` / `WebSocketUpgradeError` 在 `httpx2.websockets` 下同名同继承，直接平移。

**测试要求**：现有两个 WS 测试都把 `connect` 整体替换掉，所以新写的默认实现将不被触达 —— 这是**既有盲区**（今天的 `aconnect_ws` 同样没被覆盖），但 D4 会把新代码搬进去。补一个 loopback echo 集成用例（生态报告 §2.3 已跑通同形态探针，改造成本很低）。

### D5：OTel 换用 `HTTPX2ClientInstrumentor`

依赖不用换包（`opentelemetry-instrumentation-httpx 0.65b0` 已同时支持两个包），但 instrumentor 类必须换。`HTTPXClientInstrumentor` 绑定模块名 `httpx`，迁移后它会**成功执行、不报错、插桩到没人用的包上，出站 trace 静默消失**。

**测试要求（第 1 稿在此处的验证标准比 D3 低了一个量级，评审 B 的 M3）**：`tests/unit/test_imports.py` 对这个失效**零分辨力** —— 它只做 `import_module`，而 `"opentelemetry.instrumentation.httpx"` 这个模块名在用错 instrumentor 时照样能 import。必须新增一个判别性用例：起 loopback server + `InMemorySpanExporter`，断言 httpx2 出站请求产生了 span，并证明退回 `HTTPXClientInstrumentor` 会变红。生态报告 §3.1 已有现成的正负对照探针可以直接固化。

### D6：依赖声明写出真实的兼容 floor

```toml
- "httpx[http2,socks]",
- "httpx-ws",
+ "httpx2[http2,socks,ws]>=2.12",
+ "anthropic>=1",
+ "openai>=3",
+ "fastapi>=0.141",                                  # 见 D7：需要 starlette>=1 的 TestClient
+ "opentelemetry-instrumentation-httpx>=0.65b0",     # HTTPX2ClientInstrumentor 从这一版才有
```

floor 是**语义约束**，不是口味：代码注入 `httpx2.AsyncClient`（要 `anthropic>=1` 才收）、调用 `AsyncClient.websocket()`（2.6.0 才有）、依赖 2.12.0 的连接池行为做 D3' 判断、用 `HTTPX2ClientInstrumentor`（0.65b0 才有）。第 1 稿只写「不加上界是延续既有风格（现有依赖全部无约束）」是错的：`pyproject.toml` 已有 `cryptography>=50.0.0`。

**注意 `certifi` 已不在依赖图里**（httpx2 用 truststore 取代了它）。若 V1 需要退回 certifi 信任源，必须同时把 `certifi` 加回 `dependencies` 并重新 lock —— 第 1 稿写的退路在当时的 diff 形态下不可执行。V1 已验证通过（§4），此项当前不触发。

上界不加，理由与开放问题见 §6 Q1。

### D7：starlette / fastapi 一并升到 1.x，而不是钉回 0.52 再往 dev 组补 httpx

评审 B 的 blocker：删掉 `httpx` 后，`uv lock` 的保守解析不会抬 fastapi（`fastapi 0.129.0` 声明 `starlette<1.0.0`），starlette 停在 `0.52.1`，而 **0.52.1 的 `TestClient` 硬 import 真 httpx**（`class TestClient(httpx.Client)`），14 个文件 72 处 `TestClient` 在收集阶段全红，步骤 8 的全量回归永远不可能通过。评审给了三个修法，倾向「把 `httpx` 加进 dev 组」。

**不采纳该倾向，改为抬 fastapi 下界**，理由：

1. **starlette 1.6.0 的 `TestClient` 首选 httpx2**（`starlette/testclient.py:33` 是 `import httpx2 as httpx`，旧 httpx 只是带 `DeprecationWarning` 的回退，两者都没有时报错）。所以升上去之后 blocker 自然消失，不需要保留旧包。
2. **本次事故的根源就是开发环境与用户全新安装拿到的世界分叉。** `uvx --from git+...` 不读 `uv.lock`，用户拿到的是 starlette 1.6.0；把开发环境钉在 0.52.1 是让这个分叉继续存在。
3. **starlette 1.6.0 本身没打坏东西**：在最新依赖环境里跑当前代码（未迁移），1441 passed / 119 failed，逐条核查失败全部追溯到 anthropic 的 `http_client` 类型校验，包括看起来无关的 `tests/unit/config/test_config_paths.py` 与 `tests/systemd/test_systemd_pipeline_unit.py`（后者是服务起不来导致超时）。**没有一条失败由 starlette 1.x 引起。**

代价：这次迁移顺带做了一次 ASGI 框架大版本升级。按 §5 的要求，`uv.lock` 的 diff 必须逐行审，非 httpx 的版本变动单独裁决。

## 3. 实施顺序

第 1 稿把「依赖切换」单列为第 1 步，评审 A 的 M2 实测那会产生一个 `ModuleNotFoundError: No module named 'httpx'` 的不可导入窗口，且第 2 步的全局改名本来就会改掉第 3 步声称要改的 `cast_to`。本稿改为**一个可导入切片**。

**步骤 0（前置，已完成）**：V1 TLS 验证，见 §4。它决定 D6 要不要同时补 `certifi`。

**步骤 1 —— 可导入切片（一个提交）**。以下必须一起落，中间任何一处单独落地都会让整棵树不可导入：

1. `pyproject.toml` 按 D6 改；`uv lock`；**逐行审 `git diff uv.lock`**（§5）。
2. 用 `.dev/exp/httpx2-migration/rename_imports.py --write src tests` 做机械改名。它只改代码 NAME token，**注释与字符串一律不动**（那 51 处散文里有相当一部分是「2026-08-20 对 httpx 0.28.1 的实测结论」，改名会把实测事实变成假话）。**这一步同时改掉全部 8 处 `cast_to=httpx.Response`**，不再假装那是独立步骤。
3. 三个客户端构建点逐一确认：`composition.py:123 build_http_client`、`upstream/client.py:21 create_http_client`（还在传 `Limits`/`Timeout`，签名已实测逐字不变）、`auth/service.py:38`（device flow 一次性 client）。
4. WebSocket 按 D4 改 `openai/responses_ws.py` 与 `routes/responses_ws.py`。
5. OTel 按 D5 改 `observability/tracing.py`。
6. `tests/unit/test_imports.py` 的模块名单：`httpx` → `httpx2`，去掉 `httpx_ws`。（这是包被卸载的连带项，**不是 D5 的守卫**。）
7. 收敛点：`uv run python -c "import app.cli"` 能过，`uv run pytest --collect-only` 能收集。

**步骤 2**：`stream_cap` 按 D3' 改。先加饱和池突发用例并证明它能打红，再改实现。

**步骤 3**：判别性测试补齐 —— D5 的 tracing span 用例、D4 的 WS loopback 用例。两者都要先证明能打红。

**步骤 4**：散文与注释的改名（那 51 处），逐条判断：指代包名的改；引用「httpx 0.28 / httpcore 1.0.9 的某行为」这类历史实测结论的，连同结论一起复核，必要时标注版本与日期。特别是 `idle_timeout.py:26` —— httpx2 把 `aiter_raw` 的 `await self.aclose()` 移进了 `finally`，那句 2026-08-20 的实测结论两个分句都不再成立。评审 B 已核：**没有任何测试断言了旧行为**，所以这一条只需改注释，不会有测试变红。同时把 API delta §5.1 的「私有面存活性」对照表蒸馏进 `stream_cap.py` 的模块文档串。

**步骤 5**：V2（h2 GOAWAY 缝隙）复测，见 §4。

**步骤 6**：全量回归 —— `uv run pytest`、`ruff check`、`uv run pyright`。**排在 V1/V2 之后**，因为它们失败会改代码（第 1 稿把回归排在验证之前，评审 A 的 M4）。Pyright **可能**暴露新错误（httpx2 把 `Headers.get()` 的返回注解从 `Any` 收紧成 `str | None`），以实际输出为准 —— 第 1 稿写成「预期会报」，但没有仓库级证据。

## 4. 必须实测的项

### V1：TLS 默认信任源从 certifi 换成 truststore —— **已完成，通过**

httpx2 2.3.0 把 `verify=True` 的默认分支从 `ssl.create_default_context(cafile=certifi.where())` 换成 `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`。`SSL_CERT_FILE` / `SSL_CERT_DIR` 的优先级不变，`verify=<SSLContext>` 与 `verify=False` 路径不变。`build_http_client` 不传 `verify`，走的正是被换掉的那条分支。

2026-08-21 实测（`.dev/exp/httpx2-cap-probe/probe_tls.py`）：

```
httpx 0.28.1 default ctx: ssl
httpx2 2.12.0 default ctx: truststore._api
  httpx    https://api.githubcopilot.com/models       -> HTTP 400 (handshake OK)
  httpx    https://api.github.com/user                -> HTTP 401 (handshake OK)
  httpx2   https://api.githubcopilot.com/models       -> HTTP 400 (handshake OK)
  httpx2   https://api.github.com/user                -> HTTP 401 (handshake OK)
  control  expired.badssl.com                         -> ConnectError (probe can see failures)
```

**权重边界**：这只证明**当前这台开发机**的 OS 信任库够用。若部署到信任库不同的机器（精简容器镜像尤其常见，很多基础镜像不装 `ca-certificates`），结论不自动成立，需在该机器上复跑同一个探针。退路是把 `certifi` 加回 `dependencies` 并显式传 `verify=ssl.create_default_context(cafile=certifi.where())`。

### V2：h2 GOAWAY 缝隙的形态 —— 待做

`ghc_client/transport.py:31-33` 记录的那条「hyper-h2 从缝隙里抛出 `h2.exceptions.ProtocolError`、没人包装」的实测结论，依赖的是 httpcore 的内部结构而非 httpx 的公共契约。httpcore2 在 2.1.0（#935）、2.4.0（#1012/#1013）、2.10.0（#1093，「HTTP/2 stream 失败时传播原异常而非 KeyError」）都动过这块。

**runner 路径**：实际可执行的 PoC 是 `exp/260820-h2-goaway-poc/run_poc.py`（第 1 稿写的 `.dev/docs/upstream/h2-goaway/` 只有文档与分析脚本）。它 `:20-21` 仍 import `httpcore`/`httpx`，`:7` 指定迁移前的 `.venv`，而清单把 `exp/` 排除在机械迁移之外 —— 所以要先做一份 httpx2 版的一次性 fixture，不要就地改那个已归档的 PoC。

结论有两个方向都要接受：那条旁路可能**不再必要**（httpcore2 已经包住了），也可能**仍不充分**。两种都要写进 `transport.py` 的注释并标日期。

### V3：`uv lock` 之后的依赖图 —— 步骤 1 内

不是推理能回答的问题，取决于解析器当天看到的依赖世界。至少确认：`httpx` 是否还在（预期不在）、starlette 是哪个大版本（预期 1.x）、有没有夹带无关的大版本升级。

### V4：OTel 迁移后出站 span 还在不在 —— 步骤 3

见 D5。唯一手段是跑一次带 span exporter 的对照，推理只能证明「类名换对了」。

### V5：WS loopback —— 步骤 3

见 D4。

## 5. 回滚与中止

第 1 稿完全没写这一节。**回滚手段本身是廉价的**（`git checkout pyproject.toml uv.lock && uv sync` 还原环境，`git revert` 撤掉任何语义提交），缺的是中止判据：

- **步骤 1 是一个原子切片**，中途任何一处失败都直接 `git checkout -- .` 重来，不要试图在半迁移状态上打补丁。它的收敛判据是「`import app.cli` 能过且 `pytest --collect-only` 能收集」，不是「测试全绿」。
- **`uv lock` 的 diff 必须逐行审**。放开 fastapi 会连带 `starlette 0.52.1 → 1.6.0` 这样的大版本升级（D7 已裁决接受并给了证据），但**其他**非 httpx 的版本变动要单独裁决、单独提交，不能塞进一个标题写着「依赖切换」的提交里。仓库上一个提交 `1d14605` 正是被 starlette 1.x 打过一次。
- **V2 失败时**：`transport.py` 的旁路是加固还是删除，属于产品行为判断，不在本迁移的授权范围内 —— 停下来问用户，不要顺手改。

## 6. 待用户裁决

### Q1：依赖要不要加大版本上界

本次事故的成因是 `pyproject.toml` 依赖基本无约束，而 `uvx --from git+...` 不读 `uv.lock`，每次全新安装都是对最新依赖世界的一次重新解析。D6 已加了语义 floor，上界仍未加。

- **A（当前默认）**：只加 floor。代价是下一次上游 breaking change 同样直接落到用户的全新安装上。
- **B**：对最容易破的加上界（`anthropic>=1,<2`、`openai>=3,<4`、`httpx2>=2.12,<3`、`fastapi`/`starlette` 加上界）。
- **C**：把 `uv.lock` 纳入分发路径（改用 `uv tool install` 配合 `--frozen`，或提供 pinned requirements）。

我倾向 **B**：大版本号就是上游对 breaking change 的声明，尊重它成本很低。**但评审 A 指出 B 有一个它挡不住的洞**：本次迁移最贵的差异（`stream_cap` 失效）来自 `httpcore2` 的 **minor** 版本内部实现变化，`<3` 完全挡不住这类。要挡住只能窄范围或精确 pin 我们直接依赖了私有面的那个包。C 改变用户的安装方式，不该由我单方面决定。

### Q2：推送

本地 `main` 领先 `origin/main`（含 starlette 修复与本次迁移）。用户从 GitHub 安装，修复要到手上必须推送。按项目规矩不主动推送，等明确指示。

## 7. 记录：考虑过但不采纳，以及查过之后确认无需处理

| 方案 / 风险项 | 结论 |
|---|---|
| 钉死 `anthropic<1` / `openai<3` 等生态成熟 | 不采纳。放弃两个 SDK 的后续修复与演进，把迁移压力推迟到 openai 的临时兼容层可能删除之后；等待也不消除 TLS、类型、异常、tracing 这些差异，只是延后。 |
| 双栈共存（自建 client 用 httpx2，WS 路径继续用 httpx） | 不采纳，见 D1。技术上可行且无硬冲突，但唯一动机已被 httpx2 内置 WebSocket 消解。 |
| `alias_httpx()` 全进程重定向 | 不采纳，见 D2。 |
| 把 `httpx` 加进 dev 组只为 `starlette.testclient` | 不采纳，见 D7。这是评审 B 的倾向，我选了抬 fastapi 下界，因为保留旧包会让开发环境与用户全新安装继续分叉，而那正是本次事故的成因。 |
| 放弃 `TestClient`，全面改用 `httpx2.ASGITransport` | 不采纳。改动量最大（72 处），且 D7 之后没有必要。 |
| `stream_cap` 把 cap 谓词挪进 `can_handle_request()` | 不采纳，见 D3'。会破坏池的 reservation 不变量。 |
| `stream_cap` 改成 patch `pool._assign_requests_to_connections` | 不采纳。把私有面依赖从两个名字扩大到一整个方法体，与该模块「wrap 而非 replace」的自律相悖。 |
| WebSocket 继续用 `httpx-ws` 并传 httpx2 client | 不采纳，见 D4。错误路径静默失配。 |
| WebSocket 用 `httpx2.websockets._api.aconnect_ws`（最小 diff） | 不采纳，见 D4。半私有面。 |
| **`allow_env_proxies = trust_env and transport is None`** —— `_proxy_mounts` 存在的唯一理由 | **查过，无需处理**。评审 B 实测 `httpx2/_client.py:659` 与 `httpx/_client.py:685` 逐字相同。 |
| **`getattr(upstream, "_request", None)` 三处**（`anthropic/client.py:293,461`、`executor.py:417`） | **查过，2.12.0 下仍成立**（`hasattr(httpx2.Response(200), "_request")` 为 `True`）。属性改名会静默变 `None` 且无守卫，属既有隐患，但不是本次迁移引入的，不在本次范围内处理。 |
| **cassette 回放机制** | **查过，无需处理**。依赖面是 `MockTransport`/`AsyncBaseTransport`/`AsyncByteStream`/`Request`/`Response` 五个公共类，全部同名平移；匹配判据是请求体 sha256、不含 header，所以 User-Agent 从 `python-httpx/0.28.1` 变成 `python-httpx2/2.12.0` 不影响匹配；cassette 数据里没有任何包名。 |
| **`extensions["network_stream"]` 探针** | **查过，无需处理**。httpcore2 的 `_models.py`、`_async/http11.py`、`_async/http2.py`、`_async/http_proxy.py` 仍然写 `network_stream`，键缺失会 `KeyError`（响的）。`test_http_client_build.py:314/335/471` 那组从内核 `getsockopt` 读回 `SO_KEEPALIVE` 的强测试迁移后仍有分辨力。 |
| **`test_http_client_build.py:137 test_environment_routing_matches_native_httpx`** | **不是守卫，但不必改**。它拿 `httpx.AsyncClient()` 当 oracle，改名后变成同源对照；能抓「mounts 把 URL 送错地方」，抓不住「`allow_env_proxies` 变了导致代理挂两次而路由结果相同」。既然上面已证 `allow_env_proxies` 逐字未变，无实际风险 —— 但**不应把它当作那条风险的守卫**。 |

## 8. 第 2 稿复评（r2）的逐条处置

复评判 `needs-fix`，1 blocker、2 major、1 minor。全部采纳，处置如下。

### F1（blocker）：`fastapi>=0.141` 不会把 starlette 抬到 1.x —— **采纳，已修**

复评是对的，而且我在实施时独立撞到了同一件事：加了 `fastapi>=0.141` 之后重新 lock，starlette 仍停在 0.52.1（fastapi 0.141.1 只声明 `starlette>=0.46.0`）。已改为显式 floor。复评建议 `starlette>=1.2.1`（1.2.0 是 TestClient 运行期开始优先 httpx2 的版本，1.2.1 修了仍写 `httpx` 的类型分支），采纳该版本号——我最初写的 `starlette>=1` 语义不对，1.0/1.1 的 TestClient 仍需要旧 httpx。重新 lock 后实测 starlette 1.6.0、httpx 从依赖图消失。

### F2（major）：D3' 在池饱和时的重排放大没被记录 —— **采纳，已补测并接受**

复评在 `max_connections=2`、`burst=500` 下测到 57,873 次拒绝、5.3 秒。这个量级成立，但它的配置远低于本项目实际值：`max_connections` 走 httpx 默认 100，而 `max_streams_per_connection` 在 `docs/.human-controlled/config.example.yaml` 里是 1。按真实量级复测（cap=1、max_connections=100）：

| 突发 | 现状代码 peak | D3' peak | D3' 尝试/拒绝 |
|---|---|---|---|
| 50（未饱和） | 1 | 1 | 50 / 0 |
| 200 | **100** | 1 | 350 / 150 |
| 500 | **400** | 1 | 1809 / 1309 |

即：真实配置下的代价是 1.75~3.6 倍的内部重排（不新开 socket），换回的是一个否则完全失效的 cap——未修时 500 并发会把 400 个请求压在同一条连接上，正是这个模块存在的理由。**接受这个代价**，数字记进 `stream_cap.py` 的模块文档串。

### F3（major）：测试不能验证 `>` 边界，`peak` 的计数点不精确 —— **采纳，已重写**

两点都对，而且比复评说的更严重：我按「所有请求卡在一个事件上」写的第一版测试，连「删掉拒绝分支」这个主变异都打不红——因为那个工况从来不会进入「一趟释放多个排队请求」的状态。已按探针里真正复现问题的工况重写（响应自行完成、`max_connections=4`、cap=2、burst=60），计数点移到 inner handler 入口，断言收紧为 `peak == cap`，并加了 30 秒 deadline。两次变异实测：删掉拒绝分支 → 断言失败；`>` 改 `>=` → **挂起**。

后者是复评没有预料到的发现：`is_available()` 与发送时的谓词必须对同一个 cap 位置达成一致，否则池会「分配→拒绝→重排→再分配」活锁。这条已写进 `stream_cap.py` 的注释。

### F4（minor）：旧栈归因的措辞会淡化 D3 的回归 —— **采纳**

改为：D3 会把 httpcore 1.0.9 可出现的旧分配缺陷重新带进 httpcore2；它不是该缺陷形态的首次出现，但对迁移后的目标栈仍是新引入的回归。旧栈的 `closed_in_use` 依赖 `inner.is_idle()` 恒为 `True` 这个夸张化构造，不证明生产上真的发生过。

### 复评清单第 3 条：`test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`

复评独立观察到了这条测试在迁移后失败并挂起，与我实施时撞到的是同一处。根因已定位：httpx2 把 `Response.aiter_raw` 的 `aclose()` 移进 `finally`，所以拆除读取链会**内联关闭上游 response**，而这条测试正在那个点上设了阻塞检查点，于是 observer finalize 永远等不到。单变量确认过不是 starlette 引起的（降到 0.52.1 照样挂）。该测试的编排已按新的关闭点重排，它要证的东西（重复取消落在清理停顿处时其余清理仍须跑完）不变，变异（去掉 `finish_stream_cleanup` 的 shield）仍能打红。
