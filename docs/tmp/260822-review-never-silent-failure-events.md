# 评审：`d19ae45` — 上游失败事件不再静默

**日期**：2026-08-22。**性质**：对一个小生产改动的证伪式评审，逐条查证。
**被评审对象**：worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-never-silent-upstream-failure`，基线 `c01191f`，候选 `d19ae45`。
**评审者执行约束**：只读评审。除本报告外未修改任何仓库文件；反例验证在 `/tmp` 下的一次性脚本里跑，不落入任何工作树。未跑 `ruff format`。

**权重档位约定**（下文每条结论都带）：
- **确凿**：我自己跑了命令／读了源码，输出贴在正文里。
- **强，足以行动**：由确凿事实推出，推理链短且封闭。
- **倾向**：证据不完整，需要更多样本或一次实测才能定。
- **仅存档**：记录下来，不足以支撑任何决定。

---

## 0. 结论摘要

**总判定：`needs-fix`。** 改动的方向、边界与克制都是对的——它准确地只做了「看得见」，没有偷偷做「处理」，`seen` 确实保持 `False`，健壮性声称经实测成立。**但有两条应当在合入前处理**，都不需要推翻设计：

| # | 严重度 | 一句话 | 位置 | 权重 |
|---|---|---|---|---|
| M1 | **major** | `error` 事件的取词位置对**我们这个上游**是错的。官方客户端明确写了 CAPI 把 `code`/`message` 包在嵌套的 `error` 对象里，而候选只读顶层扁平形——于是在最可能的真实形状上，日志会打出 `code='' message=''`，本改动最主要的收益（上游原话）恰好落空。已实测复现。 | `openai_responses.py:43-51` | 确凿（形状证据二手，但来自官方客户端，比候选引用的那份更具体、更晚） |
| M2 | **major** | 交付链路上还有 **10 处**「已知不处理却零痕迹」的丢弃点，全部实测确认在任何级别都不产出日志记录。其中 `_close` 找不到 draft（S3）**已经在生产上击中过一次、导致整条回复归零**，比候选修的三个事件（三千万根帧里 0 次）更该先动。 | §2.1 表格 | 确凿（21 组探针 + 正样本对照） |
| m1 | minor | `code: null` 被 `str()` 打成 `'None'`。这不是畸形输入，SDK 里 `ResponseErrorEvent.code` 就是 `str \| None`。同一个文件里已经点名过这个陷阱。 | `openai_responses.py:51` | 确凿 |
| m2 | minor | 注释把 `response.cancelled` 的出处记成了 `260821-plan-g1-*.md`，而那份文档通篇没有这三个字。真实出处是 `deferred.md` 第 4 条 / `reports/260821-upstream-termination-reasons.md §1.2`。**词表本身是对的**（官方客户端那张表正是这五个）。 | `openai_responses.py:39` | 确凿 |
| m3 | minor | 「134336 个 operation 零观测」被说成「因为没东西会报告」。那份测量在同一批三千万根帧里数出了 64351 次 `response.completed`，是**有鉴别力的零**。说反了之后，`warning` 级的理由反而被削弱了——说对了它更强。 | 提交信息 + `openai_responses.py:410` | 确凿 |
| m4 | minor | `../h2-goaway/findings.md` 的相对路径锚在上一句提到的文档目录上，不是源文件目录；两腿引文写法不一致。 | `anthropic_messages.py:276` | 确凿 |
| m5 | minor | `response.cancelled` 那组测试参数里的 `code="cancelled"` 是编的；它实际钉的是分发不是形状，docstring 该说明。 | `test_sse_assembly.py` | 确凿 |

**逐条查证的结果一览**（对应任务的六问）：

1. **事件词表** —— 词表**证实**（官方客户端 `chatWebSocketManager.ts:145-152` 的五格表，减去两个成功终止，正是这三个）；Anthropic 腿形状**证实**；`response.failed`/`response.cancelled` 取词**证实**；**`error` 取词证伪**（M1）；注释出处**证伪**（m2）。
2. **其他静默丢弃点** —— 找到 10 处，全部实测**证实**为零痕迹（M2）。
3. **噪声风险** —— `warning` 级**证实**选对；`response.cancelled` 在本 SSE 链路上没有已知常态触发路径（**证伪**「客户端取消会常态触发」这个担心），但该结论的失效条件是「不走 WS 上游」，建议写进注释。
4. **健壮性** —— 21/21 反例全部不抛、`seen` 全部保持 `False`，**证实**；一处正常形状被印错（m1）。
5. **与 G1 的关系** —— **重复且 G1 是超集**。G1 因模块拆分**已经不能 merge**，必须手工重放（与本改动无关）；重放时 `it is not acted on yet` 会变成谎话，需一并处置；G1 自己也有 M1 同款缺陷，别在重放时静默倒回去。G1 的树还带着 `docs/agents/`+`docs/tmp/`，squash 会静默重新引入。
6. **措辞与级别** —— **证实**合本项目惯例；两腿字段名不同是有理由的不同，保持现状。

**门禁现状**：`ruff check src tests` 全过；`pytest tests/unit/pipeline/delivery` 131 passed。未跑 `ruff format`。

**我的处置倾向**：M1 与 m1～m4 都是小改，建议在本改动上就地补掉再合入（M1 一行、m1 一行、m2～m4 改文字）。M2 不在本次范围，建议登记进 `deferred.md` 并单独排期，**但要在报告里留住 S3 的优先级判断**——它是这批里唯一已经真实伤过人的。

---

## 1. 事件词表与取词位置

### 1.1 cassette「零命中」的断言：**证实**（确凿）

候选在 `openai_responses.py:39` 的注释里写「all five cassettes in this repository contain zero of these events」。我自己数了。

```
$ ls tests/int/cassettes/
anthropic_to_responses_stream.json  history_anthropic_stream.json  history_responses_stream.json
responses_web_search_nonstream.json  responses_web_search_stream.json     （共 5 份）

$ rg -c 'response\.failed|response\.cancelled|"event": ?"error"|event: error' tests/int/cassettes/
（无输出）
rg exit=1
```

正样本对照（证明命令确实在读这些文件、模式确实能命中）：

```
$ rg -c 'response\.completed' tests/int/cassettes/
tests/int/cassettes/history_responses_stream.json:1
tests/int/cassettes/anthropic_to_responses_stream.json:2
tests/int/cassettes/responses_web_search_stream.json:2
rg exit=0
```

「五份」与「零命中」都成立。注释这句话属实。

### 1.2 词表本身：**证实**（确凿），但注释里的出处**证伪**（确凿）

我不看计划文档、直接去核官方客户端。`/home/xp/src/refs/vscode-copilot-chat/src/platform/networking/node/chatWebSocketManager.ts:145-152`：

```ts
const streamTerminatingOutcomes: Readonly<Record<string, ChatWebSocketRequestOutcome>> = {
	'response.completed': 'completed',
	'response.failed': 'response_failed',
	'response.incomplete': 'response_incomplete',
	'response.cancelled': 'response_cancelled',
	'error': 'upstream_error',
};
```

CAPI 的终止事件共 5 个。其中 `response.completed` / `response.incomplete` 在本仓已由 `_read_terminal` 处理，剩下的三个正是 `_FAILURE_EVENTS` 的三个。**词表没有漏项，也没有多项。**

但候选在 `openai_responses.py:39` 写的出处是错的：

```
$ rg -n 'cancel' /home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-plan-g1-upstream-error-events.md
exit=1
$ rg -c 'response\.failed' /home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-plan-g1-upstream-error-events.md
7
exit=0
```

被引用的那份计划文档通篇**没有 `response.cancelled` 三个字**（正样本对照证明命令确实在读这个文件）。它只讲 `error` 与 `response.failed`。`response.cancelled` 的真实出处是 `.dev/docs/upstream/retry-and-continuation/deferred.md:52` 与 `.dev/docs/upstream/retry-and-continuation/reports/260821-upstream-termination-reasons.md:88-111`，后者才是抄下上面那张表的地方。

**判定：minor（确凿）**。结论对、引文错。按项目记忆「重指路径会改写引文」与「归因写下前先核 `--stat`」的同族，注释里的出处应改为 `deferred.md` 第 4 条 ／ `reports/260821-upstream-termination-reasons.md §1.2`，否则后来者顺着这条线索去查会扑空，并可能因此以为 `response.cancelled` 是凭空加的（我一开始就是这么怀疑的）。

### 1.3 `error` 事件的取词位置：**证伪**（确凿）—— major

候选 `_failure_words` 对 `kind == "error"` 读的是**顶层扁平**的 `data["code"]` / `data["message"]`。这是 OpenAI 公开 SDK 的形状，我核过：

```
$ uv run python -c "from openai.types.responses.response_error_event import ResponseErrorEvent; ..."
ResponseErrorEvent. code -> str | None
ResponseErrorEvent. message -> <class 'str'>
ResponseErrorEvent. param -> str | None
ResponseErrorEvent. sequence_number -> <class 'int'>
ResponseErrorEvent. type -> typing.Literal['error']
```

**但我们的上游不是 OpenAI，是 CAPI。** 同一份 `chatWebSocketManager.ts:124-140` 专门为这件事写了注释：

```ts
/**
 * CAPI WebSocket error shape. Unlike the OpenAI SDK's flat `ResponseErrorEvent`
 * (`{ type: "error", code, message }`), CAPI wraps the error details in a
 * nested `error` object: `{ type: "error", error: { code, message } }`.
 *
 * Non-recoverable errors (rate limits, quota, upstream failures) also include
 * `copilot_quota_snapshots` with per-model quota state.
 */
export interface CAPIWebSocketErrorEvent {
	readonly type: 'error';
	readonly error: { readonly code: string; readonly message: string };
	readonly copilot_quota_snapshots?: QuotaSnapshots;
}
```

而且官方客户端**用这一层的存在来做判别**（`:142-144`）：

```ts
export function isCAPIWebSocketError(event: ...): event is CAPIWebSocketErrorEvent {
	return event.type === 'error' && 'error' in event && typeof (event as CAPIWebSocketErrorEvent).error?.code === 'string';
}
```

后果：若上游按 CAPI 形状发 `error`，候选会打出 `code='' message=''`。**事件被报出来了（本次改动的第一目标达成），但「上游原话」——提交信息里明写的「They are the only account of what it thought went wrong」——恰好在这一种形状上全部丢失。** 也就是说，收益最大的那一半在最可能的真实形状上不生效。

同时 `copilot_quota_snapshots` 也整个落地不留痕；配额耗尽正是「非可恢复错误」的典型，而这恰恰是运维最想从日志里看到的那类。

补充两条上下文，避免把这条读成回归：

1. **legacy 链路有同一个缺陷**，不是本次引入的。`src/app/openai/responses_stream_parser.py:495-500`：
   ```python
   error_code = self._optional_string(event.get("code")) or self._optional_string(error_object.get("code"))
   ```
   其中 `error_object = response_object.get("error")`，而 `response_object = event.get("response")`。对一个没有 `response` 键的 CAPI `error` 帧，两个分支都取不到，同样落空。所以这是**两条链路共同的、从未被录制证伪过的假设**。
2. **Anthropic 腿反而是对的**（见 §1.4），它读的就是嵌套。于是本仓出现一个不对称：Anthropic 腿嵌套、Responses 腿扁平——而唯一的形状证据说 Responses 腿也该是嵌套。

**判定：major（确凿的形状证据 + 强推理）**。不需要为它推翻本次改动，修法是一行、且两种形状不冲突（扁平形没有 `error` 键，嵌套形没有顶层 `code`），可以先嵌套后扁平地取：

```python
def _failure_words(kind: str, data: dict[str, Any]) -> tuple[str, str]:
    if kind == "error":
        # CAPI 把它包一层（vscode-copilot-chat chatWebSocketManager.ts:124-140），OpenAI 公开 SDK 是扁平的。两种形状不冲突，都认。
        raw = data.get("error")
        holder = cast(dict[str, Any], raw) if isinstance(raw, dict) else data
    else:
        ...
```

**这一条的权重定位要说清楚**：它不是「候选写错了」，而是「候选把一个二手来源当成了唯一来源，而项目里还有一份更晚、更具体、指向相反的二手来源」。两份都不是录制。我的倾向是按更具体的那份（官方客户端的 CAPI 注释）走，并把两种形状都认下来——代价一行，收益是在最可能的形状上不丢原话。

### 1.4 Anthropic 腿的形状：**证实**（确凿）

`/home/xp/src/copilot-api-js/src/types/api/anthropic.ts:188-191`：

```ts
export interface StreamErrorEvent {
  type: "error"
  error: { type: string; message: string }
}
```

候选 `anthropic_messages.py:277-283` 读 `data["error"]["type"]` 与 `["message"]`，与之逐字对应。且 `kind = event.event or str(data.get("type",""))` 是**事件行优先**，正好绕开参考实现踩过的「上游只发 `event: error` 而 payload 无顶层 `type`」那个坑（计划文档 §2.2 已论证，我复核 `anthropic_messages.py:257` 成立）。

**这一条无异议。**

### 1.5 `response.failed` / `response.cancelled` 的取词位置：**证实**（确凿）

SDK 3.3.1 的类型链：

```
ResponseFailedEvent. response -> <class 'openai.types.responses.response.Response'>
ResponseError. code -> Literal['server_error', 'rate_limit_exceeded', ...]
ResponseError. message -> <class 'str'>
```

`response.error.{code,message}` 正确。`Response.error` 可为 null，候选的 `isinstance(..., dict)` 已经挡住。

顺带一条**仅存档**的观察：`ResponseError.code` 在 SDK 里是一个 20 项的 Literal，全部是图像相关错误加 `server_error` / `rate_limit_exceeded` 等——这套枚举明显是 OpenAI 自己的，CAPI 未必照发。不影响本改动（候选用 `str()` 而非枚举匹配）。

### 1.6 `response.cancelled` 在 SDK 里不存在：**仅存档**

我枚举了 SDK 3.3.1 `ResponseStreamEvent` 联合里的全部 58 个 `type` 字面量，`response.cancelled` **不在其中**（`cancelled` 只作为 `Response.status` 的取值出现）。copilot-api-js 的两处终止事件集合也没有它。所以 `_FAILURE_EVENTS` 里的它**只有官方客户端那一张表支撑**。

这不构成反对：那张表是 CAPI 自己的词表，比 OpenAI 公开 SDK 更贴近我们的上游，且多认一个事件名的代价是零（不会误伤任何已知事件）。**仅存档**，供日后若要收窄词表时回看。

---

## 2. 交付链路上还有哪些「已知不处理却不留痕」的地方

**这是本次评审最重要的一节。** 用户 2026-08-22 的裁决措辞是「**这些路径**也绝不能静默」，而候选只闭合了其中三个事件名。我把交付链路上其余的丢弃点逐个实际跑了一遍——不是读代码猜的，是喂进去看有没有任何 log record 出来。

探针：`/tmp/probe_other_silences.py`（只读；`sys.path` 指向候选工作树的 `src`，装一个 root handler 抓 `logging.NOTSET` 以上的**全部**记录）。**正样本对照在第一格**——候选新加的分支确实打出了 WARNING，证明抓取器是通的：

```
=== POSITIVE CONTROL: the branch d19ae45 does log ===
R response.failed (the new branch)
    blocks=()
    WARNING:upstream sent 'response.failed' mid-stream; it is not acted on yet: co
```

以下每一格的 `<<< NO LOG RECORD AT ANY LEVEL >>>` 都是同一个抓取器在同一次进程里给出的。

### 2.1 全部实测结果

| # | 位置 | 触发条件 | 后果 | 有无痕迹 |
|---|---|---|---|---|
| S1 | `sse_source.py:26-32` `SseEvent.json()` | 帧的 `data:` 不是合法 JSON | 整帧变成 `{}`，后续按事件名照常处理 | **无** |
| S2 | 同上 | `data:` 是合法 JSON 但不是对象（数组／字符串／数字） | 同上 | **无** |
| S3 | `openai_responses.py:458-465` `_close` | `output_item.done` 找不到对应 draft，且 item 不是 `web_search_call` | **整个 output item 消失** | **无** |
| S4 | `openai_responses.py:448-456` `_accumulate` / `_accumulate_arguments` | delta 的 `output_index` 没有对应 draft | 该段文本／arguments 丢失 | **无** |
| S5 | `anthropic_messages.py:314-318` `_close` | `content_block_stop` 的 index 没有 draft | 整个 content block 消失 | **无** |
| S6 | `anthropic_messages.py:297-301` `_accumulate` | delta 的 index 没有 draft | 该段文本丢失 | **无** |
| S7 | 两个 `push` 结尾的裸 `return ()` | 任何不认识的事件名 | 事件整个丢弃 | **无** |
| S8 | `openai_responses.py:567-570` `_anthropic_usage` | usage 转换抛 `ResponseConversionError` | `Terminal.usage` 变 `{}`，与「从没设过」同值 | **无** |
| S9 | `assembling.py:90-94` `decode_json` | tool call arguments 不是合法 JSON | 保留为 `{"__raw": …}` 走下去 | 无日志，**但内容没丢**（见 2.3） |
| S10 | `translation_driver/reasoning_carrier.py:103-142` | carrier 解不开（4 个 `except → return None`） | 推理载体降级 | **无** |

实测输出（节选，完整见探针脚本重跑）：

```
=== A1. Responses: a whole output item whose closing frame has corrupt JSON ===
done frame truncated mid-JSON
    blocks=() (the whole message block is gone)
    <<< NO LOG RECORD AT ANY LEVEL >>>

=== A2. Responses: closing frame for an index that was never opened ===
done for unopened index 7
    blocks=() (item dropped; this is the id-instability failure mode)
    <<< NO LOG RECORD AT ANY LEVEL >>>

=== A3. Responses: a text delta for an index that was never opened ===
delta for unopened index 3
    blocks=() (text silently discarded)
    <<< NO LOG RECORD AT ANY LEVEL >>>

=== A7. An event name neither assembler recognises ===
response.refusal.done (a real SDK event)
    blocks=() (refusal content dropped)
    <<< NO LOG RECORD AT ANY LEVEL >>>

=== A8. Responses: usage that will not convert ===
response.completed with malformed usage
    blocks=() terminal.usage={} upstream_usage={'input_tokens': 'not a number'}
    <<< NO LOG RECORD AT ANY LEVEL >>>

=== A9. sse_source: a frame with a data line and unparsable JSON ===
parse_frame -> SseEvent(event='', data='{broken')
  .json() -> {}   <- the swallow, no log
```

### 2.2 按严重度排序，以及为什么 S3 是这批里最该先动的

**S3（`_close` 找不到 draft）——major（确凿）。** 三条理由，都在本仓自己的文字里：

1. **它已经真实发生过，而且当时正是因为静默才难查。** `_item_key` 的 docstring 自陈：「Copilot sends a *different* `item.id` on `output_item.added` and `output_item.done` for the same item, so keying on the id meant `_close` never found what `_open` had created and **the whole response assembled into nothing**」。那次是**整条回复归零**，1243 个测试全绿（项目 CLAUDE.md 的开篇例子就是它）。
2. **同一个函数里，相邻那几行的注释已经点名了这个危险。** `web_search_call` 的迟到注册分支写着：「refusing to close it would throw away a search that actually ran, silently. The same regression is on record in the reference project, **where the item vanished with no observation of any kind**.」——项目已经认出这个形态，只为 `web_search_call` 一种 item 开了后门，**其余全部 item 类型仍然是「vanished with no observation of any kind」**。
3. **它比候选修的那三个事件更可能发生。** 那三个事件在 134336 个 operation 里 0 次（见 §3.1）；`_close` 找不到 draft 这件事**已经在生产上发生过至少一次**。

按用户裁决的字面——「即使暂时没有修复，这些路径也绝不能静默」——S3 比 `response.cancelled` 更符合裁决要保护的东西。

**S1／S2（`SseEvent.json()` 吞掉解析失败）——major（确凿）。** 它是 S3～S6 的**上游放大器**：一个坏帧在这里变成 `{}`，然后 `kind = event.event or ""` 仍然拿到事件行的名字，于是**带着一个空 payload 走进正常分支**，在 S3／S4 那里安静地丢内容。实测 A1 就是这条复合路径：`response.output_item.done` 的 JSON 被截断 → `json()` 给 `{}` → `_item_key({})` 得到 `""` → draft 找不到 → 整块消失，全程零记录。

而且这一处的注释写的是「Decode the payload, or return an empty mapping when it is not an object」——它**描述了行为，没有给理由**。按项目规则 `never-swallow-errors`：「Even for an expected error, at minimum leave a comment stating why」。这里连「为什么可以吞」都没写。

**S7（不认识的事件名）——minor，但有一条本仓自己的对照。** 候选的提交信息把这一条列为明确不做，理由是「Reporting those without noise needs a list of the ones we ignore on purpose」——这个理由成立，我不反对本次不做。但值得记下来：**legacy 链路是做了的**。`src/app/openai/responses_stream_parser.py:222`：

```python
return (self._unsupported(event, event_type),)
```

legacy 对每一个不认识的事件产出一个 `UnsupportedResponsesEvent` 记录。新链路是裸 `return ()`。这是一处**新旧链路的能力回退**，不是新链路从未拥有过的能力。

顺带，A7 里我用的两个「不认识的事件名」都是 SDK 3.3.1 里真实存在的：`response.refusal.done`（模型拒答的正文，整段丢弃）与 `response.mcp_call.failed`。前者尤其值得单独看一眼——现网 Anthropic 腿录到过 1 次 `refusal` 的 stop_reason（`reports/260821-upstream-termination-reasons.md:71`），说明拒答这条路是通的。

**S8（usage 转换失败）——minor（确凿）。** 它同时踩了本仓自己反复写下的两条：`Terminal.upstream_usage` 的注释说「`None` rather than an empty mapping, because those are different answers. A usage of zero is a measurement; not having asked is not.」——而 `_anthropic_usage` 的 `except → return {}` 恰好制造了 `usage={}`，与 `Terminal.usage` 的默认值 `{}` 无法区分。实测 A8 印证：`terminal.usage={}` 而 `upstream_usage` 里躺着那个坏值。至少该有一行 debug。

**S9（`decode_json`）——不是缺陷，是这一批里唯一做对的那个。** 它不吞：把解不开的文本包成 `{"__raw": …}` 带下去，`_json_arguments` 在出口把原文还回客户端。注释写明了理由。**这就是「知道自己不处理、但不静默」的正确形态**，而且不用日志——把事实留在数据里比留在日志里更强。可以拿它当本次裁决落地的样板。

### 2.3 与 §1 无关但同族的一条：本仓自己的 WS 路由用的是嵌套形

`src/app/routes/responses_ws.py:36,73,81,91,97` 一律发 `{"type": "error", "error": {...}}`。这是本仓自己在选嵌套。加上 Anthropic 腿也是嵌套，`_failure_words` 的扁平取词在本仓里是**孤例**，这一点为 §1.3 添一条旁证。

（该 WS 路由是 `async for event in ws_client.create_response(...)` → `websocket.send_json(event)` 的**原样转发**，不经过任何 assembler，所以候选的改动碰不到它，也不需要碰。记在这里只是为了说明取词形状的家族倾向。）

### 2.4 我给主会话的建议（不是本次必须做）

**本次不必扩大范围。** 候选做的事是对的、自足的、可交付的。但按 `no-silently-cut-but-defer`，上面这批不该消失在评审报告里。建议把 S1/S2、S3、S8 三条登记进 `.dev/docs/upstream/retry-and-continuation/deferred.md`，写清「已知不处理、当前不留痕」，并注明 S3 已在生产上击中过一次。S7 建议同时记下「legacy 有 `_unsupported`、新链路没有」这条能力差。

---

## 3. 噪声风险：`warning` 级选对了吗

### 3.1 「零观测」是真的零，不是看不见——**证实，但候选把理由说反了**

我去核了 134336 这个数字的来源：`reports/260821-upstream-termination-reasons.md §1.1`。它扫的是现网 copilot-api-js 四个 history 库里**变换图的根帧**，合计 **29 974 321 根帧**，逐事件计数：

| 库 | 有根帧的 op | 根帧数 | `response.completed` | `response.incomplete` | `response.failed` | `response.cancelled` | 根 `error` 帧 |
|---|---|---|---|---|---|---|---|
| **合计** | **134 336** | **29 974 321** | **64 351** | **20** | **0** | **0** | **0（真上游）** |

**关键点：这份测量是有鉴别力的。** 同一次扫描在同一批帧里数出了 64351 次 `response.completed` 和 20 次 `response.incomplete`——如果有一条 `response.failed`，它会被数到。这不是「没人在看」，这是**看了三千万根帧，一条都没有**。

而候选的提交信息写的是：

> 第 4 条 records zero of these across 134336 operations **with nothing in place that would have reported one**.

代码注释 `openai_responses.py:410` 略缓和一点，但仍是同一句：

> 第 4 条 records **zero** of these events across 134336 operations, **and until now there was nothing that would have reported one if it had arrived**.

**这是错的，或至少是把两件事缝在了一起。** 「没有东西会报告它」说的是**本代理自己的运行时**；「134336 个 operation 零观测」说的是**另一个服务的录制**，而那份录制恰恰是会报告它的。两句并排放，读起来像是在说那个 0 不可信——而它是可信的。

**这一条要紧，因为它正好是级别选择的依据。** 讽刺的是，把话说对之后，`warning` 的理由**更强**了：既然三千万根帧里真的一次都没有，那么它真出现一次就值得一条 warning。若那个 0 真的是盲区，反而不知道频率，选 warning 才是赌。

**判定：minor（确凿），只需改文字。** 建议改成大意为「一次都没录到——而且那份测量在同一批帧里数出了 64351 次 `response.completed`，所以它是有鉴别力的零；本代理自己此前不会报告，是另一半」。

### 3.2 会不会有常态路径触发 `response.cancelled`：**证伪常态触发**（强，足以行动）

三条证据：

1. **本仓从不请求上游取消。** SSE 上取消一次 response 要走带外的取消端点。
   ```
   $ rg -n 'responses/[^"]*/cancel|/cancel' src/
   （无命中；同一命令下 `\.cancel\(\)` 的 8 处命中全部是 asyncio 的 task/scope 取消）
   ```
   正样本对照：`rg -c '/responses' src/` 在 10 个文件里有命中，证明这类路径字符串确实搜得到。
2. **客户端离开时我们是拆连接，不是发取消。** `read_events`（`sse_source.py:85-87`）在 `finally` 里 `await close()`；`_events_with_ping` 的 `finally` 通过 `finish_stream_cleanup` 取消在飞的 pull。上游连接被拆掉之后不会再有事件读回来。
3. **官方那张表描述的是 WebSocket。** `chatWebSocketManager` 跨回合复用连接，取消在那里是**带内**消息，所以 VS Code 里按一下 Esc 的正常结局就是 `response.cancelled`。我们这条链路不是 WS——本仓的 WS 路由（`routes/responses_ws.py`）是原样转发，不经 assembler（§2.3 已核）。

结论：**在本改动覆盖的 SSE 链路上，没有已知的常态路径会产生 `response.cancelled`。** `warning` 级不会因它变成噪声。

**一个保留**：这条结论的有效期绑在「我们不走 WS 上游」上。若日后 `responses_ws` 那条腿接进 assembler，`response.cancelled` 会立刻从「罕见」变成「用户每次按 Esc」，届时这一级别必须重估。建议把这句话写进代码注释——它是这个级别选择的**失效条件**，而失效条件不写下来就等于没有。

### 3.3 `error` 会不会常态触发：**倾向**不会，但比 `cancelled` 弱

`error` 在同一批录制里也是 0 次。但 `ghc-api-py` 为「HTTP 200 之后立刻 `response.failed`、一个 token 都没产出」专门做了一个**默认开启**的重试开关（`reports/260821-...:113` 引 `/home/xp/src/refs/ghc-api-py/README.md:155-162`，`enable_responses_early_failure_retry`）——别人为它写默认开启的开关，说明**别人见过，而且不止一次**。

所以我不能说「一定罕见」。**倾向**：即便它比我们录到的频率高，一次上游明确失败本来就该在操作者的日志里露面，`warning` 仍然是对的级别。真正会变成噪声的门槛是「每次请求都触发」，而没有任何证据指向那里。

### 3.4 级别与本项目既有惯例的对照：**证实**（确凿）

本项目有一处把级别选择的判据写进注释的先例，`translation_driver/openai_responses.py:300`：

> INFO rather than DEBUG: a client with web search switched on triggers this every request, **so it is a setting and not a warning** — but it is also the only place an operator can see that the declaration they sent is not the one that went out.

判据是**频率 + 可操作性**。候选的事件：频率已知为 0，可操作性高（上游明确说了这次不行）。按同一把尺子量，`warning` 是对的。

---

## 4. 健壮性：`_failure_words` 在畸形 payload 下会不会抛

### 4.1 不会抛——**证实**（确凿）

探针：`/tmp/probe_failure_words.py`，21 组畸形输入，全部真跑。正样本对照在第一组（良构输入能打出原话，证明探针确实走到了那个分支）。

```
=== POSITIVE CONTROL: well-formed, expect a log line with words ===
R error flat (OpenAI shape)          ok | ... code='server_error' message='boom'
R response.failed nested             ok | ... code='rate_limit_exceeded' message='boom'
A error nested (Anthropic shape)     ok | ... type='overloaded_error' message='slow down'

=== MALFORMED: does anything raise? ===
R failed: response is a string        ok blocks=() seen=False | ... code='' message=''
R failed: response is a list          ok ... code='' message=''
R failed: response is null            ok ... code='' message=''
R failed: error is a string           ok ... code='' message=''
R failed: error is a list             ok ... code='' message=''
R failed: code is a number            ok ... code='500' message='x'
R failed: code is null                ok ... code='None' message='x'
R failed: code is a dict              ok ... code="{'a': 1}" message='x'
R failed: message is a list           ok ... code='c' message='[1, 2]'
R error: code is null                 ok ... code='None' message='x'
R error: code is a number             ok ... code='429' message='x'
R cancelled: bare {}                  ok ... code='' message=''
R failed: payload is a JSON array     ok ... code='' message=''
R failed: payload is invalid JSON     ok ... code='' message=''
R failed: payload is a JSON string    ok ... code='' message=''
R error: huge message (1MB)           ok ... code='c' message='<...1MB of x...>'
A error: error is a string            ok ... type='' message=''
A error: error is a list              ok ... type='' message=''
A error: type is a dict               ok ... type={'a': 1} message='m'
A error: bare {}                      ok ... type='' message=''
A error: invalid JSON                 ok ... type='' message=''
```

**21/21 全部返回、无一抛出，`seen` 全部保持 `False`。** 提交信息声称的「written to survive being wrong about them — a missing key reads as empty rather than raising」**成立**。这一条比测试只喂空 payload 覆盖得宽，我确认它不是靠运气。

### 4.2 但有一处会说谎：`code: null` 打成 `code='None'`——minor（确凿）

```
R error: code is null (SDK says str|None)   ok ... code='None' message='x'
```

`str(None)` 是四个字符 `None`。这**不是畸形输入**：SDK 里 `ResponseErrorEvent.code -> str | None`（我上面已经核过），`code: null` 是**文档化的正常形状**。于是日志行会印 `code='None'`，读起来像上游说了一个叫 `None` 的错误码，而事实是上游什么都没说。

这正好是本仓自己在同一个文件里点名过的陷阱，`openai_responses.py:536` `_upstream_cut_this_item_short` 的 docstring：

> `str()` is not used on the way in: an absent field and a null one both mean upstream said nothing, and **`str(None)` is the four characters `None`**, which is not `"incomplete"` but is also not a value upstream ever sent.

也是项目记忆「日志行上的缺席读不出来」的同一形态。修法一行：`str(holder.get("code") or "")`，或先取值再 `isinstance(..., str)`。

同族的还有 `code is a dict → code="{'a': 1}"`、`message is a list → message='[1, 2]'`——这两个是真畸形，`str()` 至少没丢信息，我不认为值得为它们加分支。**只有 `None` 那一个是正常形状被印错。**

### 4.3 Anthropic 腿：值不经 `str()`，`%r` 直出——**仅存档**

```
A error: type is a dict    ok ... type={'a': 1} message='m'
```

`anthropic_messages.py:281-282` 传的是 `detail.get("type", "")` 原值，`%r` 会把 dict 整个印出来。不抛、不丢信息。与 Responses 腿的 `str()` 不一致，但两边都能用。**仅存档**，不建议为对齐而改。

### 4.4 一条不建议动的：1MB message 原样进日志

`R error: huge message (1MB)` 把一百万个字符整个写进日志行。我**不建议**加截断——上游 message 在实践中是短的，加一个长度上限是为没见过的场景造机制，与本项目「不预建完备状态空间」的规矩相抵。**仅存档**，写在这里只是让主会话知道我看过并且是有意不提。

### 4.5 门禁与测试现状

```
$ uv run ruff check src tests
All checks passed!

$ uv run pytest tests/unit/pipeline/delivery -q
131 passed in 22.72s
```

（未跑 `ruff format`。未跑全量回归——那是合入前主会话的事，不是本次评审的判据。）

---

## 5. 与 G1 分支 `fix/upstream-error-events` 的关系

### 5.1 事实（确凿）

```
$ git log --oneline -8 fix/upstream-error-events
fd6b591 docs: narrow a comment's claim to the declaration that actually backs it
eb6cdd6 fix: stop a failed stream reporting itself as a finished one
4ffa95f feat: say what upstream said when it ended a stream early
9222ea7 docs: record where the httpx2 migration stands, ...   <- merge-base with d19ae45

$ git branch --contains fd6b591 --all
+ fix/upstream-error-events          （未进 main）

$ git branch --contains c01191f --all
+ main                               （候选基线在 main 上）

$ git diff --stat 9222ea7..fd6b591
 src/app/observability/request_log.py              |  2 +
 src/app/pipeline/delivery/assembler.py            | 65 ++++++++++++++++
 src/app/pipeline/delivery/stream.py               | 32 +++++++-
 src/app/server/pipeline_app.py                    | 37 ++++++++--
 tests/int/test_pipeline_app.py                    | 90 +++++++++++++++++++++++
 tests/unit/observability/test_request_log_file.py | 31 +++++++-
 tests/unit/pipeline/delivery/test_sse_assembly.py | 62 ++++++++++++++++
```

### 5.2 **G1 已经不能合并了**，与本改动无关——blocker（对 G1，不对候选）（确凿）

模块布局在两条线上已经分叉：

```
$ git ls-tree --name-only fd6b591 src/app/pipeline/delivery/
__init__.py  anthropic_sse.py  assembler.py  blocks.py  sse_source.py  stream.py  synthetic.py

$ git ls-tree --name-only d19ae45 src/app/pipeline/delivery/
__init__.py  assembling.py  blocks.py  formats  framing.py  sse_frame.py  sse_source.py  stream.py
```

G1 的核心补丁（`4ffa95f`）改的是 `src/app/pipeline/delivery/assembler.py`，**这个文件在候选这条线上已经不存在**——它被拆成了 `assembling.py` + `formats/anthropic_messages.py` + `formats/openai_responses.py`，另外 `anthropic_sse.py` / `synthetic.py` 也各自搬了家。**G1 无论如何都要手工重放，不能靠 merge／cherry-pick。** 这与 `d19ae45` 是否存在无关，本次改动没有让它变得更难。

**还有一个静默陷阱**（CLAUDE.md 已经点名过这一形态）：

```
$ git ls-tree --name-only fd6b591 docs/
docs/agents
docs/tmp

$ git ls-tree --name-only d19ae45 docs/
docs/.human-controlled
```

G1 的基线 `9222ea7` 早于 2026-08-21 的文档迁移，**它的树里还带着 `docs/agents/` 与 `docs/tmp/`**。按 CLAUDE.md：「a squash takes its tree — so integrating one reintroduces them silently, with no conflict and no error」。若日后用 squash 整合 G1，必须在事后核一次 `docs/` 只剩 `.human-controlled/`。

### 5.3 语义上重复还是冲突：**重复，且 G1 是超集**（强，足以行动）

G1 `4ffa95f` 做的四件事：

| # | G1 做的 | 候选做的 | 关系 |
|---|---|---|---|
| a | 新增 `UpstreamFailure` + `Terminal.failure`，两个 assembler 的 `error`／`response.failed` 分支**把上游原话记进记录** | 同样的两个分支，**把上游原话打进日志** | **重复**——同一个识别点、同一批事件、同一份取词 |
| b | `stream.py` 在 `not terminal.seen` **之前**插一格，发一个携带上游原话的 error 帧 | 明确不做（`seen` 保持 false，客户端仍收截断帧） | G1 独有 |
| c | `pipeline_app._ending()` 加一格，避免「帧说 overloaded、日志说什么都没说」自相矛盾 | 明确不做 | G1 独有 |
| d | `UPSTREAM_WORD[dialect]` 修掉截断文案在 Anthropic 腿上写「Responses」（deferred 第 19 条） | 不涉及 | G1 独有，且与本题无关，可单独摘出来 |

**所以 `d19ae45` 是 G1 的 (a) 的一个变体实现：把「记进记录」换成「打进日志」。** 两者不是互补，是同一格里的两种写法。

**合入顺序的讲究（我的倾向，够据此行动）**：

- **候选先落，G1 后重放**——这是我推荐的。候选是自足的、可交付的、当天就能进 main 的；G1 要手工重放到新布局上，工作量按 `4ffa95f` 的四件事算是本改动的数倍。用「先看得见，再处理」的次序符合用户裁决本身的措辞（「即使暂时没有修复……也应该打日志」）。
- **但重放 G1 时必须一并处理候选留下的那行 warning**，否则会出一个自相矛盾：G1 之后上游失败**是**被处理了（发帧、`_ending()` 说话、`RequestLine.upstream_error` 落盘），而候选那行日志仍然写着 `it is not acted on yet`。**这句话届时会变成一句谎。** 处置有两条，我倾向后者：
  1. 删掉 warning，让 `Terminal.failure` + `_ending()` + JSONL 承担观测——它们比日志行更结构化（项目记忆「展示层读聚合记录，不读原始对象」同向）；
  2. **保留一行，但改掉措辞与级别**，降到 `info`／`debug`，作为「事件在 assembler 这一层被认出来了」的接线证据。

  我倾向 (1)：G1 落地后 warning 是纯冗余，而 `it is not acted on yet` 这类**带保质期的断言**留在代码里，正是本仓踩过的「阻断性观察有保质期」那一类。

- **反过来（G1 先）也可行**，那样候选就整个不必要了。但 G1 现在动不了（§5.2），所以这条在现实里不成立。

**给主会话的一条具体提醒**：候选提交信息与两处代码注释里都有指向 `deferred.md` 第 4 条的引文，而 G1 落地会让第 4 条被划掉。**引文要一并更新**，否则会留下一条指向已关闭条目的活引用。

### 5.4 顺手核到的一条：G1 的 `_read_failure` 有和候选一样的 §1.3 缺陷

`4ffa95f` 的 `ResponsesAssembler._read_failure`：

```python
if kind == "response.failed":
    raw = data.get("response")
    ...
    source = response.get("error")
else:
    source = data          # <- 扁平
```

同样只认扁平形。**所以 §1.3 那条修法在 G1 重放时也要带上**，两处都别漏。这条我登记在这里，是因为它一旦被当成「候选独有的问题」修掉，重放 G1 时就会静默倒回去。

---

## 6. 日志措辞与级别是否合本项目惯例

### 6.1 级别：**证实**（见 §3.4）

### 6.2 措辞：**证实**（确凿），两腿写法不同是**有理由的不同**

两行的模板不一样：

```python
# anthropic_messages.py:279
"upstream sent an error event mid-stream; it is not acted on yet: type=%r message=%r"
# openai_responses.py:412
"upstream sent %r mid-stream; it is not acted on yet: code=%r message=%r"
```

字段名 `type=` 与 `code=` 也不一样。**这不是不一致，是对的。** G1 分支自己的 `UpstreamFailure` docstring 把理由写得最清楚：

> `type` and `code` are not the same fact wearing two names. Anthropic sends its own error taxonomy — `overloaded_error`, `api_error` — which is already the vocabulary this proxy speaks downstream. The Responses leg's `code` is OpenAI's and has no Anthropic spelling.

两腿印不同的字段名，正是不把两件不同的事装成一件。**保持现状。**

句式与本仓惯例一致：小写起首、`%s` 风格惰性格式化、把上游原话放句尾、不用句号结尾。对照 `translation_driver/openai_responses.py:222` 与 `subscribers/blank_text.py:126` 成立。

### 6.3 `it is not acted on yet` 这句话——minor（强）

它是**当前为真、且会被 G1 作废**的一句断言（§5.3）。写在这里没错，但它有保质期，而代码里没有任何东西会在它过期时提醒人。建议在该行旁补一句指向 `deferred.md` 第 4 条的话——注释里已经有了，那就够；我只是把「这句话会过期」这件事显式登记，供 G1 重放时对照。

### 6.4 注释里的另一条引文：`../h2-goaway/findings.md`——**证实存在**（确凿）

`anthropic_messages.py:276` 引 `../h2-goaway/findings.md`，相对 `.dev/docs/upstream/retry-and-continuation/` 解析为 `.dev/docs/upstream/h2-goaway/findings.md`。

```
$ ls -la .dev/docs/upstream/retry-and-continuation/deferred.md .dev/docs/upstream/h2-goaway/findings.md
-rw-r--r-- 1 xp xp 17154 Aug 22 15:05 .dev/docs/upstream/h2-goaway/findings.md
-rw-r--r-- 1 xp xp 35030 Aug 22 18:51 .dev/docs/upstream/retry-and-continuation/deferred.md
```

两个路径都存在，相对路径也解析得对。**但两腿写法不统一**：Responses 腿写的是绝对仓库路径 `.dev/docs/upstream/retry-and-continuation/deferred.md`，Anthropic 腿混用了绝对路径和一个相对路径 `../h2-goaway/findings.md`——而这个相对路径的锚点是**上一句里提到的那份文档所在的目录**，不是当前源文件所在的目录。读者在 `src/app/pipeline/delivery/formats/` 下解析 `../` 会走到 `src/app/pipeline/delivery/`。**建议改成仓库根相对的完整路径**，与同一段里的另一条引文一致。**minor。**

### 6.5 测试：一条 minor

`test_a_responses_failure_event_is_reported_with_upstream_s_own_words` 的第三组参数

```python
("response.cancelled", {"response": {"error": {"code": "cancelled", "message": "boom"}}}, "cancelled"),
```

断言的 `code == "cancelled"` 是**编出来的**。SDK 里 `ResponseError.code` 是一个 20 项 Literal，没有 `cancelled`；而现网录制显示 `response.error` 在 `incomplete` 上恒为 `null`（`reports/260821-...:63`），`cancelled` 大概率同理。这条测试实际钉住的只有**我们的分发走对了分支**——那是换个上游也成立的判据，按项目记忆「用 mock upstream，别反复实测上游」是合法的。但参数表读起来像在钉上游形状。

建议在该测试的 docstring 里补一句：形状是二手的，本测试钉的是分发不是形状。**minor，不阻塞。**

---

## 7. 我明确**不**提的建议

按本项目规矩逐条声明，免得主会话花时间判断我有没有漏说：

- **不建议**为这三个事件加参数矩阵、加门禁、加验证状态机，或把 `_failure_words` 的健壮性做成一个 property test。§4 的 21 组反例是**评审用的一次性探针**，不建议落成回归测试——现有 4 条测试已经钉住了正样本与空 payload，够了。
- **不建议**为 1MB message 加长度截断（§4.4）。
- **不建议**去取一份真实的 error 帧录制来解 §1.3。计划文档 §2.4 已经算过命中概率不高，且那个 db 属于仍在运行的 `4141` 服务。§1.3 的修法不依赖录制——两种形状都认下来即可，代价一行。
- **不建议**本次扩大范围去修 §2 的十处。登记进 `deferred.md` 就够。
- **未跑** `ruff format`（项目禁止）。**未改**任何仓库文件（本报告除外）。**未触碰**主树、未触碰 `4141` 服务、未打开任何 history db。
