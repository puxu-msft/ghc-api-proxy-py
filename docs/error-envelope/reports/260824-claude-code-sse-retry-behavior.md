# Claude Code 2.1.241 重试行为考古报告

> 素材：`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js`（660402 行）。下文所有 `L<数字>` 均指该文件行号。
> 版本对照：`/home/xp/.claude/refs/claude-code-2.1.226/app.pretty.js`、`/home/xp/.claude/refs/claude-code-2.1.207/app.pretty.js`。
> 日期：2026-08-24。

## 0. 全局结构（先看这个，否则后面每条判据都会读错层）

Claude Code 的重试**分三层**，三层的判据互不相同，且**主查询路径上 SDK 那一层是被关掉的**：

| 层 | 位置 | 判据函数 | 何时生效 |
|---|---|---|---|
| A. Anthropic SDK 内建重试 | `L13407`–`L13500` | `shouldRetry` `L13467` | 只在 `maxRetries > 0` 的客户端上。主查询路径全部传 `maxRetries: 0`，故**在主路径上完全不生效** |
| B. Claude Code 自己的请求级重试驱动 `IOi` | `L273205`–`L273365` | `Ftw` `L273460` | 包住「建立请求 / 拿到响应头」这一段。HTTP 非 2xx、连接失败、超时走这里 |
| C. 流内错误处理（不经过 B） | `L429278`–`L429610`（catch 在 `L429487`） | 内联判据，见第 3 节 | 流已经建立、正在 `for await` 消费时发生的一切 |

关键结构证据：

- `L429164`：主流式路径构造 SDK 客户端时写死 `She({ maxRetries: 0, model: i.model, ... })`。
- `L429190`–`L429194`：`IOi` 的「尝试函数」只做到 `await ll.beta.messages.create({...stream:true}).withResponse()` 然后 `return jp.data`（返回 Stream 对象）。**流的消费不在 `IOi` 内部。**
- `L429256`–`L429258`：`do { _r = await Ot.next(); ... } while (!_r.done); Ge = _r.value;` —— 把 `IOi` 生成器跑完拿到 Stream。
- `L429280`：`for await (let wi of d0E(Ge, mn))` —— 真正消费流，在外层 `e: for (;;)`（`L429130`）的 `try` 里，catch 在 `L429487`。
- `L428607`：非流式回退路径 `Ffh` 同样是 `She({ maxRetries: 0, ... })` + `IOi`。

**因此：SSE 流内的 `event: error` 帧永远不经过 `Ftw`，也永远不经过 SDK 的 `shouldRetry`。** 这是本报告最重要的一条结构结论。把握程度：**代码字面直证，可据以行动**（三处调用点 + `return jp.data` + `for await` 的位置共同锁死）。

---

## 1. HTTP 层重试

### 1.1 SDK 的 `shouldRetry`（A 层）

`L13467`–`L13478`，字面原文：

```js
async shouldRetry(e, t4) {
  let r2 = this._authFlags(t4);
  if (e.status === 401 && this._authState.tokenCache && r2.usedTokenCache && !r2.didRefreshFor401) return r2.didRefreshFor401 = true, this._authState.tokenCache.invalidate(), true;
  let n4 = e.headers.get("x-should-retry");
  if (n4 === "true") return true;
  if (n4 === "false") return false;
  if (e.status === 408) return true;
  if (e.status === 409) return true;
  if (e.status === 429) return true;
  if (e.status >= 500) return true;
  return false;
}
```

判据：
- `x-should-retry: true` → 重试，**优先级高于一切 status**；`x-should-retry: false` → 不重试，**同样优先于 5xx**。
- 408 / 409 / 429 / >=500 → 重试。其余（400/401/403/404/413/422 等）→ 不重试。
- 401 且启用了 token cache 且本次用了缓存 token 且本请求还没为 401 刷新过 → 重试一次（顺带 invalidate 缓存）。

版本对照：2.1.226 的 `L12699`–`L12710` 与 2.1.207 的 `L12384`–`L12395` **逐行同形**，仅变量名不同。把握程度：**代码字面直证**。

### 1.2 连接层失败（A 层，`shouldRetry` 之外）

`L13417`–`L13425`：`fetch` 抛出（而非返回响应）时，只要还有剩余次数就直接 `retryRequest`，不查 `shouldRetry`。判定超时用 `OPe(p) || /timed? ?out/i.test(String(p) + cause)`（`L13420`）。耗尽后：超时抛 `ife`（APIConnectionTimeoutError），其余抛 `Pk`（APIConnectionError）。

### 1.3 `retry-after` / `retry-after-ms` 解析（A 层）

`L13479`–`L13496`，字面原文：

```js
async retryRequest(e, t4, r2, n4) {
  let o4, i = n4?.get("retry-after-ms");
  if (i) { let a = parseFloat(i); if (!Number.isNaN(a)) o4 = a; }
  let s = n4?.get("retry-after");
  if (s && !o4) {
    let a = parseFloat(s);
    if (!Number.isNaN(a)) o4 = a * 1e3;
    else o4 = Date.parse(s) - Date.now();
  }
  if (o4 === void 0) { let a = e.maxRetries ?? this.maxRetries; o4 = this.calculateDefaultRetryTimeoutMillis(t4, a); }
  return await i4e(o4), this.makeRequest(e, t4 - 1, r2);
}
```

- `retry-after-ms` 优先，直接当毫秒。
- `retry-after` 次之：先按秒解析；解析不出数字则按 HTTP-date 解析（`Date.parse(s) - Date.now()`）。
- 两者都无 → 走默认退避。
- **注意：SDK 这一层对 `retry-after` 的值不做上限钳制**（下节 B 层则有钳制）。

### 1.4 退避算法（A 层）

`L13497`–`L13500`：

```js
calculateDefaultRetryTimeoutMillis(e, t4) {
  let o4 = t4 - e, i = Math.min(0.5 * Math.pow(2, o4), 8), s = 1 - Math.random() * 0.25;
  return i * s * 1e3;
}
```

指数退避，基数 0.5s，倍数 2，**上限 8s**，抖动是**向下** 0～25%（`1 - random()*0.25`）。

### 1.5 默认 maxRetries 与 Claude Code 的覆盖

- SDK 默认：`L13260` `this.maxRetries = i.maxRetries ?? 2`。
- **Claude Code 在所有主路径上覆盖为 0**：`L429164`（流式主查询）、`L428607`（非流式回退）、`L171239`（配额探测）、`L372871`（模型校验）、`L428115`（models.retrieve）、`L376422` / `L376507` / `L376586` / `L460299` / `L461402`（Bedrock/Vertex/Mantle 探测）均为 `maxRetries: 0`。
- 例外：`L428523` `verify_api_key` 用 `maxRetries: 3`；`L429851`–`L429853` 的 side query 默认 `maxRetries = 2`，但实际传给客户端的是 `w = vMt(e.querySource) ? l : 0` —— 只有「主/用户可见」的 querySource（`vMt`，`L71252`：`undefined` 或 `agent:` 前缀或在 `JGb` 集合内）才保留 2，其余仍为 0。

### 1.6 Claude Code 自己的 HTTP 重试判据 `Ftw`（B 层）

`L273460`–`L273496`，这是主路径上**真正生效**的 HTTP 重试判据。按代码顺序：

| 顺序 | 条件（`L`） | 结果 |
|---|---|---|
| 1 | `q9p(e)`：gateway 模式下的 429（`L170969`：`Wrr() && e.status === 429`） | **false（不重试）** |
| 2 | 429 且是 credits/额度类（`error_code === "credits_required"`、或消息含 `usage credits are required` / `extra usage is required`），且 `anthropic-ratelimit-unified-overage-disabled-reason` 不是 `fetch_error` / `org_level_disabled_until`（`L273462`–`L273465`） | **false** |
| 3 | `Utw(e)`（`L273500`）：429 且消息含 `service_spend_limit_reached`，或 overage-disabled-reason 命中 `G9f`/`$9f` 集合，或消息含 `exceeded_limit` 且提取出的限额名在 `$9f` 中 | **false** |
| 4 | `Ont() && N9f(e)`（`L273467`）：`CLAUDE_CODE_RETRY_WATCHDOG` 开启且是 529/overloaded 或 429 | **true** |
| 5 | `leo(e)`（`L273175`）：`CLAUDE_CODE_REMOTE` 下的 401/403 | **true** |
| 6 | `e.message?.includes('"type":"overloaded_error"')`（`L273469`） | **true** |
| 7 | `B9f(e)`（`L273383`）：400 且消息匹配 `input length and \`max_tokens\` exceed context limit: (\d+) \+ (\d+) > (\d+)` | **true**（并在 `L273326`–`L273335` 下调 `max_tokens` 后重试） |
| 8 | OAuth/subscription 场景下的 401 或 `rWe(e)`（403 且消息含 `OAuth token has been revoked`）（`L273471`–`L273473`） | **true** |
| 9 | 407 且配了代理认证（`L273474`），顺带解析 `proxy-authenticate` | **true** |
| 10 | `x-should-retry === "true"` 且 `(!ds() \|\| bjr() \|\| M9f(e))`（`L273475`–`L273476`） | **true** |
| 11 | `x-should-retry === "false"`（`L273477`–`L273480`） | **false** |
| 12 | `e instanceof Pk`（连接错误，`L273481`–`L273487`） | **true**，除非 cause code 在证书错误集合 `Ayi` 中、或是 `BedrockUnexpectedContentType` / `TestEgressBlocked` |
| 13 | `!e.status`（`L273488`） | **false** |
| 14 | 408 / 409（`L273489`–`L273490`） | **true** |
| 15 | 401（`L273491`） | **true**（顺带 `mjr()`） |
| 16 | 429（`L273493`）：`return !ds() \|\| bjr() \|\| M9f(e)` | 条件性 |
| 17 | `>= 500`（`L273494`） | **true** |
| 18 | 其余 | **false** |

其中 `ds()`（`L90788`）= 已 OAuth 登录且 scope 命中（claude.ai 订阅态）；`bjr()`（`L90863`）= enterprise；`M9f(e)`（`L273497`）= 429 且**没有** `anthropic-ratelimit-unified-representative-claim` / `-overage-status` / `-overage-disabled-reason` 这几个 header。即：**订阅用户遇到「带统一限流 header 的 429」（真·用量上限）不重试；API key / enterprise 用户的 429 一律重试。**

第 11 行有一处值得记下的字面细节（`L273477`–`L273480`）：

```js
if (t4 === "false") {
  let r2 = e.status !== void 0 && e.status >= 500;
  return false;
}
```

`r2` 计算后未被使用，函数无条件 `return false`。也就是说 **`x-should-retry: false` 会一并压掉 5xx 的重试**，和 SDK 层一致。把握程度：**代码字面直证**。

### 1.7 B 层的退避与次数

- 次数上限 `Xpl()`（`L273508`–`L273517`）：`CLAUDE_CODE_MAX_RETRIES` 若为有效非负数则采用，但 **> 15 时钳制到 15**（`qpl = 15`，`L273539`）除非开了 watchdog；未设置时默认 **10**（`btw = 10`），watchdog 模式下 **300**（`vtw = 300`）。`jtw`（`L273519`）= `options.maxRetries ?? Xpl()`。
- 退避 `CZe(e, t4, r2 = 32e3)`（`L75742`–`L75749`）：`n4 = min(500 * 2^(attempt-1), 32000)`，`o4 = round(n4 + random()*0.25*n4)` —— 指数退避、**向上**抖动 0～25%、上限 **32s**。若传了 `retry-after`（`F9f`，`L273380` 从 header 取），取 `max(retryAfterSec*1000, o4)`。
- `L273340`：非 watchdog 模式下若算出的延迟 `> Ctw = 60000`，直接抛 `wG`，遥测 `tengu_api_retry_after_too_long`。**即：`retry-after` 超过 60 秒 → 放弃，不等。**
- watchdog 模式（`Ont()`，`L273168`：`CLAUDE_CODE_RETRY_WATCHDOG`）下（`L273338`）：429 优先用 `Vtw(e)`（`L273530`，读 `anthropic-ratelimit-unified-reset` 绝对时间戳，上限 `O9f = 21600000` = 6h），否则 `min(CZe(l, retryAfter, 300000), 21600000)`，长等待按 `Itw = 30000` 分片并周期性刷新 UI（`L273345`–`L273352`）。

---

## 2. SSE 流内 `event: error` 帧

### 2.1 帧怎么变成异常

SDK 的 SSE 解码器 `L9326`–`L9358`，关键三行（`L9344`–`L9348`）：

```js
if (a.event === "ping") continue;
if (a.event === "error") {
  let l = iIn(a.data) ?? a.data, c = l?.error?.type;
  throw new $s(void 0, l, void 0, e.headers, c);
}
```

`$s` = `APIError`（`L8351`–`L8375`）。构造签名 `(status, error, message, headers, type)`，所以流内 error 帧产生的异常：

- **`status === undefined`**（第一个参数是 `void 0`）。
- `error` = 解析后的整个 payload（`{"type":"error","error":{...}}`）。
- `headers` = **HTTP 响应头**（那个 200 响应的头），所以 `x-should-retry` 理论上可读。
- `type` = `payload.error.type`，即 `overloaded_error` / `api_error` / … 原值。
- `message` 由 `makeMessage`（`L8356`–`L8362`）生成：payload 没有顶层 `message` 字段，于是走 `JSON.stringify(t4)`，得到形如 `{"type":"error","error":{"type":"overloaded_error","message":"..."}}` 的完整 JSON 串。

**这解释了为什么全代码库到处用 `e.message?.includes('"type":"overloaded_error"')` 这种字面子串匹配**——它匹配的正是 `JSON.stringify` 出来的、无空格的紧凑形式。若上游把 payload 序列化成 `{"type": "overloaded_error"}`（带空格），Claude Code 这些判据会**全部失配**。把握程度：**代码字面直证**（`L8357` + `L9346` + `L155911`/`L273469`/`L415455` 三处使用点）。

> **更正（主会话补，2026-08-24）**：上一段最后一句「带空格会全部失配」**不成立**，它与本节自己的第 171 行矛盾。`L9346` 是 `iIn(a.data) ?? a.data`，而 `iIn`（`L8432`）就是包了 try/catch 的 `JSON.parse`。所以只要 `data` 是合法 JSON，传给 `makeMessage` 的 `t4` 就是**已解析的对象**，再由 `JSON.stringify` 重新序列化成紧凑形式——**上游线上字节怎么排版、有没有空格，在匹配之前就已经被归一化掉了，不影响判定**。
>
> 真正会让这条判据失配的是另外两种情况，都与信封**形状**有关，与空格无关：
>
> 1. **扁平信封**。`makeMessage`（`L8357`）第一个分支是 `t4?.message ? …`。若 payload 写成扁平的 `{"type":"overloaded_error","message":"Overloaded"}`，顶层 `message` 存在且是字符串，于是 `n4` 直接取 `"Overloaded"`，**整个 JSON 串根本没被拼进 message**，子串匹配失败 → 不重试。必须用嵌套信封 `{"type":"error","error":{"type":"overloaded_error",…}}`（顶层无 `message`），才会走到 `JSON.stringify(t4)` 分支。附带一提，扁平信封同时让 `L9346` 的 `c = l?.error?.type` 取到 `undefined`，`APIError.type` 变成 `null`，`L429516` 那条 `ll.type === "api_error"` 的 partial 定格路径也一并失效。
> 2. **`data` 不是合法 JSON**。此时 `iIn` 返回 `undefined`，`l` 回落成原始字符串；字符串没有 `.message`，于是走 `JSON.stringify(字符串)`，内层引号被转义成 `\"type\":\"overloaded_error\"`，同样失配。
>
> 把握程度：**代码字面直证**（`L8432`–`L8438` 的 `iIn` 函数体 + `L8357` 的 `makeMessage` 三元分支 + `L9346` 的调用点）。
>
> **PoC 实测**：把 `iIn`、`makeMessage`、`L9346` 的构造逻辑原样抄进 `260824-cc-sse-retry-envelope-probe.mjs`（与本报告同目录，`node` 直接跑），七种信封形状的判定结果：
>
> | 信封形状 | 是否重试 | `APIError.type` | `message` 实际取值 |
> |---|---|---|---|
> | A 嵌套，紧凑无空格 | **重试** | `overloaded_error` | 完整 JSON 串 |
> | B 嵌套，冒号逗号后带空格 | **重试** | `overloaded_error` | 完整 JSON 串（已归一化） |
> | C 嵌套，`indent=2` 缩进换行 | **重试** | `overloaded_error` | 完整 JSON 串（已归一化） |
> | D 扁平 `{"type":"overloaded_error","message":…}` | **不重试** | `null` | `"Overloaded"`（只剩 message） |
> | E 扁平且无 `message` 字段 | 重试 | `null` | `{"type":"overloaded_error"}` |
> | F `data` 非法 JSON | **不重试** | `null` | 整串被转义 |
> | G 嵌套 `rate_limit_error` | **不重试** | `rate_limit_error` | 完整 JSON 串（不含目标子串） |
>
> A/B/C 三行是对「空格会失配」那句话的直接证伪。D 行是真正的坑。E 行虽然重试，但 `type` 为 `null`，会连带打瘸 `L429516` 的 partial 定格路径，不应依赖。

另有一条容易忽略的旁路（`L9339`）：SDK 只对白名单里的 `event:` 名做 JSON 解析并 yield。名字不在白名单、也不是 `ping`/`error` 的事件，**被静默丢弃**，既不 yield 也不报错。

### 2.2 各 `error.type` 值的实际参与情况

穷举 grep 结果（排除 bundle 内嵌的 `claude-api` skill 文档字符串，那些在 L583xxx–L648xxx 段）：

| `error.type` | 是否参与重试判定 | 字面证据 |
|---|---|---|
| `overloaded_error` | **是**。`Qle(e)`（`L155909`–`L155912`）：`e.status === 529 \|\| e.message?.includes('"type":"overloaded_error"')`。被 `Ftw`（`L273469`）、`IOi`（`L273276`/`L273295`/`L273297`）、流内 catch（`L429516`/`L429565`）共同消费 | `L155911`、`L273469`、`L429565` |
| `api_error` | **部分**。唯一按 `type` 字面判定的点是 `L429516`：`ll instanceof $s && ll.type === "api_error"`，且**只用于「已产出内容时把响应定格为 partial」**，不触发重试。无内容时它落入非流式回退（第 3 节） | `L429516` |
| `rate_limit_error` | **否（不作为流内判据）**。`I5v(e)`（`L155913`–`L155916`）确实匹配 `'"type":"rate_limit_error"'`，但 `I5v` 只在 `ZFa`（`L155921`，状态码归一化，用于展示/遥测）中被消费，不在 `Ftw` / `IOi` / 流内 catch 的任何判据里 | `L155915`、`L155921` |
| `invalid_request_error` | **否**。`L428328` 的 `e.error?.error?.type === "invalid_request_error"` 是别处的分类；`L120512` 是另一个模块 | `L428328` |
| `authentication_error` | **否**。仅 `L428531` 用完整 JSON 串 `{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}` 判定「API key 校验失败」，是 `/login` 流程，不是重试 | `L428531` |
| `permission_error` | **仅限「模型级」**。`D9f`（`L273405`–`L273409`）要求 403 **且** 消息含 `model:` → 触发 fallback model，不是重试 | `L273408` |
| `not_found_error` | **仅限「模型级」**。`L9f`（`L273400`–`L273404`）要求 404 **且** 消息含 `model:` → 触发 fallback model | `L273403` |
| `billing_error` | **否（且明确不重试）**。`L273322` 用 `C.type === "billing_error"` 把它归入「不做 last-resort fallback」的一类 | `L273322` |
| `timeout_error` | **未找到任何判定用法**。全库仅出现在 `ttw`（`L273149`）这个「已知 Anthropic 错误类型名」列表里，该列表用于响应体形态识别/遥测（`L273127` `ytw` 系列），不参与重试 | `L273149` |
| `request_too_large` | 同上，仅在 `ttw`（`L273149`）与遥测归一化 `Spl`（`L271473`）中出现 | `L273149`、`L271473` |

`ttw`（`L273149`）和 `Spl`（`L271462`–`L271478`）都是**遥测/诊断用的名字白名单**，把未知类型折叠成 `"other"`。**它们不是重试判据**——这是本次考古中最容易看走眼的一处：grep 到这两行会误以为十种类型都被逐一处理了。

### 2.3 结论：流内 error 帧的重试真值表

设：`Yi` = 已经开始过一个「非 thinking、非 fallback」的 content block（`L429358`：`if (Ha = wi.index, wi.content_block.type !== "thinking" && wi.content_block.type !== "redacted_thinking" && !_Q(wi.content_block)) Yi = true`，其中 `_Q`（`L95027`）= `e.type === "fallback"`）；`Qe` = 已 push 的 assistant 消息；`Vo` = 已完成过一个块。

**情形 A：一个字节的内容都还没产出（`Qe` 空且 `!Vo`）** —— 走到 `L429582`：只要没禁用非流式回退，就 `Ffh(...)`（`L429592`）**用非流式模式把整个请求重发一遍**。这对**任何** `error.type` 都成立（`overloaded_error` 会先在 `L429565` 试 `xOi = 3` 次流式重试）。唯一豁免是 DLP（`w_t`，`L429564`，`Vet = "dlp_request_denied"`）和用户中断。

**情形 B：已经产出过内容（含仅 thinking）** —— 进入 `L429515` 分支：

- `L429516`：`Vc = (Qle(ll) || Vpl(ll) || ll.type === "api_error") && Yi`。
- `L429517`：`if (fu || xa || Vc)` —— `fu` = 空闲看门狗触发，`xa` = 可重试连接错误。**纯 SSE error 帧时 `fu` 和 `xa` 都为 false。**
- `L429519`：重试要求 `!Yi`；而 `Vc` 要求 `Yi`。**二者互斥 → SSE error 帧永远走不到 `L429519` 的重试。**
- 于是：`Yi` 为真（有实内容）→ 定格为 partial 响应，追加一条 `API Error: Server error mid-response. The response above may be incomplete.`（`L429540`）；`Yi` 为假（只有 thinking）→ `L429543` 直接 `throw`，遥测 `fallback_cause: "partial_yield"`，**连非流式回退都不做**。

把握程度：**代码字面直证**（`Vc` 与 `!Yi` 的互斥是逐字读出来的）。

---

## 3. 流中断 / 非结构化失败

### 3.1 连接错误码集合

`L156089`（同一行定义三个集合）：

```js
uhe = new Set(["ECONNREFUSED","ConnectionRefused","ENOTFOUND","ENETUNREACH","ENETDOWN","EHOSTUNREACH","EHOSTDOWN","EAI_AGAIN","FailedToOpenSocket","ERR_PROXY_TUNNEL"]),
ece = new Set(["ECONNRESET","EPIPE","ConnectionClosed","UND_ERR_SOCKET","ETIMEDOUT","ECONNABORTED","ERR_SOCKET_CLOSED","StreamSuspended"])
```

- `ece` = 「陈旧连接」类（`hu`，`L429514`），命中会额外关掉 keep-alive（`L273215` `Sla()`）。
- `uhe` = 「网络不通」类。
- `xa = hu || uhe.has(code)` → 可重试连接错误（`L429514`）。
- 证书类 `Ayi`/`R5v`（`L156089`）在 `Ftw`（`L273483`）里被**排除**，不重试。

错误码提取靠 `BB(e)`（`L155945`–`L155960`）沿 `cause` 链最多走 5 层找 `.code`；找不到 `.code` 但消息以 `gRn`（`L13786`：`"The socket connection was closed unexpectedly"`）开头时，合成 `code = "ConnectionClosed"`。

关于任务里点名的锚点：
- `ECONNRESET` —— **在**（`ece`）。
- `socket hang up` —— API 路径上**未找到**。全库唯一出现在 `L112959`，属于插件市场远程拉取的遥测分类函数 `xme`，与 API 无关。
- `Premature close` —— 全库**未找到**。
- `terminated` —— API 路径上**未找到**。`L238516` / `L243067` 的 `/\bterminated\b/` 属于 MCP SSE 传输的重连判据，另一条链路。
- `stream_error` —— 作为错误类型名**未找到**。

### 3.2 三类流内异常类

- `e6n` = `StreamIdleTimeoutError`（`L170931`–`L170942`），message `stream idle: no bytes for ${e}ms`，带 `idleMs/bytesReceived/ttfbMs/bodyReadPending/cfRay/sleptMs`。字节级看门狗。
- `aSi` = `StreamSuspendedError`（`L170943`–`L170951`），`code = "StreamSuspended"`（已在 `ece` 中），message `Stream watchdog detected system suspend; aborting to retry on a fresh connection`。**笔记本合盖休眠**专用。
- `kyi` = `StreamNoEventsError`（`L156091`–`L156096`），message `Stream ended without receiving any events`。抛出点 `L429464`：流正常结束但**没收到 `message_start`**，或收到了 `message_start` 但**没有任何 content block 完成且无 stop_reason** → 抛出，触发非流式回退。

### 3.3 「已经吐出内容就不重试」——存在，且分三档

`L429515` 的门是 `Qe.some(m => m.message.content.some(b => !_Q(b))) || Vo`，即「产出过任何非 fallback 内容（thinking 也算）」。之后：

| 已产出 | 错误种类 | 行为 | 行号 |
|---|---|---|---|
| 无 | 任意可重试连接错误 | 流式重试，计数 `Ni < nr = Xpl()`（默认 10），退避 `CZe(Ni)`，并向 UI 推 `onRetryStatus({kind:"retrying"})` | `L429550`–`L429558` |
| 无 | 空闲看门狗 `fu` | 流式重试，计数 `oo < xr`，**`xr = 1`（只重试 1 次）** | `L429560`–`L429562` |
| 无 | 529 / overloaded | 流式重试，计数 `vr < xOi = 3`，且要求 `vMt(querySource)`（主/用户可见）或 watchdog 模式；否则转 fallback model | `L429565`–`L429580` |
| 无 | 其余一切 | **非流式回退**（整请求重发，`Ffh`） | `L429582`–`L429592` |
| 仅 thinking | 看门狗 `fu` | 重试，`oo < xr = 1`；日志 `Stream idle timeout after thinking-only yield — retrying streaming` | `L429519`–`L429528` |
| 仅 thinking | 陈旧连接 `xa` | 重试，`mi < Ln = 2`，退避 `100 * mi` ms；日志 `Stream connection closed (...) after thinking-only yield — retrying streaming` | `L429521`、`L429527` |
| 仅 thinking | SSE error 帧 | **抛出**，无重试无回退（见 2.3 情形 B） | `L429543` |
| 有实内容 | 看门狗 / 连接断 / 529 / 5xx / api_error | **不重试**。合成 `stop_reason`（有 tool_use 则 `tool_use`，否则 `end_turn`），追加一条 `API Error: ...The response above may be incomplete.` 文本块，正常收尾 | `L429530`–`L429541` |
| 有实内容 | 其余 | 抛出，`fallback_cause: "partial_yield"` | `L429543` |

计数器初值在 `L429030`：`Ln = 2, mi = 0, Ni = 0, xr = 1, oo = 0, vr = 0`。

一个特例（`L429531`–`L429533`）：如果已经收到 `message_delta` 带 `stop_reason` 且没有未闭合的块，则判定「响应其实已完整」，静默 `break`，不追加任何错误提示，遥测 `tengu_streaming_close_after_complete`。

另一个特例（`L429545`–`L429548`、`L429200`–`L429203`）：带 `anthropic-dispatch-id` 头的请求，若在首个事件前发生连接错误或 5xx，**摘掉该头重试一次**（`Kr` 一次性标志），遥测 `tengu_dispatch_header_fallback`。

把握程度：**代码字面直证**。

---

## 4. Claude Code 自己的（非 SDK）重试与回退层

### 4.1 `IOi` 驱动（B 层）

`L273205`–`L273365`。除 `Ftw` 判据外，它还带若干**特化重试**（都不消耗主计数或以独立计数器封顶）：

- `onError` 钩子（`L273262`–`L273266`）：回调返回一个字符串原因，同一原因**只允许一次**（`y` Set），返回时 `H--` 抵消本次尝试。已知原因见 `L429196`–`L429253`：`"retry:afk-beta"`（服务端拒绝 afk beta 头 → 去头重试）、`"retry:dispatch-header-strip"`、`"retry:advisor-strip"`，以及 400 归因于 `fallback-credit-` / `server-side-fallback-` 头时的剥离重试（`L429031`–`L429033`，日志 `[server-fallback] 400 attributed (...) — stripping and retrying`）。
- 低优先级排队（`L273267`–`L273271`、`Dyi` `L156242`）：主查询在 429 `slot_busy` 或 529 时，不算重试，而是进入「等容量」状态，UI 显示 `low_priority_waiting`。
- fast mode 降级（`L273276`–`L273294`）：429/529 时读 `anthropic-ratelimit-unified-overage-disabled-reason` → 关掉 fast mode 后 `continue`（不计次）。400 且消息含 `Fast mode is not enabled`（`U9f`，`L273396`–`L273399`）同理。
- max_tokens 溢出自愈（`L273326`–`L273335`）：400 且消息匹配 `input length and \`max_tokens\` exceed context limit: A + B > C` → 算出 `availableContext = C - A - 1000`，若 `< I9f = 3000` 放弃，否则设 `maxTokensOverride` 后 `continue`（不计次）。
- 各家认证刷新的独立预算：`Stw = 2`（CCR auth）、`Etw = 2`（OAuth refresh）、`Atw = 2`（host auth）、`Htw = 2`（AWS）、`Ttw = 2`（GCP）、`ktw = 2`（apiKeyHelper）——`L273539`，超出即抛。

### 4.2 Fallback model 切换

错误类 `Zoe = FallbackTriggeredError`（`L272913`–`L272925`），message `Model fallback triggered: ${e} -> ${t4}`，`reason` ∈ `overloaded` / `model_not_found` / `permission_denied` / `server_error` / `last_resort` / `model_blocked`。触发点：

| 触发点 | 条件 | 行号 |
|---|---|---|
| 模型不存在 / 无权限 / 5xx（非529） | `(L9f(C) \|\| D9f(C) \|\| !Ont() && Vpl(C))` 且配了 `fallbackModel` | `L273272`–`L273275` |
| 连续 529 | `s >= xOi = 3`，配了 `fallbackModel` → `tengu_api_opus_fallback_triggered` | `L273297`–`L273299` |
| 连续 529 但**没配** fallback | 抛 `Error(LOi)`，`LOi = "Repeated 529 Overloaded errors"`（`L415528`） | `L273300` |
| last resort | 任何带 status 的 APIError，且不在 `Ptw = {401,407,429,404,403,413}` 内、不是 `billing_error`、不命中 `Mtw` 谓词组 | `L273322`–`L273323` |
| 流内 529 且无内容、重试用尽 | `L429579` | `L429579` |

`Vpl`（`L273410`）= `status >= 500 && status < 600 && status !== 529`（**529 被显式排除**，走 overloaded 专线）。

`Mtw`（`L273586`）= `[jXr, qhr, Zpl, ROi, U9f, deo, w_t]`：
- `jXr`（`L414920`）prompt too long
- `qhr`（`L414924`）max_tokens context overflow
- `Zpl`（`L414927`）消息含 `credit balance is too low`
- `ROi`（`L414930`）消息含 `organization has been disabled`
- `U9f`（`L273396`）Fast mode is not enabled
- `deo`（`L415123`）400 且含 `cannot be used as an advisor when the request model is`
- `w_t`（`L155917`）DLP `dlp_request_denied`

### 4.3 用户可见文案

- `L459970`：`" · Retrying in ${Xss}${_Ar} · attempt ${ede.attempt}/${ede.maxRetries}"`。前缀在 `L459973`：未达阈值时显示 `"API error"`；达到 `attempt >= min(3, maxRetries)` 或网络中断或 SSL 错误或有限流信息时，显示 `error.formatted` 或 `"<限流类型> reached"`。
- `L460102`：`we = g.error.status === 529 || g.error.formatted.toLowerCase().includes("overload")`，`Ie = g.attempt >= Math.min(3, g.maxRetries)` —— 过载态的专门渲染分支。
- `L415528` 常量带（同一行）：`YA = "API Error"`、`LOi = "Repeated 529 Overloaded errors"`、`b3t = "Opus is experiencing high load, please use /model to switch to Sonnet"`、`v3t = "Fable is experiencing high load, ..."`、`zvE = "Server is temporarily limiting requests (not your usage limit)"`、`Pzt = "Request timed out"`。
- 流内定格 partial 时插入的文本（`L429540`）：`API Error: Server error mid-response. The response above may be incomplete.` / `...Connection lost mid-response...` / `...The response stopped arriving...` / `...Your computer went to sleep mid-response...`；无内容版本则是 `...Try again.`。
- 系统事件对象（`L418097`）：`{type:"system", subtype:"api_error", level:"error", error, retryInMs, retryAttempt, maxRetries, source}`，`source` ∈ `"connection_retry"`（`L429557`）/ `"request_retry"`（`L273348`、`L273356`）。

**未找到**：模型 fallback 发生时的「Falling back to X」用户文案。全库 `Falling back to` 的命中全部属于 git/plugin/sandbox/zod 等无关模块（`L23319`、`L35126`、`L64643`、`L198136` 等）。模型 fallback 走的是结构化事件 `{type:"fallback_request", ...}` 与 `{type:"server_fallback", ...}`（后者见 `L429276`），文案在 UI 层另行渲染，本次未追到渲染点。把握程度：**未找到，无法判定**（只能确定不是通过该英文串实现的）。

### 4.4 环境变量开关（可据以做兼容性实验）

| 变量 | 效果 | 行号 |
|---|---|---|
| `CLAUDE_CODE_MAX_RETRIES` | 覆盖 B 层次数，非 watchdog 下钳制到 15 | `L273509`–`L273515` |
| `CLAUDE_CODE_RETRY_WATCHDOG` | `Ont()`，把 429/529 变成「无限期等到额度恢复」，次数 300，单次等待上限 6h | `L273168`、`L273338`、`L273467` |
| `CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK` | 关掉流失败后的非流式重发 | `L429514` |
| `CLAUDE_ENABLE_STREAM_WATCHDOG` | 默认 `true`（`?? true`），空闲看门狗总开关 | `L429265`（`pu = q.CLAUDE_ENABLE_STREAM_WATCHDOG ?? true`） |
| `CLAUDE_SLOW_FIRST_BYTE_MS` | 首字节慢日志阈值，默认 30000（只报警不重试） | `L429171` |
| `API_TIMEOUT_MS` | SDK timeout，默认 600000 | `L170557` |
| `CLAUDE_CODE_DISABLE_MTLS_RELOAD_ON_STALE_CONNECTION` | 陈旧连接时不重载 mTLS 材料 | `L273190` |

---

## 5. 明确不重试的名单

按「谁做的判定」分组。

### 5.1 B 层 `Ftw` 判 false（`L273460`–`L273495`）→ `L273324` 抛 `wG`，遥测 `api_request_non_retryable`

- 任何**没有 status 且不是 `Pk`（连接错误）**的 APIError（`L273488`）——**包括所有 SSE 流内 error 帧**（但它们本来就不走这条路）。
- `x-should-retry: false`（含 5xx，`L273477`）。
- 400（除 max_tokens 溢出那一条）、403（除 OAuth revoked）、404、413、422 等 4xx（落到 `L273495` 的 `return false`）。
- gateway 模式的 429（`L273461`）。
- credits/额度类 429（`L273462`）与 spend-limit 类 429（`L273466` → `Utw` `L273500`）。
- 订阅态（`ds()` 真、非 enterprise）且带统一限流 header 的 429（`L273493` + `M9f` `L273497`）。
- 证书错误：`Ayi`（`L156089`）中的 15 个码 + `ERR_TLS_HANDSHAKE_TIMEOUT` / `ERR_SSL_WRONG_VERSION_NUMBER` / `ERR_SSL_DECRYPTION_FAILED_OR_BAD_RECORD_MAC`（`L273483`）。
- `BedrockUnexpectedContentType`、`TestEgressBlocked`（`L273484`–`L273485`）。

### 5.2 `IOi` 中的短路（不看 `Ftw`）

- `wG`（已包装错误）、`jS`（用户中断）直接透传（`L273258`–`L273259`）。
- DLP 拒绝 `w_t`（`L273260`，`Vet = "dlp_request_denied"`）→ 立即抛，遥测 `api_request_dlp_denied`。
- 529 且 querySource **不是**用户可见的（`!vMt`）且非 watchdog（`L273295`）→ 直接丢弃，遥测 `tengu_api_529_background_dropped`。**后台/辅助查询遇到过载不重试。**
- `retry-after` 换算出的延迟 > 60s（`L273340`）→ 放弃。
- 各认证预算耗尽（`L273306`/`L273310`/`L273314`/`L273318`，均为 2 次）。
- 主计数耗尽 `H > n4`（`L273304`）。

### 5.3 流内（C 层）不重试

- 已产出非 thinking 内容后的任何错误（`L429515` → `L429530`/`L429543`）。
- 仅 thinking 时的 SSE error 帧（`Vc` 与 `!Yi` 互斥，`L429516` vs `L429519`）。
- DLP（`L429564`）。
- 用户中断 `jS` 且 `o4.aborted`（`L429499`–`L429507`）。
- 空闲看门狗超过 1 次（`xr = 1`）。
- 流式 529 超过 3 次（`xOi = 3`）。

### 5.4 「不做 last-resort fallback」名单（`Ptw` + `Mtw`，`L273322`、`L273586`）

`Ptw = {401, 407, 429, 404, 403, 413}`（404 在非流式请求时豁免，`L273322` 的 `!(C.status === 404 && r2.isNonStreamingRequest)`），加 `type === "billing_error"`，加 `Mtw` 的七个谓词（见 4.2）。这一组不触发换模型，直接失败。

---

## 6. 对本项目（作为上游代理）的可行动结论

按「你要伪装成 Anthropic 上游、且希望 CC 侧行为可控」的角度：

1. **想让 CC 重试而不打扰用户**：在 HTTP 响应上加 `x-should-retry: true`，它在 `Ftw`（`L273476`）和 SDK（`L13471`）里都排在 status 判定之前。注意订阅态（OAuth 非 enterprise）会额外要求 `!ds() || bjr() || M9f(e)`。
2. **想让 CC 立刻放弃**：`x-should-retry: false` 能压掉 5xx（`L273477`–`L273480` 无条件 `return false`）。
3. **`retry-after` 别超过 60 秒**：`L273340` 会把它当成「等太久」直接失败。`retry-after-ms` 只有 SDK 层（A）读，主路径 SDK 被关掉，所以**在主查询上 `retry-after-ms` 无效**，只有 `retry-after`（秒）有效（`F9f`，`L273381`）。
4. **流内 error 帧要重试，只有一条路可靠**：payload 必须让 `JSON.stringify` 后的串包含**紧凑无空格**的 `"type":"overloaded_error"`。任何其他 `error.type` 在「已产出内容」时都不会重试。
    - **更正（主会话补，2026-08-24）**：「紧凑无空格」这个提法会误导——上游线上字节的排版无关紧要，`iIn` 先 `JSON.parse` 再由 `makeMessage` 重新 `JSON.stringify`，空格在匹配前就归一化掉了。真正的约束是**信封必须嵌套**（`{"type":"error","error":{"type":"overloaded_error",…}}`，顶层不能有 `message` 字段），且 `data` 必须是合法 JSON。详见 §2.1 的更正块。
5. **别在产出内容之后才发 error 帧**：CC 会把响应定格成 partial 并往会话里塞一条 `API Error: ... may be incomplete.`，用户看到的是半截回答而不是重试。
6. **后台/辅助查询的 529 会被直接丢弃**（`L273295`），不要指望它重试。
7. **流建立后完全不发任何事件就结束**（无 `message_start`，或有 `message_start` 但零个完成的块）→ `StreamNoEventsError`（`L429464`）→ **CC 会用非流式模式把同一个请求重发一次**。若上游是有副作用的，这一点要留意。

---

## 7. 未采纳 / 排除的路线

必须写下来，否则这些排除事后无从复原：

1. **`ttw` 列表（`L273149`）看似是「十种错误类型的处理表」，实际不是。** 它是响应体形态诊断 `ytw`（`L273127`）/ `UnexpectedApiResponseError`（`L273156`）用的已知类型名单，用于判断「这个 JSON 是不是 Anthropic 的错误信封」。读函数体后排除。同理 `Spl`（`L271462`）是遥测名字折叠。**这是本次最大的假锚点。**
2. **`I5v`（`L155913`，匹配 `'"type":"rate_limit_error"'`）不参与重试。** 追了它唯一的消费者 `ZFa`（`L155921`），是状态码归一化（给展示和遥测用）。排除。
3. **SDK 的 `shouldRetry` 在主路径上是死代码。** 一开始按「Anthropic SDK 重试逻辑」定位到 `L13467` 就想收工，但 `L429164` / `L428607` 的 `maxRetries: 0` 推翻了它。保留在报告里是因为 `verify_api_key`（`maxRetries: 3`，`L428523`）和部分 side query（`L429853`）仍走它。
4. **`socket hang up` / `Premature close` / `terminated` / `stream_error` 在 API 路径上都不存在。** `socket hang up` 唯一命中 `L112959`，属于插件市场拉取的遥测分类 `xme`；`terminated` 的两处（`L238516`、`L243067`）属于 MCP SSE 传输重连。都不是 Anthropic API 链路，排除。**注意二者代码几乎一样，容易误读成同一个函数被复用。**
5. **`Vpl` 一度被误读成「所有 5xx」。** 实际是 `>= 500 && < 600 && !== 529`（`L273411`），529 被显式排出去走 overloaded 专线。若不读到 `!== 529` 会把 529 的三次专用计数（`xOi`）算重复。
6. **`L429519` 的 `!Yi` 与 `L429516` 的 `&& Yi` 互斥这件事，是逐字对读才发现的。** 最初按日志文案「after thinking-only yield」以为它会覆盖 mid-stream 服务端错误，实际不会。若不发现这一点，会得出「流内 529 有 thinking 时也会重试」的错误结论。
7. **`_Q` 一开始被猜成「是不是 thinking 块」，实际是 `e.type === "fallback"`（`L95027`）。** 这改变了 `L429515` 门的语义：thinking 块也算「已产出内容」，会把请求推进 partial 分支。靠 grep 函数定义纠正。
8. **未追到模型 fallback 的用户可见文案。** grep `Falling back to` / `falling back to` / `Overloaded` 全部命中无关模块或 bundle 内嵌的 `claude-api` skill 文档。判定为「走结构化事件 + UI 层渲染」，但没有定位到渲染点。标记为未找到，不填空。
9. **未展开 `Hgi`（`L150679`）、`bQi`、`pfh` 等 `onError` 内部的细分归因。** 它们是 400 错误定位到具体 message/content 索引后剥离重发的机制，属于「请求体自愈」而非错误类型驱动的重试，与本次问题相关度低，主动放弃。若后续要做「CC 对畸形 400 的自愈行为」专题，入口在 `L429205`–`L429253`。
10. **未验证 `x-should-retry` 在 SSE error 帧场景下是否真能生效。** 结构上 `L9347` 确实把响应头传进了 `$s`，但流内错误不经 `Ftw`（第 0 节结论），所以那份 header 在流内路径上没有消费者。判定为「传了但用不上」，未做运行时验证。把握程度：由代码结构推断，**需交叉验证**。
11. **未做 2.1.207 的完整差分。** 只对了 SDK `shouldRetry`（三版逐行同形：`L13467` / `L12699` / `L12384`）和 `'"type":"overloaded_error"'` 判据（2.1.226 `L125270` 与 2.1.241 `L273469` 同形）。C 层流内逻辑未做版本对照，因为 2.1.226/207 的行号映射需要重新定位入口，ROI 不足。若需要，入口锚点是字符串 `Stream idle timeout after thinking-only yield`。
