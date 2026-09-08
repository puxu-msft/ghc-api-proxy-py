# 评审：count_tokens 请求日志行的可读性改动

日期：2026-08-20
评审对象：工作区未提交改动中，属于「`counted` 字段 + count 行上游腿」这一片的部分（`src/app/observability/request_log.py`、`src/app/server/pipeline_app.py` 的 count 分支、`src/app/server/handler.py` 的 `ask_upstream` extras、以及三条新测试）。
明确不在范围：同一工作区里同伴的 `web_search` 策略改动、`upstream_request_deadline` / `stream_idle` 超时改线、`src/app/streaming/deadline.py`。这些出现在同一 diff 里但不属于本次委托。

评审方式：只读。未修改仓库任何文件、未 `git add/commit/stash/checkout/restore`、未运行 `ruff format`。受控变异一律在 `/tmp/mutant/` 的源码副本上做（`cp -a src /tmp/mutant/`，用 `PYTHONPATH=/tmp/mutant/src` 遮蔽，已确认 `app.observability.request_log.__file__` 解析到副本），仓库工作树全程未被写入。

**结论：needs-fix。** 诊断成立，实现方向对，鉴别力实测通过；但有 5 条「应改」，其中两条是陈述性缺陷（注释与测试名各自断言了一件不成立的事），一条是 `[hard]` 级的 live doc 未同步。

---

## 一、核对诊断（问题 1）

### 结论：诊断成立，且我用穷举 + 实测把它收紧了

**`↑19.7k` 是词元不是字节** —— 成立。`format_tokens`（`request_log.py:240`）渲染 `↑` + `format_count(input_tokens)`，`format_count`（`:210-216`）产出裸的 `19.7k`；字节走 `format_bytes`（`footer.py:47-52`），任何取值都带 `B`/`KB`/`MB`，连 0 也是 `0B`。两者不可能混淆。

**没有 `↓` 是因为 count 没有输出词元** —— 成立。`format_tokens:258` 是 `if "output_tokens" in usage`，而 count 分支只塞 `{"input_tokens": tokens}`（`pipeline_app.py:300-302`）。注意这里是**键存在性**判断而非真值判断，所以交付轮次即使 output 为 0 也会打出 `↓0`——这正是把 count 行与交付轮次分开的一个额外事实。

**没有字节字段、只有一条协议腿，是因为 count 分支在 delivery 路径之前 return** —— 成立。`pipeline_app.py:282-312` 的 `if route.count_tokens:` 在 `:312` 就 `return JSONResponse(counted)`，而 `trace.bytes_in` / `trace.upstream_protocol` / `trace.upstream_conn` 全部在 `:345-348` 赋值，`trace.received` 在 `:400` 或 `_counted_upstream`（`:506`）里累加。

### 有没有别的 200 路径产生同形的行？我穷举了

进入 `format_completion_line` 的唯一入口是 `_log_completion`，唯一调用者是 `_serve`（`:241`）与 `_StreamAccounting.finish`（`:448`）；而 `_serve` 只挂在 `build_router()` 注册的 `ROUTES` 五条路径上（`:535-548`）。

- **`/v1/models`、`/health`、`/metrics`**：由 `ops_router` 服务（`ops_routes.py:30-75`），完全不经 `_serve`，**不产生任何完成行**。排除。
- **未注册 URL**：由 FastAPI 自己的 router 答 404，`_dispatch:250-252` 的分支是防御性的、且不是 200。排除。
- **`/v1/messages` 非流式成功**：`:345-346` 无条件设 `bytes_in` 与 `upstream_protocol`，`:400` 设 `trace.received`。行必然是 `H1/H1 200 … ↑<B> ↓<B> …`，两条腿两个字节字段。排除。
- **`/embeddings`**：`reply_summary` 对该路由无 reader，返回 `None`，`trace.absorb` 不被调用，所以确实没有 stop_reason 与 usage——但字节与两条腿仍在。排除。
- **流式 `/v1/messages`**：状态码在响应头到达时定死为 200，同样先过 `:345-346`。排除。

所以「单腿 `H1` + 无字节字段 + 只有 `↑<裸数字>`」这个组合，在改动前**只有** count 路径能产生。诊断的因果链完整，可作为决策依据（强）。

顺带修正一处措辞：`format_counted` 的 docstring 说这条行「indistinguishable from a delivered turn whose every reply field had gone missing」。严格说，那样的交付轮次仍会带 `↑<B> ↓<B>` 与 `H1/H1`，所以两者并非字面同形；真正成立的说法是**读者无法从「缺席」读出区别**（这正是项目记忆里那条「日志行上的缺席读不出来」）。docstring 现在的写法把一个可读性论证写成了同形论证，属于把结论说得比证据大一点点。不必改，但知道差别在哪。

---

## 二、发现清单

### F1 [应改] `handler.py:175-176` 的注释断言了一件有反例的事

位置：`src/app/server/handler.py:176`

> Only a count upstream *answered* reaches here: `send_anthropic_count_tokens` turns a refusal into a pipeline error before returning, so a failed attempt leaves no leg on the line and `provider(local)` is the whole of what says the estimator finished the job.

反例：上游返回 **200 但 body 里没有可用的 `input_tokens`**。此时 `provider.count_tokens` 正常返回，两行 extras 已经写入（`:177-178`），随后 `:185-186` 抛 `ValueError`；`count_tokens()`（`pipeline/count_tokens.py:79-80`）捕获 `Exception` 并降级到 `local`。最终结果是 `provider(local)` **同时带着上游腿**。同一形状还有第二个触发点：200 但 body 不是合法 JSON，`response.json()` 在同一位置抛出。

实测（`/tmp/probe_count_line.py`，复用 `tests/http/test_pipeline_app.py` 的 `make_client`，upstream 桩返回 `200 {"input_tokens": 0}`）：

```
H1/H1 200 anthropic-messages/claude-model 531ms ↑77B ↑7 request_id=… provider(local)
```

权重：**实测复现，足以据此改注释**。

要不要改行为？我认为**不要**——这条行其实比注释描述的更诚实（上游确实被问了、确实答了、只是答的不能用）。要改的是注释：把「a failed attempt leaves no leg」收窄成它真正成立的范围，即「上游**连响应都没给**（refusal、传输失败）时不会留下腿；上游给了响应但答案不可用时，腿在而 `provider(local)` 在」。`pipeline_app.py:305` 那条「present only when upstream actually answered the count」本身是准确的，改 handler 那条即可，两处就一致了。

### F2 [应改] 字段名 `counted` 与它自己的形参、与仓库既有命名习惯都对不上

位置：`request_log.py:117`（`counted: str`）、`:172`（`def format_counted(counter: str, …)`）、`pipeline_app.py:149`、`:194`、`:304`。

三条依据：

1. **同一件事在同一模块里有两个名字。** 渲染函数的形参已经叫 `counter`，docstring 通篇也说 "which counter answered"；只有字段叫 `counted`。
2. **`counted` 在本仓已经是「过去分词 = 布尔」的位置。** `RequestLine` 里的分词式命名是 `terminal_seen: bool`。一个叫 `counted` 的字段，读者的第一反应是 `bool`（这次被计数了吗），而它实际装的是「谁计的」。其余字段（`stop_reason` / `dialect` / `tools` / `blocks` / `usage`）全是名词。
3. **`counted` 这个词在相邻代码里已经有两个别的含义。** `request_log.py:136` 的局部 `counted` 是 `(kind, count)` 对的列表；`pipeline_app.py:286` 的局部 `counted` 是 count 端点的响应体 dict。加上新字段，一个词在两个文件里三种意思。本仓 `format_pending_tools` 的 docstring（`:166`）专门为「`tools` 一词撞了两个含义」改过名，同一条标准在这里应当适用。

建议改成 `counter`（与形参、docstring、`CountTokensProvider` 的词汇一致），或 `counted_by`。

**为什么现在改而不是以后**：`write_request_record` 用 `asdict(line)`（`request_log_file.py:41`）把字段名直接写进 `~/.local/share/…/requests/requests-*.jsonl`。这个键一旦落到磁盘上的历史文件里，改名就变成 schema 迁移。当前该文件**没有任何生产读者**（`rg` 全仓只有测试引用），是改名成本最低的时刻。

### F3 [应改] live doc `.dev/docs/tui/spec.md` 未同步

`.dev/docs/tui/spec.md` 是这条日志行的现行权威（它规定了前缀、字段顺序、着色规则表、以及「描述回复的用词跟随上游」那张词汇表）。本次新增了**一个新的行尾结局档位**，spec 三处该动而没动：

- 「着色规则」表逐字段列了颜色，没有 `provider(...)` 这一行（现状是：`count` 与括号不着色、计数器名 DIM）。
- 「一次流式请求怎么结束，由行来说」与「结束原因」的讨论都建立在「行尾是 stop reason」之上；现在行尾多了一个互斥的备选，而 spec 里没有任何一句说 count 请求长什么样。
- spec 自己立过一条纪律：「新增档位必须同时进 `STATUS_PREFIXES` 与 `PREFIX_COLOURS`，且测试要断言渲染出来的前缀」。那条是针对前缀的，但精神一致——新增一个可见档位要落进 spec 的表里。

项目规则 `sync-live-docs-timely` 是 `[hard]`。这条是本报告里唯一触及硬规则的发现，但它不影响运行行为，故仍判「应改」而非 blocker。

同时建议在 spec 里写下**为什么 count 行只有一条腿**（F1 收窄后的准确版本），因为这正是问题 3 担心的误读点，而误读发生在读日志的人身上，不是读代码的人。

### F4 [应改] 测试名把 "refused" 用错了，且它描述的真实场景行为与断言相反

位置：`tests/http/test_pipeline_app.py`，`test_a_count_upstream_refused_is_reported_as_an_estimate`，桩是 `httpx.Response(500, …)`。

在本仓，"refusal" 是有确定所指的词：`pipeline/count_tokens.py` 的模块 docstring 明写「A refusal is not a failure. … so `ProviderError` travels out rather than being handed on」，`:75-78` 也确实对 `ProviderError` 直接 `raise`。而 `ProviderError` 的实例是 `UnknownModel` / `CapabilityMissing` / `EndpointNotSupported` 等（`model_provider/types.py:22-54`），由 `GithubCopilotProvider.count_tokens`（`github_copilot.py:186-187`）的 `describe` / `require_endpoint` 抛出。

也就是说：**真正的 refusal 根本不会降级到 `local`**，它会一路冒到 400，行上既没有 `provider(local)` 也不是 200。这条测试测的是「上游 500 挂了」，与 refusal 是相反的两档。测试名 + docstring 正在教下一个读者一件与 `count_tokens.py` 模块契约相反的事。

改法：把测试名与 docstring 里的 "refused" 换成 "could not answer" / "upstream failed"，并把 docstring 里那句「`send_anthropic_count_tokens` raises a refusal as a pipeline error」改成「把上游的错误状态抬成 pipeline error」。行为与断言都不用动。

（补充测试缺口，供裁决：真正的 refusal 路径——例如对只支持 `/responses` 的模型走 count 端点——在 count 行上长什么样，目前没有测试固定。`docs/tmp/260820-review-count-tokens-shared-pipeline.md` 的 M2 已经登记过这一带的相关缺口。）

### F5 [应改] 上游腿只报了一半：记了 `bytes_in`，没记 `bytes_out`

位置：`handler.py:177-178`。

改动的自我论证是「so the count line can report the leg it actually flew」。但同一条腿的返回方向没有被记：`ask_upstream` 里 `response.json()` 之后 `response.content` 是现成的，却没有对应的 `count_tokens_bytes_out`。结果是 count 行出现 `↑77B` 而没有 `↓`，而这条行自己的约定是「字段缺席 = 这次交换里没有这个东西可放」（`_StreamAccounting.finish` 的注释、`RequestLine` 的类 docstring 都是这么立的）。于是新加的半条腿，在同一条行上复现了这次改动要修的那个毛病：读者看到 `↑77B` 无 `↓`，按约定推出「上游什么都没回」，而上游回的恰恰就是行上那个数字。

改法很小：`context.extras["count_tokens_bytes_out"] = len(response.content)`，在 `pipeline_app.py` 同样 `isinstance` 取出后填 `trace.received`。收益在 F1 那个反例上最明显——`↑77B ↓25B … provider(local)` 比现在可读得多。

如果你判断「count 的回包太小、不值得占宽度」，那也请把这个取舍写进 F3 要补的 spec 段落里，否则下一个人会把它当遗漏来修。

### F6 [可选] `provider(local)` 说不出上游为什么没答

三种情况在行上完全同形：上游被问了但失败、上游压根没被问（翻译路由没有 counter，`handler.py:198`、`:209`）、`providers` 配置里没有 `ghc`。区别其实已经被记下来了——`count_tokens_attempts`（`handler.py:212-213`）里躺着 `ghc:0:APIStatusError` 还是 `ghc:no-counter-for-openai-responses`——但**至今没有任何读者**。这一点 `docs/tmp/260820-review-count-tokens-shared-pipeline.md:72` 已经指出过并悬置，本次改动接了 `count_tokens_provider` 这个键，正好路过它而没有接。

最便宜的一档：把 `count_tokens_attempts` 也带进 `_Trace` → `RequestLine` → JSONL 结构化记录（**不上控制台行**，不占宽度）。这样 `request_id=` 这个 join key 就能回答「为什么是估算」，而控制台行保持现在的形状。上控制台（例如 `provider(no-counter,local)`）属于产品面，应由用户裁决，不建议评审自行推动。

判为「可选」而非「应改」：它不是本次改动引入的，本次改动也没有加重它。

### F7 [可选] 两个上行字段现在紧挨着，只靠单位字母区分

count 行的字段序变成 `↑<字节> ↑<词元>`，实测形如 `↑77B ↑7`，真实规模下是 `↑1.2KB ↑19.7k`。在交付轮次上这两者被 `↓` 隔开（`↑B ↓B ↑tok ↓tok`），count 行上没有隔断。`1.2KB` 与 `19.7k` 差一个字母。

这是既有约定（模块 docstring 第 7 行）的直接后果，不是新错误，所以判可选。真要处理，F5 补上 `↓<字节>` 就顺带把两者隔开了——这是我更偏好 F5 的另一个理由。

### F8 [可选] 三行相邻的 extras 读取用了两种风格

`pipeline_app.py:304` 是 `str(context.extras.get(...) or "")`，紧接着的 `:306-311` 两处是 `isinstance` 守卫。后者的语义是「类型不对就当没有这个字段」，前者的语义是「类型不对就强转成字符串」——例如塞进一个 `5` 会渲染成 `count(5)`。建议统一成 `isinstance(provider, str)`。影响极小，纯一致性。

### F9 [可选] http 测试里的 `[↑>]\d+B` 正则绑死了 fixture 体积

`assert re.search(r"[↑>]\d+B", lines[0])`。一旦上行 body 超过 1024 字节，`format_bytes` 输出 `1.2KB`，正则匹配不上。**它会响亮地失败而不是静默通过**，所以不是隐患，只是脆。改成 `re.search(r"[↑>][\d.]+(B|KB|MB)\b", …)` 更稳。

---

## 三、不变量核对（问题 4）：没有被破坏，且既有测试对破坏有鉴别力

**可达性分析**：`trace.counted` 只在 `pipeline_app.py:304` 赋值，那是 `if route.count_tokens:` 分支内、`:312` return 之前；`trace.stop_reason` 只经 `_Trace.absorb`（`:160`）赋值，而 `absorb` 只有两个调用点——`:406`（非流式，在 count 分支 return 之后）与 `:437`（`_StreamAccounting.finish`，只有流式路径构造）。两者互斥，**不存在同时置位的可达状态**。`format_completion_line` 的 if/elif 不会吞掉任何真实 turn 的 stop_reason。

**变异验证**（`/tmp/mutant`，只改副本）：把 `_log_completion` 的 `counted=trace.counted` 改成 `counted=trace.counted or "ghc"`，模拟「`counted` 泄漏到每条行上」，`tests/http` **5 条既有测试变红**——`test_a_stream_cut_after_its_stop_reason_is_not_called_truncated`、`test_a_stream_that_did_terminate_is_still_reported_as_one`、`test_upstream_token_usage_reaches_the_line`、`test_a_responses_upstream_is_logged_in_its_own_words`、`test_a_streamed_responses_reply_is_logged_in_its_own_words`。所以这个不变量即使将来被写坏，也有守卫会响。

一条记录性观察：`request_log.py:334` 那条注释花了不少篇幅论证「为什么 counted 必须排在第一个检查」，但既然两者不可同时置位，if/elif 的顺序在**当前所有可达状态下都不可观测**——把顺序调换，全套测试仍然全绿。注释本身没错（它论证的是可读性意图，不是行为），只是它读起来像在防一个正在发生的冲突。若要保留这个论证，值得顺带说明「这两者当前不可能同时出现，顺序是给读者看的，不是给状态机看的」。

## 四、测试鉴别力（问题 5）：三条都有牙

全部在 `/tmp/mutant` 副本上做，仓库工作树未被写入。

| 变异 | 预期 | 实测 |
|---|---|---|
| A：删掉 `handler.py` 两行 extras（上游腿不再被记录） | `test_a_token_count_says_it_was_one_…` 红，`…refused…` 仍绿 | 符合。红在 `startswith("H1/H1 …")`，实际行退化成 `H1 200 … ↑4.2k … provider(ghc)` |
| B：`pipeline_app.py` 无条件宣称上游腿 | `…refused…` 红，另一条仍绿 | 符合。红在 `startswith("H1 200 …")`，实际行变成 `H1/H1 … provider(local)` |
| C：`format_completion_line` 的 counted 分支永不渲染 | 三条全红 | 符合，3 failed / 105 passed |
| D：`counted` 泄漏到每条行上 | 既有交付轮次测试应红 | 符合，5 条既有测试红（见上节） |

**特别核对你点名的 `assert lines[0].startswith("H1/H1 …")`**：它就是变异 A 抓住的那一条断言，确实是鉴别 `handler.py` 那两行 extras 是否接线的唯一守卫。有牙。

单测 `test_a_token_count_is_not_a_turn_that_lost_its_reply` 断的是**整行相等**而不是子串，并且带一条 `counted=""` 的负样本（`"count(" not in …`），这两点都值得保留。

未被任何测试固定的两处（供裁决，不必然要补）：F1 那个「上游 200 但答案不可用」的反例；if/elif 的顺序（因不可观测，无法用行为测试固定）。

## 五、消费者对账（问题 6）

逐个查过，**除 F3 的 spec 外没有该改而没改的**：

- **footer / TUI**：`build_footer` 与 `_item`（`observability/footer.py:55-166`）只渲染在飞请求的「模型 / 耗时 / 下行字节 / 重试数」，登记项字段由 `ActiveRequest` 定义，完全不碰 `RequestLine`。`rg 'stop_reason|thinking|tools|usage' src/app/observability/tui.py src/app/observability/footer.py` 零命中。**无需同步**——count 行的结局字段属于完成行，不属于在飞面。
- **结构化 JSONL 记录**：`write_request_record` 用 `asdict(line)`（`request_log_file.py:41`），新字段自动进入；`tests/unit/test_request_log_file.py` 的键集合与取值都已补。**已同步**。该文件目前**没有生产读者**（全仓 `rg` 只有测试），所以 F2 的改名窗口还开着。
- **`context.extras` 的其他读者**：`rg '\.extras' src/` 共 12 处，除本次三个键外没有任何订阅者/hook/history 写入器消费 extras。新键不会外溢。
- **`docs/2604-rewrite/telemetry-observability.md:61`** 的示例行是 `[ OK ] 14:32:07 POST /v1/messages model=… tokens=1024/342 duration=2.3s`，与实现相去甚远。这是**既有漂移**，早于本次改动，不是这次引入的，也不该由这个切片承担。仅记录，供你决定要不要单独立一个 doc 清理切片。
- **`docs/2604-rewrite/DESIGN.md`**：只在路由表里提到 count 端点，不描述日志行字段，无需改。

## 六、问题 2 与问题 3 的直接回答

**问题 2（`counted` / `provider(ghc)` 可读吗）**：渲染 `provider(ghc)` / `provider(local)` **可读，且贴合本仓习惯**——它复用了 `think(...)` / `called(...)` / `tool_use(...)` 的同一形状；`ghc` 与 `local` 直接来自 `CountTokensProvider = Literal["ghc","local"]`（`config/schema.py:14`），是封闭集合、与配置文件用词一致，不会随部署变化；「词不着色、括号内容 DIM」与 `format_pending_tools` 的着色分工完全一致。**字段名不可读**，见 F2。注释风格（长句、说清为什么不是另一种、不硬折行）与本仓一致，`format_counted` 的三段 docstring 是这套风格的正确用法。

**问题 3（上游腿的取舍说清楚了吗）**：**在代码里说清了，在日志行上没有。** 三处注释（`handler.py:175-176`、`pipeline_app.py:305`、测试 docstring）把意图讲得很完整，读代码的人不会误解——但其中一条（F1）说得太绝对，另一条（F4）用错了本仓的专有词。至于「会不会让读者把『只有一条腿 + provider(local)』误读」——**会**，而且误读的正是读日志的人而非读代码的人，因为这三条注释都不在他眼前。缓解按成本排序：先做 F3（把这条约定写进 spec，让 `provider(local)` 的含义有个可查的权威），再考虑 F5（补上 `↓`，让「上游被问过」这件事在行上自己说话），F6 留给用户裁决。

---

## 附：证据文件

- `/tmp/probe_count_line.py` —— F1 反例的复现探针（复用 `tests/http/test_pipeline_app.py` 的 `make_client` 与 `request_log` fixture，未写入仓库）。
- `/tmp/mutant/src/` —— 变异用的源码副本。四次变异后均已从仓库重新拷贝还原；该目录与仓库无任何关联，可随时删除。

---

## 七、处置（由主会话补写，2026-08-20）

| 发现 | 处置 | 说明 |
|---|---|---|
| F1 注释断言有反例 | **采纳** | `handler.py` 注释改成准确范围：这条腿的含义是「上游**响应了**」而非「上游答出了这个数」。另补测试 `test_a_count_upstream_answered_uselessly_keeps_the_leg_it_flew`（桩返回 `200 {"input_tokens": 0}`）把这个反例钉住——评审指出它当时没有测试固定。行为未改，评审的判断（这条行比注释更诚实）成立。 |
| F2 字段名 `counted` | **采纳** | 全面改名 `counted` → `counter`，`format_counted` → `format_counter`。三条依据都成立，尤其「同模块形参已叫 `counter`」与「`counted` 在相邻代码里已有两个别的含义」。趁 JSONL 键还没有生产读者时改，成本最低。 |
| F3 live doc 未同步 | **采纳** | `.dev/docs/tui/spec.md` 新增「一次计数请求怎么读」一节（含三档上游腿的含义、以及 `ghc`/`local` 为什么必须说），着色规则表新增「计数器」一行，并补了它**不进结束原因阶梯**的理由。F3 建议的「把只有一条腿的原因写进 spec」一并写了。 |
| F4 测试名误用 "refused" | **采纳** | 改名为 `test_a_count_upstream_could_not_answer_is_reported_as_an_estimate`，docstring 里点明真正的 `ProviderError` refusal 根本不会降级到 local、也不会产生这条行。评审对本仓「refusal」一词所指的考据成立。 |
| F5 只记了 `bytes_in` | **采纳** | 补 `count_tokens_bytes_out`（在 `response.json()` 之后取 `len(response.content)`）→ `trace.received`。理由采纳得完整：半条腿在同一条行上复现了本次要修的毛病。两条测试都加了 `↓` 断言。 |
| F6 `provider(local)` 说不出为什么 | **不在本切片做，已登记** | 属产品面且非本次引入。已写入 `.dev/docs/tui/deferred.md` 第 4 条（含两档做法与证据强度），spec 正文也指向它。**待用户裁决**：`count_tokens_attempts` 要不要进结构化记录（不上控制台）。 |
| F7 两个上行字段紧邻 | **由 F5 顺带缓解** | 补上 `↓<字节>` 后，字节与词元被隔开，恢复成交付轮次的 `↑B ↓B ↑tok` 节奏。评审自己也偏好这个解法。 |
| F8 extras 读取两种风格 | **采纳** | 三处统一成 `isinstance` 守卫。原写法 `str(... or "")` 会把 `5` 渲染成 `count(5)`。 |
| F9 正则绑死 fixture 体积 | **采纳** | 改为 `[↑>][\d.]+(B|KB|MB)\b`，下行同理。 |
| §一 末尾 docstring 措辞 | **采纳** | `format_counter` 的 docstring 原写「indistinguishable」，把可读性论证说成了同形论证。改成「交付轮次仍带自己的字节字段，真正读不出的是缺席」。 |
| §三 末尾 if/elif 顺序 | **采纳** | 注释改为明说：两者不可同时置位，顺序是给读者看的、不是给状态机看的，交换两臂不改变任何运行行为。 |

**验证**：`uv run pytest tests/unit tests/http` = **1244 passed**（先前唯一失败的 `test_a_domain_restriction_refuses_before_upstream_is_called` 属同伴的 web_search 切片，处置这些发现期间已由对方修好）。`ruff check src tests` 干净，Pyright 三个文件 0 error。**未运行 `ruff format`。**

**提交**：`d3335b6`（谁应答的）、`9e3d374`（为什么是估算）、`40681ce`（`count(...)` 改名为 `provider(...)`，并把括号改成按发生顺序的轨迹）。`handler.py` 里的那部分在我提交之前已被同伴的 `064ba63` 整文件裹走。

工作区自始至终是共享的，同伴的在途改动与本切片混在同一批文件里，所以这三个提交的索引内容都是**从 HEAD 构造**的（`git hash-object` + `git update-index --cacheinfo`），既没有 `git add` 整文件，也没有用 `git commit -- <path>`（后者取的是工作区内容）。每次提交前都核对过索引里没有同伴的标志性改动。

**F6 后续**：用户于 2026-08-20 裁决把降级原因上到行上（`provider(ghc-failed,local)` / `provider(no-counter,local)`），见 `9e3d374`。仍未做的是更细的失败原因（超时还是 500），见 `.dev/docs/tui/deferred.md` 第 4 条。

评审自留的临时证据 `/tmp/mutant/`、`/tmp/probe_count_line.py` 未清理，可随时删。

---

## 八、时点框架（后加，2026-08-20 收尾时）

本报告是**评审当时**的记录，逐字保留，不回改。读它时请注意两处已被后续裁决取代的用词：

- 正文与变异表里的字段名 `counted` / `counter`、渲染 `count(...)`，此后经用户裁决改为 `count_provider` / `count_provider_reason` 与 `provider(...)`（提交 `40681ce`）。变异表里点名的符号名要按这个映射读。
- F6 当时判为「可选、可推迟」。用户随后推翻该判断，降级原因已上到行上（提交 `9e3d374`），见第七节处置表。

收尾报告：`docs/tmp/260820-closeout-count-tokens-log-line.md`。
