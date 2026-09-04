# Responses WebSocket 现状核查

核查对象：`docs/.human-controlled/ghc-api.md` 中 `ws:/responses` 一行的裁决——

> | `ws:/responses` | 暂不支持 | 支持 `POST /responses` 的 OpenAI 模型具备该端点 |
>
> 2026-08-16：Responses WebSocket 已在项目内存在，现有代码、测试均保留，**不最终接线**，如果存在陈旧可适当注释掉。

结论先给：**现状与裁决一致**。代码与测试确实保留着，且确实没有接到实际对外服务的那条链路上。以下逐条列证据。全过程只读，未修改任何文件。

## 1. 完整清单（按行数）

下游（我们对客户端暴露的 WS 端点）：

- `src/app/routes/responses_ws.py` — 101 行。`@router.websocket("/responses")`，收 `response.create` 帧，跑审批门（`apply_approval_guard`）、写 protocol history，再转发给上游 ws 客户端。

上游（我们作为 ws 客户端连 GHC/OpenAI 上游）：

- `src/app/openai/responses_ws.py` — 50 行。`ResponsesWebSocketClient`，包一层 `httpx2.AsyncClient.websocket(...)`（不是 `httpx_ws` 独立包，见第 5 节）。

接线基础设施（legacy 链路专用，见第 2 节）：

- `src/app/runtime.py` — `RuntimeState.responses_ws_client: ResponsesWebSocketClient | None` 字段。
- `src/app/deps.py:66-69` — `get_responses_ws_client` / `ResponsesWSClientDependency`。
- `src/app/upstream/bootstrap.py:249-254` — 构造 `ResponsesWebSocketClient(client, f"{ws_base_url}/responses", queue_size=settings.openai_responses.ws_queue_size)`；`bootstrap.py:158` 在 `upstream.type == "generic"` 分支里显式置 `None`（即只有 Copilot 供应商分支才会造这个客户端）。
- `src/app/server/app_factory.py:35,177` — `app.include_router(responses_ws_router, prefix=prefix)`，三个前缀（`""`、`/v1`、`/openai/v1`）都挂。

测试：

- `tests/int/test_responses_ws.py` — 156 行，6 个用例，走 `app.server.app_factory.create_app`。
- `tests/unit/openai/test_responses_ws_transport.py` — 97 行，2 个用例，直接测 `ResponsesWebSocketClient`。
- `tests/unit/pipeline/test_route_policy.py:125` — `test_websocket_advertisement_proves_responses_without_forcing_websocket`，测的是「目录里出现 `ws:/responses` 这个字符串可以证明模型具备 Responses 能力，但不强制真的用 websocket 传输」这条设计意图（见第 4 节）。

模型能力/路由词汇表（不是 responses_ws 专属文件，但携带这个端点标识）：

- `src/app/model_provider/types.py:18` — `ModelEndpoint.OPENAI_RESPONSES_WS = "ws:/responses"`。
- `src/app/pipeline/route_policy.py:44,49,75` — `TransportAvailability.responses_websocket` 字段、`_RESPONSES_ENDPOINTS = frozenset({"/responses", "ws:/responses"})`。

配置项（`ResponsesConfig`，`src/app/config/settings.py:127-133`）：

- `upstream_ws: bool = False` —— 全代码库 `rg` 只在这一行出现，**没有任何地方读取它**（不是 bootstrap.py 构造 ws 客户端的门槛，也不是路由决策的门槛）。
- `ws_queue_size: int = 32` —— 唯一被读取的一个，供 `bootstrap.py:253` 传给 `ResponsesWebSocketClient` 的构造参数。
- `max_ws_frame_bytes` / `max_client_ws_connections` / `max_upstream_ws_connections` —— 同样全代码库只出现在声明处，未被任何地方读取。

历史/实验/验收脚本（不在 `tests/` 之下，不受 pytest 默认扫描约束）：

- `verification/phase3_acceptance.py` — 582 行，2026-07-16 提交，`verify_httpx_ws_transport` 检查点。
- `verification/final_acceptance/probes/04_responses_websocket.py` — 119 行，同批次验收脚本。
- `exp/httpx-ws/poc.py` — 40 行，2026-07-15 提交，早期 PoC。

## 2. 接线核查（最关键）

**运行中的服务不可达这个端点。** 证据链：

1. `src/app/cli.py:23` 只 `from app.server.pipeline_app import create_pipeline_app`，全文件没有任何地方 import 或调用 `app.server.app_factory.create_app`。`main()` 经 `app.lifecycle.entry.run_standalone` 最终在 `cli.py:151` 与 `cli.py:176` 用 `create_pipeline_app(chain)` 起服务——这是唯一真正对外监听的入口。
2. `src/app/server/pipeline_app.py:699-713`（`create_pipeline_app`）只挂了 `build_router()`（`ROUTES` 来自 `app.server.inbound`，全部是 `POST` 路由，见 `pipeline_app.py:683-696`）和 `ops_router`。**通篇没有 `@router.websocket`，没有 import `responses_ws_router`，没有任何 WebSocket 路由。**
3. `responses_ws_router` 只在 `src/app/server/app_factory.py:35,177` 被挂载；而 `create_app`（`app_factory.py:157`）除了这里，全项目仅被 `tests/int/*.py`（十余个集成测试文件）与旧脚本 `verification/phase3_acceptance.py:217-226` 引用——**没有任何生产入口调用它**。
4. 即使在 `app_factory` 这条 legacy 链路内部，`RuntimeState.responses_ws_client` 也只由 `app.upstream.bootstrap.initialize_upstream_services` 填充，而这个函数只被 `app_factory.py:98-99` 的 `_lifespan` 调用——同样是 legacy-only，`pipeline_app.py`/`cli.py` 完全不触碰 `bootstrap.py`。
5. 没有配置开关能让运行中的 pipeline 服务多长出这条路由：挂不挂 `responses_ws_router` 是「调用哪个 app 构造函数」这个结构性选择，不是由某个 config 布尔值决定的（`ResponsesConfig.upstream_ws` 声明了但从未被读取，见第 1 节）。

**结论**：`responses_ws` 属于「已实现但未接线」——现有代码、测试均保留，且确实没有接进当前实际对外提供服务的那条 `pipeline_app` 链路，与用户 2026-08-16 的裁决完全一致。可达性验证方法：跑 `uv run python -m app.cli start ...`（即 `create_pipeline_app` 路径）后请求 `ws://.../responses` 会被 FastAPI 自身的路由表拒绝（未注册路径），而不是走到 `responses_websocket()` 处理函数。

## 3. 方向澄清

用户文档表格里的 `ws:/responses` 指的是**上游**（GHC/OpenAI 侧）具备的能力端点标识。项目里实际存在两侧代码，需要分开看：

- **上游侧存在**：`src/app/openai/responses_ws.py` 的 `ResponsesWebSocketClient` 就是"我们连上游 ws"的客户端，`bootstrap.py:250-254` 把它指向 `wss://<base>/responses`。`src/app/model_provider/types.py:18` 的 `ModelEndpoint.OPENAI_RESPONSES_WS` 是目录解析时用来识别上游是否声明了这个端点的枚举值——它**能被目录解析成功识别**（`ModelEndpoint(entry)` 会正常构造，不会因未知字符串报错），但 `src/app/model_provider/github_copilot.py:33-36` 的分发表（`ANTHROPIC_MESSAGES`/`OPENAI_CHAT_COMPLETIONS`/`OPENAI_RESPONSES`/`OPENAI_EMBEDDINGS`）里**没有 `OPENAI_RESPONSES_WS` 对应的分发方法**；`github_copilot.py:153-154` 对不在分发表里的端点会 `raise EndpointNotImplemented`——即便真被路由选中也是显式失败，不是静默假成功。
- **下游侧也存在**：`src/app/routes/responses_ws.py` 是我们**对客户端**暴露的 WebSocket 端点（`@router.websocket("/responses")`），这是用户文档没有直接提及的另一侧——项目在实现时把"上游有没有这个能力"和"我们要不要把等价能力透出给下游客户端"两侧都写了，但只有下游这一层在 legacy `app_factory` 链路里被路由表接住，且如第 2 节所证，这条链路本身不对外提供服务。

再看路由决策层如何处理这个方向问题：`src/app/pipeline/route_policy.py:44,49` 的 `TransportAvailability.responses_websocket` 字段刻意与 `responses_http` 分开，`supports()` 用 `responses_http or responses_websocket` 判断"Responses 协议腿是否可用"；但生产环境唯一的调用点 `src/app/anthropic/client.py:227-230` 构造 `TransportAvailability(messages_http=True, responses_http=True)`，**从未传 `responses_websocket=True`**。也就是说：即使某天上游目录真的对某个模型只声明 `ws:/responses`（不声明 HTTP `/responses`），`_validated_endpoints` 会把它算进 `supports_responses`（因为 `_RESPONSES_ENDPOINTS` 两个字符串都收），但 `_require_transport` 会因为 `responses_websocket` 恒为 `False` 而拒绝、抛 `TRANSPORT_UNAVAILABLE`——这条门槛设计得干净利落，不是遗留的漏洞。`test_websocket_advertisement_proves_responses_without_forcing_websocket`（`tests/unit/pipeline/test_route_policy.py:125`）测的正是这一条不变量，当前通过。

## 4. 测试现状

在默认扫描范围内（`pyproject.toml:62` `testpaths = ["tests"]`；`addopts` 只 `--ignore=tests/tui --ignore=tests/e2e`，两个 responses_ws 测试文件都不在被排除之列）：

```
uv run pytest tests/int/test_responses_ws.py tests/unit/openai/test_responses_ws_transport.py -q
........                                                                 [100%]
8 passed in 2.98s

uv run pytest tests/unit/pipeline/test_route_policy.py -q -k websocket
.                                                                        [100%]
1 passed, 13 deselected in 0.03s
```

九个测试全部通过，且都在默认扫描范围内、会被 `uv run pytest tests --cov=app ...`（本项目验证命令）自动跑到。**未跑全量套件**，按任务要求只跑了相关路径。

`verification/` 目录下的两个脚本不在 `testpaths` 之下，pytest 默认扫描不会碰它们，也没有 CI/脚本引用它们（`rg` 未发现 `verification/` 被任何构建脚本、CI 配置或活跃文档引用，只有它自己目录下的 `MANIFEST.md`/`SUMMARY.md` 互相指涉）。

## 5. 陈旧候选清单（供用户裁决，未动手）

以下按"确实陈旧"的判据——引用了已被重构掉的接口、依赖已不存在的包、或建立在当前架构不成立的假设上——列出，**均未修改**：

1. **`verification/phase3_acceptance.py` 的 `verify_httpx_ws_transport`（约 343-390 行）**：`import httpx_ws` 检查已安装的包。实测 `uv run python -c "import httpx_ws"` 报 `ModuleNotFoundError`——项目已在 2026-08-21（`git log` 见 `feat: move off httpx onto httpx2`）迁移到 `httpx2[ws]`（`pyproject.toml:20`），不再依赖独立的 `httpx_ws` 包。这一验证点现在跑起来就是直接失败/跳过，检查的是一个已经不存在的依赖。整份文件提交于 2026-07-16，早于 2026-08-16 的裁决和 2026-08-21 的迁移。

2. **`verification/final_acceptance/probes/04_responses_websocket.py`**：起服务用的是 `python -m app start`——对应生产入口 `create_pipeline_app`（第 2 节已证）——然后去连 `ws://127.0.0.1:<port>/v1/responses`。按当前架构这个路径在生产入口下根本没有注册，这个探针如果真的跑一遍，预期结果是连接失败/找不到路径，而不是脚本假设的"WebSocket 连接建立、上游拒绝或超时"。这份脚本建立在"生产服务会挂这条路由"的假设上，这个假设在当前架构里不成立。

3. **`exp/httpx-ws/poc.py`**：同样 `from httpx_ws import aconnect_ws` / `from httpx_ws.transport import ASGIWebSocketTransport`，包不存在，跑不起来。2026-07-15 的探索性 PoC，早于 httpx2 迁移。

4. **`ResponsesConfig` 里的四个孤儿字段**（`src/app/config/settings.py:129,131-133`）：`upstream_ws`、`max_ws_frame_bytes`、`max_client_ws_connections`、`max_upstream_ws_connections`——声明了默认值，但全代码库没有任何地方读取。`upstream_ws` 尤其容易被误读成"这就是控制要不要接线的开关"，但 `bootstrap.py` 构造 `ResponsesWebSocketClient` 时根本没检查它。这四个字段本身不依赖任何已被重构掉的接口，谈不上"跑不起来"，但作为摆设配置项，是否要保留、要不要在某处接上门槛判断，值得用户判断。

**不在候选之列、故意保留说明的部分**：`src/app/routes/responses_ws.py`、`src/app/openai/responses_ws.py`、两个 `tests/` 下的测试文件、`route_policy.py` 的 `responses_websocket` 字段与 `_RESPONSES_ENDPOINTS`、`model_provider/types.py` 的 `OPENAI_RESPONSES_WS` 枚举——这些全部语法正确、依赖现存、测试全绿，是"实现了但不接线"的正常状态，不是陈旧。尤其 `route_policy.py` 那条"广播能力但不强制传输"的设计（第 3 节），读起来是深思熟虑的产物，不建议动。
