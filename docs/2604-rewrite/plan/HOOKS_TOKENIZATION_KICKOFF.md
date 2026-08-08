# Hooks、Tokenization 与协议修复：实施 Kick-off

> **历史实施记录，禁止作为 current kick-off 执行。** 本文描述 2026-07-17 当时的迁移步骤，已被 current [Hooks 规格](../hooks-tokenization-spec.md)、[Hooks 机制](../hooks-system.md)与[Tool Use 机制](../tool-use.md)取代。尤其不得按下文恢复跨协议 `builtin:tool_preprocessor` payload hook；该名称当前仅是兼容禁用键，ordinary tool 的 defer-loading 与 tool-search adaptation只在 route 已确定为 direct Messages 后执行。

## 任务概述

你将实施 `docs/2604-rewrite/hooks-tokenization-spec.md` 中定稿的规格说明，按照 `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md` 的 10 个阶段逐步完成。

**核心目标**：

1. 删除代理侧 `auto_truncate` 与 Anthropic server-tool support
2. 保留并增强 token counting、calibration、prompt-limit observation
3. 重写 tool pair/orphan repair 算法（全局集合 → 局部相邻）
4. 建立强类型 hooks 系统（PayloadHook、RetryStrategyFactory、ResponseHook、ObserverHook）
5. 将现有 sanitizer 改造为 built-in hooks 并集成到请求管道
6. 暴露管理 API 查询 tokenization 状态

## 背景与约束

### 项目上下文

- **项目名**：`ghc-api-proxy-py`，Python 多协议 LLM API 代理
- **技术栈**：Python 3.14, FastAPI, Pydantic v2, httpx, pytest, pyright strict, ruff
- **测试策略**：TDD 驱动，每阶段先红测试，实施转绿，覆盖率门禁 ≥80%
- **类型检查**：Pyright strict mode，零错误容忍
- **代码风格**：Ruff，遵循项目现有约定

### 硬约束（不可违背）

1. **长期正确优于短期速度**：KV cache 保真、协议官方约束、错误显式，绝不为"方便"牺牲正确性
2. **零破坏性**：不要求 reset/clean 工作树，兼容现有用户修改
3. **TDD 严格执行**：阶段 0 先捕获预期为绿的回归 oracle；阶段 1 起每个行为变更都必须从能证伪旧实现的红测试开始，不得先写实现再补测试
4. **协议规范优先**：Anthropic 官方要求（immediate-follow、result-first、幂等）必须满足
5. **反-YAGNI on feature**：spec 中所有验收要求都必须映射到计划，不得静默删除或降级
6. **类型安全**：Pyright strict 必须通过，不得用 `type: ignore` 逃避
7. **覆盖率门禁**：关键模块（tokenization、hooks、sanitize）≥95%，整体 ≥80%
8. **文档同步**：代码完成后必须更新 live docs，保持一致性

### 软约束（优先但可协商）

- 每阶段独立可测、可审、可合并
- 增量交付，避免大 PR
- 性能优化（off-event-loop、异步优先）
- 可观测性（telemetry、logging）

## 实施路径

### 推荐阶段顺序

按照实施计划的阶段 0-10 顺序执行，**不可跳过阶段**：

1. **阶段 0**：前置准备与探针 — 建立回归测试基线，记录代码清单
2. **阶段 1**：Tool pair/orphan repair 算法重写 — 核心协议修复
3. **阶段 2**：删除 auto-truncate 与 server-tool — 清理旧代码
4. **阶段 3**：Calibration 与 limits observation — 状态模型与存储
5. **阶段 4**：Hooks 类型系统与 registry — 框架基础
6. **阶段 5**：Built-in hooks 实现 — 迁移现有能力
7. **阶段 6**：Tokenization service — count_tokens endpoint
8. **阶段 7**：管理 API — 状态暴露
9. **阶段 8**：Hooks 管道集成 — 端到端流程
10. **阶段 9**：文档全局清理 — live docs 同步
11. **阶段 10**：完整验收 — 黑盒测试与门禁

### 阶段依赖关系

```
阶段 0 必须首先完成（建立基线）
    ↓
阶段 1、2、3 可并行（但推荐顺序执行）
    ↓
阶段 4 依赖阶段 3（需要 calibration 数据模型）
    ↓
阶段 5 依赖阶段 4（需要 hooks 框架）
    ↓
阶段 6 依赖阶段 3、5（需要 calibration 与 observer hooks）
    ↓
阶段 7 依赖阶段 3、6（需要状态与 service）
    ↓
阶段 8 依赖阶段 5、6（需要所有 hooks 与 service）
    ↓
阶段 9 可与阶段 8 并行
    ↓
阶段 10 依赖所有前序阶段（完整验收）
```

## 关键设计决策（必读）

### 1. Tool Pair Repair 算法

**问题**：现有全局集合算法会让跨轮同名 ID 假配对，不验证 immediate-follow 约束。

**解决方案**：局部相邻算法

- 顺序扫描 messages，维护全局已见 `tool_use.id`
- 只有紧随的 user 消息可提供 result
- 删除 orphan use/result（局部交集）
- 移动 result 到 content 数组首部（result-first）
- 幂等性验证（第二次运行零改变）

**测试覆盖**：9 类场景（adjacent、parallel、duplicate、reversed、cross-round、mixed-content、idempotence、empty message、name casing）

### 2. Tokenization Calibration

**问题**：本地估算不精确，需要从真实上游响应学习校准。

**解决方案**：Size-aware bucket calibration

- 按 `(protocol, normalized_model)` 分组
- 6 个 size buckets：[0, 15k), [15k, 30k), [30k, 60k), [60k, 120k), [120k, 240k), [240k, +∞)
- 每 bucket 维护 `sum_real / sum_estimated`，限制在 [0.5, 3.0]
- 有界滑动权重（WEIGHT_CAP=2000），避免历史冻结
- Off-event-loop 周期 flush + shutdown flush
- `RuntimeState` 持有 store；shutdown final flush 必须发生在关闭 upstream 与取消 lifespan task group 之前

**学习来源**：
1. Anthropic `/count_tokens` 精确响应
2. Anthropic completion success usage
3. Token-limit 400 错误体的 `current` 值

Completion usage 需要 byte-preserving 旁路 tap：非流式解析已读取的原始 JSON bytes，流式只旁路观察 SSE `message_delta.usage`，不得重编码、合并或延迟客户端收到的 chunks。

**消费**：上游成功返回精确值，失败时返回 calibrated 本地估算

### 3. Hooks 类型系统

**问题**：现有 sanitizer、destack、retry 策略散落各处，难以扩展和测试。

**解决方案**：强类型 hooks 框架

- 4 类 hooks：PayloadHook、RetryStrategyFactory、ResponseHook、ObserverHook
- 3 个 payload phases：pre_sanitize、post_sanitize、pre_send
- HookRegistryBuilder（可变）→ HookRegistry（不可变快照）
- `HooksConfig` 提供 `modules`、`disabled` 与 `timeout_ms`，不可变 registry 快照由 `RuntimeState` 持有
- 内建 hooks（order 0-999）vs 用户 hooks（order ≥1000）
- 错误模式：fail_request（默认）vs continue（显式）
- Observer 异常隔离（不影响请求）

**安全**：用户模块与代理同权限执行，不提供虚假 sandbox，文档明确警告

### 4. 删除边界

**删除**：
- `src/app/auto_truncate/` 整个目录
- `src/app/anthropic/server_tool_filter.py`
- `tests/unit/test_auto_truncate.py`
- Feature negotiation 的 `serverTools`/`serverToolDowngrade` 类别

**保留并迁移**：
- `src/app/anthropic/token_counting.py` → `src/app/tokenization/estimators.py`
- Token estimation、calibration、prompt-limit observation
- Client `tool_use`/`tool_result`、tool search、`defer_loading`

**破坏性变更**：从旧版本升级时，客户端历史中残留的 server-tool blocks 可能被上游拒绝，这是有意的 breaking removal，项目只提供清晰错误与 release note。

## 每阶段工作流

### 1. 理解阶段目标

- 阅读实施计划中该阶段的"目标"、"涉及文件"、"验收标准"
- 理解该阶段在整体任务中的位置与前后依赖

### 2. 编写红测试

- 严格按照计划中"测试（红）"章节编写测试
- 确保测试先失败（红），验证测试本身有效
- 不得跳过测试直接写实现

### 3. 实施代码

- 按照"实施步骤"逐步完成
- 保持类型安全（Pyright strict）
- 遵循项目代码风格（Ruff）
- 增量提交，每个子步骤可独立 commit

### 4. 转绿与清理

- 运行测试直到全绿
- 重构代码改进可读性（不改变行为）
- 检查覆盖率，补充遗漏的测试

### 5. 验收检查

- 按照"验收"清单逐项检查
- 运行类型检查：`pyright src/app/<module>/`
- 运行 lint：`ruff check src/app/<module>/`
- 运行测试：`pytest tests/unit/test_<module>.py -v --cov`
- 确认覆盖率达标

### 6. 文档与提交

- 更新相关 docstring 与注释
- 提交 commit，消息格式：`feat(<module>): <description>`（遵循 Conventional Commits）
- 准备进入下一阶段

## 关键文件速查

### 需要新建的目录与模块

```
src/app/tokenization/
├── __init__.py
├── estimators.py        # 本地估算器
├── calibration.py       # 校准模型
├── limits.py            # Prompt limit 解析
├── state_store.py       # 状态存储
└── service.py           # Count tokens service

src/app/hooks/
├── __init__.py
├── types.py             # Protocol 定义
├── registry.py          # Builder 与 Registry
├── context.py           # HookContext
├── loader.py            # 用户模块加载
└── builtin/
    ├── __init__.py
    ├── strip_read_tool_result_tags.py
    ├── thinking_destack.py
    ├── tool_preprocessor.py
    ├── deduplicate_tool_calls.py
    ├── poisoned_thinking.py
    └── token_calibration.py

src/app/pipeline/
└── hooks_executor.py    # Hooks 调用编排

tests/unit/
├── test_tool_pair_regression.py
├── test_tokenization_regression.py
├── test_anthropic_tool_pair_repair.py
├── test_tokenization_estimators.py
├── test_tokenization_calibration.py
├── test_tokenization_limits.py
├── test_tokenization_state_store.py
├── test_tokenization_service.py
├── test_hooks_registry.py
├── test_hooks_loader.py
├── test_builtin_hooks.py
├── test_hooks_executor.py
└── test_documentation.py

tests/integration/
└── test_hooks_pipeline.py

tests/acceptance/
├── test_tool_pair_acceptance.py
├── test_tokenization_acceptance.py
├── test_hooks_acceptance.py
└── test_deletion_acceptance.py

docs/2604-rewrite/
├── hooks-system.md      # 新建
└── tokenization.md      # 新建
```

### 需要修改的现有文件

```
src/app/anthropic/sanitize/tool_blocks.py      # 重写算法
src/app/anthropic/feature_negotiation.py       # 移除 serverTools/serverToolDowngrade
src/app/runtime.py                             # 添加 hook_registry 字段
src/app/routes/anthropic.py                    # 更新 count_tokens endpoint
src/app/routes/management.py                   # 扩展 /api/tokenization 管理 API
src/app/anthropic/client.py                    # 集成 hooks
src/app/pipeline/executor.py                   # attempt/retry/observer 接线
docs/2604-rewrite/sanitize-pipeline.md         # 更新
docs/2604-rewrite/request-pipeline.md          # 更新
docs/2604-rewrite/tool-use.md                  # 更新
README.md                                      # 更新
```

### 需要删除的文件

```
src/app/auto_truncate/                         # 整个目录
src/app/anthropic/server_tool_filter.py
tests/unit/test_auto_truncate.py
tests/unit/test_anthropic_server_tool_filter.py  # 如果存在
```

## 常见陷阱与注意事项

### 1. 不要跳过回归测试（阶段 0）

回归测试是重写算法的 oracle，确保现有合法行为不破坏。必须先建立基线再重写。

### 2. 不要让跨轮 ID 假配对

Tool pair repair 的核心难点：同一 ID 在不同轮次重复出现时，只保留首次轮次的 pair，后续删除。全局集合算法做不到这一点，必须用局部相邻算法。

### 3. 不要混淆 protocol 的 calibration

Anthropic 与 Gemini 的 wire protocol 序列化开销不同，真实计数口径不同，calibration key 必须包含 protocol。不得把 Anthropic 样本用于 Gemini。

### 4. 不要在 flush 时阻塞请求

State store flush 必须 off-event-loop，失败时只告警不阻塞请求结果。周期 flush 与 shutdown flush 通过 async lock 串行化。

### 5. 不要让 Observer 异常影响请求

Observer hook 异常必须隔离，记录 warning 后继续请求流程。不得因 observer 失败导致请求失败。

### 6. 不要忘记 result-first 约束

Anthropic 官方要求 user message 中所有 `tool_result` blocks 必须位于其他 text blocks 之前。算法必须稳定移动 result 到 content 数组首部。

### 7. 不要用 `type: ignore` 逃避类型检查

Pyright strict 必须通过，类型错误必须真正修复而非屏蔽。项目拒绝降低类型安全性。

### 8. 不要删除 spec 中的验收要求

所有验收要求都必须映射到实施计划，不得以"暂时用不上"或"成本高"为由删除。长期正确优于短期速度。

## 验收标准速查

完成所有阶段后，必须满足以下 8 条验收标准（对应 spec 第 9 节）：

1. ✅ 生产代码和 live docs 不再声明或引用代理侧 auto-truncate 与 server-tool support
2. ✅ 任意 built-in 路径都不会因 prompt 超限删除、压缩或摘要历史
3. ✅ Anthropic 精确 count 成功会训练 calibration；fallback 消费对应 protocol/model factor
4. ✅ Prompt-limit 400 被记录但 payload 不变，错误仍按原状态透传
5. ✅ Tool pair repair 通过 adjacent、parallel、partial、duplicate、reversed、cross-round、result-first、mixed-content 与 idempotence 测试，并保持现有合法 pair/casing 测试行为等价
6. ✅ 用户 hooks 可按确定顺序加载；冲突和启动错误显式失败；Observer 故障被隔离
7. ✅ Ruff、Pyright strict、全量 pytest 与覆盖率门禁通过
8. ✅ 管理 API 按 protocol/model 返回 calibration buckets、样本数、advertised/observed prompt limits 及差异

## 工具与命令速查

### 测试

```bash
# 运行单个测试文件
pytest tests/unit/test_<module>.py -v

# 运行测试 + 覆盖率
pytest tests/unit/test_<module>.py -v --cov=app.<module> --cov-report=term-missing

# 运行全量单元测试
pytest tests/unit/ -v

# 运行全量测试（含集成与验收）
pytest tests/ -v

# 生成 HTML 覆盖率报告
pytest tests/unit/ --cov=app --cov-report=html
```

### 类型检查

```bash
# 检查单个模块
pyright src/app/<module>/

# 检查整个 src/
pyright src/

# 检查 tests/
pyright tests/
```

### Lint

```bash
# 检查单个模块
ruff check src/app/<module>/

# 检查整个项目
ruff check src/ tests/

# 自动修复
ruff check src/ tests/ --fix
```

### 代码搜索

```bash
# 搜索代码中的引用
grep -r "auto_truncate" src/ tests/ --include="*.py"

# 搜索文档中的引用
grep -r "server-tool" docs/ --include="*.md"

# 精确搜索已删除的 server-tool 支持符号；不要要求保真模型或 breaking-removal 测试中的字面量归零
grep -rE "server_tool_filter|filter_server_tool_blocks|serverToolDowngrade|serverTools" src/ tests/ --include="*.py"
```

## 沟通与反馈

### 何时请求澄清

- Spec 与现有代码冲突时（优先 spec，但需确认）
- 测试场景不明确时
- 性能优化与正确性冲突时（优先正确性，但需讨论）
- 发现 spec 遗漏的边界条件时

### 何时报告阻塞

- 依赖的上游模块不存在或接口不匹配
- 现有测试大面积失败且不清楚原因
- 类型检查错误无法合理修复（可能是 spec 设计问题）
- 发现 spec 中的内在矛盾

### 何时提出改进建议

- 发现更简洁的实现方式（不改变语义）
- 发现可合并的重复逻辑
- 发现性能优化机会（不破坏正确性）
- 发现测试覆盖盲点

## 开始实施

1. **克隆或切换到工作分支**：
   ```bash
   git checkout -b feat/hooks-tokenization-rewrite
   ```

2. **阅读完整 spec**：
   ```bash
   cat docs/2604-rewrite/hooks-tokenization-spec.md
   ```

3. **阅读完整实施计划**：
   ```bash
   cat docs/2604-rewrite/plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md
   ```

4. **开始阶段 0**：
   ```bash
   # 创建测试文件
   touch tests/unit/test_tool_pair_regression.py
   touch tests/unit/test_tokenization_regression.py
   
   # 编写红测试
   # ...
   ```

5. **逐阶段推进**，每阶段完成后提交 commit

6. **最终验收（阶段 10）**，确保所有门禁通过

---

**祝实施顺利！遇到问题随时反馈。**
