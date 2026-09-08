# 候选：`config.example.yaml` 未覆盖、而旧配置在用的功能

> 本文是候选素材，无效力。
>
> **2026-08-22 更新**：按 `.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md` 的逐条对账，第一节由四节缩为两节（审批与 tokenization 端点已被用户标为「暂不支持」），第三节的「常驻字节预算」整条撤下（前提已被 2026-08-19 的重裁消除），并把原文对 `MAIN.md` 的引用改指拆分后的 `api.md` / `module-org.md` / `ghc-api.md`。
>
> 起因：把入口从旧 `AppSettings` 切到新 `ProxyConfig` 时，下列功能会**静默失效**——不是实现缺失，是新规格里没有承载它们的配置项。
>
> 复算方式：两个 pydantic 模型的叶子字段做差集，再逐项判断是「改名重组」还是「真的没有」。本文只列后者。
>
> 数字会随规格改动而变，不在此固化。要取当前值，跑：
>
> ```bash
> uv run python -c "
> from pydantic import BaseModel
> from app.config.schema import ProxyConfig
> from app.config.settings import AppSettings
> def leaves(m, prefix=''):
>     out = []
>     for name, f in m.model_fields.items():
>         ann = f.annotation
>         if isinstance(ann, type) and issubclass(ann, BaseModel):
>             out += leaves(ann, f'{prefix}{name}.')
>         else:
>             out.append(prefix + name)
>     return out
> old, new = set(leaves(AppSettings)), set(leaves(ProxyConfig))
> print(len(old), len(new), len(old - new))
> "
> ```

## 一、端点在 `api.md` 列了，配置项不在

**2026-08-22 收紧。** 原文以 `MAIN.md` 的「运维与调试端点」为出处，该文件已被拆分，端点清单现在在 `docs/.human-controlled/api.md:14-21`。**同时四节中有两节的前提变了**：`api.md:20` 的审批端点与 `:21` 的 tokenization 端点现在都被用户划掉并标注「暂不支持」。对这两节而言，「规格没有配置项」与「用户说暂不支持」是一致的，不再构成缺口——按既有裁决，暂不支持是对外行为的裁决，不是删除已实现代码的授权，旧 `AppSettings` 那一侧的实现留着即可。

**仍然是缺口的两节**：

| 旧配置节 | 控制什么 | 对应端点 |
|---|---|---|
| `history.db_path` / `success_limit` / `failure_limit` / `reaper_interval` / `websocket` | SQLite 历史库位置、保留条数、回收间隔、WS 推送开关 | `api.md:17` 的 `/history/api/*`、`/history/ws` |
| `observability.log_level` / `log_format` / `tracing_enabled` / `tracing_endpoint` / `tui_enabled` | 日志、OTel、TUI | `api.md:18` 的 `/metrics` |

规格侧 `config.example.yaml:413-414` 的 `history` 只有 `enabled` 一项，`observability` 一节全文不存在（`docs/.human-controlled/README.md:18` 列了一份 `observability.md`，但该文件尚未创建）。旧字段仍在 `src/app/config/settings.py:51-55` 与 `:120-124`。

**提案**：这两节按原样进入新 schema，键名沿用旧的即可——它们与规格里其他节不冲突。

**已随「暂不支持」裁决撤下的两节**（记录）：`approval.enabled` / `timeout_seconds`，`tokenization.state_path` / `snapshot_root` / `flush_interval`。tokenization 的校准状态路径目前由代码推导（`src/app/config/paths.py:42` 的 `tokenization_state_path()`），不经配置，与「暂不支持该端点」并行不悖。

## 二、机制缺配置

### hook 列表项的语义与单 hook 超时

**旧**：可信 module loader 按配置加载 hook 模块，可禁用单个 hook，单 hook 有超时。

**新**：`config.example.yaml:420-437` 的 `hooks` 一节已有六个订阅点（`on_client_request_parsed`、`on_upstream_request_ready`、`on_upstream_sse_block_ready`、`on_client_sse_block_ready`、`on_upstream_request_closed`、`on_client_request_closed`），六个都是裸 `[]`，但**列表项指什么没有说明**（模块路径？已注册订阅者的 id？），实现暂按 `list[str]` 建模、无消费者。**单 hook 超时**也没有承载。

> 同一件事也记在 [pipeline-subscriptions.md](pipeline-subscriptions.md) 的待决点 3。那边是从订阅机制一侧看，这边是从配置迁移一侧看；裁决时一并处理。

### token 来源

**旧**：`auth.github_token`（CLI 直给，`src/app/config/settings.py:32`）、`auth.show_github_token`（`:35`）。

**新**：无承载。CLI/env/file 三个 provider 的**顺序与启用与否**也仍是硬编码（`composition.build_github_token_source()`）。

> 这与 [uncovered-modules.md](uncovered-modules.md) 里「顶层 `auth/` 的来源链仍无模块位置」是同一件事的两面——一面是模块归属，一面是配置承载。`ghc-api.md:5-8` 只承载了 device flow 与 token 交换，没有承载来源链。

### generic 上游

**旧**：`upstream.type: copilot | generic` 加 `openai_base_url` / `anthropic_base_url` / `api_key` / `auth_type`（`src/app/config/settings.py:18-21`），可直连任意 OpenAI 兼容上游。

**新**：`config.example.yaml:150-152` 的 `model_providers.*.type` 目前只有 `github_copilot` 一个合法值。`module-org.md:15` 的 `app.model_provider` 抽象为它留了位置（注释明写「未来可能有其他提供方」），配置面还没开。

## 三、已实现但新规格未提的守卫

### ~~常驻字节预算~~（2026-08-22 撤下：前提已消失）

原文的诉求是「旧 `openai_responses.global_resident_bytes` / `request_resident_bytes` 是跨请求的全局预算，新规格只有单响应的 `client_delivery.buffer_cap_bytes`，切换会静默丢掉全局那一层」。

**这个前提不再成立**：用户已于 2026-08-19 重裁——字节级内存预算过细，进程级改以并发数封顶。记录见 `.dev/docs/anthropic-responses-bridge/architecture.md:664`（U3 行，覆盖 U1 的容量机制部分）。相应地：

- `src/app/delivery/reservation.py` 与两个 resident-bytes 配置项都已删除。复算：`rg -n 'global_resident_bytes|request_resident_bytes|reservation' src --glob '*.py'` 无命中。
- 进程级守卫改由 `proactive_rate_limiter.max_inflight` 承担（默认 50，`src/app/server/admission.py:25` 的 `InFlightLimit`），健康检查与 `/metrics` 豁免。

所以没有东西会在切换时被静默丢掉——旧实现已经不存在了。`buffer_cap_bytes` 作为 per-request 守卫按 U3 明确保留。关于 `proactive_rate_limiter` 在规格里的表述另见 [proactive-rate-limiter.md](proactive-rate-limiter.md)。

### `anthropic.route_override`

**旧**：全局配置（`src/app/config/settings.py:78`），强制走 Messages 或 Responses。

**新**：用 `model@format` 后缀取代。语义相近但作用域不同——一个是部署级默认，一个是单次请求。是否仍需要部署级的那个，需要用户判断。

## 四、判定为「改名重组、无需新增」的部分

以下旧字段在新规格中有对应物，切换时照搬即可，不在本文的缺口范围内：

`upstream.ghc_api_base_url` → `model_providers.*.base_url`；`upstream.proxy` → 顶层 `proxy`；`upstream.max_connections` / `keepalive_expiry` / `http2` → `upstream_transport`；`timeouts.*` → `upstream_request_timeouts.*` 与 `client_delivery.client_request_deadline`；`model_overrides` + `model_mappings` → `model_mappings`；`disabled_models`、`model_refresh_interval` → `model_providers.*`；`headers.*` → `GhcClientConfig` 默认值；`anthropic.thinking_*`、`poisoned_thinking_*` → `hook_fix_anthropic_request.thinking.*`；`anthropic.beta_strip_headers` → `hook_strip_anthropic_request_headers`；`anthropic.use_upstream_count_tokens` → `inbound.anthropic_count_tokens.providers`；`shutdown.*` → `graceful_cleanup_timeout` 与 `client_request_deadline`。

以下旧字段对应规格中**被注释掉的**配置项，按「被注释项暂不实现」处置：`anthropic.tool_search`、`anthropic.request_header_blacklist` / `whitelist`、`anthropic.response_header_*`、`openai_responses.normalize_call_ids`。

以下对应已裁决不接线的 WS：`openai_responses.upstream_ws` / `ws_queue_size` / `max_ws_frame_bytes` / `max_client_ws_connections` / `max_upstream_ws_connections`。

## 五、实施建议

监听地址已就位（规格已标注为不支持热重载），入口切换不再被硬阻断。剩余顺序（2026-08-22 重排，因第一节缩为两节、第三节缩为一项）：

1. 补第一节的两个运维配置节（`history` 的五个字段、`observability` 一整节），否则历史与可观测在新路径上失效
2. 第二节的三项机制配置（hook 列表项语义与超时、token 来源的其余部分、generic 上游）可与切换并行，缺失期间用代码内默认值，并在切换说明里列明
3. 第三节剩下的 `anthropic.route_override` 交用户判断是否保留部署级默认
