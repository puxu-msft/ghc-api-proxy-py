# Bridge-next successor 只读回放审计

- **评审范围**：只读审计 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、semantic source `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`、route successor `feat/anthropic-responses-route-happy@dd376d6f1e9dc2997bc2f95d03a352fed4df1412` 与 block source `feat/anthropic-block-delivery@e506bf87318424e4075b6422772ee0c7e9b8694a`。范围包括 source worktree clean、完整提交范围、逐提交 stable patch-id、patch paths、旧 bridge-next hooks major 的同一 oracle 红→绿正控、临时 overlay 合并态回归，以及新 integration 的唯一推荐顺序。未修改 Git ref、index、commit、branch、worktree 或对象库；唯一仓库写入是本报告。
- **总体 verdict**：**可进入下一阶段。** 本次回放审计为 **0 blocker／0 major／0 minor**。Semantic 可先独立进入 main；随后必须从 semantic 已通过 main-side gate 的新 main HEAD 建立全新 integration，按 route 完整三提交范围后接 block 完整两提交范围。不得复用旧失败组合 `a23081c5d5f48143bf3015182d8f00e1f6297755`，不得只摘 route 尾提交 `dd376d6…`，也不得把本预检 verdict 外推为未来 integration HEAD 的 0 major。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **未来 0 major 边界**：本报告只证明 source identity、建议顺序、净补丁可叠加性与旧 major 已被 successor 精确关闭。未来 integration 必须绑定其新完整 HEAD，重新取得 merged-state code review 的 `0 blocker／0 major` 与独立 verification `PASS`；source 绿灯、本报告绿灯、临时 overlay 全绿或旧 integration verdict均不能替代该门。

## 双视角覆盖证据

### 机械核对

- 主树固定为 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。三个 source worktree 分别固定为 semantic `f5bca39…`、route `dd376d6…`、block `e506bf8…`，审计前后 `git status --porcelain` 均为空，tracked／untracked clean。主树自身存在用户／并行会话的既有文档与 verification WIP，因此本报告不声称整个 main worktree clean；指定输出路径写入前不存在。
- 三条 source 都直接以 `80bc8f2…` 为 merge-base：semantic 为两提交线性范围，route 为三提交线性范围，block 为两提交线性范围。提交数由 `rev-list --count` 与 first-parent 序列交叉核对。
- 每个提交的 stable patch-id均以 `git show --binary` 与 `git diff --binary <parent> <commit>` 两个入口交叉验证一致；完整 identity 账本见下文。
- 三条完整 range 的 path 集合两两零重叠。该事实允许 semantic 先独立进入 main，再把 route／block净补丁应用到 semantic 后继 main，而不需要冲突选边；零重叠只证明静态可组合，不替代运行门。
- 旧 bridge-next 独立 harness在“semantic＋route 截止 `44808b7…`＋block”overlay 上按目标原因变红：三条 pre-attempt typed reject均只有 `request_received`，进程非零退出。只叠加 `44808b7… → dd376d6…` successor delta后，同一 harness观察到三条路径均为 `request_received → error → finalize`，`LIFECYCLE_FAILURES=[]`，parser→delivery两项 oracle同时通过，进程退出为零。这是旧 major 的直接 A/B 正控，不是候选自测自证。
- 在自动回收的非 Git `/tmp` 目录从 `main@80bc8f2…` 原始 tree按 semantic→route→block顺序叠加三个完整净补丁，三个 `git apply --check`均通过。组合定向 pytest、全仓 pytest、全仓 Ruff与全仓 Pyright均通过；pytest runner原始摘要分别为 `48 passed`与`468 passed`，这些计数未用第二原理交叉验证，只记录 runner输出，不作为 0 major 的独立 oracle。Pyright runner原始摘要为 `0 errors, 0 warnings, 0 informations`，同样只记录工具输出。
- 现有 exact source证据对账：semantic `f5bca39…` 已有代码 R2 `0 blocker／0 major／0 minor`与独立 verify R2 `PASS`；block `e506bf8…` 已有代码 R2 `0 blocker／0 major／0 minor`。Route旧 `44808b7…` 已有 source R2 0 major与 verify R2 `PASS`，但它们不覆盖 successor；本轮以 successor最终代码、候选回归、旧独立 harness A/B及临时 merged overlay重新审计 `dd376d6…`。

### 第一人称执行

- 作为 main 回放执行者，先消费 semantic 两提交并完成 semantic main-side gate；随后从该新 main HEAD建立新 integration。若直接从旧 `a23081c…`续写，会把已绑定旧 route patch的失败组合当作新基线，证据归属与旧 major关闭关系均不再单义，因此该路径拒绝。
- 作为 route执行者，必须消费 `f3a5a76… → 44808b7… → dd376d6…`完整范围。只摘 `dd376d6…`没有 route生产接线和 Responses header归一化前置实现；只摘到`44808b7…`则重现旧 bridge-next 的 hooks lifecycle major。
- 作为失败请求执行者，capability missing、explicit Responses override unsupported与selected Responses stream unsupported均在 attempt创建／upstream调用前结束。Successor的single owner把同一context标记失败，按顺序发出`ERROR`与`FINALIZE`，再让History对同一context finalize一次；attempt仍为空、upstream调用仍为零。Observer自身失败由`HooksExecutor.observe()`隔离，后续observer与History不会被截断。
- 作为 block执行者，在route完整范围后消费`e3fceb1… → e506bf8…`。当前block片仍是无生产调用者的typed delivery骨架；它验证parser facts、连续source prefix、完整block batch、terminal gate与single writer，但不把骨架存在冒充真实route stream已经接线。
- 作为未来验收者，在新integration最终HEAD上必须重跑route真实ASGI hook trace与parser→delivery oracle，并重新审阅最终代码。当前若写一个测试手工调用route一遍、再手工调用delivery一遍并称为“hook trace＋delivery组合测试”，两侧没有共享同一生产请求owner，只会制造拼接假绿。真正的同请求组合测试应等生产stream route wiring存在后成为必需门。

## Source identity 与 patch paths

### Semantic：必须先独立 main

固定线性范围：

1. `1cde3d58338eeefb3cf8040f970c3612d451668b`，`fix: enforce responses stream semantic parity`，stable patch-id `46aca51800fb72fb9792d832466867eae292cd04`。
2. `f5bca39ac582911b61d278fd678ec9298ad0c08e`，`fix: reject unsupported reasoning summary parts`，stable patch-id `f037d26f6c39e808aea163ec0e8a77f11f2669db`。

完整 range paths：

- `src/app/openai/responses_stream_parser.py`
- `tests/unit/test_responses_stream_parser.py`

结论：按既有 semantic replay审计，先把完整两提交语义作为独立 main切片回放／squash并完成 main-side gate；archive仍精确指向 reviewed pre-squash source HEAD `f5bca39…`。Semantic与route／block paths均零重叠，它不应继续被旧 bridge-next FAIL阻塞。

### Route successor：必须使用完整三提交范围

固定线性范围：

1. `f3a5a768491c542224103a87b75e5bb39803ac4a`，`feat: serve Anthropic requests via Responses`，stable patch-id `4c17965e5db686a772c05f177ea386d2f7d10550`。
2. `44808b7d0be84a0c1eb5c58294726c620d4280cd`，`fix: filter Responses headers for Anthropic clients`，stable patch-id `dcea205a9b541cd346dda01639c205bf1a8b5c74`。
3. `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`，`fix: finalize pre-attempt hook failures`，stable patch-id `289c3996708b260192533b07101d93c5ee28ac3a`。

完整 range paths：

- `src/app/anthropic/client.py`
- `src/app/anthropic/header_policy/__init__.py`
- `src/app/config/settings.py`
- `src/app/pipeline/context.py`
- `src/app/pipeline/executor.py`
- `src/app/routes/anthropic.py`
- `src/app/upstream/bootstrap.py`
- `tests/component/test_pipeline_executor.py`
- `tests/smoke/test_anthropic_responses_route.py`
- `tests/smoke/test_systemd_units.py`

结论：新integration必须从完整range重建。可以保留三个线性提交，也可以形成一个内容等价的route squash；若squash，必须对完整range结果blobs／paths做机械对账，不能只以尾提交patch-id代表整个route。`dd376d6…`精确关闭旧bridge-next的pre-attempt hooks major，但不表示完整LIFE-02／LIFE-03 Acceptance已通过；approval modified／rejected／timeout／pending cancel、rate limiter与retry factory等完整lifecycle矩阵仍属于后续required gates。

### Block source：route之后使用完整两提交范围

固定线性范围：

1. `e3fceb1cd14c44527bf2625acee0873421386caf`，`feat: add Anthropic block delivery skeleton`，stable patch-id `13971dccf73c009fc6a3ea8f960d258780cc5099`。
2. `e506bf87318424e4075b6422772ee0c7e9b8694a`，`fix: enforce typed block delivery ordering`，stable patch-id `c649d656a53d4e3f66f23112590c1ebdb8288fb6`。

完整 range paths：

- `src/app/delivery/__init__.py`
- `src/app/delivery/anthropic_sse.py`
- `tests/smoke/test_anthropic_block_delivery.py`

结论：在route完整range之后应用block完整range。Block source自身0 major有效，但未来integration仍须复核route未建立第二finalize owner、block未建立第二sink，以及typed terminal／single writer合同未被组合代码旁路。

## 唯一推荐的新 integration 顺序

1. **Semantic独立进入main。** 从当时真实main重新gate HEAD、index、worktree与semantic两个preimage；按`1cde3d5… → f5bca39…`完整范围回放或内容等价squash。执行semantic定向、交叠、全仓pytest、Ruff、Pyright与独立semantic oracle；通过后形成main checkpoint与reviewed source archive。
2. **从semantic checkpoint后的新main建立全新integration。** 不复用、不amend旧`integrate/260807-bridge-next@a23081c…`。记录新base完整OID，并重新核对route／block source refs仍为本报告绑定的exact HEAD且clean。
3. **应用route完整三提交范围。** 顺序固定为`f3a5a76… → 44808b7… → dd376d6…`，或使用经结果blob／path对账的完整route squash。先运行route source回归与旧bridge-next独立route oracle，要求三条pre-attempt reject均为`REQUEST_RECEIVED → ERROR → FINALIZE`、History finalize一次、attempt为空、upstream零调用；再进入下一片。
4. **应用block完整两提交范围。** 顺序固定为`e3fceb1… → e506bf8…`，或使用经结果blob／path对账的完整block squash。运行parser→delivery多part、较晚source、零block source、typed terminal与并发single-writer门。
5. **重建merged-state证据。** 在最终integration HEAD运行定向与全仓pytest、Ruff、Pyright、真实ASGI route/header/hooks matrix、独立parser→delivery matrix及正控；检查生产调用者仍为空还是已建立真实stream wiring，并据此使用下节的组合测试判据。
6. **重新取得0 major。** 对最终integration HEAD进行独立merged-state code review与verification。只有两者分别给出`0 blocker／0 major`与`PASS`，才可把新integration写成0 major并进入main-side逐片回放；本报告不得被引用为该未来HEAD的替代verdict。

## 是否需要新的 hook trace＋delivery 组合测试

### 当前 route＋block 骨架 checkpoint

**不应新增一个手工拼接的“同请求hook trace＋delivery”测试作为当前squash门。** 当前route对selected Responses stream明确typed reject，block delivery在生产`src/**`中没有route／pipeline调用者；测试若分别直接调用`execute_anthropic_pipeline()`和`DeliverySession.consume()`，没有共同owner、attempt、response或sink，只能重复两个既有单侧测试，无法证明集成接缝。

当前新integration仍必须有一个merged-state验收入口同时运行两条独立oracle：

- route真实ASGI phase trace，至少重放旧major的三条pre-attempt reject并保留success／429对照；
- parser→typed delivery的完整block／source order／terminal／single writer矩阵。

这两条可以位于同一harness或同一次gate中，但报告必须明确它们是两个尚未生产接线的独立轴，不能称为end-to-end stream。

### 生产 stream route wiring 建立后

**需要，而且是required merged-state门。** 新测试必须从真实Anthropic `/v1/messages` stream入口驱动同一request owner，经route decision、每attempt `PRE_SEND`、Responses transport、parser、typed `DeliverySession.consume()`与真实下游writer；在同一trace中联合断言：

- `REQUEST_RECEIVED`与sanitize phases只属于同一Anthropic request，retry时每attempt各有一次`PRE_SEND`；
- 首个完整block commit前下游零success header／body，失败可重试且旧attempt facts／usage／bytes全部隔离；
- 每个committed block只产生一个完整envelope，frontier与sink accepted顺序一致；
- pre-commit failure、post-commit failure、client cancel与terminal分别得到正确`ERROR／FINALIZE`，History与hooks finalize恰好一次；
- post-commit failure不得透明full replay，不得发伪success terminal；
- 移除route finalizer、旁路typed delivery或建立第二writer／第二finalize owner时，同一oracle按目标原因变红。

在该生产接缝出现前，不把上述未来required门提前伪造成手工组合测试；在接缝出现后，也不得继续以当前两条独立oracle替代真正end-to-end test。

## 事实性发现

未发现阻止按本报告顺序重建新integration的事实性问题。旧bridge-next唯一major已由`dd376d6…`在同一独立oracle上从红修到绿；三条完整source range可按semantic→route→block无冲突叠加，source worktrees保持clean。

## 主观建议

[建议] 新integration提交形状 — 优先让semantic独立main，route与block各保持一个语义清楚的integration提交；若为保留逐提交来源而选择route三提交／block两提交原样replay也可 — 预期影响是故障归属、回滚与archive provenance更清晰 — 推荐至少冻结每个source commit的patch-id、完整range paths与最终result blobs，不使用单一尾提交OID代表整个slice。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/pipeline/executor.py` 的pre-attempt失败与attempt内失败 | lifecycle终结入口仍分布于preparation、approval、stream gate、rate limiter、strategy factory与attempt send分支；局部三样本容易被误写成完整Acceptance | **当前旧major已关闭，不阻断重建**；未来LIFE-02／LIFE-03对approved modified、rejected、timeout、pending cancel及其他异常入口补完整phase trace与exactly-once门 |
| `src/app/delivery/anthropic_sse.py` 的typed／manual双API | 生产接线后调用者可能误用manual API绕过parser source／terminal facts | **当前由mode机械禁止混用，不阻断骨架**；真实stream driver只暴露typed `consume()`，组合review扫描所有调用者 |
| Route与block之间没有生产调用边 | 两个模块同树全绿容易被误称为end-to-end stream | **本报告明确保留边界**；当前只跑两个独立merged-state oracle，真实调用边建立后强制新增同请求hook trace＋delivery门 |

## 结论

本次审计为 **0 blocker／0 major／0 minor**，可进入下一阶段。唯一推荐顺序是：**semantic `1cde3d5… → f5bca39…`先独立进入main并通过main-side gate；从该新main建立全新integration；route完整`f3a5a76… → 44808b7… → dd376d6…`；block完整`e3fceb1… → e506bf8…`；最后对新完整HEAD重建merged-state review／verification。** 旧`a23081c…`不得复用，route尾提交不得单独摘取。当前不新增手工拼接的hook trace＋delivery伪E2E；一旦生产stream route真正接入typed delivery，同请求hook trace＋delivery测试立即成为required gate。
