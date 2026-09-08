# 未知 output item 的处置：两条路径的已知集合不一致

日期：2026-08-30
状态：**发现记录**，处置未定
来源：实施 issue #2 止血刀时自查 + [`260830-review-issue2-fix.md`](260830-review-issue2-fix.md) 的 major-02／03／05

## 结论先说

评审要求「流式与非流式对未知 item 给同一个答案」。实施时发现这个要求**不够**——两条路径的**已知集合本身就不同**，所以就算两边都拒绝未知，同一个 item 仍会一边被处理、一边被拒绝。

实测（本工作树 `ec3abfc`，探针 `function_call_output` item）：

| 路径 | 结果 |
|---|---|
| 缓冲 `blocks_from_item` | `role="user"`，`BlockKind.TOOL_RESULT`，正常返回 |
| 流式 `ResponsesAssembler` | **拒绝**，`code=unknown_output_item` |

这是止血刀**放大**出来的差异：改动前流式产出的是自相矛盾的空块（也是错的），改动后是拒绝。评审 major-05 问「有没有哪个 item type 今天能被正确处理、现在被误伤」，答案是有两个：`web_search_call`（已由 issue #1 的护栏测试抓到并显式加回映射表）和 `function_call_output`（**无测试覆盖，本次自查发现**）。

## 更深的一层：`blocks_from_item` 被两个方向共用

`translation_driver/openai_responses.py::blocks_from_item` 的 docstring 写着它「Shared by the request `input` reader and the response `output` reader」，理由是「an item means the same thing in both」。

**那个理由对 `function_call_output` 不成立。** 它在请求方向是正常的（客户端回传工具结果，`role="user"` 完全正确），在响应方向可疑（assistant 的 output 里出现工具结果）。「已知集合」是**有方向的**，而这个函数没有方向参数。

顺带发现的第二处：`from_openai_responses_response` 调用它时写的是 `_, blocks = blocks_from_item(...)` —— **role 被丢弃**。于是缓冲侧把一个 `role="user"` 的 `TOOL_RESULT` 块直接放进 assistant 回复的 blocks 里。两条路径都不正确，只是错法不同。

## 这对评审的三条 major 意味着什么

- **major-02（两路径不等价）**：修法不是「让缓冲侧也拒绝未知」，而是「让两条路径共用同一份**响应方向**的已知集合」。前者只对齐了兜底，没有对齐集合。
- **major-03（strict converter 零调用）**：唯一 production semantic owner 必须区分请求方向与响应方向，否则 `function_call_output` 这类条目无处安放。`protocols/responses_anthropic.py::convert_responses_response_to_anthropic` 只处理响应方向，这一点反而是它比在产实现更正确的地方。
- **major-01（malformed lifecycle 与 unknown content part）**：与上面同源——判定点应当只有一个，且它要同时覆盖 item 层与 content part 层。

## 还需要的证据

- **Copilot 会不会在响应 `output` 里发 `function_call_output`？** 无证据。SDK 的 `ResponseOutputItem` union 里有 `ResponseFunctionToolCallOutputItem`，说明协议允许；但本项目 cassette 与 history 里有没有真实样本未查（前一轮取证 §6 也因工具受限未闭合）。**在拿到答案之前，不应为它单方面选择「拒绝」或「按 tool_result 处理」**——前者会误伤一个协议允许的形态，后者会把 user 角色的块塞进 assistant 回复。
- 其余 21 个未知 type 里，还有哪些在缓冲侧其实有分支。本次只逐条比对到 `function_call_output` 一项差异，比对方法是读两处分支表，**不是机械穷举**。

## 我的判断

两条 blocking major 的正确修法需要一份小设计（响应方向的单一判定点、请求/响应方向分离、content part 层一并覆盖），不是几行改动。这份设计与 [`plan.md`](../plan.md) 的「彻底刀」高度相关——直连腿分流之后根本不走这个转换，能消掉一半的面。

因此：**止血刀的流式部分已消除 issue #2 的撕流并已提交；两条 blocking major 与本记录一并转入设计**，不在本轮草率落地。
