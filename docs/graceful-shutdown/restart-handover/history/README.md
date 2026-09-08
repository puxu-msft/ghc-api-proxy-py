# pidfile 接替的历史证据

本目录保存 `restart-handover/` 的 2026-08-22 时点原件。它们从 `.dev/docs/tmp/` 原样归口而来；迁移没有修改原件的正文、时点、命令输出、路径、行号或结论。

| 原件 | 角色 | 证据边界 |
|---|---|---|
| [260822-pidfile-missing-forensics.md](260822-pidfile-missing-forensics.md) | pidfile 覆盖—删除事故的一手时间线与排除假设 | 只证明文中取得时的事故与观测，不替代 current 运行态取证。 |
| [260822-review-pidfile-port-scoping-opus.md](260822-review-pidfile-port-scoping-opus.md) | Opus 的时点评审 | verdict、文件路径与行号绑定当时评审输入，不自动覆盖迁移后的 README 或 current code。 |
| [260822-review-pidfile-port-scoping-gpt.md](260822-review-pidfile-port-scoping-gpt.md) | GPT 的时点评审 | verdict、文件路径与行号绑定当时评审输入，不自动覆盖迁移后的 README 或 current code。 |
| [260822-review-pidfile-dir-refusal-gpt.md](260822-review-pidfile-dir-refusal-gpt.md) | GPT 对第二批 `pidfile_dir`／拒绝覆盖／`--fd` 改动的补充评审 | 评审快照为 `HEAD 80068ebb5737` 的指定 8 文件未提交 diff；其 F1／F2 是当时输入的发现，不自动描述随后修复后的代码。 |
| [260822-review-pidfile-dir-refusal-opus.md](260822-review-pidfile-dir-refusal-opus.md) | Opus 对同一第二批主题的补充评审 | 结论绑定 2026-08-22T15:18:04+00:00 的 8 文件快照；评审期间实现仍在变化，故它不能与 GPT 报告合并为同一 current verdict。 |

## 证据之间的关系

forensics 原件记录事故的一手时间线；两份 port-scoping 评审评价第一批“端口入名＋缺前任告警”改动。两份 `pidfile-dir-refusal` 补充评审评价其后的第二批 `pidfile_dir`、活记录拒绝／force override 与 `--fd` 冲突处理。它们补充、而不取代前一批的事故和评审证据。

两个第二批评审也不是相互覆盖的单一结论：GPT 报告记录其固定输入上仍可复现的 inactive-option 与拒绝接线缺口；Opus 报告明确记录在自己的更晚快照中这两项已被实施者修复，并评价该快照的其余问题。读取时必须保留各自的时间、输入哈希和证据边界。

现行解释以父目录的 [README](../README.md) 及其引用的 human-controlled 规范为准。若后续再迁移或更新引用，必须保留本目录原件不变并复查所有入站链接。
