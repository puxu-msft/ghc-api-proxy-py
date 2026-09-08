# Task 2：Raw SSE frames 与 authoritative Chat attempt facts 独立评审

- report_id: `task-2-facts-review`
- attempt_id: `task-2-review-a9976b3e`
- status: `in-review`
- reviewed_at_rev: `364e3a490714c3613f7d47f149377fd069433684`
- requirements_brief: `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/task-2-brief.md`
- implementation_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/reports/260906-task-2-facts-implementation.md`，reviewed SHA-256 `9296d5cbaff5b756b9b749756d43af32464f0f62906644ad65dcc7a3478115b3`
- diff_package: `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/review-5995bbe..364e3a4.diff`，reviewed SHA-256 `5828c9039494d3dac62afe9c0bcfaf2d987b06dc95554b73b6a48e41412123cb`
- criteria_snapshots: Task 2 brief SHA-256 `c4bfedaa29370cbbb90d81dfd4da4ef3b837a51e86d32b71dd53558276060183`；direct-passthrough Spec SHA-256 `6f0e7b4d83b8c0dc575c7b1b7bf3df1a7b065103f5e81eab59b6d127ef1a42e2`；TUI Spec SHA-256 `5654b2beed95a70fd74c5262fb10a88b4168983b00efebfff5c5db838ed5e6cc`；implementation plan SHA-256 `7ed5221af6938d861690532ee0554d2809ebe572b82a063e05947c12de31a484`

## 评审范围

本轮评审固定比较 `5995bbe0ac1885482e4976975c3b74d196cb7b11..364e3a490714c3613f7d47f149377fd069433684`，范围仅含 Task 2 的八个变更文件：`src/app/pipeline/chat_completions/{__init__,events,state}.py`、`src/app/pipeline/delivery/sse_source.py`、`src/app/pipeline/delivery/formats/openai_chat_completions.py`、`tests/unit/pipeline/chat_completions/{test_events,test_state}.py`、`tests/unit/pipeline/delivery/test_chat_completions_assembler.py`。判据来自 Task 2 brief、`direct-passthrough/spec.md` §5.4／§8／§9.3.1／§10、`tui/spec.md` 的“Chat provider observation schema”，以及调用方列出的 binding constraints。Collector、retry orchestration、provider migration、TUI 接线与 Task 3 以后代码不在被检实现范围；但 Task 2 承诺供这些后续切片使用的接口是否足够，属于本轮范围。

## 总体 verdict

- SPEC COMPLIANCE：❌
- TASK QUALITY：Not approved
- blocker 数：2

## Findings

### task-2-facts-review-01

- severity: `blocker`
- primary_location: `src/app/pipeline/delivery/sse_source.py:97-131`
- related_locations: `src/app/pipeline/delivery/sse_source.py:151-176`；`tests/unit/pipeline/chat_completions/test_events.py:22-41`；`direct-passthrough/spec.md:315-319,345,696`
- failure_scenario: 合法 `CRLF CRLF` frame separator 恰在 transport chunk 的第三个字节之后断开，例如第一块以 `b"data: [DONE]\r\n\r"` 结束、下一块以 `b"\n"` 开始。Decoder 在尚不知道尾部 `\r` 会与下一字节组成 `CRLF` 时，已经把它当作 bare `CR`，把 `b"\r\n\r"` 识别成完整 separator并提前产出 frame；下一块的 `\n` 被划到后续frame。于是 `RawSseFrame.raw`没有保留该frame的完整原separator，half-open offsets与ordinal按错误边界推进。若该frame是首个 `[DONE]` 且cap只剩到错误边界，collector还能把缺最后一个 `LF` 的不完整terminal frame当作成功并把真正的separator尾字节当tail拒掉，直接违反“首个完整 `[DONE]` frame必须在cap内”的合同。
- evidence: 独立穷举probe以完整字节串上的separator扫描为oracle，对长度0～8的 `x/CR/LF` 字节串逐字节切块。首个反例为 `raw=b'\r\r\n'`、chunks=`b'\r'`,`b'\r'`,`b'\n'`：完整输入应产生一个 `raw=b'\r\r\n'` 的terminated frame；实现实际先产生 `raw=b'\r\r'` 的terminated frame，再产生 `raw=b'\n'` 的EOF remainder。失败来自 `feed_bounded()`在chunk末尾立即接受可能属于下一块 `CRLF` 的bare `CR`，现有测试没有把separator切在这个歧义点。
- fix: 流式扫描必须对chunk末尾的歧义 `CR` 延迟判定，直到读到下一字节或EOF；只有下一字节不是 `LF` 时才能把它定为bare `CR`。修复后用完整 `CRLF CRLF` 及全部混合separator在每个字节边界切块的独立literal oracle核对每个frame的`raw/body/start/end/ordinal/terminated`，并特别覆盖 `[DONE]` separator第三字节后的切分与cap边界。

### task-2-facts-review-10

- severity: `blocker`
- primary_location: `src/app/pipeline/chat_completions/state.py:205-217`
- related_locations: `src/app/pipeline/chat_completions/events.py:22-29,87-128`；`src/app/pipeline/chat_completions/state.py:793-796`；`direct-passthrough/spec.md:328,333,336`；`tui/spec.md:174`
- failure_scenario: `FrozenJson`合法包含Python `None`来表示JSON null，但`ChatEventFacts.value`又用`None`表示“没有可读value”。普通`data: null`被reader正确分类为non-object `UNKNOWN`，state却因`facts.value is None`而只记issue、不标`unassemblable`；在前后有合法chunk与`[DONE]`时，mode adaptation静默丢掉该可读content event并返回成功JSON。`event: error`携带`data: null`时同一歧义又把明确的JSON null记录成`stream_error=UNREADABLE`，违反explicit null与unreadable分槽。
- evidence: reviewed commit probe依次observe合法identity/choice、`data: null`、`[DONE]`。Reader事实为`kind=UNKNOWN, value=None, issue=chat_event_non_object`，但最终`state.unassemblable=False`且`to_completion_payload()`成功。第二个probe对`event: error\ndata: null`得到`ChatEventKind.ERROR`，snapshot却为`JsonAvailability.UNREADABLE`而非`EXPLICIT_NULL`。这直接证伪“strict JSON区分non-object/malformed”在state消费端仍成立。
- fix: 不要用裸`None`同时编码合法JSON null与absence／decode failure；为event value引入明确availability/sentinel，或使facts分别携带`value_present`与FrozenJson。State对所有可读non-object值包括null都标`unassemblable`；error observation把可读null记为`EXPLICIT_NULL`、只有decode失败才记`UNREADABLE`。补`null`、`[]`、malformed三向测试并断言只有malformed是unreadable、两种可读non-object均不能被adaptation丢弃后成功。

### task-2-facts-review-02

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:734-775`
- related_locations: `src/app/pipeline/chat_completions/state.py:183-186,612-630`；`tests/unit/pipeline/chat_completions/test_state.py:324-339`；`direct-passthrough/spec.md:694-696`；Task 2 brief lines 124-128
- failure_scenario: 任一层unknown object使用超长field name与很小的value，例如top-level `{<100000-byte key>: "x"}`。State把完整key保留在`dict`中并会把它写入最终projection／observation，但`_held_bytes()`只累计unknown value的`repr`大小，不累计key。Task 3即使严格按`additional_held_bytes()`先预量，也会把这次增长读成3 bytes；100000 bytes的retained key完全绕过cap。相同漏计存在于top-level、choice、delta/message、legacy function、logprobs、tool与tool.function各层unknown map。
- evidence: 在reviewed commit上构造100000-byte unknown key、value为`"x"`的单frame probe。`raw_frame_bytes=100016`、`unknown_key_utf8_bytes=100000`，而`additional_held_bytes(facts)=3`且mutation后`held_bytes=3`。这证明不是估算误差，而是攻击面大小的retained string被接口完整漏掉。
- fix: 对每个retained unknown mapping按完整frozen entry计量，至少包含UTF-8 key bytes与value的既定`repr(frozen_json)`大小，并让所有层共享同一helper；增加top-level与嵌套tool/function unknown的大key正反例，断言prospective delta包含key且replacement／same-value重复只反映实际新增或释放量。

### task-2-facts-review-03

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:183-186`
- related_locations: `src/app/pipeline/chat_completions/state.py:285-305,786-790,830-839`；Task 2 brief lines 124-128；Task 3 brief lines 26-67,85-99
- failure_scenario: Task 3必须在allocation前通过`BufferedMemoryAccount.replace(...)`预留state／projection／observation容量，但三个Task 2接口都先制造待计量对象再返回数字。`additional_held_bytes()`先`deepcopy`整份state并在副本上apply；`projection_size_bytes()`先构造完整payload、连接全部字符串并调用`orjson.dumps()`生成最终bytes；`observation_size_bytes()`先构造完整snapshot再生成整份`repr(...).encode()`。当raw＋现有state已接近cap而新projection或observation很大时，调用方尚未来得及预留就已经让这些副本与state共存，违反`projection/observation materialization calls memory.replace before allocation`；大nested unknown还会在`deepcopy`和`repr(...).encode()`路径产生未计量容器／字符串副本。
- evidence: 这是接口调用顺序的直接源码事实：size方法的返回值依赖已完成的`to_completion_payload()`／`observation_facts()`与serialization，prospective delta依赖已完成的`_copy_for_preview()`。Task 3 brief明确要求先`memory.replace(...)`、后allocation；现接口不存在不allocation即可取得所需数字的调用路径。若“allocation前预留”前提为假，Task 3的`peak<=cap`结论即失效，因此该事实直接支撑Not approved。
- fix: 提供不构建candidate的纯prospective sizing路径，或提供能由caller先得到size、成功预留后才materialize的两阶段builder；`additional_held_bytes()`应从当前field ledger与incoming facts计算delta而不是clone whole state。结构化值大小也应使用不生成完整`repr`临时副本的递归计数。测试应在materializer／copy入口安装sentinel，证明预量先返回且未调用materialization，再由显式预留后的第二步生成对象。

### task-2-facts-review-04

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:786-790`
- related_locations: `src/app/pipeline/chat_completions/state.py:363-367,399-402,623-630`；`src/app/pipeline/chat_completions/state.py:285-286`；`src/app/pipeline/response_observation.py:47-57`；`direct-passthrough/spec.md:790-801`
- failure_scenario: Strict stdlib JSON合法保留任意精度integer，但field merge用`orjson.dumps()`判断semantic equality。一个unknown field、repeated identity或usage snapshot只要含超出64-bit的integer，第二次出现相同JSON value时就抛`TypeError`，既没有按same-value retention成功，也没有按conflict得到`unassemblable`，而是把合法upstream JSON变成本地state bug。即使只出现一次，最终`projection_size_bytes()`也会因同一个orjson限制失败，导致Task 3不能为本可由项目FrozenJson域表示的projection计量。
- evidence: reviewed commit上的最小probe连续observe两次`{"future": 10**100}`。第一次保留成功，第二次在`additional_held_bytes()`→`_merge_unknown()`→`_same_frozen_json()`抛出`TypeError: Integer exceeds 64-bit range`。项目现有`freeze_json()`逐字说明JSON integer不受JavaScript 53-bit限制、该domain必须精确保留，并特意使用stdlib decoder避免orjson在边界处改变值，因此这里不是可接受的输入收窄。
- fix: FrozenJson equality应直接递归比较JSON value，object按key语义比较而不依赖key order，array保序，且不得通过受64-bit限制的serializer；projection sizing／serialization也必须使用与最终client writer相同且支持本项目FrozenJson数值域的codec，或在规范层先明确收窄并让reader产生具名`unassemblable`，不能抛local `TypeError`。

### task-2-facts-review-05

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:285-286`
- related_locations: `src/app/server/routes/inference.py`的既有`JSONResponse`出口；`.dev/docs/direct-buffered-chat-completions/plan.md:123,703,715`；Task 2 brief lines 124-128
- failure_scenario: `projection_size_bytes()`用`orjson.dumps()`计量，但既有且计划继续使用的client出口由Starlette `JSONResponse.render()`调用stdlib `json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",", ":"))`。两种serializer并非byte-length等价；当projection含合法unknown float `1e-7`时，orjson写`1e-7`，JSONResponse写`1e-07`。Task 3按前者预留后，Task 5实际materialize的body可以更大并突破cap，接口因而没有提供承诺的exact serialized size。
- evidence: reviewed commit最小probe建立合法identity、一个已完成choice、1000个值为`1e-7`的unknown top-level fields并观察`[DONE]`。`state.projection_size_bytes()`返回12059，`len(JSONResponse(state.to_completion_payload()).body)`为13059，低估1000 bytes。若“两个serializer等长”前提为假，按该size预留即可越界；probe已证明此前提为假。
- fix: 让size oracle与最终writer共享唯一serializer／最终bytes。优先让projection builder在已预留后一次生成将直接交付的bytes并转移ownership，避免先算orjson、后由JSONResponse再编码；若仍返回mapping，size必须调用与最终`JSONResponse.render()`逐字相同的纯计数逻辑，并用float exponent、Unicode、escaping与大integer正反例锁定byte equality。

### task-2-facts-review-06

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:547-577`
- related_locations: `src/app/pipeline/chat_completions/state.py:689-699`；`tests/unit/pipeline/chat_completions/test_state.py:236-284`；`direct-passthrough/spec.md:798`；Task 2 brief lines 124-128
- failure_scenario: 标准known-field正例中，chunk携带`choice.logprobs={"content": null, "refusal": null}`。实现只对整个`logprobs`为null设置`null_seen`，对子字段null直接`continue`，final projection因此写`"logprobs": {}`，把两个显式null都改成缺席。该结果不按OpenAI字段结构保留已观察值，也破坏JSON field merge的absent／explicit-null区分。
- evidence: 对同一合法chunk运行installed OpenAI `ChatCompletionStreamState`正例辅助，`get_final_completion().model_dump(exclude_unset=True)`保留`logprobs: {content: null, refusal: null}`；reviewed state在相同输入加`[DONE]`后输出`logprobs: {}`。这只作为标准known-field正例的differential oracle，结论仍由§9.3.1的字段表与TUI对absent／null分槽原则支撑。
- fix: 为`logprobs.content`与`logprobs.refusal`分别记录absent／explicit-null／array状态；无array而见null时投影null，见一个或多个array时按Spec连接并输出数组，wrong type仍`unassemblable`。增加only-null、null后empty array及array后null三个表驱动用例；SDK只用于标准正例，不用于unknown／conflict规则。

### task-2-facts-review-07

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:191-204`
- related_locations: `src/app/pipeline/chat_completions/events.py:22-29,130-188`；`src/app/pipeline/chat_completions/state.py:45-53,231-245`；`.dev/docs/direct-buffered-chat-completions/plan.md:95-123`；Task 3 brief lines 83-91
- failure_scenario: Reader正确产出的`ChatEventFacts.retry_reason`、`error_values`与error frame `end`在`ChatAttemptState.observe()`中被丢弃；state只保存完整error JSON为`stream_error`。Task 3的generic collector返回`body + state + ending`而不返回最后一份facts，且规范要求`ChatAttemptState`产生typed decision、orchestration不得重解析raw error。于是collector结束后，decision无法从state区分known server error、known rate-limit error、unknown／conflicting error，也无法在后续frame同chunk到达时选择“截至error frame结束offset”的raw carrier；若重读`stream_error`或raw body则违反single parse／single owner合同。
- evidence: `ChatEventFacts`在events.py中明确持有`error_values`与`retry_reason`，但state的ERROR分支仅执行`self._stream_error = ...`与`self._semantic_frozen = True`；`ChatAttemptSnapshot`及state公开属性均没有分类或terminal frame offset。Task 3 brief逐字要求“known event errors use state’s explicit reason”，plan又要求orchestration读取一个typed outcome且never re-parses raw error fields，现有state没有可供读取的explicit reason。
- fix: 在state内单次保存首个semantic terminal的typed error classification、原始spellings与frame half-open end offset，并由后续`ChatAttemptDecision`直接读取；该state字段与snapshot／held-size规则保持一致。测试应在error后附同chunk普通frame，断言known server、rate-limit、unknown与conflict得到不同typed outcome，`body_end`恰为error frame.end，且CountingReader调用数不增加。

### task-2-facts-review-08

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:328-344`
- related_locations: `src/app/pipeline/chat_completions/state.py:497-545,701-724`；`direct-passthrough/spec.md:793,797,804,829`；`tui/spec.md:173,180-186`
- failure_scenario: 一个可读JSON chunk含invalid choice index或invalid tool index时，direct raw streaming必须继续保留wire，同时durable observation要以issue和相应raw unknown槽保存可读事实；mode adaptation还要让`unassemblable` carrier保存原始frame／field path。实现对invalid index只追加一个不含frame ordinal、raw value或detail的issue，然后`continue`并丢掉整个choice/tool object。最终`ChatAttemptSnapshot`没有该对象，Task 7若不违反“不得重解析raw／synthetic body”就无法恢复unknown字段、content、tool name等事实，Task 5也拿不到§9.3.1要求的原始frame。
- evidence: reviewed commit probe在ordinal 23输入choice `{"index":"bad","delta":{"content":"lost","future_delta":{"large":"value"}},"future_choice":7}`。Snapshot结果为`choices=()`、`top_level_unknown={}`，唯一记录是`ObservationIssue(code='chat_choice_index_invalid', field_path='choices[0].index', detail=None)`；ordinal 23及整个可读对象均已丢失。Tool index分支同样在记录issue后直接`continue`。
- fix: 为无法归入合法index的choice／tool保存immutable raw FrozenJson及frame ordinal／offset provenance，作为snapshot中与合法有序集合分槽的unattributed/invalid facts；`ChatCompletionUnassemblable`应携带对应frame或稳定frame引用与完整field path。该副本必须进入`held_bytes`、prospective delta与observation size，Task 7直接投影而不重解析。

### task-2-facts-review-09

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:701-710`
- related_locations: `src/app/pipeline/chat_completions/state.py:421,460-465,612-630,637-670`；`direct-passthrough/spec.md:801`；`tui/spec.md:180`
- failure_scenario: Unknown choice-level field名恰为`message`，同时delta层也有unknown field时，state分别正确保留两层值，但`_choice_snapshot()`先复制choice unknown，再无条件用合成的delta-unknown object覆盖`unknown["message"]`。Direct streaming的最终observation因此静默丢失原始choice-level `message`值；mode adaptation虽然稍后由`_choice_payload()`抛`unassemblable`，snapshot仍已丢事实且没有collision issue，违反unknown按原JSON层级冻结与冲突可观察合同。
- evidence: reviewed commit probe输入choice-level `message={"from_choice":1}`与delta-level `future_delta=2`。`observation_facts().choices[0].unknown`仅为`{"message":{"future_delta":2}}`，原`from_choice`完全消失；`to_completion_payload()`另行抛`ChatCompletionUnassemblable(field_path="choices[0].message")`，说明delivery与observation对同一冲突得出不一致的保留结果。
- fix: Snapshot中为choice-level unknown与message/delta-level unknown设置不可碰撞的独立槽，或使用始终显式的层级wrapper；在observe阶段记录output-reserved-name collision issue，而不是等projection时才临时抛错。补一个choice unknown名为`message`并同时含delta unknown的raw-stream observation测试，断言两层值与issue均保留且size计入两者。

### task-2-facts-review-11

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/state.py:386-402`
- related_locations: `src/app/pipeline/chat_completions/state.py:45-53,842-912`；`tui/spec.md:184,190`
- failure_scenario: 一个attempt完全没有`usage`与一个attempt显式发送`"usage": null`会得到逐字段相等的`ChatAttemptSnapshot.usage is None`且没有issue。TUI Spec要求“未报 usage”与“显式 null”在durable record可区分，并要求Chat沿用`UsageObservation`的normalized／raw／exact三槽；当前state在看到null时直接return，永久抹掉这个事实。另一个同类边界是usage object内token字段类型错误：`_integer_or_none()`静默降成None但不生成conversion issue，导致consumer若不重读raw就无法区分缺席与malformed。
- evidence: `_observe_usage()`仅对non-null mapping构造`UsageObservation`；null分支不设置任何seen／raw状态。`_usage_observation()`对`prompt_tokens`等错误类型只返回None，唯一issue来源是算术不一致。该结构与`ResponsesObserver._observe_usage()`对null建立`JsonAvailability.EXPLICIT_NULL`、对conversion error写issue的既有三槽实现不一致。
- fix: 即使usage为null也构造`UsageObservation(raw=EXPLICIT_NULL, exact=None, normalized=empty)`，但不覆盖先前last explicit object的projection authority；为存在但类型错误的标准token/detail字段写稳定conversion issue并保留raw。补absent／explicit-null／empty-object／zero／wrong-type／inconsistent六向测试，且让observation size覆盖这些新增facts。

### task-2-facts-review-12

- severity: `major`
- primary_location: `src/app/pipeline/chat_completions/events.py:87-117`
- related_locations: `src/app/pipeline/response_observation.py:47-57`；`direct-passthrough/spec.md:326-336`
- failure_scenario: Python stdlib接受合法但超出binary64范围的JSON number，例如`1e400`，得到`inf`；reader随后在识别top-level error carrier之前冻结整个object，`freeze_json()`抛`FrozenJsonError`。因此`{"error":{"code":"server_error"},"future":1e400}`没有先认出明确error与known transient code，也没有返回typed local/unreadable facts，而是让未声明异常穿出reader。一个与taxonomy无关的future字段就能把应走`SERVER_ERROR`的carrier改成local bug。
- evidence: reviewed commit probe读取`data: {"error":{"code":"server_error"},"future":1e400}`，在`events.py:112`直接抛`FrozenJsonError: non-finite float at frame[0].data.future is not valid JSON`；`_error_facts()`从未执行。`1e400`不是JSON的`NaN`／`Infinity`扩展常量，而是语法合法的number，`parse_constant`不会拦截它。
- fix: Carrier识别与code/type分类不能依赖整份value已经成功冻结；先从stdlib解析结果识别carrier与taxonomy，再以显式availability记录无法进入FrozenJson域的完整value。或者用能保留任意JSON number的解析表示并扩展freeze边界。无论选择哪条，known error加不相关large-number字段的测试必须仍返回`ERROR`且分类不退化；ordinary chunk则得到具名unreadable／unassemblable事实而不是未捕获异常。

### task-2-facts-review-14

- severity: `major`
- primary_location: `src/app/pipeline/delivery/sse_source.py:115-125`
- related_locations: `src/app/pipeline/delivery/sse_source.py:64-70,81-83`；Task 2 brief lines 44-62；Task 3 brief lines 26-67,83-99
- failure_scenario: 每个terminated frame同时持有`raw=bytes(self._buffer)`与`body=raw[:body_end]`；因为slice去掉separator，`body`是第二份接近frame全长的bytes。`feed_bounded()`只按`required`扣一次capacity，`RawSseFrameDecoder.held_bytes`在clear后又报告0，`RawFrameFeed`没有暴露这份body副本的计量。一个大小接近cap的合法单frame因此会在返回feed时同时保留约两倍cap的payload bytes，Task 3在feed返回之后才有机会更新memory account。
- evidence: Python对非完整bytes slice分配独立bytes object；这里terminated frame的`body_end < len(raw)`恒成立。现有测试自己的首frame为`len(raw)=21`、`len(body)=17`，但bounded断言只用`remaining_capacity=len(raw)`并没有为17-byte body副本预留。该问题与finding 03的projection预量不同：即使state与projection全为空，raw decoder本身也已先分配未计量副本。
- fix: Raw frame应只拥有一份bytes并以body end offset／memoryview表达解析范围，或把body副本作为staging显式纳入feed前可判定的capacity并避免在reservation前构造；`RawFrameFeed`需要让caller能转移这份ownership而非再复制。增加near-cap单frame测试，按实现真实同时持有项断言peak不超过cap，而不是只断言`len(frame.raw)`。

### task-2-facts-review-13

- severity: `minor`
- primary_location: `tests/unit/pipeline/chat_completions/test_state.py:93-284`
- related_locations: `/home/xp/.claude/jobs/3db40195/tmp/task2_production_probe.py:40-97`；Task 2 brief lines 128-129；implementation report lines 51-58
- failure_scenario: Task 2要求以OpenAI `ChatCompletionStreamState`作为标准known-field正例的异源辅助oracle，但production probe与focused tests只对照手写expected object，diff、报告与三个保存的probe脚本中均没有SDK accumulator调用。于是实现与手写expected可以一起误读同一字段规则；本轮`logprobs` explicit-null丢失正是一个SDK正例会直接照出的偏差。
- evidence: 在完整diff、implementation report、`task2_production_probe.py`、`task2_baseline_probe.py`与`task2_mutation_controls.py`中检索`ChatCompletionStreamState`无命中。独立review probe对标准logprobs-null chunk调用installed SDK，SDK final snapshot保留`{"content": null, "refusal": null}`，而项目state输出`{}`。
- fix: 增加至少一个只覆盖typed标准known fields的SDK differential正例，将SDK helper fields `parsed`／`parsed_arguments`与stream-only tool `index`在比较边界显式剥离；unknown、conflict、identity-first与项目特有失败规则继续只以Spec-ownedliteral oracle断言，不让SDK成为生产依赖或行为authority。


## 已满足要求与未发现问题的检查面

- 变更范围严格为Task 2列出的八个实际变更文件，没有实现collector、retry owner、provider migration或TUI接线。
- 对不存在歧义chunk边界的输入，raw decoder保留separator、half-open offsets、ordinal与EOF `terminated=false`；`read_events()`仍通过三组既有literal oracle。Finding 01只否定任意chunk切分下的全称，不否定这些已覆盖样本。
- 常见error carrier路径满足event-name error、top-level error、flat `type:error`的优先级；known code/type同类时给出retry reason，unknown与跨类冲突不retry。Finding 10与12限定了仍失败的JSON边界。
- 常见standard projection覆盖first identity、封闭last-explicit集合、multi-choice与tool index排序、文本／reasoning／arguments拼接、finish consistency、last object usage及多层unknown same-value/conflict；不合成id／created／model，不生成SDK helper fields或stream-only tool index。Finding 06指出一处known-field null merge偏差。
- 第一个正常`[DONE]`后semantic state不再变化；post-terminal raw tail职责没有越界塞进state。
- Existing translated `ChatCompletionsAssembler`只复用reader facts并保持原single-projection结构；未发现偷偷修复deferred multi-choice或改用direct state。
- 对`events → sse_source/response_observation/retry`、`state → events/sse_source/response_observation`、translated assembler → events的import关系逐项检查，当前图无runtime cycle；相关既有suite据implementation report已成功import并执行。

## 检索面与验证证据

完整读取了Task 2 brief、2101行diff package、implementation report、reviewed commit中的五个production source与三份变更test，以及`direct-passthrough/spec.md` §5.4／§8／§9.3.1／§10、`tui/spec.md` Chat schema、Task 3 consumer brief和plan中的cross-lifecycle／Task 5／Task 7接口。按调用方要求没有重跑implementer已运行的96-test、Ruff或Pyright命令；这些结果只按implementation report记为作者自报证据，不用来覆盖本轮反例。

本轮仅运行未被既有测试覆盖的最小只读probe：separator逐字节切分穷举在`b'\r\r\n'`给出首个反例；100000-byte unknown key证明state只报3 bytes；`10**100`重复unknown证明orjson equality抛64-bit异常；1000个`1e-7`证明projection size比实际`JSONResponse`少1000 bytes；SDK standard positive与项目state对照证明logprobs null丢失；invalid index、choice/message unknown collision及JSON null分别证明snapshot或adaptation事实丢失；`1e400` error carrier证明freeze发生在carrier识别之前。Probe只证明本地decoder／state／serializer行为，不冒充真实provider样本。

未运行真实provider、未检验Task 3以后尚未实现的collector／retry／provider／TUI production wiring，也没有修改任何源码、tests或living docs。最终结论只覆盖reviewed revision；后续candidate字节改变后需针对相关finding复评。

## 审查后否决建议

1. 否决“把OpenAI SDK accumulator直接接入production来快速修正聚合”的路线。SDK只应作为标准known-field正例辅助；unknown、conflict、identity与cap合同仍由本项目Spec和state拥有。
2. 否决“在本切片顺手修translated assembler的multi-choice”的路线。其既有single-projection行为是明确范围边界，本轮只应保留reader事实复用。
3. 否决“让Task 3／Task 7重新解析raw SSE或synthetic completion来补齐丢失facts”的路线。这会破坏single-read authority；Task 2 state接口本身必须保存error分类、invalid-index provenance与unknown层级。
4. 否决“先接collector，再靠Task 3的cap tests兜底”的路线。Findings 01、02、03、05、14均处在collector要建立其正确性的下层接口，带病接线只会让`peak<=cap`成为假绿。
5. 否决超出Task 2去实现retry orchestration、provider行为、TUI renderer或真实upstream探测；这些均有后续切片和独立证据边界。

## 我最没把握的三个判断

1. `task-2-facts-review-08`：结论对当前TUI Spec是高置信；但Task 7 plan列出的DTO字段没有显式invalid raw槽，与Spec“issue＋相应raw unknown槽”存在接口张力。若owner认定plan有意收窄，不能直接驳回finding，而应先让living Spec与plan在Task 3／7开工前对齐；否则后续实现无处安放该事实。
2. `task-2-facts-review-12`：`1e400`按JSON语法是合法number，故“不得未捕获异常”是高置信；究竟扩展FrozenJson精确保留decimal，还是把超出当前数值域具名标成unreadable／unassemblable，是实现选择而非本报告裁定。即使选择后者，error carrier必须先被识别，不能退化成local exception。
3. `task-2-facts-review-14`：按Spec“当前持有”与brief“所有coexisting copy”的字面，`raw`与`body`两份bytes都应计量，因此major定级有充分依据；若项目只想约束长期逻辑payload而明确豁免parser临时副本，则该finding可降级，但必须先修改cap权威文字，不能在实现里静默采用较窄口径。

## 执行本契约时遇到的摩擦

CodeGraph无法为implementer worktree找到索引，因此本轮在先读完整diff后改用绝对路径`Read`核对最终源码；这不影响覆盖范围。当前agent被worktree隔离，`Write`拒绝直接写shared main path；按项目规定通过本worktree的`.dev` symlink用Bash逐段写入唯一获授权的报告文件。除此之外无阻塞。

## 最终判定

SPEC COMPLIANCE：❌。至少raw frame chunk invariance、JSON null语义、§9.3.1 logprobs merge、error decision facts、unknown/index observation与统一cap计量不符合权威合同。

TASK QUALITY：Not approved。修复全部blocker与major后再复评变更过的承重路径；minor的SDK differential oracle应同时补齐，因为它已能判出一个实际known-field偏差。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-06
- finding_total: 14
- blocker: 2
- major: 11
- minor: 1
- nit: 0


---

## Fix round 1 scoped re-review — 2026-09-06

- attempt_id: `task-2-rereview-a9976b3e-1`
- reviewed_at_rev: `b417bf6508e65eb72195ebb71fbc79550dcf33d3`
- scope: 只复核原14项finding的fix diff `364e3a490714c3613f7d47f149377fd069433684..b417bf6508e65eb72195ebb71fbc79550dcf33d3`，并检查该fix diff是否引入新的Critical／Important breakage；不重开首轮全量评审。
- refreshed_requirements: `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/task-2-brief.md`，SHA-256 `c45a4a8a204e3bf7046636e09193bd2c25c7df313deb162c328314904354f07b`
- updated_implementation_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/reports/260906-task-2-facts-implementation.md`，SHA-256 `0b1bb2ab74dc05b7d9677511e1564fc3cf3534785d1b8f0d7f40a81b6de32b0e`
- fix_diff_package: `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/review-364e3a4..b417bf6.diff`，SHA-256 `7f90b49ffbbddf7cc49bd15126e33e0fd1fdaede67fccc877273c358eb5fd66c`

### 总体 verdict

- SPEC COMPLIANCE：❌
- TASK QUALITY：Not approved
- 原finding：13 ADDRESSED／1 NOT ADDRESSED
- fix diff新增Critical／Important breakage：0

### 原14项finding处置复核

| finding_id | 状态 | 复核依据 |
|---|---|---|
| `task-2-facts-review-01` | **ADDRESSED** | `sse_source.py:159-196`延迟chunk末歧义CR并在下一byte／EOF定案；`test_events.py:44-85`覆盖全部合法separator的every-byte split及`[DONE]` cap边界。 |
| `task-2-facts-review-02` | **ADDRESSED** | `state.py:1359-1374`统一递归累计FrozenJson的key与value；top-level及tool/function 100000-byte keys均有prospective／held断言。 |
| `task-2-facts-review-03` | **NOT ADDRESSED** | Size方法已不再调用完整projection／snapshot，`copy.deepcopy`也已删除；但接口仍不足以兑现“no-allocation sizing＋所有coexisting copies统一计量”。`additional_held_bytes()`在`state.py:240-243,543-566,1143-1216`先构造新的state并复制被触及choice的全部mutable metadata；更关键的是新增`to_completion_bytes()`在`state.py:336-338,1402-1408`先materialize完整payload及joined field strings，再把完整JSON `str`编码成第二份`bytes`，而`projection_size_bytes()`只预留最终bytes一份。独立2,000,000-byte content probe得到`state_held=2000088`、`reserved_projection=2000167`、`to_completion_bytes()`新增peak=4004211；因此Task 3按接口预留后，实际峰值仍可比账面多约一个完整projection。Implementer新增test只patch `copy.deepcopy`／public materializers，抓不到custom clone与materializer内部双份payload。修复需让prospective delta直接计算而不clone retained metadata，并让projection reservation覆盖materializer的真实同时存活量，或改成不会同时形成完整payload string与final bytes的ownership-transfer writer。 |
| `task-2-facts-review-04` | **ADDRESSED** | `state.py:1227-1247`用递归typed value equality取代orjson；object key order无关，bool与number不混，`10**100`重复值有正例与mutation control。 |
| `task-2-facts-review-05` | **ADDRESSED** | `state.py:381-501,1402-1475`按最终stdlib JSON encoder逐字段计数并提供同codec的bytes builder；独立500-case deterministic randomized probe对照Starlette `JSONResponse.body`全部byte length相等。 |
| `task-2-facts-review-06` | **ADDRESSED** | `state.py:104-121,861-892,1003-1014`为`logprobs.content/refusal`分别保存null／array状态；only-null、null→empty-array、array→null测试与SDK正例均覆盖。 |
| `task-2-facts-review-07` | **ADDRESSED** | `state.py:198,206-208,222-231,259-264,305-315`持久化首个semantic terminal end、error spellings与typed retry reason，post-freeze不覆盖。 |
| `task-2-facts-review-08` | **ADDRESSED** | `ChatUnattributedFact`及`state.py:590-618,799-821,1037-1051`保存invalid choice/tool的完整FrozenJson、ordinal、half-open offsets与field path；projection error回带匹配provenance。 |
| `task-2-facts-review-09` | **ADDRESSED** | Snapshot将choice/message与tool/function unknown拆成独立字段；choice-level reserved `message`在observe时具名失败，两层raw facts均保留，未再互相覆盖。 |
| `task-2-facts-review-10` | **ADDRESSED** | `ChatEventFacts.value`改为显式`JsonObservation`；reader把JSON null记为`EXPLICIT_NULL`、array/scalar记为observed、decode/freeze failure记为`UNREADABLE`，state对两种可读non-object均标`unassemblable`。 |
| `task-2-facts-review-11` | **ADDRESSED** | `state.py:669-698,1478-1599`保留usage absent／null／empty object／zero／wrong type／inconsistent六态；null不清空last object projection，错误类型产生frame-qualified conversion issue。 |
| `task-2-facts-review-12` | **ADDRESSED** | `events.py:117-147,169-237`先识别／分类carrier再冻结whole value；known error加`1e400`仍保留ERROR、spelling、retry reason并把whole value标UNREADABLE，ordinary对应输入成为unassemblable。 |
| `task-2-facts-review-13` | **ADDRESSED** | `test_state.py:532-629`加入OpenAI SDK标准known-field differential，覆盖logprobs null与tool call；比较边界剥离SDK helper与stream-only index，production无SDK依赖。 |
| `task-2-facts-review-14` | **ADDRESSED** | `RawSseFrame`改为单一`raw: bytes`＋`body_end`，`body`为引用同一raw object的memoryview；near-cap与identity断言覆盖，不再保留第二份frame-sized body bytes。 |

### Fix diff新增breakage检查

未发现独立于原finding的新Critical／Important breakage。Fix diff仍局限Task 2的七个源／测试文件；translated assembler只适配新的`JsonObservation`封装，single-projection行为未改；两种import顺序的干净进程probe均成功，未形成import cycle。唯一阻断仍是`task-2-facts-review-03`的cap premeasurement接口未完整闭合，不另编号成“新增”finding。

### 本轮证据与边界

按指令未重跑implementer已报告的`121 passed`、Ruff或Pyright；这些仍是implementation report的自报证据。本轮完整读取刷新后的brief、更新报告与3182行fix diff，并核对最终`events.py`、`state.py`、`sse_source.py`及相关tests。新增只读probe只有两类：500组deterministic随机合法projection与Starlette `JSONResponse.body`长度逐项相等；两个干净进程按chat-first及delivery-first顺序import均成功。另运行一个针对未覆盖cap前提的2,000,000-byte content probe，确认size阶段本身不materialize final payload，但`to_completion_bytes()`在仅预留一份projection时新增peak为4004211 bytes；该probe证明本地Python materializer的同时存活量，不外推真实provider或完整Task 3 wiring。

### 审查后否决建议

- 继续否决用OpenAI SDK替换production state；本轮SDK oracle的边界正确。
- 继续否决把translated multi-choice、collector／retry、provider或TUI实现并入本fix；diff没有越界。
- 否决把“移除了`copy.deepcopy`”等同于“cap预量合同已闭合”：custom metadata clone与projection materializer的同时存活量仍需同一memory account可表达。

### 我最没把握的三个判断

1. 对`task-2-facts-review-03`判NOT ADDRESSED的置信为中高：源码调用顺序与tracemalloc都显示未计量的完整projection副本；不确定点只在项目是否想把Python materializer内部临时对象排除出“当前持有”。当前Spec／brief写的是all coexisting copies与allocation前reserve，未提供该豁免，因此本轮不能自行降级。
2. `task-2-facts-review-01`的`finish()`可能返回`terminated=True`，表面上与旧brief“EOF remainder terminated=false”有张力；刷新后的测试与实现报告明确把它限定为EOF才消除歧义的完整separator，而普通remainder仍false。按frame语义判为ADDRESSED；若调用方把旧句读成“finish绝不返回terminated frame”，需先修brief内部矛盾。
3. `task-2-facts-review-11`中object后null的snapshot选择null、projection继续保留object，是刷新brief明确指定的双槽语义；它不同于“最终observation一律最后object”的另一种直觉，但不构成本轮实现缺陷。

### 执行本契约时遇到的摩擦

CodeGraph仍无法索引implementer worktree；本轮用完整diff package与绝对路径源码读取替代。未遇到权限或文件缺失阻塞，未修改源码、tests或living docs。

### Re-review交付声明

- delivery_complete: true
- completed_at: 2026-09-06
- original_findings_total: 14
- addressed: 13
- not_addressed: 1
- new_critical: 0
- new_important: 0
- spec_compliance: fail
- task_quality: not-approved


---

## Fix round 2 scoped re-review — 2026-09-06

- attempt_id: `task-2-rereview-a9976b3e-2`
- reviewed_at_rev: `e42fc7660a656bc53a1ee7ea06e920b555d2a1f5`
- scope: 仅复核`task-2-facts-review-03`及fix diff `b417bf6508e65eb72195ebb71fbc79550dcf33d3..e42fc7660a656bc53a1ee7ea06e920b555d2a1f5`，并检查该diff引入的新Critical／Important breakage。
- updated_implementation_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/reports/260906-task-2-facts-implementation.md`，SHA-256 `10e8b57c880f5ce9c3c6179cfe1b583db5b277a1b6d6376e765ef396eb02b188`
- fix_diff_package: `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/review-b417bf6..e42fc76.diff`，SHA-256 `006cafd2abc5ba50ac3137e906f5ba400f7f95bfa08b32ea9a643004423cf7a3`

### `task-2-facts-review-03`：NOT ADDRESSED

本轮修复关闭了三个子面中的一部分：`additional_held_bytes()`不再clone既有retained metadata，而是把同一incoming facts送入fresh state后与current ledger合并；`projection_reservation()`／`observation_reservation()`均在调用public materializer之前返回；2,000,000-byte flat content／reasoning probes及把`working_copy_bytes`归零的mutation对该单一形状有分辨力。以上均判为已落实，但不足以关闭finding，因为prospective delta仍非精确，projection／observation reservation也仍未覆盖合法输入上的真实同时存活量。

#### Residual A：prospective delta在同event重复index时不等于真实mutation

- severity: `major`（原finding的未关闭部分）
- primary_location: `src/app/pipeline/chat_completions/state.py:251-314`
- related_locations: `src/app/pipeline/chat_completions/state.py:1251-1415`
- failure_scenario: Current choice已有`finish_reason="B"`，下一event按顺序含同一choice index两次，finish reasons依次为`"A"`、`"B"`。真实apply先对A记一次conflict，再让B与仍保留的current B相等；fresh incoming ledger却先保留A、再对B记一次内部conflict，merge阶段又把current B与collapsed incoming A比较并再记一次conflict。Prospective接口因此多算一份issue；临近cap时collector会把应归为`unassemblable`的attempt提前改判为cap failure，且`before + delta == after`不成立。
- evidence: reviewed revision上的最小probe得到`before=20`、`additional_held_bytes=161`、`after=131`，真实delta为111。Implementer自报的500-step fuzz没有覆盖“existing值等于incoming同event后一个duplicate、但不等于第一个”的顺序组合。
- fix: Delta计算必须保持同event重复choice／tool index的逐项顺序，并针对current state逐次演算，而不能先把incoming压成一个fresh-state结果再与current做第二次merge。增加choice finish、tool id/name与unknown value各一组`current=B；incoming=A,B`控制，逐项断言`before + delta == after`及failure provenance。

#### Residual B：materialization reservation仍不覆盖结构型峰值

- severity: `major`（原finding的未关闭部分）
- primary_location: `src/app/pipeline/chat_completions/state.py:412-434`
- related_locations: `src/app/pipeline/chat_completions/state.py:598-699,1661-1766`
- failure_scenario: Projection的working reservation固定为`output_bytes + 64KiB`，但递归generator stack的工作量取决于JSON深度而非输出byte length；100层nested array的输出只有380 bytes，materializer peak已超过该固定余量。Observation reservation更把`working_copy_bytes`固定为0；大量小choice会materialize成大量dataclass／tuple／JsonObservation对象，其真实峰值远大于按字符串逻辑量计算的`output_bytes`。因此flat 2M字符串probe通过，不能支撑“所有合法shape的working copy＋output都已预留”。
- evidence: 两个只针对未覆盖结构的probe在CPython 3.14.2复现。其一，100层nested unknown的projection：`output=380`、`reservation.total=66296`、`tracemalloc peak=109131`。其二，5000个合法小choice的observation：`working=0`、`output=317934`、`tracemalloc peak=1363924`。两者均在materializer完成且结果语义正确时超过reservation，不是fixture或异常路径代打。原2M flat probe与only-output mutation仍有效，但只判别“大字符串需要output＋working两份”，看不见深度与高fan-out对象开销。
- fix: 不使用固定64KiB猜测writer开销，也不把observation materialization的working cost写死为0。要么把writer改为显式迭代状态机并对其有界工作结构给出可计算上界，同时为snapshot逐对象／tuple计入working/output；要么把reservation定义为经验证的保守结构函数，至少随nesting depth、choice/tool/unattributed/issue数量增长。测试需保留2M正控，并新增deep-nesting与many-small-records两类正交控制；把working reservation退回固定值／0时，各自必须在`peak <= reservation.total_bytes`处判红。

### Fix diff新增breakage检查

未发现独立于`task-2-facts-review-03`的新Critical／Important breakage；上述三个失败面均属于原finding要求的prospective delta与materialization cap闭包，未另编号。Diff只改Task 2的`__init__.py`、`state.py`与对应unit tests，没有进入collector／retry／provider／TUI；其余13项已关闭finding的行为未见被反转。

### 证据边界

按指令未重跑作者报告的`123 passed`、Ruff或Pyright，也未重跑其2M flat probe和19项mutation。完整读取原review的round 1结论、更新后的implementation report与1221行fix package，并核对最终`state.py`及新增tests。新增probe只覆盖作者证据未覆盖的三个前提：same-event duplicate相对existing state的delta equality、deep nested projection working peak、many-choice observation allocation peak；tracemalloc数字只绑定本地CPython 3.14.2，不外推其它runtime，但源码中的固定64KiB／zero working reservation已足以说明接口没有结构性上界。

### 当前 verdict

- SPEC COMPLIANCE：❌
- TASK QUALITY：Not approved
- F-03：NOT ADDRESSED
- fix diff新增Critical／Important breakage：0

### Fix round 2 re-review交付声明

- delivery_complete: true
- completed_at: 2026-09-06
- reviewed_finding_total: 1
- addressed: 0
- not_addressed: 1
- new_critical: 0
- new_important: 0
- spec_compliance: fail
- task_quality: not-approved


---

## Fix round 3 scoped re-review — 2026-09-06

- attempt_id: `task-2-rereview-a9976b3e-3`
- reviewed_at_rev: `0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f`
- scope: 仅复核`task-2-facts-review-03`的residual A／B及fix diff `e42fc7660a656bc53a1ee7ea06e920b555d2a1f5..0a7c9ceb76d1de55311f0c6557a2c6fc1a94d11f`，并检查该diff引入的新Critical／Important breakage。
- updated_implementation_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/reports/260906-task-2-facts-implementation.md`，SHA-256 `de5fe12130e6341fecb7cbad240482c77b57afb0231acadf59d764ff1ecc7a1d`
- fix_diff_package: `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/review-e42fc76..0a7c9ce.diff`，SHA-256 `8d7082bfa6bde29c042a96af83f0fd44d18fe70fec486cbe346cf7af01455d50`
- ruling_basis: 本轮按下发Ruling把cap解释为同时存活representation的logical encoded bytes，沿用`DeliveryUnit.size_bytes`；不再用CPython heap／tracemalloc峰值本身作合规门，但working reservation必须随nesting与record count增长。

### `task-2-facts-review-03`：NOT ADDRESSED

Residual A的顺序语义已修正，但“additional sizing不clone retained metadata”仍未兑现；Residual B按新Ruling已修正。因此F-03整体仍为NOT ADDRESSED。

#### Residual A：部分关闭，仍有retained FrozenJson metadata clone

`_ProspectiveSizer`按同event原序维护first-string、concat、unknown、seen与new choice/tool的sparse overlay，已消除上一轮`current=B；incoming=A,B`被collapsed incoming重复计issue的问题；choice finish、tool id/name与unknown三组回归逐项对照`before + delta == after`，其判据与production merge顺序一致。

但`additional_held_bytes()`遇到已有structured unknown／usage值时仍调用`_same_frozen_json()`；该函数在`state.py:1486-1494`对current retained `FrozenJsonObject`执行`dict(left.items)`，并在每一层递归重复创建dict。也就是说，新的sizer没有clone choice/tool draft，却仍会为被比较的retained FrozenJson object复制完整mapping metadata。现有“no clone”test只拦`copy.deepcopy`、`thaw_json`和public materializer，无法判红内建`dict(left.items)`。这直接违反本轮要求的“`additional_held_bytes`不clone retained metadata”，故Residual A未关闭。

修复应让semantic equality只索引incoming侧，直接遍历current `FrozenJsonObject.items`并在incoming索引中查值，递归时保持同一方向；或给FrozenJson在创建时保存order-insensitive canonical equality／fingerprint。需要一个带宽/深nested existing unknown的控制，在prospective sizing期间令任何对current `.items`的mapping copy触发sentinel，同时仍断言same value delta为0、conflict只新增一次issue。

#### Residual B：ADDRESSED

按本轮Ruling，不再把tracemalloc heap peak当作cap oracle；上一轮报告用`peak > reservation.total_bytes`否定logical reservation的那部分理由由本节明确撤回，不再支撑verdict。`projection_reservation()`与`observation_reservation()`现在都返回`working_copy_bytes == output_bytes`，所以working与output两份同时存活representation被分槽计入；两者在预量阶段不调用payload／snapshot materializer。2,000,000-byte content control断言两份完整logical copies；100层nested projection使reservation total从378增长到778；5000-choice observation使total从single-choice 318增长到218060。对应only-output、fixed-64KiB与zero-observation-working mutations均在目标reservation断言判红。该证据足以支持本Ruling要求的结构扩展性，不声称约束CPython allocator。

### Fix diff新增breakage检查

未发现独立于F-03的新Critical／Important breakage。Diff仅修改`state.py`及其unit tests；projection incremental writer与既有stdlib byte oracle保持同一字段顺序／escaping规则，已关闭的其余13项finding所依赖的reader、raw decoder、state snapshot字段与translated assembler均未被改动。

### 证据边界

按指令未重跑作者报告的127 tests、Ruff或Pyright。完整读取更新implementation report与1311行fix package，并核对最终`_ProspectiveSizer`、reservation、incremental writer及新增tests。没有把本轮Ruling排除的tracemalloc heap ceiling继续当作验收；结论来自源码中对retained `FrozenJsonObject`的显式`dict(left.items)`复制。顺序duplicate与2M／deep／5000 controls按source、oracle与mutation位置审查，未重复执行作者命令。

### 当前 verdict

- F-03：NOT ADDRESSED
- fix diff新增Critical／Important breakage：0
- SPEC COMPLIANCE：❌
- TASK QUALITY：Not approved

### Fix round 3 re-review交付声明

- delivery_complete: true
- completed_at: 2026-09-06
- reviewed_finding_total: 1
- addressed: 0
- not_addressed: 1
- new_critical: 0
- new_important: 0
- spec_compliance: fail
- task_quality: not-approved


---

## Fix round 4 scoped re-review — 2026-09-06

- attempt_id: `task-2-rereview-a9976b3e-4`
- reviewed_at_rev: `bfd9c2d952e89ee77d3c8daade19d5c2640eb4a3`
- scope: 仅复核`task-2-facts-review-03` Residual A及fix diff `9dc86112db0d122f6e01a0077bea41a06411aff0..bfd9c2d952e89ee77d3c8daade19d5c2640eb4a3`；同时确认上一轮已关闭的Residual B与其余13项finding未被本diff回退，并检查新增Critical／Important breakage。
- updated_implementation_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/reports/260906-task-2-facts-implementation.md`，SHA-256 `f0798f5597ad56946e2e958162f4612d3437ab7c8b6eae7bd6e1eb892b5145ff`
- fix_diff_package: `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/review-9dc8611..bfd9c2d.diff`，SHA-256 `14b33895158ea30f493f80f21a999ba4528d97e8b52c8c3a9aa56f07da4198e0`
- ruling_basis: cap计同时存活representation的logical encoded bytes，沿用`DeliveryUnit.size_bytes`，不声称CPython heap／tracemalloc ceiling；working reservation必须随nesting／record数量增长，不能是fixed 64KiB／zero。

### `task-2-facts-review-03`：ADDRESSED

Residual A已关闭。`_same_frozen_json(left, right)`现在先核object tuple长度，仅为incoming `right.items`建立lookup dict，直接迭代current／retained `left.items`，并在递归object／array比较中始终保持left→right方向；不再复制current retained mapping metadata。全部production与prospective call site均以既有值／overlay值为left、当前incoming value为right，overlay本身只记录本event的新facts，不是retained state clone。

Deep/wide sentinel的鉴别力成立：测试先收集current retained object各层`.items` tuple identity，再patch模块级`dict`，仅当`dict(...)`收到这些current tuples时判红；正常实现对incoming建索引可通过，把旧`left_items = dict(left.items)`恢复后会在目标sentinel失败。Same-value reversed-key object的delta为0，deep `True→1`与array顺序变化各只新增一个unknown conflict issue，并逐步断言`before + delta == after`。先前choice finish、tool id/name及unknown的`current=B；incoming=A,B`顺序controls仍保留，故collapsed-incoming回归也有独立判据。

Residual B继续为ADDRESSED。本diff只改变FrozenJson equality及对应tests，没有改动`projection_reservation()`／`observation_reservation()`、incremental byte writer或materializer入口。按本轮Ruling，2,000,000-byte control计working与output两份logical representation；deep projection与5000-choice observation使reservation随structure／record count增长；only-output、fixed-64KiB与zero-observation-working mutations均指向各自断言。上一轮基于tracemalloc heap ceiling的否定已明确撤回，本轮没有重新采用。

### Fix diff新增breakage检查

未发现新Critical／Important breakage。Source diff只有`_same_frozen_json()`删除current-side dict conversion并保持语义比较不变；tests只增加deep/wide retained-side sentinel与same/conflict delta断言。其它13项finding涉及的decoder、event reader、snapshot字段、usage/logprobs、serializer及translated assembler均未被修改；Residual B的reservation代码也未被修改。

### 证据边界

按指令未重跑作者报告的128 tests、Ruff或Pyright。完整读取原review追加段、implementation report round 4及174行fix package，并核对全部`_same_frozen_json()`call sites的left／right方向、deep/wide sentinel及既有2M／deep／5000与mutation controls的保留情况。本结论证明当前source与tests满足本轮scoped合同，不外推Task 3 collector接线或真实provider行为。

### 当前 verdict

- F-03：ADDRESSED
- fix diff新增Critical／Important breakage：0
- SPEC COMPLIANCE：✅
- TASK QUALITY：Approved

### Fix round 4 re-review交付声明

- delivery_complete: true
- completed_at: 2026-09-06
- reviewed_finding_total: 1
- addressed: 1
- not_addressed: 0
- new_critical: 0
- new_important: 0
- spec_compliance: pass
- task_quality: approved
