# 多 model provider 路由 Spec 事实对账

> **落盘说明**：本报告由事实对账评审 subagent（gpt-opus）产出。该 subagent 的约束禁止它自行创建 `.md` 文件，因此由主会话代为落盘，**正文逐字保留**，仅添加本说明块。评审时间 2026-08-27，被评对象为 `spec.md` 的 v1（首版）。
>
> 处置结果：8 条全部采纳，`spec.md` 已按其修订，逐条记入该文件的「条款修订记录」表。

## 评审范围

- 被评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/multi-provider-routing/spec.md`
- Ground truth：主树 `/home/xp/src/ghc-api-proxy-py/src/`、`/home/xp/src/ghc-api-proxy-py/tests/`、`/home/xp/src/ghc-api-proxy-py/docker-compose.yml`、`/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/`
- 版本锚：评审开始时 `main` ref 为 `d514c6bbbc0c3f967cf7ba88dab9cf51f367e363`；实际读取的是主树 working tree 文件。
- 范围限制：只核对 Spec 对现有代码和文件的事实陈述，不评价设计取舍，不复核 18 项用户裁决是否真实发生，也不提出实现建议。

## 总体判定

`needs-fix`。发现 `blocker=0`、`major=1`、`minor=7`，共 8 条。

## 发现

### facts-01

- 严重度：major
- Spec 位置与原句：§2.4，「passthrough 的名字既不在 `available_ids` 也不在 `_descriptors` 里，必然得到 `None`，于是 `raise UnknownModel`——passthrough 的名字从来不会真的发给上游。」
- 核实事实：绝对断言不成立。当前 `resolve_model()` 在某个 mapping 命中但最终目标不可用时，会放弃 mapping，并把 `resolved` 恢复成原始请求名。若这个原始请求名本身是 provider 正常提供的模型，`passthrough=True` 与 `provider.describe(resolved) != None` 可以同时成立，`decide_route()` 会成功返回 route，随后请求会以原始模型名发往上游。
- 证据：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/model_resolution.py:98-100` 返回 `requested.strip()`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/routing.py:97-99` 只按 `resolution.resolved` 调 `describe()`，不检查 `passthrough`。
- 运行证据：用 `/tmp/spec_review_passthrough_probe.py` 构造 provider 提供 `real-model`、mapping 为 `real-model -> missing-target`，执行 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/spec_review_passthrough_probe.py`，输出为：

```text
ModelResolution(requested='real-model', resolved='real-model', matched_key='real-model', passthrough=True, hops=0)
route.model_id='real-model', route.resolution.passthrough=True
```

- 失效范围：这条错误事实直接推翻 §2.4 用来证明“保持 `resolved=requested` 不改变可观察行为”的核心推导，也使 §5.2「passthrough 必然进入 `UnknownModel`」的前提失效。§2.3 所称限定目标不可用后“最终必被 `UnknownModel` 拦住”也不是无条件成立；若原始请求名在选中 provider 的目录里，当前语义会回退并发送原始模型。依赖同一 resolver 计算的 §4.2 `serviceable` 结果也会受这个边界影响。

### facts-02

- 严重度：minor
- Spec 位置与原句：§0，「`context.provider_name` 是路由的输出而非输入……而全仓唯一写入点是 `apply_route`，在 `decide_route` 之后。」
- 核实事实：窄化到 active production source 后，“唯一赋值点是 `apply_route`，且调用发生在 `decide_route` 后”属实；但“全仓唯一”和“不是输入”都过宽。`tests/` 中有 5 个直接赋值点，而且 `RequestContext.provider_name` 是公开可写字段；`shape_request()` 在调用 `decide_route()` 前就读取它来选择 provider，因此一个预填的值实际上是路由输入。
- 证据：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py:92-99` 先读取 `context.provider_name`，再调用 `decide_route()` 和 `apply_route()`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/request.py:74-76` 定义可写字段。命令 `rg --line-number -e 'context\.provider_name\s*=' /home/xp/src/ghc-api-proxy-py/src /home/xp/src/ghc-api-proxy-py/tests` 找到 production 的 `routing.py:151`，以及 `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:443,449,468,494,523`。
- 保留下来的窄结论：正常 HTTP 入站构造器 `/home/xp/src/ghc-api-proxy-py/src/app/server/inbound.py:60-68` 不设置该字段，因此当前实际入站请求仍会在 `driver.py:92` 落到 default provider。此发现不推翻 Spec 对现有 HTTP 行为的最终判断。

### facts-03

- 严重度：minor
- Spec 位置与原句：§1.3，「`driver.py:342` 的注释明确说测试依赖 `ghc:` 这个前缀的确切形状，所以对应测试一并改。」
- 核实事实：这里把注释中的 `test` 误读成了自动化测试。该注释里的 “neither test” 指紧随其后的两个运行时判定：`f"ghc:{absent_reason}" in trail` 与 `entry.startswith("ghc:")`，不是 test suite。
- 证据：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py:342-348`。注释说前缀和 exact string 已由 producer 定义，因此下面两个条件判定无需猜测 entry 形状。
- 影响：四处运行时代码字面量的计数仍然正确；只有对注释原意的归因不正确。

### facts-04

- 严重度：minor
- Spec 位置与原句：§8.2，「`composition.py:488` 还专门论证过不能合并（『模型 id 唯一，不代表两个 provider 跑它的方式相同』）。」
- 核实事实：`composition.py:488` 确实论证了 per-provider pattern 不应合并，但括号中的引文不在该文件该行。它的原文位于 `hosted_web_search.py:60`。
- 证据：`/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:488-493` 只写每个 provider 的 patterns 要分开，避免空列表继承别人的条目；完整的 “Uniqueness of the id says nothing about whether two providers run that model the same way” 位于 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/subscribers/hosted_web_search.py:55-62`。
- 影响：底层事实和 §8.2 的行为判断仍有源码支持，但引文来源归错。

### facts-05

- 严重度：minor
- Spec 位置与原句：§4.2，「`/api/config`……是 `ProxyConfig` 的完整 dump（`ops.py:88`），说『配置里写了什么』。」
- 核实事实：它以完整 `ProxyConfig.model_dump()` 为起点，但返回前会改写 `proxy`，把 URL userinfo 替换成 `***`。因此它是完整字段集合的 resolved snapshot，不是所有值未经改写的完整 dump。
- 证据：`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/ops.py:88-100`；`model_dump()` 在第 96 行，`proxy` 替换在第 97-99 行。该 handler 自己的 docstring 第 90-94 行也明确说明这一限定。
- 影响：不改变 `/api/config` 与 `/api/status` 的总体分工，只是“完整 dump”这一事实陈述缺少已有的限定。

### facts-06

- 严重度：minor
- Spec 位置与原句：§8.3，「history｜本项目没有实现｜`ops.py:7` 明说它 absent rather than answered with a plausible stub。」
- 核实事实：active live chain 没有 history 实现或端点，但“本项目没有实现”过宽。仓库保存了完整的 history 实现，只是已经移入 `src/.archived/app/history/`，当前入口不可达。`ops.py:7` 的原话限定为 “History still needs state this chain does not own, and is absent”，说的是这条 chain 不拥有所需状态以及端点缺席，不是整个项目从未实现。
- 证据：`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/ops.py:7`；`/home/xp/src/ghc-api-proxy-py/src/.archived/README.md:1-3,21-27` 明确说 archived 目录保留唯一实现，且 `/history/api/*`、`/history/ws` 与 `app.history` 尚无 live equivalent；实现文件包括 `/home/xp/src/ghc-api-proxy-py/src/.archived/app/history/store.py`、`consumer.py`、`sqlite/writer.py` 等。
- 影响：§8.3“不动 live history 链路”的结论没有因此失效，但引用把“当前 chain 无 live 实现”扩成了“项目无实现”。

### facts-07

- 严重度：minor
- Spec 位置与原句：§7.1，「三个含斜杠的命中（`claude-cli/2.0.0`、`gpt-model/responses`、一条插件路径）无一是模型 id。」
- 核实事实：核心负结论可复现，但数量和第三项类别写得不精确。扫描得到 3 个不同 token 值、6 个文本 occurrence；第三项是 `e2e/claude/cassettes/` 测试素材目录，不是插件路径。
- 证据：独立 Python 扫描 `src/`、`tests/`、`docs/`，使用 vendor-prefixed token 正则 `(?<![A-Za-z0-9_.-])((?:claude|gpt|gemini)[-A-Za-z0-9_.]*/[-A-Za-z0-9_.]+)`。结果为：
  - `claude-cli/2.0.0`：4 处，位于 `tests/unit/pipeline/test_client_request_headers.py:89,95` 和 `tests/component/model_provider/ghc_client/test_client.py:169,182`，均为 User-Agent。
  - `gpt-model/responses`：1 处，位于 `tests/int/test_pipeline_app.py:975`，是 Azure 路径的一部分。
  - `claude/cassettes`：1 处，位于 `docs/.human-controlled/test-org.md:31`，完整路径为 `e2e/claude/cassettes/`。
- 补充证据：独立统计 `config.example.yaml:172-213` 的 active 与 commented `disabled_models` 条目得到 41 个，含 `/` 的条目为 0。
- 影响：§7.1「当前记录中的 GHC model id 不含 `/`」仍由本次扫描支持；错误只在把 distinct token 写成“命中数”，以及把测试目录说成插件路径。

### facts-08

- 严重度：minor
- Spec 位置与原句：§7.2，「所有 provider 共享——包括连接池，以及打在那个池上的 `cap_streams_per_connection`……两个 GHC provider 的 `api_base_url` 默认是同一个 host，所以两者的请求会跑在同一批 TCP 连接上。」
- 核实事实：所有 production provider 的确共享同一个 `httpx2.AsyncClient`，同一实际 origin 且走同一 mount 的请求会共享 transport pool 和连接；但并非 client 只持有“那一个池”，也不能无条件断言两个未显式填写 `api_base_url` 的 provider 最终同 host。
- 证据：
  - `/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:173-187` 构造一个 client；第 460-484 行把同一 client 传给循环中的每个 provider。
  - `/home/xp/src/ghc-api-proxy-py/src/app/upstream/stream_cap.py:124-135` 明确遍历 default transport 与全部 mounted transports，并按 identity 对每个 distinct pool 分别加 cap，不是一个全局 pool。
  - `/home/xp/src/ghc-api-proxy-py/src/app/cli.py:144-147,184-187` 在建 chain 前执行 `resolve_provider_base_urls()`。
  - `/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:333-405` 按每个 provider 自己的 token 探测 subscription 并分别解析 base URL；`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/config.py:35-44` 对 individual、business、enterprise 解析为不同 host。
- 影响：§7.2 的强结论应收窄为“两个 provider 最终解析到相同 origin，并走同一 proxy/mount 时会共享连接”。同 host 的常见配置下，§8.1 所依据的交叉影响仍真实存在；不是所有双 provider 配置都已经共享同一批 TCP 连接。

## 我查过但认为没问题的

1. `src/app/pipeline/driver.py:92` 确实读取 `context.provider_name or chain.providers.default_name`；live inbound 构造器不设置 provider，因此当前 HTTP 请求会先选 default provider。
2. `decide_route()` 确实先于 `apply_route()` 执行，见 `driver.py:93-99`；active `src/app` 中 `context.provider_name` 的直接赋值点只有 `routing.py:151`。
3. `ProviderRegistry.__init__()` 在 default 不属于 providers 时确实抛 `ProviderNotConfigured`，见 `src/app/model_provider/registry.py:23-25`。
4. `CountTokensProvider = Literal["ghc", "local"]` 的位置和内容准确，见 `src/app/config/schema.py:14`；默认值 `["ghc", "local"]` 位于第 77 行。
5. `CountTokensProvider` 的 `ghc` 表示 upstream counter，而不是 `model_providers` 的键。`src/app/pipeline/count_tokens.py:52-87` 只据此选择传入的 `upstream` callback；真正的模型 provider 已在 `driver.py:260` 由 route 选定。
6. `driver.py` 中列出的四处 executable `ghc` 字面量准确，分别位于第 343、345、347、350 行；没有少数或多数。
7. `docs/.human-controlled/config.example.yaml:71` 确实写着 `providers: [ghc, local]`。
8. `_MAX_ALIAS_HOPS = 8`、`canonical()` 转小写并把 `.` 替换成 `-` 均准确，见 `src/app/pipeline/model_resolution.py:15,27-33`。
9. `split_format_suffix()` 确实以 `rpartition("@")` 剥后缀，见 `src/app/pipeline/routing.py:60-80`。
10. `ModelResolution.hops`、`matched_key`、`passthrough` 与 `Route.resolution` 在 active `src/app` 中没有属性读取者；前 3 个只在 resolver 内构造，`Route.resolution` 只在 `routing.py:126` 赋值。
11. `GithubCopilotProvider.available_ids` 确实等于 descriptor keys 减 disabled set，见 `src/app/model_provider/github_copilot.py:84-85`；`describe()` 对 disabled model 先返回 `None`，见第 87-90 行。
12. `refresh_catalogs()` 确实遍历 `chain.providers.names` 并逐个调用 `refresh_catalog()`，见 `src/app/server/composition.py:532-541`。
13. `rate_limiters` 确实按 provider 创建，见 `composition.py:527-528`；`Chain.rate_limiter_for()` 按 provider name 读取，见 `src/app/core/chain.py:50-51`。
14. production `CopilotTokenManager` 确实在 provider 构建循环内逐 provider 创建，见 `composition.py:460-483`。
15. provider 凭据确实通过每次请求生成的 `Authorization` header 发送，而不是连接状态。每个 provider 的 `GhcApiClient` 持有自己的 token manager，见 `src/app/model_provider/ghc_client/client.py:39-66,68-97`。
16. 项目定义的 Prometheus `Counter` 确实只有 3 个：`TRANSLATION_LOSSES`、`ATTRIBUTION_LINES_STRIPPED`、`BETA_FLAGS_STRIPPED`，见 `src/app/observability/metrics.py:13-34`；它们的 labels 都不含 provider。
17. `/models` 三条路径当前确实只列 default provider 的 `available_ids`，见 `src/app/server/routes/ops.py:50-64`；`owned_by` 也确实对每行都填该 default provider name。
18. `list_models()` docstring 确实写着 “The catalog routing consults”，见 `ops.py:54`。
19. `/api/status` 与 `/health/readiness` 当前确实是同一个 handler，decorators 位于 `ops.py:29-30`；其 docstring 的确论证两者问同一问题、分开会漂移，见第 32-36 行。
20. 当前 readiness 判据确实是所有 provider 中任一 `models` 非零，即 `any(...)`，见 `ops.py:39-46`。
21. `docker-compose.yml:27` healthcheck 确实请求 `/health/liveness`，不是 `/api/status`。
22. `src/app/server/admission.py:22` 的 `UNGATED_PATHS` 确实含 `/health/readiness`，不含 `/api/status`。
23. `RequestLine` 定义位置是 `src/app/observability/request_log.py:104`，没有 provider 字段；其 docstring 确实规定 `model` 为空时整段省略而不是打印占位符，见第 105-113 行。
24. `RoutingError` docstring 的原文准确：“Raised before any network request, so an unroutable request never reaches upstream.”，见 `src/app/pipeline/routing.py:40-41`。
25. `src/app/pipeline/subscribers/hosted_web_search.py:90` 确实错误地声称 `context.provider_name` 由 `server/handler.py` 设置；live 代码实际由 `apply_route()` 设置。
26. `src/app/observability/rejection_capture.py:66` 确实记录 `context.provider_name`。
27. `model_thinking_effort`、`cache_control_sanitize`、`strip_anthropic_beta_flags` 目前均属于全局 `ProxyConfig`，见 `src/app/config/schema.py:272,354,392`；composition 也从这些全局位置接线，见 `composition.py:509-521`。
28. `models_support_web_search` 确实位于每个 `ModelProviderConfig` 下，见 `schema.py:85-108`，并在 composition 中按 provider 保持分离。
29. `src/app/config/bundled-config.yaml` 确实没有 `claude-opus-5` 自映射键，而有 `fable: claude-opus-5`，见第 9-28 行。
30. `docs/.human-controlled/api.md` 确实把 `/health/liveness`、`/health/readiness` 放在“健康检查”，把 `/api/status`、`/api/config` 放在“状态与配置”，见第 14-20 行。该文档没有规定这些端点的 response body；Spec 将 body 重写的权限归于另列的用户裁决，而不是声称 `api.md` 自己规定了新 body，因此这里没有发现误引。

## 我考虑过但排除的怀疑方向

1. 一度怀疑 `describe()` 会因 `_descriptors` 仍含 disabled model 而把 disabled model 放行。已排除：`github_copilot.py:87-90` 在查 `_descriptors` 前先检查 `_disabled` 并返回 `None`。
2. 一度怀疑 shared `httpx2.AsyncClient` 会令不同 provider 的凭据串用。已排除：每个 provider 都有独立 `CopilotTokenManager`，而 `GhcApiClient.request_headers()` 每次调用从该 manager 取 token 并生成 request header；连接不保存 bearer token。
3. 一度怀疑 `ModelResolution` 元数据通过 `asdict()`、`__dict__` 或通用 serialization 被间接读取。已扫描 active `src/app`，没有 route/resolution 的此类序列化路径；零读取者断言成立。
4. 一度怀疑 `/api/status` 在用户控制文档中其实属于 healthcheck。已排除：`docs/.human-controlled/api.md:16,19` 明确分到两个不同类别。
5. 一度怀疑 active `src/app` 仍藏有 history writer，仅路由未接线。已排除：active `src/app/history` 不存在，history package 和 handlers 都在 `src/.archived/`；因此“live chain 没有 history 实现”成立，只有 Spec 扩写成“本项目没有实现”不成立。
6. 一度怀疑 §7.1 的三个 slash token 中存在实际 model id。逐处读上下文后排除：它们分别是 User-Agent、Azure URL path 和 test cassette 目录。
7. 一度怀疑除 `apply_route()` 外还有 production setter 通过不同拼写写 `context.provider_name`。对 active `src/app` 的赋值与字段引用扫描只找到 `routing.py:151`；其余 production 命中均是读取或注释。
