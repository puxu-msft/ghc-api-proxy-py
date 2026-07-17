# Feature Negotiation 内存缓存

`FeatureNegotiationStore` 是轻量的进程内 TTL 缓存。当前实现用于记录上游拒绝的已知能力值，查询为 O(1)，不在请求路径执行磁盘 I/O。

## 类别

当前类别共 9 个：

- `features`
- `betas`
- `efforts`
- `effortUnsupported`
- `deferredTools`
- `partnerFeatures`
- `systemRejectModels`
- `toolFields`
- `cacheControlSubfields`

原生 server-tool 类别已删除。未知类别不会被当作已支持能力注册；调用显式 `learn()` 或 `is_active()` 时会返回 `ValueError`，避免拼写错误静默污染缓存。

## Entry 语义

每个 `(category, key, value)` 保存：

- `first_learned_at`
- `last_confirmed_at`
- `pinned`
- `manually_expired`

默认情况下，entry 在 `last_confirmed_at + ttl` 后失效。Pinned entry 始终有效；手工过期 entry 立即无效；再次学习会刷新确认时间并清除手工过期标记。

`active_values()` 返回静态配置值与当前 active learned values 的并集。

## 当前范围

当前 Python 实现只提供内存 store 和管理路由占位快照，不宣称具有旧设计中的版本化持久化、按类别 TTL、完整写管理 API或 server-tool 自愈。若后续扩展，必须保持：

- 请求路径只读内存。
- 持久化 off-event-loop、serialized、atomic replace。
- 未知持久化类别可跳过，但显式运行时 API 的未知类别要报错。

## 相关文档

- [Anthropic 兼容](anthropic-compat.md)
- [Tool Use](tool-use.md)
- [配置系统](config-system.md)
