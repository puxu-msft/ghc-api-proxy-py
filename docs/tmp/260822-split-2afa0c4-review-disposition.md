# `2afa0c4` 拆分评审的处置

**处置日期**：2026-08-22。**评审报告**：[`260822-review-split-2afa0c4.md`](260822-review-split-2afa0c4.md)（异源独立子智能体，只读）。
**评审总判定**：pass，blocker 0、major 0、minor 3、nit 4、信息 1。
**处置提交**：主仓 `fa0b281`…`1c91870`（按 F2 重做的一轮改写）、`.dev` 本次提交（文档）。

| # | 严重度 | 发现 | 处置 |
|---|---|---|---|
| **F2** | minor | `bbf5f50` 的信息写「while CLAUDE.md **went on pointing** at `docs/.human-controlled/`」，字面要求 CLAUDE.md 在 `0b01cdc` 时已存在；实际它晚 4h44m 才由 `1b0cdd2` 建立 | **采纳，已独立复核属实**（`git cat-file -e 0b01cdc:CLAUDE.md` 报 absent；`0b01cdc` 18:21:33 vs `1b0cdd2` 23:05:32）。没有按建议只改动词，而是改成陈述那个更强也更准的事实：「CLAUDE.md, written after that, points at `docs/.human-controlled/` … — a path that until now held nothing」。**代价是整链哈希再变一轮**，`.dev` 的活文档指针与本对照表随之更新 |
| **F19** | minor | `docs/.human-controlled/` 进入版本控制后，`fix/upstream-error-events` 的 squash 整合会连带删掉这 14 份用户文档 | **采纳**，写进 [`260822-split-2afa0c4-hash-map.md`](260822-split-2afa0c4-hash-map.md) 的「波及面」。**不加新机制**——评审自己也指出 `.claude/rules/00-development-workflow.md:39` 既有的收尾检查恰好击发这一种 |
| **F18** | nit | 对照表写「两个活跃 worktree 分支」，实际还有第三个 detached worktree | **采纳**，补上限定与它的无害理由（`7839b02`，2026-08-18，在改写点之下） |
| **F20** | minor | 三处源码注释（`anthropic_request_hook.py:28`/`:59`、`pipeline_app.py:422`）引用不存在的 `docs/.human-controlled/message-format-sanitize.md`；README 清单列了不存在的 `observability.md`、漏了存在的 `release-and-deployment.md` | **不在本次动手，已上报用户**。先于本次改动存在，与拆分无关。文档侧是用户亲笔，agent 不得改；代码侧那三处注释该指向哪一份文档（`message-format-reshape.md`？还是一份尚未写的文档？）是**用户的裁决**，不是我能推断的——猜一个名字填进去会把「悬空引用」换成「指错地方的引用」，后者更难发现 |
| **F6** | nit | `cli.md` 是 0 字节，与信息里「the constraints … the user has settled on」略有出入 | **不采纳**。评审自己也建议不改：提交信息是摘要，一个空占位文件不值一句话，且那是用户目录的现状而非本次改动引入 |
| **F14** | nit | 对照表放在 `docs/tmp/`，而它是长期解码器不是报告 | **不采纳（留给用户裁决）**。风险确实低——对照关系可从保留分支用一条 `range-diff` 重算。文档归置到哪个 topic 是文档组织决策，不该由我在一次历史改写的收尾里顺手定 |
| **F15** | nit | `a/YYYY-MM-DD-<topic>` 保留分支约定有三条先例但未写进 `.claude/rules/` | **不采纳（留给用户裁决）**。`.claude/rules/` 是项目级规则，往里加一条约定属于立规矩，归用户。评审对「用 `a/` 而不是 `archive/`」这个判别的支持意见已记在此 |
| **F21** | 信息 | 新纳入版本控制的 `config.example.yaml`、`module-org.md` 在工作树里有用户未提交的改动，其一写于改写后一分钟 | **无动作，且明确不代提交**。这两份是用户亲笔，提交时机归用户。它同时是「不动工作树 + CAS 移 ref」这个做法必需而非讲究的证据 |

## 评审给出的正面判据（值得复述，故记下）

- **拆分点被证到了，不只是 tip**：`tree(800eb5b) == tree(2afa0c4)`。tip 相等证明不了两半各自正确——两边互欠一点、在后续提交里互相还上，tip 照样相等。再加路径集精确划分（不相交、并集相等，15 + 8 = 23）。
- **committer date 也保住了**，不只是 author 三字段。`range-diff` **不比** committer date，所以这是一个「不会被自己的验证发现」的漏项。
- **过程记录不回填的理由比「惯例」更硬**：那些旧哈希全部是「某时刻的 HEAD」，回填会写下一句物理上不可能的话。
