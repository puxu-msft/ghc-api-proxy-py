# Final worktree／branch 清理计划快速复核

- **评审范围**：只复核 `docs/tmp/260807-final-worktree-cleanup-plan.md` 是否会删除尚未合并功能、是否保留 dirty worktree、archive targets 与 current-main 语义门是否充分、已进入 `main` 的 source／integration 分类是否完整；特别核对 current 新增 `stream-facts` 与 `network-retry` 分支。未执行任何 worktree、branch、ref 或文件清理。
- **总体 verdict**：**修复 major 后可进入下一阶段。** 计划对已列对象的保守门基本成立，但 current 新增的两个 clean source worktree 与一个 clean historical integration worktree完全漏列，尚不能作为 current 全集的机械清理合同。
- **blocker 数**：0。
- **major 数**：1。
- **写入边界**：唯一持久化写入为本报告 `docs/tmp/260807-review-worktree-cleanup-plan.md`；未修改被评审计划，未执行清理。

## 双视角覆盖证据

### 机械核对

- 现场固定 `/home/xp/src/ghc-api-proxy-py` 的 `main@fb5c027b38cc72910dd4495979a26a57fbbaa99b`，对账 current local refs、registered worktrees、每棵 worktree 的 branch／HEAD／`git status --porcelain=v1 -uall`，并检查新增 source archive identity 与 main 祖先门。
- `fix/stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b`、`archive/260807-stream-request-facts` 与 `/home/xp/src/ghc-api-proxy-py-stream-facts` HEAD 三者精确相等，worktree clean；其 source delta 与 main 语义提交 `d903d726baf3f15bf46ddf17384564fee154ed6a` 的 stable patch-id 同为 `dec1139b60fb1cb615f457c88d8d4a0546e3ed62`，且该 main 提交是 current main 祖先。
- `feat/responses-network-retry@584e63ba3724a7b6999d2163266d3daf8e731221`、`archive/260807-responses-network-retry` 与 `/home/xp/src/ghc-api-proxy-py-network-retry` HEAD 三者精确相等，worktree clean；`integrate/260807-network-retry@97b1a5c792a919022176f7a32179b2c51c632337` 的 worktree也 clean。integration delta 与 main 语义提交 `fb5c027b38cc72910dd4495979a26a57fbbaa99b` 的 stable patch-id 同为 `70da205bb9bdf62e91b843609d84aed1ba68e5a8`，且该提交就是 current main。
- network-retry source delta 的 patch-id为 `d8419cf8a4e2b8ba8ce2844ec9f9245f090c0c95`，不同于最终 integration／main；这与已记录的 integration 修正相符。因此 source 应按“reviewed source 已归档、最终语义由后继 integration／main 承载”分类，不能把 source 与 main 写成 patch-identical。
- dirty 集合仍包含主 worktree与 `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`；后者仍只有未跟踪 `docs/tmp/260807-systemd-installer-rebuild-resume.md`。计划对两者的保留结论没有被 current facts推翻。

### 第一人称执行模拟

- 按计划从顶部“覆盖全部 worktree／refs”读到 source 表、source readiness rows、historical integration 表、archive矩阵和最终复盘时，执行者找不到 `stream-facts` source、`network-retry` source或 `network-retry` integration 的任何一行；三者既不会进入逐行 gate，也无法在“所有 refs／所有 worktrees”复盘中获得预期 disposition。
- 模拟误删 dirty worktree：计划要求 status 为空、禁止 `--force`／`clean`／`reset`／`restore`／stash，并对 dirty rebuild 固定保留；该路径会停下，不会删除未持久化报告。
- 模拟清理新增两条线：`stream-facts` 可走 source gate；`network-retry` source 可在 exact archive＋最终 main 语义载体门后清理，integration只能先移除 clean worktree并保留 branch，待创建 exact-tip integration archive后才可删除 branch。现计划缺少这三行，因此不能直接机械执行完整 current clean 历史集合。

## 事实性发现

[major] `docs/tmp/260807-final-worktree-cleanup-plan.md:5-7,31-49,67-83,104-121,189-210,216-223` — 计划声明覆盖全部 current worktrees及 `feat/*`、`fix/*`、`integrate/*`、`archive/*`，但快照停在 `main@e9fb277…`，完全漏掉 current 新增的 `fix/stream-request-facts` source、`feat/responses-network-retry` source与 `integrate/260807-network-retry` historical integration，也漏掉两个现有 exact source archives — 按现文执行虽因 allowlist形态不会误删这三棵树，却无法完成其自称的全集清理与最终 refs／worktrees disposition；尤其 network-retry source patch不等于最终 main patch，不能靠 branch subject补猜分类 — 更新计划锚点到 current main；把 stream-facts source加入分类一、source readiness rows与 archive矩阵，main语义载体写 `d903d726…`；把 network-retry source加入分类一并明确“source archive保留、最终修正版由 integration／main承载”，main语义载体写 `fb5c027…`；把 `integrate/260807-network-retry@97b1a5c…` 加入 clean historical integration，移除worktree后先保留 branch，创建并验证 exact-tip integration archive后方可删 branch；随后重新跑 current 全集 gate。

未发现 blocker。除上述 current 漏项外，未发现计划会删除尚未合并功能或 dirty worktree；既有 source archive identity＋main语义祖先门、historical integration exact-tip archive门及 dirty rebuild保留门方向正确。

## 主观建议

无。当前只需补齐 current 分类与机械 rows，不应放宽任何 existing clean、archive或 main语义门。

## 结论

本轮是 **0 blocker／1 major**，因此**尚不能**按用户给定条件放行下一轮对全部 clean 历史 worktrees进行机械清理。补齐 `stream-facts` 与 `network-retry` 三个 current 对象并重新复核到 0 major 后，才可进入该机械清理轮；dirty 主树与 dirty systemd rebuild worktree继续原样保留。
