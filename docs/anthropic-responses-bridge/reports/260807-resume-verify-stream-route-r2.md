# Responses stream route R2 独立验收报告

## 判定

**PASS。** 候选 `/home/xp/src/ghc-api-proxy-py-stream-route` 的 `HEAD` `bc436af647507df4ea45f3b01ca8942fade4f036`，相对 base `b91e58a29324b11840002efc53ed6f869b800c39`，满足本轮用户明确限定的可确定验收范围：真实 ASGI text happy／withholding／terminal／usage、首 block 前后 disconnect、postcommit Anthropic error SSE、`max_output_tokens` incomplete success、跨 chunk CRLF与`data:`无空格、message lifecycle不静默成功、malformed tool arguments typed error，以及 History committed／partial projection。

本轮没有发现实证缺陷。该 `PASS` 只覆盖下列矩阵，不外推到 retry、quota、backpressure、partial socket／sink write、delivery uncertainty、真实 loopback listener、真实 upstream或完整 bridge Acceptance。

## 输入与范围

行为 oracle为候选树的 `docs/agents/anthropic-responses-bridge/spec.md`与`docs/agents/anthropic-responses-bridge/acceptance.md`。缺陷来源输入为主树 `docs/tmp/260807-resume-review-code-stream-route.md`中的 R1 8 major；执行边界输入为主树 `docs/tmp/260807-resume-backup-port-smoke-r2.md`。本轮先从冻结 Spec／Acceptance独立推导 expected，再读取 R1、R2计划、实现与现有测试。

验收矩阵映射如下：

| 本轮行为 | 冻结 Acceptance 对应项 | 本轮判据 |
|---|---|---|
| 真实 ASGI text happy、withholding、terminal、usage | STR-01、STR-02、STR-05、TR-HTTP | `/v1/messages`只产生一次 Responses exchange；authoritative item done前零 success headers／body；首批为完整 text block；唯一成功 terminal；usage按`I=max(0,T-R-W)`归一 |
| disconnect pre／post | REL-05 | precommit零下游事件；postcommit只保留已提交完整前缀；两者均关闭upstream、不retry、History失败且finalize一次 |
| postcommit Anthropic error SSE | STR-04、REL-03、LIFE-01 | 已提交完整前缀后出现单一 Anthropic `error`，无`message_stop`；History保留前缀和错误事实 |
| incomplete max-output success | NS-04、STR-04 | `response.incomplete`且reason为`max_output_tokens`映射为`stop_reason=max_tokens`并成功终止 |
| cross-chunk CRLF、`data:`无空格 | Spec “Upstream Responses HTTP SSE” | CRLF在每个字节切分点仍只解析一个对象；`data:`后无optional space仍解析 |
| message lifecycle no silent success | NS-01、STR-03、STR-04 | authoritative item content不得消失；空message source不得形成合法零content成功 |
| malformed tool args typed error | NS-02 | malformed JSON和JSON scalar／array严格映射为`invalid_tool_arguments`，不生成`{}`或成功tool block |
| History committed／partial projection | LIFE-01 | success保存完整committed blocks／usage／complete；postcommit error或cancel保存committed prefix／incomplete／error，不从raw Responses wire伪造成功 |

## 执行来源与只读边界

所有承载结论的有效 shell运行均在同一调用中验证：

- `PWD=/home/xp/src/ghc-api-proxy-py-stream-route`。
- Git top-level为同一路径。
- `HEAD=bc436af647507df4ea45f3b01ca8942fade4f036`。
- base `b91e58a29324b11840002efc53ed6f869b800c39`是候选祖先。
- Python模块来源为候选树，例如`app.__file__=/home/xp/src/ghc-api-proxy-py-stream-route/src/app/__init__.py`与route模块位于同一候选`src/`。
- 有效测试、probe与merged-state回归的`STATUS_BEFORE`、`STATUS_AFTER`均为Git空状态的SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。

目标worktree全程只读。独立临时验收harness位于`/tmp/vr2_stream_acceptance.py`，测试／probe日志位于`/tmp/vr2-bc436af-tests.log`、`/tmp/vr2-bc436af-probe4.log`与`/tmp/vr2-bc436af-regression.log`。本报告是唯一主树写入。

共享终端期间多次出现其他并发会话输出、外部`Ctrl-C`与交互heredoc污染。凡缺少本轮唯一nonce、指向其他worktree／HEAD、未形成完整临时日志或退出码非零的调用均整体作废，没有用于`PASS`。

## 验收结果

| 验收项 | 独立实证 | 结果 |
|---|---|---|
| 真实 ASGI text happy | 独立harness直接调用生产FastAPI／Starlette ASGI app；fake Responses收到一次`stream=true`请求；下游只含Anthropic SSE | PASS |
| authoritative withholding | delta与`response.output_text.done`后下游仍无headers／body；仅authoritative`response.output_item.done`后提交首批 | PASS |
| 首block与terminal | 首body精确为`message_start → content_block_start → text_delta → content_block_stop`；尾部恰为`message_delta → message_stop` | PASS |
| usage | upstream `T=12,R=3,W=2,O=7`映射为`input=7,cache_read=3,cache_creation=2,output=7`；History usage相同 | PASS |
| precommit disconnect | 候选route smoke覆盖ASGI 2.3／2.4：零下游消息、upstream关闭、单attempt、FAILED＋HTTP 499、ERROR→FINALIZE | PASS |
| postcommit disconnect | 独立真实ASGI probe先提交完整text block，再发送`http.disconnect`；无`message_stop`、无synthetic error、无重复prefix；upstream关闭、单exchange、FAILED＋499，History保存已提交text和`complete=false` | PASS |
| postcommit error SSE | 已提交text prefix后注入unknown Responses event；HTTP仍为已提交的200，SSE尾部是唯一`error`，无`message_stop`；History保存prefix、typed error与`complete=false` | PASS |
| max-output incomplete | `response.incomplete`＋`incomplete_details.reason=max_output_tokens`得到成功`message_delta(stop_reason=max_tokens)`＋`message_stop`，History为COMPLETED | PASS |
| CRLF／`data:` framing | 独立oracle枚举CRLF frame每个切分点；全部得到同一JSON对象；`data:{...}`无空格同样解析 | PASS |
| message no silent success | authoritative item done可独立补足text；empty message lifecycle得到HTTP 502、code `empty_response_content`，无`message_stop` | PASS |
| malformed tool args | 独立parser probe覆盖`{`、`[]`、`null`与JSON string，全部产生`ResponsesStreamProtocolError(code=invalid_tool_arguments)` | PASS |
| History full projection | text happy保存完整Anthropic message、text block、normalized usage与`delivery.complete=true` | PASS |
| History partial projection | postcommit error与postcommit disconnect均保存committed prefix、`delivery.complete=false`和对应终止事实 | PASS |

## 关键正控

本轮执行了三个不写生产文件的单侧正控：

1. **Withholding正控**：向真实delayed-response入口注入“authoritative done前立即输出`LEAK-BEFORE-AUTHORITATIVE-DONE`”的source，同一下游可见性oracle按目标原因捕获early body，记录`WITHHOLDING_POSITIVE_CONTROL=RED_FOR_TARGET_REASON`。
2. **Message no-loss正控**：仅把`ResponsesStreamParser._complete_message_from_item`临时替换为静默丢弃authoritative content；同一terminal oracle不允许成功，而转为`empty_response_content`，记录`MESSAGE_NO_LOSS_POSITIVE_CONTROL=RED_FOR_TARGET_REASON`。
3. **`data:`无空格正控**：仅把SSE data-field解析临时收紧为必须`data: `；无空格正确样本随即被丢弃，原expected抓红，记录`DATA_NOSPACE_POSITIVE_CONTROL=RED_FOR_TARGET_REASON`。

这些变异仅存在于独立Python进程内，进程退出后自动恢复；候选文件未修改。正控证明关键判据具有目标判别力，但不被外推为retry、quota或socket delivery-uncertain等未执行机制的证明。

## 实际运行记录

### 限定测试集

命令范围：

- `tests/smoke/test_anthropic_responses_stream_route.py`。
- `tests/unit/test_responses_stream_parser.py`。
- `tests/unit/test_streaming_sse.py`。

结果：退出码`0`，pytest summary为`69 passed in 2.56s`。该数字只表示上述三个文件本次运行的pytest summary，不是仓库测试总数。

### 独立 ASGI／parser probes

`/tmp/vr2_stream_acceptance.py`在精确候选gate下执行，结果包含：

- `REAL_ASGI_TEXT_HAPPY_WITHHOLDING_TERMINAL_USAGE=PASS`。
- `POSTCOMMIT_ANTHROPIC_ERROR_SSE_AND_PARTIAL_HISTORY=PASS`。
- `MAX_OUTPUT_SUCCESS_AND_MESSAGE_LIFECYCLE_NO_SILENT_SUCCESS=PASS`。
- `POSTCOMMIT_DISCONNECT=PASS`。
- `CROSSCHUNK_CRLF_AND_DATA_NOSPACE=PASS`。
- `MALFORMED_TOOL_ARGS_TYPED_ERROR=PASS`。
- 三个目标正控均按预期原因变红。
- `INDEPENDENT_PROBE_VERDICT=PASS`，退出码`0`。

### 限定 merged-state 回归

命令范围额外加入：

- `tests/smoke/test_anthropic_responses_route.py`。
- `tests/smoke/test_anthropic_block_delivery.py`。

连同上述stream route、parser与framing文件一起运行，结果为退出码`0`，pytest summary为`95 passed in 3.73s`。该范围验证non-stream route、stream route、delivery、parser与framing的直接接缝；仍不是全仓回归或完整产品验收。

## 最终实现承载点

以下位置是本轮运行结果的实现承载说明，不替代黑盒证据：

- `src/app/routes/anthropic.py:29-78`：stream终态、usage与History committed projection。
- `src/app/routes/anthropic.py:145-180`：Responses stream renderer、upstream cleanup与delayed SSE response接线。
- `src/app/streaming/sse.py:53-145`：prefetch期间并发disconnect监听、延迟response start、body send与iterator close。
- `src/app/streaming/openai_sse.py:6-47`：跨chunk line buffer、CRLF处理与`data:` optional space。
- `src/app/delivery/responses_anthropic_stream.py:56-109`：从accepted frontier生成full／partial History projection。
- `src/app/delivery/responses_anthropic_stream.py:112-245`：Responses parser→delivery→Anthropic block／terminal／postcommit error。
- `src/app/openai/responses_stream_parser.py:166-318,384-423,491-663`：content lifecycle、terminal reason、strict tool arguments与authoritative message content补足／核对。

## 明确未验证

以下范围按用户要求不执行、不外推，保持`UNVERIFIED`：

- retry ownership、precommit retry、attempt reset、retry exhaustion与postcommit continuation／full replay。
- request／global quota、resident memory accounting、slow consumer、有限队列、backpressure与capacity deadline。
- partial socket write、RST offset、ASGI send outcome的完整矩阵、delivery uncertainty和真实客户端durable visibility。本轮只保留现有首body send failure的组件回归，不将其升级为完整socket验收。
- 真实loopback TCP listener、Uvicorn进程、备用端口app／fake进程incarnation、pidfd、wait／reap与shutdown smoke。用户本轮要求执行可确定代码内范围，不要求启动R2计划的完整服务拓扑。
- HTTP／WS upstream parity、真实upstream canary、capture corpus、真实凭据、systemd、部署与cutover。
- full CAL-04 strict grammar corpus、官方Anthropic SDK consumer、所有unknown／malformed event组合与完整bridge Acceptance。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/delivery/responses_anthropic_stream.py:21-45,218-229` | request-local `_BufferedSink`与ASGI body send之间仍是两段式pending→yield→ack接缝，完整partial-socket语义需要更底层transport fault验证 | 本轮不改生产代码；明确保留partial socket／delivery uncertainty为`UNVERIFIED`，不得由当前PASS外推 |
| `src/app/routes/anthropic.py:29-78` | `_history_stream`同时处理observer、context terminal、usage和History projection，职责较密集 | 当前行为有真实ASGI与full／partial projection证据，不在验收轮重构；后续driver／History owner整合时应保持单finalize与committed-frontier oracle |
| `tests/smoke/test_anthropic_responses_stream_route.py` | route smoke已超过一千行并同时承载frontier、route、failure与History场景 | 本轮不拆；后续可按route lifecycle／delivery outcome／History projection拆文件，但不能削弱真实ASGI正反控制 |

## 方法反思

- **更好的内部替代方案**：完整R2备用端口进程smoke能进一步证明真实listener、进程reap与raw socket行为，但用户明确限定本轮为可确定范围且不外推partial socket；因此本轮采用真实生产ASGI入口加独立parser／framing oracle，是当前范围内更直接的路径。
- **判据判别力**：withholding、message no-loss与`data:`无空格均完成单侧正控；postcommit disconnect通过独立ASGI probe补上候选自带测试缺口。未对每个行为做mutation，因此报告只把三个关键机制称为正控通过，不夸大为全矩阵mutation coverage。
- **成熟第三方方案**：真实ASGI路径复用FastAPI／Starlette／AnyIO的disconnect与streaming实现；SSE framing仍由项目轻量parser承载。当前修复边界没有必要引入新的第三方SSE框架，但未来若扩大到完整SSE规范与fuzz corpus，应优先评估成熟parser而不是继续手写更多分支。

## 最终结论

候选`bc436af647507df4ea45f3b01ca8942fade4f036`对本轮明确限定范围的总体verdict为**PASS**。R1 8 major对应的可确定行为均获得实际执行证据；postcommit disconnect由独立真实ASGI probe补齐；关键withholding、message no-loss与`data:` framing正控均具有判别力。目标worktree保持精确HEAD且全程只读。

retry、quota、backpressure、partial socket／delivery uncertainty与完整备用端口进程smoke继续为`UNVERIFIED`，没有被本轮PASS静默放行。本报告是当前状态交付物，需由主会话按其文档评审流程复核后定稿。