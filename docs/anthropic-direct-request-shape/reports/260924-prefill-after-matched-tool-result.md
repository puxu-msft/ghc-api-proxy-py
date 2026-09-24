# 2026-09-24 再现的 prefill 400：捕获与隔离正反对照

**基线与保密范围：** 4141 运行进程仍是用户于 2026-09-23 10:48:52 自行启动的实例；本轮只读查询本机已按 session 规则捕获的 full-transport CBOR，不输出或转存请求正文、认证头、工具输出、推理签名或密文。隔离 4142 从干净的 `main@061aff32` worktree 启动，使用专用临时 HOME/XDG 与原有凭据文件的私有副本，只发送自造的非敏感短文本；退出时清理 own child、listener、token 副本和 worktree，4141 的 owner 未改变。

## 真实故障和对照

- 捕获请求 `f5859c05-9288-4995-9908-25404b3783c7` (`sonnet → ghc-msft/claude-opus-5.5`) 的 `request.body` 与 `upstream.request.body` 都有 26 个 messages，最后三条都是 assistant（含 thinking/tool_use）、user（非空 tool_result）、system（text）。末尾 tool_result 的 ID 与最近的 tool_use 匹配；实际发送后上游返回 400 `invalid_request_error`，消息是 assistant message prefill。
- 同一客户端 session 更早的 `79983fc2`、`10f39bbc`、`a02209c4` 三次请求均解析到同一目标模型，有相同的末尾角色／工具配对、相同的 `anthropic-beta`、`anthropic-version`、adaptive thinking、high effort 与 `clear_thinking_20251015 keep=all`，真实上游均得 200。其中 `79983fc2` 的尾部 assistant block 顺序也同为 thinking/tool_use/thinking；因此这些形状单独都不是充分的失败判据。请求体大小约从 299 KB 增长到 318 KB，但这只是相关性，不证明尺寸触发了 prefill。
- 4142 四条最小合成请求：单 user → 200；user 后 system → 200；配对的 tool result 后 system → 200；给后一种再附 user `Please continue.` → 400，但不是 prefill 400。合成探针没有重现生产失败；不能把“增加 user 后就好”当成已经验证的修法。

**已排除：** 代理删除了最后一个 user turn（真实出站仍有它）；工具结果是孤儿／空内容（匹配且非空）；只要末尾是 system 就必败（前述真流量与合成探针均反例）；仅 thinking/tool_use/thinking 顺序必败（有 200 对照）；改 header／thinking policy 导致这一次失败（对照一致）。**未排除：** 请求增长、先前历史内容、上游特定验证分支或负载分配，以及它们的组合。不能单凭 HTTP 400 的措辞把根因归到任一项。

**状态与下一步：** prefill 故障再次发生，尚未 `fixed`；没有改生产的 prefill 逻辑，也没有触碰 4141。此问题归属本主题 Spec §6.6；下次若要修复，先用不含私密正文的可控合成历史或经用户明确许可的更窄样本复现同类 400，并做一次只改变一个变量的正反实验。项目人控 `upstream-retry-and-continuation.md` 把 400 列为不可续写，因此不能自行加“先吃 400 再补 user 重试”的 workaround。
