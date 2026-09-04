# systemd-next 新 main 重建只读审计

- **评审范围**：current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 的 working-tree `docs/agents/systemd-runtime/plan.md`，SHA-256 `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`；old prepared integration `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 的两提交 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` → `0a93e7f18f197bf8a2395eaaf20afda446f92d6b`；reviewed source `feat/systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5` 与 `feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`。本轮只判断四 docs checkpoint 后应直接回放旧提交还是从新 main 重建两个 squash commits，并冻结必须保留的 Plan 状态和 source 路径；未修改 Git index、HEAD、branch、ref、候选代码或四份 living docs，未执行 cherry-pick、commit、测试、unit 安装、manager 操作、部署或 cutover。唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段，但只允许下述唯一安全策略。** 四份 current living docs 先形成经过各自 current-byte `0 blocker／0 major` 证明的 checkpoint；随后以该 checkpoint 后的 actual new `main` 为 base，重新构造两个代码 squash commits，顺序保持 S3 graceful → S4 installer，并明确排除 old integration 两提交中的 `docs/agents/systemd-runtime/plan.md` patch。禁止直接 cherry-pick `91f95f7…` 或 `0a93e7f…`，也禁止在冲突处理中采用 old Plan postimage。每片重建后执行该片 main-side gate，失败即停；Plan 只从 checkpoint bytes 向前做 fresh living update，不从 old integration 反向合并状态。
- **blocker 数**：0。
- **major 数**：0 个开放 major。直接回放的 Plan 冲突是已识别并由唯一策略排除的 major 风险，不是允许带入下一阶段的 finding。
- **minor 数**：0。
- **0-major 唯一策略**：**four-docs checkpoint → 从 checkpoint 后 new main 重建 S3 code squash → S3 main-side gate → fresh Plan living update／checkpoint → 从当时 main 重建 S4 code squash → S4 main-side gate → fresh Plan living update／checkpoint。** 两个 code squash 均不得携带 old Plan patch；若执行时 main、四 docs、source refs、old integration identity、路径集合或适用性漂移，本 verdict 自动失效并停止重建。

## 双视角覆盖证据

### 机械核对

- 每个承载结论的 shell 调用均在同一次调用内固定物理 root `/home/xp/src/ghc-api-proxy-py`、cwd、`main` 分支、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`，并固定 old integration tip `0a93e7f…`。主树真实 index 在模拟前后均为 0 staged paths。
- Old integration 图严格为 `80bc8f2… → 91f95f7… → 0a93e7f…`。第一提交修改 10 个路径，第二提交修改 4 个路径；两者都修改 `docs/agents/systemd-runtime/plan.md`。
- Plan 内容身份不同：`main@80bc8f2…` commit blob 为 `ae73fdf88e104ff1f256e47fb8a51a02713a9834`，current working-tree blob 为 `0648659099df224c6bfc53106fa2992a6657b47c`，第一片 postimage blob 为 `8a57ce55db7ae31432ac2512e2b07c2227227d1b`，old tip postimage blob 为 `a38ca28bd80bb3b35672332de2905e6a9f8b5356`。Current Plan 不是 old integration 的未变 base，也不是任一 old postimage。
- 以 current Plan 为 ours、各 old commit parent Plan 为 base、对应 commit Plan 为 theirs，GNU `diff3 -m` 独立模拟得到：第一片返回 1、产生 11 个冲突区；第二片返回 1、产生 10 个冲突区。Git `merge-file` 对第一片也返回 11 并产生 11 个冲突区。两种实现一致否定“Plan 可无冲突回放且自动保持 current bytes”。
- 正常 `git cherry-pick` 在这些重叠 hunk 上应停下要求解决冲突，因此不是“静默覆盖”；但若执行者使用 `--theirs`、整文件取 old postimage，或按 old Plan patch 手工重放，就会覆盖／回退 current living 状态。故“不会静默覆盖”不等于“可以直接回放”。
- 在独立临时 index 中，从 `80bc8f2…` tree 依序应用两片**排除 Plan**的 binary patch，两个 `git apply --cached --check` 与 apply 均通过，真实 index未改变。第一片 code-only post-tree 为 `ee9b885f7dc7d89c48c32df6553acbba80863c99`；第二片 code-only post-tree 为 `8ff3fbab24eaf02fbc1f14c68f5286e15e187d81`。这证明“从新 main 重建、排除 old Plan patch”在当前 base 可机械实施；不预先证明未来 checkpoint 后 main 仍相同，执行时必须重验。
- S3 source `865a5b7…` 的 parent 是 `80bc8f2…`，stable patch-id 为 `07220276eade068ed058d18e46eef93e2dc5a59c`；其与 old integration 第一片 `91f95f7…` 已有既有证据确认 patch-equivalent。S4 source `e16c2a7…` 的 parent 同为 `80bc8f2…`，stable patch-id 为 `1817c3326fa66137d0eb08417d68e0f669dacee8`；old integration 第二片是在 S3 parent 上的 reviewed adaptation，不能把 integration commit identity冒充 source provenance。
- Current Plan 已有精确绑定 SHA-256 `5655958e…` 的独立 `0 blocker／0 major／0 minor` 评审，但本报告不替代其余三份 living docs 的 current-byte checkpoint门。四 docs 必须在执行时分别具备精确 hash→独立 0-major report→checkpoint 的闭环；任一文档后续变化都须重新绑定，不沿用旧 verdict。

### 第一人称执行

- 作为直接 cherry-pick 执行者，我先摘 `91f95f7…` 时会在 Plan 的 11 个区域进入冲突状态；这已经不满足“可无冲突回放”。若为了继续而接受 old Plan 一侧，页首、状态看板、S3／S4、S6、disposition、验证边界和 kick-off 中的 current M2／review／replay 状态会被旧阶段文字替换；若仅凭肉眼逐段拼接，则无法给出 current bytes完全保留的机械 oracle。
- 作为重建执行者，我从四 docs checkpoint 后 actual new main 创建第一片，只取 S3 source／equivalent integration 的代码、部署文档与测试路径，不取 old Plan patch。第一片 main-side gate通过后，基于 checkpoint Plan fresh 更新 actual new commit identity和已通过 gate，再形成 living doc checkpoint；失败则停止，不进入 S4。
- 作为第二片执行者，我从第一片及其 gate后的 actual main 开始，只取 S4 reviewed source语义与 old integration中经过 S3-parent adaptation的非 Plan路径。第二片 gate通过后再 fresh 更新 Plan；不把 `0a93e7f…` 的 Plan postimage当作“最终状态”。
- 作为后续维护者，我继续区分 source provenance、rebuilt main commit identity与 old integration evidence。Archive target若后续建立，S3保存 reviewed source `865a5b7…`，S4保存 reviewed source `e16c2a7…`；不得改指 rebuilt squash或 old integration commit来替代 source身份。

## 事实性发现

未发现采用上述唯一策略后仍开放的 blocker、major或 minor。

直接 cherry-pick路线被事实性否决：它不是无冲突回放。该否决不推翻 old integration 已取得的 merged-state review `0 blocker／0 major`、独立 verify `PASS` 或其作为实现证据的价值；它只说明 old commits携带的 living Plan patch已被 current WIP超越，不能再作为新 main上的提交载荷。

## 必须保留并向前推进的 current Plan 状态

1. **文档身份与节奏**：Plan 保持 `LIVING`、继续且不收口；任何 0-major只绑定对应 bytes与 checkpoint，不预先放行未来 bytes。
2. **M1 current-main事实**：M1 已以 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 进入 current main；reviewed source仍为 `49fb1988621bba4356e7a5039a6994c2e6d19604`，不得重放 M1或把 archive provenance改成integration identity。
3. **S3／S4 source状态**：S3 source `865a5b7…` 与 S4 source `e16c2a7…` 均已取得独立 `0 blocker／0 major`、明确可 squash；S3配置优先级测试判别力和S4逐文件 atomicity仍是后补，不升级为本轮重建门，也不得丢失。
4. **Old M2证据边界**：`0a93e7f…` 的 merged-state review `0 blocker／0 major`、verify `PASS`与最终 replay gate `0 blocker／0 major`继续作为组合语义和路径适配证据；但 old tip不再是可直接回放载荷，旧报告也不能预先证明 rebuilt commit identity。
5. **执行顺序**：始终保持 S3 graceful在前、S4 installer在后；每片各自 gate，第一片失败不得继续第二片。不得把两片压成一个无法独立回滚的代码提交。
6. **Plan更新方向**：checkpoint bytes是唯一基线。重建代码提交不得携带 old Plan patch；每片 gate后仅写fresh forward update，记录actual rebuilt commit、main-side gate和下一动作，不恢复“待 review／verify”等已关闭旧状态。
7. **后续范围**：两片进入main后继续S5真实user-manager／cgroup smoke，S7双实例／rolling仍为后续独立切片；两片重建不使Plan收口。
8. **运行态边界**：任何文档checkpoint、重建commit或仓库gate都不表示unit已安装、user manager已激活、effective cgroup已验证、服务已部署、`localhost:4141`已cutover或完整产品`PASS`；不得执行未获另行授权的运行态动作。
9. **术语边界**：继续区分listener continuity、queued／unaccepted connection continuity与旧进程accepted connection drain；不得把单实例socket activation写成双实例／rolling或accepted connection迁移。

## 两个 reviewed source与重建路径

### S3 graceful timeout

- **Source**：`/home/xp/src/ghc-api-proxy-py-graceful-timeout`，`feat/systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5`，parent `80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- **重建时保留的非 Plan路径**：`contrib/systemd/ghc-api-proxy.service`、`docs/agents/deployment-systemd/README.md`、`src/app/cli.py`、`src/app/config/loader.py`、`src/app/config/settings.py`、`src/app/graceful_timeout.py`、`tests/smoke/test_systemd_units.py`、`tests/unit/test_cli.py`、`tests/unit/test_config_loader.py`。
- **明确排除**：source／old integration中的 `docs/agents/systemd-runtime/plan.md` patch。Actual Plan状态在该片gate后从four-docs checkpoint bytes fresh向前更新。

### S4 rootless user installer

- **Source**：`/home/xp/src/ghc-api-proxy-py-systemd-install`，`feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`，parent `80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- **重建时保留的非 Plan路径**：`contrib/systemd/install-user.py`、`docs/agents/deployment-systemd/README.md`、`tests/smoke/test_systemd_user_install.py`。在 S3 parent 上必须保留 old integration第二片已评审的timeout parity／text validation适配，但source provenance仍绑定`e16c2a7…`。
- **明确排除**：source／old integration中的 `docs/agents/systemd-runtime/plan.md` patch。Actual Plan状态在该片gate后从当时living checkpoint fresh向前更新。

## 唯一安全执行策略

1. 先完成四份living docs的current-byte独立0-major闭环并形成精确four-docs checkpoint；提交前后重验actual main、四个hash、index、tracked WIP和pathset。若该checkpoint未成立，不开始systemd重建。
2. 从checkpoint后的actual new main建立新的integration载体。不要以`91f95f7…`或`0a93e7f…`为cherry-pick输入；它们只作为语义、diff和provenance参考。
3. 构造S3 squash：只重放上列S3非Plan路径，核对source／equivalent patch语义、pathset和result blobs；提交后执行S3 main-side gate。失败即停。
4. S3 gate通过后，fresh更新Plan到actual S3 rebuilt commit与gate结果并形成living checkpoint；不得从old Plan三方“解冲突”。
5. 从当时actual main构造S4 squash：只重放上列S4非Plan路径，保留经S3-parent adaptation的timeout parity，并核对reviewed source语义未丢失；提交后执行S4 main-side gate。失败即停。
6. S4 gate通过后，fresh更新Plan到actual S4 rebuilt commit与gate结果并形成living checkpoint；随后才进入S5。对rebuilt两片重新取得适用的merged-state review／verification，不沿用old commit identity作最终放行。
7. 两片分别通过后，归档provenance目标仍为reviewed sources `865a5b7…`与`e16c2a7…`；archive ref命名和实际ref更新另行按既有流程决定，本报告不创建或移动ref。

## 主观建议

无。当前不是两种等价方案的偏好选择：直接cherry-pick已被两种三方实现的冲突证据否决；排除old Plan patch并从four-docs checkpoint后的new main重建，是唯一同时满足代码复用、living状态保真、逐片回滚和source provenance的0-major策略。

## 结构怪味与方案反思

- **结构怪味**：两个代码提交同时携带高频演进的living Plan，使代码patch可复用性与文档状态时效性耦合；`docs/agents/systemd-runtime/plan.md`当前已超越old integration postimage，导致实现仍可复用而提交对象不可复用。处置：本轮不改仓库结构；重建时把代码squash与fresh Plan checkpoint分离，长期可考虑把volatile execution state与稳定设计／source provenance拆成不同文档，但不得因此删除当前living信息。
- **内部替代方案**：直接cherry-pick后人工逐段解Plan冲突缺少“current bytes完全保留”的机械oracle，且容易把old review阶段文字带回；不采用。
- **判据判别力**：仅看`git apply`对非Plan路径为绿会漏掉Plan冲突；仅看正常cherry-pick会停也不能证明代码不可复用。本轮分别以三方冲突和code-only临时index apply覆盖两个方向，能够区分“旧commit不可回放”与“代码语义可重建”。
- **成熟第三方方案**：Git原生三方合并、`diff3`与临时index已足以给出机械结论，不需要自造merge算法或引入第三方迁移框架。

## 结论

**0 blocker／0开放major／0minor；唯一安全策略为four-docs checkpoint后从new main重建两个code squash commits。** Normal cherry-pick不会静默覆盖current Plan，而会分别遭遇至少11／10个三方冲突区；因此它不是可无冲突回放路径，任何采用old postimage的解冲突都会回退living状态。排除old Plan patch后，两片code-only补丁已在current base的独立临时index中按顺序通过apply check，证明重建可行。执行时仍须重验actual new main和所有identity，逐片gate，fresh更新Plan，并对rebuilt identities重新取得适用的merged-state review／verification。
