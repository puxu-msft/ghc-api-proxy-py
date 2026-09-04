# Web search 两条产品行为变更后的文档对账

日期：2026-08-22
性质：只读对账报告。**未修改任何文件**，仅本报告落盘。
基线 HEAD：`767d0f23514eff350c961cf307bf6b6f7c71a761`（`0b01cdc` 的文档搬迁已是它的祖先）

> **基线漂移，写在最前面。** 对账进行中，同伴推进到 `fa628e1 test: commit the catalog capture the web-search model list is argued from`，并在工作树里留下了四个**未提交**的 `src/app/` 改动（`subscribers/__init__.py`、`subscribers/hosted_web_search.py`、`subscribers/server_tools.py`、`server/composition.py`）。本报告的全部文档结论以 `767d0f2` 的产品行为为准；受这次漂移影响的只有 S4 一条，已就地标注。**下游若要复核，先确认工作树状态**——这是一棵多会话共享的树。

## 0. 范围、方法与一处需要主会话知道的事

### 0.1 实际扫描范围

派单时给的路径（`docs/agents/`、`docs/tmp/`）在本工作树已不存在——`0b01cdc docs: move the agent working documents out of the main repository` 把它们整体搬进了 `.dev/docs/`。主会话随后确认了这一点并重定了范围。实际扫描的是：

- `.dev/docs/` 整棵树（638 份 `.md`，其中判定为**活文档**的 49 份）
- `docs/.human-controlled/`（只读，只报告不建议改）
- `README.md`、`TODO_CURRENT.md`、`CLAUDE.md`、`.claude/rules/`

**判定活文档的判据**（下文反复用到）：文件路径中不含 `reports/`、`evidence/`、`batches/`、`archive*` 目录段，且顶层话题目录不是 `archived-2604-rewrite/`、`docs-tmp-migration/`、`tmp/`。这条判据来自 `.claude/rules/00-development-workflow.md`：「报告原件是时点记录……改写它里面的路径与行号会伪造记录」。因此本报告的「必须改」只对活文档提出，报告原件一律进第 4 节的「可疑清单」而不建议修改。

### 0.2 正样本对照

在相信任何零命中之前先证明命令能命中：

- `rg -n -uu 'models_support_web_search' .dev/docs docs README.md TODO_CURRENT.md .claude/rules` → **6 行命中、4 个文件**。同一条命令对 `README.md TODO_CURRENT.md CLAUDE.md .claude/rules/` 单独跑（模式换成大小写不敏感的 `web[ _-]?search`）**exit=1、零输出**。所以「README 与 rules 里没有 web search 陈述」是命令给出的结论，不是命令坏了。
- 链接解析脚本对全部 638 份 md 跑出 **34 处断链**，对 49 份活文档跑出 **0 处**。前者证明解析器工作正常，后者才可信。

### 0.3 一份活文档在对账期间被搬走了，路径引文没跟着改

09:12 我在主仓看到 `docs/agents/anthropic-responses-bridge/hosted-web-search-status.md`（未追踪，同伴刚写）。09:16 它被搬到了 `.dev/docs/hosted-web-search/status.md`，**内容一字未改**，于是它内部 7 处指向 `docs/tmp/` 与 `docs/agents/` 的路径引文全部落空。详见第 5 节 L1。

---

## 1. 必须改（陈述与当前行为直接矛盾）

以下全部在**活文档** `.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md`（465 行）与 `.dev/docs/hosted-web-search/status.md` 内。

### M1. §8.3：把「剥离声明」写成 `必须`，而实现是合成失败结果

`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:284`：

> 路由到 **Responses 腿但能力门未通过**时：**必须**剥离 web search 声明、同步清理指向它的 `tool_choice`、记一条 `DEGRADE` fact（`server_tool_capability_unavailable`）并输出 INFO 级日志……**不得** `REJECT` 整个请求。

当前行为（`src/app/pipeline/subscribers/hosted_web_search.py`，HEAD `767d0f2` 的 `:90-111`）是第三条路：抛 `WebSearchNotExecutable`，由交付侧合成 `server_tool_use` + 失败的 `web_search_tool_result`。同模块 docstring `:11` 明写「Why it refuses rather than removing the declaration, **which is what it used to do**」。

这一条**在今天两条变更之前就已失真**（`260820-closeout-loose-ends.md:102` 的 S3 已经报过），今天的变更让它更错一层：现在**默认**就走这条分支，所以规格里这句被误读的概率从「偶发」变成「常态」。

引用同一条被推翻做法的还有：

- `:115` ——「被指向的 web search 声明因能力门未通过而被剥离时（§8.3），该 `tool_choice` **必须**同步删除」
- `:344`（§10 分工表 Responses 腿一列）——「能力门不通过时 §8.3 剥离」

### M2. §2、§9 完全没有「功能开关」这一轴

`:27` 把「能力门」定义为「判定**当前 attempt 的 resolved model** 经 Responses 腿是否真正执行 hosted web search 的算法」；`:317-321` 列出三个必须**全部**满足的条件，全部围绕模型与路由。

实现有第四个、且排在最前的条件：`hosted_web_search.py`（HEAD `:81`）`if enabled and _is_supported(...)`，`enabled` 来自 `model_translation.to_openai_responses.hosted_web_search`，默认 `False`（`src/app/config/schema.py:233`）。也就是说**按规格写出来的能力门，在默认配置下永远判通过，而实现永远判不通过**。

规格全篇没有出现 `hosted_web_search` 这个键，也没有任何一句说这条腿的 web search 默认是关的。

### M3. §9.3：配置键名与取值语义都已落地，规格仍写「待定 / 模型 id 列表 / 七个默认值」

`:323`：

> 配置键**名待定**（同 §3.4 的理由：须与人写 `config.example.yaml` 的扁平键词汇对齐），下文以 `<hosted_web_search_models>` 指代。取值为模型 id 列表。**默认值**由目录派生：`vendor == "OpenAI"` **且** `supported_endpoints` 含 `/responses`，2026-08-20 的实时目录下即 `gpt-5.3-codex`、`gpt-5.4`、`gpt-5.4-mini`、`gpt-5.5`、`gpt-5.6-luna`、`gpt-5.6-sol`、`gpt-5.6-terra` 七个。

现状（`5b8c56a`）——以下 `hosted_web_search.py` 行号均按 HEAD `767d0f2`，见文末附注：

- 键名是 `model_providers.<name>.models_support_web_search`，不待定。
- 取值是**正则表达式列表**，`fullmatch` 匹配上游 `model.id`（`hosted_web_search.py:59-64`），启动时统一编译（`compile_supported`，`:33-50`）。
- 默认值是**一条** `r"gpt-[5-9]\.\d+.*"`（`schema.py:125-127`），不是七个字面 id。
- 派生判据从 `vendor == "OpenAI"` 换成了**名字里的点**：`schema.py` 的注释写「**The dot is load-bearing.** `gpt-5-mini` has no dotted minor and is vendor `Azure OpenAI`」。规格 `:325` 那句「取 `vendor` 而**不**取 `gpt-` 名字前缀」现在把实现的判据说反了——实现取的正是名字，靠点号而不是 vendor 排除 `gpt-5-mini`。

连带失真的还有：

- `:407`（§12 设计裁决表）——「§9.3 | `gpt-5.` 前缀清单」。这个描述在 `5b8c56a` 之前就不准（当时是七个字面 id，不是前缀），现在依然不准（是正则族，覆盖 majors 5–9）。
- `:417`（P5 探针项）——「未探针前按 §9.3 默认值执行」，指向的默认值已不存在。
- `:6` 与 `:452`（D4 裁决登记）——「已裁决（2026-08-20，用户）：配置项手动维护……键名仍待与人写 `config.example.yaml` 的词汇对齐」。2026-08-21 用户又下了一次裁决「能力门采用版本清单，清单接受正则表达式」（转录在 `.dev/docs/hosted-web-search/reports/260821-responses-leg-websearch-capability-reference.md:102`），规格的裁决登记表没有这一条。

### M4. §3.4 / §14 D1：域名限制的默认值与取值集合，规格与实现是三处不一致

`:69-75` 冻结「取值三选一，默认 `error`」，三个取值是 `error` / `drop_unsupported_fields` / `drop_web_search`；`:449`（D1）复述同一裁决。

实现（`schema.py:256`）是 `web_search_domain_restrictions: WebSearchConstraintPolicy = "drop_fields"`，取值集只有 `error` 与 `drop_fields` 两个，默认是后者。`schema.py` 的注释坦白了这是有意偏离（190/190 真实 Claude Code 子请求都带非空 `allowed_domains`，取 `error` 会让 web search 永久不可用）。

**这一条严格说不是今天两条变更造成的**（`260820-closeout-loose-ends.md:86` 的 S1 已报过，并建议回到用户手上裁决），但它与今天的默认关闭是同一件事的两半：`767d0f2` 的提交说明把「域名清单发不出去且默认被丢弃」列为默认关闭的理由之一。规格 §3.4 现在同时写错了三样东西——默认值、取值个数、取值名字。**这一条我不建议由文档对账单方面改掉，它需要用户重新裁决**，见第 6 节。

### M5. `status.md:5` 与 `:71-76`：指向已不存在的目录

`.dev/docs/hosted-web-search/status.md` 是 2026-08-22 新写的活文档，内容与 HEAD 相符（我逐条核对过第 1、2 节，与 `schema.py:125/233/250` 及 `hosted_web_search.py` 一致）。但它整份是在 `docs/agents/` + `docs/tmp/` 布局下写的，搬进 `.dev/docs/` 时未重指：

| 行 | 原文路径 | 现址 |
|---|---|---|
| `:5` | 「报告原件在 `docs/tmp/` 下按日期前缀存放」 | `.dev/docs/<topic>/reports/` |
| `:55` | `docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md` | `.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md` |
| `:57` | 「结果见 `docs/tmp/260822-websearch-doc-reconciliation.md`」 | 本文件 `.dev/docs/hosted-web-search/reports/260822-websearch-doc-reconciliation.md` |
| `:71` | `docs/tmp/260821-responses-leg-websearch-capability-reference.md` | `.dev/docs/hosted-web-search/reports/` 下同名 |
| `:72` | `docs/tmp/260821-copilot-api-js-websearch-response-side.md` | 同上 |
| `:73` | `docs/tmp/260821-responses-websearch-citation-evidence.md` | 同上 |
| `:74` | `docs/tmp/260820-claude-code-websearch-request-forensics.md` | 同上 |
| `:76` | `docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md` | 同 `:55` |

它是活文档且是同伴今天写的，重指没有伪造记录的问题。

---

## 2. 建议改（不矛盾，但会误导读者）

### S1. §1 范围句把「真正执行」写成无条件的

`hosted-web-search-spec.md:19`：「请求经本项目路由到 **Responses 上游**并由上游 hosted web search 真正执行」。这是规格的目标态描述，本身没错；但整份规格没有任何一句划出「这是打开开关之后的行为」的前提。**只要在 §0 状态块加一句前提限定，§1、§3、§5、§6 的绝大部分条款就都不再需要逐条改**——它们描述的是「功能开启且模型被认领」这一支，那一支的行为确实没变。

我倾向的最小改法：在 `:6` 的状态行旁边加一条「**当前默认禁用**」，并在 §2 术语里把「能力门」拆成「功能开关 + 模型判定」两轴，然后 §8.3 按 M1 改写。

### S2. §12 证据权重表两处可以升级，一处该降级

- `:391`「§5.3 `annotations` 会真的填 `url_citation` | B7 有、C1 无，各一次 | 中等偏强」——现在有跨 4 个数据库、跨 2026-07-31 至 08-11、1082 个带 typed `url_citation` 对象的取证（`.dev/docs/hosted-web-search/reports/260821-responses-websearch-citation-evidence.md:18`）。可升级为「强」。这一条 `260821-responses-websearch-citation-evidence.md:332` 已经建议过，规格未动。
- `:407`「§9.3 | `gpt-5.` 前缀清单 | 唯一两个实测模型都在其下」——见 M3，该行描述的机制已不存在。
- `:15` 的「剩余修订项」列着 MJ-1/2/4/5/7/8 并以「**实现前必须先关闭这些项**」收尾。这句话现在读起来像「还没实现」（实现已在产：`hosted_web_search.py` + `composition.py` 里的注册接线）。

### S3. §3.4 与 §3.6 描述的「现状」是 legacy 链路

`:62`、`:79` 的论证与 `:97-100` 点名的 `src/app/protocols/anthropic_responses.py:538-540`，都属于生产不走的 legacy 链路。这一点 `.dev/docs/hosted-web-search/reports/260820-websearch-responses-leg-400-fix.md:177-181` 与 `260820-review-websearch-fix-second-opinion.md:66` 已实测钉死。**不是今天变更造成的**，但既然要动 §3 就一并修。

### S4. `models_support_web_search` 的 per-provider 作用域 —— **本条在报告写作期间被同伴的未提交改动修掉了**

原始发现（对 HEAD `767d0f2` 成立）：`status.md:16` 写键是 `model_providers.<name>.models_support_web_search`，位置准确，但 `composition.py` 当时把**所有 provider** 的模式合并成一个集合再传给门，代码注释给的理由是「模型 id 在目录里唯一，per-provider 查找无从消歧」。读者按配置文件形状会以为清单只对该 provider 生效，实际不是。

**现状**：工作树里有一份未提交的改动把它改成了 per-provider（`hosted_web_search.py` 新增 `compile_supported_by_provider`，其 docstring 逐字写「Merging them into one set was wrong, and the comment that justified it … answers a question nobody asked」；`composition.py` 改传 `{name: provider.models_support_web_search ...}` 并新增 `default_provider` 参数）。

所以**这一条不需要改文档，需要的是等那份改动落地后确认 `status.md:16` 的表述与它一致**。我保留这一条而不是删掉，是因为它记录了一次基线漂移：同一个事实在半小时内换了两个答案。

### S5. `.dev/docs/anthropic-responses-bridge/` 的三份活文档对整个 web search 切片零字

- `README.md` 的「权威边界」表仍未收录 `hosted-web-search-spec.md`（规格自己在 `:14` 登记了这条「索引待补」；`rg -i 'web|hosted' README.md` exit=1）。
- `implementation.md`（自称易变实施状态真相源）`rg 'hosted web search|hosted_web_search'` 零命中。
- `acceptance.md:101` 仍写「Web search 及其他 server／typed tools 按 server-tool no-revive 在 upstream 调用前 `REJECT`，不得由实现自行白名单化」。**这句在 Anthropic 腿上仍然成立**，但它没有划出 Responses 腿这条例外，而 `hosted-web-search-spec.md:363-366` 的 §11 覆盖清单正是为这条例外写的。建议在 `acceptance.md:101` 加一句指向 §11 的限定。

S5 的三条 `260820-closeout-loose-ends.md:106-110`（S6、S7）已报过，至今未动。

---

## 3. 不用改（看着像失真，其实成立）

这一节不是凑数：判据太宽会把下面这些一并报成缺陷，那会让整份对账不可信。

### N1. `docs/.human-controlled/config.example.yaml:218-222` 列的四个精确 id

```
    models_support_web_search:
      - gpt-5.6-sol
      - gpt-5.6-terra
      - gpt-5.6-luna
      - gpt-5.5
```

**行为完全没变。** `compile_supported` 不给条目加锚，判定用 `fullmatch`（`hosted_web_search.py:38` 的 docstring 专门解释了这个选择，就是为了让写成裸 model id 的旧条目继续只匹配自己）。四条各自 fullmatch 自身，与改成正则之前逐字等价。

唯一的技术性差异：正则里的 `.` 会匹配任意字符，所以 `gpt-5.6-sol` 现在也能匹配 `gpt-5X6-sol`。上游目录里没有这种 id，无实际影响。

另外这个文件是**用户亲笔、权威最高**，我只报告不建议改。它没有 `model_translation.to_openai_responses` 段，所以也没有一句关于 `hosted_web_search` 的陈述会因默认关闭而失真。

### N2. §5.1 与 §5.2 关于 `annotations` 可能为空的那几句

`:127`「后续 message 的 `annotations` **可能**带 `url_citation`……也可能是 `[]`——两个反向样本各一次」、`:133`「而且**可能整个是空数组**」。

这两句用的是「可能」，不是全称否定，而且 `260821-responses-websearch-citation-evidence.md:26/208` 的结论正是「`num_requests >= 1` 不蕴含 `annotations` 非空，降级分支不可省」。**它们与今天确认的事实同向，不需要改。** 需要改的只有 `:391` 的证据权重（见 S2），因为样本量从 2 个变成了上千个。

### N3. §6.3 的 2026-08-21 证据更正块（`:222`）

它已经把「cassette 实测表明」降级成「协议结构推断」，并换上了 history 库根帧的证据。P9（`:421`）也已标注结案。**这是唯一一处已经自己修好的地方**，不要重复处置。

### N4. §11 覆盖清单与 `spec.md:136`、`implementation.md:198` 的 no-revive 条款

`spec.md:136` 与 `implementation.md:198` 说 server tool 一律 `REJECT`。看起来与「Responses 腿支持 web search」矛盾，但 `hosted-web-search-spec.md:357-366` 的 §11 正是为此写的定点覆盖清单，逐条列出被覆盖的 `spec.md` 行号。**分层是完整的，母规格不该改。** 该补的是 `acceptance.md:101` 的那句限定（S5）。

### N5. §9.3 的「已知误判」清单（`:326`）

「假阳性最可疑的是 `gpt-5.3-codex`，其次 `gpt-5.4-mini`／`gpt-5.6-luna`；假阴性是 `grok-4.5`／`grok-4.6`、`mai-code-*`、`gpt-5-mini`」——这几条在新默认值下**逐条依然成立**：`gpt-[5-9]\.\d+.*` 仍然 fullmatch `gpt-5.3-codex`、`gpt-5.4-mini`、`gpt-5.6-luna`，仍然不匹配 `grok-*`、`mai-code-*`、`gpt-5-mini`（无点分小版本）。误判集合本身没变，只是获得方式从枚举变成了模式。

### N6. `README.md`、`TODO_CURRENT.md`、`CLAUDE.md`、`.claude/rules/00-development-workflow.md`

对 `web[ _-]?search`（大小写不敏感）**零命中，exit=1**。同一模式在 `.dev/docs` 下命中 100+ 文件，所以零命中是真的零。这四处不需要任何改动。

### N7. `.dev/docs/hosted-web-search/reports/` 下的全部 22 份报告原件

按 `.claude/rules/00-development-workflow.md`「报告原件是时点记录，改写路径与行号会伪造记录」，**一份都不改**。其中被今天变更推翻的结论列在第 4 节，处置方式是在活文档里写下更正，不是回去改报告。

---

## 4. 260820／260821 报告批次：结论已被推翻的可疑清单

**处置一律是「不改原件」**，列出来是为了让活文档在引用它们时知道哪几句不能再引。可疑度按「被引用后会导致错误决策」的概率排。

| 可疑度 | 文件:行 | 已被推翻的那句 | 推翻它的东西 |
|---|---|---|---|
| **高** | `260821-responses-leg-websearch-capability-reference.md:57` | 「默认值是**我挑的七个模型**。判据来自『目录里 vendor 为 OpenAI 且广告 `/responses`』」 | `5b8c56a`：一条正则 `gpt-[5-9]\.\d+.*`，判据是名字里的点 |
| **高** | `260821-responses-leg-websearch-capability-reference.md:69` | 「我们自己两份 cassette 的 `annotations` 都是 `[]`……**仍需探针**」 | `260821-responses-websearch-citation-evidence.md:18`：1082 个 typed `url_citation` 对象，探针已答。**这是任务提到的「已被显式更正的那两处」之外的第三处未更正实例** |
| **高** | `260820-websearch-responses-leg-mapping.md:59-67`（§2.4） | 能力门「不通过时**返回 400**」 | 实为抛 `WebSearchNotExecutable` → 合成失败结果。`260820-closeout-loose-ends.md:134` 已报 |
| **高** | `260820-websearch-responses-leg-mapping.md:176-178`（§5.3） | 「能力门**未实现**……本片未做」 | 已实现，且与同文 §2.4 直接打架。`260820-closeout-loose-ends.md:135` 已报 |
| 中 | `260820-websearch-responses-leg-mapping.md:170-174`（§5.2） | 「Anthropic 客户端的 forced tool choice **从未**到达上游」 | `_carry_forced_search`（`src/app/pipeline/translation_driver/openai_responses.py:621`，调用点 `:738`）让指向 web search 的那条到达了。`260820-closeout-loose-ends.md:136` 已报 |
| 中 | `260820-websearch-responses-leg-mapping.md:148` | 「能力门 | 在产腿上**完全没有**」 | 能力门已在产 |
| 中 | `260820-websearch-responses-leg-mapping.md:182` | 「上游后续 message 的 `annotations`……目前**丢弃**」 | 「丢弃」仍然为真（零处读取），但「两个反向样本各一次」的样本量描述已过时 |
| 中 | `260820-websearch-upstream-probe.md:276`、`:284-286` | 七个模型的默认清单与逐个误判判断 | 清单形态已变（误判集合本身仍成立，见 N5） |
| 中 | `260820-websearch-400-our-side.md:105-106` | 广告 `/responses` 的模型枚举被当作清单来源 | 同上 |
| 中 | `260820-review-hosted-web-search-spec.md:114`、`:125-129` | 「配置键名待与 `config.example.yaml` 对齐」「建议 `inbound.hosted_web_search:` 扁平键」 | 键名已定为 `models_support_web_search` + `model_translation.to_openai_responses.hosted_web_search`，走的是 `model_translation` 命名空间而非 `inbound` |
| 中 | `260820-review-websearch-fix-second-opinion.md:138-142`、`:178` | 「行为上确实对应 §8.3（剥离、记 DEGRADE、不 REJECT）」 | §8.3 那条路本身已被用户裁决推翻 |
| 低 | `260820-closeout-loose-ends.md:126-128`（D1 表） | 三处代码注释被自己的代码推翻 | 需复核这三处注释今天是否已随 `5b8c56a`／`767d0f2` 更新——**我未逐条核对，标为待查** |
| 低 | `260820-client-e2e-group.md:99-100` | 待建的 e2e 场景清单 | 场景本身仍有效，但「不在清单」不再是唯一的拒绝理由，多了「开关关着」一支 |
| 低 | `260821-copilot-api-js-websearch-response-side.md:135` | 「实测样本里是 `[]` 空数组」 | 同文 `:166` 与 `:343` 已显式更正，**这一行是表格里的残留**，可疑度低因为读者会读到旁边的更正 |

**扫描方式与限定**：用 `rg` 按关键词扫（`合成失败|剥离声明|返回 400|能力门`、`annotations`、七个模型 id、`允许清单|白名单|精确匹配|清单`），**未逐份精读**。所以这张表的性质是「值得复核的位置」，**不是「已被推翻结论的完整集合」**。凡标「高」的我读过上下文并确认矛盾；标「中」「低」的只读了命中行及其相邻数行。

---

## 5. 搬迁之后的链接与路径引文对账（额外要求）

### 5.1 结论

- **活文档里的 Markdown 相对链接：0 处断链。** 49 份活文档、全部 `](...)` 形式的相对链接逐个解析，无一指向不存在的文件。同一段脚本对 638 份 md 全量跑出 34 处断链，证明它有分辨力。搬迁把活文档的链接改对了。
- **活文档里的裸路径引文（不是链接、只是正文里写了一个路径）：有残留。** 逐条见下。
- **报告原件里的断链：34 处中的绝大多数，一律不动。**

### 5.2 该重指的（活文档，裸路径引文失效）

| 文件:行 | 引文 | 判断 |
|---|---|---|
| `.dev/docs/hosted-web-search/status.md:5,55,57,71,72,73,74,76` | 8 处 `docs/tmp/` 与 `docs/agents/` | **该改**，见 M5。今天新写的活文档，搬迁时漏改 |
| `.dev/docs/anthropic-responses-bridge/research.md:63` | `/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/tool-use.md:3-12` 与 `.../request-pipeline.md:24-36` | **该改**：现址 `.dev/docs/archived-2604-rewrite/`。注意这是**引证前提**而非单纯链接——`archived-2604-rewrite/README.md:7` 已裁定那批笔记「不得当作裁决、契约或当前行为」，所以重指之后这句论证本身也需要重判 |
| `.dev/docs/history/proposal.md:261` | `docs/2604-rewrite/history-system.md` 的设计明写 `busy_timeout = 5000` | **该改**路径；同样带引证前提问题（`archived-2604-rewrite/README.md:15` 已把这条列为受影响项） |
| `.dev/docs/documentation-restructure/README.md:3,21` | 两处 `docs/2604-rewrite/` | **该改**：现址 `.dev/docs/archived-2604-rewrite/` |
| `.dev/docs/tui/spec.md:9,13` | `docs/2604-rewrite/telemetry-observability.md`、`docs/2604-rewrite/lib-survey/SELECTIONS.md` | **该改**路径。同一文件 `:13` 后半句已经用了新路径 `.dev/docs/tui/archive-footer/`，所以是半改状态 |
| `.dev/docs/delivery-keepalive/deferred.md:102` | 「把 `docs/agents/` 整体移到了 `.dev/docs/`」 | **不该改**：这是在**叙述搬迁这件事**，路径是事件的宾语。改了反而不通 |

### 5.3 不该改的（时点记录 / 已自带说明）

| 文件:行 | 为什么不改 |
|---|---|
| `.dev/docs/graceful-shutdown/client-side/README.md:120` | 原文自己写着「当时几条提交的 `Docs:` 尾注逐字写的是 `docs/tmp/260820-*.md`……历史没有重写，尾注保持原样，`git log` 里仍按 `docs/tmp/` 搜得到」。这是**引用 commit trailer 的原句**，改了就对不上 `git log` |
| `.dev/docs/graceful-shutdown/client-side/README.md:124` | 同段落已经把「已移入 `.dev/docs/archived-2604-rewrite/`」写清楚了，旧路径是被裁决的对象 |
| `.dev/docs/systemd-runtime/plan.md:259` | 原文括注「原引 `docs/tmp/260807-systemd-user-manager-diagnosis.md`；该名在任何 ref 与批次清单里都不存在，**搬迁前即为断链**，未替它猜目标」。已诚实标注，不要替它猜 |
| `.dev/docs/graceful-shutdown/README.md:15` | 「（2026-08-21 之前它们在主仓库 `docs/agents/` 下。）」——时间限定已写在句内 |
| `.dev/docs/archived-2604-rewrite/**`（含 README、plan/、lib-survey/） | 该目录 README `:5` 明写「逐字节未改地搬到这里」。**逐字节未改是它的存在方式**，改任何一处都破坏这个性质 |
| `.dev/docs/tmp/260807-*.md`、`260820-*.md`、`260821-*.md`（11 份，合计约 50 处） | 报告原件 |
| `.dev/docs/sync-refs/sxwxs-ghc-api/260821-*.md`（4 份） | 带日期前缀的报告原件，虽然位置在话题根而非 `reports/` |
| 34 处断链中位于 `reports/`、`archive-*/`、`evidence/` 下的 30 处 | 报告原件与归档 |

### 5.4 断链里两处值得单独点名（仍不改）

- `.dev/docs/hosted-web-search/reports/260820-websearch-responses-leg-400-fix.md:216` 与 `260820-websearch-responses-leg-mapping.md:238` 都链向 `../agents/anthropic-responses-bridge/hosted-web-search-spec.md`。这个相对路径**在搬迁前就已经是错的**（当时它们在 `docs/tmp/`，正确写法是 `../agents/...` 相对于 `docs/`，而链接是相对于文件所在目录解析的）。搬迁没有制造这两处断链，只是没修它们。
- `.dev/docs/anthropic-responses-bridge/reports/260807-review-implementation-current.md:3` 链向 `../agents/anthropic-responses-bridge/spec.md`，同一形态。

---

## 6. 交回主会话的问题

1. **M4（域名限制默认值）不该由文档对账单方面改。** 规格 §3.4 与 §14 D1 记的是**用户亲自裁决**的三取值、默认 `error`；实现改成了两取值、默认 `drop_fields`，理由写在 `schema.py` 注释里且很强（190/190 真实子请求都带非空 `allowed_domains`）。这属于「已裁决事项被实现单方面改写」，`260820-closeout-loose-ends.md:86` 两天前就建议回到用户手上，至今未办。**建议连同「默认关闭」一起做成一次裁决请求**——两件事的取舍逻辑是同一个。
2. **第 4 节标「低」的那一条待查项**：`260820-closeout-loose-ends.md:126-128` 报的三处代码注释漂移（`openai_responses.py:277`／`:200`、`schema.py:114-115`），我**没有**逐条核对它们在 `5b8c56a`／`767d0f2` 之后是否已修。这是代码注释不是文档树，超出本次范围，但它与 M1／M2 是同一组事实。
3. **规格 §0 状态块（`:6`、`:15`）的「DRAFT / 实现前必须先关闭这些项」需要一次状态重判**：实现已经在产，MJ-1/2/4/5/7/8 里有几条（MJ-5「§9.3 默认值运行期谓词 vs 冻结字面量两解并存」）已经被 `5b8c56a` 事实上裁决掉了（选了模式，既非运行期谓词也非冻结字面量），有几条（MJ-4「§8.3 与 §3.4 组合情形未定义」）因为 §8.3 本身要重写而需要重新提问。**这不是我能替规格作者决定的。**
4. **`.dev/docs/hosted-web-search/` 现在有 `status.md` 但没有 `README.md`**，而 `.dev/docs/anthropic-responses-bridge/README.md` 的权威边界表仍未收录 `hosted-web-search-spec.md`（规格 `:14` 自己登记的欠账）。两个话题目录之间的从属关系目前只靠相对链接维持——规格在 `anthropic-responses-bridge/`，全部证据与状态在 `hosted-web-search/`。是否要把规格也搬到 `hosted-web-search/`，需要主会话裁定。

---

## 附：核对了什么、没核对什么

**一手核对过（读了全文或相关整节）**：`src/app/pipeline/subscribers/hosted_web_search.py` 全文、`src/app/config/schema.py:115-260`、`src/app/server/composition.py` 的订阅者接线段、`src/app/pipeline/subscribers/__init__.py` 的注册段、`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md` 全文（465 行）、`.dev/docs/hosted-web-search/status.md` 全文、`260820-closeout-loose-ends.md` 的 §0–§2.3、`260821-responses-leg-websearch-capability-reference.md` 全文、`5b8c56a`／`767d0f2`／`9aa31f9` 的完整提交说明与 `--stat`。

**关于 `src/` 行号**：正文里引的 `hosted_web_search.py` 行号取自 **HEAD `767d0f2`**（`if enabled and …` 在 `:81`，两处 `raise WebSearchNotExecutable` 在 `:96` 与 `:106`）。工作树里那份未提交的改动把它们推到了 `:100`／`:115`／`:125`。`schema.py` 的 `:125`／`:233`／`:256` 两边一致。`composition.py` 的行号刻意不写死，因为那正是被改动的地方。

**只读了命中行及邻近数行**：第 4 节标「中」「低」的条目、`.dev/docs/` 其余 100 余份提及 web search 的文件。

**完全未核对**：`exp/260820-websearch-probe/raw/` 下的原始探针输出（任务已声明为既有事实，未复验）；`tests/` 下的测试是否与规格一致；三处代码注释漂移的当前状态（见第 6 节第 2 点）。

**未执行任何写操作**，除本文件外没有创建、修改或删除任何文件；未触碰任何仓库的 git 状态（主仓与 `.dev` 均未 add／commit／stash）。
