# History 当前状态

日期：2026-09-14  
状态：**主体 slice 已落地；durability hardening deferred**

## 已落地

- immutable `HistoryEntry` projection；
- semantic payload、capture reference 和 transport envelope；
- bounded async writer、SQLite hot index、durability receipt；
- list/detail、keyset pagination、filters、semantic/transport/full export；
- archive state、pin/unpin、retention candidates。

主要提交：`4008bb5e`、`55d035dd`、`76fe7eab`。

## 当前限制

- `HistoryArchiveStore` 的 segment metadata 主要依赖进程内 state；重启后继续 append 的恢复与尾部校验尚未达到 Spec 的完整 durable contract。
- History list/detail 当前返回 session/agent identity metadata；这是 History identity projection 的明确选择，不等同于 raw transport headers/credentials。Raw capture 的 ordinary projection 禁止复制 transport-sensitive identity，二者边界见 Spec 修订记录。
- retention 只提供 pin-aware candidates，不提供 public purge；受控 physical purge 仍属运维流程。

## Verification

History targeted suite、Ruff、Pyright 通过。完整回归的 4 个失败在基线提交上同样出现，归属见 [`../observability/status.md`](../observability/status.md)。
