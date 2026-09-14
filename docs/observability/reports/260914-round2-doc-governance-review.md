# 第二轮文档治理复审

## 评审范围

本轮只读复审以下 current 文档及其 current links：

- `.dev/README.md` inventory、生命周期与操作入口；
- `observability/`、`history/`、`raw-capture/`、`replay/` 的 `README.md`、`spec.md`、`status.md`、`deferred.md`；
- `observability/review-disposition.md`、`raw-capture/review-disposition.md`；
- `dotdev-repository-repair/README.md`；
- 以上文件直接指向的当前 human-controlled 入口与候选材料。

代码事实只按 clean committed HEAD `30384269377cfd5f8f848ef92bb3654afda2196a`（短 SHA `30384269`）的 committed tree 核验；不以共享主树 working-copy 作为代码证据。已明确接受并写入 `status.md` / `deferred.md` 的实现限制，本轮不重新升级为 major，除非入口仍写成 done 或 current authority 丢失。

## 总体 verdict

**needs-fix**

## blocker 数

0

## Major findings

### DOC-GOV-R2-01 — root README 与 repository-repair current entry 对 re-root/worktree 状态互相矛盾

- **finding_id:** `DOC-GOV-R2-01`
- **severity:** major
- **primary_location:** `.dev/README.md:5,20,86`
- **related_locations:** `.dev/docs/dotdev-repository-repair/README.md:3,23-29,48`
- **涉及清单:** C3、C5

**证据**

`.dev/README.md` 用现在时声明它是 “dotdev re-root 后分支根目录的入口”，并声明主工作树的 `.dev/` 已是该根树的 Git worktree 挂载点（第 5、20、86 行）。同一份 README 还把 repair README 指定为 re-root/worktree 的 current owner。

但该 current owner 的状态明确写成“尚不得执行 dotdev re-root/worktree 挂载”，并把“最终独立复扫 → `.dev` git checkpoint → 才可挂载”列为唯一剩余结构性顺序（第 3、23-29、48 行）。这不是历史/目标描述的明确区分，而是两个 current 文档对同一操作的相反前置状态。

**影响**

新接手者无法判定当前应按“已挂载的根 checkout”工作，还是按“挂载前的 repair 阶段”先完成复扫和 checkpoint；也无法从入口确定 re-root 是否仍是待执行动作。该冲突使文档生命周期和同步/恢复边界不可执行，直接破坏 root → topic entry → current owner 的交接路径。

**闭合要求**

由 repository-repair README 的 current 状态裁决唯一事实，并同步 root README：明确标出“当前状态”与“目标结构”分别是什么；若 re-root 尚未完成，root README 不得用现在时声称已挂载；若已完成，则应关闭 repair 的三步前置并更新其状态。对 `tmp` 的当前路径也应在同一处明确唯一 owner，避免接手者沿两套结构操作。

### DOC-GOV-R2-02 — raw-capture 旧 major 报告没有可执行的逐报告/逐 finding current disposition

- **finding_id:** `DOC-GOV-R2-02`
- **severity:** major
- **primary_location:** `.dev/docs/raw-capture/review-disposition.md:5-15`
- **related_locations:** `.dev/docs/raw-capture/reports/raw-capture-review-2026-09-09-implementation-audit.md:2-6,26-78`；`.dev/docs/raw-capture/reports/260909-coordinator-audit-checklist.md:1-10`
- **涉及清单:** C3、C5

**证据**

当前 disposition 只给出一个宽泛的“v21/v22/v23 writer reviews”报告族结论：旧报告是 historical evidence，**已由 v24 writer slice 覆盖的 finding** 才记录为 closed；但没有列出具体报告名、finding ID、覆盖关系或未覆盖项。

其中仍在 `reports/` 的 `raw-capture-review-2026-09-09-implementation-audit.md` 自带 `status: in-review`、`criterion: ACTIVE v22`、总体 `needs-fix`，并列出 `raw-capture-impl-audit-20260909-a1-01` 至 `a1-03` 三个 major finding。当前 raw-capture `status.md` 只描述 bounded writer/ack/poison 已落地和 per-attempt capability deferred，没有明确声明这三个 finding 是 closed、accepted、rejected、superseded 还是仍待处理。与此同时，`260909-coordinator-audit-checklist.md` 明确要求对每条 finding 做复核并把采纳/拒绝/延期写入处置账；现行 disposition 没有完成这条映射。

**影响**

接手者仍可把该报告的 `needs-fix` 与三条 major 当作 current gate，也可反过来仅凭“v24 writer slice”一语忽略它们；两种读法都没有可复现的证据锚。报告生命周期因此不可执行，旧 finding 既可能重复修复，也可能在没有明确裁决的情况下被静默遗失。

**闭合要求**

在 raw-capture current disposition 中逐报告（至少包含该 implementation-audit）并逐 finding 映射 `closed / accepted-deferred / rejected / superseded`，为每项给出 current owner、替代证据和适用 Spec 版本；或者明确标记整份报告 superseded，并指向覆盖其 finding 的新 review package。所有仍保留的 raw-capture report 都应能从该 disposition 得到唯一 current 处置，不得只靠文件名中的版本推断。

## Minor / 牛角尖

### DOC-GOV-R2-M01 — raw-capture Spec 的 current version 标注落后于自身 revision record

`.dev/docs/raw-capture/spec.md:3-5` 仍写 `ACTIVE v24`，而同一文件的 revision record 已在第 108 行记录 2026-09-14 的 `v25`；`raw-capture/review-disposition.md:5` 也继续把 current state 指向 “v24 Spec”。Spec 的 authority 没有丢失，且 v25 的修订内容可读，因此这是版本导航的 minor，不改变本轮 major verdict。

## C1–C5 判定

| 清单 | 结论 | 依据 |
|---|---|---|
| C1 | **通过** | root inventory 已列出四个主题；`observability/README.md` 提供四主题总入口；四个主题各有 README、Spec、status、deferred，且 review disposition 有明确 owner。 |
| C2 | **通过** | `implementation-ledger.md` 明确自限为状态/提交/验证索引；本轮未发现它重新复制字段语义、行为合同或安全边界。 |
| C3 | **不通过** | `DOC-GOV-R2-01` 的 re-root current state 冲突，以及 `DOC-GOV-R2-02` 的 raw-capture 旧 major 报告没有逐项处置，都会使生命周期动作不可执行。 |
| C4 | **通过** | 对 21 份 current scoped Markdown 检查 148 个本地链接，missing=0。缺失的 `docs/.human-controlled/observability.md` 在 README、status、review disposition 中均明确标为缺失，且指向候选材料，没有静默以 `.dev` Spec 冒充用户控制来源。 |
| C5 | **不通过** | topic README → Spec/status/deferred 链路已成立，但 root/repair 的结构状态冲突和 raw report disposition 缺口仍会让新接手者无法唯一读出当前文档仓库状态与历史 finding 处置。 |

## 搜索面与验证

- 已读 `.claude/rules/00-development-workflow.md`、`docs/.human-controlled/README.md`、`.dev/README.md`、四个主题的 current README/Spec/status/deferred，以及 observability/raw-capture review disposition 和 repository-repair README。
- 已读 observability 第一轮三份报告、raw-capture 当前报告目录的标题/状态，并全文核对 raw-capture implementation-audit、merged-state review、coordinator checklist 与 final re-review 的 disposition 线索。
- 代码事实仅以 `git show 30384269:<path>` 核验了 History archive、Replay process/result、RequestJournal、History identity/capability projection；这些已接受限制均已在 current status/deferred 中明确标出，本轮未把它们重复计为 major。
- 已执行只读 Markdown link probe：21 个 current scoped 文件、148 个本地链接、missing=0。未运行测试；未读取共享主树作为代码证据；未修改、删除或创建除本报告外的文件；未执行 `git add` 或 `git commit`。
