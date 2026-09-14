# 可观测性用户控制文档候选

日期：2026-09-14

`docs/.human-controlled/README.md` 当前列出了 `observability.md`，但该文件不存在。本候选不改变用户控制目录，只提供待用户审阅的入口材料。

建议用户控制文档明确：

- LiveObservation、request log、HistoryEntry、CaptureAttachment、Replay result 的边界；
- 普通 projection 与 credential-sensitive transport 的安全边界；
- History identity metadata 与 raw transport identity 的区别；
- RequestJournal/RequestFacts 的事实 owner；
- 主程序不提供 Replay API，Replay 为独立 process。

在用户采纳前，本候选不是产品合同；当前 `.dev/docs/observability/spec.md` 仍是 agent-maintained living contract。
