# 评审报告存档：`debug models`

本目录是 `debug models` 实现过程中五份评审报告加一份收尾核对的原件，按产出时间排列。

**内容保持原样，未经编辑。** 报告正文里出现的路径都是评审当时读到的位置（多为主仓库 `docs/tmp/260820-*.md`），这些文件后来整体搬到了本目录。**没有回头去改报告里的路径**：报告是「某人在某个时刻看到了什么」的记录，改掉它引用的路径就等于篡改这份记录。要按报告复现，把 `docs/tmp/260820-<name>.md` 读成 `.dev/docs/cli-commands/debug-models/reports/260820-<name>.md`，把处置记录读成上级目录的 `review-disposition.md`。

同理，报告里锚定的 `HEAD` 哈希是评审当时的，与本目录 `decision.md` 列出的六个提交不是同一时刻的快照。

| 文件 | 评审对象 | 来源 | 结论 |
|---|---|---|---|
| `260820-review-debug-models-gpt.md` | `a46eb8d` | 异源，实跑证伪 | 0 blocker / 3 major / 3 minor |
| `260820-review-debug-models-opus.md` | 同上（修完第一轮的版本） | 同源，设计评审 | 0 blocker / 5 major（含一条「需用户裁决、非代码缺陷」）/ 1 minor / 2 nit |
| `260820-review-endpoint-defaulting-gpt.md` | `883b104` + `14a5012` | 异源 | 0 blocker / 1 major / 1 minor |
| `260820-review-endpoint-defaulting.md` | 同上 | 同源 | 0 blocker / 2 major / 5 minor / 3 nit |
| `260820-review-endpoint-allowlist.md` | `0f9abbc` | 异源 | 0 blocker / 1 major / 3 minor |
| `260820-closeout-factcheck.md` | 收尾文档本身 | 事实对账 | 4 处不一致，均已改正 |

两份 endpoint-defaulting 报告**独立发现了同样的两个缺陷**，只是严重度评级不同——这是本次派双评审最直接的收益。

上表的严重度是逐份点回原文数出来的。第一版是凭印象写的，`260820-review-debug-models-opus.md` 那行就写错了（写成 4 major，实为 5：§1.1、§1.2、§1.4、§3.1、§3.2）。本会话此类计数错误已发生三次，另两次由 `260820-closeout-factcheck.md` 抓出。

逐条处置（含未采纳项及理由）见上级目录 `review-disposition.md`；用户裁决见 `decision.md`。

`260820-review-endpoint-defaulting-gpt.md` 有 160 KB，绝大部分是末尾附录里一份完整的上游目录 JSON。留着是因为它是那轮结论的一手证据；只读结论的话看文件前 130 行即可。
