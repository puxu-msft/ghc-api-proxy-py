# 顶层 `tmp/` request-shape 证据迁移

**日期**：2026-09-08
**依据**：`tmp` final disposition ledger，即现归档于 [history/260822-review-disposition-manifest.md](../history/260822-review-disposition-manifest.md) 的第 7 节所列五份时点记录。
**范围**：仅移动下表五份顶层 `.dev/docs/tmp/` 原件到本主题 `history/`，并更新本主题 history 索引；原件正文未改写。

## 迁移与完整性核对

| 原始路径 | 目标路径 | SHA-256（迁移前后相同） |
|---|---|---|
| `.dev/docs/tmp/260820-system-reminder-wire-shapes.md` | `history/260820-system-reminder-wire-shapes.md` | `d16fb8db3e6a82bbbb7815c700e71be30596d312d60ee7ca2efa522663934329` |
| `.dev/docs/tmp/260822-header-forwarding-surface.md` | `history/260822-header-forwarding-surface.md` | `b96dd00c7d5d13d3511482bea3669325511f82e3f2f16f96ae731154b73ab841` |
| `.dev/docs/tmp/260822-review-closeout-claims.md` | `history/260822-review-closeout-claims.md` | `7d33783a7228cd4ca6cf90363a88efab2c9c5a04c60f909c0d2112cf7b4e5305` |
| `.dev/docs/tmp/260822-review-disposition-manifest.md` | `history/260822-review-disposition-manifest.md` | `f865e3f68c4f8d88e4267829345673374a0b640e0a5f5db54a766b67add55807` |
| `.dev/docs/tmp/260822-verify-beta-flag-strip-docs.md` | `history/260822-verify-beta-flag-strip-docs.md` | `67beb648be6a77a6572f5f4549d7d028cdcffd0d30130d1e9bbe02ce921c13cc` |

## 验证

1. 五个 destination 均存在，五个授权 source 均不存在。
2. `sha256sum` 在移动前后对每份原件一致，证明迁移没有改写原件内容。
3. [history/README.md](../history/README.md) 已为五份材料逐条保留 `tmp` 来源、日期、时点证据边界与 current carrier；没有将历史 agent 结论、SDK/第三方观察或当时的工作树状态升级为用户裁决。
4. 本次未移动、删除或修改表外 `tmp/` 文件，也未修改本主题以外的路径。
