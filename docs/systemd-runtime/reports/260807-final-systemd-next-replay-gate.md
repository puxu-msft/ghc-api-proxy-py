# systemd-next 最终逐片回放 gate

- **评审范围**：只读复核 `docs/tmp/260807-review-code-systemd-next.md`、`docs/tmp/260807-verify-systemd-next.md`、prepared integration `/home/xp/src/ghc-api-proxy-py-integrate-systemd-next` 的 `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b`，以及 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。独立核验线性提交 `91f95f7d30c0b399eef98d997c0f88f57c2d0284`、`0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 的 parent、paths、stable patch-id、pre／post blobs、current main commit preimage、source targets `865a5b71210e2436b36786b5de67146939d1e0f5`／`e16c2a700f23f66535e7347ab7357518eb8e56bd` 与后补 minor 边界；未执行 cherry-pick、archive ref 更新、worktree 清理、unit 安装、manager 操作、部署或 cutover。
- **总体 verdict**：**可进入下一阶段。** Exact integration 已取得 merged-state code review `0 blocker／0 major` 与独立 verify `PASS`；本 final gate 独立身份对账未发现 blocker 或 major。由此形成 **M2 living checkpoint**：在执行前重新确认 current main、integration exact tip、重叠 path 无未提交 WIP 后，可以且应当按 `91f95f7…` → `0a93e7f…` 逐片回放，每片 main-side gate 通过后才进入下一片，任一片失败即停止。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：2 个本轮事实性发现：merged-state 报告遗漏 1 个既有 S3 后补边界，以及 current main 共享 worktree 有 1 个回放重叠 path 正在被并行修改。另有 2 个既有 source-level 后补边界需要继续保留：S3 配置测试判别力、S4 installer atomicity；二者均不阻塞本 checkpoint 或逐片回放。
- **即时执行状态**：**checkpoint 已成立，但本轮不得直接开始回放。** 复核时 current main 的 12 个重叠路径中，`docs/agents/systemd-runtime/plan.md` 存在未暂存并行 WIP，HEAD／index blob 为 `ae73fdf88e104ff1f256e47fb8a51a02713a9834`，worktree blob 为 `53fc13ff60cc0a582d679a5d7660594c254eaa5e`。这不否定 commit preimage 或 `0 major` verdict，但执行者必须等待该 WIP 被其 owner 安全提交／处置，随后重验 main HEAD 与全部重叠 paths；不得覆盖、restore、stash 或自行吸收该 WIP。
- **证据身份**：code review SHA-256 `39dee9a80b78bf410ec54d93c0784bd0a162d7cb71e1d7bec12a46bd3236130a`；verify SHA-256 `21f14b26589be846ad2d6d114554a47837e952ee26ea8aa27c47fb97eaa75ce9`。Integration、两个 source worktree 在本轮核验时均为精确 HEAD 且 clean。

## 双视角覆盖证据

### 机械核对视角

- 完整通读两份指定报告，并对照 S3／S4 source reviews、installer atomicity 裁决和 current living Plan 的回放合同；核对报告范围、verdict、未验证边界与 minor 传播是否一致。
- 独立确认提交图严格为 `80bc8f2… → 91f95f7… → 0a93e7f…`，范围内恰有 2 个 non-merge commits、0 个 merge commit；`91f95…` 有 10 个 paths，`0a93…` 有 4 个 paths，合并范围为 12 个 unique paths。
- 对每个提交分别用 `git show --binary | git patch-id --stable` 与 `git diff --binary <parent> <commit> | git patch-id --stable` 两种入口交叉验证 patch-id；逐路径读取 parent preimage 和 commit postimage blob。
- 对 12 个 union paths 独立对账 current main commit tree 与 `91f95…` parent，已有文件 blobs 精确相等，新增文件两侧均为 `ABSENT`；另行比较 main HEAD、index、worktree，识别出 living Plan 的并行 WIP，没有把工作树脏态冒充 commit preimage 不匹配。
- 固定 source worktrees：graceful `865a5b7…` 与 integration 第一片 stable patch-id 完全相同；installer `e16c2a7…` 与第二片 patch-id 不同且不是其祖先，逐路径 blob／diff 证明第二片是在 graceful parent 上增加 user timeout parity、验证与 living docs 同步后的适配提交，而不是丢失 source 行为。
- 扫描与本 systemd 范围匹配的现有 `archive/*` refs，仅发现 M1 的 `archive/260807-systemd-runtime → 49fb198…`；未发现指向 S3／S4 source targets 的 archive refs。故本 gate 只冻结未来 archive 的 source commit targets 为 `865a5b7…` 与 `e16c2a7…`，不虚构尚未冻结的 ref 名，也不执行 ref 更新。

### 第一人称执行视角

- 作为回放执行者，从 current main 开始先读取第一片 parent，确认其就是 `80bc8f2…`；回放 `91f95…` 后执行第一片 main-side gate，只有通过才允许回放 parent 指向第一片的 `0a93…`，随后执行第二片 main-side gate。任何 HEAD 前进、patch 冲突、路径 preimage 漂移或 gate 失败都停止并重建适用性证据，不沿用本报告强推。
- 作为共享 worktree 执行者，当前会先看到 living Plan 的未提交并行修改；因此不能立即 cherry-pick，也不能为“清洁”工作树而 restore／stash 他人 WIP。等待 owner 处置后重验，是执行前置条件，不是要求重开已经达到 `0 major／PASS` 的代码评审。
- 作为 source 归档执行者，在两片分别回放且各自 main-side gate 通过后，归档目标应保留 reviewed source identity：S3 指向 `865a5b7…`，S4 指向 `e16c2a7…`。Integration 第二片的适配 patch-id 不替代 S4 reviewed source provenance；archive ref 命名与实际更新属于回放后动作。
- 作为后续 S5 执行者，不会把本 checkpoint 外推为真实 user manager activation、effective cgroup、双 fd／双栈、unit 安装、`localhost:4141` cutover、rolling 或完整产品 `PASS`；这些仍是后续 living slices。

## 提交、paths、patch-id 与 blobs

### 第一片：graceful timeout

- Commit：`91f95f7d30c0b399eef98d997c0f88f57c2d0284`。
- Parent：`80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- Stable patch-id：`07220276eade068ed058d18e46eef93e2dc5a59c`，双入口一致；与 source `865a5b71210e2436b36786b5de67146939d1e0f5` 完全相同。

| Status | Path | Parent preimage | Commit postimage |
|---|---|---|---|
| M | `contrib/systemd/ghc-api-proxy.service` | `33fe7a27ef92dd0c4c45e65f8311963919dada8d` | `40b38c56312aecf7dec3cd000b9b7727a1c07b9b` |
| M | `docs/agents/deployment-systemd/README.md` | `2e6c5b43dd280e26564a922672c33c4103dcd75b` | `bed9f5e960169592011ee4c047fb55e87f490c75` |
| M | `docs/agents/systemd-runtime/plan.md` | `ae73fdf88e104ff1f256e47fb8a51a02713a9834` | `8a57ce55db7ae31432ac2512e2b07c2227227d1b` |
| M | `src/app/cli.py` | `aaada4f20b34519d6bec98b0dbe344134a5e3d22` | `44a45a9333e999dd451d7765044fde82953ecd20` |
| M | `src/app/config/loader.py` | `82015510aec998e3964333b92eb42d74a13c9ddf` | `5709158b3c89a7d25b2bcd55bbb0568bc7ff4bbb` |
| M | `src/app/config/settings.py` | `2fcf4c39fce438dbbc19db3741c41c6f6daae3a9` | `6abee64e881973e5b84be61ea6a383128709eead` |
| A | `src/app/graceful_timeout.py` | `ABSENT` | `20ca181c1dc128eca754a32353387aa76047581e` |
| M | `tests/smoke/test_systemd_units.py` | `78866bede2150838b8bbaaf155f9dc4268438dcc` | `f7eaa2538a3cddee11c4d96326e50e9c29dd832f` |
| M | `tests/unit/test_cli.py` | `62575181a8d50152e56a2c778bc49db500461315` | `7e611b5a51a8b73b22ee82ba2ab584ec7b270483` |
| M | `tests/unit/test_config_loader.py` | `f41f4d4123bd28992fcf8a08aa1aeffd58c702b0` | `d547dcc587a5edc931155ea211ec389145fa7d10` |

### 第二片：rootless user installer

- Commit：`0a93e7f18f197bf8a2395eaaf20afda446f92d6b`。
- Parent：`91f95f7d30c0b399eef98d997c0f88f57c2d0284`。
- Stable patch-id：`dc52495c97154388dac6da7ee1fc6e78d0cad614`，双入口一致。
- Source `e16c2a700f23f66535e7347ab7357518eb8e56bd` 的 stable patch-id 为 `1817c3326fa66137d0eb08417d68e0f669dacee8`；二者不同是有意的 parent adaptation，不得声称 patch-equivalent。

| Status | Path | Parent preimage | Commit postimage |
|---|---|---|---|
| A | `contrib/systemd/install-user.py` | `ABSENT` | `fdee31ec890b2b7b408b1d0e95d01d4c4c8e8a06` |
| M | `docs/agents/deployment-systemd/README.md` | `bed9f5e960169592011ee4c047fb55e87f490c75` | `2bd8e5a00a6d2151ed378ac7b1f7ea2f26329b86` |
| M | `docs/agents/systemd-runtime/plan.md` | `8a57ce55db7ae31432ac2512e2b07c2227227d1b` | `a38ca28bd80bb3b35672332de2905e6a9f8b5356` |
| A | `tests/smoke/test_systemd_user_install.py` | `ABSENT` | `b91595c9ea0f6d701f5da9bc9a61719aec4efd2f` |

## Current main preimage 结论

- `main@80bc8f2…` 的 commit tree 与 `91f95…` parent 对 12 个 union paths 精确一致；这证明 prepared commits 是以 current main commit 为 preimage 构造的。
- 既有 paths 的 main commit blobs 分别为：service `33fe7a2…`、deployment README `2e6c5b4…`、living Plan `ae73fdf…`、CLI `aaada4f…`、loader `8201551…`、settings `2fcf4c3…`、systemd smoke `78866be…`、CLI unit `6257518…`、config loader unit `f41f4d4…`；三个新增 paths 在 main commit 与第一片 parent 均为 `ABSENT`。
- Commit preimage 正确不等于共享 worktree 当前可写。复核时只有 living Plan 的 worktree blob偏离 HEAD／index，因此 replay executor 必须在实际动作前重验完整 12-path 三层状态。

## Source provenance 与 archive targets

| Slice | Reviewed source target | Integration commit | 关系 | 回放后归档要求 |
|---|---|---|---|---|
| S3 graceful | `865a5b71210e2436b36786b5de67146939d1e0f5` | `91f95f7d30c0b399eef98d997c0f88f57c2d0284` | stable patch-id 相同 | archive target 固定为 reviewed source `865a5b7…` |
| S4 installer | `e16c2a700f23f66535e7347ab7357518eb8e56bd` | `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` | source 语义经 S3 parent adaptation；patch-id 不同 | archive target 固定为 reviewed source `e16c2a7…`，不改指 integration commit |

Archive refs 只保存 provenance，不作为后续开发 HEAD，也不证明 unit 安装或运行态切换。Ref 名尚未由 current Plan 冻结，本报告不擅自命名；创建／更新 ref 必须发生在对应片回放及 main-side gate 通过之后。

## 后补 minor 边界

1. **S3 配置测试判别力**：`tests/unit/test_config_loader.py` 的 shutdown 专属组合用例只断言最终 CLI 值 `13`；YAML `11` 与 env `12` 同时失效时仍可能假绿。独立 runtime probe 已确认当前产品链路为 `300 → 11 → 12 → 13`，故这是测试覆盖 minor，不是运行时错误。后补拆成 default-only、YAML-only、YAML＋env、YAML＋env＋CLI 四层断言或等价参数化；不阻塞回放。
2. **S4 逐文件 atomicity**：installer 按固定顺序逐文件原子替换，不承诺三份 unit group all-or-nothing。后补统一措辞为“逐文件原子替换；整组不承诺 all-or-nothing”，并增加第二／第三次 replace 失败时“显式失败、无临时残留、修复后重跑收敛”的参数化回归；不引入 generation staging、整组 rollback 或 manager orchestration，也不阻塞回放。

冲突备份／卸载 manifest、symlink hardening、共享 timeout facts 提取与真实 user-manager／cgroup smoke 仍保留在后续 slices；它们不得被静默删除，也不得被临时升级为本次 replay gate。

## 事实性发现

[minor] `docs/tmp/260807-review-code-systemd-next.md:5,49,53` — merged-state 报告把 installer atomicity 写成“唯一已知 minor”，遗漏 S3 source review 与 living Plan 已保留的配置优先级测试判别力 minor — 两项都明确不阻塞，故遗漏不改变 `0 blocker／0 major` 或逐片回放 verdict，但若按该结论清理 backlog，会静默丢失 S3 后补 — **修复建议**：以后同步 living 文档时保留本报告“后补 minor 边界”的两项清单；无需为此重开 integration code review。

[minor] current main 共享 worktree 的 `docs/agents/systemd-runtime/plan.md` — 当前 worktree blob `53fc13f…` 与 HEAD／index `ae73fdf…` 不同，且该 path 同时被两片修改 — 立即 cherry-pick 会与并行 living-doc WIP 重叠；自行 restore／stash 会有数据丢失风险 — **修复建议**：等待 owner 提交／处置该 WIP，再重验 main HEAD、12 个 overlap paths、integration exact tip 与 clean status；这是执行前置条件，不是产品或 prepared commit major。

除此之外未发现事实性问题。尤其未发现 parent 链错误、额外 commit、path 污染、patch-id 误算、main commit preimage 漂移、review／verify verdict 冲突或 source provenance 丢失。

## 主观建议

无。

## 最终结论

**0 blocker／0 major；M2 living checkpoint 已形成。** 在不覆盖 current main 并行 WIP、且执行前 identity／preimage gate 重新通过后，按 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` → `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 逐片回放，每片分别执行 main-side gate，失败即停。两项已知 minor 按上文后补，不等待它们才回放；两片完成后 Plan 继续 `LIVING`，随后进入真实 user-manager／cgroup S5 与后续 rolling，不得宣称文档收口、unit 已安装、部署／cutover 已完成或完整产品 `PASS`。
