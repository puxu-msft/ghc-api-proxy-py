---
slug: collector
agent_id: a1f635178f07a0b7b
session_id: 3db40195
base: 92ac5643985d0b28fb1d94bbce3d5eb24abcfc44
branch: worktree-agent-a1f635178f07a0b7b
worktree: /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a1f635178f07a0b7b
plan: /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md
status: done; awaiting parent review
---

# Task 3 progress：Single-attempt buffered collector

## 当前任务

Task 3实现已提交为 `c712e86400c463b8ae32809b28eaa9e8d711eb33`，等待上级会话独立评审与集成。Collector只读一个attempt，不拥有ledger、replacement或events。

## 剩余项与验收

无实现剩余项。上级会话需独立评审candidate并决定集成。

## 已完成

1. `RawSseFrameDecoder.propose_one_bounded()`逐frame提议并保留未返回suffix；legacy `feed_bounded()`改为兼容wrapper。
2. 新增typed ending/result、`BufferedProtocolState`与统一`BufferedMemoryAccount`，collector执行read once→measure→reserve→apply并逐frame重算capacity。
3. 已覆盖raw、staging、state、projection与observation的共享account；source恰好关闭一次，primary与cleanup均保留，cancellation／`GeneratorExit`传播。
4. 新增无orchestration副作用的Chat decision adapter。
5. 精确pytest为112 passed；Ruff clean；Pyright 0 errors；额外Chat state回归31 passed。8项runtime mutation controls全部FIRED。

## 在途意图

无未提交实现；`.dev`仅为指向主工作树开发文档的预置symlink。

## 已否决路线

- Collector消费ledger或打开replacement：会形成第二个orchestration owner。
- 先mutate state再算cap：无法无损回滚，且会短暂越界。
- 只计raw/staging：违反Spec对state/projection/observation同时持有量的合同。
