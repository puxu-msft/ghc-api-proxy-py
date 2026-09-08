# Residual ledger token-counting history migration

## 执行摘要

- 执行日期：2026-09-08
- 工作目录：`/home/xp/src/ghc-api-proxy-py`
- 来源账本：`.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md`
- 筛选条件：逐行 `disposition = canonical history`，且 exact `destination` 以 `.dev/docs/token-counting/history/` 开头。
- 执行结果：6/6 项完成 exact source→destination move；0 项覆盖；0 项 delete 行处理。
- 索引：已在 [`history/README.md`](../history/README.md) 登记 destination、provenance 与 evidence family。

本次只移动 ledger target 前缀下的六个 exact source，并修改 token-counting history index 与本报告；未编辑任何原件内容，未修改其它主题文件，未执行 `git add`、commit 或 push。

## 逐项 provenance 与验证

以下 SHA-256 是迁移后 destination 的完整文件摘要。移动命令使用 `mv --no-clobber`，并在每项执行前要求 source 存在、destination 不存在；因此不会覆盖既有 destination。每项执行后再次验证 source absent 与 destination present。`mv` 为原件保真移动，未经过重写或重新生成。

| # | ledger exact source | canonical destination | provenance / family | SHA-256（destination） | source absent | destination present |
|---:|---|---|---|---|---|---|
| 1 | `.dev/docs/archived-2604-rewrite/hooks-tokenization-spec.md` | `.dev/docs/token-counting/history/hooks-tokenization-260717/hooks-tokenization-spec.md` | `EF-2604-TOKEN`；260717 Hooks/Tokenization 历史 oracle | `1a8b8ba4c1182d2a815bf19549fba6fe5725c5150740be8f90a75bd1a51e6086` | PASS | PASS |
| 2 | `.dev/docs/archived-2604-rewrite/tokenization.md` | `.dev/docs/token-counting/history/2604-rewrite/tokenization.md` | `EF-2604-TOKEN`；旧 token wire-contract provenance | `778a5a98f870fa70349aa665e70af451bfea151d480db994d932a26d562ce365` | PASS | PASS |
| 3 | `.dev/docs/count-tokens/reports/260816-count-tokens-review.md` | `.dev/docs/token-counting/history/count-tokens/reports/260816-count-tokens-review.md` | `EF-2604-TOKEN` successor family；provider-chain 接线评审 | `e6d38e95502c10de5988ff244065877fe2e9072417c8f4217c614d24959ff532` | PASS | PASS |
| 4 | `.dev/docs/count-tokens/reports/260820-review-responses-token-counting.md` | `.dev/docs/token-counting/history/count-tokens/reports/260820-review-responses-token-counting.md` | `EF-2604-TOKEN` successor family；Responses estimator 与 mutation 证据 | `4a28b367d72a52d4796b09fa208cf8b78047c0c679e1c18595765de9dfc2b188` | PASS | PASS |
| 5 | `.dev/docs/count-tokens/reports/260824-heterogeneous-count-tokens-measurement.md` | `.dev/docs/token-counting/history/count-tokens/reports/260824-heterogeneous-count-tokens-measurement.md` | `EF-2604-TOKEN` successor family；314 次真实测量证据 | `11afb5679b2a9cfc19f5988feb073330f0f23027fc2135afccb3d8310868ef73` | PASS | PASS |
| 6 | `.dev/docs/early-verification/archive-260717-hooks-tokenization/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` | `.dev/docs/token-counting/history/hooks-tokenization-260717/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` | `EF-2604-TOKEN`；与 260717 spec 共址的 acceptance matrix/PASS | `5c3c49860987001ceb902caceff36b4e5b3baab9d5e3e753f60f5096175bf9d5` | PASS | PASS |

## 机械检查

逐项执行的移动前置条件与结果：

```text
test -f "$source"
test ! -e "$destination"
mkdir -p "$(dirname "$destination")"
mv --no-clobber -- "$source" "$destination"
test ! -e "$source"
test -f "$destination"
```

六项均通过。随后对六个 destination 执行 `sha256sum`，摘要记录于上表；对六个 source 执行 `test ! -e`，全部报告 `source absent`。

## 范围与未执行项

- 只处理 `canonical history` 且 destination 属于 `.dev/docs/token-counting/history/` 的 ledger 行。
- 未处理 ledger 中任何 `delete` 行。
- 未移动其它 destination 前缀的 canonical-history 行。
- 未删除空目录或候选目录。
- 未编辑六份历史原件内容。
- 未修改 source 外的其它文档、源码、测试或配置。
- 未执行 `git add`、commit、push。
- 工作树中原有的非本任务修改与 untracked 路径保持不动。
