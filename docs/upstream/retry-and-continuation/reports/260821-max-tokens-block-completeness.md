# `max_output_tokens` 截断时，被截断的 output item 有没有 `output_item.done`？

日期：2026-08-21
调查范围：只读调查，未修改任何生产代码，未向上游发出任何真实请求。
证据目录：`.dev/docs/tmp/260821-max-tokens-evidence/`（探针脚本 + 原始输出）

## 结论速览

| 子问题 | 结论 | 证据等级 |
|---|---|---|
| 1. 截断的 item 会不会收到 `output_item.done` | **会**。20/20 个录制样本中，`response.incomplete` 的前一帧永远是该 item 的 `response.output_item.done` | 实测/录制（history 原始帧，n=20） |
| 1b. `content_part.done` | **会**（message item 走 `output_text.done` → `content_part.done` → `output_item.done`；reasoning item 走 `reasoning_summary_text.done` → `reasoning_summary_part.done` → `output_item.done`） | 实测/录制（n=20） |
| 1c. `response.incomplete.response.output` | **含**那个半截 item，且其文本 / arguments 长度与 `output_item.done` 上的完全一致；`status` 标为 `"incomplete"` | 实测/录制（n=20） |
| 2. 本项目 assembler 何时判定 block 完成 | 仅在 `response.output_item.done`（`assembler.py:231-232` → `_close`，`assembler.py:279`）。`response.incomplete` 只读 terminal，**不冲刷**未 done 的草稿（`assembler.py:233-235`、`323-341`） | 代码事实 |
| 3. 「撞 max_tokens 时已交付过至少一个完整块」 | **成立**，且在所有形态下成立——因为被截断的那个 item 自己就会 `done`，从而被装配成一个完整块交付出去 | 实测/录制 + 代码事实 |

## 一、上游事实（实测/录制）

### 证据来源与检索方法

现有 cassette（`tests/int/cassettes/`）里**没有** incomplete / max_tokens 场景：5 份 cassette 中 4 份含 `incomplete_details`，全部为 `null`。`exp/` 下也无相关 PoC。

因此走 history 库。可用的带帧数据库只有 4 个（服务在 2026-08-15 停止写 frame 对象，之后的 4 个 v3 库 `frames=0`）：

| 库 | operations | frames |
|---|---|---|
| `history-v3-260807.db` | 71788 | 16075093 |
| `history-v3-260809.db` | 39927 | 10846890 |
| `history-v3-260811.db` | 6084 | 1621841 |
| `history-v3.db` | 24544 | 5263201 |

全部以 `?immutable=1` / `?mode=ro` 只读打开。

扫描方法（`probe_hist_3.py`）：对每个 operation 读 manifest，取**最后 16 个** frame handle 解压，匹配转义后的标记 `incomplete_details\":{`（非 null）与 `stop_reason\":\"max_tokens`。只解压尾部帧是让全量扫描可负担的关键（142343 个 operation，612 秒跑完）。

**正样本对照**：先单独验证过转义假设——在一个已知正常完成的 operation 里，`incomplete_details\":` 命中 10 帧（`response.created` / `in_progress` / `completed` 及其客户端改写副本），证明标记形状正确、扫描确实在读到内容而不是恒不命中。

命中 29 个 operation，其中 20 个带 Responses 腿（`gpt-5.6-sol` / `gpt-5.6-terra`，endpoint 记为 `anthropic-messages`，即旧服务的 Anthropic-in → Responses-out 路径，与本项目主路径同形），另外 9 个是 claude 模型的原生 Anthropic 上游（`stop_reason: max_tokens`），与本题无关。

取帧时按 `from_history.py` 的做法**只取变换图的根**（丢弃任何被 `transform` 事件声明为 output 的 handle），避免拿到旧服务 `rewrite-out:responses-fix-stream-ids` 改写过的副本。

### 观察结果（n=20，全部 `incomplete_details = {"reason": "max_output_tokens"}`，`status = "incomplete"`）

1. **`output_item.added` 与 `output_item.done` 计数在 20/20 中完全相等。** 没有任何一个 item 只 added 不 done。
2. **`response.incomplete` 的紧前一帧，20/20 都是 `response.output_item.done`。** 尾部形态只有三种：
   - message 被截断：`output_text.delta` … → `output_text.done` → `content_part.done` → `output_item.done` → `response.incomplete`（10 例）
   - function_call 被截断：`function_call_arguments.delta` … → `function_call_arguments.done` → `output_item.done` → `response.incomplete`（4 例）
   - reasoning 被截断：`reasoning_summary_text.done` → `reasoning_summary_part.done` → `output_item.done` → `response.incomplete`（4 例）；另有 2 例是 `output_item.done` → `output_item.added` → `output_item.done` → `response.incomplete`，即刚好在配额耗尽处新开一个 reasoning item 并立刻关闭。
3. **被截断 item 的 `status`**：message 与 function_call 标 `"incomplete"`（未被截断的前序 item 标 `"completed"`）；reasoning item 不带 `status` 字段（值为 `None`）。这是一个可用于识别「哪个 item 是被截断的那个」的可靠信号。
4. **`response.incomplete` 载荷里的 `output` 数组含全部 item，包括那个半截的**，且其内容与 `output_item.done` 上的一致（逐例核对 text_len / args_len 相等，例如 3565 vs 3565、6077 vs 6077、487011 vs 487011）。所以 `output_item.done` 已经携带了截断处的全部内容，`response.incomplete` 不带来新内容。
5. **被截断的 function_call，其 `arguments` 是残缺 JSON**（4/4 例 `json.loads` 失败）。最极端一例 `args_len=487011` 且尾部是长串重复制表符——模型在写工具参数时撞顶。

原始逐例表格见 `260821-max-tokens-evidence/inc_table.txt`。

### 样本的边界（判据权重）

- **强到可以据此行动**：「`max_output_tokens` 截断时被截断 item 会收到 `output_item.done`」这一条，20/20 无反例，覆盖 message / function_call / reasoning 三种 item 类型和两个模型。
- **仅是倾向、样本不足**：语料里 `incomplete_details.reason` **只有** `max_output_tokens` 一种。`content_filter` 之类的其他 incomplete 原因**未观测到**，本报告不对其做任何断言。
- **样本时间窗**：2026-08-04 ～ 2026-08-08 之间（旧服务 copilot-api-js），模型为 `gpt-5.6-sol` / `gpt-5.6-terra`。上游行为随时间/模型变化的可能性未被排除。

## 二、本项目装配事实（代码事实）

live 链路接线：`cli.py:151` → `create_pipeline_app`（`server/pipeline_app.py:682`）→ `pipeline_app.py:498` 调 `stream_delivery`，assembler 由 `handler.py:495 assembler_for` 按 `dialect_for` 选出，Responses 腿得到 `ResponsesAssembler`（`handler.py:500-501`）。

### block 完成的唯一判据

`src/app/pipeline/delivery/assembler.py:231-232`：

```python
if kind == "response.output_item.done":
    return self._close(data)
```

`_close`（`assembler.py:279-321`）是 `ResponsesAssembler` 中**唯一**会返回 `CompletedBlock` 的地方。所有 delta 事件（`assembler.py:225-230`）一律 `return ()`。

### `response.incomplete` 不冲刷半截 item

`src/app/pipeline/delivery/assembler.py:233-235`：

```python
if kind in {"response.completed", "response.incomplete"}:
    self._read_terminal(kind, data)
    return ()
```

`_read_terminal`（`assembler.py:323-341`）只写 `self._terminal`（`seen`、`usage`、`stop_reason`），**完全不触碰 `self._drafts`**，也不读 `response.output` 数组。它把 `incomplete_details.reason == "max_output_tokens"` 映射成下游的 `stop_reason: "max_tokens"`（`assembler.py:336-338`）。

因此：**若上游没为某个 item 发 `output_item.done`，该 item 的内容会被静默丢弃**——草稿留在 `_drafts` 里，随对象一起被回收，客户端既看不到这个块，也收不到任何关于它存在过的信号。第一节的录制证据说明在 `max_output_tokens` 形态下这个路径不会被触发，但这是**上游行为保证**，不是本地代码的构造性保证。

### 交付层

`src/app/pipeline/delivery/stream.py:238-249`：assembler 吐出的每个 block 经 `_commit` → `DeliverySession.offer` → `BlockBuffer.add`。默认 `buffering_policy = "block"`（`config/schema.py:262`），即每个块完成即释放。事件循环结束后 `stream.py:266` 的 `session.finish()` 冲刷 buffer 里还压着的块（`full` / `until-tool-use` 策略下才有内容），随后 `stream.py:290-294` 发 `message_delta` + `message_stop`，`stop_reason` 取 `terminal.stop_reason`，即 `"max_tokens"`。

`terminal.seen` 在 `_read_terminal` 里被置 True（`assembler.py:324`），所以 `response.incomplete` **算合法终止事件**，不会走 `stream.py:279-288` 的 `incomplete_responses_stream` 错误分支。这一点是对的：撞 max_tokens 是正常结束，不是传输截断。

## 三、合成结论

命题：**「撞 `max_tokens` 时客户端已交付过至少一个完整块」**。

结合第一节（被截断的 item 自己会 `done`）和第二节（`done` 即交付），结论是：**成立，而且理由比命题本身更强——被截断的那个 item 本身就会被交付成一个完整块**，而不是「靠它前面碰巧有别的块」。

分形态：

| 形态 | 语料样本数 | 撞顶前已完成的块 | 被截断 item 本身 | 客户端最终收到 |
|---|---|---|---|---|
| 纯文本回答，整个回答就是一个 message item | 1（`req_1786092873344_49`） | 0 | message，`status=incomplete`，`output_item.done` 携带全部 2668 字符 | **1 个完整 text 块** + `message_delta(stop_reason=max_tokens)` |
| reasoning + message | 8 | reasoning 块（1～5 个） | message，`status=incomplete` | reasoning 的 thinking 块 + 1 个 text 块 |
| 只有 reasoning，在 reasoning 中途撞顶 | 6 | reasoning 块（0～6 个） | reasoning，`output_item.done` 带完整 `encrypted_content` | 若干 thinking 块，**无 text 块** |
| 带工具调用（reasoning/message + function_call） | 4 | reasoning / message 块 | function_call，`status=incomplete`，`arguments` 是残缺 JSON | 前序块 + 1 个 `tool_use` 块，其 `input` 为 `{"__raw": "<残缺 JSON>"}` |
| 单独 function_call 撞顶 | 1（`req_1785710950261_5206`） | 0 | function_call，`arguments` 长 487011 字符且残缺 | **1 个 `tool_use` 块**，`input = {"__raw": ...}` |

最坏形态是「只有 reasoning，在 reasoning 中途撞顶」：客户端拿到的是若干 thinking 块、零个 text 块、`stop_reason: max_tokens`。**但它仍然收到了完整块**，不是「一个块都没收到」。语料里没有任何一例是「零块交付」。

### 一个顺带发现（不在本题范围，供裁决）

被截断的 function_call 其 `arguments` 是残缺 JSON（4/4 例），而 `assembler.py:375-380` 的 `_decode_json` 在解析失败时回退成 `{"__raw": raw}`。也就是说撞顶时若正在写工具参数，本项目会向客户端交付一个 `input` 形如 `{"__raw": "..."}` 的 `tool_use` 块。这是**有意的设计**（注释写明「a malformed argument is still evidence」），但下游 Anthropic 客户端会拿它当真实工具入参。是否要在 `stop_reason == max_tokens` 且末块为残缺 `tool_use` 时另作处理，是一个**未被裁决**的问题，记在这里而不是替它决定。证据等级：代码事实（回退分支）+ 实测/录制（残缺 JSON 的存在）。

## 复现方法

```bash
# 全量扫描（约 10 分钟，只读打开 history 库）
cd /home/xp/src/ghc-api-proxy-py
uv run python .dev/docs/tmp/260821-max-tokens-evidence/probe_hist_3.py > /tmp/scan_hits.txt

# 逐例结构化表格（依赖上一步产出的 /tmp/scan_hits.txt）
uv run python .dev/docs/tmp/260821-max-tokens-evidence/probe_hist_5.py
```

注意：探针必须在项目根目录跑，否则 `uv run` 找不到 `orjson` / `zstandard`（第一次就踩到了这个坑）。

`inc_table.txt` 中的 `tail=` 片段含用户自己会话的中文片段与文件路径原文，未做脱敏——它来自用户本机的 history 库，与 `.dev/` 下既有文档同类。若这份要进入任何会公开的载体，需要先处理。

## 建议：该录一份 cassette

本次结论依赖 history 派生帧，而 history 只有**帧边界**、没有**chunk 边界**，且语料截止到 2026-08-15。要让这个行为进入回归测试，应补一份真实录制：

```bash
PYTHONPATH=src:tests/int uv run python tests/int/recorded/record_cassette.py <scenario>
```

需要在 `record_cassette.py` 里新增一个 scenario：请求带极小的 `max_output_tokens`（例如 16），prompt 保持琐碎（如「数到一百」），目标是稳定复现 `response.incomplete`。这需要凭据并会发真实请求，**本次调查未执行**。
