# Responses stream route 独立代码复评 R2

- **评审范围**：严格只读复评 `/home/xp/src/ghc-api-proxy-py-stream-route` 的 `feat/anthropic-responses-stream-route@bc436af647507df4ea45f3b01ca8942fade4f036`，base 为 `b91e58a29324b11840002efc53ed6f869b800c39`。读取 R1 `docs/tmp/260807-resume-review-code-stream-route.md`、current base→candidate diff、冻结 Spec／Acceptance、最终代码与测试；逐项复核 R1 八项 major，并额外扫描修复引入的 terminal／cleanup 接缝。候选树、Git refs、服务、进程与环境均未修改；唯一仓库写入为本报告。
- **总体 verdict**：**修复 major 后可进入；当前不可 squash。** 0 blocker／5 major。
- **blocker 数**：0。
- **major 数**：5。
- **双视角覆盖证据——机械核对**：每个 load-bearing shell 调用均在同一调用中校验物理 cwd、Git top-level、branch 与完整 `HEAD=bc436af647507df4ea45f3b01ca8942fade4f036`，并比较调用前后候选 `git status` 哈希。逐项对账 R1 八项：disconnect、真实 sink／frontier、postcommit Anthropic error SSE、`incomplete/max_output_tokens`、CRLF／`data:` framing、message content lifecycle、tool arguments typed error、stream History。读取最终 route→delayed ASGI response→parser→typed delivery→frontier→History 调用链及相关测试。候选源码来源 oracle 指向目标 worktree；定向相关测试为 `88 passed`，全仓 pytest 为 `512 passed`，Ruff 为 `All checks passed!`。Pyright 两次被共享终端的外部 `Ctrl-C`／串流污染，未取得可信同调用完成证据，故不把 Pyright 写成通过或失败。
- **双视角覆盖证据——第一人称执行**：模拟并实际运行了首 block 前 disconnect、带 cancellation checkpoint 的 finally cleanup、first-body send outcome uncertain、postcommit protocol failure、token-limit incomplete 有／无 usage、CRLF split 与无空格 `data:`、三层 authoritative text 冲突、malformed／非 object tool arguments、成功／partial／uncertain History，以及 terminal id 不一致和 success terminal 后追加 event。实测错误状态包括：disconnect 后 finally 首个 checkpoint 再收 `CancelledError`；`FIRST／SECOND／THIRD` 三份冲突 text 被成功终止；无 usage 的合法 token-limit terminal返回 `invalid_responses_event`；uncertain frontier 的 History response 为 `None`；`response.created=A` 可由 `response.completed=B` 成功终止；terminal 后 event 已先发送 `message_stop` 再抛异常。

## R1 八项复核

| R1 项 | R2 状态 | 证据 |
|---|---|---|
| delayed-start disconnect | **未关闭，见 M1** | ASGI response 已并发监听 disconnect，现有 fake smoke 也能观察 upstream `closed=True`；但 task-group cancel scope 会打断带 checkpoint 的真实 finally 清理。 |
| 真实 sink／frontier | **部分关闭，见 M4** | block／terminal 只有 downstream 恢复 generator 后才记 accepted，response-start／body failure可记 uncertain；但 uncertainty 没有进入 History projection。 |
| postcommit Anthropic error SSE | **目标路径关闭** | committed block 后 protocol error产生单一 Anthropic `error`，不发 `message_stop`，partial committed prefix进入 History。Terminal seal 的相邻缺陷另见 M5。 |
| `incomplete/max_output_tokens` | **部分关闭，见 M3** | 有 usage 时生成 `stop_reason=max_tokens`；usage 缺失的冻结合法分支仍被拒绝。其他 incomplete reason继续显式失败。 |
| CRLF／`data:` framing | **关闭** | line parser在累计 buffer上识别 CRLF，覆盖每个 split point，并接受 `data:` 无 optional space。 |
| content lifecycle／no-loss | **部分关闭，见 M2** | item done可补 authoritative content，unknown content part与空 message成功均 typed fail；但已 emitted text 的后续 authoritative 值不再交叉核对。 |
| tool args typed error | **关闭** | parser在完成点严格解析 JSON object，malformed／array／scalar统一为 `invalid_tool_arguments`，route precommit返回 typed Anthropic HTTP error。 |
| stream History | **部分关闭，见 M4** | success 与 postcommit partial 已从 committed block ledger形成 response；write uncertainty仍丢失 projection／frontier。 |

## 事实性发现

[major] `src/app/streaming/sse.py:58-76,135-140`、`src/app/routes/anthropic.py:41-60` — disconnect 取消会在 body iterator 的异步 finally 中再次注入 cancellation，真实 upstream close／History finalize 可能被跳过 — `DelayedStartStreamingResponse.__call__()` 在任一 stream／disconnect task完成后立即取消同一 task group；`stream_response()` 的 finally随后 `await body_iterator.aclose()`，而 `passthrough_bytes()`／`_history_stream()` 的 finally继续 await inner close、explicit cleanup、observer与 History。带 checkpoint 的最小 ASGI probe实际输出 `FINALLY_ENTERED=True`、`FINALLY_INTERRUPTED=CancelledError`、`FINALIZED=False`。现有 `tests/smoke/test_anthropic_responses_stream_route.py:868-913` 的 `ControlledResponsesStream.aclose()` 与 `RecordingHistory.finalized()` 都没有 cancellation checkpoint，因此得到的 `closed=True`／finalized只是同步 fake 路径的假绿 — 把 cleanup／finalize 放入有界 shielded cancel scope，保留原 cancel provenance；以会真正让出控制权的 upstream close与 History flush做首 block前、首 block后 disconnect正控，断言资源关闭和finalize恰好一次。

[major] `src/app/openai/responses_stream_parser.py:280-337,584-632` — text lifecycle没有冻结并交叉核对已收到的 authoritative final value，互相冲突的 `.done`／content-part done／item done可成功提交错误文本 — `_on_output_text_done()` 将 draft标记 `emitted=True`但不保存 authoritative text；`_on_content_part_done()` 遇到 `draft.emitted`直接返回；`_complete_message_from_item()` 也只在 `not draft.emitted` 时产出 block，不比较已有 completed value。进程内反例依次送 `output_text.done="FIRST"`、`content_part.done="SECOND"`、`output_item.done content="THIRD"`，实现接受 `TextBlock("FIRST")`、后两步均返回空 events，并最终产生 `ResponsesTerminal(kind="completed")`。这违反 Spec `spec.md:322` 的累计 delta与 authoritative final value一致合同，也让上游 lifecycle 冲突被静默吞掉 — 在 `_TextDraft` 保存唯一 authoritative value／来源；任一后续 authoritative形态必须 value-exact一致，否则抛稳定 `authoritative_text_mismatch`。补覆盖三种 done任意组合与顺序的正反控制，并确认合法单一 done 与等值重复不会 false-red。

[major] `src/app/delivery/responses_anthropic_stream.py:180-205,239-269` — 合法 `incomplete/max_output_tokens` 在 terminal usage 缺失时被错误拒绝，不能按冻结 usage 合同输出零值＋estimated fact — adapter 对该 terminal无条件调用 `_terminal_usage()`，后者要求 `response.usage` 必须是 object。实际 probe只给合法 `incomplete_details.reason=max_output_tokens` 而省略 usage，得到 HTTP前 `ApiError(code="invalid_responses_event", message="response.incomplete requires object field usage")`。Spec `spec.md:370,379` 明确“整个 usage 缺失时 wire 使用零值并在 History／observer标记 `estimated=true`”；当前有 usage smoke `tests/smoke/test_anthropic_responses_stream_route.py:1001-1055` 没覆盖此分支 — 让 stream usage normalizer与 non-stream事实模型共享 absent usage语义，产生零 wire usage及 typed `estimated=true`／provenance，而不是把合法 terminal降成 malformed event；增加 stream／non-stream parity与缺失 usage正控。

[major] `src/app/delivery/responses_anthropic_stream.py:62-112`、`src/app/routes/anthropic.py:42-60` — delivery-uncertain 时 History 丢掉 response／frontier，无法记录客户端可能已见前缀与代理认知 — `committed_response` 在没有 accepted block且 terminal未 accepted时直接返回 `None`，即使 headers／`message_start`／block状态已经 `uncertain`；`_history_stream()`只在该 property非空时传 response。最小 probe构造 `headers_state="uncertain"` 后 finalize，实际得到 context FAILED但 `History.responses == [None]`，error还退化成无 code 的 `stream interrupted`。Acceptance `REL-03B`要求 uncertainty 后 History failed且联合保留客户端前缀与代理 frontier；现有 `tests/smoke/test_anthropic_responses_stream_route.py:437-498` 只断言内存 frontier，不走 route／History — 无论 committed prefix是否为空，History都应生成 immutable delivery projection，至少保存 envelope states、committed prefix、uncertain index／reason与失败 cause；增加 response-start、首 block、后续 block、terminal各 offset 的 route-level History正控。

[major] `src/app/delivery/responses_anthropic_stream.py:128-223`、`src/app/openai/responses_stream_parser.py:151-164,383-420` — stream没有绑定 `response.created.id` 与 terminal `response.id`，也没有在成功 terminal后封口停止读流，可跨 response混合终态或先发送成功再异常突断 — adapter保存 created id用于下游 message id，却从未对账 `ResponsesTerminal.response_id`。真实 adapter probe用 `response.created.id=RESP_A`＋`response.completed.id=RESP_B`，仍生成 A 的 `message_start`与 accepted `message_stop`。另一 probe在合法 completed后追加 `response.output_item.added`，实现先发送 `message_start → message_delta → message_stop`，随后 parser报 `event_after_terminal`，adapter尝试渲染 error但因 terminal已 scheduled抛 `DeliveryOrderError("terminal was already scheduled")`；History因 frontier terminal已 accepted可被标 completed，尾随协议破坏消失。该行为违反同一 response lifecycle与 Acceptance `STR-04` 的“failure后不得出现成功 terminal” — parser／adapter记录并 value-exact校验 created id、所有 response-bearing events与 terminal id；terminal fact到达后先封存／停止上游消费，或在 success commit前确认流已到协议允许的结束边界，禁止成功 terminal后再进入 error renderer。补跨 id、duplicate terminal、terminal后 content／error／`[DONE]`边界正反控制。

## 测试可信度

- 候选新增测试对 R1 多项修复有真实判别力：frontier pending→accepted时点、first-body uncertain、postcommit error与partial History、有 usage的max-token终态、CRLF全部切分点、`data:`无空格、unknown content与tool args typed failure均覆盖到最终路径。
- 但本轮五项反例均未被现有 `88` 项定向测试与 `512` 项全仓测试捕获。最明显的假绿是 disconnect smoke的 fake cleanup不包含任何 cancellation checkpoint；sink uncertainty测试停在内存 frontier；max-token只给 usage；text conflict只覆盖 tool／reasoning，不覆盖 text多 authoritative层；terminal测试不覆盖 id mismatch与terminal后事件。
- 因用户要求严格只读，本轮正控采用进程内最小反例而未修改候选文件。所有反例均直接运行 current生产类／函数，候选状态哈希前后保持空树哈希。

## 结论

R1 的 CRLF／`data:`、tool args typed error和普通 postcommit error SSE已经关闭；sink frontier、max-token、content lifecycle与History已实质前进但仍有上述缺口，disconnect修复则被真实 cancellation checkpoint证伪。当前另有 terminal identity／seal 新 major。**最终为 0 blocker／5 major，当前不可 squash；关闭五项并补可判红的 route-level正控后再复评。**
