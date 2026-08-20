# 候选：`config.example.yaml` 未覆盖、而旧配置在用的功能

> 本文是候选素材，无效力。
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

## 一、端点在 `MAIN.md` 列了，配置项不在

以下四节的端点都写在 `MAIN.md` 的「运维与调试端点」里，但 `config.example.yaml` 没有对应配置。

| 旧配置节 | 控制什么 | 对应端点 |
|---|---|---|
| `history.db_path` / `success_limit` / `failure_limit` / `reaper_interval` / `websocket` | SQLite 历史库位置、保留条数、回收间隔、WS 推送开关 | `/history/api/*`、`/history/ws` |
| `approval.enabled` / `timeout_seconds` | 人工审批开关与等待超时 | `/api/approval/*`、`/api/approval/ws` |
| `observability.log_level` / `log_format` / `tracing_enabled` / `tracing_endpoint` / `tui_enabled` | 日志、OTel、TUI | `/metrics` |
| `tokenization.state_path` / `snapshot_root` / `flush_interval` | 校准状态与快照的落盘位置与频率 | `/api/tokenization/*` |

**提案**：四节按原样进入新 schema，键名沿用旧的即可——它们与规格里其他节不冲突。

## 二、机制缺配置

### hook 列表项的语义与单 hook 超时

**旧**：可信 module loader 按配置加载 hook 模块，可禁用单个 hook，单 hook 有超时。

**新**：`hooks` 一节已有六个订阅点，但**列表项指什么没有说明**（模块路径？已注册订阅者的 id？），实现暂按 `list[str]` 建模、无消费者。**单 hook 超时**也没有承载。

### token 来源

**旧**：`auth.github_token`（CLI 直给）、`auth.show_github_token`。

**新**：无承载。CLI/env/file 三个 provider 的**顺序与启用与否**也仍是硬编码（`composition.build_github_token_source()`）。

### generic 上游

**旧**：`upstream.type: copilot | generic` 加 `openai_base_url` / `anthropic_base_url` / `api_key` / `auth_type`，可直连任意 OpenAI 兼容上游。

**新**：`model_providers.*.type` 目前只有 `github_copilot` 一个合法值。`MAIN.md` 的 `app.model_provider` 抽象为它留了位置，配置面还没开。

## 三、已实现但新规格未提的守卫

### 常驻字节预算

**旧**：`openai_responses.global_resident_bytes` / `request_resident_bytes`，配对启用、request ≤ global 的全局内存 admission 与背压。

**新**：只有 `client_delivery.buffer_cap_bytes`（单响应累计上限）。两者**不是同一件事**：前者是跨请求的全局预算，后者是单响应的守卫。

### `anthropic.route_override`

**旧**：全局配置，强制走 Messages 或 Responses。

**新**：用 `model@format` 后缀取代。语义相近但作用域不同——一个是部署级默认，一个是单次请求。是否仍需要部署级的那个，需要用户判断。

## 四、判定为「改名重组、无需新增」的部分

以下旧字段在新规格中有对应物，切换时照搬即可，不在本文的缺口范围内：

`upstream.ghc_api_base_url` → `model_providers.*.base_url`；`upstream.proxy` → 顶层 `proxy`；`upstream.max_connections` / `keepalive_expiry` / `http2` → `upstream_transport`；`timeouts.*` → `upstream_request_timeouts.*` 与 `client_delivery.client_request_deadline`；`model_overrides` + `model_mappings` → `model_mappings`；`disabled_models`、`model_refresh_interval` → `model_providers.*`；`headers.*` → `GhcClientConfig` 默认值；`anthropic.thinking_*`、`poisoned_thinking_*` → `hook_fix_anthropic_request.thinking.*`；`anthropic.beta_strip_headers` → `hook_strip_anthropic_request_headers`；`anthropic.use_upstream_count_tokens` → `inbound.anthropic_count_tokens.providers`；`shutdown.*` → `graceful_cleanup_timeout` 与 `client_request_deadline`。

以下旧字段对应规格中**被注释掉的**配置项，按「被注释项暂不实现」处置：`anthropic.tool_search`、`anthropic.request_header_blacklist` / `whitelist`、`anthropic.response_header_*`、`openai_responses.normalize_call_ids`。

以下对应已裁决不接线的 WS：`openai_responses.upstream_ws` / `ws_queue_size` / `max_ws_frame_bytes` / `max_client_ws_connections` / `max_upstream_ws_connections`。

## 五、实施建议

监听地址已就位（规格已标注为不支持热重载），入口切换不再被硬阻断。剩余顺序：

1. 补第一节的四个运维配置节（否则历史、审批、可观测、tokenization 一起失效）；`history` 现只有 `enabled`，其余五项仍缺
2. 第二节的三项机制配置（hook 列表项语义与超时、token 来源的其余部分、generic 上游）可与切换并行，缺失期间用代码内默认值，并在切换说明里列明
3. 第三节两项交用户判断是否保留
