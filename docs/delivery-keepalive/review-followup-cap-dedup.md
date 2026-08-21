# `10da106` cap 去重与补丁顺序复评

> **落盘说明**：本报告由评审 agent（异源模型）产出，但该 agent 被 harness 约束禁止创建评审 Markdown，故由主会话代为落盘，正文为其返回的全文，仅修正了传输过程中被转义的几处 `->`。

## 结论

**提交 `10da106 fix: cap each connection pool once, and keep the two patches on it in order` 可以集成进 `main`。** 未发现中等或更高严重度缺陷，也未发现 F1、F2、F3 修复失效。发现 1 项既有的低严重度 origin 格式边界，以及 1 项低严重度的文档论证过强；两者都不阻断该生产代码提交集成。

评审在隔离 worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive` 中完成。评审时 HEAD 为 `029bf0ac9cb3ab972ee84365d5976e176ad3e9ec`，其相对 `10da106` 只有文档提交；`composition.py`、`stream_cap.py` 与两个对应测试文件相对 `10da106` 无差异，因此所有生产代码与测试探针验证的是目标提交相同字节。

严重度口径如下：低表示不破坏当前正常配置的主要运行路径，但存在确定的边界错误或论证不准确；把握程度「高，强到足以行动」表示源码、受控变异与独立运行探针相互支持。

## 发现

### F1 `[低] [把握程度：高，强到足以后续修正] [既有问题，非本提交引入]` `_origin_of()` 会丢掉显式端口 `0`

位置：`src/app/server/composition.py:224-231`。

IPv6 加方括号的修法本身正确，但返回表达式仍以 `if parsed.port` 判断端口是否存在。httpx 会把显式端口 `0` 解析为整数 `0`，其布尔值为假，因此 `_origin_of()` 会把它当成「没有端口」。

独立探针观察如下：

- 输入 `socks5://user:secret@host.example:0`。`httpx.URL(input).port` 为 `0`，`_origin_of(input)` 输出 `socks5://host.example`，再解析输出时端口为 `None`。
- 输入 `socks5://user:secret@[::1]:0`。`httpx.URL(input).port` 为 `0`，`_origin_of(input)` 输出 `socks5://[::1]`，再解析输出时端口为 `None`。

正确判据应是 `parsed.port is not None`，而不是端口真值。该问题在本提交之前已经存在，只是本提交修改同一表达式时没有顺带修正。端口 `0` 虽是 httpx 接受的 URL 语法，但通常不是可工作的代理目的端口，因此实际影响限于诊断输出失真，不阻断本提交集成。

### F2 `[低] [把握程度：高，强到足以修正文档措辞] [文档论证问题，不是生产缺陷]` 将 H2 CONNECT 并发断言称为「同一判据的贵重述」过强

位置：`docs/agents/delivery-keepalive/deferred.md` 的「未采纳的建议」一节。

不采纳 H2 CONNECT fixture 的决定，若严格限定为「防止 keep-alive 与 cap 两处安装顺序被调换」，是成立的。实测反序时，代理池的 `create_connection()` 必然从 `StreamCappedConnection` 退化为裸 `AsyncTunnelHTTPConnection`，当前 wrapper 形状断言可以直接、稳定且便宜地捕获这一失效。

但 wrapper 形状断言与真实并发上界不是同一个性质。相对于当前只检查 wrapper 类型与 socket options 的接缝回归，H2 CONNECT 并发断言还可以额外捕获以下失效形态：

1. `build_http_client()` 仍安装 wrapper，但把错误的 cap 数值传给 `cap_streams_per_connection()`。例如配置为 2，却传入 999。当前接缝测试只看类型，仍会通过；5 个并发请求可能继续共享一条 H2 tunnel。该错误也可以通过读取 `_max_streams` 的更窄断言捕获，但当前 wrapper 判据没有捕获。
2. wrapper 仍存在，但 `assigned_request_count()` 与真实 `AsyncHTTPProxy` pool 的 request bookkeeping 脱节，或者未来 httpcore 让 proxy pool 使用不同的分配路径。通用 `AsyncConnectionPool` 的现有并发测试覆盖了当前共同机制，却没有证明未来 proxy 特化路径必然继续相同。
3. 被检查的 pool 仍产出 wrapper，但实际请求路由以后改走另一个 transport 或 pool。当前显式 proxy 配置下 `_mounts == {}`，所以今天不存在这个缺口；真实入口的 CONNECT 并发测试会在未来路由接线改变时暴露它。
4. wrapper 安装与 keep-alive socket options 都存在，但真实 CONNECT、TLS、ALPN 与 H2 multiplexing 接缝发生变化，导致 pool 没有按 wrapper 的 availability 答案控制每条 tunnel 的并发数。形状断言无法观察到 wire 侧的连接分布。

因此，更准确的文档表述应是：**当前不采用 H2 CONNECT fixture，是因为 F2 的直接目标只是锁定两个补丁的安装顺序，而该顺序已经有受控反序变异和 wrapper 接缝断言；更宽的代理端到端并发性质确有额外分辨力，但现有通用真实 pool 并发测试已经覆盖核心调度机制，在当前任务里新建 CONNECT fixture 的额外收益不足以抵偿复杂度。** 这是一项基于范围与 ROI 的取舍，不应表述成两个判据在证明力上等价。

## 去重完整性

### 真实 `build_http_client()` 环境矩阵

把握程度：**高，强到足以确认当前 httpx 0.28.1 与本项目 composition root 的 transport／pool 拓扑。**

探针先清除以下八个变量，再逐组设置环境并调用真实 `build_http_client()`：

```python
HTTP_PROXY
HTTPS_PROXY
ALL_PROXY
NO_PROXY
http_proxy
https_proxy
all_proxy
no_proxy
```

每个 client 都配置 `max_streams_per_connection=2`。探针枚举 `client._transport` 与全部 `client._mounts.values()`，分别按 `id(transport)` 与 `id(transport._pool)` 分组，并记录每个 pool 的 `_proxy_url.origin`。实际加载的模块路径为：

```text
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive/src/app/server/composition.py
```

观察结果如下：

| 环境组合 | transport 身份分组 | pool 身份分组 | 结论 |
|---|---|---|---|
| 无代理变量 | 1 个 default direct transport | 1 个 direct pool | 无重复 |
| `ALL_PROXY=http://127.0.0.1:7890`，3 条 `NO_PROXY` | default 与 3 个 `NO_PROXY` mount 共用同一个 direct transport，另有 1 个 proxy transport | 1 个共享 direct pool，另有 1 个 proxy pool | 只有 direct transport 需要按身份去重 |
| `HTTP_PROXY` 与 `HTTPS_PROXY` 指向同一个 URL | default direct 加 2 个不同 proxy transport，共 3 组 | 1 个 direct pool 加 2 个不同 proxy pool，共 3 组 | 相同 URL 不会复用 transport 或 pool |
| `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 全部指向同一个 URL | default direct 加 3 个不同 proxy transport，共 4 组 | 1 个 direct pool 加 3 个不同 proxy pool，共 4 组 | 三个代理规则都必须分别安装 cap |
| 上述三个代理变量相同，再加 2 条 `NO_PROXY` | default 与 2 个 `NO_PROXY` mount 共用一个 direct transport，另有 3 个不同 proxy transport | 1 个共享 direct pool，另有 3 个不同 proxy pool | 当前 `id()` 去重同时满足「共享 direct 只装一次」和「同 URL proxy 各装一次」 |
| 显式 config proxy 为 `http://127.0.0.1:9999`，环境仍设置 HTTP／HTTPS proxy | `_mounts == {}`，default 为显式 proxy transport | 只有显式 proxy pool | 与既有显式 proxy 语义一致 |

其中「相同 `HTTP_PROXY` 与 `HTTPS_PROXY` URL」的一次实际运行中，三个 transport ID 分别为 `131705611990768`、`131705612428656`、`131705607391696`；三个 `id(pool)` 分组也彼此不同。「相同 HTTP／HTTPS／ALL proxy URL」的一次运行中，四个 transport ID 分别为 `131705611943680`、`131705612137552`、`131705612438256`、`131705612139344`。这些具体 ID 只用于证明同一次运行中的身份不相等，不外推为稳定值。

根因也与观察一致：`_proxy_mounts()` 对每个非 `None` URL 都单独调用 `transport(url)`，每次构造新的 `httpx.AsyncHTTPTransport` 与 pool；只有 `url is None` 的 `NO_PROXY` 项显式复用传入的 `direct` 对象。因此，没有漏掉「相同代理 URL 会共用对象」的情况，因为真实 composition root 在该情况下根本不共用对象。

反方向也没有发现误折叠。当前字典以 `id(transport)` 为键，HTTP／HTTPS／ALL 三个不同对象即使 URL 相同也保留三个条目，因此三个独立 pool 都被 `_cap_one()`。

### 「按 pool 一次」与「按 transport 一次」的边界

实现变量名为 `pools_to_cap`，实际按 transport 身份去重。真实 `build_http_client()` 中，一个 transport 对应一个 pool，唯一共享 pool 的情况也是同一个 direct transport 被重复引用，因此两者在生产拓扑中等价。

理论上可以通过私有属性改写，让两个不同 transport 指向同一个 pool；当前代码会给该 pool 包装两次。但这不是 `build_http_client()`、httpx 0.28.1 或公开 transport 构造方式产生的形态，需要外部直接篡改 `_pool`。它不构成当前产品缺陷。若将来引入公开 wrapper transport 或共享 pool 工厂，应重新决定去重身份究竟是 transport 还是 `_pool`。

## `id()` 选择

把握程度：**高，强到足以保留当前实现。**

### 对象生命周期

`(client._transport, *client._mounts.values())` 会先构造持有全部非空 transport 的 tuple，随后 `pools_to_cap` 又强持有每个首见 transport，client 自身也持续持有 default 与 mounts。收集和迭代期间没有对象可以析构，因此 CPython 不可能在该字典仍使用旧键时复用相同 ID。提交注释中关于生命周期的论证成立。

### 迭代顺序

Python 字典保留插入顺序，因此 `_cap_one()` 顺序是 default transport 先、mounts 首次出现顺序随后。真实 composition root 中不同 transport 拥有不同 pool，各 `_cap_one()` 只修改自己的 `pool.create_connection`，所以顺序不影响结果。共享 direct transport 只保留第一次出现，正是目标行为。

如果将来出现不同 transport 共用 pool 的非当前拓扑，顺序才会影响 wrapper 层数；那属于前述「按 transport 还是按 pool」的新设计边界，而不是当前字典顺序缺陷。

### 值相等 transport 正控

为验证 `set` 与 `id()` 的差别，我构造了：

```python
class EqualTransport(httpx.AsyncHTTPTransport):
    def __eq__(self, other: object) -> bool:
        return isinstance(other, EqualTransport)

    def __hash__(self) -> int:
        return 0
```

然后创建两个不同实例，分别作为 client default transport 与 `mounts={"http://": second}` 的 mounted transport。一次实际运行中，两者 ID 分别为 `127560086311264` 与 `127560086249040`，但 `len({first, second}) == 1`。

调用当前 `cap_streams_per_connection(client, 2)` 后，两个 transport 各自的 pool 都产出 `StreamCappedConnection`，且两者的 `_inner` 都不是另一层 `StreamCappedConnection`，证明当前实现对两个值相等但身份不同的对象分别包装且各只包装一次。

提交论证的方向成立：这里要表达的是对象同一性，`id()` 比依赖未来 `__eq__`／`__hash__` 语义的 set 更稳。措辞上有一个细微条件：如果未来 httpx 只实现 `__eq__` 而不实现可兼容的 `__hash__`，set 会因对象不可哈希而显式报错，而不是静默折叠；只有同时提供值哈希时才会静默折叠。本探针构造的是后一种确实可能的形态。这不削弱采用 `id()` 的结论。

## 两条 F1 回归的独立分辨力复验

把握程度：**高，强到足以确认两条测试都命中预定故障机制。**

先以冻结 patch 把 `cap_streams_per_connection()` 退回旧的两段式遍历：

```python
_cap_one(client._transport, max_streams)
for mounted in client._mounts.values():
    if mounted is not None:
        _cap_one(mounted, max_streams)
```

运行前通过 `inspect.getsource()` 确认测试进程加载的是该 worktree 的变异源码，源码中不存在 `pools_to_cap`，且存在 `_cap_one(client._transport, max_streams)`。

### `test_one_pool_is_capped_once_however_many_mounts_reach_it`

测试按预期变红，失败点为：

```text
AssertionError: the same pool was capped once per mount
assert not True
```

失败对象显示 `created._inner` 本身仍是 `StreamCappedConnection`。repr 中可见内层连续三个 `[capped 0/2]`，再加最外层共四层，正好对应 default transport 加三条 `NO_PROXY` mount。该红灯直接证明测试能区分「一次包装」与「按每次引用包装」，不是类型恒真断言。

### `test_a_long_no_proxy_list_still_opens_a_connection`

测试按预期变红，并在 `_connection_for()` 调用 `pool.create_connection()` 时抛出 `RecursionError`。traceback 反复出现：

```text
return StreamCappedConnection(inner_create(origin), cast(_PoolWithRequests, pool), max_streams)
```

失败发生在任何 socket 连接之前，原因就是 1100 条 `NO_PROXY` 规则形成的递归闭包链，不是 DNS、网络或 fixture 失败。

随后使用同一冻结 patch 做 `git apply --reverse --check` 与反向应用。恢复后两条测试结果为 `2 passed`，worktree 状态为空。

这两条回归分工清晰：第一条精确断言结构不变量，第二条钉住用户可见的失败机制。二者不是重复测试。

## F2 接缝回归的独立分辨力复验

把握程度：**高，强到足以确认当前测试能锁定反序。**

受控变异从 transport factory 中移除初始 `_keep_proxy_connections_alive()`，并在 `cap_streams_per_connection()` 之后对本测试使用的显式 proxy default transport 调用 `_keep_proxy_connections_alive()`。这使目标 proxy pool 上的真实安装顺序变为 cap 先、keep-alive 后。

运行前通过 `inspect.getsource(build_http_client)` 确认实际加载路径为该 worktree，且源中 `cap_streams_per_connection(client, options.max_streams_per_connection)` 出现在 `_keep_proxy_connections_alive(client._transport, options.socket_options)` 之前。

`test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive` 按预期变红。原文要点为：

```text
AssertionError: the keep-alive patch was installed over the cap
assert False
where False = isinstance(<AsyncTunnelHTTPConnection [CONNECTING]>, StreamCappedConnection)
```

这正是预定失效：keep-alive closure 覆盖 cap closure，代理池产出裸 `AsyncTunnelHTTPConnection`，同时没有出现无关异常。

随后使用冻结 patch 通过反向检查并恢复。恢复后该测试为 `1 passed`，worktree 状态为空。

## `cast(Any, transport)._pool` helper

把握程度：**高，强到足以确认没有把运行时断言变成恒真。**

`typing.cast()` 在运行时不转换、不包装也不捕获对象，只影响静态类型检查。`cast(Any, transport)._pool` 若属性不存在仍会抛 `AttributeError`，`pool.create_connection()` 若不存在或失败也仍会直接抛错。

两轮变异本身构成了比静态阅读更强的正控：

- 旧遍历变异通过 `_connection_for()` 观察到多层 wrapper 与 `RecursionError`，两条测试都变红。
- 安装反序变异通过 `connection_the_pool_would_build()` 观察到裸 `AsyncTunnelHTTPConnection`，接缝测试变红。

因此，这两个 helper 没有缓存预期值、伪造 wrapper、吞掉异常或让断言永远为真。`Any` 只把第三方私有未类型化表面的 Pyright 诊断集中到一个位置。

需要区分的是：`Any` 确实会让 helper 内部未来的拼写错误不受静态检查，但运行测试时会显式失败。这是有意接受的静态边界，不是运行时分辨力削弱。

## IPv6 origin 修法

把握程度：**高，强到足以确认目标 IPv6 修复正确；端口 0 例外见 F1。**

独立 round-trip 探针结果如下：

| 输入 | `_origin_of()` 输出 | httpx 读回 |
|---|---|---|
| `socks5://user:secret@[::1]:1080` | `socks5://[::1]:1080` | host `::1`，port `1080`，userinfo 为空 |
| `socks5://user:secret@[::1]` | `socks5://[::1]` | host `::1`，port `None`，userinfo 为空 |
| `socks5://user:secret@[fe80::1%25eth0]:1080` | `socks5://[fe80::1%25eth0]:1080` | host `fe80::1%25eth0`，port `1080` |
| `socks5://user:secret@[fe80::1%eth0]:1080` | `socks5://[fe80::1%eth0]:1080` | host `fe80::1%eth0`，port `1080` |

已经带方括号的 URL 不会双重加括号，因为 `httpx.URL.host` 返回的是去掉方括号后的 host。zone ID 的 `%25eth0` 与 httpx 也接受的原始 `%eth0` 都被保留并可读回。

scheme 缺失的 `//[::1]:1080` 与 `[::1]:1080` 不会进入真实 warning 路径，因为 `_is_socks()` 返回假。直接调用 `_origin_of()` 会分别得到 `://[::1]:1080` 与 `://`，但该 helper 的调用前置条件是候选 URL 已由 `_is_socks()` 判定为 SOCKS，因此这不是当前可达 warning 缺陷。

空 host 的 `socks5://` 会输出 `socks5://`。`socks5:example.com` 也被 `_is_socks()` 接受，但 httpx 将其解析为空 host，helper 同样输出 `socks5://`。这两种都不是可工作的代理配置；既有评审已确认 httpx transport 最终不会把它们变成有效连接。当前 helper 没有负责替 transport 提前验证整个代理 URL，因此不把它们归为本提交回归。

凭据仍不会进入日志。所有带 `user:secret@` 的探针输出均不含 `user`、`secret` 或任何 userinfo；logger 接收的参数是 `_origin_of()` 返回值，不再接触原 URL。

## 静态检查与回归

把握程度：**高，结论限定于当前 worktree、Python 3.14、httpx 0.28.1 与 httpcore 1.0.9。**

- 目标回归基线中，三条重点测试结果为 `3 passed`。
- F1 两条测试恢复后结果为 `2 passed`。
- F2 接缝测试恢复后结果为 `1 passed`。
- `uv run pytest -q --ignore=tests/e2e` 结果为 `1554 passed, 3 skipped`，耗时 `102.38s`。
- `uv run ruff check src tests` 结果为 `All checks passed!`。
- 当前 `uv run pyright src tests` 结果为 `21 errors, 0 warnings, 0 informations`。
- 从 `10da106^` 通过 `git archive` 解出父提交到 `/tmp`，复用同一 `.venv` 并运行同一 `pyproject.toml` 配置，结果同样为 `21 errors, 0 warnings, 0 informations`。本提交 Pyright 增量为 0。
- `tests/e2e/claude` 的既有 `ModuleNotFoundError: No module named 'harness'` 未计入本提交，本轮按指定命令忽略 `tests/e2e`。
- 最终 `git status --short` 为空，`git diff --check` 通过。两轮生产源码变异均已用各自冻结 patch 反向恢复，没有把变异或其他改动留在 worktree。

## 集成判断

**可以集成进 `main`。**

F1 的 transport 身份去重对真实 `build_http_client()` 产生的全部当前拓扑完整：共享的 direct transport 只包装一次，相同 URL 但独立构造的 proxy transports 分别包装。`id()` 在对象生命周期、相等语义与迭代顺序上均站得住。

F2 回归能够可靠锁定当前两处补丁安装顺序。拒绝新增 H2 CONNECT fixture 的范围决策可以保留，但文档应把理由改为「对本次顺序缺陷而言已有足够且更便宜的判据」，不要再声称真实并发断言与 wrapper 判据证明的是同一性质。

F3 对普通 IPv6、无端口 IPv6 与带 zone ID IPv6 均修复正确，凭据不进入日志。显式端口 `0` 的丢失是低严重度既有边界，可独立跟进，不应阻断本提交。
