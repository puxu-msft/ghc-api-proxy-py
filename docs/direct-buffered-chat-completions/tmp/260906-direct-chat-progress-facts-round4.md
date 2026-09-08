---
slug: facts-round4
agent_id: a84ab1d288fe4d046
session_id: 3db40195
base: abdfd5493a5532197a642a60e4d4a7cd6dc564b5
source_candidate: 0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f
branch: worktree-agent-a84ab1d288fe4d046
worktree: /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a84ab1d288fe4d046
plan: /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md
status: integrated
replaces_progress: /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/tmp/260906-direct-chat-progress-facts.md
---

# Task 2 progress：Facts fix round 4 takeover

## 当前任务

接手Task 2唯一未闭合finding `task-2-facts-review-03` residual A。旧candidate HEAD `0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f`；旧worktree只读。

## 剩余项与验收

1. `_same_frozen_json()`不得复制current retained `FrozenJsonObject.items` mapping metadata。
2. Semantic equality仍保持object key-order independent、array order sensitive、bool与number不混、arbitrary-size integer可比较。
3. Deep/wide nested current unknown的prospective sizing不触发current-side mapping copy。
4. `current=B; incoming=A,B`三组顺序delta继续满足`before + delta == after`。
5. 跑Task 2 exact pytest、Ruff、Pyright并提交新commit。

## 在途意图

推荐只索引incoming一侧，直接迭代current tuple并向incoming index查值；不得回退serializer equality或clone whole state。

## 已否决路线

- 继续`dict(left.items)`：复制retained metadata，finding不闭合。
- 交给Task 3 cap兜底：cap需要Task 2提供pre-allocation size接口。
- 用orjson canonicalization：big integer与既有FrozenJson域不兼容。

## Round 4结果

- Cherry-pick lineage：以`abdfd5493a5532197a642a60e4d4a7cd6dc564b5`为base，顺序将source `364e3a490714c3613f7d47f149377fd069433684`／`b417bf6508e65eb72195ebb71fbc79550dcf33d3`／`e42fc7660a656bc53a1ee7ea06e920b555d2a1f5`／`0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f` cherry-pick为local `8c3e33c`／`44b5458`／`14c82df`／`9dc8611`，全程无冲突。
- Production修复：`_same_frozen_json()`仅为incoming `FrozenJsonObject.items`建立index，递归时直接遍历current retained tuple；不再复制current mapping metadata。
- Regression control：新增24层、每层24个siblings的deep/wide current unknown；sentinel拒绝任何`dict(current.items)`，同时覆盖object key-order independence、array order sensitivity、bool与number分离及`10**100`。same value delta为0；两类conflict各只新增一个issue，且每步`before + delta == after`。
- 既有`current=B; incoming=A,B` choice finish、tool id/name、unknown三组顺序回归继续通过。
- 新commit：`bfd9c2d952e89ee77d3c8daade19d5c2640eb4a3` — `fix: avoid cloning retained Chat JSON metadata`。

## Verification

- 反向变异把production临时恢复为`dict(left.items)`后，新sentinel test在`current retained FrozenJsonObject.items copied`目标断言判红；随后以SHA-256一致的快照恢复。
- Task 2 exact pytest：`128 passed in 4.50s`。
- Task 2 exact Ruff：`All checks passed!`。
- Task 2 exact Pyright：`0 errors, 0 warnings, 0 informations`。

## 集成结果

- 原评审者最终判定：14项finding全部ADDRESSED；SPEC COMPLIANCE ✅；TASK QUALITY Approved；无新Critical／Important。
- Main squash commit：`92ac5643985d0b28fb1d94bbce3d5eb24abcfc44`（`feat: model buffered Chat stream facts`）。
- Reviewed source archive：`archive/260906-direct-chat-facts` → `bfd9c2d952e89ee77d3c8daade19d5c2640eb4a3`。
- Main-side gate：128 passed；Ruff clean；Pyright 0 errors。

## Handoff

- Task 2已集成，写入权结束。
- 本轮仅修改Task 2的`state.py`与`test_state.py`，未实现Task 3，未改已关闭的其余13项。
