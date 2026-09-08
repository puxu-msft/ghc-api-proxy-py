# Resident byte budget final source squash 审计

- **评审范围**：只读审计主树 `/home/xp/src/ghc-api-proxy-py` 的 exact `main@080105b54614e1320a5c193d7206dcaa584c9b41` 与 source worktree `/home/xp/src/ghc-api-proxy-py-reservation` 的 `feat/resident-byte-budget@5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`。覆盖完整 source range、逐提交与净 pathset、main preimage／source result blobs、所有已注册 worktree 的 living WIP 路径交集、既有 review／verification 身份、唯一允许的 `merge --squash` 执行门、最小 main-side tests及 reviewed-source archive target。本轮没有执行 merge、fast-forward、regular merge、cherry-pick、commit、archive、ref 更新、部署或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入 squash。0 major 明确可执行。** Final source 在本轮 exact-tip 复核中为 `0 blocker／0 major`；限定范围验证为 `PASS`。完整两提交 range线性且无 merge commit，净四路径的 main preimage与source result blobs闭合，所有 current living WIP与候选四路径无代码路径重叠。执行时只允许在 exact main preimage上运行一次 `git merge --squash 5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`，随后通过 staged identity、main-side最小门并形成一个新的单一 non-merge main commit。
- **blocker 数**：0。
- **major 数**：0。
- **archive target**：`5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`。后续采用何种 archive ref名称，都必须精确指向这个 reviewed-source commit；不得指向未来 main squash commit，也不得退回中间 tip `63db675b59a659d8c1f06ee9bc0c7bf945bac161`。
- **范围边界**：本 verdict只放行 opt-in weighted resident-byte primitive、request-local account、DeliverySession semantic／rendered lease lifecycle、ACK bytes retention删除及其测试。它不表示 production配置／注入、route admission、parser draft charge-before-read、全部 resident owner、queue item cap、metrics／History quota facts、完整 `REL-06`、完整 bridge、部署或 cutover 已通过。

## 双视角覆盖证据

### 机械核对视角

1. 每个采信的 shell结果都在同一次调用中验证物理 cwd、Git top-level、branch与完整 HEAD。Main始终为 `main@080105b54614e1320a5c193d7206dcaa584c9b41`；source branch与worktree始终为 `feat/resident-byte-budget@5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`，source index／worktree为空。
2. `git merge-base`返回 exact main；`git rev-list --count`与逐提交 parent log交叉确认 source range为两笔线性 non-merge commits，`git rev-list --count --merges`为零。`git diff --name-status`与逐提交 pathset对账得到净四路径；range stable patch-id为 `6a5d8012df7886fedcb5340c3ff1c91808e28d1d`，`git diff --check`无输出。
3. Main preimage先用 `git cat-file -e`判存在性，再以 `git rev-parse <commit>:<path>`取 blob；新增 `src/app/delivery/reservation.py`在main为 `ABSENT`，避免把未解析表达式回显误当 blob。Source result blobs均直接来自 `5b744ce` commit tree。
4. Main index为空，且不存在 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。NUL-safe porcelain扫描全部已注册 worktree；current dirty worktree只有main与 systemd rebuild载体，二者所有 tracked／untracked living WIP与候选四路径交集均为空。这个结论只证明当前 path-level无重叠，执行时仍须重验，且不授权 stash、restore、checkout或清理任何 WIP。
5. 只读 `git merge-tree`在 exact main／source对象上没有产生冲突 marker。它证明当前文本三方合成无已知冲突，但不替代 squash后的 cached pathset／blob逐项核验。
6. 既有首轮 review绑定中间 source `63db675…`并发现四项 major；final source已在 `5b744ce`中加入 request aggregate／batch atomic／容量恢复、只读 lease、closed write rejection、ACK／close串行化与 cancellation-resilient cleanup测试。`/tmp/260808-reservation-rereview.txt`给修复中间态 `0 blocker／0 major`，但其受审实现使用 `_cleanup_leases`，而最终 commit进一步改为 shielded `_cleanup_task`，故本报告没有把旧 verdict伪装成 final byte-exact证书，而是重新读取 `5b744ce`最终代码与测试并现场运行 exact-tip门。
7. Exact `5b744ce`上显式将 `PYTHONPATH`绑定 source `src`，并断言三个 delivery模块都从 source worktree加载。`tests/smoke/test_anthropic_block_delivery.py`与`tests/smoke/test_anthropic_responses_stream_route.py`实际执行为 `45 passed`；独立 `--collect-only` node ID计数同为45。候选四路径 Ruff通过，Pyright为 `0 errors, 0 warnings, 0 informations`；运行前后 source porcelain hash均为空状态 SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
8. Exact-tip代码检查确认：`reserve_many()`在同一 condition临界区更新 request与global计数，等待发生在任何 charge前，见 `src/app/delivery/reservation.py:113-162`；release在同一临界区删除 active owner、同时扣减两级计数并原子标记 lease released，见 `src/app/delivery/reservation.py:165-176`；lease facts只读，见 `src/app/delivery/reservation.py:179-203`。DeliverySession所有 ACK与close共享 operation lock，见 `src/app/delivery/anthropic_sse.py:838-933`；首次 close先置 closed并清除 payload-bearing引用，再创建 shielded cleanup task，取消某个 waiter不会取消共享 cleanup，见 `src/app/delivery/anthropic_sse.py:915-946`；rendered lease从成功 reserve起登记到成功 release，见 `src/app/delivery/anthropic_sse.py:966-984`。Production stream state已无 `batches`累计，ACK只推进 session，见 `src/app/delivery/responses_anthropic_stream.py:64-72,330-341`。
9. 永久测试不仅覆盖正确路径，也守住首评 false-green缺口：request aggregate立即失败 `tests/smoke/test_anthropic_block_delivery.py:836`、`reserve_many()`全有或全无 `:859`、容量恢复继续 `:879`、lease不可篡改 `:914`、closed写入口在 reserve／sink前失败 `:958`、pending ACK／close两种先后顺序只释放一次 `:1064`、close waiter取消后后台cleanup继续 `:1113`。现有 accepted／uncertain与stream route smoke同时防止把正确状态误拒绝。

### 第一人称执行视角

1. **作为 squash执行者**：我先在main同一 shell链验证物理root、branch、`HEAD == refs/heads/main == 080105b…`，再验证 source ref与source worktree都精确为 `5b744ce…`且clean；随后检查main index为空、无进行中的Git操作，并重新以NUL-safe方式求所有worktree living WIP与四路径交集。任一 identity、preimage、source clean或WIP交集漂移都立即停止，不通过stash／restore／覆盖来制造绿灯。
2. **作为载荷形成者**：所有执行前门全绿后，我只运行一次 `git merge --squash 5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`。我不会执行regular merge、`git merge`默认形态、`--ff`、`--ff-only`、`--no-ff`、任何隐式fast-forward、单笔／多笔／range cherry-pick，也不会逐笔回放 `63db675…`与`5b744ce…`。
3. **作为 staged-result核验者**：`merge --squash`命令成功不等于门通过。我会在commit前验证cached pathset精确等于本文四路径、cached stable patch-id等于 `6a5d8012…`、四个cached result blob逐项等于本文oracle、`git diff --cached --check`无输出，且cached集合不含本报告、其他 `docs/tmp/**`、living docs、verification资产或并行WIP。任一不符都停止，不提交。
4. **作为 main-side验证者**：形成新的单一 non-merge commit后，我会验证其唯一parent为执行前 exact `080105b…`，commit pathset与result blobs匹配本文oracle；然后在新main commit上重新运行两个最小 smoke文件、独立 collect、候选四路径 Ruff与Pyright。不能沿用source-side退出码。任一失败都不归档、不清理source branch／worktree，也不宣称完整产品 `PASS`。
5. **作为归档执行者**：只有main-side门全绿后，reviewed-source archive才允许精确指向 `5b744ce…`。Archive动作未由本报告执行；main squash commit只承载主线结果，不能替代reviewed-source provenance。

## 完整两提交 range

Base：`080105b54614e1320a5c193d7206dcaa584c9b41`。Final source tip：`5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`。

| 顺序 | Commit | Parent | Subject | Per-commit pathset |
|---|---|---|---|---|
| 1 | `63db675b59a659d8c1f06ee9bc0c7bf945bac161` | `080105b54614e1320a5c193d7206dcaa584c9b41` | `feat: add resident byte reservations` | `src/app/delivery/anthropic_sse.py`；`src/app/delivery/reservation.py`；`src/app/delivery/responses_anthropic_stream.py`；`tests/smoke/test_anthropic_block_delivery.py` |
| 2 | `5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad` | `63db675b59a659d8c1f06ee9bc0c7bf945bac161` | `fix: harden resident lease cleanup` | `src/app/delivery/anthropic_sse.py`；`src/app/delivery/reservation.py`；`tests/smoke/test_anthropic_block_delivery.py` |

## 净 pathset、main preimage与source result blobs

| Status | Path | `main@080105b` preimage blob | `source@5b744ce` result blob |
|---|---|---|---|
| M | `src/app/delivery/anthropic_sse.py` | `9d1062a212d0b60b51eade0b8ff9bd282133675f` | `f2e3103e6d5c9eb5327bc6ab25f0de423d27c188` |
| A | `src/app/delivery/reservation.py` | **ABSENT** | `6629cb6382d9332f50de528c1f7035d11e4aef11` |
| M | `src/app/delivery/responses_anthropic_stream.py` | `00bf169377d39a0679075b4df66a754efffe4c62` | `795ac4d4b9c779f7b6889f391c449b8618f5d238` |
| M | `tests/smoke/test_anthropic_block_delivery.py` | `e73d9b4f3877cc58620bdd943a6976dbd6403869` | `b2fd6a914639e6aa81e27d3f8116b472460193c4` |

## Current living WIP与代码重叠

Main包含 tracked living docs及大量 untracked `docs/tmp/**`／verification资产；`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`另有 untracked `docs/tmp/`内容。NUL-safe扫描全部已注册worktree后，上述所有 current living WIP与 resident source净四路径的交集为**空集合**。

该结论不表示main clean，也不授权处理这些WIP。执行时必须重算交集；只要四路径中任一项成为tracked或untracked dirty path，就停止并交回其owner，不得自行stash、restore、checkout、吸收或覆盖。

## 唯一允许的 merge --squash 门

### Gate A：main与source身份

- Main物理root与Git top-level均为 `/home/xp/src/ghc-api-proxy-py`；branch为 `main`；`HEAD == refs/heads/main == 080105b54614e1320a5c193d7206dcaa584c9b41`。
- Source物理root与Git top-level均为 `/home/xp/src/ghc-api-proxy-py-reservation`；branch为 `feat/resident-byte-budget`；`HEAD == refs/heads/feat/resident-byte-budget == 5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`；source index／worktree为空。
- Merge-base、两提交 parent链、零 merge commit、净四路径与 stable patch-id仍匹配本文oracle。

### Gate B：main preimage、Git状态与living WIP

- Main index为空；不存在 `MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`。
- 四路径main preimage逐项等于本文表格，其中 `src/app/delivery/reservation.py`仍为 `ABSENT`。
- 重新以NUL-safe porcelain枚举所有registered worktree的tracked／untracked dirty paths，与候选四路径求交；交集必须为空。
- 任一门失败即停止，不用stash、restore、checkout、force或覆盖并行WIP来改变结论。

### Gate C：唯一载荷形成动作

只允许一次：`git merge --squash 5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`。

明确禁止：

- regular merge或任何产生merge commit的形状；
- fast-forward、`--ff`、`--ff-only`、`--no-ff`或隐式FF；
- cherry-pick单笔、多笔或range；
- 逐笔回放source的两笔commit；
- 把本报告、living docs、其他 `docs/tmp/**`、verification资产或并行WIP夹带进squash载荷。

### Gate D：commit前 staged-result

- Cached pathset精确等于四路径：`src/app/delivery/anthropic_sse.py`、`src/app/delivery/reservation.py`、`src/app/delivery/responses_anthropic_stream.py`、`tests/smoke/test_anthropic_block_delivery.py`。
- Cached stable patch-id精确等于 `6a5d8012df7886fedcb5340c3ff1c91808e28d1d`。
- 四个cached result blob精确等于本文 `source@5b744ce` result blob。
- `git diff --cached --check`无输出；cached集合不含任何第五路径。
- 只有全部门全绿才可形成一个新的单一 non-merge main commit；commit message遵守项目 Conventional Commits约定。本报告不预填未来main commit SHA。

### Gate E：最小 main-side tests与archive

在新的main squash commit上运行并要求全部退出零：

1. `tests/smoke/test_anthropic_block_delivery.py`与`tests/smoke/test_anthropic_responses_stream_route.py`；
2. 同一selector集合的独立 `--collect-only` node ID清点；
3. Ruff检查本文四路径；
4. Pyright检查本文四路径并绑定项目虚拟环境解释器。

随后验证新commit只有一个parent且parent为执行前exact `080105b…`，commit pathset与四个result blob均匹配本文oracle，并进行一次main merged-state只读复核。全部通过后才允许创建 reviewed-source archive，target固定为 `5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`。任一门失败即停止，不归档、不清理source branch／worktree、不部署、不cutover。

## 事实性发现

未发现blocker或major。Exact final source的两提交range、净四路径、main preimage、result blobs、living WIP零代码路径重叠与最小测试门均闭合；最终 cleanup采用单一 shielded task，使并发／取消的多个 `aclose()` waiter共享同一清理动作，未重新引入旧 rereview已经关闭的提前release、double release或close后新lease问题。

## 主观建议

无。用户已经裁定只使用 `merge --squash`；本报告不提供FF、regular merge或cherry-pick替代路线，也不以source线性可回放为由推翻该决定。

## 结构怪味扫描边界

- `src/app/delivery/reservation.py:113-203`：未发现重复的计账真相源；request／global mutation与released转换集中在account和同一condition临界区，lease不再自持可篡改account能力。处置：本轮无需修改。
- `src/app/delivery/anthropic_sse.py:838-984`：未发现ACK、close与rendered lease cleanup双 owner；operation lock与共享cleanup task统一串行化状态，source最终测试覆盖两个先后顺序及waiter取消。处置：本轮无需修改。
- `src/app/delivery/responses_anthropic_stream.py:64-72,330-341`：生产state不再重复累计已ACK bytes，保留的 `_BufferedSink._pending`只承载尚未ACK的真实边界。处置：本轮无需修改。
- 扫描范围外的production配置、route注入、parser draft、全部owner与metrics是已声明后继边界，不是本切片的结构遗漏；不得从本次squash升级为完整quota完成态。

## 报告评审状态

本会话是叶子reviewer，不能派生另一名reviewer。本报告已完成事实证伪、双视角执行模拟与exact-tip最小门；按wrap-up产物规则，主会话在对外采用本报告前仍须独立复核本文current-state断言、数字口径与执行门。该复核义务不改变本轮 `0 blocker／0 major／PASS` 结论，但不得静默省略。

## 最终结论

**`feat/resident-byte-budget@5b744ce81d0b3c8a3684aab12a376aa7b3bd5cad`相对exact `main@080105b54614e1320a5c193d7206dcaa584c9b41`为 `0 blocker／0 major`，限定验证为 `PASS`，0 major明确可执行。** 唯一允许的集成形状是在执行时重验A／B门后运行单一 `git merge --squash 5b744ce…`，再通过D／E门形成新的non-merge main commit。**禁止fast-forward、regular merge与cherry-pick。** Reviewed-source archive target固定为 `5b744ce…`；本报告没有执行merge、commit、archive、清理、部署或cutover。
