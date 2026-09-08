# History forensics historical evidence

## Provenance

本目录是 `.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md` 的 EF-HISTORY-FORENSICS canonical-history 落点。2026-09-08 已从计划退役的 `.dev/docs/history/` 精确迁入下列 13 份原件：`proposal.md`，以及 `reports/` 下 12 份 2026-08-20 至 2026-08-21 的 forensic audit、wiring/fixture/gone-scenario 调查、proposal/scope/Spec reviews 和 structured-logging design。迁移逐文件保留原文，并以 SHA-256 pre/post 一致性验证；完整逐项清单与哈希见 [`../../../reports/260908-residual-history-migration.md`](../../../reports/260908-residual-history-migration.md)。

## Evidence boundary

这些材料是时点化的调查、源码或数据库只读核验、设计稿与独立评审的原始证据。它们保留当时的事实、findings、已作废方案及范围争议，不能被解释为当前实现状态、持续有效的 product contract，或重新启用旧 History topic 的依据。特别是 `proposal.md` 的已作废方案部分只作为保真历史，不升级为 authority。

## Current carrier

当前 retry/continuation 行为、实现状态和已验证边界由 [`../../status.md`](../../status.md) 承载；尚未闭合的 forensic/query/replay 工作及其当前决策由 [`../../deferred.md`](../../deferred.md) §24–§26 承载。有关查询面和 §6 decision 的既有 canonical extracts 仍在上级 history 根目录的 `decisions-20260821-query-surface.md` 与 `decisions-20260821.md`；本目录不复制也不取代它们。

## Contents

- [`proposal.md`](proposal.md)：取证能力事实调查及已作废十片方案。
- [`reports/`](reports/)：forensic demand、fixture source、wiring、gone persistence、structured logging 的调查/设计，以及 proposal、scope、Spec 的独立复核原件。
