# HTTP 499 用户裁决整合与 dotdev 分支设计独立评审

- report_id: `http499-user-ruling-integration-review-general-opus-260904`
- attempt_id: `http499-user-ruling-opus-1`
- reviewed_at_rev:
  - `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md`: `08deb933b57dca134003cae530790f99bdc4de03b08b9b8ff7d94447a84cc29d`
  - `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md`: `02ac4c77fec44c046492005eb06e487bf0e66ad822e5dd01c0c6797fcdf8973b`
  - `/home/xp/src/ghc-api-proxy-py/.gitignore`: `64f3333b0414c16c90c40f35749aec9e05ea1bf9bcd0c9a8bae730115acd42b1`
  - `/home/xp/src/ghc-api-proxy-py/.dev/README.md`: `faf6c97de7e82e0ee9b0474d24c76f68d29717496c752eb6b766ddafe72601c0`
  - `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md`: `b17767dbf01dab2d2728342f1ce6b65326dbad6b1d1bc9c330ed5f861af64bde`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md`: `cc4c7e1e6e74ee8fc36672e105f7ec8071f0b7750ee4b825a94d175f44205e86`
  - `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md`: `f6c95ad39d848d981e5a136ae35dcbb10a59d95a3da23af8bd9d05d06edd0758`
- reviewed_at: `2026-09-04`

## 评审范围

本轮核验主树 `/home/xp/src/ghc-api-proxy-py` 中的目标 Spec、workflow rule、`.gitignore`、`.dev/README.md`、candidate、status、disposition、三轮既有评审及两份 checklist，并核验 `/home/xp/.claude/jobs/00409e7f/tmp/dotdev-worktree` 的完整文件集合、内容哈希、unborn branch 与 index 状态。生产源码只检查 HTTP 499 Spec 转录所需的 `RETRYABLE_STATUSES`、normalization/classification 和专项测试 seam，不重新评审已经完成的 499 功能实现。

## 总体 verdict

`needs-fix`

## blocker 数

0。输入身份和评审范围完整；当前否决来自 1 项 major 的 living-document 状态闭包缺陷，不是工具或权限阻塞。

## 固定输入与分支身份核验

固定输入的 7 个 SHA-256 均与 coordinator checklist 逐项一致。

目标 Spec 当前内容的 SHA-256 为 `08deb933...`，而 main 当前提交 `39274d7bc3601f2236ffdfc52ea6f34f885ba405` 中同一路径的 SHA-256 为 `47af4ebab4b7e3b798b1287cede7c68f6fd0acf17173369b3dccbe336cfacf91`。main index 中该路径的 stage-0 blob 为 `088fef878f70dd639b866fe15b07ef61bf442d16`，当前工作树 blob 为 `b7d9b970a5ae36f0da1ffb368e75b8111abd488b`。因此完整转录既未进入 index，也未进入当前 main commit，C2 所要求的“未 staged、未 committed”成立。

dotdev worktree 的 `HEAD` 为 `ref: refs/heads/dotdev`，共同仓库中不存在该 local ref，index version 2 且 entry count 为 0。因而它确实是尚无 commit 的 unborn branch；首次提交会形成无 parent 的 root commit，而不是继承 main 历史。

dotdev worktree 当前恰有 8 个 `.dev` 文件，未发现主代码文件、stream-accounting、timeout-408 或其他会话文档。8 个文件的 SHA-256 均与主树对应文件一致：

- `.dev/README.md`: `faf6c97de7e82e0ee9b0474d24c76f68d29717496c752eb6b766ddafe72601c0`
- candidate: `b17767dbf01dab2d2728342f1ce6b65326dbad6b1d1bc9c330ed5f861af64bde`
- status: `cc4c7e1e6e74ee8fc36672e105f7ec8071f0b7750ee4b825a94d175f44205e86`
- disposition: `f6c95ad39d848d981e5a136ae35dcbb10a59d95a3da23af8bd9d05d06edd0758`
- initial checklist: `6356e7bbfdea958610fbc23dcfd3f944c18e210c6fc481f38ee4d367b5398725`
- initial review: `2d8b692cf2a9cfa0157918bb4597ad21a6878fceff1d10fcdf863e6d96aa3e04`
- limited rereview: `1baa597f05755121579e46442a007f343ecadbff53ca2a68a8f592788a7953ec`
- closeout review: `b6f7a1c0b017839a386a6b0ec8600102b657a73d86e03af445151cc061cbaa59`

## C1–C8 逐项裁定

| ID | 裁定 | 核验结论 |
|---|---|---|
| C1 | **PASS** | Spec 第 18、23–29、77 行完整承载 candidate 的 retry classification、`serverError` 与共享两级预算、draining/deadline、final error envelope、rejected capture、attempt observability、transcription authority 和修订记录。candidate 的“决策来源与强度”“修订依据”“未采用方案”等过程材料没有误入 Spec。candidate 中“一旦并入”的条件语在已转录的目标 Spec 中去掉，不改变稳定态语义。 |
| C2 | **PASS** | 当前转录内容同时不同于 main index 和 main HEAD 中该路径的内容，完整转录仍只存在于工作树。后续 main 侧任何 local commit 都必须继续用精确 pathspec 排除该 Spec，直到用户审核。 |
| C3 | **FAIL** | candidate 正确记录“直接并入但不提交、仍待用户审核”的 scope，没有冒充最终批准；但它没有记录本轮第二项 `origin/dotdev` 选择。该选择目前只出现在 `.dev/README.md`，而 status 与 disposition 仍把两项都写成尚待用户裁决。严格按 C3 的文件归属和“两项裁决”量词，当前状态不成立，详见 finding 01。 |
| C4 | **PASS** | workflow rule 负责项目级布局约束，`.dev/README.md` 负责 active copy、durable snapshot、exact-path synchronization、禁止 bulk-copy、commit/push 和 recovery 操作，`.gitignore` 只负责把 `.dev/` 排除在 main 外。三者的稳定态设计一致，没有第二个内容 authority，也不存在“必须先读一个尚不可发现文档才能找到 branch”的循环：main 上的 workflow 已直接给出 `origin/dotdev` 和 dedicated worktree 的 bootstrap 路径。 |
| C5 | **PASS** | 以 checklist 创建前为截止点，8 个计划路径完整且逐文件等哈希；unborn、空 index 的 `dotdev` 会产生仅含 `.dev/` 的 root tree。orphan branch 与 main 的 ignored active copy 分离，既保留 Git durability，也避免把 `.dev` 合入 main，是适合该约定的长期 storage shape。checklist 创建后的新增文件另见 finding 02。 |
| C6 | **PASS** | 用户明确选择的是带 remote 名称的“专用 `origin/dotdev` 分支”。创建 local `dotdev` root commit 并 push 以创建该 remote branch，是使该选项成立所必需且被当前选择覆盖的发布动作；授权范围仅为 `dotdev`。它不授权 push `main`、提交或 push 未审核 Spec，也不授权发布其他 ref。 |
| C7 | **PASS** | workflow 已删除 nested separate repository 说法，改为 main ignored active copy加 orphan `origin/dotdev` durable source；这与 `.gitignore` 和 README 一致。项目根 `/home/xp/src/ghc-api-proxy-py/CLAUDE.md` 只规定 `.dev` 文档和 candidate 的路径职责，没有必须保留的旧存储机制。 |
| C8 | **FAIL** | 两条 closeout major 当前形式上仍是 `open=2`，但 disposition 仍将它们标为 `pending-user-ruling`，status 仍说“两项等待用户裁决”。这没有记录用户已经给出的执行路径，也没有表达“Spec 已转录但待审核”和“dotdev 已创建但未提交、未发布”两个真实状态。最终正确状态应是在 dotdev 成功 push 并回写证据后关闭 storage major，而 Spec major 在用户真正审核前继续 open，即 `open=1`，详见 finding 01。 |

## Findings

### http499-user-ruling-integration-review-general-opus-260904-01：两项用户裁决尚未闭合到 living status 与 disposition

- finding_id: `http499-user-ruling-integration-review-general-opus-260904-01`
- severity: `major`
- location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md:32-43`
- related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md:125-173,217-226`；`/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:7-11`；`/home/xp/src/ghc-api-proxy-py/.dev/README.md:3-16`
- evidence: candidate 已正确把 Spec 裁决写成“已转录、未提交、待用户审核”，README 也明确记录用户选择 `origin/dotdev`。但 status 仍断言 Spec 尚未由 agent 修改，并把两项列为等待用户裁决；disposition 仍将两项 decision 标为 `pending-user-ruling`、`next_actor: user`。此外，candidate 的 provenance 没有记录第二项 dotdev 裁决，因而 C3 要求的两项 scope 也没有在指定载体内闭合。
- failure scenario: 如果当前 8 文件直接成为 `origin/dotdev` 的首个 durable snapshot，后继会话会从 living status 与 disposition 得出“还要再次询问用户两项选择”的错误路由；反方向上，也可能因为 Spec 已被转录便把第一条 major 提前标成 fixed，跳过用户明确保留的审核步骤。即使 branch 已成功 push，处置账仍会显示 storage 决策尚未作出，导致 open 数量和 next actor 同实际状态冲突。
- suggestion: 在首次发布前同步更新三个 living artifact。candidate 的过程/provenance 部分应以有界表述记录 dotdev 选择，并指向 `.dev/README.md` 作为 storage procedure authority，不把它抄入目标 Spec；status 应记录“Spec 已转录、未 staged/committed、待用户审核”和“dotdev unborn、未提交、未发布”；disposition 应把两项 decision 改为已由用户裁决，同时保持 finding 的 `fix: open`。Spec finding 的 next actor 为 user reviewer；storage finding 的 next actor 为 coordinator。成功 push 并读取 remote ref 作为完成证据后，关闭 storage finding，但继续保留 Spec finding open，最终应为 `open=1`。不要覆写三轮 point-in-time review originals。

### http499-user-ruling-integration-review-general-opus-260904-02：拟发布集合尚未纳入本轮 integration checklist 与最终评审报告

- finding_id: `http499-user-ruling-integration-review-general-opus-260904-02`
- severity: `minor`
- location: `/home/xp/.claude/jobs/00409e7f/tmp/dotdev-worktree/.dev/docs/upstream/retry-and-continuation/reports/`
- related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-user-ruling-integration-review-checklist.md`；拟持久化的 `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-user-ruling-integration-review-general-opus.md`
- evidence: 当前 dotdev worktree 的 8 文件准确覆盖 integration checklist 创建前的材料，但不含已经存在于主树的 integration checklist；本报告因交付时才产生，当前也不可能已在其中。README 的 exact-owned-path 规则足以要求后续复制，但当前拟提交集合尚未执行这一步。
- failure scenario: 如果按当前 8 文件直接完成首次 push，随后 main 的 ignored `.dev` 丢失，`origin/dotdev` 可以恢复旧的三轮评审，却不能恢复决定本次用户裁决整合和 branch 发布是否可放行的 checklist 与最终报告。durable snapshot 因而缺少其自身最后一轮审查依据。
- suggestion: 主会话持久化本报告后，把 integration checklist 与本报告作为两个新增、精确路径复制到 dotdev worktree并逐文件比对哈希。若只剩本 minor，允许先对当前 8 文件创建 local root commit，再以第二个 local commit加入这两份材料；但首次 push 创建 `origin/dotdev` 应等到两份材料都已进入待发布 branch。不得通过 bulk-copy `.dev/` 补齐。

## 发布与提交结论

当前有 1 项 major，因此本评审不放行把现有 8 文件作为最终状态 commit/push。先修正 candidate、status 与 disposition，并补齐本轮 checklist/report。

完成上述修正后：

- 可以在 local `dotdev` 上以精确 pathspec 创建 root commit，并 push 创建 `origin/dotdev`；该动作在本轮用户选择范围内。
- 不得 push `main` 或其他 ref。
- 目标 Spec `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md` 必须继续保持 unstaged、uncommitted，直到用户审核。
- dotdev 首次 push 成功后，还需要回写 storage finding 的完成证据并再持久化该 living-state 更新；最终 disposition 在用户审核 Spec 前应保持恰好 1 项 open。

## 生产转录 seam

当前主树 `RETRYABLE_STATUSES` 包含 `499`，`normalize_upstream_error()` 只让未列入 retryable set 的一般 4xx 进入 `UpstreamRejected`。专项测试直接断言 499 得到 `UpstreamError(status_code=499)`、`Disposition.RETRY` 和 `RetryReason.SERVER_ERROR`，并覆盖第二次成功、预算耗尽与 498 负控。该必要 seam 与目标 Spec 第 23–29 行相符；本轮没有重新展开完整 driver、deadline 或 error-envelope 功能评审。

## 搜索面与证据边界

我逐项读取并核对了 coordinator checklist、目标 Spec、candidate、workflow rule、`.gitignore`、`.dev/README.md`、status、disposition、初始 checklist 和三轮既有评审。对 dotdev worktree进行了包含 hidden 文件的完整文件枚举，并逐项核对 8 个 `.dev` 文件哈希；直接读取其 worktree Git metadata，确认 unborn `dotdev`、缺失 local ref 和空 index。对 main Spec 直接解析 index entry，并从当前 main commit object读取同一路径内容，以区分 working tree、index 和 HEAD 三个状态。

没有重新运行 Ruff、Pyright、pytest 或真实 Copilot request，因为本轮只要求核对 Spec 转录必要 seam，且生产字节不是本轮变更对象。CodeGraph auto-sync 因锁竞争关闭，但其工具明确从磁盘重读了所示主树源码；混入的其他 worktree 符号没有用作裁定依据。

用户和 checklist 提供的先前 `ls-remote` 空结果被保留为“当时确认 remote branch 不存在”的输入。本轮两次独立重试 `git ls-remote --heads origin refs/heads/dotdev` 均因 `GnuTLS recv error (-110)` 失败，因此我没有把本轮网络调用冒充第二次确认，也没有据此推翻已提供的远端状态。

## 我最没把握的三个判断

1. C3 按 literal scope 判 FAIL 的置信度为中等偏高。把 dotdev 存储选择写进产品 Spec 正文显然错误，但 checklist 明确指定 candidate 的过程/provenance 部分要覆盖“两项用户裁决”；当前它只覆盖 Spec 裁决。最稳妥的修法是在 provenance 中作有界引用，并让 README继续拥有 procedure authority，而不是扩大目标 Spec。
2. C6 判定用户选择足以授权首次 push 的置信度为高。`origin/dotdev` 不是 local-only 选项，选择它若不覆盖创建对应 remote ref便无法执行。但该授权只覆盖实现这次明确选择所需的 dotdev publication，不是今后任意 push 的永久授权，更不覆盖 main。
3. finding 02 定为 minor、并允许分成两个 local commit 的置信度为中等。缺少最后两份审查件不会改变 branch storage 设计或 HTTP 行为，但会使首次 durable snapshot 的审计材料不完整；因此它应在首次 push 前修复，却不必阻止先创建只存在于当前 clone 的 root commit。

## 执行本契约时遇到的摩擦

- `my-agents:as-reviewer` 不在可路由 Skill 列表中，因此按用户指定的 fallback，在读取被评对象前直接读取 `/home/xp/.claude/my/my-agents/skills/as-reviewer/SKILL.md`。第一次 Read 因空 `pages` 参数被拒绝，随后使用合法参数成功；失败发生在读取任何评审输入之前。
- pinned reviewer worktree 的隔离层拒绝对主树和 dotdev worktree运行 Git CLI，即使操作只读。我没有绕过该限制；branch、ref、index 与 Spec stage 状态通过直接读取 Git metadata核验，当前 main commit 中的 Spec 则从 reviewer worktree可访问的同一 object database读取。
- 远端 `ls-remote` 连续两次因 TLS transport error失败。报告明确区分了用户／coordinator 先前已确认的 remote 状态与本轮未完成的独立复查。
- CodeGraph 的冻结索引列出了多个同名 worktree symbol；只采用了工具本次从主树磁盘重读的 source block，并把索引关系降为定位佐证。
- 本轮没有修改、暂存、提交、切换、清理、删除或 push 任何文件、worktree 或 ref。

## 收尾判断

本轮需要交付评审结论，但不适合执行实现侧 closeout：存在 1 项 major 和 1 项 minor，且修复、持久化、commit、push 与用户 Spec 审核均明确属于主会话后续动作；本 reviewer 没有产生需要清理或归档的本地可变产物。报告本身按用户要求直接交付，由主会话持久化。

## 交付声明

- delivery_complete: true
- completed_at: `2026-09-04T06:45:26+08:00`
- finding_total: 2
- blocker: 0
- major: 1
- minor: 1
- nit: 0
