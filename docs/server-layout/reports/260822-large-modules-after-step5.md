# `app.server` 两个大模块的内聚性分析（第二轮执行之后）

**性质**：subagent（GPT）报告原件。**日期**：2026-08-22。
**落盘说明**：该执行单元受 harness 约束无法自行写入文件，内容由主会话原样转录，仅修正了 heredoc 的 HTML 转义（`&lt;&lt;` → `<<`）。判断与措辞未改。

**与 [server-layout](../server-layout/README.md) 的关系**：那份是第一轮的完整设计（怪味 S1–S5、目标布局、分步路径）。本报告分析的是**该路径执行到第 5 步之后**的状态，因此它的价值在增量——其中 F3、F5 是那份设计没有覆盖的。

---

## 范围与快照

分析基于当时 `HEAD=a59800d8f31804bd89a5bc6aa3ce785d39891343`。开始分析时两个目标文件均无工作树改动；最终复核时 `composition.py` 出现一处同伴并行修改（`_warn_about_socks` 增加解释性注释并缩短 warning 文案，537 → 538 行），该改动不改变结构判断，以下 `composition.py` 行号按最终工作树版本计算。`routes/inference.py` 与 `HEAD` 一致。`src/app/pipeline/delivery/*` 的并行在途改动未作为结论依据。

历史结论可以定得很强：`routes/inference.py` 是刚拆出来的中间态，不是新近形成的独立积弊。AST 对比显示，`ef4defb^:src/app/server/pipeline_app.py` 中的 `_serve`、`_aborted`、`_dispatch`、`_StreamAccounting`、`_AccountedStreamingResponse`、`_counted_upstream`、`_tracked_delivery` 与当前文件对应符号全部 AST-identical，唯一命名变化是 `_serve` 改为跨模块公开的 `serve`。因此 `ef4defb` 完成的是落位与命名，不是内聚性整理。此前 `28c1a7a` 已移出请求累积状态，`1b34815` 已拆掉旧 handler，`b973ed0` 已移出两个纯 continuation decision，`c01191f` 已统一 chain 地址；当前剩余问题是这轮重构明确尚未完成的下一层。

可复算：

```bash
git show --format=fuller --stat 1b34815 28c1a7a b973ed0 c01191f ef4defb
git log --follow --format='%H %aI %s' -- src/app/server/routes/inference.py
python - <<'PY'
import ast
import subprocess
from pathlib import Path

repo = "/home/xp/src/ghc-api-proxy-py"
old_text = subprocess.run(
    ["git", "-C", repo, "show", "ef4defb^:src/app/server/pipeline_app.py"],
    check=True, capture_output=True, text=True,
).stdout
new_text = Path(repo, "src/app/server/routes/inference.py").read_text()
old = {n.name: n for n in ast.parse(old_text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
new = {n.name: n for n in ast.parse(new_text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
for old_name, new_name in (
    ("_serve", "serve"), ("_aborted", "_aborted"), ("_dispatch", "_dispatch"),
    ("_StreamAccounting", "_StreamAccounting"), ("_AccountedStreamingResponse", "_AccountedStreamingResponse"),
    ("_counted_upstream", "_counted_upstream"), ("_tracked_delivery", "_tracked_delivery"),
):
    left, right = old[old_name], new[new_name]
    left.name = new_name
    print(old_name, ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False))
PY
```

---

## `src/app/server/composition.py`

### 顶层符号与关注点

16 个顶层类／函数，按 6 个独立改动理由分组。

| 分组 | 顶层符号 | 关注点与改动理由 |
|---|---|---|
| 出站 HTTP transport | `TransportOptions` `:68-85`；`_keepalive_socket_options` `:92-118`；`transport_options` `:121-141`；`build_http_client` `:144-186`；`_keep_proxy_connections_alive` `:189-229`；`_warn_about_socks` `:232-252`；`_origin_of` `:255-264`；`_is_socks` `:267-268`；`_environment_bypasses_everything` `:271-278`；`_effective_proxies` `:281-299` | 配置到 socket options、proxy tier precedence、httpx mount、httpcore 私有连接构造补丁、SOCKS 可观测性 |
| GitHub 凭据来源 | `github_token_path` `:302-309`；`build_github_token_source` `:312-329` | provider-specific token file 与 CLI/env/file provider chain |
| Provider base URL 发现 | `resolve_provider_base_urls` `:332-404` | 启动期调用 GitHub account API、解释 subscription、重建校验后的配置，并定义错误降级策略 |
| Copilot provider 构造 | `build_copilot_provider` `:407-444` | 组装 OpenAI SDK、Anthropic SDK、`GhcApiClient` 和 `GithubCopilotProvider`，明确关闭 SDK retry |
| 整体对象图构造 | `build_chain` `:447-511` | provider registry、translator registry、subscriber registry、header policy 与 per-provider rate limiter |
| Catalog 运行期操作 | `refresh_catalogs` `:514-523` | 遍历现有 registry 执行 catalog refresh；**不构造任何对象** |

结论不是「16 个符号互不相干」。前 15 个大多确实服务于组装，文件不是典型 god module，也没有请求处理、客户端协议解析或业务 retry matcher 混进来。但它也不再是单一改动理由的模块：前 299 行已经是一套可独立演化和测试的 transport factory；`refresh_catalogs` 则根本不是构造职责。

配置结构变化横跨多个组不自动构成怪味——composition root 本就把配置映射到各组件。真正可区分的是：修改 proxy precedence 不应要求理解 subscriber registration；修改 GitHub subscription 识别不应要求触碰 httpcore 私有连接补丁；修改 catalog refresh 生命周期不应要求 import 整个 builder world。

### 隐藏顺序耦合

**第一处**：`build_http_client` 内部两个对同一 proxy pool `create_connection` 的补丁（`:157-186`）。`_keep_proxy_connections_alive` 必须先安装，`cap_streams_per_connection` 必须后安装；顺序反过来会让 keep-alive closure 覆盖 cap，连接上限静默失效。类型只显示「两个函数都接收 transport/client」，没有表达「第二个必须包装第一个」。注释与专门测试解释了原因，因此不是无人知道的积弊，但仍是结构未表达的顺序耦合。

```bash
rg -n -C 5 '_keep_proxy_connections_alive|cap_streams_per_connection' src/app/server/composition.py
rg -n -C 8 'test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive' tests/unit/server/test_http_client_build.py
```

**第二处**：生产 bootstrap 的固定顺序 `build_http_client` → `resolve_provider_base_urls` → `build_chain`，在 `cli.py:144-147`、`cli.py:184-187` 与 `debug/models.py:230-234` 手工重复。`resolve_provider_base_urls` 返回普通 `ProxyConfig`，`build_chain` 也接受未解析的 `ProxyConfig`——遗漏第二步不会出现类型错误，只会让 provider 落回默认 host。当前三个入口均正确，属未来入口容易漏步骤的轻微风险。

### F4（moderate）：transport 已经是独立子系统，而不是几行组装胶水

`:68-299` 的 10 个符号共同拥有 proxy precedence、OS socket option compatibility、httpcore 私有 API 适配、mount topology、警告投影和补丁组合顺序。这一组内部高度内聚，但与 `build_chain` 的 pipeline wiring 是不同改动理由。留在同一个 538 行单文件里，会让 httpx/httpcore 升级与 provider／subscriber 组装共享同一编辑热点，并隐藏上面那项补丁组合约束。适当落点是 composition root 内的 `http_client`／`transport` 子模块，而不是把依赖构造塞进 `httpx.AsyncClient` 或 `GithubCopilotProvider` 自身。

证据权重：强到足以安排拆分。依据不是行数，而是 10 个符号形成闭合调用子图，只有 `build_http_client` 对外。

### F5（moderate）：`refresh_catalogs` 不属于构造模块，应归 provider registry 的运行期接口

`:514-523` 只读取 `chain.providers` 并逐个调用 `refresh_catalog()`；`server/pipeline_app.py:21,67` 为此在 app factory 的运行期 import composition root。结果是一个已经拿到完整 `Chain` 的 HTTP app 仍要加载 OpenAI SDK、Anthropic SDK、httpx/httpcore 私有 transport 等全部建造侧依赖。若按已裁决方向把 builders 移到入口层，这条反向 import 会立即成为阻碍。

最自然的所有者是 `ProviderRegistry`（如 `await chain.providers.refresh_catalogs()`），它已拥有 names/get/default，且 refresh 是 `ModelProvider` protocol 的正式能力。准确说这不是「构造逻辑该属于被构造者」，而是**被构造 registry 的运行期操作**。

证据权重：强到足以行动。函数体完全不使用 `Chain` 的其它字段，也不创建对象。

### F6（minor）：生产对象图的异步预解析顺序没有具名入口

`resolve_provider_base_urls` 保持在 `build_chain` 外**是有充分理由的**（`:337-343` 明确指出 `build_chain` 因而保持同步、纯构造，并允许测试直接注入 provider），不应「修」成让所有 `build_chain` 调用都做网络 I/O。剩余问题只是三个真实入口手写相同三步协议；可增加入口层 `build_runtime_chain`／bootstrap facade，同时保留底层纯 `build_chain`。

### 看着像怪味、读完后排除的

- `build_copilot_provider` 和 `build_chain` **不应**搬进 `GithubCopilotProvider.__init__`：它们注入共享 `http_client`、token manager、SDK client、registries 与配置派生值；让被构造者自己创建依赖会降低可替换性并重新引入全局式组装。
- `resolve_provider_base_urls` 没有内联进 `build_chain` **是正确的**：注释给出的同步构造、测试注入、仅真实入口需要 probe 的理由成立。
- SOCKS warning、HTTP proxy keep-alive 补丁及大量解释性注释**不是**无关功能堆积：它们共同解释 transport factory 为何必须偏离第三方默认行为，且都有已测量的具体故障形态。
- `build_chain` 同时建立 provider、translator、subscriber 与 rate limiter **是 composition root 的本职**：它们因对象图一起变化，不应仅因引用多个包而拆进各被构造类型。

---

## `src/app/server/routes/inference.py`

### 顶层符号与关注点

7 个顶层符号，但 `_dispatch` 一项横跨多个职责。

| 顶层符号 | 行号 | 实际关注点 |
|---|---:|---|
| `serve` | `:68-107` | 建立 trace、登记 active request、调用 dispatcher、异常／非流式结束时释放并写 completion；通过 response 类型把流式结束责任移交给 body |
| `_aborted` | `:110-123` | 将 pre-response exception 分类成可观测 `gone`／`fail` 及 detail |
| `_dispatch` | `:130-498` | 客户端 deadline、读 body、route lookup、JSON parse、`RequestContext` 构建、attribution stripping、count_tokens、正常 pipeline 调用、HTTP error rendering、拒绝捕获、stream／buffered 分支、delivery policy 选择、replay reopen、continuation、reply translation、最终 response |
| `_StreamAccounting` | `:501-560` | 流式 finalize-once 状态机；吸收 terminal、写 `context.reply`、判定结束类别、移除 active request、写 completion |
| `_AccountedStreamingResponse` | `:563-592` | ASGI response body close owner；确保 body 从未迭代时仍 close/finalize，并保留 primary exception |
| `_counted_upstream` | `:595-618` | 在上游 chunk 边界采集首字节、最大间隔、chunk 数与 byte 数并原样转发 |
| `_tracked_delivery` | `:621-642` | 关闭 delivery iterator、区分自然耗尽／异常／下游停止，并调用 accounting finish |

按改动理由至少 5 组：HTTP surface；pipeline 调用；delivery strategy；observability projection；resource lifecycle。上游协议变化要改 `assembler_for`／`response_payload`，但本文件仍要审查 `:287-498` 三个分支；客户端契约变化要改 `:141-169`、`:273-283`、`:284-464`、`:466-498`；错误策略变化要同时检查 `_aborted`、count failure、normal handle failure 和 `_StreamAccounting._ending`。

### `b973ed0` 之后的边界判断

**已划干净**：模型选择（本文件只调 `handle_bounded`／`handle_count_tokens`，routing 在 `app.pipeline.driver`）；纯 retry eligibility（`replay_reason` 在 `app.pipeline.hand_over`，budget decision 在 pipeline delivery）。`_hand_back` 这个十行 closure 只绑定 request-scoped 参数，正是提交信息描述的合理 edge adapter，**不应**因为它是 closure 就继续拆。

**尚未干净**：mid-body replay 的实际执行仍由 `_dispatch._reopen`（`:345-402`）完成；delivery shape 仍在 route 内由 `context.stream`、`framer_for(...) is None` 分支决定（`:284-464`）；buffered continuation eligibility 仍在 route 内判断 stop reason membership 与 payload content shape（`:475-492`），而 streaming 同一语义由 `pipeline.delivery.stream` 消费 `ContinuationSupport.stop_reasons` 判断。

准确结论：`b973ed0` 移出了两个纯领域函数，方向正确；当前 HTTP surface 不再选择模型、不再自己分类 retryable exception，但**仍驱动 replay action，仍拥有一份 buffered continuation／delivery-shape policy**。不能写成「策略与 HTTP 已完全分离」。

### F1（major）：`_dispatch` 仍在 HTTP surface 执行 pipeline replay，并保留一份 buffered continuation 决策

关键位置 `:270-283`、`:345-429`、`:475-492`。`_reopen` 不是单纯把 HTTP 对象转成参数：它推进下一 attempt、调用 `handle`、恢复 request payload、选择新 delivery components、发布 attempt 状态。buffered 分支自行判断 `stop_reason in _hand_over_reasons`，再修改客户端 payload、`stop_reason` 与 trace verdict。

两个具体失效场景：

1. 新增一种 per-attempt setup 或 replay invariant 时，只改 `driver.handle` 的首次入口而漏掉 route-local `_reopen`，新 attempt 会绕过该步骤。**注释已记录过同形实例**：replayed body 曾因没有重新包 client deadline 而让 2 秒时限运行 6.1 秒。
2. 修改 continuation eligibility 时，streaming 侧的 `ContinuationSupport` 与 buffered 侧的本地 gate 可能漂移，同一个 upstream stop reason 会因请求的 `stream` 开关得到不同结局。

建议把 replay action 与 buffered continuation outcome 收进 pipeline 的 typed orchestration result；route 只解释「返回 buffered body」或「返回已准备好的 streaming delivery」。`_hand_back` 的 request binding 可留在 edge，但不应再是 route 自己决定何时调用的唯一入口。

证据权重：强到足以行动。用户亲写的 `request-pipeline.md` 把模型请求驱动交给 `app.pipeline`，而当前存在 route-local 第二次 `handle` 调用和独立 continuation gate。

### F2（major）：流式生命周期／记账簇属于 delivery execution，而不是 inference route

`_StreamAccounting`、`_AccountedStreamingResponse`、`_counted_upstream`、`_tracked_delivery` 占 `:501-642`，由 `_dispatch` 在 `:298-343`、`:382`、`:430-464` 接线。它们处理 iterator closure、upstream release、terminal facts、exactly-once completion 与 active slot，不解析 route，也不决定 HTTP status。**现有测试甚至从 `tests/unit/pipeline/delivery/test_stream_delivery.py` 跨包私有导入 `_counted_upstream`**——测试归属已经暴露实际职责。

更隐蔽的耦合在 `serve` `:102-106`：它通过 `isinstance(response, StreamingResponse)` 推断「completion owner 已转交给 body」。返回类型仍只是 `Response`，没有结构表达该 response 是否真的携带 accounting owner。未来新增一个普通 `StreamingResponse` 会导致 active request 永不移除；新增一个不继承该类的 streaming response 则会在 body 开始前提前移除并记录 completion。

这四个符号应作为同一 delivery-finalization mechanism 迁出 route，**不能**把 `_StreamAccounting` 单独当 observer 拆走（它还写 `context.reply` 并拥有 finalize action）。若要保持 FastAPI 依赖只在 server，可把 `_AccountedStreamingResponse` 留作极薄 ASGI adapter，但它与 pipeline delivery owner 之间必须有显式 typed ownership contract，而不是靠 `isinstance` 猜。

⚠️ **与 server-layout 5.3 的关系**：那一节已把这块门控在 STR-04 切片之后，落点是 `pipeline/delivery/`（不是 `observability/`，因为 `architecture.md:340` 禁止 observer 关闭 transport）。本发现与之一致，是对同一落点的独立复核。

### F3（major）：同一 upstream body guard stack 手写三遍，顺序与重建要求未被结构表达

`:307-322`、`:383-399`、`:433-450` 分别为 one-shot、replay replacement 和主 block-delivery path 组装近似相同的 iterator：

1. `with_idle_timeout`
2. `with_deadline_at`
3. `_counted_upstream`
4. `with_client_deadline_at`

次序不是装饰性的。`with_deadline_at` 与 idle guard 的外内关系决定哪个错误名能传播；client deadline 必须在 replacement iterator 上重新安装；`_counted_upstream` 的位置决定字节与 pacing 统计看到哪一侧。**三份结构已经产生过一次真实遗漏**：`tests/int/test_pipeline_app.py:3005-3050` 记录 replayed body 在修复前让 2 秒 client deadline 运行了 6 秒。

适合收敛成一个构造「受保护且计量的 attempt body」的 helper／对象，由 delivery execution 同时用于 first attempt、one-shot 和 replacement。**单纯把三段移到另一个文件而不合并，不能消除失效机制。**

证据权重：强到足以行动，已有具名历史缺陷和直接回归测试。

⚠️ **这一条 server-layout 未覆盖**——那份按「职责归属」切，这一条是同一职责内部的三份重复。

### 隐藏顺序耦合与排除项

以下顺序真实存在，但周围注释给出了成立理由，**不应仅凭「有顺序」凑成额外发现**：

- `:138-149` 先 `request.body()` 再 `request.json()`：让 body read 落在 client lifetime 内，并保证 rejection 时 body 已完整读取；Starlette 缓存 body，不是重复网络读取。
- `:267-268` 在 response release 前 snapshot connection：release 后 socket address 可能因 closed fd 无法读取。
- `:469-473` 在追加 synthesized hand-over block 前做 `reply_summary`：让日志描述 upstream 实际产生的内容，而不是把 proxy 合成的 tool call 算成模型行为。
- `_StreamAccounting.finish()` 可能从 `_tracked_delivery.finally` 与 `_AccountedStreamingResponse.__call__.finally` 两处到达；`done` gate（`:521-525`）把双入口结构化为幂等 finalize，**不是重复记账 bug**。真正的问题是整个状态机仍住在 route。
- `_AccountedStreamingResponse.__call__` 先关闭 body 再 finish，并在 close 失败时保留 primary exception（`:576-592`）：资源所有权契约，注释充分。
- `_reopen` 在使用 fresh assembler 后更新 `accounting.assembler`（`:377-382`）：必须的，但也说明 replay、assembler 与 accounting 共享一套未具名的 mutable session；已纳入 F1/F3，不另计。

---

## 最终判断

`composition.py` 不应因 538 行判成 god module。它目前仍以组装为主，`build_chain` 与 provider factory 位置基本正确；应拆的是已形成独立 subsystem 的 transport cluster，以及不属于构造阶段的 `refresh_catalogs`。生产 bootstrap 顺序可用一层 facade 表达，无需污染纯 `build_chain`。

`routes/inference.py` 确实不应长期这么大。它刚从旧 `pipeline_app.py` 原样搬出，当前形态是**重构中间态而非新模块设计失败**；但 `_dispatch` 仍有 HTTP、pipeline action、delivery policy、observability、lifecycle 五种改动理由。`b973ed0` 清除了纯 retry classifier 与 hand-back payload builder，却没有完成 replay execution、buffered continuation 和 delivery-finalization 的归位。**下一刀应按这些职责切，而不是按行数继续机械分文件。**
