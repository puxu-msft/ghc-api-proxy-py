---
report_id: completed-client-actions-implementation-review
attempt_id: completed-client-actions-implementation-review-260904-opus-01
status: in-review
reviewed_at_rev: "baseline 4b7d74f56b8b0264b481a2fefe275a233979fbb2; uncommitted candidate bound by SHA-256 manifest below"
reviewed_at: 2026-09-04T01:52:03+00:00
---

# Completed client actions merged-state implementation review

## 评审范围

以 `4b7d74f56b8b0264b481a2fefe275a233979fbb2` 为改动前 baseline，评审 `/home/xp/src/ghc-api-proxy-py` 主工作树中用户列出的 7 个 source 文件与 6 个 test 文件的当前未提交内容。判据来自 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md` §7.1、§10，`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 的着色、文本与验收条款，以及 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md` §10。

## 总体 verdict

`needs-fix`。候选有 1 条 major，修复后才可提交。

## Blocker 数

0。

## Candidate 版本绑定

下列 SHA-256 在源码阅读前后两次读取均一致，因此本报告只约束这些确切内容；任一 hash 改变都需要重判受影响结论。

```text
016da62710783b23f96b6765381cb72a66da1dadd8558c36bd6ad7feaf8535d9  src/app/pipeline/delivery/assembling.py
c73cd82d25a12cae2f715e39a88956233ff3162cced9cd2fddbb1e5ac417a3ad  src/app/pipeline/delivery/passthrough.py
66f71e0072c792d1b2ef02a1689e7ccd5b9084a220b81562c9a10f0e67a95ef5  src/app/pipeline/delivery/formats/openai_responses_actions.py
23a8bc1424c3d6e4c9c8117d929f8d415e82def1ce771af924f825b3894fc387  src/app/pipeline/delivery/formats/openai_responses_passthrough.py
d89f09deec0d4ee66b15e9822b3e60d9a51a2c9e46572eae927b26555130e0d4  src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py
fb9b543078993c1f3e494b2c3e64904439c54e4d5f9baa8a18225bbc94e06574  src/app/observability/request_trace.py
5a09c316651ba3438805034258ed2a09c65b920cbea1e0134a27258168df3f31  src/app/observability/request_log.py
ca8a471a279277ecc8297b241be010fd25936d9a205ffd85dc6272b772d7c053  tests/unit/pipeline/delivery/test_responses_passthrough.py
abbd8eb25946002d68ca24aa7ad814d1c1086962ee813c4157e8f5136360ecef  tests/unit/pipeline/delivery/test_anthropic_passthrough.py
72883d5271a494ef5f053df9f6e5d4648b089f3a4595d4aa8eca80698a4a9704  tests/unit/pipeline/delivery/test_sse_assembly.py
2ae11a7f9764aa3f7f8363cb63c4bb1d7f7bb317c23defd07fc695daabc340be  tests/unit/observability/test_request_log_file.py
9e7c865b215da2d020ee1b4f328f0c808f8042ea51e5bafbe0ed1de7b348866f  tests/unit/observability/test_request_log.py
384237deb0e7f0c7d0ecacf9ac096f76a310c5216412e269bd5d70479c13bdb7  tests/int/test_pipeline_app.py
```

## Findings

### completed-client-actions-implementation-review-01 — missing-type empty item 被错误投影为 `false`

- finding_id: completed-client-actions-implementation-review-01
- severity: major
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:104-122`; related_locations: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_actions.py:35-37`, `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:368-405`
- 判据与现状：Spec §7.1 要求 type 缺失为 `unknown`，且仅 `not_required` 投影为 `false`；classifier 对 `{}` 正确返回 `unknown`，但 batch 循环在第 113～114 行以 `if not item: continue` 丢掉空 item，最终 `any(...)` 返回 `false`。
- 复现：候选代码上的只读探针得到 `classifier=unknown`、`batch_projection=False`、`released=0 held=1`；即 `until-tool-use` 没有在安全 frontier 释放该 batch，现有测试只测 wrapper 的缺 type 与非空 opening/closing merge，未覆盖空 item 的 batch 投影。
- 影响与修复：这使三态事实、done-side `_saw_client_action=True` 与 buffering consumer 彼此矛盾，并在明确批准的 unknown 边界扣押客户端可能需要的 item；应区分“没有 item object”与“存在空 item object”，让后者参与 merge/classification，并加 batch 回归测试。

## C1～C9 逐项核验

| Criterion | 结论 | file:line 证据 |
|---|---|---|
| C1 | 不通过。三态表与 public bool wrapper 正确，但 RawEventBatch 对空 item 的 missing-type `unknown` 错投影为 `false`，见 finding 01。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_actions.py:6-59`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_passthrough.py:57-59`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:104-122`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:330-405`。 |
| C2 | 不通过一个明确边界，其余所要求路径成立。按 index merge 后才分类的结构在 108～122 行，server `tool_search_call` opening unknown 被 closing server 覆盖，Anthropic classifier 仍仅 `tool_use` 为真；但第 113 行把空 item 整体漏出 merge。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:103-122`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py:43-55`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:375-405`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_anthropic_passthrough.py:98-107`。 |
| C3 | 通过。全仓 assignment 扫描中只有 passthrough adapter 的 `response.completed` 分支写三项 facts；`response.incomplete` 在分支前返回，translated assembler 与 legacy/nonstream summaries 保持默认。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_passthrough.py:62-80`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:544-562`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_sse_assembly.py:453-475`；`/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log_file.py:210-233`。 |
| C4 | 通过。最终 facts 只枚举 terminal `response.output`；done-side 仍仅在关闭事件更新 `_saw_client_action`，混源控制明确断言 done-side `end_turn` 与 terminal 三项 required、顺序和重复并存。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_actions.py:62-83`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:183-207`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:468-506`。 |
| C5 | 通过。三项从 `Terminal` 逐槽复制到 `RequestTrace`、`RequestLine`，JSONL 继续用 recursive `asdict`；默认 `""/()/false` 与显式 `output=[]` 的 completeness true 可区分，exact-object test 锁住 enum 值与 action 字段 shape。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/assembling.py:67-72`；`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py:184-208,230-255`；`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:144-147`；`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log_file.py:40-42`；`/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log_file.py:62-205`。 |
| C6 | 通过。绿色条件精确为 completed、complete true、actions empty；required/unknown/unclassified 均不绿，action type 不染色，name 复用 dim/cyan helper；terminal branch 先于 legacy stop reason，incomplete 留在黄色 `max_tokens`。 | `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:204-236,267-288,422-438`；`/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py:371-445`。 |
| C7 | 通过，测试运行结果采用用户给出的已运行证据。helper 通过 TestClient 的真实内部 `/responses` route，route（e）在 app state 替换 capabilities 后从 structlog event 读取 ANSI；五组 oracle 分别覆盖 empty、message、missing/malformed、unknown 与混源控制，mock docstring 没冒充真实 upstream。 | `/home/xp/src/ghc-api-proxy-py/tests/int/test_pipeline_app.py:172-207,2058-2088,2839-2872,3351-3475`；mutation controls 的命令与 8 个目标判红结果见 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md:345-369`。 |
| C8 | 通过。terminal 旁路只读取并写 `Terminal`，不修改 `SseEvent`；batch encoding、passthrough framer 与 terminal wire 路径未在 baseline diff 中变化，translated/incomplete defaults 有隔离测试。唯一 release 行为变化是 C1/C2 已批准 classifier projection 本身，其中 finding 01 是错误边界。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses_passthrough.py:62-80`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:124-129,366-378`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_sse_assembly.py:453-475`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:544-562`。 |
| C9 | 发现 1 条 major state-consistency/boundary 缺陷，即 finding 01；未发现第二条达到 blocker/major 的 correctness、serialization 或 efficiency 缺陷。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:104-122,199-202`；focused probe 结果记录于 finding 01。 |

## 承重前提及证据强度

- 前提：用户给出的 6 route tests、367 merged-state tests、Ruff、Pyright 与 8 mutation controls 结果对应本 hash manifest。它支撑 C7 与“其余已写测试保持绿色”的判断；若为假，C7 必须降为 unverified。按用户的 trust-first 指示采用，未冒充本 reviewer 重跑结果。
- 前提：两次 SHA-256 读取之间候选未变。它支撑本报告的版本绑定；若为假，受影响文件必须重审。两次输出逐项一致，证据强到足以据此行动。
- 前提：缺 type 的 item 包括存在但为空的 item object。它支撑 finding 01；若为假，该复现只剩 malformed-input robustness。这里由 Spec §7.1 的“type 缺席”为 `unknown`、计划的 `{}` classifier oracle，以及候选 `_item_object` 自身关于无 readable type 的合同共同确认，强到足以定为 major。

## 搜索面与执行面

- 先读判据，再读全部 13 个用户指定 candidate 文件的当前绝对路径内容，并以 isolated worktree 中的 baseline commit 对每个既有文件做 unified diff；新文件逐行读取。
- 为追传播与真实 route 接缝，另只读了 `src/app/pipeline/delivery/blocks.py`、`src/app/pipeline/delivery/sse_source.py`、`src/app/pipeline/delivery/formats/openai_responses.py`、`src/app/observability/request_log_file.py` 与 `src/app/server/routes/inference.py` 的相关区段。
- 未重复用户已提供的 test、Ruff、Pyright 与 mutation suites。源码阅读发现 C1 矛盾后，只运行一个不写主树、禁用 bytecode 的 focused Python probe，复现结果是 `classifier=unknown`、`batch_projection=False`、`released=0 held=1`。
- 未评审用户列举范围外的其它改动，也未检查主工作树 index/status；isolated harness 拒绝把 Git 命令重定向到共享 checkout，因此 baseline 从 isolated worktree 读取，candidate 通过主树绝对路径读取并以 SHA-256 固定。

## 未采纳／排除路线

- 未因已有 green evidence 忽略源码矛盾；只对矛盾路径追加 focused probe，没有无理由重跑 367-test suite。
- 未把 `RawEventBatch.requires_client_action` 对同一 event 的二次 JSON decode 提升为 finding；没有测得实际效率影响，无法达到用户要求的 blocker/major 证据门槛。
- 未提出泛化风格建议、proof framework 或 scope reduction，也未修改被评对象；修复路由交回主会话。

## 整体判定

候选不能按当前 hash manifest 提交。finding 01 修复并以空 item batch 的 `unknown → true` projection 回归测试锁住后，应恢复同一 reviewer 复评 C1、C2、C8 与 C9；其余 C3～C7 的源码结论不受该局部修复影响，除非相应 hash 同时变化。

## 我最没把握的三个判断

1. finding 01 的 severity 在 upstream reachability 很低时可能被主会话重判为 minor；我仍定 major，因为它直接违反本切片最核心的显式 unknown projection contract，而不是一条未承诺的 malformed-input 加固。
2. C7 采用了用户提供的 mutation 执行证据而没有看到逐个失败输出；结论足以按 trust-first 行动，但不能冒充本 reviewer 独立复跑。
3. C8 的 wire 不变结论来自 baseline diff、纯读取数据流与既有测试证据，而不是本轮 byte-for-byte 执行；对当前变更面足够，但若修复 finding 01 触及 event construction 或 framing，必须重判。

## 执行本契约时遇到的摩擦

isolated harness 阻止 Git 命令通过 `git -C` 读取共享主工作树，因此改用主树绝对路径读取 candidate、从 isolated worktree 读取 baseline object，再以 `diff` 对照；这没有缩小评审面。focused probe 首次调用 `uv run` 在 isolated worktree 创建了被 ignore 的 `.venv`，未写主工作树，也未改变被评对象。

## 交付声明

delivery_complete: true
completed_at: 2026-09-04T01:52:03+00:00
finding_total: 1
blocker_count: 0
major_count: 1
minor_count: 0
nit_count: 0
