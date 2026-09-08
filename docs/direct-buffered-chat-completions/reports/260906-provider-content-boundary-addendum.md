# Provider content boundary addendum：CodeBuddy／Xingchen 的 Chat 内容处理应上移 pipeline

## 1. 本次新增约束与调查范围

本次上游任务明确给定新的架构约束：CodeBuddy 与 Xingchen 都只是 model provider；provider 不得改写 model-protocol payload、强制 `stream`、解析 SSE 或聚合 JSON；所有这类协议内容处理统一属于 `app.pipeline`。

本 addendum 只调查并提出可行设计，不修改源码、测试、Spec 或既有报告。它补充 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260905-direct-buffered-chat-completions-current-implementation.md`，不改写该报告。

调查快照仍为 `f97d243f9431d836861ce5e9938605df56b37478`；写入前，本文涉及的主树源码与隔离快照逐文件比较一致。

## 2. 架构约束与当前模块合同

### 2.1 已有上位边界

- `docs/.human-controlled/request-pipeline.md:3-6` 明确：请求从 server 进入，经 `app.pipeline` 后交给 `app.model_provider`；`app.pipeline` 负责消息变换、上游收发和重试。
- `docs/.human-controlled/module-org.md:15-20` 把 `model_provider` 定义为上游提供方抽象，把模型请求处理管线与客户端交付放在 `pipeline`。
- `src/app/model_provider/base.py:1-6,24-93` 的 `ModelProvider` docstring 也写明 provider 负责 catalog、endpoint能力和发送，不负责格式翻译、alias resolution、retry或routing。
- 本次给定约束把这个边界说得更精确：provider仍可拥有URL、认证、签名、transport和把transport／HTTP异常映射到pipeline闭集，但不能改变Chat payload字段，也不能读取Chat SSE语义或合成Chat JSON。

### 2.2 当前违反点

#### CodeBuddy

`src/app/model_provider/codebuddy_client/client.py:50-87` 当前同时做了四件超出provider边界的事：

1. 复制model-protocol payload并无条件写 `body["stream"] = True`（`:56-60`）。
2. 缺省写入 `stream_options = {"include_usage": True}`（`:61-64`）。
3. 为non-stream caller消费并解析upstream SSE（`:82-87`）。
4. 调用 `aggregate_stream()` 生成新的 `chat.completion` JSON response；该函数在 `:90-191` 解析delta、tool calls、usage和finish reason，并生成新id／created时间。

`src/app/model_provider/codebuddy.py:166-179` 本身只做endpoint gate与delegate，越界集中在provider client。

#### Xingchen

`src/app/model_provider/xingchen/client.py:58-69,77-85` 的 `_prepare_payload()` 在streaming时补 `stream_options.include_usage=true` 与 `tool_stream=true`，随后才序列化和签名。这也是model-protocol payload改写，应上移pipeline。

Xingchen client其余职责可留在provider：URL、provider-owned headers、签名、HTTP发送、response close和transport／status异常归一化（`:84-140`）。签名必须继续基于pipeline已经准备好的最终bytes，而不是基于改写前payload。

#### GitHub Copilot

`src/app/model_provider/ghc_client/client.py:68-128` 对Chat payload只做浅复制用于SDK body并添加认证headers，不强制stream、不注入Chat字段、不解析Chat SSE、不聚合Chat JSON。`src/app/model_provider/github_copilot.py:173-205` 仅分派endpoint。因此GitHub Copilot目前基本符合本次边界。

## 3. “CodeBuddy upstream 只支持 `stream:true`”的证据审计

### 3.1 没有找到真实测量结果

结论：**在当前仓库可审计材料中，没有真实upstream request证明CodeBuddy拒绝 `stream:false`，也没有真实capture证明它只会返回SSE。这个否定性结论足够用于阻止把“streaming-only”继续写成已测事实，但不能证明upstream一定支持non-stream。**

证据如下：

1. `exp/260904-codebuddy-provider/probe.py:1-20` 自称“hand-run, never in the test suite”，并把P6写成负控：`upstream refuses stream:false? (reference claims streaming-only; this is the negative control that proves it)`。也就是说文件作者自己承认当时只有reference claim，仍需P6证明。
2. 同探针 `:141-156` 才真正发送 `stream:false`，并在200时打印“reference claim 'streaming-only' needs rechecking”。当前 `exp/260904-codebuddy-provider/` 只有 `probe.py`，没有 `raw/` 结果。
3. 引入提交 `fcb6982cc4c9dcfa26eb4c82b3ecc764dc1a784d` 的提交信息一方面写“upstream has no non-streaming mode”，另一方面明确写“exp/260904-codebuddy-provider probe for live verification (not yet run)”。前一句因此是设计假设，不是本次提交已完成的实测结论。
4. 人控 `docs/.human-controlled/` 中没有CodeBuddy／WorkBuddy条款；`.dev/docs/` 中也没有一份带真实请求／响应的CodeBuddy专属调查报告或cassette。
5. 提交信息称参考 `refs/codebuddy2api`，但该路径在当前working tree和当前仓库全部可达Git object中都不存在，无法复核其原文。

证据权重：**强到足以判定“尚未实测”，不足以判定upstream支持或不支持 `stream:false`。**

### 3.2 现有证据来自参考实现行为

- 当前CodeBuddy client docstring `src/app/model_provider/codebuddy_client/client.py:1-10` 的原话是“measured by the reference converter, which always sends `stream:true`”。“参考实现总是发送true”只能证明参考实现的选择，不能测出服务端对false的响应；这里把“观察客户端实现”误写成“测量upstream能力”。
- 当前component test `tests/component/model_provider/codebuddy_client/test_codebuddy_client.py:60-73` 名为 `test_the_wire_always_streams`，只断言本实现把outbound body改成true。它是当前实现回归测试，不是upstream capability test。
- 外部参考 `/home/xp/src/refs/CLIProxyAPIPlus/internal/runtime/executor/codebuddy_executor.go:87-183` 的non-stream `Execute()` 在 `:106-111` 也将request翻译后强制 `stream=true` 和 `stream_options.include_usage=true`，随后在 `:166-182` 读完整SSE、聚合并翻译给client。这是第二份“客户端选择如此实现”的证据，仍没有发送false的control。
- 前身 `/home/xp/src/copilot-api-js` 没有CodeBuddy capability证据；它能提供的是provider-agnostic buffered sink结构，而非CodeBuddy服务端约束。

证据权重：**中等强度的兼容性提示，不能作为协议能力事实。** 两份独立客户端都选择streaming，说明该选择值得实测；它们没有排除non-stream可用。

### 3.3 当前代码注释与测试的地位

代码注释、测试名和提交信息三者都来自同一实现切片 `fcb6982`，并非三份独立证据。它们可靠地证明“当前代码有意强制stream”，但不能把同一个未验证假设重复三次后升级为真实测量。

## 4. 决策前置：先跑现成P6负控

在设计中固化 `requires_streaming=True` 之前，最小且鉴别力最高的事实收集是运行 `exp/260904-codebuddy-provider/probe.py` 的P6并保留脱敏raw结果：

- 若 `stream:false` 返回正常Chat JSON，则最小正确处理不是“把force-stream和aggregation上移”，而是删除这两种行为，让pipeline按client请求的模式发送，provider纯转发。此时只需把CodeBuddy现有实现恢复到边界内。
- 若 `stream:false` 被明确拒绝、返回SSE、挂起或表现出其它不兼容，则需要pipeline拥有“该target只能以streaming方式调用”的已验证capability，并在pipeline内做模式适配。
- 单次结果足以决定当前deployment／model的实现方向，但若能力可能按model或account变化，capability应按route选中的descriptor／target记录，而不应写成全局provider-name分支。

本任务没有被授权发起真实CodeBuddy调用，也没有可复用的capture，因此没有运行P6。

## 5. 最小正确接缝

### 5.1 推荐形状：Chat attempt adapter，位于shared retry loop内

最小正确位置是 **pipeline-owned、endpoint-specific、provider-agnostic 的 OpenAI Chat attempt adapter**。它应由 `OpenAIChatCompletionsDriver` 使用，但不能按 `provider.name` 分支。

当前可插入点非常明确：

- `src/app/pipeline/direct_driver/base.py:287-325` 的 `_prepare_and_send()` 已在每次attempt内生成私有final payload、完成admission与rate-limit wait，最后调用 `_send()`。
- `src/app/pipeline/direct_driver/base.py:327-342` 的 `_run_attempt()` 用整个attempt deadline包围 `_prepare_and_send()`。
- `src/app/pipeline/direct_driver/base.py:344-420` 的 `run()` 只有在 `_run_attempt()` 返回后才写status、运行rate-limiter response处理并发布 `attempt.succeeded`／`request.succeeded`；此前抛出的已归一化异常会进入 `_handle_failure()` 和共享ledger。
- `src/app/pipeline/direct_driver/base.py:462-489` 的 `_send()` 内层 `response_header_timeout` 只应覆盖取得headers，不能因移动aggregation而扩大到整个body。

因此正确顺序是：

1. attempt私有payload生成完毕。
2. Chat adapter根据标准化target capability准备最终Chat payload和独立的 `upstream_stream` transport mode。
3. provider按原样发送该payload；provider只持有URL／auth／signing／transport。
4. `_send()` 的response-header timeout在headers返回时结束。
5. 若client要求non-stream而target要求streaming，Chat adapter在 `_run_attempt()` 的外层attempt deadline内消费SSE、验证terminal并生成Chat JSON。
6. 只有适配成功后，`DirectDriver.run()` 才发布success events并把response交给server。
7. body transport error在adapter边界经现有 `normalize_upstream_error()` 变成 `UpstreamError`；Chat parser自身bug或其它未知异常保持未知并abort，不能伪装成upstream retry。
8. 原response在成功、失败、retry与cancellation路径都由adapter关闭；重试前不得留下占用连接。

这个位置同时满足四个条件：内容处理在pipeline；Chat逻辑不依赖provider类型；aggregation失败仍在attempt retry owner内；response-header timeout与whole-attempt deadline不被混为一个时钟。

### 5.2 Capability如何进入adapter

pipeline需要知道“target是否必须streaming”和“streaming Chat请求应补哪些标准字段”，但不能通过 `if provider.name == "codebuddy"` 判断。推荐将其建模为标准化的Chat endpoint profile，并让routing把快照带进 `Route`／`ModelDescriptor`，例如表达以下语义而非具体provider名字：

- target是否只接受streaming response；
- streaming时是否需要缺省 `stream_options.include_usage=true`；
- 是否支持或需要Chat extension `tool_stream=true`。

provider可以像今天提供endpoint、reasoning effort和token limit那样声明capability数据；解释capability并改写payload的是pipeline。`Route` 已携带routing选中的immutable descriptor（`src/app/pipeline/routing.py:60-77,333-345`），`_drive()` 又把同一descriptor交给driver（`src/app/pipeline/driver.py:250-280`），所以无需在send时第二次查询provider或按名称分派。

这组字段的最终schema仍需设计评审；“profile由route携带、pipeline解释”这一归属判断证据强，具体放在 `ModelDescriptor` 还是独立 `EndpointProfile` 的证据只够形成推荐，不够冒充既定接口。

### 5.3 Chat内容组件放在哪里

- `src/app/pipeline/delivery/formats/openai_chat_completions.py:51-154` 已有 `ChatCompletionsAssembler`，能读delta、`finish_reason`、`[DONE]`、usage和in-band error。
- 它不能直接拿来生成direct Chat JSON：它把stop reason和usage转换到Anthropic语义（`:112-116,149-153`），把内容变成 `CompletedBlock`，并不保存所有Chat原生字段。直接从它渲染会扩大当前aggregation的损失并违反“直连尽可能原样”。
- `src/app/pipeline/translation_driver/openai_chat_completions.py:295-345` 的 `from_chat_completions_response()` 同样是Chat→IR reader，适合translated response，不适合direct native output。

推荐在pipeline的Chat协议模块中抽一个共享的、provider-neutral stream state／observer：它至少给出terminal是否见过、in-band failure、choice／usage原始事实；translated `ChatCompletionsAssembler` 和non-stream aggregation从同一解析事实投影，但direct wire不经Anthropic `CompletedBlock` 反向生成。第一步若只搬迁当前 `aggregate_stream()` 也能满足模块边界，但必须明确那只是行为等价迁移，不是已经消除重复parser或改善fidelity。

## 6. 可行方案

### 方案A：先实测，确认需要后采用endpoint profile + Chat attempt adapter（推荐）

- P6证明 `stream:false` 是否真的不可用。
- profile只描述标准化Chat target capability，不携带provider可执行代码。
- `OpenAIChatCompletionsDriver` 通过pipeline adapter准备payload与mode，并在attempt success前完成必要aggregation。
- provider clients删除payload rewrite／SSE parser／JSON aggregator，仅发送最终payload并返回raw response。

优点：满足新架构约束；复用现有retry ledger、attempt deadline、admission、draining和success事件边界；GitHub默认行为可保持不变；CodeBuddy body tear自然进入正确retry位置。

代价：需要给route／descriptor增加一个小的标准化capability面，并迁移CodeBuddy／Xingchen现有测试所有权。

证据权重：**高置信推荐。** 接缝由现有调用时序唯一约束；具体profile字段需在实施设计中收口。

### 方案B：先以显式配置提供Chat target profile，再等待真实测量

把 `requires_streaming`、usage和tool-stream策略作为配置中的Chat endpoint profile，由composition编译后交给pipeline；provider不解释它。

优点：不会把未经验证的CodeBuddy能力写进静态model descriptor；可让operator按account／deployment纠正。

代价：把本应可自动发现或由provider catalog声明的事实交给operator；配置面扩大；若后续实测表明能力稳定，还要迁移来源。

证据权重：**可行的过渡方案，中等推荐。** 适合必须立即维持当前force-stream行为、又不能宣称它是已测能力的情况。

### 方案C：pipeline对所有OpenAI Chat target一律 `stream=true`，non-stream一律聚合

优点：无需capability字段，代码路径最少。

代价：会无依据地改变GitHub与Xingchen的请求／响应模式、首字节与总时延、headers、错误时点和成功body；还会把原本native JSON变成pipeline合成JSON，扩大direct passthrough损失。

证据权重：**技术可行但不推荐。** 它用统一实现替代了真实能力差异，违反最小行为影响原则。

## 7. 对各路径的行为影响

### 7.1 CodeBuddy

若streaming-only得到实测确认：

- direct／translated、client non-stream：pipeline将final payload设为streaming，provider原样发送，pipeline在attempt内聚合成Chat JSON；行为目标可与当前输出保持一致，但body tear会正确进入retry，terminal缺失不会再静默伪装成success。
- client stream：pipeline发送streaming payload，provider返回raw SSE；现有server delivery路径不因本次迁移自动改变。
- provider保留 `/v2/chat/completions`、auth state、headers、HTTP transport与status normalization；移除protocol payload和response内容逻辑。

若P6证明non-stream可用：删除force与aggregation，让provider按pipeline给定的false发送，是更小且更保真的方案。

### 7.2 Xingchen

- 当前streaming payload的 `stream_options.include_usage`／`tool_stream` 默认注入从 `XingchenClient._prepare_payload()` 移到Chat pipeline profile。
- explicit client值必须继续优先；`tests/unit/model_provider/xingchen/test_client.py:155-183` 当前固定了这一语义。
- non-stream不注入这些字段的行为应保持；当前测试位置是 `:186-209`。
- provider收到final payload后序列化并签名；签名必须覆盖pipeline最终payload。HTTP path、auth headers和transport error normalization不变。

### 7.3 GitHub Copilot

- 采用中性默认profile时，payload与stream mode都不变：non-stream仍走SDK buffered JSON，stream仍返回raw SSE。
- 不应因为CodeBuddy的未经验证假设而让GitHub全量改走stream+aggregate；那会降低direct fidelity并改变failure timing。
- production SDK `max_retries=0` 仍保留，retry继续由pipeline统一拥有。

### 7.4 Direct passthrough

- 对原生支持client所请求mode的target，direct路径继续尽可能原样：payload不额外改写，streaming response保持raw one-shot，non-stream JSON保持现有server投影。
- 对经实测确认为streaming-only、而client要求non-stream的target，request mode和response representation必然要适配。该路径仍是同一Chat wire format、`translation_required=False`，但不应再被描述成byte-level passthrough；应在attempt／observation中单独记录mode adaptation，而不是滥用translation flag。
- 当前CodeBuddy aggregator会丢未知choice字段、logprobs、provider id／created等并生成新值。把它上移pipeline只修正ownership与retry，不自动提升fidelity；若要扩大字段保真，必须作为单独行为设计。
- client `stream=true` 的direct Chat仍走 `one_shot_delivery()`，仍无post-header replay。provider内容上移不会顺带修复这一项；它可复用同一个Chat terminal observer，但必须按现有direct passthrough／retry Spec另行接线。
- direct buffered Chat reply summary／provider observation为空也是独立问题；共享Chat observer可成为共同事实源，但不能把三个切片绑成一个大改动。

## 8. 错误与重试语义

1. adapter必须在 `_run_attempt()` 内完成aggregation，否则body failure已经越过driver retry owner。
2. adapter必须在 `_send()` 的response-header timeout之外完成aggregation，否则“等headers多久”会被错误扩大成“整轮body多久”；outer attempt deadline和client deadline仍覆盖它。
3. transport body error先经过既有 `normalize_upstream_error()`；只有得到 `UpstreamError`／`UpstreamTimeout` 才进入shared retry taxonomy。parser bug、`KeyError`等未知异常继续abort。
4. clean EOF／缺terminal不是transport exception，需要Chat observer产生一个pipeline-owned、可分类的“unterminated upstream response”结果；当前是否retry由已有用户retry合同与待同步Spec决定，不能继续补成 `stop`。
5. retry replacement必须重新执行pipeline request preparation，或复用第一次已经冻结的final payload；不能让provider重新改写，也不能重复叠加 `stream_options`／`tool_stream`。
6. 每个失败response在下一attempt前关闭；CodeBuddy non-200 `aread()` 目前不在finally中的资源缺口也应随ownership迁移一并消除。

## 9. 测试所有权迁移

- `tests/component/model_provider/codebuddy_client/test_codebuddy_client.py:60-154` 中“wire always streams”和SSE aggregation测试不再属于provider component；应迁到pipeline Chat adapter tests。provider component应改为断言传入什么payload／stream mode，就发送什么并返回raw response。
- `tests/unit/model_provider/xingchen/test_client.py:101-180,186-209` 中stream extension注入断言应迁到pipeline；Xingchen provider test只断言最终bytes被正确签名并原样发送。
- 新增一条production wiring测试：CodeBuddy profile、direct `/chat/completions`、client `stream:false`，第一次upstream SSE body tear、第二次完整，断言两次attempt且client只见第二次聚合JSON。
- 增加控制：同一pipeline adapter下GitHub／Xingchen neutral profile的non-stream payload与response模式不变；client `stream:true` direct Chat仍保持raw SSE one-shot。
- terminal tests至少区分 `[DONE]`／非空 `finish_reason`、clean EOF、in-band error、malformed frame与transport exception，且断言unknown local parser bug不消费upstream retry budget。

## 10. 排除项及原因

1. **继续把force-stream／aggregation留在CodeBuddy provider，只在外层补catch。** 排除：即使retry恢复，也继续违反本次架构约束，并让Chat内容逻辑无法被Xingchen／GitHub或translated routes复用。
2. **把aggregation移到server的buffered response分支。** 排除：`DirectDriver.run()` 已经发布success并退出，body failure无法回到同一attempt ledger；server还会被迫理解provider target mode。
3. **只放进translation driver。** 排除：direct `/chat/completions` 的 `translation_required=False`，根本不调用translator；该方案在目标路径上仍是死代码。
4. **在pipeline中按 `provider.name` 或provider class分支。** 排除：只是把provider耦合换了目录，新增provider仍要改Chat执行器；正确输入是标准化capability／profile。
5. **所有Chat upstream一律强制streaming。** 排除：无证据要求GitHub／Xingchen付出同样的payload、latency、header与fidelity变化。
6. **直接拿 `ChatCompletionsAssembler` 的 `CompletedBlock` 反向生成direct Chat JSON。** 排除：它主动映射到Anthropic stop／usage／block语义并丢失未知Chat字段，适合translated delivery，不是native aggregation的无损中间态。
7. **把“参考实现总是发true”记为“upstream实测只支持true”。** 排除：没有发送false的control；仓库自己的P6正是为了补这条证据，而且明确尚未运行。
8. **用当前 `test_the_wire_always_streams` 作为产品合同。** 排除：测试只固定实现行为；它没有upstream参与，不能证明该行为必要。
9. **因为上移内容处理，顺手重写direct streaming one-shot、reply observation和所有Chat fidelity问题。** 排除：三者可共享parser事实，但行为合同和failure frontier不同；绑成一个切片会把架构迁移扩大成多项产品变更。

## 11. 结论与证据权重

1. **强到足以行动**：CodeBuddy与Xingchen当前确实在provider层修改model-protocol payload；CodeBuddy还解析SSE并聚合JSON，违反本次明确边界。
2. **强到足以纠正文案、但不足以决定能力**：仓库没有CodeBuddy `stream:false` 的真实测量；“streaming-only”来自参考实现行为、代码注释和同源测试，P6负控明确未运行。
3. **高置信设计判断**：如果streaming-only被实测确认，最小正确接缝是pipeline的OpenAI Chat attempt adapter，置于response-header send之后、attempt success之前，并由标准化route／descriptor capability驱动。该位置保留shared retry、deadline、draining和cleanup语义。
4. **中等置信接口判断**：capability最好由route携带的endpoint profile表达，而非provider-name分支；具体落在 `ModelDescriptor` 还是独立profile仍需实施设计收口。
5. **明确非结论**：本报告不证明CodeBuddy真实upstream支持或拒绝non-stream，不决定terminal必须同时见 `finish_reason` 与 `[DONE]`，也不授权改变direct streaming最终failure carrier。
