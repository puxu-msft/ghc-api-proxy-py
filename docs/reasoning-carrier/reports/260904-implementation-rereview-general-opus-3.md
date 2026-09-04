# Reasoning carrier v2 final narrow rereview

## Scope and provenance

- Prior report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/reports/260904-implementation-rereview-general-opus-2.md`。
- Candidate: `c067529bc3a58474dd0b28c50a9080db9722c751`；rereview base: `5be74ee00ba3ba5cf5e0ad7524816e3f63c3c52f`。
- Scope strictly limited to the second-round remaining major, the 3-file diff, and the requested Responses-slot helper／reader／guard matrix. No full rereview was performed。
- Source worktree: `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2`。
- `/home/xp/src/ghc-api-proxy-py/.git/refs/heads/worktree/reasoning-carrier-v2` resolves to the candidate；the 3 changed files compare byte-for-byte with the candidate objects: `compared 3 mismatches []`。

## Verdict

**PASS**。0 blocker、0 major。第二轮唯一剩余 major 已关闭；第一轮三条 major 至此全部关闭。按本轮极窄范围，候选可进入协调者的后续集成判断。

## Disposition of the remaining major

### CLOSED：Responses slot bare v2 与项目／兼容 v1 carrier classification 现已统一

- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_bridge.py:77-99` 现先把 `project_bare_v2`、项目 v1 payload／bare、兼容 v1 payload／bare／legacy 映射为 `project_v2_direction_mismatch`，再对其他 structural classifications执行早返回；第二轮的错误 coarse return 已消失。
- 该顺序保留 precedence：malformed、unknown version 与 foreign 不在 direction set 中，仍保持 structural classification；grammar-valid v2 payload 才进入 `summary_parts_from_wire()` 与 profile／presentation recovery。
- Reader 的既有结果位于同文件 `:215-231`；helper 与 reader 的矩阵测试位于 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/tests/unit/pipeline/translation_driver/test_reasoning_bridge.py:174-196`。
- Provider-bound guard 的 bare-v2 classification regression test 位于 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/tests/unit/pipeline/subscribers/test_reasoning_carrier_last_mile.py:148-165`。

## Verification

```text
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -p no:cacheprovider tests/unit/pipeline/translation_driver/test_reasoning_bridge.py tests/unit/pipeline/subscribers/test_reasoning_carrier_last_mile.py
30 passed in 1.41s
```

使用 target worktree 的 interpreter 与绝对 `PYTHONPATH` 直接重跑 helper／reader／guard 三路径矩阵，六行均完全一致：

```text
v2-bare           project_v2_direction_mismatch project_v2_direction_mismatch project_v2_direction_mismatch
project-v1-payload project_v2_direction_mismatch project_v2_direction_mismatch project_v2_direction_mismatch
project-v1-bare    project_v2_direction_mismatch project_v2_direction_mismatch project_v2_direction_mismatch
compat-v1-payload  project_v2_direction_mismatch project_v2_direction_mismatch project_v2_direction_mismatch
compat-v1-bare     project_v2_direction_mismatch project_v2_direction_mismatch project_v2_direction_mismatch
compat-v1-legacy   project_v2_direction_mismatch project_v2_direction_mismatch project_v2_direction_mismatch
```

每行三列依次是 `classify_responses_carrier()`、`read_responses_reasoning()` 的 `ReasoningBridgeError.code`、provider last-mile guard error 中保留的 classification。该 probe 同时证明修复没有只让 helper 与测试自洽，而是抵达 reader 与 resident guard 两个直接消费者。

## Scope boundary and closeout

本轮未重审 3-file diff 之外的代码，也未运行 full suite；上列 PASS 只覆盖第二轮唯一剩余 major 及其直接相邻矩阵。源码与测试保持只读，未执行 git add／commit／checkout／stash；唯一写入产物是本报告。未执行清理、合并、发布或 worktree 生命周期操作。
