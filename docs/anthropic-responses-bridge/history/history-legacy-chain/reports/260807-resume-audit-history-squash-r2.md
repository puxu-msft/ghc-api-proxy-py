# History final candidate squash 收口审计 R2

- **评审范围**：只读审计主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 `/home/xp/src/ghc-api-proxy-py-history-facts` 的 `fix/responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`。覆盖完整四提交 range、逐提交与净 pathset、main preimage／candidate result blobs、所有已注册 worktree 的 living WIP 交集、final review／verification 内容身份，以及唯一允许的 `merge --squash` 执行门与 reviewed-source archive target。本轮未执行 merge、fast-forward、regular merge、cherry-pick、commit、archive、ref 更新、测试重跑、部署或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入 squash。** Candidate 的最终受审内容取得 `0 blocker／0 major／0 minor`；exact-HEAD verification 判为 `PASS`。四提交 range 线性且无 merge commit，九路径 main preimage与result blobs闭合，candidate与当前所有living WIP无路径重叠。只允许按本文执行时门在 exact `main@b91e58a…` 上形成单一 `merge --squash` 载荷；禁止 fast-forward、regular merge与cherry-pick。
- **blocker 数**：0。
- **major 数**：0。
- **archive target**：`b1df8f910c590033e83d5cafcd5e514f12bab937`。它是最终 reviewed source tip；不得改指向未来 main squash commit，也不得退回旧 tip `864cfa30e291768cbc7b080fce80d9be4cbf2d83`。
- **范围边界**：本 verdict只放行 `b91e58a… → b1df8f9…` 的 History facts／response lifecycle 增量。它不表示完整 Anthropic Responses bridge、streaming、真实 upstream、部署或 cutover 已通过。

## 双视角覆盖证据

### 机械核对视角

1. 每个采信的 shell 结果都在同一调用中打印并验证物理 cwd、Git top-level、branch或完整HEAD。发生并发终端串线、缺少本轮 marker或被`Ctrl-C`打断的调用全部作废并重跑，未进入结论。
2. `git merge-base`返回exact `b91e58a…`；`git rev-list --count`与逐行parent log交叉确认range恰为四笔线性non-merge commits，`git rev-list --count --merges`为零。
3. `git diff --name-status b91e58a…..b1df8f9…`与九路径显式枚举交叉确认净pathset；range stable patch-id为`3de8374d866af3e692a9f6ebfd01e8221b8eb2d8`，`git diff --check`无输出。
4. Main preimage使用`git cat-file -e`先判存在性，再以`git rev-parse <commit>:<path>`取blob；两个新增路径在main上均为`ABSENT`，避免了`rev-parse`对未解析表达式回显造成的假绿。Candidate result blobs逐路径来自commit tree对象。
5. Main index为空，未发现进行中的merge、rebase、cherry-pick或revert marker。Main本身并不clean，但其tracked／untrackedliving WIP与candidate九路径交集为空。
6. 使用NUL-safe porcelain解析扫描全部已注册worktree。除main外，`integrate/260807-systemd-rebuild-resume`存在`docs/tmp/`未跟踪内容；其余候选外worktree没有需报告的dirty path。所有living WIP与candidate pathset的交集为空。
7. Final review日志`hf-lifecycle-review-e31b.log`绑定旧HEAD`864cfa3…`加未提交修复diff，最终 verdict为`0 blocker／0 major／0 minor`。该受审diff的`DIFF_AFTER` SHA-256为`e98bd35b4eee0907824c3c61a04ca2098394f840c064a6376bf3c63fe0e9b8ed`；第四提交`864cfa3…..b1df8f9…`对同两路径的文本与binary diff SHA-256均精确等于`e98bd35…`，故受审bytes与final commit bytes相同。第四提交stable patch-id为`8d51dd6720986b79b1e3ad996c1126fd81f219d9`。
8. Final verification在exact `HEAD=b1df8f9…`上运行：post-commit定向pytest退出码为零，日志摘要为`25 passed in 3.74s`；该数量只作日志摘要，未以第二原理交叉计数。独立三场景spy退出码为零，并机械断言：throwing success strategy产生failed终态、一次ERROR／FINALIZE／History finalize、零RESPONSE与零calibration；合法success产生completed终态、一次RESPONSE／FINALIZE／History finalize、一次calibration并保留History response／usage／request与response provenance；invalid final body产生failed终态、一次ERROR／FINALIZE／History finalize、零RESPONSE与零calibration。Verifier前后candidate porcelain hash均为空状态SHA-256`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，因此本审计将final verification裁为`PASS`。当前没有另行落成一份绑定`b1df8f9…`的Markdown verify verdict，不能把旧`864cfa3…`的verify文件冒充final证据。
9. 预提交同bytes回归日志另记录定向与全仓pytest、Ruff、Pyright均退出零；全仓pytest摘要为`505 passed`，该数量同样未以第二原理交叉计数，只作为相同bytes的辅助证据，不替代exact-HEAD spy与post-commit定向结果。

### 第一人称执行视角

1. **作为squash执行者**：我先在main同一shell调用中验证物理root、branch与exactHEAD，确认index为空、无进行中的Git操作，并重新求candidate pathset与当前tracked／untracked WIP交集。任一identity漂移、dirty overlap或目标preimage变化都立即停止，不stash、不restore、不覆盖并行WIP。
2. **作为载荷形成者**：所有门全绿后，我只执行一次`git merge --squash b1df8f910c590033e83d5cafcd5e514f12bab937`。我不会执行regular merge、`--ff`／`--ff-only`、任何隐式fast-forward或cherry-pick；也不会逐笔回放四个source commits。
3. **作为staged-result核验者**：merge完成不等于门通过。我会在commit前验证cached pathset精确等于九路径、cached stable patch-id等于`3de8374…`、逐路径staged result blob等于本文oracle、`git diff --cached --check`无输出，且cached集合不含main living docs、本报告、其他`docs/tmp/**`、`verification/**`或并行WIP。任一不符都停止，不提交。
4. **作为main-side验证者**：单一non-merge squash commit形成后，重新验证parent恰为执行前`b91e58a…`、commit只有九路径、result blobs与candidate一致，并在main-side运行final review要求的History／observer／calibration定向测试、全仓pytest、Ruff与Pyright。任一失败都不归档、不清理feature branch／worktree，也不宣称完整产品`PASS`。
5. **作为归档执行者**：只有main-side门全绿后，reviewed-source archive才允许指向exact`b1df8f9…`。Archive动作本身未由本报告执行；不得把main squash commit当reviewed-source target。

## 完整四提交 range

Base：`b91e58a29324b11840002efc53ed6f869b800c39`。Final tip：`b1df8f910c590033e83d5cafcd5e514f12bab937`。

| 顺序 | Commit | Parent | Subject | Per-commit pathset |
|---|---|---|---|---|
| 1 | `e5db34bcf7be017e602fb1ee3f666b3ad2e96a3f` | `b91e58a29324b11840002efc53ed6f869b800c39` | `fix: persist Responses history facts` | `docs/2604-rewrite/BACKLOG.md`；`src/app/anthropic/client.py`；`src/app/history/consumer.py`；`src/app/pipeline/context.py`；`src/app/pipeline/executor.py`；`tests/component/test_history_store.py`；`tests/component/test_pipeline_executor.py` |
| 2 | `2e3a6d2022244a6bca0e2db05e079bc27d94a585` | `e5db34bcf7be017e602fb1ee3f666b3ad2e96a3f` | `fix: harden response history facts` | `src/app/anthropic/client.py`；`src/app/anthropic/response_validation.py`；`src/app/history/consumer.py`；`src/app/pipeline/context.py`；`src/app/pipeline/executor.py`；`tests/component/test_pipeline_executor.py`；`tests/unit/test_anthropic_response_validation.py` |
| 3 | `864cfa30e291768cbc7b080fce80d9be4cbf2d83` | `2e3a6d2022244a6bca0e2db05e079bc27d94a585` | `fix: publish response observers after final facts` | `src/app/pipeline/executor.py`；`tests/component/test_pipeline_executor.py`；`tests/unit/test_anthropic_response_validation.py` |
| 4 | `b1df8f910c590033e83d5cafcd5e514f12bab937` | `864cfa30e291768cbc7b080fce80d9be4cbf2d83` | `fix: order response success callbacks` | `src/app/pipeline/executor.py`；`tests/component/test_pipeline_executor.py` |

## 净 pathset、main preimage与result blobs

| Status | Path | `main@b91e58a` preimage blob | `b1df8f9` result blob |
|---|---|---|---|
| M | `docs/2604-rewrite/BACKLOG.md` | `d4d9c07476fbfafa6725b06da6d90c1ca329b712` | `c0960b82e5787b611984dfd317578b755a331d97` |
| M | `src/app/anthropic/client.py` | `2c05425a2b0a90b5a03488a7919dbb5d0470c1ce` | `a703c73a4be14ffcef62afd828840b9a3e86d398` |
| A | `src/app/anthropic/response_validation.py` | **ABSENT** | `b7c02257178c0d4248a6016dc2d3d5c747cc352d` |
| M | `src/app/history/consumer.py` | `c0a3ec556f0eb333e5e45760fd6c8c138598fffa` | `f2d7338ff8eadb528086246907334bb1ceb9194c` |
| M | `src/app/pipeline/context.py` | `9c8074fbb38c9a663c229e0c7666af86a8f3b218` | `3a19290f200d2c53c0e96ad8860b5e7bf8a75053` |
| M | `src/app/pipeline/executor.py` | `75ace9cbbfadec87e35501b1cea4b54023a81fa5` | `16aea7e00cd4ace5699d3f8f1693c1d651332ba7` |
| M | `tests/component/test_history_store.py` | `792b7487af3b103b447817d2053cfc315704a40a` | `fdcd8552df6ff223682a6c7d53a5fa9fdc9ca93e` |
| M | `tests/component/test_pipeline_executor.py` | `8b5f7dcf4deca9abc08471ae14378ff83e4e7856` | `5aa5a12f3add35c39a45e68e80349f5b7143d6c8` |
| A | `tests/unit/test_anthropic_response_validation.py` | **ABSENT** | `dc0f755e44d1bbb706dccc4252530d3f5e9bb0ff` |

## Current living WIP与交集

Main index为空；current dirty paths如下，均不在candidate九路径中：

- `docs/agents/anthropic-responses-bridge/implementation.md`
- `docs/agents/service-cutover/readiness.md`
- `docs/agents/systemd-runtime/plan.md`
- `docs/tmp/`
- `verification/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md`
- `verification/PHASE3_ACCEPTANCE_REPORT.md`
- `verification/phase3_acceptance.py`

另一个已注册worktree`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`存在`docs/tmp/`未跟踪内容。NUL-safe全worktree扫描的candidate交集为空。空交集只证明当前path-level不重叠；执行时必须重验，且不授权stash、restore、清理或覆盖上述WIP。

## 唯一允许的 merge --squash 门

### Gate A：source与main身份

执行者必须在同一shell链中验证：

- main物理root与Git top-level均为`/home/xp/src/ghc-api-proxy-py`；branch为`main`；HEAD仍为`b91e58a29324b11840002efc53ed6f869b800c39`；
- source worktree物理root与Git top-level均为`/home/xp/src/ghc-api-proxy-py-history-facts`；branch为`fix/responses-history-facts`；HEAD仍为`b1df8f910c590033e83d5cafcd5e514f12bab937`；source worktree与index均为空；
- merge-base仍为`b91e58a…`，range仍为本文四笔线性non-merge commits，净pathset与stable patch-id仍等于本文oracle。

### Gate B：main preimage、Git状态与living WIP

- Main index为空；不存在`MERGE_HEAD`、`CHERRY_PICK_HEAD`、`REVERT_HEAD`、`rebase-merge`或`rebase-apply`；
- 九个main preimage逐项等于本文表格，两个新增路径仍为`ABSENT`；
- 重新以NUL-safe porcelain枚举所有已注册worktree的tracked／untracked dirty paths，并与candidate九路径求交；交集必须为空；
- 任一门失败即停止。不得以stash、restore、checkout、force、冲突选择或覆盖并行WIP来制造绿灯。

### Gate C：唯一载荷形成动作

只允许一次：`git merge --squash b1df8f910c590033e83d5cafcd5e514f12bab937`。

明确禁止：

- regular merge；
- fast-forward、`--ff`或`--ff-only`；
- cherry-pick单笔、多笔或range；
- 把四笔source commits逐笔带入main ancestry；
- 把任意未提交WIP夹带进squash载荷。

### Gate D：commit前 staged-result

- Cached pathset精确等于本文九路径；
- Cached stable patch-id精确等于`3de8374d866af3e692a9f6ebfd01e8221b8eb2d8`；
- 每个cached result blob精确等于本文`b1df8f9` result blob；
- `git diff --cached --check`无输出；
- Cached集合不含main living docs、本报告、其他`docs/tmp/**`、`verification/**`或任何并行WIP；
- 只有上述门全绿才可形成一个新的non-merge main commit。Commit message按项目Conventional Commits约定；本报告不预填未来main commit identity。

### Gate E：main-side验证与archive

- 新commit parent必须是执行前exact `b91e58a…`，且只有一个parent；commit pathset与result blobs必须匹配本文oracle；
- 在新main commit上运行final review要求的History／observer／calibration定向测试、全仓pytest、Ruff与Pyright；不得沿用candidate-side退出码；
- 重新执行merged-state只读审阅，检查main living docs与代码事实没有因squash产生新漂移；
- 全部门通过后才允许建立reviewed-source archive，target固定为`b1df8f910c590033e83d5cafcd5e514f12bab937`；
- 任一门失败即停止，不归档、不清理feature branch／worktree、不部署、不cutover。

## 事实性发现

未发现blocker或major。Final review的受审diff与第四提交内容身份相同，verdict为`0 blocker／0 major／0 minor`；exact-tip verifier的全部冻结断言与退出码支持`PASS`。Range、pathset、preimage／result blobs与living WIP零交集均闭合。

## 主观建议

无。本轮只裁决squash门与archive target，不扩张产品范围。

## 结构怪味扫描边界

本轮不做候选代码内容复评，结构扫描只覆盖集成形状：未发现merge commit、意外路径扩张、main preimage漂移、source／main身份混用、reviewed-source archive指向main结果或living WIP夹带。唯一需保留的长期注意点是final review先审dirty bytes、随后才提交；本报告已用diff SHA-256与commit delta双向绑定关闭该身份接缝，不把旧HEAD标签冒充final commit标签。

## 报告评审状态

本会话是叶子reviewer，不能派生另一名reviewer。本报告已完成事实证伪与双视角执行模拟；按wrap-up产物规则，主会话仍须对本文current-state断言与执行门做独立复核。该复核义务不改变候选代码现有`0 major／PASS`证据，但在主会话对外采用本报告前不得静默省略。

## 最终结论

**`fix/responses-history-facts@b1df8f910c590033e83d5cafcd5e514f12bab937`相对`main@b91e58a29324b11840002efc53ed6f869b800c39`为`0 blocker／0 major／0 minor`，final verification为`PASS`，明确可进入squash。** 唯一允许的集成形状是exact main上的单一`git merge --squash b1df8f9…`，并在commit前后执行本文A→E门。**禁止fast-forward、regular merge与cherry-pick。** Reviewed-source archive target固定为`b1df8f910c590033e83d5cafcd5e514f12bab937`；本报告没有执行merge、commit、archive、清理、部署或cutover。
