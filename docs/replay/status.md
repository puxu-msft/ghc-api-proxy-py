# Replay 当前状态

日期：2026-09-14  
状态：**独立 process skeleton 已落地；高风险结果边界 deferred**

## 已落地

- capture-required source gate；
- `client_request` / `upstream_attempt(attempt_id)` selector；
- wire diagnostic；
- semantic/live 的注入式 executor boundary；
- original/current target policy；
- deadline、timeout result、新 replay identity 和 provenance fields；
- client actions return-only，不执行工具。

主要提交：`dc9f2e81`；targeted replay tests 通过。

## 当前限制

- `app.replay` CLI 当前显式禁用，返回 `replay_cli_unavailable`；它不把调用方的 `--capture` 当作 source receipt 或直接读取的路径。现有 `HistoryWriter` 没有可供独立 CLI 安全组装的只读 source-authority seam，因此 CLI 不会绕过 History index/capability gate。semantic/live 仍需要调用方注入 executor。
- `ReplayResult` 尚未完整记录 delivery、execution policy、cancel facts 和 result History reference。
- Replay 不自动持久化新的 History entry；source transport 也不自动内嵌 result。

这些是已接受的实现边界，不应在 Spec/ledger 中写成“完整 result provenance 已完成”。
