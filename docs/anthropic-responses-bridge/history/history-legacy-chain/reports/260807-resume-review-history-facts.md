# Responses History facts 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-history-facts`，branch `fix/responses-history-facts`，candidate `e5db34bcf7be017e602fb1ee3f666b3ad2e96a3f`，base `b91e58a29324b11840002efc53ed6f869b800c39`。直接评审 7 文件差异及最终代码接缝：`docs/2604-rewrite/BACKLOG.md`、`src/app/anthropic/client.py`、`src/app/history/consumer.py`、`src/app/pipeline/context.py`、`src/app/pipeline/executor.py`、`tests/component/test_history_store.py`、`tests/component/test_pipeline_executor.py`。
- **总体 verdict**：**修复 major 后可进入下一阶段。** 当前为 **0 blocker／3 major**，**不可 squash**。
- **blocker 数**：0。
- **major 数**：3。

## 双视角覆盖证据

### 机械核对

- 每个可信 shell 调用均在同调用内验证候选物理 root、Git top-level、branch 与完整 HEAD。候选工作树在测试与探针前后均为空；唯一写入是主树本报告。
- 差异恰为 7 文件。`AnthropicAttemptResult` 保留 response-side `ConvertedResponse`；executor 在 response hook 后调用 `MessagesResponse` 校验；`HistoryConsumer` 从同一个 `RequestContext` 形成终态 entry，没有第二个 History owner或新增 SQLite 列。
- SQLite 继续使用既有 `response`／`usage` JSON blob。writer round-trip测试证明新增 `estimated`、`inconsistent`、details与`conversion_facts`键可原样写入／读出；全仓没有依赖 History usage 固定键集合的消费者，未发现 usage JSON 兼容 major。
- 成功 integration test从真实`HistoryStore.get()`读回hook后text，证明History response实际持久化。invalid hook test证明failed entry不写response／usage，但它没有观察更早的success callbacks。
- `docs/2604-rewrite/BACKLOG.md`第4节本来就是“client/upstream双腿数据模型＋multi-stage persistence”的已决简化项。新增文字只澄清现行轻量投影与未来typed schema边界，没有写入branch／HEAD／测试状态，未发现live state误放。
- candidate `e5db34b…`的`tests/`全集为`472 passed`；两份改动component测试为`13 passed`。`pyright --pythonpath "$PWD/.venv/bin/python" src tests`为0 errors／0 warnings；`ruff check src tests`通过。首次Ruff命令误含本分支不存在的`contrib/systemd/install-user.py`，其`E902`是错误pathspec造成的假红，已用实际仓库范围重跑关闭。
- false-green／false-red：① failure test只检查SQLite，没有观察limiter／strategy success callback；故障探针得到最终`ApiError:invalid_anthropic_response_body`同时`SUCCESS_CALLBACKS=1`。② invalid hook fixture只返回`{}`，没有测试“字段存在但违反Anthropic判别联合”的body；探针证明缺`type`／`role`且text block缺`text`仍被接受。③反向检查合法Messages／Responses fixture、History JSON round-trip和全量测试均通过，未发现现有合法样本因新校验被误拒。

### 第一人称执行

- **Responses成功＋hook改text**：同一`RequestContext`进入一个attempt；client返回`AnthropicAttemptResult(response, converted_response)`；executor运行Anthropic response hook、校验hook后body、把最终`MessagesResponse`与response conversion usage facts写回同一context；同一`HistoryConsumer.finalized()`写出completed entry。SQLite中的text为`hooked`，single lifecycle／finalizer成立。
- **Responses成功＋hook破坏body**：HTTP 200后executor先调用limiter与retry strategy的success callback，再运行hook与最终body validation。validation失败后context虽正确进入failed且History未写response／usage，但success side effect已不可撤销。
- **Responses request degradation**：request converter为cache-control、metadata allowlist和portable-thinking loss产生`ConvertedRequest.facts`；`AnthropicClient._send_responses()`只读取`converted_request.wire`。成功History因此只有response-side facts，request-side degradation不可观察。
- **结构上非法但可被默认值补齐的hook body**：客户端实际收到的bytes可缺`type`／`role`，且`{"type":"text"}`无`text`；`MessagesResponse.model_validate()`仍接受，并在History序列化时补出`type="message"`／`role="assistant"`。History不再是客户端可见最终response的真实投影。

## 事实性发现

[major] `src/app/pipeline/executor.py:292-293,330-359` — 最终response hook／schema validation失败前已经发布成功回调，违反“failure不写success facts”与only-final-success语义 — `limiter.report_success()`和`coordinator.notify_success()`紧跟HTTP 2xx执行；随后hook可把body变成非法Anthropic response并由`_finalize_failure()`终结为failed。可复现结果为`FINAL=ApiError:invalid_anthropic_response_body`与`SUCCESS_CALLBACKS=1`。`RetryCoordinator.notify_success()`还会调用strategy `on_success()`；现有`PoisonedThinkingStrategy.on_success()`可写quarantine store，不只是计数器噪声。现有failure测试仍全绿，因为只断言SQLite没有response／usage — 把request-success side effects移动到hook完成、最终body严格验证成功且success facts已写入context之后，并在transition／History finalization前恰好发布一次。新增recording limiter与strategy的负向测试，覆盖hook异常、hook后schema非法和body读取失败均为零success callbacks；合法最终body为恰好一次。

[major] `src/app/anthropic/client.py:233-240`、`src/app/protocols/anthropic_responses.py:150-153,210-214`、`src/app/pipeline/context.py:69-70`、`src/app/history/consumer.py:63-68,91,106` — request-side conversion degradation facts仍被丢弃，History只保存response-side facts，未完整关闭main merged report的History major — `convert_messages_request_to_responses()`返回`ConvertedRequest(wire, facts, tool_name_mapping)`，但`_send_responses()`只使用`.wire`；全仓没有`converted_request.facts`生产消费者。候选context的`conversion_facts`又被静态限定为`tuple[ResponseConversionFact, ...]`，成功时只赋`converted.facts`。因此cache-control、metadata allowlist与portable-thinking等明确degrade的请求可completed，却不会进入History；Spec `spec.md:420-423`明确要求History保留capability／degradation facts — 为attempt result／request context建立可区分request与response provenance的typed conversion facts，保留最终成功attempt的request degradation与response normalization facts并投影稳定JSON。补真实HistoryStore测试：构造允许degrade且成功的request，断言original Anthropic payload不变、entry只有一条、request degradation code／field path／reason可读；retry场景须带清晰attempt provenance或明确只投影最终成功attempt。

[major] `src/app/pipeline/executor.py:33-45`、`src/app/models/anthropic.py:9-51`、`src/app/history/consumer.py:27-31` — hook后“最终body校验”会接受结构上非法的Anthropic响应，并让History保存与客户端实际bytes不同的对象 — `MessagesResponse`给顶层`type`和`role`默认值；通用`ContentBlock`只要求`type`，`text`／tool／thinking字段均可为`None`，也不按block type建立discriminated union。因此hook返回`{"id":"msg_bad","model":"claude-test","content":[{"type":"text"}]}`时`_validate_response_body()`通过；客户端收到缺`type`／`role`且text无`text`的原始bytes，而History的`model_dump()`补出`type="message"`、`role="assistant"`。现有invalid fixture只用`{}`，无法抓到该假绿；这违反“hook修改结果重新校验Anthropic response schema后才能提交”及History保存客户端可见response的合同 — 使用严格wire validator：顶层`type`／`role`必须显式存在且取固定值，content采用按`type`判别的严格联合并要求各类型必需字段，同时拒绝不允许的组合；不要用会补默认值的模型同时充当wire acceptance oracle。History应从已验证且不改变语义形状的最终body形成投影。新增合法text／tool／thinking正样本，以及缺顶层字段、text无text、tool缺id/name/input、错role/type等负样本，并加入独立Anthropic SDK schema／严格consumer oracle避免同源假绿。

## 主观建议

无。

## 结论

当前candidate为 **0 blocker／3 major**，**不可 squash**。它已正确完成同一pipeline owner上的hook后response持久化、existing JSON blob round-trip与failed History不写response／usage，但仍有三处合同缺口：最终失败前发布success callbacks、request-side degradation facts被丢弃，以及hook后body校验过宽并导致History与客户端bytes分叉。修复三项major并补双向控制后应复评；复评达到0 major时才可明确放行squash。
