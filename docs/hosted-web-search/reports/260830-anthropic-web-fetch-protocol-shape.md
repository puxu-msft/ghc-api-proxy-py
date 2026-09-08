# Anthropic Messages `web_fetch` server tool 的线上协议形态（取证报告）

- 日期：2026-08-30
- 任务：查清 `web_fetch` 的声明形态与响应侧块对形态，精确到字段名与取值枚举；重点是**失败时的块形状与 `error_code` 完整枚举**
- 范围：只读调查，未改动 `src/`、`tests/` 任何文件
- **落盘位置说明**：本文原定写入 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260830-anthropic-web-fetch-protocol-shape.md`。本会话隔离在 worktree `260830-issue1-websearch-gate`，harness 守卫拒绝写主检出路径，且该 worktree 无 `.dev/`（`.dev` 按项目约定只存在于主工作树根）。故先落到 `/tmp`，请主会话搬运，见文末 §10。

## 0. 证据等级与来源清单

本报告用四级标注，从强到弱：

| 等级 | 含义 | 本次实际用到的来源 |
|---|---|---|
| `官方文档` | Anthropic 自己发布的文档正文 | <https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool>（2026-08-30 抓取；`docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-fetch-tool` 301 跳到此处） |
| `官方 SDK 类型` | Stainless 从 Anthropic OpenAPI spec 生成的类型定义 | 本机 `anthropic` Python SDK `1.0.0`，`/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/anthropic/` |
| `第三方实现` | 参考项目的代码或记录 | `/home/xp/src/copilot-api-js/`、`/home/xp/src/refs/*` |
| `推断` | 由上面几级推出、未被任何来源逐字确认 | 逐条单独标注 |

**本次没有 `实测` 一级。** 本项目对 Anthropic 原生 `web_fetch` 的成功响应**零样本**——`.dev/docs/hosted-web-search/reports/260821-responses-websearch-citation-evidence.md:348` 自己记着「P-D `web_fetch` 工具的响应形态 · 本次未覆盖」。已有的唯一一手实测是**被拒**的 400（见 §6），不是块形态。

SDK 版本取自 `/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/anthropic/_version.py`：`__version__ = "1.0.0"`。

## 1. 声明形态（request `tools[]`）

### 1.1 `type` 的已知日期版本

`官方文档` + `官方 SDK 类型`（两者完全一致，四个版本都在 SDK 里各有一个 param 文件）：

| `type` | 能力 | SDK 文件 |
|---|---|---|
| `web_fetch_20250910` | 基础 fetch | `types/web_fetch_tool_20250910_param.py` |
| `web_fetch_20260209` | 加 dynamic filtering | `types/web_fetch_tool_20260209_param.py` |
| `web_fetch_20260309` | 再加 `use_cache`（cache bypass） | `types/web_fetch_tool_20260309_param.py` |
| `web_fetch_20260318` | 再加 `response_inclusion`（最新） | `types/web_fetch_tool_20260318_param.py` |

文档原文：「The latest web fetch tool version (`web_fetch_20260318`) … The previous versions (`web_fetch_20260309` for dynamic filtering and cache bypass, `web_fetch_20260209` for dynamic filtering only, `web_fetch_20250910` for basic fetch) remain available.」

**我们代码里见过的 `web_fetch_20250910` 是最老的一个，不是唯一一个。** 本项目 `src/app/pipeline/subscribers/server_tools.py:40` 用的是前缀匹配 `("web_search", "web_fetch")`，这一点对四个版本都成立，不受版本增补影响——这是前缀判据相对枚举判据的一个实际收益。

### 1.2 必填与选填字段

`官方 SDK 类型`（`types/web_fetch_tool_20250910_param.py`，逐字）：

- **必填**：`name: Required[Literal["web_fetch"]]`、`type: Required[Literal["web_fetch_20250910"]]`
- **选填**：
  - `allowed_domains: Optional[SequenceNotStr[str]]`
  - `blocked_domains: Optional[SequenceNotStr[str]]`
  - `citations: Optional[CitationsConfigParam]`（`CitationsConfig` 只有一个字段 `enabled: bool`；文档明说 web fetch 的 citations **默认关闭**，与 web search 的「always enabled」不同）
  - `max_content_tokens: Optional[int]`
  - `max_uses: Optional[int]`
  - `cache_control: Optional[CacheControlEphemeralParam]`
  - `allowed_callers: List[Literal["direct", "code_execution_20250825", "code_execution_20260120", "code_execution_20260521"]]`
  - `defer_loading: bool`
  - `strict: bool`

`web_fetch_20260309` 与 `web_fetch_20260318` 额外有 `use_cache: bool`（默认 `true`）；`web_fetch_20260318` 再额外有 `response_inclusion: Literal["full", "excluded"]`（默认 `"full"`）。`web_fetch_20260209` 的字段集与 `20250910` 逐字相同（dynamic filtering 不新增声明字段）。

**注意：`allowed_callers`、`defer_loading`、`strict`、`cache_control` 这四个在文档的「Tool definition」JSON 里没有列出**，只在 SDK 类型里。文档那段只给了 `max_uses` / `allowed_domains` / `blocked_domains` / `citations` / `max_content_tokens` 五个。所以问题里点名的五个字段**全部存在**，且不止这五个。

文档补充的约束（`官方文档`）：`blocked_domains` **不能与** `allowed_domains` 同时用（原文注释 "cannot be combined with allowed_domains"）；`max_content_tokens` 是近似限制且**不适用于 PDF 等二进制内容**；`max_uses` 无默认值，失败的 fetch 也计入。

## 2. 响应侧块对形态（本次重点）

### 2.1 `server_tool_use.name`

`官方 SDK 类型`（`types/server_tool_use_block.py:27-35`，逐字）：

```python
    name: Literal[
        "web_search",
        "web_fetch",
        "code_execution",
        "bash_code_execution",
        "text_editor_code_execution",
        "tool_search_tool_regex",
        "tool_search_tool_bm25",
    ]
```

即 `name` 取 **`"web_fetch"`**（不带日期后缀——日期只在声明的 `type` 上）。`官方文档` 的响应示例逐字一致。

### 2.2 `server_tool_use.input`

`官方文档`（响应示例逐字）：

```json
{
  "type": "server_tool_use",
  "id": "srvtoolu_01234567890abcdef",
  "name": "web_fetch",
  "input": {
    "url": "https://example.com/article"
  }
}
```

所以 **是 `{"url": ...}`**，对应 web search 的 `{"query": ...}`——证据等级 `官方文档`。

**但要点名一处取证边界**：`官方 SDK 类型` 把 `input` 定成 `Dict[str, object]`（`server_tool_use_block.py:25`），**没有** 任何 `web_fetch` 专用的 input schema 类型。我在 SDK 的 `types/__init__.py` 里逐条核过所有 `WebFetch*` 导出（11 条，全是 tool param、result block、error block、error code），确认不存在 input 模型。所以：「`input` 里只有 `url`、不会有别的键」这一条**没有权威来源支持**，只有文档的一个示例。dynamic filtering（`web_fetch_20260209+`）是否会让 `input` 多出字段——**查不到，不要猜**。本项目 `src/app/pipeline/server_tool_text.py:16` 现在读 `query` 与 `url` 两个键、读不到就退化，这个写法对未知附加键是安全的。

### 2.3 结果块的 `type`

`官方 SDK 类型`（`types/web_fetch_tool_result_block.py:23-31`，逐字）：

```python
class WebFetchToolResultBlock(BaseModel):
    caller: Optional[Caller] = None
    """Tool invocation directly from the model."""

    content: Content

    tool_use_id: str

    type: Literal["web_fetch_tool_result"]
```

即 **`web_fetch_tool_result`**，与 web search 的 `web_search_tool_result` 同构。`官方文档` 一致。

`caller` 是可选字段，取 `DirectCaller` / `ServerToolCaller`（`{"type": "code_execution_20250825", "tool_id": ...}`）/ `ServerToolCaller20260120` 之一——dynamic filtering 场景下 fetch 由 code execution 发起时会带它。`web_search_tool_result` 有同名同型的字段，这不是 web_fetch 独有的。

### 2.4 成功时 `content` 的形状

**这是与 web search 差别最大的一处：不是列表，是单个对象。**

`官方 SDK 类型`：

```python
# types/web_fetch_tool_result_block.py:20
Content: TypeAlias = Union[WebFetchToolResultErrorBlock, WebFetchBlock]
```

对照 web search（`types/web_search_tool_result_block_content.py:11`）：

```python
WebSearchToolResultBlockContent: TypeAlias = Union[WebSearchToolResultError, List[WebSearchResultBlock]]
```

——**web search 成功是 `List[...]`，web fetch 成功是单个 `WebFetchBlock`。** 两族的失败侧都是单个对象。所以「单对象 ⇒ 失败」这个判据在 web_fetch 上是错的；本项目 `src/app/pipeline/subscribers/server_tools.py:91` 的注释已经逐字记下了这个坑（「A single object is not evidence of failure: a successful `web_fetch_tool_result` carries one object too」），本报告与它一致，且现在有 SDK 类型作为独立佐证。

成功时的 `WebFetchBlock`（`types/web_fetch_block.py:12-21`，逐字）：

```python
class WebFetchBlock(BaseModel):
    content: DocumentBlock

    retrieved_at: Optional[str] = None
    """ISO 8601 timestamp when the content was retrieved"""

    type: Literal["web_fetch_result"]

    url: str
    """Fetched content URL"""
```

内层 `DocumentBlock`（`types/document_block.py`）：`type: Literal["document"]`、`source`、可选 `title: Optional[str]`、可选 `citations: Optional[CitationsConfig]`。`source` 是 `Base64PDFSource | PlainTextSource` 的判别联合（按 `type` 判别）：

- `PlainTextSource`：`{"type": "text", "media_type": "text/plain", "data": <正文>}`
- `Base64PDFSource`：`{"type": "base64", "media_type": "application/pdf", "data": <base64>}`

`官方文档` 的两个示例（HTML 与 PDF）与上述类型逐字吻合。**注意 `retrieved_at` 与 `title` 都是 Optional**——文档示例里有，但不保证一定出现；`.dev` 里已有一条「日志行上的缺席读不出来」的教训，这里同样适用。

完整的成功块对（`官方文档` 逐字）：

```json
{
  "type": "web_fetch_tool_result",
  "tool_use_id": "srvtoolu_01234567890abcdef",
  "content": {
    "type": "web_fetch_result",
    "url": "https://example.com/article",
    "content": {
      "type": "document",
      "source": {
        "type": "text",
        "media_type": "text/plain",
        "data": "Full text content of the article..."
      },
      "title": "Article Title",
      "citations": { "enabled": true }
    },
    "retrieved_at": "2025-08-25T10:30:00Z"
  }
}
```

### 2.5 失败时 `content` 的形状与 error 块的 `type`

`官方 SDK 类型`（`types/web_fetch_tool_result_error_block.py:11-14`，逐字）：

```python
class WebFetchToolResultErrorBlock(BaseModel):
    error_code: WebFetchToolResultErrorCode

    type: Literal["web_fetch_tool_result_error"]
```

**只有两个字段，没有 `url`、没有 `message`。** 与 web search 的 `WebSearchToolResultError`（`types/web_search_tool_result_error.py:11-14`）逐字同构，只是 `error_code` 的枚举不同。

`官方文档` 给的完整失败块对（逐字）：

```json
{
  "type": "web_fetch_tool_result",
  "tool_use_id": "srvtoolu_a93jad",
  "content": {
    "type": "web_fetch_tool_result_error",
    "error_code": "url_not_accessible"
  }
}
```

即：与 web search 的失败形态**结构完全一致**——外层块 `type` 是 `<family>_tool_result`，`content` 是**单个**对象而非列表，该对象 `type` 是 `<family>_tool_result_error`，携带一个 `error_code` 字符串。差别只在两个字符串常量与枚举取值。

### 2.6 `error_code` 完整枚举

`官方 SDK 类型`（`types/web_fetch_tool_result_error_code.py:7-17`，逐字，**9 个**）：

```python
WebFetchToolResultErrorCode: TypeAlias = Literal[
    "invalid_tool_input",
    "url_too_long",
    "url_not_allowed",
    "url_not_in_prior_context",
    "url_not_accessible",
    "unsupported_content_type",
    "too_many_requests",
    "max_uses_exceeded",
    "unavailable",
]
```

`types/beta/beta_web_fetch_tool_result_error_code.py` 的枚举**与之逐字相同**（我逐条比对过，无增无减）——即 beta 通道没有额外的 code。

`官方文档` 的枚举列表与 SDK **完全一致**（同样 9 个、同序），并给出了各自含义：

| `error_code` | 文档给的含义 |
|---|---|
| `invalid_tool_input` | 工具输入无效，例如 URL 畸形或不是 HTTP(S) scheme |
| `url_too_long` | URL 超长（文档写 250 字符上限） |
| `url_not_allowed` | 被域名过滤规则（含组织设置）或 Anthropic 侧限制（私有地址、`robots.txt`）拦下 |
| `url_not_in_prior_context` | URL 未在此前对话上下文中出现过（见 §5 的 URL validation） |
| `url_not_accessible` | 抓取失败（HTTP 错误） |
| `unsupported_content_type` | 内容类型不支持（仅支持 text、HTML、PDF） |
| `too_many_requests` | 触发限流 |
| `max_uses_exceeded` | 超出 `max_uses` |
| `unavailable` | 内部错误 |

**与 web search 枚举的差集**（`官方 SDK 类型`，`types/web_search_tool_result_error_code.py:7-9` 是 `invalid_tool_input` / `unavailable` / `max_uses_exceeded` / `too_many_requests` / `query_too_long` / `request_too_large`，共 6 个）：

- **两族共有（4 个）**：`invalid_tool_input`、`unavailable`、`max_uses_exceeded`、`too_many_requests`
- **仅 web search 有（2 个）**：`query_too_long`、`request_too_large`
- **仅 web fetch 有（5 个）**：`url_too_long`、`url_not_allowed`、`url_not_in_prior_context`、`url_not_accessible`、`unsupported_content_type`

回答问题里的具体猜测：`url_not_accessible` **在**（且正是文档示例用的那个），`url_too_long` **也在**。另外还有三个问题里没猜到的：`url_not_allowed`、`url_not_in_prior_context`、`unsupported_content_type`。而 web search 的 `query_too_long` 与 `request_too_large` **不在** web_fetch 枚举里。

**这条直接对应 `.dev` 里那条已付过代价的教训**：给枚举加成员会给每张以它为键的表造缺项。任何按 `web_search` 那 6 个 code 写死的映射表，遇到 web_fetch 的 5 个独有 code 会全部落空。判据应当读 `type` 结尾是否为 `_error`（本项目 `server_tools.py:98` 已经这么做了）或按族分表，而不是共用一张 code 表。

### 2.7 失败是否仍是 HTTP 200

**是。** `官方文档` 逐字：「When the web fetch tool encounters an error, the Claude API returns a 200 (success) response with the error represented in the response body. Claude sees the error result and continues the turn.」

与 web search 文档的「still returns a 200 (success) response」同义。证据等级 `官方文档`。

### 2.8 流式（SSE）下的块形态

`官方文档` 逐字给出：结果块是**在一个 `content_block_start` 里整块下发的**，不是分片：

```
event: content_block_start
data: {"type": "content_block_start", "index": 2, "content_block": {"type": "web_fetch_tool_result", "tool_use_id": "srvtoolu_xyz789", "content": {"type": "web_fetch_result", "url": "https://example.com/article", "content": {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": "Article content..."}}}}}
```

而 `server_tool_use` 的 `input` 走 `input_json_delta` 分片（示例里是一整片 `{"url":"..."}`）。抓取期间流会**暂停**（文档写 "Pause while fetch executes"）——对本项目的保活守卫是个相关事实，但不在本次任务范围内，仅记录。

注意这个示例里的 `web_fetch_result` **没有** `retrieved_at`，正好印证 §2.4 说的「Optional 不保证出现」。

## 3. 请求侧回传（把结果块发回去）

`官方 SDK 类型`（`types/web_fetch_tool_result_block_param.py:22-33`）：`WebFetchToolResultBlockParam` 要求 `content`、`tool_use_id`、`type`，可选 `cache_control` 与 `caller`；`content` 同样是 `Union[WebFetchToolResultErrorBlockParam, WebFetchBlockParam]`。即历史消息里回传的形态与响应形态同构。这一点对本项目的历史块摊平逻辑（`hosted-web-search-spec.md` §5.4）是相关的。

## 4. `usage` 侧

`官方 SDK 类型`（`types/server_tool_usage.py:8-13`，逐字）：

```python
class ServerToolUsage(BaseModel):
    web_fetch_requests: int
    """The number of web fetch tool requests."""

    web_search_requests: int
    """The number of web search tool requests."""
```

两个字段**都不是 Optional**。本项目 `.dev/docs/delivery-keepalive/reports/260820-client-timeout-forensics.md:39` 记的实际载荷 `"server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}` 与之吻合（等级 `第三方实现`／本项目一手抓包）。文档也说 web fetch **不额外收费**，只按 token 计。

## 5. 一条影响可用性的行为约束（不是块形态，但会决定失败率）

`官方文档`：出于防数据外泄，**web_fetch 只能抓此前已在对话上下文中出现过的 URL**——用户消息里的、客户端工具结果里的、之前 web search／web fetch 结果里的。模型自己拼出来的 URL、以及来自容器类 server tool（Code Execution、Bash）的 URL **抓不了**，对应 `url_not_in_prior_context`。

## 6. 本机第一手证据（不是 Anthropic 协议形态，但必须区分开）

`第三方实现`／本项目一手实测：**GHC（`api.githubcopilot.com`）不支持原生 `web_fetch`。**

- `/home/xp/src/copilot-api-js/exp/server-tool-web-fetch-poc/README.md:123-132`：2026-07-12 用 individual 账号、`claude-sonnet-4.5`→`sonnet-5`，wire 上确认发出 `[{"type":"web_fetch_20250910","name":"web_fetch","max_uses":5}]`，上游回 **HTTP 400** `{"error":{"message":"rejected tool(s): web_fetch","code":"invalid_request_body"}}`。
- `/responses` 腿是**第三种措辞**：400 `Invalid value: 'web_fetch'`（`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:488`）。

所以：**本报告 §1–§5 描述的是 Anthropic 原生 Messages API 的形态，不是我们上游今天会返回的东西。** 我们的上游今天连声明都拒。要把这些形态用到代码里，前提是走自建执行（copilot-api-js PoC 里的「路线 B：自建双跳」），此时块对是**我们自己合成**的——那正是「手写替身编码了我们以为的上游行为」最容易发生的地方，本报告的价值就在于合成时对着官方 SDK 类型逐字对齐，而不是对着记忆。

## 7. 排除掉、认为不成立的可能性

逐条写下我查过并否掉的，以及为什么：

1. **「`web_fetch` 成功时 `content` 也是列表」——否。** 直接被 `types/web_fetch_tool_result_block.py:20` 的 `Union[WebFetchToolResultErrorBlock, WebFetchBlock]` 证伪（无 `List`），且与 web search 的 `Union[..., List[WebSearchResultBlock]]` 形成对照。本项目 `server_tools.py:91` 的注释独立说了同一件事。
2. **「error 块里带 `url` 或 `message`，可以据此知道哪个 URL 失败了」——否。** `WebFetchToolResultErrorBlock` 只有 `error_code` 与 `type` 两个字段。要知道是哪个 URL，只能靠 `tool_use_id` 回溯配对的 `server_tool_use.input.url`。这一点对渲染失败提示有直接影响。
3. **「web_fetch 复用 web search 的 error_code 枚举」——否。** 两个 Literal 别名各自独立，差集见 §2.6（共 4、各自独有 2 与 5）。
4. **「beta 通道有额外 error_code」——否。** `beta_web_fetch_tool_result_error_code.py` 与非 beta 版逐字相同。
5. **「`web_fetch_20250910` 是唯一的 type」——否。** 共四个版本，最新为 `web_fetch_20260318`（§1.1）。我们代码只见过最老的那个，纯属客户端选择，不是协议全集。
6. **「`server_tool_use.name` 带日期后缀（如 `web_fetch_20250910`）」——否。** `ServerToolUseBlock.name` 的 Literal 里是裸 `"web_fetch"`。
7. **「失败会以 HTTP 4xx/5xx 返回」——否，明确是 200**（§2.7），文档逐字。
8. **`/home/xp/src/refs/vscode-copilot-chat/` 里的 `web_fetch` 命中与本协议无关——已核实并排除。** 三处命中分别是：`copilotCLITools.ts:170` 与 `:1052` 的 `toolName: 'web_fetch'`，那是 Copilot CLI 的**客户端工具**命名，不是 Anthropic server tool 块；`claudeMessageDispatch.spec.ts:133` 只是 `usage.server_tool_use.web_fetch_requests: 0` 这个计数字段。**该仓库没有 `web_fetch_tool_result` 的任何定义或样本。**
9. **`/home/xp/src/refs/hooyao-copilot-bridge/` 的 `ContentBlock.cs` 不能作为来源——已核实并排除。** 它的注释（`:7-10`）逐字写着 server-side tool blocks「are not modeled」，`JsonDerivedType` 只登记了 `text` / `thinking` / `redacted_thinking` / `tool_use` 四种。是一份明确声明未建模的实现，不是证据。
10. **`/home/xp/src/refs/openclaude/src/entrypoints/sdk/coreTypes.generated.ts` 不含结果块——已核实并排除。** 对 `web_fetch_tool_result|WebFetchToolResult` 的搜索无命中（rg exit 1）。该文件里的 `WebFetchTool` 相关物是 Claude Code SDK 的客户端工具类型，与 Messages API 的 server tool 不是一回事。
11. **「`input` 里只有 `url` 一个键，可以据此写死解析」——不采纳，证据不足。** 文档示例只有 `url`，但 SDK 把 `input` 定成 `Dict[str, object]`，没有任何 schema。dynamic filtering 版本是否往 `input` 里加键，我**查不到**（§2.2）。按现在这样读 `url` 并对缺失退化，是对的；按「只有 url」写死断言，不是。

## 8. 明说查不到的

1. **`server_tool_use.input` 在 `web_fetch_20260209+`（dynamic filtering）下是否有附加字段。** 文档只在 `20250910` 语境给了 `{"url": ...}` 示例，SDK 无 input schema。**没有猜。**
2. **dynamic filtering 生效时，`web_fetch_tool_result` 是否嵌在 code execution 的结果里、块序如何。** 文档说 filtering 跑在 code execution tool 上、API 自动启用，并用 `caller` 字段与 `response_inclusion: "excluded"` 提到「nested `server_tool_use` and result block pair」，但**没有给出完整的嵌套响应示例**。我只能确认 `caller` 字段存在及其三种取值，**说不出**完整块序。
3. **任何一手实测的 Anthropic 原生 `web_fetch` 成功／失败响应。** 本项目零样本（`260821-responses-websearch-citation-evidence.md:348` 自己记着 P-D 未覆盖）。本报告全部块形态结论的最高等级是 `官方文档` + `官方 SDK 类型` 双向印证，**不是实测**。
4. **`url_too_long` 的 250 字符上限是否为硬阈值、是否随版本变化。** 只有文档一句话，无 SDK 常量、无实测。

## 9. 给调用方的一句话结论

失败块对是 `{"type": "web_fetch_tool_result", "tool_use_id": ..., "content": {"type": "web_fetch_tool_result_error", "error_code": <9 选 1>}}`，HTTP 仍是 200；成功时 `content` 是**单个** `web_fetch_result` 对象而非列表——这一点与 web search 相反，是最容易写错的一处。`error_code` 的 9 个取值与 web search 的 6 个只共享 4 个，不能共用一张表。

## 10. 落盘阻塞与搬运指令

Write 工具对目标路径返回：「This session is isolated in the worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate`. Edit the worktree copy of this file instead of the shared-checkout path.」而该 worktree 下**没有** `.dev/`（已 `ls` 确认），项目约定也要求 `.dev/` 只存在于主工作树根。用 Bash 绕过该守卫属于我不该自行授权的事，故未做。

请主会话（或有主树写权限的会话）执行：

```bash
cp /tmp/260830-anthropic-web-fetch-protocol-shape.md /home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260830-anthropic-web-fetch-protocol-shape.md
```

搬运后本文 §「落盘位置说明」与本节可一并删除。
