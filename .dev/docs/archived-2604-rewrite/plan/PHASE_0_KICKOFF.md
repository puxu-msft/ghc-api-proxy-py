# Kick-off Prompt: ghc-api-proxy-py Phase 0 实施

## 项目背景

你正在实施 `ghc-api-proxy-py` 项目——一个高性能、生产级的 LLM API 代理服务器,支持 Anthropic、OpenAI、Gemini 等多协议,面向 Python 3.14 环境。

项目已完成:
- ✅ 完整的设计文档树(位于 `docs/2604-rewrite/`)
- ✅ 成熟库选型调研与用户裁决(见 `docs/2604-rewrite/lib-survey/SELECTIONS.md`)
- ✅ 分阶段实施计划(见 `docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md`)

## 当前状态

**代码库现状**:
- `src/app/__init__.py`: 空文件
- `src/app/__main__.py`: 只有简单的 `print("Hello")` 占位符
- `pyproject.toml`: 基础依赖已声明，但需在实施当日重新解析、验证并锁定最新稳定兼容版本

**下一步目标**: 完成 **Phase 0 — 项目骨架与基础设施**

## Phase 0 目标

完成后,服务应该能:
1. ✅ 启动不报错
2. ✅ 使用 Typer CLI 支持 `--help` / `--config` / `--port` 等选项
3. ✅ 输出结构化日志(JSON 或 text 格式可切换)
4. ✅ 从四层配置源合并配置(defaults < yaml < env < cli)
5. ✅ 响应健康检查 `/health/liveness`

## 核心技术约束(必须遵守)

### 1. 库选型约束
- **版本纪律**: 调研版本只作已验证基线；实施当日重查 Typer、structlog、pydantic-settings、platformdirs 等最新稳定兼容版，跑 Python 3.14 smoke 后锁定
- **CLI**: 从起点采用 Typer，不走 argparse 中间态
- **日志**: 使用 structlog 实现 request_id contextvars 传播
- **配置**: 使用 pydantic-settings 的 `settings_customise_sources` + 自定义 merge source
- **路径**: 使用 platformdirs 替代手写 XDG 路径
- **I/O**: 所有阻塞磁盘 I/O 必须 off-loop；按场景使用 `anyio.to_thread.run_sync`、`asyncio.to_thread`、专用 executor 或 `aiofiles`，不把 aiofiles 扩张为唯一 I/O 抽象
- **并发**: lifespan 和后台服务使用 AnyIO task group；禁止无管理的 fire-and-forget task
- **OTel**: beta instrumentation 依赖随兼容批次安装，但运行时默认关闭

### 2. 架构约束
- **P1 off-event-loop**: 磁盘 I/O 必须 `asyncio.to_thread` 或 `aiofiles`
- **TDD 优先**: 每个模块先写测试,再写实现
- **Conventional Commits**: 遵循 `feat(module): description` 格式

### 3. Python 3.14 特定
- 项目要求 `requires-python = ">=3.14"`
- 第一步必须验证所有核心依赖可在 Python 3.14 导入

## 执行步骤(按顺序)

### Step 0.1: Python 环境与依赖验证
1. 创建 `.python-version` 文件,内容 `3.14.2`
2. 查询并更新 `pyproject.toml` 到当日最新稳定兼容版本，OTel core/contrib 作为原子批次解析
3. 创建 `tests/smoke/test_imports.py`,验证核心依赖可导入
4. 运行 `uv sync && uv run pytest tests/smoke/ -v`

### Step 0.2: CLI 骨架（Typer）
1. 先写 `tests/unit/test_cli.py`:
   - `test_cli_smoke()`: 验证 `--help` 输出
   - `test_start_subcommand()`: 验证 `start` 子命令存在
2. 实现 `src/app/cli.py`:
   - 定义 Typer app
   - 添加子命令: `start` / `auth`（别名 `login`）/ `logout` / `debug` / `setup-claude-code` / `setup-codex` / `list-claude-code`
   - `start` 选项: `--port` / `--host` / `--verbose` / `--config` / `--manual` / `--generate-config` 等
3. 更新 `src/app/__main__.py` 调用 `cli.app()`
4. 验证: `uv run python -m app start --help`
5. Commit: `feat(cli): bootstrap Typer CLI with start/auth/debug subcommands`

### Step 0.3: 配置系统（Pydantic Settings）
1. 先写 `tests/unit/test_config_loader.py`:
   - `test_four_layer_merge()`: 验证 defaults < yaml < env < cli
   - `test_per_key_merge_model_mappings()`: 验证 per-key 合并
   - `test_compat_migration()`: 验证弃用键迁移
2. 实现:
   - `src/app/config/settings.py`: frozen Pydantic `AppSettings` 模型
   - `src/app/config/loader.py`: `settings_customise_sources` + 自定义 merge source
   - `src/app/config/compat.py`: 弃用键迁移(`limit` → `success_limit` 等)
   - `src/app/config/paths.py`: 使用 `platformdirs.user_config_dir()` / `user_data_dir()`
3. Commit: `feat(config): implement four-layer config merge with pydantic-settings`

### Step 0.4: 结构化日志（structlog）
1. 先写 `tests/unit/test_logging.py`:
   - `test_structlog_contextvars()`: 验证 request_id 传播
   - `test_json_text_renderer()`: 验证双格式输出
2. 实现 `src/app/observability/logging.py`:
   - structlog 配置,JSON/text 双 renderer
   - 自定义 processor 拼接固定宽度前缀(`[ OK ]` / `[FAIL]`)
   - 与 uvicorn stdlib logging 整合
3. Commit: `feat(observability): integrate structlog with contextvars-based request_id`

### Step 0.5: 数据模型基础
1. 先写 `tests/unit/test_models_common.py`:
   - `test_usage_model_unknown_fields()`: 验证 `extra="allow"`
2. 实现:
   - `src/app/models/common.py`: `Usage` / `ModelInfo` / `ErrorResponse`
   - `src/app/models/capabilities.py`: 能力元数据表(空骨架)
   - `src/app/errors.py`: `ApiError` / `classify_error`
3. Commit: `feat(models): define common data models with unknown-field preservation`

### Step 0.6: 应用工厂与 lifespan
1. 先写 `tests/integration/test_server_startup.py`:
   - `test_server_lifespan()`: 验证 startup/shutdown 不抛错
2. 实现:
   - `src/app/server.py`: `create_app(settings)`，分阶段 lifespan + 应用级 AnyIO task group（空服务占位）
   - `src/app/deps.py`: FastAPI DI 提供者骨架
3. Commit: `feat(server): create FastAPI app factory with staged lifespan`

### Step 0.7: 健康检查端点
1. 先写 `tests/http/test_health_routes.py`:
   - `test_health_liveness()`: 验证 `/health/liveness` 返回 200
2. 实现 `src/app/routes/health.py`:
   - `GET /health`
   - `GET /health/liveness`
   - `GET /health/readiness`
3. Commit: `feat(routes): add health check endpoints`

### Step 0.8: Wire JSON codec
1. 先写 `tests/unit/test_wire_json_codec.py`：标准库 differential round-trip、未知嵌套字段、非 ASCII、bytes 返回、Pydantic `model_dump(mode="json")` 边界，以及 NaN/Infinity/大整数/datetime policy
2. 实现 `src/app/wire_json.py`：集中封装 `orjson` 的 `dumps() -> bytes` 与 `loads()`
3. 不把低频配置、错误快照和迁移文件机械迁移到 `orjson`
4. Commit: `feat(codec): add orjson wire codec with differential tests`

## 阶段验收标准

全部步骤完成后,运行:

```bash
# 1. 生成配置
uv run python -m app start --generate-config

# 2. 启动服务
uv run python -m app start --port 4141 &
sleep 2

# 3. 健康检查
curl http://localhost:4141/health/liveness
# 预期输出: {"status":"ok"}

# 4. 查看日志
# 预期: structlog 格式化输出,包含 timestamp/level/event

# 5. 停止
kill %1

# 6. 单元测试全绿
uv run pytest tests/unit/ tests/http/ -v --cov=app
# 预期: 所有测试通过,覆盖率 > 80%
```

## 关键参考文档

按使用频率排序:

1. **实施计划**: `docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md`
   - 完整的 Phase 0-9 步骤
   - 技术要点与 PoC 门禁

2. **模块结构**: `docs/2604-rewrite/project-structure.md`
   - 完整目录树
   - 每个模块的职责与接口

3. **配置系统**: `docs/2604-rewrite/config-system.md`
   - 配置项完整清单
   - 四层合并规则
   - CLI 参数表

4. **库选型依据**: `docs/2604-rewrite/lib-survey/SELECTIONS.md`
   - 为什么用 Typer / structlog / pydantic-settings
   - D1-D6 架构决策

5. **设计约束**: `docs/2604-rewrite/DESIGN.md` (若存在)
   - P1-P8 性能原则
   - 借鉴状态标注

## 常见问题预判

### Q: Typer 与 pydantic-settings CLI source 怎么集成?
A: Typer 负责解析 CLI 参数到 Python dict，手动桥接到 `settings_customise_sources` 的 CLI override dict。不要试图让 Typer 直接生成 Pydantic 实例。

### Q: 固定宽度前缀怎么实现?
A: 在 structlog 的 processor chain 里加一个自定义 processor,根据 `event_dict` 的 `level` / `status` 字段拼接 `[ OK ]` / `[FAIL]` / `[RETRY]` 等前缀,再交给 renderer。

### Q: per-key merge 是什么意思?
A: `model_mappings` / `timeouts.stream_idle_overrides` 这些 dict 配置项,四层合并时应该"按键合并"(如 yaml 定义了 `opus: 60`,cli 定义了 `sonnet: 30`,合并结果应包含两个键),而不是"整体替换"(cli 覆盖 yaml 的全部内容)。

### Q: 为什么磁盘 I/O 必须 off-loop?
A: 这是 P1 约束——热路径不能阻塞事件循环。启动期一次性读取可由同步 settings source 完成，但运行期 reload、错误持久化和 SQLite 必须走明确的 off-loop 边界。

## 开始实施

**请从 Step 0.1 开始**,完成一个 Step 就告知进度并 commit。遇到问题随时参考上述文档或询问。

准备好了吗? 开始 Step 0.1: Python 环境与依赖验证。
