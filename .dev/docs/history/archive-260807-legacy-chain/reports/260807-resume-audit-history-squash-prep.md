# History facts 最终修复后 squash 收口准备审计

- **评审范围**：只读审计主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 `/home/xp/src/ghc-api-proxy-py-history-facts` 的 `fix/responses-history-facts` current 状态。冻结 committed range、逐提交与净 pathset、main preimage、current 未提交 WIP、main living WIP 交集、现有 review／verification 身份，以及最终修复后的条件式 squash 门。本轮不评审代码内容、不判断未提交修复是否正确、不运行产品测试、不修改 Git index、HEAD、refs、branches、commits 或其他文件；唯一仓库写入为本报告。
- **总体 verdict**：**修复 major 后可进入；当前明确不可 squash。** 分支 ref 与 `HEAD` 仍为 `864cfa30e291768cbc7b080fce80d9be4cbf2d83`，最新 exact-HEAD code review 仍是 `0 blocker／1 major／0 minor`，并明确判定不可 squash。分支当前另有两路径未提交 WIP，不能把该 WIP 当作已评审修复。下文已冻结最终修复落盘、exact-tip 复评归零、主树 preimage／WIP 重验、squash staged 结果核对及 main-side gate；满足全部条件后可快速收口。
- **blocker 数**：0。
- **major 数**：1 个现存 squash 阶段门 major，来源为 `docs/tmp/260807-resume-review-history-facts-r3.md` 的 exact-HEAD code review。本审计未新增内容评审 finding。
- **测试边界**：未运行测试。`docs/tmp/260807-resume-verify-history-facts.md` 对同一 `864cfa3…` 给出 scoped `PASS`，但它明确未覆盖完整矩阵；R3 随后在 post-calibration late-failure 接缝发现 1 major，因此 scoped `PASS` 不能覆盖或撤销最新 code review verdict。

## 双视角覆盖证据

### 机械核对视角

1. 每份承载结论的 shell 结果均在同一调用中验证物理 cwd、Git top-level、branch 与完整 HEAD；一次缺少本轮 nonce 的并发终端串线输出已整轮作废。后续 current-state 结果先写入唯一 `/tmp/hf-squash-prep-*-31ef7ca6.log`，再按绝对路径复读。
2. 主树精确为 `main@b91e58a29324b11840002efc53ed6f869b800c39`，index 为空。Tracked living WIP 恰为三路径；下文逐路径给出 current SHA-256。主树另有既存 untracked `docs/tmp/**` 与 `verification/**`，所以不能声称 main worktree clean。
3. History 分支 ref、worktree `HEAD` 均为 `864cfa30e291768cbc7b080fce80d9be4cbf2d83`，merge-base 精确为 `b91e58a…`。`git rev-list --count` 与逐行 log 交叉确认 range 中有 3 个线性 non-merge commits；merge commit 数为 0。
4. Committed net pathset 由 `git diff --name-status b91e58a… 864cfa3…` 与下文 9 行枚举交叉确认。Stable patch-id 为 `c086bfb7fd150afe17670840ada4478409283d55`，`git diff --check` 无输出。
5. Current branch 未提交 WIP 精确修改 `src/app/pipeline/executor.py` 与 `tests/component/test_pipeline_executor.py`。Porcelain v2、`git diff HEAD --name-status` 与逐文件 blob 身份一致；index 与 untracked 路径为空。该 WIP 使 base→worktree effective stable patch-id 变为 `56e00b94b8181e173e1e692051c91c69bf118a85`，但该值只是 current WIP 身份，不是已评审 squash oracle。
6. Candidate 9-path effective pathset 与 main 三条 tracked living WIP 的交集为空；与 main 既存 untracked 路径的交集也为空。排除 History worktree自身后，其他已注册 worktree 的未提交路径与 candidate effective pathset 交集为空。
7. 最新 code review 文件 SHA-256 为 `156ab1c49d288ff865158e31339ad3b4d3fa6bb2cff60cab3d4304a22d70a523`，其 verdict 为 `0 blocker／1 major／0 minor`、不可 squash。Scoped verification 文件 SHA-256 为 `e8a9f7ab6138b7a74424526e148c54ec19100d50db141f43508485dd757bdd6c`，绑定同一 HEAD并为 `PASS`，但范围不足以推翻 R3 finding。

### 第一人称执行视角

1. **现在尝试 squash**：我会立即停止。原因有两个独立门：最新 exact-HEAD review 仍有 1 major；History worktree还存在未提交两路径 WIP。Scoped verification 的 `PASS` 不允许我越过任一门。
2. **修复者提交 current WIP，branch 前进**：我先重新读取 actual tip，要求 `b91e58a…` 仍为 merge-base、range 仍为线性 non-merge、净 pathset 没有意外扩张，并记录新 tip 的完整 range、result blobs 与 stable patch-id。Current WIP blob 只能用于识别“评审的是不是刚才这份修复”，不能提前判定内容正确。
3. **复评者检查最终 tip**：必须取得精确绑定新 tip 的 code review `0 blocker／0 major`，且明确关闭 R3 late-failure major并允许 squash。若 verification 也更新，必须绑定同一 tip；旧 `864cfa3…` 的 review／verification均不得外推到新 commit。
4. **squash 执行者进入 main**：先处理或保护 main 三份 living WIP，重新要求 index为空，并重验 candidate pathset 与 actual main tracked／untracked WIP交集。Actual main可以因独立 checkpoint 前进，但 candidate 9 个目标路径的 preimage必须逐条仍等于本文 oracle；任一路径漂移、冲突、范围扩张或 dirty overlap均停止，不能 restore、stash、force或自行选择覆盖并行工作。
5. **staged 结果核验者**：只在上述门全部通过后形成单一 squash 载荷。Cached pathset必须精确等于最终 reviewed tip 的净 pathset；cached result blobs、stable patch-id与最终复评所绑定 tip一致，`git diff --cached --check`通过，且不夹带 living docs、本报告、其他 `docs/tmp/**`、`verification/**` 或并行 WIP。
6. **main-side 验证者**：新 main commit形成后重跑最终复评要求的 History／observer／calibration定向回归、全仓 pytest、Ruff与Pyright，并重新核对 commit parent、non-merge形状、pathset、result blobs与clean状态。任一门失败即停止，不归档、不清理feature worktree、不宣称完整 bridge `PASS`。

## Current committed range

Base：`b91e58a29324b11840002efc53ed6f869b800c39`。Current tip：`864cfa30e291768cbc7b080fce80d9be4cbf2d83`。

| 顺序 | Commit | Parent | Subject | Per-commit pathset |
|---|---|---|---|---|
| 1 | `e5db34bcf7be017e602fb1ee3f666b3ad2e96a3f` | `b91e58a29324b11840002efc53ed6f869b800c39` | `fix: persist Responses history facts` | `docs/2604-rewrite/BACKLOG.md`；`src/app/anthropic/client.py`；`src/app/history/consumer.py`；`src/app/pipeline/context.py`；`src/app/pipeline/executor.py`；`tests/component/test_history_store.py`；`tests/component/test_pipeline_executor.py` |
| 2 | `2e3a6d2022244a6bca0e2db05e079bc27d94a585` | `e5db34bcf7be017e602fb1ee3f666b3ad2e96a3f` | `fix: harden response history facts` | `src/app/anthropic/client.py`；`src/app/anthropic/response_validation.py`；`src/app/history/consumer.py`；`src/app/pipeline/context.py`；`src/app/pipeline/executor.py`；`tests/component/test_pipeline_executor.py`；`tests/unit/test_anthropic_response_validation.py` |
| 3 | `864cfa30e291768cbc7b080fce80d9be4cbf2d83` | `2e3a6d2022244a6bca0e2db05e079bc27d94a585` | `fix: publish response observers after final facts` | `src/app/pipeline/executor.py`；`tests/component/test_pipeline_executor.py`；`tests/unit/test_anthropic_response_validation.py` |

## Committed net pathset 与 main preimage

| Status | Path | `main@b91e58a` preimage blob | `864cfa3` committed result blob |
|---|---|---|---|
| M | `docs/2604-rewrite/BACKLOG.md` | `d4d9c07476fbfafa6725b06da6d90c1ca329b712` | `c0960b82e5787b611984dfd317578b755a331d97` |
| M | `src/app/anthropic/client.py` | `2c05425a2b0a90b5a03488a7919dbb5d0470c1ce` | `a703c73a4be14ffcef62afd828840b9a3e86d398` |
| A | `src/app/anthropic/response_validation.py` | **ABSENT** | `b7c02257178c0d4248a6016dc2d3d5c747cc352d` |
| M | `src/app/history/consumer.py` | `c0a3ec556f0eb333e5e45760fd6c8c138598fffa` | `f2d7338ff8eadb528086246907334bb1ceb9194c` |
| M | `src/app/pipeline/context.py` | `9c8074fbb38c9a663c229e0c7666af86a8f3b218` | `3a19290f200d2c53c0e96ad8860b5e7bf8a75053` |
| M | `src/app/pipeline/executor.py` | `75ace9cbbfadec87e35501b1cea4b54023a81fa5` | `5bc4431b072d9213af3de27c48b28adb176c4bdc` |
| M | `tests/component/test_history_store.py` | `792b7487af3b103b447817d2053cfc315704a40a` | `fdcd8552df6ff223682a6c7d53a5fa9fdc9ca93e` |
| M | `tests/component/test_pipeline_executor.py` | `8b5f7dcf4deca9abc08471ae14378ff83e4e7856` | `18d727ca04a3024b2d032b4f6254deb41cb06014` |
| A | `tests/unit/test_anthropic_response_validation.py` | **ABSENT** | `dc0f755e44d1bbb706dccc4252530d3f5e9bb0ff` |

## Current branch 未提交 WIP 冻结

以下只记录内容身份，不作内容评审或正确性判断。

| Path | `864cfa3` HEAD blob | Current worktree blob | Current worktree SHA-256 |
|---|---|---|---|
| `src/app/pipeline/executor.py` | `5bc4431b072d9213af3de27c48b28adb176c4bdc` | `23e30b750ecff63d9e2242a83ca6d6822adddb5d` | `74d588ef1cb22a12d12dd128debe72b0b63dc47bc4caac85410bbb04044492a1` |
| `tests/component/test_pipeline_executor.py` | `18d727ca04a3024b2d032b4f6254deb41cb06014` | `5aa5a12f3add35c39a45e68e80349f5b7143d6c8` | `2c9b37e026b9a739b9c98c8bae13e57c9d4601c216a6f167bca5eb0e33ae5f63` |

- WIP binary diff SHA-256：`9971d6e47210b289e93a862c1573c12dfbd344468ca3682516ee169532dfaa3b`。
- WIP stable patch-id：`447005cec9bd1b1da69d02d480acdd8ecd732812`。
- Base→current worktree effective pathset仍为上述 9 路径；effective stable patch-id为 `56e00b94b8181e173e1e692051c91c69bf118a85`。
- 这些身份只允许后续确认新 commit是否消费了本次 WIP；它们不构成 `0 major`、测试通过或可 squash证据。

## Main living WIP 与交集

Main index为空；tracked living WIP如下。

| Path | Current SHA-256 | 与 candidate effective pathset交集 |
|---|---|---|
| `docs/agents/anthropic-responses-bridge/implementation.md` | `5be08662048f4f7f71a0eb104b98a7dec6795989fe290bf002cb004d152d1d8f` | 无 |
| `docs/agents/service-cutover/readiness.md` | `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8` | 无 |
| `docs/agents/systemd-runtime/plan.md` | `3c639fcd73ad1deed9a164ece43eb0f982da7f2ae8259e5903e7a7d9c9a7054f` | 无 |

- Main tracked living WIP × candidate effective pathset：**空集**。
- Main existing untracked paths × candidate effective pathset：**空集**。
- 其他已注册 worktree 未提交路径 × candidate effective pathset：**空集**。该口径排除 History worktree自身；History自身两路径 WIP已在上一节单列。
- 空交集只证明 current path-level 不重叠，不替代最终 tip 的 merged-state review，也不授权覆盖、暂存或清理 main living WIP。

## 最终修复后的冻结收口门

### A. Final-tip identity 门

最终修复提交形成后，重新记录并同时满足：

- `fix/responses-history-facts` ref与worktree `HEAD` 指向同一新 tip，worktree与index均为空；
- merge-base仍精确为 `b91e58a29324b11840002efc53ed6f869b800c39`，range保持线性 non-merge；
- 完整 committed net pathset仍精确为本文 9 路径。若修复合理地新增路径，必须先更新审计、preimage、review范围与squash oracle，不能沿用本文快速门；
- 新 tip相对`864cfa3…` 的提交确实消费 current WIP身份；若WIP继续漂移，则重新冻结；
- 对新 tip重新计算result blobs、stable patch-id与`diff --check`，不沿用`864cfa3…` committed值或current dirty-worktree值。

### B. Exact-tip review／verification 门

- 新 code review必须精确绑定final tip，给出`0 blocker／0 major`并明确允许squash；
- 复评必须明确处置R3的post-calibration late-failure major，并检查History finalization晚失败窗口没有只被平移；本条是对现有finding的关闭要求，不是本审计的新内容判断；
- 若生成新verification，必须绑定同一final tip。旧`864cfa3…` scoped`PASS`只保留历史证据，不作为final tip放行；
- Review与verification verdict冲突时停止并仲裁，不能以“测试PASS”自动覆盖code review major。

### C. Main execution-time preimage／WIP 门

- 在actual main重新验证物理root、branch、完整HEAD、空index，以及没有进行中的merge、rebase、cherry-pick或revert；
- 重新枚举tracked与untracked WIP，并与final reviewed tip净pathset求交。非空即停止；
- Actual main的9个目标preimage必须逐条等于本文表格。两个新增路径必须仍为ABSENT；其余7个blob必须精确相等；
- 若main因living checkpoint或其他独立提交前进但上述preimage仍相等，可继续；任一目标preimage漂移则本文squash准备失效，先重建candidate或重新审计，不做冲突选择。

### D. Squash staged-result 门

- 只消费final reviewed tip的完整净补丁，形成一个新的non-merge main commit；不得把三笔source commit逐笔带入main ancestry，也不得把未提交WIP直接作为载荷；
- Commit前cached pathset、result blobs与stable patch-id必须精确等于final reviewed tip的新oracle；
- `git diff --cached --check`通过，cached集合不含三份living docs、本报告、其他`docs/tmp/**`、`verification/**`或任意并行WIP；
- 出现冲突、第三方路径、空diff或身份漂移即停止，不提交。

### E. Main-side gate 与归档边界

- 在新main squash commit上运行final review要求的定向History／observer／calibration回归、全仓pytest、Ruff与Pyright；不得沿用candidate-side退出码；
- 重新核对新commit只有final reviewed pathset、parent为execution-time actual main、不是merge commit、result blobs与final tip相等，worktree与index回到clean；
- 全部门通过后才能创建reviewed-source archive ref，target必须是final reviewed source tip，不是`864cfa3…`旧tip，也不是新main squash commit；
- Archive、feature branch／worktree清理、部署与cutover均不是本报告已执行或授权的动作。

## 事实性发现

[major] `docs/tmp/260807-resume-review-history-facts-r3.md:3-6,29-38,48` — Current exact-HEAD code review仍为`0 blocker／1 major／0 minor`并明确不可squash — Scoped verification虽为`PASS`，但未覆盖R3随后实测的post-calibration late-failure；同时current修复仍只存在于两路径未提交WIP，尚无新tip或exact-tip复评 — 先把修复形成干净final tip，再按A／B门取得精确绑定的`0 blocker／0 major`可squash verdict；随后才能进入main preimage与staged-result门。

## 主观建议

无。本轮只冻结状态与后续门，不评价修复方案或提供替代内容设计。

## 结构怪味扫描边界

用户明确要求“不做内容评审”，因此本轮没有扫描代码结构怪味，也不把未提交diff内容读入审计。状态层唯一风险已作为上述major阶段门记录：已评审tip与living修复WIP不是同一内容身份，不能混用证据。

## 报告评审状态

本会话处于叶子reviewer模式，不能派生独立reviewer。本报告包含current状态、执行门与下一动作，主会话仍须安排独立复核；该义务已转交，不能把本报告自述冒充二次评审。

## 最终结论

**Current `fix/responses-history-facts@864cfa30e291768cbc7b080fce80d9be4cbf2d83` 仍为`0 blocker／1 major／0 minor`，明确不可squash。** 分支当前有`src/app/pipeline/executor.py`与`tests/component/test_pipeline_executor.py`两路径未提交WIP；本报告只冻结其身份，不判断其是否关闭major。Committed range为`b91e58a… → e5db34b… → 2e3a6d2… → 864cfa3…`，净pathset为本文9路径；current main三份tracked living WIP与candidate effective pathset交集为空。Final fix形成新tip并取得exact-tip `0 blocker／0 major`可squash复评后，按A→E门重验即可快速收口；任一identity、pathset、preimage、WIP交集或verdict漂移即停止并刷新本审计。
