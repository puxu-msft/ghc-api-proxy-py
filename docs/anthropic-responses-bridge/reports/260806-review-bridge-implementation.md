# Anthropic Responses bridge 实施状态独立评审

## 评审摘要

- **评审范围**：`docs/agents/anthropic-responses-bridge/implementation.md` 全文，内容身份 SHA-256 `8eb18f93cec23dd5ee296dd67148a7145b92057f2d95fda4f0f10b72d2399026`；Git 状态核验锚定 current `main` `ed77c9d191df81c451c25161420515cca52ce6a4`。重点核验 reasoning squash／archive、liveness reviewed HEAD／集成 squash 状态、request latest HEAD／remaining review、server-tool 裁决、分支归档与 squash 规则，以及执行者应采取的下一步。
- **总体 verdict**：**修复 major 后可进入下一阶段**。文档的归档与 squash 规则可执行，server-tool 裁决仍与 current Spec 一致，但多个当前状态与下一步已经落后于实际进展。
- **blocker 数**：0。
- **major 数**：4。

## 双视角覆盖证据

### 机械核对

- 每次有效 shell 取证均在同一调用内验证物理 root `/home/xp/src/ghc-api-proxy-py`、分支 `main`、`HEAD == refs/heads/main == ed77c9d191df81c451c25161420515cca52ce6a4`；被其他并发终端输出污染且没有本轮 nonce 的返回未作为证据。
- 对账 current `main` 日志、`refs/heads/archive/260806-anthropic-responses-reasoning`、活动 feature／integration refs、相关 worktree 的 HEAD 与 clean status；分别验证 reasoning archive 精确指向 reviewed HEAD，以及 liveness integration commit 相对 current `main` 的净补丁与 reviewed candidate 相对 anchor 的净补丁相同。
- 读取并对账 reasoning R2、liveness R3、request R2 code review、request R2 verification、server-tool arbitration、Spec R3、Architecture R3、Acceptance R3 与 current Spec；扫描 request 修复后是否已有绑定 `fdd2f75…` 的新评审报告。
- 核验文档中的两个 reasoning integration token：完整 `ed77c9d191df81c451c25161420515cca52ce6a4` 可解析，进度表中的 `ed77c9d191df81ac70d805b1da157b34d021d33d` 不可解析。

### 第一人称执行模拟

- 按“下一切片 kick-off”执行会重复派发已经完成且 0 blocker／0 major 的 liveness R3，而看不到已经准备好的、与 reviewed 净补丁相等的 integration squash commit；执行顺序因此停留在旧阶段。
- 按 request 表格执行会把父提交 `028f1f2…` 当成 latest HEAD，并可能把该提交的行为 PASS 与代码评审混合为可 squash；实际代码评审在该 HEAD 仍有 1 major，修复已落在子提交 `fdd2f75…`，且尚无绑定新 HEAD 的独立复评。
- 按文档复评表执行会重复派发已经完成的 Spec R3 与 Architecture R3，同时漏掉 Acceptance R3 当前仍有 1 major；这会让实施者在错误 gate 上等待或误判文档定稿状态。
- 按 archive／squash 规则执行 reasoning 与 liveness：reasoning archive ref 可精确解析到原 reviewed HEAD；liveness 只有 integration branch、尚未进入 `main`，所以仍应先做 main-side 组合验证与集成，再创建 archive／移除活动分支。该规则本身没有发现 blocker／major。

## 事实性发现

### [major] `docs/agents/anthropic-responses-bridge/implementation.md:15` — Reasoning 进度表写入不存在的 integration commit

**问题**：总体进度表把 reasoning 的 main commit 写成 `ed77c9d191df81ac70d805b1da157b34d021d33d`，而同文档第 6、8、27 行及 current `main` 均是 `ed77c9d191df81c451c25161420515cca52ce6a4`。前者不只是缩写或排版差异，而是不可解析的 40 位 token。

**失败场景**：执行者按表格 token 做 blob 对账、祖先关系检查或回滚会立即失败；该表是首屏执行入口，不能依靠后文纠正。

**命令证据**：

```text
git cat-file -e ed77c9d191df81ac70d805b1da157b34d021d33d^{commit}  # 不可解析
git show -s --format='%H|%s' ed77c9d191df81c451c25161420515cca52ce6a4
# ed77c9d191df81c451c25161420515cca52ce6a4|feat: add Anthropic Responses reasoning carrier
```

**修复建议**：将第 15 行改为完整有效 commit `ed77c9d191df81c451c25161420515cca52ce6a4`，并保留第 27 行作为唯一事实来源或改为引用，避免同一 hash 被手工复述后漂移。

### [major] `docs/agents/anthropic-responses-bridge/implementation.md:16,50,62-69,152,158,163` — Liveness 仍写“待 R3”，导致下一步重复已完成评审并遗漏已准备的 integration squash

**问题**：`docs/tmp/260806-review-code-liveness-r3.md` 已绑定 `f27a8c04cd3470bd50d7194a30371ca5404f727e`，结论为 blocker 0、major 0、可 squash。仓库还已有 clean integration worktree 与单提交 `8e9aef69cc8606c4ca25286da617da8fc74d5c55`，其 parent 是 current `main`，其净补丁与 reviewed candidate 相对旧 anchor 的净补丁 SHA-256 同为 `7d06bdc27f9f45258ea9a739c7d2f2461c9e2a31d440738b0130cbdbd3445587`。但文档仍把 R3 当作未发生，并将它写成唯一下一切片。

**失败场景**：执行者会重新评审同一 HEAD，而不去核验 integration commit 的 blobs、运行 main-side gate、推进 `main`，也不会在成功集成后创建 liveness archive ref。当前 `main` 仍是 reasoning commit，故不能反向把 integration branch 写成“已进入 main”；准确状态应是“R3 已放行，integration squash 已准备但尚未进入 main”。

**命令证据**：

```text
rg -n -m1 '总体 verdict' docs/tmp/260806-review-code-liveness-r3.md
# 6:- **总体 verdict**：**可进入下一阶段**。
git show -s --format='%H|%P|%s' refs/heads/integrate/260806-session-liveness
# 8e9aef69cc8606c4ca25286da617da8fc74d5c55|ed77c9d191df81c451c25161420515cca52ce6a4|feat: add session liveness coordinator
git diff --binary 47d9ef101c4b81ac70d805b1da157b34d021d33d..f27a8c04cd3470bd50d7194a30371ca5404f727e | sha256sum
# 7d06bdc27f9f45258ea9a739c7d2f2461c9e2a31d440738b0130cbdbd3445587
git diff --binary ed77c9d191df81c451c25161420515cca52ce6a4..8e9aef69cc8606c4ca25286da617da8fc74d5c55 | sha256sum
# 7d06bdc27f9f45258ea9a739c7d2f2461c9e2a31d440738b0130cbdbd3445587
git rev-parse refs/heads/main
# ed77c9d191df81c451c25161420515cca52ce6a4
```

**修复建议**：把 liveness 状态更新为 R3 0／0 已通过；记录 integration commit `8e9aef6…` 只在 `integrate/260806-session-liveness`、尚未进入 main；将下一步改为核对 integration blobs、在该 integration HEAD 运行定向／全仓／Ruff／Pyright gate，成功后推进 current `main`、机械验证、创建精确指向 `f27a8c0…` 的 liveness archive，再清理活动 worktree／branch。

### [major] `docs/agents/anthropic-responses-bridge/implementation.md:17,84-89,114,159,163` — Request latest HEAD、R2 结论与 remaining review 均已陈旧

**问题**：文档把 `028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 写成 current candidate，并称四项 major 待 R2。实际 R2 已完成：独立行为复验在该 HEAD 为 PASS，但代码复评仍发现 1 major，具体为 unknown／unbounded reasoning limits 混同。活动分支随后新增修复提交 `fdd2f75fcec11e592b04f2686c4664262052a964`，当前 worktree clean；没有发现绑定该新 HEAD 的 request R3／post-fix 独立评审报告。

**失败场景**：执行者可能把父提交上的行为 PASS 错当作最新 HEAD 的完整放行，或继续等待已经完成的 R2；两者都会跳过新修复提交自身的独立复评。旧 PASS 只绑定 `028f1f2…`，不能自动覆盖 `fdd2f75…`。

**命令证据**：

```text
git rev-parse refs/heads/feat/anthropic-responses-request
# fdd2f75fcec11e592b04f2686c4664262052a964
git log -n 2 --pretty=format:'%H|%P|%s' refs/heads/feat/anthropic-responses-request
# fdd2f75fcec11e592b04f2686c4664262052a964|028f1f2ba7f7ac8ff30e609acb4b0661aff6124f|fix: fail closed on unknown reasoning limits
# 028f1f2ba7f7ac8ff30e609acb4b0661aff6124f|cb286059b656d960225c2afff84f204b9123810d|fix: harden Anthropic Responses request conversion
rg -n -m1 '总体 verdict' docs/tmp/260806-review-code-request-r2.md
# 6:- **总体 verdict**：**修复 major 后可进入下一阶段**。
rg -n -m1 '^\*\*PASS' docs/tmp/260806-verify-request-r2.md
# 5:**PASS。** 在目标提交 `028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` 上……
fd -t f . docs/tmp | rg 'request.*(r3|fdd2f75)|r3.*request'
# 无命中
```

**修复建议**：把 current candidate 更新为 `fdd2f75…`；记录 `028f1f2…` 的 R2 状态为“行为复验 PASS、代码复评 1 major”，并记录该 major 的修复已进入子提交但尚未独立关闭。下一步应对 `fdd2f75…` 做定向 post-fix 代码复评，复核 unknown limits、非正 budget 与修复回归；同时按项目 gate 决定是否重跑受变更影响的独立行为验收。只有新 HEAD 的 code review 0／0、所需验收通过，才可进入基于届时 current main 的 squash。

### [major] `docs/agents/anthropic-responses-bridge/implementation.md:116-126` — 文档复评表落后于 Spec／Architecture／Acceptance 的实际最新 verdict

**问题**：表格仍将 Spec 和 Architecture 标为 R2 有 major、等待 R3；两份 R3 已分别给出 blocker 0、major 0，可定稿。Acceptance 也已有 R3，不再是表中的 R2 两项 major：普通 per-request aggregate gate 已关闭，但 strict grammar 仍有 1 major。Research R2 报告仍不存在，因此只有该行的“待 R2”方向没有被后续报告推翻。

**失败场景**：执行者会重复派 Spec／Architecture R3，或者错误认为 Acceptance 仍有旧的两项待修，而漏掉 R3 明确指出的 `message_delta` 基数与过早 `ping` 问题。该表被后文“规范文档剩余项可并行修订与复评”直接作为下一步来源，陈旧状态会改变执行顺序。

**命令证据**：

```text
rg -n -m1 '总体 verdict' docs/tmp/260806-review-bridge-spec-r3.md
# 6:- **总体 verdict**：**可进入下一阶段；规格可定稿。**
rg -n -m1 '总体 verdict' docs/tmp/260806-review-bridge-architecture-r3.md
# 6:- **总体 verdict**：**可进入下一阶段；架构可定稿。**
rg -n -m1 '总体 verdict' docs/tmp/260806-review-bridge-acceptance-r3.md
# 4:- **总体 verdict**：**修复 major 后可进入下一阶段**。……内嵌 grammar 仍接受冻结 Spec 禁止的多个 `message_delta` 与过早 `ping`……
test -e docs/tmp/260806-review-bridge-research-r2.md
# exit 1，报告不存在
```

**修复建议**：将 Spec 与 Architecture 更新为 R3 0／0、可定稿；将 Acceptance 更新为 R3 0 blocker／1 major，并准确写出 strict producer grammar 的剩余项；Research 保持待 R2。同步修改“行为 oracle”中 Architecture 仍待确认的状态措辞，避免首页与复评表继续冲突。

## 已核验且未形成 blocker／major 的项目

- **Reasoning squash／archive**：`refs/heads/archive/260806-anthropic-responses-reasoning` 精确指向 reviewed HEAD `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b`；current `main` 的 reasoning integration commit 是单 parent、只改 helper 与对应测试。除进度表错误 token 外，该状态成立。
- **Server-tool 裁决**：current Spec 仍明确执行 server-tool no-revive；typed／server tools 以 `server_tool_not_supported` 拒绝，不映射为 Responses hosted builtin。实施文档对仲裁结论的转述没有发现漂移。
- **Squash 与分支归档规则**：先让 reviewed HEAD 通过独立 gate，再将最终净改动重放到 current main，运行 main-side gate，随后创建精确 archive ref，最后移除 clean worktree／活动分支；该顺序与现有 reasoning 归档及 liveness integration 状态相容。未发现规则本身需要 blocker／major 级修改。

## 主观建议

无。本轮只报告 blocker／major；上述 4 条均为 current Git refs、报告绑定关系或可执行下一步直接证实的事实性问题。
