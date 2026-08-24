# 实施状态

**这份答「现在是什么样」**，不答「应该是什么样」——那是 [spec.md](spec.md)。活文档，在有意义的检查点更新。

**快照**：2026-08-24，工作树未提交状态。

## 已落地

| 面 | 在哪 |
|---|---|
| 目录能力位进活链路 | `src/app/model_provider/types.py` 的 `parse_adaptive_thinking` 与 `ModelDescriptor.adaptive_thinking`；`github_copilot.py` 的 `replace_catalog` 接线 |
| 能力事实从路由送到订阅者 | `Route.descriptor`（`pipeline/routing.py`）→ `apply_route` → `RequestContext.model_descriptor` |
| 请求体构造 | `src/app/pipeline/subscribers/anthropic_thinking.py`，跑在 `attempt.prepare` 上，id `builtin:anthropic-thinking-capability` |
| effort 与目录能力对齐 | `pipeline/translation_driver/reasoning.py` 的 `align_effort`，与翻译腿共用同一条 `EFFORT_LADDER` |
| 配置 | 顶层 `model_thinking_effort`；`hook_fix_anthropic_request.thinking.display`（`config/schema.py`），经 `server/composition.py` 绑定到订阅者 |
| 测试 | `tests/unit/pipeline/subscribers/test_anthropic_thinking.py`；顺序锁定表在 `test_builtin_subscribers.py` |

## 判据的鉴别力：做过什么变异

| 变异 | 预期 | 实际 |
|---|---|---|
| `apply_route` 里 `context.model_descriptor = route.descriptor` 改为 `= None` | 只有端到端那条变红，手工设 descriptor 的那批照绿 | 与预期一致：1 failed / 20 passed。已还原 |
| 删掉 `align_effort` 的 `if desired in supported` 分支 | 若测试锁住了「目录发布即原样发出」，应变红 | **评审时全绿——假绿**；补 `('turbo',)` 用例后重做，变红。已还原 |
| 订阅者开头加 `if context.extras.get("counting_only"): return` | 若测试覆盖了 count 腿的刻意接线，应变红 | **评审时 39 项全绿——假绿**；补走 `handle_count_tokens` 的测试后重做，变红。已还原 |

每次还原后都 `rg MUTATION-PROBE` 确认无残留（exit 1），并重跑受影响测试。

**这些变异证明了什么、没证明什么**：它们证明这三处接线各自被某一条测试真正覆盖，也证明其余测试对它们是盲的。后两条更值得记住的是**它们一开始是假绿**——断言在跑、代码在被调用、输入也真，但挑的输入恰好让被删的分支与另一条分支给出同一个答案。挑输入比写断言更决定分辨力。它们**没有**证明订阅者每一条分支都有分辨力；评审另外正控过 display-disabled 与幂等两处，记在它的报告里。

## 对真实上游的实测

2026-08-24，经运行中的代理（当时是改动前的代码，对 `thinking` 原样透传）打到真实上游：

| 探针 | 结果 |
|---|---|
| 负控制：旧请求体 `{"type":"enabled","budget_tokens":4095,"display":"omitted"}` | 400，与线上那条一字不差 |
| 正样本：`{"type":"adaptive","display":"omitted"}` + `output_config:{effort:"xhigh"}` | 200，正常作答 |
| 只带 `output_config`、完全不带 `thinking` | 200 —— 这条是 §4.5 的依据 |

覆盖范围与它证明不到的东西见 [spec.md](spec.md) §2.1。探针脚本不在仓库里（一次性，在 job 的临时目录），价值全在结果，而结果已写进 Spec。

## 评审

异源模型独立评审一轮：[reports/260824-implementation-review.md](reports/260824-implementation-review.md)，0 blocker / 3 major / 4 minor，**7 条全部采纳**。逐条处置与「只采纳一半」的那条的理由见 [review-disposition.md](review-disposition.md)。

## 验证命令与结果（本快照）

```
uv run ruff check src tests          -> All checks passed
uv run pyright src tests             -> 0 errors, 0 warnings
uv run pytest tests --cov=app ...    -> 1683 passed, 2 skipped, 覆盖率 90.28%
```

## 未落地 / 开着的

见 [spec.md](spec.md) §7 的 A-1 ～ A-5。其中 A-5（落进用户亲笔文档）是唯一一条会改变本文档权威性的：**在用户从 [`anthropic-thinking-capability.md`](../../human-controlled-docs-candidates/anthropic-thinking-capability.md) 摘取之前，spec.md 是我方推导，不是用户裁决。**

顺带指出、不属于本 topic 的一处：`hook_strip_anthropic_request_headers.strip_anthropic_beta_flags` 那张表按 `resolved_model` 匹配，而表里唯一的键 `claude-sonnet-4.6` 在同一份 `config.example.yaml` 里被 `model_mappings` 映走，两段配置同时生效时整张表匹配不到东西。2026-08-22 的评审已记下（`.dev/docs/tmp/260822-review-beta-flag-strip.md:6`），至今未处理。那是用户的文件。
