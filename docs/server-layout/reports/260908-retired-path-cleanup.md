# 2026-09-08 retired path cleanup

## 改动

- 更新 [server-layout README](../README.md) 的权威边界导航表：将旧的 2026-04 rewrite 主题从具体目录路径改为“2026-04 rewrite 旧主题（已整体过期）”。
- 保留完整的负面历史语义：该主题由用户于 2026-08-20 裁定整体过期，且不得引为依据。
- 未新增任何权威来源、设计结论或可引用目标；本次只是消除导航表中删除后会失效的具体路径。

## 理由

MSR-05（见 [merged-state review](../../dotdev-repository-repair/reports/260908-merged-state-review.md)）确认该旧主题已经没有承重 consumer，剩余命中仅是“已作废／禁止作为依据”的历史叙述。导航表不需要继续把它写成可定位的目录；但如果删掉“整体过期”和“不得引为依据”的语义，就会丢失防止误引的历史边界。因此只去掉具体 path，保留否定性警告。

## 链接与路径核查

- `server-layout/README.md` 的该导航表行已不再包含 `archived-2604-rewrite` 具体路径。
- 本报告中的两个相对 Markdown links 均以报告所在目录为基准核查：`../README.md` 与 `../../dotdev-repository-repair/reports/260908-merged-state-review.md` 均指向现存文件。
- MSR-05 另列的 `graceful-shutdown/client-side/README.md` 与 `systemd-runtime/plan.md` 命中位于本次严格所有权之外；本次未修改它们，也未把它们改写成新的 server-layout 权威。
