# 评审：count_tokens 共享请求管道（`shape_request`）

- 评审对象：`/home/xp/src/ghc-api-proxy-py` 工作树未提交改动中属于本次任务的部分
- 评审时间：2026-08-20
- 评审者：leaf executor（只读评审 + `/tmp` 一次性探针，未修改仓库任何文件）
- 基线：`git diff` 对比 `HEAD`（`git show HEAD:src/app/server/handler.py` 用于逐行比对）

## 结论

**VERDICT: needs-fix。** 契约反转的主论证成立，`shape_request` 抽取对 `handle()` 是严格等价的，两条变异结论都复核通过。但新判据 `route.target_format is WireFormat.ANTHROPIC_MESSAGES` 比它想表达的条件更宽：它把「上游没有计数器」和「这个请求根本发不出去」合并处理了，于是旧行为的理由在 **`/embeddings`、`/chat/completions` 这类没有 outbound translator 的目标格式上仍然成立**，而现在这类请求返回 200。另有一条 operator 可选配置下的 400→503 回归，以及一处代码注释声称的缓解手段实际无人读取。

计数：blocker=0，major=2，minor=4。

---

## 已核实为正确的部分（先说清楚哪些不必再查）

以下每条都做了独立验证，不是照单全收：

1. **`shape_request` 对 `handle()` 严格等价。** 逐行比对 `git show HEAD:src/app/server/handler.py`（68-83 行）与现 `src/app/server/handler.py:79-98`：`provider` 取得方式、`decide_route` 四个入参、`apply_route`、`on_routed` 回调位置（仍在 `apply_route` 之后、`fix_anthropic_request` 之前）、`fix_anthropic_request` 的 `inbound_format is ANTHROPIC_MESSAGES` 触发条件——顺序与条件一字未动，只有注释重排。`handle()` 里 translation 与 `payload["model"]` 赋值仍在函数体内，位置不变。**权重：可直接据此行动**（逐行比对 + `tests/http/test_pipeline_app.py` 70 项全绿）。

2. **count 路径上 `context.payload["model"] = route.model_id` 排在 `shape_request` 之后没有影响。** `fix_anthropic_request` 读的是 `context_management` 与 `messages`，`normalize_context_management` / `sanitize_empty_thinking` / `destack_content` 全链路都不读 `model`（`src/app/pipeline/anthropic_request_hook.py:36-90`）。且这与 `handle()` 中的相对顺序一致（那边也是先 fix 后赋 model）。**权重：可直接据此行动**（读完全部被调用函数体）。

3. **`mute-model` 这类完全不可路由的模型仍然 400。** 走的是 `decide_route` 的 `CapabilityMissing`（`src/app/pipeline/routing.py:79-80`），在任何 counter 被选中之前，与 `upstream_counts` 无关。`tests/http/test_pipeline_app.py:628` 的 `test_count_tokens_refuses_a_model_without_the_messages_capability` 未改且绿。只有 unknown endpoints 的模型同理落到 `_first_supported` 的 `EndpointNotSupported`，也是 400。

4. **不存在残留的 `EndpointNotSupported` 触发面。** 当 `target_format is ANTHROPIC_MESSAGES` 时，`decide_route` 的两条分支都保证 `descriptor.supports(ANTHROPIC_MESSAGES)`，因此 `provider.count_tokens` 的 `require_endpoint`（`src/app/model_provider/github_copilot.py:198`）在被调用时必定通过。判据用 `target_format` 而不是 `endpoint`，二者经 `ENDPOINT_FORMATS` 一一对应，等价。

5. **没有遗漏的调用点。** `rg -n "decide_route|fix_anthropic_request|apply_route" src/` 在新管道上只剩 `handler.py` 三处，全部经 `shape_request`。`src/app/anthropic/client.py:121,204` 是 legacy 链路自己的 `RouteDecision`/`_decide_route`，与本次抽取无关，不应牵动。

6. **两条变异结论均复核通过**（用 monkeypatch 在 `/tmp/probe_mutations.py` 做，未改动仓库源码）：
   - 变异 (a)：强制 `decide_route` 返回 `target_format=ANTHROPIC_MESSAGES`（等价于翻译路径仍传 upstream counter）→ 实测抛 `EndpointNotSupported: model 'claude-model' does not advertise /v1/messages on ghc` → `test_a_translated_route_is_counted_locally_rather_than_refused` 断言的 200/`estimated` 必红。**确认有分辨力。**
   - 变异 (b)：`monkeypatch.setattr(handler, "fix_anthropic_request", no-op)` → 计数 body 实测保留 `{"edits": None}`，与断言 `{"edits": []}` 不符 → `test_the_counted_body_is_the_repaired_one` 必红。**确认有分辨力，且确认 `attempt.prepare` 订阅者确实不改写 `context_management`**——用 `context_management` 替换空文本块这一改动是对的。

7. **Ruff / Pyright 干净**：`uv run ruff check src/app/server/handler.py tests/unit/test_builtin_subscribers.py tests/http/test_pipeline_app.py` → All checks passed；`uv run pyright src/app/server/handler.py tests/unit/test_builtin_subscribers.py` → 0 errors。未运行 `ruff format`（项目禁止）。

---

## Major

### M1. 判据过宽：目标格式没有 outbound translator 时，`/v1/messages` 400 而 count 返回 200

- 位置：`src/app/server/handler.py:173`（`upstream_counts = route.target_format is WireFormat.ANTHROPIC_MESSAGES`）
- 具体失败输入：`POST /v1/messages/count_tokens {"model": "embed-model", "messages": [{"role":"user","content":"hi"}]}`（`embed-model` 已在 `tests/http/test_pipeline_app.py:55` 的 `CATALOG` 里，`supported_endpoints: ["/embeddings"]`）
- 具体错误结果（实测，`/tmp/probe_count.py`，用本文件自己的 `make_client`）：

```
MESSAGES 400 {"error":{"type":"TranslatorNotFound","message":"no translator registered as outbound.to-openai-embeddings"}}
COUNT    200 {"input_tokens":6,"estimated":true}
```

- 为什么这是缺陷：本次改动的全部依据是「模型是够得着的，够不着的只是计数器」。对 `gpt-model` 成立（`tests/http/test_pipeline_app.py:157` 证明 `/v1/messages` 经翻译 200）；对 `embed-model` **不成立**——`src/app/pipeline/translation_driver/registry.py:137-141` 只注册了 `ANTHROPIC_MESSAGES` 与 `OPENAI_RESPONSES` 两个方向，`OPENAI_EMBEDDINGS` 与 `OPENAI_CHAT_COMPLETIONS` 没有 outbound translator，请求真的发不出去。此时旧测试的原话「a count for a model this request can never reach」**逐字仍然正确**，而新代码给出了 200 + 一个 estimate。这正是被推翻的那条理由所要防的场景，只是换了一类模型。
- 影响范围评估：GitHub Copilot 目录里是否真的存在「只有 `/embeddings` 或只有 `/chat/completions`」的模型，我没有实测上游目录（`refs/` 与 `docs/` 未给出快照），所以我不声称它在生产上一定被触发。但判据的正确性不应该依赖「上游目前恰好没有这种模型」——`decide_route` 的 `_FALLBACK_ORDER`（`src/app/pipeline/routing.py:25-30`）明确把这两种格式列为可路由目标，代码是按它们存在写的。**权重：判据缺陷本身是强证据（已实测复现）；「生产是否命中」只是待查，不作为降级理由。**
- 建议（供裁决，不是我能自己定的）：把 `upstream_counts` 的判定拆成两问，而不是一问。
  - 问一：上游有没有计数器 → 现有的 `target_format is ANTHROPIC_MESSAGES`。
  - 问二：这个请求本身发不发得出去 → 目标格式有没有注册 outbound translator。答否时应当继续 400（`TranslatorNotFound` 或 `EndpointNotSupported`），因为此时「量一个永远发不出的请求」这句批评仍然成立。
  - `chain.translators` 已经在 `Chain` 上，`shape_request` 拿得到；代价是加一个查询和一条测试，很小。
- 对应测试缺口：目前没有任何测试固定 `embed-model` 在 count endpoint 上的行为——无论裁决是 200 还是 400，都应该有一条。

### M2. `providers: ["ghc"]` 配置下 400 变 503，且错误消息指控了一个不存在的配置错误；`count_tokens_upstream_skipped` 目前无人读取

- 位置：`src/app/server/handler.py:170`（注释）、`:175-177`（写 extras）、`:186`（`upstream=ask_upstream if upstream_counts else None`）；`src/app/pipeline/count_tokens.py:56-58`
- 具体失败输入：配置 `inbound.anthropic_count_tokens.providers: ["ghc"]`（schema 允许，`src/app/config/schema.py:68` 只是默认值给了 `["ghc","local"]`），然后 `POST /v1/messages/count_tokens {"model": "gpt-model", ...}`
- 具体错误结果（实测，`/tmp/probe_count.py`）：

```
GHC-ONLY 503 {"error":{"type":"CountTokensUnavailable","message":"no token counter succeeded: ghc:unconfigured"}}
```

  改动前同一输入是 `400 EndpointNotSupported`。日志行同样落成 `H1 503 POST /v1/messages/count_tokens gpt-model 1ms: no token counter succeeded: ghc:unconfigured`。
- 为什么这是缺陷：
  1. 503 的语义是「配置的计数器都失败了」，`error_status` 的注释（`src/app/server/handler.py:247-250`）也是这么写的。但这里没有任何计数器失败过——是路由决定不去问。运维读到的字面结论是「我的 `ghc` 没配好」，而 `ghc` 配得好好的。
  2. 注释 `handler.py:170` 明确写「`count_tokens_upstream_skipped` carries the reason, and is the one to read」。**目前没有任何读者。** `rg -n "extras" src/` 的全部结果里，`count_tokens_provider` / `count_tokens_attempts` / `count_tokens_upstream_skipped` 三个键都只有写、没有读；`src/app/observability/request_log.py` 与 `logging.py` 都不消费 `context.extras`。所以运维实际能看到的只有那句 `ghc:unconfigured`，而注释承诺的更正记录停在内存里。这不是「以后再接线」的问题，而是注释现在就在陈述一件不成立的事，下一个维护者会据此认为缓解已经到位。
- 我对你在问题 4 里那个取舍的判断：**「复用 `upstream=None`、不动 `count_tokens()`」这一半是对的**——`count_tokens.py` 的模块契约是共享的，为一个调用点改它不划算，而且 `None` 确实就是「这个 counter 服务不了这次请求」的既有语义。**「用 extras 承载真实原因」这一半目前只完成了一半**：记录写下了，但没有出口。两个成本都不大的补法（任选，或都不做但把注释改成实话）：
  - 在 `src/app/server/pipeline_app.py:214` 之后，count 成功分支里把 `context.extras.get("count_tokens_upstream_skipped")` 放进 `trace.detail`，让它上到请求行——这会改日志行外观，属于需要你裁决的产品面。
  - 或者不碰 extras，只把 `handler.py:170` 那句「is the one to read」改成如实描述（「记录在 extras 里，目前尚无展示面」），并把 `providers: ["ghc"]` 的 503 单独处理：`upstream_counts` 为假且 `providers` 里没有 `local` 时直接抛一个说人话的错误。
- 对应测试缺口：`providers: ["ghc"]` + 翻译路径这条新行为没有任何测试；它是本次改动唯一一处状态码从 4xx 变 5xx 的地方。

---

## Minor

### m1. 文档把「未改的东西」写成了本次共享的一部分

- 位置：`docs/2604-rewrite/tokenization.md:15`
- 原文：「共用 `handler.shape_request()`：路由、`fix_anthropic_request`、以及 `attempt.prepare` 订阅者。」
- 事实：`attempt.prepare` 订阅者循环在 `src/app/server/handler.py:147-149`，在 `shape_request` **之外**；而且 `git show HEAD:src/app/server/handler.py`（141-145 行）显示它在本次改动**之前就已经**存在于 count 路径上（连同那条「Measured 2026-08-20」的注释）。本次新增的共享项只有路由 + `fix_anthropic_request`。
- 后果：读者会以为订阅者共享是这次带来的，从而误判改动的风险面；也会以为 `shape_request` 里跑了 `await`，而它是同步函数。
- 建议改法：把订阅者单列一句，标明「早于本次改动即已共享」。

### m2. 文档对 `ProviderError` 规则现状的描述偏轻

- 位置：`docs/2604-rewrite/tokenization.md:23`
- 原文：「只是不再有人在翻译路径上去触发它。」
- 事实：在 `handle_count_tokens` 这个调用点上，`provider.count_tokens` 抛 `ProviderError` 的两条路径（`UnknownModel`、`require_endpoint` 的 `EndpointNotSupported`）现在**全部不可达**——`decide_route` 在更早的地方就把 unknown / capability-missing / endpoint-unsupported 全挡掉了（见上文「已核实 4」）。不只是翻译路径不触发，是这个调用点整体不触发。规则本身仍对其他调用者与未来 provider 有意义，说法应当准确到这一层。
- 注意：`raise_for_status()` 产生的 `httpx.HTTPStatusError` 不是 `ProviderError`，走 `except Exception` 降级到 local——这条没变，`test_count_tokens_falls_back_to_the_local_estimate` 仍然覆盖。

### m3. 新测试 docstring 里「this very endpoint」指代含混

- 位置：`tests/http/test_pipeline_app.py:596`
- 原文：「`test_anthropic_request_for_a_responses_model_is_translated` sends `gpt-model` a Messages body over this very endpoint and gets 200」
- 事实：被引的那条测试 POST 的是 `/v1/messages`（`tests/http/test_pipeline_app.py:160`），不是本测试所在的 `/v1/messages/count_tokens`。「this very endpoint」在一份讨论两个 URL 之差的 docstring 里会被读成同一个 URL，而论证恰恰依赖于「另一个 URL 上同一个模型能通」。
- 建议：写成「over `/v1/messages`, the request this count is about」。

### m4. 「已知无关失败」的归因在当前树上不再成立

- 你提示 `tests/integration/test_standalone_process.py::test_a_half_sent_request_holds_the_drain_until_the_operator_escalates` 属并行会话在途改动而失败。**独立复核：在当前工作树状态下它连续 4 次全绿**（`uv run pytest <nodeid> -q`，5.9s / 5.94s / 6.10s / 6.20s / 5.99s，无 flake）。
- 归因的**方向**是对的：该测试的 diff（新增 `/swallow` 路由、signal 前先确认 handler 已在等待）与 `src/app/lifecycle/*`、`cli.py`、`pipeline_app.py` 的改动同属 graceful-shutdown 议题，和 count_tokens 无任何交集。但「它当前失败」这个事实已经过期——并行会话大概率已经修好。
- 处置建议：不要把这条 caveat 带进后续的 squash 说明或交接件，否则会变成一条无法复现的传闻。若要保留，改成「该测试属并行会话议题，评审时点已绿」。

---

## 未展开但记下的事

- `handle_count_tokens` 不向 `shape_request` 传 `on_routed`，所以 count 请求在 footer 上直到应答前都没有 model（`src/app/server/pipeline_app.py:225-226` 事后补 `trace.model`）。这是改动前就有的行为，本次未改，不算发现；但既然 `shape_request` 现在把回调参数摆在明面上，接上它是一处几乎零成本的改善——留给你裁决，我不主张现在做。
- 计数 body 现在会经过 `destack_content` 的 `assistant_message_layout` 变形（可能插入合成文本块），因此同一份 body 的估算值与改动前不同。这是「量真正会发出去的那个 body」的直接后果，符合本次意图，不是缺陷；只是若之后 calibration 出现系统性偏移，这里是第一个该查的地方。

## 复现材料

两个探针都在 `/tmp`，仓库未被修改：

- `/tmp/probe_count.py` —— M1、M2 的实测（`uv run pytest /tmp/probe_count.py -q -s -c pyproject.toml --rootdir=.`，在仓库根目录运行）
- `/tmp/probe_mutations.py` —— 两条变异的复核（同上命令）
