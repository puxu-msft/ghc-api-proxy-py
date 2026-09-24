# 2026-09-24 prefill 后续隔离对照：消息／工具数量

补充 [`260924-prefill-after-matched-tool-result.md`](260924-prefill-after-matched-tool-result.md) 的点时证据，不覆写前一份原件。

干净的 `main@061aff32` 通过独立 worktree 和私有 HOME/XDG 在备份端口 4142 启动，真实 Copilot 目标为 `claude-opus-5.5`。只发送合成短文本、合成 tool ID 和配对 result，不转发原会话正文、签名或工具结果。分别构造 23 个 message／11 个 tool_use 和 26 个 message／12 个 tool_use，每组 assistant/tool_result/system 交替，设置与故障捕获相同的非凭据 `anthropic-beta` flag、`thinking.type=adaptive`、`output_config.effort=high`、`context_management.clear_thinking keep=all` 与 `max_tokens=64000`。

两条请求均返回 HTTP 200，没有 prefill 400。上述 beta flags 是客户端侧输入，隔离 canary 没有启用全量捕获，不能声称出站头与生产完全相同。子进程和其监听在 `try/finally` 内回收，4142 最终无监听，4141 进程身份未变，凭据副本随独立临时目录销毁。

**成立的结论：** 仅 23→26 个 message、11→12 次配对工具调用和同组非凭据开关，不足以让这个模型必然返回 prefill 400。**不成立的外推：** 合成探针没有线上 318 KB／约 10 万输入 tokens 的历史、原生 thinking signature 或真实正文，不能宣布上游故障根因已找到，也不能凭 200 断言增加 user 消息可修复线上失败。后续若要为线上 400 建修法，仍需可证伪的首次分叉与正向修复对照；既有用户裁决禁止自行对 400 做透明重试。
