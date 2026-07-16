# 实施交接：Phase 5～9

> 更新时间：2026-07-15
> 当前 HEAD：`f8adb39`
> 用户指令：持续实施直至最终完成；只有出现无法从已定规格裁决的分歧时才询问用户。

## 已完成

- Phase 0：Python 3.14、Typer、四层配置、structlog、基础模型、FastAPI/AnyIO lifespan、health、wire JSON。
- Phase 1：GitHub token providers、Device Flow、Copilot token single-flight/有限重试/后台刷新、零重试 SDK、Copilot/Generic targets、模型目录、resolver。
- Phase 2：Anthropic wire models、基础 sanitizer、SSE 零缓冲/idle timeout、token counting、最小 pipeline、Messages/count_tokens routes。
- Phase 3：OpenAI wire models、Chat/Responses/Embeddings、三前缀 routes、translator/system prompt、sanitizer/accumulators、正式 httpx-ws upstream transport、management routes。
- Phase 4：Thinking protection/destack/strip/L3 内存隔离/signature shim、11 类 feature negotiation 内存 store、features、tools、header floor、warmup、深度 sanitizer、request preparation 生产接线。

## 已冻结的硬约束

1. P1：阻塞磁盘/SQLite/tokenizer 长任务 off event loop。
2. P6：默认 SSE/WS 零整体缓冲；逐事件/逐消息转发；显式 cleanup。
3. 外部 wire model `extra="allow"`，显式 unknown null 不得丢失。
4. Pipeline 是普通请求唯一 retry owner；SDK `max_retries=0`，HTTP transport retry=0。Copilot token exchange 自身的有限重试是认证子系统内部职责。
5. AnyIO task group/cancel scope 结构化持有后台服务；禁止无管理 fire-and-forget task。
6. OTel instrumentation 已安装但运行时默认关闭。
7. `RuntimeState` 是 `app.state` 中唯一类型化运行时容器；routes 通过 `deps.py` 获取服务。
8. Responses upstream WebSocket 正式使用 `httpx_ws`，`ws_queue_size` 从配置传入。
9. 配置管理端点必须脱敏 `auth.github_token` 和 `upstream.api_key`。

## 当前验证基线

- Phase 4 收尾时：205 tests passed。
- Ruff 全项目通过。
- Pyright strict 全项目通过。
- 最近 Phase 4 独立复审：0 blocker / 0 major。

## Phase 5 下一步顺序

严格按 `IMPLEMENTATION_PLAN.md` Phase 5 TDD 实施并做语义提交：

1. `pipeline/strategies/`：定义 `RetryStrategy` / `RetryAction`，实现 network、token refresh、auto truncate、orphan cleanup、deferred tool、poisoned thinking、server tool rejection；每 attempt 只允许一个 strategy owner；共享预算。
2. `pipeline/rate_limiter.py`：替换 passthrough limiter，AnyIO 结构化三态 Normal/Rate-Limited/Recovering，不得裸 `create_task()`。
3. `auto_truncate/engine.py` + `token_limits.py`：动态限制缓存 key 仅 normalized model，TTL 24h；长 tokenizer 操作 off-loop。
4. `streaming/keepalive.py`、`delayed_commit.py`、`buffered_retry.py`：默认路径零缓冲；buffered retry 仅显式 opt-in。
5. `pipeline/manager.py` + `context/consumers.py` + `error_persistence.py`：active context、deadline/stale reaper、观察者；I/O sink off-loop。
6. `shutdown.py`：Setup → Graceful Wait → Abort → Force Close，信号升级。
7. `repetition_detector.py`：独立 KMP step/commit；流式告警不干预输出。

每个语义单元：先写红灯测试 → 实现 → Ruff/Pyright/全量 pytest → Conventional Commit。

## Phase 6～9 后续

- Phase 6：history SQLite 单 writer + bounded queue、session/WS、OTel tracing/metrics、Prometheus `/metrics`、Textual TUI。
- Phase 7：AnyIO ApprovalGate + REST/WS，复用 Phase 6 WebSocket manager。
- Phase 8：Azure deployment adapter、Gemini models/translator/routes，复用核心 pipeline。
- Phase 9：按已定 BACKLOG 实现剩余可选能力；不得以 YAGNI/ROI 静默缩减已记录范围。

## Git 工作区注意

工作区仍有上一个调研会话留下的 staged/unstaged 文档、`refs/available_models.json` 和 `exp/upstream-sdk-passthrough/`。后续提交必须继续用 `git commit --only <本语义文件>`，不得混入这些既有改动。`verification/` 是 Phase 3 verifier 生成的未跟踪资产，需审阅后决定纳入 `exp/phase3-acceptance/`，不要直接删除。
