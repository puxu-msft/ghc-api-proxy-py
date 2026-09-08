# GHE Device Flow conformance evidence migration

日期：2026-09-08

## 迁移

| 项目 | 路径 |
|---|---|
| Source | `.dev/docs/tmp/260822-ghc-api-conformance-summary.md` |
| Destination | `.dev/docs/ghe-device-flow/history/260822-ghc-api-conformance-summary.md` |

该文件是 2026-08-22 的 point-in-time conformance 证据，已归入 `ghe-device-flow/history/`；未改写其历史内容。新增或更新的 history README 说明了该性质及 current authority 边界。

## 引用更新

- `ghe-device-flow/deferred.md` 的 D-3 引用已改为相对 Markdown link。
- `ghe-device-flow/spec.md` 的对应 D2 引用已改为相对 Markdown link。

## 验证

- Source 已不存在，Destination 存在。
- 两个 living 文档中的引用均解析到 `history/260822-ghc-api-conformance-summary.md`。
- history README 与本迁移报告均位于 `.dev/docs/ghe-device-flow/` 允许范围内。
- 除获授权移动的 source 文件外，未修改 `.dev/docs/` 其它目录；未执行 `git add`、`commit` 或 `push`。
