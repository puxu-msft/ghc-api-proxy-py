# 直连 Responses 原生透传：延后项台账

**这份是活文档**，**只放未闭合项**。查清、决定或做掉的条目从这里移出，并入 [spec.md](spec.md)、[plan.md](plan.md) 或代码注释，移出时带上出处。编号是标识不是序列，移走后不补号。

权威是 [spec.md](spec.md) 的**当前版本**（它也是活文档，不冻结）。本台账不新增规范，只登记它排除或推迟的东西，使其不被静默删掉。**本台账不得成为绕开 Spec 的去处**——Spec 级的事实一律落在 Spec 里，已知错误的条款当场修订，不在这里登记待办。需要用户裁决的产品分叉登记在 Spec §11，不在这里（当前那里有一项：响应头黑名单的定义域）。

建立于 2026-08-31。

## D-1　`format_sse_event` 与 `encode_frame` 是两份等价实现，前者无调用者

**状态**：等用户裁决是否删除。**我不擅自删已实现的功能。**

**事实**：`src/app/streaming/sse.py` 的 `format_sse_event(data, *, event=None)` 与 `src/app/pipeline/delivery/sse_source.py` 的 `encode_frame(event, data)` 逐语句等价——都按 `data.split("\n")` 每行写一条 `data:`，再补空行。签名只差 `event` 是否可选。**`format_sse_event` 在 `src/` 与 `tests/` 里没有任何实际调用者**，只在 `src/app/streaming/__init__.py` 被重新导出并列进 `__all__`。

**出处**：[`reports/260831-review-sse-line-endings.md`](reports/260831-review-sse-line-endings.md) F-01。该缺陷**先于** P3 那一刀存在，不是它引入的。

**为什么现在不动**：删除一个已实现并已导出的符号是对外行为决定，不是清理；`__all__` 里的名字可能被视作公开面。若要处置，两条路都可以：删掉并从 `__all__` 移除，或让它委托给 `encode_frame` 只留一个实现。

**风险**：两份实现各自演化。P3 只改了 `sse_source.py` 那一侧的**解析**方向，编码侧本轮未动，所以当前两份仍然一致——**这个一致是巧合，不是机制**。

## D-2　响应方向的 `function_call_output`：两条路径已知集合不一致，且无任何活文档记录

**状态**：权威归 `anthropic-responses-bridge`，而**那个主题当前没有记录这件事**。本条只是指针，防止它只活在一份报告里。

**事实**（实测，见出处）：Copilot 若在响应 `output` 里给出 `function_call_output` item，缓冲路径 `blocks_from_item` 把它变成 `role="user"` 的 `BlockKind.TOOL_RESULT` 正常返回，流式路径 `ResponsesAssembler` 则以 `code=unknown_output_item` 拒绝。同一个 item，两条路径两个答案。

**为什么它不归本规格**：本腿不翻译，无条件携带该 item，所以透传落地后直连腿这一半自然消失（[spec.md](spec.md) §11 已记这条定义域划分）。剩下的是**翻译腿**的问题。

**为什么仍要在这里留一条**：`anthropic-responses-bridge/spec.md` 只在**请求方向**覆盖 `function_call_output`（user `tool_result` → `function_call_output`，见其 §「双向字段处置矩阵」），**响应方向一个字没有**；该主题也没有 `deferred.md`。于是这条事实目前只存在于一份报告里，而项目规则明令报告不得成为唯一真相来源。

**还缺的证据**：Copilot 究竟会不会在响应 `output` 里发 `function_call_output`。SDK 的 `ResponseOutputItem` union 里有 `ResponseFunctionToolCallOutputItem`，说明**协议允许**；本项目 cassette 与 history 里有没有真实样本**未查**。在拿到答案之前不应单方面选定「拒绝」或「按 tool_result 处理」——前者误伤一个协议允许的形态，后者把 user 角色的块塞进 assistant 回复。

**出处**：[`reports/260830-known-set-divergence.md`](reports/260830-known-set-divergence.md)。当时的处置是「转入设计」，设计尚未落地。
