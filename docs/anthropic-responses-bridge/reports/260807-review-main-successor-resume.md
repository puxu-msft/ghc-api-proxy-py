# Current main Anthropic Responses bridge merged-state 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py` current `main@b91e58a29324b11840002efc53ed6f869b800c39`。范围为 semantic `bfc461f57a507059c5c7b098e0616e7882f7333d`、route `86b6cc3e72c0312ea8e93940513ee55e290da245`、block `b91e58a29324b11840002efc53ed6f869b800c39` 的最终 merged state，以及它们与既有 reasoning carrier、Anthropic→Responses request converter、Responses→Anthropic non-stream converter、usage、hooks、History、parser／delivery 的接缝。已消费 `docs/tmp/260807-review-code-bridge-successor.md`、`docs/tmp/260807-verify-bridge-successor.md`、`docs/tmp/260807-audit-successor-replay-resume.md` 与最终逐片回放门。除本报告外严格只读。
- **总体 verdict**：**修复 major 后可进入下一阶段。** 当前为 **0 blocker／2 major**。三片已按正确顺序进入真实 main，结果 blobs 与 reviewed successor 精确一致；Responses non-stream happy path、typed stream reject、parser→typed delivery、single writer 与 empty reasoning／cardinality foundations 均仍可作为后续开发基础。但是 production route 尚未把 request capability facts 接入 converter，non-stream conversion／usage facts也没有进入 History 投影；因此不能把当前合并态称为完整 non-stream bridge 合同已闭合。
- **blocker 数**：0。
- **major 数**：2。
- **完整 stream 产品状态**：**`UNVERIFIED`**。当前 production route仍对 selected Responses `stream=true` typed reject，parser／delivery 尚无 production stream caller；本报告不把 parser→delivery core 的局部正确性外推为真实 route→parser→delivery→ASGI SSE E2E。

## 双视角覆盖证据

### 机械核对

- Gate 固定物理 root `/home/xp/src/ghc-api-proxy-py`、branch `main` 与完整 `HEAD=b91e58a29324b11840002efc53ed6f869b800c39`。三片 parent 链为 `bfc461f… → 86b6cc3… → b91e58a…`；各片 path 集合分别为 semantic 2 条、route 10 条、block 3 条。
- 逐路径核对 15 个 current main result blob，全部与 `260807-final-successor-replay-gate.md` 冻结的 successor 结果一致，包括 parser／parser tests、route／client／pipeline／header／route tests，以及 delivery implementation／delivery tests。
- 真实 import 探针使用主仓 `.venv` 与绝对 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py/src`，`app`、`app.routes.anthropic`、`app.pipeline.executor`、`app.openai.responses_stream_parser`、`app.delivery.anthropic_sse` 全部解析到该主仓 `src/`，没有借用其他 worktree。
- Production caller扫描覆盖 `DeliverySession`、`ResponsesStreamParser`、`consume()`、`responses_stream_not_supported`、`history.finalized()`、`ConvertedResponse.facts`／`usage_facts`、`ReasoningCapabilityFacts` 与 `ToolNameMapper`。`DeliverySession`只由 delivery模块定义和导出，parser只被 delivery内部导入；route／pipeline没有 production stream caller。
- `src/app/pipeline/executor.py:193-202` 的 selected Responses stream typed reject仍在 attempt 与 upstream调用之前；`src/app/anthropic/client.py:221-226` 还有第二层 fail-closed reject。既有真实ASGI route smoke覆盖零attempt、零upstream、`ERROR → FINALIZE` 与单History finalizer。
- `DeliverySession.__init__()`只调用一次 `sink.open_writer()`，operation lock串行化 typed／manual block与terminal写入；typed／manual mode不可混用。没有发现route第二 writer或第二 delivery finalizer。
- Empty reasoning在 stream parser中产生一个 `ReasoningBlock('', None)`，delivery用项目bare marker渲染一个thinking block；non-stream converter同样保持一item一block。现有 semantic tests覆盖 absent／empty encrypted content、authoritative item done与多item cardinality。
- 两次较长pytest取证遭并行终端串扰，输出不属于本评审命令，已全部作废；本报告不虚构 current main测试计数。先前 successor verification的 scoped `PASS`仅作为已消费的历史证据，不替代本轮main代码事实。

### 第一人称执行

- **真实 non-stream无thinking请求**：从`POST /v1/messages`进入同一个`RequestContext`，完成approval与`PRE_SEND`后选择Responses leg，request转换、Responses upstream、Anthropic body转换、response hooks、header allowlist与单次finalize顺序可走通；route smoke已覆盖200与429、header过滤、Messages dual-capability回归。
- **真实 non-stream thinking请求**：模型目录即使声明`reasoning_effort`与thinking budget，`AnthropicClient._send_responses()`仍以默认`reasoning_capabilities=None`调用request converter。converter按设计fail closed为`reasoning_not_supported`，因此模型明确支持的合法请求无法进入Responses upstream。
- **真实 non-stream成功后的History**：converter构造的`ConvertedResponse.facts`与`usage_facts`在`_send_responses()`内只用于生成客户端body，随后丢失；pipeline调用`history.finalized(context)`时不传response或usage，`RequestContext`也没有这些facts。最终History entry虽为completed，但`response=None`、`usage=None`，selected route／conversion degradation也没有投影载体。
- **Responses stream请求**：仍在upstream前返回`responses_stream_not_supported`，不会误走Messages byte passthrough，也不会建立第二writer。parser／delivery只可由测试或未来driver显式调用，所以完整stream继续`UNVERIFIED`而不是“已失败的生产stream实现”。

## 事实性发现

[major] `src/app/anthropic/client.py:227`、`src/app/protocols/anthropic_responses.py:290-346`、`src/app/models/capabilities.py:8-18` — production Responses route没有把模型reasoning capability facts传给request converter，导致合法thinking请求稳定误拒 — `ModelCatalog`中的`ModelInfo.capabilities.supports`已提供`adaptive_thinking`、`min_thinking_budget`、`max_thinking_budget`与`reasoning_effort`，converter也要求显式`ReasoningCapabilityFacts`；但`_send_responses()`调用`convert_messages_request_to_responses(prepared.wire)`时没有传facts。只要请求含`thinking.enabled`或`thinking.adaptive`，即使resolved model明确支持，converter都会走`reasoning_capabilities is None`并返回`reasoning_not_supported`。这违反Spec `spec.md:203`的能力约束映射合同，也使已经合并的request converter capability API在真实route上不可达 — 在route decision后从resolved `ModelInfo`构造request-scoped `ReasoningCapabilityFacts`，明确建模known／unknown budget与effort bands并传入每个attempt的converter；新增真实ASGI Responses-only thinking success、unknown capability reject、budget boundary与approval／`PRE_SEND`修改后重转换测试。

[major] `src/app/anthropic/client.py:252-259`、`src/app/pipeline/executor.py:292-321`、`src/app/history/consumer.py:20-29` — non-stream Responses转换产生的normalized response、usage与conversion facts在生产接缝被丢弃，completed History缺少合同要求的事实 — `convert_responses_response_to_anthropic()`返回`ConvertedResponse`，其中含`facts`与`usage_facts`；`_send_responses()`只序列化`converted.message`后即丢弃其余字段。成功pipeline随后仅调用`history.finalized(context)`，而`HistoryConsumer.finalized()`只有调用者显式传`response`才写`entry.response`，且没有从context取得usage／conversion facts。全仓生产扫描也没有其他`converted.facts`或`converted.usage_facts`消费者。结果是客户端能收到正确usage，但History entry的`response`与`usage`均为空，`usage_estimated`／`usage_inconsistent`或request degradation事实也无法进入History、metrics与trace，违反Spec `spec.md:142,368,421` — 不要让client把typed conversion结果压扁为仅`httpx.Response`；让同一个pipeline owner接收并保留normalized response、exact usage与conversion facts，在response hook后的最终Anthropic body校验完成后一次性投影到History。新增真实HistoryStore integration test，分别覆盖精确usage、usage缺失estimated、inconsistent details、request degradation、hook后最终response与失败路径不写success facts。

## 主观建议

无。完整stream的HTTP SSE framing、真实ASGI sink、retry／quota／backpressure／cancel／shutdown与post-commit failure均是已知未验证范围，不重复包装成新的major。

## 结论

本轮为 **0 blocker／2 major**。Current main确实包含与reviewed successor逐blob一致的semantic、route与block三片；真实main import、Responses stream typed reject、non-stream hooks／header基本流程、parser／delivery无production caller、single writer及empty reasoning／cardinality均未发现新的阻断性回归。**这些foundations与happy-path实现可以保留并继续开发，但在修复capability adapter与History事实投影前，不应把non-stream bridge宣称为合同闭合。**

完整Responses stream仍为 **`UNVERIFIED`**：当前没有production route→parser→delivery→ASGI SSE caller，也没有真实transport、downstream commit、retry、cancel与资源关闭E2E。本报告不把typed core的局部绿色或既有successor scoped `PASS`外推为完整stream产品结论。
