# 评审：`598b778` 把代码引用改指到现行文档，改对了没有

- 评审对象：主仓 `598b778` `docs: point the code's citations at the documents that now hold them`
- 评审时仓库状态：`HEAD = 598b778`，被评审的 20 个文件工作树全部干净（脏文件只有同伴在改的 `cli.py`、`config/paths.py`、`config/schema.py`、`lifecycle/entry.py` 及其测试，不在本次范围）
- 评审性质：只读。除本报告外未写任何文件，未运行任何会改动仓库的命令
- 结论：**needs-fix**。21 条改指**逐条成立**，没有一条把代码那句话指到不承载它的文档上；问题全部出在提交信息的**计数与覆盖面声称**，以及三处可以做得更准的引用落点

## 严重度计数

| 级别 | 数量 |
|---|---|
| blocker | 0 |
| major | 1 |
| minor | 4 |
| nit | 5 |

## 一、21 条改指的逐条核对

判据：去读被指向的那份文档，看它是否真的承载了代码那句话所声称的内容。全部 **21/21 成立**。证据如下（引文按行号给出，可用 `sed -n` 复核）。

| # | 代码那句话 | 改指到 | 承载它的原文 | 判定 |
|---|---|---|---|---|
| 1 | 管线的首要任务 | `request-pipeline.md` | `:7` 「首要任务是路由判定」 | 成立 |
| 2 | driver 提供订阅点 | `request-pipeline.md` | `:17` 「可扩展点以事件订阅的形式提供，允许功能模块订阅」 | 成立（措辞见 N2） |
| 3 | 已知异常按内置逻辑、未知异常总是中止 | `request-pipeline.md` | `:19` 「已知异常……会按内置逻辑处理；未知异常则总是中止」 | 成立 |
| 4 | 一个对象描述每个请求、订阅者可修改 | `request-pipeline.md` | `:16`「每个客户端请求都由一个 ClientRequest 描述」+ `:17`「订阅者能够修改上下文对象」 | 成立 |
| 5 | 唯一 id 与可选的插入位置 | `request-pipeline.md` | `:17`「传入唯一 id 和可选的『插入到谁之前/后』」 | 成立 |
| 6 | 从 `app.server.routes` 进入、交给 `app.pipeline` | `request-pipeline.md` | `:3`「请求从 `app.server.routes` 进入，经过 `app.pipeline` 处理」 | 成立 |
| 7 | 端点清单 | `api.md` | `:5-10` 端点清单本体 | 成立 |
| 8 | OpenAI 组也挂 `/v1` 与 `/openai/v1` | `api.md` | `:7`「OpenAI 兼容前缀：同一组端点也注册在 `/v1` 和 `/openai/v1`」 | 成立 |
| 9 | 先路由、格式不同才翻译、再驱动 | `request-pipeline.md` | `:5` 「负责驱动」+ `:7-9` 路由判定含「是否需要格式翻译」+ `:13` 「可能走直连路径或翻译路径」 | 成立 |
| 10 | 驱动表按上游端点一个模块；`ws:/responses` 是不支持行 | `ghc-api.md` | `:23-29` 驱动表，`:28` 行 `ws:/responses` \| 暂不支持 | 成立，且是四条改指里最强的一条 |
| 11 | 翻译器注册名 | `message-translation.md` | `:5` 「注册为翻译器……如 `inbound.from-anthropic-messages`、`outbound.to-anthropic-messages`……」 | 成立 |
| 12 | 输入格式 <-> 中间表示 <-> 上游格式 | `message-translation.md` | `:3` 「采用『输入格式 <-> 中间表示 <-> 上游模型格式』的方式」 | 成立，逐字对应 |
| 13 | driver 对闭集之外一律中止 | `request-pipeline.md` | `:19` 同 #3，闭集也逐个列出 | 成立 |
| 14 | `instructions` 是带 role 的对象数组、我们暂时用不到这层灵活性 | `message-translation.md` | `:36-59` 示例本体 + `:62`「只是目前我们用不到这层灵活性」 | 成立，逐字 |
| 15 | 那个 worked example | `message-translation.md` | 同 #14 | 成立 |
| 16 | token 计数是 per-protocol wire contract | `api.md` 端点清单 | `:5` Anthropic 有 `count_tokens`；`:6` OpenAI 组无计数端点 | 成立但落点可议，见 F3 |
| 17 | 固定了两个映射 | `anthropic-responses-bridge/spec.md` | `:263`「`incomplete` 且原因为 output-token limit 时，`stop_reason` 为 `max_tokens`」；`:265`「没有 content 的合法成功响应可生成协议要求的空 text block」 | 成立，正好两条 |
| 18 | reasoning item 被截断时无信号，有意留开 | `upstream/retry-and-continuation/deferred.md` §2 | `:33` 标题即「2. reasoning item 被截断时没有任何信号」，含「用户 2026-08-21 裁决：……保持悬念，暂不特殊处理」 | 成立，章节号也对 |
| 19 | `encrypted_content` 必须值级原样存活 | `anthropic-responses-bridge/spec.md` | `:205`「必须 value-exact 恢复同一非空 `encrypted_content`」；`:221`「缺失或空 `encrypted_content` 产生 bare marker」 | 成立，两半都在 |
| 20 | 未知终止原因不得被压成 `end_turn` | `anthropic-responses-bridge/spec.md` | `:264`「未知 incomplete reason 必须保留原因事实，不能仅映射成看似正常的 `end_turn`」；另见 `:186`、`:387` | 成立 |
| 21 | §13 要求那一族在本地被拒而不是悄悄移除 | `anthropic-responses-bridge/hosted-web-search-spec.md` | `:452` 「## 13. 不做什么」，`:456` `web_fetch`「声明继续 `REJECT`」；`REJECT` 的落点在 `:104-109` §3.6 是我方 `_fail(..., "server_tool_not_supported")`，与「剥离」（§8.3）确是两回事 | 成立 |

补充核对 #4 与 #10 的「去向」：旧 `MAIN.md` 的驱动表在 `## app.pipeline` 段（`53fec22:docs/.human-controlled/MAIN.md:50-58`），现行 `ghc-api.md:21-29` 逐行相同（只多了 self-hosted 一行说明），提交信息说「which is where it went」属实。

补充核对 #6 的「no longer spells out」：旧 `MAIN.md:31` 确有「本模块负责基础的输入格式解析，然后交给 app.pipeline 模块。」这一句，而现行 14 份文档里这句话消失了（`api.md` 拿走了端点清单，`request-pipeline.md:3` 拿走了「交给 app.pipeline」，输入格式解析那半句无人承接）。所以 docstring 里的 “no longer spells out” 是**可核实且为真**的，不是修辞。

证据命令：

```
$ git show 53fec22:docs/.human-controlled/MAIN.md > /tmp/MAIN.md
$ rg -n '本模块负责基础的输入格式解析' /tmp/MAIN.md docs/.human-controlled/
/tmp/MAIN.md:31:本模块负责基础的输入格式解析，然后交给 app.pipeline 模块。
```

（`docs/.human-controlled/` 侧无输出。）

另核对所有被写进代码的路径是否真的存在，25 个不同路径全部命中：

```
$ python3 - <<'PY'   # 提取 598b778 树内 src/tests 里的所有 docs/.human-controlled 与 .dev/docs 路径并逐个 os.path.exists
...
PY
distinct cited paths: 25
MISSING:
   none
```

## 二、三处「撤销权威声称」的处置

判定：**处置恰当，实质信息没有丢失**，只有一处措辞可以再准一点（F4）。

- `request_log.py:3` —— 新写法点明 `.dev/docs/archived-2604-rewrite/DESIGN.md`、注明用户 2026-08-20 裁定过期、并说「no current document restates it」。
  - 出处属实：`DESIGN.md:362` 「**格式**：`[PREFIX] HH:MM:SS METHOD /path ...`」。
  - 过期裁定属实：`.dev/docs/archived-2604-rewrite/README.md:3` 「**用户裁定（2026-08-20）：这里整体过期。**」。
  - 「无现行文档承载」属实。全仓（排除该归档目录）搜 `HH:MM:SS` / `PREFIX]` 只剩归档里的两处，以及一份**报告**里谈时钟的一句（报告不是活文档）：
    ```
    $ rg -n --glob '!archived-2604-rewrite/**' -e 'HH:MM:SS' -e 'PREFIX\]' .dev/docs docs
    .dev/docs/archived-2604-rewrite/DESIGN.md:362:...
    .dev/docs/archived-2604-rewrite/telemetry-observability.md:55:...
    .dev/docs/history/reports/260821-structured-logging-design.md:176:...
    ```
- `logging.py:82` —— 从「`DESIGN.md` records」改为「the console log shape this project has kept —— `app.observability.request_log` records where the frame came from」。指向的模块 docstring 里确实写着出处，链没断，也不再冒充裁决。恰当。
- `test_request_log.py:115` —— 改为「see `app.observability.request_log`」。同上，恰当。
- `handler.py:265` —— 保留推理、注明出处 `.dev/docs/archived-2604-rewrite/tokenization.md` 与其过期状态。恰当；`tokenization.md:5` 「Token count 是协议 wire contract，不是单一通用端点」与 `:22-32` 的计数器选择表确实就是这段代码在做的事，路径留着有用。

唯一可议的是 `request_log.py:106`，见 F4。

## 三、发现

### F1（major）「这六处是各自文件里没有路径可读的那些」不成立，且提交后仍余 7 处裸引用

提交信息写：

> Six bare `spec.md` / `deferred.md` / `hosted-web-search-spec.md` mentions gained their topic path. …… these six were the ones whose own file named no path to read them against.

**反例：`tests/unit/pipeline/translation_driver/test_responses_stop_reason.py:32`** 有一处裸 `spec.md`，而整个文件**一个 `.dev/docs` 路径都没有**。它完全符合提交信息给出的判据，却没有被改。

```
$ git grep -n -e 'spec\.md' -e 'deferred\.md' 598b778^ -- src tests | wc -l
13                          # 改前共 13 处裸引用
$ git grep -n '\.dev/docs' 598b778 -- tests/unit/pipeline/translation_driver/test_responses_stop_reason.py
                            # 空：该文件改后仍无任何路径
$ git grep -n 'spec\.md' 598b778 -- tests/unit/pipeline/translation_driver/test_responses_stop_reason.py
598b778:tests/unit/pipeline/translation_driver/test_responses_stop_reason.py:32:    # spec.md fixes this direction, and it is the only one it fixes.
```

改后残留的 7 处裸引用（6 处 `spec.md` + 1 处 `hosted-web-search-spec.md`）：

| 位置 | 本文件内能否解析 |
|---|---|
| `src/app/pipeline/delivery/formats/openai_responses.py:508` | 能，同文件 `:534` 已给出 `.dev/docs/anthropic-responses-bridge/spec.md` |
| `tests/unit/pipeline/delivery/test_sse_assembly.py:211` | 能，同文件 `:222` 已给出 |
| `tests/unit/pipeline/translation_driver/test_translation_driver.py:499` | 勉强，同文件 `:760` 给的是同目录另一份 `hosted-web-search-spec.md` |
| `tests/int/test_pipeline_app.py:946` | **不能**，该文件唯一的路径是 `:2306` 的 `.dev/docs/tui/deferred.md`，另一个 topic |
| `src/app/pipeline/translation_driver/openai_responses.py:148`（`hosted-web-search-spec.md` §13） | **不能**，该文件唯一的路径是 `:150` 的 `.dev/docs/hosted-web-search/reports/...`，与 spec 所在的 `anthropic-responses-bridge/` 不是同一个目录 |
| `src/app/pipeline/translation_driver/openai_responses.py:582` | **不能**，同上 |
| `tests/unit/pipeline/translation_driver/test_responses_stop_reason.py:32` | **不能**，全文件无路径 |

第 5 行那处尤其刺眼：`src/app/pipeline/translation_driver/openai_responses.py:148` 与本次已改的 `tests/unit/pipeline/translation_driver/test_translation_driver.py:760` 是**同一句话的两份**，现在一份带路径、一份不带。

正确答案：要么把「these six were the ones whose own file named no path」这句从提交信息里去掉（改成「六处已补，其余可从同文件解析或留待后续」），要么把上表后四行也补成 `.dev/docs/anthropic-responses-bridge/spec.md` 与 `.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md`。我倾向后者：判据本身是对的，只是执行时漏了；判据留着而结果不符，会让下一个读提交信息的人以为这一类已经清干净了。

### F2（minor）两处可数事实错误：`eleven modules` 实为 12；`六份 spec.md 和六份 deferred.md` 实为各 5 份

**`eleven modules`：实际是 12 个文件，13 处引用。** 引用数 13 对，模块数错。

```
$ git grep -l 'MAIN\.md' 598b778^ -- src tests | wc -l
12
$ git grep -c 'MAIN\.md' 598b778^ -- src tests | cat
598b778^:src/app/model_provider/ghc_client/errors.py:1
598b778^:src/app/pipeline/direct_driver/__init__.py:1
598b778^:src/app/pipeline/events.py:1
598b778^:src/app/pipeline/exceptions.py:1
598b778^:src/app/pipeline/request.py:1
598b778^:src/app/pipeline/routing.py:1
598b778^:src/app/pipeline/subscribers/__init__.py:1
598b778^:src/app/pipeline/translation_driver/registry.py:1
598b778^:src/app/pipeline/translation_driver/semantic.py:1
598b778^:src/app/server/__init__.py:1
598b778^:src/app/server/handler.py:1
598b778^:src/app/server/inbound.py:2
```

12 个文件全在 `src/`，没有一个在 `tests/`，所以「modules」不论怎么解释都数不出 11（`__init__.py` 也是 module）。

**`There are six spec.md and six deferred.md under .dev/docs/`：实为 5 和 5。** 磁盘上 5+5，`.dev` 仓库 HEAD tree 里也是 5+5，且这两个文件名**从未有过删除记录**，所以不是「评审时被同伴删了一份」。

```
$ fd -HI --type f '^spec\.md$' .dev/docs | wc -l
5
$ fd -HI --type f '^deferred\.md$' .dev/docs | wc -l
5
$ git -C .dev log --all --diff-filter=D --name-only --format='%h %s' -- '*/spec.md' '*/deferred.md'
                            # 空：从未删除
$ git -C .dev ls-files | rg -e '/(spec|deferred)\.md$' | wc -l
10
```

五份：`anthropic-responses-bridge/spec.md`、`delivery-keepalive/spec.md`、`history/spec.md`、`systemd-rolling/spec.md`、`tui/spec.md`；`client-leg-formats/deferred.md`、`delivery-keepalive/deferred.md`、`tui/deferred.md`、`upstream/h2-goaway/deferred.md`、`upstream/retry-and-continuation/deferred.md`。

论证本身不受影响 —— 5 个候选和 6 个候选一样让裸文件名读不出指向 —— 但一个专门用来消除「引用指向不存在的东西」的提交，其自身的可数断言应当经得起同样的检验。**正确数字是 12、5、5。**

### F3（minor）`handler.py:301` 改指 `api.md`：不假，但这一段的主语是上游，更贴切的是 `ghc-api.md`；且这句话的原文出处被丢掉了

代码那段的主语明确是**上游**：

```
$ sed -n '301p;306p' src/app/server/handler.py
    # Whether upstream has a counter is a property of where this is going, ... the endpoint list in `docs/.human-controlled/api.md` is where that shows: ...
    upstream_counts = route.target_format is WireFormat.ANTHROPIC_MESSAGES
```

`api.md` 是**我方入站**端点清单；固定**上游**端点的是 `ghc-api.md:23-29` 的驱动表，其中 `POST /v1/messages` 那一行同时列了 `POST /v1/messages/count_tokens`，而 OpenAI 的三行都没有计数端点。两份都能读出这个结论，但只有后者的主语是上游。

另外，「Token counting is a per-protocol wire contract」这句在仓库里是**有原文的**：`.dev/docs/archived-2604-rewrite/tokenization.md:5`「Token count 是协议 wire contract，不是单一通用端点」，紧接着 `:22-32` 是「计数器按目标协议选」的表和 calibration 键跟随目标协议的理由 —— 也就是这段代码正在做的事。改指之后这段代码不再指向它。缓解因素：同文件 `:265` 仍然留着 `.dev/docs/archived-2604-rewrite/tokenization.md` 的路径（相距 36 行），所以链没有真断。

建议：把 `:301` 的落点写成 `ghc-api.md` 的上游驱动表，或者两处并列；`api.md` 单独作为「上游有没有计数器」的依据是错位的。

### F4（minor）`request_log.py:106` 变成了一句没有出处的引号话，而它其实有原文

```
$ git show 598b778 -- src/app/observability/request_log.py | rg '^\+.*non-model'
+    `model` empty means routing never resolved one — ... which is what "no model and no tokens for a non-model request" means.
```

引号里那句现在**不指向任何东西**：读者会以为在引用什么，但同文件的模块 docstring 只把 `DESIGN.md` 记为**帧**（frame）的出处，没有覆盖这条「非模型请求不显示模型名/token」的规则。而这条规则是有原文的：

```
$ sed -n '362,363p' .dev/docs/archived-2604-rewrite/DESIGN.md
- **格式**：`[PREFIX] HH:MM:SS METHOD /path ...`
- **只显示相关信息**：非模型请求不显示模型名/token
```

正确答案二选一：照 `:3` 的写法补一句出处与过期状态（`DESIGN.md:363`，用户 2026-08-20 裁定过期，保留在行为上而非其权威上）；或者干脆去掉引号写成陈述句，别让读者去找一个不存在的被引方。后者更省事，前者更诚实 —— 这条规则和帧一样，是同一份被裁定过期的文档留下的，两者在同一个文件里却一个交代了出处一个没有。

### F5（minor，对应问题 1）`request.py` 的分歧只活在 docstring 里，没有进入任何待裁决文档

处置本身是对的（详见「四、问题 1」），但按项目自己的规矩，一个**尚待文档作者裁决**的重命名应当在活文档里有个落点，而不是只存在于一句注释里 —— 注释会随下一次重写消失，而重命名这件事不会。

```
$ rg -n -e 'ClientRequest' -e 'UpstreamAttempt' src tests .dev/docs
src/app/pipeline/request.py:7:That document now calls the object `ClientRequest` ...
```

全仓只有这一处。建议在 `.dev/docs/` 相应 topic 的 `deferred.md` 里记一条，或往 `.dev/human-controlled-docs-candidates/` 放一份「代码用 `RequestContext`/`Attempt`，文档用 `ClientRequest`/`UpstreamAttempt`，请裁决是否跟随」的候选片段。**不提议改动 `docs/.human-controlled/` 下任何文件。**

### N1（nit）`Six more citations named documents in archived-2604-rewrite`：按普查读是 7，且第 7 处是**写错的路径**而不是裸文件名

本次改的确实是 6 处（`DESIGN.md` ×4、`tokenization.md` ×2），提交信息后面也自己说了 `http2_ping_interval` 那处「is left alone」，所以内部不矛盾。但那句话的句式（「六处引用命名了归档目录里的文档」）读起来像普查，而普查结果是 7。

顺带报告一个超出本次范围的事实（同伴正在编辑 `src/app/config/schema.py`，**不建议现在动**）：那一处不是裸文件名，是一条**写反的路径**。

```
$ sed -n '137p' src/app/config/schema.py
    # NOT IMPLEMENTED, ... `docs/.dev/…/streaming-resilience.md` asked for a periodic HTTP/2 PING ...
$ fd -HI 'streaming-resilience' .dev
.dev/docs/archived-2604-rewrite/streaming-resilience.md
```

`docs/.dev/…/` 应为 `.dev/docs/archived-2604-rewrite/`。这解释了提交信息里那句「2026-08-20 的清点按路径做，所以看不见这些」为什么对这一处也成立 —— 但成立的原因不是「代码写的是裸文件名」，而是「代码写的是一条错路径」。

### N2（nit）`the driver provides subscription points` 比现行文档说得更具体

`events.py:3` 与 `subscribers/__init__.py:3` 都把「**驱动**提供订阅点」记在 `request-pipeline.md` 名下。现行 `request-pipeline.md:17` 的原文是「可扩展点以事件订阅的形式提供」，没有点名谁提供；旧 `MAIN.md:62` 才是「**驱动**应该提供事件订阅点」。语义上无害（`:5` 说 `app.pipeline` 负责驱动），但严格讲代码这句话比它现在引的那份文档说得更细一点。不建议改，记录在案。

### N3（nit）`reading notes on copilot-api-js` 这个定性对 `DESIGN.md` 和 `tokenization.md` 不成立

用户 2026-08-20 的**目录级过期裁定成立**，代码里的处置（保留推理、注明出处与过期状态）也因此是对的 —— 这部分我不推翻。但提交信息把整个目录概括为「reading notes on `copilot-api-js`, with no authority over anything here」，这句对被引的这两份文档本身不实：

- `DESIGN.md:1-7` 开篇即「`ghc-api-proxy-py` 是一个 Python 反向代理……本项目**借鉴** `copilot-api-js`……但**不是它的移植**」，是本项目自己的设计文档；`:353` 还记着「`[DRIN]` 由用户裁决于 2026-08-20 加入」，即它内部含有一条与过期裁定同日的用户裁决。
- `tokenization.md` 描述的是本项目**已实现**的 `handle_count_tokens` 行为（`:22-32` 的表逐格对应现在的代码），并记录了「用户 2026-08-20 判定不够：翻译路径要**正确支持**」。它在主仓的历史里是被本项目的功能提交改出来的：
  ```
  $ git log --all --format='%h %ad %s' --date=format:'%m-%d %H:%M' -- 'docs/2604-rewrite/tokenization.md'
  d88c07a 08-20 17:51 docs: retire 2604-rewrite from the repository
  c2eae5f 08-20 15:22 feat: count the body the translated route would actually send
  a334fab 08-20 14:33 fix: count what would be sent, and by an instrument that exists
  ...
  ```

也就是说，本项目关于 token 计数契约的知识目前**只**留在一份被整体裁定过期的目录里，没有任何现行活文档承接。这不是本提交造成的，也不该由本提交解决，但值得向用户点出：这是一个真实的缺口，而这次改指把它显式地写进了代码注释里（`handler.py:265`），反而让它更容易被看见 —— 这是好事。

### N4（nit）legacy 的 `src/app/pipeline/context.py` 也定义 `RequestContext`/`Attempt`，没有对应说明

```
$ rg -n '^class (RequestContext|Attempt)\b' src
src/app/pipeline/context.py:37:class Attempt:
src/app/pipeline/context.py:70:class RequestContext:
src/app/pipeline/request.py:43:class Attempt:
src/app/pipeline/request.py:56:class RequestContext:
```

`request.py` 是**新链路**在用的那份（`server/handler.py:51`、`server/pipeline_app.py:48`、`server/inbound.py:14`、`server/composition.py:54`、`pipeline/subscribers/__init__.py:25` 都从它导入），`context.py` 服务的是 legacy 链路（`app/routes/anthropic.py:25`）。所以 docstring 放在 `request.py` 是**放对了**。仅记录：落在 `context.py` 的读者读不到这条说明。不建议改（legacy 链路是另一个话题，且项目规矩是不擅自删已实现的东西）。

### N5（nit）`docs/.human-controlled/README.md` 列了 `observability.md`，但该文件从未存在

```
$ git log --all --oneline -- 'docs/.human-controlled/observability.md'
                            # 空
$ ls docs/.human-controlled/
README.md
api.md
cli.md
client-side-block-delivery.md
config.example.yaml
ghc-api.md
lifecycle.md
message-format-reshape.md
message-translation.md
module-org.md
release-and-deployment.md
request-pipeline.md
test-org.md
upstream-retry-and-continuation.md
```

`README.md:18` 列了 `observability.md`，目录里没有；反过来目录里的 `release-and-deployment.md` 不在 README 清单里。这正是 `request_log.py:3` 那句「no current document restates it」目前为真的原因 —— 本该承接控制台日志帧的那份文档还不存在。**这是用户亲笔文档，本报告不提议对它做任何修改**，只陈述事实，供用户知悉。

## 四、问题 1：`request.py` 的处置是否恰当

**恰当，我认为这是本次提交里判断最好的一处。** 理由：

1. **它没有制造假信息，反而消掉了一处。** 改前那句「MAIN.md: every request is described by a RequestContext」指向一个在本分支历史里从未存在的文件；改后既指向了真实文档，又如实说明了名字对不上。
2. **docstring 里那句关于来历的话是可核实的，而且为真。** 「the name the earlier single-document version of that spec used」—— 旧 `MAIN.md:62` 原文就是「每个请求都由一个 RequestContext 描述」。这不是自我辩解，是有据可查的事实。
3. **改名不是本提交能做的事。** 本提交是 comments-only（下节已用 AST 验证）；跟随重命名要动 `RequestContext` 与 `Attempt` 的全部引用，是另一件事、另一个提交。
4. **裁决权确实不在这个模块。** `docs/.human-controlled/` 是用户亲笔，agent 不得修改，所以「文档改回 `RequestContext`」这条路代码这边走不通；剩下的只有「代码跟随重命名」或「维持并记录」，而前者需要裁决。把裁决权明确交还给文档作者是正确的动作，不是推诿。

**别的处置？** 有一个应当叠加、但不应当替代的动作：把这条分歧登记到活文档里（见 F5）。理由是「记录在 docstring 里」和「记录在待裁决清单里」解决的是不同问题 —— 前者防的是读代码的人以为文档就是这么写的，后者防的是这条待裁决事项随着下一次 docstring 重写一起蒸发。两者都做才完整。

一处措辞可以更准：docstring 说「gives each upstream try its own `UpstreamAttempt`」并暗示 `Attempt` 也是旧名。旧 `MAIN.md` 里**根本没有 attempt 这个概念**（`RequestContext` 是唯一被命名的对象）。现在的句子把同位语只挂在 `RequestContext` 上，所以严格讲没错，但读起来容易理解成两个名字都有旧文档背书。属 nit 级，不单列。

## 五、问题 2：提交信息逐句核对

| 断言 | 核对结果 |
|---|---|
| `MAIN.md` is what the user's spec used to be, one document | **真**。`53fec22` 的 `docs/.human-controlled/` 只有 `MAIN.md`、`config.example.yaml`、`lifecycle.md`、`model-translation.md`、`tui.md` 五个文件，`MAIN.md` 是主文档 |
| **eleven** modules still cite it by name | **假，是 12**。见 F2 |
| It has never existed in this branch's history | **真**。`git log --all --oneline -- 'docs/.human-controlled/MAIN.md'` 只有一条 `53fec22`，而 `git merge-base --is-ancestor 53fec22 HEAD` 返回非零（`git branch -a --contains 53fec22` 只列出 `a/2026-08-20-split-53fec22`） |
| the spec reached the repository already split into the **fourteen** files | **真**。`fa0b281 docs: put the user-controlled requirement documents in the repository` 一次性 `A` 了 14 个文件（含 `README.md` 与 `config.example.yaml`），目录里现在也是 14 个 |
| all **thirteen** citations named nothing | **真**。`git grep -c` 合计 13（`inbound.py` 占 2） |
| `api.md` 给端点、`request-pipeline.md` 给次序与异常契约、`message-translation.md` 给翻译器名与中间表示、`ghc-api.md` 给驱动表 | **真**，逐条见第一节 |
| `ghc-api.md` … which is where it went | **真**。驱动表原在 `MAIN.md` 的 `## app.pipeline` 段，现在逐行在 `ghc-api.md:23-29` |
| `model-translation.md`, cited **three** times | **真**。`openai_responses.py:3`、`test_translation_driver.py:24`、`:50` |
| is `message-translation.md` under its current name：example 与那句话都在里面 verbatim | **真**。`diff` 旧 `model-translation.md` 与现行 `message-translation.md` 只差标题行与新增的 translator 注册段落，`instructions` 示例与「只是目前我们用不到这层灵活性」逐字未动 |
| **Six** more citations named documents in `archived-2604-rewrite` | **本次改的确是 6 处**；按普查读则是 7（见 N1） |
| 用户 2026-08-20 裁定该目录过期 | **真**，`archived-2604-rewrite/README.md:3` |
| reading notes on `copilot-api-js`, with no authority over anything here | **对目录的官方定性属实，但对被引的这两份文档不实**（见 N3） |
| 2026-08-20 的清点按路径做、看不见这些，因为代码写的是裸文件名 | **对这 6 处为真**；第 7 处（`schema.py:137`）看不见的原因是路径写错了，不是裸文件名（见 N1） |
| The console log frame is the case with no current owner at all | **真**（见第二节的 `rg` 输出） |
| **Six** bare `spec.md`/`deferred.md`/`hosted-web-search-spec.md` mentions gained their topic path | **真**，本次正好改了 6 处 |
| There are **six** `spec.md` and **six** `deferred.md` under `.dev/docs/` | **假，各 5 份**。见 F2 |
| these six were the ones whose own file named no path to read them against | **假**。见 F1 |
| `request.py` keeps its names and says why；`ClientRequest`/`UpstreamAttempt` neither exists in the code | **真**。全仓只有 `request.py:7` 这句注释提到这两个名字 |
| Comments only: **31** lines changed, **none of them code** | **「none of them code」为真，已独立验证**；「31 lines changed」的准确说法是 31 insertions / 30 deletions |

「none of them code」的验证方法与输出（对 20 个文件逐个 parse 前后两版，把所有 docstring 常量清空后比较 `ast.dump`；注释本来就不进 AST，所以任何**非 docstring** 的改动都会暴露）：

```
$ python3 - <<'PY'
  ... ast.parse(old) vs ast.parse(new), docstrings blanked ...
PY
files in commit: 20
files whose code (AST minus docstrings) differs: NONE
```

## 六、我没有核查的部分

- **没有运行测试、Ruff、Pyright。** 本提交是 comments-only 且 AST 已证同，跑一遍全回归对本次判断没有增量信息；如果需要 gate 结论，这一项缺失。
- **没有核查 21 条之外的引用是否也该改。** 例如 `client-side-block-delivery.md`（3 处）、`lifecycle.md`（7 处）、`message-format-reshape.md`（15 处）、`upstream-retry-and-continuation.md`（2 处）这些裸文件名 —— 它们在磁盘上**唯一命中**，不构成歧义，本次没有改也没有必要改，我只确认了唯一性，没有逐条核对它们的内容是否与被引文档相符。
- **没有核查 `decisions.md`（`pipeline_app.py:569`）与 `implementation.md`（`stream.py:384`、`pipeline_app.py:838`）这两组裸引用。** `decisions.md` 在 `.dev/docs/` 下有 2 个候选（`history/`、`upstream/retry-and-continuation/`），是与 F1 同一形状的歧义，但不在本次评审给定的清单里。
- **没有核查 `.claude/worktrees/upstream-error-events/` 这棵隔离树。** 它里面还有 `docs/agents/` 版本的同名 spec，按 CLAUDE.md 的记载那是 2026-08-21 之前的布局；本次的路径解析我一律以主树为准。
- **没有核查同伴正在改的 `schema.py`/`cli.py`/`paths.py`**，只在 N1 里引用了 `schema.py:137` 的当前内容作为事实陈述，未作评价、未建议改动。
- **没有对被引的 `.dev` 文档做完整性评审**，只核对了代码那句话所声称的那一条是否在其中。
