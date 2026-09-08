# 让 S3 那一格出声（`_close` 找不到 draft 时的无痕丢弃）

日期：2026-08-27。基线 HEAD `efeab76`。改动留在主树工作区，**未做任何 git 操作**。

## 改了什么

两个文件，都在授权范围内：

- `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py` —— `ResponsesAssembler._close` 里 `if not rescuable:` 那一格，`return ()` 之前加一条 `logger.warning`，并在其上写了三段注释（级别依据、消息构成依据、以及这条路曾经的代价）。
- `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_sse_assembly.py` —— 新增 `test_an_item_that_closes_without_opening_is_ignored_out_loud`，放在既有对照测试 `test_an_ordinary_item_that_closes_without_opening_is_still_ignored` 与 `_responses_item` 辅助函数之间。

动手前复核了任务给的行号，两处都对：`_item_key` 的事故注释在 `:491-496`，`web_search_call` / `tool_search_call` 补救分支在 `:536-548`（`_close` 自 `:532` 起）。改后日志落在 `:544-553`。

日志行本身：

```
dropping an output item that closed without ever opening: type=%r item_id=%r key=%r open_drafts=%r
```

四个参数依次是 `late`（closing item 的 `type`）、`item["id"]`、`_item_key(data)` 算出的查找键、以及 `sorted(self._drafts)`。

## 日志级别与措辞的依据

**级别 `warning`。** 三条依据：

1. **同文件的既有先例就是 `warning`。** `f21d7f4` 给三个上游失败事件（`error` / `response.failed` / `response.cancelled`）装的是 `logger.warning`（`:482`），`anthropic_messages.py:342` 同级。全仓 `src/app/pipeline/` 里没有任何 `logger.error`，`warning` 就是这条链路上实际在用的最高档；再往上走会是这一层里从没出现过的新档位。
2. **这不是"预期内的跳过"，是不变量被破坏。** 本格的语义是"一个 output item 关闭了，而本侧从没为它开过 draft"。`DISCARDED` 那一格（`:559`）才是"认得、故意不交付"，它继续保持安静是对的；本格每一次命中都等于客户端要的内容丢了一段，且原因在本侧看不进去的上游。任务提示里的判据（"不变量被破坏"而非"预期内跳过"）与我读代码得到的结论一致。
3. **不升级为 raise。** 回合的其余部分仍可交付，为一个 item 掐掉整轮的代价大于收益。这一点写进了注释，免得后来者把"只是记一条"读成疏忽。

**噪声风险的评估（记下来，因为它是选 `warning` 的前提）**：每个响应的 `output_item.done` 只有个位数量级，且今天这条路的原始成因（按 `item.id` 配对）已被 `_item_key` 的 `output_index` 优先判据消掉，所以正常流量下预期是零命中。可能命中的残余情形是"某个 `tool_search_call` 既没有 `added` 又没配 `client_search_tool`"，那也确实是内容损失，值得一条 warning。**这个"预期零命中"是推理不是实测**——我没有跑上游数据去数它，用户如果要拿它当排期依据，得先量。

**消息里带什么、不带什么：**

- 带 `type` 与 `item_id` —— 回答"是哪个 item 掉了"。
- 带 `key` 与 `open_drafts` —— 回答"为什么没找到 draft"。这两个是配对的：`key='index:7'` 而 `open_drafts=['index:0']` 一眼就能读出是哪个标识符动了，正是 2026-08-22 那次事故的形状（`added` 与 `done` 的 `item.id` 不一致）。只报"没找到"而不报"拿什么去找、当时有什么"，排障时还得回去重读代码。
- **不带整个 payload** —— 按任务要求。`item` 的其余字段（`action`、`arguments`、`content`）可能很大，且对定位无用。

一处自己拿不准、如实记下：`item_id` 原样打印，不截断。这条 wire 上的 id 确实可以很长（仓库里的 `web_search_call` 夹具用的是 416 个字符的 id），所以某些形态下这一行会偏长。我选了不截断，因为 id 的**完整值**恰恰是与另一侧对照的依据，截断会毁掉它的用途；而这条路预期零命中，长行的代价是偶发的。**若复核者认为该截断，这是可翻的一项，不涉及其他判断。**

## 变异验证

两轮，都只跑改到的那个测试文件。快照在 `/tmp/s3-mutation/openai_responses.py.good`（sha256 `c78d4d42…9932de`），还原后逐字节校验并核了 `git diff`，确认树上只剩本次的加法。

| 变异 | 结果 |
|---|---|
| A. `logger.warning` → `logger.debug`（只降级别） | **红**：`1 failed, 1 passed`（`-k closes_without_opening`）。失败在 `assert "msg_closed" in caplog.text`，`caplog.text` 为空串 —— 说明这条测试同时钉住了级别，不只是钉住"有没有这个字符串" |
| B. 整段 `logger.warning(...)` 删除（保留 `return ()`） | **红**：`1 failed, 42 passed`。同一条断言、同一处失败 |

B 的脚本里放了两条前置断言（`logger.warning` 必须仍在文件里、目标消息必须消失），确保删的是本次这条而不是 `f21d7f4` 那条失败事件日志；实际删除 310 字节。

B 那一轮的 `42 passed` 同时给了一个旁证：**只有新测试变红，没有别的测试依赖这条日志的有无**，所以这次加法没有在别处造成隐性耦合。

未变异的绿（基线）：`tests/unit/pipeline/delivery/test_sse_assembly.py` 43 passed；加上 `tests/unit/pipeline/test_tool_search_wiring.py` 共 46 passed。按要求未跑全量。

## 静态检查

- `uv run ruff check src tests`：仓库整体 **1 error**，在 `tests/int/test_pipeline_app.py:70`（`ClientDeadlineError` 未使用），**是同伴的在改文件，不是我的**。我的两个文件单独跑 `All checks passed!`。
  - 补一条观察：这条命令我跑了两次，第一次 5 errors、第二次 1 error，中间我没动过任何文件 —— 同伴正在并行写盘，仓库级结果此刻是活动靶，只有按文件跑的那份结论稳定。
- `uv run pyright src tests`：同样是那一处，`1 error`，同一文件同一行。我的两个文件单独跑 `0 errors, 0 warnings`。
- 未运行 `ruff format`。
- 注释与 docstring 全部一段一行，无硬折行。

## 我否决了什么

1. **不做 S7（任意未识别事件的裸 `return ()`）。** 按任务范围限制；它需要一份"明知故忽略"的词表，而本项目规矩是上游行为靠录制不靠想象，属用户裁决。
2. **不动 §21 表里 S1、S2、S4—S10 的级别与措辞。** 那是一次成批裁决。特别是同一函数里 `DISCARDED` 那一格（`:559-561`）我一并读了，**刻意不加日志**：它是"认得、故意不交付"，与 S3 的"本该有 draft 却没有"不同类。
3. **否决了把这条路改成 `raise`。** 想过一次：不变量被破坏在别的项目里常配异常。否决理由是回合其余部分仍可交付，为一个 item 掐掉整轮不划算；已写进注释。
4. **否决了按子情形分级（`tool_search_call` 无名 → 降到 info、其余 → warning）。** 想过，理由是前者"本来就不打算交付"。否决是因为无论哪种子情形，"close 没有配对的 open"这个异常本身都成立，分级会让两条路的措辞和阈值各自演化，而收益只是少几条本就预期为零的日志。
5. **否决了修同文件 `:662` 的既有硬折行。** hook 报了 `_reasoning_signature` docstring 里一处真实的句中断行（`…must survive value-exact so the ⏎ client can echo it back…`），**不是我写的，是 HEAD 上就有的**。判定属实（不是并列条目误报）。不顺手改的理由是它与本次改动无关，会让本该只有一格的 diff 多一处噪声。**这一条留给主会话裁决：一行合并即可，我没做。**
6. **没有更新 `.dev/docs/upstream/retry-and-continuation/deferred.md` §21。** 派活时明确把 `.dev/` 划出范围（有同伴在改）。但那张表里 S3 那一行现在与代码不符了 —— 它仍写着"全部经实测确认在任何日志级别都不产出记录"，以及"不在本次范围，登记而非动手"。按项目规矩（事实不得停在权威文档之外），**这需要有人改**，见下面的交接项。

## 需要主会话处理的

- **台账 §21 与代码已脱节**：S3 那一格已出声，表格与结论段落（`deferred.md` 第 280 行的 S3 行、第 293 行的"不在本次范围"）需相应修订，并注明 S7 与其余各格仍开着。我未动，因为 `.dev/` 不在我的授权范围。
- `:662` 的既有硬折行（见"我否决了什么"第 5 条）。
- 仓库级 ruff / pyright 的那 1 条 error 属 `tests/int/test_pipeline_app.py`，归改该文件的同伴。
