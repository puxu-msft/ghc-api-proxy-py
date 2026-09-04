# 配置系统

## 加载与约束

配置优先级为：defaults < YAML < environment < CLI。环境变量前缀为 `GHC_`，嵌套分隔符为 `__`。`AppSettings` 与所有 section 均 frozen、`extra="forbid"`。

完整默认配置可用 `python -m app start --generate-config` 生成。以下为当前 settings 的权威分类。

## 顶层

| 键 | 默认 | 说明 |
|---|---:|---|
| `host` | `127.0.0.1` | 监听地址 |
| `port` | `4141` | 监听端口 |
| `debug` | `false` | 调试模式 |
| `model_overrides` | opus/sonnet/haiku aliases | 快捷模型别名 |
| `model_mappings` | `{}` | 通用模型映射 |
| `disabled_models` | `[]` | 隐藏模型 ID |
| `sanitize_tool_names` | `false` | 跨协议 tool name 清洗 |
| `model_refresh_interval` | `600` | 模型目录刷新秒数，0=关闭 |

## Sections

### `upstream`

`type`、Copilot/Generic base URLs、API key/auth type、连接池、timeouts、HTTP/2 和 proxy。

### `auth`

GitHub token、account type、token file 与日志脱敏开关。

### `headers`

VS Code/Copilot/API 版本伪装值。

### `anthropic`

| 键 | 默认 | 说明 |
|---|---:|---|
| `use_upstream_count_tokens` | `true` | Anthropic count endpoint 上游精确计数优先 |
| `thinking_block_message_policy` | `preserve` | Thinking 块策略 |
| `thinking_block_sanitize` | `all_empty` | 空 thinking 清理模式 |
| `thinking_destack_strategy` | `move_blocks` | 相邻 thinking 去堆叠 |
| `poisoned_thinking_quarantine` | `true` | L3 内存 quarantine |
| `poisoned_thinking_ttl_hours` | `72` | 滑动 TTL |
| `tool_search` | `true` | Copilot tool-search 声明注入 |
| `tool_search_non_deferred` | `[]` | 保持 eager 的普通 client tools |
| `warmup` | `allow` | allow/reject/drop/fake |
| `strict_request_headers` | `false` | 请求头白名单模式 |
| `strict_response_headers` | `false` | 响应头白名单模式 |
| `*_header_blacklist/whitelist` | 见生成配置 | Header policy |

不提供原生 server-tool 配置或代理侧历史截断配置。

### `hooks`

| 键 | 默认 | 说明 |
|---|---:|---|
| `modules` | `[]` | 可信 Python module 列表 |
| `disabled` | `[]` | 按完整 name 禁用可选 hooks |
| `timeout_ms` | `5000` | 用户 hook 单次调用 timeout |
| `deduplicate_tool_calls` | `false` | 注册可选内容签名去重 built-in |

Module 或顺序变更需要重启。用户 hook 与代理同进程同权限执行，不提供 sandbox。

### `tokenization`

| 键 | 默认 | 说明 |
|---|---:|---|
| `state_path` | `""` | 空值使用 XDG data/tokenization.json |
| `flush_interval` | `5.0` | dirty state 周期 flush 秒数 |

### 其他 sections

- `approval`：enabled、timeout。
- `history`：enabled、success/failure limits、reaper、db path、WebSocket。
- `rate_limiter`：enabled、retry/request/recovery intervals、consecutive successes。
- `timeouts`：stream/response header/upstream/stale/deadline。
- `observability`：log level/format、tracing endpoint、TUI。
- `openai_responses`：call ID、WS queue/frame/concurrency。

## 示例

```yaml
anthropic:
  use_upstream_count_tokens: true
  tool_search: true

hooks:
  modules:
    - my_proxy_hooks
  disabled:
    - builtin:strip_read_tool_result_tags
  timeout_ms: 5000
  deduplicate_tool_calls: false

tokenization:
  flush_interval: 5
```

## 安全

`/api/config` 会将 GitHub token 和 upstream API key 替换为 `***`。不要把 secrets 写入用户 hook module 或日志。

## 相关文档

- [Hooks 机制](hooks-system.md)
- [Tokenization](tokenization.md)
- [项目结构](project-structure.md)
