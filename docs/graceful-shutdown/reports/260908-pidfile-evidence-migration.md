# pidfile tmp 证据归口迁移

## 范围

本次只迁移下列三份 `.dev/docs/tmp/` 原件，并改写 `restart-handover/README.md` 的入站链接；未改动原件正文，未改动源码、测试、配置或其他文档主题。

## Canonical destinations

| Source | Canonical destination | 角色 |
|---|---|---|
| `.dev/docs/tmp/260822-pidfile-missing-forensics.md` | [`restart-handover/history/260822-pidfile-missing-forensics.md`](../restart-handover/history/260822-pidfile-missing-forensics.md) | 事故一手时间线与排除假设 |
| `.dev/docs/tmp/260822-review-pidfile-port-scoping-opus.md` | [`restart-handover/history/260822-review-pidfile-port-scoping-opus.md`](../restart-handover/history/260822-review-pidfile-port-scoping-opus.md) | Opus 时点评审 |
| `.dev/docs/tmp/260822-review-pidfile-port-scoping-gpt.md` | [`restart-handover/history/260822-review-pidfile-port-scoping-gpt.md`](../restart-handover/history/260822-review-pidfile-port-scoping-gpt.md) | GPT 时点评审 |

`restart-handover/history/README.md` 记录每份原件的角色和时点边界：它们保留当时的命令输出、路径、行号与结论，不能自动外推为 current code、config 或运行态事实。

## README 链接改写

| 原引用 | 新的可解析相对链接 | 位置 |
|---|---|---|
| ``../../tmp/260822-pidfile-missing-forensics.md`` | `[260822-pidfile-missing-forensics.md](../restart-handover/history/260822-pidfile-missing-forensics.md)` | 「起因」的完整取证引文 |
| ``../../tmp/260822-pidfile-missing-forensics.md`` | `[260822-pidfile-missing-forensics.md](../restart-handover/history/260822-pidfile-missing-forensics.md)` | 「报告原件」清单 |
| ``../../tmp/260822-review-pidfile-port-scoping-opus.md`` | `[260822-review-pidfile-port-scoping-opus.md](../restart-handover/history/260822-review-pidfile-port-scoping-opus.md)` | 「报告原件」清单 |
| ``../../tmp/260822-review-pidfile-port-scoping-gpt.md`` | `[260822-review-pidfile-port-scoping-gpt.md](../restart-handover/history/260822-review-pidfile-port-scoping-gpt.md)` | 「报告原件」清单 |

README 中共有四个出现位置、指向三份原件；四处均在同一迁移更新中改写，避免内联取证引文残留为断链。

## 检查结果

- 三个精确 source path 均不存在，三个 canonical destination 均为普通文件：`PASS`。
- `restart-handover/README.md` 不再命中三条旧 `../../tmp/260822-*.md` 路径：`PASS`。
- README 的四个新 `history/...` 相对链接均存在；history README 的三条子链接及其 `../README.md` 父链接均可解析：`PASS`。
- destination SHA-256：
  - `260822-pidfile-missing-forensics.md`: `c091856a962728dc65c7fa395ebdbe79aa4e40dbfdf20d28072c9e6436a46479`
  - `260822-review-pidfile-port-scoping-opus.md`: `3ba3babc3ce4d65925fe99fae9e697f349117040d90a1eccbf62b75ceb72e8a6`
  - `260822-review-pidfile-port-scoping-gpt.md`: `df4618d0446bdc9724d0c5a28227c366d1b60ba7ced485592b6769b716492764`

未运行源码测试：本次仅迁移 Markdown 原件并更新相对链接。

## MSR-05／MSR-06 处置（2026-09-08）

- **MSR-05**：`client-side/README.md` 的删除线历史注记不再给出 `.dev/docs/archived-2604-rewrite/` 或其他可定位目录；只保留“旧 2604 rewrite 学习笔记已退役、不得作为设计依据”的负面历史事实。
- **MSR-06**：本表的四个 `history/...` 示例链接此前按本报告所在的 `graceful-shutdown/reports/` 目录解析，会错误指向 `reports/history/`。现均改为 `../restart-handover/history/...`，与上节 canonical destination 链接一致。
- **链接检查**：从本报告目录解析四个改写链接，均落到存在的 `graceful-shutdown/restart-handover/history/260822-*.md` 原件；`PASS`。未运行源码测试，本次仅修正文档文字与相对链接。
