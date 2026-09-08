# HTTP 499 user ruling integration 评审核查清单

## 用户裁决

- Spec：用户要求“你直接并入但不提交该文件，我再审核”。该裁决只授权把已评审候选转录到目标 Spec 工作树，并明确禁止提交目标 Spec；它不是用户对转录全文的最终审核通过。
- Development docs：用户选择“专用的 origin/dotdev 分支”。只读 `git ls-remote --heads origin refs/heads/dotdev` 已确认远端尚无此分支，因此本轮拟创建只承载 `.dev/` 的 orphan `dotdev`，评审通过后提交并推送创建 `origin/dotdev`。

## 固定输入

- `docs/.human-controlled/upstream-retry-and-continuation.md`：`08deb933b57dca134003cae530790f99bdc4de03b08b9b8ff7d94447a84cc29d`
- `.claude/rules/00-development-workflow.md`：`02ac4c77fec44c046492005eb06e487bf0e66ad822e5dd01c0c6797fcdf8973b`
- `.gitignore`：`64f3333b0414c16c90c40f35749aec9e05ea1bf9bcd0c9a8bae730115acd42b1`
- `.dev/README.md`：`faf6c97de7e82e0ee9b0474d24c76f68d29717496c752eb6b766ddafe72601c0`
- `.dev/human-controlled-docs-candidates/260904-http-499-retry.md`：`b17767dbf01dab2d2728342f1ce6b65326dbad6b1d1bc9c330ed5f861af64bde`
- `.dev/docs/upstream/retry-and-continuation/status.md`：`cc4c7e1e6e74ee8fc36672e105f7ec8071f0b7750ee4b825a94d175f44205e86`
- `.dev/docs/upstream/retry-and-continuation/review-disposition.md`：`f6c95ad39d848d981e5a136ae35dcbb10a59d95a3da23af8bd9d05d06edd0758`
- dotdev worktree：`/home/xp/.claude/jobs/00409e7f/tmp/dotdev-worktree`，当前 orphan branch `dotdev` 尚无 commit，只含从主树逐文件 hash 校验复制的 8 个本任务 `.dev` 文件。

## 必须逐条核验的断言

- C1：目标 Spec 的 499 条款完整转录已通过限定复评的 candidate，包括 retry classification、两级预算、draining/deadline、final error envelope、rejected capture、attempt observability、transcription authority 与修订记录；没有把 candidate 的过程/provenance 章节误抄进规范正文。
- C2：目标 Spec 仍是工作树修改而非 staged/committed；后续任何主仓提交都必须排除它，直到用户审核。
- C3：candidate 准确记录本轮两条用户裁决的 scope，不把“直接并入但不提交”冒充最终审核通过，也不把 `origin/dotdev` 选择扩成对其它发布的授权。
- C4：`.dev/README.md`、`.gitignore` 与 project workflow 对 `main` ignored working copy、orphan `origin/dotdev` durable source、exact-path synchronization、禁止 bulk-copy peers WIP、提交与 push 权限、恢复方式的描述一致，没有第二个权威或不可执行循环。
- C5：orphan `dotdev` 是适合该约定的分支形态；初始工作树不含主代码历史中的文件，也没有复制 stream-accounting、timeout-408 或其他会话的 `.dev` WIP。计划提交的 8 个路径完整覆盖本任务在 checklist 创建前的 candidate/status/disposition/reports/README。
- C6：创建并 push 新 `origin/dotdev` 确实落在用户本次明确选择的发布范围内；不需要也不得 push `main`、未提交 Spec 或其他分支。
- C7：project workflow 从“nested separate repository”改为 orphan branch 后，不再与 `.gitignore` 或 README 冲突；`CLAUDE.md` 只要求 `.dev` 路径和候选目录，没有必须同步的旧存储说法。
- C8：最终 closeout review 的两条 minor 已正确修复；两条 major 已由用户裁决提供可执行关闭路径，但在 Spec 用户审核和 dotdev 推送真正完成前仍应保持 open，不能提前改为 fixed。

## 评审边界

只报告有具体失败场景的 blocker/major/minor，最多 6 条；不要以成本、ROI、泛化安全顾虑或纯措辞偏好报问题。评审对象尚未 commit/push，发现应在发布前修复。返回完整 Markdown 报告，主会话负责持久化；隔离 worktree 报告会自动清理，不作为交付载体。
