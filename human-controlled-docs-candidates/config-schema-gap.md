# 候选：`config.example.yaml` 与现有实现的对照

> 本文是候选素材，无效力。对照基准为 `docs/.human-controlled/config.example.yaml`（2026-08-22 版）、`src/app/config/settings.py`（旧 `AppSettings`）与 `src/app/config/schema.py`（新 `ProxyConfig`）。
>
> 依据 `docs/.human-controlled/README.md:3` 的规则：与文档相违背的既有内容需用户再次裁决；不矛盾的继续使用，用户将按需追认。
>
> **2026-08-22 更新。** 原文引用的 `MAIN.md` 已被拆分（`module-org.md` / `api.md` / `request-pipeline.md` / `message-translation.md` 等），本文的规则出处相应改指 `README.md:3`。同时按 `.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md` 的逐条对账撤下了已采纳项与因 continuation 放弃而失效的条目，各处留有一行记录。

## 一、结构对照

| 规格中的节 | 现有位置 | 差异 |
|-----------|---------|------|
| `server.tls.*` | 无 | 全新 |
| `inbound.anthropic_count_tokens.providers` | `anthropic.use_upstream_count_tokens: bool` | 布尔 → provider 链（`[ghc, local]`）＋ `max_retries` |
| `model_mappings` | `model_mappings` ＋ `model_overrides` | 见第三节「模型映射无内置默认」与「日期后缀不再自动剥离」两行 |
| `model_providers.<name>.*` | `upstream.*`、顶层 `disabled_models`、顶层 `model_refresh_interval` | 单上游 → 具名多 provider；`disabled_models` 与刷新间隔下沉到 provider 内 |
| `default_ghc_api` | 无 | 全新 |
| `pidfile_dir` | 无 | 全新（standalone）。规格 2026-08-22 由 `pidfile`（文件）改为 `pidfile_dir`（目录），实现已跟进，见 [pidfile-port-scoping.md](pidfile-port-scoping.md) |
| `graceful_cleanup_timeout` | `shutdown.graceful_timeout`、`shutdown.drain_timeout` | 语义重定义，见第三节「退出时限的命名」一行 |
| `proxy`（顶层，覆盖所有出站） | `upstream.proxy` | 作用域从上游扩到全部出站请求 |
| `upstream_transport.*` | `timeouts.upstream_keepalive`、`upstream.keepalive_expiry` | 拆为 TCP keepalive 与 HTTP/2 PING 两项 |
| `upstream_request_timeouts.*` | `timeouts.*` | 默认值反转，见第三节「上游超时默认值」一行；新增 `upstream_request_deadline` |
| `upstream_request_retry.*` | 无对应 | 全新：具名策略表、`max_total`。**原先此格还写着「continuation」，2026-08-22 撤下**——`upstream-retry-and-continuation.md` 已把「代理内续写」标为已放弃，规格里也不再有 `continuation` 与 `max_tokens_as_retryable` 两块 |
| `rate_limiter.*` | `reactive_rate_limiter.*` | 基本一致；规格无 `enabled` 字段 |
| `client_delivery.*` | 散落于 `anthropic.*`、`openai_responses.*`、`timeouts.request_deadline` | 收拢为一节；新增 `buffering_policy`、`buffer_cap_bytes`、`hedge` |
| `hook_*` 各节 | `anthropic.*` 下的大量布尔 ＋ `hooks.modules` | 从「散落配置项」变为「具名 hook 各自的配置」 |

## 二、仍需用户裁决

### C-1 `buffer_cap_bytes` 与既有的 16 MiB 裁决

**规格**：`config.example.yaml:391-393` 的 `client_delivery.buffer_cap_bytes: 16777216`，语义是「累计缓冲超此字节即放弃该响应」。

**既有裁决**：`.dev/docs/anthropic-responses-bridge/architecture.md:656` 的 U1 行——用户曾重裁「16 MiB 不是架构阈值，不设计超大 block 专属状态机、per-block threshold、disk spill」。同文件 `:664` 的 U3 行（2026-08-19）又覆盖了 U1 的容量机制部分：字节级内存预算整体删除，进程级改以并发数封顶（`proactive_rate_limiter.max_inflight`），**per-request 的 `buffer_cap_bytes` 明确保留**。

**判断**：两者**不矛盾**，且 U3 已经正面确认了保留。新规格是**整条响应的累计上限**且处置是「放弃」，不是 per-block 阈值，也没有专属状态机或落盘。

**待确认**：确认这一理解，即 `buffer_cap_bytes` 是单一的累计守卫，不重新引入按块大小分叉的路径。（U1／U3 都记录在开发文档里而非用户亲笔文档，所以这一条仍列为待确认，而不是已裁决。）

### ~~C-2 continuation 与「post-commit 不得透明重放」~~（2026-08-22 撤下）

原问题是「`config.example.yaml` 里的 continuation 规格是否即构成 `architecture.md` 要求的那个独立 ADR」。**前提已消失**：`docs/.human-controlled/upstream-retry-and-continuation.md:42` 现将该节标题写作「代理内续写（已放弃）」，规格里的 `upstream_request_retry.strategies.continuation` 也已从 `config.example.yaml` 删除。既然不再打算做，就不需要那个 ADR。

代理内续写的替代物是同文件 `:28-40` 的「MCP-driven 合成续写」——它不在代理内静默重投，而是把中断合成为一个 `tool_use` 块交给客户端，由客户端调用 MCP 后自行续写。这条路径与「post-commit 不得透明重放」不冲突（它根本不透明）。

### C-3 热重载的粒度

**规格**：`config.example.yaml:24`「除非另有说明，所有设置均支持热重载」，并逐项标出不支持热重载的例外。

**现状**：`ProxyConfig` 为 frozen 快照。`ConfigProvider`（`src/app/config/provider.py`）实现了整树切换、以及「消费者在开始一件工作时取快照并保持到该工作结束」这一语义——即**在途请求沿用受理时的那一版**。这是实现时选定的语义，规格未表态。

但这只是**已实现、未接线的快照原语**：`rg -l 'ConfigProvider|pin_restart_only' src --glob '*.py'` 只命中 `provider.py` 自身（2026-08-22 复算仍然如此），生产路径没有任何地方持有 provider、调用 `reload()`，请求也不从它取快照。所以热重载的缺口不止「触发机制」一项，provider 整体尚未接入。

**待裁决**：确认这一粒度语义。另外，**触发机制**（信号还是文件监视）规格与实现都还没有。

## 三、规格已定案，剩余的是实现缺口

以下各项规格或用户已经裁决，新 `ProxyConfig` 侧已按裁决实现。**入口已于 2026-08-17 切换**（`cli.py` 的 `start`，`--fd` 除外），所以直接运行走的已是新侧；下表「旧实现的现状」记的是 `AppSettings` 那一侧的残留，它仍服务 `--fd`（systemd）路径与旧 `routes/`，退役时机另议，不需要再裁决一次。

| 项 | 裁决 | 旧实现的现状 |
|----|------|------------|
| 退出时限的命名 | 统一为 `client_delivery.client_request_deadline`（默认 3600） | `shutdown.graceful_timeout = 300` 等三个旧字段并存；`graceful_timeout.py` 常量另见 [existing-rulings.md](existing-rulings.md) C-1 |
| 上游超时默认值 | `response_header` / `stream_idle` 均为 0，新增 `upstream_request_deadline: 1200` | 旧默认仍是 300 |
| 模型映射无内置默认 | `model_mappings` 是唯一来源，无内置默认 | `settings.py` 的 `model_overrides` 仍带三条硬编码默认，且与 `model_mappings` 两字段并存 |
| 日期后缀不再自动剥离 | 自 2026/07/16 起必须显式配置 | `transform/model_resolver.py` 仍在剥；新的 `pipeline/model_resolution.py` 已不剥 |
| 配置文件路径 | 放 `$XDG_DATA_HOME`（用户明确裁决） | `paths.config_file_path()` 仍返回 `XDG_CONFIG_HOME`；新增的 `spec_config_file_path()` 已按裁决 |

## 四、规格要求、当前尚未具备的能力

下表只列**行为尚未实现**的项。以下几项曾列在此处，复核后确认已接入生产处理链，已移出：具名重试策略表的五个 reason 与按 reason 的预算（`src/app/pipeline/retry.py:62` 的 `RetryLedger`，由 `src/app/server/handler.py:180` 构造进 `LedgerBudget`）、`buffering_policy` 三档（`src/app/pipeline/delivery/blocks.py:93` 的 `BlockBuffer.add()`，由 `handler.py:517` 的 `deliver_blocks()` 与 `:636` 的 `delivery_buffer()` 传入）、**TLS 监听层**（`src/app/lifecycle/listener.py` 的 `FirstByteRoutingAdapter`，由 `src/app/lifecycle/entry.py:141` 构造；`mode: both` 用 `MSG_PEEK` 分流，单一模式不分流，按 2026-08-17 裁决让协议自然失败）、`hook_fix_anthropic_request.thinking` 的 `assistant_message_layout` 与 `strip_both_empty_thinking_blocks`（`src/app/pipeline/anthropic_request_hook.py:251-252`，由 `handler.py` 在**翻译之前**调用——`attempt.prepare` 时 payload 已是目标格式、没有 `messages` 可修）、`content_block_start_compat` 的 `signature_delta` 与 `false` 两档（`src/app/pipeline/delivery/formats/anthropic_messages.py:59` 的 `signature_frame()`，经 `StreamSettings` 由 `handler.py:631` 的 `stream_settings()` 读配置）。

**2026-08-22 撤下的两项**：

- `synthesized_response_headers_after_sec` 的计时——原文在此记它「已接入」。**该配置键已被用户裁决删除**（`docs/.human-controlled/upstream-retry-and-continuation.md:26`），`src/` 与 `config.example.yaml` 中均已无此名，记录一项不存在的键的实现状态没有意义。
- 上一版把 `signature_frame()` 记在 `pipeline/delivery/anthropic_sse.py`，该文件已不存在；现址为 `pipeline/delivery/formats/anthropic_messages.py:59`，上面一段已改过来。

**count_tokens 的 provider 链**另属一类，单独说明：链已接入**新处理链**（`src/app/server/handler.py:236` 的 `handle_count_tokens()`，由 `src/app/server/pipeline_app.py` 按 `route.count_tokens` 调用；本地档的校准状态取自 `src/app/config/paths.py:42` 的 `tokenization_state_path()`，由 `src/app/server/composition.py:321` 装配，未新增配置键）。**入口已于 2026-08-17 切换**：`cli.py` 的 `start`（`--fd` 除外）现在构造 `create_pipeline_app`，所以 `inbound.anthropic_count_tokens` 的 `providers` 与 `max_retries` 对直接运行的真实流量已生效。

| 能力 | 规格位置 | 备注 |
|------|---------|------|
| 对冲请求（hedge） | `config.example.yaml:399-407` 的 `client_delivery.hedge` | 300 秒无块交付则并发重复请求，先返回有效块者胜；配置字段存在于 `src/app/config/schema.py:289`，`rg -n 'hedge' src --glob '*.py'` 除 schema 外**无任何命中**，即无消费者 |
| `cache_control` 四档与 `extended_cache_ttl` | `hook_fix_anthropic_request` | 现有实现无对应开关 |
| `strip_all_thinking_blocks_on_reject` | `hook_fix_anthropic_request.thinking` | 兜底重试 ＋ (session, agent) 中毒记忆；`anthropic/thinking/strip_all.py` 与 `quarantine.py` 有既有件，新链未接 |
| `context_editing` | 同上 | Anthropic `context_management` 的服务端上下文编辑 |
| `fix_malformed_unicode_escape` | `hook_fix_anthropic_sse` | **无任何既有实现**（仅配置字段），需新写 |
| `rewrite_refusal` | `hook_fix_anthropic_sse` | `end_reason=refusal` 是 Anthropic 的 stop_reason，主要落在 Anthropic 直通路径而非主干（Anthropic→Responses）；未实现 |
| `content_block_start_compat: redacted_thinking` | `hook_fix_anthropic_sse.thinking` | 规格只描述了 `signature_delta` 的行为，这一档语义未定义。实现**显式抛错**而非静默当成别的档（`src/app/pipeline/delivery/formats/anthropic_messages.py:91`）——需要用户定义它的语义 |

**因 continuation 放弃而撤下的两行**（2026-08-22）：

- ~~continuation 的续写请求构造~~ —— `upstream_request_retry.strategies.continuation` 已从规格删除，`pipeline/retry.py` 里的 `continuation_messages()` 也已随之删除（`rg -n 'continuation_messages' src tests` 无命中）。缺口连同它的规格一起消失了。
- ~~`max_tokens_as_retryable`~~ —— 该键在 `config.example.yaml` 与 `src/app/config/schema.py` 中均已不存在，被 `hand_over_stop_reasons` 取代（`config.example.yaml:339`、`schema.py:187`）且已接线。

## 五、已裁决事项

已裁决的条目不再列在候选文档中，裁决记录见 [existing-rulings.md](existing-rulings.md) 第三节。

## 六、与既有实现相容、可直接沿用的部分

`reactive_rate_limiter` 四项数值、`stream_idle_overrides` 的按模型覆盖与具体度规则（literal 子串 > glob > `*`，同类取最长键）、`beta_strip_headers` 的按模型剥离、thinking 的 `assistant_message_layout` 与 `strip_all_thinking_blocks_on_reject`（现有 `thinking_destack_strategy` 与 `poisoned_thinking_*` 对应）、`content_block_start_compat`（现有 signature 兼容层对应）——这些在现有实现中已有等价物，重构时是**改名与归位**，不是新建。

## 七、`stream_idle` 的注释措辞（部分已采纳，剩余提案见末尾）

**现状。** 守卫已接在新 pipeline 流式路径上：`src/app/server/pipeline_app.py:620-621` 用 `stream_idle_seconds(chain)` 包住 `response.aiter_bytes()`，同一形态另见 `:686` 与 `:746-747`。它计的是**上游还在不在发送**，而不是解析出的事件数。裁决于 2026-08-20：接受上游用 SSE 注释帧保活。

依据是两类都会让「字节在流动、事件为零」的情形，按事件计都会被判成静默：

- 注释帧（`: ping`）——`read_events`（`src/app/pipeline/delivery/sse_source.py:65`）按 SSE 规范丢弃它，它不产生任何事件。这个项目自己对客户端就是这么做的（`src/app/pipeline/delivery/stream.py:27` 的 `PING_FRAME`）。
- **一个大事件尚未收齐**——分段到达期间字节持续流动，完整事件要到最后一段才出现。这一条不依赖上游的任何行为假设，只需要事件足够大。

实测（`.dev/docs/delivery-keepalive/reports/260820-research-pipeline-idle-timeout.md`，原路径 `docs/tmp/` 已于 2026-08-21 迁入 `.dev/docs/`）：`stream_idle=1` 时，每 0.6 秒一个注释帧、持续 2.4 秒后正常结束 → 不触发；同样 2.4 秒的真静默 → 触发。

**已采纳的部分（2026-08-22 核对）。** `config.example.yaml:303` 现为：

```
  # 单次尝试上游，SSE 活动之间的最大间隔秒数（0 = 不超时）。适用于所有流式路径。
```

与本文提案的中文首行**逐字一致**——「事件之间」已改为「活动之间」，「适用于所有流式路径」也已补上。

**仍然打开的部分。** 英文行 `config.example.yaml:304` 仍写作：

```
  # Each upstream attempt: Max seconds between SSE events (0 = no timeout). Applies to all streaming paths.
```

即适用范围那半句已采纳，而 `SSE events` → `SSE activity` 这半句没有。中英两行现在对同一个量给出不同的口径，读英文的人仍会以为它按事件计。**建议只改这一处**：

```
  # Each upstream attempt: max seconds between SSE activity from upstream (0 = no timeout). Applies to all streaming paths.
```

两行解释性注释（「计的是上游还在不在发送，不是解析出的事件数……」及其英文）未被采纳，本文不再重提——如果用户觉得一行措辞已经够了，那就够了；上面那半句的中英不一致才是需要处理的。

其余三处措辞（`stream_idle_overrides` 的具体度规则、`0 = 禁用`、「单次尝试上游」）与实现一致，无需改动。
