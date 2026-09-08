# HTTP 499 detail placement 独立评审报告

- report_id: `http499-detail-placement-review-general-sonnet-260904`
- attempt_id: `http499-detail-placement-sonnet-1`
- reviewed_at: `2026-09-04T07:13:33+08:00`

## 评审范围

本轮只读评审主树 `/home/xp/src/ghc-api-proxy-py` 的 HTTP 499 详细解释 placement、文档权威归属及状态闭包。覆盖核查清单 C1-C7、五项固定输入、HTTP 499 implementation/test transcription seam、五份历史 review originals，以及 2026-09-04 `update docs to make HTTP 499 retryable` requirement commit。

明确不重新评审 HTTP 499 生产功能，不评审 local／remote `dotdev` branch shape，不查询真实 upstream，不运行测试、全量回归、Ruff、Pyright 或 canary，也不修改、暂存、提交、清理或推送任何路径。

## 总体 verdict

`pass`

C1-C7 全部通过。未发现 blocker、major、minor 或达到报告门槛的 nit。放行主会话把本轮 `.dev` 更新及本报告追加到 local `dotdev`；这不代表 `origin/dotdev` 已发布，也不关闭仍 open 的 storage finding。

## blocker 数

`0`

## 输入身份与 reviewed hashes

当前主树 `HEAD` 指向 requirement commit `2b7340916d0b1f93123901702953acc9301ec484`，提交主题为 `update docs to make HTTP 499 retryable`。该提交中的目标 Spec SHA-256 与当前主树文件及 checklist 固定值均为 `fa740133a25163de9647632ade08c0fc8694f0eef33cb2771a4dfdfe3394006d`。

| 输入 | SHA-256 | 结果 |
|---|---|---|
| `docs/.human-controlled/upstream-retry-and-continuation.md` | `fa740133a25163de9647632ade08c0fc8694f0eef33cb2771a4dfdfe3394006d` | 与固定值一致 |
| `.dev/docs/upstream/retry-and-continuation/http-499-retry.md` | `ad18600fd3b928b874ff8975feaa6ab886e884c831226467a7dbf04cc99c6ae4` | 与固定值一致 |
| `.dev/human-controlled-docs-candidates/260904-http-499-retry.md` | `e556fac8ffa13ada2138331d1117fe2d71adae67e011f299637b62c02c2187c5` | 与固定值一致 |
| `.dev/docs/upstream/retry-and-continuation/status.md` | `5d5c2e2066a527abb1d4bcffe7e73359718054a3be419afbae88b737641d0618` | 与固定值一致 |
| `.dev/docs/upstream/retry-and-continuation/review-disposition.md` | `a2126bda3a8741e37e043a9def346bdfa631cd041cad4cadc106ea43e61c6664` | 与固定值一致 |
| `src/app/model_provider/ghc_client/errors.py` | `5c4562b301dd8744cce87ebf9727536e1c89b7f8f8219c7d7337d0f033e6632a` | 与此前评审版本一致 |
| `tests/unit/model_provider/ghc_client/test_http_499_retry.py` | `3c192008f3005d1f54c19b6224cfcc9008835bf9b24d34c65e230e6f30b99d59` | 与此前评审版本一致 |

历史 review originals 的当前 SHA-256 也逐项匹配 `review-disposition.md` 固定的 revision：

| Review original | SHA-256 |
|---|---|
| `reports/260904-http-499-review-general-opus.md` | `2d8b692cf2a9cfa0157918bb4597ad21a6878fceff1d10fcdf863e6d96aa3e04` |
| `reports/260904-http-499-rereview-general-opus.md` | `1baa597f05755121579e46442a007f343ecadbff53ca2a68a8f592788a7953ec` |
| `reports/260904-http-499-closeout-review-general-sonnet.md` | `b6f7a1c0b017839a386a6b0ec8600102b657a73d86e03af445151cc061cbaa59` |
| `reports/260904-http-499-user-ruling-integration-review-general-opus.md` | `268f9f977f46ffdf834ef844e4d3c5fe9d09757e1b7e29d030120f3e5d122259` |
| `reports/260904-http-499-user-ruling-integration-rereview-general-opus.md` | `2d412ef76d1ea99566799f2046404288b461c018fa7df9fb4d72b5897c39b25f` |

## C1-C7 逐项核验

| ID | 裁定 | 证据与结论 |
|---|---|---|
| C1 | **PASS** | 目标 Spec 的最终 commit diff只增加 `- 499 Client Closed Request` 一行。HTTP 499 新增内容中没有残留 `serverError` mapping、两级预算、deadline／draining、error envelope、capture、observability、生产证据或未采用方案。文档中原本存在的通用 retry、429、graceful shutdown 与 continuation 条款不属于这次被迁出的 HTTP 499 详细解释。 |
| C2 | **PASS** | `http-499-retry.md` 保全了生产观测、结论强度、normalization boundary、`serverError` mapping、两级预算、deadline／draining、错误呈现、capture、observability、四项专项测试及未采用方案。其“文档边界”明确规定 requirement authority 是用户控制 Spec 中的精简 499 条目，本文件只是 implementation/specification understanding，不把派生策略归为用户裁决。当前 `RETRYABLE_STATUSES` 仍含 499，源码与专项测试哈希也与此前已评审版本一致，未发现与实现、测试或精简 Spec 的冲突。 |
| C3 | **PASS** | candidate 已变为 `status: adopted-in-concise-form` 的处置记录。它分别记录了用户要求支持 499、授权先转录后审核、最终接受精简 requirement 并迁出详细解释这三步过程；需求层唯一采纳内容就是 `499 Client Closed Request`。它还说明详细解释迁入 implementation notes 而非被删除，并有界记录 `origin/dotdev` 选择只覆盖创建及首次 push `dotdev`，不扩张为 `main` 或其它 ref 的发布授权。 |
| C4 | **PASS** | `status.md` 已记录用户审核完成、requirement commit 和精简 placement，不再要求用户重复审核。它明确写明 Spec finding 已关闭；storage finding 只有在远端 ref 建立且精确文件集可恢复后才可 fixed，当前仍路由给带凭据的执行阶段。此次 placement 调整没有误关 storage finding。 |
| C5 | **PASS** | `review-disposition.md` 对 closeout Spec major 保留了原事实、severity、用户逐字 ruling、placement action、`fix: adopted`、`outcome: fixed` 和 `next_actor: none`。storage major 仍为 `fix: open`、`next_actor: user-credentialed-shell`。汇总 `open=1`、`fixed=11` 正确：12 个已登记 findings 中，只有 storage major open；`disputed=0`、`rejected=0`、`deferred=0`。 |
| C6 | **PASS** | 权威分工清楚：用户控制 Spec 是 requirement authority；`http-499-retry.md` 是实现理解 authority；`status.md` 是当前实现与执行状态的 contextual restatement；`review-disposition.md` 是 finding 终态 authority；candidate 已成为静态处置记录，不再充当待采纳 requirement source。status 顶部显式链接 requirement、implementation notes 和 candidate disposition，正文也把详细说明指回 implementation notes，没有形成两个可独立修改的 requirement authority。五份历史 review originals 的 hashes 与 disposition 固定 revision 一致，而且正文仍保留各自当时的状态和 findings，没有被改写成当前终态。 |
| C7 | **PASS** | requirement commit 的实际 diff只加入精简 499 列表项；当前 `RETRYABLE_STATUSES` 明确含 499，专项测试文件仍是此前已评审的四路径版本。主会话提供了该提交后重新核对 transcription 并运行专项 4 tests 全绿的证据；本 reviewer 没有冒充执行者。该组合足以支持“精简 requirement 与当前实现 transcription 一致”，但只覆盖 HTTP 499 专项 seam，不支持声称全量回归、Ruff、Pyright 或真实 upstream canary 已在本轮重跑。 |

## Findings

未发现达到 finding 门槛的问题，因此本轮没有分配 `finding_id`，也没有需要填写 `severity`、`location`、`failure scenario` 或 `suggestion` 的条目。这不是字段遗漏，而是 finding 总数为零。

## 承重前提与结论强度

- 前提：checklist 中五项 SHA-256 精确标识本轮目标字节。它支撑 C1-C6；若任一不一致，本报告应停止采用并重新评审。五项均由本 reviewer 重新计算并逐项匹配，因此结论强度为“足够据此行动”。
- 前提：主会话提供的专项 4 tests 绿灯来自 requirement commit 之后的主树。它支撑 C7 的运行证据部分；若该 provenance 不成立，C7 应收窄为“静态 transcription 与此前测试版本一致，当前运行结果未核”。本 reviewer 独立确认了 current main、源码 hash、测试 hash及 requirement commit diff，但没有重复执行测试。
- 前提：storage finding 当前尚未通过 remote publication 闭合。它支撑 C4-C5 中“仍 open”的状态判断；本轮核验的是 living docs 与 disposition 没有误关该项，不是对 `origin/dotdev` 实际远端状态的独立 branch audit。

## 搜索面与未覆盖面

完整读取了：

- `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-detail-placement-review-checklist.md`
- `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/http-499-retry.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md`
- `/home/xp/src/ghc-api-proxy-py/.dev/README.md`
- 五份历史 review originals及前两轮 checklist。

生产面只核验了 `RETRYABLE_STATUSES`、HTTP 499 专项测试 seam、相关文件 hashes及此前评审所固定的调用链结论。未运行测试、全量检查、真实 Copilot request、远端查询或 `dotdev` branch-shape 检查。

## Local dotdev 放行结论

本轮为 `0 blocker / 0 major / 0 minor`，明确放行把本轮 placement 更新、checklist 和本报告按 exact-path 追加到 local `dotdev`。该放行只表示这些 `.dev` 字节通过 placement review：

- 不表示 `origin/dotdev` 已经存在或可恢复。
- 不把 storage finding 改为 fixed。
- 不授权把目标 Spec复制进 `dotdev`。
- 不替代既有 publication scope或 push 后的 remote OID复核。

## 我最没把握的三个判断

1. **C1 对“没有残留详细解释”的范围解释。** 我将它限定为此次 HTTP 499 新增内容，而没有把目标 Spec 原有的通用 retry、429、draining 和 continuation 条款误判成 499 placement 残留。requirement commit diff只新增一行，是这一判断的强依据；若用户原意是要从整个文档移除所有通用机制说明，那将是更宽的新要求，不是本次 placement 修订。
2. **C6 对 status contextual restatement 的放行。** `status.md` 确实重复概括了 normalization、budget、envelope、capture 与 observability，但它显式链接 requirement authority 和 implementation notes，并把自己限定为当前实现／执行状态，因此我判定这是带 provenance 的 contextual restatement，而不是第二个 requirement source。若后续删掉这些 authority 指针或开始在 status 中独立修改行为规则，该判断应立即重开。
3. **C7 采用主会话测试证据而不自行复跑。** 源码与测试 hashes、main commit 和 requirement diff由我独立核验；“4 tests 全绿”按调用方明确提供的执行事实采用。这个组合足以裁定当前 placement review，但运行部分不是本 reviewer 的一手命令回执，因此我没有把它外推到更宽的验证面。

## 执行本契约时遇到的摩擦

- `my-agents:as-reviewer` 不在可路由 Skill 列表中。我按用户给定 fallback，在读取任何被评对象前读取了 `/home/xp/.claude/my/my-agents/skills/as-reviewer/SKILL.md`。第一次 Read 因误传空 `pages` 参数被拒绝，随后用合法参数成功；失败发生在接触评审输入之前。
- CodeGraph auto-sync 因锁竞争关闭，并在明确要求排除时仍混入其他 `.claude/worktrees` 的符号。所有承重文档结论都来自目标主树绝对路径；源码 seam 又以目标主树文件 hash和精确 `rg` 命中复核，混入的 worktree 内容没有用于裁定。
- harness 禁止 pinned worktree agent 使用 `git -C` 查询主树。当前 main ref与历史通过主树 `.git/HEAD`、`refs/heads/main` 和 reflog直接只读核验；requirement commit对象通过共享 object database读取。没有检查或采用隔离 worktree 的文件内容，也没有对主树执行任何写入型 Git 操作。
- 作为叶子 reviewer，我无权再派生 reviewer审查本报告。报告正文按用户要求直接交付给主会话持久化；主会话仍需按自己的接收流程核对尾部计数与 fixed hashes。
- 本轮没有创建报告文件，没有修改或清理任何路径，因此 reviewer 侧没有临时产物、分支或 worktree需要处置。

## 收尾判断

本轮已到只读评审交付边界。评审范围、固定输入、C1-C7、finding 计数、未覆盖面和 local `dotdev` 放行边界均已闭合。项目整体尚未 closeout，因为 storage finding 仍 open；本报告只允许 placement 更新进入 local `dotdev`，不发出远端持久化已经完成的信号。

## 交付声明

- delivery_complete: true
- completed_at: `2026-09-04T07:13:33+08:00`
- finding_total: 0
- blocker: 0
- major: 0
- minor: 0
- nit: 0
- criteria_passed: 7
- criteria_failed: 0
- local_dotdev_append_allowed: true
- storage_finding_closed: false
- tests_executed_by_reviewer: false
