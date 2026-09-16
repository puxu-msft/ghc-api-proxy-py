# Phase 2 验收矩阵

> 从冻结 Spec 推导的用户可观察验收判据
>
> Spec 来源：
> - [IMPLEMENTATION_PLAN.md Phase 2](../../docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md#phase-2--核心管道最小闭环-walking-skeleton)
> - [streaming.md](../../docs/2604-rewrite/streaming.md)
> - [sanitize-pipeline.md](../../docs/2604-rewrite/sanitize-pipeline.md)
> - [anthropic-compat.md](../../docs/2604-rewrite/anthropic-compat.md)

## 验收判据清单

### A1. Messages 模型深层 extra/null 保真

**Spec 条款**：
- `anthropic.py`: 所有模型 `model_config = ConfigDict(extra="allow")` (IMPLEMENTATION_PLAN Step 2.1)
- "不丢弃未知字段" (IMPLEMENTATION_PLAN Phase 0 Step 0.5)

**验收项**：
- [ ] A1.1 顶层未知字段（如 `custom_field`）保留
- [ ] A1.2 嵌套 ContentBlock 的未知字段保留
- [ ] A1.3 tool_use input 中的未知字段保留
- [ ] A1.4 metadata/thinking 等深层对象的未知字段保留
- [ ] A1.5 null 值字段不被过滤

**验证方法**：构造含未知字段的请求，抓取 wire payload，确认字段保留

---

### A2. Tool Blocks 处理

**Spec 条款**：
- `process_tool_blocks`: 配对检查、孤儿过滤、name 修正 (sanitize-pipeline.md)
- `filter_empty_text_blocks`: 移除空 text 块 (sanitize-pipeline.md)

**验收项**：
- [ ] A2.1 配对完整的 tool_use/tool_result 保留
- [ ] A2.2 孤儿 tool_use（无配对 tool_result）被过滤
- [ ] A2.3 孤儿 tool_result（无配对 tool_use）被过滤
- [ ] A2.4 空 text 块（`text=""` 或 `text=None`）被移除
- [ ] A2.5 tool name 大小写修正

**验证方法**：构造含孤儿块/空块的请求，验证过滤结果

---

### A3. Raw Stream 未消费

**Spec 条款**：
- "使用 SDK 底层 `client.post(..., cast_to=httpx.Response, stream=True)` 拿原始 bytes" (IMPLEMENTATION_PLAN Step 1.3)
- "必须有回归测试确认 SDK 不消费 stream" (IMPLEMENTATION_PLAN Step 1.3 PoC 门禁)

**验收项**：
- [ ] A3.1 SDK response 的 `is_stream_consumed` 为 False
- [ ] A3.2 流可被多次迭代（未预读）

**验证方法**：Mock 上游，检查 response 状态

---

### A4. SSE 零缓冲直通

**Spec 条款**：
- "**P6 零缓冲**: SSE generator 逐 event yield,不攒完整响应" (IMPLEMENTATION_PLAN Step 2.2)
- "SSE 首块即时" (用户要求)

**验收项**：
- [ ] A4.1 首个 SSE event 在上游返回首块后立即下发（< 100ms）
- [ ] A4.2 SSE headers 正确：`text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`
- [ ] A4.3 断连时 cleanup 函数被调用
- [ ] A4.4 timeout 时流终止并清理

**验证方法**：时间戳测量、header 检查、断连模拟

---

### A5. Token Counting

**Spec 条款**：
- "**tiktoken startup 预载**: lifespan 阶段预先 `get_encoding("o200k_base")`" (IMPLEMENTATION_PLAN Step 2.4)
- "上游转发优先,本地估算回退" (IMPLEMENTATION_PLAN Step 2.4)

**验收项**：
- [ ] A5.1 `use_upstream=True` 时优先调用上游 `/count_tokens`
- [ ] A5.2 上游失败时降级到本地 tiktoken 估算
- [ ] A5.3 本地估算结果带 `estimated: true` 标记
- [ ] A5.4 tiktoken encoding 在启动时预载（不阻塞首次请求）

**验证方法**：Mock 上游成功/失败，检查返回值和 `estimated` 标记

---

### A6. Pipeline Success/Error States

**Spec 条款**：
- "管道 Executor 最小版" (IMPLEMENTATION_PLAN Step 2.5)

**验收项**：
- [ ] A6.1 成功路径：返回 HTTP 200 + SSE 流
- [ ] A6.2 失败路径：返回适当错误状态码（400/401/500等）+ 错误体
- [ ] A6.3 错误体符合 Anthropic 错误格式

**验证方法**：正常请求和异常请求的 HTTP 状态码检查

---

### A7. HTTP Endpoints

**Spec 条款**：
- "`POST /v1/messages`,`POST /v1/messages/count_tokens`" (IMPLEMENTATION_PLAN Step 2.6)

**验收项**：
- [ ] A7.1 `/v1/messages` 支持 `stream=false`（非流式）
- [ ] A7.2 `/v1/messages` 支持 `stream=true`（SSE 流式）
- [ ] A7.3 `/v1/messages/count_tokens` 返回 token 计数
- [ ] A7.4 非流式响应返回完整 MessagesResponse JSON
- [ ] A7.5 流式响应逐 event 返回（`message_start`, `content_block_*`, `message_delta`, `message_stop`）

**验证方法**：HTTP 请求测试

---

### A8. RuntimeState Bootstrap & DI

**Spec 条款**：
- "lifespan context manager 分阶段: config load → auth init → upstream init → ..." (IMPLEMENTATION_PLAN Step 0.6)
- "FastAPI DI 提供者骨架" (IMPLEMENTATION_PLAN Step 0.6)

**验收项**：
- [ ] A8.1 服务启动时 RuntimeState 初始化
- [ ] A8.2 `github_token_ready`, `copilot_token_ready`, `models_ready` 标志位正确设置
- [ ] A8.3 `/health/readiness` 反映 RuntimeState.is_ready
- [ ] A8.4 各组件（anthropic_client, token_counter）通过 DI 可用

**验证方法**：健康检查端点、进程级启动测试

---

## 未验证项（Spec 缺失/争议）

- **无**：Phase 2 的 Spec 完整且冻结

## 非阻塞项（可推迟验证）

- Feature negotiation（Phase 4）
- Thinking pipeline（Phase 4）
- Auto-truncate retry（Phase 5）
- Rate limiting（Phase 5）

