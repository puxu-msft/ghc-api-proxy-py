# 独立评审：`598b778` 文档引用修复的**覆盖面**与**过度改动**

- 评审对象：主仓 `598b778`「docs: point the code's citations at the documents that now hold them」
- 评审范围：**只有两个问题** —— (A) 还有没有解析不到或解析到错处的文档引用；(B) 有没有改了不该改的、把对的改坏的、把实质信息弄丢的。
- **不在本报告范围**：每一处引用的**映射对不对**（「这句话是不是真在 `api.md` 里」）。那是并行评审 `.dev/docs/tmp/260822-review-doc-citations-mapping.md` 的题目，本报告不重复，也不替它背书。
- 评审时工作树 HEAD = `598b778`，工作树**脏**（12 个 modified，见 §4 能力边界）。
- 本次只读。未修改任何文件；本报告是唯一写入。

**结论：needs-fix。** 1 条 major、7 条 minor、4 条 nit。

major 那条是**这次提交自己引入的**：`src/app/server/__init__.py` 新写了一个不存在的模块名 `app.server.routes`，而同一个 docstring 往下八行就列出了真实模块清单、里面没有 `routes`。改之前那句话虽然引的是死文档，但**没有对代码说过一句假话**。

三个「有意不做」我判**全部成立**，但其中 `schema.py` 那条的**理由说法**与**记录方式**都需要修正（F2）。

---

## 1. 发现清单

| # | 严重度 | 位置 | 一句话 |
|---|---|---|---|
| F1 | **major** | `src/app/server/__init__.py:3` | 本次提交引入了不存在的模块名 `app.server.routes`，与同一 docstring 第三段自相矛盾 |
| F2 | minor | `src/app/config/schema.py:137` | `docs/.dev/…/streaming-resilience.md` —— 根目录写反 + 路径段是字面 `…`，任何解析都到不了；且紧接着仍在声称它是「spec」 |
| F3 | minor | 4 处 | 裸 `spec.md` 仍在，且**按本次提交自己的判据就该改**（所在文件通篇没有该文档的路径） |
| F4 | minor | `src/app/server/pipeline_app.py:569` | 裸 `decisions.md` §4.1，全仓有两份 `decisions.md`；本次按名单扫描结构上看不见它 |
| F5 | minor | 3 处 | 「the frozen Spec」—— 连文件名都没有，路径搜和文件名搜都够不着 |
| F6 | minor | `src/app/observability/request_log.py:106` | 引用被换成了**循环自指的无出处引号**，比改之前差（唯一一处「换成了更差」） |
| F7 | minor | 提交信息 | 「six `spec.md` and six `deferred.md`」实为**各五份**；这是本次清扫的自陈依据 |
| F8 | minor | `docs/.human-controlled/README.md:18` | 反向检查确认：清单列了不存在的 `observability.md`、漏了存在的 `release-and-deployment.md`（**只报告，不得改**） |
| F9 | nit | 3 处 | 裸 `implementation.md` ×2、裸 `hosted-web-search-spec.md` ×1；名字全仓唯一故可解析，但所在文件都没给路径 |
| F10 | nit | `request_log.py:3`、`handler.py:265` | 「用户 2026-08-20 裁定过期」逐字重复两遍，日期的权威在归档自己的 README |
| F11 | nit | `contrib/systemd/ghc-api-proxy.service:3` | `Documentation=` 指向 `/opt/.../.dev/docs/...`，而 `.dev/` 被 gitignore、按项目规约只存在于主工作树根 |
| F12 | nit | `exp/phase2-acceptance/{README,ACCEPTANCE_MATRIX}.md` | 各 4 条链接指向已删的 `docs/2604-rewrite/`；**建议不改**，归档 README 已把它判为「历史快照，未动」 |

---

## 2. A 部分：覆盖面

### 2.1 我的搜索覆盖了什么

主扫描（排除 `.claude/worktrees/`、`.venv/`、`.git/`）：

```
rg --no-heading --line-number --glob '!.claude/worktrees/**' '[A-Za-z0-9_./-]*\.md\b' src tests
```

得到 86 行、34 个互异 token。逐个做存在性检查，27 个带路径的 token **全部解析成功**：

```
OK  docs/.human-controlled/{request-pipeline,api,message-translation,ghc-api,lifecycle,message-format-reshape,upstream-retry-and-continuation}.md
OK  .dev/docs/upstream/retry-and-continuation/deferred.md
OK  .dev/docs/upstream/h2-goaway/findings.md
OK  .dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-poc.md
OK  .dev/docs/anthropic-responses-bridge/{spec,implementation,hosted-web-search-spec}.md
OK  .dev/docs/tui/{deferred,spec}.md
OK  .dev/docs/delivery-keepalive/spec.md
OK  .dev/docs/test-infrastructure/reports/260818-vcrpy-poc.md
OK  .dev/docs/hosted-web-search/reports/260820-{websearch-responses-leg-400-fix,claude-code-websearch-request-forensics}.md
OK  .dev/docs/archived-2604-rewrite/{tokenization,DESIGN}.md
OK  .dev/human-controlled-docs-candidates/instructions-shape-conflict.md
OK  .dev/docs/tmp/260822-ghc-api-conformance-summary.md
OK  .dev/docs/httpx2-migration/plan.md          （pyproject.toml:16）
OK  .dev/docs/deployment-systemd/README.md      （contrib/systemd/*.service，但见 F11）
OK  .claude/rules/00-development-workflow.md    （pyproject.toml:70、.github/copilot-instructions.md:3）
```

另外三轮定向扫描：

- **非 `.md` 与目录形态**：`config.example.yaml`、`docs/…`、`.dev/…`、`exp/…`、`verification/…` 前缀。全部解析成功，含 `exp/260820-{empty-text,tool-pair,websearch}-probe/`、`exp/260820-websearch-probe/raw/C2-...txt`、`.dev/exp/httpx2-migration/probe_cap_designs.py`、`.dev/docs/upstream/retry-and-continuation/archive-proxy-side-continuation/`。`config.example.yaml` 全仓仅一份（`docs/.human-controlled/`），裸写不歧义。
- **旧路径**：`docs/agents|docs/tmp|docs/2604-rewrite|MAIN.md|model-translation.md` 在 `src/`、`tests/` 中**已彻底清零**（`.dev/docs/tmp/` 的子串匹配是假阳性）。tracked 文件中的真残留只有 F12 两份。
- **源码文件路径引用**：`src/app/debug/models.py:96`→`footer.py` OK、`src/app/pipeline/delivery/stream.py:384`→`app/delivery/responses_anthropic_stream.py` OK（相对 `src/` 的写法）、`tests/tui/conftest.py:3` OK、`tests/unit/pipeline/test_stream_ending.py:3` OK。**唯一不存在的是 F1。**

### 2.2 我的搜索必然漏掉什么

按 `state-decisiveness`，这一节是本报告最该被质疑的部分。

1. **无扩展名的文档指称。** 我的主正则以 `\.md` 收尾，`「the frozen Spec」`（F5）是靠**另起一个手搓探针**（`rg 'frozen Spec|the Spec|DESIGN|MAIN|ROADMAP|BACKLOG'`）才捞出来的，而那个探针的关键词是我**猜**的。**我不能声称 F5 这一类已经穷举**——只能说我猜到的这五个词捞出了 3 处。
2. **跨行的引用。** rg 逐行匹配，一个横跨两行的文件名不会命中。
3. **`[A-Za-z0-9_./-]` 之外的字符**，包括任何中文命名的文档。
4. **只给章节号的引用**（`§13`、`4.1`、`spec.md:266`），文件靠上下文散文承担。F4 正是这一形态。
5. **其它扩展名的产物**（`.txt`/`.json`/`.db`）若裸写而非带路径写，我的第二轮前缀扫描够不着。

> 归档 README 的 2026-08-20 清点表（第 19-25 行）**确实没有源码这一层**——三行分别是「仓库门面」「其它话题的活文档」「历史快照」。任务给的这条背景，我核对成立。

### 2.3 F1（major）—— 本次提交自己引入的悬空模块名

改之前（`598b778^`）：

```
MAIN.md: this module receives requests, does basic input format parsing, and hands them to
app.pipeline.
```

改之后（`598b778`，`src/app/server/__init__.py:3`）：

```
`docs/.human-controlled/request-pipeline.md`: requests enter at `app.server.routes` and are handed to `app.pipeline`. …
```

`app.server.routes` 不存在：

```console
$ ls -1 src/app/server/
__init__.py  admission.py  app_factory.py  composition.py  handler.py
inbound.py   ops_routes.py pipeline_app.py tls.py
$ rg --no-heading -n 'app\.server\.routes' src tests
src/app/server/__init__.py:3:`docs/.human-controlled/request-pipeline.md`: requests enter at `app.server.routes` …
```

全仓唯一一处提及，就是这次新写的那句。而**同一个 docstring 的第三段**（第 11-12 行）写着：

```
Import the module you mean: `app.server.pipeline_app`, `app.server.app_factory`,
`app.server.composition`, `app.server.handler`, `app.server.inbound`.
```

五个模块，没有 `routes`。**文件在十二行内自相矛盾。** 真实入口：`src/app/server/pipeline_app.py:969` 与 `src/app/server/app_factory.py:157` 各建一个 `FastAPI(...)`，路由表在 `src/app/server/inbound.py:34`。

来源是**用户文档确实这么写的**：

```console
$ rg --no-heading -n 'routes|app\.server' docs/.human-controlled/
docs/.human-controlled/request-pipeline.md:3:主线：请求从 `app.server.routes` 进入，经过 `app.pipeline` 处理后，交给 `app.model_provider` 上游模型提供方。
docs/.human-controlled/module-org.md:21:        routes
```

**所以这与 `RequestContext` / `ClientRequest` 是同一类事：文档规定的名字，代码没有。** 而本次提交**在 `request.py` 上正确处理了这一类**——明写差异、把改不改交给文档作者——却在 `__init__.py` 上把文档的名字当作对代码的事实陈述抄了进来。同一提交、同一类问题、两种处理，且后者制造了一个改之前不存在的断链。这是我判 major 的全部理由：不是「引用指错了」，是**引用把一个不存在的东西说成存在的**，而且是在一个专门修断链的提交里。

**更好的写法**（沿用它自己在 `request.py` 用对了的那一套）：

```
`docs/.human-controlled/request-pipeline.md`: requests enter the server and are handed to `app.pipeline`. That document calls the entry `app.server.routes`; no module by that name exists here — the app is built in `app.server.app_factory` / `app.server.pipeline_app` and the route table lives in `inbound.py`. Whether to follow the document's name is its author's call. That document no longer spells out the basic input format parsing this module also does on the way; `inbound.py` states and owns that choice.
```

### 2.4 F2（minor）—— `schema.py:137`

```console
$ sed -n '137p' src/app/config/schema.py
    # NOT IMPLEMENTED, and it cannot be from here. `docs/.dev/…/streaming-resilience.md` asked for a periodic HTTP/2 PING because … Kept rather than deleted because it is a user-authored key with a spec behind it. …
$ fd --hidden --no-ignore --glob 'streaming-resilience*' . --exclude .claude/worktrees --exclude .venv
./.dev/docs/archived-2604-rewrite/streaming-resilience.md
```

**三个缺陷，提交信息只提到第三个：**

1. 根目录写反：`docs/.dev/` 应为 `.dev/docs/`。
2. 路径中段是字面的 U+2026 `…`。这不是省略号排版，是写进路径里的一个字符——没有任何解析方式能补齐它。
3. 目标在用户 2026-08-20 裁定整体过期的归档目录里。而这句话结尾还在说「it is a user-authored key with **a spec behind it**」——**这正是本次提交在别处专门撤销的那种权威声称，原样留在了这里。**

正确答案：`.dev/docs/archived-2604-rewrite/streaming-resilience.md`，并按本次提交在 `request_log.py` / `handler.py` 用的同一套说法标为已裁定过期的笔记，同时把「a spec behind it」改掉。

**「同伴占着」这个理由成不成立？成立，但提交信息把它说成了另一回事。** 实测同伴的未提交改动落在第 42 行与第 379-383 行：

```console
$ git diff --stat src/app/config/schema.py
 src/app/config/schema.py | 5 +++--
$ git diff src/app/config/schema.py | rg '^@@'
@@ -39,7 +39,7 @@          # "pidfile" -> "pidfile_dir"
@@ -379,7 +379,8 @@        # pidfile: str -> pidfile_dir: str + 注释
```

**离 137 行很远，文本上不冲突。** 但 `git commit -- src/app/config/schema.py` 取的是工作树，会把同伴的 `pidfile` → `pidfile_dir` 一并卷进一个「只改注释」的提交里。所以**该不该延后的答案是「该」，理由是提交边界而不是文本冲突**——提交信息写的「that file is open in the worktree under somebody else's edit」表达对了一半，但把缺陷本身描述为「cites the same archived notes」，**低估了它**：那是一个根本解析不了的字符串，不是一处引证指错。

**应当怎么做**：不必另想技术手段（私有 index + CAS `update-ref` 对一行注释是杀鸡用牛刀）。该做的是**把它作为一个具名待办上报给用户/同伴**，连同上面的正确答案——而不是留在提交信息的一个从句里，那里没有人会去找它。

### 2.5 F3（minor）—— 4 处裸 `spec.md`，按提交自己的判据就该改

提交信息的判据是：「these six were the ones whose own file named no path to read them against」。我按**同一判据**逐文件核了一遍，还有四处满足它：

```console
$ rg --no-heading -n -o '[A-Za-z0-9_./-]*\.md' tests/unit/pipeline/translation_driver/test_responses_stop_reason.py
32:    spec.md                      ← 全文件唯一一个 .md token
$ rg --no-heading -n -o '[A-Za-z0-9_./-]*\.md' tests/int/test_pipeline_app.py
197:message-format-reshape.md   946:spec.md   2306:.dev/docs/tui/deferred.md
2758:message-format-reshape.md  3161:upstream-retry-and-continuation.md
$ rg --no-heading -n -o '[A-Za-z0-9_./-]*\.md' tests/unit/pipeline/translation_driver/test_translation_driver.py
24:docs/.human-controlled/message-translation.md   50:message-translation.md
54:.dev/human-controlled-docs-candidates/instructions-shape-conflict.md
499:spec.md   760:.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md
$ rg --no-heading -n -o '[A-Za-z0-9_./-]*\.md' src/app/pipeline/translation_driver/openai_responses.py
3:docs/.human-controlled/message-translation.md   148:hosted-web-search-spec.md
150:.dev/docs/hosted-web-search/reports/260820-websearch-responses-leg-400-fix.md   582:spec.md
```

四个文件里**都没有任何一处 `spec.md` 的路径**。而候选有五份：

```console
$ fd --hidden --no-ignore --glob 'spec.md' . --exclude .claude/worktrees --exclude .venv
./.dev/docs/anthropic-responses-bridge/spec.md
./.dev/docs/delivery-keepalive/spec.md
./.dev/docs/history/spec.md
./.dev/docs/systemd-rolling/spec.md
./.dev/docs/tui/spec.md
```

四处按内容都指 `.dev/docs/anthropic-responses-bridge/spec.md`（`max_output_tokens` → `max_tokens` 映射、carrier TRANSFORM、`spec.md:266` 的空文本块），正确答案就是给它们补上这条路径。

其中 `test_translation_driver.py:499` 的写法是 `spec.md:266` —— **给一个没被指名的文件配了行号**，是这批里最难解的一处。

被正确修掉的两处对照（同判据、结果相反）：`tests/unit/pipeline/delivery/test_sse_assembly.py` 在 222 行拿到了路径，故 211 行的裸写在文件内可解；`src/app/pipeline/delivery/formats/openai_responses.py` 在 534 行拿到了路径，故 508 行可解。**判据本身是对的，只是没跑完。**

### 2.6 F4（minor）—— `decisions.md`，按名单扫描结构上看不见

`src/app/server/pipeline_app.py:569`：

> **The value is provisional**: the user ruled that this case gets a category of its own but has not named it, and the server that reads it is being changed in another repository. See `decisions.md` 4.1.

两份候选，第四节内容完全不同：

```console
$ rg --no-heading -n '^#{1,4} ' .dev/docs/history/decisions.md | rg '四'
58:## 四、`request_log_file.py` 同步写盘的问题
$ rg --no-heading -n '^#{1,4} ' .dev/docs/upstream/retry-and-continuation/decisions.md | rg '四'
73:## 四、尚待裁决
```

正确答案：`.dev/docs/upstream/retry-and-continuation/decisions.md` §4。其 4.1 正是「`max_tokens` 触发合成时 `category` 传什么值」，且已于 2026-08-22 更正为「不是待裁决项，是待对齐项」——**所以这处注释里「the user ruled … but has not named it」的说法本身也已经被那份文档推翻了**（那属映射评审的题目，此处只记录我顺带撞见的事实，不作判定）。

**这条的方法论意义大于它本身**：本次清扫是按 `spec.md` / `deferred.md` / `hosted-web-search-spec.md` **三个已知歧义名**去找的，而 `decisions.md` 不在名单上，所以结构上不可能被看见。正确的判据是「**这个名字在全仓唯一吗**」，而不是「它在不在我的名单里」。

### 2.7 F5（minor）—— 「the frozen Spec」

```console
$ rg --no-heading -n 'frozen Spec' src tests
src/app/pipeline/delivery/stream.py:385
src/app/pipeline/delivery/formats/anthropic_messages.py:142
tests/unit/pipeline/delivery/test_stream_delivery.py:305
```

三处都说「the frozen Spec rules these two mutually exclusive: 不得再发 `message_stop` 冒充成功」。按内容解析得到 `.dev/docs/anthropic-responses-bridge/spec.md`：

```console
$ rg --no-heading -n -l '不得再发' .dev/docs/ | rg 'anthropic-responses-bridge/spec.md'
.dev/docs/anthropic-responses-bridge/spec.md
$ rg --no-heading -n 'FINALIZED' .dev/docs/anthropic-responses-bridge/spec.md | head -1
5:- **状态**：正式开发规格，当前为 **`FINALIZED`**。…
```

**这是裸文件名形态的极端版：连文件名都没有。** 按路径搜不到，按文件名也搜不到。它比本次修掉的六处更隐蔽，而机制完全相同。正确答案是补上 `.dev/docs/anthropic-responses-bridge/spec.md`。

### 2.8 F8（minor）—— 反向检查：`docs/.human-controlled/` 的 14 份文档

我抽取了这 14 份里的全部 Markdown 链接与反引号包裹的路径/文件名 token。

**清单与实际文件对不上，确认任务给的背景成立：**

```console
$ fd . docs --type f --hidden --no-ignore | sort
docs/.human-controlled/README.md            api.md   cli.md
client-side-block-delivery.md               config.example.yaml   ghc-api.md
lifecycle.md   message-format-reshape.md    message-translation.md
module-org.md  release-and-deployment.md    request-pipeline.md
test-org.md    upstream-retry-and-continuation.md
$ rg --no-heading -n 'observability' docs/.human-controlled/README.md
18:- [observability.md](observability.md) - 可观测性
$ fd --hidden --no-ignore --glob 'observability*.md' . --exclude .claude/worktrees --exclude .venv
（无输出）
```

- **列了但不存在**：`observability.md`（`README.md:18`）。全仓无此文件。
- **存在但没列**：`release-and-deployment.md`。

**其余链接全部解析成功**：`README.md` 另外 12 条、`request-pipeline.md:9` → `./message-translation.md`、`module-org.md:16` → `./ghc-api.md`。

一处**不算缺陷**的：`test-org.md:25` 提到 `.dev/exp/upstream-payloads/`，该目录不存在——但那句是前瞻性的（「此类测试脚本**可以放在**」），是计划而非断链。

**一个值得报给用户的呼应**：本次提交在 `src/app/observability/request_log.py:3` 新写了「no current document restates it」（指 console log frame 无现行文档承载）。这与 `README.md` 里那个不存在的 `observability.md` **是同一个缺口的两面**——用户清单里预留了这份文档的位置，它还没被写出来，于是那个 frame 无处安放。代码那句陈述属实。

**按指令不得修改这些文件，本报告只报告。**

---

## 3. B 部分：过度改动

### 3.1 「撤销权威声称」那 6 处：我判**恰当，不是过头**

任务问的是：把「`DESIGN.md` 规定了这个帧」改成「这个帧来自那份被裁定过期的笔记，是本项目一直沿用的，不是裁决，且无现行文档重述它」——是诚实还是塞了不该由注释承担的元信息？

**我判恰当，且这个判断是我看完前后文得出的，不是默认信任。理由是它改变了读者被授权做什么：**

- 「`DESIGN.md` fixes the frame」告诉读者：**这个帧你不能动**，动了就是违背规格。
- 「it is what this project shipped and has kept, not a standing decision, and no current document restates it」告诉读者：**你可以动，而且没有文档需要同步，只是要知道现状是怎么来的。**

这两句给出的**行动许可相反**。既然前一句在裁定之后已经是假的，换成后一句不是加元信息，是**修正一条会误导人的授权**。而且它是这个事实**目前唯一的载体**——`observability.md` 不存在（F8），归档 README 的清点表没有源码这一层，没有别的地方在说它。

**对照什么才算过头**：如果注释写的是「谁在哪次会话裁的、经过第几轮评审、评审报告在哪」——那是把工作记录塞进代码。本次没有出现这一类。加的是「这句话有没有权威」，那属于注释的本职。

**唯一确实过了的是 F6，以及轻微的 F10。**

### 3.2 F6（minor）—— 唯一一处「原本是对的，被改成了更差」

`src/app/observability/request_log.py:106`，`RequestLine` docstring：

```diff
-    …It is then left out rather than printed as a placeholder, which is what `DESIGN.md` means by not showing model or tokens for a non-model request.
+    …It is then left out rather than printed as a placeholder, which is what "no model and no tokens for a non-model request" means.
```

**两个问题：**

1. **句子变成了循环自指。**「省略而不是打占位符，这就是『非模型请求不显示 model 和 tokens』的意思」——用一句话解释它自己。改之前那句至少还是「某文档是这个意思」，是有信息量的。
2. **出处被删干净了，没有换成别的。** 这是全提交里**唯一一处把引用替换成「无」而不是「更好的引用」**的地方。其余 5 处「撤销权威声称」都保留了出处并标注了它的状态；只有这处直接抹掉。

**而且它和同一提交的另一处改动接在了一起**：`tests/unit/observability/test_request_log.py:115` 被从「`DESIGN.md`: a non-model request shows no model and no tokens」改成了「A non-model request shows no model and no tokens — see `app.observability.request_log`」。于是链条变成：测试 → 指向本模块 → 本模块给出一句**没有主人的引号**。**指路的终点是悬空的。**

**更好的写法**（两选一）：

- 直接删掉尾句，理由本来就已经在下一句里了：
  `…It is then left out rather than printed as a placeholder, which would read as a model actually named that.`
- 或者指向本模块 docstring——那里**确实**承载了出处（F1 之外，本次提交在 `request_log.py:3` 做对了的那一段）：
  `…It is then left out rather than printed as a placeholder; where that frame came from, and that no current document owns it, is in this module's docstring.`

### 3.3 有没有把实质信息弄丢的？—— 除 F6 外，**没有**

我逐 hunk 比对了全部 20 个文件的增删行。测量数据、理由、反例全部保留：

- `translation_driver/openai_responses.py:3`：2026-08-18 实测的 `instructions` 六种数组形态全部 `failed to parse request` —— 完整保留，只换了文档名。
- `errors.py:3`：`AsyncOpenAI.post` / `AsyncAnthropic.post` 直接抛自己异常那段推理 —— 完整保留。
- `direct_driver/__init__.py`：`ws:/responses` 无 driver 对应「unsupported row」—— 保留，且把 `the spec's` 精确成了 `that table's`，**这是变好**。
- `handler.py:265`：「一个协议一个 estimator，免得互相拿自己的误差纠正对方」这条理由 —— 保留，只是把它从「`tokenization.md` 规定的」改成「本项目自己的理由，出处是那份过期笔记」。
- `subscribers/__init__.py`、`events.py`、`exceptions.py`、`routing.py`、`semantic.py`、`registry.py`、`inbound.py`：纯换名，正文一字未动。
- `request.py`：**净增**一段（`ClientRequest` / `UpstreamAttempt` 差异），无删除。

### 3.4 F10（nit）—— 出处样板逐字重复

「which the user ruled obsolete on 2026-08-20」现在同时出现在 `request_log.py:3` 与 `handler.py:265`，而这条裁定的权威在归档自己的 README：

```console
$ sed -n '3p' .dev/docs/archived-2604-rewrite/README.md
**用户裁定（2026-08-20）：这里整体过期。** 它是早期由 peer 会话编写的 **`copilot-api-js` 学习笔记**……
```

两处重述一个日期不是缺陷（`one-authority-allows-contextual-restatement` 允许语境化重述），但这是会一起过期的形状。写出目录名 `.dev/docs/archived-2604-rewrite/` 本身就够读者走到裁定；日期可以只留在归档 README。**nit，不建议为此单独改动。**

### 3.5 F7（minor）—— 提交信息的自陈计数不实

提交信息：「There are six `spec.md` and six `deferred.md` under `.dev/docs/`」。

```console
$ git -C .dev ls-files | rg '(spec|deferred)\.md$' | rg -c '/spec\.md$'
5
$ git -C .dev ls-files | rg -c '/deferred\.md$'
5
```

**各五份，不是六份。** 且不是评审时点的漂移——`598b778` 提交于 15:17，其前后 `.dev` 没有增删过这两个名字的文件：

```console
$ git -C .dev log --diff-filter=D --name-only --since="2026-08-20" | rg '(spec|deferred)\.md'
（无输出）
$ git -C .dev log --diff-filter=A --name-only --since="2026-08-22 15:00" --pretty=format:'%h %s'
41e98ef …  docs/tmp/260822-header-forwarding-surface.md
26ed922 …  docs/tmp/260822-review-split-2afa0c4.md
           docs/tmp/260822-split-2afa0c4-review-disposition.md
```

这个数字是本次清扫「为什么这六处需要补路径」的自陈依据，所以值得在记录里更正，尽管没有任何结论依赖它。（`verify-commit-attribution-before-writing-it-down`：写进记录的计数错了，比事实错了更难被发现。）

### 3.6 三个「有意不做」的裁定

| # | 事项 | 判定 | 依据 |
|---|---|---|---|
| 1 | `schema.py:137` 未改 | **成立，但理由说法与记录方式要修正** | 同伴改动在 42 / 379-383 行，文本不冲突；但 pathspec 提交会卷走同伴的 `pidfile_dir` 重命名，**所以延后是对的，理由是提交边界不是文本冲突**。缺陷本身被低估了（F2），且只留在提交信息从句里，应作为具名待办上报 |
| 2 | `docs/.human-controlled/README.md` 未改 | **无条件成立** | 用户亲笔，agent 不得修改。两个缺陷经独立复核**均属实**（F8） |
| 3 | `RequestContext` / `Attempt` 未改名 | **对代码成立** | 改名是文档作者的裁决，docstring 记差异是正解。**但同一原则没有被用在 `app.server.routes` 上**（F1）——同类问题、同一提交、两种处理 |

补一句关于第 3 条的建议（**建议而非缺陷**）：这条差异目前只活在一个 docstring 里。按项目 `no-silently-cut-but-defer`，它同时也该登记到某份活文档，让文档作者看得见。放哪一份我没有足够依据指定，交主会话裁。

---

## 4. 我**没有**核查的部分与能力边界

按 `deliver-something-helpful-when-blocked` 与 `state-decisiveness`，以下逐项列明。

1. **全部映射正确性未核。** 「`api.md` 的端点清单是否真支撑 `handler.py:301` 那句」「`deferred.md` §2 / `decisions.md` §4.1 的章节号对不对」「`request-pipeline.md` 是否真载有 driver 的异常契约」——一律未验，属并行评审的题目。**本报告的任何一条都不构成对映射正确性的背书。**（唯一例外是 F4 里顺带撞见的一条事实，已在原处标注为「不作判定」。）
2. **搜索形态的盲区**：见 §2.2 五条。其中第 1 条（无扩展名指称）我**明确无法声称穷举**——F5 是靠猜关键词捞到的。
3. **在脏工作树上核查。** 12 个 modified + 若干 untracked。`schema.py` 我同时读了工作树与同伴 diff；**其余文件我没有分离 HEAD 态与工作树态**，所以若同伴刚在某文件里未提交地增删了一处引用，我会把它归到错的状态上（`grep-the-commit-not-the-worktree`）。这是本报告已知的最大方法论弱点，权重：**足以令个别条目的归属存疑，不足以推翻 F1–F5 任何一条**（那五条我都直接读了文件当前内容并给出了命令输出）。
4. **排除在扫描外的位置**：`.claude/worktrees/`（两棵同伴隔离树，仍带着 `598b778` 之前的这些文件副本以及 `docs/agents/` 链接）、`.venv/`、`.git/`。untracked 的 `verification/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md:5` 引用了已死的 `docs/2604-rewrite/hooks-tokenization-spec.md`，是同伴未提交产物，**记录但不计入清单**。
5. **14 份用户文档我没有通读。** 反向检查只抽取了 Markdown 链接与反引号 token，散文形态的指称（「见模块组织那一份」）不在覆盖内。
6. **未运行任何测试或校验命令**，本次是引用解析评审，与运行时行为无关。全部命令为 `git show/log/ls-files/diff/check-ignore`、`rg`、`fd`、`sed -n`、`ls`、`cat`、存在性判断——**均为只读，无副作用**。
7. **按指令未提议任何门禁、CI 检查或校验脚本**；未提议修改 `docs/.human-controlled/` 下任何文件；未触碰同伴正在改的 `schema.py` / `cli.py` / `paths.py` / `lifecycle/entry.py` / `tests/int/`。

---

## 5. 建议的处置顺序（供主会话裁，不含门禁）

1. **F1** —— 立即修，一行 docstring。它是本次提交自己造的，且和 `request.py` 的正解摆在同一个提交里，改法现成。
2. **F3 + F4 + F5** —— 一并补路径，8 处，纯注释。判据换成「这个名字在全仓唯一吗」，而不是三名单。
3. **F6** —— 一行，恢复被抹掉的出处或直接删尾句。
4. **F2** —— 连同它的正确答案上报用户/同伴，等 `schema.py` 的同伴改动落定后随手改掉；**不建议**为它单独动私有 index。
5. **F8** —— 只上报给用户，不动。
6. **F7 / F10 / F11 / F12** —— 记录即可，F12 明确建议**不改**（归档 README 已判「历史快照，未动」）。
