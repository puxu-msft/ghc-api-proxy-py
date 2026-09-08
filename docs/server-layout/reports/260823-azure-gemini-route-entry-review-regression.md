# Azure / Gemini 路由入口评审 —— 回归风险与旧链对照

评审人：独立评审者（与另一位并行，未读其报告 `260823-azure-gemini-route-entry-review-gpt.md`，结论仅出自本人直接测量）。
时间：2026-08-23T06:45Z ～ 07:00Z（UTC）。
基线提交：`af40e9b0e480cfa86f9ddb15d8364c2f8842c532`。
评审对象：该提交之上的未提交改动，限于 `src/app/server/{inbound.py,routes/inference.py,routes/router.py,routes/table.py}` 与 `tests/int/test_pipeline_app.py`、`tests/unit/server/test_server_inbound.py`。附带纳入 `src/app/pipeline/request.py`（新增一个 `WireFormat` 成员），因为它是本次改动的组成部分，且本报告最重的一条发现出在那里。
最终测量时被评审 diff 的内容指纹：`git diff -- src/app/server tests/int/test_pipeline_app.py | sha256sum` = `0c660e71…3b80323d`（07:58:47Z 取）。**指纹对不上就说明工作树已经又动过，本报告的具体结论需要重测。**

技能加载说明：任务要求先调用 `my-skills:as-reviewer`，该技能在本机不存在（`~/.claude/skills/` 下无此名）。改为加载 `verifying-authoritative-claims` 与项目级 `project-review-principles`，本报告按二者的证据纪律撰写。

## 0. 评审期间被评审对象两次变动 —— 先读这一节

这不是背景，是读本报告的前提。

1. **06:45 我读到的实现，Gemini 用的是单条 catch-all `/v1beta/models/{model_and_method}`。** 我按任务第 3 项实测了它的吞噬范围，确认 `POST /v1beta/models/anything` 与 `POST /v1beta/models/gemini-pro`（无 `:method`）都被吞成 501。**约 06:52 实现者独立改成了三条显式模板**（`{model}:generateContent` / `{model}:streamGenerateContent` / `{model}:countTokens`），并补了两条测试。我重测后确认该问题已闭合，详见 §3。**任务第 3 项的原始发现已经不再成立，我不把它列为发现。**
2. **06:57 我跑目标测试集时，`test_the_azure_paths_are_not_mounted_under_the_openai_prefixes` 报 `assert 200 == 404` 失败；约 60 秒后同一断言在新进程里稳定复现为 404，全套 224 条通过。** 该测试当时新增的 docstring 自陈「A review reproduced exactly that by mounting the wrong template on a real app」——说明另一位评审当时正在共享主树上做受控变异。**判定：测量干扰，不是缺陷。** 依据是当前 `table.py` 三条 Azure 路由均无 `openai_prefixed=True`，`_BY_PATH` 中含 `deployments` 的键恰为三条无前缀模板，且两次直接探测均为 404。**但它有一条可行动的后果**：本次改动的最终门（全量回归 + Ruff + Pyright）必须在一棵没有并发变异的树上跑一次，否则绿或红都读不出意义。

## 1. 结论

**VERDICT：needs-fix。1 条 major，0 条 blocker。**

major 那条不在被点名的 6 个文件里，但由本次改动直接造成，且落在主产品路径 `/v1/messages` 上。

改动本身的主干是**正确且偏保守**的，三处结构性判断我逐条实测后予以确认（§2）。旧链对照下**没有发现「该做而漏了」的 Azure 行为**；Gemini 侧的空缺是用户明确批准的「留空」，但有几件旧链已有的东西需要登记而不是让它自然消失（§4）。

## 2. 回归面：三处改动的调用方是否都还成立

### 2.1 `build_context` 新增第 4 参数 —— 成立

调用点全集（`rg -n 'build_context' --type py`，覆盖 `src/` 与 `tests/`，含归档树排除）：

| 位置 | 传参形态 |
|---|---|
| `src/app/server/routes/inference.py:169` | 4 位置参数（唯一生产调用点） |
| `tests/int/recorded/record_cassette.py:57` | 2 参数 |
| `tests/int/test_recorded_upstream.py` × 5 | 2 参数 |
| `tests/unit/server/test_server_inbound.py` × 8 | 2～4 参数 |
| `tests/unit/pipeline/test_client_request_headers.py` × 2 | 2～3 参数 |
| `tests/unit/pipeline/test_attribution_stripping.py:198` | 3 参数 |

新参数带默认值 `None`，全部旧调用点形态不变。**归档链 `src/.archived/` 不含任何 `build_context` 调用**（`rg` 于归档树为空）。实测：目标测试集 224 条全绿。

`payload` 构造方式的改动（`deepcopy(dict(payload))` → 先建 `working` 再传）在 `model_from_path == ""` 时逐字等价，且 deepcopy 相对 stream 校验的先后次序未变。`original_payload=payload` 仍是调用方传入的那个 Mapping 本身，未被 `working["model"]` 触及——单测 `test_a_path_named_model_reaches_the_pipeline_without_reaching_the_record` 正面钉住了这一点。**这是本次改动最值得肯定的一处**：`copilot-api-js` 的 `src/routes/azure-openai/route.ts:29-43` 用整段注释论证的正是同一件事（「不要在快照之前改 body，否则 history 记的 original 已经是改过的值」），本实现用 `working` / `original_payload` 这对字段结构性地达到了同一效果，比参考实现的「显式 override 通道 + 要求下游按顺序应用」更难写错。

### 2.2 `_dispatch` 改读 ASGI scope 的 `route.path` —— 成立，且是净修复

**机制**（FastAPI 0.141.1 / Starlette 1.6.0，均为本仓 `.venv` 实测版本）：

- `fastapi/routing.py:1258`，`APIRoute.matches` 在 `match != Match.NONE` 时设 `child_scope["route"] = self`；
- `fastapi/routing.py:1799`，`_IncludedRouter.handle` 在走 effective-route 分支时再设一次 `scope["route"] = original_route`——**取的是原始 route 对象，因此 `.path` 是未加 prefix 的模板**。
- Starlette 的 `routing.py` 里没有任何 `scope["route"]` 赋值，这个键完全由 FastAPI 提供。

**三种挂载方式实测**（每次都在 `route_for_path` 上打桩记录实参）：

| 挂载方式 | 请求 URL | `route_for_path` 实际收到 | 结果 |
|---|---|---|---|
| `app.include_router(build_router())`（当前生产形态） | `/openai/deployments/gpt-model/embeddings` | `/openai/deployments/{deployment}/embeddings` | 200 |
| `app.include_router(build_router(), prefix="/proxy")` | `/proxy/openai/deployments/gpt-model/responses` | `/openai/deployments/{deployment}/responses` | 200 |
| `TestClient(app, root_path="/api")` | `/api/v1/messages` | `/v1/messages` | 200 |

**legacy 链路的 app 工厂不构成风险**：`rg -n 'route_for_path|routes.inference|from app.server.routes' src/.archived --type py` 为空——归档链自带 `APIRouter`，从不经过 `serve`，与本改动无接触面。

**净修复的部分**：`route_for_path("/api/v1/messages")` 返回 `None`（实测）。也就是说，改动之前那版 `route_for_path(request.url.path)` 在 uvicorn `--root-path /api` 或任何路径前缀反代下，会让**每一条**路由都掉进 `_dispatch` 的防御性分支答 404 "unknown endpoint"。考虑到项目的部署目标是 systemd 托管服务，这条修复是有实际价值的。把握程度：**足以据以行动**——三种形态各测一次，正样本（200 + 正确模板）与反样本（`route_for_path` 对带前缀 URL 返回 `None`）都取到了。

**关于退路 `request.url.path` 会不会静默给出错误答案**——任务点名要回答的问题，答案是**不会给出「另一条路由」，只会给出 `None`**：

- `_BY_PATH` 当前 17 个键，其中 11 个是字面路径、6 个是含 `{}` 的模板。退路喂进去的 URL 永远不含 `{}`，所以对 6 条模板路由只可能命中不到（→ 我们自己的 404 "unknown endpoint"，**并且会写一条 completion 日志**，与 FastAPI 的 `{"detail":"Not Found"}` 形状可区分），对 11 条字面路由则给出与模板完全相同的正确答案。
- 因此 `scope["route"]` 一旦在未来版本消失，失效形态是「Azure 与 Gemini 全线 404、其余照常」的**局部**退化，而不是错路由。这个结论对处置有直接影响：不需要为退路加防护，但**升级 FastAPI 时这 6 条模板路由是要重跑的判据**。
- `getattr(scope.get("route"), "path", url.path)` 这个写法把「router 没告诉我们」和「router 告诉我们了」压成同一条表达式，读起来像是在给 `None` 兜底，实际也给了「有 route 对象但没有 `path` 属性」兜底。今天两种都不可达。归为 nit（§5.6）。

### 2.3 `openai_prefixed` / `expanded_paths` 重构 —— 行为保持，机械核对过

把 HEAD 版 `table.py` 与工作树版分别 import 成两个模块，逐键对比 `_BY_PATH`：

```
HEAD keys: 11   WORK keys: 17
removed : []
added   : ['/openai/deployments/{deployment}/chat/completions',
           '/openai/deployments/{deployment}/embeddings',
           '/openai/deployments/{deployment}/responses',
           '/v1beta/models/{model}:countTokens',
           '/v1beta/models/{model}:generateContent',
           '/v1beta/models/{model}:streamGenerateContent']
changed : []
```

**纯增量，0 删除、0 变更。** 两处判据替换（`wire_format.value.startswith("openai-")` → `openai_prefixed`，`wire_format is not ANTHROPIC_MESSAGES` → `openai_prefixed`）在当前路由集上与旧判据同解，因为三条 OpenAI 路由恰好全部标了 `openai_prefixed=True`，而新增的 Azure 三条虽然携带 `OPENAI_*` wire format 却标了 `False`——这正是旧判据会出错的地方，显式化是对的。

`_BY_PATH` 的填充从「先无条件 `[]=` 再 `setdefault`」改成「统一 `setdefault`」，语义由「后者覆盖」变为「前者优先」。当前 `ROUTES` 无重复路径，因此无差异；这一点由上面的 `changed: []` 覆盖。

另外实测了一条不变量：`build_router()` 注册的 17 条 inference 路由，`route_for_path` 全部解析得到（`unresolvable: []`）。实现者在评审期间自行补上了 `test_what_is_mounted_and_what_can_be_looked_up_are_the_same_set` 钉住它，我原本要提的建议已被闭合。

## 3. `/v1beta/...` 的吞噬范围 —— 已闭合（实发请求验证）

任务点名的这条问题**在评审期间被实现者独立修掉了**。当前形态实测（每条都是真发 HTTP，`follow_redirects=False`，并在 `route_for_path` 上打桩确认是否进入我们的 dispatcher）：

| 请求 | 状态码 | 是否进入 `_dispatch` | 匹配到的模板 |
|---|---|---|---|
| `POST /v1beta/models/gemini-pro:generateContent` | 501 | 是 | `{model}:generateContent` |
| `POST /v1beta/models/gemini-pro:streamGenerateContent` | 501 | 是 | `{model}:streamGenerateContent` |
| `POST /v1beta/models/gemini-pro:countTokens` | 501 | 是 | `{model}:countTokens` |
| `POST /v1beta/models/vendor:family:generateContent` | 501 | 是 | `{model}:generateContent`（model = `vendor:family`） |
| `POST /v1beta/models/gemini-pro` | 404 | **否** | —— |
| `POST /v1beta/models/anything` | 404 | **否** | —— |
| `POST /v1beta/models/gemini-pro:embedContent` | 404 | **否** | —— |
| `POST /v1beta/models/gemini-pro:GenerateContent`（大小写） | 404 | **否** | —— |
| `POST /v1beta/models/:generateContent`（空 model） | 404 | **否** | —— |
| `POST /v1beta/models/gemini-pro%3AgenerateContent` | 501 | 是 | `{model}:generateContent` |
| `GET /v1beta/models/gemini-pro:generateContent` | 405 | **否** | —— |
| `POST /v1beta/models/gemini-pro:generateContent/` | 307 | 否（redirect_slashes） | —— |

**没有遮住任何已有路由。** `/v1beta` 是全表独占前缀，`_BY_PATH` 全部 17 个键中无第二条以 `/v1beta` 起首；Azure 的 `/openai/deployments/{d}/…` 是 4～5 段，与 `/openai/v1/…` 的 3～4 段在第二段字面上就分开，实测 `/v1/openai/deployments/…` 与 `/openai/v1/openai/deployments/…` 均为 404。

`vendor:family:generateContent` → model `vendor:family` 这一条值得单独说：Starlette 把 `{model}` 编成贪婪的 `[^/]+`，回溯后与字面 `:generateContent` 对齐，效果等同于旧链 `src/app/protocols/gemini.py:14` 的 `rpartition(":")`，也等同于 `copilot-api-js/src/routes/gemini/route.ts:30-33` 特意用 `lastIndexOf` 而非 `indexOf` 的理由（其注释明写「Model ids may legitimately contain `:` (e.g. vendor:family:variant)」）。**三方一致，这个语义是对的。** 把握程度：足以据以行动，正反样本都取到了。

## 4. 旧链对照：哪些是「该做而漏了」，哪些是「旧链的缺陷不该照抄」

旧链的原件在 `src/.archived/app/routes/azure.py`、`src/.archived/app/routes/gemini.py`、`src/.archived/app/protocols/azure.py`，2026-08-22 由 `2248a69` 整体移出源码树。

### 4.1 Azure：**没有发现该做而漏了的行为**

| 旧链在做 | 新链 | 判定 |
|---|---|---|
| `adapt_azure_payload`：deepcopy 出 original 与 wire 两份，`wire["model"] = deployment` | `working` / `original_payload` 一对，语义逐字相同，另加 `.strip()` | **平价**，且 `.strip()` 是改进（实测 `/openai/deployments/gpt-model%20/responses` 现在发出去的 model 是 `gpt-model`） |
| body 里的 `model` 被无条件覆盖 | 同 | **平价**。`copilot-api-js` 注释 `route.ts:9-11` 亦确认「the path segment is authoritative and any body `model` field is ignored」 |
| `/openai/deployments` 前缀，三条子路由，embeddings 不流式 | 三条完全限定模板，embeddings `streamable=False` | **平价** |
| `apply_approval_guard(...)` | 无 | **旧链的东西，不该照抄**。`api.md:20` 把 `/api/approval/*` 判为 ~~暂不支持~~，`ops.py:7` 亦明写审批「deliberately not wired」，且全新链无任何路由施加审批。这不是 Azure 专属缺口 |
| `start_protocol_history` / `finalize_protocol_history` / `history_stream` | 无 | **缺口，但不是本切片的**。`rg -ln 'start_protocol_history\|history_stream' src/app` 为空——新链整体不写 history，`status.md:45` 已登记 `/history/api/*`、`/history/ws` 为「追认但无人服务」。Azure 不写 history 与 `/v1/messages` 不写 history 是同一件事 |
| `ChatCompletionRequest.model_validate(guarded)` 等 pydantic 入参校验 | 无（新链透传 dict） | **架构差异，非本切片**。三条 Azure 路径与对应的无前缀路径走完全同一条管线，差异只在 model 来源 |
| `_response` 原样透传上游 content-type 与状态码 | 走新链的块级交付 | **架构差异，按设计** |

`table.py` 里那句注释「The old `adapt_azure_payload` performed no Azure-specific reshaping beyond copying the body and setting `model` from that segment」——我逐行核对了 `src/.archived/app/protocols/azure.py:12-20`，**这句话是准确的**。

### 4.2 Gemini：留空是用户批准的，但有四件旧链已有的东西需要登记

用户裁定「如果实际处理尚未实现，可以留空」，所以 501 本身不是发现。以下是「不得静默缩小范围」意义上应当登记、而当前无处可查的东西：

1. **旧链的 Gemini 实现有相当一部分仍活在 `src/app/` 里，没跟着归档走。** `src/app/protocols/gemini.py`（`parse_model_with_method`、`gemini_to_openai`、`openai_to_gemini`）、`src/app/models/gemini.py`、`src/app/tokenization/estimators.py:78` 的 `estimate_gemini_input`、以及活的 `tests/unit/protocols/test_gemini_protocol.py`，全部在活树里，且 `src/app/protocols/__init__.py:1` 还把 `parse_model_with_method` 对外导出。**当前无任何生产代码引用它们**（`rg` 确认）。下一位实现 Gemini 的人如果不知道这些在，很可能会重写一遍 `parse_model_with_method`。→ §5.4
2. **方法白名单现在有两份独立表达。** `table.py` 里三条模板字面量，与 `src/app/protocols/gemini.py:6` 的 `GEMINI_METHODS = frozenset({...})`，内容相同、来源无关。这正是项目 `one-reply-fact-one-answer` 那条复查原则要抓的形状。→ §5.4
3. **旧链的错误体是 Gemini 信封**（`{"error": {"code", "message", "status"}}`，`gemini.py:112-124`、`:162-174`），`copilot-api-js` 也是（`route.ts:34-43`、`:57-66`）。新链的 501 用的是本代理的通用信封 `{"error": {"message": ...}}`。→ §5.2
4. **`countTokens` 旧链是本地估算**（`estimate_gemini_input`，不打上游），与新链 `/v1/messages/count_tokens` 的 `provider(local)` 那一档是同一类事。501 是对的，但「将来它该走本地估算而不是上游」这条知识只存在于归档代码里。→ §5.4

## 5. 逐条发现

### 5.1 [major] 新增的 `WireFormat.GEMINI_GENERATE_CONTENT` 让 `model@gemini-generate-content` 从 400 变成 502，并泄出 `KeyError` 的枚举 repr

把握程度：**高，已复现**。

`src/app/pipeline/request.py` 给 `WireFormat` 加了 `GEMINI_GENERATE_CONTENT`，但 `ENDPOINT_FORMATS` / `FORMAT_ENDPOINTS`（同文件 `:32-43`）没有、也不可能有对应条目。而 `src/app/pipeline/routing.py:54-68` 的 `split_format_suffix` 用 `WireFormat(suffix)` 判断「这个 `@format` 后缀认不认识」，`decide_route`（`:91`）随后无保护地做 `FORMAT_ENDPOINTS[explicit_format]`。

于是枚举里多出一个「认识但没有 endpoint」的值，`split_format_suffix` 的 docstring 那句「An unrecognised format after `@` is an error rather than part of the model name」不再覆盖全部情况。

实测（`POST /v1/messages`，主产品路径）：

| `model` | 改动前后 | 状态码 | 响应体 |
|---|---|---|---|
| `claude-model@gemini-generate-content` | **本次新增** | **502** | `{"error":{"type":"KeyError","message":"<WireFormat.GEMINI_GENERATE_CONTENT: 'gemini-generate-content'>"}}` |
| `claude-model@nope` | 不变 | 400 | `{"error":{"type":"RoutingError","message":"unknown target format 'nope' in 'claude-model@nope'"}}` |
| `claude-model@openai-responses` | 不变 | 400 | `EndpointNotSupported` |

这条同时踩了两项项目纪律：`never-swallow-errors` 的反面（错误没被吞，但是以未处理内部异常的形态到达客户端），以及 `explanation-does-not-belong-on-a-surface-that-is-read-as-a-promise`（客户端拿到的是 Python 枚举的 repr，读者据此做不了任何事）。

**建议**（择一，我倾向第一个）：

- 在 `split_format_suffix` 里把「不在 `FORMAT_ENDPOINTS` 里」也算作 unrecognised，与未知后缀走同一条 `RoutingError`。判据放在一处、由一张表决定，且随 `FORMAT_ENDPOINTS` 自动演进，`implemented=False` 的新格式将来加多少个都不用再动它。
- 或在 `decide_route` 的两个 `FORMAT_ENDPOINTS[...]` 取值处改用带诊断的显式失败。

配一条测试：`model@<某个已定义但无 endpoint 的 WireFormat>` 应得 400 而不是 5xx。**注意别把断言钉在 `gemini-generate-content` 这个名字上**——它一旦被实现就会进 `FORMAT_ENDPOINTS`，测试会静默失去分辨力；钉「枚举里存在而 `FORMAT_ENDPOINTS` 里不存在的成员集合」这个结构更稳。

### 5.2 [minor] 501 的响应体把路由模板原样吐给客户端，且不是 Gemini 信封

把握程度：中高（前半实测，后半是对 Gemini 客户端行为的推断，未实测 SDK）。

`inference.py:154` 返回 `f"{route.path} is not implemented yet"`，客户端实际收到的是：

```
{"error":{"message":"/v1beta/models/{model}:generateContent is not implemented yet"}}
```

两个问题。一是那对花括号是本仓路由表的内部拼写，客户端读到 `{model}` 什么也做不了；二是 Gemini 客户端解析的是 `error.code` / `error.message` / `error.status`，旧链（`src/.archived/app/routes/gemini.py:112-124`）与 `copilot-api-js`（`route.ts:34-43`）都按那个形状答。

建议：消息里换成 `request.url.path`，或干脆一句不含模板的定值。信封形状是否要按 inbound format 分化，属于对外契约，倾向登记到 `deferred.md` 交由用户裁，而不是本切片顺手改。

### 5.3 [minor] 三条 Gemini 路由上的 `streamable` / `count_tokens` / `model_from_path` 当前不可达，且 `streamable` 编码了一个对 Gemini 不成立的机制

把握程度：高（不可达性实测；「机制不成立」由 `build_context` 的实现直接可读）。

`implemented=False` 的判定在 `_dispatch:150` 就返回，而 `build_context` 在 `:169` 才被调用，所以这三条路由上的 `model_from_path="model"`、`streamable=False/True` 全都不会被执行到。`count_tokens` 是唯一有部分效果的（`trace.count_tokens` 在 `:148` 早于 501 分支被赋值），实测日志行干净、没有伪造出 token 数，无害。

真正值得记的是 `streamable`：`build_context:51` 读的是 `payload.get("stream", False)`，而 **Gemini 的请求体里没有 `stream` 字段**——是否流式由路径方法段决定（`streamGenerateContent`）。所以这三个 `streamable` 值今天不可达、将来也不会以现在这个机制生效。留在那里的后果是它读起来像「已经决定好了」，下一位实现者会以为接线好了。

建议：要么删掉这三条路由上的 `streamable`（保留 `count_tokens`，它是对的），要么在注释里写明「Gemini 的流式由方法段决定，`route.streamable` 对它不适用，此处的值是占位」。我倾向删——`explanation-…` 那条原则的反面同样成立：一个不可行动的配置值比没有更糟。

### 5.4 [minor] Gemini 留空的知识没有落点：活树里的旧实现、双份方法白名单、countTokens 走本地估算

把握程度：高（全部由 `rg` 与文件内容直接确认）。

见 §4.2 的四点。这是「不得静默缩小范围」的登记义务，不是代码缺陷。

建议：在 `.dev/docs/server-layout/deferred.md`（若无则新建）记一条 Gemini 条目，点名：
- `src/app/protocols/gemini.py`（含 `parse_model_with_method`、`GEMINI_METHODS`、双向翻译）、`src/app/models/gemini.py`、`estimate_gemini_input`、`tests/unit/protocols/test_gemini_protocol.py` 仍在活树、无人引用，实现时优先复用；
- `table.py` 的三条模板与 `GEMINI_METHODS` 是同一事实的两份表达，实现时择一为准；
- `countTokens` 旧链走本地估算而非上游；
- 错误信封形状待裁（§5.2）。

### 5.5 [minor] `src/.archived/README.md:21` 已经不成立

把握程度：高。

原文：「`api.md` ratifies Azure, Gemini, `/history/api/*`, `/history/ws`, `/api/status` and `/api/config`. **The live chain serves none of them**」。

现状：`/api/status` 与 `/api/config` 自 `7525f76` 起活在 `ops.py:30` / `:88`；本次改动后 Azure 三条真正被服务、Gemini 三条被路由并明确答 501。这句话现在同时错在三处。`.dev/docs/server-layout/status.md:45`（仍写「收窄为四个：Azure、Gemini、`/history/api/*`、`/history/ws`」）与 `decisions.md:60-61`（「已追认，倾向迁移」）同样需要随本切片更新。

建议：随本次提交一并改，属于 `sync-live-docs-timely`。归档 README 里那段「what is unfinished」的缺口清单收窄到 `/history/api/*` 与 `/history/ws` 两条即可。

### 5.6 [nit] `route_for_path` docstring 把读 scope 的动作记在 `serve` 名下

`table.py:77` 写「`serve` reads it off the ASGI scope」。实际读它的是 `_dispatch:142`，`serve` 只是它的调用者。同一句 docstring 还断言了 `route_for_path` 的调用方式（「Given the **template** … not its URL」），而 `record_cassette.py:54` 与 `test_recorded_upstream.py` 里的五处调用传的都是字面 URL——对 11 条字面路由两者恰好同形，所以无害，但这句绝对陈述比事实强。

建议：改成「`_dispatch` reads it off the ASGI scope」，并把那句绝对陈述放宽成「含参数的路由必须传模板」。

### 5.7 [nit] `getattr(request.scope.get("route"), "path", request.url.path)` 把两种缺失压成一条表达式

`inference.py:142`。今天两种缺失都不可达（§2.2），退化形态也只是局部 404 而非错路由，所以不构成风险。但这个写法读起来像在给 `None` 兜底，实际连「route 对象没有 `path` 属性」也一起兜了。若想让它更可读，`route = request.scope.get("route")` 后显式 `route.path if route is not None else request.url.path` 是等价的。纯风格，可不动。

## 6. 我验证过、判定为没问题的事（避免重复劳动）

- Azure 三条路径的端到端行为：`/openai/deployments/{model}/{chat/completions,responses,embeddings}` 分别打到上游 `/chat/completions`、`/responses`、`/embeddings`，请求体 `model` 为 path 段（实测发出的字节）。
- 编码与空白 deployment：`%20` → 400（说明 `build_context` 里那条「segment is empty」守卫**是 HTTP 可达的**，不是只有单测能进的死分支）；`a%2Fb` → 404；`gpt-model%20` → 200 且 model 被 strip。
- Azure 路径不被 OpenAI 前缀二次挂载：`/v1/openai/deployments/…`、`/openai/v1/openai/deployments/…` 均 404，`_BY_PATH` 中含 `deployments` 的键恰好三条。
- `expanded_paths` 的两个消费者一致：注册的 17 条 inference 路由全部可经 `route_for_path` 反查（`unresolvable: []`）。
- `WireFormat` 新成员对既有分派逻辑无影响：`registry.py`、`delivery_policy.py`、`driver.py`、`reply.py` 等处全部是 `is <具体成员>` 的正向比较，没有穷举 match 会因新增成员而漏分支。**唯一的例外就是 §5.1 的 `FORMAT_ENDPOINTS` 字典下标。**
- Ruff `check src tests` 全绿。Pyright 21 个错误全部在 `tests/unit/upstream/test_stream_cap.py`，该文件由 `8703cad` 提交、本次未修改，属**既有**问题，与本改动无关。
- 目标测试集（`tests/unit/server` + `tests/int/test_pipeline_app.py` + 两个相关 unit 文件）224～286 条全绿（区间是因为测试文件在评审期间被追加过）。

## 7. 给主会话的处置建议

1. **先修 §5.1**，它是唯一需要改生产代码的。修在 `routing.py` / `request.py`，不在被点名的 6 个文件里。
2. §5.3、§5.6、§5.7 可与 §5.1 合并成一次收口，都是几行。
3. §5.2 的信封形状与 §5.4 的登记，建议写进 `deferred.md` 而不是本切片做。§5.2 前半（别把 `{model}` 吐给客户端）可以顺手改。
4. §5.5 的文档同步随本次提交做。
5. **最终门必须在一棵没有并发变异的树上跑**，理由见 §0 第 2 点。
