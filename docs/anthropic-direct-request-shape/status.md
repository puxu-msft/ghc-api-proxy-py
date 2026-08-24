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
| `messages` 末尾角色 | `src/app/pipeline/subscribers/anthropic_trailing_assistant.py`，id `builtin:anthropic-trailing-assistant`，以 `after=` 显式排在 `builtin:blank-text-blocks` 之后 |
| `cache_control` 子字段按模型点名剥离 | `src/app/pipeline/subscribers/anthropic_cache_control.py`，id `builtin:anthropic-cache-control-vocabulary`，以 `after=` 显式排在 `builtin:server-tool-capability` 之后（那一步会把 `cache_control` 搬进它重写出来的文本块）。**默认档 `sanitize`**，删掉 `hook_fix_anthropic_request.cache_control_sanitize` 为该模型点名的字段（随包表在 `src/app/config/bundled-config.yaml`，今天只有 Claude 一族的 `scope`），位置集合按官方请求 schema 覆盖七处：顶层、`system[]`、`messages[].content[]`、`tool_result.content[]`、`search_result.content[]`、`document.source.content[]`、`tools[]`。**首版只做了中间三处**，顶层与嵌套是评审 CCBIR-02 补的 |
| 网关 beta 词汇表剥离 | `src/app/pipeline/request_headers.py` 的 `GATEWAY_UNSUPPORTED_BETAS` 与 `strip_gateway_unsupported_betas`，在 `pipeline/driver.py` 的 `shape_request` 里排在按模型剥离之前。**与用户那张 per-model 表并列而非合并**——两者回答的是不同的问题，规范条款见 spec §7.6～§7.8 |
| 新增损失码 | `LossCode.SYNTHETIC_TURN_ADDED`——唯一记录「加了东西」而非「丢了东西」的一个；`LossCode.CACHE_CONTROL_FIELD_NOT_CARRIED`——剥掉 `scope` 是真实的语义损失（它决定缓存共享范围），不是清噪音 |
| 测试 | `tests/unit/pipeline/subscribers/test_anthropic_thinking.py`、`test_anthropic_trailing_assistant.py`、`test_anthropic_cache_control.py`；beta 两层与其组合在 `tests/unit/pipeline/test_client_request_headers.py`；顺序锁定表在 `test_builtin_subscribers.py` |

## 判据的鉴别力：做过什么变异

| 变异 | 预期 | 实际 |
|---|---|---|
| `apply_route` 里 `context.model_descriptor = route.descriptor` 改为 `= None` | 只有端到端那条变红，手工设 descriptor 的那批照绿 | 与预期一致：1 failed / 20 passed。已还原 |
| 删掉 `align_effort` 的 `if desired in supported` 分支 | 若测试锁住了「目录发布即原样发出」，应变红 | **评审时全绿——假绿**；补 `('turbo',)` 用例后重做，变红。已还原 |
| 订阅者开头加 `if context.extras.get("counting_only"): return` | 若测试覆盖了 count 腿的刻意接线，应变红 | **评审时 39 项全绿——假绿**；补走 `handle_count_tokens` 的测试后重做，变红。已还原 |
| 拿掉 `repair_trailing_assistant` 的 `original_payload` 判别器 | 「客户端自己的 prefill 不修」那条应变红 | 变红 2 条（含 `test_a_blank_block_is_gone_from_what_the_driver_actually_sends`，它现在真的在守着这个判别器）。已还原 |
| 把 `after=(BLANK_TEXT_BLOCKS_ID,)` 改成 `before=` | 若这条顺序约束真的承重，行为测试应变红而不只是顺序锁定表 | 变红 6 条，**其中 3 条是行为测试**。已还原 |
| 把 `builtin:anthropic-cache-control-vocabulary` 的注册整段关掉（`if False:`） | 若有测试真的在守「接线」而不只是守函数，端到端那条应变红、直接调函数的那批应照绿 | 与预期一致：1 failed / 8 passed，且红在正确的位置（`scope` 仍出现在 wire 上）。用快照还原，`rg '_unregistered|if False'` 确认无残留 |
| 删掉 `shape_request` 里 `strip_gateway_unsupported_betas` 的调用 | 走 `shape_request` 的那条应变红 | 与预期一致：1 failed / 32 passed。用快照还原，`rg` 确认两处引用都在 |

| 清空 `bundled-config.yaml` 里的 `cache_control_sanitize` | 「开箱即用」与「随包表内容」两条应变红，其余照绿 | 与预期一致：2 failed / 20 passed。快照还原 |
| 把 schema 默认值改回 `passthrough` | 「开箱即用」那条应变红 | 与预期一致：1 failed / 21 passed。快照还原 |

每次还原后都 `rg MUTATION-PROBE` 确认无残留（exit 1），并重跑受影响测试。**后两条用文件快照还原而不是 `git checkout`**：本次改动尚未提交，`git checkout` 会连修复一起抹掉。

**这些变异证明了什么、没证明什么**：它们证明这三处接线各自被某一条测试真正覆盖，也证明其余测试对它们是盲的。后两条更值得记住的是**它们一开始是假绿**——断言在跑、代码在被调用、输入也真，但挑的输入恰好让被删的分支与另一条分支给出同一个答案。挑输入比写断言更决定分辨力。它们**没有**证明订阅者每一条分支都有分辨力；评审另外正控过 display-disabled 与幂等两处，记在它的报告里。

## 对真实上游的实测

2026-08-24，经运行中的代理（当时是改动前的代码，对 `thinking` 原样透传）打到真实上游：

| 探针 | 结果 |
|---|---|
| 负控制：旧请求体 `{"type":"enabled","budget_tokens":4095,"display":"omitted"}` | 400，与线上那条一字不差 |
| 正样本：`{"type":"adaptive","display":"omitted"}` + `output_config:{effort:"xhigh"}` | 200，正常作答 |
| 只带 `output_config`、完全不带 `thinking` | 200 —— 这条是 §4.5 的依据 |

覆盖范围与它证明不到的东西见 [spec.md](spec.md) §2.1。探针脚本不在仓库里（一次性，在 job 的临时目录），价值全在结果，而结果已写进 Spec。

2026-08-24 第二轮，`cache_control` 与 beta 词汇表，**这次脚本留在仓库里**（`exp/260824-beta-and-cache-control-probe/`，三个脚本 + `raw/`）。直连上游 `api.enterprise.githubcopilot.com`、`claude-opus-5`、每格一次调用、正控制先跑、主矩阵与对照各跑两遍逐格一致：

| 探针 | 结果 |
|---|---|
| 负控制：`cache_control: {type: ephemeral, scope: "organization"}` | 400，与用户线上那条一字不差 |
| **同一 body 加上 `prompt-caching-scope-2026-01-05`** | **400，错误一字不差**——补 beta 救不回来 |
| 该 beta 单独发、body 不用它 | 200——网关收下 beta，后端 schema 仍拒它启用的字段 |
| `{type: ephemeral}` / `{type: ephemeral, ttl: "1h"}` | 200（`ttl` 带不带自己的 beta 都收），这是白名单留下 `ttl` 的依据 |
| `scope` 放在 message 块 / tool 上 | 400，路径分别是 `messages.0.content.0.text.…` 与 `tools.0.custom.…`——三层各自独立 |
| 14 个 beta 逐个单发 | 拒 `tool-search-tool-2025-10-19` 与 `output-128k-2025-02-19`，收其余 12 个（含只差一位数字的 `tool-search-tool-2025-11-19`） |
| `defer_loading` 混合 true/false，**不带任何 beta** | 200 |
| `tool_search_tool_regex_20251119` 服务端工具，**不带 beta** | 200 |
| 第二轮 `tool_result.content[]` 里的 `{"type":"tool_reference"}`，**不带 beta** | 200 |

最后三行是「剥掉那个 flag 不会引发二次 400」的依据，覆盖了 tool search 的完整生命周期而不只是第一轮。完整矩阵、否决项与限定见 [reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md](reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md)。**限定**：只有企业端点、只有 `claude-opus-5`、只有非流式。

## 评审

异源模型独立评审一轮：[reports/260824-implementation-review.md](reports/260824-implementation-review.md)，0 blocker / 3 major / 4 minor，**7 条全部采纳**。逐条处置与「只采纳一半」的那条的理由见 [review-disposition.md](review-disposition.md)。

`cache_control` 与 beta 词汇表这一片另有一轮异源独立评审：[reports/260824-cache-control-and-beta-implementation-review.md](reports/260824-cache-control-and-beta-implementation-review.md)，**1 blocker / 2 major / 4 minor**。逐条处置见 [review-disposition-cache-control-and-beta.md](review-disposition-cache-control-and-beta.md)；其中 blocker（`passthrough` 档下也剥未知键）不由本方处置、交回用户，**用户随后两次裁定**：`passthrough` 字面成立，默认档改为 `sanitize`，同时把 `sanitize` 从白名单收窄为「只剥配置表为该模型点名的字段」并把表放进随包配置。条款见 spec §7.1～§7.3。

## 验证命令与结果（本快照）

```
uv run ruff check src tests          -> All checks passed
uv run pyright src tests             -> 0 errors, 0 warnings
uv run pytest tests --cov=app ...    -> 1788 passed, 2 skipped
```

## 未落地 / 开着的

见 [spec.md](spec.md) §9 的 A-1 ～ A-10。三条需要用户裁决或追认的：

- **A-5**（落进用户亲笔文档）是唯一一条会改变本文档权威性的：**在用户从 [`anthropic-thinking-capability.md`](../../human-controlled-docs-candidates/anthropic-thinking-capability.md) 摘取之前，spec.md 是我方推导，不是用户裁决。**
- ~~**A-8**~~ **已闭合**：用户 2026-08-24 两次裁定——`passthrough` 字面成立，同日默认档改为 `sanitize`，且 `sanitize` 收窄为「只剥配置表点名的字段」。条款见 spec §7.1～§7.3。
- **A-9**：四档中 `proxied` 仍未实现（配置到它启动即拒），`extended_cache_ttl` 仍零实现。

原先第 62 行「顺带指出」的那条已经不再是纯旁观：`strip_anthropic_beta_flags` 那张表按 `resolved_model` 匹配，而表里唯一的键 `claude-sonnet-4.6` 在同一份 `config.example.yaml` 里被 `model_mappings` 映走，两段配置同时生效时整张表匹配不到东西（2026-08-22 评审记于 `.dev/docs/tmp/260822-review-beta-flag-strip.md:6`，用户已在工作树里给那张表加了一条说明该现象的注释）。那仍是用户的文件。**本次新增的网关剥离不受这个缺陷影响**，因为它不查那张表——这正是两者不合并的实际收益之一。
