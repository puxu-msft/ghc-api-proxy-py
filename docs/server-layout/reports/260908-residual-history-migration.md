# residual ledger：`server-layout` canonical-history 实施报告

**实施日期**：2026-09-08
**执行范围**：candidate residual disposition ledger 中 destination 位于 `.dev/docs/server-layout/history/`、disposition 为 `canonical history` 的全部行。
**范围外**：未处理任何 `删除` 行；未移动 destination 不属于 `server-layout` 的行；未编辑原件正文；未执行 `git add`、commit 或 push。

## 实施输入与选择

输入为 `.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md`。按其 “按 retained target topic 汇总”，`server-layout` 恰有 12 行：EF-ARCH 的 9 份 `architecture-audit` 报告及 EF-TEST 的 3 份 `test-infrastructure` 报告。所有 12 个 source 和 12 个 destination 均为不同的精确路径。

迁移前逐一确认每个 source 是 regular file、每个 exact destination 在仓库中计数为 0；因此没有覆盖既存文件。迁移以 rename 完成，未改变原件字节。

## 逐项 source → destination 与 SHA-256

| # | Source（迁移前） | Destination（迁移后） | SHA-256（迁移前后相同） |
|---:|---|---|---|
| 1 | `.dev/docs/architecture-audit/reports/260814-audit-dependency-graph.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-dependency-graph.md` | `46e0b38d2ed8bc7e0f5e5d59cc791834e7c474a641f619525cc7ea38849d4683` |
| 2 | `.dev/docs/architecture-audit/reports/260814-audit-duplication.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-duplication.md` | `e82410653aab82f117d11c6c0b5a572b2adaaf2b6a5ec9a7e5456b043bf65e34` |
| 3 | `.dev/docs/architecture-audit/reports/260814-audit-library-alternatives.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-library-alternatives.md` | `120f6b3e562f1cecfcf8fa5c2d063fd21257e55fc37e6054cd03dbe0e9c1dffb` |
| 4 | `.dev/docs/architecture-audit/reports/260814-audit-lifecycle-ownership.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-lifecycle-ownership.md` | `74807b34432ea4afdf6e97fbaf79ce48c109b1f9502d250cf99e2404d108736c` |
| 5 | `.dev/docs/architecture-audit/reports/260814-audit-module-boundaries.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-module-boundaries.md` | `44edc8da1b25e5a6131fec95c5ff6d4957b1e1bb5176e8cd74199d923d97ec07` |
| 6 | `.dev/docs/architecture-audit/reports/260814-audit-test-structure.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-test-structure.md` | `f20fc53b4f34a7552b16dd4ab2b6af1d2b9d6fba72045feb3a2d88199d8bbcd4` |
| 7 | `.dev/docs/architecture-audit/reports/260814-audit-typing-leaks.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-audit-typing-leaks.md` | `b33514763805035bd62e0e8d586fb1956753a3a7c1d8a4afe430207e3c5b2abb` |
| 8 | `.dev/docs/architecture-audit/reports/260814-synthesis-gaps.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-synthesis-gaps.md` | `d2ded257334bcd0190f77de9a2ba49e9af8c9262eafc06d1a33cbbc13fbc6c88` |
| 9 | `.dev/docs/architecture-audit/reports/260814-synthesis-vs-proposal.md` | `.dev/docs/server-layout/history/architecture-audit/reports/260814-synthesis-vs-proposal.md` | `b831bfbc6066b046f38786874339ccc5579e407efb38aff529f42b7153d66347` |
| 10 | `.dev/docs/test-infrastructure/reports/260818-vcrpy-poc.md` | `.dev/docs/server-layout/history/test-infrastructure/reports/260818-vcrpy-poc.md` | `34e5e66de2d782abb5a8f8852d6edf3d839317ead5bc7da0a7c876385fdcfce2` |
| 11 | `.dev/docs/test-infrastructure/reports/260820-test-hygiene-two-defects.md` | `.dev/docs/server-layout/history/test-infrastructure/reports/260820-test-hygiene-two-defects.md` | `803b156e935aa04c9100514f0196e8598350a13a61127342cc15cf977988b8ca` |
| 12 | `.dev/docs/test-infrastructure/reports/260820-unit-smoke-combined-hang.md` | `.dev/docs/server-layout/history/test-infrastructure/reports/260820-unit-smoke-combined-hang.md` | `467385771909dcdca3b4004e5978a8a8dee3ff5c812300eb19dd523feeb22dc0` |

## 实施后复核

对上表每一行均执行：

1. destination 为 regular file 且 SHA-256 等于迁移前 source 的记录值；
2. exact source 路径不存在；
3. exact destination 路径存在；
4. 从仓库根以完整 destination path 搜索，计数为 1。

结果：`source_absent=12`、`destination_present=12`、`sha256_unchanged=12`、`unique_exact_destination=12`、`destination_collisions=0`。迁移前的 exact destination 计数均为 0；迁移后均为 1。

## history index 与时点边界

`.dev/docs/server-layout/history/README.md` 已新增两组来源索引，并明确：

- EF-ARCH 原件来自旧 `.dev/docs/architecture-audit/reports/`，记录 2026-08-14 的审计；
- EF-TEST 原件来自旧 `.dev/docs/test-infrastructure/reports/`，记录 2026-08-18 至 08-20 的实验与诊断；
- 旧主题路径、正文内旧路径、当时观察和结论均不是 current authority；
- 当前状态、现行设计决策和测试合同必须以 `server-layout` 现行文档、当前代码及现行测试为准。

## 受限范围留下的后续动作

ledger 对 `260818-vcrpy-poc.md` 标记 “EF-TEST+改链”：`tests/int/recorded/cassettes.py:3` 是其 current consumer，要求与移动原子改链。本次唯一所有权只允许修改 `.dev/docs/server-layout/history/` 和新建本报告，禁止修改 `tests/`；故未改该注释。调用方应在获授权的后续变更中将该引用改为上表第 10 项 destination，并复核链接/注释可解析性。
