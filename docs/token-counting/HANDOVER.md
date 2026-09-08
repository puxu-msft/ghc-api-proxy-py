# Token-counting historical learning handover

**状态：草稿·Task 4A与Task 4B-P均已集成main。下一步是生成Task 4B brief；Task 4B-P authority correction、source、merged-state review与gate均已完成。**

**Authority snapshot：** [status.md](status.md)是唯一volatile进度权威；本交接按其2026-09-07 Task 4B-P integrated snapshot复述。Behavior authority为[spec.md](spec.md) SHA-256 `fdf63872b906dc87ec44eb4627c199552cc904d730add186600cc5095c639df9`；implementation authority为[plan.md](plan.md) SHA-256 `bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a`；volatile projection snapshot为[status.md](status.md) SHA-256 `112d7270095025ce6eabab02c94c00ec0177bebc0518c86bb545c266e121569f`；Task 4B-P source archive为`archive/260907-token-prefix-residuals → d10121c9`，main squash为`4fe53d0fe8102e35efeea53ce3024ffadb6823d4`。

**Git／worktree snapshot：** shared main为`3badac7f6b020764cf8e30b2528ff51055dad0c2`，`main...origin/main [ahead 5]`；当前root可见untracked为`.claude/worktrees/`、`.dockerignore`、`Dockerfile`、`docker-compose.yml`、`exp/260820-h2-stream-cap/`，不要stash／reset／restore／clean这些路径。Task 4A reviewed source为`archive/260907-token-prediction-exact-prefix → 7d7e43b32c1d90e1723e6ad469262c5617e670a5`；Task 3B reviewed source为`archive/260907-token-learning-prerequisites → e2461a6e`；dotdev worktree为`dotdev-token-counting-learning → b1dd960d6e5a5781f46610be8ff9ed212eaca5c0`，本地ahead、未push。

**门禁：** Task 3B与Task 4A均已review、归档并集成main；Task 4B-P authority correction follow-up、source review、merged-state review均通过，merged gate为`PASS`。Task 4B-P source已归档并以squash commit进入main；Task 4B source仍未授权。

## 可复制 kick-off

```text
不要使用旧Task 4A brief，也不要把Task 3B source重复派发。先在/home/xp/src/ghc-api-proxy-py读取：
1. .dev/docs/token-counting/HANDOVER.md——本次交接事实与下一步。
2. .dev/docs/token-counting/status.md——唯一volatile进度权威。
3. .dev/docs/token-counting/task-3b-brief.md——已通过独立review的Task 3B scope边界。
4. .dev/docs/token-counting/reports/260907-task3b-source-review-grok-xhigh-followup.md与260907-task3b-merged-state-review-grok-xhigh.md——source与merged-state review verdict。
5. .dev/docs/token-counting/task-4a-brief.md及[Task 4A gate reports](reports/260907-task4a-source-review-grok-xhigh.md)——当前deterministic predictor scope和已完成的Task 4A边界。

第一件事重新核对current main `3badac7f`、Task 4A archive `7d7e43b3`、authority hashes和shared untracked边界。然后生成Task 4B-P implementation brief并独立review；Task 4B-P只负责learned prefix variants、historical pair index、full-baseline/current-zero controls和newest31，不回写已完成的Task 4A或Task 3B；不要移动dirty shared main，不push，不控制4141。
```

## Action table

| ID | 状态 | 依赖 | 执行入口 | evidence.locator | 完成判据 |
|---|---|---|---|---|---|
| H0 | done | — | `git rev-parse`、`git status --short --branch`、`sha256sum .dev/docs/token-counting/{spec,plan,status}.md` | 当前 refs 与 authority hashes；本会话首次冻结输出 | main、integration、两个 archive、dotdev 和三个 authority hash 已记录；不触碰 shared main WIP。 |
| H1 | done | H0 | 对照当前[authority review](reports/260907-task3b-authority-review-gpt-high.md)修正 Spec／Plan，并同步 status projection | `spec.md` revision record；`plan.md` Task 3B／4B-P checklist；`status.md` authority repair snapshot | AUTH-01、02、04、Minor05 的 authority／acceptance 缺口已有唯一文字归属；AUTH-03 保留为待复核 provenance。 |
| H2 | done | H1 | fresh scoped authority review，输入当前 Spec／Plan／status 与 H1 报告 | [260907-subagent-authority-repair-review.md](reports/260907-subagent-authority-repair-review.md)；Spec／Plan／status hashes已固定 | `READY`，0 Blocker／Major，1 non-blocking Minor；H3可执行，H4仍blocked。 |
| H3 | done | H2 | 生成 Task 3B implementation brief并独立review | `task-3b-brief.md`；follow-up report `260907-task3b-brief-review-gpt-l-followup.md` | `READY`，0 Blocker／Major，status hash stale minor已同步；formula-level A45 controls留给Task 4B-P。 |
| H4 | done | H3 | 在 stacked token-local base 上执行 source preflight，然后完成 Task 3B source、review、gate | source `e2461a6e`；archive `archive/260907-token-learning-prerequisites`；source review `260907-task3b-source-review-grok-xhigh-followup.md`；merged review `260907-task3b-merged-state-review-grok-xhigh.md`；main gate `260907-task3b-merged-precommit-gate-gpt-s.md` | source review APPROVED；3375 passed／2 skipped／90.35%；squash integration `6044919a`已进入main。 |
| H5 | done | H4 | 生成deterministic Task 4A implementation brief并独立review | `task-4a-brief.md`；follow-up report `260907-task4a-brief-review-grok-xhigh-followup.md` | `READY`，0 Blocker／Major；仅四个Task 4A allowed paths，4B-P／4B／4C／Task 5均为non-goal。 |
| H6 | done | H5 | 在main `6044919a`隔离worktree完成Task 4A source、review、gate并集成 | source `7d7e43b3`；archive `archive/260907-token-prediction-exact-prefix`；source review `260907-task4a-source-review-grok-xhigh.md`；merged review `260907-task4a-merged-state-review-grok-xhigh.md`；main gate `260907-task4a-merged-precommit-gate-gpt-s.md` | source／merged-state APPROVED；574 tokenization passed；main squash `3badac7f`已进入main。 |
| H7 | done | H6 | 在隔离3badac7f worktree完成Task 4B-P source、review与gate | source `d10121c9`；archive `archive/260907-token-prefix-residuals`；source review `260907-task4bp-source-review-grok-xhigh.md`；merged review `260907-task4bp-merged-state-review-grok-xhigh.md`；main gate `260907-task4bp-merged-precommit-gate-gpt-s.md` | C04 correction READY；source／merged-state APPROVED；588 tokenization passed；main squash `4fe53d0f`已进入main。 |
| H8 | ready | H7 | 生成Task 4B implementation brief并独立review | current main `4fe53d0f`；Task 4B-P archive `d10121c9` | brief必须严格承接learned variants与Task 3B／4A carriers，覆盖profile candidates、promotion和16／8 checkpoint policy，不实现4C drift或Task 5 pipeline。 |

### Evidence status and negative space

- H2 之前没有任何 source authorization；H4在source review通过后完成，H5 brief review通过，H6只待volatile authority与source启动状态同步。
- Handover 没有项目专用机械检查器；相对链接可解析不等于 handoff 通过。
- Task 3B source report明确保留A40 SQLite／worker、A41 predictor pairing、A44全矩阵mutation和A45 formula未验证边界；A45 formula controls由Task 4B-P负责，不得由Task 3B gate冒充。
- `3,358 tests／2 skipped`、coverage、旧 review finding 数和 `111／211` 是历史报告或当前 Spec 的点时数字，不由本交接重新计数；不得把它们当作当前 source evidence。
- 本次Task 3B已运行source tests、Ruff、Pyright和main-side full gate；没有运行真实 upstream或4141，没有修改`docs/.human-controlled/`，也没有清理shared untracked worktree。

## 必读清单

| 文件 | 为什么必读 |
|---|---|
| [status.md](status.md) | 唯一volatile进度权威；HANDOVER的状态复述冲突时以它的更新版为准。 |
| [spec.md](spec.md) | 完整behavior authority；Task 3B writeback已在这里，但当前review未通过。 |
| [plan.md](plan.md) | 当前顺序为3B → deterministic 4A → 4B-P → profile＋eligibility 4B → drift 4C → 5；不能回到旧4A全包。 |
| [Task 3B authority review](reports/260907-task3b-authority-review-gpt-high.md) | 当前唯一open review，逐条给4 Major／1 Minor、反例和最小修法。 |
| [Task 4A brief review](reports/260907-task4a-brief-review-claude.md) | 证明whole visual不可分解suffix、eligibility会随prune丢失；这些是Task 3B存在的原因。 |
| [Task 3B prerequisite design](reports/260907-task4a-prerequisite-design-gpt-high.md)与[architecture review](reports/260907-task4a-prerequisite-design-review-grok.md) | 解释per-item、committed order、checkpoint和4B-P分片的初始设计与被否路线。 |
| [design amendments 1](reports/260907-task3b-design-amendment-1.md)、[2](reports/260907-task3b-design-amendment-2.md)、[3](reports/260907-task3b-design-amendment-3.md)及各review | 解释capacity从cross-identity变为current-identity、零收益reject、required outcome矩阵和single transition authority；不要重新走已否路线。 |
| `.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/progress.md` | 恢复map；本次交接后应标记“已被HANDOVER取代”并停止更新，接手者另开自己的进度载体。 |
| `.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/task-4A-brief.md` | 只为识别旧错误；头部已标`SUPERSEDED／不得派发`。 |

## 已完成并可直接采用的硬事实

| 事实 | 证据等级与依据 |
|---|---|
| 当前Responses旧估算器在reasoning-heavy重建请求上约高估4.927230倍，主因opaque ciphertext被当ordinary text | 点时取证；见README链接的260906分析／erratum。不能外推成所有请求固定倍率，也不能证明事故overflow由local count触发。 |
| Task 2 structured features已进入main | Git历史与早期full gate；reviewed source archive `archive/260907-token-features`。 |
| Task 3 SQLite store实现／review完成并已进main | Reviewed source archive `archive/260907-token-learning-store`；main squash `6044919a`包含该stack。 |
| Task 3A candidate／visual／decision persistence实现／review完成并已进main | Source review与re-review；archive `archive/260907-token-prediction-persistence`；main squash `6044919a`。 |
| Task 3B source实现／review完成并已进main | Source `e2461a6e`由`archive/260907-token-learning-prerequisites`保留；source与merged-state review APPROVED；main squash `6044919a`。 |
| Stacked candidate在其位置通过Ruff、Pyright及3,375 tests／2 skipped，coverage 90.35% | 2026-09-07 source与main-side gate，命令／结果见`reports/260907-task3b-full-gate-gpt-s.md`和`reports/260907-task3b-merged-precommit-gate-gpt-s.md`。 |
| Task 3B source已启动并完成 | Git：source commit `e2461a6e`已review、归档并以`6044919a`进入main；TaskList #26的projection需由后续调度器同步。 |
| Task 4A source实现／review完成并已进main | Source `7d7e43b3`由`archive/260907-token-prediction-exact-prefix`保留；source与merged-state review APPROVED；main squash `3badac7f`。 |
| Task 3B Spec action denominator拟从108／204变111／211 | Current Spec table；数学为新增1个EFC＋2个EC。该值尚未由source实现／runtime trace验证。 |

## 历史open review：原样保留

以下是authority repair前的点时finding原文，保留用于追溯；它们已由authority repair、Task 3B brief review和source review分别关闭，不是当前source gate。

### T3B-AUTH-01：policy与store同时拥有final observation

Plan上层仍写pure policy返回`LearningUpdate`＋`TokenLearningObservation`，但Spec又要求store在stamping、capacity、prune和COMMIT后产生required checkpoint outcome。接手者应把logical policy output和durable observation分开：`LearningUpdate`只含pending sample／record／evaluations／required checkpoint command／optional drift；store唯一构造final observation。若保留draft，必须换名换type且不能冒充durable observation。

### T3B-AUTH-02：current checkpoint evidence没有合法committed order

Persistent triple要求positive `committed_order`，但policy时pending sample order为None。新增orderless pending triple，或只允许logical evidence的唯一tail order为None；store以`next_global_revision`同时stamp sample和tail，再构造全positive persistent checkpoint。拒绝多个pending、non-tail pending与提前encode。A42与transcription补policy无order→store stamp equality control。

### T3B-AUTH-03：执行入口同步不完整

Plan／SDD／TaskList顺序已正确；交接过程中已把status补上4B-P，并给旧Task4A brief加`SUPERSEDED`。这些是在authority review之后的未review变化，只能算“部分处理、待复核”，不能把finding标closed。Task 3B review通过后重新生成3B brief和收窄4A brief；4B-P启动前单独生成brief。

### T3B-AUTH-04：acceptance抓不住known-only baseline与current-zero gate

扩展A45或新增criterion：

1. Historical known delta为0、visual／prior delta为正且actual匹配完整baseline；断言residual、ratio、candidate value、sample count。Mutation改known-only必须红。
2. 至少3条positive ratio history且current baseline为0；multiplicative仍在record、count正确、full value等于anchor actual。恢复current-value gate必须红。

同步§13 transcription与Task 4B-P mutation清单。

### T3B-AUTH-05：same-transaction current-sample prune control缺席

Minor。新增fixture让current sample成为本事务sample-cap victim，同时断言sample row缺席、checkpoint replacement仍存在、event保留实际Applied／Deleted outcome与revision；“pruned时跳过checkpoint”和“改写NoChange”两种mutation必须红。

## 计划与实际差异

| 计划里怎么写 | 实际状态 | 被什么证伪／为什么 |
|---|---|---|
| Task 4A一次实现cold、exact、learned prefix、demotion／recovery | 拆为Task 3B → deterministic 4A → 4B-P → profile＋eligibility 4B → drift 4C | Whole visual None不可分解append item；prunable records无法承载长期eligibility。 |
| Prefix suffix可用whole-request totals差分 | 必须持久化exact per-item contributions并按anchor item count切片 | None→None＋新完整image的6 tokens无法从whole totals恢复。 |
| Prefix eligibility每次从records重放 | 必须持久化独立sample-FK的per-ProfileKey 16／8 checkpoint | Demotion records被sample prune后会无条件恢复eligible。 |
| Capacity可选另一个global victim identity rollover | 只允许causal current identity；prior rows为0的零收益分支typed reject | Cross-identity event／revision／cache与single-identity policy无法同事务闭合；零收益rollover会反复清空history。 |
| Policy可预构造完整observation | 当前review要求store唯一拥有final observation | Policy看不到global cap、stamp、prune和COMMIT结果。 |

## 当前Git／worktree边界

### Shared main

冻结HEAD：`42fb23299bc9487d1751749668277ac4304861f8`。该HEAD包含旧交接后新增的`feat: use routed upstream for token counting`；stacked `16a09044`仍未集成。当前root没有可见tracked WIP；不要把下列untracked路径视为本任务产物或自行清理。

Main当前untracked：`.claude/worktrees/`、`.dockerignore`、`Dockerfile`、`docker-compose.yml`、`exp/260820-h2-stream-cap/`。不要stash／reset／restore／clean这些路径；`docs/.human-controlled/`由用户控制，绝不修改。

### 本任务refs／worktrees

| 载体 | 状态 |
|---|---|
| `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration` | Clean，branch `integration/token-learning-store`，保留；Tasks 3／3A stacked source。 |
| `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd` | Tracked clean，只有managed `.dev` symlink untracked；保留reviewed source lineage。 |
| `/home/xp/.claude/jobs/4f9bdf9a/tmp/dotdev-token-counting` | Dedicated dotdev branch，本地ahead、未push；active `.dev`的持久源。 |
| `archive/260907-token-learning-store` | 保留Task 3 reviewed source。 |
| `archive/260907-token-prediction-persistence` | 保留Task 3A reviewed source。 |

没有执行worktree／branch清理；没有manifest独立评审，故按fail-closed全部保留并交harness／接手者处置。没有push或publication。

## Task tracker snapshot

- #26 `补齐 prefix 学习前置状态`：已完成；source review、merged-state review和main-side gate均通过，main squash为`6044919a`。
- #13 `实现 exact/prefix predictor`：pending，blocked by #26。
- #27 `实现 learned prefix variants`：pending，blocked by #13，并阻塞#14。
- #14 → #15 → #16 → #17 → #18 → #19／#20 → #21／#22 → #23保持后续链。
- #24 `集成 token store 到 main`：已完成于本次stacked squash；current main仍有untracked WIP，不得把后续Task 4A误用为ff-only操作。

## 下一步与验收／证伪

1. **生成并review Task 4B brief。** Task 4B负责profile candidates、promotion和per-ProfileKey 16／8 checkpoint policy；不实现Task 4C drift或Task 5 pipeline。
2. **Task 4B source＋review＋stacked gate。** 不回写Task 4B-P learned variants、Task 4A predictor或Task 3B carriers。
3. **之后按4C推进。** 每个slice继续使用source review、merged-state review和一次对应gate，不回退旧Task 4A全包路线。

## 明确未做

- 已写入authority repair并通过fresh scoped review；Task 3B brief、source、merged-state review和main-side gate也已完成。
- Task 4A与Task 4B-P source均已review、归档并集成main。
- Tasks 3／3A／3B／4A／4B-P stacked candidates已通过main-side squash进入`4fe53d0f`。
- 未对shared main执行reset／clean／stash；main-side squash在临时integration worktree完成后以单一commit应用。
- 未触碰shared main WIP、`docs/.human-controlled/`或4141 service。
- 未push dotdev／main／archive refs，未发布PR。
- 未清理job scratch、worktrees、branches或临时报告；缺manifest review，因此有意fail-closed保留。
- Handover已完成subagent接手性检查；原始报告结论为`接不住`，后续修订补齐action table、refs、hash、negative space和当前产物状态；本handover仍是草稿型交接，不是Spec authority。

## 复发点

- **旧brief复用：** 接手者生成Task 3B／4A brief时，若打开`.superpowers/.../task-4A-brief.md`，先读其SUPERSEDED头；不得删头后继续。
- **authority hash误读：** 接手者修AUTH findings后必须更新status snapshot；不能把本handover头部hash当永久冻结开关。
- **main移动误判：** #24开始前重新冻结main；`16a09044`不是当前main祖先，不能再写“ff-only已就绪”。
- **outcome塌槽：** Task 3B DTO实现时，NoChange、NotAttempted、NotCommitted不得合并；policy不得产生final durable observation。
- **probe假绿：** learned prefix tests必须显式让visual／prior非0和current baseline0，否则AUTH-04会再次全绿。

## 档案与清理

本计划未完成，不归档living Spec／plan／HANDOVER。Point-in-time reports均留在`reports/`，由README可发现。HANDOVER完成接手后，下一会话应把旧SDD progress的状态保持为“已被HANDOVER取代”，并建立自己的进度载体。

本轮未执行删除。Job scratch中的commit-message、临时合并报告与review临时文件已有`.dev`／Git对象接收者，但因未做独立manifest review，不删除；让harness自行过期。所有worktree／refs保留，避免丢失未集成source与peer WIP。
