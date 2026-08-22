# 四条裁决实现评审（`eb74a60`..`630f7f3`）

日期：2026-08-22。评审员：独立只读评审 agent。
评审对象：`eb74a60` `3a05fb0` `b92d4ce` `2769a64` `4c7129a` `ebb2fec` `630f7f3` 七个提交（区间内另有同伴的 `1018e3a` `66b63c9` `e81f07f`，已按归属排除）。

## 0. 方法与证据基线

- **代码一律读提交态**（`git show <commit>:<path>`）。主树工作区当前有同伴在途改动（`docs/.human-controlled/` 新增、`Dockerfile`、`exp/260820-h2-stream-cap/` 等），一律未作判据。
- **未修改仓库任何文件**（本报告除外）。所有运行与变异都在 `git archive` 导出的一次性副本里做：`/tmp/rev630`（= `630f7f3`）与 `/tmp/revbase`（= `e81f07f`，即 `630f7f3^`）。变异后逐次恢复并复跑确认还原。
- 解释器统一用主树 venv：`/home/xp/src/ghc-api-proxy-py/.venv/bin/python`，`PYTHONPATH` 指向副本树的 `src`（已确认 import 来自副本而非主树）。

基线数据（全部在 `/tmp/rev630` 上实测）：

| 项目 | 结果 |
|---|---|
| `pytest tests` | **1701 passed, 3 skipped**（101s） |
| `ruff check src tests` | **All checks passed** |
| `pyright src tests` | 26 errors —— 与 `e81f07f`（同伴提交，`630f7f3^`）**逐项相同**，不归这七个提交 |
| 七个提交逐个 `import app.server.pipeline_app, app.server.composition, app.cli` | 仅 `2769a64` 报 `ImportError: ContinuationSupport`，`4c7129a` 之后恢复 |

pyright 那 26 条的落点是 `tests/unit/upstream/test_stream_cap.py`(18)、`src/app/server/pipeline_app.py`(5，全在同伴的 `_hand_back` 里)、`src/app/upstream/stream_cap.py`(3)。我在 `e81f07f` 导出树上跑了同一条命令，错误数与文件分布完全一致，因此归因是可写下的，不是推测。

---

## 1. 裁决落实度总表

| 裁决 | 落实 | 判定 |
|---|---|---|
| 1. `/chat/completions` 一次性交付 | `one_shot_delivery` + `delivers_blocks` + 一次性路径接线 | 做到了，但**收尾语义与声称不符**，见 M-1 |
| 2a. 删 `--ghc-api-base-url` | `3a05fb0`，并加了「flag 不得回流」的断言 | 做到了 |
| 2b. 订阅自动识别移植到新链路 | `resolve_provider_base_urls`，三个入口全覆盖 | 做到了；**没有新增 `account_type` 配置项**（已核实）；但启动失败面变了，见 M-4 |
| 3. 移除 copilot token 后台刷新循环 | `eb74a60`，连带删 `next_refresh_delay` / `minimum_refresh_interval` / `refresh(force=)` | 做到了，无残留引用 |
| 4. Responses 直接块级成帧 | `responses_sse.py` + `OutboundFramer` + `framer=` 传参 | 做到了；provenance 声明与 SDK 字段两处不实，见 M-2 / M-3 |

**没有发现越权扩大范围（做多）**。七个提交的 diff 我逐个读过，每一处改动都能对上某条裁决，没有夹带无关重构。

**没有发现静默裁掉（做少）**。裁决 2 的两半、裁决 3 的连带删除、裁决 4 的接线，都写进了提交信息并附了理由。

### 已核实为正确的关键点（附证据，不是「看着对」）

1. **`framer=None` 时与改动前逐字节相同**。写了 11 场景探针（两块文本、thinking+tool_use、`signature_compat=False`、无 terminal、空流、带 usage、空 stop_reason、client deadline、torn 无 replay、max_tokens 交接、torn 交接），在 `e81f07f` 与 `630f7f3` 两棵树上各跑一遍：**输出完全一致**。随后把 `AnthropicFramer.terminal` 里的 `or "end_turn"` 摘掉做正样本对照，探针立刻报出差异；恢复后再次一致。这条结论强到可以据以行动。
   —— 特别覆盖了任务书点名的三处：`_hand_over` 的 terminal 合成（`framing.terminal(replace(terminal, stop_reason=TOOL_USE_KIND))` 与旧的 `terminal_frames(stop_reason=TOOL_USE_KIND, usage=terminal.usage or None)` 等价，因为 `"tool_use" or "end_turn"` 就是 `"tool_use"`）、keep-alive（`AnthropicFramer.keepalive()` 与 `PING_FRAME` 同为 `b": ping\n\n"`，且 `PING_FRAME` 仍在 `stream.py` 里、测试仍在导入它）、两处 error frame。

2. **`framer_for` 选 `route.inbound_format` 而非 `dialect_for`，主产品路径确实仍收 Anthropic 事件**。把 `framer_for` 的判据换成 `dialect_for(handled) is ReplyDialect.RESPONSES` 后，`tests/int/test_pipeline_app.py` 立刻两条变红，其中 `test_an_anthropic_client_on_a_responses_upstream_still_gets_anthropic_events` 报 `assert 'response.created' == 'message_start'`。这条测试走的是生产入口 `POST /v1/messages` + Responses 上游 cassette 形状，不是靠测试名。恢复后 107 passed。

3. **`output_index` 重编号是真判据**。把三处 `index = self._output_index` 换成 `index = block.index` 后，`test_output_index_is_renumbered_rather_than_taken_from_the_block` 变红，且异常来自 **SDK 自己**（`openai/lib/streaming/responses/_responses.py:344: IndexError`），不是测试写死的期望。oracle 选得对，没有被绕过。

4. **`api_base_url` 已配置时确实不探测**：`if provider_config.type != PROVIDER_TYPE or provider_config.api_base_url: continue`，且 `test_a_hand_written_base_url_is_never_probed` 断言 `seen == []`，同一 harness 里另有测试证明 `seen` 会被填满（正样本对照已具备）。

5. **无 token 不把服务弄挂**：`NoGitHubToken` 被捕获、记 info、continue；`test_absent_credentials_leave_the_base_url_unresolved` 断言 chain 仍能建起来且落到 individual host。

6. **没有新增 `account_type` 配置项**。全区间 diff 里唯一新增的 `account_type` 出现是 `GhcClientConfig(account_type=...)`（库内既有 dataclass 字段）与文档串。`src/app/config/settings.py:33` 的 `account_type` 是 legacy `AppSettings` 的，早已存在。

7. **`web_search_call` 的语义损失声明属实**：`ResponsesAssembler` 在 `output_item.done` 上确实把它改写成 `kind = TEXT` 的散文块（`assembler.py:323-329`），所以 `responses_sse.py` 顶部那段「一个 `web_search_call` item 过不了往返」写的是事实。

8. **「没有 cassette 带 function_call」属实**：五份 cassette 全文 grep，`function_call` 出现 0 次。

9. **共享树纪律**：`4c7129a` 修干净了。七个提交逐个导入验证，只有 `2769a64` 一个不可导入，`4c7129a` 之后全绿；其余六个提交的 diff 我逐个 hunk 读过，没有第二处同类夹带。按项目规则「commit 边界只由语义决定」，中途一个不可导入的提交不是缺陷。

---

## 2. 发现

### M-1 `[major]` 一次性交付路径上，client deadline 不产生任何 error frame，客户端重新拿到「200 + 0 字节」

`2769a64` 的提交信息与 `pipeline_app._routed` 里的注释都写着：

> The same guards in the same order as the block path below, so an idle upstream, an expired attempt and an expired client deadline all still end this the way they end that one.

守卫的**顺序与包装**确实一致（我逐层比对过 `with_client_deadline_at` / `_counted_upstream` / `with_deadline_at` / `with_idle_timeout` 的嵌套，两条路径完全相同）。但**收尾方式不一致**。实测：

```
one_shot  -> chunks: []  raised: ClientDeadlineError: client request exceeded its deadline
block     -> last chunk: b'event: error\ndata: {"type":"error","error":{...,"code":"client_deadline_exceeded"}}\n\n'  raised: None
```

`one_shot_delivery` 没有 `try/except`，`ClientDeadlineError` 直接穿出生成器，`_tracked_delivery` 只记账后 re-raise。客户端得到的是：200、`text/event-stream`、**零字节**、连接被中断、没有任何错误帧——**正是 `2769a64` 立项要消除的那个症状**，只是触发条件从「协议不认识」换成了「超时」。上游守卫（idle timeout / attempt deadline）同理。

而且一次性交付把这件事放大了：块级路径超时时客户端至少已经拿到了已提交的块，一次性路径整个 body 都还在 `bytearray` 里，超时即全丢。

- 改法（择一，我倾向前者）：
  1. 在 `one_shot_delivery`（或它外面那层）捕获 `ClientDeadlineError`，至少发出一帧客户端读得懂的东西，例如 `data: {"error":{"message":...,"code":"client_deadline_exceeded"}}\n\ndata: [DONE]\n\n`。注意**不要**顺手 flush 半截 body——块级路径明确写了「Nothing is flushed first either」，两边应当保持这个一致。
  2. 如果认为在没有出站成帧器的腿上凭空造错误帧超出了「buffer now, parse later」的授权，那就**改正声明**：把提交信息那句「end this the way they end that one」和 `_routed` 里对应的注释改成「守卫相同、收尾不同」，并把这个缺口登记进 deferred。
  当前状态是两者都没做，声明与行为不符，这才是需要修的部分。

### M-2 `[major]` `responses_sse._reasoning` 的 provenance 声明不准确，且掩盖了第二处「无录制支撑」的帧组

`_reasoning` 的 docstring：

> Upstream sends none either — in all three recordings a reasoning item arrives as `added` then `done` with the summary already in place — so this copies that shape rather than inventing a finer-grained one.

逐份解析三份带 Responses 流的 cassette，实测结果：

| cassette | source | reasoning item | `summary` | `encrypted_content` |
|---|---|---|---|---|
| `anthropic_to_responses_stream` (int 2) | live-recording | 有，added+done，中间无 delta | `[]` | 有 |
| `history_responses_stream` (int 0) | history 派生 | 有，added+done，中间无 delta | `[]` | `placeholder` |
| `responses_web_search_stream` (int 1) | live-recording | **没有** | — | — |

两处不实：

1. 是**两份**录制带 reasoning item，不是三份。
2. **三份里 `summary` 全是 `[]`**，没有任何一次「summary already in place」。也就是说 `_reasoning` 里发的 `summary: [{"type": "summary_text", "text": ...}]` 这个形状，**没有任何录制支撑**，它的证据等级和 `_function_call` 完全一样——都是照 SDK 类型推的。

「added 然后 done、中间没有 delta 事件」这一半是有录制支撑的（2/2），要保留。任务书问「还有没有别的未声明的推测」——有，就是这一处，而且它被写成了「照录制抄的」，比不写更容易误导后来人。

- 改法：把该 docstring 改成三句分开的事实：(a) 两份录制里 reasoning item 是 added→done、无 delta 事件，这一点照抄录制；(b) 三份录制里 `summary` 均为空，`summary_text` 的形状取自 SDK 类型，与 `function_call` 同级，无录制支撑；(c) `encrypted_content` 在录制里确实出现过，这一点有支撑。

### M-3 `[major]` `response.function_call_arguments.done` 缺 SDK 声明为 required 的 `name`

模块 docstring 说 function_call 那组「follows the SDK's own types and parser instead of a recording」。用 openai 3.3.1 的模型逐事件核对我方 payload 的必填字段：

```
response.function_call_arguments.done       missing_required=['name']
response.output_text.delta                  missing_required=['logprobs']
response.output_text.done                   missing_required=['logprobs']
（其余 9 种事件 missing_required=[]）
```

也就是说，唯一一组自称「照 SDK 类型来」的帧，恰恰漏了 SDK 类型里的一个必填字段。SDK 的 `construct_type` 是宽松构造，所以测试不会红、真实 SDK 客户端也不会炸——但这正是问题：这个缺失**在当前 oracle 下不可见**，而任何做严格 schema 校验的非 Python 客户端会拒。

- 改法：`_function_call` 的 `.done` 帧补 `"name": <function name>`。同时建议把这项「按 SDK 声明的必填字段逐事件对账」的检查做成一条测试（遍历我方发出的每种事件，取 `ResponseStreamEvent` 联合里对应的模型，断言必填字段齐全）——它是当前测试套完全看不见的一层，而且写起来只有十几行。

### M-4 `[major]` 启动期订阅探测把一次网络调用变成了启动门，需要用户裁决

`resolve_provider_base_urls` 里 `get_copilot_usage` 走 `raise_for_status()`，除 `NoGitHubToken` 外一切异常上抛。三个调用点全在 `try` 里但没有 catch，所以：**有 GitHub token、但 GitHub 返回 403/5xx 或网络抖动时，`serve` / `serve-inherited` / `debug models` 直接起不来**。这个行为被 `test_a_refused_probe_is_raised_rather_than_defaulted` 固化了，是有意为之，提交信息也写了理由（「defaulting to the individual host is how the wrong host stays wrong」）——理由本身站得住。

但它超出了裁决 2 的字面内容（裁决说的是「修复未配置时按订阅自动识别」，没说「探测失败就不许启动」），并且与项目当前的部署目标直接相关：`.claude/rules/00-development-workflow.md` 写的是 systemd/cgroup 托管、socket activation 保 listener 连续性。在那个模型下，一次 GitHub 侧的瞬时故障会让新进程起不来；旧进程已经交出 listener 的话，这不是「维持现状」而是「服务中断」。另外它还给每次启动加了一个到 `api.github.com` 的往返延迟。

我不认为应该改成静默回落（那会重新引入这次要消除的缺陷）。我倾向的候选：把「认证类失败」（401/403）与「传输类失败」（超时、连接错误、5xx）分开——前者上抛，后者记 warning 后 continue 并留待首个请求时再解析；或者保持现状但让用户明确知情。

- 建议动作：**不要自行改**，把这个取舍连同上面两个候选一起交用户裁决，并按 `no-silently-cut-but-defer` 记进 deferred。

### m-5 `[minor]` `_FINISHED` 是反向白名单：任何未列出的 stop reason 一律变成 `response.incomplete`，且 reason 直接透传我方词汇

实测各 stop_reason 的落点：

| `Terminal.stop_reason` | 产出事件 | `incomplete_details` |
|---|---|---|
| `end_turn` / `tool_use` / `""` | `response.completed` | — |
| `max_tokens` | `response.incomplete` | `{"reason": "max_output_tokens"}` ✓ |
| `incomplete` | `response.incomplete` | `{"reason": "incomplete"}` ✗ |
| `stop_sequence` / `pause_turn` / `refusal` | `response.incomplete` | 原样透传 ✗ |

`"incomplete"` 是**可达的**：`ResponsesAssembler._read_terminal` 在上游发 `response.incomplete` 但没给 reason 时，正是把 stop_reason 置为字面量 `"incomplete"`（`assembler.py:355-357`）。于是我方会发出一个 Responses 词汇表里根本不存在的 `incomplete_details.reason`。Anthropic 那几个值（`stop_sequence` 等）需要 /responses 入站配 Anthropic 方言装配器，当前被翻译器注册表挡住（见 m-13），可达性低，但白名单的默认方向仍然是危险的那一边。

- 改法：`incomplete` 这一支映射回 `None`（`incomplete_details: null` 是上游自己的合法形态）；对未识别的 reason，要么落到 `null`，要么在代码里写清「原样透传是有意的、且知道它不在枚举里」。

### m-6 `[minor]` `ResponsesFramer.block` 对未知 kind 静默降级为空 text item

`block()` 只分 `TOOL_USE` / `THINKING` / 其它，其它一律走 `_message`，而 `_message` 读 `payload["text"]`。实测传一个 `server_tool_use` 块进去，得到的是一整组 `output_item.added` → … → `done`，`text` 全为 `""`——一个空消息 item，没有任何警告。

可达路径：`AnthropicAssembler` 的 kind 直接取自 `block["type"]`（`assembler.py:157`），所以 `server_tool_use` / `web_search_tool_result` / `redacted_thinking` / `image` 都可能出现；而 `framer_for` 在 `handled.synthesized` 为真时会先通过 `delivers_blocks` 的 carve-out，再按 `inbound_format` 选到 `ResponsesFramer`。也就是说「/responses 入站 + 合成的 web-search 失败答复」这条组合会把 `server_tool_use` 喂给 `ResponsesFramer`。我没能构造出这条路径的端到端复现（需要 /responses 入站触发 `WebSearchNotExecutable`），所以这条的**权重是「结构上成立、可达性未证实」**，按 minor 记。

- 改法：`block()` 里给未知 kind 一条显式分支——要么落成带说明文字的 message item（像 assembler 处理 `web_search_call` 那样），要么 raise。当前这种「静默产出空内容」是本项目多次付过代价的形状。

### m-7 `[minor]` `response.output_text.delta` / `.done` 缺 `logprobs`

见 M-3 的对账表。录制里上游**是发这个字段的**（`anthropic_to_responses_stream` 的 delta 事件键集为 `content_index / delta / item_id / logprobs / obfuscation / output_index / sequence_number / type`），SDK 也把它声明为必填。补 `"logprobs": []` 即可。

### m-8 `[minor]` `response.id` 是裸 UUID，没有 `resp_` 前缀

实测：`response.id = f0de7649-3580-4d74-b727-d120e2563594`，而 item id 是 `rs_<uuid>_0` / `fc_<uuid>_1`。`framer_for` 直接把 `context.id`（`uuid4()` 字符串）当 `response_id` 传进去。真实 Responses 的 response id 一律是 `resp_` 前缀，客户端可能据前缀分派或校验，`previous_response_id` 复用时尤其。

- 改法：`ResponsesFramer.__init__` 里对不带前缀的 id 补 `resp_`，与 `msg_` / `fc_` / `rs_` 的做法保持一致。

### m-9 `[minor]` `--account-type` 与 `--ghc-api-base-url` 同族，处置不一致

`3a05fb0` 删掉了 `--ghc-api-base-url`，理由是 2026-08-22 裁决把 base URL 收敛到「探测 或 手写全 URL，无第三条路」。但 `--account-type` 还在，且 `_NO_HOME_IN_SPEC` 给它的理由写的是 `"config.example.yaml has no auth section"`——这句话的意思是「还没移植」，而裁决 2 的更正实际上是让它**永远不会回来**（`account_type` 就是那条被否掉的第三条路）。

好的一面：它不是静默的，`_load_spec_config` 会把它收进 `inactive` 并打印出来，所以不构成 `--ghc-api-base-url` 那种「设了等于没设」的缺陷。

- 改法：要么一并删掉，要么把理由改写成「2026-08-22 裁定订阅由探测决定，本项不再有归宿」。同时 `resolve_provider_base_urls` 的 docstring 里那句「Two ways to reach a base URL and no third」在 `--account-type` 还挂在 `--help` 上的情况下读起来是自相矛盾的。

### m-10 `[minor]` `refresh_in` 已无人读，却仍是硬性必填字段

`eb74a60` 删掉调度后，`CopilotTokenInfo.refresh_in` 在整个 `src/` 里再无读者。但 `refresh()` 里仍是 `refresh_in=int(raw["refresh_in"])`，缺失即 `RuntimeError("invalid Copilot token response")`——一个没人读的字段现在能让每个请求失败。提交信息给的理由（「it is part of reading the response」）作为保留动机成立，但没覆盖「保留 ≠ 必填」。

- 改法：`int(raw.get("refresh_in", 0))`，或干脆连字段一起删。风险实际很低（GitHub 一直发这个字段），所以是 minor。

### m-11 `[minor]` 「the three cassettes in this repository」——实际有五份

`responses_sse.py` 顶部与 `_function_call` 里都写「the three cassettes in this repository」。`tests/int/cassettes/` 下有**五**份，其中三份带 Responses 流。实质结论（五份都没有 function_call）我已核实为真，但这个措辞把「带 Responses 流的三份」写成了「仓库里的三份」，后来人加第六份 cassette 时会读错这句话的适用范围。

### m-12 `[minor]` 四条裁决目前只活在提交信息与 `.dev/docs/tmp/`

`.dev/docs/` 下所有提到 `stream_delivery` / `assembler_for` / `delivers_blocks` / `OutboundFramer` 的文件，无一例外都在 `reports/` 或 `archived-*` 里（点内记录，按项目规则不得改写）。没有任何 living document 记录「出站成帧器按客户端腿选择」这条架构事实，也没有记录「chat-completions 暂为一次性交付」这条对外行为裁决。项目规则明写「Distil current conclusions into living documents promptly; do not let a report become the only source of truth」。

- 改法：建一个 `delivery-framing`（或并入既有主题）的 living doc，把四条裁决、当前实现边界（哪条腿有成帧器、哪条没有）、以及 M-1/M-4 两个待裁决项写进去；`260822-responses-out-framing-design.md` 作为 report 原件归档进该主题的 `reports/`。

### m-13 `[minor]` `one_shot_delivery` 的「客户端拿回自己协议的 SSE」是有前提的，但没有断言守着

docstring 写「The client asked for `stream: true` and gets its own protocol's SSE back, byte for byte」。这只有在 chat-completions 入站**不需要翻译**时才成立。我实测了两条会打破它的路由，当前都被翻译器注册表挡住：

- `/v1/messages` + 只支持 `/chat/completions` 的模型 → 400 `no translator registered as outbound.to-openai-chat-completions`
- `/chat/completions` + 只支持 `/responses` 的模型 → 400 `no translator registered as inbound.from-openai-chat-completions`

所以今天没有缺陷。但一旦有人注册了 `from-openai-chat-completions` 入站翻译器，`one_shot_delivery` 就会把上游的 `response.*` SSE 原样转给一个 chat-completions 客户端，静默地。

- 改法：在 `delivers_blocks` 或一次性分支里加一条断言/守卫——「无出站成帧器的腿只允许 `translation_required is False`」，否则拒绝。成本极低，且把一个隐式耦合变成显式的。

### n-14 `[nit]` keep-alive 测试的注释声称了一件它没测的事

`test_the_keepalive_is_a_comment_no_parser_turns_into_an_event` 末尾：

```python
    # And it did not consume a sequence number, which would make the numbering lie.
    assert one.keepalive() == b": ping\n\n"
```

这条断言只比对了一个字节常量，跟「有没有消耗 sequence number」无关。想测那件事，应当在 keepalive 前后各取一帧、断言 `sequence_number` 连续。当前是构造性保证（`keepalive` 不走 `_frame`），所以我不认为必须加测试——但注释和断言必须对上，否则下次有人把 keepalive 改成走 `_frame` 时这条测试仍然绿。

### n-15 `[nit]` `pytest.raises(Exception)` 过宽

`test_exhausted_exchange_reports_the_failure_to_the_caller` 用 `with pytest.raises(Exception):  # noqa: B017`。`attempts == 3` 那条断言承担了主要鉴别力，但异常类型完全没约束——把 `_exchange_with_retry` 改成抛 `AssertionError` 也照样绿。建议收窄到 `httpx2.HTTPStatusError`。

### n-16 `[nit]` 文档痛斥 `model_copy(update=...)`，最后一行自己用了它

`resolve_provider_base_urls` 里那段注释专门解释「Revalidated rather than `model_copy(update=...)`. That call does not check the name it is given」，然后函数最后一行是 `return config.model_copy(update={"model_providers": resolved})`。外层这次是安全的（字段名真实存在、值已逐个 `model_validate` 过），但注释的绝对措辞与紧邻的代码打架。建议在那一行补半句说明为什么外层这次可以。

### n-17 `[nit]` `stream_settings(chain)` 在 `_routed` 里被调用两次

一次给 `framer_for` 取 `signature_compat`，一次传给 `stream_delivery`。纯属重复构造，无行为影响。

---

## 3. 总体裁决

**needs-fix。** 四条裁决的核心机制都实现对了，而且实现得相当扎实——`framer=None` 的逐字节等价、`framer_for` 的选择判据、`output_index` 重编号，这三条我都用变异法证明了测试有分辨力，不是恒真绿。裁决 2 的更正也确实遵守了：没有新增 `account_type` 配置项。

需要修的集中在两类。一类是**声明与行为不符**（M-1 的收尾语义、M-2 的 reasoning provenance、M-3 的 SDK 字段），这三条都属于「文档说它照着某个权威做了，实际没有」，在这个项目里是最贵的一类错误，因为它让后来人把推测当成了测量。另一类是 M-4 —— 启动期探测变成启动门，这不是缺陷而是一个超出裁决字面范围的取舍，应当交用户裁决而不是由实现者或评审员定。

---

## 4. 给主会话的交回事项

1. M-4 需要用户裁决（启动探测失败是否应当阻止服务启动），建议把 401/403 与传输类失败分开的候选一并呈上。
2. M-1 需要主会话选一条：补错误帧，还是改正声明并登记 deferred。
3. m-12 的 living doc 缺口不在这七个提交的责任范围内，但由它们造成，建议在本轮收尾时一并补。
4. 复评触发条件：只要 M-1 / M-2 / M-3 中任意一条的修法改动了 `responses_sse.py` 或 `one_shot_delivery` 的出站字节，需要重跑第 1 节那个 11 场景逐字节探针（脚本在 `/tmp/probe_bytes.py`，如需长期保留应移入仓库）。其余发现的修改不影响本报告结论，不需要复评。
