# Four living docs current checkpoint 审计

- **评审范围**：`main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 上四份 current working-tree living docs：`docs/agents/anthropic-responses-bridge/acceptance.md`、`docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/service-cutover/readiness.md`、`docs/agents/systemd-runtime/plan.md`；各自 current SHA-256 与独立 review 绑定；真实 Git index；tracked WIP 精确集合；仅四路径 prospective staging、`diff --check` 及 `docs/tmp`／verification 排除。未修改四文档、review、代码、branch、ref 或真实 index，未创建 commit、回放代码、运行产品测试、安装 unit、操作 manager、部署或 cutover。
- **总体 verdict**：**存在 blocker。当前不得暂存或提交四文档 checkpoint。** Acceptance、Readiness 与 Systemd Plan 均有精确绑定 current SHA-256 的独立 `0 blocker／0 major` 报告；Implementation current SHA-256 `5389756fb9f868b5c1bc92d26cbeac0d77e36162cb5187991218ed0199b36330` 没有任何精确绑定的独立 review。最新 Implementation R7 绑定旧 SHA-256 `47a01b344b93929f4a6b7e59723be4bff863da46f1d04e2801a5e6df50c50b16`，且 verdict 为 `0 blocker／1 major`。Current bytes 虽已变化并看似处置 R7 finding，但本审计不能代替被要求的独立 current-byte review，也不能把旧 verdict 外推到新 bytes。
- **blocker 数**：1。
- **major 数**：0。
- **minor 数**：0。
- **提交门状态**：**`BLOCKED`。** 真实 index 保持为空。只有 Implementation current SHA-256 `5389756…` 取得精确绑定的独立 `0 blocker／0 major` verdict，且执行当刻本报告第“条件式可执行提交门”的全部 identity、hash、index、WIP、pathset 与 diff-check 条件仍成立，才可执行精确四路径 `git add` 并进入 commit dry-run／提交。

## 双视角覆盖证据

### 机械核对

- 每次承载结论的 shell 调用都在同一次调用内验证物理 root 与 cwd 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- 四文档在提交边界演练前后各读取一次 SHA-256，两次结果完全一致：Acceptance `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`；Implementation `5389756fb9f868b5c1bc92d26cbeac0d77e36162cb5187991218ed0199b36330`；Readiness `4d1e5a5281bd186d4742560f58dda799c6c8c2840c62b741605f945ba377314d`；Systemd Plan `5655958edc768e1284560a3cd5f1ace392cf15116fad842e09919c51d7516c13`。
- Acceptance current SHA 由 `docs/tmp/260807-review-acceptance-empty-reasoning-r2.md` 精确绑定，verdict 为 `0 blocker／0 major／0 minor`，明确可 checkpoint；`docs/tmp/260807-audit-acceptance-current.md` 对同一 SHA 另给出 `0 blocker／0 major／0 minor` 交叉证据。
- Readiness current SHA 由 `docs/tmp/260807-review-readiness-current-r5.md` 精确绑定，verdict 为 `0 blocker／0 major／0 minor`，明确可 checkpoint、继续 living 实施。
- Systemd Plan current SHA 由 `docs/tmp/260807-review-systemd-runtime-plan-r8.md` 精确绑定，verdict 为 `0 blocker／0 major／0 minor`，明确可形成文档 checkpoint；`docs/tmp/260807-audit-systemd-plan-checkpoint.md` 对同一 SHA 另给出 `0 blocker／0 major／0 minor` 交叉证据。
- 对 Implementation current SHA-256、Git blob `78b1cd52288255498a3a304c2a35747e2072fb15`、SHA 前缀与 `docs/tmp/*.md` 中全部 Implementation review 文件进行检索，未发现绑定 current bytes 的报告。最新 R7 只绑定旧 SHA `47a01b…`，明确为 `0 blocker／1 major`；旧 R6／R4 的 `0 major` verdict 也只绑定各自旧 bytes，均不得沿用。
- 审计开始及临时 index 演练前后，真实 index staged path 数均为 0；真实 index 文件 SHA-256 前后均为 `663fbf24e628c1eec203cd2c5ef46c4a1c697e050faff949539f06b179c85cfc`，staged patch SHA-256 前后均为空 patch 的 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- `git diff --name-only` 精确得到四个 tracked WIP，集合与顺序均为 Acceptance、Implementation、Readiness、Systemd Plan；没有第五个 tracked WIP。
- 在独立临时 index 中从真实空 index 副本执行精确四路径 `git add -- <四路径>`，prospective staged path 数严格为 4，且仅为四份目标文档；`docs/tmp`、文件名含 `verify` 的 verification 资产及其他路径均未进入 prospective index。临时 index 的 `git diff --cached --check` 通过；四文档 worktree `git diff --check` 也通过。临时 index 已清理，真实 index 未改变。

### 第一人称执行

- 作为 checkpoint 提交者，从四文档审查清单逐项进入时，Acceptance、Readiness 与 Systemd Plan 都能落到“current hash → current review → 0 major”的闭环；Implementation 在第二步即断链，只能找到旧 SHA 上的 R7 `1 major`。若此时继续暂存，就会把“current bytes 看似修复”冒充“current bytes 已独立复评”，直接违反本轮要求的 review-to-hash 绑定门。
- 作为 Git 操作者，精确四路径 staging 本身可形成只含四文档的 prospective index，`diff --check` 也为绿；但 staging 边界正确不证明内容 review 门成立。故真实 index必须继续为空，不能因为机械 pathset 通过而越过缺失的 Implementation 证书。
- 作为后续执行者，在 Implementation current review 达到 `0 blocker／0 major` 后，必须重新读取全部四 SHA 和现场集合；若任一 bytes、HEAD、index、tracked WIP 或 review verdict发生漂移，本报告的条件式门自动失效，需重新审计。通过后形成的 checkpoint 只放行 living 实施与后续逐片回放，不表示文档收口、完整 bridge `PASS`、unit 已安装、部署完成或 cutover 获授权。

## 事实性发现

[blocker] `docs/agents/anthropic-responses-bridge/implementation.md` current SHA-256 `5389756fb9f868b5c1bc92d26cbeac0d77e36162cb5187991218ed0199b36330` — 缺少精确绑定 current bytes 的独立 `0 blocker／0 major` review，因此四文档 checkpoint 的必要内容门未闭合 — `docs/tmp/260807-review-implementation-current-r7.md` 绑定的是旧 SHA `47a01b344b93929f4a6b7e59723be4bff863da46f1d04e2801a5e6df50c50b16`，verdict 为 `0 blocker／1 major`；对 current 完整 SHA、Git blob、SHA 前缀及全部 Implementation review 文件的检索均未找到后续 current-byte 报告。旧 `0 major` 报告不能覆盖新 bytes，临时 index pathset 与 `diff --check` 通过也不能替代独立内容评审 — **修复建议**：对 Implementation current SHA `5389756…` 做定向独立复评，至少消费 R7 唯一 major，核对 clean successor `c43db35…`、三提交拓扑、四文档 checkpoint、逐片回放、living 不收口与产品 `UNVERIFIED`；只有 verdict 达到 `0 blocker／0 major` 后，才重新运行下述提交门。

## 已通过但不构成放行的机械条件

- `main` 与工作树身份正确：`80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- 真实 index 为空且演练前后未改变。
- Tracked WIP 恰为四份目标文档。
- 四份 current bytes 在两次 hash 读取之间稳定。
- 精确四路径 prospective staging 只含四份目标文档，不夹带 `docs/tmp`、verification 或其他 WIP。
- Worktree 与 prospective staged diff-check 均通过。

这些条件只证明 Git 提交边界可机械实现，不证明四份内容均已取得 required review。Blocker 未关闭前不得执行真实 `git add`。

## 条件式可执行提交门

以下门只在新的 Implementation 独立复评精确绑定 SHA-256 `5389756fb9f868b5c1bc92d26cbeac0d77e36162cb5187991218ed0199b36330` 并给出 `0 blocker／0 major` 后启用；在此之前，本节是冻结的后续动作说明，不是当前授权。

1. 重新 gate 物理 root、cwd、`main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。若 main 已前进，停止并重建审计。
2. 重新计算四文档 SHA-256，要求精确等于：Acceptance `6457b896…`、Implementation `5389756…`、Readiness `4d1e5a52…`、Systemd Plan `5655958e…`；逐份验证独立报告精确绑定该完整 SHA 且为 `0 blocker／0 major`。任一不等即停止。
3. 要求真实 index path 数为 0，tracked WIP 集合精确等于四个目标路径；任一额外 tracked WIP、已暂存路径或缺失路径均停止。
4. 对四文档执行 worktree `git diff --check`；失败即停止。
5. 仅执行精确四路径 staging：`git add -- docs/agents/anthropic-responses-bridge/acceptance.md docs/agents/anthropic-responses-bridge/implementation.md docs/agents/service-cutover/readiness.md docs/agents/systemd-runtime/plan.md`。禁止使用目录级、通配符、`.`、`-A` 或 `-u`。
6. 暂存后要求 staged path 集合精确等于上述四路径，数量严格为 4；明确断言无 `docs/tmp`、verification、代码或其他文档。执行 staged `git diff --cached --check`，失败即恢复本轮精确 staging并停止。
7. 执行仅含四路径的 commit dry-run，确认 prospective commit仍严格为四文档；随后才可形成单一 docs checkpoint commit。Commit 完成后重新核对提交路径集合、工作树剩余项与 index 为空。
8. 该 checkpoint 只放行 Implementation／Readiness／Systemd Plan 既定的后续逐片回放与 living 更新；任何代码回放仍须执行其自身 identity、preimage、main-side gate与归档门，不得把本提交外推为产品、部署或 cutover证据。

## 主观建议

无。

## 结构怪味与方案反思

- **结构怪味扫描**：四份 living docs 的 checkpoint 门依赖“内容 SHA → 独立 report → verdict”，但三个文档已有 current 证书，Implementation 则停在“新 bytes 已写、旧 report仍为1 major”的中间态。处置：本轮不修文档、不暂存，只记录 blocker并要求补齐独立 current-byte review；不允许集合审计自己兼任缺失的文档评审。
- **内部替代方案**：直接复用 R7、由本集合审计顺手给 Implementation 判 `0 major`，或只凭现文看似关闭 finding放行，都破坏独立评审边界；没有更可靠的内部替代方案。
- **判据判别力**：临时 index 演练证明 pathset与diff-check能区分夹带／格式错误，却不能区分内容是否已独立评审；current-hash review绑定正是补足这一判别维度。两类门必须同时成立，不能互相替代。
- **成熟第三方方案**：本轮是 Git checkpoint与文档证据链审计，不存在应由第三方库替代的实现机制；Git原生临时 index、pathspec与diff-check已足够且未污染真实 index。

## 结论

当前四份 living docs 的 Git边界满足：index为空、tracked WIP恰四文件、精确四路径 prospective staging不夹带`docs/tmp`／verification、worktree与staged diff-check通过，且四个 current hash在双读间稳定。但内容门只闭合三份；Implementation `5389756…` 缺少精确绑定的独立`0 blocker／0 major`报告，最新R7仍只覆盖旧SHA且为1 major。因此本轮为 **1 blocker／0 major／0 minor**，真实 index保持为空，**当前不可暂存或提交**。补齐Implementation current-byte `0 major`复评后，重新执行本报告的条件式门；全部保持成立时，四文档checkpoint才获得可执行提交放行。
