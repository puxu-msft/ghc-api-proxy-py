# httpx2 迁移计划第 2 稿复评

复评范围严格限于 D3' 与 D7。计划、两份第 1 稿评审及迁移前 `stream_cap.py` 均按题定 ref 读取；没有读取并行迁移中的工作树版本。

VERDICT: needs-fix

D3' 的安全边界 `> max`、池内捕获 `ConnectionNotAvailable`、代理池复用同一处理路径等核心判断站得住，但计划漏记了饱和时系统性的内部重排放大，且拟议测试不足以验证 `>` 与 `>=` 的边界。D7 的方向——让开发与全新安装都使用 Starlette 1.x，而不是把旧 `httpx` 留在 dev 组——也站得住；然而 `fastapi>=0.141` 根本不会强制升级 Starlette，照计划执行仍会留下 `starlette==0.52.1` 并重现评审 B 的 blocker。

## Findings

### F1．`fastapi>=0.141` 不会把保守 lock 中的 Starlette 0.52.1 升到 1.x

- 严重度：blocker
- 置信度：高，足以阻断当前依赖切片
- 证据权重：强 enough to act on。既有 lock、发布元数据与隔离解析三者一致。
- 证据：
  - `efe5bb2:uv.lock` 当前是 `fastapi==0.129.0`、`starlette==0.52.1`。
  - FastAPI 0.141.0 与本次环境里的 0.141.1 都只声明 `starlette>=0.46.0`，没有 `starlette>=1`。所以 0.52.1 仍满足约束。
  - 我在 `/tmp/httpx2-r2-lock.3pPkN7` 从 `efe5bb2` 的 `pyproject.toml` 与 `uv.lock` 构造隔离 fixture，逐字应用 D6 的五项依赖改动后执行 `uv lock`。解析结果是 `fastapi=0.141.1`、`starlette=0.52.1`、`httpx=ABSENT`、`httpx2=2.12.0`。这正是评审 B 已证明无法收集 TestClient 测试的组合。
- 判断：D7 的产品裁决没有错，错的是表达该裁决的依赖约束。当前步骤 1 不能按计划实施。
- 必要修正：显式写 Starlette floor。若 floor 只表达本次真正依赖的能力，较准确的是 `fastapi>=0.133` 加 `starlette>=1.2.1`：FastAPI 0.133.0 首个移除了 `starlette<1.0.0` 上界的正式版本；Starlette 1.2.0 首个在 TestClient runtime 优先使用 httpx2，1.2.1 又把 TYPE_CHECKING 分支从 `httpx` 修成 `httpx2`。保留 `fastapi>=0.141` 也可以，但仍必须另加 `starlette>=1.2.1`；若项目有意只支持本轮实测版本，则直接写 `starlette>=1.6`，不要把 FastAPI floor 误写成 Starlette floor。

### F2．D3' 在池饱和时产生系统性的内部重排放大，现有表格与测试要求没有衡量它

- 严重度：major
- 置信度：高
- 证据权重：强 enough to act on。数字来自题定探针的同一真实 `AsyncConnectionPool.handle_async_request` 循环，只增加了 `handle_async_request` 调用与拒绝计数，没有改变分配逻辑。
- 证据：原探针的有限场景全部完成，因此我没有复现活锁；但 `not_available` 会把一次快照中过量分给连接的请求逐个抛回池里，再由每个请求各自触发一次完整重排。实测如下：

| 场景 | wrapper 调用数 | `ConnectionNotAvailable` 拒绝数 | 总耗时 |
|---|---:|---:|---:|
| burst=100，max_connections=4，cap=4 | 953 | 853 | 未单独计时 |
| burst=500，max_connections=2，cap=4 | 58,373 | 57,873 | 5.332s |
| burst=1000，max_connections=8，cap=4 | 22,977 | 21,977 | 4.593s |

- 公平性：burst=100、max_connections=4 时每请求尝试次数为 min=1、median=9.5、p90=24、max=28；所有请求最终完成，但完成顺序不是 FIFO。有限突发下这不是活锁，连续到达下是否会形成长尾饥饿，当前证据没有裁决。
- 超时语义：httpcore2 2.12.0 在每次 `ConnectionNotAvailable` 后执行 `clear_connection()` 并回到循环，而 `wait_for_connection(timeout=pool_timeout)` 每轮重新接收完整 timeout。异常不会冒出 pool，因此不会被 Anthropic/OpenAI SDK 当成上游错误重试；但该 timeout 也不是覆盖整段重排循环的总 deadline。
- 判断：D3' 的正确性机制仍可采用，但计划不能用“每一列都理想”概括它。那张表只量了 `peak/conns/closed_in_use`，漏掉了这个裁决独有的代价。
- 必要修正：在裁决中明确接受或拒绝这一饱和成本，并把 `attempts/rejections` 与有 deadline 的完成性加入探针或判别测试。无需追求一个任意性能门槛，但至少应记录目标规模下的量级，避免把 853 次内部拒绝描述成一次普通重排。

### F3．D3' 拟议测试不能验证计划专门论证的 `>` 边界，探针的 `peak` 也不是它声称的精确计数点

- 严重度：major
- 置信度：高
- 证据权重：强 enough to act on。可直接从题定探针第 89～101、125～128、164～168、185～191 行推出。
- 边界：`assigned_request_count() > max_streams` 是正确的。wrapper 被调用时本请求已经在 `pool._requests` 中并指向该连接，所以 count 包含本请求；count 等于 cap 时必须允许发送，超过 cap 才拒绝。
- 测试缺口：计划只要求“实际在飞数不超过 cap”。若实现误写成 `>=`，峰值会变成 cap-1，测试仍然全绿；“删掉拒绝分支应变红”的正控也不能区分这个 off-by-one。断言必须是饱和时 `peak == cap`，或另加恰好 cap 个请求都进入 inner 的边界用例。
- 计数点：`Meter.enter()` 不在 `FakeInner.handle_async_request()` 入口，而在返回的 response body 第一次被迭代时才执行。它测的是“正在消费 fake body 且停在 sleep 的请求数”，不是从请求进入 inner 到 response close 的完整在飞区间。当前 workload 的正控确实有分辨力——删除拒绝机制时它测到 peak=68——所以这些数字不是伪造；但这个投影仍可能漏掉进入 inner 后、开始迭代 body 前的重叠。
- `FakeInner` 的边界：它保留了真实池的分配、`clear_connection()`、重新排队与关闭路径，但固定答复 available/connected/multiplexing，并跳过 TLS、h2 状态机、远端 stream limit 及 response-header 时段。因此它足以比较三种 pool/wrapper 策略，不足以声称驱动了“真实连接”或证明真实 HTTP/2 stream 生命周期。建议把计数前移到 inner handler 入口，并在 body close 时退出；另用现有真实集成路径确认接线即可，不必把这个判别测试扩成网络测试。
- `closed_in_use` 判据成立：在 `aclose()` 入口检查仍被 `pool._requests` 引用的请求，恰好测的是 pool 是否关闭了已 reservation 的连接。它有意把“已分配但尚未进入 inner”也视为 in use，这与评审 A 所指出的不变量一致。探针不在请求进行中主动关闭整个 pool，因此没有把正常 shutdown 混进数字。

### F4．“这个缺陷不是 D3 引入的”数值上有依据，因果措辞仍会淡化 D3 的回归

- 严重度：minor
- 置信度：高
- 证据权重：强 enough to correct wording，不足以据此声称旧生产流量实际撞过该缺陷。
- 证据：按题定命令复跑旧栈，burst=100、max_connections=8、`inner.is_idle()=True` 时三种设计都得到 `conns=25 / closed_in_use=17`；计划引用的数字成立。命令首行显示 `httpcore2 1.0.9` 只是探针第 178 行把显示标签写死为 `httpcore2`，第 27 行实际按 `PROBE_CORE=httpcore` 导入了旧包。
- 限制：该结果依赖 `FakeInner.is_idle()` 恒为 `True`。它证明 httpcore 1.0.9 的算法在这个 reservation 窗口存在同形缺陷，不证明真实生产 h2 连接已经发生过 `closed_in_use`。计划自己也承认真正有流在飞时 h2 状态是 ACTIVE。
- 判断：更准确的表述是“D3 会把 httpcore 1.0.9 可出现的旧分配缺陷重新带进 httpcore2 2.12.0；D3 不是该算法形状的首次出现，但对迁移后的目标栈而言仍是新引入的回归”。第 2 稿已经撤回 D3，所以这不是实施 blocker；它只应避免用旧栈也有问题来削弱评审 A 的 finding。

## D3' 其余攻击结论

- 代理池与 SOCKS 池：`AsyncHTTPProxy`、`AsyncSOCKSProxy` 在 httpcore2 2.12.0 都继承 `AsyncConnectionPool`；`cap_streams_per_connection()` 又补丁各 transport 所持 pool 的 `create_connection`。因此 `ConnectionNotAvailable` 的捕获、`clear_connection()` 与重新排队路径一致。题定探针没有走 tunnel/SOCKS wire，但就 D3' 新增的 pool 行为而言没有发现分叉。
- 取消：D3' 不维护自己的可泄漏 counter，count 每次从 `pool._requests` 派生。httpcore2 在等待或发送阶段收到 `BaseException` 时移除 request 并重新分配；response body 正常或取消关闭时 `PoolByteStream.aclose()` 也在 cancellation shield 内移除 request。因此没有发现 D3' 特有的计数泄漏。仍建议把“取消一个正在重排的请求后其 reservation 消失”作为便宜的 targeted case，而不是据当前探针宣称取消全覆盖。
- 饱和行为：有限突发下所有连接都到 cap 时，没有可用连接且预算为 0，队列等待已有 response close；close 后 pool 再分配并取得进展。实测未活锁，但重排放大与非 FIFO 完成顺序是真实代价，见 F2。

## D7 依据与 Starlette 1.x 影响面

### 第三条依据是否够

原来的“1441 passed / 119 failed，119 条全部追溯到 Anthropic 类型校验”单独不足以证明 Starlette 没有隐藏回归。若某文件或 fixture 在 app/client 构造阶段先失败，测试 body、TestClient 请求、teardown 与 WebSocket session 都没有执行；给 119 条 traceback 归同一根因，只证明第一个可见失败，不证明移除它之后没有第二个失败。

我用两组隔离 fixture 补了这个缺口：

1. `/tmp/httpx2-r2-starlette.82YeNc` 保持 `efe5bb2` 源码与旧 httpx 路径，只把 Anthropic 固定到兼容旧 client 的 0.79.0，并解析到 `fastapi==0.141.1`、`starlette==1.6.0`。14 个含 TestClient 的文件共 155 tests 全过，只有 Starlette 因使用旧 httpx fallback 发出一条预期的 deprecation warning。这是对“Starlette 1.6 本身会不会把当前 ASGI/TestClient 面打坏”的隔离正证据，强 enough to proceed with the framework upgrade。
2. `/tmp/httpx2-r2-tests.4uZnIM` 从 `efe5bb2` 机械执行计划的 import renamer，并在题定最新 venv 中使用 Starlette 1.6/httpx2。TestClient 相关集合有 154 tests 通过，包括 `tests/int/test_responses_ws.py` 的 6 个 WebSocket tests；唯一未通过的是 `test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`，它是直接驱动 ASGI 的取消测试，不经过 TestClient，在机械迁移后先失败且 teardown 75s 内未结束，而同一固定提交的旧 httpx baseline 3.19s 通过。这个现象不是 Starlette 反例，因为两边都是 Starlette 1.6，且失败路径不走 TestClient；它说明的是原 1441/119 运行不能替代迁移后的回归，后续实施必须按计划真正跑到该测试并调查 httpx2 取消差异。

因此，D7 的第三条依据经过隔离后可以收窄为：“Starlette 1.6 的框架升级面已有 155 个相关 tests 通过”；不能继续写成旧的失败归因已经证明整个迁移没有其他失败。

### 版本与 API 影响面

- `TestClient` response：Starlette 1.2 起 runtime 优先绑定 httpx2，1.6 下返回 `httpx2.Response`。固定 ref 中没有对 TestClient response 做 `isinstance(..., httpx.Response)` 的断言；机械改名 fixture 的相关 route tests 通过，所以未发现类型身份依赖。
- WebSocket TestClient：`tests/int/test_responses_ws.py` 在 httpx2 路径下 6 tests 通过，`WebSocketDisconnect` 仍存在；未发现 1.x 特有破坏。
- 私有 `_utils`：固定 ref 已不再 import `starlette._utils.collapse_excgroups`，`src/app/streaming/sse.py` 使用本地 helper；这个已知 1.x 破坏面已解除。
- 异常类：仓库只直接使用 `ClientDisconnect` 与 `WebSocketDisconnect`，两者在 1.6 仍可导入，相关 tests 通过。1.0～1.6 官方 release notes 没有这两者改名记录。
- 1.0 删除项：按固定 ref 检索，没有使用 Starlette 已删除的 `on_startup/on_shutdown` 参数、`on_event/add_event_handler`、route/websocket/exception/middleware decorators、旧 `TemplateResponse`、`Jinja2Templates` env options、`FileResponse(method=...)`、`StaticFiles` 或 `HTTPEndpoint`。命中的 `server.lifespan.startup()/shutdown()` 是 uvicorn lifespan，不是被删除的 `starlette.routing.Router.startup()/shutdown()`。
- 其他行为变化：仓库没有使用本轮 release notes 中发生变化的 FileResponse、StaticFiles、SessionMiddleware、GZipMiddleware、templates 与 HTTPEndpoint，因此当前没有新增影响面。这个结论以 `efe5bb2` 的静态使用清单和上述 targeted tests 为范围，不外推到未检索的动态插件。

## 最小处置清单

1. D6 改为显式约束 Starlette；推荐 `fastapi>=0.133` + `starlette>=1.2.1`，或保留 `fastapi>=0.141` 再加 `starlette>=1.2.1`。重新从 `efe5bb2` 的 lock 做一次保守 `uv lock`，必须观察到 Starlette 实际升到 1.x 且旧 httpx 消失。
2. D3' 计划正文补记饱和重排放大；新测试把断言从 `peak <= cap` 收紧到饱和时 `peak == cap`，把计数点移到 inner handler 入口，并给完成性加 deadline。
3. 在实施后的全量回归中单独复核 `test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`；这不是 D7 blocker，但已实测证明 Anthropic 构造失败之后确实还能藏着另一个迁移失败。
4. 把旧栈归因改成“D3 会重新引入旧算法缺陷”，不要写成 D3 没有引入问题。

## Sources

- [FastAPI 0.141.0 PyPI metadata](https://pypi.org/pypi/fastapi/0.141.0/json)
- [FastAPI 0.133.0 PyPI metadata](https://pypi.org/pypi/fastapi/0.133.0/json)
- [Starlette 1.6.0 PyPI metadata](https://pypi.org/pypi/starlette/1.6.0/json)
- [Starlette release notes](https://www.starlette.io/release-notes/)
