# ghc-api-proxy-py 实施计划

> **基准文档**：[TODO_CURRENT.md](../../../TODO_CURRENT.md)、[SELECTIONS.md](../lib-survey/SELECTIONS.md)、[HANDOVER.md](../lib-survey/HANDOVER.md)、[project-structure.md](../project-structure.md) 以及完整设计文档树。
>
> **执行原则**：TDD 驱动、分阶段交付、每阶段可独立验收、优先打通端到端骨架再横向铺开、纵向加固。
>
> **状态**：2026-07-15 定稿；Phase 0 已实施并通过独立验收，下一阶段为 Phase 1。

## 全局约束与门禁

### 依赖版本锁定

所有第三方库必须在实施开始时重新解析**当日最新稳定兼容版**，完成 Python 3.14 smoke/PoC 后锁定到 `pyproject.toml`/lockfile，避免中途版本漂移。下列包名是选型结果，不把调研日版本号当成永久锁：

```toml
[project]
requires-python = ">=3.14"
dependencies = [
    "fastapi",
    "uvicorn",
    "httpx",
    "anthropic",
    "openai",
    "pydantic",
    "pydantic-settings",
    "anyio",
    "structlog",
    "orjson",
    "tiktoken",
    "platformdirs",
    "aiofiles",
    "typer",
    "httpx-ws",
    "textual",

    # 用户已接受 beta 自动 instrumentation；包必须安装，运行时默认关闭。
    # core/contrib 必须作为同一兼容批次解析与锁定。
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-instrumentation-fastapi",
    "opentelemetry-instrumentation-httpx",
    "opentelemetry-exporter-prometheus",

    # sse-starlette 通过保真 PoC 后加入；失败则使用 Starlette StreamingResponse。
    # "sse-starlette",
]
```

### Python 3.14 验证

Phase 0 第一步：创建 `.python-version` 文件,`uv sync`,运行最小探针确认核心依赖可导入:

```python
# tests/smoke/test_imports.py
def test_core_imports():
    import fastapi, uvicorn, httpx, anthropic, openai
    import pydantic, pydantic_settings, anyio, structlog
    import orjson, tiktoken, platformdirs, aiofiles, typer, textual
    import opentelemetry.instrumentation.fastapi
    import opentelemetry.instrumentation.httpx
```

### 硬约束检查清单

每个阶段实施完成前必须自查:

- [ ] **P1 off-event-loop**: 所有磁盘/SQLite I/O 走 `asyncio.to_thread` 或专用 executor
- [ ] **P6 零缓冲**: SSE/WS 逐事件/逐消息直通,不强制整体缓冲
- [ ] **保真度**: 未知字段经 Pydantic `extra="allow"` 保留,SDK 与 translator 不丢弃
- [ ] **单一 retry owner**: SDK `max_retries=0`,transport retries 关闭
- [ ] **已知字段 differential tests**: 新引入的 codec/serializer 必须有对照测试
- [ ] **结构化取消**: AnyIO task group/cancel scope 中不遗留裸 `asyncio.create_task()`；混用路径必须测试取消并 await 清理
- [ ] **OTel 默认关闭**: beta instrumentation 已安装，但无显式配置时不得激活

---

## Phase 0 — 项目骨架与基础设施

> **目标**: 能启动空壳服务、有配置、有日志、有健康检查。为后续一切提供地基。
>
> **实施状态（2026-07-15）**：✅ 完成。65 个测试通过，覆盖率 92.87%，Ruff/Pyright strict 通过；真实进程级启动与关闭验收通过；独立代码评审最终 0 blocker / 0 major。

### 前置依赖

无(项目起点)。

### 实施步骤与测试策略

#### Step 0.1: Python 环境与依赖验证

**交付物**:
- `.python-version` (内容: `3.14.2`)
- `pyproject.toml` 补齐上述依赖清单
- `tests/smoke/test_imports.py`

**验收**:
```bash
uv sync
uv run pytest tests/smoke/test_imports.py -v
```

#### Step 0.2: CLI 骨架 (Typer)

**先写测试**:
```python
# tests/unit/test_cli.py
def test_cli_smoke():
    from app.cli import app as typer_app
    from typer.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(typer_app, ["--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout
```

**实现文件**:
- `src/app/cli.py`: Typer app 定义，子命令 `start` / `auth`（别名 `login`）/ `logout` / `debug` / `setup-claude-code` / `setup-codex` / `list-claude-code`
- `src/app/__main__.py`: 入口点 `if __name__ == "__main__": app()`

**技术要点**:
- 从起点采用 Typer,不走 argparse 中间态
- `start` 子命令选项按 [project-structure.md CLI 表格](../project-structure.md#cli-参数) 完整定义
- `--config` / `--port` / `--host` / `--verbose` / `--manual` / `--generate-config` 等

**Commit**: `feat(cli): bootstrap Typer CLI with start/auth/debug subcommands`

#### Step 0.3: 配置系统 (Pydantic Settings)

**先写测试**:
```python
# tests/unit/test_config_loader.py
def test_four_layer_merge():
    # defaults < yaml < env < cli
    ...
def test_per_key_merge_model_mappings():
    # model_mappings 按键合并,不是整体替换
    ...
def test_custom_merge_source():
    # 自定义 source 实现 per-key vs replace 策略
    ...
```

**实现文件**:
- `src/app/config/settings.py`: frozen Pydantic `AppSettings` 模型
- `src/app/config/loader.py`: `settings_customise_sources` + 自定义 merge source
- `src/app/config/compat.py`: 弃用键迁移(`limit` → `success_limit` 等)
- `src/app/config/paths.py`: 使用 `platformdirs` 替代手写 XDG

**技术要点**:
- 采用 `pydantic-settings` 内置 YAML/CLI source,但保留自定义 merge source 实现 per-key 策略
- `model_mappings` / `timeouts.stream_idle_overrides` per-key 合并,其余 dict 整体替换
- frozen 模型,四层优先级: defaults < yaml < env < cli

**PoC 门禁**: 单元测试必须覆盖 per-key merge 与 replace merge 两种场景

**Commit**: `feat(config): implement four-layer config merge with pydantic-settings`

#### Step 0.4: 结构化日志 (structlog)

**先写测试**:
```python
# tests/unit/test_logging.py
def test_structlog_contextvars():
    from app.observability.logging import setup_logging, get_logger
    setup_logging(log_format="json")
    logger = get_logger()
    with structlog.contextvars.bound_contextvars(request_id="test-123"):
        logger.info("test_event")
        # 验证输出包含 request_id
```

**实现文件**:
- `src/app/observability/logging.py`: structlog 配置,JSON/text 双 renderer,自定义固定宽度前缀 processor

**技术要点**:
- `structlog.contextvars` 驱动 request_id 传播
- 自定义 processor 拼接 `[ OK ]` / `[FAIL]` / `[RETRY]` 前缀
- 与 uvicorn stdlib logging 整合(`ProcessorFormatter`)

**Commit**: `feat(observability): integrate structlog with contextvars-based request_id`

#### Step 0.5: 数据模型基础

**先写测试**:
```python
# tests/unit/test_models_common.py
def test_usage_model_unknown_fields():
    data = {"input_tokens": 100, "unknown_field": "keep_me"}
    usage = Usage.model_validate(data)
    assert usage.model_extra["unknown_field"] == "keep_me"
```

**实现文件**:
- `src/app/models/common.py`: `Usage` / `ModelInfo` / `ErrorResponse`,`extra="allow"`
- `src/app/models/capabilities.py`: 能力元数据表(暂为空骨架)
- `src/app/errors.py`: 错误分类 `ApiError` / `classify_error`

**技术要点**:
- 所有入站模型 `model_config = ConfigDict(extra="allow")`
- 不丢弃未知字段

**Commit**: `feat(models): define common data models with unknown-field preservation`

#### Step 0.6: 应用工厂与 lifespan

**先写测试**:
```python
# tests/integration/test_server_startup.py
@pytest.mark.asyncio
async def test_server_lifespan():
    from app.server import create_app
    app = create_app(settings)
    async with LifespanManager(app):
        pass  # 验证 startup/shutdown 不抛错
```

**实现文件**:
- `src/app/server.py`: `create_app(settings)`，分阶段 lifespan + 应用级 AnyIO task group（空服务占位）
- `src/app/deps.py`: FastAPI DI 提供者骨架

**技术要点**:
- lifespan context manager 分阶段: config load → auth init → upstream init → ...
- 后台服务统一由 lifespan 内的 AnyIO task group 持有，禁止散落 fire-and-forget task
- 每阶段空实现，后续填充

**Commit**: `feat(server): create FastAPI app factory with staged lifespan`

#### Step 0.7: 健康检查端点

**先写测试**:
```python
# tests/http/test_health_routes.py
def test_health_liveness(client):
    resp = client.get("/health/liveness")
    assert resp.status_code == 200
```

**实现文件**:
- `src/app/routes/health.py`: `/health` / `/health/liveness` / `/health/readiness`

**Commit**: `feat(routes): add health check endpoints`

#### Step 0.8: Wire JSON codec

**先写测试**:
- `tests/unit/test_wire_json_codec.py`: 标准库 differential round-trip、未知嵌套字段、非 ASCII、bytes 返回、Pydantic `model_dump(mode="json")` 边界
- 显式覆盖 NaN/Infinity、超大整数、datetime 等 `orjson` 与标准库可能不同的行为，并把项目接受的 wire policy 固化为断言

**实现文件**:
- `src/app/wire_json.py`: 集中封装 `dumps(obj) -> bytes` / `loads(data)`，业务模块不得散落直接 import `orjson`

**技术要点**:
- 只建立 codec 边界，本阶段不把低频配置、错误快照、迁移文件机械改成 `orjson`
- Phase 2 起 HTTP/SSE 热路径必须通过此 codec 编码单帧，不能聚合完整流

**Commit**: `feat(codec): add orjson wire codec with differential tests`

### 阶段验收

**端到端验收命令**:
```bash
# 1. 生成默认配置
uv run python -m app start --generate-config

# 2. 启动服务并保持运行
uv run python -m app start --port 4141 &
sleep 2

# 3. 健康检查
curl http://localhost:4141/health/liveness
# 预期: {"status":"ok"}

# 4. 停止
kill %1
```

**用户可观察**:
- 服务可启动不报错
- 配置文件可生成
- 日志输出格式正确(JSON 或 text)
- 健康检查端点返回 200

### 里程碑

✅ 服务可启动、可配置、可观测。

### 风险与回滚

**风险**: Typer 与 Pydantic Settings CLI source 冲突
**缓解**: Typer 的参数映射手动桥接到 settings override dict

**逃生舱**: Typer 是已裁决选型，不退回 argparse。若 Typer 与 pydantic-settings CLI source 直接集成有阻塞性问题，保留 Typer 解析层并桥接成普通 override mapping。

---

## Phase 1 — 上游连接与认证

> **目标**: 能拿到 Copilot token、能向上游发出一个裸请求。
>
> **实施状态（2026-07-15）**：✅ 完成。130 个测试通过；认证链、Device Flow、Copilot token 生命周期、零重试 SDK raw passthrough、模型目录和 resolver 已通过独立评审与验收。

### 前置依赖

Phase 0 完成。

### 实施步骤

#### Step 1.1: Token Provider 链

**先写测试**:
```python
# tests/unit/test_auth_providers.py
@pytest.mark.asyncio
async def test_token_provider_chain():
    # mock 各 source,验证优先级
    ...
def test_github_token_file_read():
    # 验证 aiofiles off-loop 读取
    ...
```

**实现文件**:
- `src/app/auth/providers.py`: `TokenProvider` ABC,链式查找
- `src/app/auth/github.py`: GitHub token 管理(读取/存储/校验)
- `src/app/auth/device_flow.py`: GitHub OAuth 设备授权

**技术要点**:
- CLI/env/file/device-auth 优先级
- 文件 I/O 走 `aiofiles`(off-loop)

**Commit**: `feat(auth): implement token provider chain with device flow`

#### Step 1.2: Copilot Token 交换

**先写测试**:
```python
# tests/unit/test_copilot_token.py
@pytest.mark.asyncio
async def test_copilot_token_exchange(httpx_mock):
    httpx_mock.add_response(json={"token": "ghu_...", "expires_at": ...})
    manager = CopilotTokenManager(...)
    token = await manager.get_token()
    assert token.startswith("ghu_")
```

**实现文件**:
- `src/app/auth/copilot.py`: GitHub→Copilot token 交换,自动刷新

**Commit**: `feat(auth): add Copilot token exchange and auto-refresh`

#### Step 1.3: Upstream 抽象与 HTTPX 客户端

**先写测试**:
```python
# tests/unit/test_upstream_client.py
@pytest.mark.asyncio
async def test_upstream_client_with_sdk_passthrough(httpx_mock):
    # 验证 SDK client.post(cast_to=httpx.Response) 直通
    ...
def test_sdk_max_retries_zero():
    client = create_upstream_client(...)
    assert client._client.max_retries == 0
```

**实现文件**:
- `src/app/upstream/base.py`: `UpstreamTarget` 协议
- `src/app/upstream/client.py`: `httpx.AsyncClient` 封装,连接池配置
- `src/app/upstream/copilot.py`: Copilot 上游,请求头伪装
- `src/app/upstream/generic.py`: 通用上游(备用)

**技术要点**:
- **SDK max_retries=0**: 构造 `AsyncOpenAI` / `AsyncAnthropic` 时显式 `max_retries=0`
- 使用 SDK 底层 `client.post(..., cast_to=httpx.Response, stream=True)` 拿原始 bytes
- HTTP/2 支持,连接池限制,超时配置

**PoC 门禁**: 必须有回归测试确认 SDK 不消费 stream:
```python
async def test_sdk_does_not_consume_stream():
    response = await sdk_client.post(..., cast_to=httpx.Response, stream=True)
    assert not response.is_stream_consumed
```

**Commit**: `feat(upstream): implement SDK-based upstream clients with zero retries`

#### Step 1.4: 模型列表 API

**先写测试**:
```python
# tests/unit/test_models_api.py
@pytest.mark.asyncio
async def test_models_api_fetch_and_cache(httpx_mock):
    ...
def test_models_indexing_o1():
    # 验证 O(1) 查找
    ...
```

**实现文件**:
- `src/app/upstream/models_api.py`: `/models` 获取,缓存,定期刷新,O(1) 索引

**Commit**: `feat(upstream): add models API with caching and O(1) lookup`

#### Step 1.5: 模型名解析

**先写测试**:
```python
# tests/unit/test_model_resolver.py
def test_alias_resolution():
    assert resolve("opus") == "claude-opus-4.6"
def test_override_map():
    ...
def test_family_fallback():
    ...
```

**实现文件**:
- `src/app/transform/model_resolver.py`: 别名/标准化/Override/Family 回退

**Commit**: `feat(transform): implement model name resolution with alias/override/family`

### 阶段验收

**集成测试验收**:
```bash
# 1. 获取模型列表
uv run python -m app debug models
# 预期: 打印模型列表 JSON

# 2. 认证测试(需真实 GitHub token)
uv run python -m app auth
# 预期: 完成设备授权流程,写入 token 文件
```

**单元测试覆盖**:
```bash
uv run pytest tests/unit/test_auth* tests/unit/test_upstream* -v --cov=app/auth --cov=app/upstream
# 预期: 覆盖率 > 80%
```

### 里程碑

✅ 认证打通、模型列表可用、模型名可解析。

---

## Phase 2 — 核心管道最小闭环 (Walking Skeleton)

> **目标**: 第一个端到端可用请求 —— `/v1/messages` 直连 Copilot、SSE 流式直通。**全项目最重要的验证点**。
>
> **实施状态（2026-07-15）**：✅ 完成。154 个测试通过；Anthropic wire models、基础 sanitizer、零缓冲 SSE、token counting、最小 pipeline 和 Messages routes 经独立评审与验收为 0 blocker / 0 major。

### 前置依赖

Phase 0 + Phase 1。

### 实施步骤

#### Step 2.1: Anthropic 数据模型

**先写测试**:
```python
# tests/unit/test_models_anthropic.py
def test_messages_request_unknown_fields():
    req = MessagesRequest.model_validate({"messages": [...], "custom_field": "x"})
    assert req.model_extra["custom_field"] == "x"
```

**实现文件**:
- `src/app/models/anthropic.py`: `MessagesRequest` / `MessagesResponse` / `ContentBlock`,`extra="allow"`

**Commit**: `feat(models): define Anthropic request/response models`

#### Step 2.2: SSE 零缓冲直通 + 条件 PoC

**PoC 门禁**: 在采用 `sse-starlette` 前,必须运行保真 PoC:

```python
# exp/sse-starlette/poc.py + CONCLUSION.md
# 验证: 1. 逐事件不缓冲  2. 未知字段不被规范化  3. 断连检测
```

**若 PoC 通过**,写测试:
```python
# tests/unit/test_streaming_sse.py
@pytest.mark.asyncio
async def test_sse_zero_buffering():
    # 模拟逐 yield,验证不等完整响应
    ...
```

**实现文件**:
- `src/app/streaming/sse.py`: 
  - 若 PoC 通过: 使用 `sse-starlette.EventSourceResponse`,业务层仍自己格式化事件
  - 若 PoC 失败: 手写 `StreamingResponse` 包装 + 自定义 SSE 格式化
- `src/app/streaming/idle_timeout.py`: `anyio.fail_after` 包装单次 `__anext__()`

**技术要点**:
- **P6 零缓冲**: SSE generator 逐 event yield,不攒完整响应
- `X-Accel-Buffering: no` 头防止 Nginx 缓冲
- PoC 代码和结论文档必须保留并 commit；失败路径同样记录具体反例

**Commit**: `feat(streaming): implement SSE zero-buffering with idle timeout`

#### Step 2.3: Anthropic 客户端 + 基础清洗

**先写测试**:
```python
# tests/unit/test_anthropic_client.py
@pytest.mark.asyncio
async def test_anthropic_send_messages_stream():
    # 验证 SDK 直通 + stream 未被消费
    ...
# tests/unit/test_anthropic_sanitize.py
def test_tool_pairing():
    # tool_use 与 tool_result 配对修复
    ...
def test_empty_text_block_filter():
    ...
```

**实现文件**:
- `src/app/anthropic/client.py`: 使用 `AsyncAnthropic.post(..., cast_to=httpx.Response, stream=True)`
- `src/app/anthropic/sanitize/` 骨架:
  - `__init__.py`: 管道入口
  - `tool_blocks.py`: tool 配对检查,孤儿过滤
  - `text_blocks.py`: 空 text 块过滤

**Commit**: `feat(anthropic): add client with SDK passthrough and basic sanitization`

#### Step 2.4: Token Counting (最小版)

**先写测试**:
```python
# tests/unit/test_token_counting.py
@pytest.mark.asyncio
async def test_count_tokens_upstream(httpx_mock):
    # 验证默认走上游
    ...
def test_count_tokens_local_fallback():
    # tiktoken 估算
    ...
```

**实现文件**:
- `src/app/anthropic/token_counting.py`: 上游转发优先,本地估算回退

**技术要点**:
- **tiktoken startup 预载**: lifespan 阶段预先 `get_encoding("o200k_base")`,失败记录告警
- 离线部署预热并固定 `TIKTOKEN_CACHE_DIR`，禁止首个请求同步下载 encoding
- 长文本走 `anyio.to_thread.run_sync` offload；直接执行阈值由目标硬件与事件循环延迟 benchmark 固化

**Commit**: `feat(anthropic): add token counting with upstream-first and local fallback`

#### Step 2.5: 管道 Executor 最小版

**先写测试**:
```python
# tests/component/test_pipeline_executor.py
@pytest.mark.asyncio
async def test_execute_pipeline_success():
    # 验证骨架流程: sanitize → (限流占位) → execute
    ...
```

**实现文件**:
- `src/app/pipeline/context.py`: `RequestContext` 状态机
- `src/app/pipeline/executor.py`: `execute_pipeline` 主循环(重试策略为空列表占位)
- `src/app/pipeline/rate_limiter.py`: `AdaptiveRateLimiter` 空实现(直通,Phase 5 再填充)

**技术要点**:
- 限流器此阶段只是 `async def acquire(): return 0`,不阻塞
- 重试策略列表为空,首次失败直接抛错

**Commit**: `feat(pipeline): implement minimal executor with context state machine`

#### Step 2.6: Anthropic 路由 `/v1/messages`

**先写测试**:
```python
# tests/http/test_anthropic_routes.py
@pytest.mark.asyncio
async def test_post_v1_messages_stream(client, httpx_mock):
    httpx_mock.add_response(stream=sse_generator(...))
    resp = client.post("/v1/messages", json={...}, headers={"Accept": "text/event-stream"})
    assert resp.status_code == 200
    # 验证逐事件返回
```

**实现文件**:
- `src/app/routes/anthropic.py`: `POST /v1/messages`,`POST /v1/messages/count_tokens`

**Commit**: `feat(routes): add /v1/messages endpoint with SSE streaming`

### 阶段验收

**端到端验收 (需真实 Copilot token)**:
```bash
# 1. 启动服务
uv run python -m app start &

# 2. 发送测试请求
curl -X POST http://localhost:4141/v1/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "claude-opus-4.6",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 100,
    "stream": true
  }'

# 预期: 看到逐行 SSE 事件流
```

**Claude Code 集成测试**:
```bash
# 配置 Claude Code 连接到本地代理
# 验证: 能发起对话,流式响应正常
```

### 里程碑

✅ **Claude Code 能连上、能对话、能流式**。这是全项目最关键的里程碑。

### 风险与回滚

**风险**: sse-starlette PoC 失败(非常规帧被规范化)
**逃生舱**: 退回手写 `StreamingResponse` + 自定义 SSE 格式化

---

## Phase 3 — OpenAI 协议族

> **目标**: 补齐 OpenAI 三端点 + 跨格式翻译。
>
> **实施状态（2026-07-15）**：✅ 完成。184 个测试通过，覆盖率 91.55%；Chat/Responses/Embeddings、三前缀、translator、sanitizer/accumulators、httpx-ws 与管理端点经独立复审为 0 blocker / 0 major。

### 前置依赖

Phase 2 完成。

### 实施步骤

#### Step 3.1: OpenAI 数据模型

**实现文件**:
- `src/app/models/openai.py`: `ChatCompletionRequest` / `ResponsesRequest`,`extra="allow"`

**Commit**: `feat(models): define OpenAI Chat/Responses models`

#### Step 3.2: 跨协议翻译器

**先写测试**:
```python
# tests/unit/test_translator.py
def test_anthropic_to_openai_messages():
    # 验证未知字段保留
    ...
def test_openai_to_anthropic_tools():
    ...
```

**实现文件**:
- `src/app/transform/translator.py`: 非流式格式翻译(Anthropic ↔ OpenAI ↔ Responses)
- `src/app/transform/system_prompt.py`: 系统提示词定制(prepend/append/regex)
- `src/app/streaming/translator.py`: 流式逐事件翻译

**技术要点**:
- 保留未知字段
- thinking signature / server_tool 块保真

**Commit**: `feat(transform): add cross-protocol translator with unknown-field preservation`

#### Step 3.3: OpenAI 客户端三件套

**实现文件**:
- `src/app/openai/client.py`: Chat Completions
- `src/app/openai/responses_client.py`: Responses API
- `src/app/openai/responses_conversion.py`: `call_` → `fc_` 标准化
- `src/app/openai/embeddings.py`: Embeddings
- `src/app/openai/sanitize.py`: OpenAI 消息清洗
- `src/app/openai/stream_accumulator.py`: Chat SSE 累积器
- `src/app/openai/responses_stream_accumulator.py`: Responses SSE 累积器

**Commit**: `feat(openai): add Chat/Responses/Embeddings clients with sanitization`

#### Step 3.4: Responses WebSocket + 条件 PoC

**PoC 门禁**: 采用 `httpx_ws` 前必须验证:

```python
# exp/httpx-ws/poc.py + CONCLUSION.md
# 1. 逐消息不缓冲  2. 取消传播  3. 代理/TLS 透传  4. Python 3.14 安装
```

**若 PoC 通过**:

**实现文件**:
- `src/app/routes/responses.py`: `GET /v1/responses`(WebSocket 升级)
- 上游侧使用 `httpx_ws.aconnect_ws(client=httpx_client)`

**若 PoC 失败**: 记录逃生舱为 `websockets`,但需要单独维护连接配置

PoC 资产与结论文档必须保留并 commit；测试还需覆盖 bounded queue/backpressure 与 shutdown 取消清理。

**Commit**: `feat(routes): add Responses WebSocket with httpx_ws upstream client`

#### Step 3.5: OpenAI 路由

**实现文件**:
- `src/app/routes/openai.py`: `POST /v1/chat/completions`,`GET /v1/models`,`POST /v1/embeddings`
- `src/app/routes/responses.py`: HTTP 与 WS 路由

**Commit**: `feat(routes): add OpenAI Chat/Responses/Embeddings routes`

#### Step 3.6: 管理与静默端点

**实现文件**:
- `src/app/routes/token.py` / `usage.py` / `config.py` / `event_logging.py`(轻量实现)

**Commit**: `feat(routes): add management and silent-consumption endpoints`

### 阶段验收

**端到端验收**:
```bash
# 1. Chat Completions
curl -X POST http://localhost:4141/v1/chat/completions \
  -d '{"model":"gpt-5.5","messages":[...]}'

# 2. Responses API (HTTP)
curl -X POST http://localhost:4141/v1/responses \
  -d '{"model":"gpt-5.5","input":{...}}'

# 3. Responses WebSocket
wscat -c ws://localhost:4141/v1/responses
# 发送 JSON,验证逐消息返回
```

### 里程碑

✅ OpenAI 生态客户端(Cursor 等)可用。

---

## Phase 4 — Anthropic 深度兼容

> **目标**: 把 Anthropic 路径做深做正确。价值密度最高、也是上游最复杂的部分。
>
> **实施状态（2026-07-15）**：✅ 完成。205 个测试通过；Thinking、feature negotiation、tools、header policy、warmup、sanitizer 与 request preparation 已接入生产路径并通过独立复审，最终 0 blocker / 0 major。

### 前置依赖

Phase 3 完成。

### 实施步骤

#### Step 4.1: 完整 2 阶段清洗

**实现文件**:
- `src/app/anthropic/sanitize/` 补全:
  - `content_blocks.py` / `deduplicate_tool_calls.py` / `read_tool_result_tags.py`
  - `system_prompt.py` / `system_reminders.py`

**Commit**: `feat(anthropic): complete 2-phase sanitization pipeline`

#### Step 4.2: Thinking 管道 (L1/L3 内存版)

**先写测试**:
```python
# tests/unit/test_thinking_pipeline.py
def test_thinking_block_preserve():
    # 验证块级保护
    ...
def test_destack_move_blocks():
    # 去堆叠策略
    ...
def test_l3_quarantine_memory():
    # 内存隔离表,滑动 TTL
    ...
```

**实现文件**:
- `src/app/anthropic/thinking/protection.py`: 块级保护
- `src/app/anthropic/thinking/destack.py`: 去堆叠(passthrough/insert_text/move_blocks)
- `src/app/anthropic/thinking/quarantine.py`: **L3 内存隔离表**(dict + 滑动 TTL,替代上游磁盘 sidecar)
- `src/app/anthropic/thinking/strip_all.py`: L2 剥离(Phase 5 作为重试策略接入)
- `src/app/anthropic/thinking/signature_compat.py`: signature 兼容

**技术要点**:
- **P5 内存重设计**: L3 隔离表是纯内存 `dict[(session_id, agent_id), float]`,不走磁盘
- 滑动 TTL: 每次命中刷新过期时间
- L2 剥离在 Phase 5 作为 `PoisonedThinkingRetryStrategy` 接入

**Commit**: `feat(anthropic): implement thinking pipeline with memory-based L3 quarantine`

#### Step 4.3: Feature Negotiation 内存缓存

**先写测试**:
```python
# tests/unit/test_feature_negotiation.py
def test_11_category_learning():
    # 验证 features/betas/efforts/... 11 个类别
    ...
def test_ttl_裁决():
    ...
def test_config_twin_merge():
    # config ∪ 学习缓存
    ...
```

**实现文件**:
- `src/app/anthropic/feature_negotiation.py`: 11 类学习缓存,TTL 裁决,内存常驻
- `src/app/anthropic/features.py`: 特性检测 + beta headers

**技术要点**:
- **内存常驻**: 学习缓存主体是 `dict`,查询 O(1),零 I/O
- **异步落盘**: 防抖写,临时文件 + `os.replace` 原子写
- v1→v2 迁移自动处理

**Commit**: `feat(anthropic): add 11-category feature negotiation with memory caching`

#### Step 4.4: Tool 预处理管道

**实现文件**:
- `src/app/anthropic/message_tools.py`: tool_search 注入,defer_loading,CC 官方工具
- `src/app/anthropic/server_tool_filter.py`: 响应侧 server tool 过滤 + 块索引重映射

**Commit**: `feat(anthropic): add tool preprocessing with search injection and filtering`

#### Step 4.5: Header 转发策略

**实现文件**:
- `src/app/anthropic/header_policy/request_header_forward.py`: 黑/白名单 + 安全底线
- `src/app/anthropic/header_policy/response_header_forward.py`: 同上

**技术要点**:
- 注意 Anthropic SDK 会注入 `x-stainless-timeout`,不应误判为客户端注入

**Commit**: `feat(anthropic): implement header forwarding policy with security floor`

#### Step 4.6: Warmup 策略

**实现文件**:
- `src/app/anthropic/warmup.py`: allow/reject/drop/fake

**Commit**: `feat(anthropic): add warmup request strategy`

#### Step 4.7: 请求准备总编排

**实现文件**:
- `src/app/anthropic/request_preparation.py`: cache control 四模式,context editing,特性协商

**Commit**: `feat(anthropic): implement request preparation orchestration`

### 阶段验收

**单元测试覆盖**:
```bash
uv run pytest tests/unit/test_thinking* tests/unit/test_feature* -v --cov=app/anthropic
# 预期: thinking 与 feature negotiation 机制完整可测
```

**集成测试**:
```bash
# 验证 thinking L1 destack 生效
# 验证 feature negotiation 学习并主动跳过不支持功能
```

### 里程碑

✅ Anthropic 路径机制完整——保护/destack/剥离/隔离/特性协商/cache/header/warmup 均单元可测。

**重要说明**: thinking L2/L3 的**行为闭环**(拒绝后剥离→重试→成功→记入隔离表→后续主动跳过)依赖 Phase 5 的 `PoisonedThinkingRetryStrategy` 接入,本阶段只完成机制就绪。

---

## Phase 5 — 韧性与重试

> **目标**: 容错、限流、优雅关闭。让代理"扛得住"。
>
> **实施状态（2026-07-15）**：✅ 完成。218 个测试通过；retry owner、limiter feedback、自愈 Thinking、truncate/token cache、stream resilience、context consumers、4 阶段 shutdown 与 KMP 经独立复审为 0 blocker / 0 major。

### 前置依赖

Phase 4 完成。

### 实施步骤

#### Step 5.1: 重试策略完整集

**先写测试**:
```python
# tests/unit/test_retry_strategies.py
@pytest.mark.asyncio
async def test_network_retry():
    ...
async def test_token_refresh_retry():
    ...
async def test_auto_truncate_retry():
    ...
async def test_poisoned_thinking_retry():
    # L2 剥离 → 重试 → 学习写 L3
    ...
```

**实现文件**:
- `src/app/pipeline/strategies/` 全部策略:
  - `network_retry.py` / `token_refresh.py` / `auto_truncate.py`
  - `orphan_cleanup.py` / `deferred_tool_retry.py`
  - `poisoned_thinking.py`: **接入 Phase 4 的 L2 剥离,成功后写 L3 隔离表**
  - `server_tool_rejection.py`: server tool 降级重试

**技术要点**:
- `PoisonedThinkingRetryStrategy`: 400 匹配"thinking cannot be modified" → 调用 `strip_all_thinking()` → 重试 → 成功后 `quarantine.record(session, agent)`
- 共享 `max_reactive_retries` 预算
- 策略优先级: 网络 → token → auto-truncate → orphan → thinking → server-tool

**Commit**: `feat(pipeline): implement full retry strategy suite with thinking L2/L3 closure`

#### Step 5.2: 自适应限流器

**先写测试**:
```python
# tests/unit/test_rate_limiter.py
@pytest.mark.asyncio
async def test_rate_limiter_三态():
    # Normal → Rate-Limited → Recovering → Normal
    ...
```

**实现文件**:
- `src/app/pipeline/rate_limiter.py`: 完整实现(替换 Phase 2 的空实现)

**Commit**: `feat(pipeline): implement adaptive rate limiter with 3-state machine`

#### Step 5.3: Auto-Truncate 引擎

**先写测试**:
- `tests/unit/test_token_limits.py`: key 仅按规范化 model、默认 24h TTL、目录/错误明确 limit 立即刷新、到期后回到响应式学习、不主动探针
- `tests/unit/test_auto_truncate.py`: tool 配对、thinking/system 保护、原消息索引映射、最近对话保留、截断后重跑 Phase 2 sanitize

**实现文件**:
- `src/app/auto_truncate/engine.py`: 截断策略选择
- `src/app/auto_truncate/token_limits.py`: 动态 token 限制学习

**技术要点**:
- 用户已裁决 token-limit cache 使用 24h 可配置 TTL，key 仅为规范化 model；若未来出现跨账户/endpoint 反例，必须做持久化 key 迁移

**Commit**: `feat(auto-truncate): add responsive truncation engine with limit learning`

#### Step 5.4: 流式韧性

**实现文件**:
- `src/app/streaming/keepalive.py`: keepalive 心跳(empty_text / ping)
- `src/app/streaming/delayed_commit.py`: 延迟提交窗口
- `src/app/streaming/buffered_retry.py`: 缓冲重试(默认关)

**Commit**: `feat(streaming): add resilience features (keepalive/delayed-commit/buffered-retry)`

#### Step 5.5: RequestContextManager

**实现文件**:
- `src/app/pipeline/manager.py`: stale reaper,deadline
- `src/app/context/manager.py`: 门面
- `src/app/context/consumers.py`: 消费者注册
- `src/app/context/error_persistence.py`: 错误持久化(off-loop)

**Commit**: `feat(pipeline): add RequestContextManager with stale reaper and deadline`

#### Step 5.6: AnyIO 取消传播门禁

**先写集成测试**:
- `tests/integration/test_cancellation.py`: lifespan task group、流式 `__anext__()`、httpx/httpx_ws asyncio transport、审批等待者在 cancel scope 触发后全部退出
- 检查所有通过 `asyncio.create_task()` 创建的互操作任务都被保存、取消并 await，不产生 task leak 或 “Task was destroyed” 告警

**实现要求**:
- 应用生命周期和后台服务使用 AnyIO task group
- timeout/cancel scope 内使用 `task_group.start_soon()`；只有底层库互操作允许原生 asyncio task

**Commit**: `test(concurrency): verify AnyIO cancellation across asyncio transports`

#### Step 5.7: 优雅关闭

**实现文件**:
- `src/app/shutdown.py`: 4 阶段关闭 + 信号升级

**技术要点**:
- Setup → Graceful Wait → Abort → Force Close 的阶段编排保留自研，等待与升级使用 AnyIO cancel scope/event 原语
- History DB 只在 finalize 关闭；客户端连接先于上游连接关闭

**Commit**: `feat(shutdown): implement 4-phase graceful shutdown with signal escalation`

#### Step 5.8: KMP 重复检测

**先写测试**:
- `tests/unit/test_repetition_detector.py`: 与朴素周期 oracle 做 property-based/differential 对拍，覆盖跨 delta 边界、固定窗口淘汰、最小模式/重复次数和无误报文本

**实现文件**:
- `src/app/repetition_detector.py`: 有界窗口 KMP 前缀函数检测，只告警不截断流

**Commit**: `feat(streaming): add bounded KMP repetition detector`

### 阶段验收

**集成测试**:
```bash
# 1. 验证 thinking L2/L3 端到端
# 发送带 thinking 的历史消息,触发 400,验证自动剥离并成功

# 2. 验证限流自愈
# 人工触发 429,验证进入 Rate-Limited 后自动恢复

# 3. 验证优雅关闭
kill -TERM <pid>
# 验证: Graceful Wait → Abort → Force Close 阶段输出
```

### 里程碑

✅ 长时运行稳定、优雅关闭、限流自愈;**thinking L2/L3 端到端可用**。

---

## Phase 6 — 历史与可观测性

> **目标**: 审计、监控、运维面板。

### 前置依赖

Phase 5 完成。

### 实施步骤

#### Step 6.1: 异步 SQLite 历史存储

**先写测试**:
```python
# tests/component/test_history_store.py
@pytest.mark.asyncio
async def test_history_writer_bounded_queue():
    # 验证有界队列 + 背压丢弃
    ...
async def test_reaper_success_failure_buckets():
    ...
```

**实现文件**:
- `src/app/history/sqlite/schema.py`: 建表 DDL
- `src/app/history/sqlite/writer.py`: 单一 writer 协程 + `asyncio.Queue` + `asyncio.to_thread`
- `src/app/history/sqlite/reaper.py`: 分桶删最旧
- `src/app/history/sqlite/sessions_agg.py`: Session 聚合

**技术要点**:
- **P1 off-loop**: SQLite 调用走 `asyncio.to_thread`
- 有界队列(maxsize=1000),满时丢弃 `discardable` job
- 单一 writer 持有唯一连接,免锁

**Commit**: `feat(history): implement async SQLite store with bounded queue`

#### Step 6.2: In-flight 映射与 Sessions

**实现文件**:
- `src/app/history/in_flight.py`: 进行中请求内存映射
- `src/app/history/sessions.py`: Session 识别(HTTP header 优先)
- `src/app/history/types.py`: `HistoryEntry` / `EntrySummary` / `SessionSummary`

**Commit**: `feat(history): add in-flight tracking and session identification`

#### Step 6.3: WebSocket 实时推送

**实现文件**:
- `src/app/history/ws.py`: WebSocket 连接管理与广播

**Commit**: `feat(history): add WebSocket real-time push`

#### Step 6.4: History API

**实现文件**:
- `src/app/routes/history.py`: `/history/api/*` 查询端点 + `/history/ws`

**Commit**: `feat(routes): add history query and WebSocket endpoints`

#### Step 6.5: OTel 自动 instrumentation

用户已决定接受 beta instrumentation。core/contrib 依赖在 Phase 0 作为兼容批次安装；运行时默认关闭，仅当配置显式启用时激活。

**先写测试**:
- 默认配置下不 instrument；启用后只安装一次，不重复注册 middleware/transport
- HTTPX instrumentation 不消费、不包装 SSE body，业务完整流时长由项目指标表达
- structlog 渲染时从有效 OTel span 单向注入 trace_id/span_id；无 span 时省略字段

**实现文件**:
- `src/app/observability/tracing.py`: `FastAPIInstrumentor.instrument_app()`,`HTTPXClientInstrumentor().instrument()`
- `src/app/observability/middleware.py`: 请求日志中间件(structlog contextvars 集成)

**Commit**: `feat(observability): integrate OTel auto-instrumentation (beta, opt-in)`

#### Step 6.6: Metrics 与 Prometheus

**实现文件**:
- `src/app/observability/telemetry.py`: 删除手写 `_counters` dict,只保留 OTel Metrics API
- `src/app/routes/metrics.py`: `/metrics` 用 `PrometheusMetricReader` 拉取

**技术要点**:
- **单一数据源**: 只用 OTel `Counter`/`Histogram`,不双写
- `PrometheusMetricReader` pull 模型

**Commit**: `feat(observability): add Prometheus metrics with OTel single data source`

#### Step 6.7: 管理 API

**实现文件**:
- `src/app/routes/management.py`: `/api/status`,`/api/config`,`/api/tokens`,`/api/models`,`/api/logs`,`/api/negotiation/*`

**Commit**: `feat(routes): add management API endpoints`

#### Step 6.8: TUI

**实现文件**:
- `src/app/observability/tui.py`: Textual TUI

**先写测试**:
- reducer 纯函数状态迁移、关键按键/布局 smoke、TUI 关闭时不订阅或影响请求路径

**技术要点**:
- Textual 是已选实现库；功能可由运行时配置关闭，不通过删除依赖或砍实现表达“可选”

**Commit**: `feat(observability): add terminal UI with Textual`

### 阶段验收

**集成测试**:
```bash
# 1. 发送几个请求,验证 SQLite 落盘
sqlite3 <data_dir>/history.db "SELECT * FROM entries;"

# 2. WebSocket 推送
wscat -c ws://localhost:4141/history/ws
# 发请求,验证实时推送

# 3. Prometheus 抓取
curl http://localhost:4141/metrics
# 预期: Prometheus 文本格式

# 4. 管理 API
curl http://localhost:4141/api/negotiation
# 预期: 11 类学习缓存快照
```

### 里程碑

✅ 完整审计 + 可观测。

---

## Phase 7 — 手动审批

> **目标**: 完成可超时、可修改、可在 shutdown 中确定性拒绝的审批闭环。

### Step 7.1: ApprovalGate 状态机

**先写测试**:
- `tests/unit/test_approval_gate.py`: approve、reject、modify-and-approve、timeout、重复裁决幂等、并发 pending 隔离
- `test_reject_all_pending_on_shutdown`: Phase 1/3 触发后全部等待者被唤醒且没有孤儿 task

**实现文件**:
- `src/app/pipeline/approval.py`: AnyIO event/cancel scope 门控，pending registry 有界且确定性清理

**Commit**: `feat(pipeline): implement approval gate state machine`

### Step 7.2: Approval REST/WS API

**先写测试**:
- `tests/http/test_approval_routes.py`: list/detail/approve/reject/modify 输入校验与竞态返回
- `tests/integration/test_approval_ws.py`: 复用 Phase 6 `WebSocketManager` 广播 pending/resolved 事件

**实现文件**:
- `src/app/routes/approval.py`: `/api/approval/*` 审批端点(复用 Phase 6 的 `history/ws.py` WebSocketManager)

**Commit**: `feat(routes): add approval REST and WebSocket APIs`

### 阶段验收

```bash
uv run pytest tests/unit/test_approval_gate.py tests/http/test_approval_routes.py tests/integration/test_approval_ws.py -v
```

黑盒验收：一个请求进入 pending 后可在另一个客户端批准、拒绝或修改后批准；超时与 shutdown 都会结束原请求且 pending 数归零。

---

## Phase 8 — 多协议扩展

> **目标**: 落地 Azure OpenAI 与 Gemini `/v1beta`，复用既有 translator、streaming 和上游能力，不另建并行 pipeline。

### Step 8.1: Gemini 模型与路径解析

**先写测试**:
- `tests/unit/test_gemini_models.py`: unknown 字段保真、usage/reasoning 映射
- `tests/unit/test_gemini_paths.py`: `models/{model}:generateContent` 与 `:streamGenerateContent` 分割，非法 method 早退

**实现文件**:
- `src/app/models/gemini.py`: Gemini 模型
- `src/app/protocols/gemini.py`: 路径解析与请求/响应适配

**Commit**: `feat(gemini): add models and v1beta path parsing`

### Step 8.2: Gemini 转换与路由

**先写测试**:
- `tests/unit/test_gemini_translation.py`: Gemini ↔ 内部规范，tool/thinking/unknown 字段策略
- `tests/http/test_gemini_routes.py`: 非流式与逐事件流式，断言 P6 零缓冲

**实现文件**:
- `src/app/routes/gemini.py`: Gemini `/v1beta` 路由，流式复用 `streaming/translator.py`

**Commit**: `feat(gemini): add v1beta routes and streaming translation`

### Step 8.3: Azure deployment 解析与适配

**先写测试**:
- `tests/unit/test_azure_protocol.py`: classic deployment 与 v1 路径、api-version、deployment→model override
- `tests/http/test_azure_routes.py`: Chat/Responses 请求、错误格式与 header 保真

**实现文件**:
- `src/app/protocols/azure.py`
- `src/app/routes/azure.py`

**技术要点**:
- **复用** Phase 3 的 openai 客户端与清洗
- **复用** Phase 4 的 anthropic 深度能力

**Commit**: `feat(azure): add deployment and v1 protocol adapters`

### 阶段验收

```bash
uv run pytest tests/unit/test_gemini* tests/unit/test_azure* tests/http/test_gemini_routes.py tests/http/test_azure_routes.py -v
```

黑盒验收：Gemini 非流式/流式请求与 Azure classic/v1 请求都复用统一 attempt、metrics、shutdown 和 error pipeline。

---

## Phase 9 — 可选能力 (BACKLOG)

按需启动,不在本计划强制范围内。

### 已选库的条件基准：uvloop

这不是可砍功能，而是选型门禁。用本项目 SSE/WS 并发、取消、信号升级和四阶段 shutdown 场景，对 asyncio 3.14 与 uvloop 做同机对照；保存 benchmark 脚本、原始结果和结论文档。只有吞吐/尾延迟有稳定收益且取消/shutdown 行为等价时，才把 uvloop 设为 Linux/macOS 默认 deployment extra；Windows 保持 asyncio。

---

## 跨阶段持续任务

### 文档同步点

每个阶段完成后:
1. 更新仓库根 [TODO_CURRENT.md](../../../TODO_CURRENT.md)，勾选对应 Phase 的复选框
2. 若设计有调整,同步更新对应专题设计文档
3. 若引入新库,更新 `SELECTIONS.md`

### Conventional Commits 规范

```
feat(module): description       # 新功能
fix(module): description        # Bug 修复
refactor(module): description   # 重构
test(module): description       # 测试
docs: description               # 文档
chore: description              # 构建/工具
perf(module): description       # 性能优化
```

### 持续集成检查

每次 commit 前:
```bash
# 1. 格式化
uv run black src/ tests/
uv run isort src/ tests/

# 2. 类型检查
uv run mypy src/

# 3. 单元测试
uv run pytest tests/unit/ -v

# 4. 集成测试(Phase 2+ 可用)
uv run pytest tests/http/ -v
```

---

## 总结

本计划共 9 个 Phase。完成条件以每阶段测试、PoC 门禁和用户可观察验收为准，不以预估工时替代验收。Phase 5 与 Phase 6 在公共 context/bus 契约冻结后可并行；Phase 7 与 Phase 8 可分别在其前置接口稳定后并行推进。

关键里程碑:
- **Phase 0 完成**: 地基就绪
- **Phase 2 完成**: 端到端打通(最重要)
- **Phase 4 完成**: Anthropic 深度能力就绪
- **Phase 6 完成**: 生产级可观测性

每个 Phase 独立可验收,支持增量交付。
