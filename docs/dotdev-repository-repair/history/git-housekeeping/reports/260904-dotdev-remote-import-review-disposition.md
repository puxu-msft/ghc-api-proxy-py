# `origin/dotdev` 内容导入评审处置

日期：2026-09-04。
状态：closed。三条 finding 全部采纳；原 reviewer 窄复评 pass，remaining blocker=0、major=0、minor=0。
来源：[`260904-dotdev-remote-import-review-gpt-opus.md`](260904-dotdev-remote-import-review-gpt-opus.md)。

## 接收回执

首轮 verdict 为 needs-fix：blocker 1、major 2。C1、C2、C4、C6、C7 通过；C3、C5 不通过。报告未提出可选清理或 proof framework。

## Findings

| Finding | 成立度／判断 | 处置 | 级别 | 实际修改 |
|---|---|---|---|---|
| F-01 HTTP 499 living 状态与当前人写 authority／实现冲突 | confirmed／concurred | adopted | A | 不改 `docs/.human-controlled/`，不把另一 clone 的 requirement 反写成本地用户裁决。`status.md` 将 HTTP 499 段改为 imported source-clone snapshot，点明当前 human requirement 与 `RETRYABLE_STATUSES` 都不含 499；`http-499-retry.md` 与 `review-disposition.md` 加 imported snapshot banner，所有 current／closed 只限定原 source clone，并列出恢复 current 地位的条件 |
| F-02 timeout-408／Xingchen status 冒充当前 main | confirmed／concurred | adopted | C | `timeout-408/status.md`、`xingchen/status.md` 与 Xingchen disposition 标明 source clone snapshot、当前 source/archive 不可达；两份 spec 保留为目标行为规格，但撤掉“当前 checkout 已实现”的表述。报告 originals 不改 |
| F-03 reasoning-carrier tracking 指向不存在的唯一 source | confirmed／concurred | adopted | C | `tracking.md` 标为 source-unreachable，原 worktree／branch 只作历史记录，不再提供虚假的 `git rev-parse HEAD` 恢复指令；终态改为找回 ref／bundle／另一 clone 后重建身份并复评。Spec 同步说明当前 source 不可达，报告 originals 不改 |

## 未采纳路线

1. 未采纳“远端报告 PASS 即直接采用 living status”：评审只绑定原 source clone，不证明当前 checkout 的 requirement、源码或 ref。
2. 未采纳“为使文档成真而修改用户控制需求”：用户控制目录只有用户可改；本轮只忠实降格导入记录。
3. 未采纳“删除无法装位的文档”：报告、规格与处置仍是找回 source history 的恢复输入；删除会丢证据。
4. 未采纳 force push、覆盖远端或改写报告 originals：计划仍以远端 tip 为第一父、本地 tip 为第二父，最终只规范化树路径。

## 复评结论

原 reviewer 已完成窄复评，见 [`260904-dotdev-remote-import-review-gpt-opus-r2.md`](260904-dotdev-remote-import-review-gpt-opus-r2.md)：F-01～F-03 全部 closed，remaining blocker=0、major=0、minor=0；相邻 README 索引同义，报告 originals 相对 remote tip 的变化数为 0。候选可提交到本地迁移历史并进入远端 merge-tree 构造。