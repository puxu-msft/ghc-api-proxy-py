# Token identity source squash 只读审计

- **评审范围**：只读审计主树 `/home/xp/src/ghc-api-proxy-py` 的现场 `main@6e0112f90f39245f77618a7b4887dfe6b526c60a` 与 source worktree `/home/xp/src/ghc-api-proxy-py-token-identity` 的 `fix/copilot-token-identity@8f164d897966fd80f9a5087083f420f2caf79ac9`。覆盖完整两提交 range、逐提交与净 pathset、main preimage／source result blobs、所有 registered worktree 的 living WIP 路径交集、source final-tip 定向验证、唯一允许的 `merge --squash` 执行门、最小 main-side tests及 reviewed-source archive target。本轮没有执行 merge、fast-forward、regular merge、cherry-pick、commit、archive、ref 更新、部署或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入 squash。0 major 明确可执行。** Source range恰好从现场 main HEAD分叉并线性前进两笔 non-merge commits；净五路径的 main preimage与source result闭合，所有 current living WIP与候选五路径交集为空。现场 main相对source base没有任何后续提交，故当前无需语义合成；执行时只允许在 exact main preimage上运行一次 `git merge --squash 8f164d897966fd80f9a5087083f420f2caf79ac9`，随后通过 staged identity与最小 main-side门并形成一个新的单一 non-merge main commit。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **archive target**：`8f164d897966fd80f9a5087083f420f2caf79ac9`。后续 archive ref无论采用何种名称，都必须精确指向这个 reviewed-source tip；不得指向未来 main squash commit，也不得退回只含实现的中间 tip `d48792f7e47cebd34aaf61b2b86bcea337446548`。
- **范围边界**：本 verdict只放行 Copilot token exchange四个 identity headers、bootstrap装配、逐attempt动态核心头覆盖及其测试。它不扩展到完整 auth provider、device flow、真实 endpoint A/B、完整上游 header矩阵、部署或 cutover。

## 双视角覆盖证据

### 机械核对视角

1. 所有采信的 shell结果都在同一次调用中验证物理 cwd、Git top-level、branch与完整 HEAD。Main始终为 `main@6e0112f90f39245f77618a7b4887dfe6b526c60a`；source始终为 `fix/copilot-token-identity@8f164d897966fd80f9a5087083f420f2caf79ac9`，source index／worktree为空。
2. `git merge-base main 8f164d8`返回 exact main `6e0112f…`；`git rev-list --count 6e0112f..8f164d8`为2，逐提交 parent log确认两笔提交线性且均只有一个parent。净 range stable patch-id为 `fcc76000818ca31d8dcabbdb71fbd835cb1dd3df`；`git diff --check`无输出。
3. `git diff --name-status`与逐提交 pathset对账得到净五路径，全部为 `M`。五个 main preimage blob与source result blob均直接从对应commit tree解析；只读 `git merge-tree`未发现 conflict marker。
4. Main index为空，且不存在 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。Main并不clean：存在既有未跟踪 `docs/tmp/**`及 `verification/**`资产；另一个 systemd worktree有一份未跟踪临时文档。逐个枚举全部 registered worktree的tracked、staged与untracked dirty paths后，它们与候选五路径的交集为**空集合**。这个结论不授权stash、restore、checkout、覆盖或清理任何living WIP。
5. Main prewrite复核得到 `source base == current main == 6e0112f…`、`main commits after source base == 0`，且对五路径执行的 `git log 6e0112f..main -- <paths>`无命中。因此当前不存在“main后来修改了同路径”的语义合成任务。若执行时main已经前移，必须重新枚举 `6e0112f..new-main` 的五路径改动：有命中时不得机械沿用本报告或直接squash，须逐hunk对账新main语义与token identity不变量，形成并独立复核合成结果；无命中时也必须重算preimage、WIP交集与staged oracle。
6. 既有首轮 review在未提交中间态发现一项 major：大小写变体的静态核心头可能与动态核心头并存。实现提交 `d48792f…`改为先构造 `httpx.Headers`、再以 `Headers.update()`写入动态 `Accept`、`Authorization`与固定内部 API version；既有验收绑定 `d48792f…`为PASS。Final tip `8f164d8…`再加入大小写变体与401重试保护测试。本报告没有把旧验收冒充final-tip证书，而是重读tip代码、测试并在 exact `8f164d8…`上重跑门。
7. Exact source tip上以 `PYTHONPATH=<source>/src`绑定import，并断言 `app.auth.copilot`、`app.upstream.bootstrap`与`app.upstream.copilot`均从source worktree加载。五个改动路径的定向 pytest为 `13 passed`，独立 `--collect-only`为13；Ruff通过；Pyright为 `0 errors, 0 warnings, 0 informations`。加入未改但守护共享 `build_copilot_headers()` 的 `tests/unit/test_upstream_client.py`后，拟定的最小 main-side pytest为 `21 passed`，独立收集同为21。首次把预期数误写为19的自制门按预期false-red；该结果未归因于产品失败，复核实际node IDs后以21重新执行并闭合。
8. Source验证前后 porcelain SHA-256均为空状态 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。共享终端曾回传其他并发任务内容，两次受污染回传全部作废；采信结果来自唯一 `/tmp/260808-token-identity-final-gate-31ef7ca6.log`与 `/tmp/260808-token-identity-min-main-tests-r2-31ef7ca6.log`，两者内部再次绑定source cwd、top-level、branch与HEAD。

### 第一人称执行视角

1. **作为 squash执行者**：我先在main同一shell链验证物理root、branch、`HEAD == refs/heads/main == 6e0112f…`，再验证source ref与source worktree都精确为 `8f164d8…`且clean；随后检查main index为空、无进行中的Git操作，并重新求全部registered worktree living WIP与五路径的交集。任一identity、preimage、source clean或WIP交集漂移都立即停止，不通过stash／restore／覆盖来制造绿灯。
2. **作为主线演进裁决者**：我检查 `6e0112f..current-main`。当前计数为零，故无需语义合成。若执行时该range非空但五路径无命中，可重新审计后继续；若任一候选路径有命中，我会停止，把new-main版本、source净变化及共同不变量逐hunk合成并独立复核，而不是让文本无冲突替代语义裁决。
3. **作为载荷形成者**：所有执行前门全绿后，我只运行一次 `git merge --squash 8f164d897966fd80f9a5087083f420f2caf79ac9`。我不会执行regular merge、`git merge`默认形态、`--ff`、`--ff-only`、`--no-ff`、任何隐式fast-forward、单笔／多笔／range cherry-pick，也不会逐笔回放 `d48792f…`与 `8f164d8…`。
4. **作为 staged-result核验者**：`merge --squash`命令成功不等于门通过。我会在commit前验证cached pathset精确等于本文五路径、cached stable patch-id等于 `fcc76000…`、五个stage-0 result blob逐项等于本文oracle、`git diff --cached --check`无输出，且cached集合不含本报告、其他 `docs/tmp/**`、verification资产或并行WIP。任一不符都停止，不提交。
5. **作为 main-side验证者**：在main的staged squash结果上绑定 `PYTHONPATH=<main>/src`并验证三个生产模块从main加载，运行本文三文件pytest集合、独立collect、五路径Ruff与Pyright。全部退出零后才形成一个新的单一 non-merge commit；随后验证该commit唯一parent为执行前exact `6e0112f…`，commit pathset、patch-id与五个result blob仍匹配本文oracle。不能沿用source-side退出码代替main-side门。
6. **作为归档执行者**：只有main-side门、单parent与内容oracle全绿后，reviewed-source archive才允许精确指向 `8f164d8…`。Archive动作未由本报告执行；未来main squash commit只承载主线结果，不能替代reviewed-source provenance。

## 完整两提交 range

Base：`6e0112f90f39245f77618a7b4887dfe6b526c60a`。Final source tip：`8f164d897966fd80f9a5087083f420f2caf79ac9`。

| 顺序 | Commit | Parent | Subject | Per-commit pathset |
|---|---|---|---|---|
| 1 | `d48792f7e47cebd34aaf61b2b86bcea337446548` | `6e0112f90f39245f77618a7b4887dfe6b526c60a` | `fix(auth): send identity headers for token exchange` | `src/app/auth/copilot.py`；`src/app/upstream/bootstrap.py`；`src/app/upstream/copilot.py`；`tests/integration/test_phase1_bootstrap.py`；`tests/unit/test_copilot_token.py` |
| 2 | `8f164d897966fd80f9a5087083f420f2caf79ac9` | `d48792f7e47cebd34aaf61b2b86bcea337446548` | `test(auth): protect dynamic token headers` | `tests/unit/test_copilot_token.py` |

`git rev-list 6e0112f..8f164d8`只包含上述两笔，merge commit数为零；第二笔是对第一笔动态核心头覆盖语义的永久测试保护，不是可从squash范围裁掉的旁支。

## 净 pathset、main preimage与source result blobs

| Status | Path | `main@6e0112f` preimage blob | `source@8f164d8` result blob |
|---|---|---|---|
| M | `src/app/auth/copilot.py` | `8f8f9434453f2efe1cb289d1f474d6594765c3ad` | `f94d291e34b908358c1ad70cf921664ad485b338` |
| M | `src/app/upstream/bootstrap.py` | `48281355e305d76906ae4cd590ee939b7c7a20c6` | `0a401c9b217bff9107198cad0223834d0ef1c7d0` |
| M | `src/app/upstream/copilot.py` | `bea709db510a0c901b7c414008dd5cb417886dc5` | `d2d84d0a908732c10e9dcd45c24283b655b124fa` |
| M | `tests/integration/test_phase1_bootstrap.py` | `4106d5bc16af18ab0684218cd0bf7c7d400bf68c` | `e0a3c9c5ef454a086fafa08bf1cb5d71af570415` |
| M | `tests/unit/test_copilot_token.py` | `70cbf6f990e1099c1fab452af29ee96da170210b` | `57760a383088e518334aa9a41980b3e2a546d13e` |

## Current living WIP与代码重叠

Main包含大量既有未跟踪 `docs/tmp/**`与三项 `verification/**`资产；`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`另有一份未跟踪 `docs/tmp/260807-systemd-installer-rebuild-resume.md`。其余registered worktree在扫描时没有dirty path。逐worktree扫描tracked、staged及untracked路径后，上述所有current living WIP与token identity净五路径的交集为**空集合**。

该结论不表示main clean，也不授权处理这些WIP。执行时必须重算交集；只要五路径中任一项成为dirty path，就停止并交回其owner，不得自行stash、restore、checkout、吸收或覆盖。

## 唯一允许的 merge --squash 门

### Gate A：main与source身份

- Main物理root与Git top-level均为 `/home/xp/src/ghc-api-proxy-py`；branch为 `main`；`HEAD == refs/heads/main == 6e0112f90f39245f77618a7b4887dfe6b526c60a`。
- Source物理root与Git top-level均为 `/home/xp/src/ghc-api-proxy-py-token-identity`；branch为 `fix/copilot-token-identity`；`HEAD == refs/heads/fix/copilot-token-identity == 8f164d897966fd80f9a5087083f420f2caf79ac9`；source index／worktree为空。
- Merge-base、两提交parent链、零merge commit、净五路径与stable patch-id仍匹配本文oracle。

### Gate B：main preimage、Git状态、主线演进与living WIP

- Main index为空；不存在 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。
- 五路径main preimage逐项等于本文表格。
- `6e0112f..current-main`提交数仍为零。若不为零，先检查五路径命中；有命中必须语义合成并重新评审，不能继续使用本文的patch-id或result blob门。
- 重新枚举所有registered worktree的tracked／staged／untracked dirty paths并与候选五路径求交；交集必须为空。
- 任一门失败即停止，不用stash、restore、checkout、force或覆盖并行WIP来改变结论。

### Gate C：唯一载荷形成动作

只允许一次：`git merge --squash 8f164d897966fd80f9a5087083f420f2caf79ac9`。

明确禁止：

- regular merge或任何产生merge commit的形状；
- fast-forward、`--ff`、`--ff-only`、`--no-ff`或隐式FF；
- cherry-pick单笔、多笔或range；
- 逐笔回放source的两笔commit；
- 把本报告、其他 `docs/tmp/**`、verification资产或并行WIP夹带进squash载荷。

### Gate D：commit前 staged-result

- Cached pathset精确等于五路径：`src/app/auth/copilot.py`、`src/app/upstream/bootstrap.py`、`src/app/upstream/copilot.py`、`tests/integration/test_phase1_bootstrap.py`、`tests/unit/test_copilot_token.py`。
- Cached stable patch-id精确等于 `fcc76000818ca31d8dcabbdb71fbd835cb1dd3df`。
- 五个stage-0 cached result blob精确等于本文 `source@8f164d8` result blob。
- `git diff --cached --check`无输出；cached集合不含任何第六路径。

### Gate E：最小 main-side tests、commit与archive

在main的staged squash结果上绑定main自身 `src`，要求下列门全部退出零：

1. Import oracle：`app.auth.copilot`、`app.upstream.bootstrap`与`app.upstream.copilot`的 `__file__`均位于main物理root下。
2. Pytest：`tests/unit/test_copilot_token.py`、`tests/integration/test_phase1_bootstrap.py`、`tests/unit/test_upstream_client.py`。Source exact tip实测为 `21 passed`；main-side必须独立重跑，不能硬编码“21 passed”替代退出码。
3. 同一selector集合的独立 `--collect-only` node ID清点；若数量相对本报告21发生变化，先解释新增／删除，再裁决，不以凑数方式改测试。
4. Ruff检查净五路径。
5. Pyright检查净五路径并绑定项目虚拟环境解释器。

全部通过后才可形成一个新的单一 non-merge main commit，commit message遵守Conventional Commits。提交后验证唯一parent为执行前exact `6e0112f…`，commit pathset、stable patch-id与五个result blob匹配本文oracle，并进行一次main merged-state只读复核。只有上述门全部闭合，才允许创建reviewed-source archive，target固定为 `8f164d897966fd80f9a5087083f420f2caf79ac9`。任一门失败即停止，不归档、不清理source branch／worktree、不部署、不cutover。

## 事实性发现

未发现问题。审计范围内 blocker 0、major 0、minor 0；完整两提交range、净五路径、main preimage、source result blobs、current living WIP零代码路径重叠及最小main-side门均闭合，明确可按本文gate执行单一 `merge --squash`。

## 主观建议

无。用户已经裁定只使用 `merge --squash`；本报告不提供FF、regular merge或cherry-pick替代路线，也不因source可线性fast-forward而推翻该决定。

## 结构怪味扫描与处置

- `src/app/upstream/copilot.py:24-31,44-46` — **重复identity builder风险** — 四个identity headers集中在 `build_copilot_identity_headers()`，普通Copilot请求复用同一builder；未发现第二份弱化实现。处置：本轮无需修改。
- `src/app/auth/copilot.py:35,44,99-116` — **静态身份与动态核心头职责混合风险** — 构造时复制冻结静态映射，每次attempt使用case-insensitive `httpx.Headers.update()`重建动态核心头；测试覆盖大小写变体与401后token变化，未发现stale核心头并存。处置：本轮无需修改。
- `src/app/upstream/bootstrap.py:157-174` — **helper存在但未接入真实启动路径风险** — bootstrap把同一builder结果传给 `CopilotTokenManager`，随后同步等待首次exchange；integration测试检查实际token request。处置：本轮无需修改。
- `tests/unit/test_copilot_token.py:40-116,212-258`与 `tests/integration/test_phase1_bootstrap.py:38-73` — **只测快乐路径导致false-green风险** — 已覆盖调用方映射复制、大小写冲突核心头、401动态刷新及真实bootstrap装配；未发现本切片内缺失的主要反向分支。处置：本轮无需修改。

## 报告评审状态

本会话是叶子reviewer，不能派生另一名reviewer。本报告已完成事实证伪、双视角执行模拟、全文自读与exact-tip最小门；按wrap-up产物规则，主会话在对外采用本报告或据此执行squash前仍须独立复核本文current-state断言、数字口径、blob／patch-id oracle与执行门。该复核义务不改变本轮 `0 blocker／0 major／PASS` 结论，但不得静默省略。

## 最终结论

**`fix/copilot-token-identity@8f164d897966fd80f9a5087083f420f2caf79ac9`相对现场exact `main@6e0112f90f39245f77618a7b4887dfe6b526c60a`为 `0 blocker／0 major／0 minor`，限定验证为 `PASS`，0 major明确可执行。** 当前main就是source base，五路径没有后续main改动，故无需语义合成。唯一允许的集成形状是在执行时重验A／B门后运行单一 `git merge --squash 8f164d8…`，再通过D／E门形成新的non-merge main commit。**禁止fast-forward、regular merge与cherry-pick。** Reviewed-source archive target固定为 `8f164d897966fd80f9a5087083f420f2caf79ac9`；本报告没有执行merge、commit、archive、清理、部署或cutover。
