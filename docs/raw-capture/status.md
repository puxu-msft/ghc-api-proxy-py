# Raw capture 当前状态

日期：2026-09-14  
状态：**v25 full-header slice 已落地；per-attempt durable capability deferred**

## 已落地

- SQLite rule-selected capture；
- CBOR Sequence + per-item zstd frame；
- bounded writer、reservation、ack、poison path 和安全完成诊断；
- request/upstream/client selected boundaries 的完整 header values；
- capture reference 与 aggregate replay/capability projection。

主要证据：`050f0e3e`、`1c348dfc`、raw-capture targeted tests。v24 只表示 full-header implementation slice 的点时来源，不是 current contract 版本。

## 当前限制

- `RawCaptureObservation` / History attachment 当前保留 aggregate capability；每个 upstream attempt 的 durable capability matrix 尚未完全投影。
- full transport 仍是 credential-sensitive evidence，只能通过显式 transport/evidence projection读取。
- `.dev/human-controlled-docs-candidates/raw-capture.md` 是候选材料，不是 current authority；其中旧配额/旧 provider 文字不得反推 v25。
