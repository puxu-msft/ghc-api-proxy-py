# Bridge successor 回放现场只读恢复审计

- **评审范围**：只读恢复 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、successor worktree `/home/xp/src/ghc-api-proxy-py-integrate-successor` 的 `integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f`、线性 semantic `04bdfcbf75bfa7e9709d55869c70106c49146db6` → route `088d66d3f12bd39be7ce7f61877336f490e7dbdb` → block `c43db35a7a5851225b55ce31b8edbec2cf90917f`，消费 `docs/tmp/260807-final-successor-replay-gate.md`、`docs/tmp/260807-review-code-bridge-successor.md` 与 `docs/tmp/260807-verify-bridge-successor.md`，并在仓库外临时 index／object directory 中从四文档 current bytes 合成 checkpoint 后逐片回放。未 cherry-pick，未修改 main ref、真实 index、四文档、代码、服务、数据或 archive refs；唯一写入为本报告。
- **总体 verdict**：**可进入下一阶段。当前为 0 blocker／0 major／0 minor。四文档 current-byte checkpoint 已明确闭合；其后 semantic → route → block 三片只读逐步回放全部通过。** 该 verdict 只恢复回放现场并证明 checkpoint 后三片仍适用，不表示四文档或代码已经提交到 main、main-side gates 已运行、archive refs 已建立、完整 Responses stream 为 `PASS`、部署完成或 cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **四文档 checkpoint 结论**：Acceptance `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001` 与 Readiness `ad36f43aea165b2a8cb1d6eaa6bbc08a0eca75278e6c7b6f1b623a514e44fd0a` 已分别有精确 current-byte `0 blocker／0 major` 复评。Implementation current `ccdf6edf83aa9703a6a95a74801e11e433df8248d76d7b9f077ab18664d5ffe2` 与 Systemd Plan current `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e` 已相对各自旧证书独立复核 current 增量：两者均一致切换到 rebuilt code-only `862f4cfa… → 2ec0cb8…`，旧 `91f95f7… → 0a93e7f…` 仅作历史 provenance并明确禁止回放，未发现 blocker、major或执行路线冲突。因此四份 current bytes 均达到 0 major，合成 checkpoint tree 为 `d5f12078da17d55a3e12bac2037b5c5f79c3cb65`。该 tree 仅是只读临时对象，不是 main commit。
- **successor 结论**：三片 parent、路径、preimage、stable patch-id、result blob与 reviewed source tip逐项闭合；每片 synthetic post-tree相对对应 integration commit tree只多四份 checkpoint文档，最终主树现场与successor worktree均未改变。
- **archive 结论**：reviewed source targets固定为 semantic `f5bca39ac582911b61d278fd678ec9298ad0c08e`、route `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`、block `e506bf87318424e4075b6422772ee0c7e9b8694a`。当前 `refs/heads/archive/` 对三者的精确指向计数均为0。每个 archive只能在对应slice真实进入main且该片main-side gate通过后建立，本轮未创建任何ref。

## 双视角覆盖证据

### 机械核对

- 每次承载结论的 shell 均在同一调用内验证物理 cwd与Git top-level为`/home/xp/src/ghc-api-proxy-py`、分支为`main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`，并验证真实index无staged paths。
- Successor worktree物理root、branch与完整HEAD分别为`/home/xp/src/ghc-api-proxy-py-integrate-successor`、`integrate/260807-bridge-successor`、`c43db35a7a5851225b55ce31b8edbec2cf90917f`；回放前后tracked／untracked status均为空。
- Git提交图严格为`80bc8f2… → 04bdfcb… → 088d66d… → c43db35…`，范围内恰有3个non-merge commits。三个唯一parent分别精确为上一节点。
- 主树tracked WIP精确为四份目标文档；真实index为空。其他既有untracked `docs/tmp/**` 与 `verification/**` 未进入临时checkpoint，也未被修改。
- Acceptance current hash与`docs/tmp/260807-review-acceptance-empty-reasoning-r2.md`的0 major证书闭合；Readiness current hash与`docs/tmp/260807-review-readiness-current-r8.md`的0 major证书闭合。
- Implementation旧R8只绑定`305e2d6…`，Systemd Plan旧R8只绑定`5655958…`，两者不能外推到current bytes。本轮完整通读current文件并扫描全部执行入口，独立验证current路线统一为code-only `862f4cfa… → 2ec0cb8…`，旧`91f95f7… → 0a93e7f…`只在历史、禁用与重建说明中出现；Git又独立确认code-only两片线性且均不修改Plan。因此两份current bytes均为0 blocker／0 major。
- 临时index使用仓库外`/tmp/ghc-successor-resume.*`目录及独立object directory，以`main@80bc8f2…` tree初始化，再仅加入四份current文档。合成checkpoint tree为`d5f12078da17d55a3e12bac2037b5c5f79c3cb65`；四份文档的SHA-256与Git blob已冻结并在三片前后保持不变。
- Slice S1 semantic包含2条路径，stable patch-id为`4e7b96c163311c775ad68b95057195c5a5f66202`。应用前两条blob均等于`80bc8f2…`，apply check与apply通过，应用后均等于`04bdfcb…`及reviewed source `f5bca39…`；synthetic post-tree为`9a4ef190989bfc7a30c83172296a1fa5d88b9a68`，相对`04bdfcb…^{tree}`只多四份文档。
- Slice S2 route包含10条路径，stable patch-id为`d990e5457fc1fa29392cf80f5c71957e98a1154b`。应用前全部blob／absence等于`04bdfcb…`，apply check与apply通过，应用后全部等于`088d66d…`及reviewed source `dd376d6…`；synthetic post-tree为`ca0506db727f822ad7b0c253feee7a027d51fc8f`，相对`088d66d…^{tree}`只多四份文档。
- Slice S3 block包含3条新增路径，stable patch-id为`b44e8ca968ecaf63132da5d20ac432e2ab41ef2b`。应用前三条均不存在，apply check与apply通过，应用后全部等于`c43db35…`及reviewed source`e506bf8…`；synthetic post-tree为`5847e04b9e465828071a02740f076216ee7bb2ae`，相对`c43db35…^{tree}`只多四份文档。
- 三片路径数与最终 replay gate记录的2／10／3独立一致；stable patch-id也逐片一致。每条result blob另与integration commit及source tip双重相等，未以patch-id单独自证。
- 回放前后main ref与HEAD保持`80bc8f2…`，真实index SHA-256保持`663fbf24e628c1eec203cd2c5ef46c4a1c697e050faff949539f06b179c85cfc`，完整status输出hash保持`98760c13410be49bed0d1f8b37019c7e766f4e7a90ba07b856c70893b16e8d16`；successor仍为`c43db35…`且clean。临时目录在成功后清理。

### 第一人称执行

- 作为checkpoint执行者，我先逐份走“current hash → current review或本轮独立current增量复核 → 0 major”链。旧四文档审计曾因Implementation缺current证书而正确阻断；本轮没有沿用该旧结论，也没有拿旧R8覆盖新bytes，而是重新验证Implementation与Plan current执行路线后才明确四文档checkpoint闭合。
- 作为semantic回放执行者，我要求当时main的两条目标path仍等于`80bc8f2…`preimage，只应用`04bdfcb…`。真实执行后必须运行semantic parser／reasoning parity main-side gate；通过后才允许建立指向`f5bca39…`的archive并进入route。
- 作为route回放执行者，我要求当时main的10条目标path等于`04bdfcb…`postimage，只应用完整route squash`088d66d…`。真实执行后必须运行ASGI route／hooks／header main-side gate；通过后才允许建立指向`dd376d6…`的archive并进入block。
- 作为block回放执行者，我要求三个目标path仍全部不存在，只应用`c43db35…`。真实执行后必须运行parser→typed delivery／terminal／single-writer main-side gate；通过后才允许建立指向`e506bf8…`的archive。
- 作为最终验收者，我不会把只读临时index回放写成真实main已回放，也不会把successor scoped `PASS`外推为完整Responses stream产品`PASS`。真实三片进入main后仍须执行merged-state smoke、全仓pytest、Ruff、Pyright、最终result blob对账及绑定最终main HEAD的新merged review／verification。
- 任一真实slice的identity、preimage、测试、lint、type或独立oracle失败时必须停在该片，不建立该片archive，也不继续后片；不得用最终整体验证掩盖前片失败。

## 事实性发现

未发现问题。四文档current-byte内容门、successor拓扑、三片preimage／paths／patch-id／result blobs、reviewed-source provenance、archive前置状态与只读边界均闭合。

## 主观建议

无。

## 结构怪味与方案反思

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `docs/agents/anthropic-responses-bridge/implementation.md:12,38,71-89,196,212,234` | current systemd执行路线在多处复述，容易让旧integration身份残留为可执行指令 | 本轮逐入口扫描并确认全部统一到code-only `862f4cfa… → 2ec0cb8…`，旧链均明确禁用；当前不修文档，后续identity变化仍须全文传播并重新绑定current hash |
| `docs/agents/systemd-runtime/plan.md:8,99,195,300,336,381,426` | living Plan同时保留旧证据与current路线，机械关键字扫描会产生历史命中，执行者若不模拟语义可能误选旧链 | 本轮按第一人称执行区分历史provenance与imperative；current唯一执行路线闭合，旧链明确禁止cherry-pick／回放／采用old Plan postimage |
| `docs/tmp/260807-audit-four-doc-checkpoint.md` | 集合审计的旧blocker若脱离绑定hash阅读，可能被误当成永久阻断 | 本轮保留旧审计为当时正确证据，并明确以current四hash重新裁定；不覆盖或改写历史报告 |
| 三片integration commit tree与四文档checkpoint后的synthetic tree | 若仍要求全树OID等于integration tree，会把正确的文档checkpoint误判为冲突 | 本轮使用逐path preimage／result blob与“相对integration tree只多四文档”的判据，不要求全树OID相等 |

- **更好的内部替代方案**：保留semantic／route／block三个边界并逐片gate，优于压成一个不可归因提交；临时index＋独立object directory优于修改真实index或worktree。
- **判据判别力**：逐片preimage、apply check、result blob、source-tip、只多四文档、真实index hash与status hash共同区分正确与错误状态；没有只依赖单一patch-id或现成successor tree。
- **成熟第三方方案**：本轮是Git对象与文档证据链审计，Git原生临时index、alternate object directory、patch-id与tree/blob接口已是适合的成熟方案，无需自建补丁引擎。

## 结论

本轮为 **0 blocker／0 major／0 minor**。四份current living docs已明确形成current-byte 0 major checkpoint；在该合成checkpoint后，semantic `04bdfcb…`、route `088d66d…`、block `c43db35…`依次通过全部只读适用性门，且每片结果与reviewed source精确闭合。主树ref、真实index、既有WIP与successor worktree未被回放修改，archive refs仍未创建。

**允许后续按 `04bdfcb… → 088d66d… → c43db35…` 在真实main逐片执行，但每片仍须重新验证当时preimage并完成对应main-side gate；通过后archive分别精确指向 `f5bca39…`、`dd376d6…`、`e506bf8…`。本报告不执行或替代这些真实main动作。**
