# direct-passthrough provenance 迁移

**日期**：2026-09-08
**范围**：完成 retirement reference map 的 R-16／R-17，并把 direct-passthrough 对已迁走 request-shape 原件的两处承重引用改为唯一 canonical link。

## 原件迁移

| 原始路径 | 目标路径 | 归属与边界 |
|---|---|---|
| `.dev/docs/git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition-recheck.md` | `.dev/docs/dotdev-repository-repair/history/260904-dotdev-dirty-inventory-disposition-recheck.md` | R-16；2026-09-04 的仓库脏文件处置复核 provenance，不是产品合同。 |
| `.dev/docs/git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus.md` | `.dev/docs/dotdev-repository-repair/history/260904-dotdev-merge-review-gpt-opus.md` | R-17；2026-09-04 的仓库合并候选复核 provenance，不是产品合同。 |

两个原件以移动方式归入 repair 主题，正文未改写。新增 [history/README.md](../history/README.md) 记录其原始路径、时点证据边界和“仓库治理 provenance、非产品合同”的归类。

## 链接改写

| 引用方 | 原目标 | 新目标 |
|---|---|---|
| `direct-passthrough/spec.md` §2.6 | `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md` 的 code span | [`../anthropic-direct-request-shape/history/260822-round2-disposition.md`](../../anthropic-direct-request-shape/history/260822-round2-disposition.md) |
| `direct-passthrough/deferred.md` D-4 | `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md` 的 code span | [`../anthropic-direct-request-shape/history/260822-round2-disposition.md`](../../anthropic-direct-request-shape/history/260822-round2-disposition.md) |
| `direct-passthrough/spec.md` §12 v22 provenance | `../git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition-recheck.md` | [`../dotdev-repository-repair/history/260904-dotdev-dirty-inventory-disposition-recheck.md`](../history/260904-dotdev-dirty-inventory-disposition-recheck.md) |
| `direct-passthrough/spec.md` §12 v22 provenance | `../git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus.md` | [`../dotdev-repository-repair/history/260904-dotdev-merge-review-gpt-opus.md`](../history/260904-dotdev-merge-review-gpt-opus.md) |

链接表中的展示链接以本报告所在目录为基准；实际 direct-passthrough 文本分别使用其自身可解析的 `../anthropic-direct-request-shape/history/...` 与 `../dotdev-repository-repair/history/...` 相对目标。

为满足 direct-passthrough 内所有 Markdown link 的解析检查，另将历史 round-9 report 中建议文字的相对链接由 `spec.md` 校正为 `../spec.md`。这只修正了 link target；评审结论和其他历史记录未改写。

## 验证

1. Anthropic request-shape canonical 原件和两个新的 repair history 目标均存在；`git-housekeeping/reports/` 下的两个旧源均不存在。
2. `direct-passthrough/spec.md` 与 `deferred.md` 不再包含本次替换的 `sync-refs` 或 `git-housekeeping` 旧目标。
3. 对 `direct-passthrough/` 全部 Markdown 文件解析相对本地 Markdown targets，结果为 `direct_passthrough_markdown_links=ok`。
4. `git diff --check` 对本次允许范围通过。

## 未做事项

- 未改动任何产品源码、测试、配置或人控合同；没有改变产品行为或产品合同的语义。
- 未移动、删除或修改 `git-housekeeping/reports/` 的其它文件。
- 未删除 `git-housekeeping` 主题，也未处理 reference map 中的其它迁移项。
- 未执行 `git add`、`commit` 或 `push`。
