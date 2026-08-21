# Go 协议桥参考调查：Anthropic ↔ OpenAI Responses

## Verdict

**可参考，但不可整套照搬。** `CLIProxyAPIPlus` 擅长细粒度 SSE 状态、并行 tool 分桶和终态延迟，但只注册经 Chat Completions 中转的两段桥；`awsl-maxx` 有 Claude↔Responses 直接注册，然而 Claude→Responses 流仅覆盖文本且事件不标准。

1. **门禁与 HEAD。** `/home/xp/src/copilot-api-js/refs/CLIProxyAPIPlus` 的物理 Git 根是 `/home/xp/src/refs/CLIProxyAPIPlus`；同一 shell 调用验证 `pwd -P == git rev-parse --show-toplevel`，HEAD `0c48ef58e0d37220367401b8f7cf689e2e50a701`，结束时状态为空。另一相关 Go repo `/home/xp/src/refs/awsl-maxx` 同样通过门禁，HEAD `03d018fac3645b14d7b6d51b223b2148227c8992`，状态为空。

2. **接线。** `CLIProxyAPIPlus` 分别注册 Claude→Chat 与 Responses→Chat：`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/claude/init.go:10`、`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/init.go:10`；可组合但不是 direct bridge。`awsl-maxx` 在 `/home/xp/src/refs/awsl-maxx/internal/converter/claude_to_codex.go:12`、`/home/xp/src/refs/awsl-maxx/internal/converter/codex_to_claude.go:12` 直接注册双向桥。

3. **Chat→Responses 状态机。** `CLIProxyAPIPlus` 状态含 `Started/CompletionPending/CompletedEmitted/Seq/NextOutputIx` 及消息、reasoning、function 的 added/done 集合：`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response.go:20`。首帧发 created/in_progress（`:311`），item 经 added→delta→done（`:368`、`:405`、`:486`），finish 仅置 pending（`:520`、`:611`），`[DONE]` 才唯一发 completed（`:229`）。可复用“两阶段终结”，以收齐 late usage。

4. **并行 tool 分桶。** tool key 是 `choice index + tool index`：`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response.go:281`、`:467`；各类 output 共用单调 index 并按 index 排序。可复用，避免多 choice/tool 串参数或撞 `output_index`。

5. **Chat→Claude block。** `CLIProxyAPIPlus` 的 thinking/text/tool 共用动态 block index，类型切换前关闭当前 block：`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/claude/openai_claude_response.go:158`、`:162`、`:190`、`:246`。tool arguments 累积至 finish 或 `[DONE]`，再一次性发 `input_json_delta` 并 stop（`:290`、`:298`、`:340`、`:361`）。显式 start/index/stop 可复用；要求真增量时不可照搬终态合并。

6. **Responses→Claude 直接流。** `awsl-maxx` 状态只有 `HasToolCall/BlockIndex/ShortToOrig`：`/home/xp/src/refs/awsl-maxx/internal/converter/codex_to_claude.go:20`。映射 created→message_start（`:147`），reasoning summary→thinking block（`:160`～`:190`），content→text block（`:192`～`:221`），function→tool_use block（`:223`～`:276`），completed→message_delta/stop（`:279`）。顺序单流可参考；交错并行不可采用单一全局 `BlockIndex`，应按 item/output/content id 分桶。

7. **Claude→Responses 直接流不可照搬。** `/home/xp/src/refs/awsl-maxx/internal/converter/claude_to_codex.go:239`～`:278` 仅处理 message_start、text_delta、message_stop，并发 `response.created`、非标准 `response.output_item.delta`、`response.done`；缺 thinking/signature/tool input/usage 及标准 added/done/completed，不是完整桥。

8. **reasoning 边界。** `CLIProxyAPIPlus` 仅接受 assistant `thinking`，忽略 user/system thinking，并丢弃 `redacted_thinking`：`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/claude/openai_claude_request.go:147`～`:159`。角色门禁可复用；若要跨轮保留 Anthropic signature/provenance，丢弃不可视为等价。

9. **tool 邻接。** Claude text/thinking/tool calls 合并为一个 assistant Chat message，tool result 先于同轮用户文本，以保持 OpenAI 邻接：`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/claude/openai_claude_request.go:165`～`:188`、`:209`～`:239`。邻接不变量可复用；中转会丢原始 block 交错顺序，不适合 shape fidelity。

10. **非流直接映射与策略。** `awsl-maxx` 的 tool_use/result↔function_call/output 在 `/home/xp/src/refs/awsl-maxx/internal/converter/claude_to_codex.go:86`～`:123`、`/home/xp/src/refs/awsl-maxx/internal/converter/codex_to_claude.go:77`～`:108`。Responses effort→Claude output_config 在后者 `:39`；反向缺省注入 medium/summary=auto 在前者 `:150`～`:167`。结构可复用，默认值属于产品策略，不应照搬。

11. **强测试证据。** `CLIProxyAPIPlus` 覆盖 `[DONE]`/late usage/无 usage（`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response_test.go:27`～`:137`）、多 tool 隔离（`:141`～`:242`）、跨 choice index（`:244`～`:326`）、混合输出和完成顺序（`:328`～`:421`）；Claude reasoning/tool 邻接见 `/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/claude/openai_claude_request_test.go:11`、`:38`、`:251`、`:393`、`:649`。测试维度可复用。

12. **薄测试警告。** `/home/xp/src/refs/awsl-maxx/internal/converter/claude_codex_test.go:8` 仅查基本 input，`:37` 仅查非流 tool stop reason，`:68` 的流测试只断言调用不报错；没有核事件名/顺序/index/reasoning/tool args/usage/exactly-once。其绿灯不能证明互操作。

13. **验证口径。** 未执行 `go test`，因为用户限定唯一可写路径，而 Go 会写 build/test cache。结论锚定上述两个 HEAD，来自最终源码、注册接线、测试源码与空工作树；没有把“测试存在”写成“测试通过”。
