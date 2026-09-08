# Copilot response identity source squash 只读审计

- **评审范围**：只读审计主树 `/home/xp/src/ghc-api-proxy-py` 的 exact `main@c188165dd413b7683a65472781ca3bef9c1a29b3` 与 source worktree `/home/xp/src/ghc-api-proxy-py-response-identity` 的 `fix/copilot-response-identity@1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。覆盖完整两提交 range、逐提交与净 pathset、main preimage／source result blobs、所有 registered worktree 的 living WIP 路径交集、exact-tip 代码复评与定向验证、唯一允许的 `merge --squash` 执行门、最小 main-side tests及 reviewed-source archive target。本轮没有执行 merge、fast-forward、regular merge、cherry-pick、commit、archive、ref 更新、部署或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入 squash。0 major 明确可执行。** Source range恰好从现场 main HEAD分叉并线性前进两笔 non-merge commits；净五路径的 main preimage与source result blobs闭合，所有 current living WIP与候选五路径无代码路径重叠。执行时只允许在 exact main preimage上运行一次 `git merge --squash 1bc5a8185a6a19101679e13c9a3a0bda3072bab4`，随后通过 staged identity、main-side最小门并形成一个新的单一 non-merge main commit。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **archive target**：`1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。后续 archive ref无论采用何种名称，都必须精确指向这个 reviewed-source tip；不得指向未来 main squash commit，也不得退回中间 tip `08643a9f98fff3f25d28467e37dd71e64b4724f4`。审计时没有 `refs/heads/archive/**` 指向该 source，推荐名称 `refs/heads/archive/260807-copilot-response-identity` 也尚不存在。
- **范围边界**：本 verdict只放行 Copilot Responses stream lifecycle中非空 response ID可漂移、generic默认保持稳定ID、所有 nested-response terminal仍要求非空ID、`error` identity继续严格及其回归测试。它不扩展为完整stream、完整bridge、部署或cutover通过。

## 双视角覆盖证据

### 机械核对视角

1. 每个采信的 shell结果都在同一次调用内验证物理cwd、Git top-level、branch与完整HEAD。用户给出的短SHA实际解析为 `main@c188165dd413b7683a65472781ca3bef9c1a29b3` 与 source `1bc5a8185a6a19101679e13c9a3a0bda3072bab4`；报告全程使用这两个Git对象，不使用曾出现在并发上下文中的相似完整SHA。
2. `git merge-base`返回 exact main `c188165d…`；`git rev-list --count`与逐提交parent log交叉确认range恰为两笔线性提交，merge commit数为零，main在base之后的提交数为零。净range stable patch-id为 `069edc647c34e8f709a8d78cfdcfa146a75f908f`，binary full-index diff的SHA-256为 `eba3c1178829648faa7a10bd2b7e1e7ec0e50b9b179259ca8a01543b4985b866`，`git diff --check`无输出。
3. `git diff --name-status`与逐提交pathset对账得到净五路径，全部为修改。五个main preimage blob与source result blob均直接从对应commit tree解析；只读 `git merge-tree`未发现conflict marker。Main index为空，且不存在 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。
4. Main并不clean：存在大量既有未跟踪 `docs/tmp/**`与三项 `verification/**`资产；systemd rebuild worktree另有一份未跟踪临时文档。逐个枚举所有registered worktree的tracked、staged及untracked dirty paths后，它们与候选五路径的交集均为空。该结论不授权stash、restore、checkout、覆盖或清理任何living WIP；执行时必须重新扫描。
5. 既有 `docs/tmp/260807-review-copilot-response-identity-r2.md`精确绑定同一base与source tip，verdict为 `0 blocker／0 major／0 minor`、可squash。它确认generic默认严格、Copilot route单点放宽、所有非`error` lifecycle／terminal仍要求非空nested ID、`error`继续严格及成功terminal在`message_stop`前校验。
6. 本轮在exact source tip上使用主项目虚拟环境，但将`PYTHONPATH`绑定到source `src`，并以模块`__file__`确认实际加载source代码。独立身份探针覆盖strict／relaxed下三类nested-response terminal缺失ID、Copilot三阶段ID漂移及generic ID mismatch，结果为`PASS`。
7. Source exact tip定向unit selector实测`9 passed`，独立参数口径为`1＋2＋5＋1＝9`；最小route selector实测`3 passed`，独立collect同为3。两文件合并回归实测`63 passed`，独立collect同为63；五路径Ruff通过，Pyright为`0 errors, 0 warnings, 0 informations`。首次测试因source worktree没有独立`.venv`而以`rc=127`失败，前后工作树仍clean；改用主项目解释器并绑定source import后上述门全部退出零。Source验证前后porcelain SHA-256均为空状态`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

### 第一人称执行视角

1. **作为squash执行者**：我先在main同一shell链验证物理root、branch、`HEAD == refs/heads/main == c188165dd413b7683a65472781ca3bef9c1a29b3`，再验证source ref与source worktree都精确为`1bc5a8185a6a19101679e13c9a3a0bda3072bab4`且clean；随后检查main index为空、无进行中的Git操作，并重新求全部registered worktree living WIP与五路径的交集。任一identity、preimage、source clean或WIP交集漂移都立即停止，不通过stash／restore／覆盖来制造绿灯。
2. **作为协议执行者**：Copilot route中`response.created`、`response.in_progress`与`response.completed`可以携带三个不同但非空的nested ID并成功输出`message_stop`；generic route遇到跨帧ID变化必须输出typed error且不得输出`message_stop`；strict与relaxed两种parser模式遇到任何非`error` nested-response terminal缺失或空ID都必须拒绝。最终代码与正反测试同时满足这三条路径。
3. **作为载荷形成者**：所有执行前门全绿后，我只运行一次 `git merge --squash 1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。我不会执行regular merge、`git merge`默认形态、`--ff`、`--ff-only`、`--no-ff`、任何隐式fast-forward、单笔／多笔／range cherry-pick，也不会逐笔回放`08643a9…`与`1bc5a81…`。
4. **作为staged-result核验者**：`merge --squash`命令成功不等于门通过。我会在commit前验证cached pathset精确等于本文五路径、cached stable patch-id等于`069edc64…`、五个stage-0 result blob逐项等于本文oracle、`git diff --cached --check`无输出，且cached集合不含本报告、其他`docs/tmp/**`、verification资产或并行WIP。任一不符都停止，不提交。
5. **作为main-side验证者**：在main staged squash结果上绑定main自身`src`，先运行9个parser identity unit节点与3个route identity smoke节点，再执行五路径Ruff与Pyright。全部退出零后才形成一个新的单一non-merge main commit；随后验证该commit唯一parent为执行前exact `c188165d…`，commit pathset、patch-id与五个result blobs仍匹配本文oracle。不能沿用source-side退出码代替main-side门。
6. **作为归档执行者**：只有main-side门、单parent与内容oracle全绿后，reviewed-source archive才允许精确指向`1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。Archive动作未由本报告执行；未来main squash commit只承载主线结果，不能替代reviewed-source provenance。

## 完整两提交 range

Base：`c188165dd413b7683a65472781ca3bef9c1a29b3`。Final source tip：`1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。

| 顺序 | Commit | Parent | Subject | Per-commit pathset |
|---|---|---|---|---|
| 1 | `08643a9f98fff3f25d28467e37dd71e64b4724f4` | `c188165dd413b7683a65472781ca3bef9c1a29b3` | `fix(stream): accept Copilot response id drift` | `src/app/delivery/responses_anthropic_stream.py`；`src/app/openai/responses_stream_parser.py`；`src/app/routes/anthropic.py`；`tests/smoke/test_anthropic_responses_stream_route.py`；`tests/unit/test_responses_stream_parser.py` |
| 2 | `1bc5a8185a6a19101679e13c9a3a0bda3072bab4` | `08643a9f98fff3f25d28467e37dd71e64b4724f4` | `fix(stream): require terminal response identity` | `src/app/openai/responses_stream_parser.py`；`tests/unit/test_responses_stream_parser.py` |

第二笔关闭了首笔中“strict反而允许terminal缺失ID、relaxed反而拒绝”的反向实现，并补永久回归；它不是可从squash范围裁掉的旁支。

## 净 pathset、main preimage与source result blobs

| Status | Path | `main@c188165d` preimage blob | `source@1bc5a818` result blob |
|---|---|---|---|
| M | `src/app/delivery/responses_anthropic_stream.py` | `3b46588994cb382e9b27abd32e3a4cd0bbb58a83` | `3ba6b1357c13f097a12f704ab49dbc3d2def2189` |
| M | `src/app/openai/responses_stream_parser.py` | `6aa0bce39ab3fedd705eaec6975da487fc71cc74` | `f09ce87a9f21e8470dff291a7fcff8e4c54a8801` |
| M | `src/app/routes/anthropic.py` | `394d044c3231f7517ddad11a2cd4387df040e427` | `af32e2e520daa5cbe7ba1ae3f56786389e52fbc7` |
| M | `tests/smoke/test_anthropic_responses_stream_route.py` | `2a5a419dd7f6270bba113dd408f817a5bcc20019` | `74bdeb1a8cfcab7fef9abe4b81263c4bed49b347` |
| M | `tests/unit/test_responses_stream_parser.py` | `35bdea62c4a3dd3aaf037f2ff40b2e9c5b4bfb61` | `71f9c8b9bfba680a47e8baa315ab41963fa658f4` |

## Current living WIP与代码重叠

Main包含大量既有未跟踪`docs/tmp/**`与三项`verification/**`资产；`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`另有一份未跟踪`docs/tmp/260807-systemd-installer-rebuild-resume.md`。逐worktree扫描tracked、staged及untracked dirty paths后，上述所有current living WIP与response identity净五路径的交集为**空集合**。

本报告自身也是main的未跟踪文档WIP，但不属于候选五个代码／测试路径，不得夹带进squash载荷。该结论不表示main clean，也不授权处理任何WIP。执行时必须重算交集；只要五路径中任一项成为dirty path，就停止并交回其owner，不得自行stash、restore、checkout、吸收或覆盖。

## 唯一允许的 merge --squash 门

### Gate A：main与source身份

- Main物理root与Git top-level均为`/home/xp/src/ghc-api-proxy-py`；branch为`main`；`HEAD == refs/heads/main == c188165dd413b7683a65472781ca3bef9c1a29b3`。
- Source物理root与Git top-level均为`/home/xp/src/ghc-api-proxy-py-response-identity`；branch为`fix/copilot-response-identity`；`HEAD == refs/heads/fix/copilot-response-identity == 1bc5a8185a6a19101679e13c9a3a0bda3072bab4`；source index／worktree为空。
- Merge-base、两提交parent链、零merge commit、净五路径与stable patch-id仍匹配本文oracle。

### Gate B：main preimage、Git状态与living WIP

- Main index为空；不存在`MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。
- 五路径main preimage逐项等于本文表格。
- `c188165d..current-main`提交数仍为零。若main已前移，即使候选五路径没有文本命中，也必须重新计算merge-base、preimage、pathset、WIP交集及staged oracle；任一路径有命中时须先做逐hunk语义合成与独立复核，不能机械沿用本文。
- 重新枚举所有registered worktree的tracked／staged／untracked dirty paths并与候选五路径求交；交集必须为空。
- 任一门失败即停止，不用stash、restore、checkout、force或覆盖并行WIP来改变结论。

### Gate C：唯一载荷形成动作

只允许一次：`git merge --squash 1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。

明确禁止：

- regular merge或任何产生merge commit的形状；
- fast-forward、`--ff`、`--ff-only`、`--no-ff`或隐式FF；
- cherry-pick单笔、多笔或range；
- 逐笔回放source的两笔commit；
- 把本报告、其他`docs/tmp/**`、verification资产或并行WIP夹带进squash载荷。

### Gate D：commit前 staged-result

- Cached pathset精确等于五路径：`src/app/delivery/responses_anthropic_stream.py`、`src/app/openai/responses_stream_parser.py`、`src/app/routes/anthropic.py`、`tests/smoke/test_anthropic_responses_stream_route.py`、`tests/unit/test_responses_stream_parser.py`。
- Cached stable patch-id精确等于`069edc647c34e8f709a8d78cfdcfa146a75f908f`。
- 五个stage-0 cached result blob精确等于本文`source@1bc5a818…`result blob。
- `git diff --cached --check`无输出；cached集合不含任何第六路径。

### Gate E：最小 main-side tests、commit与archive

在main的staged squash结果上绑定main自身`src`，要求下列门全部退出零：

1. Parser identity unit selector：`response_id or relaxed_response_identity`，source exact tip实测与独立collect均为9个参数展开节点。Main-side以退出码与node IDs为准，不以硬编码数量替代成功。
2. Route identity smoke selector：`copilot_route_accepts_distinct_response_ids_across_lifecycle or success_terminal_is_validated_before_message_stop`，source exact tip实测与独立collect均为3个参数展开节点。
3. Ruff检查本文五路径。
4. Pyright检查本文五路径，并绑定项目虚拟环境解释器。

全部通过后才可形成一个新的单一non-merge main commit，commit message遵守Conventional Commits。提交后验证唯一parent为执行前exact`c188165d…`，commit pathset、stable patch-id与五个result blob匹配本文oracle，并进行一次main merged-state只读复核。只有上述门全部闭合，才允许创建reviewed-source archive，target固定为`1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。任一门失败即停止，不归档、不清理source branch／worktree、不部署、不cutover。

## 事实性发现

未发现问题。审计范围内blocker 0、major 0、minor 0；完整两提交range、净五路径、main preimage、source result blobs、current living WIP零代码路径重叠及最小main-side门均闭合，明确可按本文gate执行单一`merge --squash`。

## 主观建议

无。用户已经裁定只使用`merge --squash`；本报告不提供FF、regular merge或cherry-pick替代路线，也不因source可线性fast-forward而推翻该决定。

## 结构怪味扫描与处置

- `src/app/routes/anthropic.py:238-245` — **provider条件泄漏风险** — Copilot判断只在route边界选择policy，parser与renderer保持provider-agnostic默认严格。处置：本轮无需修改。
- `src/app/openai/responses_stream_parser.py:149-150,465-475,760-780` — **一个flag同时放宽结构与相等性风险** — 最终实现只放宽跨帧ID相等比较，不放宽nested object／nonempty string要求，且`error` identity继续严格。处置：本轮无需修改。
- `tests/unit/test_responses_stream_parser.py:843-922`与`tests/smoke/test_anthropic_responses_stream_route.py:1398-1512` — **单向测试假绿风险** — unit覆盖默认拒绝、relaxed非空与`error`严格；smoke同时覆盖Copilot接受和generic拒绝。处置：本轮无需修改。

## 报告评审状态

本会话是叶子reviewer，不能派生另一名reviewer。本报告已完成事实证伪、双视角执行模拟、全文自读与exact-tip最小门；按wrap-up产物规则，主会话在对外采用本报告或据此执行squash前仍须独立复核本文current-state断言、数字口径、blob／patch-id oracle与执行门。该复核义务不改变本轮`0 blocker／0 major／0 minor`结论，但不得静默省略。

## 最终结论

**`fix/copilot-response-identity@1bc5a8185a6a19101679e13c9a3a0bda3072bab4`相对现场exact `main@c188165dd413b7683a65472781ca3bef9c1a29b3`为`0 blocker／0 major／0 minor`，定向验证为`PASS`，0 major明确可执行。** 当前main就是source base，五路径没有后续main改动，故无需语义合成。唯一允许的集成形状是在执行时重验Gate A／B后运行单一`git merge --squash 1bc5a818…`，再通过Gate D／E形成新的non-merge main commit。**禁止fast-forward、regular merge与cherry-pick。** Reviewed-source archive target固定为`1bc5a8185a6a19101679e13c9a3a0bda3072bab4`；本报告没有执行merge、commit、archive、清理、部署或cutover。
