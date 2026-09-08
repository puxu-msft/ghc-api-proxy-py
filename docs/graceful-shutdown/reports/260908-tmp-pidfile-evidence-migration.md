# 第二批 pidfile 补充评审的 tmp 归口迁移

## 范围

按 tmp final disposition ledger，仅迁移下列两份补充评审：`.dev/docs/tmp/260822-review-pidfile-dir-refusal-gpt.md` 与 `.dev/docs/tmp/260822-review-pidfile-dir-refusal-opus.md`。除 `graceful-shutdown/` 外未修改任何路径；原件正文未改写。

## Source、destination 与 hash

| Source | Canonical destination | SHA-256（迁移前／后） |
|---|---|---|
| `.dev/docs/tmp/260822-review-pidfile-dir-refusal-gpt.md` | [`restart-handover/history/260822-review-pidfile-dir-refusal-gpt.md`](../restart-handover/history/260822-review-pidfile-dir-refusal-gpt.md) | `e680dfbee11b195b5dafeffddc895fac71f3af102b7af1ec09777cd77c59665a` |
| `.dev/docs/tmp/260822-review-pidfile-dir-refusal-opus.md` | [`restart-handover/history/260822-review-pidfile-dir-refusal-opus.md`](../restart-handover/history/260822-review-pidfile-dir-refusal-opus.md) | `3a3d5ab3e802ddc7fd0a188e73aefea4ab3a8d99bb76866e23878c3ea8250203` |

迁移前对两个精确 source 计算 SHA-256；迁移后对 destination 重算，两个 digest 均相同。因此归口只改变了位置。

## 与既有证据的关系与时点边界

`260822-pidfile-missing-forensics.md` 是事故的一手时间线；两份 `port-scoping` 评审是第一批“端口入名＋缺前任告警”改动的时点评审。本次两个 `pidfile-dir-refusal` 原件评价后续第二批 `pidfile_dir`、活记录拒绝／force override 与 `--fd` 冲突处理，故是补充关系，不取代前一批证据。

两个补充评审也不是可合并的 current verdict：GPT 原件绑定 `HEAD 80068ebb5737` 的指定 8 文件未提交 diff；Opus 原件绑定 2026-08-22T15:18:04+00:00 的独立 8 文件快照，并记录评审期间实现仍在变化。History README 已逐项写入该关系与边界；任何结论均只适用于自身输入，不自动外推 current code／config／运行态。

## 检查结果

- 两个精确 `.dev/docs/tmp/` source 均已不存在，两个 canonical destination 均存在：`PASS`。
- destination SHA-256 与迁移前 source SHA-256 一致：`PASS`。
- `restart-handover/history/README.md` 包含两个相对链接，且其文件目标可解析；README 也明确了与 forensics／port-scoping 证据的关系及两个评审的不同快照边界：`PASS`。
- 已检查本报告与 history README 的 Markdown trailing whitespace：`PASS`。

未运行源码测试：本次仅移动两份 Markdown 原件、更新 history index 并记录迁移结果。
