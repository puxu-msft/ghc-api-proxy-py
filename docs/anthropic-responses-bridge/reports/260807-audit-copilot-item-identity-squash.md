# Copilot item identity source squash 只读审计

- **评审范围**：只读审计主树 `/home/xp/src/ghc-api-proxy-py` 的现场 `main@0e66cab5ffd636e40a0f378d6017326603a3196a` 与 source worktree `/home/xp/src/ghc-api-proxy-py-item-identity` 的 `fix/copilot-item-identity@f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`。覆盖完整单提交 range、精确 pathset、main preimage／source result blobs、全部 registered worktree 的 tracked WIP 与全部 dirty path交集、exact-tip 复评与定向验证、唯一允许的 `merge --squash` 执行门、最小 main-side tests及 reviewed-source archive target。本轮没有执行 merge、fast-forward、regular merge、cherry-pick、commit、archive、ref 更新、清理、部署或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入 squash。0 major 明确可执行。** Source tip恰好是现场main HEAD的单一直接子提交，range仅含一笔non-merge commit；净五路径的main preimage与source result blobs闭合，现场main在source base之后没有提交，全部current tracked WIP与候选五路径交集为空。执行时只允许在exact main preimage上运行一次 `git merge --squash f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`，随后通过staged identity与最小main-side门并形成一个新的单一non-merge main commit。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **archive target**：`f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`。后续archive ref无论采用何种名称，都必须精确指向这个reviewed source tip；不得指向未来main squash commit。审计时没有archive ref指向该source，推荐名称 `refs/heads/archive/260807-copilot-item-identity` 也尚不存在。
- **范围边界**：本verdict只放行Copilot Responses stream中item ID跨lifecycle漂移、generic默认保持稳定item ID、missing／null event-level `item_id`继续等价于省略、present empty／non-string ID继续typed失败，以及output index、item type、content index、function `call_id`／`name`等其余identity合同继续严格。它不扩展为完整stream、完整bridge、部署或cutover通过。

## 双视角覆盖证据

### 机械核对视角

1. 每个采信的tree-dependent shell结果都在同一次调用中打印并验证物理cwd、Git top-level、branch与完整HEAD。用户给出的短SHA `f171fa0`解析为 `f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`；现场main为 `0e66cab5ffd636e40a0f378d6017326603a3196a`。
2. `git merge-base`返回exact main；source唯一parent也是exact main。`git rev-list --count main..source`为1，merge commit数为0，逐提交log只含 `f171fa05… fix(stream): accept Copilot item id drift`。Range与commit两种输入的stable patch-id均为 `cf17db7175a3c94d4dc6e22f512fd8b0d728148a`；binary full-index diff的SHA-256为 `10820af0a300920fbbe7fd2a7e9cf70bc5728692e67f12a01670757a74aa446a`；`git diff --check`退出零。
3. 净range与单commit的pathset完全相同，均为五条修改路径。每条main preimage与source result blob均以 `git rev-parse <commit>:<path>`和 `git ls-tree <commit> -- <path>`两种不同查询交叉核对，一致结果列于下表。
4. Main index为空，且不存在 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。Main工作树并不clean：存在大量既有未跟踪 `docs/tmp/**`与三项 `verification/**`资产；systemd rebuild worktree另有未跟踪临时文档。逐个扫描全部registered worktree的tracked、staged及untracked dirty paths后，候选五路径与tracked WIP交集为空，与全部dirty path交集也为空。该结论不授权stash、restore、checkout、覆盖或清理任何living WIP；执行时必须重算。
5. Main就是source base，`0e66cab5..refs/heads/main`提交数为0，对候选五路径的同range log无命中。因此现场不存在main同路径前进，也无需语义合成。若执行时main已经前移，必须重新计算merge-base、逐路径preimage、main同路径log、WIP交集与staged oracle；任一路径有main-side命中时停止机械squash，先逐hunk语义合成并独立复核。
6. Exact-tip独立复评R2结论为 `PASS／0 blocker／0 major`，确认先前两项测试缺口均已关闭：event-level `item_id: null`在strict／relaxed两种模式下继续等价于missing；relaxed模式仍严格保护output association、item type、function `call_id`／`name`与content coordinates。本轮另行重读最终实现和测试，没有把复评者结论直接当作Git对象或测试证据。
7. 本轮在exact source tip上使用主项目虚拟环境，但以 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-item-identity/src`绑定source代码，并确认parser、renderer与route模块的 `__file__`均位于source worktree。最小parser identity selector实测15个展开节点通过，独立 `--collect-only`同为15；最小route selector实测2个节点通过，独立collect同为2。合计17个节点的数字口径是下文两个selector集合，且由执行与collect两种方法交叉核对。五路径Ruff通过，Pyright为 `0 errors, 0 warnings, 0 informations`。验证前后source porcelain SHA-256均为空状态 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

### 第一人称执行视角

1. **作为squash执行者**：我先在main同一shell链验证物理root、branch、`HEAD == refs/heads/main == 0e66cab5ffd636e40a0f378d6017326603a3196a`，再验证source ref与source worktree都精确为 `f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`且source clean；随后检查main index为空、无进行中的Git操作，并重新求全部registered worktree tracked WIP与五路径的交集。任一identity、preimage、source clean或WIP交集漂移都立即停止，不通过stash／restore／覆盖来制造绿灯。
2. **作为协议执行者**：Copilot route中同一 `output_index`的added／content part／text delta／text done／content done／item done可以使用不同但非空item IDs并成功输出 `message_stop`；generic route遇到同类漂移必须输出typed `item_id_mismatch`；event-level missing与explicit null在strict／relaxed两种模式下继续允许；present empty／non-string ID仍失败；relaxed开关不得放宽unknown output index、item type、content index、function `call_id`或`name`。最终代码与正反测试共同覆盖这些路径。
3. **作为载荷形成者**：所有执行前门全绿后，我只运行一次 `git merge --squash f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`。我不会执行regular merge、`git merge`默认形态、`--ff`、`--ff-only`、`--no-ff`、任何隐式fast-forward、单笔／多笔／range cherry-pick，也不会以任何其他命令把source commit直接带入main ancestry。
4. **作为staged-result核验者**：`merge --squash`命令成功不等于门通过。我会在commit前验证cached pathset精确等于本文五路径、cached stable patch-id等于 `cf17db71…`、五个stage-0 result blob逐项等于本文oracle、`git diff --cached --check`无输出，且cached集合不含本报告、其他 `docs/tmp/**`、verification资产或并行WIP。任一不符都停止，不提交。
5. **作为main-side验证者**：在main staged squash结果上绑定main自身 `src`并验证三个生产模块从main加载，运行本文15＋2节点selector、独立collect、五路径Ruff与Pyright。全部退出零后才形成一个新的单一non-merge main commit；随后验证该commit唯一parent为执行前exact `0e66cab5…`，commit pathset、patch-id与五个result blobs仍匹配本文oracle。不能沿用source-side退出码替代main-side门。
6. **作为归档执行者**：只有main-side门、单parent与内容oracle全绿后，reviewed-source archive才允许精确指向 `f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`。Archive动作未由本报告执行；未来main squash commit只承载主线结果，不能替代reviewed-source provenance。

## 完整单提交 range

Base：`0e66cab5ffd636e40a0f378d6017326603a3196a`。Final source tip：`f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`。

| 顺序 | Commit | Parent | Subject | Per-commit pathset |
|---|---|---|---|---|
| 1 | `f171fa05bc0a2afcdd1dab12d3010cf09ce978ab` | `0e66cab5ffd636e40a0f378d6017326603a3196a` | `fix(stream): accept Copilot item id drift` | `src/app/delivery/responses_anthropic_stream.py`；`src/app/openai/responses_stream_parser.py`；`src/app/routes/anthropic.py`；`tests/smoke/test_anthropic_responses_stream_route.py`；`tests/unit/test_responses_stream_parser.py` |

该range只有上述一笔提交，且该提交只有一个parent，不含merge commit。Source ref `refs/heads/fix/copilot-item-identity`在审计时精确指向final tip。

## 净 pathset、main preimage与source result blobs

| Status | Path | `main@0e66cab5` preimage blob | `source@f171fa05` result blob |
|---|---|---|---|
| M | `src/app/delivery/responses_anthropic_stream.py` | `3ba6b1357c13f097a12f704ab49dbc3d2def2189` | `04919041e3e232c80d4db072146f28a224ae0b42` |
| M | `src/app/openai/responses_stream_parser.py` | `f09ce87a9f21e8470dff291a7fcff8e4c54a8801` | `5f0e4f843c9393c04836f7517582cf7574b97a86` |
| M | `src/app/routes/anthropic.py` | `af32e2e520daa5cbe7ba1ae3f56786389e52fbc7` | `6ecebf16030d0de501f7dd4d58144cd5ebb61926` |
| M | `tests/smoke/test_anthropic_responses_stream_route.py` | `74bdeb1a8cfcab7fef9abe4b81263c4bed49b347` | `b751c4448db03b0fd6bb38d575b9050e1b5cf995` |
| M | `tests/unit/test_responses_stream_parser.py` | `71f9c8b9bfba680a47e8baa315ab41963fa658f4` | `91caf6142eb4aeecc8d4fc59c16caf805b580354` |

## Current living WIP与候选路径交集

Main已有大量未跟踪 `docs/tmp/**`与三项 `verification/**`资产；`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`另有未跟踪 `docs/tmp/260807-systemd-installer-rebuild-resume.md`。Source worktree自身clean。逐worktree扫描tracked、staged及untracked dirty paths后，所有current **tracked WIP**与item identity净五路径的交集为**空集合**；把untracked路径也纳入后，全部dirty path交集仍为空集合。

本报告自身是main的新增未跟踪文档，但不属于候选五个代码／测试路径，不得夹带进squash载荷。该结论不表示main clean，也不授权处理任何WIP。执行时必须重算交集；只要五路径中任一项成为dirty path，就停止并交回其owner，不得自行stash、restore、checkout、吸收或覆盖。

## 唯一允许的 merge --squash 门

### Gate A：main与source身份

- Main物理root与Git top-level均为 `/home/xp/src/ghc-api-proxy-py`；branch为 `main`；`HEAD == refs/heads/main == 0e66cab5ffd636e40a0f378d6017326603a3196a`。
- Source物理root与Git top-level均为 `/home/xp/src/ghc-api-proxy-py-item-identity`；branch为 `fix/copilot-item-identity`；`HEAD == refs/heads/fix/copilot-item-identity == f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`；source index／worktree为空。
- Merge-base、唯一parent、单提交、零merge commit、净五路径与stable patch-id仍匹配本文oracle。

### Gate B：main preimage、Git状态、主线演进与living WIP

- Main index为空；不存在 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。
- 五路径main preimage逐项等于本文表格。
- `0e66cab5..current-main`提交数仍为零。若不为零，先检查五路径命中；任一路径有命中必须语义合成并重新评审，不能继续使用本文的patch-id或result blob门。即使五路径无命中，也必须重新冻结new-main identity、preimage、WIP交集和staged oracle后才能继续。
- 重新枚举所有registered worktree的tracked／staged／untracked dirty paths并与候选五路径求交；交集必须为空。
- 任一门失败即停止，不用stash、restore、checkout、force或覆盖并行WIP来改变结论。

### Gate C：唯一载荷形成动作

只允许一次：`git merge --squash f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`。

明确禁止：

- regular merge或任何产生merge commit的形状；
- fast-forward、`--ff`、`--ff-only`、`--no-ff`或隐式FF；
- cherry-pick单笔、多笔或range；
- 把source commit直接带入main ancestry；
- 把本报告、其他 `docs/tmp/**`、verification资产或并行WIP夹带进squash载荷。

### Gate D：commit前 staged-result

- Cached pathset精确等于五路径：`src/app/delivery/responses_anthropic_stream.py`、`src/app/openai/responses_stream_parser.py`、`src/app/routes/anthropic.py`、`tests/smoke/test_anthropic_responses_stream_route.py`、`tests/unit/test_responses_stream_parser.py`。
- Cached stable patch-id精确等于 `cf17db7175a3c94d4dc6e22f512fd8b0d728148a`。
- 五个stage-0 cached result blob精确等于本文 `source@f171fa05` result blob。
- `git diff --cached --check`无输出；cached集合不含任何第六路径。

### Gate E：最小 main-side tests、commit与archive

在main的staged squash结果上绑定main自身 `src`，要求下列门全部退出零：

1. Import oracle：`app.openai.responses_stream_parser`、`app.delivery.responses_anthropic_stream`与 `app.routes.anthropic`的 `__file__`均位于main物理root下。
2. Parser identity unit selector：文件 `tests/unit/test_responses_stream_parser.py`，表达式 `default_item_identity or missing_event_item_id or null_event_item_id or relaxed_item_identity`。Source exact tip实测与独立collect均为15个参数展开节点。
3. Route identity smoke selector：文件 `tests/smoke/test_anthropic_responses_stream_route.py`，表达式 `copilot_route_accepts_distinct_response_and_item_ids_across_lifecycle or generic_route_rejects_distinct_item_ids_across_message_lifecycle`。Source exact tip实测与独立collect均为2个节点。
4. Ruff检查本文五路径。
5. Pyright检查本文五路径，并绑定项目虚拟环境解释器。

全部通过后才可形成一个新的单一non-merge main commit，commit message遵守Conventional Commits。提交后验证唯一parent为执行前exact `0e66cab5…`，commit pathset、stable patch-id与五个result blobs匹配本文oracle，并进行一次main merged-state只读复核。只有上述门全部闭合，才允许创建reviewed-source archive，target固定为 `f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`。任一门失败即停止，不归档、不清理source branch／worktree、不部署、不cutover。

## 事实性发现

未发现问题。审计范围内blocker 0、major 0、minor 0；完整单提交range、净五路径、main preimage、source result blobs、current tracked WIP零路径重叠及最小main-side门均闭合，明确可按本文gate执行单一 `merge --squash`。

## 主观建议

无。用户已经裁定只使用 `merge --squash`；本报告不提供FF、regular merge或cherry-pick替代路线，也不因source是main直接子提交而推翻该决定。

## 结构怪味扫描与处置

- `src/app/routes/anthropic.py:226-247` — **provider条件泄漏风险** — Copilot判断只在route边界形成policy，parser与renderer默认仍为strict；同一个布尔策略同时传给response ID与item ID是本次两片相邻identity兼容需求的明确组合结果。处置：本轮无需修改。
- `src/app/openai/responses_stream_parser.py:933-944` — **relaxed开关误放宽结构合同风险** — event-level missing／null在两种模式下维持既有允许行为，present ID仍须nonempty string，只有跨事件相等比较受开关控制；done item仍无条件要求nonempty string。处置：本轮无需修改。
- `tests/unit/test_responses_stream_parser.py:95-258`与 `tests/smoke/test_anthropic_responses_stream_route.py:1449-1563` — **单向测试假绿风险** — final tests同时覆盖Copilot接受、generic拒绝、missing／null正样本、present empty负样本，以及association／type／content coordinate／function identity负样本。先前WIP评审指出的测试判别力major已关闭。处置：本轮无需修改。

## 报告评审状态

本会话是叶子reviewer，不能派生另一名reviewer。本报告已完成事实证伪、双视角执行模拟、全文自读与exact-tip最小门；按wrap-up产物规则，主会话在对外采用本报告或据此执行squash前仍须独立复核本文current-state断言、数字口径、blob／patch-id oracle与执行门。该复核义务不改变本轮 `0 blocker／0 major／0 minor`结论，但不得静默省略。

## 最终结论

**`fix/copilot-item-identity@f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`相对现场exact `main@0e66cab5ffd636e40a0f378d6017326603a3196a`为 `0 blocker／0 major／0 minor`，限定验证为 `PASS`，0 major明确可执行。** 当前main就是source唯一parent，五路径没有后续main改动，故无需语义合成。唯一允许的集成形状是在执行时重验Gate A／B后运行单一 `git merge --squash f171fa05…`，再通过Gate D／E形成新的non-merge main commit。**禁止fast-forward、regular merge与cherry-pick。** Reviewed-source archive target固定为 `f171fa05bc0a2afcdd1dab12d3010cf09ce978ab`；本报告没有执行merge、commit、archive、清理、部署或cutover。
