# GHE Device Flow 历史证据

本目录保存 GHE Device Flow 主题的 point-in-time 证据。这里的材料用于追溯当时的 conformance 检查、裁决与依据，不是当前行为契约；当前行为以主题的 [spec.md](../spec.md) 为权威，未闭合事项以 [deferred.md](../deferred.md) 为准。

## 已归档

- [260822-ghc-api-conformance-summary.md](260822-ghc-api-conformance-summary.md)：2026-08-22 的 GHC API conformance 汇总，包含当时的裁决落地记录、证据权重和未闭合项。本文保留其时点状态，不得将其中的“未经验证”或历史发现改写为当前结论。
- [260822-ghc-api-conformance-auth.md](260822-ghc-api-conformance-auth.md)：GHC auth 调用链核实底稿。
- [260822-ghc-api-conformance-baseurl.md](260822-ghc-api-conformance-baseurl.md)：GHC base URL 需求对照底稿。
- [260822-ghc-api-conformance-crosscheck.md](260822-ghc-api-conformance-crosscheck.md)：四份 conformance 报告的独立交叉复核底稿。
- [260822-ghc-api-conformance-direct-paths.md](260822-ghc-api-conformance-direct-paths.md)：GHC direct driver 端点核查底稿。
- [260822-ghc-api-conformance-responses-ws.md](260822-ghc-api-conformance-responses-ws.md)：Responses WebSocket 现状核查底稿。
- [260822-ghc-api-conformance-summary-review.md](260822-ghc-api-conformance-summary-review.md)：canonical conformance summary 的独立评审底稿。

上述六份底稿与 conformance summary 及其评审共同构成同一套 2026-08-22 GHC API conformance evidence set。summary 中的逐名清单提供原始关联，本文提供可解析的归档索引；不得将这些 point-in-time 材料当作当前实现或验证结论。

### Copilot token identity（2026-08-07）

以下四份材料从退役的 `copilot-token-identity/reports/` exact source 移入本目录，组成 token identity review/audit/verification 的 canonical history family。它们只保留历史 provenance，不改变当前 `spec.md` 的 authority：

- [260807-audit-token-identity-squash.md](copilot-token-identity/reports/260807-audit-token-identity-squash.md)：source/main squash 审计与 archive gate。
- [260807-review-token-exchange-identity-r2.md](copilot-token-identity/reports/260807-review-token-exchange-identity-r2.md)：identity fix 定向终审。
- [260807-review-token-exchange-identity.md](copilot-token-identity/reports/260807-review-token-exchange-identity.md)：首轮 token exchange identity 代码评审。
- [260807-verify-token-exchange-identity.md](copilot-token-identity/reports/260807-verify-token-exchange-identity.md)：scoped 独立验收及其边界。

本 family 的逐项 source/destination、hash 与迁移后校验记录见 [260908-residual-history-migration.md](../reports/260908-residual-history-migration.md)。
