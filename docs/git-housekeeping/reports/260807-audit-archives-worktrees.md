# Current archive refs、branches 与 worktrees 只读清理审计

- **评审范围**：`/home/xp/src/ghc-api-proxy-py` 的 current local refs、全部 registered worktrees、五个 `archive/*` refs、current `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`，以及与 reasoning baseline／cardinality／liveness／request／systemd reviewed HEAD 对应的最终评审报告。本轮只判断 Git 证据载体是否可保留或可机械清理，不重新评审代码，不重跑产品验收，不执行任何 worktree／branch／archive 清理。
- **总体 verdict**：**可按本文“机械清理清单”清理；“保留清单”中的对象不可清理。** Foundations 三个 reviewed source、共享 foundations integration、旧 liveness integration、systemd source 与 systemd integration 均有 clean worktree；所需 archive ref 已精确指向 reviewed HEAD；foundations 三个 integration commits 与 systemd squash 均已以 stable patch-id 等价提交进入 current main，current Implementation 记录对应 main-side gates 已通过。Happy integration、四个 happy source worktrees与 non-stream usage 后继仍承载未进入 main 的后续链，必须保留。另有 1 项不阻断本机械清理清单的 living-doc major，须在继续 happy-path／deployment 执行前修复。
- **blocker 数**：0。
- **major 数**：1。
- **审计写入边界**：唯一写入为本文件 `docs/tmp/260807-audit-archives-worktrees.md`。未创建、移动、更新或删除任何 ref、branch 或 worktree，未切换分支，未执行 stash／restore／reset／clean，也未触碰现有主树 WIP。
- **主树基线**：`main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。审计开始前主树已有 `docs/agents/service-cutover/readiness.md` 修改，以及 `docs/tmp/`、`verification/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md`、`verification/PHASE3_ACCEPTANCE_REPORT.md`、`verification/phase3_acceptance.py` 未跟踪状态；这些不是本审计创建的内容，本轮未修改。主树自身不是清理对象。

## 双视角覆盖证据

### 机械核对

- 直接读取 `git worktree list --porcelain` 与 `git for-each-ref refs/heads`，逐项记录所有 worktree 的绝对路径、branch、精确 HEAD 与 porcelain dirty count；本文涉及的 feature／integration worktree 均为 `dirty=0`。
- 对五个 archive ref 逐项执行对象值等式核对；每个 ref 的实际 object ID 均与最终评审报告绑定的 reviewed HEAD 完全相等，且 archive refs 当前没有直接 worktree binding。
- 读取 current main first-parent 历史，确认 foundations 的三个语义提交按 cardinality → liveness → request 顺序进入 main，随后 systemd runtime 进入 main。
- 用 `git patch-id --stable` 交叉比较 source integration commit 与 current main commit：`9e5f874…` ↔ `d274f58…`、`cae83f4…` ↔ `798ba3e…`、`6a00f6f…` ↔ `1c13fda…`、`fe9c203…` ↔ `cf53334…` 均一一相等。由于这些分支经 squash／replay 后不会成为 main 的 commit ancestor，本文不使用 `git branch --merged` 作为清理判据。
- 对旧 `integrate/260806-session-liveness@8e9aef69…` 另做 stable patch-id 对账，确认它与 reviewed liveness source range `47d9ef101c4b81ac70d805b1da157b34d021d33d..f27a8c04cd3470bd50d7194a30371ca5404f727e` 的净补丁相等；它只是已被完整 foundations 链取代的历史载体。
- 直接读取最终评审报告：reasoning R2 绑定 `d90c90d…`，cardinality 绑定 `b876e62…`，liveness R3 绑定 `f27a8c0…`，request R3 绑定 `fdd2f75…`，systemd R4 绑定 `49fb198…`。
- 直接读取 `260807-review-main-foundations-systemd.md` 与 current `implementation.md`：current main 的四个回放提交未发现代码 blocker／major；cardinality、liveness、request 与 systemd 的 main-side gates均记录为通过，reviewed source refs已归档。前者的唯一 major是 living文档状态冲突，不是代码或 Git 载体缺口。
- Request source range 与第三个 integration commit不要求简单 patch-id相等：第三片在已落 cardinality基线上对共享 `responses_reasoning.py` 做语义合并。该追溯由 request R3 reviewed HEAD archive、`260806-review-code-bridge-foundations-r2.md` 的 merged-state 0 blocker／0 major、`260806-verify-bridge-foundations-r2.md` 的 production forward→public converter范围内 `PASS`、回放预检累计 blob oracle，以及 integration→main patch-id等价共同闭合。

### 第一人称执行模拟

- 模拟清理 foundations：先保留 archive refs，再移除 clean reviewed feature worktrees／branches，最后移除 clean shared integration worktree／branch。完成后 reviewed source HEAD 仍由 immutable archive refs 可达，main 仍保留三个等价语义提交，不依赖 integration branch 存活。
- 模拟清理 systemd：先确认 archive 精确、source 与 integration clean、prepared squash 与 current main tip patch-id 等价，再移除 source 与 integration worktree／branch。完成后 reviewed source HEAD 仍由 archive 可达，main 保留等价 systemd 提交；这不表示 unit 已安装、已部署或 cutover 获授权。
- 模拟误清 happy/source：若删除 `integrate/260807-bridge-happy-path` 或 carrier／nonstream／parser／route source refs，尚未进入 main 的四提交冻结链及其后续评审／main-side replay载体会丢失；若删除 usage worktree，则以 happy tip 为 parent 的后继提交也失去活动载体。因此这些对象全部判为保留。
- 模拟只看 ancestor 的错误路径：所有 squash/replay source branch 当前都不是 main ancestor；若机械使用 `git branch --merged main`，会把实际可清理对象误判为不可清理。本文改用“archive 精确对象＋clean worktree＋stable patch-id 等价 main commit”的组合判据。

## Archive refs 精确性与保留结论

| 领域 | 最终评审绑定 | Archive ref | Current object | 结论 |
|---|---|---|---|---|
| Reasoning baseline | `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b`，`260806-review-code-reasoning-r2.md` | `archive/260806-anthropic-responses-reasoning` | `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b` | **精确；保留且不得移动／force-update** |
| Reasoning cardinality | `b876e626dda821b267535b0bcffc9d81ced12763`，`260806-review-code-reasoning-cardinality.md` | `archive/260807-anthropic-responses-reasoning-cardinality` | `b876e626dda821b267535b0bcffc9d81ced12763` | **精确；保留且不得移动／force-update** |
| Session liveness | `f27a8c04cd3470bd50d7194a30371ca5404f727e`，`260806-review-code-liveness-r3.md` | `archive/260807-anthropic-responses-liveness` | `f27a8c04cd3470bd50d7194a30371ca5404f727e` | **精确；保留且不得移动／force-update** |
| Request converter | `fdd2f75fcec11e592b04f2686c4664262052a964`，`260806-review-code-request-r3.md` | `archive/260807-anthropic-responses-request` | `fdd2f75fcec11e592b04f2686c4664262052a964` | **精确；保留且不得移动／force-update** |
| systemd runtime | `49fb1988621bba4356e7a5039a6994c2e6d19604`，`260807-review-code-systemd-runtime-r4.md` | `archive/260807-systemd-runtime` | `49fb1988621bba4356e7a5039a6994c2e6d19604` | **精确；保留且不得移动／force-update** |

Reasoning baseline 的活动 source branch／worktree 已不在 current registered worktree 与 local branch 集合中；本轮只确认其 archive ref 精确并继续保留。其余四个 archive 对应的 feature worktree 当前均 clean。

## Main 落地与等价性

| 语义片 | Source integration | Current main commit | Stable patch-id | 结论 |
|---|---|---|---|---|
| Cardinality | `9e5f874d5b547bd9d733b0ee134e165f818de205` | `d274f584219f8ae32f59d15d08ac007c45058c8d` | `d5a27f67b536a3144c8b9e33add8a4779b5cf337` | 等价进入 main |
| Liveness | `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` | `798ba3e7653b513c3c9c732019e793f828ae0890` | `80976d48781b46e56ca9dc142ead02f488d201b2` | 等价进入 main |
| Request | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7` | `1f8c17fe1c12d4a3fe050a5754b6d54ae6b85811` | 等价进入 main |
| systemd runtime | `fe9c20315b0137ca5b2253fdbd86a30d504255ef` | `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` | `eab37d38b63730f895be3e55fd256f0547209630` | 等价进入 main |

Current main 的 first-parent 顺序为 `d274f58…` → `798ba3e…` → `1c13fda…` → `cf53334…`。前三项完整覆盖 foundations integration 的冻结顺序；第四项覆盖 prepared systemd squash。Current `implementation.md` 记录 foundations三片及systemd的 main-side gates已通过；`260807-review-main-foundations-systemd.md` 在该 exact HEAD上复核最终代码、四片身份及定向运行证据，未发现代码 blocker／major。该结论不把局部提交升级为完整 bridge产品 `PASS`，也不授权部署或 cutover。

## 机械清理清单

以下清单是**允许执行的顺序与精确对象**，不是本轮已执行动作。每一组执行前应重新读取 current object 与 clean 状态；若任一值漂移，停止该组，不使用 force 或 discard 绕过。

### Foundations reviewed feature 载体

- [ ] 重新确认 `archive/260807-anthropic-responses-reasoning-cardinality == b876e626dda821b267535b0bcffc9d81ced12763`，且 `/home/xp/src/ghc-api-proxy-py-reasoning-cardinality` 仍为 `fix/reasoning-cardinality@b876e626dda821b267535b0bcffc9d81ced12763`、clean；current Implementation 仍记录 main `d274f584…` 的 cardinality gate已通过。
- [ ] 移除 worktree `/home/xp/src/ghc-api-proxy-py-reasoning-cardinality`。
- [ ] 删除活动 branch `fix/reasoning-cardinality`；保留对应 archive ref。
- [ ] 重新确认 `archive/260807-anthropic-responses-liveness == f27a8c04cd3470bd50d7194a30371ca5404f727e`，且 `/home/xp/src/ghc-api-proxy-py-liveness` 仍为 `feat/session-liveness@f27a8c04cd3470bd50d7194a30371ca5404f727e`、clean；current Implementation 仍记录 main `798ba3e765…` 的 liveness gate已通过。
- [ ] 移除 worktree `/home/xp/src/ghc-api-proxy-py-liveness`。
- [ ] 删除活动 branch `feat/session-liveness`；保留对应 archive ref。
- [ ] 重新确认 `archive/260807-anthropic-responses-request == fdd2f75fcec11e592b04f2686c4664262052a964`，且 `/home/xp/src/ghc-api-proxy-py-request` 仍为 `feat/anthropic-responses-request@fdd2f75fcec11e592b04f2686c4664262052a964`、clean；current Implementation 仍记录 main `1c13fda4…` 的 request＋跨片 gate已通过。
- [ ] 移除 worktree `/home/xp/src/ghc-api-proxy-py-request`。
- [ ] 删除活动 branch `feat/anthropic-responses-request`；保留对应 archive ref。

### Foundations integration 载体

- [ ] 重新确认 `/home/xp/src/ghc-api-proxy-py-integrate-bridge` 仍为 `integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79`、clean。
- [ ] 重新确认三组 stable patch-id 仍分别映射到 main 的 `d274f58…`、`798ba3e…`、`1c13fda…`，三个 reviewed archive refs仍精确，current Implementation 仍记录三片 main-side gates已通过。
- [ ] 移除 worktree `/home/xp/src/ghc-api-proxy-py-integrate-bridge`。
- [ ] 删除 branch `integrate/260806-bridge-foundations`。

### 旧 liveness integration 历史载体

- [ ] 重新确认 `/home/xp/src/ghc-api-proxy-py-integrate-liveness` 仍为 `integrate/260806-session-liveness@8e9aef69cc8606c4ca25286da617da8fc74d5c55`、clean，且其 stable patch-id仍等于 reviewed liveness source range及 main liveness提交。
- [ ] 移除 worktree `/home/xp/src/ghc-api-proxy-py-integrate-liveness`。
- [ ] 删除 branch `integrate/260806-session-liveness`。

### systemd source 与 integration 载体

- [ ] 重新确认 `archive/260807-systemd-runtime == 49fb1988621bba4356e7a5039a6994c2e6d19604`，且 `/home/xp/src/ghc-api-proxy-py-systemd` 仍为 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`、clean；current Implementation 与 systemd Plan仍记录 main `cf53334…` 的 main-side gates已通过。
- [ ] 重新确认 `/home/xp/src/ghc-api-proxy-py-integrate-systemd` 仍为 `integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef`、clean，且 `fe9c203…` 与 main `cf53334…` 的 stable patch-id仍同为 `eab37d38b63730f895be3e55fd256f0547209630`。
- [ ] 移除 worktree `/home/xp/src/ghc-api-proxy-py-systemd`。
- [ ] 删除活动 branch `feat/systemd-cgroup-runtime`；保留 systemd archive ref。
- [ ] 移除 worktree `/home/xp/src/ghc-api-proxy-py-integrate-systemd`。
- [ ] 删除 branch `integrate/260807-systemd-runtime`。

## 保留清单

### 永久／长期评审证据

- [ ] 保留 `archive/260806-anthropic-responses-reasoning@d90c90d7b52533e0dc5bd8baadc4c387a8511c3b`。
- [ ] 保留 `archive/260807-anthropic-responses-reasoning-cardinality@b876e626dda821b267535b0bcffc9d81ced12763`。
- [ ] 保留 `archive/260807-anthropic-responses-liveness@f27a8c04cd3470bd50d7194a30371ca5404f727e`。
- [ ] 保留 `archive/260807-anthropic-responses-request@fdd2f75fcec11e592b04f2686c4664262052a964`。
- [ ] 保留 `archive/260807-systemd-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`。
- [ ] 保留主 worktree `/home/xp/src/ghc-api-proxy-py` 与 branch `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`；不得把本报告当作清理主树 WIP 的授权。

### Happy integration 与其 reviewed source 载体

- [ ] 保留 `/home/xp/src/ghc-api-proxy-py-integrate-happy`，branch `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443`。它是 carrier → nonstream → stream parser → route／smoke 的冻结四提交组合载体，当前不是 main ancestor；后续仍需按该 exact chain 做评审消费与 main-side replay。
- [ ] 保留 `/home/xp/src/ghc-api-proxy-py-carrier-v2`，branch `feat/reasoning-carrier-v2@8301ee938601ad86c7f72d313abc6c976a74b2a9`。当前无对应 archive ref，且仍承担项目主 v1 producer、direct Messages strip与后续 malformed／foreign／echo边界追溯。
- [ ] 保留 `/home/xp/src/ghc-api-proxy-py-response`，branch `feat/responses-anthropic-nonstream@7ddf17364d97349638d44352bbd9a9b025723ccc`。当前无对应 archive ref，仍承担 non-stream checkpoint、carrier-first组合依赖与后续 response边界追溯。
- [ ] 保留 `/home/xp/src/ghc-api-proxy-py-stream-parser`，branch `feat/responses-stream-parser@73a6aa114647440262691651cd17e9127785c75a`。当前无对应 archive ref，仍承担后续 grammar／framing／strict lifecycle／sequencer接线追溯。
- [ ] 保留 `/home/xp/src/ghc-api-proxy-py-route-policy`，branch `feat/anthropic-responses-route-policy@84a22c07db3923768db44a1314e5ae6d5aed2e98`。当前无对应 archive ref，仍承担后续 route handler／transport／History接线追溯。
- [ ] 上述五个 worktree 审计时均 clean，但 **clean 不是可清理充分条件**；它们的提交尚未进入 current main，且 source refs尚未由精确 archive refs替代。

### Happy 后继

- [ ] 保留 `/home/xp/src/ghc-api-proxy-py-nonstream-usage`，branch `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857`。它是以 happy tip `7e4b642…` 为 parent 的活动后继，当前不是 main ancestor，仍需独立 review、在 happy 链之后消费并执行 main-side gate；当前也没有对应 archive ref。

## 事实性发现

未发现 archive 指错 reviewed HEAD、目标 feature worktree dirty、foundations／systemd integration 未落 main却被误列可清理，或 happy/source worktree可安全删除的证据。

[major] `docs/agents/anthropic-responses-bridge/README.md:24-34,195-209,243,274`、`docs/agents/service-cutover/plan.md:8,31-39,525-540` — README导航快照与 service-cutover Plan仍把 foundations／systemd写成尚未进入旧 main，并要求再次回放；current Git与已同步的 `implementation.md`、systemd Plan、readiness均确认四片已进入 `main@cf53334…`，对应 archive已建立且 main-side gates已通过 — 后续执行者若沿这两个 current段落会重复回放已落地提交或使用虚假前置状态 — 该问题不改变本文基于 current Git、current Implementation与合并态评审形成的机械清理分类，但须在继续 happy-path／deployment执行前同步并复评这两份文档；本轮唯一写入授权不允许代修。

## 结构怪味扫描

- `docs/agents/anthropic-responses-bridge/README.md:24-34,195-209,243,274` — **易变状态复制到导航文档并漂移** — 本轮不修，仅登记为上述 major；后续应让导航只指向 `implementation.md` 的 current状态，或在同一checkpoint原子同步。
- `docs/agents/service-cutover/plan.md:8,31-39,525-540` — **部署 Plan复制代码回放状态并成为第二真相源** — 本轮不修，仅登记为上述 major；后续同步为“代码已进 main、未安装／未部署／`NO_CUTOVER`”，保留运行态边界而移除重复回放动作。
- 本报告的 Git判据 — **squash后 ancestor关系与语义落地关系不同** — 本轮已修：不使用 `git branch --merged`，而采用 archive精确对象、clean状态、integration→main stable patch-id、merged-state接缝证据与 main-side gate组合判据。

## 方法反思

1. **更好的内部替代方案**：`git branch --merged main` 无法识别 squash／replay对象；当前组合判据比 ancestor-only更准确，也保留 reviewed source与main提交的身份分层。
2. **判据判别力**：所有拟清理worktree与所有拟保留worktree都为 clean，故 clean-only会假绿；happy/source与usage作为反向样本证明“clean但仍承载未落main后继”必须保留。
3. **成熟第三方方案**：本轮完全使用Git原生 worktree porcelain、refs、object IDs、first-parent拓扑与stable patch-id，没有自制branch数据库或复制对象。

## 主观建议

无。本文只给出机械清理清单与保留清单，不建议扩大清理范围，也不建议删除任何 archive ref。

## 最终结论

可清理：foundations 的 cardinality／liveness／request feature worktrees与活动 branches、共享 foundations integration、旧 liveness integration、systemd source与systemd integration；执行时按本文每组前置等式重新 gate，禁止 force／discard。

必须保留：全部五个 archive refs、main worktree／branch、happy integration、carrier v2／nonstream／stream parser／route policy四个 source worktrees与branches，以及 non-stream usage后继。清理这些保留对象会删除尚未进入 main 的活动组合／后继载体，当前没有等价 archive coverage。
