# Systemd new-main 逐片 squash 回放策略独立审计 R2

- **评审范围**：只读复核主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 integration `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume` 的 `integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54`。覆盖线性两片 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` 与 `d3fabfadfba57af6c2d63e543e3198444777df54` 的 parent、精确 pathset、preimage／result blob、非 Plan patch、current living WIP 隔离、逐片单 commit 重建、每片 main-side gate、fresh Plan checkpoint及 reviewed-source archive targets。已有 merged-state review `0 blocker／0 major` 与两份 exact-tip verify `PASS` 作为既有证据，本轮另以 Git 对象、临时 index顺序应用和逐 blob 对账独立复验回放可执行性。
- **总体 verdict**：**可进入下一阶段。0 blocker／0 major，明确可执行。** 唯一安全路线是：先把主树 current living WIP形成独立 checkpoint并重新固定 actual main HEAD；随后只从 new-main candidate的精确父子 commit对象提取每片非 Plan patch，在主树逐片重建两个新的 non-merge单一语义 commits。S3完成 main-side gate、fresh Plan checkpoint及 source archive后才允许开始S4。禁止 fast-forward、regular merge、cherry-pick、两片合成一个 commit、旧 integration载荷、旧 Plan postimage，以及从 reviewed source `e16c2a7…` 直接提取S4 patch。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0个新增回放问题。既有配置优先级永久测试判别力、installer三文件事务措辞及timeout facts重复owner仍是已登记的 non-blocking minors，不改变本审计结论。
- **写入边界**：本轮未修改主树或 integration的 tracked files、真实 index、HEAD、branch或refs；未运行安装、manager、service、端口、进程、部署或cutover动作。唯一仓库写入为本报告 `docs/tmp/260807-resume-audit-systemd-squash-r2.md`。

## 双视角覆盖证据

### 机械核对视角

- 每个承载结论的 shell调用均在同一次调用内验证主树物理root与完整 `HEAD=b91e58a29324b11840002efc53ed6f869b800c39`，并验证integration物理root与完整 `HEAD=d3fabfadfba57af6c2d63e543e3198444777df54`；没有依赖共享terminal遗留cwd。
- 提交图严格为 `b91e58a29324b11840002efc53ed6f869b800c39 → 8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`。两片都是单 parent、non-merge提交；第一片subject为 `feat: configure graceful shutdown timeout`，第二片subject为 `feat: add rootless systemd user installer`。
- S3精确含9个非 Plan paths，S4精确含3个非 Plan paths。两片均未修改 `docs/agents/systemd-runtime/plan.md`；Plan在base、S3与tip的commit-object blob保持相同。
- S3 new-main patch-id为 `26dcc6fbfffe0db7d3358728ff244fec36078be1`，与旧 parent-adapted code-only `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc`及reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5`去除Plan后的patch-id相等。S4 new-main patch-id为 `412e73c47064720386c1075bfac0d3d8d08c6d26`，与旧 parent-adapted code-only `2ec0cb81832691685bfe8d98ad03071d2d5e5316`相等；reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd`去除Plan后的原始patch-id为 `861d8756f0120f7c32ef820a85be5cf8fc7ae463`，不同是既有S3-parent adaptation的必然结果。
- 当前主树tracked WIP精确为Implementation、Readiness与Systemd Plan三份living文档，真实index为空；两片code pathset与三份WIP的集合交集均为空。主树同时有既存untracked `docs/tmp/`与verification资产，integration也有既存untracked `docs/tmp/`，故两个现有worktree都不能被口头称为“全树clean”，更不能使用全量 `git add`。
- 在 `/tmp` 临时index中从 `main@b91e58a…`载入tree，精确加入三份living WIP形成模拟checkpoint后，S3 binary full-index patch的 `git apply --cached --check`通过；应用后9个结果blob逐项等于 `8cae6c2…`。再从该结果应用S4 patch，`--check`通过且3个结果blob逐项等于 `d3fabfa…`。整个临时演练退出0，真实index保持为空。
- Reviewed source refs仍精确为 `feat/systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5` 与 `feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`；当前没有指向两者的 `refs/heads/archive/*`。
- 本轮写报告前冻结三份living WIP的审计快照SHA-256：Implementation `93534c35d3912bec6c50feb50b64ed069cd16bfc48d60a9f5409fd070eaf2d84`、Readiness `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8`、Systemd Plan `3c639fcd73ad1deed9a164ece43eb0f982da7f2ae8259e5903e7a7d9c9a7054f`。这些值只描述本轮审计时的并行WIP快照；实际checkpoint前必须重取，不得把本报告中的hash当作未来提交门。

### 第一人称执行视角

- 作为checkpoint执行者，我先只处理current living-doc WIP，使用精确pathspec形成独立checkpoint；不加入 `docs/tmp/`、verification资产或systemd代码。提交后重新读取actual main完整SHA，并要求tracked worktree与index不再含未提交living docs；若并行会话继续修改任一living文档，先完成其owner流程并重建checkpoint，不能用restore／stash丢弃。
- 作为S3执行者，我不在candidate分支上merge或改写历史，也不cherry-pick `8cae6c2…`。我从冻结commit对象 `b91e58a… → 8cae6c2…`提取binary full-index patch，在checkpoint后的actual main上先核对9个preimage，再只应用这9个paths，确认真实index staged集合精确相等后创建一个新S3 commit。该新commit的parent是living checkpoint后的actual main，而不是原始 `b91e58a…`。
- 作为S3 gate执行者，我核对新commit相对其parent的patch-id、9个result blobs、`git diff --check`和Plan排除，随后运行S3定向与全仓main-side gates。只有全部完整退出0，才fresh更新Plan到actual S3 main commit并形成Plan checkpoint，再把reviewed source provenance归档到 `865a5b7…`；任一失败都停在S3，不开始S4。
- 作为S4执行者，我从“S3 commit＋S3 gate＋fresh Plan checkpoint”后的actual main开始，从冻结commit对象 `8cae6c2… → d3fabfa…`提取三路径parent-adapted patch。README preimage必须是S3结果，两个新增文件必须不存在。应用后只形成一个新S4 commit，不采用原始source `e16c2a7…` 的patch，因为它缺少S3-parent timeout adaptation且三项result blobs均不同。
- 作为S4 gate执行者，我核对adapted patch-id `412e73…`、3个result blobs、Plan排除与S3不回退，再执行installer、system／user timeout parity、全仓main-side gates。全绿后fresh更新Plan、形成checkpoint并做actual-main merged-state复核，再把source provenance归档到 `e16c2a7…`。
- 作为部署执行者，我不会把仓库squash、main-side tests或archive解释为unit已安装、manager已加载、effective cgroup已验证、生产 `4141` 可接管、rolling成立或cutover获授权。

## 事实性发现

未发现问题。审计范围内 blocker 0、major 0、minor 0；该策略在living checkpoint后明确可执行。

本轮唯一需要显式防止的误操作不是候选缺陷，而是身份混用：S4的reviewed source `e16c2a7…` 是archive provenance，不是当前回放patch载体。正确载荷只能来自new-main精确父子范围 `8cae6c2… → d3fabfa…`；直接应用source patch会丢失已评审的S3-parent adaptation并产生错误result bytes。

## 精确载荷与 preimage oracle

### S3 graceful timeout

- **载荷范围**：`b91e58a29324b11840002efc53ed6f869b800c39 → 8cae6c260c8bc2930be96eaecc7d6d24d470e00a`。
- **Stable patch-id**：`26dcc6fbfffe0db7d3358728ff244fec36078be1`。
- **Binary full-index patch SHA-256**：`bb7490325a8d35bc860d18cb86c83a4ef9f7e445a9fa67f187476f896a4d9308`。口径为本轮从exact parent／child Git对象生成的完整9-path patch；执行时应重取并交叉核对patch-id，不把该文件hash当永久常量。

| Path | Required preimage at replay | Required result blob |
|---|---|---|
| `contrib/systemd/ghc-api-proxy.service` | `33fe7a27ef92dd0c4c45e65f8311963919dada8d` | `40b38c56312aecf7dec3cd000b9b7727a1c07b9b` |
| `docs/agents/deployment-systemd/README.md` | `2e6c5b43dd280e26564a922672c33c4103dcd75b` | `bed9f5e960169592011ee4c047fb55e87f490c75` |
| `src/app/cli.py` | `aaada4f20b34519d6bec98b0dbe344134a5e3d22` | `44a45a9333e999dd451d7765044fde82953ecd20` |
| `src/app/config/loader.py` | `82015510aec998e3964333b92eb42d74a13c9ddf` | `5709158b3c89a7d25b2bcd55bbb0568bc7ff4bbb` |
| `src/app/config/settings.py` | `b6983eee29ec898cc8b1cfc6bb31c8ffd02a183d` | `d10f705891187b37daf2ac7c86d731088733c9f8` |
| `src/app/graceful_timeout.py` | absent | `20ca181c1dc128eca754a32353387aa76047581e` |
| `tests/smoke/test_systemd_units.py` | `7e67c524a7dbec9b14ef8ff75de0ba032c7b1d96` | `5ed2f96fff1860a0b3b11d9f468cf786cc194d66` |
| `tests/unit/test_cli.py` | `62575181a8d50152e56a2c778bc49db500461315` | `7e611b5a51a8b73b22ee82ba2ab584ec7b270483` |
| `tests/unit/test_config_loader.py` | `f41f4d4123bd28992fcf8a08aa1aeffd58c702b0` | `d547dcc587a5edc931155ea211ec389145fa7d10` |

S3 reviewed source与new-main candidate的 `src/app/config/settings.py`、`tests/smoke/test_systemd_units.py` result blobs不同，是因为new main保留了同路径同期变化；stable patch-id相同且临时index结果精确匹配candidate，故回放oracle必须使用上表new-main blobs，不能要求所有source postimage直接相等。

### S4 rootless installer

- **载荷范围**：`8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`。
- **Adapted stable patch-id**：`412e73c47064720386c1075bfac0d3d8d08c6d26`。
- **Binary full-index patch SHA-256**：`e3799c58c6fa8cd796494f5ed637ace58a23da17acf3c0973f91944d407c6034`。口径为本轮从exact parent／child Git对象生成的完整3-path patch；执行时同样重取。

| Path | Required preimage after S3 | Reviewed source blob | Required adapted result blob |
|---|---|---|---|
| `contrib/systemd/install-user.py` | absent | `07bbc94bc1e1e234b0b6e75551280d1595671821` | `fdee31ec890b2b7b408b1d0e95d01d4c4c8e8a06` |
| `docs/agents/deployment-systemd/README.md` | `bed9f5e960169592011ee4c047fb55e87f490c75` | `e3e54cb77ead5656ba83d38f760914f5ebca6c28` | `2bd8e5a00a6d2151ed378ac7b1f7ea2f26329b86` |
| `tests/smoke/test_systemd_user_install.py` | absent | `2da0f10ca0cccfc3dd06e60c11d44f2153b7270f` | `b91595c9ea0f6d701f5da9bc9a61719aec4efd2f` |

三项source blob与adapted result blob全部不同，因此source只能用于provenance归档与行为追溯；回放内容身份必须以 `d3fabfa…` 的三项result blobs为准。

## 安全执行序列

### Gate 0：living checkpoint

1. 在主树重新固定物理root、branch `main`、`HEAD == refs/heads/main`与当时完整SHA；固定integration物理root、branch与exact `d3fabfa…`，并重新证明两级parent不变。
2. 枚举主树tracked／staged WIP。由各owner完成current living docs的复评与checkpoint，只提交明确批准的living文档paths；不得使用 `git add -A`或把untracked `docs/tmp/`／verification资产吸入checkpoint。
3. Checkpoint后要求tracked worktree与真实index没有遗留living WIP，记录actual main完整SHA。若仍有并行tracked WIP，停止；不得restore、stash或覆盖。
4. 从candidate commit对象而不是现有integration worktree内容生成两份冻结binary full-index patches，并重算parent、pathset、patch-id与patch hash。现有integration有untracked `docs/tmp/`，提取必须显式使用commit-object范围，或在新建的干净detached临时worktree中进行。
5. 在任何真实应用前，用临时index从actual main tree演练S3 `--check`／apply／result blobs；对S4则从演练后的S3 tree继续。若checkpoint改变了任一代码preimage，停止并重新审计，不用三方merge或context fuzz强推。

### Gate 1：重建S3单一commit

1. 在checkpoint后的主树逐项验证9个preimage，真实index为空，tracked code paths无WIP。
2. 只把 `b91e58a… → 8cae6c2…` 的精确9-path patch应用到worktree＋index。应用后机械验证staged path集合与9项pathset精确相等；Plan、三份living docs、`docs/tmp/`与verification不得staged。
3. 创建一个新的non-merge S3 commit，parent为checkpoint后的actual main。不得cherry-pick `8cae6c2…`，不得mergeintegration，不得更新main到candidate ref，也不得把S4一起提交。
4. 验证新commit相对parent的patch-id为 `26dcc6…`，result blobs逐项匹配S3表，`git diff --check`通过，Plan不在commit中。
5. 运行S3定向配置／CLI／systemd unit／short-SIGTERM gates、全仓pytest与同范围collect-only、Ruff、Pyright及deadline／配置层正控。所有命令完整退出0；中断、共享terminal污染或不完整输出整组作废。
6. Gate通过后fresh更新Systemd Plan到actual S3 main完整SHA与实测结果，形成独立Plan checkpoint。随后创建immutable archive ref，target精确为reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5`；ref名称若仍未冻结则由主流程先冻结，不得擅自猜测。机械验证target后才允许进入S4。

### Gate 2：重建S4单一commit

1. 从“S3 commit＋S3 gate＋Plan checkpoint＋S3 archive”后的actual main开始，重新固定全部identity。验证README preimage为 `bed9f5e…`，两个新增文件absent，真实index为空且3个code paths无WIP。
2. 只把 `8cae6c2… → d3fabfa…` 的精确3-path adapted patch应用到worktree＋index。禁止从 `e16c2a7…`、`2ec0cb8…`或任何旧Plan-bearing commit提取替代载荷。
3. 验证staged path集合精确为三项并创建一个新的non-merge S4 commit，parent为S3 Plan checkpoint后的actual main；不得把S3与S4压成一个commit。
4. 验证新commit相对parent的patch-id为 `412e73…`，3个result blobs逐项匹配S4表，S3结果未回退，Plan不在commit中，`git diff --check`通过。
5. 运行installer定向pytest、真实 `systemd-analyze --user verify`、默认／`--check`零持久写、隔离临时XDG显式apply、重复apply bytes＋mtime幂等、零 `systemctl`、secret不泄露、system／user timeout parity、S3回归、全仓pytest／collect-only、Ruff与Pyright。不得连接或改变真实manager。
6. Gate通过后fresh更新Systemd Plan到actual S4 main完整SHA与实测结果并形成checkpoint；执行actual-main merged-state review／范围内verification。随后创建immutable archive ref，target精确为reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd`，不得指向 `d3fabfa…`、旧integration或未来main commit。

### Gate 3：最终历史形状

Main历史应呈现：`living checkpoint → S3 semantic squash → S3 Plan checkpoint → S4 parent-adapted semantic squash → S4 Plan checkpoint`。两个代码commit均为non-merge且各自只有本片精确paths；Plan只存在于片间／片后checkpoint，不进入任一代码commit。

这一路线同时排除三类错误：fast-forward会在checkpoint前一次把candidate identity写入main；regular merge会跨过S3 gate与片间Plan停止点；cherry-pick虽会创建新commit identity，但会直接消费candidate commit及其patch／message／author provenance，绕过本策略要求的显式commit-object patch提取、staged-path核对与checkpoint后重建门；用户也已明确禁止该方式。三者均不满足冻结流程。

## Reviewed-source archive

| Slice | Archive target | 建立前置 | 禁止替代目标 |
|---|---|---|---|
| S3 graceful timeout | `865a5b71210e2436b36786b5de67146939d1e0f5` | S3 main-side gate与fresh Plan checkpoint通过 | `862f4cfa…`、`8cae6c2…`、未来main S3 commit |
| S4 rootless installer | `e16c2a700f23f66535e7347ab7357518eb8e56bd` | S4 main-side gate、fresh Plan checkpoint与actual-main merged-state复核通过 | `2ec0cb8…`、`d3fabfa…`、未来main S4 commit |

Archive保存最终独立评审通过的pre-squash source provenance，不保存parent-adapted载荷身份。Archive ref名称当前未在审计输入中冻结；本报告只冻结target与时序，不创建、命名、移动或发布refs。

## 为什么不是 merge、FF 或 cherry-pick

1. **Checkpoint改变parent**：candidate第一片直接基于旧 `main@b91e58a…`；living checkpoint先进入main后，未来S3正确parent必然是新的actual main。FF不再适用，checkpoint前抢先FF则违反顺序并绕过WIP保护。
2. **逐片停止点是合同**：S3后必须先跑main-side gate、fresh Plan checkpoint与archive，失败即停。Merge tip或一次FF会把S4同时带入，无法证明S3停止点真实存在。
3. **Commit identity职责不同**：`8cae6c2…`／`d3fabfa…`是new-main构建与验收载体；未来main commits是checkpoint后重建身份；`865a5b7…`／`e16c2a7…`是reviewed-source provenance。逐片squash保持三层身份可机械区分。
4. **S4有parent adaptation**：原始source patch-id与adapted candidate patch-id不同。Cherry-picksource错误，cherry-pickcandidate仍违反用户指定的squash重建方式；只有从candidate父子commit对象提取adapted patch并在actual main形成新commit同时满足内容与历史合同。
5. **回滚粒度**：两个独立代码commit加片间Plan checkpoint保留S3／S4各自回滚与审计边界；两片合一或一个merge commit包装两片都会破坏该粒度。

## 结构怪味与处置

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| Reviewed source、old code-only、new-main candidate与future main | 同一行为存在四类commit identity，S4又有parent adaptation，容易误取patch或误归档 | 本轮冻结source provenance、candidate载荷与future main三层职责；S4禁止直接消费source patch |
| 两个现有worktree | tracked WIP与untracked审计资产并存，“clean”容易只看tracked状态后误用全量staging | checkpoint使用精确pathspec；载荷从commit对象或新detached临时树提取；每次commit前机械比较staged集合 |
| Living Plan与代码收敛时序 | 高频状态文档若进入代码commit会污染可复用载荷，若完全后置又失去逐片停止点 | 代码片排除Plan；每片main-side gate后fresh Plan checkpoint，Plan保持LIVING |

## 主观建议

无。当前没有同等安全的第二条路线；上述逐片semantic squash是同时满足用户指定历史形状、living WIP保真、逐片gate、S4 parent adaptation与reviewed-source provenance的唯一0-major方法。

## 最终结论

**0 blocker／0 major／0 minor，明确可执行。** 先形成并重验living checkpoint；随后只从new-main commit-object范围提取S3九路径patch与S4三路径parent-adapted patch，在actual main逐片重建两个新的non-merge单一语义commits。每片都必须依次通过identity／preimage、result blob、main-side tests、fresh Plan checkpoint与reviewed-source archive门；失败即停。禁止FF、regular merge、cherry-pick、两片合并、旧Plan bytes、旧integration载荷及source S4 patch。仓库收敛不授权unit安装、真实manager／cgroup、生产 `4141`、部署、rolling或cutover。
