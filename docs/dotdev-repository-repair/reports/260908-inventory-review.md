# `.dev` 文档处置清单独立审阅报告

**评审范围**：`.dev/docs/dotdev-repository-repair/README.md`（2026-09-08 07:42 版本，104 行）的事实完整性与退役计划安全性，限四项：42 主题分类表对照独立证据、退役前迁移清单的遗漏、TUI tmp 26 份清单的归属边界、`.dev` clone/嵌套与全量合并事实。判据来源：评审者对本会话内 42 主题的第一手核查证据（src/ 符号 grep、各主题主文档首读）与本次复核新取的 git/文件系统证据；所有关键断言重新取证，不以被检文档自述或评审者先前结论为准。主文档未做任何修改。

**总体 verdict**：分类表与合并事实**全部核对通过**（无一误判、计数全部对账闭合）；退役计划存在一处**系统性遗漏**——「退役前必须完成的迁移」没有涵盖「被活文档引用的证据迁出与入站引用改写」，按清单字面执行会不可恢复地丢失仍被引用的材料。结构描述有两处次要的不准确。

**blocker 数**：0（major 2、minor 2）。

## 发现

### F-1（major）迁移清单缺「被引证据迁出 + 入站引用改写」，按清单执行会断链甚至毁证

**primary_location**：README.md「退役前必须完成的迁移」一节（6 条均未含引用处理）与「执行顺序」第 2～4 步。
**related_locations**（全部实测在案，均为**保留主题的活文档**指向**退役候选目录或 tmp/**的引用）：

- `direct-passthrough/spec.md:95`、`direct-passthrough/deferred.md:41` → `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md`——承重事实「`claude-sonnet-5` 不支持 Responses API、只能走直连」的证据源。
- `anthropic-direct-request-shape/README.md:22`、`anthropic-direct-request-shape/spec.md:117`、`:428`（证据出处表）→ sync-refs 的 round2-disposition 与 vscode-copilot-chat-reasoning-values 两份。
- `delivery-keepalive/spec.md:5`、`:66`、`:80` → `../empty-text-block/reports/260820-review-synthetic-start-fix.md`——其中 `:80` 用它证明「选 `message_start` 不是用户裁决、至今未裁」，是活性条款的权威状态依据。
- `tui/deferred.md:37` → `../count-tokens/reports/260820-review-count-tokens-shared-pipeline.md:72`。
- `hosted-web-search/status.md:83` → `../hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`。
- `direct-passthrough/spec.md:871`（条款修订记录）→ `../git-housekeeping/reports/` 两份。
- `anthropic-responses-bridge/implementation.md:239` → `../documentation-restructure/README.md`（该行还写着「剩余有效目标继续保留」，正应由本文承接，指针需改指）。

**为什么是 major 而不只是 nit**：其一，执行顺序第 3 步把点时材料从 `<topic>/reports/` 移入 `<topic>/history/`，即使目录不删，上述 `../<topic>/reports/...` 相对链接也已经断了；其二，执行顺序第 2 步允许「无长期证据价值的临时材料删除」，而 tmp/ 中至少 10 份被活文档点名（见 F-2），其中被点名的合并新增文件**尚未提交到 dotdev 仓**（工作树 128 条未提交变更），删了即不可恢复；其三，「执行顺序」第 4 步的「不再含……有效引用」只是退役目录侧的删除门槛，没有指明任何人负责改写入站引用。本文自述「未按本文清单完成迁移前不得删除主题」，清单即合同——清单缺项等于这道闸漏了这一类。

**修正方向**（交调用方裁决）：在迁移清单补一条「逐份清点保留主题活文档对退役候选目录与 tmp/ 的引用；证据迁入被引主题（或本文指定位置）后统一改写入站引用路径，再进入退役」。

### F-2（major）tmp/ 归口未与「被活文档引用」联动，4 份在 26 份 TUI 候选内、6 份在候选外

**primary_location**：README.md「TUI 范围内的临时材料」一节与执行顺序第 2 步。
**related_locations**：

- `upstream/retry-and-continuation/status.md:251`、`:255` → `../../tmp/260822-h2-streamreset-cancel-diagnosis.md`、`../../tmp/260821-plan-g1-upstream-error-events.md`（两份均在 26 份清单内）。
- `upstream/retry-and-continuation/deferred.md:11`、`:21`、`:191`、`:224` → `../../tmp/260822-deferred-md-inventory.md`、`../../tmp/260822-review-session-closeout.md`（在 26 份清单内）、`../../tmp/260822-review-never-silent-failure-events.md`（在 26 份清单内）。`:11` 还明文「清点全文见 `../../tmp/260822-deferred-md-inventory.md`」——编号永不回收的公共接口约定以它为证。
- 候选外被引：`ghe-device-flow/spec.md:155`、`ghe-device-flow/deferred.md:32` → `.dev/docs/tmp/260822-ghc-api-conformance-summary.md`；`graceful-shutdown/restart-handover/README.md:19`、`:190-192` → `260822-pidfile-missing-forensics.md` 及两份 pidfile 评审（4 份）。graceful-shutdown 是保留主题，这 4 份应随 F-1 的引用清点一并归入 `graceful-shutdown/`。

按正文归属，这些材料的正确去处分别是 `upstream/retry-and-continuation/`、`ghe-device-flow/`、`graceful-shutdown/`——都**不是** TUI，但当前只有 TUI 一组获得了逐份处理指令，其余 67 份没有「先查入站引用再定去留」的约束。

### F-3（minor）「`862b137` 已保存嵌套旧树的历史」归因不准

**primary_location**：README.md「已核实的错误结构」第 4 段。
实测：`git -C .dev show --stat 862b137` 仅 1 个文件、52 行新增（`direct-passthrough/reports/260904-completed-client-actions-review-artifact-cleanup.md`）；嵌套旧树的历史由 dotdev 分支自身提交链承载（例：`c3601f6` 触及嵌套路径 `.dev/docs/tui/spec.md`）。安全性质不受影响——`862b137` 是当前 HEAD，祖先链完整，re-root 后历史自然保留——但「该提交保存了嵌套历史」的字面表述会误导后续操作者以为只需保住这一个提交。建议改为「嵌套旧树的历史由 dotdev 分支提交链（至 `862b137` 为止的祖先）承载」。

### F-4（minor）「已核实的错误结构」的现在时描述落后于磁盘现状

**primary_location**：README.md「已核实的错误结构」嵌套树清单。文档以现在时列出嵌套四树 `docs`、`exp`、`human-controlled-docs-candidates`、`tools`；实测 `ls .dev/.dev/` 只剩 `docs`，其余三树已在工作树删除（`git -C .dev status` 共 128 条未提交变更，含 `D .dev/exp/...`、`D .dev/.gitignore`、`D .dev/README.md` 等），且嵌套 exp 的内容已存在于活跃 `.dev/exp/`（如 `260820-streaming-and-timeouts/` 及其 `idle-research`、`pty-footer`、`rev-idle-impl` 子目录）。文档只记载了 docs 的合并，未记载 exp（等）的合并与工作树删除已同步发生——按文档核对现状会得出「嵌套 exp 仍在」的错误结论。另「合并前的本地备份已依用户要求删除」一句无法核实（备份已不存在），记 unverified。

## 核对通过项（含搜索面）

- **分类表**：42 行与 `.dev/docs/` 实际 42 个被审目录一一对应（现盘 43 个含本文档自身目录）；逐行对照评审者独立证据（`src/` 符号 grep 与各主题主文档），无保留/退役/条件退役误判。`tmp` 归「保留为临时交换目录」与项目规则（topic 不明时新报告入 `tmp/`）一致，成立。`history`、`httpx2-migration` 设「条件退役」并各挂明确前置，与本会话发现的待裁决项/残余项吻合。注：`anthropic-responses-bridge/implementation.md` 中 `copilot-token-identity` 的多处命中是主仓 archive ref 名（`archive/260807-copilot-token-identity@…`），不是指向 `.dev/docs/copilot-token-identity/` 的文档引用，不构成 F-1 证据。
- **TUI 26 份清单**：`grep -ilE "tui|footer|request[ _-]?log|function-call-grouping"` 对 93 份 tmp 的命中集与清单逐一比对**完全一致**；文档明示「命中关键词不等于 TUI 所有权、须逐份按正文判断」，并对 stream-reset、buffered Chat 各给了非 TUI 归属示例。遗漏方向：对未命中的 67 份追加中文关键词（请求日志／在飞请求／完成行／实时 footer）扫描，命中 5 份，逐一读正文后均为 upstream（reset 留痕）与 error-envelope（E-11）切片证据，按正文归属不属 TUI——**未发现「直接 TUI 材料被遗漏」的高置信案例**。
- **合并事实**：嵌套 `.dev/.dev/docs` 1064 份文件逐一核对，目标树全部存在（missing=0）；同路径 12 份内容不同（rsync `--ignore-existing` 语义下保留活跃版），1052 份为净新增；账目闭合：1211（审计时文件数）− 1052 = 159 ✓，主题 12→42、文件 1211 均与实测一致（当前 1212/43 含本文档目录）。
- **tui 迁移**：`tui/history/` 实有 14 份 ✓；`tui/design.md:21` 与 `tui/function-call-grouping-plan.md:13,35,434` 的链接已指向 `history/` ✓。
- **结构事实**：`.dev` remote 为 `gh_puxu-msft:puxu-msft/ghc-api-proxy-py.git`、分支 `dotdev`、`git ls-tree HEAD` 顶层仅 `.dev`、`HEAD:.dev` 含 `.gitignore/README.md/docs/exp/human-controlled-docs-candidates/tools`、活跃未跟踪树含 `verification`（嵌套无）——均与文档表述一致。

## 未覆盖面

tmp/ 其余约 60 份、各退役候选目录报告内文的交叉引用只做了目录名级扫描，未逐份读正文；「合并前本地备份已删除」unverified。此两点不改变上述结论。
