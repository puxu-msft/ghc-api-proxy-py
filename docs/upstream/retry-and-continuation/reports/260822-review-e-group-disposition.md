# E 组评审的处置

**评审报告**：`260822-review-e-group.md`（异源评审，gpt-opus）。**结论**：1 blocker、4 major、8 minor，`needs-fix`。
**处置日期**：2026-08-22。**处置提交**：主仓 `bce8b0d`。

评审自己跑了 5 处变异（sha256 核对还原），**其中一处存活**——那正是它抓到的 M4。它还做了残留反查（变异串零命中、原串在位）并删掉了自己的探针。

## 全部采纳并已改

| 发现 | 处置 |
|---|---|
| **B1（blocker）** `decide_stream_ending` 的 COMPLETE 与 ABANDON 被折叠：上游已发完 `message_delta` + `message_stop` **之后**撕流，一个**已完成**的回合被伪造成 `turn_interrupted` 工具调用 | COMPLETE 单独判、直接跳出循环。**改动前是看得见的抛错，改动后是格式合法、内容错误的静默产出**——这是更坏的一种坏 |
| **M1** `max_tokens` 且丢弃后一块不剩时，客户端实收 200 + 零字节 | 交接判断移到「一个字节都没发就 return」之前 |
| **M2** `if remaining and not session.started` 是死分支——`session.finish()` 已把 `started` 置真 | 在 flush **之前**读 `started`。M1 修好后这条才会显形，两条必须一起改 |
| **M4** 四条交接测试全走 Anthropic 直连腿，主路径零覆盖；`num_messages` 唯一断言是 `== 0` 而 fixture 是空 `messages`，**恒真** | 新增翻译腿测试，三条真实消息、断言 `== 3`。评审那条存活的变异（改读翻译后 payload）现在会打红 |
| minor 各条 | 照改 |

**一条值得单独记的**：B1 本该被 `test_a_stream_the_client_already_saw_is_not_replaced` 抓住，但**那条测试自己的样本也是错的**——`anthropic_stream` 末尾会补 `message_delta` + `message_stop`，所以它喂的流里上游其实已经把这一轮说完了。它之前能过，正是因为「已完成」与「已放弃」落进了同一个分支。两个错误互相掩护。

## 登记但不动手

| 发现 | 为什么不动 |
|---|---|
| **M3** 一次性交付路径的 `one_shot_accounting` 不带 `assembler`，而 `finish()` 把整段结局判定包在 `if self.assembler is not None:` 里，撕流/断开的 chat-completions 流一律记 `[ OK ] 200` | **来自同伴的 `2769a64`，且他们此刻仍在改这个文件**（`630f7f3` 落于 11:09）。真实缺陷，归他们的切片。已登记 `deferred.md` |

## 待用户裁决（评审明确未代判）

1. **丢弃规则要不要覆盖非流式路径？** 目前只在流式装配器里。非流式整条响应一次性交付，`status:"incomplete"` 的 item 同样存在于 body 里。
2. **`auto_retry_tool_call_full_name` 未进 `config.example.yaml`**，而且**缺一个 schema → example 的反向检查**：现有测试只查「example 里的键 schema 认不认」，不查「schema 新增的键有没有写进 example」。后者正是这次漏掉的方向。
3. **`max_tokens` 交接时 `category` 的取值**仍是 provisional（见 `decisions.md` 4.1），需与改 MCP 的同伴对齐。

## 未采纳

无。
