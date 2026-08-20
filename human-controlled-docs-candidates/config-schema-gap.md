# 候选：`config.example.yaml` 与现有实现的对照

> 本文是候选素材，无效力。对照基准为 `docs/.human-controlled/config.example.yaml`（2026-08-15 22:35）与 `src/app/config/settings.py` 当前实现。
>
> 依据 `MAIN.md` 规则：与文档相违背的既有内容需用户再次裁决；不矛盾的继续使用。

## 一、结构对照

| 规格中的节 | 现有位置 | 差异 |
|-----------|---------|------|
| `server.tls.*` | 无 | 全新 |
| `inbound.anthropic_count_tokens.providers` | `anthropic.use_upstream_count_tokens: bool` | 布尔 → provider 链（`[ghc, local]`）＋ `max_retries` |
| `model_mappings` | `model_mappings` ＋ `model_overrides` | 见第三节「模型映射无内置默认」与「日期后缀不再自动剥离」两行 |
| `model_providers.<name>.*` | `upstream.*`、顶层 `disabled_models`、顶层 `model_refresh_interval` | 单上游 → 具名多 provider；`disabled_models` 与刷新间隔下沉到 provider 内 |
| `default_ghc_api` | 无 | 全新 |
| `pidfile` | 无 | 全新（standalone） |
| `graceful_cleanup_timeout` | `shutdown.graceful_timeout`、`shutdown.drain_timeout` | 语义重定义，见第三节「退出时限的命名」一行 |
| `proxy`（顶层，覆盖所有出站） | `upstream.proxy` | 作用域从上游扩到全部出站请求 |
| `upstream_transport.*` | `timeouts.upstream_keepalive`、`upstream.keepalive_expiry` | 拆为 TCP keepalive 与 HTTP/2 PING 两项 |
| `upstream_request_timeouts.*` | `timeouts.*` | 默认值反转，见第三节「上游超时默认值」一行；新增 `upstream_request_deadline` |
| `upstream_request_retry.*` | 无对应 | 全新：具名策略表、`max_total`、continuation |
| `rate_limiter.*` | `reactive_rate_limiter.*` | 基本一致；规格无 `enabled` 字段 |
| `client_delivery.*` | 散落于 `anthropic.*`、`openai_responses.*`、`timeouts.request_deadline` | 收拢为一节；新增 `buffering_policy`、`buffer_cap_bytes`、`hedge` |
| `hook_*` 各节 | `anthropic.*` 下的大量布尔 ＋ `hooks.modules` | 从「散落配置项」变为「具名 hook 各自的配置」 |

## 二、仍需用户裁决

### C-1 `buffer_cap_bytes` 与既有的 16 MiB 裁决

**规格**：`client_delivery.buffer_cap_bytes: 16777216`，语义是「累计缓冲超此字节即放弃该响应」。

**既有裁决**（记录于 `architecture.md` U1）：用户曾重裁「16 MiB 不是架构阈值，不设计超大 block 专属状态机、per-block threshold、disk spill」。

**判断**：两者**可能不矛盾**——新规格是**整条响应的累计上限**且处置是「放弃」，不是 per-block 阈值，也没有专属状态机或落盘。

**待确认**：确认这一理解，即 `buffer_cap_bytes` 是单一的累计守卫，不重新引入按块大小分叉的路径。

### C-2 continuation 与「post-commit 不得透明重放」

**规格**：`upstream_request_retry.strategies.continuation.enabled: true`——已有块提交给客户端后若中断，把已提交块作 assistant 轮、附一条 user 消息，让模型续写。

**既有裁决**（`spec.md` ADR-BRIDGE-05）：一旦外部 envelope 进入 accepted/uncertain，**禁止透明重放整条 generation**，必须显式 partial failure；`architecture.md` 另记「continuation 必须先形成独立 ADR 与 PoC 才能扩展」。

**判断**：continuation **不是**透明重放——它不重发原请求，而是构造一轮新的、包含已提交内容的请求。两者可以共存。

**待裁决**：确认 `config.example.yaml` 中的 continuation 规格即构成 `architecture.md` 所要求的那个「独立 ADR」，还是仍需单独立项与 PoC。

### C-3 热重载的粒度

**规格**：「除非另有说明，所有设置均支持热重载」，并逐项标出不支持热重载的例外。

**现状**：`ProxyConfig` 为 frozen 快照。`ConfigProvider`（`src/app/config/provider.py`）实现了整树切换、以及「消费者在开始一件工作时取快照并保持到该工作结束」这一语义——即**在途请求沿用受理时的那一版**。这是实现时选定的语义，规格未表态。

但这只是**已实现、未接线的快照原语**：`rg -l 'ConfigProvider|pin_restart_only' src --glob '*.py'` 只命中 `provider.py` 自身，生产路径没有任何地方持有 provider、调用 `reload()`，请求也不从它取快照。所以热重载的缺口不止「触发机制」一项，provider 整体尚未接入。

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

下表只列**行为尚未实现**的项。以下几项曾列在此处，复核后确认已接入生产处理链，已移出：具名重试策略表的五个 reason 与按 reason 的预算（`pipeline/retry.py` 的 `RetryLedger`，由 `server/handler.py` 的 `handle()` 构造进 `LedgerBudget`）、`buffering_policy` 三档（`pipeline/delivery/blocks.py` 的 `BlockBuffer.add()`，由 `handler.py` 的 `deliver_blocks()` 与 `delivery_buffer()` 传入）、`synthesized_response_headers_after_sec` 的计时（`pipeline/delivery/stream.py`，与既有的 SSE ping 共用同一个等待，不另开读取器；合成块**绕过** `BlockBuffer` 直接写出，否则 `full` 策略会把它扣到上游结束，等于没合成）、**TLS 监听层**（`lifecycle/listener.py` 的 `FirstByteRoutingAdapter`，`mode: both` 用 `MSG_PEEK` 分流；单一模式不分流，按 2026-08-17 裁决让协议自然失败）、`hook_fix_anthropic_request.thinking` 的 `assistant_message_layout` 与 `strip_both_empty_thinking_blocks`（`pipeline/anthropic_request_hook.py`，由 `server/handler.py` 在**翻译之前**调用——`attempt.prepare` 时 payload 已是目标格式、没有 `messages` 可修）、`content_block_start_compat` 的 `signature_delta` 与 `false` 两档（`pipeline/delivery/anthropic_sse.py` 的 `signature_frame()`，经 `StreamSettings` 由 `handler.stream_settings()` 读配置）。

**count_tokens 的 provider 链**另属一类，单独说明：链已接入**新处理链**（`server/handler.py` 的 `handle_count_tokens()`，由 `server/pipeline_app.py` 按 `route.count_tokens` 调用；本地档的校准状态取自 `config/paths.py` 的 `tokenization_state_path()`，由该 app 的 lifespan 负责 load／flush，未新增配置键）。**入口已于 2026-08-17 切换**：`cli.py` 的 `start`（`--fd` 除外）现在构造 `create_pipeline_app`，所以 `inbound.anthropic_count_tokens` 的 `providers` 与 `max_retries` 对直接运行的真实流量已生效。

| 能力 | 规格位置 | 备注 |
|------|---------|------|
| continuation 的续写请求构造 | `upstream_request_retry.strategies.continuation` | 预算已接线（见本节开头），但 `pipeline/retry.py` 的 `continuation_messages()` 只有测试调用者，处理链未据此重发 |
| `max_tokens_as_retryable` | `upstream_request_retry.strategies` | `end_reason=max_tokens` 触发续写；配置字段存在于 `schema.py` 的 `UpstreamRequestRetryConfig`，无消费者 |
| 对冲请求（hedge） | `client_delivery.hedge` | 300 秒无块交付则并发重复请求，先返回有效块者胜；配置字段存在于 `schema.py` 的 `ClientDeliveryConfig.hedge`，无消费者 |
| `cache_control` 四档与 `extended_cache_ttl` | `hook_fix_anthropic_request` | 现有实现无对应开关 |
| `strip_all_thinking_blocks_on_reject` | `hook_fix_anthropic_request.thinking` | 兜底重试 ＋ (session, agent) 中毒记忆；`anthropic/thinking/strip_all.py` 与 `quarantine.py` 有既有件，新链未接 |
| `context_editing` | 同上 | Anthropic `context_management` 的服务端上下文编辑 |
| `fix_malformed_unicode_escape` | `hook_fix_anthropic_sse` | **无任何既有实现**（仅配置字段），需新写 |
| `rewrite_refusal` | `hook_fix_anthropic_sse` | `end_reason=refusal` 是 Anthropic 的 stop_reason，主要落在 Anthropic 直通路径而非主干（Anthropic→Responses）；未实现 |
| `content_block_start_compat: redacted_thinking` | `hook_fix_anthropic_sse.thinking` | 规格只描述了 `signature_delta` 的行为，这一档语义未定义。实现**显式抛错**而非静默当成别的档——需要用户定义它的语义 |

## 五、已裁决事项

已裁决的条目不再列在候选文档中，裁决记录见 [existing-rulings.md](existing-rulings.md) 第三节。

## 六、与既有实现相容、可直接沿用的部分

`reactive_rate_limiter` 四项数值、`stream_idle_overrides` 的按模型覆盖与具体度规则（literal 子串 > glob > `*`，同类取最长键）、`beta_strip_headers` 的按模型剥离、thinking 的 `assistant_message_layout` 与 `strip_all_thinking_blocks_on_reject`（现有 `thinking_destack_strategy` 与 `poisoned_thinking_*` 对应）、`content_block_start_compat`（现有 signature 兼容层对应）——这些在现有实现中已有等价物，重构时是**改名与归位**，不是新建。

## 七、`stream_idle` 的注释措辞（提案，供直接摘取）

**现状。** 守卫已接在新 pipeline 流式路径上（`src/app/server/pipeline_app.py:286` 起，包住 `response.aiter_bytes()`），计的是**上游还在不在发送**，而不是解析出的事件数。裁决于 2026-08-20：接受上游用 SSE 注释帧保活。

依据是两类都会让「字节在流动、事件为零」的情形，按事件计都会被判成静默：

- 注释帧（`: ping`）——`read_events`（`src/app/pipeline/delivery/sse_source.py`）按 SSE 规范丢弃它，它不产生任何事件。这个项目自己对客户端就是这么做的（`src/app/pipeline/delivery/stream.py:18` 的 `PING_FRAME`）。
- **一个大事件尚未收齐**——分段到达期间字节持续流动，完整事件要到最后一段才出现。这一条不依赖上游的任何行为假设，只需要事件足够大。

实测（`docs/tmp/260820-research-pipeline-idle-timeout.md`）：`stream_idle=1` 时，每 0.6 秒一个注释帧、持续 2.4 秒后正常结束 → 不触发；同样 2.4 秒的真静默 → 触发。

**提案。** `docs/.human-controlled/config.example.yaml:296-297` 现写作「SSE 事件之间的最大间隔秒数 / Max seconds between SSE events」，与上述实现不符。建议替换为：

```yaml
  # 单次尝试上游，SSE 活动之间的最大间隔秒数（0 = 不超时）。适用于所有流式路径。
  # 计的是上游还在不在发送，不是解析出的事件数：注释帧与尚未收齐的大事件都会让字节持续到达而事件为零，按事件计会把仍在传输的连接判成静默。
  #
  # Each upstream attempt: max seconds between SSE activity from upstream (0 = no timeout). Applies to all streaming paths.
  # Activity, not parsed events: a comment frame and a large event still arriving both keep bytes moving while the parser yields nothing, so timing events would call a connection that is still transmitting silent.
  #
  stream_idle: 0
```

其余三处措辞（`stream_idle_overrides` 的具体度规则、`0 = 禁用`、「单次尝试上游」）与实现一致，无需改动。
