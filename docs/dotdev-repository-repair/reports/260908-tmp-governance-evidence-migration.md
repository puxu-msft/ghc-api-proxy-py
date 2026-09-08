# 顶层 tmp 治理证据归档

**日期**：2026-09-08
**范围**：将获准的 13 份 `.dev/docs/tmp/` 仓库文档治理 / shared-index 过程证据移动至 `dotdev-repository-repair/history/`。原件内容未改写。

## 归类

这些材料是仓库文档治理、shared-index 演进和 repair 决策的 historical provenance，供解释当时的操作、评审和处置链使用。它们不是产品的 current authority；当前产品行为仍以对应产品主题的 living 文档和用户控制文档为准。

历史索引已更新为 [`../history/README.md`](../history/README.md)，并明确关联：

- `2afa0c4` 的 hash map、独立 review 与 review disposition；
- 代码文档 citation 的 mapping review、coverage review 与 disposition。

## 移动与逐份验证

验证方法：迁移前记录每个源文件的 SHA-256；迁移后逐份确认 `tmp/<name>` 不存在、`history/<name>` 存在，并将目标 SHA-256 与迁移前值比较。下表的 `yes` 表示三项均通过。

| 文件 | SHA-256（迁移前 = 迁移后） | source absent | destination present | hash unchanged |
|---|---|---:|---:|---:|
| `260820-review-session-closeout.md` | `c167b7af66e79c262d555d78027d903b3ac0410194ea8db30125df8fb628b4db` | yes | yes | yes |
| `260821-shared-index-left-reverting-head.md` | `0b0afc0821c1bc99922824371227c885bb3b171370aa514100ffbf3a1014818d` | yes | yes | yes |
| `260822-audit-other-stale-blobs-committed.md` | `9dcd2322e695756bc359363192fa033cc09a6442f8b545baa9bcccf80a6dce0d` | yes | yes | yes |
| `260822-candidate-docs-refresh-log.md` | `2a2dab7eb88b78ebcc17aa2ce11d4c42e73b221af68c28ab971960e0ec0916c3` | yes | yes | yes |
| `260822-candidates-vs-user-updates-reconciliation.md` | `68524a55e8913c1a2f4e28a61e12db2e8a91bee1ab148763d2e2a7a33a71df8a` | yes | yes | yes |
| `260822-doc-citations-review-disposition.md` | `694cb3dd0983a5eb01bb3d20c15256ccb7c17118455e6e75dcf26bfa1bcd3432` | yes | yes | yes |
| `260822-review-doc-citations-coverage.md` | `a03c6060103e3c2f0ea1b4c85a3a46a6dc18483b0c669306124d44dcf6e8cf6e` | yes | yes | yes |
| `260822-review-doc-citations-mapping.md` | `f95f6e31cfc43623a540c4b0a360169166ca77396ff6b929da8662ee248ce42b` | yes | yes | yes |
| `260822-review-split-2afa0c4.md` | `87bdc86d4e33398be0b514a38bb984c1736667fee4ffc7f22054cb1a67134ed0` | yes | yes | yes |
| `260822-split-2afa0c4-hash-map.md` | `5a743aaa8e68642293f72d906f45eb71cabe5dc80c1be042b9eb3bd439c49aed` | yes | yes | yes |
| `260822-split-2afa0c4-review-disposition.md` | `ff722c333408584c722b8b14f8c6cb1a07ed81e30f5ecfdf3348c39c42173583` | yes | yes | yes |
| `260824-spec-freeze-encoding-inventory.md` | `d3aaa5b08e8a9cb829f21208fcf242f747cebb021b0d2f3f950092fb72ddf0af` | yes | yes | yes |
| `260827-ledger-cleanup.md` | `a040be5a44f57ad78ea28f781fb1f4d9aab5db9227b49843647291d97d98a139` | yes | yes | yes |

目标路径均为 `.dev/docs/dotdev-repository-repair/history/<同名文件>`。

## 未做事项

- 未改动 `.dev/docs/dotdev-repository-repair/README.md`。
- 未改动任何 ledger 内容；`260827-ledger-cleanup.md` 只是作为历史原件移动。
- 未移动、删除或修改授权清单以外的 `.dev/docs/tmp/` 文件。
- 未执行 `git add`、`commit` 或 `push`。
