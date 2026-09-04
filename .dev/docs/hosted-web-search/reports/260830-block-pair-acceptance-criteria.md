# 搜索块对（`server_tool_use` + `web_search_tool_result`）独立验收矩阵

> **落盘位置说明（写给主会话，读完可删）**：本文原定路径是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/reports/260830-block-pair-acceptance-criteria.md`。写入被 harness 的隔离守卫拦下（提示「This subagent's parent bg session hasn't isolated yet, so writes to the shared checkout are blocked」），守卫明确允许工作树内路径，故落在隔离工作树内的**同名相对路径**下：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate/.dev/docs/hosted-web-search/reports/260830-block-pair-acceptance-criteria.md`。`.dev/` 在两棵树里都被 gitignore，所以没有 git 噪声。**请主会话把它移到主树对应路径。** 我没有绕过守卫（未用 Bash 写共享 checkout）。

**日期**：2026-08-30
**角色**：独立验收者（`my-skills:as-verifier`），在读任何实现代码之前建立判据
**判据来源**：`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md`（2026-08-30 当前版本，528 行，含当日两次修订），重点 §1、§5.2、§5.3、§5.4、§6.1、§6.3、§8.3、§8.4、§9.0
**被检对象**：尚未实现的「Responses `web_search_call` → Anthropic 块对」行为，**以及它将来自带的那些测试**

## 0. 这份文件是什么，不是什么

它是**冻结的验收矩阵**，在打开实现之前写成。按 `as-verifier` 的约定，此后它只能因为「规格说了而我漏了」而增补，**不能因为「实现原来是这样」而修改**。

**本轮没有执行任何验证**：被验对象尚未实现，且本次任务明确禁止读取 `src/app/pipeline/delivery/formats/openai_responses.py`、`src/app/pipeline/translation_driver/openai_responses.py` 与任何现有测试。因此每一条判据的结论栏一律是 `未验证（实现未就绪）`，这是 `as-verifier` 认可的合格终态，**不得被读成「通过」**。

**我读了什么**（全部列出，便于判断污染面）：

| 读了 | 为什么允许 | 只取了哪一层 |
|---|---|---|
| `hosted-web-search-spec.md` 全文 | 判据来源 | 全部 |
| `src/app/pipeline/delivery/blocks.py` | 输出契约（`CompletedBlock` 的定义与缓冲策略） | `CompletedBlock` 字段、`BlockBuffer.add` 的策略分支 |
| `src/app/pipeline/delivery/formats/anthropic_messages.py` L36-278 | 输出契约（块 → Anthropic SSE 帧） | `block_frames`、`_delta_for`、`terminal_frames`、`render`、`AnthropicFramer` |
| `src/app/pipeline/delivery/formats/anthropic_messages_synthetic_reply.py` L60-104 | §8.3 的**已在产**合成路径，是块对形态的姊妹契约，不是本次被验对象 | `failed_search_blocks` 的两个 dict 与 `stop_reason` |
| `.venv/.../anthropic/types/*`（1.0.0）、uv 缓存中的 0.59.0／0.77.0、`@anthropic-ai/sdk` 0.116.0 的 `messages.d.ts` | P12 探针的 ground truth | 五个类型定义 |
| `https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool` | P12 探针的第二个独立来源 | Errors 一节、Response 一节、Streaming 一节 |

**没读**：两个被点名禁止的实现文件、任何现有测试、`subscribers/server_tools.py`、`protocols/anthropic_responses.py`。

---

## 1. 统一的观测装置（所有判据共用，只写一次）

**入口**：`POST /v1/messages`，body 含

```json
{
  "model": "<一个能通过 §9 能力门的模型，例如 gpt-5.5>",
  "max_tokens": 1024,
  "messages": [{"role": "user", "content": "<触发搜索的提问>"}],
  "tools": [{"type": "web_search_20250305", "name": "web_search"}]
}
```

`stream` 两个取值各跑一遍。配置须置 `model_translation.to_openai_responses.hosted_web_search: true`（§9.0 默认 `false`，不开则永远走 §8.3 合成路径，**整个矩阵会在一个假通过上收敛**）。

**上游**：受控 Responses SSE ／非流式 body，按各判据给出的 item 序列构造。优先用 `tests/int/cassettes/` 的真实存证；但规格 §12 已记明现有两份 web-search cassette 的 `annotations` **皆为空数组**，所以**凡涉及 citation 的判据，现有 cassette 一律没有分辨力**，必须重录，或按 §6.3 引用的 history 根帧证据（`260821-responses-websearch-citation-evidence.md`）派生。

**观测点**（按可信度从高到低，判据里逐条指定用哪个）：

- **O1 — 原始字节**：客户端 socket 上收到的完整字节流／JSON body。`content_block_start` / `content_block_delta` / `content_block_stop` 逐帧解析，**不经过本项目自己的任何解析器**。这是唯一能发现「framer 层丢字段」的观测点。
- **O2 — 重建块序列**：把 O1 的 SSE 按 Anthropic 官方语义重建成 `content[]`（`content_block_start.content_block` 为底，叠加 delta）。非流式直接就是 `content[]`。
- **O3 — facts**：`ConversionFact` 落到 History（`history-v3*.db`）、日志行、footer。
- **O4 — 第三方校验器**：把 O2 的块喂 `anthropic` SDK 1.0.0 的类型（`ServerToolUseBlockParam` / `WebSearchToolResultBlockParam`）。**这是一个来源完全独立于本项目的 oracle**，用于 AC-10、AC-11、AC-12；但在 AC-03b 与 AC-12 上它会**反向说谎**，见各条。

> **关于 O2 的一个陷阱，先写在这里，因为它污染大半个矩阵**：`anthropic_messages.py:54 _delta_for()` 对 `text` ／ `thinking` ／ `tool_use` 之外的 kind 返回 `None`，`block_frames()` 也只对这三种 kind 清空 start payload。所以一个 kind 为 `server_tool_use` 的块，**整个 payload 会随 `content_block_start` 一次发出，且没有任何 `content_block_delta`**。而 Anthropic 官方文档的 streaming 示例里，`server_tool_use` 的 `input` 是靠 `input_json_delta` 送的（`content_block_start` 只带 `{"type","id","name"}`）。**一个只做 O2 重建的验收会把两种形态都判通过，而一个照官方语义写的客户端解析器可能只认后者。** 见 SPEC-GAP-4。

---

## 2. 验收矩阵

字段约定：**陈述**（用户可观察行为）／**规格来源**／**观测**／**通过侧**／**失败侧**／**可能骗过它的假象**／**结论**。

### 2.1 `server_tool_use` 块的字段

---

**AC-01 — call 块的类型与工具名**

- **陈述**：客户端在块对的第一个块上看到 `"type":"server_tool_use"` 且 `"name":"web_search"`。
- **规格来源**：§5.3 字段表前两行（`type` = `server_tool_use`，`name` = `web_search`）。
- **观测**：O1 取 `content_block_start.content_block`；O2 取 `content[i]`。
- **通过侧**：两个键逐字为上述值。
- **失败侧**：`name` 透传客户端声明里的 `name`（客户端可以把它命名成任何东西——§4 已就反方向警告过「不得按 `name` 字符串直接判断」）；或 `type` 写成 `tool_use`（客户端会当成要自己执行的工具，多一次空转往返）。
- **假象**：夹具里客户端声明的 `name` 恰好就是 `web_search`，于是「透传客户端 name」与「固定写 web_search」**逐字符同形**。→ 必须用一个把 `name` 声明成 `web_search_but_different` 的请求跑一次。
- **结论**：未验证（实现未就绪）。

---

**AC-02 — call 块的 id 由 `output_index` 派生，且不是上游句柄**

- **陈述**：`id` 形如 `srvtoolu_ws_<output_index>`；客户端**永远看不到**上游那个 416 字符的句柄。
- **规格来源**：§5.3「`id` **必须**由 `output_index` 派生，**不得**使用上游那个 416 字符的句柄」；§7.2「`web_search_call` 的 `id` **必须**在转换出 Anthropic wire 时丢弃」并记 `DEGRADE`（`server_tool_call_id_not_carried`）。
- **观测**：O2 读 `id`；**外加**对整个响应字节流做否定检查——上游 fixture 里那五个 id 的任何一个（含任意 10 字符前缀）都不得出现在 O1 的任何字节里。
- **通过侧**：`output_index == 0` 时 `id == "srvtoolu_ws_0"`；否定检查零命中。
- **失败侧**：`id` 是上游句柄；或是随机 UUID（不可由 `output_index` 复现，破坏流式／非流式的可比性）；或句柄泄漏在别处（塞进 `input`、或某条 fact 的 wire 侧）。
- **假象**：**（a）**上游 fixture 的 id 短且形似 `ws_0`，「派生」与「透传」同形——fixture 必须用真实的 416 字符句柄，且五个事件各不相同（§6.1 实测形态）。**（b）**否定检查只查完整句柄；实现若做了截断（取前 32 字符）就查不出来，必须查前缀。**（c）**`DEGRADE` fact 的编码写对了但 fact 根本没发出，而日志「有才打印」——缺席与不报同形，须查 History 表而不是日志文本。
- **结论**：未验证（实现未就绪）。

---

**AC-03a — `input.query` 的来源与 `queries` 连接**

- **陈述**：`input.query` 等于上游 `action.query`；`action.query` 缺失而 `action.queries` 存在时，等于 `queries` 各项以 `", "`（逗号加一个空格）连接的结果。
- **规格来源**：§5.3 字段表 `input` 行：`{"query": <action.query，缺失时取 action.queries 以 ", " 连接，都没有则省略 input>}`。
- **观测**：O2 读 `content[i].input.query`。三个上游变体：`{query:"a", queries:["a"]}`（实测常态，§5.1）、`{queries:["a","b"]}` 无 `query`、`{query:"a"}` 无 `queries`。
- **通过侧**：分别得到 `"a"`、`"a, b"`、`"a"`。
- **失败侧**：用 `", "` 之外的分隔符（`","`、`" "`、`" | "`）；或在两者同时存在时改用 `queries` 连接；或把 `queries` 原样塞进 `input`（多出一个规格未授权的键）。
- **假象**：**这一条最容易被夹具消解。** 实测常态是 `query` 与 `queries[0]` 相同且 `queries` 只有一项，此时「读 query」「读 queries[0]」「以任意分隔符连接单元素 queries」**三种实现产出逐字相同**。分辨力只来自 `queries` 长度 ≥ 2 且不含 `query` 的那个变体——而该变体**在本项目一手样本里不存在**（§5.1 只记录了同值形态），所以它是构造样本，报告里必须标明它没有上游实测背书。
- **结论**：未验证（实现未就绪）。

---

**AC-03b — 两者皆无时省略整个 `input` 键**

- **陈述**：`action` 缺失、或既无 `query` 也无 `queries` 时，块上**没有 `input` 这个键**——不是 `{}`，不是 `{"query": ""}`，不是 `{"query": null}`。
- **规格来源**：§5.3 字段表「都没有则省略 input」；§6.3「`action` 缺失**必须**被容忍，按 §5.3 渲染为不带查询的形态」；§5.1 记录 `status:"incomplete"` 时可能整个缺 `action`。
- **观测**：O2 上 `"input" not in block`。
- **通过侧**：键不存在。
- **失败侧**：出现 `input: {}` 或空串 query。这不是等价形态：空串是一个断言（「模型搜了空查询」），键不存在是「我们没有这个信息」——与 §5.3 对 `encrypted_content` 的论证同构。
- **假象**：**O4 在这条上会反向说谎。** `anthropic` 1.0.0 的 `ServerToolUseBlockParam` 把 `input` 标为 `Required[Dict[str, object]]`（`.venv/lib/python3.14/site-packages/anthropic/types/server_tool_use_block_param.py:21`），所以**规格要求的形态是 schema-invalid 的**。一个把「SDK 校验通过」当验收 oracle 的实现会被推着去填 `{}`，恰好违反本条。→ 本条的 oracle 必须是规格原文；O4 在本条上只可用于**记录**这处偏离，不可用于判定。
- **附带发现**：§5.3 为 `encrypted_content` 的省略写了整段论证并声明「这是**有意的**」，对 `input` 的省略**没有写**同样的话。见 SPEC-GAP-5。
- **结论**：未验证（实现未就绪）。

---

**AC-04 — query 已 strip 首尾空白**

- **陈述**：`input.query` 不以空白字符开头或结尾。
- **规格来源**：§5.3「`query` **必须**已 strip 首尾空白。上游拒收结尾带空白的 assistant 轮次」。
- **观测**：O2 上 `q == q.strip()`。上游变体：`{"query": "  weather in NYC\n"}`。
- **通过侧**：`"weather in NYC"`。
- **失败侧**：保留任一侧空白；或做了超出 strip 的规范化（压掉内部换行、collapse 连续空格）——规格只授权首尾。
- **假象**：**（a）**所有夹具的 query 都是干净字面量，于是有没有 strip 同形。**（b）**`queries` 连接路径（AC-03a）单独实现，strip 只加在 `query` 分支上——必须对连接路径也验一次；且 `["a ", " b"]` 上「每项各自 strip 再连接」与「连接后整体 strip」结果不同，规格未指明，见 SPEC-GAP-6。
- **结论**：未验证（实现未就绪）。

---

**AC-05 — result 块的 `tool_use_id` 与紧邻 call 块配对**

- **陈述**：`web_search_tool_result.tool_use_id` 逐字等于**它前面那一个** `server_tool_use` 块的 `id`。
- **规格来源**：§5.3「一个 `server_tool_use`，紧随其后一个**同 `tool_use_id`** 的 `web_search_tool_result`」；§2「搜索块对」定义。
- **观测**：O2 逐对比较。关键样本：一个响应里两组「call → 文本」序列（`output_index` 0 与 2），产生两对块。
- **通过侧**：对 1 的 `tool_use_id == "srvtoolu_ws_0"`，对 2 的 `== "srvtoolu_ws_2"`。
- **失败侧**：两对交叉配对；result 引用了响应里不存在的 id；所有 result 都引用最后一个 call。
- **假象**：**单 call 样本上任何配对错误都不可见**——只有一个 id，交叉与正确同形。必须用双 call 样本；且两个 `output_index` 要不连续（用 0 与 2，别用 0 与 1），否则「off-by-one 的 index 派生」也能蒙对。
- **结论**：未验证（实现未就绪）。

---

### 2.2 `web_search_tool_result.content` 的三个分支

> **前置警告**：§5.3 的三分支表**条件不互斥**，且与 §6.3 的局部归因规则**计数口径冲突**。见 SPEC-GAP-1 与 SPEC-GAP-2。下面按我认定的操作性读法写（§6.3 优先），但**在冲突输入上不给结论**，也不把任一读法判成实现缺陷。

---

**AC-06 — 分支一：单 call + 有 citation → 结果列表**

- **陈述**：待归因队列中恰好一个 call、且随后完成的文本块带 `url_citation` annotations 时，`content` 是一个**列表**，每条 citation 一项 `{"type":"web_search_result","url":<url>,"title":<title>}`。
- **规格来源**：§5.3 content 表第一行；§6.3「只有当待归因队列中**恰好一个** call 时，才用该文本块的 `url_citation` 填充其 `content`」。
- **观测**：O2 读 `content`，断言它是 list；逐项与上游 annotation 的 `url`、`title` **逐字**比对。
- **通过侧**：项数等于去重后的 citation 数；每项键集**恰好三个**（`type`、`url`、`title`）；顺序与 annotations 数组顺序一致。
- **失败侧**：`content` 是裸对象（错分支）；项里多出 `page_age`、`encrypted_content`、`cited_text`、`encrypted_index`（后两个只存在于 `web_search_result_location`，出现即为跨结构挪用）；`url` 或 `title` 被改写。
- **假象**：**（a）**`title` 由 `url` 派生（取域名）在「title 恰好是域名」的样本上同形；夹具的 title 必须与 url 无字面关系。**（b）「content 填了」不等于「来源是 annotations」**——一个从模型正文正则抓 markdown 链接的实现也会填出形状正确的列表，且在同时带内联引用的真实样本上**结果可能一致**（§12 P10 记录了两种形式共存的样本）。分辨力只来自一个**内联 markdown 链接与 annotations 故意不一致**的构造样本。**这是本矩阵里我判断最容易被骗过的一条**，理由展开在 §4。
- **结论**：未验证（实现未就绪）。

---

**AC-07 — 去重按 `url`、保出现顺序、且 url 逐字不改写**

- **陈述**：同一 `url` 出现多次时只保留第一次；保留项的相对顺序是它们在 annotations 里首次出现的顺序；`url` 与 `title` **逐字**来自 annotation，不做任何规范化。
- **规格来源**：§5.3 content 表第一行「按出现顺序，按 `url` 去重」。规格**只授权按 `url` 去重**，未授权任何 url 规范化。
- **观测**：上游 annotations 构造为 `[A, B, A, C]`（A 重复），且**每个 url 都带 `?utm_source=openai` 尾巴**（一手样本形态）。O2 断言 `[url(A), url(B), url(C)]`。
- **通过侧**：三项，顺序 A、B、C；每个 url 含完整 `?utm_source=openai`。
- **失败侧**：**（a）**去重后重排（按 title 排序，或用 `set` 导致顺序不定）；**（b）**保留最后一次而非第一次；**（c）**剥掉 `?utm_source=openai` 再输出——那是代理擅自改写一条给人点击的地址，且与模型正文里的内联链接不再字面一致；**（d）先规范化再去重**——把 `x.com/a?utm_source=openai` 与 `x.com/a?utm_source=bing` 折叠成一条，静默丢掉一条真实来源。
- **假象**：**（a）**Python 的 `dict.fromkeys` 与 `set` 在小样本上顺序常常「看起来对」——判据必须用 ≥ 4 项、url 差异大的样本，且**在两个 `PYTHONHASHSEED` 不同的进程里各跑一次**才有分辨力。**（b）**夹具 url 若都不带 query string，则「逐字」与「剥 query」同形——一手样本带 `?utm_source=openai` 正是为此，**必须保留在夹具里**。**（c）**去重发生在 annotation 层还是 block 层，单文本块样本区分不了；需要 citation 跨两个 `content_part` 的样本（该形态是否存在未探针）。
- **结论**：未验证（实现未就绪）。

---

**AC-08 — 分支二：多于一个 call → error 形态，且该组全部落 error**

- **陈述**：待归因队列中多于一个 call 时，**该组每一个** call 的 result 块 `content` 都是 error 形态，且**各记一条** `DEGRADE`，编码 `web_search_results_unattributable`。
- **规格来源**：§5.3 content 表第二行；§6.3「队列中多于一个时，该组**全部**落 §5.3 的 error 形态并各记一条 `DEGRADE`」。
- **观测**：上游序列 `call(idx0) → call(idx1) → message(带 citations)`。O2 断言两对块、两个 result 的 content 都是 error 裸对象；O3 断言**恰好两条** `web_search_results_unattributable`。
- **通过侧**：两对、两条 fact；**且 citations 一条都没进 content**（不做归因是本条的全部意义）。
- **失败侧**：**（a）**把 citations 填给第一个 call（发明了一条关联关系，§5.2 第 2 条明令禁止）；**（b）**只记一条 fact（「各记一条」被读成「记一条」）；**（c）**只让第二个 call 落 error 而第一个拿到结果。
- **假象**：**（a）**「两个 call」的样本若让两个 call 之间夹着一个文本块，队列会在中间清空，于是**它其实是两次单 call 归因，本条根本没跑到**——夹具必须让两个 call 连续入队。这与 AC-05 的双 call 样本是**两个不同样本**，不能复用。**（b）**若实现按 §5.3 字面的全局计数判定，它在这个夹具上与局部规则同结果，**冲突不可见**；分辨力只来自 SPEC-GAP-1 的判别样本（AC-25）。
- **结论**：未验证（实现未就绪）。

---

**AC-09 — 分支三：无 citation 或 `status != completed` → error 形态**

- **陈述**：随后文本块没有 `url_citation`（含 `annotations: []`），或该 call 的 `status` 不是 `completed` 时，`content` 是 error 形态，并记 `DEGRADE`，编码 `web_search_results_not_representable`。
- **规格来源**：§5.3 content 表第三行；§6.3「`status` 不是 `completed` 时……**必须**照常入队并成块，按 §5.3 反映状态。**不得**因状态非终态而丢弃该 item」。
- **观测**：两个独立样本——(i) `status:"completed"` + `annotations: []`（**本项目现有 cassette 就是这个形态**）；(ii) `status:"incomplete"` 无 `action` + 有 citations（**该样本落在 SPEC-GAP-2 上，不计入本条结论**）。
- **通过侧**：样本 (i) 得到 error 裸对象 + 一条 `web_search_results_not_representable`。
- **失败侧**：**（a）**`content: []`（空列表）——§5.3 明令这是与事实相反的断言，Anthropic 官方文档独立确认「A search that succeeds but matches no results returns an empty `content` list, not an error」，即空列表在协议里读作「搜到了零条」；**（b）**块对整个被丢弃（客户端看不到搜索发生过）；**（c）**整轮 400（§6.3「不得丢弃」与 §8.4「不得失败」的反面）。
- **假象**：**（a）**`annotations` 键**缺失**与 `annotations: []` 是两个输入，实现常只处理其中一个；两个都要跑。**（b）**fact 编码写成了 AC-08 的 `web_search_results_unattributable`——两条 DEGRADE 都存在、都是 error 形态，**只有编码能区分它们**，而一个只断言「有一条 DEGRADE」的测试对此全盲。
- **结论**：未验证（实现未就绪）。

---

**AC-10 — error 形态是裸对象，不是单元素数组**

- **陈述**：error 分支下 `content` 的 JSON 值是 `{...}`，不是 `[{...}]`。
- **规格来源**：§5.3「error 形态**必须是裸对象**……**不得**包成单元素数组」，理由是在产的摊平实现 `subscribers/server_tools.py` 的 `_failure_of()` 只认 dict，包成数组会让 §5.4 的摊平静默产出 `[web_search results omitted]`。
- **观测**：O1 上直接看字节（`"content":{` 而非 `"content":[`）；O4 用 `WebSearchToolResultBlockContent` 的 union 判别。
- **通过侧**：`content` 是 object。
- **失败侧**：`content` 是 array。
- **独立佐证（非本项目来源）**：Anthropic 官方文档 Errors 一节逐字写「On an error, `content` is a single error object rather than a list of result blocks.」；`anthropic` 1.0.0 的 `web_search_tool_result_block_content.py:11` 把两支写成 `Union[WebSearchToolResultError, List[WebSearchResultBlock]]`，error 支不是 list。**三个来源同向**，本条的依据强度是「强，可直接据此实现」。
- **假象**：**这条最阴的失效不在块本身，而在下一轮。** 包成数组的响应对客户端**当轮完全正常**（照样渲染），失败要到**下一轮把历史发回来、走 §5.4 摊平**时才显形，显形方式是文本变成 `[web_search results omitted]`——**没有异常、没有日志**。所以只断言当轮 wire 的验收全绿也说明不了什么；本条**必须**配 AC-30 的二轮回灌验证。
- **结论**：未验证（实现未就绪）。

---

**AC-11 — `error_code` 取 `unavailable`**

- **陈述**：error 形态的 `error_code` 逐字为 `unavailable`。
- **规格来源**：§5.3 content 表第二、三行，并注明「该取值是否在 Anthropic 该块的合法枚举内，实现前必须核对（新增探针项 P12）」。
- **观测**：O2 读 `content.error_code`；O4 用 `WebSearchToolResultErrorCode` 校验。
- **通过侧**：`"unavailable"`。
- **失败侧**：任何其他取值；或自造码（`not_representable`、`unattributable`）——会让客户端落进未知分支。
- **P12 已结案**：`unavailable` **在合法枚举内**。完整枚举与证据见 §3。
- **假象**：AC-08 与 AC-09 两个分支用**同一个** `error_code`，所以**错误码本身不携带区分信息**；一个「按 error_code 分类」的验收会把两个分支混为一谈。区分只靠 DEGRADE 编码。
- **结论**：未验证（实现未就绪）。

---

**AC-12 — `encrypted_content` 必须省略（且结果项键集恰好三个）**

- **陈述**：每个 `web_search_result` 项上**没有 `encrypted_content` 这个键**；不是空串，不是占位串，不是 `null`。键集恰好 `{type, url, title}`。
- **规格来源**：§5.3「**`encrypted_content` 必须省略**，不得填空串、不得填占位串。省略是『我们没有这个句柄』，占位串是『这里有一个句柄』——后者是断言，且是假的」；§5.2 第 3 条。
- **观测**：O2 对每项断言 `set(item.keys()) == {"type","url","title"}`；**外加** O1 全字节否定检查：不得出现 `encrypted_content` 或 `encrypted_index`。
- **通过侧**：键不存在；否定检查零命中。
- **失败侧**：该键的任何取值，含 `""`、`null`、`"<omitted>"`、或复用上游 `web_search_call.id`——后者最诱人，因为那个 416 字符句柄「看起来像」加密句柄，但它是 call 的句柄不是 result 的，且 AC-02 已禁止它出现在 wire 上。
- **假象**：**（a）**`"encrypted_content": ""` 在一个只做 `assert "url" in item` 的测试下完全不可见；断言必须钉**键集全等**，不是包含关系。**（b）O4 在本条上同样反向说谎**：`WebSearchResultBlockParam.encrypted_content` 是 `Required[str]`（`.venv/.../types/web_search_result_block_param.py:12`），且官方文档写明「If `encrypted_content` is missing or modified, the request fails with a 400 validation error」——**规格要求的形态在 Anthropic 上游是非法的**。§5.3 已声明这是有意的，代价由 §5.4 摊平吸收、且这些块永不回喂 Anthropic 上游。**这使 AC-30 从「锦上添花」升级为本条的必要配套**：摊平一旦漏了一条路径，客户端下一轮就会吃 400。
- **结论**：未验证（实现未就绪）。

---

**AC-13 — `content: []` 与 error 裸对象是两种必须都产得出的形态**

- **陈述**：`<unsupported_constraints>` 取 `empty_result` 时，`content` 是**空列表 `[]`**；而 §5.3 ／ §8.3 的不可得情形是**裸 error 对象**。两者不得互相替代。
- **规格来源**：§3.4 `empty_result` 行「`content` 为**空列表** `[]`——即协议里『搜索跑了、零结果』的形态，不是错误」；§5.3 error 裸对象条；§8.3「后者 `content` 为单个 `{...}` 对象」。
- **观测**：两个配置各跑一次，O1 比较字节。
- **通过侧**：`"content":[]` 与 `"content":{"type":"web_search_tool_result_error",...}` 各自出现在各自路径上。
- **失败侧**：把两条路径收敛到一个构造函数上，于是其中一个形态永远产不出来（最可能的方向：`empty_result` 也发 error 对象，因为 §8.3 的在产实现已经是 error 对象）。
- **假象**：`<unsupported_constraints>` 的**默认值仍在待裁状态**（规格写默认 `error`，实现是 `drop_fields`，见文档状态第 4 条），所以 `empty_result` 路径在默认配置下**根本不会被走到**；只跑默认配置的验收对此全盲，且会把「没跑到」读成「通过」。
- **来源**：本条超出本次任务点名的十项，是按 §3.4 反向走查补的——它与 AC-10 共享同一个 `content` 字段，两者的失效互为镜像。
- **结论**：未验证（实现未就绪）。

---

### 2.3 块的位置、索引与消息级影响

---

**AC-14 — 两块相邻、各占独立 block index、不与相邻文本块合并**

- **陈述**：块对在同一条 assistant message 内相邻；两个块各有自己的 index；相邻的答案文本块是第三个独立块。
- **规格来源**：§5.3「两者**必须**在同一条 assistant message 内、相邻」「这一对块与相邻的答案文本块**不得**合并，各占独立 block index」。
- **观测**：O1 收集所有 `content_block_start.index` 与 `content_block_stop.index`；O2 读 `content[]` 长度与顺序。
- **通过侧**：index 多重集合等于 `{0,1,2}`，严格递增、无重复、无缺号；每个 index 恰好一次 start、一次 stop，不交错；块对两个 index 相差 1。
- **失败侧**：**（a）**两块共用一个 index（客户端会认为第二个 start 覆盖第一个）；**（b）**index 有缺号（按下标装配的客户端会留洞或抛错）；**（c）**块对插在文本块之后而 index 却在文本块之前（顺序与编号打架，见 AC-19）；**（d）**call 的 input 被并进文本块。
- **假象**：**（a）**只断言「有三个块」对重号完全无感——必须断言 index 的**多重集合**。**（b）**非流式路径没有 index 字段（用数组下标），所以**重号只在流式可见**；拿非流式的绿当流式的证据是标准假绿。**（c）**`BlockBuffer` 的 `until-tool-use` 策略按 `block.kind == "tool_use"` 放行（`blocks.py:104`）；实现若给 call 块取 kind `"tool_use"`（为复用 `_delta_for` 的 `input_json_delta` 分支），该配置下的**交付时机**会被搜索块提前触发。规格无条款，见 SPEC-GAP-4 的第二半。
- **结论**：未验证（实现未就绪）。

---

**AC-15 — `stop_reason` 不因搜索块变成 `tool_use`**

- **陈述**：响应里只有搜索块对与文本块时，`stop_reason` 不是 `tool_use`；客户端不会去等一个它要执行的工具。
- **规格来源**：§5.3「搜索块**不得**设置 `stop_reason` 为 `tool_use`。它不是客户端要执行的工具调用，客户端无事可做。`stop_reason` 仍由是否存在真正的 `function_call` 决定」。
- **观测**：流式取 O1 的 `message_delta.delta.stop_reason`，非流式取 body 的 `stop_reason`。**三个样本**：只有搜索、搜索 + 真 function_call、只有文本。
- **通过侧**：分别为 `end_turn`、`tool_use`、`end_turn`。
- **失败侧**：第一个样本给出 `tool_use`——客户端会停下来等一个它拿不到定义的工具，最好的结局是回一个空 tool_result 触发新一轮，最坏是挂住。
- **假象**：**（a）**`anthropic_messages.py:267` 的 `terminal.stop_reason or "end_turn"` 是**兜底合成**——上游没给 stop_reason 时它也会产出 `end_turn`。于是「实现正确地没设 tool_use」与「实现根本没处理 stop_reason、靠兜底捡到了 end_turn」**在只有搜索的样本上同形**。分辨力来自第二个样本（搜索 + function_call 必须仍是 `tool_use`）——**这两个样本必须成对存在，缺一条就没有分辨力**。**（b）**在产的 §8.3 合成路径已硬写 `"stop_reason": "end_turn"`（`anthropic_messages_synthetic_reply.py:104`），验收若误用那条路径的样本，它恒绿。
- **结论**：未验证（实现未就绪）。

---

**AC-16 — citation 用过之后不再附到文本块上**

- **陈述**：被用于填充 `content` 的 `url_citation`，**不得**再以 Anthropic `citations` ／ `web_search_result_location` 的形式出现在后随文本块上。
- **规格来源**：§5.3「……**不得**再重复以 Anthropic `citations` / `web_search_result_location` 形式附加到文本块上——那需要伪造 `encrypted_index`」；§14 D5 同。
- **观测**：O1 全字节否定检查：`citations`、`web_search_result_location`、`encrypted_index`、`cited_text` 四个字符串零命中；O2 上文本块的键集恰好 `{type, text}`。
- **通过侧**：四项零命中。
- **失败侧**：出现任一项。伪造 `encrypted_index` 是把一个不存在的服务端引用当真的送给客户端——与 AC-12 同类。
- **假象**：**（a）**否定检查若跑在「无 citation」的样本上（现有 cassette 就是），文本块本来就不会有 citations，**恒绿**；本条必须跑在**有 citation** 的样本上，也就是 AC-06 那个。**（b）**`citations` 也可能被塞进 `web_search_tool_result` 而不是文本块——否定检查要覆盖整个响应字节。
- **结论**：未验证（实现未就绪）。

---

**AC-17 — 每对块记一条 DEGRADE fact，编码与携带字段齐全**

- **陈述**：每产生一对块，就有一条 `DEGRADE` 性质的 `ConversionFact`，编码 `server_tool_partially_representable`，携带 `output_index`、`status`、结果条数、以及 `encrypted_content` 缺失这一事实；**不得**记为已保真。
- **规格来源**：§5.3 倒数第四条；§7.3「结构化 `ConversionFact` **必须**进入 History、metrics 与 trace」。分支专属编码另见 AC-08（`web_search_results_unattributable`）、AC-09（`web_search_results_not_representable`）、AC-02（`server_tool_call_id_not_carried`）。
- **观测**：O3 查 History 中本次 operation 的 fact 行，断言编码集合与每条的字段；**不查日志文本**。
- **通过侧**：N 对块 → N 条 `server_tool_partially_representable`，每条四个字段齐全（error 分支的结果条数为 0），严重度是 DEGRADE 而非 INFO ／ FAITHFUL。
- **失败侧**：**（a）**整个响应只记一条（per-pair 被读成 per-response）；**（b）**字段缺一个——最可能缺的是「`encrypted_content` 缺失」，因为它是恒真布尔，写起来像废话；**（c）**记成保真；**（d）**只进日志不进 History。
- **假象**：**这是本矩阵里「缺席不可读」最严重的地方。** fact 若采用「有值才写」的序列化，「没记录 status」与「status 恰好是默认值」**在库里逐字符相同**；断言必须钉**键存在性**而不只是值。另外 `结果条数 = 0` 与「该字段没写」在反序列化后都可能读成 0。
- **结论**：未验证（实现未就绪）。

---

**AC-18 — `tool_usage.web_search.num_requests` 进 facts，不进 wire content**

- **陈述**：上游响应体的 `tool_usage.web_search.num_requests` 出现在日志与 footer 里；**不出现在** Anthropic content 块的任何字段中。
- **规格来源**：§5.3 末条「**必须**进入可观测 facts（日志与 footer），**不得**进入 Anthropic wire content。是否同时写入 Anthropic `usage.server_tool_use.web_search_requests` 见待裁决 D7」。
- **观测**：O3 断言 footer ／日志含该计数；O1 断言 `content[]` 内不含该数值来源的字段。
- **通过侧**：facts 有，content 无。
- **失败侧**：塞进 `server_tool_use.input` 或 result 块的额外键。
- **未决**：`usage.server_tool_use.web_search_requests`（**wire usage，不是 content**）是 D7，用户未裁决。**本条不对该字段给判据**——出现或不出现都不判为缺陷，只要求实现方把选择记回规格。
- **假象**：`num_requests` 常为 1，与「硬写 1」「数了块对个数」三者同形；夹具须让上游回报 `num_requests: 3` 而响应里只有 1 个 `web_search_call`（该计数与 item 数之间没有契约关系）。
- **结论**：未验证（实现未就绪）。

---

### 2.4 成块时点与顺序（§6.3）

---

**AC-19 — wire 上先出块对、再出那个文本块**

- **陈述**：在客户端收到的字节序里，块对的两个 `content_block_start` 都早于后随文本块的 `content_block_start`。
- **规格来源**：§6.3「发射顺序**必须**是：该文本块对应的每个待归因 call 的 `server_tool_use` 与 `web_search_tool_result` 块，**然后**才是该文本块本身。**不得**反转」。
- **观测**：O1 记录每个 `content_block_start` 的**字节偏移**，比较先后。非流式比较 `content[]` 下标。
- **通过侧**：偏移严格递增，顺序为 call、result、text。
- **失败侧**：文本块先出——客户端会先看到答案再看到「我搜了什么」，且若客户端按到达顺序装配，历史里的顺序与语义相反。
- **假象**：**（a）「index 顺序对」不等于「字节顺序对」**——一个先发 index 2 的文本块、再发 index 0/1 的块对的实现，在只看 index 的断言下全绿，而客户端是按到达顺序渲染的。断言必须钉字节偏移或事件序号。**（b）**非流式天然是数组，顺序恒对；拿非流式的绿去证流式是本条最常见的假绿来源。
- **结论**：未验证（实现未就绪）。

---

**AC-20 — 在文本块完成之前，一个字节都不发**

- **陈述**：`output_item.added`（web_search_call）与该 item 的 `output_item.done` 到达时，客户端侧没有任何新字节；第一批字节要到后随文本块的 `content_part.done` 才出现。
- **规格来源**：§6.3「`added` 到达时**必须**登记该 `output_index`……**不得**产生任何 `CompletedBlock`，**不得**向下游发出任何字节」；「`output_item.done` ……**必须**把它记入一个**待归因队列**，但**不得**成块，**不得**向下游发出任何字节」。
- **观测**：受控上游**逐帧投喂并在每帧后暂停**，观测客户端 socket 已收字节数是否变化（keepalive 注释帧 `: ping` 不计）。
- **通过侧**：投喂到 `content_part.done` 之前，累计字节为空（`blocks.py` 的不变量：第一个完整块之前没有 `message_start`）。
- **失败侧**：`added` 或 `done` 上就发出了 `content_block_start`——那个块的 `content` 此刻**必然是错的**（citations 还没到），且已经不可撤回。
- **假象**：**（a）**若观测用的是「整流跑完后看字节序」，本条与 AC-19 塌缩成同一条，且分不出「早发了但内容恰好也对」；必须逐帧暂停。**（b）**块级交付本身会推迟很多东西，于是「没早发」可能是缓冲策略的副作用而非本条的实现——把 `client_delivery.buffering_policy` 设为最激进的逐块交付再验一次，才排除这个混淆。
- **结论**：未验证（实现未就绪）。

---

**AC-21 — 三个专有事件不产块、不进 content、不落未知事件分支**

- **陈述**：`response.web_search_call.in_progress` / `.searching` / `.completed` 到达时，不开块、不提交块、不关块，不产生任何 Anthropic content，也不触发 `UnsupportedResponsesEvent`。
- **规格来源**：§6.2 全节（识别为已知非语义 control metadata、`item_id` 不得用于校验、不得触发任何 block 的开启／提交／关闭）。
- **观测**：投喂含这三个事件的流；O1 断言字节无变化；O3 断言 provenance 记录了 event type 且**没有** unsupported-event 告警。
- **通过侧**：字节零变化 + 有 provenance 记录 + 无告警。
- **失败侧**：**（a）**落进 unsupported 默认分支（规格明说「今天它们会落进去」，所以这是**当前实际状态**，本条是一条真会红的判据）；**（b）**`.completed` 被当成成块信号——这是最直觉的错误实现，且它在「call 后面没有文本块」的样本上**恰好产出正确结果**，见 AC-24。
- **假象**：三个事件都带 `item_id`，而 §6.1 禁止用它做校验；一个用 `item_id` 去定位 item 的实现在这三个事件上**会静默找不到**（五个事件五个不同 id），然后按「找不到就忽略」处理——**表现与正确实现完全一样**。分辨力只来自 §6.1 的 id 不稳定夹具，配一个把 `output_index` 与 `item_id` 指向不同 item 的构造流。
- **结论**：未验证（实现未就绪）。

---

**AC-22 — 关联键是 `output_index`，五个不同 id 不破坏配对**

- **陈述**：同一个 `web_search_call` 在五个事件上带五个互不相同的 416 字符 id 时，仍然产出**恰好一对**块，配对正确。
- **规格来源**：§6.1 全节，含那张五事件五 id 的实测表；「**不得**用 `id`、`item_id` 或其任何派生值作为关联键、去重键或幂等键」；「`BlockIdentity.item_id` 对 `web_search_call` **只作诊断字段**，取值**必须**取自 `output_item.done` 上的权威快照」。
- **观测**：夹具直接复用 §6.1 表里的五 id 形态。O2 断言块对数为 1。
- **通过侧**：一对；`item_id` 若出现在诊断字段里，取值等于 `output_item.done` 那一个。
- **失败侧**：**（a）**产出五对（每个 id 当成新 item）；**（b）**产出零对（去重键用 id，后到的被当重复丢弃）；**（c）**诊断字段取了 `added` 上那个而非 `done` 上那个。
- **假象**：本项目 `routes/anthropic.py:228` 对 Copilot 上游把 `require_stable_item_id` 设为 `False`；夹具若走 generic 上游路径（strict），流会在别处先失败，**本条根本没跑到**，而失败信息看起来像「上游格式问题」。夹具必须显式走 Copilot 分流。
- **结论**：未验证（实现未就绪）。

---

**AC-23 — `done` 无 `added` 时补登记，不失败不丢弃**

- **陈述**：一个 `web_search_call` 只出现 `output_item.done` 而从未 `output_item.added` 时，仍然产出块对，整轮不失败。
- **规格来源**：§6.3「**`done` 到达而该 `output_index` 从未 `added` 时，必须补登记并照常入队，不得失败也不得丢弃。**」，并记明现有 parser 会以 `unknown_output_item` 显式失败。
- **观测**：构造流删去 `added` 帧。O1 断言 200 + 完整块对。
- **通过侧**：块对照出；**且 index 编号与保留 `added` 的版本一致**。
- **失败侧**：整轮 400 ／ 500；或该 item 静默消失且无 fact（参考项目记录在案的回归形态）。
- **假象**：**这是一个防御性分支，P7 标注「是否真的存在该形态」未探针**，所以它永远不会被真实流量触发——实现一旦漏掉，**任何真实样本都发现不了**。它只能靠构造样本验，而构造样本在「实现方也写了同一个构造样本」时是同源的。通过侧那句 index 一致的要求就是为此加的：否则补登记改变了 index 分配次序，违反 §6.3「冻结 block index 的分配次序」，而块对本身照样产出。
- **结论**：未验证（实现未就绪）。

---

**AC-24 — 兜底：call 后面没有文本块时，在自然边界以 error 形态成块**

- **陈述**：一个 call 之后响应就结束（或下一个 item 是 `function_call` 等非文本 item）时，待归因队列里的全部 call 仍产出块对，`content` 为 error 形态，不丢失。
- **规格来源**：§6.3「**兜底：一个 call 后面没有文本块时**……**必须**在其自然边界（`response.completed`，或该非文本 item 开始时）以 error 形态成块发出，**不得**丢失」。
- **观测**：两个样本——(i) `call → response.completed`；(ii) `call → function_call item → …`。
- **通过侧**：两个样本都得到块对；样本 (ii) 的块对**早于** function_call 对应的块出现在 wire 上。
- **失败侧**：**（a）**块对丢失（客户端完全不知道搜索发生过）；**（b）**样本 (ii) 里块对排到 function_call 之后（顺序反转，与 AC-19 同类）；**（c）**流挂住等一个永远不来的文本块。
- **假象**：一个把 `.completed` 专有事件当成块信号的错误实现（AC-21 失败侧 b）**在样本 (i) 上产出完全正确的结果**——它恰好在同一个位置成块。所以 AC-24 单独通过说明不了 AC-21，反之亦然；**两条必须同时成立才有意义**。
- **结论**：未验证（实现未就绪）。

---

**AC-25 — 队列在每次成块后清空（并且这是 SPEC-GAP-1 的判别样本）**

- **陈述**：`call#1 → text#1 → call#2 → text#2` 的响应里，第一对块拿 text#1 的 citations，第二对拿 text#2 的，互不串味；两对都不落 error。
- **规格来源**：§6.3「队列在每次成块后**必须**清空」；「**归因是局部规则**……**不得**依赖 `response.completed` 才知道的全局 call 总数——那会让流式与非流式再次分叉」。
- **观测**：上述四段样本，text#1 与 text#2 的 citations 取**不相交的 url 集合**。O2 断言两对块的 content 各自等于对应集合。
- **通过侧**：两对，各拿各的。
- **失败侧**：**（a）**第二对里出现 text#1 的 url（队列没清）；**（b）**两对都落 error；**（c）**第二对的 content 是两个集合的并集。
- **假象**：**失败侧 (b) 恰好是 §5.3 表格字面读法（全局计数）的正确行为。** 所以本条**不能单方面把 (b) 判成实现缺陷**——它先是一个规格冲突。我在本条采用的读法（§6.3 优先）是**推荐**，须经规格修订确认后才成为判据。
- **结论**：未验证（且判据本身待规格收敛，见 SPEC-GAP-1）。

---

**AC-26 — 流式与非流式对同一语义样本产出等价结果**

- **陈述**：同一份上游语义内容，以 SSE 与非流式两种形式喂进来，客户端重建出的 `content[]` 等价（除 message id 等无关字段）。
- **规格来源**：§6.3 末条「非流式路径与流式路径**必须**对同一语义样本产出等价结果」；§6.3 选这个成块边界的理由正是「流式与非流式**必然等价**」。
- **观测**：O2 两条路径各得一个 `content[]`，规范化后比较（排除 `id`、时间戳）。
- **通过侧**：完全相同，含块顺序、index 顺序、content 分支、去重结果。
- **失败侧**：任一处不同。最可能的分叉点：非流式实现能看到全局 call 总数，于是走了 §5.3 的全局计数分支；流式看不到，走局部分支——**规格已经点名警告过这个分叉**。
- **假象**：**（a）**若两条路径共用同一份转换代码，本条恒绿而毫无信息量——它测的是「同一个函数调用两次相等」。分辨力要求：比较必须发生在**两个真实 HTTP 入口**之上，且非流式样本是**独立构造的 JSON body**，不是把 SSE 拼起来生成的。**（b）**单 call 样本上全局与局部计数同值，本条恒绿；必须用 AC-25 的四段样本。
- **结论**：未验证（实现未就绪）。

---

### 2.5 客户端腿约束与回路

---

**AC-27 — Anthropic Messages 客户端拿到块对（AC-28 的正控）**

- **陈述**：inbound 为 `/v1/messages`、target 为 Responses 上游时，客户端收到的是 Anthropic 块对。
- **规格来源**：§1「本规格的所有规范性行为只在一条 crossing 上成立：inbound 是 Anthropic Messages，target 是 Responses 上游」；§5.3。
- **观测**：AC-01～AC-26 的全部样本本来就跑在这条腿上；单列以便与 AC-28 成对。
- **通过侧／失败侧**：同上。
- **假象**：无独立假象。**它存在的唯一理由是：没有它，AC-28 全绿也可能只是因为块对根本没实现。**
- **结论**：未验证（实现未就绪）。

---

**AC-28 — 直连 `/responses` 客户端不拿块对**

- **陈述**：inbound 为 `/responses` 的请求，无论其模型解析到哪条上游，客户端收到的都是 **Responses 协议**的字节；**永远不出现** Anthropic `server_tool_use` / `web_search_tool_result` 块，流不被撕断，也不出现「200 + Anthropic body」。
- **规格来源**：§1 末段（直连 `/responses` 自己声明的 `{"type":"web_search"}` 由该端点自己的上游契约决定，代理**不得**拦截、剥离或合成答复；用户 2026-08-30 裁决放行到上游）；§8.3 末条（合成**必须**只在客户端腿是 Anthropic Messages 时产出）；§9.0 末段（能力门判据**必须**包含 inbound 格式，**不得**只读 target format）。
- **观测**：**四个样本，缺一不可**——
  1. inbound `/responses` + 模型走 Responses 上游 + `stream: true`；
  2. 同上 + `stream: false`；
  3. inbound `/responses` + 模型只支持 `/v1/messages`（`claude-*`）→ 路由到 Anthropic 上游 + `stream: true`；
  4. 同 3 + `stream: false`。
  每个样本都带 `tools:[{"type":"web_search"}]`。O1 断言字节符合 Responses SSE ／ JSON 语法；**否定检查**：`server_tool_use`、`web_search_tool_result` 两个字符串在**响应**里零命中；断言无 `ValueError: no Responses item shape for block kind 'server_tool_use'`；断言日志 outcome 不是「ok 但交付了错协议」。
- **通过侧**：四个样本都是纯 Responses 字节（或该端点自己的 error envelope），否定检查零命中。
- **失败侧**：**（a）**样本 3 流式：200 已发出之后抛 `ValueError` 撕流（规格 §8.3 记录的实测复现之一）；**（b）**样本 3 ／ 4 非流式：返回 200、日志记 `ok`、把一份 Anthropic message body 交给 Responses 客户端，**全程没有任何一处说出这件事**（第二种实测复现）；**（c）**样本 1 ／ 2：能力门在直连请求上击发，声明被拦下而不是放行到上游。
- **假象**：**这是本矩阵里假象最密的一条。**
  - **（i）**样本 1 ／ 2 若碰巧走了一个能力门放行的模型，则「门只读 target」与「门读 inbound + target」**同形**——规格 §9.0 那段脚注记录的正是这么错的。分辨力**只**来自样本 3 ／ 4（模型不支持 `/responses`，于是 target 是 Anthropic 而 inbound 是 Responses），配一个门不放行的模型。
  - **（ii）**非流式的失败侧 (b) **完全不报错**：HTTP 200、日志 `ok`。任何以「响应码 + 无异常」为 oracle 的验收对它全盲。**判据必须是响应体的协议形状**，不是状态码。
  - **（iii）**`server_tool_use` 的否定检查会被请求里客户端自己的声明干扰；否定检查只查**响应**字节。
  - **（iv）**规格 §9.0 明确划界：inbound 格式判据**证明得了「哪条 crossing 归这道门管」，证明不了「这个声明是不是本项目写的」**。一个 Anthropic inbound 自带 Responses 形状 `{"type":"web_search"}` 的请求仍会被门判——**那种输入的处置不在本规格范围，本条不对它给判据，实现方也不得顺手改动**。
- **结论**：未验证（实现未就绪）。

---

**AC-29 — §8.4：上游返回未请求的 `web_search_call` 时降级而不失败**

- **陈述**：请求里没有 web search 声明而上游主动返回了 `web_search_call` item 时，客户端仍拿到 200 与降级后的内容，并有一条额外标注 `unsolicited` 的 DEGRADE fact。
- **规格来源**：§8.4 全节（覆盖 `spec.md:136` ／ `:181` 的显式失败），「覆盖范围严格限于 `web_search_call`。其余 server-tool item **继续** `server_tool_not_supported` 显式失败」。
- **观测**：两个样本——(i) 无声明 + 上游返 `web_search_call`；(ii) 无声明 + 上游返 `code_interpreter_call`（或任意其他 `*_call`）。
- **通过侧**：(i) 200 + 内容 + `unsolicited` 标注；(ii) 显式失败（`server_tool_not_supported`）。
- **失败侧**：(i) 整轮失败；或 (ii) 也被降级——那等于把 §8.4 的定点覆盖扩成全面放行，`spec.md` 的 no-revive 被无声掏空。
- **规格内部张力**：§8.4 说「**必须按 §5.3 降级成文本块**」，而 §5.3 现在规定的形态是**块对**不是文本块。这是 D6 改写 §5.3 之后 §8.4 措辞未同步。见 SPEC-GAP-3。**本条在「降级成什么」上不给结论。**
- **假象**：样本 (ii) 若选了一个上游根本不会返的 item 类型，测试写起来像跑了，实际只是在验一条永不触发的分支；**且它与「实现把 (ii) 也降级了但那条代码从未执行」同形**。
- **结论**：未验证（且部分待规格收敛，见 SPEC-GAP-3）。

---

**AC-30 — 块对回灌下一轮时被摊平，不 REJECT，且两腿同一份渲染**

- **陈述**：把本轮产出的块对原样放进下一轮请求的 `messages[]` 里：(i) 走 Responses 腿时被摊平成文本、请求成功；(ii) 同一份历史走 Anthropic 直连腿时由 `builtin:server-tool-capability` 摊平；(iii) **两条腿摊出来的文本逐字相同**。
- **规格来源**：§5.4 全节；§10「**必须**把『rejected ／ degraded server-tool block → 文本』的渲染提取为**一份共享实现**」。
- **观测**：三段脚本。(i)(ii) 断言 200，且上游收到的请求体里没有 server-tool 块；(iii) 抓两腿实际发往上游的请求体，逐字比较那段文本。
- **通过侧**：两腿都 200，两段文本逐字相同。
- **失败侧**：**（a）**Responses 腿 `REJECT`（`protocols/anthropic_responses.py:409` 的现状）；**（b）**两腿文本形状不同——规格明说「这种漂移**不会有任何东西报错**」；**（c）**error 分支的块被摊成 `[web_search results omitted]`（说明 content 被包成了数组，AC-10 的下游显形）。
- **为什么这条是 AC-10 与 AC-12 的必要配套**：`encrypted_content` 省略使块对在 Anthropic 上游是 schema-invalid 的（官方文档：missing 即 400）。规格接受这一点，理由**恰恰是**「这些块永不回喂 Anthropic 上游」——那个前提由本条守住。本条一旦不成立，AC-12 的论证基础就没了，失效形态是客户端下一轮吃 400。
- **假象**：**（a）**回灌样本若只用 error 分支的块，就测不到 `web_search_result` 列表项的摊平；两个分支都要回灌。**（b）**「两腿文本相同」若靠两边各自断言一个硬编码字符串，那是两份转写，**改一边不会红**；断言必须是两腿**运行时输出的互相比较**。**（c）**摊平在共享实现里 vs 各自复制一份，**当下**产出相同文本——本条查不出复制，那属 `as-reviewer` 的面，本矩阵记为「不可由行为判定」。
- **结论**：未验证（实现未就绪）。

---

## 3. P12 探针答案：`unavailable` 在合法枚举内

**结论：是。`unavailable` 是 Anthropic `web_search_tool_result_error.error_code` 的合法取值，语义为「An internal error occurred」。**

**完整枚举（六个）**：

| 取值 | 官方文档给的语义 |
|---|---|
| `too_many_requests` | Rate limit exceeded |
| `invalid_tool_input` | Invalid search query parameter |
| `max_uses_exceeded` | Maximum web search tool uses exceeded |
| `query_too_long` | Query exceeds maximum length |
| `request_too_large` | The search request is too large, typically because of a long domain filter list |
| **`unavailable`** | **An internal error occurred** |

**三个独立来源，同向**：

1. **Anthropic 官方文档**，`https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool`，Errors 一节，2026-08-30 取。逐字列出上表六项。
2. **`anthropic` Python SDK 1.0.0**（本项目 venv 内已装）：`/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/anthropic/types/web_search_tool_result_error_code.py:7-9` —— `Literal["invalid_tool_input", "unavailable", "max_uses_exceeded", "too_many_requests", "query_too_long", "request_too_large"]`。beta 变体 `beta_web_search_tool_result_error_code.py` 逐字相同。
3. **`@anthropic-ai/sdk` 0.116.0（TypeScript）**：`/home/xp/src/copilot-api-js/node_modules/@anthropic-ai/sdk/resources/messages/messages.d.ts` —— `export type WebSearchToolResultErrorCode = 'invalid_tool_input' | 'unavailable' | 'max_uses_exceeded' | 'too_many_requests' | 'query_too_long' | 'request_too_large';`

**证据等级：强，足以据此实现，无需再探。** 判据：三个来源相互独立（官方文档由 Anthropic 撰写；两个 SDK 虽同由 Stainless 从 OpenAPI spec 生成，但语言不同、版本不同、来源仓库不同），且**逐字一致**。

**版本漂移已核，这决定了「强」的边界**：uv 缓存里的 `anthropic` 0.59.0 只有**五个**取值——`request_too_large` 尚未加入（`/home/xp/.cache/uv/archive-v0/hdgufGemgzHlqk-oZMV9I/lib/python3.13/site-packages/anthropic/types/web_search_tool_result_error.py:11`）。**`unavailable` 在 0.59.0、0.77.0、1.0.0 三个版本里都在**，所以它的稳定性比枚举整体更强。该枚举是**开放的（会增项）**，因此「某取值不在枚举内」这类否定判断必须按版本限定；「`unavailable` 在枚举内」这个肯定判断不需要。

**顺带取回的两条一手事实，直接支撑本矩阵，权重同上**：

- **error 是裸对象**：官方文档逐字「On an error, `content` is a single error object rather than a list of result blocks.」；SDK 侧 `WebSearchToolResultBlockContent = Union[WebSearchToolResultError, List[WebSearchResultBlock]]`。→ §5.3 的裸对象要求得到**规格之外的独立确认**，AC-10 的依据从「在产实现的摊平细节」升级为「协议本身如此」。
- **空列表另有语义**：官方文档「A search that succeeds but matches no results returns an empty `content` list, not an error.」→ §5.3 选 error 而非 `content: []` 的论证（「说返回了零条结果是与事实相反的断言」）**与协议语义方向一致**，不是本项目自造的区分。同时它确认了 §3.4 `empty_result` 取值在协议里读作「搜过了、零结果」——那正是 §3.4 那段 ⚠️ 提醒的代价，与 AC-13 呼应。

---

## 4. 我认为最容易被假象骗过的一条

**AC-06（单 call + citation → 结果列表）。** 理由不是它最难实现，而是它的**三重同形**：

1. **数据源同形。** 上游同一份响应里，引用**同时**以内联 markdown 与结构化 `annotations` 两种形式到达（§12 P10 记录了 B7 样本的实证，并明说「这只证明可以共存，不证明必然」）。因此一个从模型正文正则抓链接的实现，与一个正确读 annotations 的实现，**在真实样本上产出相同的 url 列表**。「content 填了」不等于「来源对了」——这正是本次任务点名的那个假象，而它恰恰在最像真的样本上最不可见。
2. **夹具同形。** 本项目现有两份 web-search cassette 的 `annotations` **都是空数组**（§12 与 §6.3 的 2026-08-21 证据更正各说了一次）。所以**用现成 cassette 跑 AC-06，它永远走的是 AC-09 那条 error 分支**——测试会绿，因为它测的是另一条判据。这是「未验证被写成通过」的标准形态。
3. **判据同形。** `title` 若与域名相近、citation 若只有一条、url 若不带 query string，则「逐字取 annotation」与「派生／规范化」产出相同字符串。而一手样本的 `?utm_source=openai` 尾巴是**唯一**能把「逐字」与「清洗」分开的特征——一个「顺手把追踪参数去掉」的实现看起来更体面，且**没有任何断言会红**。

要让这条有分辨力，夹具必须**同时**满足：annotations 非空且 ≥ 4 条含一组重复 url、每个 url 带真实的 `?utm_source=openai` 尾巴、title 与 url 无字面派生关系、**且正文里的内联 markdown 链接与 annotations 故意不一致**。前三项是构造成本，第四项是构造样本（真实上游不会产出不一致的两份），必须标明它没有上游实测背书。

**第二名是 AC-28 的样本 3 ／ 4 非流式分支**：HTTP 200、日志 `ok`、body 是错协议，全程无异常。任何以状态码或异常为 oracle 的验收对它 100% 全盲，而它已经在 2026-08-30 实测复现过一次。

---

## 5. 规格缺陷（不是实现缺陷；按 `as-verifier` 的约定原样记录，不代为择一）

**SPEC-GAP-1 — §5.3 的 content 分支按「本次响应」计数，§6.3 按「待归因队列」计数，两者在同一输入上给出相反结果。**
判别输入：`call#1 → text#1 → call#2 → text#2`。§5.3 表第二行「本次响应中 `web_search_call` **多于一个**」→ 两对都落 error；§6.3「队列中**恰好一个**……**不得**依赖 `response.completed` 才知道的全局 call 总数」→ 两对各自拿到自己的 citations。
**我的推荐读法（是推荐，不是判据）**：§6.3 优先。理由在 §6.3 自己的文字里——全局计数会让流式与非流式分叉，且 §6.3 是 D6 之后专门重写的成块规则，§5.3 的表格早于它。**但这需要一次规格修订，把 §5.3 表格改成队列口径**；在此之前 AC-25 不成立。
影响：AC-08、AC-25、AC-26。
（规格文档状态第 24 行已登记相邻问题 MJ-7「§5.3 三分支条件不互斥，须改为有序判定」，但**没有登记这条计数口径冲突**。）

**SPEC-GAP-2 — §5.3 三分支条件不互斥；规格自己已登记为 MJ-7 并标为「实现前必须关闭」，至今未关。**
判别输入：一个 `status: "incomplete"` 的 call，队列里只有它，随后文本块**带** citations。第一行（恰好一个 + 有 citation）与第三行（`status != completed`）同时命中，结果相反。
影响：AC-09 的样本 (ii) 无法判定。

**SPEC-GAP-3 — §8.4 的措辞未随 D6 同步。**
§8.4 写「**必须**按 §5.3 降级成**文本块**」，而 D6 之后 §5.3 规定的形态是**块对**。两处只能有一个是当前意图。
影响：AC-29 的「降级成什么」无结论。

**SPEC-GAP-4 — 块对的 SSE 帧形状未规定，而两种形状对客户端解析器不等价。**
Anthropic 官方 streaming 示例里，`server_tool_use` 的 `input` 走 `input_json_delta`（`content_block_start` 只带 `{"type","id","name"}`），`web_search_tool_result` 的 content 则整个在 `content_block_start` 里。本项目 `anthropic_messages.py:54 _delta_for()` 对这两个 kind 都返回 `None`，`block_frames()` 也不清空它们的 start payload——所以两个块都会**整包随 `content_block_start` 发出，且没有任何 delta**。规格 §5.3 只冻结了块的**内容**，没说帧形状。
两个后果：**(a)** 一个照官方语义写的客户端解析器可能读不到 `input.query`；**(b)** 若实现为了拿到 `input_json_delta` 而把 `CompletedBlock.kind` 取成 `"tool_use"`，`blocks.py:104` 的 `until-tool-use` 缓冲策略会被搜索块**提前触发**，改变该配置下的交付时机——规格对此无条款。
建议：在 §5.3 增一条帧形状条款，并先确认目标客户端的解析路径。
影响：AC-03a、AC-14。

**SPEC-GAP-5 — `input` 省略缺少 `encrypted_content` 那样的论证。**
§5.3 为 `encrypted_content` 的省略写了整段（「这一条使合成块不满足 Anthropic 对该项的完整 schema；这是**有意的**」），但对「都没有则省略 input」**没有写**同样的话，而 `ServerToolUseBlockParam.input` 同样是 `Required`。两处是同一类刻意偏离，只有一处被记录。
影响：AC-03b。

**SPEC-GAP-6 — `queries` 连接路径上的 strip 时机未指明。**
§5.3 说 query「**必须**已 strip 首尾空白」，但对 `queries` 连接后的结果，是「每项各自 strip 再连接」还是「连接后整体 strip」未定。输入 `["a ", " b"]` 下两者给出 `"a, b"` 与 `"a ,  b"`。
影响：AC-04。

**SPEC-GAP-7 — 派生 id 的唯一性范围未声明；规格自己已登记为 MJ-8 并标为「实现前必须关闭」，至今未关。**
`srvtoolu_ws_<output_index>` 在**一轮之内**唯一，跨轮次必然重复：连续两轮各在 `output_index: 0` 搜一次，历史里就有两个 `srvtoolu_ws_0`。规格没说这是否可接受。
影响：AC-02、AC-30（回灌时同 id 的两个块能否被正确摊平）。

**开着的用户裁决，本矩阵不代判**：D2（`max_uses`）、D3（未请求的 call）、D5（已被 D6 推翻但 P10 未结）、D7（`usage.server_tool_use.web_search_requests` 是否写 wire usage）、以及 §3.4 `<unsupported_constraints>` 的**默认值**（规格写 `error`，实现是 `drop_fields`；文档状态第 4 条自己判定这是「实现单方面偏离了用户已下的裁决」且「至今没有回到用户手上重裁」）。

---

## 6. 我显式排除掉的可能性

考虑过、判定不属本矩阵，列出以便日后不必重走：

1. **§3 declaration 映射的全部判据**（`{"type":"web_search"}` 的键集、`user_location` 五键透传、`allowed_domains` 三取值、多重声明去重、`tool_choice` 映射）。理由：本次被验对象是**响应侧块对**，请求侧是独立的一面。**不是判它们不重要**——它们需要自己的矩阵。
2. **§9.3 能力门的正则清单判据**（`gpt-[5-9]\.\d+.*` 的松紧、`.` 通配导致 `gpt-5.5` 认领 `gpt-5x5`、per-provider 不合并）。同上，属请求侧／路由面。唯一保留的是 AC-28 里与 inbound 格式相关的那一半，因为它直接决定客户端拿到什么字节。
3. **`page_age` 字段**。Anthropic schema 有（optional），规格 §5.3 的结果项键集只有三个。**没有**为它单列判据，而是折进 AC-12 的「键集恰好三个」——规格没授权它，凭空产出它就是编造（上游 annotation 里也没有这个信息）。
4. **`caller` 字段与 dynamic filtering**（`web_search_20260209` / `20260318` 引入的 `allowed_callers`、`response_inclusion`，以及嵌套 pair 上的 `caller`）。§3.1 的识别判据是前缀 `web_search_`，所以新版本声明**会**被认领，但规格全文建立在 `20250305` 的字段集上，新版本的新字段会落进 §3.5「允许集之外 → `REJECT`」。这是**前瞻风险而非当前缺陷**，记在这里而不做成判据——允许集是显式冻结的，改它需要裁决。
5. **`pause_turn` stop reason**。Anthropic 原生 server-tool 编排的产物，本腿上游是 Responses，产不出它。排除。
6. **`web_fetch` 与混合声明**。§8.3 末条已裁决走 `REJECT` 且已落地；它不产块对，不在本矩阵。
7. **`/v1/messages/count_tokens` 腿**。§10 已记为独立已知缺口，§13 明确不在范围。
8. **代码结构判据**（渲染实现是否真的共享、`_family` 等函数是否提取）。AC-30 的备注已说明：行为观测查不出「复制了一份」，那属 `as-reviewer` 的面。**没有**把它伪装成一条行为判据。
9. **性能／缓冲区判据**（`buffer_cap_bytes` 在块对上的计量，`CompletedBlock.size_bytes` 用 `repr` 计长）。规格无条款，不自造。仅在 AC-14 的假象栏记了 `until-tool-use` 策略的耦合。

**没有排除但也没有判据的**：SPEC-GAP 七项，以及 §5 末尾那五个开着的用户裁决。它们是「未验证 + 写明为什么」，不是「通过」。

---

## 7. 矩阵收敛状态

| 终态 | 条数 | 说明 |
|---|---|---|
| 通过 | 0 | — |
| 偏差 | 0 | — |
| 已豁免 | 0 | — |
| 未验证 | 30 | 全部。被验对象未实现；本次任务明确禁止读取实现与现有测试 |

**AC-01 … AC-30 共 30 条，每条都有结论栏。**

**反向走查已执行**（`as-verifier` 要求的第二个动作：不看矩阵、只读规格，逐句问「这句产生了哪一行」）：§5.3 逐条 → AC-01～AC-18；§6.1 → AC-22；§6.2 → AC-21；§6.3 逐条 → AC-19、AC-20、AC-23、AC-24、AC-25、AC-26，以及 AC-09（status 非终态）、AC-03b（action 缺失）；§5.4 → AC-30；§1 末段 + §8.3 末条 + §9.0 末段 → AC-27、AC-28；§8.4 → AC-29；§3.4 → AC-13；§7.2 → AC-02。

反向走查中**新长出**的两行：**AC-13**（`empty_result` 的 `[]` 与 error 裸对象两种形态必须都产得出）与 **AC-30**（回灌摊平，从 AC-10 ／ AC-12 的论证前提反推出来）。这两条不在本次任务点名的十项里。

**非验收性陈述**（读规格时产生不出判据行的句子，逐类写明，这是它们的正确终态而不是遗漏）：§5.1 与 §5.2 是证据与论证；§7.1 是参考项目探针记录；§8.1 三种拒绝措辞是上游事实表；§9.1 ／ §9.2 是目录分析；§11 是覆盖清单；§12 是证据权重表；§14 是待裁清单。
