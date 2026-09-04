# 这台机器的自动压缩阈值是 967,000 tokens

日期：2026-08-24
作者：主会话（Claude Opus 5），代码判据逐条自核；`~/.claude.json` 的 env 注入、失败熔断、`/context` 输出三条来自 general-opus 取证（`260824-cc-autocompact-same-version-divergence.md`）并经复核
适用版本：Claude Code 2.1.241
前置：`260824-why-autocompact-did-not-fire.md`（其主线对本机不适用，已在该文件头部更正）

## 结论

用户 `~/.claude/settings.json` 的 `env` 块里有：

```
CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000
CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000
CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000
```

推导链（行号为 2.1.241 的 `app.pretty.js`）：

1. `_9:155275` 的第一个分支就是 `process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW`。1000000 落在合法区间 `[cyi=1e5, OFa=1e6]` 内，于是 `return { window: Math.min(o4, 1e6), configured: 1e6, source: "env" }`。**来源恒为 `"env"`**，`zzw` 的 `X3e` 门（要求来源不是 `"auto"`）永远放行。
2. `o4 = FC(model, betas)`（`:73384`）。`NBd()` 要求 `DISABLE_COMPACT` 才让 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 直接生效——未设，返回 undefined。`rha` 依赖 `KPr()`＝`accountCreditLatches.longContext1mCreditsBlocked()`（`:4350`），这是运行时由账户信号置位的闩，经 Copilot 代理不会置位，所以不夹回 20 万。于是落到 `FBd`。
3. `FBd:73400`：
   - `IA(e)`＝`/\[1m\]/i.test(原始模型名)`（`:73330`）→ 名字带 `[1m]` 直接 **1e6**；
   - `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 那条（`:73406`）带一个前缀判断 `!$o(vs(e)).startsWith("claude-")` —— **只对不以 `claude-` 开头的模型名生效**，于是 `gpt-5.6-sol` / `gpt-5.6-terra` / `gpt-5.6-luna` 全部拿到 **1e6**；
   - 都不命中才是 `y2r = 200000`（`:73454`）。
4. `KSe:155301`：effectiveWindow = window − `min(Hlr(model), 2e4)` = 1,000,000 − 20,000 = **980,000**。
5. `lyi:155197`：无 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`（settings.json 里那行的键名是 `"// CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"`，被注释掉了），阈值 = effectiveWindow − 13,000 = **967,000**。
6. `PFa:155205`：warn 在 947,000，blocked 在 `n1p(model) − 3000` = 977,000。

对照：不带 `[1m]` 的 `claude-` 模型走 200,000 窗口 → 阈值 167,000，压缩正常。

**所以这个差别按会话用的模型名走，不按机器走**，但表现得非常像机器差异。本机 transcript 里 `claude-opus-5` 的单次输入总量最高到过 1,567,011 tokens，与 96.7 万这个阈值同一量级。

## 实测定案（2026-08-24，另一台机器的 `/context`，模型 `gpt-5.6-sol[1m]`）

```
920.9k/1m tokens (92%)
⛝ Autocompact buffer: 33k tokens (3.3%)
Auto-compact window: 1m tokens
```

三点各自说明一件事：

- `Autocompact buffer: 33k` ＝ `20,000 + 13,000`，与本文第 4、5 步逐项吻合，阈值确为 **967,000**。
- `Auto-compact window:` 这一行**存在**，所以来源不是 `"auto"`——那道门放行了，判定在正常运行。行文光秃秃无标注，与 `source: "env"` 一致（`CLAUDE_CODE_AUTO_COMPACT_WINDOW` 在 settings.json 里）。
- 当前 920.9k，**距阈值还差约 46k**。

**所以「未触发压缩」是正确行为，不是缺陷——它确实还没到。** CC 自己的提示也写着 "Autocompact will trigger soon"。真正的问题是阈值本身太高：967,000 是 200k 模型默认阈值（167,000）的 5.8 倍。

`gpt-5.6-sol[1m]` 有**两条独立的路**通向 1e6 窗口，这一点决定了怎么修：

1. `IA(e)`（`:73330`）—— 名字含 `[1m]`；
2. `:73406` —— `gpt-5.6-sol` 不以 `claude-` 开头，`CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000` 直接生效。

**因此对 gpt 系模型，只把 `[1m]` 去掉不起作用**，第二条仍然给它 1e6。唯一有效的杠杆是 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`，因为 `_9` 取 `min(模型窗口, 它)`：设 400000 → 阈值 367,000；设 200000 → 阈值 167,000（合法区间 `[1e5, 1e6]`）。代价是它**只有一个全局值**，会同时压低 `claude-opus-5[1m]` 的窗口。

### 一条不能拿来用的证据

本机历史库 49,824 次 `gpt-5.6-sol` 成功操作：输入总量中位 278,717、p95 736,648、最大 **920,916**，超过 967,000 的**零次**。

**这条不能用来证明上游吃不下 96.7 万**——没有超过阈值的样本，恰恰因为阈值就在那里，属于循环论证。它能说明的只有：这个模型上跑到 60 万～92 万是常态（超过 80 万的成功操作 1,121 次）。800k 以上按 25k 分桶是平滑衰减（400 / 240 / 230 / 162 / 89），没有堆在某个数上，所以也**看不到**上游硬顶的迹象。上游的真实上限本次未测。

## 现场判据：`/context`

**更正（2026-08-24，实测 `/context` 输出后）**：本节初稿引用的是 `:372555`，那不是 `/context` 用的渲染器——实测输出里没有它承诺的来源括号与 `capped to` 后缀。`/context` 走的是 `:497107`：

```js
$8t = IHo !== "auto" && ("Auto-compact window: " + (
  IHo === "experiment" || IHo === "clientdata" ? `auto (${ic(kde)} tokens)` :
  IHo === "unknown-model"                      ? `${ic(kde)} tokens (default for an unrecognized model)` :
                                                 `${ic(kde)} tokens`))
```

两点与初稿不同，都要紧：

1. **来源是 `"auto"` 时整行不渲染**（`IHo !== "auto" &&`）。所以「`Auto-compact window:` 这一行压根不出现」才是「本会话永不主动压缩」的判据，而不是某个后缀。
2. `env` / `settings` / `model-default` 三种来源都印**光秃秃的 `N tokens`**，没有任何标注，且 `kde` 是 `configured` 而非夹过的 `window`。所以这一行本身**分不出**是哪种来源，也不告诉你模型有没有把它夹低。

真正给出有效窗口的是仪表本身。实测本机（`claude-opus-5[1m]`）：

```
920.9k/1m tokens (92%)
⛝ Autocompact buffer: 33k tokens (3.3%)
Auto-compact window: 1m tokens
```

`33k = 20,000 + 13,000`，即 `min(Hlr, 2e4)` 的输出预留加 `lyi` 的 13,000——**与本文第 4、5 步的推导逐项吻合**，阈值确为 967,000。所以判读顺序是：

| 看什么 | 读法 |
|---|---|
| `Auto-compact window:` 这一行**有没有** | 没有 → 来源是 `"auto"`，该会话永不主动压缩 |
| 仪表分母（`/1m` 还是 `/200k`） | 模型实际拿到的窗口 |
| `Autocompact buffer:` 的值 | 窗口减阈值；`33k` 对应 1m 窗口 |
| `Auto-compact is currently disabled (see /config)` | `mL()` 为 false |


## 「settings.json 一致」推不出「环境变量一致」

`applySafeConfigEnvironmentVariables`（`:191817`）先做 `Object.assign(process.env, filterSettingsEnv(cr().env, "globalConfig"))`——`cr()` 是 `~/.claude.json`。**该文件顶层的 `env` 对象会被灌进 `process.env`**，而且排在各 settings 层之前。本机没有这个键（已查），另一台可能有。

这是我此前论证的一个真实缺口：比对 `~/.claude/settings.json` 相同，并不能得出两台机器的 `CLAUDE_CODE_*` 环境一致。

## 「判定说该压缩，却没压成」的通道

本地会话里 reactive 是唯一的压缩执行路径（取证报告第 9 点，我未独立复核）。`rvl:366200` 开头：

```js
if (o4?.consecutiveFailures !== void 0 && o4.consecutiveFailures >= _Om) return { kind: "failure_breaker_open" };
```

`_Om = 3`（`:366248`）。**连续 3 次压缩失败后整个会话不再压缩**，而前两次是静默的。这是唯一一条「阈值到了、判定也过了，却什么都没发生」的真实通道，症状与「未触发」不可区分。

## 未证之处

- 没有在运行中观察到 `effectiveWindow=980000`。`/context` 或 `zzw` 的日志行可证实或证伪。
- 未确认另一台机器的模型名、`~/.claude.json` 的 `env` 块、以及是否撞过 failure breaker。
- `ZU(e)`（`:73353`）也可能让某些 `claude-` 模型返回 1e6，我未追到底；对本案结论无影响，因为 `gpt-*` 已由 `:73406` 决定。
- reactive 是唯一执行路径这一条来自取证 agent，未独立复核。
