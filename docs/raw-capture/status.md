# Raw capture 当前状态

日期：2026-09-16
状态：**v29 full-header、per-attempt capability 与 total admission cap 已落地**

## 已落地

- SQLite rule-selected capture；
- CBOR Sequence + per-item zstd frame；
- bounded writer、reservation、ack、poison path 和安全完成诊断；
- request/upstream/client boundaries 的保序 full-header values（重复字段不折叠）；
- capture reference 与 aggregate replay/capability projection。
- 每个 upstream attempt 的 writer-acknowledged capability matrix；
- current-format per-file/total admission cap，不自动删除已有 evidence。

主要证据：`541a738b`、RCR-04 final review、v29 targeted tests。旧报告中的 v24/v25
只表示当时的点时实现切片，不是 current contract 版本。

## 当前限制

- full transport 仍是 credential-sensitive evidence，只能通过显式 transport/evidence projection读取。
- 失败 attempt 的 request-level cleanup boundary、独立 HTTP oracle、准备阶段 warning
  hardening 和安全 physical retention 仍见 `deferred.md`；它们不改变 v29 已落地的
  writer-ack matrix 与 full-header contract。
