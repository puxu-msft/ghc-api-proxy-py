# 候选：auto mode 授权判定请求的本地处置

给 `docs/.human-controlled/config.example.yaml` 的候选片段，以及一段供裁决的背景。用户自行取用，不取用也不影响实现——特性默认关闭。

## 一、背景：这个开关管的是什么

Claude Code 的 auto mode 打开后，**每一次即将执行的动作**（编辑文件、跑命令、派 subagent……）之前，客户端都会先发一次独立的、非流式的 `POST /v1/messages`，把「这个动作该不该放行」交给模型判断。这次调用与主对话共用同一个 base URL、同一套认证、同一批请求头，所以它会原样打到本代理上，并被当作普通请求转发给 Copilot。

**开销是实测的，不是估算的。** 本机前身服务的历史库里有 2300 条这样的真实请求（2026-07-25 ～ 08-13）。抽一条看：

| 项 | 值 |
|---|---|
| 上行字节 | 710179 |
| 其中 分类器 system prompt | 110851 字符 |
| 其中 用户 CLAUDE.md 全文 | 129683 字符 |
| 其中 会话转录 | 272750 字符 |
| 上游耗时 | 1759 ms |

每次工具调用付一遍。two-stage 模式下阶段 2 再付一遍（样本里 2247 条阶段 1、53 条阶段 2）。

本特性让代理认出这类请求并**就地作答**，不转发上游。

## 二、需要裁决的是什么

打开这个开关，等于**把 auto mode 的模型审查替换成一个常量**。代理读不懂被审查的动作，也不试图读懂——它不是一个更便宜的分类器，它是一个开关。

- `allow`：所有动作一律放行。auto mode 的 UI 与流程仍在，但审查环节恒真。效果接近 `bypassPermissions`，区别在于客户端仍以为自己在受审。
- `block`：所有动作一律拦下，退回人工确认。
- `passthrough`（默认）：照旧转发上游，即当前行为。

**客户端会把它显示成一次真实的模型判定。** 放行时 Claude Code 返回并展示 `Allowed by fast classifier`，还会把这次判定计入 auto mode 的遥测统计（含分类器类型与模型名）——它不知道是代理答的。所以界面上这一次放行与一次真实审查**长得一模一样**。当打开开关的人和使用客户端的人不是同一个（本项目的 subagent 场景就是），使用者没有任何本地信号能分辨。这是做决定时需要知道的后果，不是恐吓。

**另有一件事影响它现在有没有用**：本机 `~/.claude/settings.json` 当前是 `defaultMode: "bypassPermissions"`，该模式下客户端根本不调用分类器。所以在当前配置下这个开关无流量可处置——它是为「将来切换到 auto mode」准备的能力，不是当下生效的优化。打开后看不到任何命中是预期的，不是实现有问题。

## 三、候选片段

接在 `config.example.yaml` 现有 `inbound:` 段的 `anthropic_count_tokens` 之后。

```yaml
inbound:
  anthropic_count_tokens:
    providers: [ghc, local]
    max_retries: 2

  # Claude Code 的 auto mode 会在每个动作前发一次独立请求，让模型判断该不该放行。
  # 这类请求带着完整会话转录与 CLAUDE.md，实测单条 710 KB，且每次工具调用付一遍。
  # 本节控制是否由代理就地作答、不转发上游。
  #
  # Claude Code's auto mode sends a separate request before each action, asking a model whether to allow it.
  # Such a request carries the whole transcript and CLAUDE.md — one measured sample is 710 KB, spent once per tool call.
  # This section controls whether the proxy answers it locally instead of forwarding it.
  auto_mode_classifier:
    # passthrough = 照旧转发上游（默认）；allow = 一律放行；block = 一律拦下。
    # 注意 allow / block 是**固定答复**，代理不理解被审查的动作，也不试图理解。
    # 打开它等于把 auto mode 的模型审查换成一个常量，而不是换成一个更便宜的审查。
    #
    # passthrough = forward upstream as before (default); allow = always permit; block = always refuse.
    # Note that allow / block are **constant answers**: the proxy does not read the action under review and does not try.
    # Turning this on replaces auto mode's review with a constant — not with a cheaper review.
    decision: passthrough

    # 仅在 block 时写入回复的 <reason>；放行时分类器 prompt 要求不带 reason。
    # Written into <reason> on a block only; the classifier prompt asks for none when allowing.
    reason: "Blocked by proxy configuration, without a model review."

    # 两条识别标记，任一命中即算——但都不单独成立：还要求这个请求整体像一次分类器调用
    # （无 tools、非流式、没有 assistant 轮）。评审构造过两个合法的普通请求各自触发一个裸标记，
    # 那种情况下用户的真实请求会被答以一句伪造的决定、且永不发出，用户看不到发生了什么。
    #
    # 标记是**别人程序里的字符串字面量**，会随客户端升级失效，所以做成可配置——失效时改这里即可。
    # 识别失效的方向是「认不出 → 照常转发」，不会答错，只是不再省那 710 KB。
    # 注意还有一条与客户端升级无关的失效通道：客户端的服务端可以下发配置改掉分类器的模式和模型，
    # 客户端一个字节都不用变。版本号是看得见的，这个看不见。
    #
    # Two recognition markers; either one matching is enough, but neither fires alone — the request must also
    # be shaped like a classifier call (no tools, not streaming, no assistant turn). Review built two legal
    # ordinary requests that each tripped a bare marker; in both, the user's real request would have been
    # answered with a fabricated decision and never sent.
    #
    # They are string literals owned by another program and will decay when that program rewords them, which
    # is why they are settings. Decay in recognition means "not recognised → forwarded as usual": never a
    # wrong answer, only the bytes back. A second decay channel has no version number attached: the client's
    # own server can change the classifier's mode and model by pushed-down config, with the client unchanged.
    system_prompt_prefix: "You are a security monitor for autonomous AI coding agents."
    transcript_open: "<transcript>\n"
```

## 四、判据的证据强度（供判断要不要把字面量写进用户文档）

两条判据在两个独立方向上验证过：

- **流量侧**：2300 条真实请求全中；在 145781 条 operation 的库里，`You are a security monitor for autonomous AI coding agents.` 这句话只出现在分类器请求里，零误报。
- **代码侧**：Claude Code 2.1.207 / 2.1.226 / 2.1.241 三个版本的静态提取源码里逐字一致；用户自定义 auto mode 规则只替换 prompt 中部的占位槽，severity 模式只重写 Output Format 段，**都不动首行**。

明确**不可用**的判据（写在这里免得日后有人再试一遍）：`anthropic-beta: auto-mode-classifier-2026-07-16` 在反代场景下永远收不到——客户端只在 base URL 是 `api.anthropic.com` 时才发送它。`x-app: cli-bg` 判别力接近零（同期 6084 条里 5274 条是它）。其余请求头与主对话逐字相同。

完整规格与行号级出处：`.dev/docs/auto-mode-classifier/spec.md`。
