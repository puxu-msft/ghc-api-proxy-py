# Responses History facts 独立定向终审 R3

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-history-facts`，branch `fix/responses-history-facts`，candidate `864cfa30e291768cbc7b080fce80d9be4cbf2d83`，base `b91e58a29324b11840002efc53ed6f869b800c39`。仅复核 R2 的 1 个 major、1 个 minor，并检查 R1 的 3 个 major 是否反弹；未重建全量状态空间。
- **总体 verdict**：**修复 major 后可进入下一阶段。** 当前为 **0 blocker／1 major／0 minor**，**不可 squash**。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对

- 每个采信的 shell 结果都在同一次调用内验证物理 root、Git top-level、branch 与完整 HEAD。两次出现与本轮 marker、目录或 HEAD 不符的终端串线输出均作废；最终证据改由带唯一 marker 的 `/tmp/hf-r3-864cfa-*.log` 回读确认。
- 候选树起始为空。R2 `2e3a6d2…` 到 R3 `864cfa3…` 只修改 `src/app/pipeline/executor.py`、`tests/component/test_pipeline_executor.py`、`tests/unit/test_anthropic_response_validation.py`，与本轮定向修复范围一致。
- `src/app/pipeline/executor.py:334-388` 已把 `ResponseHook`、严格 wire validation、`normalized_response`、`final_response_payload`、response usage 与 request／response conversion facts 放在 `ObserverEvent.RESPONSE` 之前。R3 使用真实 `register_builtin_hooks()` 与 `TokenizationStateStore` 的测试覆盖 hook 抛错、hook 后非法 body、body 读取失败均零 calibration；合法 hook 后 usage 只学习一次，并在学习点断言 final facts 已存在。
- `tests/unit/test_anthropic_response_validation.py:24-80` 现有显式 fixture 覆盖当前锁定 SDK 的 6 类合法 content block：text、tool use、thinking、redacted thinking、server tool use、web search tool result；每类同时通过项目严格 validator、Anthropic SDK `Message` 与内部 `MessagesResponse` 投影，并断言 block JSON 不丢失。R2 minor 已关闭。
- request-side provenance、最终成功 attempt 投影与严格 wire validator 的防反弹测试均纳入最小定向集。精确 candidate 上该命令 rc=0；pytest 原始摘要为 `33 passed, 5 deselected in 2.52s`，该测试数量未用第二原理交叉计数，故只把 rc=0 与逐项测试选择作为放行证据。测试前后候选 `git status --porcelain=v1 -z` 哈希均为 clean-tree SHA-256。
- 对 R2 major 的 false-green 反查没有止于已有失败测试：继续扫描 `ObserverEvent.RESPONSE` 之后、函数返回之前的所有可失败步骤，发现正式 `RetryStrategyFactory` 扩展点的 `on_success()` 仍位于 calibration 之后，且异常按项目文档应终止流程。独立只读探针命中下述 major。

### 第一人称执行

- **hook 抛错／hook 后非法 body／body 读取失败**：均在发布 `ObserverEvent.RESPONSE` 前进入 failure finalization；真实 builtin calibration snapshot 不变、not dirty，R3 对 R2 原复现场景的修复有效。
- **合法 hook 后 body**：先完成 hook、严格 validator 和 final facts，再发布一次 `RESPONSE`；校准读取 hook 后最终 usage，学习一次。R2 要求的主成功路径成立。
- **合法 response＋用户 retry strategy 的 `on_success()` 抛错**：`RESPONSE` observer 先学习 calibration；随后 `RetryCoordinator.notify_success()` 抛出 `RuntimeError`。实测调用方收到异常，calibration snapshot 已变化且 dirty，context 仍为 `executing`，History finalized 次数为 0。故“失败零 calibration”在正式扩展路径上仍不成立。
- **前 3 个 major 防反弹**：request-side facts 仍带 typed provenance 与最终成功 attempt 编号；严格 validator 仍拒绝缺顶层 type／role、mixed fields、未知 block 与第二 block 非法；success facts 的 pre-hook／pre-validation 早发已修，但 post-calibration 晚失败窗口仍使第 1 个 major 未完全关闭。

## 事实性发现

[major] `src/app/pipeline/executor.py:391-410`、`src/app/pipeline/strategies/__init__.py:63-67`、`docs/2604-rewrite/hooks-system.md:8,29-34` — `TokenCalibrationSuccessObserver` 虽已移动到 hook、严格校验与 final facts 之后，但仍在可失败的 retry strategy success callback 和 completed transition 之前，正式扩展点异常会造成“最终调用失败但 calibration 已写入” — executor 先发布 `ObserverEvent.RESPONSE`，builtin observer 立即调用 `calibration.learn()`，随后 `coordinator.notify_success()` 无异常隔离地调用每个 strategy 的 `on_success()`。项目文档将用户 `RetryStrategyFactory` 定义为四类正式 hooks 之一，并明确 strategy 异常应终止流程。独立探针注册一个 `on_success()` 抛 `RuntimeError` 的合法用户 strategy，结果为 `EXCEPTION=RuntimeError`、`CALIBRATION_CHANGED=True`、`DIRTY=True`、`CONTEXT_STATE=executing`、`FINALIZED_COUNT=0`；目标树前后保持 clean。现有 R3 测试只覆盖 calibration 之前失败，以及不会抛错的 success callback，因此仍可全绿 — 把 calibration 的 `RESPONSE` 发布放到所有仍可使请求失败的成功提交步骤之后，或建立明确且受测的非抛错 commit boundary；至少加入真实 builtin observer＋抛错 `on_success()` 的回归，断言最终异常时 calibration 不变且 History／context 终态一致。还应同一判据检查后续 History finalization 失败，避免仅把窗口从 strategy callback 移到持久化步骤。

## 主观建议

无。

## 结构怪味与本轮处置

- `src/app/pipeline/executor.py:391-410` — **职责／提交边界错位**：observer、limiter、retry callback、状态 transition 与 History finalization 的 success side effects 交错排列，没有单一“之后不可再失败”的提交边界。**处置**：本轮作为上述 major，不另记重复事项；建议修复时明确 commit boundary，而不是只再移动一行 observer。
- 扫描范围：R2→R3 的 3 个文件、`HooksExecutor.observe()` 的异常语义、`RetryCoordinator.notify_success()`、生产 token calibration observer、History finalization 接缝。除上述同一根因外未发现新的定向结构问题。

## 方法反思

1. **更好的内部替代方案**：相比继续逐个移动 callback，项目内更稳妥的方案是明确 success commit 顺序，把所有可能终止请求的步骤放在 calibration 之前，并让 observer 只消费已提交事实。
2. **判据判别力**：R3 现有正负测试能区分 pre-validation 失败与正常成功，但不能区分 post-calibration 晚失败；本轮抛错 strategy 探针证明该缺口真实存在。
3. **成熟第三方方案**：本缺陷是项目内部生命周期与提交顺序，不存在能直接替代该状态机语义的第三方库；不建议为此引入新框架。

## 结论

R2 minor 已关闭，request provenance 与严格 wire validation 未反弹；R2 major 的原始 pre-hook／pre-validation 复现场景也已修复。但正式 retry strategy success callback 仍能在 calibration 写入后让调用失败，因此 candidate 仍为 **0 blocker／1 major／0 minor**，**不可 squash**。修复晚失败窗口并补对应真实 builtin 回归后再做定向复评；达到 0 major 时方可明确可 squash。
