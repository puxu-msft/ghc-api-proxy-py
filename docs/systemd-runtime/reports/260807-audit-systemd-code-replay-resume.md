# systemd code-only 回放现场恢复只读审计

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、integration `/home/xp/src/ghc-api-proxy-py-integrate-systemd-code` 的 `integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`、线性 code-only 提交 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` → `2ec0cb81832691685bfe8d98ad03071d2d5e5316`、reviewed sources `865a5b71210e2436b36786b5de67146939d1e0f5` 与 `e16c2a700f23f66535e7347ab7357518eb8e56bd`、四份 current living docs，以及 `docs/tmp/260807-audit-systemd-next-rebuild.md`、`docs/tmp/260807-review-systemd-code-only.md`、`docs/tmp/260807-verify-systemd-code-only.md`。本轮未执行 cherry-pick、patch apply 到真实 index／worktree、commit、ref 更新、archive 创建、测试、unit 安装、manager 操作、部署或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入四文档 checkpoint 阶段；checkpoint 完成并重验执行时门后，可按 code-only 两片逐片回放。0 blocker／0 major。** 当前不得跳过 checkpoint 直接回放，因为主树当前 tracked WIP 仍是 Acceptance、Implementation、Readiness 与 Systemd Plan 四份 living docs；其中 reviewed source／旧载荷路径范围与 tracked WIP 的唯一交集是 `docs/agents/systemd-runtime/plan.md`。Code-only 两片自身已排除 Plan，故它们与 current tracked WIP 的交集实际为空。精确四路径 checkpoint 的临时 index 模拟证明 checkpoint 后 tracked WIP 归零；完成真实 checkpoint 后必须重新取得同样结果，才能开始第一片。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0 个新增 minor。Code-only review 已登记的 S3 配置优先级测试判别力与 S4 逐文件 atomicity 两项 non-blocking minor继续后补，不升级为本轮回放门。
- **执行方法边界**：**不得 cherry-pick。** 旧 `91f95f7d30c0b399eef98d997c0f88f57c2d0284` → `0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 禁止作为载荷；新 `862f4cfa…` → `2ec0cb8…` 也不通过 cherry-pick搬运。执行者应从精确父子 commit diff冻结每片 code-only patch与 pathset，在当时 main 上逐片重建提交，并以 preimage、result tree／blob与 main-side test gate验证；不得把旧 Plan patch、old Plan postimage或人工三方拼接带回主树。
- **运行态边界**：本 verdict不表示两片已进入main、unit已安装、真实user manager／effective cgroup已验证、服务已部署、`localhost:4141`已cutover或完整产品`PASS`。Readiness继续保持`NO_CUTOVER／FOUNDATIONS_ONLY`，不得触碰旧Bun、生产端口或`cc-daemon`。

## 双视角覆盖证据

### 机械核对

- 每个承载结论的 shell 调用均在同一次调用内打印并验证目标物理 root、Git top-level、branch与exact HEAD；没有依赖前一调用的cwd。
- 主树实时身份为`main@80bc8f252b46c511f428af1d97159a5980ee9dc9`，真实index为空。`git status --porcelain=v2 --untracked-files=all`显示四个tracked WIP，精确为Acceptance、Implementation、Readiness与Systemd Plan；其余大量`docs/tmp`／verification资产为untracked，不在index。
- Integration重启后实时身份仍为`integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`，`git status --porcelain`为空。`git log`与`git rev-list`两种视图一致证明范围严格为两个non-merge commits、零merge commit：第一片parent是`80bc8f2…`，第二片parent是`862f4cfa…`。
- 第一片`862f4cfa…`只包含S3的九个non-Plan paths；第二片`2ec0cb8…`只包含S4的三个non-Plan paths。该计数由本轮`git diff-tree`路径枚举与既有code-only review的独立清点交叉一致。Base、第一片与tip的Plan blob均为`ae73fdf88e104ff1f256e47fb8a51a02713a9834`，证明两条code-only commits没有修改Plan。
- Current tracked WIP与code-only union pathset的集合交集为空。Current tracked WIP与两个reviewed source commit的路径union交集严格只有`docs/agents/systemd-runtime/plan.md`。因此“Plan WIP是唯一重叠”只适用于reviewed source／旧载荷范围；对实际code-only载荷，更精确的结论是“无WIP路径重叠”。
- 对S3九个路径逐个比较`main@80bc8f2…` commit tree与第一片parent tree：既有路径blob全部相同，新增`src/app/graceful_timeout.py`两侧均为`ABSENT`。该检查明确使用`git cat-file -e`判缺失后再取blob，避免`git rev-parse <rev>:<missing-path>`把失败参数文本混入stdout造成假红。结论为`S3_MAIN_COMMIT_TREE_PREIMAGE=PASS`。
- 在独立临时index中从`80bc8f2…`开始，第一片`git apply --cached --check`通过；应用第一片到临时index后，第二片`--check`通过；顺序应用后的tree为`8ff3fbab24eaf02fbc1f14c68f5286e15e187d81`，与`2ec0cb8…^{tree}`精确相等。真实index随后仍为空。该证据证明当前main commit-tree preimage与两片code-only结果仍适用，不等于授权修改真实树。
- 四份current living docs的SHA-256由`sha256sum`与Python`hashlib.sha256`两种实现交叉一致：Acceptance `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`、Implementation `ccdf6edf83aa9703a6a95a74801e11e433df8248d76d7b9f077ab18664d5ffe2`、Readiness `ad36f43aea165b2a8cb1d6eaa6bbc08a0eca75278e6c7b6f1b623a514e44fd0a`、Systemd Plan `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e`。
- Acceptance current hash已有精确绑定的`0 blocker／0 major／0 minor`独立报告；Readiness current hash由`docs/tmp/260807-review-readiness-current-r8.md`精确绑定并给出`0 blocker／0 major／0 minor`。Implementation与Systemd Plan已在上述旧报告后继续变化，旧R8不能外推；本报告完整通读并独立对账这两份current bytes，确认它们已统一到code-only路线、禁止旧链、逐片gate、fresh Plan checkpoint、reviewed-source archive与运行态边界，未发现新的blocker、major或minor。本报告因此是这两份current bytes的本轮独立审计证据，不沿用旧hash verdict。
- 使用真实空index的副本做精确四路径临时staging，prospective staged集合严格等于上述四份living docs，`git diff --cached --check`通过，`docs/tmp`与verification交集为空；该prospective index下worktree tracked WIP为空。真实index始终未改变。此结果证明“checkpoint后重叠消失”在当前bytes上机械可实现，但真实checkpoint尚未发生。
- Reviewed source worktrees重启后分别固定为clean `feat/systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5`与clean `feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`。对应archive refs当前尚未创建；这与“每片main-side gate通过后再归档reviewed source”的顺序一致。

### 第一人称执行

- 作为checkpoint执行者，我先把四份current living docs作为一个精确checkpoint处理，只使用四个完整pathspec；提交前重新验证四个hash、各自current-byte `0 blocker／0 major`证据、空index、tracked WIP集合恰为四文件与`diff --check`。Checkpoint完成后重新检查tracked WIP为空；若任何bytes、HEAD、index或pathset漂移，停止并重建本门。
- 作为第一片执行者，我从checkpoint后的actual main开始，固定integration exact tip与父链，但不运行cherry-pick。我只重建`80bc8f2… → 862f4cfa…`的S3 code-only diff，执行前逐路径核对actual main preimage，执行后核对result blobs／tree并运行S3 main-side tests、Ruff、Pyright及timeout parity gate。任何一项失败即停止，不进入S4。
- 作为living Plan维护者，我只在S3代码提交与main-side gate均通过后，从刚形成checkpoint的Plan bytes fresh向前更新实际main commit identity、gate结果、archive状态与下一动作，再独立形成新的Plan checkpoint。不得从旧`91f95f7…`或`0a93e7f…`抽取Plan hunk，不得restore、stash或覆盖并行WIP。
- 作为S3归档执行者，我在S3 main-side gate通过后把reviewed source provenance固定到`865a5b71210e2436b36786b5de67146939d1e0f5`，而不是`862f4cfa…`或新main重建commit。Archive ref写入属于主会话后续动作，本轮没有创建ref。
- 作为第二片执行者，我只从S3 main-side gate与fresh Plan checkpoint后的actual main开始，重建`862f4cfa… → 2ec0cb8…`的S4 code-only diff，保留已经reviewed的S3-parent timeout parity adaptation。执行后运行S4 main-side tests、Ruff、Pyright、installer dry-run／apply幂等／零`systemctl`与system／user timeout parity gate；失败即停止。
- 作为S4归档与Plan维护者，我只在第二片gate通过后把reviewed source provenance固定到`e16c2a700f23f66535e7347ab7357518eb8e56bd`，再从当时living Plan checkpoint fresh记录实际S4 main commit、gate与后续S5；不得把archive指向`2ec0cb8…`或新main重建commit，也不得让Plan收口。
- 作为部署执行者，我不会把仓库回放或archive完成解释为安装、真实manager activation、effective cgroup、双栈生产接管或cutover证据。后续S5仍须在备用端口、隔离状态根与可回收user-manager fixture中独立验收；生产动作仍需用户另行明确授权。

## Current living 文档审计结论

### Acceptance

Current SHA-256 `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`继续保持`FINALIZED_ACCEPTANCE_ORACLE`，完整产品为`UNVERIFIED`。它不参与systemd代码pathset，只作为四文档checkpoint的行为与边界输入；已有精确current-byte独立`0 blocker／0 major／0 minor`证据，本轮未发现状态外推。

### Implementation

Current SHA-256 `ccdf6edf83aa9703a6a95a74801e11e433df8248d76d7b9f077ab18664d5ffe2`已把current systemd载荷统一为`integrate/260807-systemd-code-only@2ec0cb8…`，执行顺序统一为`862f4cfa… → 2ec0cb8…`，明确旧`91f95f7… → 0a93e7f…`只作历史provenance且不得回放，并在`docs/agents/anthropic-responses-bridge/implementation.md:71,232,234`一致规定四文档checkpoint、逐片main-side gate、每片后fresh Plan checkpoint与reviewed-source archive。旧Implementation R8绑定`305e2d6a…`且仍使用旧systemd-next路线，不能覆盖current bytes；本轮独立对账未发现current Implementation的新问题。

### Readiness

Current SHA-256 `ad36f43aea165b2a8cb1d6eaa6bbc08a0eca75278e6c7b6f1b623a514e44fd0a`由Readiness R8精确绑定为`0 blocker／0 major／0 minor`。`docs/agents/service-cutover/readiness.md:6,9,72,149`一致保持`NO_CUTOVER／FOUNDATIONS_ONLY`、code-only两片、checkpoint后逐片回放、每片fresh Plan与reviewed-source archive边界；未把局部`PASS`外推为P1、安装态或生产授权。

### Systemd Plan

Current SHA-256 `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e`在`docs/agents/systemd-runtime/plan.md:3,8,96-97,300,302,379-381,426`统一声明Plan继续`LIVING`、code-only两片排除Plan、旧链禁止回放、每片main-side gate后fresh更新／checkpoint、archive targets固定为reviewed sources。旧Plan R8绑定`5655958e…`且仍放行旧链，已失效；本轮完整通读current Plan与code-only review／verify／rebuild审计，未发现current bytes的新问题。

## 0-major后唯一执行序列

1. **四文档current checkpoint**：精确固定Acceptance `6457b896…`、Implementation `ccdf6edf…`、Readiness `ad36f43a…`与Systemd Plan `0f372ab2…`。提交后要求四路径clean、真实index为空、其他untracked `docs/tmp`／verification资产未进入提交。
2. **重验现场**：主树仍必须是checkpoint后的actual `main`，integration必须仍是clean exact `2ec0cb8…`，父链仍是actual base→`862f4cfa…`→`2ec0cb8…`，两片仍为code-only且不含Plan；重新计算pathset与preimage。任一漂移即停止，不沿用本报告。
3. **重建S3，不cherry-pick**：冻结第一片exact diff与pathset，在actual main上逐路径验证preimage后重建单一S3提交。提交后核对result blobs／tree并执行S3 main-side gate；失败即停。
4. **S3 fresh Plan checkpoint与archive**：S3 gate通过后fresh更新living Plan并形成新checkpoint；归档reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5`。不得归档integration或main重建commit来替代source provenance。
5. **重建S4，不cherry-pick**：只从S3 gate＋Plan checkpoint后的actual main继续，冻结第二片exact diff与pathset，保持S3-parent adaptation并重建单一S4提交。提交后执行S4 main-side gate；失败即停。
6. **S4 fresh Plan checkpoint与archive**：S4 gate通过后fresh更新living Plan并形成新checkpoint；归档reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd`。随后才进入S5，Plan继续living。
7. **合并态复核**：两片都进入main后，重新执行适用于new main identities的merged-state review／verification与全仓回归；旧`2ec0cb8…`的review／verify继续作为构建与语义证据，但不冒充new main commit identities的最终放行。

## 每片 main-side gate最低要求

### S3 graceful timeout

- 主树identity、S3 preimage与result blob／tree匹配。
- 定向pytest覆盖`tests/unit/test_cli.py`、`tests/unit/test_config_loader.py`与`tests/smoke/test_systemd_units.py`，并运行全仓pytest；数量以执行时current tests为准，不沿用`440`作永久阈值。
- 全仓Ruff与Pyright通过。
- System service的application `300s`、manager `330s`与正余量合同通过；短timeout SIGTERM路径继续观察Uvicorn timeout、FastAPI lifespan cleanup与有界退出。
- Gate后主树不得出现意外dirty code path，Plan仅在随后fresh update阶段改变。

### S4 rootless installer

- 主树identity、S4 preimage与result blob／tree匹配，并证明S3结果未被回退。
- 定向pytest覆盖`tests/smoke/test_systemd_user_install.py`及受影响systemd smoke，并运行全仓pytest；数量以执行时current tests为准。
- 全仓Ruff与Pyright通过。
- 默认／`--check`保持零持久写，显式`--apply`只写隔离临时XDG目录，重复apply保持bytes与mtime幂等，所有路径零`systemctl`。
- Rendered user units与system templates继续满足application `300s`、manager `330s` parity并通过适用的真实`systemd-analyze`静态verify；不得外推为manager activation。
- Gate后主树不得出现意外dirty code path，Plan仅在随后fresh update阶段改变。

## 事实性发现

未发现阻断性或major问题。

当前现场尚未完成真实四文档checkpoint，也尚未创建两份reviewed-source archive refs；二者是已冻结的后续顺序条件，不是“已经完成”的事实。只要严格执行本报告的checkpoint→S3重建→S3 gate→fresh Plan／archive→S4重建→S4 gate→fresh Plan／archive序列，当前证据支持继续；若跳过checkpoint、使用cherry-pick、携带任何旧Plan patch、把旧postimage用于冲突处理，或在第一片gate前进入第二片，本verdict立即失效。

## 主观建议

无。当前不存在两条等价路线：旧integration直接回放已由重建审计否决；code-only逐片重建是唯一同时满足living Plan保真、逐片归因、main-side gate与source provenance的0-major路线。

## 结构怪味与方案反思

- `docs/agents/systemd-runtime/plan.md`与旧systemd commits｜高频living状态与可复用代码patch耦合｜**本轮处置**：只使用排除Plan的code-only两片，每片gate后fresh更新Plan；旧Plan patch永久留在历史provenance。
- `docs/agents/anthropic-responses-bridge/implementation.md`与`docs/agents/systemd-runtime/plan.md`｜同一current执行路线多点复述，identity前进时容易产生弱一致性副本｜**本轮处置**：current bytes已统一到`862f4cfa… → 2ec0cb8…`，后续每次identity变化须全文传播并重新绑定hash审计。
- Reviewed source与integration／main重建commit｜三种identity都可被误写成archive对象｜**本轮处置**：archive target只允许`865a5b7…`与`e16c2a7…`，integration和main commits只作执行identity。
- **内部替代方案**：cherry-pick旧链会重新引入Plan冲突；cherry-pick新code-only链虽然路径上无WIP重叠，但用户已明确禁止cherry-pick，且逐片重建＋preimage／tree gate能更清晰证明载荷边界。故不采用任何cherry-pick路线。
- **判据判别力**：本轮同时区分三类结论：reviewed-source范围的唯一Plan重叠、actual code-only载荷的零重叠、prospective checkpoint后的零tracked WIP；没有把不同集合口径混成一句“唯一重叠”。临时index顺序应用得到exact tip tree，能区分“补丁可应用”与“结果bytes完全一致”。
- **成熟第三方方案**：Git原生commit对象、`diff-tree`、`cat-file`、临时index、`apply --cached --check`与`write-tree`已提供完整机械oracle，不需要自造patch或merge算法。

## 结论

**0 blocker／0 major／0 minor。** Integration重启后仍为clean exact `2ec0cb81832691685bfe8d98ad03071d2d5e5316`；current main commit-tree满足S3 preimage；两片在临时index顺序应用后得到exact tip tree `8ff3fbab24eaf02fbc1f14c68f5286e15e187d81`；actual code-only pathset与current tracked WIP无交集，reviewed-source／旧载荷范围的唯一交集是living Plan，精确四文档checkpoint后该tracked WIP可机械归零。完成真实checkpoint并重验现场后，按`862f4cfa…`→`2ec0cb8…`逐片**重建**而非cherry-pick；每片gate后fresh更新并checkpoint living Plan，分别归档reviewed sources`865a5b7…`与`e16c2a7…`。任何旧Plan patch、old postimage、跳片、运行态操作或生产外推均不在放行范围内。
