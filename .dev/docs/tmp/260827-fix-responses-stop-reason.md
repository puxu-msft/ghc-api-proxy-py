# retry §16：反方向（`/responses` 客户端 + Anthropic 上游）的 stop_reason 抹平，已修

日期：2026-08-27。主树 `/home/xp/src/ghc-api-proxy-py`，分支 `main`，改动留在工作区，未做任何 git 操作。

改到的文件（仅此两个）：

- `src/app/pipeline/translation_driver/responses.py`
- `tests/unit/pipeline/translation_driver/test_responses_stop_reason.py`

## 1. 修前实测基线

行号复核：`to_openai_responses_response` 的那行原本在 `responses.py:212`，与派活提示一致。修前实测（`SemanticResponse(stop_reason=...)` 直接喂 `to_openai_responses_response`）：

| stop_reason | status | `incomplete_details` 键 |
|---|---|---|
| `end_turn` | `completed` | 不存在 |
| `tool_use` | `completed` | 不存在 |
| `max_tokens` | `incomplete` | 不存在 |
| `refusal` | `completed` | 不存在 |
| `pause_turn` | `completed` | 不存在 |
| `stop_sequence` | `completed` | 不存在 |
| `model_context_window_exceeded` | `completed` | 不存在 |
| `incomplete` | `completed` | 不存在 |
| `content_filter` | `completed` | 不存在 |
| `""` | `completed` | 不存在 |

与台账 `.dev/docs/upstream/retry-and-continuation/deferred.md`「已查清未修」栏第 16 条记录的点时观测一致。

## 2. 判据来源（先说清楚，因为它决定了整张表）

**关键发现：这张表已经存在，而且已经落地、评审过了——只是在另一条腿上。**

`75273e1`（2026-08-22，*fix: stop the Responses framer answering with words the protocol does not have*）给**流式**的 Responses 成帧器 `src/app/pipeline/delivery/formats/openai_responses.py` 建了两张表：

- `_FINISHED = frozenset({"end_turn", "tool_use", ""})` → `status: "completed"`
- `_INCOMPLETE_REASONS = {"max_tokens": "max_output_tokens"}`，其余 → `status: "incomplete"` + `incomplete_details: null`

这不是「相似的东西」，而是**同一个函数的流式那一半**：两者都是「语义记录 → Responses 客户端」这一个方向的写出端，一个走 SSE，一个走缓冲。而 `fef7d96` 的全部论点正是「一个产品的两条交付路径不得对同一事实给出不同答案」。所以本次修法不是我自选映射，而是把已落地的那张表按同一形状搬到缓冲这一半。台账原话「修法与 `fef7d96` 同构，无岔路」在这个意义上成立。

三份独立佐证：

1. **Responses 侧枚举**（协议契约，非实现反推）：openai SDK 3.3.1 `openai.types.responses.response.IncompleteDetails.reason: Optional[Literal["max_output_tokens", "content_filter"]]`。同文件 `Response.status` 的取值是 `completed | failed | in_progress | cancelled | queued | incomplete`。所以「无合法拼法即 null」不是发明，是枚举本身的约束。
2. **Anthropic 侧取值域**：`src/app/models/anthropic.py:77` 的 `stop_reason: str | None` 不带枚举，本仓不约束它。取值域来自 `.dev/docs/upstream/retry-and-continuation/reports/260821-upstream-termination-reasons.md` §2.3 对 Claude Code 自身消费端的逐字面量统计：`refusal`(23)、`pause_turn`(6)、`end_turn`(6)、`max_tokens`(4)、`tool_use`(2)、`model_context_window_exceeded`(2)、`stop_sequence`(1)，共七个；加上本仓自己合成的 `incomplete`（`from_openai_responses_response` 在上游说 incomplete 而不给理由时写入）。同报告 §2.3 还记了 `model_context_window_exceeded` 本来就不是标准 Anthropic 枚举值，CC 却专门写了分支——即「stop_reason 可能出现枚举外的值」是消费端的设计前提，所以这张表必须对未列名的值有确定行为，而不是假定穷举。
3. **`refusal` 与 `content_filter` 是邻居而非同义词**：`src/app/config/schema.py:167` 的注释是本仓自己的裁决记录——`content_filter` 被**故意**排除在 `hand_over_stop_reasons` 之外，理由是「`refusal` 被裁定不可续写，被过滤的一轮是它的邻居」。两者被本仓当作两件事，不是一件事的两种拼法。

**技能 `my-skills:anthropic-messages-format`** 的 wire 参考只覆盖 `end_turn` / `tool_use` 两个值（`references/messages-wire.md` 的流式清单），对本题其余取值没有判据，故未据它扩表。

## 3. 映射表（修后）

| Anthropic `stop_reason` | Responses `status` | `incomplete_details` | 依据 |
|---|---|---|---|
| `end_turn` | `completed` | `null` | 姊妹表 `_FINISHED`（`75273e1`）；模型自己收的尾 |
| `tool_use` | `completed` | `null` | 同上。以调用工具结束是模型选择的结束，不是被截断 |
| `""`（未设置） | `completed` | `null` | 同上。`SemanticResponse.stop_reason` 是裸 `str`；「没人说」不能读成「上游截断了」（记忆条目「日志行上的缺席读不出来」的同型） |
| `max_tokens` | `incomplete` | `{"reason": "max_output_tokens"}` | 唯一在 Responses 枚举里有合法拼法的截断；`_INCOMPLETE_REASONS`；`incomplete` 这一半修前就对，缺的是「为什么」 |
| `refusal` | `incomplete` | `null` | 本条即缺陷本体：修前报 `completed`。`refusal` 无 Responses 拼法（见 §4 否决），故 reason 为 null |
| `pause_turn` | `incomplete` | `null` | 同上，无合法拼法 |
| `stop_sequence` | `incomplete` | `null` | 同上，无合法拼法。见 §5 的保留意见 |
| `model_context_window_exceeded` | `incomplete` | `null` | 同上，无合法拼法 |
| `incomplete`（本仓合成） | `incomplete` | `null` | 上游说截断但没说原因，`null` 正是 Responses 自己表达这件事的形状 |
| 其余任何值 | `incomplete` | `null` | 正向表的兜底。CC 的消费方式是一串独立相等比较、无 `default` 抛错（同报告 §2.3 第 3 条），所以枚举外的值必须有确定行为 |

`incomplete_details` 这个**键现在恒定存在**，无合法 reason 时为 `null`。理由：修前是键根本不出现，于是「上游没给原因」与「本代理漏写了这个字段」在客户端看来同形；上游自己的响应体在一切正常时也是带着 `"incomplete_details":null` 的（`tests/int/cassettes/anthropic_to_responses_stream.json` 里的 `response.created` 帧可见）。

表的位置：`responses.py` 顶部的 `_FINISHED_STOP_REASONS` 与 `_INCOMPLETE_REASONS`。**是复制而不是 import**，因为 `docs/.human-controlled/module-org.md` 的层次是 `delivery` 在 `translation_driver` 之上——实测 `delivery/formats/openai_responses.py:34` import 了 `translation_driver.reasoning_carrier`，反向零 import。从下层去 import 上层的私有名会把层次倒过来。复制这件事在两处注释里都写明了「必须与姊妹表保持同值」并互相指名。见 §6 的移交项。

## 4. 我否决了什么

- **`refusal` → `incomplete_details.reason: "content_filter"`。** 这是最诱人的一条：Responses 枚举里只有两个值，`max_output_tokens` 已占其一，`content_filter` 空着，而 `refusal` 语义上确实靠近内容过滤。否决理由有二：(a) 本仓已有相反裁决的记录——`config/schema.py:167` 把 `content_filter` 故意排除在 `hand_over_stop_reasons` 之外，措辞是「`refusal` 被裁定不可续写，被过滤的一轮是**它的邻居**」，即本仓把两者当作两件事；(b) 姊妹表 `75273e1` 已经审过同一个选择并且没有映射，我单方面加上去，就会制造出 `fef7d96` 明令消灭的那种「同一事实两条路两个答案」。
- **`stop_sequence` → `completed`。** 语义上「撞到调用方指定的停止串」确实是一次受控的正常结束，报 `completed` 有话可说。否决理由同上（(b)）：姊妹表把它归进「非 finished」，改成 `completed` 就是单方面制造分歧。我的保留意见记在 §5，不进代码。
- **`content_filter` → `content_filter`（恒等映射）。** 这条不是空想：`from_openai_responses_response` 会原样写出上游的词，其中就包括 `content_filter`（`test_any_other_reason_reaches_the_client_in_upstream_s_own_words` 钉的正是这条）。若这样一条 `SemanticResponse` 走到本写出端，一个两边协议都有的词会被抹成 null。否决理由：(a) 该路径是 Responses→Responses，registry 上同格式一般不过翻译（`.dev/docs/client-leg-formats/deferred.md` 记的 D-5「一次性交付的前提写成断言：路由被翻译过就 raise」），可达性未证；(b) 姊妹表有**完全相同**的缺口，加在我这一半就是制造分歧。转为 §6 的移交项，两半应当一起加或一起不加。
- **`model_context_window_exceeded` 走一条特殊路径。** `reports/260821-upstream-termination-reasons.md` §2.2 已证它在 Responses 腿上根本不是 stop_reason 而是 HTTP 400，归错误映射管。所以在本写出端它只是又一个没有合法拼法的截断，不需要特殊待遇。
- **给未知值加日志或 `Conversion.record` 丢失登记。** 想过，没做：`fef7d96` 的提交信息明确写了「nothing is lost now that the reason reaches the client」，把丢失登记删掉了；这里的 reason 变 null 确实**是**一次信息丢失（词被抹掉了），但它与姊妹表的行为一致，而加登记会让两半再次分叉。属 §6 移交项的一部分。
- **改 `_responses_stop_reason`（读入方向）。** 未动。本次只修写出方向；读入方向是 `fef7d96` 已经修过的那一半。

## 5. 我拿不准的

- **`stop_sequence` 报 `incomplete` 是否真的对。** 撞到 `stop_sequences` 是调用方自己要求的结束，说它「不完整」有点重；但 Responses 的 `status` 枚举里没有第三个位置可放，`completed` 会把「被截了」这件事整个抹掉。姊妹表选了 `incomplete`，我照做。**这是一个产品措辞取舍，不是缺陷**，若用户认为该报 `completed`，两半要一起改。我没有找到用户对这一条的直接裁决。
- **`""` 该不该在 finished 集合里。** 在本仓当前接线下它**不可达**：`from_anthropic_response` 用 `str(payload.get("stop_reason") or END_TURN)` 把空值强制成 `end_turn`，`from_openai_responses_response` 也从不返回空串；只有直接构造 `SemanticResponse` 并显式赋空串才能走到。保留它纯粹是为了与姊妹表逐字一致（姊妹表那边 `Terminal.stop_reason` 的默认值就是空串，是可达的）。若评审认为不可达的分支不该写，删掉它会让两半分叉一个字符。
- **`incomplete_details` 恒存在、值为 `null`（而不是 `{"reason": null}`）。** 姊妹表的 `_response_object` 就是这么写的（reason 为 None 时整个字段置 null），我照做。SDK 类型上两者都合法（`IncompleteDetails.reason` 本身是 Optional）。没有录制能仲裁「上游在一次真实的、无原因的 incomplete 上到底发哪一种」——仓里 20 条非空 `incomplete_details` 的 reason **全部**是 `max_output_tokens`（`reports/260821-upstream-termination-reasons.md` §2.4），无原因的那一形态**零观测**。

## 6. 需要主会话处置的（HANDOFF）

1. **两张表现在有两份拷贝**，分别在 `translation_driver/responses.py`（我这份）与 `delivery/formats/openai_responses.py`（姊妹表，正被并行 agent 改）。正确的收口方向是让**姊妹表反过来 import 我这份**（`delivery` → `translation_driver` 是合法方向），从而只留一份。我没有做，因为那要改范围外且正在被别人编辑的文件。
2. **`content_filter` 的恒等映射缺口是两半共有的**（详见 §4 第三条）。若要补，应当两半同一次改完。
3. **台账 `.dev/docs/upstream/retry-and-continuation/deferred.md`「已查清未修」栏第 16 条应移出**（我未改 `.dev/`，按派活约束）。移出时注意：该条正文里的那张点时观测表已被本次修复作废，别原样留下。

## 7. 变异验证

快照法，全程未用 `git checkout`：`cp` 到 `/tmp/mut-0e3de57b/responses.py.good`，变异后逐次从快照还原，最后以 `sha256sum` + `diff` 核对还原到位（两者一致，`IDENTICAL`）。

**变异 A：把修复整段撤回修前那一行**（`"status": "incomplete" if response.stop_reason == MAX_TOKENS else "completed"`，且不写 `incomplete_details` 键）。

- 结果：**11 红 / 10 绿**。8 条表行全部红（`incomplete_details` KeyError），加 `test_a_refusal_is_not_reported_as_a_finished_turn`（`assert 'completed' == 'incomplete'`）、`test_the_token_limit_now_says_why_it_stopped`、`test_the_field_is_always_present_even_on_a_finished_turn`。
- 这一轮**分辨力不够**：缺键的 KeyError 盖住了 status 规则那一半，读不出哪条测试在钉哪个事实。所以又做了两次拆分变异。

**变异 B：只把 status 规则退回旧写法，`incomplete_details` 照常发。**

- 结果：**6 红 / 15 绿**。红的正是 5 条截断行（`refusal` / `pause_turn` / `stop_sequence` / `model_context_window_exceeded` / `incomplete`，断言形如 `('completed', None) == ('incomplete', None)`）加具名的 `test_a_refusal_is_not_reported_as_a_finished_turn`。
- **控制项全绿**：`end_turn` / `tool_use` / `max_tokens` 三条表行、`test_the_field_is_always_present_even_on_a_finished_turn`、`test_a_finished_turn_is_unaffected`。这正是它们该有的表现——它们在旧规则下也成立，所以那 6 条红是关于 `refusal` 这类值的证据，而不是「函数根本没跑」的证据。

**变异 C：status 规则与键都保留，只让 reason 永远填不进去（`"incomplete_details": None`）。**

- 结果：**2 红 / 19 绿**，恰为 `max_tokens` 那一行与 `test_the_token_limit_now_says_why_it_stopped`。status 那一族全绿。

B 与 C 的红集互不相交且各自命中自己那一半，说明测试确实分别钉住了「哪个 stop_reason 翻成什么 status」与「max_tokens 要说出理由」两件事，而不是靠一个大 assert 蒙对。

## 8. 验证

- `uv run pytest tests/unit/pipeline/translation_driver/test_responses_stop_reason.py -q --no-cov` → **21 passed**（原 10 条 + 新增 11 条）。
- `uv run pytest tests/unit/pipeline/translation_driver -q --no-cov` → **134 passed**。
- `uv run ruff check src tests` → **All checks passed**（`ruff format` 未运行）。
- `uv run pyright src tests` → **0 errors, 0 warnings, 0 informations**。
- 未跑全量。

**一条与我无关但需要主会话知道的红灯**：跑扩大到 `tests/unit/pipeline` 时，`tests/unit/pipeline/delivery/test_stream_delivery.py` 有 4 条 `DID NOT RAISE ClientDeadlineError` 失败。已证与本次改动无因果：把我这个文件临时换成 `git show HEAD:` 的版本后，同样 4 条依旧红（且多出 `test_the_client_deadline_is_the_one_ending_that_says_so`，说明那批测试自身正在被改、结果不稳定），随后从快照还原并 `diff` 确认无残留。该文件在 `git status` 里是 ` M`，属并行 agent 的在途改动。**这条观察有保质期**，复述前请重测。
