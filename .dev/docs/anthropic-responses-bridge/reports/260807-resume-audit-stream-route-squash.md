# Anthropic Responses stream route checkpoint 后 squash 只读审计

- **评审范围**：固定主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 clean feature `/home/xp/src/ghc-api-proxy-py-stream-route` 的 `feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。核对完整线性三提交 range、逐提交与聚合 pathset、main preimage／candidate result blobs、exact-HEAD code review／verification、所有已登记 worktree 的 living WIP 重叠、checkpoint 后 `git merge --squash` 形状、最小 main-side tests及 reviewed-source archive target。未修改 Git index、HEAD、refs、branches、候选代码、服务或运行态；唯一主树写入为本报告。
- **总体 verdict**：**修复 living checkpoint 的 2 个文档 major 后可进入。Stream-route 代码候选本身为 0 blocker／0 major，明确可执行；checkpoint 闭合后，在 actual main 上执行且只执行 `git merge --squash f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。** 禁止 fast-forward、regular merge 与 cherry-pick。Squash 后必须通过本文 identity／pathset／blob／tests 门并创建新的单一 non-merge main commit；全部通过后，reviewed-source archive target 必须精确保留 `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。
- **blocker 数**：0。
- **major 数**：0 个 stream-route 代码或 squash 机制 major。当前另有 2 个 living checkpoint 文档 major：Implementation exact bytes `5be08662048f4f7f71a0eb104b98a7dec6795989fe290bf002cb004d152d1d8f` 仍把 History／stream 写成旧施工身份，`docs/tmp/260807-resume-review-implementation-current-r4.md` 因而判为 `0 blocker／2 major`、不可 checkpoint。先同步 current identities并把新 Implementation bytes复评到 `0 blocker／0 major`；不得跳过 checkpoint 直接 squash。
- **证据边界**：`docs/tmp/260807-resume-review-stream-route-r3.md` 的 `0 blocker／0 major` 与 `docs/tmp/260807-resume-verify-stream-route-r3.md` 的限定范围 `PASS` 都精确绑定 `f3922a9…`。它们放行本候选的 squash，不表示完整 Anthropic Responses bridge、完整 Acceptance、retry、quota／resident backpressure、真实 socket partial-write、部署或 cutover 已通过。

## 双视角覆盖证据

### 机械核对视角

1. 每个承载结论的 shell 都在同一次调用内打印并验证物理 cwd、Git top-level、分支／ref与完整 HEAD。主树精确为 `main@b91e58a29324b11840002efc53ed6f869b800c39`；feature ref与隔离 worktree HEAD均精确为 `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，feature status为空。
2. `git rev-list --count b91e58a…f3922a9` 为 3；merge-base精确为 `b91e58a…`；三片各有且只有一个 parent，形成 `b91e58a… → 2087f8f02516136314985f5c48bdee20b2f4b861 → bc436af647507df4ea45f3b01ca8942fade4f036 → f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，没有 merge commit。
3. 聚合 range pathset恰为 17 条：15 个修改、2 个新增，无删除、rename或文档路径。聚合 stable patch-id为 `1bc35d728390a5c96cac34a832b85b6499f1176c`；`git diff --check b91e58a…f3922a9`通过。
4. 三个独立提交的 stable patch-id分别为 `5909820eddf2d5fae546b0915352710cf35c9f50`、`a1dfdb68e6d6c5047ef1b99b2387a55fb00addc4`、`672e3f08af8d37d478788017a52156d0b5d4686a`。逐提交 pathset与父关系见下文，不用“tip diff正确”替代完整 range核对。
5. 对全部已登记 worktree执行 tracked＋untracked status扫描。只有主树与 systemd rebuild worktree存在未提交内容；它们与 stream聚合17路径的交集均为空。主树真实index为空，tracked WIP精确为 Implementation、Readiness与Systemd Plan三份living docs；systemd rebuild仅有一份不相关的untracked临时报告。`ANY_TARGET_WIP_OVERLAP=false`。因此可准确声明“与当前全部 living WIP 无代码路径重叠”，不是只检查主树后作全局外推。
6. 17条main工作树目标路径均未被tracked／untracked WIP改动；现有文件的worktree bytes仍对应 `main@b91e58a…` preimage，两个新增路径在main不存在。候选结果blob逐路径可由commit object读取。
7. `docs/tmp/260807-resume-review-stream-route-r3.md` 精确绑定 `f3922a9…`，verdict为 `0 blocker／0 major`、明确可 squash；`docs/tmp/260807-resume-verify-stream-route-r3.md` 精确绑定相同 base／tip并给出定向 `PASS`，记录实际主路径与本轮失败机制测试、目标正控、候选导入路径及测试前后clean。
8. 严格临时克隆演练从 `b91e58a…` checkout，复制并提交current三份living WIP形成单一模拟checkpoint `80005ccdfcd753e1e866ef1e97587f540d03fdac`，其唯一parent为 `b91e58a…`；随后真实运行 `git merge --squash f3922a9…`。Cached pathset精确17条，全部cached result blobs逐路径等于candidate tip，stable patch-id仍为 `1bc35d7…`，`git diff --cached --check`通过。模拟commit只证明checkpoint后形状可实现，不授权当前绕过Implementation 2 major。
9. 当前 `refs/archive/**` 中没有指向 `f3922a9…` 的ref，也没有名称含stream的archive ref。Archive尚未执行，目标未被错误占用。

### 第一人称执行视角

1. **作为living checkpoint执行者**：先同步 Implementation 中 History `864cfa30e291768cbc7b080fce80d9be4cbf2d83` 与 stream `f3922a9…` 的clean current identities及各自exact-HEAD复评状态；新Implementation bytes须取得独立 `0 blocker／0 major`。Readiness `c1e8494e…` 与Systemd Plan `3c639fcd…` 的旧0-major证据只在bytes不漂移时继续成立。任一bytes或报告绑定漂移即停。
2. **作为squash执行者**：checkpoint后重新读取actual main完整SHA，要求`b91e58a…`仍为其祖先，index与tracked worktree为空，并重新核对feature ref／commit、三提交父链、聚合pathset以及17条actual-main preimage。Actual main可以因living checkpoint前进，但17条代码／测试preimage必须仍等于本文oracle；不满足即停，不用restore、stash、`--force`或冲突选择覆盖并行工作。
3. **作为合并策略执行者**：只运行用户指定的 `git merge --squash f3922a9ba9f90e4eea598dac1d899ebbe18985e8`。即使Git图允许fast-forward，也禁止FF；regular merge会把feature提交直接带入main ancestry；cherry-pick不属于用户指定的聚合流程。三者都不是获准路线。
4. **作为staged结果核验者**：squash后尚未commit时，cached pathset必须精确等于17条目标路径；每条result blob、聚合stable patch-id与diff-check必须命中本文oracle。出现第18条路径、preimage／result漂移、冲突或空diff均停止，不提交。
5. **作为main-side验证者**：创建一个新的non-merge main squash commit后，只运行本文冻结的最小stream主路径与本轮失败机制测试；不把候选侧绿灯冒充main结果。进程内导入路径必须落在actual main root。任一测试失败即停，不创建archive，不宣称完成。
6. **作为archive执行者**：只有main squash commit已创建且最小main-side gate完整退出0后，才创建immutable reviewed-source archive ref；ref目标必须精确为 `f3922a9…`，不得指向新main squash commit。Archive ref只保留reviewed source provenance，不升级产品或部署状态。

## 完整三提交 range

### S1 `2087f8f02516136314985f5c48bdee20b2f4b861`

- Parent：`b91e58a29324b11840002efc53ed6f869b800c39`
- Subject：`feat: route Responses streams to Anthropic SSE`
- Stable patch-id：`5909820eddf2d5fae546b0915352710cf35c9f50`
- Pathset：
  - `M src/app/anthropic/client.py`
  - `A src/app/delivery/responses_anthropic_stream.py`
  - `M src/app/openai/responses_stream_parser.py`
  - `M src/app/pipeline/executor.py`
  - `M src/app/routes/anthropic.py`
  - `M tests/smoke/test_anthropic_responses_route.py`
  - `A tests/smoke/test_anthropic_responses_stream_route.py`

### S2 `bc436af647507df4ea45f3b01ca8942fade4f036`

- Parent：`2087f8f02516136314985f5c48bdee20b2f4b861`
- Subject：`fix: harden Anthropic Responses streaming`
- Stable patch-id：`a1dfdb68e6d6c5047ef1b99b2387a55fb00addc4`
- Pathset：
  - `M src/app/delivery/__init__.py`
  - `M src/app/delivery/anthropic_sse.py`
  - `M src/app/delivery/responses_anthropic_stream.py`
  - `M src/app/openai/responses_stream_parser.py`
  - `M src/app/routes/anthropic.py`
  - `M src/app/streaming/openai_sse.py`
  - `M src/app/streaming/sse.py`
  - `M tests/smoke/test_anthropic_block_delivery.py`
  - `M tests/smoke/test_anthropic_responses_stream_route.py`
  - `M tests/unit/test_responses_stream_parser.py`
  - `M tests/unit/test_streaming_sse.py`

### S3 `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`

- Parent：`bc436af647507df4ea45f3b01ca8942fade4f036`
- Subject：`fix: harden responses stream lifecycle`
- Stable patch-id：`672e3f08af8d37d478788017a52156d0b5d4686a`
- Pathset：
  - `M src/app/anthropic/client.py`
  - `M src/app/delivery/anthropic_sse.py`
  - `M src/app/delivery/responses_anthropic_stream.py`
  - `M src/app/openai/responses_stream_parser.py`
  - `M src/app/routes/anthropic.py`
  - `M src/app/streaming/keepalive.py`
  - `M src/app/streaming/sse.py`
  - `M tests/http/test_anthropic_routes.py`
  - `M tests/smoke/test_anthropic_responses_stream_route.py`
  - `M tests/unit/test_responses_stream_parser.py`
  - `M tests/unit/test_streaming_resilience.py`
  - `M tests/unit/test_streaming_sse.py`

## 聚合 pathset 与 blob oracle

`ABSENT` 表示该路径在 `main@b91e58a…` 不存在；squash后必须新增为给定result blob。

| Path | Main preimage blob | Candidate result blob |
|---|---|---|
| `src/app/anthropic/client.py` | `2c05425a2b0a90b5a03488a7919dbb5d0470c1ce` | `20f4379e38171c0d5caea81260f25787e5d3c518` |
| `src/app/delivery/__init__.py` | `e9efab0f9877a1f4d5f4e9881e754a76d94e43d5` | `a6a328bd394651fc1f713c0ca2c6cc415314a16c` |
| `src/app/delivery/anthropic_sse.py` | `932567e1eec3d26934a761ff5c59bd0ec240de19` | `9d1062a212d0b60b51eade0b8ff9bd282133675f` |
| `src/app/delivery/responses_anthropic_stream.py` | `ABSENT` | `00bf169377d39a0679075b4df66a754efffe4c62` |
| `src/app/openai/responses_stream_parser.py` | `df3353f1a1882fd4035657563280bfa5f93989ab` | `6aa0bce39ab3fedd705eaec6975da487fc71cc74` |
| `src/app/pipeline/executor.py` | `75ace9cbbfadec87e35501b1cea4b54023a81fa5` | `b9632fb4282dd9496a9e4e3747890427347d9e25` |
| `src/app/routes/anthropic.py` | `d6905a86f556c7dd008751c00276d44875b0f5e0` | `944508c720403763aca1916366eff107298ad6ce` |
| `src/app/streaming/keepalive.py` | `3aeb655cf667b6ee7bc207f21dadd9efa509dee2` | `61fea16be80a8c98d0fd0166544924b5b370d303` |
| `src/app/streaming/openai_sse.py` | `3d432b354a7b402c7a67014f29162cce43dfa3ef` | `2bee675e469f7c5212326d66fd7951d1f6ed6218` |
| `src/app/streaming/sse.py` | `50e5489cce69c6f28fa8f82a666474f3f605191c` | `5f9205b4e41efd1ce6aca63047e5d667313f5df0` |
| `tests/http/test_anthropic_routes.py` | `4aa3163466e2a43be30dc1c1d975af06a19232b7` | `d31e8a7306898ffdee777d47133c653c510eb69f` |
| `tests/smoke/test_anthropic_block_delivery.py` | `2c1f4bfcd26cbdcb292e9ca3bd746f26341b34b8` | `e73d9b4f3877cc58620bdd943a6976dbd6403869` |
| `tests/smoke/test_anthropic_responses_route.py` | `54f3e6c3788463edb0d0620a31d057da88f84e80` | `5cf490b01af385b807fd2fd5aca869af42b0841f` |
| `tests/smoke/test_anthropic_responses_stream_route.py` | `ABSENT` | `cac25d29672f5e63f9c5f2e5e61ab0aba191d6d2` |
| `tests/unit/test_responses_stream_parser.py` | `bb77e15edce5c05f4abbf9c1a9b819635b804ec8` | `35bdea62c4a3dd3aaf037f2ff40b2e9c5b4bfb61` |
| `tests/unit/test_streaming_resilience.py` | `5f072f6290177789632fec19fe4c0dec7bfa87ec` | `6debeaf4e54cebcf5ce797ca1f576391331086bd` |
| `tests/unit/test_streaming_sse.py` | `f2e101e450473627adce7fe6288c19024f19ccde` | `bc511f3e280f2d266049eb3029c1d2d8288af2ad` |

## Checkpoint 后精确 squash 门

以下是执行合同，不表示本报告已执行真实checkpoint、squash、commit、tests或archive。

### A. Living checkpoint门

1. 同窗重新gate主树物理root、Git top-level、`main`与执行时actual HEAD；`b91e58a…`必须仍为actual HEAD祖先。
2. 修订Implementation，使其同步History `864cfa3…`、stream `f3922a9…` 及各自current exact-HEAD报告；对新Implementation SHA-256取得独立 `0 blocker／0 major`且明确可checkpoint的报告。
3. 重取Implementation、Readiness、Systemd Plan current SHA-256。Readiness必须仍为 `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8`，Systemd Plan必须仍为 `3c639fcd73ad1deed9a164ece43eb0f982da7f2ae8259e5903e7a7d9c9a7054f`，否则重做各自exact-byte复评。
4. 真实index必须为空；tracked WIP必须精确等于获准living载荷。使用完整字面pathspec逐文件暂存，禁止`.`、`-A`、`-u`、目录或glob。Cached pathset、staged blobs与获准bytes精确相等，`git diff --cached --check`通过，且`docs/tmp/**`、`verification/**`与代码路径命中为0后，才创建独立living checkpoint commit。
5. Checkpoint后重新要求index与tracked worktree为空；untracked报告可保留，但17条目标pathspec的porcelain状态必须为空。然后才进入B门。

### B. Squash前 identity／preimage 门

必须同时满足：

- `refs/heads/feat/anthropic-responses-stream-route` 与feature worktree HEAD均精确为 `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，feature worktree clean；
- `b91e58a… → 2087f8f… → bc436af… → f3922a9…` 三片父链、提交数3与每片non-merge属性均未漂移；
- 聚合pathset精确为本文17条；
- actual main的17条目标preimage精确等于本文表格，包括两个路径必须不存在；
- actual main index与tracked worktree为空，17条目标pathspec无tracked或untracked状态；
- 不存在进行中的merge、rebase、cherry-pick或revert状态。

然后且仅然后执行：

```bash
git merge --squash f3922a9ba9f90e4eea598dac1d899ebbe18985e8
```

不得换成 `git merge`、`git merge --ff-only`、`git merge --no-ff`、`git cherry-pick`或逐提交replay。

### C. Squash staged结果门

提交前必须同时满足：

- cached pathset精确为本文17条；
- cached result blobs逐路径精确等于本文candidate result列；
- cached stable patch-id精确为 `1bc35d728390a5c96cac34a832b85b6499f1176c`；
- `git diff --cached --check`通过；
- staged集合不含任何living docs、`docs/tmp/**`、`verification/**`或其他并行WIP；
- feature三个原提交均不因squash进入main ancestry。

全部通过后创建一个新的non-merge main commit。Commit唯一parent必须是checkpoint后的actual main；commit subject应使用Conventional Commits，例如 `feat: route Responses streams to Anthropic SSE`。

### D. 最小 main-side测试门

只运行stream真实主路径与本轮失败机制，不扩大为完整Acceptance或全仓门：

```text
tests/smoke/test_anthropic_responses_stream_route.py::test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block
tests/smoke/test_anthropic_responses_stream_route.py::test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation
tests/unit/test_responses_stream_parser.py::test_empty_text_delta_conflicts_with_nonempty_authoritative_text
tests/smoke/test_anthropic_responses_stream_route.py::test_max_output_tokens_without_usage_uses_estimated_zero_usage
tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_uncertainty_is_projected_into_history
tests/smoke/test_anthropic_responses_stream_route.py::test_success_terminal_is_validated_before_message_stop
```

- 第1项是实际ASGI stream主路径，覆盖完整block前withholding、text／tool顺序、唯一terminal、History与finalize。
- 第2～6项覆盖本轮决定放行所依赖的失败机制：二次取消后的cleanup、空delta authoritative冲突、missing usage＋`max_output_tokens`、首body write uncertainty History、terminal identity／seal。参数化展开数量不作为硬编码门；以具名selector全部退出0为准。
- 测试必须在新main squash commit的物理root运行，并在同一进程确认 `app.__file__` 与关键模块解析路径位于 `/home/xp/src/ghc-api-proxy-py/src/`，不能从feature或其他worktree加载实现。
- 测试后重新核对新commit相对唯一parent的pathset、result blobs、stable patch-id、`git diff --check`与tracked worktree clean。任一失败即停，不进入archive门。

### E. Archive门

- 仅在D门全部通过后创建reviewed-source archive ref。
- 推荐ref名为 `refs/archive/260807-anthropic-responses-stream-route`；创建前必须确认不存在。
- 唯一合法target是 `f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，不得指向新main squash commit。
- 创建后再次读取ref object并断言精确等于 `f3922a9…`。Archive ref创建不隐含删除feature branch／worktree；清理须另行满足archive、main语义、main-side gate与feature clean条件。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md` current SHA-256 `5be08662…` — living checkpoint仍有2项精确current-state major，当前不能立即执行真实squash — `docs/tmp/260807-resume-review-implementation-current-r4.md` 已确认文档仍把History与stream写成旧身份；stream虽已取得 `f3922a9…` 的R3 `0 blocker／0 major`与限定`PASS`，Implementation bytes尚未同步，History身份也仍需同步 — 先修订Implementation并复评新bytes到0 major，形成独立living checkpoint，再执行本文B～E门。

Stream-route代码与用户指定的`squash`路线未发现blocker／major。Exact candidate已有 `0 blocker／0 major`代码终审与独立限定`PASS`，完整三提交range、17路径、blob oracle、全worktree WIP隔离及checkpoint后真实`squash`演练均闭合。

## 主观建议

无。用户已明确裁定使用 `git merge --squash`，本报告不提供替代合并策略，也不以当前图可FF为由推翻该决定。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/anthropic/client.py`、parser、delivery与route等17条共享热点 | 三提交range跨route、parser、delivery、SSE primitive与测试，若只核tip或只看最终pathset会遗漏中间片来源与组合接缝 | 本轮同时冻结逐提交parent／pathset／patch-id与聚合result blobs；实际只允许整体`squash`，main-side最小门覆盖真实ASGI主路径和本轮失败机制 |
| 全部worktree的living WIP | 多并行线可能修改同名热点，单看主树clean或“不同worktree”会假绿 | 本轮扫描所有登记worktree的tracked＋untracked路径，17条交集为0；执行时仍须重扫，结果漂移即停 |
| `docs/agents/anthropic-responses-bridge/implementation.md` 多点复述current身份 | clean successor与终审形成后，旧施工状态仍分散在顶部、表格、下一步与结构怪味入口 | 当前2 major先由独立living checkpoint关闭；不得用本代码审计替代Implementation内容复评 |
| 合并策略 | 三提交feature在图上可FF，容易被“保留历史更简单”或逐片可归因为由偏离用户裁决 | 固定唯一合法动作 `git merge --squash f3922a9…`；显式禁止FF、regular merge与cherry-pick |

## 报告评审状态

本会话处于叶子reviewer模式，不能派生独立reviewer。本报告包含current状态、执行门与下一动作，主会话仍须安排独立复核；该义务已转交，不能把本报告自述冒充二次评审。

## 最终结论

**Stream-route candidate `f3922a9ba9f90e4eea598dac1d899ebbe18985e8` 为0 blocker／0 major，限定独立验收PASS，明确可执行。** 当前不能跳过living checkpoint：Implementation `5be08662…`仍有2 major。同步History／stream current identities、把新Implementation bytes复评到0 major并形成checkpoint后，重新gate actual main并只用 `git merge --squash f3922a9…`。Squash staged identity、最小main-side测试及clean gate全部通过后，archive target精确为reviewed source `f3922a9…`。本报告不声称这些真实Git写操作已经执行。
