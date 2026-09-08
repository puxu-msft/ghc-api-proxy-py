# Final worktree／branch 清理计划

## 状态、范围与硬边界

本计划是只读盘点后的机械清理合同，不是删除授权，也不执行任何 worktree、branch 或 ref 删除。盘点绑定 `/home/xp/src/ghc-api-proxy-py` 的 `main@080105b54614e1320a5c193d7206dcaa584c9b41`，日期为 2026-08-08；该 commit 的 parent 为 `fb5c027b38cc72910dd4495979a26a57fbbaa99b`，对象类型为 `commit`，subject 为 `test: cover Responses retry exhaustion`。后续执行时必须现场重新解析 current `main^{commit}`；若 `main` 已前进，以下旧 SHA 只作历史映射，必须先重跑同类 gate，不能把本快照当成永久许可。

本计划覆盖 `git worktree list --porcelain` 返回的全部 worktree、`refs/heads/feat/*`、`refs/heads/fix/*`、`refs/heads/integrate/*` 与 `refs/heads/archive/*`。不覆盖远端 refs，不执行 push，不操作服务、systemd manager、部署、cutover 或当前运行中的进程。

清理原则只有四条：

1. **已进入 `main` 并归档的 source 线**：只有在 worktree clean、branch tip 精确等于 immutable archive ref、对应 main 语义 commit 是 current `main` 祖先时，才允许先移除 worktree，再删除 `feat/*`／`fix/*` branch；archive ref 必须保留。
2. **纯历史 integration 线**：integration tip 通常不是 `main` 祖先，且当前没有 exact-tip archive。允许在 clean gate 后移除 worktree，但 branch 先保留为唯一 durable ref；只有先创建并验证 exact-tip integration archive 后，才允许删除 `integrate/*` branch。
3. **仍含未合并或未持久化工作**：任何 staged、unstaged、untracked 内容都阻断 worktree 移除。不得用 `--force`、`git clean`、`reset`、`restore` 或整文件覆盖把 gate 变绿；先逐文件持久化或由用户明确裁决 disposition。
4. **新建 active／reservation 线**：即使 worktree clean、branch tip 恰好等于 current `main`，只要该 branch／worktree 已为下一阶段施工预留或正在使用，就不是历史载体。必须保留 worktree 与 branch；不得因“零 diff”“与 main 同点”或“尚无独有 commit”把它吸收到 source 清理批次。

当前主 worktree **dirty**，且不是清理目标。最终盘点看到以下并行 WIP，必须原样保留：

- `docs/agents/anthropic-responses-bridge/implementation.md`
- `docs/agents/service-cutover/readiness.md`
- `docs/agents/systemd-runtime/plan.md`
- `docs/tmp/` 下既有未跟踪文件
- `verification/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md`
- `verification/PHASE3_ACCEPTANCE_REPORT.md`
- `verification/phase3_acceptance.py`

本计划自身是本轮唯一允许新增的仓库文件。不得把主树 dirty 误写成由本计划造成，也不得为执行清理而暂存、stash、restore 或提交上述并行 WIP。

新增的 `/home/xp/src/ghc-api-proxy-py-reservation` 是 active reservation，不是旧 source：`feat/resident-byte-budget@080105b54614e1320a5c193d7206dcaa584c9b41` 当前与 `main` 同点且 worktree clean，但已经为 resident byte budget／reservation 后续施工占用。它与所有 dirty／active 线均必须原样保留，不进入任何 readiness、worktree remove、branch archive 或 branch delete 批次。

## 分类一：已进入 `main` 且 reviewed source 已归档

下表每一行均满足盘点时的两个静态事实：source worktree 为 clean，且 archive ref 精确 points-at source tip。`Tip ancestor main` 全部为 `no`，这是 squash／重建后的正常拓扑，不表示语义未合并；“主线语义载体”给出 living 文档记录的 current-main 等价提交。后续清理必须同时验证 archive identity 与主线语义载体祖先关系，不能只看 subject 或 branch 名。

| Source branch | Worktree | Reviewed tip／archive ref | Tip ancestor main | 主线语义载体 | 分类与动作 |
|---|---|---|---|---|---|
| `fix/reasoning-cardinality` | `/home/xp/src/ghc-api-proxy-py-reasoning-cardinality` | `b876e626dda821b267535b0bcffc9d81ced12763`／`archive/260807-anthropic-responses-reasoning-cardinality` | no | `d274f584219f8ae32f59d15d08ac007c45058c8d` | 已进入 main；可按 gate 删除 worktree＋source branch，保留 archive |
| `feat/session-liveness` | `/home/xp/src/ghc-api-proxy-py-liveness` | `f27a8c04cd3470bd50d7194a30371ca5404f727e`／`archive/260807-anthropic-responses-liveness` | no | `798ba3e7653b513c3c9c732019e793f828ae0890` | 同上 |
| `feat/anthropic-responses-request` | `/home/xp/src/ghc-api-proxy-py-request` | `fdd2f75fcec11e592b04f2686c4664262052a964`／`archive/260807-anthropic-responses-request` | no | `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7` | 同上 |
| `feat/reasoning-carrier-v2` | `/home/xp/src/ghc-api-proxy-py-carrier-v2` | `8301ee938601ad86c7f72d313abc6c976a74b2a9`／`archive/260807-reasoning-carrier-v2` | no | `a0d807fe807629b739ab16c5463f99bc27bc7aac` | 同上 |
| `feat/responses-anthropic-nonstream` | `/home/xp/src/ghc-api-proxy-py-response` | `7ddf17364d97349638d44352bbd9a9b025723ccc`／`archive/260807-responses-anthropic-nonstream` | no | `cdc080e1795ee1ac63d589ee00a10acd581b460e` | 同上 |
| `feat/responses-stream-parser` | `/home/xp/src/ghc-api-proxy-py-stream-parser` | `73a6aa114647440262691651cd17e9127785c75a`／`archive/260807-responses-stream-parser` | no | `a815948ef1b8e739e4bd49e31894be4dffc06950` | 同上 |
| `feat/anthropic-responses-route-policy` | `/home/xp/src/ghc-api-proxy-py-route-policy` | `84a22c07db3923768db44a1314e5ae6d5aed2e98`／`archive/260807-anthropic-responses-route-policy` | no | `d913a033252693022f0871f1e92c1b996d05eb71` | 同上 |
| `feat/nonstream-usage-details` | `/home/xp/src/ghc-api-proxy-py-nonstream-usage` | `aca3ced6e38efabf13ffe43d5935697801c74857`／`archive/260807-nonstream-usage-details` | no | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 同上 |
| `fix/responses-semantic-parity` | `/home/xp/src/ghc-api-proxy-py-semantic-parity` | `f5bca39ac582911b61d278fd678ec9298ad0c08e`／`archive/260807-responses-semantic-parity` | no | `bfc461f57a507059c5c7b098e0616e7882f7333d` | 同上 |
| `feat/anthropic-responses-route-happy` | `/home/xp/src/ghc-api-proxy-py-route-happy` | `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`／`archive/260807-anthropic-responses-route-happy` | no | `86b6cc3e72c0312ea8e93940513ee55e290da245` | 同上 |
| `feat/anthropic-block-delivery` | `/home/xp/src/ghc-api-proxy-py-block-delivery` | `e506bf87318424e4075b6422772ee0c7e9b8694a`／`archive/260807-anthropic-block-delivery` | no | `b91e58a29324b11840002efc53ed6f869b800c39` | 同上 |
| `fix/responses-reasoning-capability` | `/home/xp/src/ghc-api-proxy-py-reasoning-capability` | `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`／`archive/260807-responses-reasoning-capability` | no | `bd86207b4fdb55b7c10c795118f61ba693192003` | 同上 |
| `fix/responses-history-facts` | `/home/xp/src/ghc-api-proxy-py-history-facts` | `b1df8f910c590033e83d5cafcd5e514f12bab937`／`archive/260807-responses-history-facts` | no | `38bb06ff0eefef69fd4fdab830e67ff549563a20` | 同上 |
| `feat/anthropic-responses-stream-route` | `/home/xp/src/ghc-api-proxy-py-stream-route` | `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`／`archive/260807-anthropic-responses-stream-route` | no | `ae84aa9d4330e56b83aefdad977e7d93190ff0d4` | 同上；后续 stream 缺口从 current main 新建 successor，不续写旧 happy source |
| `fix/stream-request-facts` | `/home/xp/src/ghc-api-proxy-py-stream-facts` | `4fa7a87728376f14bd84b4b5853f8212d5bc786b`／`archive/260807-stream-request-facts` | no | `d903d726baf3f15bf46ddf17384564fee154ed6a` | 已进入 main；可按 gate 删除 worktree＋source branch，保留 archive |
| `feat/responses-network-retry` | `/home/xp/src/ghc-api-proxy-py-network-retry` | `584e63ba3724a7b6999d2163266d3daf8e731221`／`archive/260807-responses-network-retry` | no | 实现 `fb5c027b38cc72910dd4495979a26a57fbbaa99b`；exhaustion 永久回归 `080105b54614e1320a5c193d7206dcaa584c9b41` | 已进入 main 且后继回归已进入最新 main；source archive 保留 reviewed provenance，最终修正版由后继 integration／main 承载；可按 gate 删除 worktree＋source branch |
| `feat/systemd-cgroup-runtime` | `/home/xp/src/ghc-api-proxy-py-systemd` | `49fb1988621bba4356e7a5039a6994c2e6d19604`／`archive/260807-systemd-runtime` | no | `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` | 已进入 main；可按 gate 删除 worktree＋source branch，保留 archive |
| `feat/systemd-graceful-timeout` | `/home/xp/src/ghc-api-proxy-py-graceful-timeout` | `865a5b71210e2436b36786b5de67146939d1e0f5`／`archive/260807-systemd-graceful-timeout` | no | `c53849e2b5103c6426a67a8cbab687f2e45c1fa0` | 同上 |
| `feat/systemd-user-install` | `/home/xp/src/ghc-api-proxy-py-systemd-install` | `e16c2a700f23f66535e7347ab7357518eb8e56bd`／`archive/260807-systemd-user-install` | no | `e9fb2771d6e040c761bb4074e3fcf2547caece28` | 同上 |

### Source 线只读 readiness gate

先运行本段，只输出 `READY`，不删除。任一断言失败都停止，不得删减判据绕过。

```bash
ROOT=/home/xp/src/ghc-api-proxy-py
cd "$ROOT" && printf 'ROOT=%s\nTOP=%s\nBRANCH=%s\nHEAD=%s\nMAIN=%s\n' "$(pwd -P)" "$(git rev-parse --show-toplevel)" "$(git branch --show-current)" "$(git rev-parse HEAD)" "$(git rev-parse main^{commit})" && test "$(pwd -P)" = "$ROOT" && test "$(git rev-parse --show-toplevel)" = "$ROOT" && test "$(git branch --show-current)" = main && test "$(git rev-parse HEAD)" = "$(git rev-parse main^{commit})" && {
while IFS='|' read -r branch worktree tip archive main_commit; do
  test "$(git rev-parse "$branch^{commit}")" = "$tip" &&
  test "$(git rev-parse "$archive^{commit}")" = "$tip" &&
  test "$(git -C "$worktree" rev-parse HEAD)" = "$tip" &&
  test "$(git -C "$worktree" branch --show-current)" = "$branch" &&
  test -z "$(git -C "$worktree" status --porcelain=v1 -uall)" &&
  git merge-base --is-ancestor "$main_commit" main &&
  printf 'READY|%s|%s\n' "$branch" "$worktree" || exit 1
done <<'SOURCE_ROWS'
fix/reasoning-cardinality|/home/xp/src/ghc-api-proxy-py-reasoning-cardinality|b876e626dda821b267535b0bcffc9d81ced12763|archive/260807-anthropic-responses-reasoning-cardinality|d274f584219f8ae32f59d15d08ac007c45058c8d
feat/session-liveness|/home/xp/src/ghc-api-proxy-py-liveness|f27a8c04cd3470bd50d7194a30371ca5404f727e|archive/260807-anthropic-responses-liveness|798ba3e7653b513c3c9c732019e793f828ae0890
feat/anthropic-responses-request|/home/xp/src/ghc-api-proxy-py-request|fdd2f75fcec11e592b04f2686c4664262052a964|archive/260807-anthropic-responses-request|1c13fda4f5eac5e42ca0025d503f91eb0563f0e7
feat/reasoning-carrier-v2|/home/xp/src/ghc-api-proxy-py-carrier-v2|8301ee938601ad86c7f72d313abc6c976a74b2a9|archive/260807-reasoning-carrier-v2|a0d807fe807629b739ab16c5463f99bc27bc7aac
feat/responses-anthropic-nonstream|/home/xp/src/ghc-api-proxy-py-response|7ddf17364d97349638d44352bbd9a9b025723ccc|archive/260807-responses-anthropic-nonstream|cdc080e1795ee1ac63d589ee00a10acd581b460e
feat/responses-stream-parser|/home/xp/src/ghc-api-proxy-py-stream-parser|73a6aa114647440262691651cd17e9127785c75a|archive/260807-responses-stream-parser|a815948ef1b8e739e4bd49e31894be4dffc06950
feat/anthropic-responses-route-policy|/home/xp/src/ghc-api-proxy-py-route-policy|84a22c07db3923768db44a1314e5ae6d5aed2e98|archive/260807-anthropic-responses-route-policy|d913a033252693022f0871f1e92c1b996d05eb71
feat/nonstream-usage-details|/home/xp/src/ghc-api-proxy-py-nonstream-usage|aca3ced6e38efabf13ffe43d5935697801c74857|archive/260807-nonstream-usage-details|80bc8f252b46c511f428af1d97159a5980ee9dc9
fix/responses-semantic-parity|/home/xp/src/ghc-api-proxy-py-semantic-parity|f5bca39ac582911b61d278fd678ec9298ad0c08e|archive/260807-responses-semantic-parity|bfc461f57a507059c5c7b098e0616e7882f7333d
feat/anthropic-responses-route-happy|/home/xp/src/ghc-api-proxy-py-route-happy|dd376d6f1e9dc2997bc2f95d03a352fed4df1412|archive/260807-anthropic-responses-route-happy|86b6cc3e72c0312ea8e93940513ee55e290da245
feat/anthropic-block-delivery|/home/xp/src/ghc-api-proxy-py-block-delivery|e506bf87318424e4075b6422772ee0c7e9b8694a|archive/260807-anthropic-block-delivery|b91e58a29324b11840002efc53ed6f869b800c39
fix/responses-reasoning-capability|/home/xp/src/ghc-api-proxy-py-reasoning-capability|8bff1c3fbd721060a87f18b0ef9d90d7d998a997|archive/260807-responses-reasoning-capability|bd86207b4fdb55b7c10c795118f61ba693192003
fix/responses-history-facts|/home/xp/src/ghc-api-proxy-py-history-facts|b1df8f910c590033e83d5cafcd5e514f12bab937|archive/260807-responses-history-facts|38bb06ff0eefef69fd4fdab830e67ff549563a20
feat/anthropic-responses-stream-route|/home/xp/src/ghc-api-proxy-py-stream-route|f3922a9ba9f90e4eea598dac1d899ebbe18985e8|archive/260807-anthropic-responses-stream-route|ae84aa9d4330e56b83aefdad977e7d93190ff0d4
fix/stream-request-facts|/home/xp/src/ghc-api-proxy-py-stream-facts|4fa7a87728376f14bd84b4b5853f8212d5bc786b|archive/260807-stream-request-facts|d903d726baf3f15bf46ddf17384564fee154ed6a
feat/responses-network-retry|/home/xp/src/ghc-api-proxy-py-network-retry|584e63ba3724a7b6999d2163266d3daf8e731221|archive/260807-responses-network-retry|080105b54614e1320a5c193d7206dcaa584c9b41
feat/systemd-cgroup-runtime|/home/xp/src/ghc-api-proxy-py-systemd|49fb1988621bba4356e7a5039a6994c2e6d19604|archive/260807-systemd-runtime|cf53334a10a717a3a3d30d6c0e8a297f5000d90c
feat/systemd-graceful-timeout|/home/xp/src/ghc-api-proxy-py-graceful-timeout|865a5b71210e2436b36786b5de67146939d1e0f5|archive/260807-systemd-graceful-timeout|c53849e2b5103c6426a67a8cbab687f2e45c1fa0
feat/systemd-user-install|/home/xp/src/ghc-api-proxy-py-systemd-install|e16c2a700f23f66535e7347ab7357518eb8e56bd|archive/260807-systemd-user-install|e9fb2771d6e040c761bb4074e3fcf2547caece28
SOURCE_ROWS
}
```

### Source 线执行清单

只有上一 gate 对全部目标输出 `READY` 后，才逐行执行。每次实际执行仍须重跑对应单行 gate；不要把一次批量 readiness 当作之后状态不会变化的证明。

对每一行执行以下固定序列：

1. current-main gate。
2. 目标 worktree 的 branch、HEAD、clean 再验证。
3. archive ref 精确等于 tip，再验证主线语义 commit 是 current main 祖先。
4. 运行不带 `--force` 的 `git worktree remove <exact-path>`。
5. 验证 worktree 路径不再注册、archive ref仍精确等于 tip。
6. 运行 `git branch -D <exact-source-branch>`。这里之所以允许 `-D`，只因为 squash source tip本来就不是 main祖先，且 exact archive已承担 durable ref；缺 archive identity时绝不运行。
7. 再次验证 archive ref、current main与主树 WIP未变化。

不得删除本节任何 `archive/*` ref。

本节中 capability、History、stream、stream facts 与 network retry 的旧 source 均已完成“main 语义对象＋exact reviewed-source archive”双重承载：capability 对象为 `bd86207b4fdb55b7c10c795118f61ba693192003`，History 为 `38bb06ff0eefef69fd4fdab830e67ff549563a20`，stream 为 `ae84aa9d4330e56b83aefdad977e7d93190ff0d4`，stream facts 为 `d903d726baf3f15bf46ddf17384564fee154ed6a`，network retry 为 `fb5c027b38cc72910dd4495979a26a57fbbaa99b` 加 `080105b54614e1320a5c193d7206dcaa584c9b41`。对应 archive exact tips 仍是表内 `8bff1c3…`、`b1df8f9…`、`f3922a9…`、`4fa7a87…` 与 `584e63b…`；不得把 main squash object 与 archive source object混为一个 SHA。

## 分类二：纯历史 integration

这些 integration worktree 在最终盘点中除最后一行外均 clean。它们的 branch tip都不是 main祖先；`git cherry` 对多数行显示 patch等价，少数因 parent adaptation、组合提交或被后继替代仍有 `+`，不能单凭 cherry正负号裁决。living Implementation／Systemd Plan已经明确记录其语义进入main、被后继替代或仅作失败／适配 provenance。

| Integration branch | Worktree／tip | 主线语义或替代关系 | 当前状态 | 安全清理动作 |
|---|---|---|---|---|
| `integrate/260806-bridge-foundations` | `/home/xp/src/ghc-api-proxy-py-integrate-bridge`／`6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | foundations 分片已成为 `d274f584… → 798ba3e765… → 1c13fda4…` | clean，纯历史 | 可移除 worktree；branch先保留，exact archive建立后才删 branch |
| `integrate/260806-session-liveness` | `/home/xp/src/ghc-api-proxy-py-integrate-liveness`／`8e9aef69cc8606c4ca25286da617da8fc74d5c55` | 旧 liveness 组合被 reviewed source `f27a8c04…`与 main `798ba3e765…`取代 | clean，纯历史 | 同上 |
| `integrate/260807-bridge-happy-path` | `/home/xp/src/ghc-api-proxy-py-integrate-happy`／`7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | happy 分片已成为 `a0d807fe… → cdc080e1… → a815948e… → d913a033…` | clean，纯历史 | 同上 |
| `integrate/260807-bridge-next` | `/home/xp/src/ghc-api-proxy-py-integrate-next`／`a23081c5d5f48143bf3015182d8f00e1f6297755` | 旧候选为 `0 blocker／1 major`且 verify FAIL，已被 successor取代；只保留失败 provenance | clean，纯历史但 exact tip有审计价值 | 可移除 worktree；必须先保留 branch，或创建 exact archive后再删 branch |
| `integrate/260807-bridge-successor` | `/home/xp/src/ghc-api-proxy-py-integrate-successor`／`c43db35a7a5851225b55ce31b8edbec2cf90917f` | 三片已成为 `bfc461f5… → 86b6cc3e… → b91e58a2…` | clean，纯历史 | 可移除 worktree；branch先保留，exact archive建立后才删 branch |
| `integrate/260807-post-capability` | `/home/xp/src/ghc-api-proxy-py-integrate-post-capability`／`b647991f0e38ab4c4815b926e81514d9d7941192` | capability 后 History 组合已成为 `38bb06ff0eefef69fd4fdab830e67ff549563a20`，capability／History source 分别由 exact archive 保留 | clean，纯历史载体 | 同上 |
| `integrate/260807-semantic-parity` | `/home/xp/src/ghc-api-proxy-py-integrate-semantic`／`04bdfcbf75bfa7e9709d55869c70106c49146db6` | semantic 结果已成为 `bfc461f5…` | clean，纯历史 | 同上 |
| `integrate/260807-post-history-stream` | `/home/xp/src/ghc-api-proxy-py-integrate-stream`／`b5d5d0ce9dff4a1c28aac4371b3fdc71e806bba0` | History 后 stream 组合已成为 `ae84aa9d4330e56b83aefdad977e7d93190ff0d4`，History／stream source 均已有 exact archive | clean，纯历史载体 | 同上 |
| `integrate/260807-network-retry` | `/home/xp/src/ghc-api-proxy-py-integrate-network-retry`／`97b1a5c792a919022176f7a32179b2c51c632337` | source 后的修正版已成为 `fb5c027b38cc72910dd4495979a26a57fbbaa99b`，exhaustion 永久回归已成为最新 main `080105b54614e1320a5c193d7206dcaa584c9b41`；source archive 只保留 reviewed source provenance | clean，纯历史载体 | 可移除 worktree；branch 先保留，创建并验证 exact-tip integration archive 后才删 branch |
| `integrate/260807-systemd-runtime` | `/home/xp/src/ghc-api-proxy-py-integrate-systemd`／`fe9c20315b0137ca5b2253fdbd86a30d504255ef` | runtime 结果已成为 `cf53334a…` | clean，纯历史 | 同上 |
| `integrate/260807-systemd-code-only` | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-code`／`2ec0cb81832691685bfe8d98ad03071d2d5e5316` | old-base S3／S4 oracle；current main结果为 `c53849e2… → e9fb2771…`，禁止 replay | clean，纯历史适配 oracle | 可移除 worktree；必须保留 exact ref，archive后才删 branch |
| `integrate/260807-systemd-next` | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-next`／`0a93e7f18f197bf8a2395eaaf20afda446f92d6b` | old Plan postimage禁止使用；current main结果为 `c53849e2… → e9fb2771…` | clean，纯历史适配 provenance | 同上 |
| `integrate/260807-systemd-rebuild-resume` | `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`／`d3fabfadfba57af6c2d63e543e3198444777df54` | rebuilt S3／S4已成为 `c53849e2… → e9fb2771…` | **dirty**：唯一未跟踪报告 | **保留 worktree与branch**，先完成下节 disposition |

### Historical integration worktree gate

对 clean integration 只允许移除 worktree，不立即删除 branch。逐行执行时必须把期望 branch、tip、path作为字面量带入同一次 current-main gate；下面是机械模板：

```bash
ROOT=/home/xp/src/ghc-api-proxy-py
TARGET=/home/xp/src/ghc-api-proxy-py-integrate-bridge
BRANCH=integrate/260806-bridge-foundations
TIP=6a00f6f7aaa5083cebd7387208eca65b7df3bd79
cd "$ROOT" && printf 'ROOT=%s\nTOP=%s\nBRANCH=%s\nHEAD=%s\nMAIN=%s\nTARGET=%s\nTARGET_BRANCH=%s\nTARGET_HEAD=%s\n' "$(pwd -P)" "$(git rev-parse --show-toplevel)" "$(git branch --show-current)" "$(git rev-parse HEAD)" "$(git rev-parse main^{commit})" "$TARGET" "$(git -C "$TARGET" branch --show-current)" "$(git -C "$TARGET" rev-parse HEAD)" && test "$(pwd -P)" = "$ROOT" && test "$(git rev-parse --show-toplevel)" = "$ROOT" && test "$(git branch --show-current)" = main && test "$(git rev-parse HEAD)" = "$(git rev-parse main^{commit})" && test "$(git rev-parse "$BRANCH^{commit}")" = "$TIP" && test "$(git -C "$TARGET" branch --show-current)" = "$BRANCH" && test "$(git -C "$TARGET" rev-parse HEAD)" = "$TIP" && test -z "$(git -C "$TARGET" status --porcelain=v1 -uall)" && { git worktree remove "$TARGET"; }
```

执行下一行前必须替换三个字面量并重新运行完整 gate。禁止对 dirty rebuild worktree套用该模板。

### Historical integration branch gate

移除 clean historical worktree后，integration branch继续保护 exact tip。若确需清理 branch，先建立独立 archive ref；建议名称按清理日与 integration 身份固定，例如 `archive/260808-integration-260806-bridge-foundations`。每条 branch分别执行以下序列：

1. current-main gate。
2. 验证 integration branch仍精确指向表中 tip。
3. 验证旧 worktree已不再注册。
4. 创建新的 `archive/260808-integration-<identity>`，目标为完整 tip；若 ref已存在但不是该 tip，立即停止，禁止 force-update。
5. 验证 archive精确等于 tip。
6. 运行 `git branch -D <exact-integrate-branch>`。
7. 再验证 archive仍精确等于 tip、main未移动、主树WIP未被修改。

`bridge-next` 的失败 provenance、两个 old-base systemd oracle与 rebuilt exact tip不能因“功能已被替代”而省略 archive；这不是 ROI 取舍，而是避免让文档引用变成不可达对象。

`integrate/260807-network-retry` 同样必须先创建 `archive/260808-integration-260807-network-retry` 并验证其 exact tip 为 `97b1a5c792a919022176f7a32179b2c51c632337`，再删除 integration branch；不得用已有的 source archive `archive/260807-responses-network-retry`（tip `584e63ba3724a7b6999d2163266d3daf8e731221`）替代该 integration archive，因为两者承载的语义版本不同。

## 分类三：active reservation 或仍含未合并／未持久化工作，必须保留

### `feat/resident-byte-budget`

保留对象为：

- Worktree：`/home/xp/src/ghc-api-proxy-py-reservation`
- Branch：`feat/resident-byte-budget`
- HEAD：`080105b54614e1320a5c193d7206dcaa584c9b41`
- 与盘点时 `main^{commit}` 的关系：精确相等
- 状态：clean，但 active／reserved
- Archive：无，也不应为本轮清理而创建

该线是从最新 main 新建的 resident byte budget／reservation 施工入口。clean 只表示尚无 working-tree 差异，不表示施工意图消失；与 main 同点只表示 reservation 的基线新鲜，不表示它是已完成的历史 source。结论固定为：**保留 worktree、保留 branch、不创建清理 archive、不运行 remove 或 branch delete。** 只有用户明确宣布该 reservation 作废，或后续工作完成并另行形成新的清理裁决，才允许重新分类。

### `integrate/260807-systemd-rebuild-resume`

阻断对象为：

- 文件：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume/docs/tmp/260807-systemd-installer-rebuild-resume.md`
- 状态：untracked
- 盘点时大小：22,059 bytes
- SHA-256：`49bedcfaf4879d61cf597c93847a10a1aae5bb64b7ded14ef2ae84869e42313f`
- 主树同路径：不存在

该报告记录 S4 rebuild 的 parent、pathset、patch-id、result blobs、测试边界与结构怪味，虽然其中 current-main快照已经过期，但它仍是不可由 Git commit自动重建的运行日志。不得直接删除或因 S4已进入main而判定无价值。

解除阻断的机械条件：

1. 选择一个主仓 tracked 的历史证据路径；优先按项目文档归档约定落位，禁止只复制到另一个 untracked `docs/tmp`。
2. verbatim复制后核对 SHA-256仍为 `49bedcfaf4879d61cf597c93847a10a1aae5bb64b7ded14ef2ae84869e42313f`；若需增加 time-point header，必须另建 wrapper／index，不改写原报告 bytes。
3. 确认目标文件已被一个 current-main可达 commit跟踪：`git ls-files --error-unmatch <path>`成功，且包含该文件的 commit是 current main祖先。
4. 对该历史报告及其 current-state边界完成独立文档评审；过期断言只作为 time-point事实，不得提升为current真相。
5. 回到 rebuild worktree，重新验证除该报告外没有其他 staged、unstaged或untracked内容；由用户明确确认该文件已有 durable copy后，才可移走原件或让 worktree达到clean。
6. worktree clean后，按“纯历史 integration”流程先移除worktree、保留branch；需要删branch时，再创建 exact-tip integration archive。

在以上六项全部完成前，结论固定为：**保留 worktree、保留 branch、禁止 force remove。**

### 后续产品缺口的保留方式

当前仍存在真实后续缺口，但它们不位于上述旧 source／integration branch的独有提交中：

- stream semantic reorder、完整usage／terminal／History矩阵、retry frontier、quota／resident backpressure、真实socket partial-write／RST、in-flight shutdown、持久化harness／safety tests与完整Acceptance；
- systemd S5真实user-manager／effective cgroup smoke；
- systemd S7双实例／rolling；
- 三个已登记 non-blocking minor与后续 installer hardening。

这些缺口由 living Implementation、Systemd Plan、Readiness与Acceptance承载。它们的安全保留方式是保留 current main上的living WIP与archive provenance，并在实施时从当时current main新建 successor branch；**不得为了“保留缺口”继续复用已归档的旧 source branch或旧 integration parent。** 如果后续发现某项缺口确实只存在于待清理branch的独有commit，立即把该branch重新归类为“仍含未合并工作”，停止清理并先形成新reviewed successor或明确用户裁决。

## Archive refs 盘点与 disposition

所有现有 archive refs均保留，不在本清理计划中删除、移动或 force-update。它们不是“可合并branch”，而是 squash前reviewed source的immutable provenance。

| Archive ref | Exact tip | Main语义／用途 | Disposition |
|---|---|---|---|
| `archive/260806-anthropic-responses-reasoning` | `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b` | 原 reasoning reviewed source；main baseline `ed77c9d191df81c451c25161420515cca52ce6a4`及后续cardinality修复保留current语义 | 保留 immutable |
| `archive/260807-anthropic-responses-reasoning-cardinality` | `b876e626dda821b267535b0bcffc9d81ced12763` | main `d274f584…` | 保留 immutable |
| `archive/260807-anthropic-responses-liveness` | `f27a8c04cd3470bd50d7194a30371ca5404f727e` | main `798ba3e765…` | 保留 immutable |
| `archive/260807-anthropic-responses-request` | `fdd2f75fcec11e592b04f2686c4664262052a964` | main `1c13fda4…` | 保留 immutable |
| `archive/260807-reasoning-carrier-v2` | `8301ee938601ad86c7f72d313abc6c976a74b2a9` | main `a0d807fe…` | 保留 immutable |
| `archive/260807-responses-anthropic-nonstream` | `7ddf17364d97349638d44352bbd9a9b025723ccc` | main `cdc080e1…` | 保留 immutable |
| `archive/260807-responses-stream-parser` | `73a6aa114647440262691651cd17e9127785c75a` | main `a815948e…` | 保留 immutable |
| `archive/260807-anthropic-responses-route-policy` | `84a22c07db3923768db44a1314e5ae6d5aed2e98` | main `d913a033…` | 保留 immutable |
| `archive/260807-nonstream-usage-details` | `aca3ced6e38efabf13ffe43d5935697801c74857` | main `80bc8f25…` | 保留 immutable |
| `archive/260807-responses-semantic-parity` | `f5bca39ac582911b61d278fd678ec9298ad0c08e` | main `bfc461f5…` | 保留 immutable |
| `archive/260807-anthropic-responses-route-happy` | `dd376d6f1e9dc2997bc2f95d03a352fed4df1412` | main `86b6cc3e…` | 保留 immutable |
| `archive/260807-anthropic-block-delivery` | `e506bf87318424e4075b6422772ee0c7e9b8694a` | main `b91e58a2…` | 保留 immutable |
| `archive/260807-responses-reasoning-capability` | `8bff1c3fbd721060a87f18b0ef9d90d7d998a997` | main `bd86207b…` | 保留 immutable |
| `archive/260807-responses-history-facts` | `b1df8f910c590033e83d5cafcd5e514f12bab937` | main `38bb06ff…` | 保留 immutable |
| `archive/260807-anthropic-responses-stream-route` | `f3922a9ba9f90e4eea598dac1d899ebbe18985e8` | main `ae84aa9d…` | 保留 immutable |
| `archive/260807-stream-request-facts` | `4fa7a87728376f14bd84b4b5853f8212d5bc786b` | main `d903d726…` | 保留 immutable |
| `archive/260807-responses-network-retry` | `584e63ba3724a7b6999d2163266d3daf8e731221` | reviewed source provenance；最终修正版由 integration `97b1a5c792a919022176f7a32179b2c51c632337`、main 实现 `fb5c027b38cc72910dd4495979a26a57fbbaa99b`与 exhaustion 回归 `080105b54614e1320a5c193d7206dcaa584c9b41`承载 | 保留 immutable |
| `archive/260807-systemd-runtime` | `49fb1988621bba4356e7a5039a6994c2e6d19604` | main `cf53334a…` | 保留 immutable |
| `archive/260807-systemd-graceful-timeout` | `865a5b71210e2436b36786b5de67146939d1e0f5` | main `c53849e2…` | 保留 immutable |
| `archive/260807-systemd-user-install` | `e16c2a700f23f66535e7347ab7357518eb8e56bd` | main `e9fb2771…` | 保留 immutable |

## 最终机械执行顺序

以下顺序不可交换：

1. **冻结 current main与并行WIP**：打印 root、top-level、branch、HEAD、`main^{commit}`、`git status --porcelain=v1 -uall`与`git worktree list --porcelain`。若主树WIP集合变化，只更新快照，不自行归属或清理；显式断言 active reservation `/home/xp/src/ghc-api-proxy-py-reservation`仍注册在`feat/resident-byte-budget`，不得进入后续目标集合。
2. **先处理 source线 readiness**：运行本计划的 source gate。逐行移除clean worktree，验证archive后再删对应`feat/*`／`fix/*` branch。任一行失败只阻断该行，不把它改成force操作。
3. **再处理 clean historical integration worktree**：逐行重跑exact branch／tip／path／clean gate，只移除worktree，保留branch。
4. **给 historical integration tip建立exact archive**：每条单独创建，验证ref不存在或已精确相等；禁止force-update。archive建立后才允许删除对应`integrate/*` branch。
5. **保留 active／dirty 线**：无条件排除`feat/resident-byte-budget` reservation；dirty rebuild则先完成22,059-byte报告的durable-copy、hash、tracked-commit与独立评审门，未满足时不执行任何remove。
6. **复盘所有refs**：重新列出`feat/*`、`fix/*`、`integrate/*`与`archive/*`，确认删掉的活动branch都有对应exact archive，现有archive未移动。
7. **复盘所有worktrees**：`git worktree list --porcelain`中只应少掉本轮明确处理且已通过clean gate的路径；main worktree仍在，dirty WIP仍在。
8. **最终状态比较**：除本轮明确删除的worktree注册与branch、明确新增的integration archive外，current main、主树index／working-tree内容与所有现有archive必须保持不变。发现额外变化立即停止，不继续下一项。

## 明确禁止

- 不使用 `git worktree remove --force`。
- 不移除、归档或删除`feat/resident-byte-budget`与`/home/xp/src/ghc-api-proxy-py-reservation`；clean且与main同点不是清理授权。
- 不使用 `git clean`、`git reset --hard`、`git restore`、`git checkout -- <path>`、stash或整文件覆盖来制造clean。
- 不删除或force-update任何现有`archive/*`。
- 不因branch tip不是main祖先就判定“未合并”，也不因subject同名就判定“已合并”；必须使用本计划的archive identity＋main语义映射。
- 不按ROI删除未合并功能、缺口、失败provenance或适配oracle；无法机械证明已被main／archive承载时，默认保留。
- 不操作远端，不push，不创建PR，不安装／启动／停止unit，不部署，不cutover。
- 不把本计划标为清理已完成；它只给出条件式、安全、可逐行执行的后续清单。

## 证据来源与复核边界

本计划的 current-state依据来自同一次绑定`main@080105b54614e1320a5c193d7206dcaa584c9b41`的盘点：current-main gate、`git cat-file -t`、`git show -s`、`git worktree list --porcelain`、逐worktree `git status --porcelain=v1 -uall`、`git merge-base --is-ancestor`、`git cherry`、archive points-at，以及 living `docs/agents/anthropic-responses-bridge/implementation.md` 与 `docs/agents/systemd-runtime/plan.md`。其中 `git cherry`只作补丁等价辅助，不单独裁决语义；living docs提供source／integration→main的正式映射，Git祖先检查确认这些main载体已进入current main。盘点还单独确认`integrate/260807-post-capability@b647991…`、`integrate/260807-post-history-stream@b5d5d0c…`与`integrate/260807-network-retry@97b1a5c…`均为clean历史载体，而`feat/resident-byte-budget@080105b…`虽clean却是active reservation；两类状态不得混淆。

本文写成后必须全文重读，并逐项复验表内ref／tip／path。由于本会话是leaf reviewer，不能调度独立agent；因此本文在交付时标记为 **independent review required**。该标记不影响本轮只读盘点结论，但在任何实际删除前，执行者必须取得独立评审的`0 blocker／0 major`，并对评审后发生的任何Git状态漂移重新跑全部机械gate。
