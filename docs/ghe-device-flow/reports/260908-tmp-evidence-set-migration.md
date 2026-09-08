# GHE conformance evidence set 迁移报告

日期：2026-09-08

本次按 tmp final disposition ledger 将六份 GHC API conformance 底稿作为同一 evidence set 归档。文件内容未改写，仅改变路径。

## Source → Destination 与 hash

| 文件 | Source | Destination | Source 初始 SHA-256 | Destination SHA-256 |
|---|---|---|---|---|
| auth | `.dev/docs/tmp/260822-ghc-api-conformance-auth.md` | `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-auth.md` | `679393e389633e1c89150fb8a64b04cf5ab70aaa2cd8777cf36bfadaabea5da4` | `679393e389633e1c89150fb8a64b04cf5ab70aaa2cd8777cf36bfadaabea5da4` |
| baseurl | `.dev/docs/tmp/260822-ghc-api-conformance-baseurl.md` | `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-baseurl.md` | `333957e46e7bc6a7f6d094c7d26b38afff1ecc284ae9bd2f72e66b1c851581c7` | `333957e46e7bc6a7f6d094c7d26b38afff1ecc284ae9bd2f72e66b1c851581c7` |
| crosscheck | `.dev/docs/tmp/260822-ghc-api-conformance-crosscheck.md` | `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-crosscheck.md` | `55791a7290761dc59252f3a57bde07256c0377ac9cd37e7e686569b9a028816a` | `55791a7290761dc59252f3a57bde07256c0377ac9cd37e7e686569b9a028816a` |
| direct-paths | `.dev/docs/tmp/260822-ghc-api-conformance-direct-paths.md` | `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-direct-paths.md` | `66e7d32d3d26ff3e1069cfc3657a612518c4fcd93292230eed766e0fa629998c` | `66e7d32d3d26ff3e1069cfc3657a612518c4fcd93292230eed766e0fa629998c` |
| responses-ws | `.dev/docs/tmp/260822-ghc-api-conformance-responses-ws.md` | `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-responses-ws.md` | `2829ea23dc09dd179c7e156517d3ff4755d5c7f7d20b9dfb1f024ff7096d461b` | `2829ea23dc09dd179c7e156517d3ff4755d5c7f7d20b9dfb1f024ff7096d461b` |
| summary-review | `.dev/docs/tmp/260822-ghc-api-conformance-summary-review.md` | `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-summary-review.md` | `f3464447107eea9d8740b81d35d58cf83dd08d9e69eaac69e38d004d6746c713` | `f3464447107eea9d8740b81d35d58cf83dd08d9e69eaac69e38d004d6746c713` |

## 验证结果

- 六个 source 路径均已不存在。
- 六个 destination 路径均存在于 `ghe-device-flow/history/`。
- 每份 destination 的 SHA-256 均与移动前 source hash 一致，确认内容未变。
- `history/README.md` 已逐项建立可解析链接，并说明六份底稿与 conformance summary/评审属于同一时点 evidence set。
- 未修改或移动上述清单之外的文件；未执行 `git add`、`commit` 或 `push`。
