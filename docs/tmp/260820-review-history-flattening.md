# 评审：历史 server-tool blocks 摊平（2026-08-20 第二批裁决）

**评审者**：leaf executor（只读；未修改仓库任何文件，本报告除外）
**评审基准**：工作树 `git diff` 中属于本切片的 6 个文件，HEAD = `db9aa7d`
**范围**：`src/app/pipeline/subscribers/server_tools.py`、`tests/unit/test_subscribers_server_tools.py`、`docs/2604-rewrite/{hooks-system,tool-use,anthropic-compat}.md`、`docs/.human-controlled-candidates/pipeline-subscriptions.md`
**已排除**：`5e98a9e` 已评审部分（本次未破坏它，见 §5 的隔离验证）；并行会话的 `auth/providers.py`、`cli.py`、`bundled-config.yaml`、`model_provider/github_copilot.py`、`server/handler.py`、`tests/unit/test_builtin_subscribers.py`

**结论**：blocker 1，major 1，minor 7。摊平这条路本身的判据是对的，实现对 `web_search` 族正确；缺陷集中在 `web_fetch` 族与一份未同步的冻结 spec。

**验证手段**：`ruff check` 与 `pyright` 对两个改动文件均零问题；`uv run pytest tests/unit/test_subscribers_server_tools.py tests/unit/test_builtin_subscribers.py` 24 passed；另在 `/tmp` 的 `git archive HEAD` 纯净导出树上跑了 6 组探针（`/tmp/probe_wf.py`），下文标 **实测** 的结论都来自它。

---

## 1. Blocker

### B1 — 冻结 spec 与代码正面矛盾，而 live doc 恰恰引用了说反话的那一段

`docs/2604-rewrite/tool-use.md:14` 写：

> **2026-08-20 起，「不过滤服务端 blocks」不再成立**（用户裁决，见 [hooks-tokenization-spec.md](hooks-tokenization-spec.md) §5.2 的增补段）。

被引用的那一段，`docs/2604-rewrite/hooks-tokenization-spec.md:132`，逐字写的是：

> 它**只动 `tools[]` 声明，不碰历史 blocks**，所以本节关于「残留 server-tool blocks 被上游拒绝是有意的 breaking removal」的立场**未被改变**，仍然有效。

`hooks-tokenization-spec.md` 本次**未被修改**（`git status` 中不出现）。于是：

- 具体失败输入：一个读者（或下一个会话）想确认「历史 blocks 到底动不动」，顺着 `tool-use.md` 给的引用跳过去。
- 具体错误结果：他读到的权威原文说「不碰历史 blocks，breaking removal 立场未变」，与磁盘上正在运行的代码相反。若他据此判断，这次摊平会被当成**未经裁决的越权改动**而被回退。

项目规则「Specs remain normative while their external contract is active」与用户第二批裁决的第 4 项（「文档要写好并正确链接」）在这里同时失效。修法只有一条：在 `hooks-tokenization-spec.md:128-132` 那段增补里补写第二批裁决——「历史 blocks 这一半也被推翻，改为摊平成文本」，并说明 breaking removal 立场退役。在此之前 `tool-use.md` 的那句引用是**指向反义原文的链接**。

判为 blocker 而非 major 的依据：这是本批裁决唯一明确要求做的文档动作，而它正好是唯一做错的那份；且矛盾的两端都是**规范性**文本，不是解释性复述。

---

## 2. Major

### M1 — `web_fetch` 成功的结果被渲染成「失败」，且抓回的正文与 URL 全部丢弃

`src/app/pipeline/subscribers/server_tools.py:96-99`：

```python
if isinstance(content, dict):
    entry = cast(dict[str, Any], content)
    code = entry.get("error_code")
    return f"[{family} failed: {code}]" if isinstance(code, str) else f"[{family} failed]"
```

「`content` 是 dict ⇒ 这是错误块」这个判据只对 `web_search` 成立。Anthropic SDK 的类型定义（`copilot-api-js/node_modules/@anthropic-ai/sdk/resources/messages/messages.d.ts:1920`）写得很清楚：

```ts
export interface WebFetchToolResultBlockParam {
    content: WebFetchToolResultErrorBlockParam | WebFetchBlockParam;   // 单个对象，不是数组
    tool_use_id: string;
    type: 'web_fetch_tool_result';
}
export interface WebFetchBlockParam {          // 成功形态
    content: DocumentBlockParam;               // ← 抓回来的正文在这里
    type: 'web_fetch_result';
    url: string;
    retrieved_at?: string | null;
}
```

即 `web_fetch` **成功**时 `content` 也是 dict，且不含 `error_code`。

**具体失败输入**（探针 A，实测）：

```json
{"role": "assistant", "content": [
  {"type": "server_tool_use", "id": "srvtoolu_9", "name": "web_fetch",
   "input": {"url": "https://example.com/spec"}},
  {"type": "web_fetch_tool_result", "tool_use_id": "srvtoolu_9",
   "content": {"type": "web_fetch_result", "url": "https://example.com/spec",
               "retrieved_at": "2026-08-20T00:00:00Z",
               "content": {"type": "document", "title": "The Spec",
                           "source": {"type": "text", "media_type": "text/plain",
                                      "data": "PAGE BODY TEXT"}}}}]}
```

**具体错误结果**（实测输出）：

```
[{'type': 'text', 'text': '[web_fetch]'}, {'type': 'text', 'text': '[web_fetch failed]'}]
```

三处损伤，从重到轻：

1. **告诉模型一件假事**。抓取成功，摊平后说它失败了。后续的 assistant 文本会引用抓回来的内容，而上文说这次抓取失败——这是自相矛盾的历史，比信息缺失更糟。M1 的严重性主要在这一条。
2. **正文整份丢弃**。`web_fetch` 的全部价值就是 `content.content.source.data` 那段文本；`_render_results` 从不看它。对 `web_search` 而言「只留 title/url」是合理的（见 §4），因为搜索结果本来就没有正文字段；对 `web_fetch` 而言留下的**什么都不是**。
3. **URL 也丢了**。`web_fetch_result.url` 在 dict 分支上根本没被读；调用侧 `server_tools.py:138-142` 又只读 `input.get("query")`，而 `web_fetch` 的入参键是 `url`（`WebFetchTool*.input` 用 `url`），所以调用块也退化成裸 `[web_fetch]`。整轮 `web_fetch` 交互被压成两个不含任何信息的标记。

**这不是理论输入**：`web_fetch` 就在 `_REJECTED_TYPE_PREFIXES` 里，它的声明会被剥掉；而这一遍存在的全部理由就是「历史来自真 Anthropic API 或别的曾执行过 server tool 的代理」（`docs/tmp/260820-review-server-tool-subscriber.md:126`）。那类历史里的 `web_fetch_tool_result` 绝大多数是成功的。

**建议修法**（判据换成块自己的 `type`，而不是 Python 类型）：

- `content.get("type")` 以 `_tool_result_error` 结尾 → 失败渲染（现有分支）；
- `type == "web_fetch_result"` → 渲染 `url`、`content.title`，并考虑截断保留一段正文；
- 其余 dict → 现在的 `[{family} results omitted]` 兜底，而不是断言失败；
- `server_tool_use` 的入参同时读 `query` 与 `url`。

---

## 3. Minor

| # | 位置 | 具体输入 → 具体结果 | 判据 |
|---|---|---|---|
| m1 | `server_tools.py:108-111` | `content: [{"type":"web_search_result","title":"Only a title","encrypted_content":"zz"}]`（缺 `url`）→ 实测得到 `[web_search results omitted]`，那条结果整个消失 | `url` 在 SDK 里是必填，所以这是畸形输入；但兜底把「有部分数据」说成「omitted」，与 §4 的取舍原则不一致。至少该退回只印 `title` |
| m2 | `server_tools.py:150` | 带 `cache_control: {"type":"ephemeral"}` 的 `web_search_tool_result` → 实测新块不含 `cache_control`，断点静默消失 | 无正确性影响（断点上限是 4，少一个不报错）；但若客户端唯一的断点落在该块上，这个会话的 prompt caching 从此不再命中，且无任何日志 |
| m3 | `server_tools.py:140` | `input: {"query": "date   "}` → 实测 `'[web_search] date   '`，尾随空白被原样带入 | `query.strip()` 只用来判空，插值时没有 strip。仅当该块是**末尾 assistant 轮的最后一个块**时才致命（Anthropic 拒 `final assistant content cannot end with trailing whitespace`），且这段文本不会再经过 `fix_anthropic_request`。一字符修法：插值也用 `query.strip()` |
| m4 | `server_tools.py:9`、`:52`、`:120` | 三处把 `Tool 'web_search' not found in provided tools` 当作上游必然回话陈述，无出处标注 | 溯源到 `copilot-api-js/src/lib/request/strategies/web-search-not-found-retry.ts` 的 matcher，是参考项目的一手、本项目的二手，**本项目未实测**。同一个模块对别的事实标注得极其克制（「measured on gpt-5.5」「has not been measured」），这三处破了自己的规矩。**证据权重：足以据此决策**（参考项目为它专门写了一条自愈臂），只是措辞该标出来 |
| m5 | `server_tools.py:184-234` | `_strip_declarations` 定义在唯一调用者 `adapt_server_tools` **之后** | 运行无碍。但这个文件的主产物是 docstring，顺读一遍现在是倒着的；`:198` 的注释「the declaration line below」也只有靠这个倒序才读得通。建议把 `_strip_declarations` 挪到 `adapt_server_tools` 之前 |
| m6 | `docs/.human-controlled-candidates/pipeline-subscriptions.md`（2026-08-20 增补段） | 「六个调用点无一改动」 | `git grep -n "build_chain(" 5e98a9e -- src tests` 实测 **9** 处（去掉锁定测试自己是 8 处）。承重的那半句（无一改动）成立，数字不成立 |
| m7 | `docs/2604-rewrite/hooks-system.md` 新增小节标题 | 「## 事件订阅（新链路，**正在吸收 hooks**）」 | 同一节的「尚未建成」条目写「吸收本身……没有一个内置 hook 迁过来」，`pipeline-subscriptions.md` 写「吸收尚未发生」。标题比正文超前一步，读目录的人会以为迁移已开工。改成「（新链路，方向是吸收 hooks）」即可 |

另有一处不在评审范围但顺手看到、修起来极便宜：`docs/tmp/260820-websearch-fix-v2-design.md:262` 表格里「出站前剥除」误写成「出**станции**前剥除」（混入西里尔字母）。`anthropic-compat.md` 本身没有这个问题。

---

## 4. 判为正确的部分及其判据

**摊平的正确性（提问 1）——对 `web_search` 族正确，对 `web_fetch` 族见 M1。**

- 非 dict block、`type` 非 str、`server_tool_use` 缺 `name`：全部 `return None` 原样保留（`:124-134`）。判据：这个模块的既定立场是「只删上游已实测拒绝的东西，不替客户端整理畸形输入」（`:56` 已写下同一条），与 `_rejected_type` 一致。
- 普通 `tool_result` 不被误吞：`:145` 先排 `== "tool_result"` 再排非 `_tool_result` 后缀。判据：与翻译器里同一条判据同形（`src/app/protocols/anthropic_responses.py:624`），两处不会漂移。
- `code_execution_tool_result` / `mcp_tool_result` / `tool_search_tool_result`：两个前缀都不命中，实测原样保留（探针 F）。判据：它们的声明没被剥，引用仍有指向。
- `content` 为 list 但元素非 dict：跳过；全跳完落到 `[{family} results omitted]`，非空。

**摊平后的合法性（提问 2）——未发现失败面。**

- **不会产生空文本块**。四条返回路径全是非空字面量：`[{family}]`、`[{family}] <非空 query>`、`[{family} failed…]`、`[{family} results…]`。所以并行会话刚加的空文本块剥离已经跑过这件事不构成损失。
- **thinking 相邻性不变**。摊平是 1:1 替换，不删块不加块，非 thinking 块换成非 thinking 块，`destack` 留下的相邻关系原封不动；turn 也不可能被摊平成空。
- **配对不受影响**。`server_tool_use` / `*_tool_result` 按 `hooks-tokenization-spec.md:126` 本就不进入 client tool 配对修复。
- **assistant 轮里多个连续 text 块合法**。Anthropic 的 content 是有序块列表，对 `text` 没有相邻性约束；本项目自己就在产出相邻 text（`destack.py:32` 的 `insert_text` 策略往两块之间插 text 块）。

**顺序问题（提问 3）——不构成问题，只有 m3 一个窄口。** 结论建立在上面三条之上：摊平产生的文本不经过 `fix_anthropic_request` 的三件事（空文本剥离、thinking layout、`context_management` 规整）里，前两件都被上面证明无从触发，第三件是顶层字段。唯一漏网的是尾随空白（m3），而 `fix_anthropic_request` 本来也不处理尾随空白，所以不是「顺序错了」而是「两边都没这条规则」。

另外实测确认摊平**幂等**（探针 E）：`attempt.prepare` 在重试循环内，第二次 attempt 时块已是 text，`flattened` 为 0，不会重复改写也不会重复打日志。

**信息取舍（提问 4）——对 `web_search` 合理。** `WebSearchResultBlock` 的全部字段是 `encrypted_content`、`page_age`、`title`、`type`、`url`（SDK `messages.d.ts:1709`）——**没有正文片段字段**，所以 title + url 就是全部可读内容，不存在「更该保留的正文」。`encrypted_content` 丢弃正确（除上游外不透明，且是绝大部分字节）。`page_age` 是唯一有价值的漏项（新鲜度），ROI 低，不建议为它单独动手。渲染格式 `[web_search results]\n- Title — URL` 出现在 assistant 文本块里，读起来是转录注记而不是工具信封，与参考实现的降级文本同形；**不认为会被误读成真实工具输出**。

**家族判据（提问 5）——正确，且边界可说清。** `web_search_helper` 这类客户端工具到达时是 `tool_use` 而非 `server_tool_use`，根本进不到 `_family`。要误判，需要存在一个名字以 `web_search`/`web_fetch` 开头、却不属于这两族的 **Anthropic 托管** server tool；SDK 的 `ServerToolUseBlock.name` 是闭合并集 `'web_search' | 'web_fetch' | 'code_execution' | 'bash_code_execution' | 'text_editor_code_execution' | 'tool_search_tool_regex' | 'tool_search_tool_bm25'`（`messages.d.ts:1041`），没有这样的名字。type 一侧同理，实测 `code_execution_tool_result` 不命中。**证据权重：足以据此决策**，限定条件是「以该 SDK 版本的闭合并集为界」。

**文档（提问 6）——除 B1、m6、m7 外准确。**

- `anthropic-compat.md` 那行从「完整支持」改成「不支持，且已实测被拒的族会在出站前剥除」：**既不过头也不不足**。逐条核对——代理确实不执行 web search/fetch/code execution（一直如此，旧文写「完整支持」才是错的）；`web_search*`/`web_fetch*` 声明与历史 blocks 确实被剥/摊平；`memory_*`/`tool_search_*`/`text_editor_*` 确实继续透传（`_REJECTED_TYPE_PREFIXES` 只有两个前缀）；Responses leg 的 hosted web search 确实未实现。旧文那句「可按配置剥离」暗示存在一个从来不存在的配置项，删掉是对的。
- 「已实测被拒」对 `web_fetch` 成立：Anthropic 腿 400 `rejected tool(s): web_fetch` 有 2026-07-12 的一手记录（经 `docs/tmp/260820-websearch-on-responses-leg.md:351` 转述自 `copilot-api-js/exp/server-tool-web-fetch-poc/README.md`）。
- `hooks-system.md` 新节的事实核对：五个事件名与 `direct_driver/base.py:29-33` 逐字一致；「`attempt.prepare` 在重试循环内发布」与 `base.py:130` 一致；「翻译发生在驱动之前，订阅者在翻译腿上看到的是已翻译成目标格式的载荷」与 `server/handler.py:79-87` 一致；锁定测试 `tests/unit/test_builtin_subscribers.py` 存在且断言按事件全集（`frozen_by_event`）。
- **链接全部可解析**：`../.human-controlled-candidates/pipeline-subscriptions.md`、`../.human-controlled-candidates/config-migration-gaps.md`、`hooks-tokenization-spec.md`、`anthropic-compat.md`、`tool-use.md`、`../2604-rewrite/hooks-system.md` —— 逐个对 `ls` 核过，均存在。（B1 是**语义**断链，不是路径断链。）
- 一处观察不列为发现：`tool-use.md:24` 从 live doc 指向 `docs/tmp/260820-websearch-fix-v2-design.md`。它是并列在 `anthropic-compat.md` 之后的补充指针，不是唯一权威，符合项目规则的字面；只提醒该主题定稿时把它蒸馏掉。

**测试分辨力（提问 7）——无恒真断言。**

- 逐条查过 7 条新增断言，没有一条在被测代码被短路时仍然为真。特别是 `test_the_opaque_bulk_of_a_result_is_not_carried_into_the_text`：看着像「not in」这种容易恒真的形状，实际上摊平不发生时 `content[0]` 是原始 dict、没有 `"text"` 键，直接 KeyError 而失败——有分辨力。
- 短路 `_flatten_history` 仍绿的 3 条（客户端 `tool_result`、`code_execution`、纯文本历史）是**反向守卫**，它们防的是过度匹配而不是摊平本身，全绿是设计正确而非分辨力不足。与派发说明里「4 条变红」完全吻合。
- **该测而没测的失败面，两条，都对应上面的具体缺陷**：(1) 成功的 `web_fetch_tool_result`（M1，会红）；(2) `server_tool_use{name:"web_fetch", input:{"url":...}}`（M1 第 3 点，会红）。不提任何与具体失败面无关的覆盖率建议。

---

## 5. 评审过程中的一次红灯及其归因（**与本切片无关，无需处置**）

首次运行 `uv run pytest tests/unit/test_subscribers_server_tools.py tests/unit/test_builtin_subscribers.py` 时 `test_the_counting_leg_gets_the_same_treatment_as_the_leg_it_measures` 失败（`{'input_tokens': 6, 'estimated': True} != {'input_tokens': 7}`）。归因如下，结论是**并行会话的在途状态**：

1. `/tmp` 下 `git archive HEAD` 导出纯净树 → 该文件 4 passed；
2. 只把本切片的 `server_tools.py` 拷进去 → 仍 4 passed；
3. 把并行会话改过的 4 个 `src/` 文件全拷进去 → 仍 4 passed；
4. 回到真实仓库重跑 → 24 passed，且该文件变成 **5** 个用例（导出树是 4 个）。

即 `src/app/server/handler.py` 与 `tests/unit/test_builtin_subscribers.py` 正在被并行会话编辑（mtime 07:22:13 / 07:22:23，晚于 `server_tools.py` 的 07:13:34），我第一次跑时撞上了写到一半的中间态。**本切片没有破坏 `5e98a9e`**（第 2 步即为该结论的隔离证明）。

顺带一个跨切片的提醒，不是发现：并行会话正在让 `handle_count_tokens` 也发布 `attempt.prepare`。一旦落地，`_flatten_history` 会在计数腿上同样改写 payload——这是想要的（计的是真正会发出去的 body），且实测幂等，两边不冲突。
