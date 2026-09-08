# Current main → happy replay 最终门禁复核

- **评审范围**：只读复核 `/home/xp/src/ghc-api-proxy-py` 的 current `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`、`docs/tmp/260807-audit-happy-replay.md`、`docs/tmp/260807-review-code-happy-path-r2.md`、`docs/tmp/260807-verify-happy-path.md`、`docs/tmp/260807-audit-usage-replay.md`，以及 `/home/xp/src/ghc-api-proxy-py-integrate-happy` 的 `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443`。本轮不重做代码 review、不运行产品测试、不执行 cherry-pick、不创建或移动 ref；只确认 current main HEAD／tree 仍满足 frozen preimage、integration tip clean、四提交顺序、usage 依赖、archive targets 状态及 living docs checkpoint 后的执行门。
- **总体 verdict**：**可进入下一阶段。完成已获 0 blocker／0 major 放行的 living docs checkpoint 后，可立即按 `1ed13ad → 80b3cfa → c950912 → 7e4b642` 回放 happy 四片。** 本轮为 0 blocker／0 major／0 minor。该结论只放行真实逐片回放及每片 main-side gate，不表示 checkpoint 已提交、happy 已进入 main、usage 已进入 main或完整 bridge 产品已 `PASS`。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：每个 load-bearing shell 调用均在同一次调用内验证 main physical root、`main`、精确 HEAD，happy／usage physical root、branch、精确 HEAD与 clean status。Git object probe确认 current main commit tree为 `fa084a0790a2fab84ac8e59a641fc37842474edb`；以 `git cat-file -e`、`rev-parse` 与工作树 `hash-object` 对 frozen base `6a00f6f…` 到 happy tip的 16 个 changed paths逐项复核，7 个既存路径满足 base blob＝main HEAD blob＝main工作树 blob，9 个新增路径在三侧均不存在。四片由完整 `rev-list`、`--no-merges`／`--merges`互补计数及逐提交单 parent等式交叉核对为4个线性non-merge commits。Usage HEAD `aca3ced…` 的直接 parent精确为 `7e4b642…`。四个活动source refs均精确指向reviewed HEAD，四个目标archive refs均不存在。
- **双视角覆盖证据——第一人称执行模拟**：作为回放执行者，先提交已放行的三份 living docs checkpoint，不夹带本报告或其他 `docs/tmp/**`；随后重新 gate current main与无 cherry state，消费现有clean happy integration链而不是从source refs重建第二条链。逐片回放时必须执行既有 audit冻结的blob／定向／交叠／全仓／Ruff／Pyright gate并在通过后把archive指向reviewed source HEAD；任一片失败即停止。只有四片全部进入main且逐片gate通过后，才进入直接后继usage `aca3ced…`。
- **写入边界**：唯一持久化写入为本报告 `docs/tmp/260807-final-happy-replay-gate.md`。本轮未修改、暂存、提交、stash、restore或清理既有main WIP，未修改integration／usage worktree，也未创建、移动或删除任何ref。

## Current main preimage

现场固定为：

- `HEAD == refs/heads/main == cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。
- Commit tree为 `fa084a0790a2fab84ac8e59a641fc37842474edb`，与 happy replay audit冻结的current-main起始tree一致。
- `CHERRY_PICK_HEAD`、`MERGE_HEAD`、`REVERT_HEAD`均不存在，index无staged paths。
- 对 `6a00f6f…..7e4b642…` 的完整16-path并集，7个既存路径逐blob满足 frozen base＝current main HEAD＝current main工作树；9个新增路径经object existence probe确认三侧均不存在。
- Main工作树存在既有living docs与临时报告WIP，但它们不与上述16个代码／测试preimage paths重叠。本结论不把整个main工作树误写为clean。

因此，current `main@cf53334…` 的 HEAD tree和现场工作树仍满足 happy四片的冻结preimage；`260807-audit-happy-replay.md` 的临时index无冲突模拟没有因current代码路径漂移而失效。

## Happy integration tip 与四提交顺序

Integration现场为clean `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443`，tree为 `9099d52562c7066777d5c9bd01278993971867fd`。从 frozen base起的唯一顺序为：

| 顺序 | Commit | Parent | Stable patch-id | Subject |
|---|---|---|---|---|
| 1 | `1ed13ad7e19385b9f86a1cd292547438f6137179` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `67e66ccc765074c98599c6381509e710280fb7e0` | `feat: add versioned reasoning carrier codec` |
| 2 | `80b3cfade000cd9e1626074d14b1f9c9d5294891` | `1ed13ad7e19385b9f86a1cd292547438f6137179` | `c947d52bd902b1140211952454a323b7501307df` | `feat: convert Responses JSON to Anthropic messages` |
| 3 | `c950912ad739f85c39397ab0f2c4d25b82dddcb7` | `80b3cfade000cd9e1626074d14b1f9c9d5294891` | `35c3332dadede958158df47bd102caf179ce9599` | `feat: assemble Responses stream events` |
| 4 | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | `c950912ad739f85c39397ab0f2c4d25b82dddcb7` | `6fd013e08f7b1320f666c9cbae1f001f73cfb808` | `feat: add typed protocol route policy` |

计数口径为 `6a00f6f…..7e4b642…`：完整rev-list为4，`--no-merges`为4，`--merges`为0；逐提交均恰有一个parent且首尾精确相接。不得交换顺序、拆用source refs或从四个source worktree重建另一条integration链。

## R2／verify／audit 对账

- `260807-review-code-happy-path-r2.md` 精确绑定current integration tip `7e4b642…`，为0 blocker／0 major／0 minor；它关闭了R1的同源carrier expected major，并明确四片可按固定顺序回放。
- `260807-verify-happy-path.md` 绑定amend前 `d78b3cdc…`，只证明其声明的happy primitives／pure-path范围；R2通过current amend的静态Spec vector与目标正控把该旧HEAD证据正确接到 `7e4b642…`，但完整bridge仍为 `UNVERIFIED`。
- `260807-audit-happy-replay.md` 绑定 `main@cf53334…` 与 `7e4b642…`，用临时index从current main逐片三方应用，四片均无unmerged entry，逐片patch-id／changed blobs相等，最终happy路径blobs等于integration tip。本轮独立preimage重检确认该模拟的起始代码tree未漂移。
- `260807-audit-usage-replay.md` 绑定usage `aca3ced6e38efabf13ffe43d5935697801c74857`，其直接parent为 `7e4b642…`，stable patch-id为 `e53b2de91c45471e405af6890eb8c245fa481b5d`。因此usage只能在happy四片全部进入main并逐片通过main-side gate后回放，不能提前摘取，也不能把usage candidate-side PASS写成future-main PASS。

## Usage 依赖

Usage worktree现场为clean `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857`，直接parent精确为happy tip `7e4b642be8bd526d8f20f3f8d7e2d7848278a443`。其三个preimage blobs分别来自happy nonstream／smoke结果，因此“happy先、usage后”是提交内容合同，不只是流程偏好。

**本门不放行提前回放usage。** 执行顺序固定为：living docs checkpoint → happy四片逐片回放与逐片main-side gate／archive → usage回放与usage main-side gate／archive → route wiring。

## Archive targets

四个archive refs现场均不存在；这符合“对应integration片真实进入main且该片main-side gate通过后才归档”的合同。活动source refs未漂移，未来archive必须指向reviewed source HEAD，而不是integration commit或main replay commit：

| Slice | 活动source ref | Reviewed source HEAD | 目标archive ref | 当前状态 |
|---|---|---|---|---|
| Carrier v2 | `feat/reasoning-carrier-v2` | `8301ee938601ad86c7f72d313abc6c976a74b2a9` | `archive/260807-anthropic-responses-reasoning-carrier-v2` | absent；Slice 1 gate后指向source HEAD |
| Non-stream | `feat/responses-anthropic-nonstream` | `7ddf17364d97349638d44352bbd9a9b025723ccc` | `archive/260807-anthropic-responses-nonstream` | absent；Slice 2 gate后指向source HEAD |
| Stream parser | `feat/responses-stream-parser` | `73a6aa114647440262691651cd17e9127785c75a` | `archive/260807-anthropic-responses-stream-parser` | absent；Slice 3 gate后指向source HEAD |
| Route policy | `feat/anthropic-responses-route-policy` | `84a22c07db3923768db44a1314e5ae6d5aed2e98` | `archive/260807-anthropic-responses-route-policy` | absent；Slice 4 gate后指向source HEAD |

Archive缺席不是阻断项；提前创建或指向integration／main commit才会破坏reviewed-source provenance。

## Living docs checkpoint 与立即回放门

`docs/tmp/260807-review-living-after-main-replay-r2.md` 绑定current `main@cf53334…` 下三份living工作树bytes：

- `docs/agents/anthropic-responses-bridge/implementation.md` SHA-256 `60e09d3b6310361dad0025e88802f3774d0dc4ff8d264bdabe483bfc7635ba2a`。
- `docs/agents/systemd-runtime/plan.md` SHA-256 `6646cb727e1bc92ce02ec2bd76f825bb8c9b7d190dbd907ed9f9a6e776f156e6`。
- `docs/agents/service-cutover/readiness.md` SHA-256 `a8abccf4ffd3168c5b3eaa5531de24f24f423948d72235a383e7a220e8101270`。

该R2为0 blocker／0 major／1 minor，并**明确放行三份current living docs作为同一checkpoint提交**。唯一minor是Readiness内嵌Implementation hash仍指向上一稳定bytes；报告已裁定它不反转foundations／systemd已进入main、happy／usage未进入main、产品 `UNVERIFIED`、`NO_CUTOVER`及living不收口六项核心状态。

因此本轮的唯一前置动作是完成这三份living docs checkpoint；checkpoint后**无需新增代码review、无需重跑integration侧verify、无需等待archive预创建，可立即开始happy Slice 1真实回放**。Checkpoint提交必须只包含该次已裁决的living docs路径集合，不得夹带本报告、其他 `docs/tmp/**` 或并行WIP；实际提交前仍须按checkpoint报告复核staged identity。若三份living bytes、current main HEAD、happy tip或任一archive／source ref在执行前漂移，本final gate立即失效并须重新核对。

## 事实性发现

未发现问题。审计范围内blocker 0、major 0、minor 0。Current main HEAD／tree仍满足preimage，integration tip clean，四提交顺序与usage依赖稳定，archive targets尚不存在且必须在逐片gate后指向reviewed source HEAD。

## 主观建议

无。执行者应直接消费现有integration链与既有逐片main-side gates，不重做代码review，不从source refs重组，也不把局部checkpoint外推为完整产品 `PASS`。

## 结构怪味扫描

- `main` 的 commit tree与dirty living工作树并存——**整体clean与目标path preimage容易混淆**——本轮按16个happy路径逐项核对HEAD与工作树，不以全树dirty否决不相交的代码回放，也不把局部clean误写为全树clean。
- `verify-happy-path.md`绑定amend前HEAD，而R2绑定current tip——**旧verify与current放行身份分层**——本轮只把旧verify用于其声明的pure-path范围，由R2 current-byte复评和本轮对象门完成current连接，不直接把旧HEAD PASS冒充current证明。
- Route integration片比route source多一份happy smoke——**source range patch-id与integration commit patch-id不可混用**——继续以integration patch-id验证整片，以reviewed source HEAD只验证route两个source blobs与归档target。
- Usage直接修改happy产生的三个blobs——**后继依赖可能被流程文字弱化**——本轮以direct parent和preimage blobs固定为硬顺序，禁止提前摘取usage。

## 方法反思

1. **更好的内部替代方案**：若只复述旧audit，无法证明current工作树在报告之后没有漂移。本轮重新读取Git对象、工作树blob、refs与worktree status；不重做代码review，但独立验证所有会使旧verdict失效的身份条件。
2. **判据判别力**：首次missing-path探针使用的`rev-parse`失败输出不适合作为最终不存在性证据，已废弃该输出并改用`git cat-file -e`重跑；最终判据明确区分7个存在且三侧blob相等、9个三侧均不存在，防止查询自身造成假绿。
3. **成熟第三方方案**：全部使用Git原生commit／tree／blob／ref／patch-id primitives与现有review／verify报告，没有手写merge算法、补丁解析器或另建状态数据库。

## 最终结论

**0 blocker／0 major／0 minor。完成已获0-major放行的三份living docs checkpoint后，可立即按 `1ed13ad → 80b3cfa → c950912 → 7e4b642` 回放current main。** 每片必须在进入下一片前完成既有main-side gate并把archive精确指向 `8301ee9…`、`7ddf173…`、`73a6aa1…`、`84a22c0…` 对应reviewed source HEAD。四片全部完成前不得回放usage `aca3ced…`；四片与usage完成也不表示route wiring、完整Acceptance、部署或cutover已经通过。
