# 延后项：TUI 请求日志

本文件记录**已经想到、但本次未做**的事，以及为什么没做。用于避免下一次把同一个问题再想一遍，也避免有人误以为这些是遗漏。

权威来源：`spec.md`（行为契约）。本文件只登记尚未进入契约的候选。

## 0. Direct buffered `/chat/completions` provider observation 已进入 Spec，实施待闭合

**现状**：Responses upstream 已由统一 provider observer 覆盖 direct／translated 与 streaming／non-streaming；Direct buffered Chat仍没有生产接线，reasoning、tool calls、finish reason与usage尚未进入完成行和durable response observation。

**行为已不归本台账决定**：用户于2026-09-05明确把TUI／durable observation纳入direct buffered Chat retry同一工作，规范已写入 [`spec.md`](spec.md) 与 [`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §10，架构见 [`../direct-buffered-chat-completions/design.md`](../direct-buffered-chat-completions/design.md)。本条只记录尚未实现，不重复转述字段、排序或展示合同；冲突时以上述Spec为准。

**关闭条件**：Chat streaming、native non-stream JSON与capability驱动的streaming→buffered JSON三种production入口都从最终attempt的同一typed facts生成observation；discarded attempt不泄漏；console与schema v2测试通过。实现完成后删除本条，不保留空号补位。

**证据强度**：静态调用链足以确认当前缺口并据此行动；没有真实upstream cassette，因此mock integration只证明本代理接线，不证明真实provider shape频率。

## 3. `[GONE]` 分不出「客户端走了」与「我们自己关停了」

**现状**：三种结局里最后一档由「两个标记都没置上」判定——`_tracked_delivery` 的 `async for` 既没正常跑完（`drained`），也没抛出异常（`failure`），也就是 GeneratorExit 或 CancelledError 从 `yield` 处展开。这同时覆盖两件事：客户端按 Esc 或断线走人，以及**关停时本进程取消自己的在途流**。后者里客户端还在，走掉的是我们。

**为什么措辞仍然成立**：detail 写的是 `delivery stopped before upstream finished`——没人收到答案、交付先于上游结束，两种情形都为真。`[GONE]` 同理：都不是本代理或上游的过错。所以这不是错误，是**分辨率不足**。

**要做需要什么**：让关停路径在取消在途流之前给 `_StreamAccounting` 留一个标记（关停是本进程自己发起的，它知道自己在做什么），再在 `_ending()` 里多一档。技术上不难，难在判断值不值：关停时终端通常正在被 SIGTERM 收走，那批行有没有人读是个问题。

**判断**：**证据强度仅为「已想到」，未观测到任何人因此误判过**。不建议在没有真实困扰之前做——多一档就多一个要维护的词，而这条区分只在关停这一个窗口内有意义。若将来关停诊断成为议题，这是现成的接入点。

## 4. 计数行说不出上游是怎么失败的

**已解决的那半**：`provider(local)` 原本合并了「没有上游计数器」「上游被问了却答不出」「运维配成只估算」三种情形。2026-08-20 由用户裁决，改为 `provider(no-counter,local)` / `provider(ghc-failed,local)` / `provider(local)`，判定在 `handle_count_tokens` 里做（依据是它自己传出的 `upstream_absent_reason` 与尝试轨迹里有没有 `ghc:` 条目）。见 `spec.md`「一次计数请求怎么读」。

**仍然没有读者的那半**：`ghc-failed` 说不出是超时、429 还是 500，也说不出重试了几次。这些都躺在 `context.extras["count_tokens_attempts"]` 里（形如 `ghc:0:APIStatusError`），**至今没有任何消费者**。

**做法**：把 `count_tokens_attempts` 带进 `_Trace` → `RequestLine` → JSONL 结构化记录，**不上控制台行**——`request_id=` 这个 join key 就能回答「那次到底怎么失败的」，而行宽不变。上控制台会把最长的那个字段放进最常见的端点，不建议。

**为什么没做**：`ghc-failed` 已经把「要不要看一眼」这个判断交付给读者了，剩下的是排障时才需要的细节，而排障时结构化记录本来就在手边。**证据强度：已想到，未观测到有人因此卡住过。**

**来源**：`archive-count-tokens-line/reports/260820-review-count-tokens-log-line.md` F6，以及更早的 `../token-counting/history/260820-review-count-tokens-shared-pipeline.md:72`（后者属另一切片）。
