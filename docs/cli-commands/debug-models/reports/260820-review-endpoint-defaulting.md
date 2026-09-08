# 评审报告：`883b104` 端点缺省填补 与 `3bcf14c` `--json` 形状开关

- 日期：2026-08-20
- 评审对象：`883b104 fix(model-provider): serve the models whose endpoint the catalog leaves unstated`、`3bcf14c feat(cli): drop the provider wrapper from --json when --provider named one`
- 不在范围：`a46eb8d`（已过两轮评审）；两个 commit 之间并行会话的其他提交；工作树里未提交的中间态改动（`src/app/pipeline/translation_driver/*`、`src/app/server/handler.py`、`src/app/lifecycle/*`、`src/app/cli.py` 的 shutdown 报告段等）。
- 核对过：被评审的 5 个文件（`src/app/debug/models.py`、`src/app/model_provider/{__init__,types,github_copilot}.py`、`src/app/cli.py` 的 `debug_models`、两个测试文件）在当前工作树中与 `HEAD` 一致，`git diff HEAD` 对这些区域为空，因此本报告读到的字节就是被评审的字节。`src/app/cli.py` 确有同伴的未提交改动，但全部落在 `report_shutdown`，与本次无关。

**结论：needs-fix。blocker 0 条，major 2 条，minor 5 条，nit 3 条。**

---

## 验证方式与证据强度

除静态阅读外，跑了三组只读探针（未修改任何仓库文件，脚本走 stdin heredoc）：

1. `resolve_endpoints` 对 8 类输入 × 3 类 `model_type` 的真值表；
2. `build_rows` 对四种 `supported_endpoints` 形态的行输出与 `render_text` 全文；
3. 用手工 `ModelDescriptor` 驱动 `decide_route` + `default_registry()`，走通「Anthropic Messages 入站 → 被填补端点的模型」这条真实调用链。

外加 `uv run ruff check`（5 个文件全绿）与 `uv run pytest tests/unit/test_debug_models.py tests/unit/test_model_provider.py`（64 passed）。

**未做变异验证**：工作树带着并行会话的未提交改动，在共享 checkout 上把源码改坏再改回来有丢失同伴工作的实际风险，不值当。因此下文关于「测试有没有分辨力」的判断是**读代码得出的**，权重为「足以作为改进建议，不足以作为『这条测试一定不红』的断言」。凡是探针跑出来的事实（第 1、2、4 条）权重为**足以直接据以行动**。

---

## Major

### M1 — 非 list 的 `supported_endpoints` 也会被填上默认端点，与函数自己的文档相反

**位置**：`src/app/model_provider/types.py:113-124`（判定），`src/app/model_provider/github_copilot.py:114-117`（路由侧调用点）

**问题**：`resolve_endpoints` 的分支顺序是「解析出东西 → 采信」「是 list → 采信为空」「其余 → 填默认」。于是**任何不是 list 的值**——字符串、dict、数字——都落进最后一支，被当作「上游什么都没说」而填上 `/chat/completions`（或 `/embeddings`）。

探针实测（`resolve_endpoints(value, model_type=...)`）：

| 输入 | known | advertised | 判定 |
|---|---|---|---|
| `None`（键缺席） | `['/chat/completions']` | `False` | 预期内 |
| `[]` | `[]` | `True` | 预期内 |
| `"/chat/completions"`（字符串） | `['/chat/completions']` | `False` | **非预期** |
| `{"a": "/chat/completions"}` | `['/chat/completions']` | `False` | **非预期** |
| `7` | `['/chat/completions']` | `False` | **非预期** |
| `[7]` / `[None]` | `[]` | `True` | 见 M2 |

而 `types.py:116` 的 docstring 写的是「The fallback fires only where upstream said nothing at all」，commit message 写的是「A `supported_endpoints` that arrived as a string rather than a list is a field we could not read at all, and it must not be reported as a confident claim about what upstream offers」。代码与这两句都不符：对一个**读不出来的**字段，路由侧现在给出了一个确信的答案，并且会真的把请求发上去。改动前这类条目走 `require_endpoint` 的 `CapabilityMissing`，在网络之前被拒。

**为什么算 major 而不是 minor**：这不是「多兜了一个边界」，而是把一条被文档明确声明为 fail-closed 的守卫，在文档没有改口的情况下悄悄放宽成 fail-open。报告侧有 `_wrong_shape`（`debug/models.py:131-143`）挡着，路由侧没有对应物——同一份 commit 里，两条路径对「读不出来」的处理不一致，而它的整个立论正是「路由和报告不能给出不同答案」。触发概率低（Copilot 未观测到发过畸形值）不改变这一点：一条守卫的价值恰恰在它没被触发的时候。

**建议改法**（三行，语义与 commit message 声明的完全一致）：

```python
    known, unknown = parse_endpoints(advertised)
    if known or unknown:
        return ResolvedEndpoints(known, unknown, True)
    if advertised is not None:
        # 上游说了话，只是我们读不懂或它说的是「没有」。两种都不是我们该替它填的。
        return ResolvedEndpoints(frozenset(), (), True)
    default = _DEFAULT_ENDPOINT_BY_TYPE.get(model_type, DEFAULT_ENDPOINT)
    return ResolvedEndpoints(frozenset({default}), (), False)
```

若还想把「键缺席」与「键存在但值为 `null`」分开（`model.get("supported_endpoints")` 对两者都返回 `None`），需要在两个调用点改传哨兵：`model.get("supported_endpoints", _ABSENT)`。**我的倾向是不分**——目前没有任何证据表明 Copilot 会发 `"supported_endpoints": null`，而多引入一个哨兵会让两个调用点又多一处必须同步的约定。这是个可以直接做的选择，不是需要用户裁决的分叉。

同时把 `types.py:116` 的 docstring 从「said nothing at all」改成能覆盖新条件的说法（「只有键完全缺席时才填补；上游给了任何值——包括读不懂的和空的——都算它说了话」）。

**建议补测**（对应 M1 的失败面，目前完全没有覆盖）：一条 provider 侧用例，`replace_catalog({"data": [{"id": "wrong-shape", "supported_endpoints": "/chat/completions"}]})` 后断言 `describe("wrong-shape").endpoints == frozenset()`，并断言 `send(...)` 抛 `CapabilityMissing`。

---

### M2 — 显式空列表这个状态失去了报告词汇，被报成 `no-driver`（指向了错误的责任方）

**位置**：`src/app/debug/models.py:103-128`（`status_of` 删掉了 `advertised` 参数）、`src/app/debug/models.py:190`（`drivable=bool(set(offered) - undriven)`）

**问题**：commit 明确保留了「显式 `[]` = 上游说没有」这一语义，路由侧照旧抛 `CapabilityMissing`。但报告侧的对应词 `no-endpoints` 被整个删掉了，于是这个状态掉进了 `no-driver`。探针实测 `build_rows`：

```
ID             STATUS     ENDPOINTS
absent         ok         /chat/completions?
explicit-none  no-driver  -
list-of-ints   no-driver  -
string-shaped  malformed  /chat/completions?
```

`status_of` 自己的 docstring（`debug/models.py:112`）说 `no-driver` 的含义是「a missing driver is **ours** to write」。而 `explicit-none` 的真实状态是 upstream 没有发布端点，路由会以 `CapabilityMissing`（「ghc advertises no endpoints for model X」）拒绝——**责任方是上游，不是我们**。报告现在把操作者指向了写驱动的方向，而那正是旧 docstring 里写明要避免的事（「calling that a missing driver would send someone looking for a driver we would have no way to select」）。

更直接的证据是同一份 commit 里两段 docstring 互相矛盾：

- `debug/models.py:114`：「There is no answer here for "upstream named no endpoints", because **that is not a state a model is in**」
- `types.py:116`：「an empty list is upstream speaking and is taken at its word ... **"none" and "unstated" are different claims**」

第二句成立的话，第一句就不成立。改动只在「Copilot 实际发的目录」这个样本上为真，而 `resolve_endpoints` 是按「上游可能怎么说」写的。

**为什么算 major**：这不是漏了一个罕见分支，而是一条 commit 在同一次改动里既坚持保留某个状态、又拆掉了报告该状态的能力，并且报告给出的替代词把责任方指反了。修复成本约三行。同样，触发概率低不改变判断——理由与 M1 相同。

顺带：`[7]` / `[None]` 这类「是 list 但一个字符串都没有」的输入也落进 `no-driver`，而 `_wrong_shape`（`debug/models.py:136-138`）只检查顶层是不是 list，不看元素类型，所以它连 `malformed` 都拿不到。这一条是**改动前就存在的**，此处只是被 M2 一并放大，列在这里供一并处置。

**建议改法**：把 `advertised` 这一支按「解析之后的事实」恢复，而不是按原始字段恢复——填补生效之后，`offered == ()` 当且仅当上游确实说了话而说的是「没有」，所以这个词此时是精确的：

```python
                status=status_of(
                    disabled=model_id in blocked,
                    policy_state=_text(_mapping(model.get("policy")).get("state")),
                    advertised=bool(offered),
                    drivable=bool(set(offered) - undriven),
                    malformed=_wrong_shape(model),
                ),
```

`status_of` 里把 `if not advertised: return "no-endpoints"` 放回 `no-driver` 之前，并把 docstring 里那句「that is not a state a model is in」改成「这个状态只在上游显式给出空列表时出现，实测目录里没有，但它与 `CapabilityMissing` 是同一件事，所以留着」。

**建议补测**：现有的 `test_an_endpoint_upstream_did_name_is_never_overwritten`（`tests/unit/test_debug_models.py`）已经断言了 `rows["explicitly-none"].status == "no-driver"`——修复时这一行要改成 `"no-endpoints"`，它本身就是这条发现的锚点。

---

## Minor

### m3 — `completion` 类型映射到 `/chat/completions` 是推测，参考实现指向另一个端点

**位置**：`src/app/model_provider/types.py:97`（注释），commit message 第二段

注释断言：「The absent set on that date held 14 models of type `chat` and one of type `completion`, and both are chat-completions models.」

`refs/available_models.json` 里那个 `completion` 类型的模型是 `gpt-41-copilot`（family `gpt-4.1`）。参考实现的做法与这个断言不一致：

- `refs/vscode-copilot-chat/src/extension/completions-core/vscode-node/lib/src/openai/model.ts:112` 用 `item.capabilities.type === 'completion'` 筛出这一类模型；
- 这一类模型的请求 URL 由 `refs/vscode-copilot-chat/src/extension/completions-core/vscode-node/lib/src/openai/fetch.ts:310` 构造：`getEndpointUrl(accessor, token, 'proxy', 'v1/engines', modelId, endpoint)`——即 **proxy 主机上的 `v1/engines/<model>/completions`**，而不是 `api.githubcopilot.com` 上的 `/chat/completions`。

项目规矩写着「Upstream behaviour is recorded, not imagined」。这里没有录制证据，注释却以事实语气写下了它，而这句注释正是默认值的全部依据。

**影响面很小**：只涉及 1 个模型，且不在主产品路径上（`/v1/messages` 进来的请求本来就到不了它，见 m4）。真发生时上游会以 404/400 回答，`error_status` 走 `UpstreamRejected` 原样透传状态码，失败是响的、不是静默的。

**建议**：不必现在改行为。把注释改成实测得到的话（「absent set 里 14 个 `chat` 和 1 个 `completion`；`chat` 的默认端点有目录内 11 个同类模型的显式声明佐证，`completion` 的没有，参考实现把它送去 `v1/engines/<model>/completions`，此处按 `/chat/completions` 兜底是未经录制验证的选择」），或把这个未决点记进 `deferred.md`。这属于 `no-silently-cut-but-defer` 覆盖的情形，不该只留在 commit message 里。

### m4 — 报告说 `ok`，但 `/v1/messages` 到这些模型会 400（既存缺口，被本次从 3 个放大到 23 个）

**位置**：`src/app/debug/models.py:126-128` 的 `drivable` 语义 ⇄ `src/app/pipeline/translation_driver/registry.py:127-154`

探针实测（`decide_route` + `default_registry()`）：

```
chatter  -> /chat/completions  openai-chat-completions  translate=True
   TranslatorNotFound: no translator registered as outbound.to-openai-chat-completions
embedder -> /embeddings        openai-embeddings        translate=True
   TranslatorNotFound: no translator registered as outbound.to-openai-embeddings
registry names: ['inbound.from-anthropic-messages', 'inbound.from-openai-responses',
                 'outbound.to-anthropic-messages', 'outbound.to-openai-responses']
```

`debug models` 的 `ok` 定义在 `DRIVEN_ENDPOINTS`（= provider 有 `send_*` 方法）上，而主产品路径还需要一对 translator。两者不重合。

改动前后的状态变化：

- **改动前**：这 18 个模型 → `no-endpoints` + `CapabilityMissing`（400）。
- **改动后**：`ok` + `TranslatorNotFound`（400）。状态码不变（`handler.error_status` 把 `ProviderError`、`RoutingError`、`TranslatorNotFound` 一起映射到 400），错误正文的 `type` 与 `message` 变了。

**这个缺口是既存的**：`refs/available_models.json` 里已有 3 个模型只声明 `/chat/completions`（`gemini-3.1-pro-preview`、`gemini-3.5-flash`、`trajectory-compaction`），它们改动前就是 `ok` + `/v1/messages` 400。本次把这个集合从 3 扩到 23。

**`ok` 并不是假的**：这些模型在 `/chat/completions` 与 `/embeddings` 入站路由上是真能打通的——`src/app/server/inbound.py:41-43` 注册了这两条入站路由，`src/app/pipeline/direct_driver/__init__.py:48-50` 有对应的 direct driver，`translation_required=False` 走直驱，不碰 translator。commit 声称的「Those models can now actually be routed to」是**成立的**，我验证过这条链路的每一环存在。

**建议**：不在本切片里改。要么在 `status_of` 的 docstring 里点明 `ok` 的含义是「provider 能驱动这个端点」而非「任意入站格式都能到达它」，要么把「`debug models` 是否该区分主路径可达性」记进 `deferred.md`。**不建议**为此加新状态词——那会让一个报告命令去承载 pipeline 的翻译拓扑，成本远超收益。

### m5 — `capabilities.type` 被独立读了两遍

**位置**：`src/app/model_provider/github_copilot.py:29-38`（`_model_type`）与 `src/app/debug/models.py:169,174`（`_mapping` + `_text`）

逐行核对过：两者行为**当前完全等价**（都要求 `capabilities` 是 `dict`、`type` 是 `str`，否则给 `""`），所以现在不会读出不一致的结果。JSON 解码出来的目录里 `capabilities` 只会是 `dict`，`MappingProxyType` 之类的差异在这条链路上到不了。

但这条 commit 的整个立论是「同一个问题不能有两处独立判定」，而它只共享了 `resolve_endpoints` 这个**函数**，没有共享喂给它的**输入**。`_DEFAULT_ENDPOINT_BY_TYPE` 将来若新增一个键（比如 `"completion"`，见 m3），两处对 `type` 的读法就有了两个必须同步的地方。

**建议**：把 `_model_type` 提到 `app.model_provider`（与 `resolve_endpoints` 同一个模块）并导出，两个调用点都用它；或者更彻底一点，让 `resolve_endpoints` 直接接受整条 model entry。前者改动更小，我倾向前者。

### m6 — `test_an_endpoint_upstream_did_name_is_never_replaced_by_the_default` 的 `embed-model` 那一半没有分辨力

**位置**：`tests/unit/test_model_provider.py`（`883b104` 新增，函数末尾第三个新用例）

```python
    assert provider.describe("embed-model") is not None
```

注释说这是「an embeddings model that names an endpoint keeps it」，但断言只检查了这个模型存在。它在 `resolve_endpoints` 被改坏的任何一种情况下都成立。

更要紧的是：即使把它改成 `endpoints == {ModelEndpoint.OPENAI_EMBEDDINGS}` 也**仍然没有分辨力**——`CATALOG` 里 `embed-model` 声明的是 `["/embeddings"]`，而 `embeddings` 类型的默认端点也是 `/embeddings`，采信与填补给出同一个答案。

真正的负对照（一个 `type: embeddings` 却声明了**别的**端点的模型）只存在于报告侧：`tests/unit/test_debug_models.py` 的 `test_an_endpoint_upstream_did_name_is_never_overwritten` 里那个 `named` 模型（`capabilities={"type": "embeddings"}` + 默认的 `supported_endpoints=["/v1/messages"]`），断言 `endpoints == ("/v1/messages",)`。那一条是有分辨力的。

同一用例的 `mute-model` 那一半（`endpoints == frozenset()`，`CATALOG` 里是 `"supported_endpoints": []`）**是有分辨力的**——它正是 M1 建议改法必须保住的那条不变量。

**建议**：给 provider 侧同样的形状，例如加一个 `{"id": "named-embedder", "capabilities": {"type": "embeddings"}, "supported_endpoints": ["/v1/messages"]}` 并断言其 `endpoints == {ModelEndpoint.ANTHROPIC_MESSAGES}`，然后把那句 `is not None` 删掉。

### m7 — `render_json` 的 docstring 没写 `len(catalogs) == 1` 这个条件

**位置**：`src/app/debug/models.py:368-376`

docstring 说「`keyed` reflects what was asked for, not how many providers happen to be configured」，但代码是 `if not keyed and len(catalogs) == 1`。也就是说传 `keyed=False` 而给了两个 catalog 时，`keyed` 被**静默忽略**。理由写在 commit message 里（「two catalogs cannot be one document」），但下一个读者看的是 docstring。

顺带核对过 CLI 侧不存在这个组合：`collect_catalogs` 在 `only is not None` 时 `names = [only]`，最多产出一个 catalog；`--provider` 名字不在配置里会在 `src/app/cli.py:427-432` 被 `typer.BadParameter` 提前挡下；抓取失败则 `catalogs` 为空，`if catalogs:` 让 `render_json` 根本不被调用，stdout 保持空、退出码 1——与改动前一致。所以这条纯粹是文档问题。

**建议**：docstring 补一句「超过一个 payload 时 `keyed` 不生效，因为两份目录无法构成一个文档」。

---

## Nit

### n8 — `test_json_stays_keyed_for_several_providers_even_unkeyed` 覆盖的是 CLI 到不了的状态

`tests/unit/test_debug_models.py`，`3bcf14c` 新增。它测的是 `render_json` 的函数契约，不是一条活路径（见 m7 的核对）。无害，作为防御性契约测试是合理的；记在这里只是免得日后有人把它当成一条真实场景。

### n9 — `debug/models.py:356-359` 的 legend 列表行较长

`(any(row.undriven for row in catalog.rows), f"...")` 这种「布尔 + f-string」的元组列表，两行都超过 120 列。`ruff check` 全绿（项目禁止 `ruff format`，所以这只是观感），不建议改。

### n10 — `parse_endpoints` 在 `src/` 里已无生产调用点

`883b104` 之后，`src/` 里只剩 `types.py:118` 一处内部调用，其余全在测试。它仍在 `app/model_provider/__init__.py` 的 `__all__` 里导出。这不是缺陷（它是 `resolve_endpoints` 的组成部分，单独测试它是合理的），仅记录现状。

---

## 检查过但无发现的方面

逐条写出，避免留白：

1. **`available_ids` / `GET /models` / `/health/readiness` / `/api/*` 管理面**——**不受影响**。`replace_catalog`（`github_copilot.py:105-125`）在改动前就为这 18 个模型建了 `ModelDescriptor`（当时 `endpoints` 为空集），`available_ids = frozenset(self._descriptors) - self._disabled` 与端点无关。所以 `ops_routes.py:60-71` 的 `/models`、`:38-54` 的 readiness、`routes/management.py:47` 读到的集合改动前后完全一致。**反过来说**：这 18 个模型改动前就出现在 `/models` 里却每次请求都 400——本次改动实际上是**缩小**了这个既存的不一致，而不是制造了新的。

2. **模型解析与别名**（`src/app/pipeline/model_resolution.py`、`src/app/transform/model_resolver.py`、`src/app/upstream/bootstrap.py:121,206`）——**不受影响**。它们的输入是 `available_ids`（见上条，未变），不读 `endpoints`。`decide_route` 里 `resolve_model` 在 `describe()` 之前调用，顺序也没变。

3. **`count_tokens`**——**行为等价**。`github_copilot.count_tokens`（`:184-199`）对这 18 个模型现在抛 `EndpointNotSupported` 而非 `CapabilityMissing`。两者都是 `ProviderError` 子类；`pipeline/count_tokens.py:75-78` 对 `ProviderError` 一律原样上抛（不重试、不降级到本地估算）；`handler.error_status` 把 `ProviderError` 整支映射到 400。所以状态码、是否降级、attempts 轨迹都不变，只有错误正文的 `type` 与 `message` 变了。

4. **`routing.py:83-84` 的 `CapabilityMissing` 是否被架空**——**没有**。它对显式 `[]` 和「是 list 但无字符串元素」两种输入仍会触发（探针第 1 组已证 `advertised=True, known=∅`）。全仓生产代码里构造 `ModelDescriptor` 的只有 `github_copilot.py:118` 一处（其余全在测试），所以这条守卫的可达性完全由 `resolve_endpoints` 决定，而后者保住了这两条入口。**注意**：如果采纳 M1 的改法，可达性还会扩大回「所有非 list 输入」，这正是 M1 想要的。

5. **`send()` 真的能打通被填补的模型**——**能**。`_SEND_METHODS`（`github_copilot.py:42-47`）含 `OPENAI_CHAT_COMPLETIONS` 与 `OPENAI_EMBEDDINGS`；`src/app/server/inbound.py:41-43` 注册了 `/chat/completions` 与 `/embeddings` 入站路由；`src/app/pipeline/direct_driver/__init__.py:48-50` 有对应 direct driver。新测试 `test_a_model_with_an_unstated_endpoint_can_actually_be_sent_to` 断言 `request.url.path == "/chat/completions"`，是这条链上有分辨力的一环。

6. **`gpt-3.5-turbo` 这类老模型走 `/chat/completions` 是否合理**——**合理**。`refs/available_models.json` 里 20 个缺键条目中 16 个是 `type: chat`（`gpt-3.5-turbo`、`gpt-4`、`gpt-4o` 系列等），而目录里显式声明端点的条目有 13 个包含 `/chat/completions`，没有任何 `chat` 类型模型声明过别的独占端点。默认值与观测一致。失败形式也可接受：上游拒绝 → `UpstreamRejected` → `handler.error_status` 原样透传上游状态码（不折成 502），客户端拿到的是上游自己的判词。唯一没有观测支撑的是 `completion` 类型，已单列为 m3。

7. **`_endpoint_cell` 的 `*` 与 `?` 组合**（`debug/models.py:260-271`）——**正确**。`?` 追加在每个 part 之后，而 `assumed` 为真时 `endpoints` 恒为单元素（`resolve_endpoints` 的填补分支只产出一个端点），所以不会出现「`a?, b?`」这种读起来像两个假设的排版。docstring 里「both are applied rather than chosen between」的设计意图与代码一致。渲染实测见 M2 的表格。

8. **legend 的负对照**——`test_a_mark_nothing_carries_is_left_out_of_the_legend` 用 `_model("routable")`（`supported_endpoints=["/v1/messages"]`，既非 assumed 也非 undriven）同时否掉两条图例行，是真负对照，不是恒真。

9. **`3bcf14c` 的意外输入面**——已在 m7 里逐个走过：`--provider` 未配置（提前 `BadParameter`）、抓取失败（`catalogs` 为空，不调 `render_json`，exit 1）、非 Copilot 类型 provider（`CatalogFailure`，同上）、`--provider` 产出多个 catalog（`collect_catalogs` 结构上不可能）。均无回归，仅剩 docstring 一处不完整。

10. **legacy 链的第二份答案**——`src/app/pipeline/route_policy.py:151-156` 仍然把「missing or empty」一并判成 `capability_missing`，与新 pipeline 现在的答案不同。但它的唯一调用点是 `src/app/anthropic/client.py:205-219`，属于 `app_factory` 那条 legacy 链，不在当前 CLI 所用的 `pipeline_app` 上（项目 review 原则明确把 legacy 链排除在外）。**记录而非计入发现**：若 legacy 链哪天重新接线，这两条链对同一目录会给出不同的可路由集合。

11. **人写权威文档**——`docs/.human-controlled/MAIN.md:19-58` 只规定了入站端点集合与「上游模型端点 → 驱动模块」的对应表，未对 `supported_endpoints` 缺席时该怎么办作出裁决。本次改动与该文档**无冲突**（`/chat/completions`、`/embeddings` 都在表内且有驱动模块）。

12. **静态检查与测试**——`uv run ruff check` 对 5 个改动文件全绿；`uv run pytest tests/unit/test_debug_models.py tests/unit/test_model_provider.py` 64 passed。未跑全量 pytest：任务已说明当前约 8 个失败来自并行会话的中间态，跑它不会产出关于本次评审对象的信息。

---

## 处置建议（按优先级）

1. **M1** 与 **M2** 一起修，同一个切片，约 8 行源码 + 2 处 docstring + 2 条测试（1 新增、1 修断言）。两者是同一处设计的一体两面：M1 管「谁算说了话」，M2 管「说了话而说的是没有，报告怎么讲」。
2. **m5** 顺手做掉（把 `_model_type` 提到 `app.model_provider` 共享），成本几行，且能防住 m3 将来若新增 `completion` 键时的漂移。
3. **m3**、**m4** 记进对应话题的 `deferred.md`，写清不做的理由；m3 另需改一句注释的语气。
4. **m6**、**m7** 是低成本改进，可与第 1 项同一次提交。
5. **n8**–**n10** 仅记录，不建议改。

不建议做的：不要为 m4 新增报告状态词；不要为本次改动引入任何新的验收门禁或覆盖率阈值（项目规矩明确禁止）；不要跑 `ruff format`。
