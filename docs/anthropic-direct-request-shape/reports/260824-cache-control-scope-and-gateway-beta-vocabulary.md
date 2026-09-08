# `cache_control.scope` 与网关 beta 词汇表：两个 400 的实测定形

- 日期：2026-08-24
- 探针：`exp/260824-beta-and-cache-control-probe/`（`probe.py` 主矩阵，`probe_controls.py` 补充对照，`probe_tool_reference.py` 第二轮），逐格输出在该目录 `raw/`，每个脚本各留两轮
- 上游：`https://api.enterprise.githubcopilot.com`（本机账号 token 交换解析出的 `endpoints.api`，**与用户报错日志里的主机逐字相同**）
- 模型：`claude-opus-5`（用户两个 400 报的就是它；beta 是应答模型的能力，换模型测的判决不能搬）
- 形态：非流式，一句话提示词，`max_tokens` 16，每格一次调用，正控制先跑
- 复现性：主矩阵与对照各跑两遍，两遍逐格一致

## 0. 一句话

两个 400 是两层拒绝：`scope` 被 **Anthropic 后端的 body schema** 拒，加上对应 beta 也救不回来；`tool-search-tool-2025-10-19` 被 **Copilot 网关的 beta 词汇表** 拒，而它启用的 body 字段上游**不带这个 beta 也照收**——所以剥掉这个 flag 不会引发二次 400。

## 1. 触发它的那两次失败

用户在另一台机器上，Claude Code 打到本代理的 `/v1/messages`，走直连路径（`translation_required: false`，body 按客户端原样转发）：

```
[FAIL] 400 POST /v1/messages claude-opus-5 660ms: upstream rejected the request: Error code: 400 -
{'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'system.1.cache_control.ephemeral.scope: Extra inputs are not permitted'}, 'request_id': 'req_011CeN2ECTn17ZNEDWfRQfjx'}

[FAIL] 400 POST /v1/messages claude-opus-5 831ms: upstream rejected the request: Error code: 400 -
{'error': {'message': 'unsupported beta header(s): tool-search-tool-2025-10-19', 'code': 'invalid_request_body'}}
```

**两个错误信封的形状不同，这是第一条线索而不是噪声**：前者是 Anthropic 自己的 `{"type":"error","error":{"type":"invalid_request_error"}}`，后者是 Copilot 网关的 `{"error":{"message","code":"invalid_request_body"}}`。实测证实这对应两个不同的拒绝层，且两层的规则互不知情（见 §2 的 C3）。

## 2. `cache_control` 的字段矩阵

| 发出的东西 | 上游 | 分量 |
|---|---|---|
| C0 什么都不加（正控制） | **200** | 这一轮可读的前提 |
| C1 `cache_control: {type: ephemeral}` | **200** | 裸标记被接受 |
| C2 `cache_control: {type: ephemeral, scope: "organization"}`，不带 beta | **400** `system.1.cache_control.ephemeral.scope: Extra inputs are not permitted` | 逐字复现用户的第一个 400 |
| C3 同 C2，**带** `anthropic-beta: prompt-caching-scope-2026-01-05` | **400** 同上，一字不差 | **决定修复方向的那一格** |
| C4 `cache_control: {type: ephemeral, ttl: "1h"}`，不带 beta | **200** | `ttl` 不必剥 |
| C5 同 C4，带 `extended-cache-ttl-2025-04-11` | **200** | |
| C6 `scope` 放在 message 的 content block 上 | **400** `messages.0.content.0.text.cache_control.ephemeral.scope: …` | |
| C7 `scope` 放在 tool 上 | **400** `tools.0.custom.cache_control.ephemeral.scope: …` | |
| E3 `scope: "session"`（换一个值） | **400** 与 C2 同形 | 未知的是**键**，不是值 |
| E4 `{type: ephemeral, ttl: "1h", scope: "session"}` | **400** 只点 `scope` | `ttl` 与 `scope` 可分别处置 |

三条结论，**都可据以行动**：

1. **加 beta 救不了（C3）。** 而单独发 `prompt-caching-scope-2026-01-05` 这个 header、body 不用它，网关是 **200**（§3 的 B 系列）。也就是说**网关收下了这个 beta，后端 schema 却不认它启用的字段**——上游自身两层不一致。这一格是决定性的，因为它排掉了「补发 beta」这条与「剥字段」方向完全相反的修法。
2. **必须剥字段，而且要覆盖三层。** `system` 块、message 的 content 块、`tools` 各有各的 schema，三处都拒（C2/C6/C7）。只修 `system` 会在下一个请求上换个路径再挂。
3. **上游是 strict schema（`Extra inputs are not permitted`），所以判据应当是白名单而不是黑名单。** 实测里 `type` 与 `ttl` 收、`scope` 拒；下一个新字段落地时，黑名单会再挂一次，白名单不会。代价是：若上游将来支持某个我们没列的新字段，会被我们提前剥掉——但那只是**少一个优化**，而不剥是**整个请求死**，两边代价不对称。

**这套探针不覆盖什么**：只有 `claude-opus-5` 一个模型、只有非流式、只有 enterprise 端点、每格一次调用。个人端点（`api.githubcopilot.com`）与流式没测。

## 3. 网关的 beta 词汇表

每个 flag 单独一发，body 不用它启用的任何东西：

| flag | 上游 |
|---|---|
| `claude-code-20250219` | 200 |
| `oauth-2025-04-20` | 200 |
| `interleaved-thinking-2025-05-14` | 200 |
| `fine-grained-tool-streaming-2025-05-14` | 200 |
| `context-management-2025-06-27` | 200 |
| `prompt-caching-2024-07-31` | 200 |
| `extended-cache-ttl-2025-04-11` | 200 |
| `prompt-caching-scope-2026-01-05` | 200 |
| `mid-conversation-system-2026-04-07` | 200 |
| `advanced-tool-use-2025-11-20` | 200 |
| `token-efficient-tools-2025-02-19` | 200 |
| `tool-search-tool-2025-11-19` | **200** |
| **`tool-search-tool-2025-10-19`** | **400** `unsupported beta header(s): tool-search-tool-2025-10-19` |
| **`output-128k-2025-02-19`** | **400** `unsupported beta header(s): output-128k-2025-02-19` |

补充对照：

- E1：把上表 200 的那些**一起**放进一个 header 值 → **200**。不是只有单发才行。
- E2：同一组再加上 `tool-search-tool-2025-10-19` → **400**，且网关**只点名坏的那一个**。一个坏 flag 会连坐整组，这就是用户那次失败的形状。

**注意这是「网关认不认识这个名字」，不是「这个模型有没有这个能力」。** 错误信封是网关的，措辞是 `unsupported beta header(s)` 而不是 `invalid beta flag`；而 `tool-search-tool-2025-11-19` 与 `tool-search-tool-2025-10-19` 只差一个日期戳，前者收后者拒——这是词汇表比对，不是能力判定。分量：可据以行动。这一点对实现位置有直接后果，见 §5。

## 4. 剥掉 tool search 的 beta 之后，body 会不会二次挂

`src/app/pipeline/request_headers.py:11` 有一条承重的担忧：剥 header 不会优雅降级，beta 启用的 body 字段会变成未识别字段而再吃 400。**在这个 flag 上这条担忧不成立**，实测：

| 用例 | 上游 |
|---|---|
| D0 两个普通 tool（正控制） | 200 |
| D1 `defer_loading: true` / `false` 各一个，**不带任何 beta** | **200** |
| D2 同 D1 的 body，带 `tool-search-tool-2025-10-19` | **400** 只报 header |
| T2 `{type: "tool_search_tool_regex_20251119"}` 服务端工具 + 一个 `defer_loading` 工具，**不带 beta** | **200** |
| T3 同 T2，带 `tool-search-tool-2025-11-19` | 200 |

所以：**`defer_loading` 与 `tool_search_tool_regex_*` 这两样上游不需要 beta 就收**。剥掉 `tool-search-tool-2025-10-19` 是安全的，body 原样travel 即可。D1/D2 是同一 body 的两发，唯一变量是 header，所以「header 是唯一死因」这句是对照出来的，不是推断的。

**但上面这些只覆盖第一轮。** Claude Code 用的是**客户端自定义**的 tool search：它声明一个普通 `ToolSearch` function tool、给候选工具打 `defer_loading`，模型调用后由客户端执行搜索，**下一轮**才把 `{"type":"tool_reference","tool_name":…}` 放进 `tool_result.content[]` 送回。`tool_reference` 只在第二轮出现，只测第一轮会漏掉「第一轮成功、第二轮 400」这个失败形状——而那正是 `request_headers.py:11` 警告的那种二次失败真正会现身的地方。所以第二轮单独测（`probe_tool_reference.py`，两遍，`raw/run-tool-reference*.txt`）：

| 用例 | 上游 |
|---|---|
| R0 同样的两轮对话，`tool_result` 是普通文本（正控制） | 200 |
| **R1 第二轮 `tool_result.content[]` 里是 `tool_reference` 块，不带任何 beta** | **200** |
| R2 同 R1，带 `tool-search-tool-2025-11-19` | 200 |
| R3 同 R1，带 `advanced-tool-use-2025-11-20` | 200 |

R1 是这一节的结论所在：**整条 tool search 生命周期在完全不带 beta 时都被接受**，所以剥掉那个 flag 之后没有第二轮在等着。

一处**用例设计缺陷，记下来免得下一个人误读**：主矩阵的 T1（只放一个 tool 且 `defer_loading: true`，不带 beta）返回 400 `At least one tool must have defer_loading=false. All tools cannot be deferred.` —— 这**不是**「上游不认识这个字段」，恰恰相反，是上游**认识并执行了这个字段的语义规则**，而我的用例把所有工具都 defer 了。D1 是为修掉这个缺陷补的。第一遍读这一格时很容易读成「defer_loading 被拒」，那会得出完全相反的结论。

## 5. 对实现的直接后果

1. **`cache_control` 的剥离必须发生在 body 上，覆盖 system / messages content / tools 三层，判据用白名单（保留 `type`、`ttl`）。** 依据 §2。
2. **beta 的剥离是网关词汇表问题，与模型无关。** 现有 `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags` 是 **per-model 正则表**，语义是「这个模型没有这个能力」；而这次要挡的是「这个 GHC 部署不认识这个名字」。两者可以用 `.*` 硬凑到一起，但那会把两种判据混进同一张表，且 spec §7 与 A-4 已把**那张表的内容判给用户裁决**——所以不应当把内置默认塞进用户的表。
3. **`ttl` 不要动。** C4/C5/E4 都说明它被接受，剥它是净损失。
4. 若将来 GHC 补上 `tool-search-tool-2025-10-19`，我们多剥一个 flag 的代价是「少一个上游其实已支持的协商」，而 §4 证明 body 侧不受影响。不剥的代价是整请求死。这个不对称是「内置一份实测词汇表」值得做的理由，也是它过期时不会造成伤害的理由。

## 6. 我排除了什么

- **「补发缺失的 beta 就能收 scope」**——C3 直接证伪。这条如果不测，是最自然的第一猜想，而且方向与正解相反。
- **「只修 `system` 层就够」**——C6/C7 证伪。用户的日志只报了 `system.1`，只看日志会以为这是 system 独有的问题。
- **「`scope` 的值非法」**——E3 换值同形错误，证伪；未知的是键。
- **「`defer_loading` 被上游拒绝，所以剥 beta 会二次挂」**——T1 一度支持这个读法，D1 证伪。见 §4 那段设计缺陷说明。
- **「个人端点与企业端点行为不同，本机测不了用户的问题」**——本机 token 交换解析出的 `endpoints.api` 就是 `api.enterprise.githubcopilot.com`，与用户日志逐字相同，这个担忧不成立。**但反过来不成立**：个人端点没测，本文所有结论仅对企业端点有效。
- **未做**：没有测流式，没有测其它模型，没有测 `/v1/messages/count_tokens`。`count_tokens` 值得补——它吃同一个 body，很可能有同一个 `scope` 问题——但不在这次的证据里，故不写进结论。
