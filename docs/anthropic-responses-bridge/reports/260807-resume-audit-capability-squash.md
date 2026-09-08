# Reasoning capability checkpoint 后 squash 只读审计

- **评审范围**：固定主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 clean feature `/home/xp/src/ghc-api-proxy-py-reasoning-capability` 的 `fix/responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。核对单提交拓扑、精确 pathset、main preimage／candidate result blobs、exact-HEAD code review／verification、current living WIP 重叠、checkpoint 后 `git merge --squash` 形状、main-side gate及 reviewed-source archive target。未修改 Git index、HEAD、refs、branches、候选代码、服务或运行态；唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。Capability 代码候选为 0 blocker／0 major，明确可执行；当前先闭合 living checkpoint，再在 actual main 上执行且只执行 `git merge --squash 8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。** 禁止 fast-forward、regular merge 与 cherry-pick。Squash 后必须按本文 identity／pathset／blob／tests 门验证并创建新的单一 main commit；全部通过后，reviewed-source archive target 必须精确保留 `8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。
- **blocker 数**：0。
- **major 数**：0 个 capability 代码或 squash 机制 major。当前 living checkpoint 尚未闭合，是执行前置条件而非该候选代码缺陷：Implementation current SHA-256 已前进到 `5be08662048f4f7f71a0eb104b98a7dec6795989fe290bf002cb004d152d1d8f`；`docs/tmp/260807-resume-audit-living-checkpoint-r4.md` 精确绑定该 hash并判为 `0 blocker／0 major／1 pending`，pending原因是仍无精确绑定该bytes的独立Implementation内容复评报告；在其取得 `0 blocker／0 major` 并与已放行 Readiness、Systemd Plan 形成 checkpoint 前，不得开始真实 squash。
- **证据边界**：Code review 的 `0 blocker／0 major` 与 verify 的 `PASS` 都精确绑定 `8bff1c3…`，只放行 reasoning capability 合同，不表示完整 Anthropic Responses bridge、stream、History、部署或 cutover 已通过。

## 双视角覆盖证据

### 机械核对视角

1. 每个承载结论的 shell 都在同一调用内打印并验证物理 cwd、Git top-level、分支与完整 HEAD；并发终端出现但缺少本轮唯一 nonce 的输出全部作废。可信日志均具有完整 begin／end nonce或被写入唯一 `/tmp/UNIQUE31EF7CA6*.log` 后按绝对路径复读。
2. `git rev-list --count b91e58a…8bff1c3` 为 `1`；`8bff1c3…` 的唯一 parent 精确为 `b91e58a…`，不是 merge commit。Feature branch ref仍精确指向 `8bff1c3…`，对应 worktree clean。
3. 精确 pathset只有两个修改：`src/app/anthropic/client.py` 与 `tests/smoke/test_anthropic_responses_route.py`。无新增、删除、rename或文档路径。
4. Blob oracle如下：

| Path | `main@b91e58a` preimage | `feature@8bff1c3` result |
|---|---|---|
| `src/app/anthropic/client.py` | `2c05425a2b0a90b5a03488a7919dbb5d0470c1ce` | `b9f44148215c675c76d861ac74ddf9ec848739ae` |
| `tests/smoke/test_anthropic_responses_route.py` | `54f3e6c3788463edb0d0620a31d057da88f84e80` | `15ab87594435af6074e907cd18bf01c0e297a46e` |

5. Stable patch-id为 `2f99dd6c86780a223c7e2d0fa8ced25de5764c48`。`git diff --check b91e58a…8bff1c3`无输出。
6. `docs/tmp/260807-resume-review-reasoning-capability-r2.md` 精确绑定该 HEAD，verdict为 `0 blocker／0 major`、可进入 squash。`docs/tmp/260807-resume-verify-reasoning-capability.md` 精确绑定同一 HEAD与base，verdict为 `PASS`；它还记录独立真实 ASGI／pipeline probe、目标正控、定向回归、候选前后clean及实际模块加载路径。
7. Current main真实index为空；tracked living WIP精确为 Implementation、Readiness与Systemd Plan三路径。它们与候选两个代码路径交集为空，且主树这两个代码文件的worktree blobs仍精确等于上述preimage。候选不会覆盖current main living WIP。
8. 全部注册 worktree扫描发现 stream-route隔离worktree也有未提交 `src/app/anthropic/client.py`。因此本报告只声明“与current main living WIP无代码重叠”，不谎称“与所有隔离worktree pathset无重叠”。真实main squash不读取stream-route WIP；未来跨feature组合仍须单独做merged-state review。
9. 严格临时克隆演练先把当时current的三份living文档复制并形成真实模拟checkpoint `cb6021702a8e801310b76d868f9903bab20535dc`，其parent为`b91e58a…`；随后真实运行 `git merge --squash 8bff1c3…`。结果只暂存上述两个代码路径，两个worktree blob精确等于candidate result blob，stable patch-id仍为`2f99dd6…`，`git diff --cached --check`通过。
10. 初版临时演练因交互式 `cp` 未复制文件，且命令以分号继续导致伪绿，已明确作废。可信第二轮改用Python非交互复制与全程 `&&` 短路，并断言checkpoint必须产生三路径新提交；任何前置失败都会阻断squash。
11. 当前没有任何 `refs/archive/**` 或 tag指向 `8bff1c3…`，也没有名称包含reasoning capability的archive ref。Archive尚未执行，目标未被错误占用。

### 第一人称执行视角

1. **作为living checkpoint执行者**：先处理current三份tracked living docs，不把本报告、其他`docs/tmp/**`、`verification/**`或代码混入checkpoint。Readiness `c1e8494e…`与Systemd Plan `3c639fcd…`已有exact-byte `0 blocker／0 major`；Implementation current `5be08662…`经living checkpoint R4判为`PENDING`，仍无exact-byte内容复评报告，必须先取得独立`0 blocker／0 major`。任一bytes漂移则旧报告失效并停止。
2. **作为squash执行者**：checkpoint后重新读取actual main完整SHA，要求index与tracked worktree为空；再核对feature ref／commit、single-parent关系、exact pathset及两个actual-main preimage。Actual main可以因checkpoint前进，但两个代码preimage必须仍分别是`2c05425…`与`54f3e6c…`。不满足即停，不用`--force`、restore、stash或冲突选择覆盖并行工作。
3. **作为合并策略执行者**：只运行用户指定的 `git merge --squash 8bff1c3…`。即使图上仍可fast-forward，也禁止FF；regular merge会把feature commit带入main ancestry；cherry-pick会生成一个非用户指定squash流程的新提交。三者均不是获准路线。
4. **作为staged结果核验者**：squash后尚未commit时，cached pathset必须精确等于两个目标文件；结果blob、stable patch-id与diff-check必须命中本文oracle。出现第三条路径、preimage／result漂移、冲突或空diff均停止，不提交。
5. **作为main-side验证者**：先运行reasoning capability定向ASGI／request回归，再运行全仓pytest、Ruff与Pyright。每个命令都在actual main物理root与当时squash commit identity上重新gate，并用进程内模块路径或行为oracle排除加载其他worktree。任一项失败即保留现场用于诊断，不归档、不宣称完成。
6. **作为archive执行者**：只有main squash commit已创建且所有main-side gate完整退出0后，才创建immutable reviewed-source archive ref，ref目标必须精确为`8bff1c3…`，不得指向新main squash commit。创建后再次读取ref object并断言精确相等；archive ref只保存reviewed source provenance，不改变产品`UNVERIFIED`或部署`NO_CUTOVER`。

## Checkpoint 后安全执行门

以下是执行合同，不表示本报告已执行真实checkpoint、squash、commit、tests或archive。

### A. Living checkpoint门

- 重新gate主树物理root、top-level、`main`与执行时actual HEAD。
- 重取Implementation、Readiness、Systemd Plan current SHA-256；每个current bytes必须有精确绑定的独立`0 blocker／0 major`报告。
- 真实index必须为空；tracked WIP必须精确等于获准living载荷。使用完整pathspec逐文件暂存，禁止`.`、`-A`、`-u`、目录或glob。
- Cached pathset、staged blobs与获准bytes精确相等，`git diff --cached --check`通过，且`docs/tmp/**`、`verification/**`与代码路径命中为0后，才创建独立living checkpoint commit。
- Checkpoint后重新要求index与tracked worktree为空，再进入B门。

### B. Squash前identity／preimage门

必须同时满足：

- feature branch ref与commit object均为`8bff1c3fbd721060a87f18b0ef9d90d7d998a997`，worktree clean；
- `8bff1c3…`唯一parent仍为`b91e58a…`，base到target提交数仍为1；
- candidate pathset精确为两个目标文件；
- actual main的两个目标文件blob仍为`2c05425…`与`54f3e6c…`；
- actual main index与tracked worktree为空；
- 没有进行中的merge、rebase、cherry-pick或revert状态。

然后且仅然后执行：`git merge --squash 8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。

### C. Squash staged结果门

提交前必须同时满足：

- cached pathset精确为`src/app/anthropic/client.py`与`tests/smoke/test_anthropic_responses_route.py`；
- staged result blobs精确为`b9f44148215c675c76d861ac74ddf9ec848739ae`与`15ab87594435af6074e907cd18bf01c0e297a46e`；
- cached stable patch-id精确为`2f99dd6c86780a223c7e2d0fa8ced25de5764c48`；
- `git diff --cached --check`通过；
- staged集合不含任何living docs、`docs/tmp/**`、`verification/**`或其他并行WIP。

全部通过后创建一个新的non-merge main commit。Commit parent必须是checkpoint后的actual main，不能是`b91e58a…`或feature tip；commit subject应保持Conventional Commits，例如`fix: fail closed on ambiguous reasoning efforts`。

### D. Main-side测试门

在新main squash commit上按顺序运行：

1. Reasoning定向回归：`tests/smoke/test_anthropic_responses_route.py`与`tests/unit/test_anthropic_responses_request.py`中reasoning／effort／dual-capability selector；至少覆盖singleton enabled／adaptive、multi-effort顺序不变拒绝、unknown fail closed、budget闭区间、每attempt `PRE_SEND`后重转换及dual-capability Messages默认。
2. 全仓pytest。
3. Ruff：`src tests`。
4. Pyright：使用项目`.venv` Python检查`src tests`。
5. 重新核对新commit相对parent的pathset、result blobs、stable patch-id、`git diff --check`与工作树clean。

既有候选侧绿灯是candidate-side证据；main-side的定向pytest、全仓pytest、Ruff与Pyright必须全部重跑，不能沿用候选侧结果。

### E. Archive门

- 仅在D门全部通过后创建reviewed-source archive ref。
- Archive ref名称由主会话按项目归档命名约定选择；无论名称如何，唯一合法target是`8bff1c3fbd721060a87f18b0ef9d90d7d998a997`。
- 创建前确认该ref不存在；创建后确认其object精确等于`8bff1c3…`。
- 不得把archive改指main squash commit，不得删除feature branch／worktree作为本门的隐含动作；清理须另行审计与授权。

## 事实性发现

未发现capability代码或用户指定`squash`路线的blocker／major。Exact candidate已有`0 blocker／0 major`代码评审与独立`PASS`，单提交／pathset／blob oracle闭合，checkpoint后真实`git merge --squash`严格演练通过。

当前不可立即开始真实squash的唯一原因是living checkpoint内容门尚未闭合：Implementation current hash `5be08662…`只有精确绑定的living checkpoint R4 `PENDING`审计，没有exact-byte独立内容复评。该前置不推翻“capability代码0 major、明确可执行”，但禁止跳过checkpoint抢跑。

## 主观建议

无。用户已明确裁定使用`git merge --squash`，本报告不提供替代合并策略，也不以FF当前可行性推翻该决定。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/anthropic/client.py`同时被capability committed candidate与stream-route隔离WIP修改 | 并行feature共享热点文件，未来组合存在语义接缝风险 | 本轮不阻断capability独立squash；在stream后续进入main前必须基于包含capability的新main重建或做merged-state review，不能用“不同worktree”冒充无重叠 |
| living checkpoint current证据 | Implementation bytes前进后旧R3 verdict失效，checkpoint容易被旧报告假绿 | 本轮明确以exact SHA绑定；`5be08662…`取得独立内容0-major前不允许checkpoint或squash |
| merge策略 | 单提交分支在当前图上可FF，容易被“更简单”理由偏离用户裁决 | 固定唯一合法动作`git merge --squash 8bff…`；显式禁止FF、regular merge与cherry-pick |

## 报告评审状态

本会话处于叶子reviewer模式，不能派生独立reviewer。本报告包含current状态、执行门与下一动作，主会话仍须安排独立复核；该义务已转交，不能把本报告自述冒充二次评审。

## 最终结论

**Capability candidate `8bff1c3fbd721060a87f18b0ef9d90d7d998a997` 为0 blocker／0 major，独立验收PASS，明确可执行。** 当前先对Implementation `5be08662…`取得exact-byte内容复评`0 blocker／0 major`，完成独立living checkpoint；随后重新gate actual main并只用`git merge --squash 8bff1c3…`。Squash staged identity、main-side定向／全仓／Ruff／Pyright及clean gate全部通过后，archive target精确为reviewed source `8bff1c3…`。本报告不声称这些真实写操作已经执行。
