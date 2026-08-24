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

## 现场判据：`/context`

`:372555` 直接把窗口与来源印出来，不需要开 debug：

- `Auto-compact window: 1M tokens (from CLAUDE_CODE_AUTO_COMPACT_WINDOW)` —— 没有 `· capped to … by model` 后缀，说明模型窗口本身就 ≥ 1e6，阈值 96.7 万，**等于不压**；
- 同一行带 `· capped to 200k by model` —— 模型窗口是 20 万，阈值 16.7 万，正常；
- `Auto-compact is currently disabled (see /config)` —— `mL()` 为 false，另找原因。

`capped to` 后缀的条件是 `configured > window`（`:372555` 的 `i`），所以它的**有无**恰好就是这两种情形的判别式。

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
