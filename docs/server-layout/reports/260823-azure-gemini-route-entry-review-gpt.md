# Azure 与 Gemini 路由入口评审

## 结论

**Verdict：needs-fix。** 共发现 `blocker=0`、`major=2`、`minor=1`、`nit=2`。两个 major 都与本次明确要求核查的路由边界和测试鉴别力有关：Gemini 路由当前把合法集合写成了 catch-all；Azure「未挂 OpenAI 前缀」测试则可能在路由已经错误挂载时仍因另一处 lookup 失败而保持绿色。

评审快照为主仓 `HEAD=e2cb70b87d5028d15839061dfa9bdc5ab2d68838` 上指定 6 个文件的未提交 diff。评审期间共享分支的 `HEAD` 曾前进，但复核时受审 diff 仍为 6 个文件、156 insertions、11 deletions；下述结论以该复核时点为准。

方法说明：已按要求首先调用 `my-skills:as-reviewer`，但当前 harness 返回 `Unknown skill`；随后按 `verifying-authoritative-claims` 与 `trusting-a-green-result` 的方法核对用户亲笔文档、当前源码、归档实现、生产入口和黑盒行为。未修改任何被评审源文件。

## 发现

### F1——Gemini catch-all 把未追认的路径也当成已实现入口

- 严重度：`major`
- 把握程度：高，证据强到可直接修改。
- 位置：`src/app/server/routes/table.py:58-63`、`tests/int/test_pipeline_app.py:958-968`。
- 问题：`/v1beta/models/{model_and_method}` 只约束「一个非空 path segment」，并没有约束 `:{generateContent|streamGenerateContent|countTokens}`。因此它不只是覆盖 `api.md:10` 的三条端点，还会把没有冒号、空模型、未知 method 的任意单段 `POST` 路径交给 `_dispatch` 并返回 501。黑盒探针在当前生产路由上得到：`POST /v1beta/models/gemini-pro:unknownMethod` → 501、`POST /v1beta/models/gemini-pro` → 501、`POST /v1beta/models/something-else` → 501；只有多一个 `/extra` 的路径才是 FastAPI 404。这与用户亲笔 `api.md:10` 列出的有限 method 集合不一致，也让生成的 OpenAPI 表面声明了比合同更宽的入口。
- 测试为何没发现：新增测试只枚举三个合法 suffix；三个字符串都只是同一个 catch-all 的正样本。即使把其中任何一个 suffix 改成 `unknownMethod`，测试仍会拿到 501，所以它没有证明 method 集合被路由约束。
- 将来冲突：如果以后把一个新的单段 `POST /v1beta/models/...` 路由追加在该 catch-all 后面，当前泛化路由会先匹配并返回 501；只有把新路由插到它之前才能避开。这个冲突是有条件的未来风险，但当前对未知路径返回 501 已经是可复现的现存行为。
- 可执行建议：把三条入口显式注册为 `/v1beta/models/{model}:generateContent`、`/v1beta/models/{model}:streamGenerateContent`、`/v1beta/models/{model}:countTokens`，当前都可继续设置 `implemented=False`。FastAPI 小型探针确认这种模板能把 `vendor:family:model` 完整捕获为 model，同时让无冒号和未知 method 返回 404。补两个负例即可：无 method 与未知 method 都应为 404；保留三个合法 method 的 501 正例，并保留一个 model 内含冒号的正例，避免修边界时误伤现有 `parse_model_with_method` 支持的模型名。

### F2——「Azure 未挂前缀」测试会因 `_BY_PATH` 缺项而假绿，未覆盖两处规则失配

- 严重度：`major`
- 把握程度：高，已用不改源文件的生产入口探针复现。
- 位置：`tests/int/test_pipeline_app.py:943-956`、`src/app/server/routes/router.py:20-28`、`src/app/server/routes/table.py:66-71`、`src/app/server/routes/inference.py:141-146`。
- 问题：测试名和 docstring 声称验证「路由没有挂载」，但断言只有 HTTP 404 与 `seen == []`。若 `build_router` 错误注册了 `/v1/openai/deployments/{deployment}/responses`，而 `_BY_PATH` 仍不知道该模板，请求会真实进入 `serve`，随后由 `_dispatch` 的 defensive branch 返回同样的 404 且不访问 upstream；现有两条断言全部通过。评审探针向真实 app 额外挂入这个错误模板而不改 `_BY_PATH`，实际得到 `registered_template=/v1/openai/deployments/{deployment}/responses`、HTTP 404、body 为 `{"error":{"message":"unknown endpoint"}}`、upstream requests 为 0，正好满足当前测试。
- 变异证据的边界：`mutate.py` 的第一个变异把同一个 `InboundRoute.openai_prefixed` 改成 `True`，所以 `build_router` 与 `_BY_PATH` 会一起改变，测试当然会打红；它不能辨别「两个消费者只有一个漏改」这一历史上已经发生过、且本次明确要防的失配。
- 当前实现状态：当前快照里的两套展开规则在现有表上确实一致。运行时枚举得到 registered POST templates 为 15 条、可由 `route_for_path` 找到的对应 templates 也是 15 条，双向差集均为空。发现针对的是测试不能守住这一事实，而不是声称当前已有 split-brain。
- 可执行建议：把「是否挂载」直接断言在 `build_router().routes` 的 POST template 集合上，并把 `route_for_path` 对两个非法前缀返回 `None` 作为独立断言；不要用一个最终 404 同时替代两层事实。更稳妥且改动仍很小的做法是提取一个 `expanded_paths(route)`，让 router 和 lookup 共用同一展开函数，再保留一条结构测试检查已注册 template 集合与可 lookup template 集合相等。这里不需要新建验证框架。

### F3——Azure 注释把已核实的 adapter 事实扩大成了整条旧链的事实

- 严重度：`minor`
- 把握程度：高，当前归档源码可直接裁决。
- 位置：`src/app/server/routes/table.py:41`。
- 问题：注释称 model substitution 是「the whole of what the chain this replaces did for these three」。可核实的窄事实是 `src/.archived/app/protocols/azure.py:12-20` 中的 `adapt_azure_payload` 除深拷贝外只执行 `wire["model"] = deployment`；但旧 Azure route 还做 endpoint-specific Pydantic validation、approval guard、history、上游调用和响应处理，见 `src/.archived/app/routes/azure.py:55-141`。新链可能已经用通用组件接替其中多项，但「旧 adapter 只做一项 Azure-specific reshape」不能扩写成「旧 chain 只做这一项」。这条理由会误导下一位维护者判断迁移完整性。
- 可执行建议：改为「The old `adapt_azure_payload` performed no Azure-specific wire transformation beyond copying the body and setting `model` from `deployment`; the shared pipeline owns the remaining behavior.」若要声称 remaining behavior 已逐项接替，应另列对应 owner，而不是把它藏在「whole」中。

### F4——几处说明把协议习惯与 HTTP 404 语义写成绝对事实

- 严重度：`nit`
- 把握程度：高，文本与本次测试本身即可交叉核对。
- 位置：`src/app/server/inbound.py:42`、`src/app/server/routes/table.py:41`、`src/app/server/routes/inference.py:151`、`src/app/server/routes/table.py:58`、`tests/int/test_pipeline_app.py:960`。
- 问题：两处称 Azure body「carries no model at all」，但新增的 `test_the_deployment_in_the_path_wins_over_a_model_in_the_body` 明确把携带冲突 model 的 body 当作支持场景；准确事实应是 Azure-compatible body 可以不带 model，且 URL deployment 在带与不带 body model 时都具有权威性。另三处把 404 解释成「never」也过强；HTTP 404 表示当前未找到资源或不愿披露，并不表达永久性，永久性更接近 410。选择 501 仍然合理，成立的理由是它明确表达「该已登记能力尚未实现」，而 404 会与未注册路径同形，不是 404 本身承诺「永不提供」。
- 可执行建议：把前者改为「may omit `model`; the deployment path is authoritative」，把后者改为「would be indistinguishable from an unregistered endpoint」或「would report the registered endpoint as not found」。

### F5——新增测试文件末尾多出空白行

- 严重度：`nit`
- 把握程度：高，工具直接报告。
- 位置：`tests/unit/server/test_server_inbound.py:126`。
- 问题：`git diff --check -- src/app/server tests/int/test_pipeline_app.py tests/unit/server/test_server_inbound.py` 以 code 2 退出并报告 `new blank line at EOF`。
- 可执行建议：删除额外空白行，保留文件末尾单个 newline，然后重跑同一条 `git diff --check`。

## 重点问题的确认结果

### Azure 不需要 stub

已确认，结论强到可据此继续。三个 OpenAI wire format 都有 active direct driver；旧 `adapt_azure_payload` 的唯一 Azure-specific wire 改写确实是把 deployment 写入工作 payload 的 `model`。新增参数化集成测试逐条走过 chat completions、Responses 与 embeddings，并断言实际出站 bytes 中的 model 和 upstream endpoint，足以区分「仅路由成功」与「deployment 真正成为 model」。上述 F3 只要求收窄注释，不推翻实现选择。

### Gemini 返回结构化 501，并在 JSON parse 前拒绝

已确认，结论强到可据此继续。`TranslatorNotFound` 当前由 `error_status` 映射为 400，因此让未实现格式落入 pipeline 会错误归类；`implemented=False` 在 `request.json()` 前返回 501，非法 JSON 正例证明了 parse 没发生。要精确区分的是 `_dispatch` 仍先执行 `await request.body()`，所以成立的是「解析前返回」，不是「读取 body 前返回」；当前注释没有越过这条边界。F1 要求收紧哪些 URL 能到达该 501，不反对合法三条路径返回 501。

### `build_context` 中写入 `working["model"]`

保留是合理的，现有单元层断言足够支撑它声明的 `RequestContext` 不变量。直接 Azure happy path 的最终 upstream model 的确会被 `driver.py:128` 再次写成 resolved model，所以集成层不能单独证明 `working["model"] = model.strip()`；这不是测试缺陷，而是该行为的可观察层就是 `build_context` 产出的 context。单元测试同时钉住 `requested_model`、working payload、`original_payload` 和调用方 body 四个面，且集成测试另行证明 `_dispatch` 真把 `request.path_params` 送进该函数。不要为了让集成测试“看到”这一行而增加只供测试的生产行为。该行也让翻译前的 working payload 表达完整客户端意图，即使当前 driver 会在翻译后再次规范化 model。

### `openai_prefixed` 的当前两处读取

当前实现一致，结论只对上述评审快照成立：两处都以同一个 field 为开关、都使用 `OPENAI_PREFIXES`、都包含空前缀的原始路径，现有 15 条 inference POST template 双向无差集。F2 指出的是这项一致性尚未由现有负例独立守住。

### 范围完整性

Azure 三条已全部显式登记并分别经过参数化 happy-path 请求。Gemini 三个合法 method 字符串都能到达 501，未遗漏 `streamGenerateContent` 或 `countTokens`；但 F1 所述 catch-all 使这份正向覆盖无法证明集合边界。Gemini 的实际处理仍未接入新链，`implemented=False` 与响应都把这一点明示出来，没有把未实现伪装成 400。验收后还应及时把 `.dev/docs/server-layout/status.md:45` 从「Azure、Gemini 无人服务」更新为「Azure 已服务、Gemini 路由已登记但处理返回 501」；当前是未提交评审阶段，本报告不把尚未同步活文档另计为 finding。
