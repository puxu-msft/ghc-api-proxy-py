# Reasoning carrier v2 implementation rereview

## Scope and provenance

- Prior report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/reports/260904-implementation-review-general-opus-1.md`。
- Rereview scope: 原 `MAJOR-1`～`MAJOR-3`、修复 commit `5be74ee00ba3ba5cf5e0ad7524816e3f63c3c52f` 相对 `9cd96cebef0e3bc5e726a692d178499d79e0d8a5` 的 diff，以及三项修复的直接相邻合同。Stream reviewer 的其他 finding 按协调指令不作全量复审。
- Source worktree: `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2`；权威 Spec: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`。
- Runtime 仍无 `my-agents:as-reviewer` skill；第一轮已记录该能力缺失并按合同继续。本轮延续同一 reviewer 上下文。
- `/home/xp/src/ghc-api-proxy-py/.git/refs/heads/worktree/reasoning-carrier-v2` 解析为本轮修复 commit；修复 diff 的 15 个文件逐一与 `git show 5be74ee:<path>` 比较，结果 `compared 15 mismatches []`。

## Verdict

**NEEDS-FIX**。原 `MAJOR-1` 与 `MAJOR-3` 已关闭；原 `MAJOR-2` 的四类 Anthropic-slot facade 反例已关闭，但其新增 slot-aware classifier 在直接相邻的 Responses bare-v2 合同上仍与 consumer 分叉。当前共 1 major、0 blocker，不能 PASS。

## Remaining finding

### MAJOR-2 remains open：Responses slot 的 bare v2 被新增 slot-aware helper 错分为 `project_bare_v2`
- Spec `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md:144-151,218-226` 明定 bare v2 在 Responses `reasoning.encrypted_content` 中是 direction mismatch；reader 也在 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_bridge.py:215-219` 产生 `project_v2_direction_mismatch`。
- 但新增 `classify_responses_carrier()` 在同文件 `:77-90` 对任何 structural class 非 `project_v2` 都提前返回，故 bare v2 永远不进入 slot rule，实际返回 `project_bare_v2`。
- Resident guard 在 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/subscribers/reasoning_carrier.py:93-105,109-122` 使用该错误值，probe 的 provider-bound error 明文为 `synthetic reasoning carrier project_bare_v2 reached provider last-mile`，没有保留真实 direction classification。
- 对照 probe 同一输入得到 `helper project_bare_v2`、`reader project_v2_direction_mismatch`；全测试搜索没有 `classify_responses_carrier` 或 Responses-slot bare classification 用例。证据强度：直接 helper／reader／guard 三路径反例，足以据此修复。

## Original finding dispositions

| Original finding | Result | Evidence |
|---|---|---|
| MAJOR-1 strict UTF-8／JSON／record type grammar | **CLOSED** | `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_carrier.py:178-205` 现用 `allow_nan=False`、strict UTF-8 decode 与 rejecting `parse_constant`；`:44-45,225-250` 施行 dotted ASCII namespace regex。原 UTF-16LE probe 现同时得到 structural 与 bridge `project_malformed_v2`；原 NaN probe 现为 producer rejected＋consumer `project_malformed_v2`；原 `"x"` type probe同样 producer rejected＋consumer malformed。独立 Unicode literal vector 位于 `tests/unit/pipeline/translation_driver/test_reasoning_carrier.py:78-85`，generator 的 Unicode输入在 `exp/reasoning-carrier-v2/gen_vectors.py:29-36`。
| MAJOR-2 shared slot-aware classification | **PARTIALLY CLOSED／REMAINS MAJOR** | `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_bridge.py:53-99` 新增共享 slot-aware helpers；facade 在 `src/app/anthropic/thinking/responses_reasoning.py:78-104` 使用 Anthropic helper。重跑原四类 probe，unsupported／direction／profile／presentation 的 core 与 facade 现逐一完全相等；matrix test 在 `tests/unit/anthropic/test_responses_reasoning.py:111-152`。然而上列 Responses bare-v2 反例说明 helper 的 slot state space 仍不闭合。
| MAJOR-3 redacted data guard gap | **CLOSED** | `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/subscribers/reasoning_carrier.py:45-80` 现扫描 `redacted_thinking.data`；回归测试在 `tests/unit/pipeline/subscribers/test_reasoning_carrier_last_mile.py:103-125`。重跑原完整路径 probe，经 same-format translator 后 guard 现拒绝为 `reasoning_carrier_not_unwrapped messages.0.content.0.data`。

## Verification commands and outcomes

```text
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider tests/unit/pipeline/translation_driver/test_reasoning_carrier.py tests/unit/pipeline/translation_driver/test_reasoning_bridge.py tests/unit/anthropic/test_responses_reasoning.py tests/unit/pipeline/subscribers/test_reasoning_carrier_last_mile.py tests/unit/pipeline/delivery/test_sse_assembly.py tests/unit/pipeline/delivery/test_openai_responses_format.py
130 passed in 3.34s
```

原反例使用 target worktree 的 `.venv/bin/python` 与绝对 `PYTHONPATH` 逐一重跑，结果如下：

```text
UTF-16LE carrier: structural project_malformed_v2; bridge project_malformed_v2
NaN: producer-rejected; raw consumer project_malformed_v2
Non-namespaced type "x": producer-rejected; raw consumer project_malformed_v2
Facade matrix: unsupported/direction/profile/presentation 均为 core == facade
Redacted same-format path: reasoning_carrier_not_unwrapped messages.0.content.0.data
Responses bare-v2 adjacent control: helper project_bare_v2; reader project_v2_direction_mismatch
Responses bare-v2 last-mile guard: reasoning_carrier_not_unwrapped input.0.encrypted_content synthetic reasoning carrier project_bare_v2 reached provider last-mile
```

## Scope boundary and closeout

本轮没有全量重审同 commit 中 stream reviewer 所辖修复；`130 passed` 只证明列出的 scoped tests 在修复 worktree 通过，不外推为 full-suite 结论。源码与测试保持只读，未执行 git add／commit／checkout／stash；唯一写入产物是本报告。未执行清理、合并、发布或 worktree 生命周期操作。
