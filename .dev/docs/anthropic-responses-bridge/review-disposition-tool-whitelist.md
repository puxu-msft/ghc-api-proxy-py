# 评审处置：Responses 腿的 tool 字段白名单

对象：[reports/260824-tool-whitelist-implementation-review.md](reports/260824-tool-whitelist-implementation-review.md)，异源模型（GPT）独立评审，**0 blocker / 4 major / 7 minor / 1 nit**。

处置日期：2026-08-24。

> **2026-08-25 追记（原文不改）**：本文第 2 节记录的「用户裁定 tool search 不是本代理提供的能力」**已被同一位用户次日的裁决推翻**——客户端声明的 tool search 现在被翻译，见 [spec.md](spec.md)「Tools 与 tool choice」与 [review-disposition-tool-search.md](review-disposition-tool-search.md)。仍然有效的是那条裁决的另一半：代理不得**主动注入**客户端没要求的 tool search，被删掉的两个 legacy 开关也不恢复。
>
> 本文其余内容是 2026-08-24 那次处置的时点记录，按项目规则不重写。加这条注记而不改正文，是因为被复述错的是一条**用户裁决**——一个未来的读者可能拿它当一手复述，据以把已经做好的翻译再撤回去。

## 四条 major

| 编号 | 处置 | 落点 |
|---|---|---|
| R1 | **采纳，且这是本轮唯一的真缺陷** | `openai_responses.py` 的 `_function_tool` 早返回；spec「白名单只管 function tool」一条；新增 union 成员测试 |
| R2 | 采纳，两个残留面写进 Spec 正文 | spec「Tools 与 tool choice」新增两条编号项 |
| R3 | 采纳，越界处收窄 | spec:147 |
| R4 | 采纳（一半由 R1 顺带解决），其余记为设计事实 | 见下 |

### R1：白名单量错了对象

**这一条我写错了，而且写错的方式很典型：我在 docstring 里替一个我没有验证过的性质做了担保。** 原文说「一个已经是 Responses 形状的 tool，它携带的一切按构造都在白名单里，所以早返回可以去掉」——白名单是 `FunctionToolParam` 的，而 `_function_tool` 收的是整个 `ToolParam` 联合。评审实测 `web_search.user_location`、`mcp.server_url`、`custom.format` 三个字段被静默吃掉。

「按构造」这四个字是没有依据的：我没有去看 union 里其它成员长什么样就写下了它。生产今天到不了这条路径（Responses→Responses 不翻译），但测试套件在走，而且**「不可达」不是一个值得用静默丢数据去编码的性质**。

修法是恢复一个早返回，但判据比原来准确：声明了 `type` 且不是 `function`、又没有 Anthropic 的 `input_schema` 的条目，原样通过。新增测试三个 builtin 各带一个自有字段，做过变异（去掉早返回 → 变红）。

### R2：响亮的失败换成了安静的失败

采纳。评审的措辞值得原样留下：修掉 400 之后，客户端会走进 `tool_reference → output: ""` 这条**静默**失效。这一条本身不是本次引入的（既有的 tool_result flatten 行为），但本次改变了它的可见性——原先请求整个 400，现在请求成功、模型收到一次空的工具搜索结果。

它和「`tool_search_tool_regex_*` 必然 400」两项原本只写在 `.dev/docs/tmp/` 的调查报告里。**这正是本项目付过一次代价的形态**（`.dev/docs/anthropic-direct-request-shape` 那边的调查记录了同一件事：两份四天前的报告早就查出过 `cache_control` 的缺口，事实没进活文档，今天以线上 400 的形式重现）。已写进 Spec 正文并标注哪些是本次引入、哪些是既有。

### R3：把一句裁决读宽了

采纳，**这是我第二次在同一天犯这个错**（前一次是 `cache_control` 那边的 blocker：用本文自己新写的解释去覆盖用户定义的默认档）。

用户说的是 tool search 不是本代理提供的能力。我在 spec:147 把它写成了支撑「`memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_` 五族都不映射」的依据。五族里用户只提了一族。已收窄：其余四族不映射的依据仍然只是 Server-tool no-revive，与本次裁决无关。

**另一半——「用户裁定」在 `docs/.human-controlled/` 零命中——是事实且不能靠改措辞解决。** 该裁决来自 2026-08-24 的会话，尚未落进用户亲笔文档。这与本仓既有的 A-5 同形（`anthropic-direct-request-shape` 的 effort 裁决也还没落进用户文档）。处理方式相同：Spec 里注明来源是会话裁决，等用户追认。

### R4：两个函数对未知字段的策略不一致

`_web_search_tool` 对白名单外字段 raise，新的 `_function_tool` 静默剥离。

- **`web_fetch.allowed_domains` 被吃这一格，由 R1 的修复顺带解决**：`web_fetch_*` 声明了一个本白名单不认领的 `type`，现在原样通过，不再被 function tool 的白名单量。（它随后会被上游拒绝——那是 Server-tool no-revive 说的 REJECT，本应在 capability gate 拦下，`subscribers/server_tools.py` 今天不拦这一族。既有缺口，已随 R2 记进 Spec。）
- **剩下的不一致是有理由的，保留**：web search 的未知字段是**语义约束**（`allowed_domains` / `blocked_domains`），丢掉一个会把「限制」变成「无限制」，而且结果永远不经过本代理，没有任何下游能察觉——代码里那段注释早就写明了这一点。function tool 的未知字段没有这个性质。同一个动作在两处的代价不同，所以策略不同不是疏漏。

## 七条 minor 与一条 nit

未逐条展开，处置随上面四条一并落地或记录：测试分辨力相关的（R7 一族）已由 R1 的新用例与既有变异覆盖；`LossCode` 是否新开成员（R9）**不采纳新开**——`EXTENSIONS_NOT_CARRIED` 的既有语义（「扩展字段没带过去」）与本用法一致，`SERVER_TOOL_CONSTRAINT_DROPPED` 用于 `defer_loading` 是因为它丢的是与 server tool 绑定的能力约束，与 web search 的 `max_uses` 同族。

## 评审的一处自我校正，值得记下

评审对第 6 点（我把负控制断言从 `conversion.lossless` 收窄到两个具体 code，是必要还是掩盖）的结论是「**收窄是必要的、不是掩盖**」，并给了依据：共享夹具恰好只产生一条 `system-metadata-not-carried`，而白名单路径能产生的 code 只有那两个。它没有为了给出一个更"严厉"的结论而硬判。

## 派发提示里的一处不实

我在派发提示里写了「低概率扩展删除第 5 项」，评审核对后指出工作树里不存在第 5 项。**评审是对的，我的提示有误导**：我先加了第 5 项（把 hosted tool_search 映射列为待裁决扩展），随后用户裁决不做，我又把它删掉了，净效果是 HEAD 从未有过第 5 项。评审没有被这句错误的提示带走，而是去核对了工作树——这正是派发提示里的背景应当被独立核实的理由。
