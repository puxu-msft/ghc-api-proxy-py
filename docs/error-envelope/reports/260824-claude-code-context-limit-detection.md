# Claude Code 「上下文超限」识别判据考古报告

> 素材：`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js`（660402 行）。除非另行标注，下文所有 `L<数字>` 均指该文件行号。
> 版本对照：`/home/xp/.claude/refs/claude-code-2.1.226/app.pretty.js`（562347 行）、`/home/xp/.claude/refs/claude-code-2.1.207/app.pretty.js`（461543 行）。
> 版本确认：三份 `manifest.json` 各自带 `version` 字段（`"2.1.241"` / `"2.1.226"` / `"2.1.207"`），且 `prettyLines` 与实测 `wc -l` 互为交叉校验（实测 = `prettyLines - 1`，差一来自尾随换行）。**可据以行动**。
> PoC 探针：`260824-cc-context-limit-predicate-probe.mjs`（与本报告同目录，`node` 直接跑）。
> 前置报告：`260824-claude-code-sse-retry-behavior.md`（同目录），本报告复用其第 0 节的三层重试结构结论，不再重复。
> 日期：2026-08-24。

---

## 0. 一句话结论

**Claude Code 认的是 `error.message` 里小写化之后的子串 `prompt is too long`（或 `input is too long for requested model`），不看 `error.type`，不看 `error.code`，在主判据上也不看 HTTP status。**

用户实测的那条上游错误——`Your input exceeds the context window of this model.`——**在 HTTP 400 下完全不会被识别**。它含有 `context window`，而 `context window` 这条判据（`Aci`，`L116766`）**被 HTTP 413 的门挡住**，400 到不了它。

后果是实质性的，不是文案问题：识别成功会触发**反应式自动压缩并重发请求**（`reactive_compact_retry`）；识别失败则只是把一条 `API Error: 400 {...}` 贴进会话，**不压缩、不重试、不换模型**，用户必须自己动手。

---

## 1. 确切谓词（问题 1）

### 1.1 三条基础判据，全部是 `toLowerCase()` 之后的子串匹配

`L116762`–`L116771`，逐字原文：

```js
  function Eci(e) {
    let t4 = e.toLowerCase();
    return t4.includes("prompt is too long") || t4.includes("input is too long for requested model");
  }
  function Aci(e) {
    return e.toLowerCase().includes("context window");
  }
  function Nxa(e) {
    return e.toLowerCase().includes("input length and `max_tokens` exceed context limit");
  }
```

注意三点：

- 三条都先 `toLowerCase()`，所以**上游的大小写无关紧要**。探针 case H（`Prompt Is Too Long: ...`）实测被识别。
- `Nxa` 的匹配串里**含反引号**（`` `max_tokens` ``），是字面量的一部分，不是 Markdown 修饰。
- 三条吃的都是**裸字符串**，`instanceof Error` 的门在调用方。

### 1.2 包装成错误谓词

`L414920`–`L414926`，逐字原文：

```js
  function jXr(e) {
    if (!(e instanceof Error)) return false;
    return Eci(e.message) || A3(e.message, "prompt_too_long");
  }
  function qhr(e) {
    return e instanceof Error && (Nxa(e.message) || A3(e.message, "max_tokens_context_overflow"));
  }
```

**`jXr` 只要求 `e instanceof Error`，没有任何 HTTP status 限定。** 这是全篇最关键的一条：`prompt is too long` 在**任何**状态码下都被识别，甚至在 `status === undefined` 的流内错误帧上也识别。

### 1.3 `A3` 是 Claude Code 自己的内部协议，不是给上游用的

`L116836`：`var myp = "capability_rejected: "`。`L116746`–`L116758`：

```js
  function Oxa(e) {
    return `${myp}${e}`;
  }
  function A3(e, t4) {
    let r2 = Oxa(t4), n4 = 0;
    for (; ; ) {
      let o4 = e.indexOf(r2, n4);
      if (o4 === -1) return false;
      let i = e[o4 + r2.length];
      if (i === void 0 || !/[A-Za-z0-9_:.-]/.test(i)) return true;
      n4 = o4 + 1;
    }
  }
```

即 `A3(msg, "prompt_too_long")` 找的是子串 `capability_rejected: prompt_too_long`，且要求其后不是 `[A-Za-z0-9_:.-]`（token 边界，防止误匹配 `prompt_too_long_x`）。

**生产端是 Claude Code 自己的网关消毒路径**：`Tci`（`L116816`）在 `lR0`（`L646698`）/ `ro_`（`L646708`）里把上游错误重写成带该前缀的消息。本项目作为上游代理**不应该**伪造这个 token —— 它是网关侧内部契约，且只有 2.1.241 认（226/207 全文命中 0，见 §5）。**仅存档，不建议使用。**

---

## 2. 判据作用在哪个对象上（问题 2）

### 2.1 一律作用在 `Error.prototype.message` 字符串上，不是结构化字段

`jXr` / `qhr` 读的是 `e.message`。这个 `message` 由 Anthropic SDK 的 `APIError`（代码里是 `$s`）构造，`L8351`–`L8362`：

```js
    $s = class $s2 extends ma {
      constructor(e, t4, r2, n4, o4) {
        super(`${$s2.makeMessage(e, t4, r2)}`);
        this.status = e, this.headers = n4, this.requestID = n4?.get("request-id"), this.error = t4, this.type = o4 ?? null;
      }
      static makeMessage(e, t4, r2) {
        let n4 = t4?.message ? typeof t4.message === "string" ? t4.message : JSON.stringify(t4.message) : t4 ? JSON.stringify(t4) : r2;
        if (e && n4) return `${e} ${n4}`;
        if (e) return `${e} status code (no body)`;
        if (n4) return n4;
        return "(no status code or body)";
      }
    };
```

对标准 Anthropic 错误信封 `{"type":"error","error":{"type":"invalid_request_error","message":"..."}}`：顶层没有 `message` 字段，于是 `n4 = JSON.stringify(整个 body)`，最终 `e.message` 形如：

```
400 {"type":"error","error":{"type":"invalid_request_error","message":"prompt is too long: 210000 tokens > 200000 maximum"}}
```

**嵌套的 message 文本确实在这个串里**，所以子串匹配能命中。探针 case C 实测确认。

**推论（可据以行动）**：`error.type` 与 `error.code` 在上下文超限这条链路上**完全不参与判定**。判据只关心那一整串里有没有那几个短语。把 `type` 写成 `invalid_request_error` 还是别的，对识别**没有任何影响**。

### 2.2 非流式与流式两条腿

| 腿 | 错误如何产生 | `e.status` | `jXr`（`prompt is too long`） | `Aci`（`context window`） |
|---|---|---|---|---|
| HTTP 响应非 2xx（含 `stream: true` 请求在建流前就 400） | `$s.generate(status, body, ...)`（`L8363`） | 真实状态码 | **生效** | 仅当 status 恰为 413 |
| SSE 流内 `event: error` 帧 | `L9347` `throw new $s(void 0, l, void 0, e.headers, c)` | **`undefined`** | **生效** | **永远不可达** |

`L9345`–`L9348` 逐字：

```js
              if (a.event === "error") {
                let l = iIn(a.data) ?? a.data, c = l?.error?.type;
                throw new $s(void 0, l, void 0, e.headers, c);
              }
```

第一个参数是 `void 0`，所以流内错误帧的 `status` 恒为 `undefined`，而 `Mah(e)`（`L414951`）是 `e instanceof $s && e.status === 413`，**在流内腿上恒为 false**。

> **对本项目的直接含义**：上下文超限是在请求发出时就能判定的，代理会在建流之前返回 HTTP 400，所以走的是第一行（非流式腿），`stream: true` 与否不改变判据。这一点**仅倾向**（结构推断：`L429190` 的 `await ll.beta.messages.create({...stream:true}).withResponse()` 在 4xx 时抛错而非返回 Stream），未做运行时验证。

---

## 3. HTTP status 的限定（问题 5）

这是本次调查里最容易读错、也最关键的一节。**两条判据的 status 门完全不同。**

### 3.1 主判据 `prompt is too long`：无 status 门

`YvE`（`L415215`，错误 → 用户可见消息的总映射函数）里，`L415249` 逐字：

```js
    if (jXr(e) || qhr(e)) return Xd({ content: Y9, error: "invalid_request", errorDetails: e.message });
```

前面没有任何 status 判断，`jXr` 自己也没有。400、413、500、`undefined` 一律识别。

### 3.2 `context window` 判据：被 413 死死挡住

`L415264`–`L415265` 逐字：

```js
    if (Mah(e)) {
      if (Aci(e.message) || A3(e.message, "prompt_too_long")) return Xd({ content: Y9, error: "invalid_request", errorDetails: e.message });
```

`Mah(e)`（`L414951`–`L414953`）：

```js
  function Mah(e) {
    return e instanceof $s && e.status === 413;
  }
```

**`Aci` 只在 `Mah` 这一个门内被调用**（客户端侧）。全库 `includes("context window")` 只有一处命中：

```
$ rg -n --no-heading -F 'includes("context window")' app.pretty.js
116767:    return e.toLowerCase().includes("context window");
```

即 `Aci` 自身。它的三个调用点是 `L116817`（网关侧 `Tci`）、`L415265`、`L415409`，后两者都在 `Mah`（413）之内。

### 3.3 网关侧分类器 `Tci` 的门（旁证，不是客户端判据）

`L116816`–`L116830` 节选：

```js
  function Tci(e, t4, r2) {
    if (e === 413) return Aci(t4) || Eci(t4) ? "prompt_too_long" : void 0;
    if (e !== 400) return;
    ...
    if (Eci(t4)) return "prompt_too_long";
    if (Nxa(t4)) return "max_tokens_context_overflow";
```

`Tci` 只在 `L646698` / `L646708` / `L646992` 被调用，全部属于网关消毒路径（`ro_` 的外层门是 `e.status === 400 || e.status === 413`），产出的是 `capability_rejected:` token。**它不是客户端识别上游错误的判据**，本项目不经过它。

### 3.4 唯一一处主动的 status 限定：max_tokens 改参自愈

`B9f`（`L273384`）要求 `e.status !== 400 || !e.message` 时直接 return，即**必须恰为 400**。详见 §5.2。它管的是「改参重发」这一个动作，不影响 §1 的识别与 §4 的压缩。

---

## 4. 识别成功后的行为（问题 3）——反应式自动压缩 + 重发

这是完整调用链，每一跳都有逐字证据。**可据以行动。**

### 4.1 第 1 跳：判据命中 → 消息正文被替换成常量 `Y9`

`L415528` 常量带节选：`Y9 = "Prompt is too long"`。

`L415249` / `L415265` 命中后返回 `Xd({ content: Y9, ... })`。`Xd`（`L416069`–`L416073`）逐字：

```js
  function Xd({ content: e, apiError: t4, apiErrorIsTransient: r2, quotaLimits: n4, error: o4, errorDetails: i, now: s, uuid: a }) {
    let l = Rlh({ content: [{ type: "text", text: e === "" ? XR : e }], isApiErrorMessage: true, apiError: t4, apiErrorIsTransient: r2, quotaLimits: n4, error: o4, errorDetails: i, now: s, uuid: a });
```

于是会话里被追加一条 assistant 消息，`isApiErrorMessage: true`，`content[0].text` **逐字等于 `"Prompt is too long"`**。

### 4.2 第 2 跳：主循环用「消息正文的前缀」重新认出它

`L414875`–`L414881`（`rot`）逐字：

```js
  function rot(e) {
    if (!e.isApiErrorMessage) return false;
    let t4 = e.message.content;
    if (!Array.isArray(t4)) return false;
    return t4.some((r2) => r2.type === "text" && r2.text.startsWith(Y9));
  }
```

`L312755` 逐字（节选）：

```js
        }, xr = bt.at(-1), oo = xr?.type === "assistant" && xr.isApiErrorMessage && rot(xr), ...
```

**这是一个二次判据，判的是 Claude Code 自己刚写下的那条消息，而不是上游的字节。** 换言之：只要第 1 跳没把正文设成 `Y9`，第 2 跳必然为 false，后续整条自愈链条全部不发生。

### 4.3 第 3 跳：`oo` 为真 → 反应式压缩

`L312769` 逐字（节选）：

```js
          let ms = performance.now(), go = oo && xr ? YJr(xr) : void 0, { outcome: Qi, swap: is, emittedEarlyCompactStart: Er } = yield* wWr((ce, Be, Tt) => Xyl({ toolUseContext: ce, messages: Ye, trigger: "ptl", isWithheld413: oo, hasAttemptedReactiveCompact: oe, borrowFrom: je ? X.precomputeSourceKey : void 0, detectedAt: ms, querySource: l }), hn), jn = yield* wWr((ce, Be, Tt) => zFi({ hasAttempted: oe, querySource: l, aborted: hn.abortController.signal.aborted, messages: Ye, cacheSafeParams:
```

`trigger: "ptl"`（prompt too long）。`Xyl`（`L305010` 起）的启用门 `L305029`：

```js
    }, c = !Xto(i) && eZr() && (e.trigger === "threshold" || e.isWithheld413 === true && !e.hasAttemptedReactiveCompact);
```

`zFi` 是真正执行压缩的函数，遥测事件 `tengu_reactive_compact_triggered`。其准入门 `t_l`：

```js
  function t_l(e) {
    return !e.hasAttempted && !EWr(e.querySource) && (e.hasPrecomputedSwap === true || !QNt(e.querySource)) && mL() && VSe() && !e.aborted;
  }
```

`!e.hasAttempted` ⇒ **一轮对话里反应式压缩只尝试一次**。

> 字段名 `isWithheld413` 是历史遗留：它的**取值**来自 `oo`（消息正文前缀），与 HTTP 413 无关。不要被名字误导。**可据以行动**（赋值点 `L312769` 逐字可读）。

### 4.4 第 4 跳：压缩成功 → 用压缩后的历史**重发请求**

`L312779` 逐字（节选）：

```js
            Ue = UFa(m.uuid(), qs), y = { messages: ce, toolUseContext: X, compactTracking: Ue, maxOutputTokensRecoveryCount: de, hasAttemptedReactiveCompact: is === void 0, thinkingOnlyNudged: ee, maxOutputTokensOverride: void 0, resumeIncompleteThinking: Ie, pendingToolUseSummary: void 0, stopHookActive: he, stopHookBlockingCount: 0, turnCount: we, transition: { reason: is ? "precomputed_compact_swap" : "reactive_compact_retry" } };
            continue;
```

`transition.reason = "reactive_compact_retry"` 且 `continue` 回到主循环顶部 —— **这就是自动重试**。用户看到的是「压缩了一下，然后继续」，而不是一条错误。

### 4.5 压缩不可行时：换成带诊断数字的解释文案

`L312765`–`L312768` 节选：

```js
          if (xr && t_l({ hasAttempted: oe, querySource: l, aborted: X.abortController.signal.aborted }) && drm(Ye)) {
            let ce = Kto(Ye), Be = ce.length, Tt = Kr ? "image_error" : "prompt_too_long", { actualTokens: Ot, limitTokens: _r } = rno(xr.errorDetails ?? ""), mn = w2(ce.flat()), Fn = Ot !== void 0 ? Math.max(0, Ot - mn) : void 0;
```

`drm(e)` = `Kto(e).length < 2`，即「整个会话不足两组，压无可压」。此时用 `Jam(...)`（`L414893`）生成解释，`_vl` 替换正文。`Jam` 的三条文案里两条引用了从错误消息里抠出来的 token 数，抠取靠 `rno`（`L414879`）：

```js
    let t4 = e.match(/prompt is too long[^0-9]*(\d+)\s*tokens?\s*>\s*(\d+)/i);
```

**这条正则是本报告里唯一对上游消息「格式」而非「关键词」有要求的地方**：想让用户看到具体的 token 数，消息需形如 `prompt is too long: <实际> tokens > <上限>`。抠不到只会退化成一句不带数字的通用解释（`Jam` 第一分支），不影响压缩本身。**可据以行动**。

### 4.6 明确**不会**发生的事

- **不换模型**。`L273586`：`Mtw = [jXr, qhr, Zpl, ROi, U9f, deo, w_t]`，`Mtw` 是「不做 last-resort fallback」谓词组，`jXr`/`qhr` 在其中。
- **不走 HTTP 层重试**。400 在 `Ftw`（`L273460`）里落到兜底 `return false`；唯一例外是 `qhr` 那条 max_tokens 溢出自愈（下节）。
- **auto-compact 的常规触发与本错误无关**。常规 auto-compact 由本地 token 记账在**发请求之前**触发（`L312213` / `L312326` / `L327303` 的 `autoCompactWindow` 阈值判断），`Sco`（`L374239`）那条 `Context exceeds the ${n4}-token limit by ${r2} tokens — run ${i} to continue.` 也是本地记账文案。**本报告讲的是错误驱动的那条反应式路径，两者是不同机制。** 代理无法通过错误响应影响前者。

### 4.7 `prompt_too_long` 作为「回合终止原因」只出现在放弃的那一支

§4.3 的压缩若成功，主循环 `continue`（`L312779`），**回合不结束**。只有 §4.5 那条压不动的分支、以及 `L312782` 之后的失败分支，才 `return { reason: "prompt_too_long" }`。该 reason 随后被 `PNn`（`L74122`）判为「算错误」：

```js
      case "prompt_too_long":
      ...
        return true;
```

用于 `tengu_turn_end` 的 `is_error` 字段（`L311375`）。**纯遥测，不改变行为。**

另有一处外围消费：`j1m`（`L368790`）用 `jXr(e) || qhr(e) || includes("input is too long for requested model")` 门住后调 `rno` 抠 token 数，服务于沙箱网络自动分类器（`qrn`，`L368798`），与主链路无关。它还有第二个用途 `qGw`（`L368530`）：一个 400 如果其实是 PTL，就**不要**归因成「beta header 被拒」去掉 beta 重试。

### 4.8 反向陷阱：同一句 `Prompt is too long` 也可能根本没发出过请求

`L312325`–`L312330` 逐字：

```js
      if (We.kind !== "compacted" && l !== "compact" && !et && !Le) {
        if (Wet(eP(Ye, KR(X.options.mainLoopModel)) - Ge, X.options.mainLoopModel, X.options.autoCompactWindow).level === "blocked") {
          let oo = QNt(l), vr = We.kind === "failed" ? We.compactFailure : void 0;
          if (!oo) N("tengu_ptl_surfaced_to_user", { reason: Ce("blocking_limit"), querySource: eT(l), wasGatedByPriorAttempt: false, reactiveUnsupported: !VSe(), compactFailureReason: io(vr?.reason) });
          let Kr = Xd({ content: e_l(vr) ?? Y9, error: "invalid_request", now: m.now, uuid: m.uuid });
          return yield Kr, FVe(X, l, Kr), { reason: "blocking_limit" };
        }
```

这是**本地按 token 估算直接拒发**，一个字节都没上行，却产出与真实 PTL 逐字相同的 `Y9` 消息（reason 为 `blocking_limit` 而非 `prompt_too_long`）。

**对本项目的含义（调试时极易误判）**：在 Claude Code 界面上看到 `Prompt is too long`，**不能反推代理返回过 4xx**，也不能用它验证改写是否生效。要验证识别，看的应当是代理侧是否收到了紧随其后的**第二个（压缩后的）请求**，或 Claude Code 的遥测事件 `tengu_reactive_compact_triggered`。**可据以行动。**

### 4.9 auto-compact 开关会一并关掉反应式路径

`t_l`（§4.3 已引）含 `mL()`，而：

```js
  function KOp() { return Boolean(q.DISABLE_COMPACT || q.DISABLE_AUTO_COMPACT); }
  function mL() { if (KOp()) return false; return ap("autoCompactEnabled", true).value; }
```

`autoCompactEnabled` 默认 `true`（`L93159`）。若用户关掉 auto-compact 或设了 `DISABLE_COMPACT` / `DISABLE_AUTO_COMPACT`，**识别照常发生，但压缩与重发不发生**，直接展示给用户。**可据以行动。**

### 4.10 用户实际看到的文案

`L476887` 的 `case Y9:` 渲染 `Arc`（`L476849`），关键两行逐字：

```js
    let mKh = poA, kVP = q.DISABLE_COMPACT ? "/clear to continue" : "/compact or /clear to continue", CVP = wt(woA) !== void 0, xVP = Bcn(), grc = !CVP && !xVP && LFa() ? " \xB7 auto-compact is off \xB7 /config to turn it on" : "";
    ...
    if (fKh[1] !== grc) yrc = lc.jsxs(v, { color: "error", children: ["Context limit reached \xB7 ", kVP, grc, mKh ? ` \xB7 ${mKh}` : ""] }), ...
```

即 `Context limit reached · /compact or /clear to continue`。**注意这条只在压缩失败或被关掉时才会走到**；成功路径上用户看到的是压缩进度事件，然后请求自动重发。

压缩失败时另有专门文案 `e_l`（`L305129`）：

```js
  function e_l(e) {
    if (e?.reason !== "error" || !e.detail) return;
    return `${Y9} \xB7 automatic compaction failed: ` + ql(e.detail, Gfw, true);
  }
```

### 4.11 压缩内部还有两层各自的 PTL 自愈

- **摘要请求自身超限 → 丢历史重发**：`tzi`（`L365831` 起）循环判断摘要结果是否 `startsWith(Y9)`，是则 `pOm`（`L365780`）丢掉最早若干组后重来，上限 `dOm = 3`（`L366098`）。丢多少由 `YJr`（token 差）决定，抠不到就丢 20%。
- **反应式摘要逐步退让**：`DFi`（`L304639`）的 `while (s < o4)` 每次多保留几组、少摘要几组，直到成功或 `exhausted`。

这两层都是 Claude Code 内部行为，代理侧只会观察到「同一轮里连续多个请求」。**这是采用本方案后代理必须能承受的流量形态。**

---

## 5. 其他相关短语与分支（问题 4）

### 5.1 全部候选，及各自触发什么

| 字面量 | 谓词 | status 门 | 触发 |
|---|---|---|---|
| `prompt is too long` | `Eci` `L116763` → `jXr` `L414920` | **无** | 正文置 `Y9` → 反应式压缩 + 重发 |
| `input is too long for requested model` | `Eci` `L116764` → `jXr` | **无** | 同上 |
| `` input length and `max_tokens` exceed context limit `` | `Nxa` `L116770` → `qhr` `L414924` | **无** | 同上；**另有独立自愈**，见 §5.2 |
| `context window` | `Aci` `L116767` | **必须 413** | 正文置 `Y9` → 同上 |
| `capability_rejected: prompt_too_long` | `A3` `L116749` | 无（客户端）/ 413（`L415265` 那处） | 同上。Claude Code 网关内部协议，**不建议代理伪造** |
| `capability_rejected: max_tokens_context_overflow` | `A3` via `qhr` | 无 | 同上 |
| `request_too_large` | `PvE` `L414899` | —— | 媒体剥离路径，非上下文超限 |

### 5.2 `max_tokens` 溢出是唯一会**自动改参数重发**的一条

`L273383`–`L273387`（`B9f`）逐字：

```js
  function B9f(e) {
    if (e.status !== 400 || !e.message) return;
    if (!qhr(e)) return;
    let t4 = /input length and `max_tokens` exceed context limit: (\d+) \+ (\d+) > (\d+)/, r2 = e.message.match(t4);
    if (!r2 || r2.length !== 4) return;
```

`Ftw` 的第 7 条（`L273469` 附近）认它为**可重试**，`L273326`–`L273335` 算出 `availableContext = C - A - 1000`，若 `< I9f = 3000` 放弃，否则设 `maxTokensOverride` 后 `continue`（不计重试次数）。

这条路径有**三重**门，缺一不可：**`status` 必须恰为 400**（`L273384`，这是本报告里唯一一处主动的 status 限定）、消息要过 `qhr`、且要匹配那个三捕获组正则拿到 `A + B > C` 三个数字。任一不满足就退回 §4 的压缩路径 —— 也就是说，只有关键词、没有数字，会被认成普通 prompt-too-long，走压缩而非改参。**可据以行动。**

> 注意区分两件事：`qhr` 作为**识别**判据没有 status 门（§1.2），走的是「置 `Y9` → 反应式压缩」；`B9f` 作为**改参自愈**判据有 400 门。同一个 `qhr` 在两条链路上被复用，门不一样。

### 5.3 明确不存在的候选（空结果，含搜索模式）

在 `/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js` 上执行 `rg -c --no-heading -F '<模式>'`：

| 模式 | 命中行数 |
|---|---|
| `context_length_exceeded` | **0** |
| `too many tokens` | **0** |
| `exceeds the context` | **0** |
| `invalid_request_body` | **0** |
| `exceeds the context window` | **0** |
| `'context window'`（单引号字面量） | **0** |
| `` `context window` ``（反引号字面量） | **0** |

即：**OpenAI 系的 `context_length_exceeded`、以及用户实测那条消息的原句 `exceeds the context window`，Claude Code 完全不认识。** 上游返回的 `code: "invalid_request_body"` 同样不被读取。

另有几条含 `context` 的命中经逐条核对**与本链路无关**，已排除：`L309509` 的 `/\b(too long|too large|exceeds|token limit|prompt is too long)\b/i` 属于 Auto 模式的输出分类器（另一个子系统）；`L311302` 的 `return "context_limit"` 属于后台 agent 的目标循环；`L372557` / `L489773` 是 `/config` 的设置说明散文。

---

## 6. 反向问题：不含那个短语会怎样（问题 6）

### 6.1 探针实测

`260824-cc-context-limit-predicate-probe.mjs` 把 `makeMessage`、`A3`、`Eci`、`Aci`、`Nxa`、`jXr`、`qhr`、`Mah` 以及 `YvE` / `Nnt` / `Tci` 的相关分支**逐字抄进 Node 脚本**，喂九种信封。关键三行：

| 信封 | `Eci` | `Aci` | `jXr` | `Mah` | 用户看到 | `Nnt` 归类 |
|---|---|---|---|---|---|---|
| **A** 400 + Copilot 原文（用户实测） | false | true | false | false | `API Error: 400 {"error":{"message":"Your input exceeds the context window of this model. ...` | **null** |
| **B** 400 + anthropic 信封 + Copilot 措辞 | false | true | false | false | `API Error: 400 {"type":"error","error":{...}}` | **null** |
| **C** 400 + anthropic 信封 + `prompt is too long` | true | false | true | false | **`Prompt is too long`** | `prompt_too_long` |

A 与 B 走到 `YvE` 的泛化兜底 `L415356`：

```js
    if (e instanceof $s) return Xd({ content: `${YA}: ${xlr(e)}`, error: "unknown" });
```

（`YA = "API Error"`，`L415528`。）

### 6.2 后果

正文变成 `API Error: 400 {...整串 JSON...}`，**不以 `Y9` 开头** ⇒ `rot()`（`L414877`）返回 false ⇒ `oo` 为 false（`L312755`）⇒ §4.3–§4.4 整条反应式压缩链**一次都不执行**。

同时 `Nnt(e)`（`L415388`）返回 `null`（探针实测），意味着遥测里连 `prompt_too_long` 这个类目都不会记。

**用户可观察的表现**：会话中出现一条丑陋的、把整个 JSON 塞进正文的 `API Error: 400 {...}`，对话停在那里。没有压缩、没有重试、没有 `/compact` 提示、没有 token 数字。用户只能自己判断这是上下文满了，然后手动 `/compact` 或 `/clear`。**可据以行动**（代码字面直证 + 探针实测双重确认）。

---

## 7. 跨版本适用性

`app.pretty.js` 三版本对照，字面量搜索（混淆后的函数名跨版本不稳定，因此全部按字面量定位）：

| 判据字面量 | 2.1.207 | 2.1.226 | 2.1.241 |
|---|---|---|---|
| `prompt is too long` | 有（`L169875`，`y8i`） | 有（`L124356`，`Oun`） | 有（`L116764`，`Eci`） |
| `input is too long for requested model` | **无（全文 0 命中）** | 有（`L124356`） | 有（`L116764`） |
| `context window` | 有（`L170148`、`L170251`，**内联在 413 分支**） | 有（`L124666`、`L124777`，同样内联在 413 分支） | 有（`L116767`，提炼为 `Aci`） |
| `` input length and `max_tokens` exceed context limit `` | 有（`L169878`） | 有（`L124359`） | 有（`L116770`） |
| `Prompt is too long`（常量） | 有（`L170354`，`w3`） | 有（`L124883`，`QV`） | 有（`L415528`，`Y9`） |
| `capability_rejected` | **0** | **0** | 2（`L116836` 定义 + 1 处文档） |

要点：

1. **`context window` 不是 2.1.241 新增的**，2.1.207 起就在，且**三个版本都同样被 413 挡住**（`L170251` / `L124777` / `L116817`+`L415265` 逐条核对）。我在调查中途一度以为它是新增判据，被跨版本对照推翻。
2. **`prompt is too long` 是三版本唯一的最大公约数**，且在 400 与 413 下都成立。要兼容旧版，就用它。
3. `input is too long for requested model` 只对 **≥ 2.1.226** 有效，2.1.207 完全不认。
4. `capability_rejected:` token 层是 2.1.241 独有；对旧版是无害的普通文本。

结论的适用限度：以上仅覆盖这三个版本。判据是**未文档化的内部实现**，Anthropic 随时可改，本项目不应把它当作稳定契约，而应当作「当前实测的兼容目标」。**可据以行动，但需随版本复测**（复测锚点：字面量 `prompt is too long`）。

---

## 8. 官方文档（仅旁证，不作判据）

`https://platform.claude.com/docs/en/api/errors`（2026-08-24 取）：

- 400 → `invalid_request_error`；413 → `request_too_large`，且文档明确说 413 指的是**请求字节数**超限（Messages API 32 MB），**不是 token 数超限**。
- 文档**没有**为「上下文窗口超限」定义任何专门的 status 或 `error.type`。
- 错误信封形状为 `{"type":"error","error":{"type":..., "message":...}}`，与 §2.1 的推导一致。
- 文档建议「Catch the SDK's typed classes rather than string-matching error messages」—— 而 Claude Code 在这条链路上**恰恰是靠字符串匹配**。这正好印证本项目的既有认知：**判据是客户端的解析器，不是协议规范。**

因此：把 status 从 400 改成 413 **不是**更「符合规范」的做法（413 在规范里是字节数超限），且没有必要 —— 主判据本就不看 status。

---

## 9. 对本项目的可行动建议

按「代理要在翻译路径上把上游的上下文超限改写成 anthropic-messages 表达」这个目标：

1. **必要且充分的一条**：让改写后 body 的 `error.message` 里含（小写化后的）子串 `prompt is too long`。这一条覆盖 2.1.207 / 2.1.226 / 2.1.241 三个版本，且不依赖 status。
2. **建议的完整形状**，能同时喂饱识别、诊断数字与用户文案：

   ```json
   {"type":"error","error":{"type":"invalid_request_error","message":"prompt is too long: <实际tokens> tokens > <上限> maximum"}}
   ```

   其中 `<实际tokens> tokens > <上限>` 这一段用于满足 `rno` 的正则（`L414880`），让用户看到具体数字（§4.5）。抠不到数字不影响压缩，只是文案退化。
3. **status 保持 400**。改 413 无收益（主判据不看 status），且与官方语义（413 = 字节数超限）冲突。
4. **不要**依赖 `context window` 这个词 —— 它只在 413 下生效，且没有覆盖旧版之外的额外好处。
5. **不要**伪造 `capability_rejected: prompt_too_long` —— 那是 Claude Code 网关侧内部 token，只有 2.1.241 认，属于越界模仿内部协议。
6. `error.type` / `error.code` 写什么都不影响识别，按 anthropic 规范写 `invalid_request_error` 即可（`richest-context-flow`：上游原始的 `code: "invalid_request_body"` 建议保留在别处而非丢弃，但它对客户端行为无影响）。
7. **副作用要有心理准备**：识别成功意味着 Claude Code 会**自动压缩并重发**（§4.4），而且压缩内部还有两层各自的重试（§4.11）。代理侧要能承受同一轮对话里紧接着来的**若干个**请求，而不只是一个。
8. **验证方法不要看界面文案**：`Prompt is too long` 也可能来自 Claude Code 的本地拒发（§4.8），与代理无关。要确认改写生效，看代理是否收到了紧随其后的压缩后请求。
9. **用户若关掉了 auto-compact**（§4.9），识别照常但压缩与重发不发生。这不是代理能控制的，属于已知限制。

---

## 10. 未采纳 / 排除的路线

必须写下来，否则这些排除事后无从复原：

1. **`Aci`（`context window`）作为改写目标 —— 排除。** 它被 `Mah`（413）挡住，而我们的错误是 400。即便改成 413 也不划算：413 在官方规范里是字节数超限，且主判据 `Eci` 无 status 门、更宽、更兼容旧版。
2. **改用 HTTP 413 —— 排除。** 理由同上。另注意 2.1.241 里 413 的两条路径判据**不完全相同**（`Tci` `L116817` 用 `Aci || Eci`；`Mah` 路径 `L415265` 用 `Aci || A3`，不含 `Eci`），但这个不对称**在客户端不产生实际差异**，因为 `L415249` 的 `jXr`（含 `Eci`）排在 `L415265` 之前先短路。探针 case D（413 + `prompt is too long`）实测 via `L415249 jXr||qhr`，证实了这一点。**这条修正了协作 agent 报告里的一处推断**（该报告据代码形状认为这类 413 会被判成 `request_too_large`，实测不成立）。
3. **伪造 `capability_rejected:` token —— 排除。** 见 §9.5。
4. **依赖 `error.type` / `error.code` —— 排除。** 全链路无任何消费点；`invalid_request_body` 全文 0 命中。
5. **`Tci`（`L116816`）一度被误当成客户端判据 —— 排除。** 追它的三个调用点（`L646698` / `L646708` / `L646992`）发现全在网关消毒路径 `lR0` / `ro_` 里，产出 `capability_rejected:` token 给下游客户端消费。本项目不经过它。**这是本次最大的假锚点** —— `Tci` 长得最像「上下文超限分类器」，而且它确实是，只是站在另一侧。
6. **常规 auto-compact 阈值机制 —— 查明后排除出主线。** `autoCompactWindow` / `Elr` / `Sco`（`L374239`）那一套由本地 token 记账在请求前触发，与错误响应无关，代理影响不到。保留在 §4.6 是为了防止把两种机制混为一谈。
7. **`promptTooLongIsHandled` 一度被当成行为开关 —— 排除。** 读 `pfl` 函数体（`L274286`）后确认：`M = b && I === "prompt_too_long"`，作用仅是**抑制错误日志与遥测**，不改变任何行为。
8. **`L309509` 的 `/\b(too long|too large|exceeds|token limit|prompt is too long)\b/i` —— 排除。** 属于 Auto 模式权限分类器的转录超限判断（`oMn` 那条 `Auto mode classifier transcript exceeded context window` 文案的同一子系统），不是 API 错误链路。**容易误命中**，因为它字面上同时含 `exceeds` 和 `prompt is too long`。
9. **`strings-n6.txt` 与压缩版 `app.js` —— 全程未使用。** 前者无代码结构、无法区分判据与散文；后者单行、行号不可复核。所有结论仅取自三份 `app.pretty.js`。
10. **2.1.241 的 `L583xxx`–`L648xxx` 段 —— 排除出代码结论。** 该段是 bundle 内嵌的 `claude-api` skill markdown 文档。涉及本主题的命中（`L648035`、`L648307`、`L648400`）已逐条标注为文档非代码。
11. **未验证反应式压缩的运行时表现。** §4.3–§4.4 全部由代码字面读出，**未实际跑一次真实的超限请求观察压缩是否发生**。判定为**可据以行动**（每一跳都有逐字赋值点），但若要更强的保证，锚点是遥测事件名 `tengu_reactive_compact_triggered` 与 `tengu_ptl_surfaced_to_user`。
12. **未展开 `Kto` / `w2` / `hvl` 等 token 记账函数的内部。** 它们决定「压缩后能省多少」，与「能不能被识别」正交，ROI 不足，主动放弃。

---

## 11. 协作 agent 报告的处置

本次并行派了两个调查 agent，其结论**未整体照单全收**，逐项处置如下：

| 来源 | 结论 | 处置 |
|---|---|---|
| 版本对照 agent | 三版本字面量清单与 `manifest.json` 版本确认 | **采纳**，构成 §7 |
| 版本对照 agent | 「`context window` 是 2.1.241 新增」——其自身报告已自我更正为「207 起就有，241 只是提炼成函数」 | **采纳更正后的版本** |
| 版本对照 agent | 「走 `Mah` 那条路的 413，若消息只写 `prompt is too long` 会被判成 `request_too_large`」 | **驳回**。该推断只读了 `L415265` 的代码形状，漏了 `L415249` 的 `jXr`（含 `Eci`）排在其前面先短路。探针 case D 实测证伪。见 §10.2 |
| 自动压缩 agent | 反应式压缩链路（`rot` → `trigger:"ptl"` → `reactive_compact_retry`） | **采纳**，且我已独立逐跳复核过同样的行号与原文，两条独立路径结论一致 |
| 自动压缩 agent | 本地硬拦截 `blocking_limit`（`L312326`） | **采纳**，已逐字复核，构成 §4.8。这是我自己那条线索没查到的，价值最高的一条补充 |
| 自动压缩 agent | UI 文案 `Context limit reached · /compact or /clear to continue`（`L476856`） | **采纳**，已逐字复核，构成 §4.10 |
| 自动压缩 agent | `t_l` 含 `mL()`，auto-compact 关掉则反应式路径一并失效 | **采纳**，已逐字复核，构成 §4.9 |
| 自动压缩 agent | 内层两层自愈（`pOm` / `DFi`） | **采纳**，构成 §4.11 |
| 自动压缩 agent | `j1m` 位于 `L368789`，判据在 `L368792` | **更正为 `L368790` / `L368793`**。`rg -n` 与 `sed -n` 两种取号方式在本机一致指向后者，该 agent 的行号整体偏移一格 |
| 自动压缩 agent | 建议「伪造 `capability_rejected: prompt_too_long` 比抄英文文案更稳」 | **驳回**。那是 Claude Code 网关侧内部 token，只有 2.1.241 认（226/207 命中 0），代理伪造属于越界模仿内部协议，稳定性反而更差。见 §9.5 |
