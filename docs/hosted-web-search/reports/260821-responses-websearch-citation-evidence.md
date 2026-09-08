# Copilot `/responses` hosted web search 是否给出可引用信息：取证报告

- 日期：2026-08-21
- 调查员：subagent（取证模式；只读取证，唯一的写操作是本报告）
- 目标问题：GitHub Copilot 的 OpenAI Responses 端点在执行 hosted web search 时，会不会在响应里给出搜索结果的可引用信息（URL、标题、摘要）？如果会，放在哪个字段、什么形状？

---

## 0. 结论

**A. 上游会给引用信息。**

形状是 Responses 标准的 `url_citation` annotation，挂在 **`message` item 的 `content[].annotations[]`** 上；**不在 `web_search_call` item 里**。非流式与流式两条路径**都**已被真实字节证实，流式下还额外有逐条推送的 `response.output_text.annotation.added` 事件。

**证据强度：足以据此实现。** 依据分两层，互相独立：

1. 本项目自己 2026-08-20 对 `https://api.githubcopilot.com/responses` 发出的真实调用，原始响应落盘在 `exp/260820-websearch-probe/raw/`（非流式，gpt-5.5）。
2. 既有 `copilot-api-js` 服务的历史库全量扫描：34 721 733 个对象、39.17 GB 解压后字节，命中 **1082** 个带 typed `url_citation` 的对象、**426** 个带非空 `annotations` 的对象，跨 **4 个数据库**、跨 2026-07-31 至 2026-08-11、跨多个模型（含 `gpt-5.6-sol`），且经 transform 图核对确认为**上游根帧**而非客户端改写副本（流式）。

任务描述里的猜想被证实：**两份 cassette 里的空 `annotations` 是那次查询（「现在几点／今天几号」）的特性，不是上游从不给引用。**

三条必须随结论一起带走的限定：

- **只有 `url` / `title` / `start_index` / `end_index`。没有摘要、没有 `encrypted_content`、没有 `page_age`。** Anthropic 原生 `web_search_tool_result` 的**完整** schema 造不出来。
- **`title` 可以是空字符串 `""`**（实测样本里 raw 文件类 URL 就是空标题）。
- **`annotations` 可以是空数组，即使 `num_requests >= 1`。** 降级分支不可省。

---

## 1. 非流式：本项目自己的真实探针（一手字节）

### 1.1 出处

- 文件：`/home/xp/src/ghc-api-proxy-py/exp/260820-websearch-probe/raw/B7-responses-tool-choice-builtin-response.txt`（mtime 2026-08-20 07:12）
- 发起者：`exp/260820-websearch-probe/probe.py`，`BASE_URL = "https://api.githubcopilot.com"`，token 取自 `~/.local/share/copilot-api/github_token`，文件头自述「it needs credentials and it makes real calls」。落盘只脱敏 `token`／`tracking_id`／`enterprise_list`／`organization_list`／`safety_identifier`。
- 场景定义在 `probe.py:182-183`。响应首行 `# HTTP 200 content-type: application/json`。

### 1.2 请求

```jsonc
{
  "model": "gpt-5.5",
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "What is the capital of France?"}]}],
  "max_output_tokens": 64,
  "stream": false,
  "tools": [{"type": "web_search"}],
  "tool_choice": {"type": "web_search"}     // 强制走搜索
}
```

### 1.3 响应（字段名与嵌套一字未改；超长 opaque id 已截断并标注）

```jsonc
{
  "model": "gpt-5.5-2026-04-23",
  "object": "response",
  "status": "completed",
  "output": [
    {
      "action": {"queries": ["capital of France"], "query": "capital of France", "type": "search"},
      "id": "raShE0EPZQC+gQjFFG5rtoHs7X0468oP1RW6BO0Cx3/6…(opaque，本报告截断)",
      "status": "completed",
      "type": "web_search_call"
    },
    {
      "content": [
        {
          "annotations": [
            {
              "end_index": 168,
              "start_index": 36,
              "title": "France – EU country | European Union",
              "type": "url_citation",
              "url": "https://european-union.europa.eu/principles-countries-history/eu-countries/france_en?utm_source=openai"
            }
          ],
          "logprobs": [],
          "text": "The capital of France is **Paris**. ([european-union.europa.eu](https://european-union.europa.eu/principles-countries-history/eu-countries/france_en?utm_source=openai))",
          "type": "output_text"
        }
      ],
      "id": "+0PzkZ2CMzb8SWq6kiWsPcRqx+Krwfi796GaOx433FE7…(opaque，本报告截断)",
      "phase": "final_answer",
      "role": "assistant",
      "status": "completed",
      "type": "message"
    }
  ],
  "tool_choice": {"type": "web_search_preview"},   // 上游把请求里的 {"type":"web_search"} 规范化成了这个
  "tool_usage": {"image_gen": { /* 全 0 */ }, "web_search": {"num_requests": 1}},
  "tools": [{
    "type": "web_search", "return_token_budget": "default", "search_content_types": ["text"],
    "search_context_size": "medium",
    "user_location": {"type": "approximate", "city": null, "country": "US", "region": null, "timezone": null}
  }]
}
```

### 1.4 从这份字节直接读出的事实

1. `web_search_call` item 的键**恰好四个**：`action` / `id` / `status` / `type`。没有 `sources`、没有 `results`、没有 `encrypted_content`。
2. `action` 的键：`queries`（数组）、`query`（单数，与数组首项重复）、`type: "search"`。
3. 引用在**后一个 `message` item** 的 `content[0].annotations[]`，类型 `url_citation`，字段恰好五个。
4. **同一响应里引用同时以两种形式到达**：结构化 `annotations` + 正文 `text` 内的内联 markdown 链接，指向同一 URL。`start_index=36` / `end_index=168` 正是那段内联 markdown 在 `text` 中的字符区间。
5. 搜索后端会给 URL 追加 `?utm_source=openai`（历史库样本同样如此）。

---

## 2. 流式：历史库里的真实上游根帧（一手字节）

这一节回答了原本被列为「未观测」的问题，也是本次调查最重要的增量。

### 2.1 样本出处与 provenance 核对

- 数据库：`~/.local/share/copilot-api/history-v3-260807.db`
- 操作：`req_1785485769182_1081`，**2026-07-31 08:16 UTC**
- 客户端侧 endpoint `anthropic-messages`（即 copilot-api-js 把 Anthropic Messages 请求翻成 Responses 发给 Copilot），`responseModel='gpt-5.6-sol'`，`stream=True`，`responseSuccess=True`
- **provenance 已核**：用 `/tmp/probe_origin.py` 展开该操作的 timeline，按 transform 图判定——该操作共 573 个事件、136 个 frame 是 transform 产物，而下文引用的 4 个 frame（`frame:191` / `frame:295` / `frame:296` / `frame:297`）**都不是任何 transform 的输出**，即 **UPSTREAM ROOT**。因此它们不是 copilot-api-js 的 `rewrite-out:responses-fix-stream-ids` 之类改写副本。

### 2.2 该响应的形态

一次响应里出现了 **13 个 `web_search_call` item**（`output_index` = 1,3,5,7,9,11,13,15,17,18,19,21,23），穿插 `reasoning` item，最后在 `output_index=24` 给出带 5 条引用的 message。

`output_index=24` 的上游帧序列（已滤掉 `output_text.delta`）：

| seq | 事件 | 关键内容 |
|---|---|---|
| 89 | `response.output_item.added` | `item.type=message`，`item.id` 为 412 字符 opaque |
| 90 | `response.content_part.added` | `part.type=output_text`，`annotations` **长度 0** |
| 91-103 | `response.output_text.delta` ×13 | — |
| **104** | **`response.output_text.annotation.added`** | `annotation_index=0`，`title=""`，`start=392`，`end=483` |
| 105-117 | `response.output_text.delta` ×13 | — |
| **118** | **`response.output_text.annotation.added`** | `annotation_index=1`，`start=871`，`end=965` |
| **127** | 同上 | `annotation_index=2` |
| **134** | 同上 | `annotation_index=3` |
| **148** | 同上 | `annotation_index=4` |
| 158 | `response.output_text.done` | — |
| 159 | `response.content_part.done` | `part.annotations` **长度 5**（完整数组） |
| 160 | `response.output_item.done` | `item.content[].annotations` **长度 5**（完整数组） |

### 2.3 `annotation.added` 帧原文（`frame:191`，一字未改）

```json
{"type":"response.output_text.annotation.added",
 "annotation":{"type":"url_citation","end_index":483,"start_index":392,"title":"",
               "url":"https://github.com/systemd/systemd/raw/refs/heads/main/src/login/loginctl.c"},
 "annotation_index":0,"content_index":0,
 "item_id":"msg_0f7304d0c68a6cd2016a6c59f2caf881a1a3adf43b4be4019c",
 "output_index":24,"sequence_number":104}
```

`content_part.done`（`frame:296`）的 `part` 节选，同样一字未改：

```json
{"annotations":[
  {"end_index":483,"start_index":392,"title":"","type":"url_citation","url":"https://github.com/systemd/systemd/raw/refs/heads/main/src/login/loginctl.c"},
  {"end_index":965,"start_index":871,"title":"","type":"url_citation","url":"https://github.com/systemd/systemd/raw/refs/heads/main/src/login/logind-dbus.c"},
  {"end_index":1310,"start_index":1216,"title":"","type":"url_citation","url":"https://github.com/systemd/systemd/raw/refs/heads/main/src/login/logind-user.c"},
  {"end_index":1646,"start_index":1552,"title":"","type":"url_citation","url":"https://github.com/systemd/systemd/raw/refs/heads/main/src/login/logind-user.c"},
  {"end_index":2064,"start_index":1970,"title":"","type":"url_citation","url":"https://github.com/systemd/systemd/raw/refs/heads/main/src/login/logind-dbus.c"}],
 "logprobs":[],
 "text":"Search completed. The most relevant GitHub source locations are:\n\n1. **`loginctl enable-linger` implementation** — `src/login/loginctl.c`  \n   `verb_enable_linger()` invokes the synchronous D-Bus method call:\n\n   ```c\n   r = bus_call_method(…"}
```

### 2.4 ⚠️ 实现层面的关键陷阱：`item_id` 不能用来关联

在这个操作里，**同一个 `output_index=24` 的每一个事件都携带一个不同的 412 字符 opaque `item_id`**（seq 89 / 90 / 91 / 92 … 各不相同）。这是本项目已知的 Copilot id 不稳定问题，在这里以最极端的形态出现：**逐事件全变**。

更进一步：**只有 `response.output_text.annotation.added` 这一族事件携带的是明文 `msg_…`（54 字符）id，与同一 item 的其它所有事件完全不同形**。这在 4 个数据库的样本里一致出现（`msg_0f7304d0…`、`msg_0ad56e6c…`、`msg_0dfed660…`、`msg_09bbfbc5…`）——看起来是 Copilot 在这条事件路径上漏加密了原始 OpenAI id。

**因此：跨事件关联只能用 `output_index`（配合 `content_index` / `annotation_index`），绝不能用 `item_id`。** 强度：强，四个独立数据库、四段不同会话一致复现；且这些帧经 transform 图核定为上游根帧。

### 2.5 三个载体的取舍建议

引用在流式下有三个载体，都携带完整信息：

| 载体 | 时机 | 完整度 |
|---|---|---|
| `response.output_text.annotation.added` | 与 delta 交错，边生成边推 | 逐条，需自行累积 |
| `response.content_part.done` 的 `part.annotations` | 该 part 收尾 | **完整数组** |
| `response.output_item.done` 的 `item.content[].annotations` | 该 item 收尾 | **完整数组** |

本项目是**块级交付**，成块时刻本就在 `content_part.done` / `output_item.done` 之后，因此**建议直接读终态数组、完全忽略 `annotation.added`**——顺带绕开 §2.4 的 id 陷阱。参考项目 `copilot-api-js` 在 Responses→Responses 透传里也是把 `annotation.added` 归入「item-summary 模式下要丢弃的中间子帧」（`src/lib/codec/openai-responses/buffered-merge-reducer.ts:20,27`），理由是官方 SDK accumulator 在 `annotation.added` 与 `content_part.added` 分家时会抛异常——**若我们向下游发 Responses SSE，这条同样适用**。

---

## 3. 反向样本：搜索执行了，但 annotations 是空的

同一批探针，同一天，同一模型：

| 探针 | 查询 | `tool_choice` | `num_requests` | 有 `web_search_call` item | `annotations` |
|---|---|---|---|---|---|
| B1 | What is the capital of France? | `"auto"` | **0** | 无 | `[]` |
| B3 | 同上（带 `user_location`） | `"auto"` | **0** | 无 | `[]` |
| B7 | 同上 | `{"type":"web_search"}` | **1** | 有 | **1 条 `url_citation`** |
| B8 | 同上（带 `include: ["web_search_call.action.sources"]`） | `"auto"` | **0** | 无 | `[]` |
| C1 | Search the web for today's date.（非流式） | `"auto"` | **1** | 有 | **`[]`** |
| C2 | 同 C1（流式） | `"auto"` | 1 | 有 | 全部 `[]`，且**无** `annotation.added` 事件 |

C1 的 `action`：

```json
{"queries": ["time: {\"utc_offset\":\"-04:00\"}"], "query": "time: {\"utc_offset\":\"-04:00\"}", "type": "search"}
```

——一个「查当前时间」的特殊查询，没有可引用网页，于是 `annotations` 为空。

**所以 `num_requests >= 1` 不蕴含 `annotations` 非空。** 这是必须实现的降级分支，不是理论边界。

---

## 4. 官方 Responses API 的标准形状（Copilot 有没有裁剪）

参照实现取自本机已安装的官方 SDK：`/home/xp/src/play-a2a/.venv/lib/python3.13/site-packages/openai/types/responses/response_output_text.py`（OpenAI 的 OpenAPI spec 经 Stainless 生成）。

`AnnotationURLCitation` 字段：

| 字段 | 类型 | 官方注释 |
|---|---|---|
| `type` | `Literal["url_citation"]` | 恒为 `url_citation` |
| `url` | `str` | 网络资源 URL |
| `title` | `str` | 网络资源标题 |
| `start_index` | `int` | 引用在 message 文本中的首字符下标 |
| `end_index` | `int` | 末字符下标 |

联合类型还含 `file_citation` / `container_file_citation` / `file_path`；挂载点是 `ResponseOutputText.annotations: List[Annotation]`。

**对照结论：Copilot 返回的 `url_citation` 与官方形状逐字段一致，未裁剪、未增补。** 官方本身也不在 `url_citation` 里给摘要（snippet），所以「没有摘要」是 Responses API 的设计，不是 Copilot 削的。

**唯一未验证项**：OpenAI 官方支持 `include: ["web_search_call.action.sources"]`，把来源列表塞进 `web_search_call.action.sources`。B8 探针确实发了这个 `include` 且**返回 200 未报错**（Copilot 至少接受该参数），但那次 `num_requests` 为 0、根本没搜，所以 **Copilot 会不会真的填 `action.sources` 仍然未知**。见 §7 P-B。

---

## 5. 历史库全量扫描

### 5.1 方法与安全性

- **只读**：全部连接用 `sqlite3.connect("file:<db>?mode=ro", uri=True)`，只发 `SELECT`。未写入、未 `VACUUM`、未 `ATTACH`、未触碰正在运行的 4141 服务。
- 对象体是 **zstd** 压缩（列名叫 `*_gz` 属误导），用 `zstandard.ZstdDecompressor` 解开后按字节匹配。
- 探针脚本：`/tmp/probe_ws.py`、`/tmp/probe_ws2.py`、`/tmp/probe_ws3.py`、`/tmp/probe_origin.py`、`/tmp/probe_dump_op.py`。

### 5.2 ⚠️ 我第一版探针是假阴性的，必须记下来

第一版的 needle 写成 `rb'"annotations"\s*:\s*\[\s*[^\s\]]'`（带真引号）。**history 的 frame 对象把 SSE payload 存成一个转义过的 JSON 字符串**，实际字节是 `\"annotations\":[…]`——闭合引号前多了反斜杠，于是这个正则**对全部 3400 万个 frame 对象一次都不匹配**。第一轮扫描据此报出「非空 annotations = 0」，如果直接写进报告，结论就会反过来。

抓住它的是**正样本对照**：拿已知含引用的 B7 与已知不含引用的 C1，各自按「原始 JSON」和「转义成 history frame 的样子」两种形态过一遍 needle。结果 `B7 escaped → False`，当场暴露。

修正后的 needle 用 `\\?"` 同时覆盖转义与非转义两种拼法，并重新验证判别力：

| 样本 | 形态 | `num_requests_nonzero` | `web_search_call_typed` | `url_citation_typed` | `annotations_nonempty` |
|---|---|---|---|---|---|
| B7（有引用） | raw | True | True | **True** | **True** |
| B7（有引用） | escaped | True | True | **True** | **True** |
| C1（搜了没引用） | raw | True | True | False | False |
| C1（搜了没引用） | escaped | True | True | False | False |

下面所有数字都出自修正后的探针。

### 5.3 语料规模与端点分布

| 数据库 | `anthropic-messages` | `openai-responses` | 其他 | 扫描对象数 | 解压字节 |
|---|---|---|---|---|---|
| `history-v3-260807.db` | 71773 | 13 | `openai-chat-completions` 2 | 16 480 278 | 20.18 GB |
| `history-v3-260809.db` | 39468 | 459 | — | 11 148 914 | 15.55 GB |
| `history-v3.db` | 24533 | 11 | — | 5 398 594 | 2.52 GB |
| `history-v3-260811.db` | 6082 | — | `unknown` 2 | 1 661 173 | 0.83 GB |
| `history-v3-20260815-183721.db` | 798 | — | — | 8 028 | 0.02 GB |
| `history-v3-20260816-160151.db` | 906 | — | — | 9 458 | 0.02 GB |
| `history-v3-20260817-050754.db` | 572 | — | — | 5 468 | 0.02 GB |
| `history-v3-20260818-044224.db` | 1164 | — | — | 9 820 | 0.03 GB |
| **合计** | | | | **34 721 733** | **39.17 GB** |

后四个库 `kind='frame'` 计数为 0——与既有认知一致：既有服务在 2026-08-15 之后不再存 frame。

### 5.4 命中（`frame` + `sequence-item` + `payload` + `payload-skeleton` 全部对象）

| 数据库 | `url_citation_typed` | `annotations_nonempty` | `num_requests_nonzero` | `web_search_call_typed` | 对照 `annotations` 键 |
|---|---|---|---|---|---|
| `history-v3-260807.db` | 633 | 237 | 88 | 487 | 45 635 |
| `history-v3-260809.db` | 375 | 159 | 49 | 367 | 71 996 |
| `history-v3.db` | 66 | 27 | 9 | 27 | 2 682 |
| `history-v3-260811.db` | 8 | 3 | 1 | 3 | 410 |
| 2026-08-15 之后四库 | 0 | 0 | 0 | 0 | 11 |
| **合计** | **1082** | **426** | **147** | **884** | **120 734** |

抽样核对了每个库的前 3 个 `url_citation_typed` 命中，**全部是真实上游 SSE 帧**，无一是散文：

- `history-v3-260809.db`：`title: "GitHub - openai/openai-node: Official JavaScript / TypeScript library for the OpenAI API · GitHub"`，`url: "https://github.com/openai/openai-node?utm_source=openai"`
- `history-v3.db`：`title: "Migrating to the Interactions API | Gemini API | Google AI for Developers"`，`url: "https://ai.google.dev/gemini-api/docs/migrate-to-interactions?utm_source=openai"`
- `history-v3-260811.db`：`title: "bun install - Bun"`，`url: "https://bun.com/docs/pm/cli/install?utm_source=openai"`（数据库 mtime 2026-08-11）

**结论：`title` 通常非空；只有 raw 源码文件那类无 `<title>` 的 URL 才给 `""`。**

### 5.5 一条容易误读的负面数字

只针对 483 条 **`openai-responses` 端点**操作（客户端直接发 Responses）逐对象扫描其 manifest 引用的 148 795 个对象时，`url_citation` 命中为 **0**。这**不是**「上游不给」的证据：那 483 条操作里 `tool_usage.web_search.num_requests` **全部为 0**，即**一次真实搜索都没发生过**。真实带引用的样本全部落在 **`anthropic-messages` 端点**的操作里（copilot-api-js 把 Anthropic 请求翻成 Responses 发给 Copilot）。

同理，全部 44 095 个 `payload` / `payload-skeleton` 对象里 `web_search_call` 的 329 处命中，抽样后**全部是散文**——是操作者自己写的中文设计文档被当作 prompt 或 tool 输出记录下来（例如「`web_search_call` **永远降级** tool_use/text 绝不合成 `web_search_tool_result`=R-NO-REVIVE」）。真实 item 都在 `frame` 对象里。

---

## 6. 与既有文档的对账（两处需要修正）

### 6.1 `docs/tmp/260821-copilot-api-js-websearch-response-side.md`（同日同伴报告）——结论已被推翻

该报告 §3.4（`:166`）写：

> **上游没有把搜索结果的标题、URL、摘要放在任何字段里。**

以及 §6.3-8（`:341`）：

> 实测样本里上游没有在任何字段给出标题/URL/摘要，`annotations` 是空数组。这不是参考项目「忘了读」，是**真的没东西可读**。

**这两句的无条件形式是错的。** 该报告的调查范围写得很清楚（`:5`「参考项目 `/home/xp/src/copilot-api-js`」、单一样本 `exp/anthropic-responses-direct/probe-c-websearch.json`），在那个范围内它的观测无误；问题出在**把一个单样本观测写成了关于上游的全称否定**。

该报告自己在 `:342` 正确地划了边界（「这个结论有**边界**……`annotations` 在别的模型 / 别的 `search_context_size` / 更长回答下是否非空，没人测过」），并在 `:348` 把「测 annotations 到底空不空」排为第二优先的探针。**那个探针不必再做**：答案在同一个仓库的 `exp/260820-websearch-probe/raw/B7-*.txt` 里已经躺了一天，历史库里更是有上千个样本。

建议：把 `:166` 与 `:341` 改成带范围限定的表述，并把 `:348` 的优先级表更新——`8` 已答，`7`（synthetic `server_tool_use`）的前提条件因此成立（该报告自己说「如果 annotations 非空，7 就能变成真正的块对而不只是半个」）。

### 6.2 `docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md:220` ——「实测」二字用得过强

原文：

> 「cassette 实测表明 `url_citation` 只在后续 message 的 `content_part.done` 出现，**晚于** `web_search_call` 的 `done`」

逐字节核对：

- **「晚于 `web_search_call` 的 `done`」成立**（C2 与 stream cassette 的事件序都支持，§2.2 的真实样本也支持）。
- **「`url_citation` 在 `content_part.done` 出现」不是 cassette 实测出来的**：两份 cassette 里 `url_citation` 出现 **0** 次（我逐个数过：`responses_web_search_stream.json` 0 次、`responses_web_search_nonstream.json` 0 次，`annotations` 全部为 `[]`）。它当时是合理推断。
- **现在这个推断已被独立证实为真，但同时不完整**：`content_part.done` 确实带完整数组，**但 `output_item.done` 也带**，而且更早还有逐条的 `annotation.added`（§2.2）。

建议：把 `:220` 的「cassette 实测表明」改成指向 §2 的真实样本，并把三个载体都写进去。同文件 §12 的探针 **P9**（`:419`，「流式带 `url_citation` 时是否发 `response.output_text.annotation.added`」）**已可结案：会发**。§11 证据表 `:389`（「`annotations` 会真的填 `url_citation`：B7 有、C1 无，各一次；中等偏强」）可升级为「强」——现在有上千个跨库跨月样本。

### 6.3 仍然成立、无需改动的既有结论

- `web_search_call` item 键恰好四个、无 `encrypted_content`（`:123`）——本次跨 4 库复现，成立。
- `encrypted_content` 一律省略而非伪造（`:166`）——上游确实没有这个句柄，成立。
- citation 与 call 之间**没有关联字段**（`:134`）——本次证实且加剧：§2.2 那个响应里一次有 **13 个 `web_search_call`** 而只有一个带引用的 message，且 `item_id` 逐事件全变（§2.4）。「队列中恰好一个 call 才填充，否则全部落 error 形态」这条局部规则的必要性被强化。

---

## 7. 仍然未决的问题

| # | 问题 | 为什么重要 | 最小探针 |
|---|---|---|---|
| P-B | `include: ["web_search_call.action.sources"]` 在**真的搜了**的那一次，会不会让 `web_search_call.action` 多出 `sources`？ | 若会，这是比 `annotations` 更好的数据源：挂在 call 上、天然与 call 关联，直接消掉「citation 与 call 无关联字段」这个难题 | B8 的 body 加 `tool_choice:{"type":"web_search"}`，其余不变 |
| P-C | 一次响应多个 `web_search_call` 时，引用能不能归属到具体某个 call？ | §2.2 证明多 call 是常态（13 个），归因规则的代价由此决定 | 已有历史样本可离线分析；无需发请求 |
| P-D | `web_fetch` 工具（B9）的响应形态 | 本次未覆盖 | — |

**触发引用最可靠的配方（已实测）**：`tool_choice: {"type": "web_search"}` 强制搜索 + 一个**有稳定权威网页可引**的事实性问题（B7 用的是 "What is the capital of France?"）。反例是「今天几号／现在几点」——那会走成 `time:` 特殊查询，搜了但没有可引用页面。

---

## 8. 对「能不能重建 Anthropic `web_search_tool_result`」的直接回答

Anthropic 的 `web_search_result` 需要 `url` / `title` / `page_age` / `encrypted_content`。逐项对照实测字节：

| Anthropic 字段 | 上游有没有 | 来源 |
|---|---|---|
| `url` | **有** | `url_citation.url` |
| `title` | **有**（**可能为 `""`**） | `url_citation.title` |
| `page_age` | **没有** | 上游任何字段都没有页面时间 |
| `encrypted_content` | **没有** | `web_search_call` item 只有四个键；annotation 也没有 |

所以这不是「退化成一行文本」与「完整原生块」的二选一，而是三选一：

1. **完整原生 `web_search_tool_result`** —— 做不到，缺的字段无论填什么都是伪造。
2. **缺 `encrypted_content` 的近似原生块** —— **做得到**，而且原料比先前认为的充足得多（URL + 标题 + 字符区间 + 可多条）。本项目 `hosted-web-search-spec.md` §5.3（`:161-172`）已按这条路裁决：`encrypted_content` **省略**而非填空串／占位串，并强制记一条 `DEGRADE` 的 `ConversionFact`。**本次取证支持该裁决，并把它的原料从「一份中等强度样本」升级为「跨 4 库、跨 2026-07-31→08-20、上千样本」。**
3. **一行降级文本** —— 做得到，但在有 `url_citation` 的情况下白白丢掉 URL 与标题。

实现时必须同时带上的三条约束：

- **降级分支不可省**：`num_requests >= 1` 不蕴含 `annotations` 非空（§3）。
- **关联只能用 `output_index`**，不能用 `item_id`（§2.4）。
- **`title` 可能是空字符串**，不要把空标题当成「没有这条引用」。

---

## 9. 我做了什么、没做什么

**做了**：

- 读了 `~/.local/share/copilot-api/` 全部 8 个 `history-v3*.db` 的 schema；只读全量扫描 **34 721 733** 个对象（`frame` + `sequence-item` + `payload` + `payload-skeleton`），解压后 **39.17 GB**；对 4 个候选帧做了 transform 图 provenance 判定；完整重建了 1 个带引用的流式响应的上游帧序列。
- 逐字节读了本项目 `exp/260820-websearch-probe/raw/` 下 B1/B3/B7/B8/C1/C2 六份真实上游响应。
- 核对了两份 cassette 的 `url_citation` / `annotation.added` / `annotations` 计数。
- 对照了官方 OpenAI SDK 的 `AnnotationURLCitation` 定义。
- 搜索了 `/home/xp/src/copilot-api-js` 全部 worktree 与 `refs/copilot-reverse`。
- 对第一版探针做了正负样本判别力验证，并因此发现并修掉了一次假阴性（§5.2）。

**没做**（因此这些问题本报告不回答）：

- **没有发任何真实上游请求。** §7 的 P-B 需要凭据与真实调用，未执行。
- 没有查 OpenAI 在线文档页面（用的是本机官方 SDK 生成代码作为官方形状的 ground truth，二者同源于同一份 OpenAPI spec；若需文档原文措辞仍需另查）。
- 没有验证 `web_fetch`（B9）。
- 没有统计带引用的**操作**数（只统计了带引用的**对象**数）——一次响应会贡献多个命中对象，所以 1082 不等于 1082 次会话。
- **没有修改任何数据库、代码或既有文档。** §6 的两处修正是**建议**，未动手。

**旁证（二手，未采信为独立交叉验证）**：`copilot-api-js/refs/copilot-reverse/e2e/RESULTS.md:385-392`（2026-06-26 条目）声称「verified live: gpt-5.5 returns output items `reasoning/web_search_call/message` with citations」，其 `src/providers/copilot/borrow-search.ts:21-36` 的 `extractCitations()` 整个功能建立在「Copilot 会返回 `url_citation`」之上。方向与本报告一致，但那是别人文档里的声称、我没找到对应的原始响应落盘，且它与本报告的一手证据同源于 Copilot，不构成独立交叉验证。
