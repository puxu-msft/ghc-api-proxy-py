# 历史承重证据迁移

**日期**：2026-09-08
**范围**：将 `sync-refs`、`hooks-subscription-migration` 与顶层 `tmp/` 中属于 Anthropic request-shape 的五份原件归入本主题；不改写原件正文，不修改本主题以外的文件。

## 迁移清单

| 原始路径 | 目标路径 | SHA-256（迁移前后相同） |
|---|---|---|
| `.dev/docs/sync-refs/sxwxs-ghc-api/260822-round2-disposition.md` | `history/260822-round2-disposition.md` | `830a4df34d2f1162628c91e0e43d7bb395ad3dcbd4d9bf86c93b8186d3daa03a` |
| `.dev/docs/sync-refs/sxwxs-ghc-api/260822-vscode-copilot-chat-reasoning-values.md` | `history/260822-vscode-copilot-chat-reasoning-values.md` | `b89557cd7a8d5d47e54f7e4324ab38475d297fb956b988967f68302077c5fe27` |
| `.dev/docs/hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md` | `history/260822-beta-flag-strip-implementation.md` | `8079664fad1d28277fe446543cc7fddad512597bb8b1652ef47328010d6b15a7` |
| `.dev/docs/tmp/260822-review-beta-flag-strip.md` | `history/260822-review-beta-flag-strip.md` | `0b7e4d9da6e1abb6343c264287bfc8f5aecd103d7653ff64490e52ade4ab2ecf` |
| `.dev/docs/tmp/260824-cache-control-scope-400-investigation.md` | `history/260824-cache-control-scope-400-investigation.md` | `3b19a72e0c969b9230e3ffb355377a4d105a6fc82aa18894652f51744933991c` |

`260822-round2-disposition.md` 只在 `history/` 保留这一份 canonical 原件；不得在其它主题复制。其余主题应跨主题链接这个位置。

## current/living 入站链接改写

| map ID / 引用方 | 原引用 | 改写后 |
|---|---|---|
| R-01，`README.md` | code span `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md:62` | [history/260822-round2-disposition.md](../history/260822-round2-disposition.md) 的相对 Markdown link |
| R-04，`spec.md` | code span `sync-refs/.../260822-vscode-copilot-chat-reasoning-values.md` | [history/260822-vscode-copilot-chat-reasoning-values.md](../history/260822-vscode-copilot-chat-reasoning-values.md) 的相对 Markdown link |
| R-05，`spec.md` 证据表 | `.dev/docs/sync-refs/.../260822-vscode-copilot-chat-reasoning-values.md` | [history/260822-vscode-copilot-chat-reasoning-values.md](../history/260822-vscode-copilot-chat-reasoning-values.md) 的相对 Markdown link |
| §4 顶层 `tmp`，`spec.md` | `.dev/docs/tmp/260822-review-beta-flag-strip.md:6` | [history/260822-review-beta-flag-strip.md](../history/260822-review-beta-flag-strip.md) 的相对 Markdown link |
| §4 顶层 `tmp`，`status.md` | `.dev/docs/tmp/260822-review-beta-flag-strip.md:6` | [history/260822-review-beta-flag-strip.md](../history/260822-review-beta-flag-strip.md) 的相对 Markdown link |
| §4 顶层 `tmp`，`spec.md` A-9 | `../tmp/260824-cache-control-scope-400-investigation.md` | [history/260824-cache-control-scope-400-investigation.md](../history/260824-cache-control-scope-400-investigation.md) 的相对 Markdown link |

`260822-round2-disposition.md` 的两处跨主题 current consumer 也必须守住唯一 canonical 原件：R-02 `../direct-passthrough/deferred.md:41` 与 R-03 `../direct-passthrough/spec.md:95` 应各改为相对 Markdown link `../anthropic-direct-request-shape/history/260822-round2-disposition.md`。这两个文件不在本任务所有权内，故未越权修改。

R-19 的引用方 `../hosted-web-search/status.md:83` 属于另一主题。它必须由该主题所有者改为相对跨主题 link `../anthropic-direct-request-shape/history/260822-beta-flag-strip-implementation.md`；本任务的严格所有权禁止修改该文件，故本迁移未越权改写它。

## 验证

1. 五个授权源路径均已不存在，五个目标均存在；迁移前后 SHA-256 一致，证明原件内容未改写。
2. 本主题的 `README.md`、`spec.md` 与 `status.md` 中已不含这五个旧源路径；其承重引用均为解析到 `history/` 的相对 Markdown links。
3. [history/README.md](../history/README.md) 为每份原件保留原始路径、日期、证据边界与 current carrier，明确历史 agent/第三方时点证据不升级为用户裁决。
4. 待 R-02、R-03 与 R-19 的外部所有者完成改链后，重跑保留主题的入站引用扫描，确认没有 current/living 文档再指向已迁走的 `sync-refs` 或 `hooks-subscription-migration` 路径。
