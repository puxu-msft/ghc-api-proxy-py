# 文档重组计划独立复评 R2

## 评审摘要

- **评审范围**：current `main`，`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4` 工作树中的 `docs/agents/documentation-restructure/plan.md`；定向逐条复核上一轮 `docs/tmp/review-doc-migration-plan.md` 的 5 条 major，以及用户最新要求的 `docs/tmp` 日期前缀命名与临时结论及时归纳约束。未重新评审 42 份源文档正文。
- **总体 verdict**：**修复 major 后可进入下一阶段**。当前计划尚不能按“0 major，可执行”放行。
- **blocker 数**：0。
- **major 数**：1。
- **机械核对覆盖证据**：每次 shell 均绑定并验证仓库绝对根、`main` 与 HEAD；确认规划基线 `47d9ef101c4b81ac70d805b1da157b34d021d33d` 是 current HEAD 的祖先，且该基线到 current HEAD 的 `docs/2604-rewrite/**/*.md` 无提交态漂移。用 `fd --type f --extension md` 与 Python `Path.rglob('*.md')` 在上述 HEAD／路径口径下分别得到 42；机器解析第 5.4 节得到 42 行、42 个唯一 source、42 个唯一 canonical destination，源集合与实际文件集合精确相等，所有 `extract phase ≤ final move phase`。逐条对账上一轮 5 条 major 的修订落点，并核对 `markdown-it-py 4.2.0` 已在 `uv.lock` 锁定且当前 `.venv` 可导入。
- **第一人称执行覆盖证据**：模拟了阶段 0 在全新工作目录提交 checker／fixtures／manifest 后暂停并恢复；模拟了阶段 1 给 40 份 retained source 加 banner、移动两个 `final move phase = 1` 的 streaming 源并生成 phase pathspec；模拟了 canonical destination 正确但额外复制正文的失败路径；模拟了移动后 relative rebasing、Unicode／重复 heading slug、GitHub line fragment 的正反路径；最后按阶段 1 实际执行者视角逐项清点两个被最终移动源在第 5.1 节声明的全部输出，发现三个 spec 没有阶段 owner。

## 上一轮 5 条 major 复核

| 上一轮 major | R2 结论 | 证据 |
|---|---|---|
| 1. 阶段 0 oracle 只在临时目录，无法跨暂停复现 | **关闭** | `plan.md:73-74,248,281-293` 把 manifest、checker、fixtures、执行说明固定到 `docs/agents/documentation-restructure/verification/`，要求先形成独立 `test(docs)` 提交；系统临时目录只存运行输出。阶段 11 在 `plan.md:507` 无条件复跑这些已提交 gate。锁文件已有可用的成熟 Markdown AST parser。 |
| 2. 迁移窗口仍可直达旧冲突合同 | **关闭** | `plan.md:37,305-317` 要求阶段 1 给所有 40 份 `final move phase > 1` 的 retained source 加唯一 banner，并让 `docs/README.md` 首屏否定旧目录的当前真相源地位；banner final phase 由 manifest 校验，删除 banner 的反 fixture 必须红。 |
| 3. 跨阶段提炼与最终移动 owner 含糊 | **未完全关闭，仍有 1 major** | 42 个 source 的 final owner 已唯一，且两个 phase-1 move 已精确冻结；但 source owner 已唯一不等于所有派生产物都有 owner。第 5.1 节要求从这两个源生成三个额外 spec，阶段 1 的显式产物清单和后续阶段均未接管它们。详见事实性发现 1。 |
| 4. 映射全绿仍可能留下未标注正文副本 | **关闭** | `plan.md:73,282-286,486,507` 冻结 raw／body hash、`destination_kind` 与 canonical destination；对 `docs/**` 做精确 hash 和近似块扫描，并要求“canonical move 正确但额外复制一份”反 fixture 红、合法提炼正 fixture 绿。受管 header 识别也有伪 header 反例，避免过度剥离导致假绿。 |
| 5. 链接 gate 未定义 fragment／renderer／移动 rebasing | **关闭** | `plan.md:284-285,315,487,507,533` 把 renderer 固定为 GitHub 仓库 Web UI 的 GitHub Flavored Markdown，分别覆盖文件、heading fragment 与 `#L<n>`／`#L<n>-L<m>`，并冻结 relative rebasing、Unicode、重复 heading suffix、畸形／越界 line fragment 的双向 fixtures。 |

## 最新临时文件约束复核

- **命名通过**：本轮唯一报告路径为 `docs/tmp/260806-review-doc-migration-plan-r2.md`，符合用户指定的 `260806-` 日期前缀与 R2 命名。
- **及时归纳约束通过，但有执行前动作**：`plan.md:35,74,260` 明确 `docs/tmp/**` 不是长期权威、不进入正式引用链或迁移提交；`plan.md:587-597` 已把上一轮 5 条 major 归纳进正式计划。主会话修复本轮 major 时，必须同步更新正式计划正文及第 12 节处置表，再复评；不得只在本临时报告中留下结论，也不得让正式文档反向链接本报告。

## 事实性发现

### 1. [major] `plan.md:145-146,182,229,299-305` — 两个阶段 1 final-move 源的三个派生 spec 没有阶段 owner，phase-1 pathspec 仍不能从计划机械唯一生成

- **问题**：第 5.1 节要求 `streaming-resilience.md` 产出 `docs/agents/streaming-resilience/spec.md` 与 `docs/agents/upstream-keepalive/spec.md`，要求 `streaming.md` 产出 `docs/agents/stream-consumers/spec.md`。第 5.4 节又把两个源的 `extract phases` 与 `final move phase` 都固定为 1，意味着这些内容必须在阶段 1 最终移动源之前完成提炼。但阶段 1 的显式产物只列 `buffering/spec.md`、`anthropic-messages/spec.md` 和另外五个 Anthropic topic specs，没有列上述三个 spec；全计划对这三个精确路径也只在第 5.1 节出现一次，后续阶段没有 owner。
- **证据或失败场景**：执行者按阶段 1 “涉及文件”生成 pathspec，会移动两个源却不创建三个 spec，违反第 5.1 节 disposition 并可能丢失 keepalive、delayed commit、transport keepalive 与逐协议 consumer 缺口的正式去向；执行者若自行把三个 spec 补进 phase 1，则是在计划未分配 owner 的情况下猜测 pathspec。两种执行都能满足当前第 5.4 节 checker 所列的 source 数量、唯一 final owner、destination 唯一和 `extract ≤ final` 不变量，因为这些不变量只覆盖 source／canonical destination，没有机械核对第 5.1～5.3 节每个“新位置／产物”是否恰有一个生产阶段。上一轮 major 3 因而只关闭了 source move ownership，未关闭派生产物 ownership。
- **修复建议**：在阶段 1 “涉及文件”中显式加入这三个 spec，并把它们加入 phase-1 exact pathspec；同时扩展阶段 0 manifest／checker，使第 5.1～5.3 节列出的每个新产物路径都有且只有一个 producer phase，且每个 source 的所有 required outputs 不晚于其 `final_move_phase`。增加双向 fixture：完整 producer 分配为绿；漏掉一个派生产物、重复分配给两个阶段、或晚于 source final move 才生产均为红。修订后重新独立复评；只有 blocker 0、major 0 才可执行阶段 0／1。

## 主观建议

无。本轮唯一发现是上一轮 major 3 的可复现残留，不是风格偏好。

## 结论

未发现 blocker。上一轮 major 1、2、4、5 已由可提交验证资产、迁移期 banner、hash／provenance 重复 gate和 renderer-aware fragment fixtures 关闭；42 个 source 的集合、唯一 final owner 与 canonical destination 也已机械通过。当前仍有 1 条 major：三个由阶段 1 最终移动源要求生成的 spec 没有 producer phase，导致完整 phase pathspec 仍需执行者自判。把该缺口归纳回正式计划并补 producer-coverage 双向 gate 后再复评；达到 0 major 时可明确判定计划可执行。
