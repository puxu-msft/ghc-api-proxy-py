# 评审报告 A：httpx2 迁移计划（对抗性评审）

> **落盘说明**：本报告由评审 agent（gpt-opus）产出，但该 agent 受 harness 限制无法新建文件，正文经由会话原样转录落盘。评审对象是 `docs/agents/httpx2-migration/plan.md` 在 2026-08-21 12:00 前后的版本。**转录者按语与后续实测见文末「主会话处置」一节**，正文本身未作改动。

**VERDICT：needs-fix**

计数：`blocker=1 major=4 minor=5 nit=0`

## Blocker

### B1．D3 会在连接池达到 `max_connections` 时关闭仍承载已分配请求的空闲 HTTP/2 连接

- 严重度：blocker
- 置信度：高，足以阻断实施
- 证据：
  - `httpcore2/_async/connection_pool.py:318-324` 快照 `available_connections` 和连接预算。
  - 同文件 `:343-366` 中，`can_handle_request()` 返回 `False` 后不仅会创建连接；预算耗尽时还会把 `is_idle()` 为真的连接移出池并加入 `closing_connections`。
  - 计划所述 wrapper 仍把 `is_idle()` 委托给 inner。已建立、当前没有实际 stream 的 HTTP/2 连接会答 `True`；但在同一分配趟里，刚分给它的请求尚未开始发送，inner 仍保持 IDLE。
  - 现有探针 `.dev/exp/httpx2-cap-probe/probe_cap.py:29-30` 把 `FakeInner.is_idle()` 固定为 `False`，恰好屏蔽了该分支。
- 单变量反例：只把探针 inner 的 `is_idle()` 改为 `True`，`cap=2`、6 个请求时得到：

```text
max_connections=1
  made counts        = [2, 1]
  pool connection ids= [1]
  closing ids        = [0]
  assigned ids       = [0, 0, 1, None, None, None]

max_connections=2
  made counts        = [2, 1, 1]
  pool connection ids= [1, 2]
  closing ids        = [0]
  assigned ids       = [0, 0, 1, 2, None, None]
```

连接 `0` 已承载两个已分配请求，却被放入 `closing`。`handle_async_request()` 会先关闭这些连接，再让等待任务取得已分配连接，随后只能依靠 `ConnectionNotAvailable` 清除并重新排队。这不是「偏保守」，而是破坏连接池的 reservation 不变量并引入重试抖动。

`AsyncHTTPProxy` 与 `AsyncSOCKSProxy` 分别在 `httpcore2/_async/http_proxy.py:50` 和 `httpcore2/_async/socks_proxy.py:103` 继承同一个 `AsyncConnectionPool`，因此 tunnel HTTP/2 与 SOCKS HTTP/2 路径同样受影响。

**要求：撤回当前 D3 裁决。新的判别用例至少必须覆盖 `inner.is_idle() == True`、有限 `max_connections`，并断言任何仍被 `pool._requests` 引用的连接都不会进入 `closing_connections`。单纯把谓词移到 `can_handle_request()` 不能实施。**

## Major

### M1．计划严重低估了 D3 的连接放大，不是普通的「多几条连接」

- 严重度：major
- 置信度：高
- 当前算法只把既有连接保留在 `available_connections`；本趟新建连接不会加入快照。因此既有连接达到 cap 后，每个剩余请求各建一条连接。
- 实测 `burst=100`、`cap=4`、`max_connections=100`：

```text
burst=100 cap=4 max_connections=100: made=97 retained=97 closing=0 assigned=100 max_assigned_on_one=4
```

理想分组只需 `ceil(100 / 4) = 25` 条连接，D3 却创建 97 条，并发触发大量 TCP/TLS/代理握手。默认连接预算正是 100；默认 keepalive 上限为 20，因此其中大部分连接完成后会被关闭，不符合计划所称「多出的连接会在后续趟次被复用」。

这会把 stream cap 从「限制单连接爆炸半径」变成「突发时接近一请求一连接」，代价不能按「方向偏保守」接受。

### M2．实施顺序产生确定的不可运行中间状态，且第 2、3 步定义重叠

- 严重度：major
- 置信度：高
- 按第 1 步只切依赖并重新解析，旧 `httpx` 与 `httpx-ws` 都不会继续安装。隔离 fixture 实测解析到 `httpx2==2.12.0`、`starlette==1.6.0`，没有 `httpx`；随后导入当前源码：

```text
ModuleNotFoundError: No module named 'httpx'
import_rc=1
```

首个失败点为 `src/app/ghc_client/account.py:3`。此外，在第 5 步之前，`responses_ws.py` 仍 import 已从依赖中删除的 `httpx_ws`；在第 6 步之前，`tests/unit/test_imports.py` 仍要求旧模块名。因此计划所称「每一步都是可单独提交的语义单元」掩盖了第 1～5 步无法进行常规测试收集的事实。

第 2 步又明确执行全局 `httpx.` → `httpx2.`，这已经会修改全部八处 `cast_to=httpx.Response`；第 3 步因而没有独立产物。若第 2 步故意排除这些位置，计划必须列明排除集，而不能同时声称全局机械替换。

应将依赖、源码 import、WebSocket import 和 import 守卫组成一个可导入切片；或者明确设计双栈过渡，并在过渡期让异常捕获同时覆盖两套异常家族。

### M3．D6/Q1 的版本约束不完整，选项 B 不能建立计划依赖的兼容合同

- 严重度：major
- 置信度：高
- D6 没有给 `httpx2` 下界，但计划依赖：
  - `AsyncClient.websocket()`，该功能到 2.6.0 才加入。
  - 针对 2.12.0 连接池源码作出的 D3 判断。
- `opentelemetry-instrumentation-httpx` 也没有下界，而 `HTTPX2ClientInstrumentor` 到 `0.65b0` 才存在。当前锁文件仍是旧生态；仅因一次 fresh resolution 恰好选择最新版，不能替代依赖合同。
- 若给 Starlette 采用直观的大版本上界 `starlette<1`，`uv pip compile` 实测解析为：

```text
anthropic==1.0.0
fastapi==0.141.1
httpx2==2.12.0
openai==3.3.1
starlette==0.52.1
```

`starlette==0.52.1` 的 `starlette/testclient.py:37-44` 强制 import 旧 `httpx`，但该解析结果不安装 `httpx`，测试层会直接失败。SDK 不会退回旧大版本，因为 `anthropic>=1`、`openai>=3` 已给出 floor；真正会回退旧 HTTPX 路径的是未设兼容 floor 的 Starlette/FastAPI 组合。

更根本的问题是，本迁移最昂贵的差异来自 `httpcore2` 的 2.x minor 私有实现变化；`httpx2>=2,<3` 并不能防止同类事件再次发生。选项 B 只能挡 SDK 下一大版本，既不提供可复现安装，也不保护 private API。

建议至少声明实际兼容 floor，例如 `httpx2>=2.12,<3`、`opentelemetry-instrumentation-httpx>=0.65b0`，并为 Starlette 写出已经实测使用 HTTPX2 TestClient 的 floor。对直接依赖的 private `httpcore2` 行为，应新增「窄兼容范围或精确 pin」选项，而不是把选择限定为大版本上界与改变安装方式两类。

### M4．最终回归排在可能修改代码的 V1/V2 之前，且 V2 当前不能照文档执行

- 严重度：major
- 置信度：高
- 计划先做最终回归，再做真实验证。
- V1 失败会新增 `verify=` 代码和 `certifi` 依赖；V2 失败会修改异常旁路。计划没有在这些修复后重新运行 pytest、Ruff 与 Pyright，所以第 8 步不是最终回归。
- V2 只要求「重跑 `.dev/docs/upstream/h2-goaway/` 下的 PoC」，但该目录只有文档和分析脚本。实际 runner 是 `exp/260820-h2-goaway-poc/run_poc.py`，其 `:20-21` 仍 import `httpcore` 和 `httpx`，`:7` 还指定迁移前 `.venv`。清单又明确把 `exp/` 排除在机械迁移外。因此第 9 步没有生产一个可在 HTTPX2 环境中执行的 PoC。

应先建立 HTTPX2 版一次性 PoC fixture，执行 V1/V2 并处理结果，最后再运行全量回归。

## Minor

### m1．确有第四处哑失败接缝，但它在 2.12.0 中尚未实际失效

- 严重度：minor
- 置信度：高
- `src/app/anthropic/client.py:293,461` 与 `src/app/pipeline/executor.py:417` 使用 `getattr(response, "_request", None)`。属性改名会静默丢失 request association，计划完全没有处理。
- 实测 httpx 0.28.1 与 httpx2 2.12.0 都仍保存 `_request`，公共 `response.request` 在未设置时也都抛 `RuntimeError`。因此它不是本次 2.12.0 的即时第四个故障，但它是清单已点名、计划遗漏的第四个无守卫哑失败接缝。
- 计划应明确记录「2.12.0 已核实不变」并加守卫，或者改为显式公共访问与未设置分支。

### m2．`cast_to` 被描述成哑失败与实际 SDK 行为不符

- 严重度：minor
- 置信度：高
- 用现代 `httpx2.AsyncClient` 和 `MockTransport` 实测：

```text
openai cast_to=httpx.Response -> returned httpx2.Response
openai cast_to=httpx2.Response -> returned httpx2.Response
anthropic cast_to=httpx.Response -> builtins.RuntimeError: Unsupported type ...
anthropic cast_to=httpx2.Response -> returned httpx2.Response
```

OpenAI 3.3.1 的 `openai/_httpx2.py:60-62` 特意把已加载的旧 `httpx.Response` 也列为 raw-response marker；Anthropic 才进入解析分支，并且当前结果是响亮的 `RuntimeError`，不是静默返回错误模型。八处仍应迁移，但「三处哑失败」这一事实分类不成立。

### m3．「Pyright 预期会报新错误」没有仓库级证据

- 严重度：minor
- 置信度：中高
- 报告只证明 `Headers.get()` 注解由 `Any` 收紧为 `str | None`，没有运行迁移后 Pyright，也没有点出任何确定报错位置。
- 当前调用点要么提供字符串默认值，要么本来就消费 `str | None`，不能从注解变化直接推出本仓库会新增错误。应改写为「可能暴露新错误，以实际 Pyright 输出为准」，或提供具体诊断。

### m4．两条全称事实错误

- 严重度：minor
- 置信度：高
- 计划称 `build_http_client` 是唯一入口，但清单明确还有 `src/app/upstream/client.py:21-37` 的第二套持久 client builder，以及 `src/app/auth/service.py:38` 的一次性 client。
- 计划称现有依赖「全部无约束」，但 `pyproject.toml:33` 已有 `cryptography>=50.0.0`。

### m5．触发事件的精确运行时间线未由所列三份报告或探针支撑

- 严重度：minor
- 置信度：中
- `1d14605` 的 `--stat` 确实证明它修复了 Starlette 私有 helper，Anthropic 源码和探针也证明旧 client 会在构造阶段报错；但没有所列证据复现「同一条 `uvx --from git+...` 先在 Starlette 失败、修复后恰在 `composition.py:340` 失败」的完整历史运行输出。
- 这条应标成历史观察并附 transcript/log，不能作为「三份一手报告已验证」的派生事实。

---

## 主会话处置

处置人：主会话，2026-08-21。逐条结论如下，采纳与不采纳都记录理由。

### B1：**采纳，D3 已撤回**

自建探针 `.dev/exp/httpx2-migration/probe_cap_designs.py` 驱动**真实的 `AsyncConnectionPool.handle_async_request` 循环**（而非手工调用一次 `_assign_requests_to_connections`）复现，结论比评审的更完整：

- 在 `inner.is_idle()=True`、`max_connections` 有限时，D3 确实产生 `closed_in_use`（burst=100/cap=4/max_conn=4：conns=25、closed_in_use=21）。**B1 成立。**
- 但同一探针在 **httpcore 1.0.9** 上跑，**现状代码（cap 只在 `is_available()`）在同样条件下同样产生 conns=25、closed_in_use=17**。所以「关掉仍承载已分配请求的连接」是今天就存在的性质，不是 D3 引入的新缺陷 —— D3 是把 1.0.9 的行为连同这个缺陷一起搬回 httpcore2。这一点评审没有测到，不影响 B1 的结论，但影响它的归因。
- `inner.is_idle()` 恒为 `True` 是夸张化构造：真实 h2 连接在有流在飞时状态是 ACTIVE，`is_idle()` 为 `False`。在真实的 `idle=False` 一列，D3 与 R2 都干净（conns=8、closed_in_use=0），而**现状代码 peak=68，cap 彻底失效**。

改用 R2（发送时抛 `ConnectionNotAvailable`），它在两列、五种规模下都是 peak=4、连接数理想、closed_in_use=0。详见计划 D3'。

### M1：**采纳**。连接放大的量级我低估了，「多出的连接会在后续趟次被复用」这句已从计划删除。R2 不产生放大（saturated 场景 conns == max_connections，unsaturated 场景 conns == ceil(burst/cap)）。

### M2：**采纳**。§3 已重排为「一个可导入切片」，并显式声明第 2 步包含 `cast_to`，不再假装它是独立步骤。

### M3：**部分采纳**。加 floor 采纳（`httpx2>=2.12`、`opentelemetry-instrumentation-httpx>=0.65b0`）。但 `starlette<1` 那个反例的前提是「给 Starlette 加大版本上界」，而计划并不打算这么做：**starlette 1.6.0 的 `TestClient` 首选 `httpx2`**（`starlette/testclient.py:33` 是 `import httpx2 as httpx`，旧 httpx 只是带 DeprecationWarning 的回退），所以正确动作是让 starlette 一起升到 1.x，而不是钉住它再补 httpx。评审 B 的 blocker 是同一件事的另一面，处置见那份报告。

### M4：**采纳**。V1 已前移并已完成（结果记在计划 §4）。V2 的 runner 路径评审是对的，计划已改指 `exp/260820-h2-goaway-poc/run_poc.py` 并说明它需要一份 httpx2 版 fixture。

### m1：**采纳**，计划新增「`_request` 私有属性在 2.12.0 已核实不变」的记录与守卫要求。

### m2：**采纳**。「三处哑失败」的说法不成立，已改写：`cast_to` 在 anthropic 侧是响亮的 `RuntimeError`，在 openai 侧被兼容层接住。

### m3：**采纳**，改写为「可能暴露新错误，以实际 Pyright 输出为准」。

### m4：**采纳**，两条全称错误已改。

### m5：**采纳**。触发事件改标为历史观察；`composition.py:340` 那次失败有本会话的实际运行输出，starlette 那次来自用户贴的 traceback，二者都不是三份调研报告的派生事实。
