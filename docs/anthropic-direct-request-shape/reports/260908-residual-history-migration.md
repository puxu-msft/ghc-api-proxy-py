# Anthropic request-shape residual history 迁移

**日期**：2026-09-08
**依据**：`.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md` 的逐行 `source → destination` ledger。
**范围**：只实施 destination 位于 `.dev/docs/anthropic-direct-request-shape/history/` 的 17 条 `canonical history` 行：EF-HOOKS 的 4 份与 EF-SYNC 的 13 份。没有处理任何 `删除` 行，没有移动、删除或修改表外路径，也没有执行 `git add`、commit 或 push。

## 迁移与内容完整性

| evidence family | 原始路径 | 目标路径（相对本 topic） | SHA-256（迁移前后相同） |
|---|---|---|---|
| EF-HOOKS | `.dev/docs/hooks-subscription-migration/reports/260820-external-rewrite-surface.md` | `history/hooks-subscription-migration/reports/260820-external-rewrite-surface.md` | `65741db8f9ddb3b07e6ba92e74599805fb779f790a0e19d6f2431e4a7b0e7f2f` |
| EF-HOOKS | `.dev/docs/hooks-subscription-migration/reports/260820-js-rewriter-architecture.md` | `history/hooks-subscription-migration/reports/260820-js-rewriter-architecture.md` | `40553ccb0481bfcd98d680e8b2d473ceb24c2154f96b7203bef1f9464b38d1a9` |
| EF-HOOKS | `.dev/docs/hooks-subscription-migration/reports/260820-sanitize-family-migration-status.md` | `history/hooks-subscription-migration/reports/260820-sanitize-family-migration-status.md` | `99cda9c20dfbe30142354a873a5fab6bd8a36c32e19be18ebcf2eeba21adfed2` |
| EF-HOOKS | `.dev/docs/hooks-subscription-migration/reports/260822-session-closeout.md` | `history/hooks-subscription-migration/reports/260822-session-closeout.md` | `f5ea5665832376424d05973a8841d6f925f30a2fe03888656d70182750412020` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-answer-loss-persistence.md` | `history/sync-refs/sxwxs-ghc-api/260821-answer-loss-persistence.md` | `d035c4fd2505b395d2050a841133cde6722c106311fda8f6e1ce1445352d4126` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-design-thinking-effort-wiring.md` | `history/sync-refs/sxwxs-ghc-api/260821-design-thinking-effort-wiring.md` | `508b04d3261fd96c2bbb0d52a1ab92208c05e161357c1046b928f2132aa484b9` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-ghc-api-lessons-for-us.md` | `history/sync-refs/sxwxs-ghc-api/260821-ghc-api-lessons-for-us.md` | `6bd56d195cdb8cdb9795e9c662d8d99affc77fd897123d19782f83c22bfb7dcf` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-inventory-our-capabilities.md` | `history/sync-refs/sxwxs-ghc-api/260821-inventory-our-capabilities.md` | `c3a2bba1fe19657faf91194f6da36e5aea7a995c4fa39534f12fb3dafea0df91` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-probe-upstream-sanitize-rules.md` | `history/sync-refs/sxwxs-ghc-api/260821-probe-upstream-sanitize-rules.md` | `10b4d230092215044afdef48b7d7085b3ae8ab2f63dbbf846ba5bf0639e691f3` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-review-losses-attribution.md` | `history/sync-refs/sxwxs-ghc-api/260821-review-losses-attribution.md` | `9d90f2d9ff5ee8eba8afd69a9547bb1d4afcf451d782645cca2c96773f704c20` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-round-disposition.md` | `history/sync-refs/sxwxs-ghc-api/260821-round-disposition.md` | `c5a596631cab38955f11a378de8f3c2cbcb584ce00e5e2b1847ac5cd546a5123` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-core-translation.md` | `history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-core-translation.md` | `d70b690a8bf7f936c317889c64bcbedae8ef8cbf271c622163b88dfcb5c7266f` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-observability.md` | `history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-observability.md` | `7694564d54e3735b148d6a0dbfc62a532663a03f6e1eef9acbd1227946740c94` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-periphery.md` | `history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-periphery.md` | `e3166d0d547d8cd34e014086b7ebc36acd366c87b9ab264c5fe9e6dff196fcd0` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-reliability.md` | `history/sync-refs/sxwxs-ghc-api/260821-survey-ghc-api-reliability.md` | `4a43ff6c7bb410ae437a47c993503aa52c55b18d78ebc1d3f195cd4cff6eb0f6` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-verify-ghc-api-claims.md` | `history/sync-refs/sxwxs-ghc-api/260821-verify-ghc-api-claims.md` | `28a46ad057a43f366426dfe236f4b7015e727e8471413c19e994f0533fd1baa4` |
| EF-SYNC | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-verify-our-side-claims.md` | `history/sync-refs/sxwxs-ghc-api/260821-verify-our-side-claims.md` | `c6080cda7ac85b43c20cdb1050c25d8c6a68dbc501e61ab9d7fc098a4cce6cd5` |

## history index 与 authority 边界

[history/README.md](../history/README.md) 已按 source topic 和 evidence family 增列全部 17 份原件，并对每份保留其原始路径。索引明确 EF-HOOKS 与 EF-SYNC 都是时点证据：不因迁移成为 current authority，也不把其中的 agent 判断、外部项目源码调查、真实 probe 或当时的处置记录升级为用户裁决。当前合同和当前实现状态仍分别由 [spec.md](../spec.md) 与 [status.md](../status.md) 承载。

## 验证

1. 移动前逐项确认 17 个 source 均存在、17 个精确 destination 均不存在，且 destination 集合路径唯一。
2. 移动后逐项重新计算 SHA-256；每个 destination 与表中移动前哈希相同，证明原件正文未改写。
3. 移动后逐项确认全部 source absent、全部 destination present；只创建了 ledger 指定的两个 family 子目录。
4. 扫描 17 个完整 destination path，确认各自只出现一次；本次没有复制任何前批 canonical original。
5. `history/README.md` 的新增相对 Markdown links 都解析到上述 destination；报告本身的相对 Markdown links 也解析。
