# Interaction context：当前合同

状态：**living**。本文只描述 2026-09-08 current source 已建立的可观察行为与接口 seam，并明确列出尚缺的验证和非目标。

## 0. 来源与效力

本文由 2026-09-07 的 point-in-time 设计比较稿提炼，并重新核对 current `src/`。原稿包含当日 HEAD、dirty WIP、推荐方案和未实施测试矩阵，已保真归档在 [`history/260907-interaction-context-design.md`](history/260907-interaction-context-design.md)；它不是 current authority。

本文没有把任何旧设计建议、WIP 状态或 agent 判断标为用户裁决。下列条款按证据分成：

- **current implementation**：current source 已实现，且本主题将其作为当前接口/行为合同记录；
- **仍待实现或验证**：实现看起来已具备，但缺少能独立钉住边界的测试，或合同本身尚未落地；
- **非目标**：本主题不拥有、也不据此改变的行为。

## 1. Identity 三分

### 1.1 Current implementation

| Identity | 载体与生命周期 | 当前用途 |
|---|---|---|
| 代理 request identity | `RequestContext.id`；每个 inbound HTTP request 构造一个 UUID，并由该 request 的全部 attempt 共用 | 代理内部请求关联；当客户端没有声明逻辑会话时，作为该 request 的 provider interaction fallback |
| 客户端 logical conversation identity | `RequestContext.interaction_id: str \| None`；从 inbound headers 抽取，`None` 表示客户端没有声明 | 对暴露 interaction binding 的 provider 提供客户端会话键 |
| GHC provider-instance fallback | `GhcApiClient._interaction_id`；构造 provider client 时确定 | provider-owned、没有 client request identity 的流量；current GHC catalog 与 Anthropic `count_tokens` 使用它 |

`RequestContext.provider_interaction_id: str | None` 不是第四种 identity。它是 request 内的 memoized resolution：第一次 provider send 调用 `interaction_id_for_provider()` 时，将 `interaction_id or id` 固定下来。之后即使 mutable subscriber 改写 `interaction_id`，同一 request 的 retry 或 delivery reopen 仍使用第一次解析出的 provider value。

### 1.2 可观察边界

- 客户端声明 identity 时，inference 的 provider binding 使用该值，不用 `RequestContext.id` 覆盖它。
- 客户端未声明 identity 时，pipeline inference 使用该 request 的 `RequestContext.id`；不同 HTTP requests 不共享一个进程级匿名 interaction。
- GHC inference 不允许悄悄退回 provider-instance fallback：`GithubCopilotProvider.send(..., interaction_id=None)` 在触网前失败。正常 driver 总是传入 `interaction_id_for_provider()` 的非空结果。
- `RequestContext.id`、client conversation identity 和 GHC provider-instance fallback 不互相充当同义名。

## 2. Inbound header 抽取

### 2.1 Current implementation

`app.pipeline.session_identity.INTERACTION_ID_HEADERS` 是唯一候选顺序。抽取按下列顺序选择**第一个 strip 后非空**的值：

1. `x-claude-code-session-id`
2. `x-session-id`
3. `x-conversation-id`
4. `x-chat-session-id`
5. `x-thread-id`
6. `x-interaction-id`

合同：

- header name 比较大小写不敏感；
- 值先 `strip()`；空字符串或纯空白不获胜，继续检查低优先级候选；
- 不合并多个候选，不按 UUID 形状打分；
- inbound 载体是 `Mapping[str, str]`，本层不另定义同名 multi-value 合并规则；
- `build_context()` 从原始 inbound headers 抽取 `interaction_id`；
- `forwarded_client_headers()` 先执行 credential/hop-by-hop floor，随后 `without_interaction_id_headers()` 从可转发 header bag 删除**全部六个候选名**；
- 删除后的 mapping 同时成为 `RequestContext.client_headers` 与初始 `source_headers`。因此已消费的 semantic identity 不再作为 direct extra header 或 translation source header 传播。

抽取 identity 与删除已消费 header 是 semantic consumption，不把这六个名字重新定义为 credential 或 security denylist。

### 2.2 仍待验证

current source 已实现六候选有序选择、case-insensitive 和 blank-skip，但测试目前只直接钉住 `x-claude-code-session-id` 胜过 `x-session-id`、并验证 identity 不留在 `client_headers`。仍需表驱动 unit tests 独立覆盖：

- 六个候选各自可单独命中；
- 混合大小写；
- 高优先级纯空白、低优先级非空；
- 无候选返回 `None`；
- 所有候选名均从 forwarded/source bags 删除。

## 3. RequestContext → provider → GHC seam

### 3.1 Current implementation

1. `server.inbound.build_context()` 写入 `RequestContext.interaction_id`，不生成匿名会话 UUID。
2. `RequestContext.interaction_id_for_provider()` 在第一次 send 时解析并 memoize `interaction_id or id`。
3. direct driver 的统一 `_send()` 调用：

   ```python
   provider.send(
       endpoint,
       payload,
       descriptor=descriptor,
       stream=context.stream,
       extra_headers=context.client_headers or None,
       interaction_id=context.interaction_id_for_provider(),
   )
   ```

4. `ModelProvider.send()` 公开可选 keyword-only `interaction_id: str | None = None`。它表达逻辑 interaction binding，不借用 `extra_headers` 的约定键。
5. `GithubCopilotProvider` 要求 inference 的 `interaction_id` 非空，并把同一个值下传到 Messages、Chat Completions、Responses 和 Embeddings GHC send method。
6. CodeBuddy、Xingchen、OpenAI-compatible provider 维持同一 protocol 签名，但明确忽略 `interaction_id`；driver 不按 provider type 分支。
7. `GhcApiClient.headers_for_interaction()` 将值写为 owned `X-Interaction-Id`。客户端 `extra_headers` 不能以任何大小写覆盖或并列注入 `Authorization`、`X-Interaction-Id` 等 owned headers。
8. 每次 GHC request 独立生成 `x-request-id`/`X-Agent-Task-Id`；它们不是 conversation identity。

## 4. 路径边界

### 4.1 Direct inference

**Current implementation。** Direct route 可以按 header policy 继续转发仍有意义的 client protocol headers，但六个 identity candidates 已在 inbound 阶段从 `client_headers` 删除。interaction identity 只通过显式 provider argument 到达 GHC owned `X-Interaction-Id`。

### 4.2 Translated inference

**Current implementation。** Translation 修改 payload，不拥有 interaction identity。`TRANSLATED_PATH_WHITELIST` 当前为空，translated route 不转发 client protocol headers；identity 已在 path policy 和 translation 之前进入 `RequestContext`，之后与 direct route 共用 `_drive()`、direct driver `_send()` 和 provider seam。因此 translation 不依赖把 session header 加回 whitelist。

现有 integration test 已钉住 Anthropic Messages → Responses 的 declared Claude session：上游 `x-interaction-id` 等于客户端值，原 `x-claude-code-session-id` 不在上游。

**仍待验证。** 缺少与 translated integration test 对称的 direct end-to-end 用例，直接观察 declared session 在 Messages 等 direct leg 上成为 owned `X-Interaction-Id` 且原候选 header 不出站。

### 4.3 Retry 与 delivery reopen

**Current implementation。** pre-header retry、限流返回后的 retry 和 torn-body delivery reopen 都继续使用同一个 `RequestContext`。`provider_interaction_id` 在第一次 provider send 后固定，因此后续 attempt 不重新从 mutable `interaction_id` 解析，也不生成新 interaction UUID。pre-header retry 的冻结行为已有 unit test。

**仍待验证。** delivery reopen 确实经 `replay_prepared()` 和同一 `_send()` seam 复用该 context，但尚缺一条专门观察 reopen 前后 provider interaction id 相同的测试。

### 4.4 Anonymous inference

**Current implementation。** 当六个候选都没有有效值时，`interaction_id is None`；第一次 provider send 把 `RequestContext.id` 固定为 `provider_interaction_id`。同一 HTTP request 的 retry/reopen 保持它，不同 HTTP requests 由各自 `RequestContext.id` 隔离。

现有 driver unit test 已钉住无 client identity 时 provider 收到 `context.id`。

**仍待验证。** 缺少 pipeline end-to-end 测试同时证明同一匿名 request 的多个 attempts 相同、两个匿名 HTTP requests 不同。

### 4.5 `count_tokens`

**Current implementation。** `ModelProvider.count_tokens()` 没有 `interaction_id` 参数，count path 不经过 inference `_send()`。GitHub Copilot 的 `send_anthropic_count_tokens()` 使用 GHC provider-instance fallback，而不是 inbound client identity 或 `RequestContext.id`。translated count 若目标协议没有 upstream counter，则走 local estimator，也不创建 conversation binding。

这是当前边界，不是“计数永远不得绑定 interaction”的用户裁决。

**仍待验证。** GHC client component test 证明 count request 使用 instance fallback；尚缺一条带 inbound session header 的 pipeline test，明确观察 client session 没有进入 count leg。

## 5. 非目标

本主题不据此改变：

- `REQUEST_FLOOR`、credential/hop-by-hop/forwarded-chain 安全策略；
- direct blacklist、translated whitelist 或 Anthropic beta flag policy 的一般规则；
- 从 `x-request-id`、`X-Agent-Task-Id`、`user-agent`、body metadata、`previous_response_id` 或 agent identity headers 推断 conversation identity；
- session store、TTL、跨进程持久化、UUID 格式校验或客户端 multi-value header 语义；
- provider routing、payload translation、retry eligibility/budget、delivery replay eligibility或 token estimator 算法；
- 给非 GHC provider 发明上游 session header；
- 把 `RequestContext` 改为 immutable，或为 subscriber 建立字段所有权；
- 让 client `extra_headers` 覆盖 GHC owned identity/credential headers；
- 自动把 `count_tokens` 归入客户端 conversation。若未来实测与明确产品决定要求绑定，必须显式扩展 count provider seam 和本 Spec，而不是从 extra headers 猜。

`session_identity.py` 当前还抽取 agent identity；agent identity 的候选、语义与消费路径不属于本 interaction-context Spec。
