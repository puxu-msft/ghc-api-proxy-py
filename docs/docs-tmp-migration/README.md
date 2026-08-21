# `docs/tmp` 与 `docs/agents` 搬入 `.dev/docs`（2026-08-21）

主仓库的 `docs/tmp/`（417 份报告）与 `docs/agents/`（8 个话题、43 份文档）整体搬入 `.dev/docs/`。这两个目录**已不存在，不要再重建**。主仓库 `docs/` 现在只剩 `docs/.human-controlled/`。

- 主仓库删除提交：`0b01cdc`（106 条纯删除，其余 300 多份本来就未被跟踪）
- `.dev` 接收提交：`5e94b75`（482 个文件，纯搬迁，内容零改动）
- 用户裁决（2026-08-21）：`docs/agents/` 下的活文档**全部话题整体搬入**，不只搬报告。CLAUDE.md 早前已授权「可逐步按主体迁移」，这次一次做完。

## 搬到哪了

一个话题一个目录。话题的**活文档**（`spec.md`、`status.md`、`plan.md`、`acceptance.md`、`deferred.md` 等）在话题根，**报告原件**在 `<topic>/reports/`。

| 话题 | 报告 | 活文档 |
|---|---:|---:|
| `anthropic-responses-bridge` | 200 | 11 |
| `documentation-restructure` | 34 | 2 |
| `service-cutover` | 33 | 3 |
| `systemd-runtime` | 42 | 3 |
| `hosted-web-search` | 22 | — |
| `delivery-keepalive` | 16 | 20 |
| `architecture-audit` | 9 | — |
| `empty-text-block` | 8 | — |
| `httpx2-migration` | 6 | 1 |
| `pipeline-rewrite-parity` | 5 | — |
| `git-housekeeping` | 5 | — |
| `tui` | 4 | — |
| `copilot-token-identity` | 4 | — |
| `test-infrastructure` | 3 | — |
| `project-review-principles-skill` | 3 | — |
| `lifecycle-reorg` | 3 | — |
| `hooks-subscription-migration` | 3 | — |
| `count-tokens` | 3 | — |
| `history` | 1 | — |
| `deployment-systemd` | — | 1 |
| `systemd-rolling` | — | 2 |
| **`tmp/`（未分类）** | **13** | — |

上表是**评审改判之后**的数字，与 10 份批次表的原始判定有出入；出入逐条记在下面「偏离批次表的改判」一节。

`tui`、`history` 是 `.dev` 里早已存在的话题，这次只是往里加报告。另有一份编辑器备份残件 `refs-go-bridges.md~` 与正本内容不同，一并留在 `tmp/`。

## 怎么分的

417 份逐个被打开读过，不是按文件名猜的。分 10 批派给 10 个 agent，每批的判据、逐文件表和置信度在 `reports/260821-classify-batch-*.md`，共享判据在 `BRIEF.md`，批次清单在 `batches/`。并集校验过：10 批无重、无漏，恰好 417。

判据的要点：

- **按内容判，不按文件名判。** 文件名里的 `review` / `audit` / `verify` 只说明体裁，不说明话题。
- **一个文件只归一个话题。** 跨话题的按「它评审的那个被改对象属于谁」定；仍判不了就留未分类。
- **未分类不是失败。** 硬塞进一个话题比留在 `tmp/` 更糟。

三个新话题由分类 agent 提出：`pipeline-rewrite-parity`、`hooks-subscription-migration`、`project-review-principles-skill`。

## 偏离批次表的改判

批次表是分类的一手记录，不改写。下面四处是合并与评审阶段偏离它的裁决，逐条留痕。

1. **补建 `copilot-token-identity`（4 份）与 `git-housekeeping`（5 份）。** 这两族分散在不同批次里，每批都不足 3 份而被判为未分类，合起来才够成话题。这是分批本身的产物，不是 agent 判错。
2. **`260807-audit-resident-byte-budget-squash.md`：`UNCLASSIFIED` → `anthropic-responses-bridge`。** 批次表以 high 置信度判它为「新话题，本批仅 1 份不足门槛」。但它评审的 `reservation.py` / `anthropic_sse.py` / `responses_anthropic_stream.py` 与另外 5 份已在 bridge 下的同族报告是同一条 squash 决策链，单独拆走会割裂它。这一处最初没有留痕，由抽样审计指出后补记（`reports/260821-audit-classification-sample.md` 次要发现）。
3. **9 份从 `documentation-restructure` 改判**（7 份去 `anthropic-responses-bridge`，2 份去 `service-cutover`）。`260807-resume-review-implementation-current-r2..r7.md` 与 `-post-s3.md` 评审的是 bridge 的 `implementation.md`；`260807-resume-review-readiness-current{,-r2}.md` 评审的是 service-cutover 的 `readiness.md`。两个批次的 agent 把它们的**体裁**（living 文档真相审计）当成了话题，而 BRIEF 判据第 2 条要求按**被评审对象**归属。同一批次里 `resume-review-systemd-plan-current-*` 却按对象判对了，说明这是执行不一致而非判据本身有歧义。
4. **不改的一处。** 抽样审计曾怀疑 `260807-audit-readme-drift.md` 与 `260807-doc-state-dependency-dag.md` 也该一并挪去 bridge，读后自行否定：它们评审的是文档体系结构本身（跨文档导航链接、正式文档间的同步依赖图），不是某一份 living 文档的候选状态，留在 `documentation-restructure` 正确。

抽样审计另外复核了全部 13 份未分类文件（无一应改判）、`anthropic-responses-bridge` 的 6 份样本（未出现「装不下就扔最大话题」），并对全部 417 个文件名做了词根聚类扫描，除上述第 3 条外没有发现第二个被拆散的同族簇。

## 未分类的 13 份，以及为什么

绝大多数是**同一时刻对分属不同话题的两三份活文档做的联合评审**——`260807-review-main-foundations-systemd.md` 同时评 bridge 的 reasoning／liveness 与 systemd 的 unit／shutdown，`260807-review-identity-living-checkpoint.md` 横跨 bridge 与 service-cutover。给它们挑一个话题就等于丢掉另一半。剩下两份是流程记录而非产品话题：`260820-review-session-closeout.md`（会话收尾）与 `260820-system-reminder-wire-shapes.md`（`<system-reminder>` 上行形态普查）。

## 引用重指：改了什么、没改什么

**归档报告原件里的路径一律不动。** 报告里写的 `docs/tmp/xxx.md:251` 是**当时那一刻**的位置，把它改成今天的布局等于伪造记录。`.dev/README.md` 的「归档文档里的路径与行号是快照」那条讲的就是这件事。所以 `.dev/docs/**/reports/`、`archive-*/reports/` 与 `archive-*/evidence/` 下的约 2400 处旧路径保持原样，读的时候当快照读。

**但 `archive-*/README.md` 与 `evidence-index.md` 是例外，它们重指了（31 处）。** 按 `.dev/README.md` 的定义，`archive-<subtopic>/README.md` 是「重写过的知识文档」，与 `reports/` 里逐字保留的原件不是一类；它俩的全部职能就是把读者送到证据那里，路由失效比快照失真更糟。同目录下的 6 处目标本来就不存在，保持原样。

**活文档重指了。** 27 个活文档、180 处引用，分两遍：

1. 字面 `docs/tmp/x.md` 与 `docs/agents/<topic>/y.md` → 新位置的相对路径。
2. 原文里就写成相对形式的（`../../tmp/x.md`），按**旧位置**解析出它当时指向谁，映射到新位置，再按**新位置**重算相对路径。第二遍必须跳过第一遍已经改对的，否则会把正确路径按旧基准重新解析成垃圾——这个坑踩过一次。

顺手修了更早一次搬迁遗留的 `docs/2604-rewrite/` → `../archived-2604-rewrite/`（6 处）。

**独立评审在这套重指里找出三处实错，都已修**，值得记下它们各自的形状：

- `research.md` 的 7 处**绝对路径**被塞进了相对形式的替换值，变成 `/home/xp/src/ghc-api-proxy-py/reports/…`——一个不存在的目录。替换是按字符串做的，没有区分这段路径是相对的还是绝对的。
- `history/proposal.md` 的 8 份报告被指向 `../tmp/`，而它们在 `history/reports/`。成因是裸目录兜底规则算的是「`docs/tmp/` 这个**目录**搬到哪了」，而不是「这**份文件**搬到哪了」；这 8 份是更早一次搬迁挪进 `.dev` 的，不在本次映射表里，于是掉进了兜底。
- `graceful-shutdown/client-side/README.md` 里一句**对 commit trailer 的引述**被机械改写了。那些提交的尾注逐字写的是 `Docs: docs/tmp/260820-…`，改完之后引述与被引述物不符，而同一句还紧跟着「尾注保持原样」。这恰好是本次搬迁自己立的原则在**活文档引述快照**的地方失守——原则在 `reports/` 目录层面守住了，却没想到活文档里也会有引文。

**主仓库里 11 处引用**（`src/`、`tests/`、`exp/`、`pyproject.toml`、`.claude/rules`、`.claude/skills`、`contrib/systemd`）改为 `.dev/docs/...`。这些是从被跟踪文件指向 gitignored 目录的链接——对 clone 本仓库的人是断的，但它准确说明了那份文档现在在哪，比指向一个已经不存在的路径强。

链接可达性检查跑过，检查器先用正样本证明过能报出坏链（第一版检查器自己崩了、退出码恰好也是 1，差点当成通过）。

## 留下的问题

- **四棵活 worktree 仍带着旧目录与旧规则，这是最容易让搬迁被撤销的一处。** 它们的分支都在 `0b01cdc` 的祖先侧，树里仍有这两个目录：`slice0/exactly-once` 105 份、`fix/upstream-error-events` 106 份、`worktree-proxy-priority` 105 份、`826d4cda` 那棵 detached 21 份。**按项目约定它们最终以 squash 进 `main`，而 squash 的 tree 来自分支侧——会把这两个目录整个带回来，且是静默的：没有冲突、没有报错。** 同时 `.claude/rules/` 是被跟踪文件，那四棵树里的规则仍写着「报告写进 `docs/tmp/`」，与磁盘上确实存在的目录互相印证，被派进去的 agent 没有理由起疑。规则里新加的那句约束的是「新建」，拦不住「合并带回」，所以**集成完这四条分支中的任何一条之后，必须复核主仓库 `docs/` 是否只剩 `.human-controlled/`**。四棵都有别的会话在用，rebase 或删除属破坏性操作，**需用户逐项授权**，本次未动。
- **`README.md` 在提交态仍有 3 处指向 `docs/agents/`**（`:56` `:58` `:59`），其中第 56 行直接以「各专题的开发文档在这里」的口吻做路由。工作树里看不到它们，是因为并行会话把 `README.md` 整体重写成了产品 README 并删掉了那一节，**但那份重写未暂存也未提交**。也就是说干净是偶然的，且依赖别人一份随时可能被丢弃的改动。我没有改它——改就等于把同伴那份未提交的重写一并提交。**根因值得记住：在有并行未提交改动的仓库里，用工作树 grep 判断「还有没有残留」会漏掉提交态里的残留，正确判据是 `git grep <commit>`。** 本次搬迁的引用面就是这样漏掉 README 的。
- **没做蒸馏。** 这次只搬和分类，没把报告里的结论提炼进活文档。`.dev/README.md` 说「归档要重写，不要堆」——现在各话题的 `reports/` 就是堆着的，缺 `README.md` 入口。200 份的 `anthropic-responses-bridge` 尤其需要。
- **搬迁之前就断的链接。** 在本次重指的 27 份活文档范围内有 3 处：`systemd-runtime/plan.md` 引的 `260807-systemd-user-manager-diagnosis.md`（这个名字在任何 ref、任何批次清单、`0b01cdc^` 的树里都没有过；`reports/260807-review-systemd-user-manager-diagnosis.md` 名字对不上，没有替它猜）、`systemd-rolling/plan.md` 引的 `copilot-api-js-comparison.md` 与 `tests/systemd_vm/README.md`。把范围扩到 `.dev/docs` 下全部 126 份活文档则是 11 处，多出来的 9 处在 `archived-2604-rewrite/` 下、是 2026-08-20 导入时就带着的坏链，本次未触碰（其中 `thinking-pipeline.md` 那处目标今天近在咫尺，顺手修了）。
- **`contrib/systemd/ghc-api-proxy.service` 的 `Documentation=` 需要用户裁决。** 它原本指 `/opt/ghc-api-proxy/docs/agents/deployment-systemd/README.md`；那份文档现在在 `.dev/`，而 `.dev/` 不随部署分发。我做了机械重指，但无论指哪儿这一行都不完全成立：指旧路径是指向不存在的文件，指新路径是断言了一个不会被部署的位置，指 `README.md` 则那里没有 systemd 内容。
- **CLAUDE.md 第 9 行已过时**，说「曾经用户选用过 `docs/agents/`，你可以逐步按主体迁移」——迁移已经做完。该文件由用户控制，未改动；另外它**未纳入 git 跟踪**，所以既不会被任何提交带走，也没有历史兜底。

## 评审

三份独立评审报告在 `reports/` 下，均为只读评审，未修改被检文件：

| 报告 | 视角 | 结论 |
|---|---|---|
| `260821-review-migration-integrity.md` | 完整性与可逆性：文件有没有丢、有没有卷走同伴的东西、归档原件有没有被改写 | 见报告 |
| `260821-review-instruction-surfaces.md` | 指令面覆盖：读完当前指令还会不会写回 `docs/tmp/` | 命题被推翻，1 blocker（worktree）+ 2 major（README、`.dev` 根路径未说明）+ 4 minor，已逐条处置 |
| `260821-audit-classification-sample.md` | 分类质量抽样：31 份逐字复核 + 417 个文件名词根聚类 | 9 份应改判，已改判；其余分类站得住 |
