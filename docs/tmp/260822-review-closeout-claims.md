# 收尾终态声称独立核查

## 核查锚点与结论

- 核查对象：主仓提交 `a2169de`、`80068eb`、`959e8d1`，`.dev` 提交 `0ca6da8`、`41e98ef`、`2ab949a`，当前主工作树，以及实现报告 `.dev/docs/hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`。
- 权威需求：`docs/.human-controlled/message-format-reshape.md`，只读。
- 主仓阅读时 HEAD：核查开始为 `81c36d2b31313c0d085c581ba22e4d5ffa17ccd4`；并行会话在核查期间提交，最终复核锚点为 `14593204a207e70b9d515d4927a64fe364af122f`，时间 `2026-08-22T16:13:31+00:00`。
- `.dev` 最终复核 HEAD：`58663b50bd8c1b86ccc8bcd6cb246644508f7e42`。目标实现报告最后一次改动仍是 `cb472f7`，工作树无该文件的未提交改动，核查时 SHA-256 为 `398e6528e8d13488ac30381944f338051650c45574b1052a430e0ac7c47a08f5`。
- 共享树限定：最终锚点下，相关脏文件为用户亲笔 `message-format-reshape.md`，以及同伴正在改的 `server/handler.py`、`server/pipeline_app.py`、`tests/int/test_pipeline_app.py`。后面三者的未提交差异分别位于 retry drain、reopen drain 和相应测试，不改动本报告核查的 `shape_request`、attribution 接线或请求头测试段。
- 总结论：**实现的七条裁决和凭据修复在当前主工作树上成立，未发现功能性 blocker；但实现报告不能作为可信的终态交接件，它保留了多处与裁决后代码正面相反的现时态结论，且翻译腿测试把 header 缺席错误归因给 beta strip。结论为 `needs-fix`。**
- 证据权重：代码与运行探针结论为“强，足以据此行动”；关于活跃嵌套 worktree 将来是否会被整合，只能支持“存在回归入口”，不支持断言它必然进入 `main`。

## 分级发现

### Blocker

无 blocker。当前实现没有阻止本次核查完成的权限、文件或工具缺口，也没有发现七条裁决在生产主链上失效。

### Major 1：实现报告同时声称“正文已是裁决后终态”和三组相反的裁决前终态

实现报告 §0 明说“代码与本文都已按裁决改写”“下文正文以裁决后的形态为准”，但当前文件仍有下列现时态反结论：

- §4 写 `strip_attribution_header`“仍是空转开关”，并说刻意保留；当前 `StripRequestHeadersHook` 已无该字段。
- §4 写 `config/loader.py` docstring 仍过时且未改；当前该 docstring 已改。
- §4 写旧文档名还有 6 处断链未改；当前主提交态和主工作树均为 0 处。
- §7 写 major-1 已改成 requested ∪ resolved；当前 `shape_request` 只把 `context.resolved_model` 交给 `strip_denied_beta_flags`。
- §7 写翻译腿不转发 `anthropic-beta`“未改行为”；当前 `apply_path_header_policy(..., translated=True)` 使用空白名单，确实已改为不转发。
- §7 写保留 `strip_attribution_header`；当前已删除。
- §3.1 与 §3.2 仍列裁决前的 union／canonical 测试名，例如 `test_the_table_fires_on_the_alias_the_client_asked_for`；当前测试名和断言已经是 `test_the_table_is_keyed_on_the_model_the_attempt_is_sent_to` 与 `test_a_table_keyed_on_an_alias_does_not_fire`。
- §3.4 还写“把 `models=` 换回单 `resolved_model`”，但裁决后的函数已经没有 `models=` 参数；该句无法对应当前代码或一次可复现的当前变异。
- §4 的“不支持通配，若加通配还需决定哪条键赢”也是裁决前残留；当前键已经是 regex，`.*` 可表达宽匹配，而且 first-match-wins 已经裁定并实现。

具体失败场景：下一位维护者把该报告当终态权威，可能据 §7 恢复 requested ∪ resolved，或据 §4 重新保留已删除开关，直接逆转用户裁决；也可能把已经完成的断链修复与 loader 更新重复列为待办。该问题不是措辞瑕疵，而是同一交接件给出两套互斥终态。

### Major 2：翻译腿测试和报告把 `anthropic-beta` 缺席错误归因给 beta strip，判据不能证明它声称证明的路径

当前真实顺序是 `shape_request` 先执行 `apply_path_header_policy`，再执行 `strip_denied_beta_flags`。翻译腿的 whitelist 为空，因此第一步已经把 `context.client_headers` 变成 `{}`；第二步看不到 `anthropic-beta`，只能 no-op。

然而当前 `tests/int/test_pipeline_app.py::test_the_strip_applies_on_the_translated_path_too` 的名称和 docstring 仍写“while the header does travel, the strip travels with it”，并声称 `forwarded_client_headers` 会把它送往 `/responses`。这与现代码相反。实现报告 §3.2 也把该测试列作 beta strip 的翻译腿接线证据。

受控变异证实了这个分辨力缺口。用最终锚点 HEAD 的 `git archive` 建 `/tmp/beta-strip-discrimination.EaIqiQ`，只在隔离副本把 `shape_request` 的 beta strip 调用替换成 `stripped_flags = ()`；运行时以 `handler.__file__` 和 `inspect.getsource` 确认加载的是该变异副本。结果：翻译腿测试仍为 `1 passed`，直连 beta strip 测试按预期变红，看到未剥的完整 header。正反对照排除了“变异没加载”和“整个 harness 没跑”的解释。

具体失败场景：删除翻译腿上的 `strip_denied_beta_flags` 调用而保留空白名单，这条测试仍会通过，因为它观测到的 header 缺席由路径白名单造成。它能证明“翻译腿最终不发 `anthropic-beta`”，不能证明“beta strip 在翻译腿起作用”。当前产品行为是对的，错误在测试命名、docstring 和报告的因果归属。

### Minor 1：删除 schema 开关后，`strip_attribution_lines` docstring 仍声称该开关存在

`app.pipeline.anthropic_request_hook.strip_attribution_lines` 当前 docstring 仍写 `hook_strip_anthropic_request_headers.strip_attribution_header exists in the schema`。这与 `StripRequestHeadersHook` 当前定义及裁决 2 相反；行为本身仍常驻并接线，不受影响。

具体失败场景：维护者会误以为存在一个可配置但故意不读取的开关，进而把正确的常驻行为当成“配置空转缺陷”再次处理。

### Minor 2：`config/loader.py` 已更新且事实正确，但相邻权威代码说明 `config/loading.py` 仍反向声称 `--fd` 走旧 `AppSettings`

`app.config.loader` 的新模块 docstring逐句核对成立：`--fd` 经 `_load_spec_config` → `ProxyConfig` → `serve_inherited`，`load_settings` 在 `src/` 只有 `app.config.__init__` re-export，没有生产调用方，旧 `AppSettings` 链仍存在但不被新链读取。

但 `app.config.loading` 的模块 docstring 仍写它只供 direct-run，且 `app.config.loader` 为 `--fd` 加载 `AppSettings`。该句与 `cli.start`、`serve_inherited` 和刚更新的 `loader.py` 互相矛盾。

具体失败场景：从真正的新 loader `app.config.loading` 入口阅读代码的人，仍会得到 `--fd` 使用旧 schema 的错误结论；两份相邻模块说明无法共同作为当前事实来源。

### Minor 3：主提交态无旧文档名残留，但活跃嵌套 worktree 仍有 8 处，报告的“全仓无残留”量词过宽

`git grep -F message-format-sanitize HEAD` 为 0，排除嵌套 worktree后的主工作树 `rg` 也为 0；提交 `80068eb` 确实修了主线 8 处：`anthropic_request_hook.py` 4、`pipeline_app.py` 1、`test_pipeline_app.py` 1、`test_attribution_stripping.py` 2。

但是从仓库根递归全扫会在活跃 worktree `.claude/worktrees/delivery-keepalive` 命中 8 处。该 worktree 由分支 `proxy-priority-on-httpx2` 使用，HEAD `8703cad8b700d3714321b1433061e28b73c47df5`，不是无关缓存。

具体失败场景：若该分支以后以其旧文件版本整合，旧引用会重新进入主线。当前 `main` 没有断链，不能把这条写成当前主线功能缺陷；需要把报告量词收窄为“当前主提交态／主工作树无残留”，并在分支整合前处理其 8 处旧引用。

### Minor 4：报告仍有若干可机械核对的事实错误

- §0 表格写“6 处断链”，§2.5 和真实提交都是 8 处。
- §2.1 写 `AppSettings.beta_strip_headers`；真实符号是 `AnthropicConfig.beta_strip_headers`，通过 `AppSettings.anthropic.beta_strip_headers` 挂入旧 schema。
- §3.1 写单元 14 条，§3.4 写裁决后单元 26 条；当前 `tests/unit/pipeline/test_client_request_headers.py` 有 27 个测试，其中 `959e8d1` 新增的大小写测试使 26 变 27。历史时点数字可以保留，但必须带提交锚点，不能作为当前数。
- §0 的第 4 条把问题指向 §7；§7 只保留旧评审处置和 gate 的部分观察，没有完整回答该测试“在做什么”。

具体失败场景：数量与符号名被后续审计或自动定位直接采用时，会漏查两个引用、定位到不存在的字段，或误判测试集合是否变化。

### Nit 1：相对文档引用总体可解析，但源码路径缩写不是从报告位置或仓库根可直接解析的链接

所有 intended `.dev` 文档目标均存在，包括 `../../tmp/260822-verify-beta-flag-strip-docs.md`、`../../sync-refs/sxwxs-ghc-api/260821-round-disposition.md`、`../../hosted-web-search/status.md`、`../../tmp/260822-header-forwarding-surface.md`、`../../tmp/260822-h2-streamreset-cancel-diagnosis.md`、`../../tmp/260822-review-beta-flag-strip.md`；wildcard `../../upstream/retry-and-continuation/reports/260822-review-*.md` 当前匹配 7 个真实文件。`docs/.human-controlled/message-format-reshape.md` 和同目录简写 `message-format-reshape.md` 也能唯一解析。

`docs/.human-controlled/message-format-sanitize.md` 不存在，但报告两次提到它时是在陈述“这是已改名的旧路径”，不是把它当当前目标链接。另一方面，开头的 `lifecycle/*`、`pipeline/retry.py`、`translation_driver/responses.py`、`server/pipeline_app.py` 等缩写只有假定基准为 `src/app` 才能解析；从报告目录或仓库根不能直接解析。建议若要把它们当链接，写完整仓库相对路径。

具体失败场景：自动 link checker 或不熟悉隐含 `src/app` 基准的读者会把这些缩写判为缺失；对代码行为无影响。

## 八组终态声称逐条核实

### 1. 裁决 1：只按 `resolved_model` 匹配

**通过。** `app.server.handler.shape_request` 在 `apply_route` 后调用 `strip_denied_beta_flags(..., model=context.resolved_model, ...)`。`requested_model` 只参与 `decide_route`，没有进入 denial table。`app.pipeline.request_headers.strip_denied_beta_flags` 接受单个 `model`，`_denied_for` 也只匹配这个值；不存在 requested ∪ resolved 的残留生产路径。

成立范围：当前主工作树的主链。legacy `AppSettings.anthropic.beta_strip_headers` 仍是另一套零消费者配置，不属于这条新链。

### 2. 裁决 7：regex、`fullmatch`、配置顺序 first-match-wins、启动时编译

**四项均通过。**

- Regex：`compile_beta_flag_denials` 对每个配置键调用 `re.compile`。
- `fullmatch`：`_denied_for` 调用 `expression.fullmatch(model)`。
- First-match-wins：`compile_beta_flag_denials` 依 `Mapping.items()` 保留配置插入顺序；`_denied_for` 顺序遍历，首个命中立即返回，不 union 后项。
- 启动时编译：`build_chain` 构造 `Chain` 时调用 `compile_beta_flag_denials`；`cli.serve_inherited` 与 `cli._serve_pipeline` 两个实际启动入口都调用 `build_chain`。

独立启动探针使用合法 provider 配置并从 `build_chain` 传入坏键 `unterminated-[`，同步得到 `ValueError: strip_anthropic_beta_flags key 'unterminated-[' is not a valid regular expression: ...`。这证明错误发生在 chain 构建时，不等待请求。第一次用无 provider 的最小配置尝试时，`build_chain` 更早在 `resolve_default_name` 抛 `ProviderNotConfigured`；补齐有效 provider 后命中目标错误。该前置错误不否定坏 regex 的启动期性质，只说明多个配置错误并存时先报告控制流先遇到的那个。

### 3. 裁决 2：schema 开关删除，常驻剥离行为保留

**功能通过，文档有 Minor 1。**

- `StripRequestHeadersHook` 只有 `strip_anthropic_beta_flags`，没有 `strip_attribution_header` 字段。
- `app.pipeline.anthropic_request_hook.strip_attribution_lines` 仍实现 leading attribution line 剥离。
- `app.server.pipeline_app._dispatch` 在 `build_context` 后、路由前，对 Anthropic Messages 请求无条件调用 `strip_attribution_lines` 并更新 `ATTRIBUTION_LINES_STRIPPED`。
- 目标回归 `test_the_attribution_line_never_reaches_a_direct_upstream` 与 `test_the_attribution_line_is_not_counted_as_prompt` 通过。

因此没有把行为和开关一起删除；仅函数 docstring 还错误声称开关存在。

### 4. 裁决 3 + 6：8 处断链与 loader docstring

**当前主线通过，限定见 Minor 2 与 Minor 3。**

- 主提交态和主工作树均无 `message-format-sanitize` 残留；`80068eb` 的 patch 精确修了 8 处。
- 活跃嵌套 worktree 仍有 8 处，故只能声称当前主线无残留，不能无条件声称仓库根递归 0 命中。
- `config/loader.py` 新 docstring 对 `--fd` 链、`load_settings` 调用者、legacy 链存续和新链不读取 `AppSettings` 的每句事实都成立。
- `config/loading.py` 的相反旧 docstring 尚未同步，见 Minor 2。

### 5. 裁决 5：直连黑名单、翻译白名单、翻译腿不转发 `anthropic-beta`，以及两级顺序

**通过。**

- `build_context` 调用 `forwarded_client_headers`，先应用 `REQUEST_FLOOR`；运行探针把混合大小写的 `Authorization`、`Cookie`、`X-Api-Key` 放入请求，得到的中间 `context.client_headers` 只有 `anthropic-beta` 与普通 `x-custom`。因此路由前到路径策略之间的 context 不持有这些客户端凭据。
- `shape_request` 在 `apply_route` 后先调用 `apply_path_header_policy`。直连传 `translated=False`，使用空的额外 blacklist，因此保留 floor 后的未知客户端头；翻译传 `translated=True`，使用空 whitelist，因此转发 0 个客户端头。
- 之后才执行 beta flag strip。直连腿可见并按模型剥 flag；翻译腿已没有 `anthropic-beta`，strip no-op。
- driver 的 `_send` 最终只把经过上述两级处理的 `context.client_headers` 交给 provider。

结论强度：足以确认当前两条实际路径的 wire 结果和中间 context 状态；不把翻译腿 header 缺席错误归因给 beta strip，见 Major 2。

### 6. 文档新增的“大小写不敏感”

**通过。** `forward_request_headers` 的每一道请求判据都把 header name 折成小写：

- `REQUEST_FLOOR`：`name.lower() not in REQUEST_FLOOR`。
- core key：先建 `{name.lower() for name in core}`，再比较 `name.lower()`。
- `x-github-`／`openai-` prefix：对 `name.lower()` 调 `startswith`。
- `_matches`：header name 与 pattern 两侧都 `.lower()` 后交给 `fnmatch`。

独立探针用混合大小写分别命中 floor、core、两个 prefix、blacklist `_matches` 和 whitelist `_matches`，结果均符合大小写不敏感。HTTP header name 限 ASCII，使用 `lower()` 而非 `casefold()` 在这里没有未覆盖的 Unicode 语义。

### 7. `GhcApiClient.request_headers` 凭据缺陷修复

**通过。** `request_headers` 先把 owned header 名全部 `.lower()`，再丢弃任何大小写折叠后与 owned 冲突的 `extra_headers`，最后合并 owned headers。

独立 `httpx2.MockTransport` 探针没有复用仓库测试：

- OpenAI Responses 腿，输入 extra `authorization: Bearer client-secret`，wire 上 `authorization_count=1`，唯一值 `Bearer owned-token`。
- Anthropic Messages 腿，输入 mixed-case `aUtHoRiZaTiOn: Bearer client-secret`，wire 上 `authorization_count=1`，唯一值 `Bearer owned-token`。
- 两条腿的完整 header pairs 均不含 `client-secret`。

现有 component test 只驱动 Anthropic 腿，但独立探针已经补足用户要求的 OpenAI 腿验证。

### 8. 实现报告自身事实性

**不通过，原因是 Major 1、Major 2、Minor 4。** 结构对象核查结果如下：

- 报告内 commit hash `ec8b2a5`、`f191e4d`、`1743a0b`、`53fec22`、`80068eb`、`1c91870`、`fa0b281` 全部解析为主仓真实 commit object；`53fec22` 由分支 `a/2026-08-20-split-53fec22` 持有。
- 用户背景列出的主仓 `a2169de`、`80068eb`、`959e8d1` 以及 `.dev` `0ca6da8`、`41e98ef`、`2ab949a` 全部解析为真实 commit object，并且都是各自当前 HEAD 的 ancestor。
- 报告内所有 intended `.md` 当前目标均解析；旧名 `message-format-sanitize.md` 的两处文字是被改名对象说明，不是有效当前目标；源码缩写限定见 Nit 1。
- 所有 `§` 目标标题都存在，包括 §1、§2.1、§2.2、§2.3、§2.4、§2.5、§4、§5、§7、外部报告 §1.1、`hosted-web-search/status.md` §4.5，以及本节内命名小节“照字面实现会造成一个凭据缺陷”。但“标题存在”不等于“语义指向正确”：§0 第 4 条指到 §7 后没有得到完整答案，§7 自身还保留裁决前处置。
- `260820-external-rewrite-surface.md:36` 与 `:404` 的引文内容及行号存在；`260821-round-disposition.md:97` 存在；`53fec22:docs/.human-controlled/config.example.yaml:486` 确实是 `beta_strip_headers:`；当前权威配置的 `model_mappings` 映射在 123 行、denial 表模型键在 443 行。

## 反向差异核查

### 是否有提交改了但报告没说的内容

**未发现。** 逐文件检查三个主仓 commit 的完整 patch：

- `a2169de` 的 6 个文件分别属于 schema 改名、metric、beta strip helper、handler 接线、unit/int 测试，报告 §2.1、§2.2、§2.3、§2.6、§3 均有对应说明。
- `80068eb` 的 12 个文件分别属于 loader docstring、schema 删除开关、case-insensitive owned-header merge、4+1+1+2 处旧文档名修复、header 两级策略与 regex 编译、`build_chain` 接线、handler 调序、component/int/unit 测试，报告 §2.1、§2.2、§2.4、§2.5、§3.4 均覆盖。
- `959e8d1` 只新增大小写回归测试，报告 §2.4 后半明确记录。

报告没有逐文件列 patch，但没有发现未披露的产品行为或额外文件改动。

### 是否有报告说改了但实际没改

裁决后功能部分没有发现“说改而未改”：resolved-only、regex 顺序、启动编译、schema 删除、常驻 attribution、两级 header 策略、翻译零转发、大小写合并都在当前代码中。真正的问题是报告后半又把这些已改项写成“未改／保留旧形态”，形成自相矛盾，而不是代码没落地。

### 报告内部是否自相矛盾

**是，且足以判 `needs-fix`。** 详见 Major 1 与 Major 2。需要把裁决前的过程事实明确移入带时点的“历史形态”小节，或把 §4、§7 的处置行逐条追加最终 superseded 状态；不能让现时态旧结论与 §0 的终态声明并存。

## 验证记录与边界

- 独立 credential wire 探针：OpenAI 与 Anthropic 两条腿各 1 个 `authorization`，均为 proxy-owned 值。
- 独立坏 regex 探针：有效 provider 配置下，`build_chain` 立即抛命名坏 key 的 `ValueError`。
- 独立 floor／case-insensitivity 探针：中间 context 无三类客户端凭据；floor、core、prefix、blacklist／whitelist `_matches` 的 mixed-case 样本全部命中。
- 隔离变异：`/tmp/beta-strip-discrimination.EaIqiQ` 中禁用 beta strip 后，翻译腿测试仍绿、直连测试变红，证明前者只由空 whitelist 承载最终 header 缺席，不验证 strip。变异只存在于 `/tmp` 的 `git archive` 副本，未写共享工作树。
- 目标测试：`tests/unit/pipeline/test_client_request_headers.py` 全文件，加 credential component test、6 条 beta int test、2 条 attribution int test，共 `36 passed`，耗时 2.99 秒。第一次命令同时禁用 cache provider 又传 `--cache-clear`，pytest 因参数不可识别退出 4；去掉不相容参数后按同一 selector 重跑得到上述结果。
- 未运行完整 `pytest tests`、Ruff 或 Pyright；本次是只读终态核查，结论不外推为全仓 gate 通过。
