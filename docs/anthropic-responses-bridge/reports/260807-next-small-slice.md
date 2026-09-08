# 下一最小代码切片：headers 前 network retry

## 调查边界与结论

- **调查锚点**：`/home/xp/src/ghc-api-proxy-py` 的 `main@d903d726baf3f15bf46ddf17384564fee154ed6a`。
- **规范输入**：current Spec `docs/agents/anthropic-responses-bridge/spec.md`、Acceptance `docs/agents/anthropic-responses-bridge/acceptance.md`、Readiness `docs/agents/service-cutover/readiness.md`。本调查只用它们确定行为边界，不设计完整状态空间或新验证系统。
- **候选方向**：只比较仍未验证的 retry、quota／resident backpressure、真实 socket partial-write。
- **推荐**：下一片只做 **response headers 形成前，`send_prepared_attempt()` 抛出明确 `NETWORK` 错误时，由现有 application pipeline owner 在既有一次预算内透明 retry**。它关闭 Acceptance `REL-01`／`REL-04` 的 headers-before 最小子集，但不声称关闭首 block 未完成后的 stream retry、post-commit failure、quota／backpressure、真实 socket partial-write或完整 retry Acceptance。
- **为什么优先**：正确服务首先要求短暂连接建立失败不能直接让用户请求失败；当前代码已有唯一 retry owner、两次 attempt loop、每-attempt `PRE_SEND`、attempt／History事实和成功重试测试基座，只缺异常分支接入 coordinator。该切片不新增第二 lifecycle owner，能在现有 happy path 与 component smoke 后形成单一、可评审、可立即 squash 的提交。

## 用户可见目标

当 Anthropic 客户端通过 `/v1/messages` 选择 Responses leg，而第一次 upstream exchange 在任何 response headers 返回前因明确网络连接错误失败时，代理在同一 `RequestContext` 内执行至多一次透明 retry。若第二次成功，客户端只看到一份合法 Anthropic 成功响应；若预算耗尽，客户端只看到一个 Anthropic network error。失败 attempt 不泄漏 body、headers、usage、conversion success facts或成功 terminal；真实 upstream 调用数必须等于 `context.attempts`。

这一片刻意不承诺：HTTP 200 stream 已建立后、首 block 尚未完成时的 clean EOF／read reset retry。该路径发生在 pipeline 已把 streaming response 交给 route 之后，需重新协调 stream owner 与 retry owner，不能伪装成本片的顺手扩展。

## 现有接缝与事实证据

1. Spec 已冻结 application pipeline 为唯一 retry owner、SDK retry 关闭、pre-commit 可按预算 retry、失败 attempt 不得泄漏，见 `docs/agents/anthropic-responses-bridge/spec.md:333-360`。
2. Acceptance `REL-01` 要求 headers 前 transport reset 可由唯一 pipeline owner 新建下一 attempt，`REL-04` 要求预算耗尽只产生一个最终失败事实，见 `docs/agents/anthropic-responses-bridge/acceptance.md:195-230`。
3. Readiness 当前把完整 retry 标为 `UNVERIFIED`，并明确现有 happy smoke 没有发生第二 exchange，见 `docs/agents/service-cutover/readiness.md:57`。
4. `execute_anthropic_pipeline()` 已构造 request-scoped `RetryCoordinator(max_retries=1)`，见 `src/app/pipeline/executor.py:235`；attempt loop 每轮新建 `Attempt` 并重新运行 `PRE_SEND`，见 `src/app/pipeline/executor.py:248-268`。
5. 当前缺口就在 `send_prepared_attempt()` 的异常分支：`src/app/pipeline/executor.py:270-291` 把异常归一为 `NETWORK` 后立即 `_finalize_failure()` 并抛出，没有调用同一文件 `src/app/pipeline/executor.py:441` 已用于非成功 HTTP response 的 `coordinator.decide()`。
6. 现有 coordinator 已统一拥有预算、策略选择和 owner 记录，见 `src/app/pipeline/strategies/__init__.py:31-67`。生产默认只注册 poisoned-thinking 策略，见 `src/app/hooks/builtin/__init__.py:39-42` 与 `src/app/pipeline/strategies/__init__.py:70-111`。当前异常分支却把任意非 `ApiError` 都包装成 `NETWORK`；因此本片必须先用明确 transport exception allowlist形成 retryable observation，再交给 coordinator，不能只看包装后的 category。
7. 已有 component fixture 证明 429 后第二 attempt 成功、真实 calls 为 2、attempts 为 `[429, 200]` 且 History 只投影最终成功 attempt facts，见 `tests/component/test_pipeline_executor.py:1064-1109`。它可作为本片的就地测试基座，不需要新建验收框架。

## 最小改动 paths

### 必改

- `src/app/pipeline/strategies/__init__.py`：新增一个无 payload 改写、只接收“已由 executor 判定为 retryable transport failure”这一 typed observation 的有界 retry strategy。继续由 `RetryCoordinator` 消耗既有 `max_retries=1`，策略不自行分类任意异常、不 sleep、不发请求、不 finalize。
- `src/app/pipeline/executor.py`：只在 `prepared.route.protocol_leg == responses` 且原始异常属于明确 transport allowlist 时，把当前 attempt 记录为 typed network failure并交给现有 coordinator；获准则记录 `strategy_applied`／modifications 并 `continue`，未获准或预算耗尽才执行现有 `_finalize_failure()`。最小 allowlist须覆盖当前 runtime实测互不继承的 `httpx.TransportError`、`openai.APIConnectionError`与`anthropic.APIConnectionError`家族，其中 timeout subclasses已包含在各自connection／transport基类下。不得把普通 `RuntimeError`、conversion／capability `ApiError`、cancellation或shutdown归入 retry。
- **不要修改 `src/app/hooks/builtin/__init__.py`**：把 network strategy全局注册会顺带改变 direct Messages leg，而本切片只获准关闭 Responses bridge 的 headers-before 子集。由 executor在已解析 route事实后仅为 Responses leg组合该内建 policy，仍由同一个 coordinator执行。
- `tests/component/test_pipeline_executor.py`：复用现有 client、History、observer 与 Responses target fixtures，新增下述两个判别性测试。

### 不改

- `src/app/routes/anthropic.py`、`src/app/delivery/**`、`src/app/streaming/**`：本片不处理 pipeline 返回后的 stream read／delivery retry。
- `src/app/config/settings.py`：沿用现有一次 retry budget，不增加新配置、状态空间或 backoff policy。
- quota／reservation／queue 相关新模块：本片不引入。
- Spec、Acceptance、Readiness：代码片完成前不改 living 状态；后续只按实际证据更新，不提前写完整 retry `PASS`。

## 测试边界

只需运行已有测试与新增 2 个 component tests：

1. **新测试：headers-before network failure then success**。Responses target 第一次在返回 `httpx.Response` 前抛 `httpx.ConnectError`，第二次返回现有合法 non-stream Responses body。断言：客户端结果成功；`target.calls == 2`；attempt 数为 2；attempt 0 为 `NETWORK` error且记录 network retry owner；attempt 1 成功；`PRE_SEND` 每 attempt 一次；History／`RESPONSE`／`FINALIZE` 各只形成最终成功语义；失败 attempt 没有 success usage／response facts。该测试可再用一个 SDK wrapper exception参数值校准同一路径，但不要扩张成异常全空间。
2. **新测试：headers-before network retry exhaustion＋非transport反例**。两次都在 headers 前抛同类 network error，断言总调用数严格为 2、不发生第三次、两个 attempts均有 error、客户端得到单一 network failure、History failed且只 finalize一次、零 `RESPONSE` success callback；同一测试或紧邻断言再让 target 抛普通 `RuntimeError`，证明只调用一次且不会因当前宽包装误重试。仍只计一个测试函数，保持本片为2个新测试。

复跑已有：

- `tests/component/test_pipeline_executor.py`，尤其保留现有 429 retry、final success facts、failure lifecycle与History测试。
- `tests/smoke/test_anthropic_responses_happy_path.py`，确认 direct route／conversion happy path不回归。
- 项目现有全量 `pytest`、Ruff、Pyright，作为 squash 前回归门；不为本片搭建新的 acceptance harness。

这两个新测试必须区分两个方向：正常首次成功仍只调用一次，明确 network failure 才可调用第二次；预算耗尽不得调用第三次。它们不应把 `ApiError` 的所有类别都参数化成可 retry，否则会错误放宽 conversion、client、cancel 与 capability failure。

## 风险与护栏

- **最大风险——先 finalize 后 retry**：若保留当前 `_finalize_failure()` 再 `continue`，同一 context 会先进入 `FAILED`，随后又尝试执行，破坏 single terminal。修复顺序必须是“记录 attempt error → coordinator 决策 → 获准则 continue；拒绝／耗尽才 finalize”。
- **错误分类过宽**：当前 executor 在 `src/app/pipeline/executor.py:278-283` 把任何非 `ApiError` 包装成 `NETWORK`，所以检查 `normalized_error.category` 仍会错误重试普通程序异常。当前 `.venv` 类型探针还确认 `openai.APIConnectionError`／`anthropic.APIConnectionError` 不继承 `httpx.TransportError`。实现必须依据原始异常的明确 allowlist判 retryability，再构造统一 network fact；不得靠错误文本或包装后 category。
- **协议腿范围泄漏**：全局 builtin注册会改变 direct Messages leg。只有 current attempt 已明确选择 Responses leg时才组合该策略；Messages行为保持原样，除非另有规格与测试决定扩展。
- **资源关闭**：headers 前异常通常没有 `httpx.Response` 可关闭；若 target 抛出的 typed error未来携带 response，不能因 retry 泄漏它。本片不修改已有 response-returning非成功路径的 `response.aclose()`。
- **策略顺序**：network strategy 不修改 payload，poisoned-thinking仍只处理其确定性 upstream error。两者不应同时声称同一错误；测试须固定实际 owner名称和预算归属。
- **语义边界误报**：本片通过后只能写“headers-before network retry 子集已实现并回归通过”。首 block 未完成后的 stream truncation、post-commit、partial-write与quota仍为 `UNVERIFIED`。

## 为什么不选另外两个方向

### 暂不选 quota／resident backpressure

`REL-06` 要求 request aggregate＋global reservation、所有 resident owner 统一计账、有限 completed-block queue、charge-before-read、可取消等待、drain恢复、admission rejection及所有终态 release。Current `ResponsesConfig` 只有 WS queue／frame／connection limits，见 `src/app/config/settings.py:127-133`；生产代码搜索不到 bridge reservation／quota owner。要正确实现至少会跨 config、全局生命周期、parser／assembler、delivery queue、admission、observability和多类终态，绝不是可 happy-path＋smoke 后立即 squash的最小片。现在硬切一小段只会制造“有配置名但无真实 await 背压”的假实现。

### 暂不选真实 socket partial-write

当前 typed 基座已经把 sink outcome 分成 pending／accepted／uncertain，writer 返回后才推进 frontier，见 `src/app/delivery/anthropic_sse.py:699-705,771-775,787-804`；ASGI send 失败会调用 body uncertainty hook，见 `src/app/streaming/sse.py:141-171,173-186`；现有 route smoke 也覆盖首个 body send 抛错后的 uncertain frontier与History，见 `tests/smoke/test_anthropic_responses_stream_route.py:479-636`。真正未验证的是 Acceptance `REL-03B` 指定的 loopback socket 多 byte offset短写／RST及客户端实收前缀，而 ASGI `send()` 并不暴露底层 `socket.send()` 的短写字节数。要诚实补齐需 real server＋TCP fault proxy／socket injector与真实客户端观测，不只是再加一个 mock `send()` 测试；这更适合作为后续独立 local-fault slice，不能在当前小片里假称关闭。

## 推荐实施顺序与退出声明

1. 先写上述两个 component tests，使当前异常分支因“调用数只有1／过早 finalize”而红。
2. 增加 Responses-only的窄 network retry policy，并把明确 transport异常分支接入现有 coordinator。
3. 跑 component文件与既有 happy-path smoke，再跑全量 pytest、Ruff、Pyright。
4. 独立 review只核对该窄子集：single owner、两次上限、attempt／hook／History一致、非network错误不重试。
5. 通过后立即形成单一 squash候选；提交说明不得声称完整 `REL-01`～`REL-04`、完整 retry、P0或cutover已通过。

**推荐 verdict：选择 headers-before network retry。** 它是三个方向中唯一同时满足“直接改善正确服务”“复用现有成熟 owner与测试基座”“最少改动 paths”“不需要新验证系统”“happy-path＋smoke后可立即squash”的切片。随后优先级建议是：真实 socket partial-write local-fault slice，其次才是需要完整 reservation所有权设计的 quota／resident backpressure slice。
