---
report_id: tool-search-beta-400-investigation
attempt_id: tool-search-beta-400-investigation-260824-01
status: in-review
reviewed_at_rev: 2c4ba5928c5f9ea1937a87b35b47c71d83d5c5d0
reviewed_at: 2026-08-24
scope: direct Anthropic Messages path to api.enterprise.githubcopilot.com
---

# `tool-search-tool-2025-10-19` 400 调查

## 范围与证据等级

本报告只调查用户指定的五个问题，不修改 `src/`。主项目源码快照为 `2c4ba5928c5f9ea1937a87b35b47c71d83d5c5d0`；所读的相关 `src/` 文件在调查时均未出现在 `git status --short -- <files>` 输出中。官方 VS Code Copilot Chat 参考仓库快照为 `5863f5a7088958050792b5dccbe8b46c6e13eccc`，相关文件最后一次提交为 `b7e094da0521c8502824fed042101f877e6f7c15`。前身 `copilot-api-js` 快照为 `8001c3028f6c58cda99e1bdf2fd0516d64c1ae66`。Claude Code 行为取自本机抽取源码 `claude-code-2.1.241/app.pretty.js`，并用 2.1.207、2.1.226 的同名常量交叉检查。

证据分三类：①“读到的原文”是源码、官方文档或已保存的原始探针输出；②“命令输出”是本轮只读命令所得；③“我的推断”明确标出，不与实测混写。分量档位使用“可据以行动”“仅为倾向需更多样本”“仅存档”。

## 核心结论

| ID | 结论 | conclusion_strength | 分量档位 |
|---|---|---|---|
| TS-01 | `src/app/config/settings.py` 的 `tool_search` 与 `tool_search_non_deferred` 属于已退出生产路径的旧 `AppSettings`；当前生产链无人读取，和活跃的 `strip_anthropic_beta_flags` 没有接线关系。 | confirmed | 可据以行动 |
| TS-02 | Tool search 有两种相关 wire 形态：自定义／客户端搜索使用普通搜索 tool、`tools[].defer_loading` 和后续 `tool_reference`；Anthropic 托管搜索再增加 `type: tool_search_tool_regex_20251119` 或 BM25 变体。Claude Code 2.1.241 的运行时代码走前一种，不会自行加入 `_20251119` server tool；VS Code Copilot Chat 与前身会加入后者。 | confirmed | 可据以行动 |
| TS-03 | 对本次同一 enterprise GHC host、`claude-opus-5`，网关拒绝 `tool-search-tool-2025-10-19`，接受 `tool-search-tool-2025-11-19` 与 `advanced-tool-use-2025-11-20`。`20251119` 不是 `2025-10-19` 的另一种排版，而属于后续版本的工具类型／beta 词汇。 | confirmed | 可据以行动 |
| TS-04 | 现有实测已证明：去掉坏 header 后，混合 `defer_loading:true/false` 的普通 tools 会 200，`tool_search_tool_regex_20251119`＋一个 deferred tool 也会 200；因此用户点名的两类 body 字段不会紧接着造成第二个 400。 | confirmed | 可据以行动 |
| TS-05 | direct Anthropic path 没有 tool-search 专用的 `tools` 数组清洗或改写；它只对已实测不支持的 `web_search*`／`web_fetch*` 声明提前拒绝，并明确让 `tool_search_*` 原样通过。 | confirmed | 可据以行动 |
| TS-06 | 尚无“剥掉 header 后，Claude Code 完成一次自定义 `ToolSearch` 调用并在下一轮回传 `tool_reference`”的端到端实测。当前官方文档已把该能力写成无需 beta 的请求，但官方 Python SDK 示例仍发送旧 beta；这不推翻 TS-04，只限制“整段多轮生命周期同样无 beta 可用”的外推。 | inconclusive | 仅为倾向需更多样本 |

## 1．`settings.py` 中的 `tool_search` 到底是什么

### 1.1 读到的原文

`src/app/config/settings.py:77-92` 把 `tool_search: bool = True` 与 `tool_search_non_deferred: list[str]` 放在旧类 `AnthropicConfig` 中；同一类还有旧字段 `beta_strip_headers`（`:81`）。这不是当前配置 schema 的 `FixAnthropicRequestHook`。

`src/app/config/loader.py:1-5` 已在模块 docstring 中明确写道：`AppSettings` “no longer serves any production path”；`load_settings` 在 `src/` 中除 re-export 外没有调用者；当前所有入口使用一字之差的 `app.config.loading` 来装载 `ProxyConfig`。`src/app/config/loader.py:86-106` 是旧加载器实现本身。

本轮用下列两类读法搜索整个 `src/`，均无命中：

```text
$ rg -n '\.tool_search\b|\.tool_search_non_deferred\b|getattr\([^\n]*tool_search' src -g '*.py'
attribute_reader_rg_exit=1
$ rg -n -F '["tool_search"]' "['tool_search']" '["tool_search_non_deferred"]' "['tool_search_non_deferred']" src -g '*.py'
mapping_reader_rg_exit=1
```

反向搜索 `AppSettings` 的生产 import，只命中旧 `app.config.loader`、`app.upstream.*` 和测试；当前 composition root 明确接收 `ProxyConfig`，见 `src/app/server/composition.py:1-5,23-24,450-454`。入口调用当前 loader 的证据是 `src/app/cli.py:105,387`，而 `load_settings()` 在 `src/` 无调用点；本轮命令输出仅列出测试中的调用。

### 1.2 与 beta strip 的关系

活跃配置是 `src/app/config/schema.py:269-274` 的 `StripRequestHeadersHook.strip_anthropic_beta_flags`。`src/app/server/composition.py:503-507` 在启动时编译它；`src/app/pipeline/driver.py:98-115` 在路由得出 resolved model 后调用 `strip_denied_beta_flags()`；具体 token 过滤在 `src/app/pipeline/request_headers.py:82-129`。因此两者只是在问题域上都与 Anthropic tool/beta 有关，代码上没有父子、开关或 fallback 关系。

当前 `docs/.human-controlled/config.example.yaml:439-448` 展示的是活跃的 `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags`。同文件 `:467-472` 另有一段被注释掉的 `hook_fix_anthropic_request.tool_search.enabled` 示例，但当前 `ProxyConfig` 的 `FixAnthropicRequestHook` 在 `src/app/config/schema.py:343-350` 没有该字段，也没有 compat migration；这段注释不能证明功能接线。人写文档本轮不改。

**结论 TS-01。读到的事实：**字段属于旧 `AppSettings`，无 reader，活跃 beta strip 是另一套 `ProxyConfig` 配置。**我的推断：无。**分量：可据以行动。

## 2．这个 beta 给 body 带来什么

### 2.1 Anthropic 官方契约：两种搜索方式

当前官方文档《Tool search tool》明确区分两种方式：内建 tool search 是 server-side；自定义 tool search 由客户端执行。共同基础是 `tools[].defer_loading: true`，含义是完整定义仍随每个请求发送，但不会预先进入模型上下文，待 `tool_reference` 被搜索结果选中后再展开。官方还规定搜索 tool 自身不得 deferred，且至少一个 tool 必须 non-deferred。来源：<https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool> 的“How tool search works”“Deferred tool loading”“Custom tool search implementation”“Error handling”各节。

内建 server-side 形态在同一官方文档中是：

```json
{"type":"tool_search_tool_regex_20251119","name":"tool_search_tool_regex"}
{"type":"tool_search_tool_bm25_20251119","name":"tool_search_tool_bm25"}
```

其它候选 tools 带 `defer_loading:true`。响应会含 `server_tool_use`、`tool_search_tool_result`、嵌套的 `tool_search_tool_search_result` 与 `tool_reference`；server search 在 Anthropic 侧执行。

自定义／客户端搜索不需要上述 typed server tool。官方 Python SDK 的现行示例 `examples/tools_runner_search_tool.py` 在 blob `a63f90919f4a3155ac8b55a1b83f6e1ad74802e0` 中给普通 `get_weather` 加 `@beta_tool(defer_loading=True)`，定义普通函数 `search_available_tools`，由它返回 `{"type":"tool_reference","tool_name":...}`，并发送 `betas=["tool-search-tool-2025-10-19"]`。固定历史 URL：<https://github.com/anthropics/anthropic-sdk-python/blob/23cf45839f4e4beae970c83de1a13e0f24430318/examples/tools_runner_search_tool.py>；本轮 `gh api` 读取当前文件也得到同一 beta 与同一 custom-search 形态。

Anthropic 2025-11-24 官方工程文章把后续组合写成 `betas=["advanced-tool-use-2025-11-20"]`，同时展示 `tool_search_tool_regex_20251119` 与 `defer_loading:true`；这个 beta 同时覆盖 Tool Search、Programmatic Tool Calling、Tool Use Examples。来源：<https://www.anthropic.com/engineering/advanced-tool-use>。

因此字段并非只有一个：

- 所有 tool-search 形态都可能在普通工具定义上增加 `defer_loading:true`；未加或显式 false 的工具预加载。
- 自定义搜索会有一个普通 client tool，并在后续 `tool_result.content[]` 中返回 `tool_reference`；它不要求 `tools[]` 中出现 `_20251119` typed server tool。
- 托管 regex/BM25 搜索会在 `tools[]` 中增加 `type: tool_search_tool_regex_20251119` 或 `tool_search_tool_bm25_20251119`。

### 2.2 Claude Code 2.1.241 实际构造

`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:71246-71250` 同时登记两个同属 `tool_search` 的 beta：`advanced-tool-use-2025-11-20` 与 `tool-search-tool-2025-10-19`。`:73655-73659` 按 provider 选择：Vertex、Bedrock、Mantle、Gateway，以及禁用 experimental betas 的条件走旧 `2025-10-19`；其它条件走 `advanced-tool-use-2025-11-20`。`:428845-428869` 在 tool search 确实启用且存在 deferred tools 时把选中的 beta 加入请求，并把 deferred 判定传给 tool schema 构造器。

`app.pretty.js:427734-427758` 构造每个普通 tool 的 wire 对象，字段为 `name`、`description`、`input_schema`，并在 `deferLoading` 为真时增加 `defer_loading:true`。`:333714-333728` 定义普通 client-executed `ToolSearch`；`:333830-333848` 把其结果映射为标准 `tool_result`，命中时 content 是 `tool_reference` 数组。`:428858-428871` 保留 `ToolSearch` 本身而对候选工具 deferred；`:428143-428150` 还可能插入一个 non-callable deferred placeholder 维持 deferred-loading 形态。

这段运行时代码没有构造 `type: tool_search_tool_regex_20251119`。对 2.1.241 抽取文件的精确字符串搜索只在内嵌的 API skill 文档大字符串中命中该 type，而运行时搜索实现是上面的普通 `ToolSearch`。所以用户这次看到旧 beta，最贴近的 Claude Code body 形态是“普通 `ToolSearch`＋若干 `defer_loading:true` tools”，不是必然存在 server tool type。仅凭错误日志无法断言那一次 body 实际有哪些 tools；本代理不记录请求 body 的原始 wire bytes。

**结论 TS-02。读到的事实：**官方契约和客户端源码都直接给出了字段；Claude Code 当前抽取版本走 custom/client-side 形态。**我的推断：**另一台机器的该次请求很可能由 gateway 分支选出旧 beta，但客户端版本和 provider 分类未随日志提供，所以“为什么选中该分支”只是高置信推断。分量：字段契约可据以行动；对另一台机器分支归因仅为倾向，需它的 Claude Code 版本／环境才能定死。

## 3．GHC 上游支持什么

### 3.1 同一 enterprise endpoint 的保存实测

项目现有探针 `exp/260824-beta-and-cache-control-probe/probe.py:42-46,84-100,230-277` 用本机 GitHub token 换取 Copilot token，并采用 token 返回的 `endpoints.api`，实际打印为 `https://api.enterprise.githubcopilot.com`；请求模型为 `claude-opus-5`。`:51-67` 列出逐个测试的 beta，`:185-215` 定义 tool-search body 用例。补充对照 `probe_controls.py:49-72,86-109` 使用同一认证／endpoint 获取方式。

保存的原始输出给出以下结果：

```text
exp/260824-beta-and-cache-control-probe/raw/run-main.txt:25-27
[400] B-tool-search-tool-2025-10-19: unsupported beta header(s): tool-search-tool-2025-10-19
[OK ] B-tool-search-tool-2025-11-19:
[OK ] B-advanced-tool-use-2025-11-20:
```

对应的完整请求与 response 在 `exp/260824-beta-and-cache-control-probe/raw/results.json:523-572`：`:524-538` 是 `2025-10-19` 的 400，`:541-555` 是 `2025-11-19` 的 200，`:558-572` 是 `advanced-tool-use-2025-11-20` 的 200。这三格 body 都不使用 beta 特有字段，隔离的是网关对 header token 的接受情况。

这不是只凭文件表格转述。本轮解析保存结果并打印目标用例，输出为：

```text
C0-control-plain status=200
T1-defer-loading-no-beta status=400 At least one tool must have defer_loading=false. All tools cannot be deferred.
T2-tool-search-tool-no-beta status=200
T3-tool-search-tool-with-1119-beta status=200
T4-defer-loading-with-1019-beta status=400 unsupported beta header(s): tool-search-tool-2025-10-19
B-tool-search-tool-2025-10-19 status=400 unsupported beta header(s): tool-search-tool-2025-10-19
B-tool-search-tool-2025-11-19 status=200
B-advanced-tool-use-2025-11-20 status=200
```

### 3.2 官方 Copilot 实现与生产录制旁证

官方 VS Code Copilot Chat 源码 `src/platform/endpoint/node/chatEndpoint.ts:193-210` 在 tool search 启用时发送 `advanced-tool-use-2025-11-20`。`src/platform/endpoint/node/messagesApi.ts:111-142` 给普通工具添加 `defer_loading:true`，并在 server-side 模式添加搜索 tool；常量在 `src/platform/networking/common/anthropic.ts:72-84`，type 为 `tool_search_tool_regex_20251119`。其 Claude Code passthrough server 明写 CAPI beta 白名单为 `interleaved-thinking`、`context-management`、`advanced-tool-use`，见 `src/extension/chatSessions/claude/node/claudeLanguageModelServer.ts:32-40`；过滤按前缀执行，见 `:404-418`，测试锁住 `advanced-tool-use-2025-11-20`，见 `src/extension/chatSessions/claude/node/test/extractSessionId.spec.ts:53-74`。这里没有 `tool-search-tool` 前缀。

另一个参考实现 `/home/xp/src/refs/caozhiyuan-copilot-api/copilot-api/src/services/copilot/create-messages.ts:26-32` 的 allowlist 同样只收 `advanced-tool-use-2025-11-20`；`:41-55` 会过滤其它 client beta；`:128-144` 将过滤后 header 与 payload 发往 GHC。它是独立旁证，不是支持矩阵的权威。

本轮还从只读 history DB `/home/xp/.local/share/copilot-api/history-v3-20260818-044224.db` 重建了一条既有成功请求的 `payload:2` tools 序列，命令输出为：

```text
operation_id= req_1787028163651_1
model= claude-opus-5
responseSuccess= True
anthropic-beta= ...,advanced-tool-use-2025-11-20
tools_count= 32
typed_tools= [('tool_search_tool_regex', 'tool_search_tool_regex_20251119', False)]
defer_loading_counts= {'True': 13, 'False': 1}
```

这里的 `False:1` 只统计显式 false；其它普通工具可缺省该字段。该记录证明这种 header＋body 组合实际成功过，但不单独证明每个字段都是成功原因。权威实验是上面的对照探针。

`docs/.human-controlled/ghc-api.md:21-29` 只规定 GHC 暴露哪些 direct endpoint，其中 `:25` 是 `/v1/messages` 和 `/v1/messages/count_tokens`；对该文件搜索 `beta|tool.search|defer_loading|anthropic-beta` 得 `rg_exit=1`。所以这份人写文档没有声称任何 beta 支持清单，不能拿它补出一张名单。

### 3.3 日期戳应如何理解

读到的事实是三套不同标识：旧 custom tool-reference beta `tool-search-tool-2025-10-19`；后来的 tool type `tool_search_tool_regex_20251119`；以及 Anthropic 2025-11-24 发布的组合 beta `advanced-tool-use-2025-11-20`。此外 GHC 网关实测还接受 `tool-search-tool-2025-11-19`。因此不能把 `_20251119` 与 header `2025-10-19` 当作“同一日期的两种拼法”。

**结论 TS-03。读到的事实：**本次 enterprise GHC 网关对 token 名称做精确词汇判断，明确拒绝 10 月 19 日版，接受 11 月 19 日版和 `advanced-tool-use`；官方 Copilot 自己发送后者。**我的推断：**`2025-11-19` 是 `_20251119` tool type 对应的后续 feature token／兼容 token，这一语义对应关系未在当前官方文档中明说；能据以行动的是“哪几个 token 实测收／拒”，不是该命名历史的猜测。分量：接受矩阵可据以行动；命名沿革仅为倾向。

## 4．只剥 beta 后会不会二次 400

### 4.1 直接对照结果

`exp/260824-beta-and-cache-control-probe/raw/run-controls.txt:1-5` 是最直接的 A/B：

```text
[OK ] D0-control-two-plain-tools:
[OK ] D1-defer-loading-mixed-no-beta:
[400] D2-defer-loading-mixed-with-1019-beta: unsupported beta header(s): tool-search-tool-2025-10-19
[OK ] E1-accepted-beta-set-together:
[400] E2-accepted-set-plus-1019: unsupported beta header(s): tool-search-tool-2025-10-19
```

D1 与 D2 的 body 完全相同，定义见 `probe_controls.py:50-60`：一个普通 tool 为 `defer_loading:true`，另一个为 false，唯一变量是旧 beta header。因此对该 body，剥掉旧 beta 后不是“第二个 400”，而是从 400 变为 200。

server tool 候选也有直接结果。`probe.py:190-208` 构造 `tool_search_tool_regex_20251119`＋一个 deferred 普通 tool；`raw/run-main.txt:13-14` 显示不带 beta 的 T2 与带 `tool-search-tool-2025-11-19` 的 T3 都是 200。`raw/results.json:267-336` 保留了完整 body 与 200 response。

T1 的 400 不能被误读成字段未知。`probe.py:185-188` 的 T1 只有一个 tool 且把它 deferred；`raw/results.json:235-264` 的错误明确是 `At least one tool must have defer_loading=false. All tools cannot be deferred.`。这说明 GHC 识别并执行了 `defer_loading` 的语义规则。Claude Code 自身又明确不 defer `ToolSearch`，见 2.1.241 `app.pretty.js:121173` 的名称、`:152363-152376` 对搜索 tool 返回 false 的 deferred predicate，以及 `:428858-428871` 的保留／序列化流程，所以正常 custom-search 请求不会是 T1 的“所有工具都 deferred”形状。

### 4.2 边界

上述结论只覆盖用户问到的“同一请求中有 `defer_loading` 或 `_20251119` server tool，剥 header 后是否立即再 400”。它对 enterprise endpoint＋`claude-opus-5`＋非流式 body 是实测，不是推断。

尚未单独实测 custom `ToolSearch` 的完整两轮：第一轮模型调用普通 `ToolSearch`，客户端执行后，第二轮把 `tool_result.content[]` 中的 `tool_reference` 发回，而 header 已被 proxy 剥掉。当前 Anthropic 官方文档把 custom tool search 写在无需 beta 的同一页面，倾向于说明它已不再依赖 header；但官方 Python SDK 当前示例仍发送旧 beta，所以不能把“第一轮 body 200”扩大成“多轮生命周期必然全部 200”。这就是 TS-06，分量仅为倾向需更多样本。

**结论 TS-04。读到的事实：**对用户点名的两个字段形态，现有对照实测已经排除紧接着的第二个 schema 400；唯一额外约束是不可把全部 tools 都 deferred。**我的推断：无。**分量：可据以行动，适用范围如上。

## 5．本项目 direct path 会不会改写 `tools`

### 5.1 实际调用链

`src/app/server/inbound.py:55-68` 对 parsed body 做 `deepcopy`，原样放入 `RequestContext.payload`。`src/app/pipeline/driver.py:98-115` 先做 path header policy、beta token strip 与 `fix_anthropic_request()`；`src/app/pipeline/anthropic_request_hook.py:220-265` 的 fixup 只归一化 `context_management`、修复历史消息的 tool-use/tool-result 配对、处理 thinking blocks，不读也不写顶层 `tools`。

`src/app/pipeline/driver.py:142-154` 只有在 `route.translation_required` 为真时才调用 translator；用户已确认本次 direct path 为 false，因此 Anthropic→Responses 的 tool conversion 不参与。

每次 attempt 仍会跑 builtin subscribers。`src/app/pipeline/subscribers/__init__.py:60-96` 注册 `adapt_server_tools` 等处理；其中和 direct Anthropic `tools` 有关的是 `server_tools.py`。它的 `_REJECTED_TYPE_PREFIXES` 只有 `web_search` 与 `web_fetch`，见 `src/app/pipeline/subscribers/server_tools.py:32-40`；`:39` 还逐字说明 `tool_search_` 被刻意排除。`:198-232` 遇到前两类时抛 `WebSearchNotExecutable`，并不把 `kept` 写回 payload；`:235-255` 只对 Anthropic target 执行这一检查，并可能改写历史消息中的 web search 结果，不改 `tools` 数组。

其它相关 builtin `hosted_web_search` 在 `src/app/pipeline/subscribers/hosted_web_search.py:94-105` 明确只对 `OPENAI_RESPONSES` target 生效，direct Anthropic path 立即返回。全 active pipeline 的工具处理搜索输出只找到这些点；不存在 `preprocess_tools()` 调用，且当前树中也不存在旧的 `src/app/anthropic/message_tools.py`。

最后，`src/app/pipeline/direct_driver/base.py:136-151` 在 `attempt.prepare` 后从 `context.payload` 复制 attempt payload；`:236-253` 将它交给 provider。`src/app/model_provider/github_copilot.py:141-162` 对 Anthropic endpoint 直接调用 `send_anthropic_messages`；`src/app/model_provider/ghc_client/client.py:84-98,130-144` 又把 `dict(payload)` 作为 raw Anthropic SDK `post` body 发出。

**结论 TS-05。读到的事实：**direct path 没有 tool-search-specific 的 tools 清洗，也不会注入搜索 tool、添加／删除 `defer_loading` 或把旧 beta 对应的 body 改成另一版；`tool_search_*` 会原样到达上游。存在的 server-tool guard 只拒绝 web search/fetch，不是 tool search rewrite。**我的推断：无。**分量：可据以行动。

## 6．对处置方向的含义

1. `settings.py` 的 `tool_search=True` 不能解决问题，也不会改变请求；它是未接线旧字段。
2. 把 `tool-search-tool-2025-10-19` 加入现有 `strip_anthropic_beta_flags`，配一个能命中 resolved model 的 regex，机械上可以挡住这次 400；但现有表的语义是“按模型剥 capability”，而实测问题是 enterprise Copilot 网关的 token 词汇表。把它永久塞进 per-model operator 表会混淆两个判据。这里仅陈述实现含义，不修改配置或 Spec。
3. 不需要为了防止紧接着的 body 400 而删除 `defer_loading` 或 `_20251119` server tool；这两类 body 已在相同 host/model 上无 beta 200。贸然删字段会关闭客户端本来要求的延迟工具加载。
4. 若要永久修复，最小行为是只移除网关明确拒绝的旧 token，并保留其它 beta 与 body。是否内置 gateway denylist、把旧 token改写成 `2025-11-19`／`advanced-tool-use`，或仍借用 per-model 配置，属于实现／Spec 决策；本报告没有替用户裁决。若要求保持 custom `tool_reference` 多轮行为，先补一组完整两轮实测再在“strip”和“rewrite”之间定案。

承重检查：前提“D1/T2 在同一 enterprise endpoint 和 `claude-opus-5` 无 beta 得到 200”支撑结论“无需连带删除 `defer_loading`／server tool”。若该前提为假，结论会反转，因此本报告以保存的请求 body、状态与 response 三者核验，而不只引用摘要。前提“旧 `AppSettings` 无 reader”支撑结论“不要改 `settings.py` 期待生效”；若为假，结论会改变，因此同时查了 attribute、mapping 与 loader 调用三种读法。

## 7．排除过的解释、死路与不相关来源

1. **排除“`settings.py:90` 已经把 tool search 打开”。** 字段存在不等于运行时读取；两种 reader 搜索均为 exit 1，旧 loader 自己也声明不服务生产路径。
2. **排除“只要把旧 beta 名换成与 type 同样的无连字符日期写法”。** header token 的实际接受项是 `tool-search-tool-2025-11-19`，不是 `tool-search-tool-20251119`；`_20251119` 是 JSON tool type suffix。探针按完整 token 测的是 10 月 19 日与 11 月 19 日两个不同版本。
3. **排除“GHC 完全不支持 tool search”。** T2、T3 的 body 200；另有成功历史请求带 `_20251119`、13 个 deferred tools 与 `advanced-tool-use`。
4. **排除“GHC 只接受 `_20251119`，因此普通 `defer_loading` 必须跟 server tool 一起出现”。** D1 只有两个普通 tools、无 beta、无 server tool，200。
5. **排除“剥掉 header 后 `defer_loading` 会作为 unknown field 被拒绝”。** D1 直接证伪。T1 的失败是 all-deferred 语义校验，不是 unknown field。
6. **排除“Claude Code 一定发送 `tool_search_tool_regex_20251119`”。** 2.1.241 运行时代码定义普通 `ToolSearch` 并返回 `tool_reference`；typed regex server tool 是 VS Code Copilot Chat 和前身的形态，不是该 Claude Code 实现的构造。
7. **排除“官方当前已完全废弃 `tool-search-tool-2025-10-19`，所以任何服务都应拒绝”。** 官方 Python SDK 当前示例仍发送它；事实是 Copilot gateway 不接受它，不是该 token 在整个 Anthropic 生态中不存在。
8. **排除“`docs/.human-controlled/ghc-api.md` 给出了 GHC beta 白名单”。** 该文档只列 endpoint；相关关键词无命中。
9. **查过但不相关：CLIProxyAPIPlus。** `/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/gemini-cli/claude/gemini-cli_claude_request.go:145-160`、`internal/translator/gemini/claude/gemini_claude_request.go:171-193` 与 `internal/translator/codex/claude/codex_claude_request.go:245-270` 在跨协议转换时删除 `defer_loading`，但它们不是 GHC Anthropic direct path，也没有 beta 支持矩阵，不能回答本题。
10. **查过但不足以单独定案：caozhiyuan 参考实现。** 它对白名单的选择与官方 Copilot 一致，但它在 `create-messages.ts:140-144` 原样发送 payload，没有提供“旧 beta 被剥后 custom `tool_reference` 全生命周期”的实测。
11. **没有做新的 live call。** 本轮复用了同日已保存且包含请求、response、正控制和反例控制的探针资产；再次消耗真实上游没有增加鉴别力。没有改动 `src/`，没有 push。

## 8．我最没把握的三个判断

1. **另一台机器为何被 Claude Code 归入旧 beta 分支。** 观察到的 token 与 2.1.241 gateway／受限分支完全一致，但没有该机器的版本、环境或实际 provider classifier 输出。分量：仅为倾向需更多样本；不影响“网关拒绝该 token”的结论。
2. **custom `tool_reference` 第二轮在不带 beta 时是否被 GHC 接受。** 第一轮 `defer_loading` 与 server tool body 已实测，第二轮 custom result 未测；官方当前文档与 SDK 示例在是否仍发送 beta 上不一致。分量：仅为倾向需更多样本；若永久修复选择纯 strip 而非 rewrite，这是应补的唯一关键样本。
3. **`tool-search-tool-2025-11-19` 的正式命名地位。** GHC 实测接受，但当前 Anthropic页面重点使用 `_20251119` type 且不再展示该 header；能确定的是网关行为，不能从公开文档确定它是正式 beta、兼容别名还是 gateway 私有词汇。分量：仅存档，不用于选择修复。

## 9．执行本契约时遇到的摩擦

- WebSearch 后端对四个查询均返回 `unavailable`，因此官方材料改用 WebFetch、GitHub API 与本地官方 SDK／Claude Code 源码；没有把搜索失败伪装成“网上没有资料”。
- 项目无 `.codegraph/`，按项目规则没有自行建索引，改用精确 `rg` 与逐文件读取。
- `src/` 之外已有同日 probe 与报告由并行工作产生；本报告只读取其原始资产，没有覆盖或修改。

## Sources

- [Anthropic Tool search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [Anthropic：Introducing advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Anthropic Python SDK custom tool-search example，固定历史提交](https://github.com/anthropics/anthropic-sdk-python/blob/23cf45839f4e4beae970c83de1a13e0f24430318/examples/tools_runner_search_tool.py)

## 整体判定

五个指定问题均已回答。对当前已知故障，证据支持：真正的直接阻断是 Copilot gateway 不接受 `tool-search-tool-2025-10-19`；旧 `settings.py` 开关不生效；direct path 不改 tool-search body；移除该 token 后，用户点名的 `defer_loading` 与 `_20251119` body 不会立即产生第二个 400。唯一保留项是 custom `tool_reference` 的完整第二轮没有无 beta 实测。

## 交付声明

- delivery_complete: true
- completed_at: 2026-08-24
- finding_total: 6
- confirmed: 5
- likely: 0
- inconclusive: 1
- refuted: 0
