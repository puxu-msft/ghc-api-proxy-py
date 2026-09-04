# 为什么同一份 settings.json，一台机器不触发自动压缩

> **2026-08-24 更正（本文写成当天）**：用户随后告知两台机器**都是 2.1.241**，且其 `settings.json` 的 `env` 块设了 `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000`。这两件事各废掉本文主线的一半——
> 1. 版本差异不成立（两台同版本）；
> 2. 更根本的是，`_9` 的**第一个分支**就是 `process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW`（`:155278`），命中即 `return { …, source: "env" }`。来源既然不是 `"auto"`，下文那道 `X3e` 门根本拦不住，未知模型名那整套推理对该用户不适用。
>
> 该用户的实际情形写在 `260824-autocompact-window-is-one-million.md`：`CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000` 只对不以 `claude-` 开头的模型名生效（`FBd:73406`），加上模型名带 `[1m]` 同样走 1e6（`IA:73330`），使 `gpt-5.6-*` 会话的 compact 阈值变成 967,000 tokens。
>
> **本文以下内容仍然正确，但只适用于没有设 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 的环境。** 保留原文不改写，作为该条件下的机制记录。

日期：2026-08-24
作者：主会话（Claude Opus 5），基于 `.dev/docs/tmp/260824-cc-autocompact-trigger-forensics.md`（general-opus 取证）并逐条复核
性质：客户端行为取证。结论对 Claude Code 2.1.207 / 2.1.226 / 2.1.241 三个抽出版本成立。

## 结论

自动压缩的判定是 `zzw`（`app.pretty.js:366191`，2.1.241 行号），第四道门是：

```js
if (VSe() && !X3e(t4, r2)) return false;
```

`X3e(model, window)` 即 `_9(model, window).source !== "auto"`（`:155295`），`VSe()` 在非远程会话恒为 true（`:155145`）。**所以只要自动压缩窗口的来源解析成 `"auto"`，本地会话就永不主动压缩**，压缩改由 reactive 路径在撞上限之后才发生。

窗口来源怎么解析，**三个版本不一样**：

| 版本 | 未知模型名的 `source` | 结果 |
|---|---|---|
| 2.1.207 | `"auto"`（`:298844` 兜底，该版本的窗口解析里**没有** `unknown-model` 分支） | 不主动压缩 |
| 2.1.226 | `"unknown-model"`（`:131321`） | 有具体窗口，会压缩 |
| 2.1.241 | `"unknown-model"`（`:155292`） | 有具体窗口，会压缩 |

2.1.207 的窗口解析在 `:298833-298844`，六个分支依次是 env、settings、clientdata、experiment、model-default（两条）、auto 兜底，没有第七条。

**这条路径对本项目的用户是可达的**：本机 transcript 里 `gpt-5.6-sol` 出现 56,858 次、`gpt-5.6-terra` 228 次、`gpt-5.6-luna` 100 次——这些模型名 Claude Code 不认识，窗口查找必然落空。

2.1.226+ 的 `unknown-model` 分支还有一个环境变量开关 `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT`（`:155292` 条件的第二项）。**设了它就退回 `"auto"`，于是新版也不压缩**——这是第二个跟机器走、不跟 settings.json 走的输入。

## 现场可读的判据

`zzw` 在门之后立刻打一行日志：

```js
E(`autocompact: tokens=${s} level=${a.level} effectiveWindow=${KSe(t4, r2)}`)
```

**这行日志排在那道门后面**，所以它的缺席本身就是判据：看得到这行 → 门放行了，是阈值没到；完全看不到 → 被 `"auto"` 那道门短路了。

## 其他跟本机走、不在 settings.json 里的输入

- `autoCompactEnabled` 可以落在 `~/.claude.json` 的**顶层**（`ap` 的 legacyGlobalConfig 回退，`:92730`）。比对 `~/.claude/settings.json` 看不见它。
- `autoCompactWindowsCache` 存在 `~/.claude.json`（`:73415` → `cr()` → `Ib()` → `ex_()`），由 bootstrap 接口 `GET {BASE_API_URL}/api/claude_cli/bootstrap` 的 `auto_compact_windows` 填充（`:372738`、`:372679`）；该 URL **不读 `ANTHROPIC_BASE_URL`**。取证 agent 判断它在本案中不是主因（置信度中高）：表由 Anthropic 下发、只含 Claude 模型名，`gpt-*` 命不中。我未独立复核这一条。

## 与另一条机制的关系

这是「未触发压缩」的**第一因**，与另一条独立：客户端记录的锚点 usage 为 0 时，`eP` 会塌成「其后消息的本地估算」。实测本机主会话 transcript，gpt 系模型 777/19869（3.91%）的 assistant 消息 usage 总和为 0，claude 系只有 40/88349（0.05%）；而既有服务历史库里 14 万次成功操作中上游没报 usage 的只有个位数——数字是在送往客户端的路上丢的。详见 `260824-heterogeneous-count-tokens-measurement.md` 之外的会话记录。

两者都与 `/v1/messages/count_tokens` 的高估无关：压缩不读那个端点。

## 复核记录与一处更正

取证报告称 2.1.207 对 `unknown-model` **零命中**。实测为 2 处（`:456214`、`:457018`），但都在 spend meter 的文案里，**窗口解析路径确实没有这个分支**——实质结论成立，措辞不准。其余承重断言（`zzw` 是判定入口、`X3e` 的定义、三版本分支差异、日志排在门后）均已逐条复核。

## 未证之处

- 没有在真实运行中观察到 `"auto"` 门短路（只读代码 + 版本对照）。用现场那行日志的有无即可证实或证伪。
- `autoCompactWindowsCache` 的生命周期结论来自取证 agent，我未独立复核。
- 未确认用户另一台机器的 Claude Code 版本与环境变量。
