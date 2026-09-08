已修复，`main` 的 `1fb37cd`。

## 根因

不是 `custom_tool_call` 这个类型没被支持，而是**这条腿本来就不该做翻译**。

`assembler_for` 按**上游方言**挑 assembler。`/responses` 请求两端都是 `openai-responses`，但只要上游是 Responses，它拿到的就是「Responses → Anthropic」那个翻译型 assembler——而那张表只认 6 个 item 类型（`message`、`function_call`、`reasoning`、`tool_search_call`、`web_search_call`、`tool_search_output`），SDK 声明的 28 个里其余一律落进 `UNKNOWN`。

于是「本代理认识多少 item 类型」成了客户端能收到什么的上界。客户端说的是 Responses、上游说的也是 Responses，中间却走了一次**唯一消费者是把它撤销的那个 framer** 的往返翻译，而 `custom_tool_call` 正落在这次往返的丢失点上。

## #2 的修复为什么不算修好

#2 当时把撕流换成了显式拒绝（`unknown_output_item`）。那只换了症状：天花板一寸没动，所以同一个 item 类型换个客户端就又打了一次——也就是本 issue。

## 现在的做法

`translation_required is False` 时既不翻译也不拒绝，直接携带上游自己的事件，按块级边界分组交付。分组只读 `output_index`，**不读 item 类型**——所以一个从没听说过的 item 也能完整到达，不需要谁去认识它。加类型表会把那道天花板原样建回来。

## 验证

把分流点关掉（变异），本 issue 里那两行日志逐字回来：

```
refusing an output item this proxy cannot carry: type='custom_tool_call'
refused mid-stream: upstream sent an output item this proxy cannot convert: custom_tool_call
```

打开就没有了。集成测试断言的是 payload 而不只是事件名——只断言事件名的话，一个内容为空的块也能通过，而那正是 #2 引入拒绝要避免的静默失败。

全量 1998 passed，ruff 与 pyright 均通过。

## 当前范围

只有 **Responses 直连腿**接线了。Anthropic ↔ Anthropic 直连腿有完全相同的缺陷（未知 content block 类型被 framer 拒绝），词汇已实现并单测，但**暂未启用**——那条腿上的 `max_tokens` 续写会合成一个必须排在终局之前的块，而原样透传时上游的终局已经发出去了，先接会造成回归。这一条单独记录在案，不在本 issue 范围内。
