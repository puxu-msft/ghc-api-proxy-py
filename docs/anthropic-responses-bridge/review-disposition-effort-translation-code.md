# Effort translation 代码评审处置

- status：awaiting-final-scoped-re-review
- implementation_base：`b67634d929b22f3cdcc83cf5607cd37c4eb35c2c`
- pre_fix_head：`505d62fd2622c4ecb35e701fad33e1ca12300fb6`
- current_candidate：`ed6addd017f461c15abc494584e727f1badec633`
- task_reports：[Task 1 R1](reports/260903-review-effort-translation-task1.md)／[R2](reports/260903-review-effort-translation-task1-r2.md)；[Task 2](reports/260903-review-effort-translation-task2.md)；[Task 3 R1](reports/260903-review-effort-translation-task3.md)／[R2](reports/260903-review-effort-translation-task3-r2.md)／[R3](reports/260903-review-effort-translation-task3-r3.md)；[Task 4](reports/260903-review-effort-translation-task4.md)；[Task 5](reports/260903-review-effort-translation-task5.md)
- final_reports：[whole-branch R1](reports/260903-review-effort-translation-final.md)；R2 pending
- final_R1_counts：blocker=0，major=2，minor=4，nit=1

本文只记录代码实施评审的finding、裁定来源与终态。行为authority仍是[current Spec](spec.md)，Acceptance只转录可判否判据，[Implementation](implementation.md)报告候选进度；本文不得把某轮review pass外推为完整bridge、其它model／effort或部署状态。

## Task review处置

| Finding | 来源与成立度 | 裁定级别 | 处置 | 理由与实际修法 |
|---|---|---|---|---|
| Task 1 I1：profile最终接线无可判否测试 | Task 1 R1；事实`confirmed`，判断`concurred` | C | `adopted`，R2 closed | 补真实`build_chain→Chain→handle/count→TranslationTarget`记录型translator测试；commit`69b6ac6`。 |
| Task 3 M1：compatibility loss producer可删除而测试仍绿 | Task 3 R1；事实`confirmed`，判断`concurred` | C | `adopted`，R2 closed | 补`auto`、missing budget、low budget、over-bound四类ordered loss静态oracle与单侧控制；commit`edf1abb`。 |
| Task 3 stale integration expected | Task 3 fix R2；事实`confirmed`，判断`concurred` | C | `adopted`，R3 closed | 含compatibility extension样本保留default-high not-carried，真正lossless control改用明确发布high的model；commit`d824e4f`。没有删掉正确production loss来迁就旧expected。 |
| D1：Responses same-format stale residual effort precedence缺oracle | Task 3 deferred，final R1 F-MIN-2重裁为成立 | C | `adopted`，candidate fixed | Existing test加入residual`effort=low`与owned`high`冲突，完整wire固定owned precedence；commit`ed6addd`。 |
| D2：same-value per-message provenance与future-only original retention缺oracle | Task 3 deferred，final R1 F-MIN-3重裁为成立 | C | `adopted`，candidate fixed | Reader固定`high→high`仍为`ANTHROPIC_PER_MESSAGE`；public pipeline spy同时固定control从target input缺席、在`original_payload`保留；commit`ed6addd`。 |
| D3：过滤后的Anthropic effort候选loss detail误述整个catalog | Task 4 deferred，final R1 F-MIN-1重裁为真实defect | C | `adopted`，candidate fixed | Diagnostic显式命名`Anthropic-compatible`候选域，generic Responses wording不变；补交集为空、混合floor与downward exact oracle；commit`ed6addd`。 |
| D4：minimal二阶段alignment缺ordered双loss组合oracle | Task 4 deferred，final R1 F-MIN-4重裁为成立 | C | `adopted`，candidate fixed | 补minimal＋medium-only与minimal＋catalog absent完整wire和ordered losses；commit`ed6addd`。 |
| Task 5 nit：`Conversion`／`TranslationRefused` docstrings滞后于facts职责 | Task 5 review，final R1 F-NIT-1确认 | D | `adopted`，candidate fixed | 只同步non-loss facts、lossless独立性与refusal snapshot文字，不改runtime；commit`ed6addd`。 |

Task 2 review为Spec／Quality PASS且0 findings；Task 4、Task 5除上表deferred项外没有未闭合finding。

## Final whole-branch R1处置

| Finding | 陈述类型与成立度 | 裁定级别 | 处置 | 理由与实际修法 |
|---|---|---|---|---|
| F-MAJ-1：transparent replay丢失per-message effort beta source header | 新事实经coordinator按`driver.py:168→shape_request():109-112→inference.py:_reopen():416-420`首次确证；判断`concurred` | C | `adopted`，candidate fixed | `RequestContext.source_headers`以`None`区分未初始化和合法空mapping；`build_context`保存过滤后的request-lifetime snapshot，直接构造context首次读取时初始化一次；send／count／replay共用，path policy只改`client_headers`。真实首块前tear回归固定两个attempt均为controlled high、control不进input、header不转发且最终成功；旧行为变异精确以`beta-required`判红。Commit`ed6addd`。 |
| F-MAJ-2：Spec写同pattern整体替换，loader／plan／test／批准合同执行deep merge | 新事实经coordinator对`spec.md:281`、`loading.py:37-53`、plan与partial override test首次确证；判断`concurred` | C | `adopted`，docs fixed，runtime no change | 这是agent对配置层行为的错误转录，不是用户裁决。Spec revision record与正文纠正为通用recursive deep merge：同pattern未点名字段继承，mapping外值整体替换；Acceptance同时补正样本与whole-replacement缺陷注入。Runtime与现有test本来就正确。 |
| F-MIN-1～4 | Final R1对Task 3／4 deferred项逐条重裁；事实均有具体邻近错误实现 | C | `adopted`，candidate fixed | 对应D3、D1、D2、D4，见上一表与`ed6addd`。未新建proof／mutation framework。 |
| F-NIT-1 | Final R1；runtime正确、接口文档不完整 | D | `adopted`，candidate fixed | 对应Task 5 nit，见上一表与`ed6addd`。 |

## 明确未采纳／无需改变的路线

以下均来自final R1的“考察但未采纳”清单。本处置继续采用其结论；final R2须能反驳这些理由，沉默不单独构成新授权。

| 路线 | 裁定级别 | 处置 | 理由 |
|---|---|---|---|
| 要求same-format空`reasoning={}`或显式`effort:null`保持presence／bytes exact | C | `no_change_needed` | Direct Responses leg原样绕过translator；translated IR按Spec把absent与null都归一为enabled＋unspecified。当前同格式合同要求siblings与owned precedence，不要求claimed字段保留原拼写。若要改变，须先修订Spec而不是从test偷渡。 |
| Same-format writer重新插入已折叠的per-message control message | C | `no_change_needed` | Direct Anthropic不运行translator；translated target prompt按Spec必须移除control。未来control的权威副本是`original_payload`／History，已补的是这个保留oracle，不是向target wire复活control。 |
| 扩大cassette redaction字段或新增泛化secret detector | C | `rejected` | 当前既定credential／identifier字段、递归scrub和response-header allowlist未发现具体泄露；没有用户相关hazard，扩大属于security theater。 |
| 为其它model／effort继续录制live cassette | C | `not_adopted_in_scope` | 当前真实证据只校准PONG＋gpt-5.5＋explicit high，且报告明确不外推。其它静态组合由mock和oracle覆盖；没有新的上游事实问题值得真实调用。 |
| 新建常驻mutation framework、coverage gate或proof infrastructure | C | `rejected` | D1／D2／D4各有直接、可判否的局部test；新控制面不属于功能，也被项目规则禁止。 |
| 为D3重写通用alignment architecture | C | `rejected` | Defect只在过滤后诊断域名；向共享helper传candidate domain即可让Anthropic和Responses两种事实各自正确。全面重构扩大修复面而不改善合同。 |

## 当前证据

- `505d62f`：full Ruff通过；full Pyright 0 errors／warnings／informations；full pytest 2175 passed／2 skipped，coverage 91.17%。该证据在F-MAJ-1 replay gap被发现前取得，只说明当时已收集tests全绿，不证明缺失场景。
- `99e3642` agent source／`ed6addd` squash candidate：effort unit 187 passed；完整`tests/int/test_pipeline_app.py` 179 passed；focused replay／source-header／future-retention 7 passed；Ruff changed paths通过；Pyright changed paths 0 errors；`git diff --check`通过。
- Replay判别控制：把send／count source snapshot临时恢复为旧`dict(context.client_headers)`后，新test精确在第二次handle以`beta-required`失败；恢复后1 passed。该控制证明test打到request-lifetime source header接缝，不冒充其它retry行为。
- 真实cassette仍只证明本轮PONG场景在gpt-5.5对explicit high返回可回放high stream；没有追加真实调用。

## 等待R2核验

Final scoped R2只核：R1七项finding、`505d62f..ed6addd`fix diff、Spec／Acceptance correction、candidate config文档、Implementation与本处置账同步，以及这些修复触及的相邻合同。若R2确认全部addressed且无new breakage，再把本文status改为closed、补R2 counts与报告链接；之后仍须在exact candidate HEAD运行final full suite，不能把R2静态review替代测试。
