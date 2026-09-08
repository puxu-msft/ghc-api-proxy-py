# history 子系统接线状态审计（260820）

审计范围：只读调查，未修改任何源文件。仓库 `/home/xp/src/ghc-api-proxy-py`，截至 commit 树的当前工作区状态（2026-08-20）。

## 结论摘要（先说结果）

**`app/history/*`、`app/routes/history.py`、`app/routes/protocol_history.py` 整个 history 子系统在当前生产入口（`cli.py` → `create_pipeline_app`）上完全没有接线——不是配置默认关闭，而是这条新链路的 import 闭包里根本不存在 `app.history` 或 `app.routes.*` 任何模块。** 这不是我的推断，仓库自己的结构性测试 `tests/unit/test_module_boundaries.py::test_the_new_chain_does_not_drag_in_the_existing_one` 断言了这一点：

```python
new_chain = reachable_from("app.server.pipeline_app")
assert "app.server.app_factory" not in new_chain
assert "app.pipeline.executor" not in new_chain
assert not [name for name in new_chain if name.startswith("app.routes")]
```

`app.history.consumer.HistoryConsumer`、`app.history.store.HistoryStore`、`app/routes/history.py`、`app/routes/protocol_history.py` 全部只能从 `app.server.app_factory:create_app` 这条**旧链路**到达，而 `create_app` 现在仅被测试套件调用（`tests/http/*`、`tests/integration/test_server_startup.py` 等），生产入口 `cli.py` 的 `start` 命令只调用 `create_pipeline_app(chain)`（`server/composition.py` + `server/pipeline_app.py`），从未导入 `app_factory`。

`~/.local/share/ghc-api-proxy/history.db` 里的 8534 行数据可以印证这一点：`endpoint` 分布里没有一条 `anthropic-messages`（即 `/v1/messages`，本项目的主产品路径），全部是 `openai-*`、`azure-*`、`gemini-*`——这些正是仍挂在旧链路 `protocol_history.py` 上的协议入口在**本地跑测试套件**时写入真实用户数据目录留下的痕迹（测试没有隔离 `history.db` 路径），而不是生产流量。

---

## 1. `HistoryConsumer.started` / `.finalized` 的调用链

有两条互不相通的调用路径，分属两套完全不同的 history 写入机制：

### 路径 A —— `HistoryConsumer`（挂在旧链路 `AnthropicClient` 上）

```
routes/anthropic.py:messages()  (旧链路 /v1/messages，仅 create_app 挂载)
  → client.execute(request, ...)                         [anthropic/client.py:350-364]
    → app.pipeline.executor.execute_anthropic_pipeline()  [pipeline/executor.py:196]
      → client.history.started(context)                  [executor.py:212-213]
      → ...（发送、重试、hooks）...
      非流式成功:   client.history.finalized(context)      [executor.py:467-468]
      失败:         _finalize_failure() → client.history.finalized(context)  [executor.py:122-123]
      上游非 2xx:   client.history.finalized(context)      [executor.py:510-511]
流式成功（非流式路径不会走到这里，返回给路由后）:
routes/anthropic.py:_history_stream()                     [routes/anthropic.py:35-126]
  → client.history.finalized(context, response=..., usage=..., ...)  [anthropic.py:117]
```

`HistoryConsumer.started/.finalized` 定义在 `src/app/history/consumer.py:19` 和 `:26`，本体只是把 `RequestContext` 转成 `HistoryEntry` 后写 `self._store`（`HistoryStore`）并广播 WebSocket 事件——没有问题，方法本身逻辑健全，问题在于谁调用它、以及那个调用点在生产里能不能被触达（见第 2、3 节）。

### 路径 B —— `protocol_history.py`（挂在 `openai.py` / `azure.py` / `gemini.py` / `responses_ws.py` 路由上，绕开 `HistoryConsumer`）

```
routes/openai.py:chat_completions() / responses() / embeddings()
routes/azure.py:azure_chat() / azure_responses() / azure_embeddings()
routes/gemini.py（同构）
routes/responses_ws.py（同构）
  → start_protocol_history(runtime, endpoint=..., model=..., payload=...)   [routes/protocol_history.py:10-31]
      直接操作 runtime.history_store.in_flight，不经过 HistoryConsumer
  → ...
  → finalize_protocol_history(runtime, entry, status=...)                  [protocol_history.py:34-48]
      直接调用 runtime.history_store.finalize(entry)
```

路径 B 从不实例化、也从不引用 `HistoryConsumer`；它直接拿 `RuntimeState.history_store` 手写一份等价逻辑（构造 `HistoryEntry`、`in_flight.add`、`finalize`、广播）。两套机制各自维护一份几乎相同但不共享代码的 `HistoryEntry` 构造与终结逻辑。

**两条路径共同的前提**：无论 A 还是 B，都要求 `RuntimeState`（`app.runtime.RuntimeState`，旧链路专属，不是新链路的 `Chain`）里的 `history_store` 非空——而 `RuntimeState`/`history_store` 只在 `server/app_factory.py` 的 `_lifespan` 里被创建，这个 lifespan 只在 `create_app()`（`app_factory.py:157`）里被注册为 FastAPI 的 `lifespan=`。`create_pipeline_app`（新链路，`pipeline_app.py:386`）用的是自己独立的 `_lifespan`（`pipeline_app.py:414`），完全不构造 `RuntimeState`，也完全不构造 `HistoryStore`。

## 2. 主产品路径（Anthropic Messages 入 → OpenAI Responses 上游）上 history 到底有没有被调用

**在当前生产运行的进程里没有被调用。断点定位如下（按“代码存在”到“不可达”的层层收窄）：**

- **断点最上层——入口选择**：`src/app/cli.py` 的 `start` 命令（第 198-324 行）只 `import` 并调用 `create_pipeline_app`（`from app.server.pipeline_app import create_pipeline_app`，`cli.py:23`），全文件没有任何地方 `import app.server.app_factory` 或 `app.routes.anthropic`。生产二进制启动时压根不会加载含 `HistoryConsumer` 接线代码的模块。
- **新链路自身的路由表**：`create_pipeline_app` 挂载的路由来自 `server/inbound.py` 的 `ROUTES`（`build_router()`，`pipeline_app.py:370-383`）加 `ops_router`（health/models/metrics，`pipeline_app.py:392`）。这份路由表、`server/handler.py`、`server/composition.py`、`pipeline/subscribers.py`、`pipeline/request.py` 全文 grep `history` **零命中**——不是没调用，是这些文件里根本没有这个词。
- **即便假设某天新链路想复用旧的 `HistoryConsumer`**：它也拿不到，因为 `HistoryConsumer` 依赖的 `HistoryStore` 挂在旧的 `app.runtime.RuntimeState.history_store` 上，而新链路的等价对象是 `server/composition.py` 里的 `Chain`（第 84-101 行），`Chain` 数据类没有 `history_store` 字段，构造函数 `build_chain()`（`composition.py:180-230`）也不创建它。
- **`config/schema.py` 里确实有一个 `HistoryConfig`**（`schema.py:198-199`，只有 `enabled: bool = True` 一个字段），挂在 `ProxyConfig.history`（`schema.py:309`），`cli.py` 的 `--history/--no-history` 选项（`cli.py:214`）也确实把它写进 `cli_overrides["history"] = {"enabled": history}`（`cli.py:254-255`）。但这个字段从构造到消费全程只有"构造"没有"消费"：`composition.py`、`pipeline_app.py`、`inbound.py`、`handler.py` 没有一处读取 `config.history` 或 `chain.config.history`。**这是一个连到了 schema、却连不到任何代码的配置开关**——生产环境无论 `--history` 传 true 还是 false，行为完全一样（都是"没有 history"）。这与依赖未注入是同一类断点的两种呈现：史料层面它"看起来"是个功能开关，运行时它是死代码。

**因此答案是**：新链路（当前生产实际运行的那条链路）里，"路由没接" + "依赖没注入" + "config 字段没有消费者"三层同时成立，其中最本质的一层是**架构层面的隔离本身**——`test_module_boundaries.py` 把"新链路不得引入 `app.pipeline.executor` / 任何 `app.routes.*`"写成了断言并在 CI 里强制执行，这不是遗漏，是这次链路重排明确要求的结构，只是 history 子系统还没有被移植到新链路上。

## 3. legacy / 新链路分裂的具体形态

| | 新链路（生产实际运行） | 旧链路（legacy，仅测试调用） |
|---|---|---|
| 入口函数 | `app.server.pipeline_app.create_pipeline_app(chain)`，由 `cli.py:_serve_pipeline` / `cli.py:serve_inherited` 调用 | `app.server.app_factory.create_app(settings)`，仅被 `tests/http/*.py`、`tests/integration/test_server_startup.py` 等测试文件调用 |
| 组合根 | `app.server.composition.Chain` / `build_chain()` | `app.runtime.RuntimeState`，在 `app_factory._lifespan` 里逐字段赋值 |
| 请求路由 | `app.server.inbound.ROUTES` + `_serve`/`_dispatch`（`pipeline_app.py`） | FastAPI `APIRouter`：`routes/anthropic.py`、`routes/openai.py`、`routes/azure.py`、`routes/gemini.py`、`routes/history.py`、`routes/protocol_history.py` 等 |
| 请求上下文类型 | `app.pipeline.request.RequestContext` | `app.pipeline.context.RequestContext`（同名不同类，字段也不同——`executor.py` 用的是后者） |
| 是否接 history | **否**：`Chain` 无 `history_store` 字段，新链路文件 grep `history` 零命中 | **是**：`/v1/messages` 走 `HistoryConsumer`；`openai.py`/`azure.py`/`gemini.py`/`responses_ws.py` 走 `protocol_history.py`，两者共享同一个 `RuntimeState.history_store` 但代码路径不同（本报告第 1 节路径 A / B） |
| 结构性保证 | `tests/unit/test_module_boundaries.py::test_the_new_chain_does_not_drag_in_the_existing_one` 断言新链路 import 闭包里没有 `app_factory`、没有 `pipeline.executor`、没有任何 `app.routes.*` | 无对应保证；是被断言"不可再侵入新链路"的一方 |

这与项目记忆 `guards-stranded-on-the-legacy-chain.md` 里记录的现象同源：该记忆记录的是**清洗/守卫**（`server_tool_not_supported`、`filter_empty_text_blocks`）只被 `anthropic/client.py`/`pipeline/executor.py` 调用、新链路访问不到；本次审计确认 **history 落在了同一个"legacy 专属"的桶里**，性质相同——不是"写错了"，是新链路尚未把这块能力迁移过去，而旧链路仍然完整可用、只是不再被生产入口执行。

## 4. `HistoryStore` 的构造、启动、配置项

**构造与启动位置**：`src/app/server/app_factory.py` 的 `_lifespan()`，第 73-83 行：

```python
if settings.history.enabled:
    history_path = (
        Path(settings.history.db_path)
        if settings.history.db_path
        else user_data_path() / "history.db"
    )
    runtime.history_store = HistoryStore(history_path)
    runtime.websocket_manager = runtime.history_store.websockets
    await runtime.history_store.start()
```

随后（第 98-101 行）只有在 `runtime.anthropic_client is not None`（由 `initialize_upstream_services()` 设置，`upstream/bootstrap.py:145`/`236`）时才把 `HistoryConsumer` 挂到 `AnthropicClient.history` 上：

```python
if runtime.history_store is not None and runtime.anthropic_client is not None:
    runtime.anthropic_client.history = HistoryConsumer(runtime.history_store)
```

reaper 后台任务在第 129-138 行按 `settings.history.reaper_interval > 0` 条件性启动。关闭时（第 147-149 行）`await runtime.history_store.close()` 并置空。

**受控配置**（`src/app/config/settings.py:49-55`，`AppSettings.history`，`HistoryConfig`，这是旧链路专用的配置类，与新链路 `config/schema.py` 里同名但字段单薄的 `HistoryConfig` 是两个不同的类）：

```python
class HistoryConfig(FrozenModel):
    enabled: bool = True
    success_limit: int = 50
    failure_limit: int = 200
    reaper_interval: int = 600
    db_path: str = ""
    websocket: bool = True
```

**生产默认值**：`enabled=True`，`db_path=""`（回退到 `user_data_path() / "history.db"`，即 `~/.local/share/ghc-api-proxy/history.db`），`success_limit=50`、`failure_limit=200`（reaper 保留条数上限），`reaper_interval=600` 秒。**如果 `create_app()` 真的被生产进程启动，默认就是"开"**；但如第 2 节所述，生产进程根本不启动 `create_app()`，所以这些默认值目前对生产行为没有任何影响——它们只对跑 `tests/http/*` 的测试进程生效。

`HistoryStore` 本身（`src/app/history/store.py:11`）提供 `start()`、`finalize()`、`flush()`、`run_reaper()`、`list_entries()`、`get()`、`set_pinned()`、`close()`，构造函数签名在第 12 行（未展开读取全部细节，属于旧链路自身实现，未见异常）。

## 5. `~/.local/share/ghc-api-proxy/history.db` 实测（只读查询，未写入）

```
$ ls -la ~/.local/share/ghc-api-proxy/history.db
-rw-r--r-- 1 xp xp 2486272 Aug 20 09:00 history.db
```

用 `sqlite3` URI 只读模式（`file:...?mode=ro`）查询，表名为 `entries`（不是 `history`）：

- **总行数**：8534
- **`endpoint` 分布**：

  | endpoint | 行数 |
  |---|---|
  | openai-chat-completions | 2655 |
  | openai-responses-websocket | 2132 |
  | azure-responses | 537 |
  | azure-embeddings | 537 |
  | azure-chat-completions | 537 |
  | gemini-streamGenerateContent | 536 |
  | gemini-generateContent | 536 |
  | openai-responses | 532 |
  | openai-embeddings | 532 |

  **没有任何一行 `endpoint` 是 `anthropic-messages`/`/v1/messages`**——即本项目声明的主产品路径从未在这个库里留下过一条记录。全部 endpoint 都来自旧链路里挂 `protocol_history.py` 的那几个协议入口（`openai.py`/`azure.py`/`gemini.py`/`responses_ws.py`），且行数分布规整（537/536/532 这类接近但不完全相等的整数），与本地反复跑 `tests/http/test_openai_routes.py`、`test_azure_routes.py`、`test_gemini_routes.py`、`test_responses_ws.py` 的行为特征吻合，而不像生产真实流量。
- **`status` 分布**：`completed` 6939，`aborted` 1064，`failed` 531。
- **`started_at` 范围**：原始 epoch 最小 `1784193889.34`，最大 `1787216418.55`；换算为可读时间为 **2026-07-16 09:24:49 到 2026-08-20 09:00:18**（本地时区）。跨度约 35 天，与"测试套件在本地反复运行"的假设一致。
- **`request_payload` 平均字节数**：约 **46.66 字节**（min 32，max 64）。这个尺寸完全不像真实的 Anthropic/OpenAI 请求体（真实请求通常几百到几万字节），高度符合测试用 fixture 里的极简 payload（例如仅 `{"model": "x", ...}` 这类占位对象）。

结论：这个 `history.db` 是**测试进程在本机真实用户数据目录留下的痕迹**，不是生产观测数据；同时它也从侧面独立证实了第 2 节的结论——如果 `/v1/messages` 真的在生产中走过 `HistoryConsumer`，这个库里就应该出现 `anthropic-messages`/`messages` 相关 endpoint，而实测中一条都没有。

（附带发现，非本次任务目标但值得记录：`tests/http/test_openai_routes.py` 等测试用 `create_app()` 默认设置时会把数据写入真实的 `~/.local/share/ghc-api-proxy/history.db`，而不是临时目录，属于测试隔离缺口——不在本审计的整改范围内，仅如实记录供后续参考。）

## 6. `routes/history.py` 与 `routes/protocol_history.py` 暴露的端点

### `src/app/routes/history.py`（REST + WebSocket，供前端/管理界面查询 `HistoryStore`）

| 方法+路径 | 返回 |
|---|---|
| `GET /history/api/entries` | `{"data": [...]}`，支持 `limit`/`model`/`endpoint`/`status`/`session_id` 过滤，来自 `store.list_entries()` |
| `GET /history/api/entries/{entry_id}` | 单条 `HistoryEntry`（`asdict`），404 若不存在 |
| `GET /history/api/entries/{entry_id}/export` | 同上，附 `Content-Disposition: attachment` |
| `POST /history/api/entries/{entry_id}/pin` / `unpin` | `{"pinned": true/false}` |
| `GET /history/api/sessions` | 按 `session_id` 聚合的请求计数 |
| `GET /history/api/stats` | `{"total", "completed", "failed"}` 汇总 |
| `GET /history/api/export` | 全量导出（`limit=10000`） |
| `WS /history/ws` | 订阅式实时事件（`entry_added`/`entry_updated`），由 `HistoryConsumer`/`protocol_history.py` 广播驱动 |

这些端点全部依赖 `HistoryStoreDependency`（`app/deps.py:73-77`，从 `RuntimeState.history_store` 取），本身实现没有问题。

### `src/app/routes/protocol_history.py`（不是路由文件，是被 `openai.py`/`azure.py`/`gemini.py`/`responses_ws.py` 直接调用的内部函数集合，不注册任何 HTTP 路径）

- `start_protocol_history()`：构造 `HistoryEntry`，`status="pending"`，塞进 `runtime.history_store.in_flight`，返回该 entry（若 `history_store is None` 直接返回 `None`，调用方随后把 `None` 一路传递，其余环节都做了 `entry is None` 判空，不会崩溃，只是静默不记录）。
- `finalize_protocol_history()`：写终态、`store.finalize()`、`in_flight.remove()`、WebSocket 广播。
- `history_stream()`：包一层流式转发生成器，`finally` 里调用 `finalize_protocol_history`。

**是否挂在实际运行的 app 上**：`routes/history.py` 的 `history_router` 由 `app_factory.create_app()`（第 173 行 `app.include_router(history_router)`）挂载；`protocol_history.py` 的三个函数由 `routes/openai.py`/`azure.py`/`gemini.py`/`responses_ws.py` 调用，这四个路由文件又都是被 `app_factory.create_app()`（第 24-35 行的 import、168-178 行的 `include_router`）挂载的。**`create_pipeline_app()`（新链路，生产实际调用的那个）完全不 import、不挂载这些文件中的任何一个**——`test_module_boundaries.py` 的断言字面上就是 `not [name for name in new_chain if name.startswith("app.routes")]`。所以：这些端点在**测试进程**里是真实可访问、行为正确的；在**生产进程**里，路径 `/history/api/*`、`/history/ws` 根本不存在（`create_pipeline_app` 的路由表来自 `server/inbound.py:ROUTES` + `ops_router`，两者都不包含它们），请求这些路径会得到 `pipeline_app.py:_dispatch` 里"unknown endpoint" 的 404，或者更早被 FastAPI 自身的 404 拦截（取决于路径是否命中 `route_for_path`）。

## 涉及文件一览（均为已读、未修改）

- `src/app/history/consumer.py`
- `src/app/history/store.py`
- `src/app/pipeline/executor.py`
- `src/app/routes/anthropic.py`
- `src/app/routes/openai.py`
- `src/app/routes/azure.py`
- `src/app/routes/history.py`
- `src/app/routes/protocol_history.py`
- `src/app/deps.py`
- `src/app/runtime.py`
- `src/app/server/app_factory.py`
- `src/app/server/pipeline_app.py`
- `src/app/server/composition.py`
- `src/app/cli.py`
- `src/app/config/settings.py`（`HistoryConfig`，第 49-55 行）
- `src/app/config/schema.py`（`HistoryConfig`，第 198-199 行；`ProxyConfig.history`，第 309 行）
- `src/app/anthropic/client.py`（`execute`/`send_prepared_attempt`，第 189-364 行）
- `tests/unit/test_module_boundaries.py`
- `~/.local/share/ghc-api-proxy/history.db`（只读查询，未写入）
