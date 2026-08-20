# Hooks、Tokenization 与协议修复实施计划

> **状态：历史实施记录，已执行且非规范；禁止重放。**
> 日期：2026-07-17  
> Current oracle：[Hooks 规格](../hooks-tokenization-spec.md)、[Hooks 机制](../hooks-system.md)与[Tool Use 机制](../tool-use.md)。正文记录当时的迁移设计，不得据此恢复跨协议 `builtin:tool_preprocessor` payload hook；该名称当前仅是兼容禁用键，ordinary tool 的 wire adaptation只在 direct Messages leg执行。

## 概述

本计划将规格说明中的所有验收要求转化为可执行的 TDD 阶段。每阶段遵循「先写失败测试 → 实现 → 转绿 → 清理」循环，确保代码质量、类型安全与协议正确性。

**核心原则**：

- 长期正确优于短期速度——KV cache 保真、协议官方约束、错误显式
- TDD 驱动——每阶段从红测试开始，实现转绿，覆盖率门禁
- 增量交付——每阶段独立可测、可审、可合并
- 零破坏性——不要求 reset/clean 工作树，兼容现有修改

---

## 阶段 0：前置准备与探针

**目标**：建立测试基础设施、理解现有代码、记录待删除与待迁移的代码清单。

### 涉及文件

- `tests/unit/test_tool_pair_regression.py` (新建)
- `tests/unit/test_tokenization_regression.py` (新建)
- `docs/2604-rewrite/plan/PHASE0_CODE_INVENTORY.md` (新建)

### 回归 oracle（预期为绿，属于 TDD 前置例外）

本阶段只捕获现状中应保留的合法行为，不是功能实现的红测试。阶段 1 起恢复严格的红→绿循环；所有用于证明旧缺陷的新用例必须先在旧实现上失败。

1. **Tool pair regression 探针**（`test_tool_pair_regression.py`）：
   - 编写覆盖当前所有已知合法 pair 场景的回归测试套件（作为后续重写的 oracle）
   - 测试场景：简单相邻配对、并行完整工具对、name casing、合法 mixed-content 消息
   - 预期：当前实现通过这些测试（绿）
   - 目的：确保重写后不丢失现有合法行为

2. **Tokenization 基准**（`test_tokenization_regression.py`）：
   - 记录当前 `estimate_input_tokens()` 对典型请求的估算值
   - 不同尺寸 buckets（<15k, 15k-30k, 30k-60k, 60k-120k, 120k-240k, >240k）各 2-3 个样本
   - 预期：当前实现通过（绿）
   - 目的：迁移后验证估算器输出稳定性

### 实施步骤

1. 创建 `tests/unit/test_tool_pair_regression.py`，复制现有 `test_anthropic_sanitize.py` 中的合法配对测试，并扩展：
   - 并行工具调用（多个 tool_use/result pair）
   - 混合内容消息（tool + text）
   - Name casing 修正
   
2. 创建 `test_tokenization_regression.py`，调用现有 `estimate_input_tokens()` 并记录基准值

3. 创建 `docs/2604-rewrite/plan/PHASE0_CODE_INVENTORY.md`，列出：
   - **待删除**：`src/app/auto_truncate/`、`src/app/anthropic/server_tool_filter.py`、`tests/unit/test_auto_truncate.py`、对应 server-tool filter tests
   - **待迁移**：`src/app/anthropic/token_counting.py` → `src/app/tokenization/`
   - **待重写**：`src/app/anthropic/sanitize/tool_blocks.py`（当前全局集合算法 → 局部相邻算法）
   - **待改为可选 hook**：`src/app/anthropic/sanitize/deduplicate_tool_calls.py`
   - **待增强**：现有 thinking destack、strip read tool result tags、tool preprocessor

4. 运行 `pytest tests/unit/test_tool_pair_regression.py tests/unit/test_tokenization_regression.py -v`

### 验收

- [ ] Regression tests 全绿（确认当前实现的合法行为基线）
- [ ] Code inventory 文档完整列出所有待删除/迁移/重写的文件
- [ ] 无破坏性——现有工作树状态不变

### 风险

- 现有 tool pair 实现可能有未发现的 edge case，需要在后续阶段通过新增测试覆盖

---

## 阶段 1：Tool Pair/Orphan Repair 算法重写

**目标**：用局部相邻算法替换全局集合算法，满足 Anthropic 官方约束（immediate-follow、result-first、幂等）。

### 涉及文件

- `src/app/anthropic/sanitize/tool_blocks.py` (重写)
- `tests/unit/test_anthropic_tool_pair_repair.py` (新建)
- `tests/unit/test_tool_pair_regression.py` (已有，必须保持绿)

### 测试（红）

1. **Adjacent-only pairing**：
   - Assistant tool_use 后紧跟 user tool_result → 保留
   - Assistant tool_use 后非紧邻的 user tool_result → 删除双方（orphan）
   - 验证只有 immediate-follow 的 result 才配对

2. **Parallel tool calls**：
   - 单个 assistant 消息含多个 tool_use，紧随 user 消息含对应多个 result → 全保留
   - 部分 result 缺失 → 只删除缺失的 pair，保留完整 pair

3. **Duplicate ID handling**：
   - 同一 assistant 消息内重复 ID → 保留首次出现的 use，后续删除（含其 result）
   - 跨轮重复 ID → 保留首次轮次的 pair，后续轮次的同名 ID pair 删除
   - 单个 user 消息内同 ID 多个 result → 保留首次 result

4. **Reversed blocks (result-first)**：
   - User 消息内 tool_result 不在最前 → 移动到 content 数组首部
   - 混合消息（text + tool_result）→ result 排序到前面，text 保持相对顺序
   - 验证算法保持 text/image/document blocks 相对顺序

5. **Cross-round ID collision**：
   - Round 1: assistant tool_use id=A → user result A
   - Round 2: assistant tool_use id=A → user result A
   - 预期：只保留 Round 1 的 pair，Round 2 的 pair 删除（优先保持旧前缀）

6. **Mixed-content messages**：
   - User 消息：`[text, tool_result, image]` → `[tool_result, text, image]`
   - Assistant 消息：`[tool_use, text]` 但 result 缺失 → 删除 tool_use，保留 text
   - 验证非工具 blocks 不受影响

7. **Idempotence**：
   - 运行算法两次，第二次不应有任何改变（零修复计数）
   - 验证算法是纯函数，不依赖历史状态

8. **Empty message removal**：
   - 删除所有 blocks 后的消息 → 整条消息移除
   - 混合消息删除工具部分 → 保留非工具内容

9. **Name casing**：
   - Tool definition: `TestTool`，use: `testtool` → 修正为 `TestTool`
   - 空 tools 数组 → 跳过 casing 修正
   - 保留但未在 tools 中的 use → 保持原 name

### 实施步骤

1. 在 `tests/unit/test_anthropic_tool_pair_repair.py` 编写上述 9 类红测试

2. 重写 `src/app/anthropic/sanitize/tool_blocks.py`：
   - 新函数签名保持不变：`process_tool_blocks(messages, tools) -> (cleaned, orphan_uses, orphan_results, names_fixed)`
   - 实现局部相邻算法：
     - 维护全局已见 `tool_use.id` 集合（检测重复）
     - 顺序扫描 messages
     - Assistant 消息：收集 tool_use IDs，标记重复
     - 紧随 user 消息：收集 tool_result IDs，标记重复，做局部交集
     - 删除孤儿 blocks
     - 移动 result 到 content 数组首部
     - Casing 修正
     - 清理空消息
   - 确保幂等性（第二次运行零改变）

3. 运行测试：`pytest tests/unit/test_anthropic_tool_pair_repair.py -v`，转绿

4. 运行回归测试：`pytest tests/unit/test_tool_pair_regression.py -v`，确保现有合法行为不破坏

5. 类型检查：`pyright src/app/anthropic/sanitize/tool_blocks.py`

### 验收

- [ ] 所有新测试绿
- [ ] 回归测试保持绿（现有合法行为不变）
- [ ] Pyright strict 零错误
- [ ] 覆盖率 ≥95%（`pytest --cov=app.anthropic.sanitize.tool_blocks --cov-report=term-missing`）

### 风险

- 局部算法的边界条件可能比全局算法复杂，需要充分的测试覆盖
- 若现有测试依赖旧算法的副作用（如跨轮假配对），需调整测试而非算法

---

## 阶段 2：删除 Auto-Truncate 与 Server-Tool Support

**目标**：移除代理侧历史改写机制，迁移保留的 token counting 能力到新模块。

### 涉及文件

- `src/app/auto_truncate/` (删除整个目录)
- `tests/unit/test_auto_truncate.py` (删除)
- `src/app/anthropic/server_tool_filter.py` (删除)
- `tests/unit/test_anthropic_server_tool_filter.py` (删除，如果存在)
- `src/app/anthropic/feature_negotiation.py` (修改，移除 serverTools 相关)
- `src/app/tokenization/` (新建目录)
- `src/app/tokenization/estimators.py` (新建，迁移 token estimation)
- `tests/unit/test_tokenization_estimators.py` (新建)

### 测试（红）

1. **Estimator 迁移验证**（`test_tokenization_estimators.py`）：
   - `test_estimate_anthropic_input_matches_baseline()`：对比新旧实现输出一致性（使用阶段 0 的基准）
   - `test_estimate_anthropic_excludes_thinking()`：验证 assistant thinking blocks 被排除
   - `test_estimate_gemini_input_basic()`：Gemini 协议估算（基础版本）
   - `test_offload_threshold()`：验证大请求 offload 到线程池

2. **依赖清理验证**：
   - `test_no_auto_truncate_imports()`：grep 代码库，确保无 `from app.auto_truncate` 或 `import auto_truncate`
   - `test_no_server_tool_support_symbols()`：精确检查 `server_tool_filter`、`filter_server_tool_blocks`、`serverTools`、`serverToolDowngrade` 等已删除支持面；不得要求通用保真模型、错误透传或 breaking-removal 测试中的 `server_tool_use` 字面量全局归零

3. **Feature negotiation 更新**：
   - `test_feature_negotiation_ignores_unknown_categories()`：解析包含未知类别的响应，不因 serverTools 失败

### 实施步骤

1. 创建 `src/app/tokenization/` 目录与 `__init__.py`

2. 创建 `src/app/tokenization/estimators.py`，迁移实现：
   - 从 `src/app/anthropic/token_counting.py` 迁移 `estimate_input_tokens()` → `estimate_anthropic_input()`
   - 新增 `estimate_gemini_input()` 占位符（基础实现）
   - 保留 `preload_tokenizer()` 与 `_content_for_count()` 辅助函数
   - 添加类型注解与文档字符串

3. 编写 `tests/unit/test_tokenization_estimators.py`，验证迁移正确性

4. 使用精确路径删除文件，不使用通配符或 `find -delete`：
   - 删除 `src/app/auto_truncate/__init__.py`、`engine.py`、`token_limits.py`
   - 删除 `tests/unit/test_auto_truncate.py`
   - 删除 `src/app/anthropic/server_tool_filter.py`
   - 从 `tests/unit/test_anthropic_tools.py` 中只移除 server-tool filter 对应用例；保留同文件中的其他测试

5. 更新 `src/app/anthropic/feature_negotiation.py` 中解析逻辑：
   - 移除 `serverTools` 与 `serverToolDowngrade` 类别枚举值
   - 修改解析器：遇到未知类别时忽略并保留其他已知类别，不失败

6. 全局搜索替换引用：
   ```bash
   # 替换所有 import
   grep -r "from app.anthropic.token_counting import" src/ tests/ --include="*.py"
   # 手动更新为：from app.tokenization.estimators import
   ```

7. 更新 `src/app/runtime.py` 与 `src/app/deps.py` 中 TokenCounter 初始化引用

8. 运行测试：`pytest tests/unit/test_tokenization_estimators.py -v`

9. 全量测试：`pytest tests/unit/ -v`，确保无破坏

### 验收

- [ ] `src/app/auto_truncate/` 目录不存在
- [ ] `test_auto_truncate.py` 不存在
- [ ] `server_tool_filter.py` 不存在
- [ ] 代码库中无 `auto_truncate`、`server_tool_use`、`server_tool_result` 引用（排除文档）
- [ ] Estimator 测试全绿，输出与旧实现一致
- [ ] Feature negotiation 测试通过（忽略未知类别）
- [ ] Pyright strict 零错误
- [ ] 全量单元测试绿

### 风险

- 若其他模块依赖 auto_truncate 的副作用（如 token limit cache），需要识别并迁移或重构
- server-tool 残留可能存在于历史数据，但按 spec 有意不提供降级，清晰错误即可

---

## 阶段 3：Tokenization Calibration 与 Limits Observation

**目标**：实现本地估算校准、prompt-limit 错误解析与状态存储。

### 涉及文件

- `src/app/tokenization/calibration.py` (新建)
- `src/app/tokenization/limits.py` (新建)
- `src/app/tokenization/state_store.py` (新建)
- `tests/unit/test_tokenization_calibration.py` (新建)
- `tests/unit/test_tokenization_limits.py` (新建)
- `tests/unit/test_tokenization_state_store.py` (新建)

### 测试（红）

#### Calibration 测试

1. **Size bucket 分配**：
   - `test_bucket_boundaries()`：验证 [0, 15k), [15k, 30k), ..., [240k, +∞) 边界正确
   - `test_bucket_assignment()`：不同估算值分配到正确 bucket

2. **Factor 计算**：
   - `test_factor_no_samples()`：无样本时 factor = 1.0
   - `test_factor_single_bucket()`：单 bucket 样本计算 `sum_real / sum_estimated`
   - `test_factor_clamp()`：factor 被限制在 [0.5, 3.0]
   - `test_factor_interpolation()`：跨 bucket 插值（log-linear）

3. **有界滑动权重**：
   - `test_weight_cap()`：单 bucket 样本超过 WEIGHT_CAP=2000 时，老样本被衰减
   - `test_sample_count_capped()`：验证 `sample_count` 不无限增长

4. **Protocol + Model 分离**：
   - `test_protocol_isolation()`：anthropic/gemini 样本不互相污染
   - `test_model_normalization()`：模型名规范化（复用 `normalize_for_matching()`）

#### Limits Observation 测试

1. **Error 解析**：
   - `test_parse_anthropic_prompt_limit_error_format1()`：`"prompt token count of 150000 exceeds the limit of 100000"`
   - `test_parse_anthropic_prompt_limit_error_format2()`：`"prompt is too long: 150000 tokens > 100000 maximum"`
   - `test_parse_structured_error()`：`{"error": {"message": "..."}}`
   - `test_ignore_non_limit_400()`：其他 400 错误不解析为 limit 错误

2. **Observation 记录**：
   - `test_record_observation()`：成功解析后记录 `observed_limit`、`observed_input_tokens`、`source`、`observed_at`、`observation_count`
   - `test_observation_count_increment()`：重复观测同一 model/protocol 累加计数
   - `test_advertised_vs_observed()`：catalog `max_prompt_tokens` 与观测值独立存在

#### State Store 测试

1. **生命周期**：
   - `test_runtime_owns_one_state_store()`：每个应用 `RuntimeState` 持有一个 store，不使用跨 app 的进程全局 singleton
   - `test_dirty_flag()`：学习后标记 dirty，flush 后清除

2. **序列化**：
   - `test_state_serialization()`：JSON 序列化/反序列化保持数据完整
   - `test_versioned_schema()`：包含 schema 版本号
   - `test_corrupted_file_recovery()`：损坏文件告警后从空状态启动

3. **Flush 策略**：
   - `test_periodic_flush()`：周期性 writer 按固定间隔 flush
   - `test_shutdown_flush()`：关闭时最终 flush
   - `test_flush_serialization()`：所有 flush 通过 async lock 串行化
   - `test_flush_failure_resilience()`：写失败告警但不改变请求结果，dirty 保留

4. **Atomic replace**：
   - `test_atomic_write()`：写入临时文件 → atomic rename
   - `test_concurrent_read_during_write()`：写入期间读不阻塞（读旧版本或新版本，无部分写）

### 实施步骤

1. 创建 `src/app/tokenization/calibration.py`：
   - `CalibrationBucket` dataclass：`sum_real`、`sum_estimated`、`sample_count`、`mean_estimated`
   - `CalibrationModel` dataclass：按 protocol+model 保存 buckets
   - `CalibrationEngine`：`learn(protocol, model, estimate, real)`、`calibrate(protocol, model, estimate) -> calibrated`
   - Bucket 边界常量、clamp 常量、weight cap 常量

2. 创建 `src/app/tokenization/limits.py`：
   - `PromptLimitError` dataclass：`observed_limit`、`observed_input_tokens`、`source`、`observed_at`、`observation_count`
   - `parse_prompt_limit_error(text, protocol, endpoint) -> PromptLimitError | None`
   - `PromptLimitRegistry`：记录与查询

3. 创建 `src/app/tokenization/state_store.py`：
   - `TokenizationStateStore` 应用生命周期单例，由 `RuntimeState` 持有，不实现进程全局 singleton accessor
   - `State` dataclass：calibration models、prompt limit observations、schema version
   - `load_state(path) -> State`
   - `save_state(state, path)`（atomic replace）
   - `run_periodic_flush(interval)`（由 lifespan task group 启动的异步任务）
   - `flush()`（周期与 shutdown 共用，同一 async lock 串行化）

4. 接入 `src/app/runtime.py` 与 `src/app/server.py`：
   - `RuntimeState` 增加 `tokenization_state` 字段
   - lifespan 启动时先 load，再启动 periodic flush
   - finally 中必须在关闭 upstream、取消 task group 之前执行最终 `await tokenization_state.flush()`；推荐顺序为拒绝 pending approvals → flush tokenization → close history → close upstream → cancel task group

5. 编写测试并转绿

6. 类型检查：`pyright src/app/tokenization/`

### 验收

- [ ] Calibration 测试全绿，覆盖率 ≥95%
- [ ] Limits 解析测试全绿，覆盖两种消息格式
- [ ] State store 测试全绿，验证并发安全与恢复能力
- [ ] Pyright strict 零错误

### 风险

- State store 的并发控制需要仔细设计，避免 flush 竞态
- Atomic replace 在某些文件系统上可能需要特殊处理（如 Windows）

---

## 阶段 4：Hooks 类型系统与 Registry

**目标**：建立强类型 hooks 框架，支持 PayloadHook、RetryStrategyFactory、ResponseHook、ObserverHook 四类。

### 涉及文件

- `src/app/hooks/` (新建目录)
- `src/app/hooks/types.py` (新建)
- `src/app/hooks/registry.py` (新建)
- `src/app/hooks/context.py` (新建)
- `src/app/hooks/loader.py` (新建)
- `src/app/config/settings.py` (修改，增加 HooksConfig)
- `src/app/runtime.py` (修改，持有不可变 registry)
- `tests/unit/test_hooks_registry.py` (新建)
- `tests/unit/test_hooks_loader.py` (新建)

### 测试（红）

#### Registry 测试

1. **Builder 可变性**：
   - `test_builder_mutable_registry_immutable()`：Builder 可变，build() 后的 Registry 不可变
   - `test_registry_frozen()`：Registry 快照冻结，不可修改

2. **注册与顺序**：
   - `test_register_payload_hook()`：注册 payload hook，按 order 排序
   - `test_builtin_namespace_reserved()`：用户 hook 不得使用 `builtin:*` 前缀
   - `test_user_order_constraint()`：用户 hook order 必须 ≥1000
   - `test_duplicate_name_rejected()`：重复 name 注册冲突，启动失败

3. **禁用**：
   - `test_disabled_hook_excluded()`：`hooks.disabled` 中的 hook 在 build() 时排除
   - `test_mandatory_hook_not_disableable()`：尝试禁用 mandatory hook 失败（或忽略）

4. **四类 hook 注册**：
   - `test_register_all_hook_types()`：PayloadHook、RetryStrategyFactory、ResponseHook、ObserverHook 各注册一个
   - `test_query_by_phase()`：查询 `pre_sanitize` / `post_sanitize` / `pre_send` 的 hooks

#### Loader 测试

1. **Module 加载**：
   - `test_load_user_module()`：从 `hooks.modules` 加载 Python module，调用 `register(builder, settings)`
   - `test_module_import_failure()`：module 不存在时启动失败，不静默跳过
   - `test_module_missing_register()`：module 缺少 `register()` 函数时失败
   - `test_module_register_conflict()`：module 注册冲突名称时失败

2. **可信模块警告**：
   - `test_user_module_executes_with_process_permission()`：文档警告用户模块与代理同权限执行

#### Context 测试

1. **Frozen snapshot**：
   - `test_hook_context_frozen()`：HookContext 是 frozen dataclass，不可修改
   - `test_hook_context_contains_request_id()`：包含 request_id、endpoint、protocol、model 等只读字段
   - `test_hook_context_attempt_number()`：pre_send phase 包含 attempt_number

2. **无暗通状态**：
   - `test_no_mutable_extra_field()`：不通过可变 `extra` 字段在 hooks 间传递状态

### 实施步骤

1. 在 `src/app/config/settings.py` 新增 frozen `HooksConfig`：
   - `modules: list[str] = Field(default_factory=list)`
   - `disabled: list[str] = Field(default_factory=list)`
   - `timeout_ms: int = Field(default=5000, ge=1)`
   - `AppSettings.hooks: HooksConfig = Field(default_factory=HooksConfig)`
   - 补 YAML/env 四层配置与 frozen/extra-forbid 回归测试

2. 创建 `src/app/hooks/types.py`：
   - `PayloadPhase` 枚举：`pre_sanitize`、`post_sanitize`、`pre_send`
   - `HookErrorMode` 枚举：`fail_request`、`continue`
   - `PayloadHook` Protocol
   - `RetryStrategyFactory` Protocol
   - `ResponseHook` Protocol
   - `ObserverHook` Protocol

3. 创建 `src/app/hooks/context.py`：
   - `HookContext` frozen dataclass：request_id、endpoint、protocol、original_model、resolved_model、session、agent、attempt_number、settings（只读）

4. 创建 `src/app/hooks/registry.py`：
   - `HookRegistryBuilder`（可变）：`register_payload_hook()`、`register_retry_factory()`、`register_response_hook()`、`register_observer()`、`build()`
   - `HookRegistry`（不可变）：查询方法 `get_payload_hooks(phase)`、`get_retry_factories()`、`get_response_hooks()`、`get_observers()`
   - 内建 hooks 命名空间验证
   - Order 排序与去重逻辑

5. 创建 `src/app/hooks/loader.py`：
   - `load_user_modules(builder, settings)`：从 `settings.hooks.modules` 加载并调用 `register()`
   - 错误处理：import 失败、缺少 register、注册冲突

6. 编写测试并转绿

7. 集成到 `RuntimeState`：
   - 新增字段：`hook_registry: HookRegistry | None`
   - 在 lifespan 启动时构建 registry

8. 类型检查：`pyright src/app/hooks/`

### 验收

- [ ] Registry 测试全绿，验证可变/不可变边界
- [ ] Loader 测试全绿，验证模块加载与错误处理
- [ ] Context 测试全绿，验证 frozen 与只读
- [ ] Pyright strict 零错误
- [ ] 覆盖率 ≥95%

### 风险

- 用户模块加载的安全性完全依赖用户，需清晰文档说明
- 错误处理需要区分"用户错误"与"代理 bug"

---

## 阶段 5：Built-in Hooks 实现与集成

**目标**：将现有 sanitizer、destack、thinking 等实现改造为 built-in hooks，并集成到请求管道。

### 涉及文件

- `src/app/hooks/builtin/` (新建目录)
- `src/app/hooks/builtin/strip_read_tool_result_tags.py` (新建)
- `src/app/hooks/builtin/thinking_destack.py` (新建)
- `src/app/hooks/builtin/tool_preprocessor.py` (新建)
- `src/app/hooks/builtin/deduplicate_tool_calls.py` (新建，可选，默认关闭)
- `src/app/hooks/builtin/poisoned_thinking.py` (新建)
- `src/app/hooks/builtin/token_calibration.py` (新建)
- `tests/unit/test_builtin_hooks.py` (新建)

### 测试（红）

1. **Strip read tool result tags**：
   - `test_strip_read_result_tags_basic()`：移除 `<system-reminder>` 标签
   - `test_enabled_by_default()`：作为常规 built-in 注册；只有显式列入 `hooks.disabled` 才关闭

2. **Thinking destack**：
   - `test_thinking_destack_separates_adjacent_blocks()`：按配置插入 text separator 或移动既有非 thinking blocks，绝不删除 thinking 内容
   - `test_thinking_destack_preserves_non_adjacent_content()`：无相邻 thinking 时保持内容等价

3. **Tool preprocessor**：
   - `test_tool_preprocessor_inject_tool_search_regex()`：注入 `tool_search_tool_regex`
   - `test_tool_preprocessor_set_defer_loading()`：为非白名单工具设置 `defer_loading`
   - `test_tool_preprocessor_preserves_unknown_fields()`：保持未知字段
   - `test_tool_preprocessor_ignores_server_tools()`：不处理 server tools（已删除）

4. **Deduplicate tool calls (可选)**：
   - `test_deduplicate_tool_calls_disabled_by_default()`：默认关闭
   - `test_deduplicate_tool_calls_preserves_blocks()`：启用时保留 blocks，不删除整条消息
   - `test_deduplicate_tool_calls_signature_based()`：基于 name/input/result 签名去重

5. **Poisoned thinking (retry factory)**：
   - `test_poisoned_thinking_retry_strategy()`：检测 poisoned thinking 模式并重试
   - `test_poisoned_thinking_per_request_state()`：每请求独立 strategy 实例

6. **Token calibration observers**：
   - `test_token_calibration_success_observer()`：completion 成功时学习
   - `test_token_calibration_failure_observer()`：token-limit 400 时学习
   - `test_observer_isolated_on_error()`：observer 异常不影响请求结果
   - `test_nonstream_usage_tap_is_body_preserving()`：解析完整 JSON usage，但向客户端返回的 bytes 不变
   - `test_stream_usage_tap_is_byte_preserving()`：旁路解析 SSE `message_delta.usage`，输出 chunks 逐字节不变且保持背压

### 实施步骤

1. 迁移现有实现到 built-in hooks：
   - `strip_read_tool_result_tags`：从 `anthropic/sanitize/read_tool_result_tags.py` 迁移；当前未接生产路径，本阶段首次作为默认 built-in 接线
   - `thinking_destack`：从 `anthropic/thinking/` 迁移；当前已由 `request_preparation.py` 调用，必须保持行为等价
   - `tool_preprocessor`：从 `message_tools.py` 迁移；当前已由 `request_preparation.py` 调用，必须保持行为等价
   - `deduplicate_tool_calls`：从 `anthropic/sanitize/deduplicate_tool_calls.py` 改造为 block-preserving

2. 实现新 built-in hooks：
   - `poisoned_thinking.py`：RetryStrategyFactory，检测 poisoned pattern
   - `token_calibration.py`：两个 ObserverHooks（success / failure）

3. 实现只读 usage tap，而不是 streaming transform hook：
   - 非流式响应在返回原始 bytes 前解析一份 JSON usage 快照
   - 流式响应复用现有 SSE parser/accumulator 能力做 byte-preserving tee，只观察 `message_delta.usage` 与终态；不得重编码、合并或延迟原始 chunks
   - usage snapshot 作为结构化 observer event data 传给 success observer；解析失败只告警，不影响透传

4. 每个 built-in hook 包含：
   - Hook 实现（符合对应 Protocol）
   - 注册函数（`register(builder, settings)`）
   - Order 常量（0-999 范围）
   - 默认启用/禁用配置

5. 编写测试并转绿

6. 集成到 `hooks/builtin/__init__.py`：
   - `register_all_builtin_hooks(builder, settings)`

7. 在 lifespan 启动时调用 `register_all_builtin_hooks()`

8. 类型检查：`pyright src/app/hooks/builtin/`

### 验收

- [ ] 所有 built-in hooks 测试绿
- [ ] Built-in hooks 按正确 order 注册
- [ ] 只有 deduplicate 默认关闭；strip tags、destack 与 tool preprocessor 默认启用
- [ ] Observers 故障隔离测试通过
- [ ] Pyright strict 零错误
- [ ] 覆盖率 ≥95%

### 风险

- 迁移现有实现时需确保行为等价，使用回归测试验证
- Observer 隔离需要正确的异常处理与超时机制

---

## 阶段 6：Tokenization Service 与 Count Tokens Endpoint

**目标**：实现 Anthropic count_tokens 上游优先/本地 fallback 服务，集成 calibration 学习。

### 涉及文件

- `src/app/tokenization/service.py` (新建)
- `src/app/routes/anthropic.py` (修改，更新 count_tokens endpoint)
- `tests/unit/test_tokenization_service.py` (新建)
- `tests/http/test_anthropic_count_tokens.py` (新建)

### 测试（红）

#### Unit 测试

1. **Upstream 优先**：
   - `test_count_tokens_upstream_success()`：上游成功时返回精确结果
   - `test_count_tokens_upstream_failure_fallback()`：上游失败时 fallback 到本地估算
   - `test_count_tokens_upstream_disabled()`：禁用时直接本地估算

2. **Calibration 学习**：
   - `test_count_tokens_learns_from_upstream()`：上游成功时用精确值学习 calibration
   - `test_count_tokens_fallback_uses_calibration()`：fallback 时使用 calibrated 值
   - `test_estimate_and_real_use_same_estimator()`：学习与消费使用同一 `estimate_anthropic_input()`

3. **Thinking 排除**：
   - `test_count_tokens_excludes_assistant_thinking()`：估算排除 assistant thinking blocks

#### HTTP 测试

1. **Endpoint 行为**：
   - `test_count_tokens_endpoint_success()`：成功请求返回 200 + `{"input_tokens": N}`
   - `test_count_tokens_endpoint_upstream_down()`：上游不可达时返回估算值 + `{"estimated": true}`
   - `test_count_tokens_endpoint_validation()`：无效请求返回 422

### 实施步骤

1. 创建 `src/app/tokenization/service.py`：
   - `AnthropicTokenCountingService` 类
   - `count(request: MessagesRequest) -> dict[str, Any]`
   - 逻辑：上游优先 → 学习 → fallback 本地估算 → 应用 calibration

2. 更新 `src/app/routes/anthropic.py`：
   - 替换旧 `TokenCounter` 为新 `AnthropicTokenCountingService`
   - 注入依赖：`TokenizationStateStore`、`CalibrationEngine`

3. 编写测试并转绿

4. HTTP 测试：启动测试服务器，验证 endpoint 行为

5. 类型检查：`pyright src/app/tokenization/service.py`

### 验收

- [ ] Unit 测试全绿，验证学习与 fallback 逻辑
- [ ] HTTP 测试全绿，验证 endpoint 正确性
- [ ] 上游成功时学习样本，fallback 时消费 calibration
- [ ] Pyright strict 零错误
- [ ] 覆盖率 ≥95%

### 风险

- 上游 API 变化可能导致解析失败，需要健壮的错误处理
- Calibration 学习的样本质量依赖上游精确性

---

## 阶段 7：管理 API 与状态暴露

**目标**：暴露 tokenization 状态（calibration buckets、prompt limits）的只读管理 API。

### 涉及文件

- `src/app/routes/management.py` (扩展现有管理路由)
- `tests/http/test_admin_tokenization.py` (新建)

### 测试（红）

1. **Calibration 状态查询**：
   - `test_get_calibration_state()`：返回所有 protocol/model 的 buckets、factor、样本数
   - `test_calibration_state_empty_on_startup()`：启动时无样本返回空状态

2. **Prompt limit 查询**：
   - `test_get_prompt_limits()`：返回 advertised 与 observed limits
   - `test_prompt_limit_diff()`：高亮 advertised vs observed 差异
   - `test_prompt_limit_observation_count()`：显示观测次数与最后观测时间

3. **按 protocol/model 过滤**：
   - `test_filter_by_protocol()`：只返回指定 protocol 的状态
   - `test_filter_by_model()`：只返回指定 model 的状态

### 实施步骤

1. 扩展 `src/app/routes/management.py`，保持项目现有 `/api/*` 约定：
   - `GET /api/tokenization/calibration` - 返回 calibration 状态
   - `GET /api/tokenization/limits` - 返回 prompt limits 状态
   - 支持查询参数：`protocol`、`model`

2. 响应格式：
   ```json
   {
     "calibration": {
       "anthropic:claude-sonnet-3.5": {
         "buckets": [
           {"range": "[0, 15000)", "factor": 1.05, "samples": 42, "mean_estimated": 8500},
           ...
         ]
       }
     },
     "limits": {
       "anthropic:claude-sonnet-3.5": {
         "advertised_limit": 200000,
         "observed_limit": 180000,
         "observed_input_tokens": 180500,
         "diff": -20000,
         "observation_count": 3,
         "last_observed_at": "2026-07-16T10:30:00Z"
       }
     }
   }
   ```

3. 编写测试并转绿

4. 类型检查：`pyright src/app/routes/management.py`

### 验收

- [ ] HTTP 测试全绿
- [ ] 管理 API 返回正确的 calibration 与 limits 状态
- [ ] 支持按 protocol/model 过滤
- [ ] Pyright strict 零错误

### 风险

- 管理 API 需要适当的访问控制（当前版本可能无认证，需文档说明）

---

## 阶段 8：Hook 调用集成到请求管道

**目标**：将 hooks 集成到实际请求管道中，按正确 phase 调用，记录 telemetry。

### 涉及文件

- `src/app/pipeline/hooks_executor.py` (新建)
- `src/app/anthropic/client.py` (修改，集成 hooks)
- `src/app/pipeline/executor.py` (修改，attempt/retry/observer 接线)
- `tests/unit/test_hooks_executor.py` (新建)
- `tests/integration/test_hooks_pipeline.py` (新建)

### 测试（红）

#### Executor 测试

1. **Phase 调用顺序**：
   - `test_payload_hooks_called_in_order()`：按 order 顺序调用 payload hooks
   - `test_pre_sanitize_before_mandatory()`：`pre_sanitize` 在 mandatory sanitizer 之前
   - `test_post_sanitize_after_mandatory()`：`post_sanitize` 在 mandatory sanitizer 之后
   - `test_pre_send_per_attempt()`：`pre_send` 每个 attempt 都调用

2. **错误处理**：
   - `test_payload_hook_fail_request_default()`：Payload hook 异常默认失败请求
   - `test_payload_hook_continue_on_error()`：显式 `continue` 模式隔离异常
   - `test_observer_isolated()`：Observer 异常记录 warning，不影响请求
   - `test_retry_factory_error_terminates_retry()`：Retry factory 异常终止重试决策

3. **Telemetry**：
   - `test_hook_telemetry_recorded()`：记录 name、type、phase、duration、modified、error

4. **Context 传递**：
   - `test_hook_context_frozen()`：传递给 hook 的 context 是 frozen snapshot
   - `test_hook_context_attempt_number()`：`pre_send` 的 context 包含 attempt_number

#### Integration 测试

1. **端到端 flow**：
   - `test_anthropic_request_with_hooks()`：完整 Anthropic 请求通过所有 hooks
   - `test_hooks_modify_payload()`：Hook 修改 payload，后续 hook 看到修改后的版本
   - `test_anthropic_hooks_do_not_run_for_openai()`：OpenAI 生产路径保持现状，Anthropic built-ins 不接收 OpenAI payload

2. **Retry 策略**：
   - `test_retry_strategy_modifies_payload_on_retry()`：Retry 时 payload 被 strategy 修改
   - `test_pre_send_sees_modified_payload_on_retry()`：`pre_send` 看到 retry 修改后的 payload

### 实施步骤

1. 创建 `src/app/pipeline/hooks_executor.py`：
   - `HooksExecutor` 类
   - `execute_payload_hooks(phase, payload, context, hooks) -> modified_payload`
   - `execute_retry_factories(context, factories) -> RetryStrategy`
   - `execute_response_hooks(response, context, hooks) -> modified_response`
   - `execute_observers(event, context, observers)`
   - 错误处理、超时、telemetry 记录

2. 修改 `src/app/anthropic/client.py`：
   - 在 `_prepare_request()` 中插入 `pre_sanitize` hooks
   - Mandatory sanitizer 之后插入 `post_sanitize` hooks
   - 每个 attempt 发送前插入 `pre_send` hooks
   - 注入 retry factories 到重试逻辑
   - 响应接收后调用 response hooks
   - 各关键点调用 observers

3. 修改 `src/app/pipeline/executor.py`：
   - 以现有 `PreparedAnthropicRequest` 与 `RequestContext` 承载 original/resolved model、sanitization、wire 与 headers，不假设 `request_preparation.PreparedRequest` 拥有这些字段
   - 每请求从 registry factories 创建 retry strategies
   - retry 修改 payload 后，再以递增的 `attempt_number` 运行 `pre_send`
   - 发送 response/error/finalize observer events，并保留 HistoryConsumer 的 guaranteed lifecycle

4. 首版不修改 `src/app/openai/client.py`。Registry 与 HookContext 保留 protocol 字段，但 Anthropic built-ins 只由 Anthropic executor 调度；跨协议 hooks 需另立规格。

5. 编写测试并转绿

6. 类型检查：`pyright src/app/pipeline/hooks_executor.py`

### 验收

- [ ] Executor 测试全绿，验证调用顺序与错误处理
- [ ] Integration 测试全绿，验证端到端 hook flow
- [ ] Telemetry 正确记录所有 hook 调用
- [ ] Pyright strict 零错误
- [ ] 覆盖率 ≥95%

### 风险

- 集成到现有管道可能影响性能，需要性能基准测试
- Hook 调用的错误处理需要非常小心，避免破坏请求流程

---

## 阶段 9：文档全局清理

**目标**：更新所有 live docs，移除 auto-truncate 与 server-tool 引用，添加 hooks 与 tokenization 文档。

### 涉及文件

- `docs/2604-rewrite/sanitize-pipeline.md` (更新)
- `docs/2604-rewrite/request-pipeline.md` (更新)
- `docs/2604-rewrite/tool-use.md` (更新)
- `docs/2604-rewrite/hooks-system.md` (新建)
- `docs/2604-rewrite/tokenization.md` (新建)
- `README.md` (更新)
- `docs/API.md` (更新，如果存在)

### 测试（红）

1. **Doc 一致性检查**：
   - `test_no_auto_truncate_doc_references()`：grep docs/ 确保无 auto-truncate 引用（除 archive/changelog）
   - `test_no_server_tool_doc_references()`：grep docs/ 确保无 server-tool support 引用（除说明删除的地方）
   - `test_hooks_documented()`：验证 hooks-system.md 存在且非空
   - `test_tokenization_documented()`：验证 tokenization.md 存在且非空

### 实施步骤

1. 更新 `sanitize-pipeline.md`：
   - 移除 auto-truncate 相关章节
   - 更新 tool blocks 处理描述为新算法（局部相邻）
   - 添加 hooks 集成点说明

2. 更新 `request-pipeline.md`：
   - 添加 hooks phases 调用时机图
   - 移除 auto-truncate retry 流程

3. 更新 `tool-use.md`：
   - 移除 server-tool 支持说明
   - 更新 tool preprocessor 为 hook

4. 创建 `hooks-system.md`：
   - 概述四类 hooks
   - Payload phases 与调用时机
   - Registry builder 使用
   - 用户模块加载
   - Built-in hooks 列表
   - 错误处理与超时
   - 安全警告（用户模块同权限执行）

5. 创建 `tokenization.md`：
   - Estimators（anthropic/gemini）
   - Calibration 原理与数据模型
   - Prompt limits observation
   - State store 生命周期
   - Count tokens endpoint 行为
   - 管理 API 使用

6. 更新 `README.md`：
   - 移除 auto-truncate 特性
   - 添加 hooks 与 tokenization 简介

7. 运行 doc 测试：`pytest tests/unit/test_documentation.py -v`

### 验收

- [ ] 所有 live docs 不含 auto-truncate 与 server-tool 引用（除明确说明删除的地方）
- [ ] hooks-system.md 与 tokenization.md 完整且准确
- [ ] README 与 API 文档同步更新
- [ ] Doc 测试全绿

### 风险

- 文档更新容易遗漏，需要系统性 grep 检查

---

## 阶段 10：完整测试套件与验收

**目标**：运行全量测试、覆盖率检查、类型检查、黑盒验收测试，确保所有验收标准通过。

### 涉及文件

- 所有已修改/新建的代码与测试文件
- `tests/acceptance/` (新建目录，黑盒验收测试)

### 测试（红 → 绿）

#### 黑盒验收测试

1. **A1: Tool pair repair 全场景**：
   - Adjacent pairing
   - Parallel tools
   - Partial orphans
   - Duplicate IDs
   - Reversed blocks (result-first)
   - Cross-round IDs
   - Mixed-content messages
   - Idempotence
   - 对比阶段 0 回归测试基线

2. **A2: Token counting 全流程**：
   - Anthropic upstream 成功 → 返回精确值 → 学习 calibration
   - Anthropic upstream 失败 → fallback 本地估算 → 应用 calibration
   - Gemini 本地估算（无 calibration）
   - Prompt-limit 400 → 记录 observation → payload 不变

3. **A3: Hooks 端到端**：
   - User module 加载 → 注册成功 → 按顺序调用
   - Built-in hooks 正常工作（strip tags、destack、tool preprocessor）
   - Deduplicate hook 默认关闭，启用后生效
   - Poisoned thinking retry strategy 触发重试
   - Observer 学习 calibration（success/failure）
   - Observer 异常隔离

4. **A4: 删除验证**：
   - Auto-truncate 代码与测试完全删除
   - Server-tool 代码与测试完全删除
   - 无相关引用（除文档说明）

5. **A5: 管理 API**：
   - 查询 calibration 状态 → 返回 buckets
   - 查询 prompt limits → 返回 advertised/observed/diff
   - 按 protocol/model 过滤

### 实施步骤

1. 创建 `tests/acceptance/` 目录与黑盒测试套件

2. 编写验收测试（基于 spec 的 9 条验收标准）

3. 运行全量单元测试：
   ```bash
   pytest tests/unit/ -v --cov=app --cov-report=term-missing --cov-report=html
   ```

4. 验证覆盖率 ≥80%（关键模块 ≥95%）

5. 运行类型检查：
   ```bash
   pyright src/
   ```

6. 验证 Pyright strict 零错误

7. 运行 Ruff 检查：
   ```bash
   ruff check src/ tests/
   ```

8. 修复所有 lint 问题

9. 运行黑盒验收测试：
   ```bash
   pytest tests/acceptance/ -v
   ```

10. 启动测试服务器，手动验证关键端点：
    - POST /v1/messages - Anthropic 请求通过 hooks
    - POST /v1/messages/count_tokens - 返回精确/估算值
   - GET /api/tokenization/calibration - 返回状态
   - GET /api/tokenization/limits - 返回 limits

### 验收

- [ ] ✅ 验收标准 1：生产代码和 live docs 不再声明或引用代理侧 auto-truncate 与 server-tool support
- [ ] ✅ 验收标准 2：任意 built-in 路径都不会因 prompt 超限删除、压缩或摘要历史
- [ ] ✅ 验收标准 3：Anthropic 精确 count 成功会训练 calibration；fallback 消费对应 protocol/model factor
- [ ] ✅ 验收标准 4：Prompt-limit 400 被记录但 payload 不变，错误仍按原状态透传
- [ ] ✅ 验收标准 5：Tool pair repair 通过所有场景测试，保持现有合法 pair/casing 行为等价
- [ ] ✅ 验收标准 6：用户 hooks 可按确定顺序加载；冲突和启动错误显式失败；Observer 故障被隔离
- [ ] ✅ 验收标准 7：Ruff、Pyright strict、全量 pytest 与覆盖率门禁通过
- [ ] ✅ 验收标准 8：管理 API 按 protocol/model 返回 calibration buckets、样本数、advertised/observed prompt limits 及差异
- [ ] 全量单元测试绿（0 failures, 0 errors）
- [ ] 覆盖率 ≥80%（关键模块 ≥95%）
- [ ] Pyright strict 零错误
- [ ] Ruff 零 lint 问题
- [ ] 黑盒验收测试全绿

### 风险

- 集成测试可能发现之前单元测试未覆盖的边界条件
- 性能回归需要基准测试验证

---

## 总结与交付

### 阶段依赖图

```
阶段 0（前置准备）
    ↓
阶段 1（Tool pair repair） ─┐
阶段 2（删除/迁移）       ─┼─→ 阶段 4（Hooks 类型系统）
阶段 3（Calibration）     ─┘
    ↓
阶段 5（Built-in hooks）
    ↓
阶段 6（Tokenization service）
    ↓
阶段 7（管理 API）
    ↓
阶段 8（Hooks 管道集成）
    ↓
阶段 9（文档清理）
    ↓
阶段 10（完整验收）
```

### 关键度量

- **新增代码**：~2000-3000 行（含测试）
- **删除代码**：~500-800 行（auto_truncate、server_tool_filter 等）
- **测试覆盖率目标**：≥80%（关键模块 ≥95%）
- **预计工时**：每阶段 4-8 小时，总计 40-80 小时

### 回滚策略

每阶段独立可测、可审、可合并。若某阶段失败：

1. 保留该阶段的测试（作为待修复的 TODO）
2. 回滚该阶段的实现代码
3. 不影响前序阶段的已合并成果
4. 重新设计该阶段后继续

### 后续优化（不在本计划范围）

- 性能基准测试与优化
- Hooks 热重载（需要完整 config hot reload）
- 更多协议的 token counting 支持
- Advanced calibration 算法（adaptive bucket、time decay）
- Streaming hooks（逐事件变换）

---

## 附录：关键常量与配置

### Calibration 常量

```python
BUCKET_BOUNDARIES = [0, 15_000, 30_000, 60_000, 120_000, 240_000]
FACTOR_CLAMP_MIN = 0.5
FACTOR_CLAMP_MAX = 3.0
WEIGHT_CAP = 2000
```

### Built-in Hook Order

```python
BUILTIN_STRIP_READ_TOOL_RESULT_TAGS = 100
BUILTIN_THINKING_DESTACK = 200
BUILTIN_TOOL_PREPROCESSOR = 300
BUILTIN_DEDUPLICATE_TOOL_CALLS = 400
BUILTIN_POISONED_THINKING = 500
BUILTIN_TOKEN_CALIBRATION_SUCCESS = 600
BUILTIN_TOKEN_CALIBRATION_FAILURE = 700
```

### State Store 路径

```python
# 用户数据目录（platformdirs）
state_file_path = user_data_dir("ghc-api-proxy-py") / "tokenization_state.json"
```

---

**计划编写完成**。每阶段遵循严格的 TDD 循环，确保实施质量与可审查性。
