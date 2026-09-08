# httpx 0.28.1 → httpx2 2.12.0 API/行为差异调研

调研日期 2026-08-21。调研范围限定为「httpx 与 httpx2 的差异」，**未修改本仓库任何代码**。

证据来源共三类，正文中逐条标注：

- **[探针]** — 探针环境 `/home/xp/.claude/jobs/ca953617/tmp/latest-venv/`（Python 3.14，同时装有 `httpx 0.28.1` + `httpcore 1.0.9` 与 `httpx2 2.12.0` + `httpcore2 2.12.0`）里跑过的脚本及其真实输出，本文档给出脚本要点与输出。
- **[源码]** — 上述环境 `site-packages/` 下的源码路径 + 行号，或对两棵源码树做归一化重命名后的 `diff` 结果。
- **[文档]** — 官方 CHANGELOG / 迁移指南 / PyPI 元数据，给出 URL。

---

## 0. 结论摘要

**没有阻断性问题。** httpx2 2.12.0 是 httpx 0.28.1 的直系分叉，公共 API 几乎逐字相同（68 个公共名字完全重合，仅删了 1 个、加了 8 个），异常层级 28 个公共异常类的 MRO **零差异**，默认超时/连接池上限/重定向默认值/`Headers` 大小写与多值语义全部不变。迁移的主体工作量是改名。

但有 **4 项真实的行为差异会具体影响本仓库**，其中 2 项会静默降级（不报错、测试仍绿）：

| # | 差异 | 影响模块 | 严重度 |
|---|---|---|---|
| A | httpcore2 把连接池的 `_assign_requests_to_connections` 改成「单趟循环 + 一次性快照」，`is_available()` 不再对每个排队请求重新求值 | `src/app/upstream/stream_cap.py` | **高（静默失效）** |
| B | `AsyncConnectionInterface` 新增 `is_connected()` / `can_multiplex()`，我们的 wrapper 未转发，会用错默认值 | `src/app/upstream/stream_cap.py` | 中（静默行为改变） |
| C | `Response.aiter_raw` 的 `await self.aclose()` 移进了 `finally`：关闭 `aiter_bytes()` 生成器现在**会**关闭 response | `src/app/streaming/idle_timeout.py` | 中（行为改变 + 现有注释作废） |
| D | 默认 TLS 校验从 `certifi` 换成 `truststore`（读操作系统信任库） | 部署环境 | 中（环境相关） |

另外一项**对前提的更正**（有直接证据，见 §7.1）：`openai==3.3.1` **接受** legacy `httpx.AsyncClient`（它带了一层 `openai/_httpx2.py` 兼容层）；**只有 `anthropic==1.0.0` 拒收**。派单描述里的报错文本与 anthropic 的源码逐字相符，与 openai 的不符。

---

## 1. httpx2 是什么

### 1.1 与 httpx 的关系

**不是 httpx 的下一个大版本，是 Pydantic 接管维护后另起发行名的分叉（fork）**，分叉基点是 `httpx 0.28.1`（上游 commit `b5addb6`）。

CHANGELOG `2.0.0b1` 条目原文 [文档]（<https://github.com/pydantic/httpx2/blob/main/src/httpx2/CHANGELOG.md>）：

> First release of `httpx2`, a fork of [`httpx`](https://github.com/encode/httpx) maintained by Pydantic. Forked from `httpx 0.28.1` (commit [`b5addb6`](https://github.com/encode/httpx/commit/b5addb6)).
>
> ### Breaking changes
>
> * **Renamed package**: `httpx` -> `httpx2`. `import httpx` becomes `import httpx2`. The CLI is now `httpx2`, the User-Agent header is `python-httpx2/<version>`, and the logger is `httpx2`. **No other public API changed.**
> * **Renamed transitive dependency**: `httpcore` -> `httpcore2`, vendored into the same repository as a uv workspace member.

包元数据也证实这层关系 [源码 `httpx2-2.12.0.dist-info/METADATA:5-9`]：

```
Project-URL: Homepage, https://github.com/pydantic/httpx2
Author-email: Tom Christie <tom@tomchristie.com>
Maintainer-email: "Pydantic Services Inc." <engineering@pydantic.dev>
```

README 里 Pydantic 的说法是「HTTPX itself seeing limited activity recently, Pydantic is picking up stewardship under the HTTPX2 name」。

`httpcore2` 同样是 `httpcore 1.0.9` 的分叉，与 httpx2 同仓库、同版本号、**精确 pin**（`Requires-Dist: httpcore2==2.12.0`）[源码 `httpx2-2.12.0.dist-info/METADATA:36`]。

### 1.2 发布状态

**正式版**，不是预发布 [文档 PyPI JSON API]：

- 最新版 2.12.0，发布于 2026-08-18，无 `a/b/rc` 后缀，未 yank。
- `Classifier: Development Status :: 5 - Production/Stable` [源码 METADATA:12]。
- CHANGELOG：`2.0.0` 条目写 "Official first release of `httpx2`. No changes since `2.0.0b1`."
- `Requires-Python: >=3.10`（本仓库 `requires-python = ">=3.14"`，无冲突）。

发布节奏很密：2.0.0 → 2.12.0 之间的 12 个 minor 都在 2026-05 至 2026-08 之间。

### 1.3 官方迁移指南

- 迁移指南：<https://httpx2.pydantic.dev/migration/>（文档站导航里叫 "Migrating from HTTPX"，位于 QuickStart 与 Advanced 之间）
- 文档站：<https://httpx2.pydantic.dev/>
- CHANGELOG：<https://github.com/pydantic/httpx2/blob/main/src/httpx2/CHANGELOG.md>（httpcore2 的在同仓库 `src/httpcore2/CHANGELOG.md`）
- 源码：<https://github.com/pydantic/httpx2>

迁移指南的要点（[文档]，转述）：

1. 两步：换依赖、换 import。大代码库可以 `import httpx2 as httpx` 把 diff 压到最小。
2. **边界规则**：两个包的类互不相通，`isinstance()` 与 `except` 都不跨包。判据是「**接收对象的那个包决定你从哪个模块创建它**」。
3. 两个包可以并存，可以逐模块迁移，"There is no flag day"。
4. `alias_httpx()` 逃生舱：让全进程的 `import httpx` 解析到 `httpx2`。必须在入口最顶部调用（否则 `RuntimeError`），只允许应用调用、库不得调用。它治不了三件事：`importlib.metadata.version("httpx")`、名为 `httpx` 的 logger、以及子进程（子进程要自己再调一次）。
5. 明确劝阻手写 `sys.modules["httpx"] = httpx2`。

---

## 2. 公共 API 面差异（全量对照）

[探针] 直接比对 `httpx.__all__` 与 `httpx2.__all__`：

```
httpx 0.28.1 / httpx2 2.12.0
共有: 68 个名字
仅 httpx 有（httpx2 删除）: main
仅 httpx2 有（新增）: EventSource, FunctionAuth, Origin, SSEError, ServerSentEvent, alias_httpx, query, websocket
```

`httpx.main` 在 httpx2 里改成惰性属性并带 `DeprecationWarning`，指向 `httpx2` CLI 入口 [源码 `httpx2/__init__.py:102-114`]。本仓库不用它。

### 2.1 构造与类型逐项对照

[探针] `inspect.signature(cls.__init__)` 对比结果：

| 名字 | 差异 |
|---|---|
| `AsyncClient.__init__` | **仅一处**：`default_encoding: str \| Callable[[bytes], str]` → `str \| Callable[[bytes], str \| None]`（放宽，回调允许返回 `None`）。其余 20 个参数逐字相同 |
| `AsyncHTTPTransport.__init__` | **完全相同**（`verify, cert, trust_env, http1, http2, limits, proxy, uds, local_address, retries, socket_options`） |
| `Limits.__init__` | **完全相同** |
| `Timeout.__init__` | **完全相同**（`UnsetType` 哨兵的模块路径不同，无语义差别）；httpx2 额外给 `connect/read/write/pool` 加了类注解 [源码 `_config.py:+89..+93`] |

具体到派单点名的每个参数：

| 参数 | httpx 0.28.1 | httpx2 2.12.0 | 备注 |
|---|---|---|---|
| `limits=` | `Limits(100, 20, 5.0)` | 同 | 默认值 [探针] 逐字相同 |
| `timeout=` | `Timeout(timeout=5.0)` | 同 | |
| `transport=` | `AsyncBaseTransport \| None` | 同 | |
| `http2=` | `bool = False` | 同 | |
| `proxy=` | `ProxyTypes \| None` | 同 | |
| `proxies=` | **已不存在**（httpx 0.28.0 移除） | 不存在 | 不是 httpx2 的变化 |
| `headers=` | `HeaderTypes \| None` | 同 | |
| `base_url=` | `URL \| str = ""` | 同 | |
| `follow_redirects=` | `bool = False` | 同 | |
| `event_hooks=` | `Mapping[str, list[EventHook]] \| None` | 同 | |
| `mounts=` | 同 | 同（只补了 docstring） | |

`Request` / `Response` 构造签名相同；`Response` 的流式方法 [探针] 逐个 `hasattr` 检查，`aiter_bytes / aiter_raw / aiter_text / aiter_lines / aread / aclose / read / close / iter_bytes` 两边**全部存在**。返回类型注解从 `AsyncIterator[bytes]` 收紧为 `AsyncGenerator[bytes, None]`（`aiter_bytes` / `aiter_raw`），这是**更精确**的注解，不是收窄能力 [源码 `_models.py` diff]。

`client.stream()` / `client.build_request()` / `client.send(stream=True)`：签名相同，返回注解 `typing.Iterator[Response]` → `Generator[Response]`（同义）。[探针] 实测 `build_request` + `send(stream=True)` 在两边行为一致。

`MockTransport`：**无实质变化**，只是把 `handle_async_request` 的多行签名压成一行 [源码 `_transports/mock.py` diff 全文只有格式变化]。

### 2.2 异常层级

[源码 `httpx2/_exceptions.py:1-32`] 的层级注释与 httpx 0.28.1 **逐字相同**：

```
* HTTPError
  x RequestError
    + TransportError
      - TimeoutException  (ConnectTimeout / ReadTimeout / WriteTimeout / PoolTimeout)
      - NetworkError      (ConnectError / ReadError / WriteError / CloseError)
      - ProtocolError     (LocalProtocolError / RemoteProtocolError)
      - ProxyError
      - UnsupportedProtocol
    + DecodingError
    + TooManyRedirects
  x HTTPStatusError
* InvalidURL
* CookieConflict
* StreamError (StreamConsumed / StreamClosed / ResponseNotRead / RequestNotRead)
```

[探针] 机器比对 28 个公共异常类型的完整 MRO：

```
28 public exception types compared; MRO differences: NONE
```

**名字没改、继承关系没改。** `httpx.HTTPError` → `httpx2.HTTPError`，`ConnectError` / `ReadTimeout` / `RemoteProtocolError` 同名同位。

httpx2 新增一个 `HTTPXDeprecationWarning(UserWarning)`（不在 `__all__` 里）[源码 `httpx2/_exceptions.py:75-83`]，用途是让弃用警告默认可见。

**关键陷阱（跨包不相通）** [探针]：

```
issubclass(httpx2.ConnectError, httpx.TransportError): False
issubclass(httpx2.HTTPError,    httpx.HTTPError):      False
isinstance(httpx2.Response(200), httpx.Response):      False
isinstance(httpx.Response(200), httpx2.Response):      False
```

传输层实际抛出的异常也确实各归各家 [探针]，两边都对 `http://127.0.0.1:1/` 发请求：

```
httpx : httpx.ConnectError   TransportError=True
httpx2: httpx2.ConnectError  TransportError=True
```

---

## 3. extras 与底层依赖

[源码 `httpx2-2.12.0.dist-info/METADATA:33-53`]：

```
Requires-Dist: anyio>=4.10; sys_platform != 'emscripten'
Requires-Dist: httpcore2==2.12.0; sys_platform != 'emscripten'
Requires-Dist: httpx2-jsfetch; sys_platform == 'emscripten' and python_version >= '3.12'
Requires-Dist: idna>=3.18
Requires-Dist: truststore>=0.10; sys_platform != 'emscripten'
Requires-Dist: typing-extensions>=4.5.0; python_version < '3.13'

Provides-Extra: brotli   -> brotli>=1.2.0 / brotlicffi>=1.2.0.0
Provides-Extra: cli      -> click>=8.4.2, pygments==2.*, rich>=10,<16
Provides-Extra: http2    -> h2>=3,<5
Provides-Extra: socks    -> socksio==1.*
Provides-Extra: ws       -> wsproto>=1.2
Provides-Extra: zstd     -> backports-zstd>=1.0.0 (python_version <= '3.13')
```

| 问题 | 答案 |
|---|---|
| 有没有 `http2` extra？ | **有**，语义与 httpx 相同：拉 `h2`，仍需显式声明 |
| 有没有 `socks` extra？ | **有**，拉 `socksio`，仍需显式声明 |
| HTTP/2 与 SOCKS 是内置还是仍需 extra？ | **仍需 extra**，与 httpx 0.28 完全一致 |
| 底层还是 httpcore 吗？ | **是**，改名为 `httpcore2`（同仓库 vendored，版本号精确 pin） |

新增 `ws` extra（内置 WebSocket，vendored httpx-ws 0.9.0）与 `zstd` extra 的实现换成 `backports.zstd` / stdlib `compression.zstd`（原来是 `zstandard` 包）。

依赖侧两个减法/加法：**去掉了 `certifi`**、**加上了 `truststore`**（见 §4.2）。

[探针] 在探针环境（装了 `h2` 与 `socksio`）里实测：

```
httpx : http2=True OK    socks5 proxy OK (AsyncHTTPTransport)
httpx2: http2=True OK    socks5 proxy OK (AsyncHTTPTransport)
```

我们 `pyproject.toml` 里的 `"httpx[http2,socks]"` 直接对应 `"httpx2[http2,socks]"`。

---

## 4. 行为差异（非签名）

### 4.1 默认值：全部不变

[探针] 直接构造 `AsyncClient()` 并读取实际生效的默认值：

| 项 | httpx 0.28.1 | httpx2 2.12.0 |
|---|---|---|
| 默认 timeout | `Timeout(timeout=5.0)` | `Timeout(timeout=5.0)` |
| `DEFAULT_LIMITS` | `Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0)` | 同 |
| 实际连接池上限（读 `transport._pool`） | `max_conn 100 / max_ka 20 / ka_expiry 5.0` | 同 |
| `follow_redirects` | `False` | `False` |
| `max_redirects` | `20` | `20` |
| 默认请求头 | `accept: */*` / `accept-encoding: gzip, deflate, zstd` / `connection: keep-alive` / `user-agent: python-httpx/0.28.1` | 同，但 **`user-agent: python-httpx2/2.12.0`** |
| `ACCEPT_ENCODING` | `gzip, deflate, zstd` | 同 |
| `SUPPORTED_DECODERS` | `identity, gzip, deflate, zstd` | 同 |

**唯一的默认值变化是 User-Agent 字符串**，以及 logger 名从 `httpx` 变成 `httpx2` [源码 `httpx2/_client.py:110`：`logger = logging.getLogger("httpx2")`]。

### 4.2 TLS 默认校验：certifi → truststore

[源码 `_config.py` diff，对应 CHANGELOG httpx2 2.3.0]：

```python
# httpx 0.28.1
import certifi
if verify is True:
    if trust_env and os.environ.get("SSL_CERT_FILE"): ...
    elif trust_env and os.environ.get("SSL_CERT_DIR"): ...
    else:
        ctx = ssl.create_default_context(cafile=certifi.where())

# httpx2 2.12.0
import truststore
if verify is True:
    if trust_env and os.environ.get("SSL_CERT_FILE"): ...      # 不变
    elif trust_env and os.environ.get("SSL_CERT_DIR"): ...     # 不变
    else:
        # Default case: rely on the system trust store via `truststore`.
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
```

[探针] 实测 `create_ssl_context()` 返回的类型：

```
httpx : ssl.SSLContext
httpx2: truststore._api.SSLContext
```

- `SSL_CERT_FILE` / `SSL_CERT_DIR` 的优先级**不变**，仍然压过默认分支。
- `verify=<ssl.SSLContext>` 与 `verify=False` 路径**不变**。
- 顺带一个新的硬错误：`verify=<str>` 与 `cert=...` 同时给会 `raise TypeError`（httpx 0.28 只是各自 warn）[源码 `_config.py:+45..+51`，CHANGELOG 2.3.0 #990]。

**对我们的影响**：`build_http_client` 不传 `verify`，走默认分支，所以生效路径确实换了。风险面取决于部署机的 OS 信任库是否包含上游证书链，以及是否存在只在 certifi bundle 里的根。**这一点我没有在目标部署环境上验证过**，见 §8。

### 4.3 流式关闭语义：`aiter_raw` 的 `aclose()` 进了 `finally`

[源码 `_models.py` diff]：

```python
# httpx 0.28.1  Response.aiter_raw()
with request_context(request=self._request):
    async for raw_stream_bytes in self.stream: ...
for chunk in chunker.flush():
    yield chunk
await self.aclose()                       # <- 只在正常跑完时执行

# httpx2 2.12.0  Response.aiter_raw()
stream = self.stream.__aiter__()
try:
    with request_context(request=self._request):
        async for raw_stream_bytes in stream: ...
    for chunk in chunker.flush():
        yield chunk
finally:
    if isinstance(stream, AsyncGenerator):
        await stream.aclose()             # <- 新增：也关内层生成器
    await self.aclose()                   # <- 移进 finally
```

`aiter_bytes()` 同理，改用 `contextlib.aclosing(self.aiter_raw())` 包住内层迭代；`aread()` 也改成 `async with contextlib.aclosing(self.aiter_bytes())`。同侧还有 `BoundAsyncStream.__aiter__` 也加了 `finally: await stream.aclose()` [源码 `_client.py` diff]。

[探针] 用 `MockTransport` + 自定义 `AsyncByteStream`（`aclose` 里打点）实测：

```
httpx 0.28.1  early-break inside stream(): is_closed=False  events so far=[]
httpx 0.28.1  after ctx exit:              is_closed=True   events=['stream.aclose']
httpx 0.28.1  aiter_bytes generator aclose(): resp.is_closed=False  events=[]

httpx2 2.12.0 early-break inside stream(): is_closed=False  events so far=[]
httpx2 2.12.0 after ctx exit:              is_closed=True   events=['stream.aclose']
httpx2 2.12.0 aiter_bytes generator aclose(): resp.is_closed=True   events=['stream.aclose']
```

判读：

- **在 `client.stream()` 上下文里 `break` 出来 —— 两边一样**（`async for` 的 `break` 不会立刻 finalize 异步生成器，关闭仍由 `stream()` 的 `finally` 完成）。
- **显式 `await gen.aclose()` —— 有差异**。httpx 0.28 只关生成器、response 仍开着；httpx2 会连带关闭 response 与底层 stream。

这条**直接作废了本仓库的一句实测注释** `src/app/streaming/idle_timeout.py:26`：

> 「Measured 2026-08-20 against a real server: when the source is `httpx`'s `aiter_bytes()`, closing it does not close the response — `aiter_raw` runs `await self.aclose()` after its loop rather than in a `finally`, so the response is released by generator finalisation either way.」

在 httpx2 下这句话的两个分句都不再成立。方向上这对我们是**改善**（idle timeout 关掉生成器就真的释放了连接），但它是一处可观测行为变化，注释与相关测试需要同步。

### 4.4 `Response.headers` 大小写与多值语义：无变化

[探针] 同一组 header 在两边的完整行为：

```
httpx : ['set-cookie']='a=1, b=2'  get_list=['a=1','b=2']  keys=['set-cookie','x-foo']
        raw=[(b'Set-Cookie', b'a=1'), (b'set-cookie', b'b=2'), (b'X-Foo', b'V')]
        h['X-FOO']='V'   multi_items=[('set-cookie','a=1'),('set-cookie','b=2'),('x-foo','V')]
httpx2: 逐字相同
```

大小写不敏感查找、`raw` 保留原始大小写、多值用逗号拼接、`get_list()` / `multi_items()` 语义 —— **全部不变**。

新增（httpx2 2.5.0）：`Headers` 支持 `|` / `|=` / `__ror__` [源码 `_models.py:+289..+305`]。[探针]

```
httpx2 Headers | dict: {'a': '1', 'b': '2'}
httpx  Headers | dict: TypeError -> unsupported operand type(s) for |: 'Headers' and 'dict'
```

`Headers.get()` 的返回类型注解从 `Any` 收紧成带 overload 的 `str | None` / `str | _T`（CHANGELOG 2.10.0 #1121）—— 这会让 Pyright **发现新的类型错误**，属于静态检查面而非运行时。

### 4.5 取消/超时抛出的异常类型：无变化

异常类名与继承关系零差异（§2.2），`map_httpcore_exceptions` 的映射表 [源码 `_transports/default.py` diff] 只有格式变化，没有条目增删。

### 4.6 内容解码器：内部协议变了（只影响自定义解码器）

httpx2 把 `ContentDecoder.decode()` 的返回类型从 `bytes` 改成 `Iterator[bytes]`，为的是给解压加上 1 MiB 的分片上限（`MAX_DECODE_CHUNK_SIZE`，防解压炸弹式的内存峰值）[源码 `_decoders.py` diff，CHANGELOG 2.12.0 #1126]。`MultiDecoder` 的构造参数也从「解码器实例列表」变成「编码名列表」。

**本仓库不自定义解码器**，`SUPPORTED_DECODERS` 与 `ACCEPT_ENCODING` 对外表现不变，所以这条只是备案。另有 httpx2 2.4.0 把链式 `Content-Encoding` 解码器数量限制在 5 个。

### 4.7 其他零散语义变化（已核，均不影响本仓库主路径）

| 变化 | 来源 |
|---|---|
| `302 FOUND` 转 `GET` 时新增排除 `QUERY` 方法（RFC 10008 §2.5） | [源码 `_client.py` diff] |
| 同源判定改用新的 `URL.origin` / `Origin` 值对象，替代私有的 `_same_origin` / `_port_or_default` | [源码 `_client.py` diff，CHANGELOG 2.11.0 #1134] |
| `Request._prepare`：显式设了 `Transfer-Encoding` 时不再自动补 `Content-Length` | [源码 `_models.py` diff，CHANGELOG 2.11.0 #1137] |
| 无 `Set-Cookie` 头时跳过 cookie 抽取（性能） | [源码 `_models.py:+1101`，CHANGELOG 2.10.0 #1107] |
| `Response.elapsed` 改存在 stream wrapper 上（避免引用环），读不到 `_elapsed` 时回落到 `self.stream.elapsed` | [源码 `_models.py` diff，CHANGELOG 2.3.0 #948] |
| `httpx._utils.unquote` 被删除 | [探针] `dir()` 对比。我们不用它 |
| `no_proxy` 支持 IPv6 CIDR | [源码 `_utils.py` diff，CHANGELOG 2.5.0 #967] |
| 新功能：`client.sse()`（内置 SSE，替代 `httpx-sse`）、`client.websocket()` + `httpx2[ws]`（替代 `httpx-ws`）、`client.query()`（QUERY 方法） | CHANGELOG 2.5.0 / 2.6.0 |

---

## 5. httpcore → httpcore2 的差异（我们直接依赖了它的私有面，必须单列）

`httpcore2` 的 CHANGELOG 自称 "Renamed package ... **No other public API changed.**"，但从 2.0 到 2.12 之间对**连接池内部**做了实质重写。本仓库的 `stream_cap.py` 与 `composition.py` 都直接读写这些私有面，所以这一节是本次调研里风险最集中的部分。

`stream_cap.py` 的模块 docstring 自己写过：

> **Private surface, named so an upgrade knows what to check.** ... httpcore's CHANGELOG has never once mentioned the pool internals — including in the release that rewrote them — so **upgrading httpcore means diffing its source, not reading its release notes**.

这句话在这次升级上完全应验。

### 5.1 私有面存活性检查

[探针] 我们代码触及的每个私有名字：

| 名字 | httpx 0.28 / httpcore 1.0.9 | httpx2 / httpcore2 2.12.0 |
|---|---|---|
| `client._transport` | 有 | **有** |
| `client._mounts` | 有 | **有** |
| `transport._pool` | `httpcore.AsyncConnectionPool` | `httpcore2.AsyncConnectionPool` |
| `pool.create_connection` | 有 | **有** |
| `pool._requests` | 有 | **有** |
| `AsyncPoolRequest.connection` | 有 | **有** |
| `httpx._utils.get_environment_proxies` | 有 | **有，签名相同** |
| `httpcore.AsyncHTTPProxy` 不传 `socket_options` 给 `create_connection` 的缺陷 | 存在 | **仍然存在**（`create_connection` 里对 `AsyncForwardHTTPConnection` / `AsyncTunnelHTTPConnection` 都没传）[源码 `httpcore2/_async/http_proxy.py:136-158`] |

结论：`composition.py` 的 `_keep_proxy_connections_alive` 与 `_proxy_mounts` **原样有效**，`stream_cap.py` 的结构守卫测试（点名 `pool._requests` 与 `.connection`）**仍然全绿**。

### 5.2 【差异 A，高】连接池分配循环重写，`is_available()` 不再逐请求求值

httpcore2 2.3.0 CHANGELOG [文档]：

> * Rewrite `_assign_requests_to_connections` as a single-pass loop. ([#974](https://github.com/pydantic/httpx2/pull/974))

httpcore 1.0.9 的写法是**对每个排队请求重算一次可用连接** [源码 `httpcore/_async/connection_pool.py:301-308`]：

```python
queued_requests = [request for request in self._requests if request.is_queued()]
for pool_request in queued_requests:
    origin = pool_request.request.url.origin
    available_connections = [
        connection for connection in self._connections
        if connection.can_handle_request(origin) and connection.is_available()   # 每个请求都重新问一次
    ]
```

httpcore2 改成**每趟只算一次快照** [源码 `httpcore2/_async/connection_pool.py:312-325`]：

```python
# Snapshot the set of reusable connections once, rather than rebuilding
# it per queued request — this is what brings the loop from O(N*M) to O(N+M)...
available_connections = [
    connection for connection in self._connections
    if connection.is_available()                                                  # 整趟只问一次
    and not (connection.is_idle() and connection in request_connections and not connection.can_multiplex())
]
```

`StreamCappedConnection` 的**全部机制就是覆盖 `is_available()`**。快照化之后，一趟分配里 `is_available()` 只被问一次，之后即使已经分配了 N 个请求上去，这一趟剩下的请求依然会看到它「可用」。

[探针] 直接构造两个版本的 pool，塞入一个已建立的 capped 连接（`MAX=2`），再一次性排队 6 个请求，然后调用 `_assign_requests_to_connections()`：

```
httpcore 1.0.9 : MAX=2; 1 established conn + burst of 6 in ONE pass
    on established conn: 2   all counts: [2, 2, 2]   cap respected = True
httpcore2 2.12.0: MAX=2; 1 established conn + burst of 6 in ONE pass
    on established conn: 6   all counts: [6]         cap respected = False
```

**6 个请求全部落在同一条连接上，cap 完全失效，无任何报错。**

**触发条件的诚实边界**：这个失效需要「同一趟分配里有 ≥2 个排队请求」。我另外跑了「逐个到达」（每加一个请求就调用一次分配）的对照：

```
httpcore 1.0.9  (max_connections=100) DRIP x6 -> counts [2, 2, 2]; cap respected = True
httpcore2 2.12.0 (max_connections=100) DRIP x6 -> counts [2, 2, 2]; cap respected = True
httpcore 1.0.9  (max_connections=2)   DRIP x6 -> counts [2, 2, 2]; cap respected = True
httpcore2 2.12.0 (max_connections=2)   DRIP x6 -> counts [2, 2, 2]; cap respected = True
```

逐个到达时 cap 仍然守得住。真实进程里 `_assign_requests_to_connections` 会在**请求到达**与**响应结束（`PoolByteStream.aclose()` 把请求摘出 `_requests`）**两个时机触发，后者在池饱和、有请求排队时就会一趟分配多个。

**证据分级**：`is_available()` 不再逐请求求值 —— 强证据，源码 + 可复现探针，**足以据此行动**。「本项目的真实到达模式下会不会打到」—— 未测，只能说存在这条路径；**迁移时必须给 `stream_cap` 补一个多请求同趟分配的用例，并在真实并发下复测**，不能靠现有测试的绿色下结论。

另外 httpcore2 2.8.0 还有一条相关改动 [文档]：「Assign each released connection to a single queued request, eliminating multi-assignment churn in the connection pool.」

### 5.3 【差异 B，中】`AsyncConnectionInterface` 新增两个方法，我们的 wrapper 没转发

[源码 `httpcore2/_async/interfaces.py:98-108, 143-151`] 新增：

```python
def is_connected(self) -> bool:
    """... A connection in the NEW state (just created but not yet connected) returns `False`.
    The default implementation returns `not self.is_closed()` ..."""
    return not self.is_closed()

def can_multiplex(self) -> bool:
    """... The default covers HTTP/1.1-style implementations, which serve a single request at a time."""
    return False
```

`StreamCappedConnection`（`src/app/upstream/stream_cap.py:31-87`）逐个转发了 `can_handle_request` / `has_expired` / `is_idle` / `is_closed` / `info` / `aclose` / `handle_async_request` / `max_concurrent_requests`，但**这两个新方法不存在于 httpcore 1.0.9，所以没有被转发**，会用基类默认值：

1. **`can_multiplex()` 恒为 `False`** —— 内层若是已建立的 HTTP/2 连接，真实答案是 `True` [源码 `httpcore2/_async/connection.py:180-181`]。后果：池会把每一条 capped 连接当成 HTTP/1.1 式连接对待，在两处判定里走错分支（快照过滤 `connection_pool.py:322`、分配后剔除 `connection_pool.py:346`）。这正好和差异 A 纠缠 —— 我上面的探针里 wrapper 也没定义 `can_multiplex`，复现的就是这个组合。
2. **`is_connected()` 回落成 `not is_closed()`** —— 对处于 NEW 态（TCP 还没握手完）的内层连接，真实答案是 `False`，wrapper 会答 `True`。后果：池在 `connection_pool.py:280` 的「握手前被取消的垃圾连接直接丢弃」分支对 capped 连接永远不触发（对应 httpcore2 2.6.0 的 #983「Clean up garbage connections on cancellation」）。

`max_concurrent_requests()` 那段防御性转发（`stream_cap.py:78-84`，针对 httpcore PR #1088）在 httpcore2 2.12.0 里**仍未被用到** —— [探针] 全仓 grep httpcore2 无 `max_concurrent_requests`。留着无害。

修法（迁移时补两行转发）：

```python
    def is_connected(self) -> bool:
        return self._inner.is_connected()

    def can_multiplex(self) -> bool:
        return self._inner.can_multiplex()
```

### 5.4 httpcore2 其余相关变更（备案）

| 版本 | 条目 |
|---|---|
| 2.10.0 | HTTP/2 stream 失败时传播原异常而非 `KeyError`（#1093）；SOCKS5 下 `wss` 正确起 TLS（#1104）；大 h2 请求体避免二次拷贝（#1127） |
| 2.6.0 | 取消时清理 garbage connection（#983） |
| 2.4.0 | h2 stream 事件清理移入 `_state_lock`（#1013）；`NoAvailableStreamIDError` 时释放 h2 信号量（#1012）；`Lock` 改 `RLock` 防线程死锁（#1008） |
| 2.1.0 | 对端 `SETTINGS` 把发送窗口压成负数时等待正向流控额度，而不是让 h2 抛 `LocalProtocolError`（#935） |
| 2.0.0b1 | 继承上游 #1000：修 `max_keepalive_connections` 未被正确处理 |

其中 2.4.0 与 2.10.0 那几条 h2 修复，方向上正是我们 2026-08-20 那次 GOAWAY 事故所处的区域，**但我没有验证它们是否改变了 `RemoteProtocolError` / `h2.exceptions.ProtocolError` 的抛出形态**，`src/app/ghc_client/transport.py:31-33` 那段「hyper-h2 从缝隙里抛出、没人包装」的实测结论需要在 httpcore2 上重测。

---

## 6. 两个包能否同时安装并共存于一个进程

**能，而且是官方明确支持的迁移路径。**

探针环境本身就是证据：`httpx 0.28.1`、`httpcore 1.0.9`、`httpx2 2.12.0`、`httpcore2 2.12.0` 四个包并存 [源码 `site-packages/` 目录列表]。

[探针] 进一步验证 import 层面互不干扰 —— 同一进程、同一 event loop 里各建一个 client 并发发请求：

```
== coexistence: both clients in one loop ==
  results: {'who': 'httpx'} {'who': 'httpx2'}
  loggers: True / httpx2: True
  sys.modules distinct: True | httpcore distinct: True
```

逐项确认：

| 检查项 | 结果 |
|---|---|
| `sys.modules['httpx'] is not sys.modules['httpx2']` | `True` —— 两套完全独立的模块树 |
| `sys.modules['httpcore'] is not sys.modules['httpcore2']` | `True` —— **不共用 httpcore 单例**，各自有自己的连接池、backend、异常映射表 |
| logger 名 | 分别是 `httpx` 与 `httpx2`，两个 logger 同时注册，互不覆盖 [源码 `httpx2/_client.py:110`] |
| 全局可变状态 | `HTTPCORE_EXC_MAP`（`_transports/default.py` 里的模块级映射表）各自一份；`create_ssl_context` 无全局缓存；`_backends/auto.py` 的 backend 选择也是各自实例化。**未发现跨包共享的全局状态** |
| 环境变量读取 | 两边都读 `SSL_CERT_FILE` / `SSL_CERT_DIR` / `getproxies()`，是**读取**而非写入，不构成冲突 |
| 事件循环 | 都基于 `anyio` + `sniffio`，共用同一个 event loop 无问题（[探针] `asyncio.gather` 并发已验证） |

唯一的进程级全局副作用来自 **`alias_httpx()`**（它往 `sys.meta_path` 插一个 finder 并改写 `sys.modules["httpx"]`）[源码 `httpx2/_alias.py:48-71`]。它有自保护 [探针]：

```
alias_httpx() after httpx already imported
  -> RuntimeError: httpx was already imported; call `alias_httpx()` before any `import httpx`.
```

**注意这是一把双刃剑**：如果我们调用了 `alias_httpx()`，那么进程里就**不再**有真正的 httpx 了 —— 所有 `import httpx` 都指向 httpx2。这与「共存」是互斥的两种策略，不能同时用。

---

## 7. 对本仓库的具体影响与改法

本仓库当前状态：`pyproject.toml` 依赖 `httpx[http2,socks]`（锁 0.28.1）、`httpx-ws`、`opentelemetry-instrumentation-httpx`；`requires-python = ">=3.14"`。`src/` 下有 20+ 个文件 import httpx。

### 7.1 前提更正：只有 anthropic 拒收 legacy client

[源码 `openai/_httpx2.py:1-141`] 显示 openai 3.3.1 带了一层完整的 legacy 兼容 shim：`_loaded_legacy_httpx()` 读 `sys.modules.get("httpx")`，配合 `is_legacy_httpx_async_client()` / `normalize_httpx_timeout()` / `normalize_legacy_httpx_auth()` / `http_response_types()` 等函数，两边都吃。

[源码 `openai/_base_client.py:935-941`]：

```python
if (
    http_client is not None
    and not is_httpx2_sync_client(http_client)
    and not is_legacy_httpx_sync_client(http_client)      # <- legacy 放行
):
    raise TypeError(
        "Invalid `http_client` argument; Expected an instance of `httpx.Client` or `httpx2.Client` "
        f"but got {type(http_client)}"
    )
```

[源码 `anthropic/_base_client.py:1685-1688`] 没有任何 legacy 分支：

```python
if http_client is not None and not isinstance(http_client, httpx2.AsyncClient):
    raise TypeError(
        f"Invalid `http_client` argument; Expected an instance of `httpx2.AsyncClient` but got {type(http_client)}"
    )
```

[探针] 四种组合实测：

```
openai 3.3.1  anthropic 1.0.0
  openai(http_client=httpx.AsyncClient)    -> OK
  anthropic(http_client=httpx.AsyncClient) -> TypeError: Invalid `http_client` argument; Expected an instance of `httpx2.AsyncClient` but got <class 'httpx.AsyncClient'>
  openai(http_client=httpx2.AsyncClient)    -> OK
  anthropic(http_client=httpx2.AsyncClient) -> OK
```

派单里给出的报错文本与 anthropic 的源码**逐字相符**。**结论：迁移的真正硬约束只有 anthropic 一家**，而 openai 的 legacy 路径也不是长久之计（那层 shim 显然是过渡品）。这不改变「要迁」的结论，但改变了迁移可以怎么分批 —— 完全可以先只把喂给 anthropic 的那条链路换成 httpx2。

### 7.2 依赖改动

```toml
# pyproject.toml
dependencies = [
    "anthropic",
-   "httpx[http2,socks]",
+   "httpx2[http2,socks]",
-   "httpx-ws",                              # 见 7.5：httpx2 内置了，但我们的调用形态要一起改
+   "httpx2[ws]",
    "openai",
    "opentelemetry-instrumentation-httpx",   # 不用改，见 7.6
    ...
]
```

### 7.3 全局改名（机械部分）

官方推荐两种写法，我倾向第一种（显式），因为本仓库的注释里大量出现「httpx 的 xxx 行为」，保留 `httpx` 这个名字会让读者分不清说的是哪个包：

```python
# 方案一（推荐）：显式改名
-import httpx
+import httpx2
-import httpcore
+import httpcore2
```

```python
# 方案二：最小 diff，调用点不动
-import httpx
+import httpx2 as httpx
```

**不推荐** `alias_httpx()`：它是给「依赖链里还有别的库死抱着 httpx 不放」的场景用的逃生舱，而我们的依赖链里唯一还需要真 httpx 的是 `httpx-ws`，而那个恰好有内置替代品（§7.5）。

需要改的 import 面（[探针] `rg` 统计）：`src/` 下 20+ 文件，`tests/` 下 30+ 文件。类型注解 `httpx.Response` / `httpx.AsyncClient` / `httpx.AsyncBaseTransport` / `httpx.AsyncHTTPTransport` / `httpx.Headers` / `httpx.URL` 全部同名平移。

### 7.4 `stream_cap.py`（差异 A + B）—— 唯一需要动脑子的地方

```python
# src/app/upstream/stream_cap.py
-from httpcore import AsyncConnectionInterface, Origin, Request, Response
+from httpcore2 import AsyncConnectionInterface, Origin, Request, Response

 class StreamCappedConnection(AsyncConnectionInterface):
     ...
+    def is_connected(self) -> bool:
+        """httpcore2 新增。基类默认 `not is_closed()`，对 NEW 态连接答错，
+        会让池的 garbage-connection 清理分支（connection_pool.py:280）永不触发。"""
+        return self._inner.is_connected()
+
+    def can_multiplex(self) -> bool:
+        """httpcore2 新增。基类默认 False，会让池把已建立的 h2 连接当 HTTP/1.1 对待。"""
+        return self._inner.can_multiplex()
```

**但补上这两个方法不足以让 cap 重新生效** —— 差异 A 是机制层面的：httpcore2 每趟分配只问一次 `is_available()`，而 cap 的全部实现就在 `is_available()` 里。可选路线（**未做取舍，需要主会话/用户裁决**）：

- **路线 1：接受一趟内可能超额**。若实测本项目的到达模式下一趟排队请求数几乎恒为 1，则 cap 的实际效果基本不变。前提是**先测出来**，不能假设。
- **路线 2：改成拦 `handle_async_request` 计数并主动抛 `ConnectionNotAvailable`**。池收到这个异常会 `clear_connection()` 并重新排队（`connection_pool.py:224-231`），等于把「拒绝」从分配时挪到发送时。代价是多一次分配往返。
- **路线 3：转而 patch `pool._assign_requests_to_connections`** 而不是 `create_connection`。这把私有面依赖从「两个名字」扩大到「一整个方法体」，与该模块 docstring 里那条「wrap 而不 replace」的自律相悖。
- **路线 4：向上游提 issue/PR**，让快照在每次分配后失效或让 `is_available()` 参与逐请求判定。

无论走哪条，**必须先给 `tests/unit/upstream/test_stream_cap.py` 加一个「同趟多请求」的判别性用例** —— 现有的结构守卫（点名 `_requests` / `.connection`）在 httpcore2 上照样全绿，它对这个失效没有分辨力。

`composition.py` 的 `_keep_proxy_connections_alive` 与 cap 的**先后顺序**约束（cap 必须后跑，否则 keep-alive 闭包会盖掉 cap）在 httpcore2 上依然成立 —— 两者仍然都 patch 同一个 `create_connection`。

### 7.5 WebSocket（`httpx-ws` → `httpx2[ws]`）

`httpx-ws 0.9.0` 的元数据是 `Requires-Dist: httpx>=0.23.1` + `httpcore>=1.0.4` [源码 `httpx_ws-0.9.0.dist-info/METADATA:22-23`]，**它认的是真 httpx 的类，不接受 httpx2 client**。

httpx2 2.6.0/2.7.0 把 httpx-ws 0.9.0 **vendored** 成 `httpx2.websockets` [文档 CHANGELOG]。[源码] 对比两边的导出：

- 异常类 `HTTPXWSException` / `WebSocketUpgradeError` / `WebSocketDisconnect` / `WebSocketInvalidTypeReceived` / `WebSocketNetworkError` —— **同名、同继承**（`httpx2/websockets/_exceptions.py:11-51` vs `httpx_ws/_exceptions.py:5-47`）。
- `aconnect_ws` 存在于 `httpx2/websockets/_api.py:1544`，**签名与 httpx_ws 逐字相同**（`url, client=None, *, max_message_size_bytes, queue_size, keepalive_ping_interval_seconds, keepalive_ping_timeout_seconds, subprotocols, params, headers, cookies, auth, follow_redirects, timeout, extensions`）。
- 但 `aconnect_ws` / `connect_ws` **不在 `httpx2.websockets.__all__` 里**（`__all__` 只有 session/client/exception/transport 类），公开入口是 `client.websocket()`。

改法：

```python
# src/app/routes/responses_ws.py
-from httpx_ws import WebSocketDisconnect as UpstreamWebSocketDisconnect
-from httpx_ws import WebSocketNetworkError, WebSocketUpgradeError
+from httpx2.websockets import WebSocketDisconnect as UpstreamWebSocketDisconnect
+from httpx2.websockets import WebSocketNetworkError, WebSocketUpgradeError
```

```python
# src/app/openai/responses_ws.py
-import httpx
-from httpx_ws import aconnect_ws
+import httpx2
+from httpx2.websockets._api import aconnect_ws     # 注意：不在 __all__ 里，属半私有
```

**取舍点（需裁决）**：`aconnect_ws` 从 vendored 的私有模块导入，还是改用公开的 `client.websocket(url, ...)`？后者更稳，但 `ResponsesWebSocketClient.__init__` 目前把 `connect` 做成可注入参数（`connect: Callable[..., Any] = aconnect_ws`，`src/app/openai/responses_ws.py:23`）是为了测试替身，换成方法调用要改注入形态。我倾向改用 `client.websocket()` 并把注入点改成「注入一个 `connect(url, **kw)` 可调用，默认实现包一层 `self._http.websocket(...)`」，但这是实现取舍，不在本次调研授权范围内。

### 7.6 OpenTelemetry

**不用改依赖，但要改用另一个 instrumentor 类。** `opentelemetry-instrumentation-httpx 0.65b0` 已原生支持 httpx2 [源码 `opentelemetry/instrumentation/httpx/package.py`]：

```python
_instruments_httpx  = ("httpx >= 0.18.0",)
_instruments_httpx2 = ("httpx2 >= 2.0.0",)
_instruments_any = (*_instruments_httpx, *_instruments_httpx2)
```

[源码 `opentelemetry/instrumentation/httpx/__init__.py:1821-1826`]：

```python
class HTTPX2ClientInstrumentor(_BaseHTTPXClientInstrumentor):
    """An instrumentor for httpx2 Client and AsyncClient."""
    _module = _httpx2_module
    _module_name = "httpx2"
```

同侧还提供 `SyncOpenTelemetryTransportHttpx2` / 异步对应物。`src/app/observability/tracing.py` 里的 `HTTPXClientInstrumentor` 要换成 `HTTPX2ClientInstrumentor`。

### 7.7 异常捕获点

`src/app/ghc_client/transport.py:8-13` 与 `src/app/ghc_client/errors.py:44` 只需把 `httpx.` 换成 `httpx2.`，类名与继承关系不变。

**但要注意跨包不相通**：迁移过程中若还有一部分链路用 httpx、另一部分用 httpx2，这些 `except` 会漏掉另一半。官方迁移指南的原话是「Don't mix both packages within a single code path」。

`transport.py:31-33` 那条针对 hyper-h2 从缝隙里抛出的 `H2ProtocolError` 的旁路 —— httpcore2 2.10.0 有一条 "Propagate the original exception instead of raising `KeyError` when an HTTP/2 stream fails"（#1093），**方向相关但我没有验证它是否改变了那条缝隙的形态**，建议迁移时重跑 `.dev/docs/upstream/h2-goaway/` 下的 PoC。

### 7.8 `idle_timeout.py` 注释与行为（差异 C）

`src/app/streaming/idle_timeout.py:26` 那段 2026-08-20 的实测结论在 httpx2 下不成立（§4.3）。行为变化方向对我们有利，但注释必须改，相关测试若断言了「关生成器不关 response」会变红。

### 7.9 测试面

- `MockTransport` 语义不变，`tests/` 里的 mock upstream 只需改名。
- `tests/int/cassettes/` 的回放路径依赖 `httpx.Response` 构造与 `aiter_*` —— API 不变，只需改名。
- **Pyright 会报新错**：`Headers.get()` 返回类型从 `Any` 收紧成 `str | None`（CHANGELOG 2.10.0 #1121），任何把它当别的类型用的地方会被抓出来。这是好事，但要预留修复量。

---

## 8. 不确定项（明确标注，未用推测填空）

| # | 不确定的事 | 为什么不确定 | 怎么消除 |
|---|---|---|---|
| 1 | truststore 换掉 certifi 后，目标部署机能否正常校验 GitHub Copilot 上游的证书链 | 我只在探针环境验证了 `create_ssl_context()` **返回 truststore 的 context**，没有对真实上游发过 TLS 握手；部署机 OS 信任库内容我没看 | 在目标机上跑一次真实上游请求；或显式传 `verify=ssl.create_default_context(cafile=certifi.where())` 保持旧行为 |
| 2 | 差异 A（cap 失效）在本项目真实到达模式下会不会打到 | 探针证明了机制差异，但「一趟分配里出现 ≥2 个排队请求」的频率取决于并发形态与 `max_connections`，我没有测量生产流量形态 | 加一个同趟多请求的单测确认分辨力；在真实并发下观测每连接实际 stream 数 |
| 3 | httpcore2 的 h2 修复（2.4.0 #1012/#1013、2.10.0 #1093、2.1.0 #935）是否改变了 2026-08-20 GOAWAY 事故里 `H2ProtocolError` 从缝隙抛出的形态 | 我读了 CHANGELOG 条目，没有读这几个 PR 的 diff，也没有重跑 PoC | 重跑 `.dev/docs/upstream/h2-goaway/archive-260820/` 的 PoC |
| 4 | `openai` 的 legacy httpx 兼容层会维持多久 | `openai/_httpx2.py` 明显是过渡品，但 openai 没有对外声明弃用时间表 | 无法从本地证据回答；按「随时会消失」规划 |
| 5 | httpx2 vendored 的 `httpx2.websockets._api.aconnect_ws` 是否会保持可导入 | 它不在 `httpx2.websockets.__all__` 里，属半私有；官方公开入口是 `client.websocket()` | 用公开入口，或接受私有面依赖并加守卫测试 |
| 6 | 迁移指南全文我只拿到了摘要 | WebFetch 拒绝逐字复制整页 | 需要逐字条款时人工打开 <https://httpx2.pydantic.dev/migration/> |
| 7 | 本报告没有覆盖 `httpx2` 的 sync 侧（`Client` / `HTTPTransport`）与 WSGI/ASGI transport 的差异 | 本仓库只用 async 侧，按派单范围裁掉 | 若将来用到，同法 diff `_transports/wsgi.py` / `asgi.py`（[源码] 两文件 diff 均只有格式变化） |

---

## 附：复现方式

所有探针脚本都是独立的、只读的，可用探针环境的解释器直接重跑：

```bash
/home/xp/.claude/jobs/ca953617/tmp/latest-venv/bin/python -c 'import httpx, httpx2; print(sorted(set(httpx.__all__) ^ set(httpx2.__all__)))'
```

源码树 diff 的复现（在 `/tmp` 下做，不碰仓库）：

```bash
V=/home/xp/.claude/jobs/ca953617/tmp/latest-venv
SP=$(echo $V/lib/python*/site-packages)
mkdir -p /tmp/hxdiff2/a /tmp/hxdiff2/b
(cd $SP/httpx  && find . -name '*.py' -print0 | tar --null -cf - -T -) | (cd /tmp/hxdiff2/a && tar xf -)
(cd $SP/httpx2 && find . -name '*.py' -print0 | tar --null -cf - -T -) | (cd /tmp/hxdiff2/b && tar xf -)
find /tmp/hxdiff2/b -name '*.py' -exec sed -i 's/httpx2/httpx/g; s/httpcore2/httpcore/g; s/HTTPX2/HTTPX/g' {} +
diff -ru /tmp/hxdiff2/a /tmp/hxdiff2/b        # 3502 行，其中绝大多数是 ruff 行宽格式差异
```

`httpcore` / `httpcore2` 同法（`diff -ru` 3804 行）。
