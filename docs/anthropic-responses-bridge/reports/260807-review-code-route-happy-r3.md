# Anthropic Responses route happy-path 定向代码复评 R3

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-route-happy` 分支 `feat/anthropic-responses-route-happy`，固定 `HEAD=dd376d6f1e9dc2997bc2f95d03a352fed4df1412`、base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。上一 R2 已确认父提交 `44808b7d0be84a0c1eb5c58294726c620d4280cd` 的 route／header 范围为 0 major，独立 verification 为 `PASS`。本轮只复核 successor `dd376d6…` 的统一 pre-attempt failure finalizer：`REQUEST_RECEIVED → ERROR → FINALIZE`、History 恰好一次、零 attempt／零 upstream、observer failure 隔离，以及 approval rejection／approval 修改后 validation failure等相邻失败路径；不把结论扩张为完整 LIFE-02／LIFE-03、stream bridge、block delivery、retry frontier或完整产品验收。
- **总体 verdict**：**可进入下一阶段；0 major。base `80bc8f2…` 到 HEAD `dd376d6…` 的完整三提交结果范围明确可 squash。** 该授权不只覆盖尾提交 patch；squash 后必须保留完整范围的结果 blobs与十个变更路径。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对

- 每次采纳为证据的 shell 都在同一调用内固定物理 root、branch、完整 HEAD、base与 clean worktree；候选执行前后均为 `dd376d6f1e9dc2997bc2f95d03a352fed4df1412` 且 `git status --porcelain` 为空。
- Successor 元数据为 `dd376d6…`，父提交精确为上一 R2 评审的 `44808b7…`，只修改 `src/app/pipeline/executor.py`、`tests/component/test_pipeline_executor.py` 与 `tests/smoke/test_anthropic_responses_route.py`。base→HEAD 是三条线性提交：`f3a5a76…` route、`44808b7…` header、`dd376d6…` finalizer。
- `src/app/pipeline/executor.py:31-73` 的 `_finalize_failure()` 先做 terminal-state 幂等门，再保留既有 `ApiError`或归一化 internal error，随后按同一 `HookContext` 投影 `ERROR`、`FINALIZE`，最后 finalize History。`HooksExecutor.observe()` 对 observer exception 记录 hook record并继续，因此失败 observer不改变主请求 action。
- 调用点对账覆盖初始 prepare／route decision、approval rejection、approval modified payload重校验、Responses stream typed reject、retry strategy factory、`PRE_SEND` hook、transport exception与response transform failure。已有 upstream HTTP 非成功分支仍按原路径只发一次 `ERROR`和一次 `FINALIZE`，没有被新 helper重复终结。
- 三条 typed pre-attempt route rejection——capability missing、显式 Responses override不受支持、Responses stream不支持——均断言同一 request id、`REQUEST_RECEIVED → ERROR → FINALIZE`、History started／finalized同一 context且各一次、attempt为空、Messages／Responses upstream均零调用。失败 terminal observer的两条错误记录进入 `hook_records`，后续 recorder仍收到两项事件。
- 父提交 R2 报告与独立 verification 均绑定 `44808b7…`：route／header为 0 major且 `PASS`。本轮没有发现 successor 改坏 success、Responses 429、Messages leg或header policy。

### 第一人称执行

- 以 capability missing 请求进入真实 FastAPI／ASGI `/v1/messages`：History先创建同一 context，hook先收到 `REQUEST_RECEIVED`；route decision在 attempt与upstream前返回 typed error；统一 finalizer发布 `ERROR`、失败 `FINALIZE`并只 finalize一次History；客户端得到稳定 Anthropic 400，两个upstream计数均为零。
- 以显式 Responses override但模型仅支持 Messages执行：行为与上项相同，错误 code保持`override_unsupported`，没有回退到Messages、没有approval、没有attempt或真实exchange。
- 以 Responses-only＋`stream=true`执行：approval仍恰好一次，随后在attempt前返回`responses_stream_not_supported`；同一context按失败序列终结，零upstream。
- 注入一个同时订阅`ERROR`与`FINALIZE`且两次都抛异常的 observer：异常被记录并隔离；后续observer仍完整收到`ERROR → FINALIZE`，History仍只finalize一次，原typed error仍返回客户端。
- 让approval直接rejected：真实ASGI探针得到403、`REQUEST_RECEIVED → ERROR → FINALIZE`、History一次、attempt零、upstream零。让approval返回非法modified payload：原validation exception仍是primary failure，context归一化为internal failed并完成同一终态序列，History一次且零upstream。
- 正控把运行时 `_finalize_failure()` 临时替换为父提交旧语义，同一 capability missing oracle只观察到`REQUEST_RECEIVED`并按缺失`ERROR／FINALIZE`原因变红；恢复production helper后为绿。该gate确实依赖本次修复，不是fixture天然通过。

## 结构怪味扫描

- **扫描范围**：`src/app/pipeline/executor.py:31-309` 的 failure owner／History finalizer／hook terminal调用点，`src/app/hooks/executor.py:101-133` 的 observer隔离边界，以及本 successor两份测试中的 recorder／fake owner。
- **判据**：检查重复 lifecycle owner、同一 failure同时走helper与legacy direct finalizer、observer反向改变request action、History重复finalize、attempt前错误误建attempt或触发upstream，以及测试expected从production实现同源生成。
- **处置**：未发现本 successor新增的结构怪味。Upstream HTTP non-success与stream route仍保留既有专用终结路径，但本提交未让它们与`_finalize_failure()`双重执行；完整stream／LIFE-02／LIFE-03统一owner继续由后续组合验收处理，不在本轮静默宣称已重构完成。

## 事实性发现

未发现问题。

## 主观建议

无。

## 验证摘要

- 相关 route／hooks／HTTP／prepare／policy 定向范围：运行结果 `36 passed`；独立 `--collect-only` 为 `36 tests collected`。
- 新增 component executor范围：运行结果 `4 passed`；独立 `--collect-only` 为 `4 tests collected`。
- approval／internal直接ASGI探针：rejection、非法modified payload和旧finalizer正控全部按目标机制通过。
- Targeted ruff：`All checks passed!`。
- Targeted pyright：`0 errors, 0 warnings, 0 informations`。
- base→HEAD `git diff --check`通过；最终候选HEAD不变且clean。

## 完整 squash 范围

完整范围是`80bc8f252b46c511f428af1d97159a5980ee9dc9..dd376d6f1e9dc2997bc2f95d03a352fed4df1412`，包含三条提交：

1. `f3a5a768491c542224103a87b75e5bb39803ac4a`——`feat: serve Anthropic requests via Responses`。
2. `44808b7d0be84a0c1eb5c58294726c620d4280cd`——`fix: filter Responses headers for Anthropic clients`。
3. `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`——`fix: finalize pre-attempt hook failures`。

结果范围包含十个路径：`src/app/anthropic/client.py`、`src/app/anthropic/header_policy/__init__.py`、`src/app/config/settings.py`、`src/app/pipeline/context.py`、`src/app/pipeline/executor.py`、`src/app/routes/anthropic.py`、`src/app/upstream/bootstrap.py`、`tests/component/test_pipeline_executor.py`、`tests/smoke/test_anthropic_responses_route.py`与`tests/smoke/test_systemd_units.py`。**0 major与可squash结论绑定这整个结果范围；仅squash尾提交不满足本结论。**

## 结论

Successor `dd376d6…` 已统一关闭上一组合态发现的 pre-attempt hooks终结缺口。目标三条typed reject均保持单owner、单History finalizer、零attempt／零upstream，并按`REQUEST_RECEIVED → ERROR → FINALIZE`结束；observer failure被隔离，approval rejection与相邻internal validation failure未回归。总体为**0 blocker／0 major／0 minor**，base `80bc8f2…`到HEAD `dd376d6…`的完整三提交范围**明确可squash**。完整LIFE-02／LIFE-03及其余bridge Acceptance范围仍由后续组合验收承担，不由本报告提前放行。

本报告属于当前状态交付物；按叶子评审者边界，仍需主会话对报告中的当前状态命题与证据引用完成独立复核后再定稿。
