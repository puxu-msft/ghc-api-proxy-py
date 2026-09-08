# Systemd new-main rebuild checkpoint 后回放审计

- **评审范围**：只读审计主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume` 的 `integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54`。覆盖 `b91e58a… → 8cae6c2… → d3fabfa…` parent 链、逐片 pathset、main preimage／result blobs、current living WIP 重叠、stable patch／source provenance、checkpoint 后回放形状、main-side gate 与 reviewed-source archive targets。已知并现场读取 merged-state review `0 blocker／0 major` 与两份 exact-tip verification `PASS`；未重跑产品测试，未修改 Git index、HEAD、branch、ref、worktree代码或运行态。唯一写入是本报告。
- **总体 verdict**：**修复 living checkpoint 的 major 后可进入。候选代码链本身为 0 blocker／0 major，可在 checkpoint 后按 S3 → S4 精确逐片 squash；当前不得立即回放。** 当前 Readiness exact bytes 已为 0 major，但 Implementation exact bytes仍有2 major，Systemd Plan exact bytes仍有1 major，故 checkpoint 前置尚未闭合。两项文档复评归零并形成 checkpoint 后，按下文逐片门执行；任一门失败即停。
- **blocker 数**：0。
- **major 数**：1 个阶段门 major——current living checkpoint尚未取得全部 current-byte `0 blocker／0 major`。这不是候选代码缺陷；它阻止当前立即回放，但不推翻候选 review／verification。
- **候选代码 verdict**：`integrate/260807-systemd-rebuild-resume@d3fabfa…` 为 `0 blocker／0 major`，两份独立验收均为 `PASS`；其中一份记录3个 non-blocking minor。该局部 verdict不表示 unit已安装、真实 user manager／cgroup已验证、部署或cutover获授权。
- **报告自身状态**：本报告是 wrap-up／执行依据，按项目规则仍需主会话安排另一名独立 reviewer复核；本叶子 reviewer不调度其他 agent。

## 双视角覆盖证据

### 机械核对视角

- 每个采用为证据的 shell 调用都在同一次调用内验证物理 cwd、Git top-level与完整 `HEAD=b91e58a29324b11840002efc53ed6f869b800c39`。一次 blob-table调用被共享终端其他会话污染且没有本轮 nonce，已整组作废并以唯一前缀重跑，不纳入结论。
- 提交图严格为 `b91e58a29324b11840002efc53ed6f869b800c39 → 8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`；范围内恰有2个 non-merge commits、0个 merge commits。S3 subject为 `feat: configure graceful shutdown timeout`，S4 subject为 `feat: add rootless systemd user installer`。
- S3 pathset精确为9个非Plan路径；S4 pathset精确为3个非Plan路径。`docs/agents/systemd-runtime/plan.md` 在 base、S3与S4的blob OID均为 `a390efd0d2cd5393fa6d935f5c8c078a2d245253`。
- New-main逐片 stable patch-id分别为 S3 `26dcc6fbfffe0db7d3358728ff244fec36078be1`、S4 `412e73c47064720386c1075bfac0d3d8d08c6d26`；与旧 parent-adapted code-only两片 `862f4cfa…`／`2ec0cb8…`逐片相等，`git range-diff`两项均为 `=`。
- Source provenance分层核对：S3 reviewed source `865a5b7…` 的非Plan stable patch-id同为 `26dcc6…`，且其非Plan结果与旧S3 code-only片一致。S4 reviewed source `e16c2a7…` 的原始非Plan stable patch-id为 `861d8756f0120f7c32ef820a85be5cf8fc7ae463`；它在S3 parent上加入timeout parity／text validation适配后，旧S4 code-only片与new-main S4片才同为 `412e73…`。因此S4是“reviewed source语义＋已评审parent adaptation”，不得错误要求原始source patch-id等于回放片patch-id，也不得把adapted integration identity冒充source provenance。
- Current tracked living WIP精确为 `docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/service-cutover/readiness.md`、`docs/agents/systemd-runtime/plan.md`。New-main code-only 9＋3 pathset与它们的交集为空；historical Plan-bearing `91f95f7… → 0a93e7f…` 与current tracked living WIP的唯一交集为 `docs/agents/systemd-runtime/plan.md`。结论是：**current new-main载荷为 code-only且无living WIP重叠；只有旧链会撞Plan。**
- Current living内容身份与最新定向报告为：Implementation SHA-256 `10533f5d234d331bd92d7d5849f38964a3de1c5572a312b1f7f533514db134cb`，`260807-resume-review-implementation-current-r2.md` 为 `0 blocker／2 major`、不可checkpoint；Readiness SHA-256 `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8`，`260807-resume-review-readiness-current-r2.md` 为 `0 blocker／0 major`、可checkpoint；Systemd Plan SHA-256 `f5704171f674579b3865bf5466593411c08d4f70cff59b9e3ec4421cfbaefc80`，`260807-resume-review-systemd-plan-current-r2.md` 为 `0 blocker／1 major`、不可checkpoint。
- Reviewed sources `865a5b7…`与`e16c2a7…`均为有效commit，目前分别仅由活动feature ref指向；指向两者的 `refs/heads/archive/*` 数量均为0。现有systemd archive只有 `archive/260807-systemd-runtime → 49fb1988621bba4356e7a5039a6994c2e6d19604`。

### 第一人称执行视角

- 作为checkpoint执行者，我不能因候选代码已 `0 major／PASS` 就跳过living文档门。当前先修复Implementation的2项current-state major与Plan遗漏new-main merged-state review的1项major，对新bytes重新取得独立 `0 blocker／0 major`，再连同已放行Readiness形成精确checkpoint。若任一文档hash在checkpoint前漂移，旧报告不再覆盖新bytes。
- 作为S3回放执行者，我从checkpoint后的actual main开始，只消费 `8cae6c2…` 的9-path代码补丁，生成一个以当时main为parent的新单一语义squash commit；我不会regular merge、fast-forward整个integration tip，也不会把S4一起带入。S3 gate全绿后立即fresh更新并checkpoint Plan，再归档reviewed source `865a5b7…`。
- 作为S4回放执行者，我从“S3 squash＋S3 gate＋fresh Plan checkpoint”后的actual main开始，只消费 `d3fabfa…` 的3-path adapted补丁。`docs/agents/deployment-systemd/README.md` 的preimage必须是S3结果；两个新增文件必须仍不存在。S4 gate全绿后fresh更新并checkpoint Plan，再归档reviewed source `e16c2a7…`。
- 作为合并策略执行者，我不会在checkpoint前利用当前图上理论可行的fast-forward。Checkpoint必须先进入main，一旦如此，candidate tip与main自然分叉，FF不再成立；即使抢先FF，仍会绕过checkpoint、逐片gate和片间Plan checkpoint。Regular merge会把两条rebuilt commit identity一起保留在main ancestry并以一个merge动作跨过片间停止点，无法满足“每片独立squash、gate、fresh Plan checkpoint、独立回滚／archive”的冻结流程。
- 作为部署执行者，我不会把仓库squash、main-side gate或archive写成unit已安装、manager已加载、effective cgroup已验证、生产 `4141` 可接管或cutover获授权。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/systemd-runtime/plan.md` — current living checkpoint尚未闭合，当前不得立即开始S3回放 — Implementation当前SHA绑定报告为0 blocker／2 major；Plan当前SHA绑定报告为0 blocker／1 major；只有Readiness当前SHA为0 blocker／0 major — 先修复三项current-state传播问题，对各自新bytes重新取得独立0 blocker／0 major，再形成精确living checkpoint。Checkpoint提交后重新读取actual main HEAD，不能预填未来commit identity。

除该阶段门外，未发现候选代码链的blocker或major。Commit graph、pathset、Plan排除、new-main preimage、stable patch、source provenance、review／verification与archive targets均闭合。

## Checkpoint 后的精确逐片门

### Gate 0：living checkpoint

1. 再次固定主树物理root、`main`与当次HEAD；确认candidate branch仍精确指向 `d3fabfadfba57af6c2d63e543e3198444777df54`，且两级parent仍为 `8cae6c2…`、`b91e58a…`。
2. Implementation与Systemd Plan完成上述major修订，并对新SHA分别取得独立 `0 blocker／0 major`；Readiness若bytes仍为 `c1e8494…`可消费现有R2 verdict，若漂移则同样重评。不得用旧hash报告覆盖新bytes。
3. Checkpoint前重新枚举tracked／staged living WIP与candidate两片pathset。代码载荷交集必须为空；historical Plan-bearing链不得成为输入。禁止restore／stash／old Plan postimage覆盖living WIP。
4. 形成精确living-doc checkpoint并记录actual完整main SHA。Checkpoint只稳定current truth source，不表示candidate已main或产品／部署PASS。
5. Checkpoint后重新确认9个S3路径仍与 `b91e58a…` preimage一致。若有任一路径变化，停止并重新做适用性审计；不得以三方自动合并替代preimage门。

### Gate 1：S3 graceful timeout squash

**输入身份**：source provenance `865a5b71210e2436b36786b5de67146939d1e0f5`；new-main rebuilt slice `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`；rebuilt parent `b91e58a29324b11840002efc53ed6f869b800c39`；stable patch-id `26dcc6fbfffe0db7d3358728ff244fec36078be1`。

**精确pathset与result blob oracle**：

| Path | Main preimage blob | S3 result blob |
|---|---|---|
| `contrib/systemd/ghc-api-proxy.service` | `33fe7a27ef92dd0c4c45e65f8311963919dada8d` | `40b38c56312aecf7dec3cd000b9b7727a1c07b9b` |
| `docs/agents/deployment-systemd/README.md` | `2e6c5b43dd280e26564a922672c33c4103dcd75b` | `bed9f5e960169592011ee4c047fb55e87f490c75` |
| `src/app/cli.py` | `aaada4f20b34519d6bec98b0dbe344134a5e3d22` | `44a45a9333e999dd451d7765044fde82953ecd20` |
| `src/app/config/loader.py` | `82015510aec998e3964333b92eb42d74a13c9ddf` | `5709158b3c89a7d25b2bcd55bbb0568bc7ff4bbb` |
| `src/app/config/settings.py` | `b6983eee29ec898cc8b1cfc6bb31c8ffd02a183d` | `d10f705891187b37daf2ac7c86d731088733c9f8` |
| `src/app/graceful_timeout.py` | absent | `20ca181c1dc128eca754a32353387aa76047581e` |
| `tests/smoke/test_systemd_units.py` | `7e67c524a7dbec9b14ef8ff75de0ba032c7b1d96` | `5ed2f96fff1860a0b3b11d9f468cf786cc194d66` |
| `tests/unit/test_cli.py` | `62575181a8d50152e56a2c778bc49db500461315` | `7e611b5a51a8b73b22ee82ba2ab584ec7b270483` |
| `tests/unit/test_config_loader.py` | `f41f4d4123bd28992fcf8a08aa1aeffd58c702b0` | `d547dcc587a5edc931155ea211ec389145fa7d10` |

**动作与验收门**：

1. 在checkpoint后的actual main上重验上述9个preimage及无living／code WIP重叠；只应用S3 slice，生成一个新的non-merge单一语义squash commit。其parent必须是checkpoint后的actual main，subject保持S3语义，changed pathset必须与表完全相等；不得保留merge commit或把rebuilt `8cae6c2…`原identity当main checkpoint identity。
2. 新commit相对其parent的stable patch-id必须为 `26dcc6…`，9个result blobs必须逐项等于上表，`git diff --check`必须通过，Plan不得进入commit。
3. 运行S3定向配置／CLI／systemd unit／真实short-SIGTERM gates、全仓pytest、同一tests selector的collect-only、Ruff与Pyright；全部完整退出0，执行项数与collect-only node IDs须同范围一致，不硬编码历史数量。正控继续覆盖deadline严格正余量与配置分层判别；共享终端污染或中断结果整组作废。
4. Gate全绿后，fresh更新Systemd Plan到actual S3 main commit与实际gate证据，对新Plan bytes取得适用的0-major checkpoint；失败则停，不进入S4。
5. 只有S3 main-side gate与fresh Plan checkpoint都完成后，才建立immutable archive provenance，target精确为reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5`。Archive ref名称尚未由现有Plan冻结，后续流程可命名，但不得改指S3 rebuilt commit或未来main squash commit。

### Gate 2：S4 rootless installer squash

**输入身份**：source provenance `e16c2a700f23f66535e7347ab7357518eb8e56bd`；new-main parent-adapted slice `d3fabfadfba57af6c2d63e543e3198444777df54`；rebuilt parent `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`；adapted stable patch-id `412e73c47064720386c1075bfac0d3d8d08c6d26`。原始source非Plan patch-id `861d8756…`不同是预期parent adaptation，不是失败。

**精确pathset与result blob oracle**：

| Path | S4 preimage要求 | S4 result blob |
|---|---|---|
| `contrib/systemd/install-user.py` | absent | `fdee31ec890b2b7b408b1d0e95d01d4c4c8e8a06` |
| `docs/agents/deployment-systemd/README.md` | S3 result `bed9f5e960169592011ee4c047fb55e87f490c75` | `2bd8e5a00a6d2151ed378ac7b1f7ea2f26329b86` |
| `tests/smoke/test_systemd_user_install.py` | absent | `b91595c9ea0f6d701f5da9bc9a61719aec4efd2f` |

**动作与验收门**：

1. 只有Gate 1及S3 fresh Plan checkpoint完成后才开始。重验actual main、candidate exact tip／parent、上述3个preimage与无living／code WIP重叠；只应用S4 adapted slice，生成一个新的non-merge单一语义squash commit。其parent必须是“S3 squash＋S3 Plan checkpoint”后的actual main，changed pathset必须精确为3项。
2. 新commit相对其parent的stable patch-id必须为 `412e73…`，3个result blobs必须逐项等于上表，`git diff --check`必须通过，Plan不得进入commit。不得用原始source `861d8756…` patch-id作为相等门；正确oracle是reviewed source行为保留＋S3-parent timeout adaptation＋最终result blobs。
3. 运行installer定向pytest、真实 `systemd-analyze --user verify`、默认／`--check`零持久写、临时显式apply、幂等bytes与mtime、零 `systemctl`、secret不泄露，以及S3回归、全仓pytest／collect-only、Ruff与Pyright；全部完整退出0。不得连接或改变真实manager。
4. Gate全绿后，fresh更新Systemd Plan到actual S4 main commit与实际gate证据，对新Plan bytes取得适用的0-major checkpoint；随后再做actual main merged-state审阅／范围内verification，确认片间Plan checkpoints没有改变代码组合语义。失败则停，不进入S5。
5. 只有S4 main-side gate与fresh Plan checkpoint都完成后，才建立immutable archive provenance，target精确为reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd`。不得指向old integration、new-main rebuilt `d3fabfa…`或未来main squash commit；archive ref名称另行按流程冻结。

### Gate 3：两片完成后的组合边界

- Main历史应呈现“living checkpoint → S3 squash → S3 Plan checkpoint → S4 squash → S4 Plan checkpoint”的可追溯阶段，而不是regular merge／FF一次吞入两片，也不是把两片压成一个commit。
- 两个main squash各自保留独立revert边界；reviewed-source archive targets分别为 `865a5b7…`、`e16c2a7…`，main commit identities与source provenance明确分离。
- S5真实user-manager／cgroup仍是后续独立切片；S7 rolling仍未设计。任何仓库绿灯都不得升级为安装、真实manager、生产端口或cutover授权。

## 为什么必须 squash，而不是 regular merge／fast-forward

1. **Checkpoint先于代码是冻结顺序。** 当前candidate确实以 `b91e58a…` 为base，因此在checkpoint前图论上可FF；但这么做会绕过尚未闭合的living checkpoint。Checkpoint提交一旦先进入main，main与candidate自然分叉，FF不再可能。
2. **逐片停止点不可省略。** Regular merge candidate tip会把S3与S4同时带入，无法在S3后先运行main-side gate、fresh更新／checkpoint Plan、失败即停，再开始S4。
3. **身份职责不同。** `8cae6c2…`／`d3fabfa…`是new-main重建与验收载体；未来main commits是checkpoint后实际回放身份；`865a5b7…`／`e16c2a7…`才是reviewed-source provenance。Regular merge把载体identity直接写入main ancestry，模糊三类职责；逐片squash保持它们机械可区分。
4. **回滚粒度是合同。** 两片不得压成一个commit；同时也不得用一个merge commit包装两片。两个独立semantic squash加片间Plan checkpoint，才同时保留S3／S4独立回滚、审计和archive时序。

## Archive reviewed targets

| Slice | Reviewed source target | 当前archive状态 | 建立时机 | 禁止目标 |
|---|---|---|---|---|
| S3 graceful timeout | `865a5b71210e2436b36786b5de67146939d1e0f5` | 0个archive refs；活动ref为 `feat/systemd-graceful-timeout` | S3 main-side gate＋fresh Plan checkpoint后 | `862f4cfa…`、`8cae6c2…`、未来main squash |
| S4 rootless installer | `e16c2a700f23f66535e7347ab7357518eb8e56bd` | 0个archive refs；活动ref为 `feat/systemd-user-install` | S4 main-side gate＋fresh Plan checkpoint后 | `2ec0cb8…`、`d3fabfa…`、未来main squash |

现有文档只冻结archive target对象，没有冻结S3／S4 archive ref名称；执行者不得为追求表面完整而擅自假定命名。Ref创建、branch／worktree清理与任何远端发布均不在本报告执行范围。

## 主观建议

[建议] `docs/agents/systemd-runtime/plan.md` 的回并边界 — 在下一轮修订中把“逐片squash，不是regular merge／FF”写成显式机械合同，而不是只写“不得把两片压成一个commit” — 预期影响是避免执行者因当前candidate恰好直接基于main而选择FF，绕过checkpoint与片间Plan门 — 推荐直接复用本报告Gate 0～3的身份、pathset、patch-id、result blob与archive时序。

## 结构怪味与处置

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| Reviewed source／old adapted integration／new-main rebuild／future main squash | 同一行为存在四类commit identity，容易错误归档或错误要求patch-id相等 | 本轮以source provenance、adapted patch、main replay三层明确分工；S4特别禁止原始source patch-id相等门 |
| Living docs checkpoint与code-only replay | 高频状态文档和代码提交时序耦合，regular merge会吞掉片间停止点 | 本轮要求checkpoint先行、逐片squash、每片后fresh Plan checkpoint；长期可继续拆分volatile execution ledger与稳定设计，但不得删减living truth |
| Shared terminal | 外部会话输出可污染命令证据 | 本轮废弃一次无nonce结果并重跑；后续main-side tests须使用独立session／日志与完整退出码 |

## 最终结论

**当前总体为0 blocker／1阶段门major：候选代码链本身0 blocker／0 major且两份verification均PASS，但living checkpoint尚未闭合，所以现在不得回放。** Implementation与Systemd Plan修复并取得current-byte 0 major、与Readiness共同形成checkpoint后，唯一放行路线是：**S3九路径semantic squash → S3 main-side gate → fresh Plan checkpoint → archive target `865a5b7…` → S4三路径parent-adapted semantic squash → S4 main-side gate → fresh Plan checkpoint／merged-state复核 → archive target `e16c2a7…`。** 禁止regular merge、禁止fast-forward、禁止一次吞入两片、禁止旧Plan载荷、禁止把rebuilt或main commit当reviewed-source archive target。
