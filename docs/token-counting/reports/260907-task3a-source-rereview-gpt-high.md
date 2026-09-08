# Task 3A source rereview

## 范围与总体 verdict

- 原报告：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-source-review-gpt-high.md`，已在检查fix前完整读取。
- Fix范围：`56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8` → `c59cdd66a008f8ae8248b781a0c74fc36e129287`。
- 固定diff：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/review-task3a-fix1-56ec5e7..c59cdd6.diff`，101行，SHA-256为`7c96b078ae4b99970e2817d4c8ca7b1e4ae2b1de811daa08e5a6bd7d00ec2d9e`。
- 本轮仅复核原T3A-SR-01／02、101行fix及直接相邻的snapshot、event codec、retention、action-ID和intent-absence合同；未重审unchanged 2,320-line base diff。
- **总体 verdict：APPROVED。**
- **Spec compliance：APPROVED。**
- **Code quality：APPROVED。**
- **新发现计数：Critical=0，Important=0，Minor=0。**

## 原finding处置

### T3A-SR-01：ADDRESSED

Fix位于：

- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src/app/tokenization/types.py:874-887`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/test_features.py:501-536`

`LearningSnapshot.__post_init__()`现在从每个`PredictionRecord`的全部candidates构造`(record.sample_key, candidate.candidate_key)`集合，并要求snapshot evaluation keys为该集合的子集。

这同时满足两侧合同：

- Cold-only record携带额外`history-exact/median` evaluation时，subset检查拒绝该extra key。
- Diagnostic retention删除older evaluations时，空集或不完整evaluation集合仍是record candidate集合的合法子集，不会错误要求全集相等。

新增负控使用真实cold-only record和同sample的extra exact candidate，直接命中原反例；若删除新增subset检查，该测试会由预期`ValueError`变成成功构造，具有分辨力。

直接相邻的160-record／128-diagnostic测试通过，证明新增DTO检查没有把older missing误判为非法。

### T3A-SR-02：ADDRESSED

Fix位于：

- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src/app/tokenization/types.py:1008-1012`
- `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/tests/unit/tokenization/test_learning_store.py:5152-5222`

`TokenLearningObservation.__post_init__()`现在从所有evaluations提取candidate keys，并以tuple长度与set长度比较拒绝重复key。由于此前已经验证所有evaluation sample keys等于observation sample key，按candidate key判重等价于按`(sample_key, candidate_key)`判重。

Raw DB负控复制一个完整合法event evaluation entry，而不是把key改成非法值。Startup decode构造`TokenLearningObservation`时即触发唯一性检查，最终得到`LearningStoreStartupError(INVALID_STATE)`；测试同时断言启动前后的DB bytes逐字相等。

因此本修复不依赖原先会折叠重复项的graph set equality，准确覆盖了T3A-SR-02的失败机制。

## 直接相邻合同

- Fix commit只改变3个预期路径：`src/app/tokenization/types.py`、`tests/unit/tokenization/test_features.py`、`tests/unit/tokenization/test_learning_store.py`。
- `learning_schema.py`、`learning_store.py` production codec／graph、diagnostic pruning与其它candidate facts未改变。
- Fixed action ledger仍为108 semantic bases／204 expanded IDs；独立literal对账测试通过。
- Candidate／event／DDL intent-absence相邻测试通过。
- Per-candidate diagnostic budget及160 records＋128 diagnostics重建测试通过。
- Full tokenization sweep通过，未发现新增snapshot、event、schema、retention或其它candidate回归。

## 独立验证

所有load-bearing命令均在同一调用内显式进入`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd`，打印并断言physical cwd、toplevel、branch及HEAD；Python import oracle确认加载的是candidate `src/`。

- 原fix与相邻action／absence selectors：4 passed，1.41s。
- Older-missing、intent-absence与per-key retention selectors：3 passed，2.27s。
- 完整`tests/unit/tokenization/`：535 passed，147.77s。该命令包含完整`test_learning_store.py`，因此未再单独重复运行同一369-test文件。
- Ruff fix三路径：All checks passed。
- Pyright `src tests`：0 errors、0 warnings、0 informations。

## Identity与最终状态

开始和结束均确认：

- Candidate HEAD为`c59cdd66a008f8ae8248b781a0c74fc36e129287`。
- 唯一parent为`56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8`。
- Commit tree为`838f721573c0c910012fb39fb92ca5fbae85a122`。
- Fix diff SHA-256保持`7c96b078ae4b99970e2817d4c8ca7b1e4ae2b1de811daa08e5a6bd7d00ec2d9e`，行数保持101。
- 三个changed files的working-tree Git blob IDs逐项等于固定diff的new IDs。
- Candidate index重建出的tree等于commit tree；683个tracked entries逐blob比较为0 mismatch。
- `/proc`扫描得到`non_ancestor_candidate_processes=0`；candidate内无`*.sqlite*`或`*.db*`残留。
- 未修改、提交或push任何candidate source、test、authority或commit。

请求的新报告`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-source-rereview-gpt-high.md`未创建，因为当前subagent harness的developer约束明确禁止写review报告`.md`；原报告保持未覆盖。按任务fallback，完整报告正文在此回传。
