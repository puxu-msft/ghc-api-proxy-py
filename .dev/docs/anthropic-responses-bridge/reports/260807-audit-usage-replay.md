# Non-stream usage main replay 只读审计

- **评审范围**：只读审计 `/home/xp/src/ghc-api-proxy-py-nonstream-usage` 的 `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857`，相对直接 parent `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 与审计时 current `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。范围包括既有 review／verify verdict、提交 parent／path、stable patch-id、逐片结果 blob、current-main preimage 与未来 main-side gate；不执行 cherry-pick／squash，不创建或移动 ref，不修改候选或主树既有 WIP。
- **总体 verdict**：**可进入下一阶段，但必须先完成 happy 四片。** Usage 单提交本轮为 **0 blocker／0 major**；在 `1ed13ad… → 80b3cfa… → c950912… → 7e4b642…` 已按序进入 `main` 且各片 main-side gate 通过后，`aca3ced6…` 可作为单一语义提交 **squash／cherry-pick**。当前 `main@cf53334…` 尚不包含 happy，因此本 verdict 不授权提前摘取 usage，也不把 feature 侧绿色冒充回放后的 main-side PASS。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：核对目标 physical root、branch、精确 HEAD、clean worktree、单提交 parent、subject、精确 changed paths 与 `git diff --check`；完整读取 `docs/tmp/260807-review-code-nonstream-usage.md`、`docs/tmp/260807-verify-nonstream-usage.md`、`docs/tmp/260807-review-code-happy-path-r2.md` 及 current `docs/agents/anthropic-responses-bridge/implementation.md`。对 happy 四片与 usage 逐提交使用 `git show --binary` 和 `git diff <parent> <commit> --binary` 两个入口交叉验证 stable patch-id；逐 path 使用 `rev-parse <commit>:<path>` 与 `ls-tree` 交叉验证结果 blob。对全部受影响路径同时核对 frozen base blob、current main HEAD blob与主工作树 blob；三者相等或三者均不存在。候选定向 pytest、全仓 pytest、Ruff 与 Pyright 均在目标 import／cwd 下成功；Pyright 最终可信探针同时校验成功退出与 `0 errors, 0 warnings, 0 informations` 正文，未采用一次跨树 cwd 产生诊断却错误捕获退出码的失真探针。
- **双视角覆盖证据——第一人称执行模拟**：模拟从 current `main@cf53334…` 消费 frozen chain，而不是从四个 source refs重建第二条链。执行者先按 carrier → nonstream → parser → route／smoke 回放四个 happy commits，每片核对本报告 patch-id、changed paths与结果 blobs并完成该片 main-side gate；只有 `7e4b642…` 已进入 main且 gate通过后，才消费直接后继 `aca3ced6…`。Usage回放后核对三个最终 blobs，再运行 usage定向、happy交叠、全仓 pytest、Ruff与Pyright；任一 parent／path／patch-id／blob／gate漂移即停止，不以冲突解决、重建提交或 feature侧 PASS绕过。

## Review／verify 与依赖结论

- `docs/tmp/260807-review-code-nonstream-usage.md` 精确绑定 `aca3ced6…` 相对 `7e4b642…`，结论为可进入下一阶段、可 squash，且 blocker／major均为零。
- `docs/tmp/260807-verify-nonstream-usage.md` 绑定同一 candidate／base，独立覆盖 cache净 input、output保持、reasoning detail不二次计数、upstream total inconsistency、future details保留与 usage缺失 estimated，结论为 `PASS`；删除 reasoning映射的正控按目标机制变红。
- 本轮独立复跑候选定向测试、全仓测试、Ruff与Pyright均通过，候选执行前后保持 clean。测试结果口径分别为目标两份 usage／happy测试文件与候选 `tests` 全集；不把这些 candidate-side结果写成 future-main gate已经执行。
- `docs/tmp/260807-review-code-happy-path-r2.md` 绑定 `7e4b642…` 并给出 blocker／major／minor均为零，明确允许在 foundations进入 main后按四个线性 commits回放。Current Implementation进一步固定执行顺序为 happy四片 → usage → route wiring。
- Current `main@cf53334…` 已包含 foundations语义，但不包含 `7e4b642…` 或 `aca3ced6…` 的 commit ancestry。Squash／replay场景不能以 ancestry单独判断语义；本轮以 parent链、patch-id、changed paths与blob oracle判定。结论是 **happy必须先进入main并逐片通过main-side gate，随后usage可squash／cherry-pick**。

## Commit identity 与 changed paths

| 顺序 | Commit／subject | Parent | Stable patch-id | Changed paths |
|---|---|---|---|---|
| Happy 1 | `1ed13ad7e19385b9f86a1cd292547438f6137179` `feat: add versioned reasoning carrier codec` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `67e66ccc765074c98599c6381509e710280fb7e0` | `src/app/anthropic/request_preparation.py`；`src/app/anthropic/thinking/reasoning_carrier.py`；`src/app/anthropic/thinking/responses_reasoning.py`；`src/app/protocols/anthropic_responses.py`；`tests/unit/test_anthropic_client.py`；`tests/unit/test_anthropic_preparation.py`；`tests/unit/test_anthropic_responses_request.py`；`tests/unit/test_reasoning_carrier.py`；`tests/unit/test_responses_reasoning.py` |
| Happy 2 | `80b3cfade000cd9e1626074d14b1f9c9d5294891` `feat: convert Responses JSON to Anthropic messages` | `1ed13ad7e19385b9f86a1cd292547438f6137179` | `c947d52bd902b1140211952454a323b7501307df` | `src/app/protocols/responses_anthropic.py`；`tests/unit/test_responses_anthropic_nonstream.py` |
| Happy 3 | `c950912ad739f85c39397ab0f2c4d25b82dddcb7` `feat: assemble Responses stream events` | `80b3cfade000cd9e1626074d14b1f9c9d5294891` | `35c3332dadede958158df47bd102caf179ce9599` | `src/app/openai/responses_stream_parser.py`；`tests/unit/test_responses_stream_parser.py` |
| Happy 4 | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` `feat: add typed protocol route policy` | `c950912ad739f85c39397ab0f2c4d25b82dddcb7` | `6fd013e08f7b1320f666c9cbae1f001f73cfb808` | `src/app/pipeline/route_policy.py`；`tests/smoke/test_anthropic_responses_happy_path.py`；`tests/smoke/test_route_policy.py` |
| Usage | `aca3ced6e38efabf13ffe43d5935697801c74857` `fix: preserve nonstream usage details` | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | `e53b2de91c45471e405af6890eb8c245fa481b5d` | `src/app/protocols/responses_anthropic.py`；`tests/smoke/test_anthropic_responses_happy_path.py`；`tests/unit/test_responses_anthropic_nonstream.py` |

五个对象构成从 frozen foundations integration `6a00f6f…` 开始的严格线性、无 merge parent链。Usage本身只修改上述三个预期路径；没有文档、配置、route handler、History或stream production接线混入该提交。

## Current-main preimage oracle

审计时 current main为 `cf53334…`。对上表所有 changed paths，frozen base `6a00f6f…`、current main HEAD与current主工作树内容满足以下机械关系：

- Frozen base中已存在的路径，其 base blob、main HEAD blob与主工作树 `hash-object` 完全相等。
- Frozen base中不存在的 happy新增路径，在 current main HEAD与主工作树中也均不存在。
- 主树没有 `CHERRY_PICK_HEAD`、`MERGE_HEAD` 或 `REVERT_HEAD`。
- 主树有与本代码回放路径不重叠的既有文档／临时报告WIP，因此不得把本报告写成“整个main worktree clean”。未来动作仍须在每片回放前重新核对现场HEAD、index、changed paths与generation／action gate。

这组 preimage oracle证明审计时 current main在 happy＋usage代码路径上没有未裁决漂移；它不替代实际 cherry-pick，也不预先证明未来 main仍保持同一状态。

## 逐片结果 blob oracle

以下 OID均由提交树的 `rev-parse` 与 `ls-tree` 双入口交叉验证。未来每片进入main后，其列出的 changed-path结果blob必须精确相等；若main上下文导致任一blob不同，停止并重新审查差异。

### Happy 1 `1ed13ad…`

| Path | Expected blob |
|---|---|
| `src/app/anthropic/request_preparation.py` | `f0e518046ced0d0783c4b5033d4834fecc086748` |
| `src/app/anthropic/thinking/reasoning_carrier.py` | `7686b90f41d9b5f6c1620139d9a9962585cbeae2` |
| `src/app/anthropic/thinking/responses_reasoning.py` | `5b71443ac963eab47041a1cd030ffb074a14874d` |
| `src/app/protocols/anthropic_responses.py` | `7f8f4fa09add615fb5b8eb56dbf88f7e468de4f1` |
| `tests/unit/test_anthropic_client.py` | `3d461001d51f49536b940b2ec715c9a720935079` |
| `tests/unit/test_anthropic_preparation.py` | `73216e0928856ae3d3752eb03c634d0cf658ec35` |
| `tests/unit/test_anthropic_responses_request.py` | `2bdcd9e6bb6bcb37bd6fcb4e8346283cc69c56c7` |
| `tests/unit/test_reasoning_carrier.py` | `678ca7502db6b13fcdd8f192389126a2f13ecd37` |
| `tests/unit/test_responses_reasoning.py` | `228382df131693d18fac88f591a46e5615bbcd9d` |

### Happy 2 `80b3cfa…`

| Path | Expected blob |
|---|---|
| `src/app/protocols/responses_anthropic.py` | `c39fe3eb27b76a38b99d569010ba5a955593b02a` |
| `tests/unit/test_responses_anthropic_nonstream.py` | `477c91fdb573ffa8b58a4c5726ff0c3fbca11100` |

### Happy 3 `c950912…`

| Path | Expected blob |
|---|---|
| `src/app/openai/responses_stream_parser.py` | `f1eb3a0c901111ee24b363869e97ee0a3d6b2337` |
| `tests/unit/test_responses_stream_parser.py` | `a0d045df8225904fe3ce941091d4715a0253ab97` |

### Happy 4 `7e4b642…`

| Path | Expected blob |
|---|---|
| `src/app/pipeline/route_policy.py` | `03533eed8ad3ca30d240e3ba43259ae987d47d83` |
| `tests/smoke/test_anthropic_responses_happy_path.py` | `8290af7fef8366f1b63e09a16057b5ae70f6aa6e` |
| `tests/smoke/test_route_policy.py` | `63445d9e6c06839b1e1354f1e2042580155f2827` |

### Usage `aca3ced…`

| Path | Happy preimage blob | Expected usage blob |
|---|---|---|
| `src/app/protocols/responses_anthropic.py` | `c39fe3eb27b76a38b99d569010ba5a955593b02a` | `cf5de12314ef3adeb53c21c9a798bcc2b14b69f9` |
| `tests/smoke/test_anthropic_responses_happy_path.py` | `8290af7fef8366f1b63e09a16057b5ae70f6aa6e` | `11cea7f8cdd5a1f3d578b4df0ad4edecc5a7a10e` |
| `tests/unit/test_responses_anthropic_nonstream.py` | `477c91fdb573ffa8b58a4c5726ff0c3fbca11100` | `da80df0a5fff7e120e2b382fe5c448e1279218fe` |

Usage三个preimage blobs精确等于happy链对应结果，因此“happy先进入main”不仅是流程偏好，而是该提交内容身份的直接parent合同。提前摘取usage会绕过这个合同。

## Main-side gate

### 回放前

1. 核对主树physical root、branch `main`、`HEAD == refs/heads/main`、无进行中的 cherry-pick／merge／revert，并记录完整HEAD。
2. 核对 frozen integration仍为 `7e4b642…`、usage仍为 `aca3ced6…`、两个worktree clean；重新验证本报告parent／subject／changed paths／patch-id。
3. 对即将回放提交的全部changed paths，核对current main preimage与上一阶段expected blobs精确相等；对新增路径核对仍不存在。任一漂移即停止，不自动采用 `ours`／`theirs`，不从source refs重建第二条链。

### Happy四片

按 `1ed13ad… → 80b3cfa… → c950912… → 7e4b642…` 逐片回放。每片后先核对本报告结果blobs，再执行该片定向测试、交叠接缝、全仓pytest、Ruff与Pyright；全部通过后才进入下一片并按既有合同归档对应reviewed source。四片全部进入main且各片main-side gate通过，是usage回放的硬前置。

### Usage

1. 核对current main已包含happy四片的最终结果blobs，尤其是usage表中的三个happy preimage blobs。
2. 回放 `aca3ced6…` 后核对stable patch-id `e53b2de91c45471e405af6890eb8c245fa481b5d`、精确三个changed paths与三个expected usage blobs。
3. 运行 `tests/unit/test_responses_anthropic_nonstream.py`、`tests/smoke/test_anthropic_responses_happy_path.py`、与happy／request／reasoning相关的交叠接缝、全仓pytest、全仓Ruff与全仓Pyright。只有这些future-main结果实际全绿，才可记录usage main-side gate `PASS`并建立精确指向reviewed feature HEAD `aca3ced6…` 的immutable archive ref。
4. 回放后的main commit OID可因parent不同而变化，故不要求等于source commit；要求的是patch-id、path集合、结果blobs与main-side运行门共同成立。

## 事实性发现

未发现问题。审计范围内不存在阻止usage在happy之后squash／cherry-pick的major；当前唯一顺序约束是不可把`aca3ced6…`提前到其直接parent `7e4b642…`之前。

## 主观建议

无。

## 结构怪味扫描

- `docs/agents/anthropic-responses-bridge/implementation.md:192-194,213-214`——**候选侧PASS与future-main gate容易混写**——本轮不改living文档；本报告明确分离“review／verify与candidate质量门已通过”“happy必须先落main”“usage回放后main-side gate尚待实际执行”三层事实。
- `src/app/protocols/responses_anthropic.py`与两份usage测试——**同一文件跨happy与usage连续修改，提前摘取会隐藏parent依赖**——本轮用三个preimage／result blob对显式固化依赖；future-main任一blob不等即停止重审。
- Stable patch-id判据——**仅凭patch-id无法证明路径结果或运行语义**——本轮同时冻结parent、changed paths、逐片结果blobs、current-main preimage和运行门，没有把patch-id单独作为放行依据。

## 最终结论

`feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857` 相对 happy integration `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 的 review与独立verify均为 `PASS`，本轮审计为 **0 blocker／0 major／0 minor**。Current `main@cf53334…` 在全部相关代码路径上保持 frozen-base preimage，happy四片与usage五提交的parent、paths、patch-id及结果blobs已冻结。**明确放行：先将happy四片按序进入main并逐片通过main-side gate；随后`aca3ced6…`可作为单一语义提交squash／cherry-pick。** 在实际回放并完成future-main测试前，不得声称usage已经进入main或main-side gate已经PASS，也不得外推为stream parity、History持久化、完整bridge产品验收或部署／cutover完成。
