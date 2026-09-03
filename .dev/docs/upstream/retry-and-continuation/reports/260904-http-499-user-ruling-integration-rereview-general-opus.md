# HTTP 499 用户裁决整合限定复评

- report_id: `http499-user-ruling-integration-rereview-general-opus-260904`
- attempt_id: `http499-user-ruling-rereview-opus-1`
- source_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-user-ruling-integration-review-general-opus.md`
- source_report_sha256: `268f9f977f46ffdf834ef844e4d3c5fe9d09757e1b7e29d030120f3e5d122259`
- reviewed_at: `2026-09-04`

## 复评范围

本轮只复核 source report 的两个 findings、整改后的 candidate/status/disposition，以及 `/home/xp/.claude/jobs/00409e7f/tmp/dotdev-worktree` 的精确文件集合和 unborn/index 状态。不重开 C1–C8，不重新评审 HTTP 499 功能、目标 Spec、workflow、`.gitignore` 或生产源码。

## 总体 verdict

`pass`

两个原 findings 均已 fixed，未发现 not-fixed 或 regressed。新增 1 项不阻断 commit/push 的 status minor；当前为 0 blocker、0 major。

## 输入哈希

以下主树输入均已独立重算，并与 coordinator 提供的完整哈希一致：

| 输入 | SHA-256 |
|---|---|
| `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md` | `cef0635de0b193ba21275498fcb9081c7267a5a93fb054a36cf45e7a26daa969` |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md` | `e656fd58b9e1b5c06459c51026e41ec4450bcd479c0700d5956bdc2e6b6bfa32` |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md` | `05701d8dea2c8f9c6e5bca9819d77542de9eaecce5a40f38ec11fe6d9a37f571` |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-user-ruling-integration-review-checklist.md` | `240046e75e9d25dfc0ba71af06f6d8b0f38bc642a5e55f05b9eef81b5f8e96fc` |
| `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-user-ruling-integration-review-general-opus.md` | `268f9f977f46ffdf834ef844e4d3c5fe9d09757e1b7e29d030120f3e5d122259` |

这五项在 dotdev worktree 中的对应文件与主树逐文件等哈希。

## 原 findings outcomes

| 原 finding | outcome | 复评结论 |
|---|---|---|
| `http499-user-ruling-integration-review-general-opus-260904-01` | **fixed** | candidate 已有界记录两项用户裁决；status 不再把两项写成待用户裁决；disposition 已准确区分 Spec 待用户审核与 storage 执行中，并保持两条 closeout major open。 |
| `http499-user-ruling-integration-review-general-opus-260904-02` | **fixed** | integration checklist/report 已进入 dotdev，整改后的 candidate/status/disposition 也已逐路径同步；当前 worktree 恰有 10 个 `.dev` 普通文件，没有额外会话文件。 |

- fixed: 2
- not_fixed: 0
- regressed: 0

### F01：用户裁决与执行路由

`fixed`。

- candidate 第 10 行仍准确说明“直接并入但不提交”不是最终审核通过，也不授权提交目标 Spec。
- candidate 第 11 行已记录用户选择“专用的 `origin/dotdev` 分支”，明确只授权创建并首次 push `dotdev`，不授权 push `main`、目标 Spec或其他 ref，并把 storage procedure authority 指向 `.dev/README.md`。
- status 第 32–45 行不再要求用户重新裁决。它准确说明 Spec 已转录、未 staged/committed、等待用户审核；dotdev 已进入 coordinator 执行阶段。
- disposition 中 Spec decision 为 `user-selected-pending-review`，`next_actor: user-reviewer`，对应 finding 仍为 `fix: open`。
- disposition 中 storage decision 为 `user-selected-execution-in-progress`，`next_actor: coordinator`，对应 finding 仍为 `fix: open`。
- 两个 integration findings 当前仍 `fix: open` 并路由给 original reviewer，是等待本限定复评结果的正确复评前状态，不构成整改未完成。本报告接收后可将它们登记为 fixed。

没有提前把 Spec 用户审核或尚未发生的 remote publication写成完成，也没有扩大用户授权。

### F02：dotdev 精确文件集合

`fixed`。

dotdev worktree 当前恰有以下 10 个普通文件，`symlink=0`、其他文件类型为 0：

| 路径 | SHA-256 |
|---|---|
| `.dev/README.md` | `faf6c97de7e82e0ee9b0474d24c76f68d29717496c752eb6b766ddafe72601c0` |
| `.dev/human-controlled-docs-candidates/260904-http-499-retry.md` | `cef0635de0b193ba21275498fcb9081c7267a5a93fb054a36cf45e7a26daa969` |
| `.dev/docs/upstream/retry-and-continuation/status.md` | `e656fd58b9e1b5c06459c51026e41ec4450bcd479c0700d5956bdc2e6b6bfa32` |
| `.dev/docs/upstream/retry-and-continuation/review-disposition.md` | `05701d8dea2c8f9c6e5bca9819d77542de9eaecce5a40f38ec11fe6d9a37f571` |
| `.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-review-checklist.md` | `6356e7bbfdea958610fbc23dcfd3f944c18e210c6fc481f38ee4d367b5398725` |
| `.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-review-general-opus.md` | `2d8b692cf2a9cfa0157918bb4597ad21a6878fceff1d10fcdf863e6d96aa3e04` |
| `.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-rereview-general-opus.md` | `1baa597f05755121579e46442a007f343ecadbff53ca2a68a8f592788a7953ec` |
| `.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-closeout-review-general-sonnet.md` | `b6f7a1c0b017839a386a6b0ec8600102b657a73d86e03af445151cc061cbaa59` |
| `.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-user-ruling-integration-review-checklist.md` | `240046e75e9d25dfc0ba71af06f6d8b0f38bc642a5e55f05b9eef81b5f8e96fc` |
| `.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-user-ruling-integration-review-general-opus.md` | `268f9f977f46ffdf834ef844e4d3c5fe9d09757e1b7e29d030120f3e5d122259` |

worktree metadata仍为：

- `HEAD`: `ref: refs/heads/dotdev`
- local `refs/heads/dotdev`: 不存在
- index version: 2
- index entries: 0

因此 branch 仍是尚未 staged/committed 的 unborn orphan，当前精确集合没有主代码、stream-accounting、timeout-408 或其他会话 `.dev` WIP。

## 新 findings

### http499-user-ruling-integration-rereview-general-opus-260904-01：status 仍把已经补齐的两份评审件写成待补齐

- finding_id: `http499-user-ruling-integration-rereview-general-opus-260904-01`
- severity: `minor`
- location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md:42-45`
- related_location: `/home/xp/.claude/jobs/00409e7f/tmp/dotdev-worktree/.dev/docs/upstream/retry-and-continuation/reports/`
- evidence: status 第 45 行仍写 dotdev“等待补齐该轮 checklist/report”，但当前精确枚举已经确认 integration checklist 和 integration report 均存在于 dotdev，且分别与主树等哈希。等待 exact commit/first push 仍然属实，等待补齐两份文件则已经过时。
- failure scenario: 若当前 status 随 root commit进入 `origin/dotdev`，后继执行者会在实际文件集已经完整时仍把 storage finding理解成缺文件，可能重复执行 copy/hash 步骤或错误地延后对首次 push 结果的处置。
- suggestion: 将第 45 行收窄为“两份 integration 评审件已补齐并等哈希，等待 exact-path commit 与首次 push”。这项状态措辞不改变已验证文件集合、branch shape 或 publication authorization，因此不阻断本轮 local root commit与首次 push；可以在提交前修正，或最迟在首次 push 后回写 storage outcome时一并修正。

## disposition 核验与下一状态

当前 disposition 的两条用户 decision 与 coordinator 指定值逐字一致：

- Spec：`decision_status: user-selected-pending-review`，`next_actor: user-reviewer`，原 closeout finding 保持 `fix: open`。
- Storage：`decision_status: user-selected-execution-in-progress`，`next_actor: coordinator`，原 closeout finding 保持 `fix: open`。

living status 已不再说“两项待用户裁决”。

本报告被处置后，两个原 integration findings 应从 `open` 转为 `fixed`。在尚未处理新增 minor 时，汇总应为 `open=3`、`fixed=9`；若同步修正 status 并登记该 minor fixed，则为 `open=2`、`fixed=10`。其中两项承重 open 必须仍是：

1. Spec 用户审核。
2. Storage 首次 push及 remote ref 可恢复性确认。

首次 push成功后可以关闭 storage finding；Spec finding 在用户真正审核前必须继续 open。

## commit 与 publication 放行结论

本轮为 0 blocker、0 major，明确放行：

- 使用精确 pathspec在 local `dotdev` 创建 root commit。
- 首次 push仅执行 `dotdev:dotdev`，以创建 `origin/dotdev`。
- 不得 push `main`、目标 Spec或其他 ref。
- 不得 stage 或 commit `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md`。

当前 10 文件可以作为精确 root-commit 输入。本限定复评由主会话持久化后，也应按 exact-path 同步进 dotdev；可以把它作为同一 root commit的第 11 个文件，或在首次 push前追加一个仅含本报告的 local commit。该交付后同步步骤不重开 F02，也不要求重新全量评审。

新增 status minor不否定该放行：它错误描述的是一个已经完成的预发布子步骤，实际文件集合本身已经通过独立枚举与哈希核验。

## 搜索面与未覆盖面

本轮重读了 source report全文，并完整读取整改后的 candidate、status、disposition和 integration checklist。对 dotdev worktree进行完整普通文件枚举、类型检查和逐文件 SHA-256 核验，并读取 worktree Git metadata确认 unborn branch与空 index。

本轮没有读取或复评 HTTP 499 生产源码、目标 Spec、workflow、`.gitignore` 或三轮更早评审正文，也没有运行 Ruff、Pyright、pytest、真实 Copilot request或远端 `ls-remote`。因此本报告只支持两个原 findings 的整改 outcome、当前 dotdev local pre-publication shape及其 publication放行，不重新背书 source report中 C1–C8 的其他裁定，也不声称 remote ref已经创建。

## 我最没把握的三个判断

1. 新 status 问题定为 minor、而不是把 F02 改判 not-fixed，置信度中等偏高。原 F02 的失败谓词是 checklist/report 不在拟发布集合；两个文件现在确实存在且等哈希，所以原 finding 已 fixed。当前问题只是 living status没有追上这一状态转变，失败机制不同，应单列。
2. 新 minor不阻断首次 push的置信度高。它不改变待提交文件的字节身份、完整性、branch parentage或用户 publication scope；即使原样进入首个 snapshot，恢复所需文件仍然齐全。它会误导后继路由，但不会使 durable source失效。
3. 本限定复评报告应在首次 push前追加到 dotdev的判断置信度中等。这样能避免再次产生“放行报告只在 ignored active copy中”的同类缺口；但报告只能在本轮交付后出现，因此它属于主会话明确承担的交付后同步，而不是当前 10 文件核验失败。

## 执行本契约时遇到的摩擦

- 本轮收到 course correction时，初评报告已在主树持久化；我按要求先完整重读该报告，再读取整改对象，没有沿用对旧字节的记忆。
- pinned reviewer worktree仍不允许对目标 dotdev worktree运行 Git CLI。unborn ref、index entry count及文件集合通过只读 Git metadata和文件系统探针核验，没有修改或绕过目标 worktree。
- coordinator 最初给出的是省略中段的哈希表示；本轮直接重算得到完整 SHA-256，并与其前后缀及 dotdev对应文件逐项吻合。
- 本轮未修改、暂存、提交、切换、清理、删除或 push任何路径或 ref。

## 收尾判断

本限定复评已完成其两个 outcome和当前系统状态两问。后续持久化本报告、更新 disposition、可选修正 status、创建 root commit、首次 push及 remote ref复核均属于 coordinator 的执行阶段；reviewer没有需要清理或归档的本地可变产物。

## 交付声明

- delivery_complete: true
- completed_at: `2026-09-04T06:52:05+08:00`
- original_outcome_total: 2
- fixed: 2
- not_fixed: 0
- regressed: 0
- new_finding_total: 1
- finding_total: 1
- blocker: 0
- major: 0
- minor: 1
- nit: 0
