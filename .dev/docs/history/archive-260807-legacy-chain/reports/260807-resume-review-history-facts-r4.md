# Responses History facts 独立定向终审 R4

- **评审范围**：只读评审 `/home/xp/src/ghc-api-proxy-py-history-facts`，branch `fix/responses-history-facts`，candidate `b1df8f910c590033e83d5cafcd5e514f12bab937`，base `b91e58a29324b11840002efc53ed6f869b800c39`。定向复核 R3 唯一 major，并抽查前序 request／response facts 与 strict validator；未重建全量状态空间。
- **总体 verdict**：**可进入下一阶段。0 major，可 squash。**
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对

- 每项被采信的候选树 shell 证据均在同一次调用内验证物理 root、Git top-level 与完整 HEAD。候选测试进程还打印并断言 `app.pipeline.executor`、`app.history.consumer` 与 `app.anthropic.response_validation` 均从 `/home/xp/src/ghc-api-proxy-py-history-facts/src/` 加载，排除了共享环境解析到主树实现的假绿。
- R3 candidate `864cfa30e291768cbc7b080fce80d9be4cbf2d83` 到 R4 candidate 只修改 `src/app/pipeline/executor.py` 与 `tests/component/test_pipeline_executor.py`。`src/app/pipeline/executor.py:390-410` 现按 `coordinator.notify_success()` → `limiter.report_success()` → `ObserverEvent.RESPONSE` 排列；strategy 或 limiter 抛错会先关闭 response、调用 failure finalization 并重新抛出，尚未发布 `RESPONSE`。
- 真实 builtin success calibration observer 仅订阅 `ObserverEvent.RESPONSE`，并在 `src/app/hooks/builtin/token_calibration.py:36-65` 调用 `state.calibration.learn()`。因此 strategy／limiter 的失败窗口位于 calibration 发布点之前，不是仅靠测试替身实现“零 calibration”。
- 新增回归 `tests/component/test_pipeline_executor.py:920-948` 使用真实 `register_builtin_hooks()` 与 `TokenizationStateStore`，证明 throwing `on_success()` 时 calibration snapshot 不变、state 不 dirty、`RESPONSE` 为零，并仅发布 failure lifecycle；`tests/component/test_pipeline_executor.py:951-975` 证明正常成功顺序严格为 strategy → limiter → `RESPONSE`，且三者各一次。
- 为验证新增测试具备判别力，在 `/tmp` 一次性快照中用 R4 两条新测试运行 R3 生产实现 `864cfa30e291768cbc7b080fce80d9be4cbf2d83`。两条均按目标机制失败：一条显示 calibration 从空状态产生样本，另一条显示旧顺序为 `response` → `limiter` → `strategy`。随后精确 R4 candidate 上同两条测试通过。
- 最小相关 pytest 选择了 throwing strategy、正常成功顺序、合法最终响应 calibration、request／response facts provenance、最终成功 attempt facts 投影，以及 strict validator 的完整参数化单测文件；命令 rc=0。pytest 原始摘要为 `25 passed in 3.74s`，该数量未用第二原理交叉计数，故不把数量本身作为放行依据。候选测试前后 `git status --porcelain=v1 -z` 均为空树 SHA-256，candidate 保持 clean。
- 前序 facts 抽查：`tests/component/test_pipeline_executor.py:996-1061` 仍验证原始 request payload、typed request／response provenance 与字段语义；`tests/component/test_pipeline_executor.py:1064-1109` 仍验证重试后只投影最终成功 attempt 的 facts。两条均在上述最小集通过。
- strict validator 抽查：`src/app/anthropic/response_validation.py:10-46` 仍要求显式 `type=message`、`role=assistant`，通过 Anthropic SDK `Message` 校验，并逐 block 拒绝类型不兼容字段；`tests/unit/test_anthropic_response_validation.py:24-135` 的合法 SDK blocks 与非法 wire 参数化用例均在上述最小集通过。

### 第一人称执行

- **throwing strategy／`on_success()` 失败**：最终响应先完成 response hook、strict validation 与 facts 填充；进入 success callback 后，strategy 抛错立即走 failure finalization。此时 limiter 尚未执行，`RESPONSE` observer 尚未发布，真实 builtin success calibration observer不可达；调用方收到原始异常，History 终态为 failed，符合“零 `RESPONSE` observer／零 calibration”。
- **正常成功**：strategy success callback 先执行一次，随后 limiter success callback 执行一次，再发布一次 `RESPONSE`。builtin calibration observer在 facts 已就绪后学习一次，之后 context 转为 completed、发布 FINALIZE 并持久化 History；与指定顺序完全一致。
- **前序 facts 路径**：按一次带 request 降级 facts 的成功 Responses 请求执行，最终 History 同时保留 request 与 response typed provenance；按一次先 429、后成功的重试路径执行，History 只保留最终成功 attempt 的 facts，没有把失败 attempt 混入。
- **strict validator 路径**：合法 SDK content blocks 保持原 wire block 投影；缺失顶层 discriminator、mixed fields、未知 block 与第二 block 非法均继续被拒绝。R4 的 callback 顺序改动没有改变 validator 或 facts 生产代码，定向测试也未见回归。

## 事实性发现

未发现问题。

R3 唯一 major 已关闭：throwing strategy／`on_success()` 失败时为零 `RESPONSE` observer、零 success calibration；正常成功路径为 strategy → limiter → `RESPONSE`，各一次。前序 request／response facts 与 strict validator 抽查未见回归。

## 主观建议

无。

## 结构怪味与本轮处置

- 扫描范围：R3→R4 的生产与测试差异、`RetryCoordinator.notify_success()` 的异常传播、`HooksExecutor.observe()` 的 observer 异常隔离、builtin token calibration observer 的真实学习点，以及前序 facts／validator 接缝。
- 未发现新增结构怪味。R3 指出的 success commit boundary 错位已由当前顺序直接修复；本轮不建议引入额外状态机或新验证框架。

## 方法反思

1. **更好的内部替代方案**：当前实现把会终止请求的 strategy 与 limiter callbacks 放在 `RESPONSE` commit 之前，并统一纳入 failure finalization，已经比逐个针对 calibration 打补丁更接近项目现有最小共同提交边界；本轮未发现更优且不改变既有契约的内部路径。
2. **判据判别力**：候选绿灯之外，R4 两条新测试在 R3 生产实现上均按目标机制变红，分别区分失败污染与成功顺序错误；正、反样本均成立。
3. **成熟第三方方案**：问题属于项目内部 lifecycle 与 callback ordering，没有可直接替代该语义的成熟第三方组件；不建议引入新依赖。

## 结论

精确 candidate `b1df8f910c590033e83d5cafcd5e514f12bab937` 对 R3 唯一 major 的修复成立，定向最小测试与旧实现正样本对照均支持该结论。最终为 **0 blocker／0 major／0 minor**，**可 squash**。
