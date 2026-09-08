# GitHub Copilot 会话标识：显式请求上下文（长期方案）

- 日期：2026-09-07
- 范围：只读设计与审查。不修改 `src/` / `tests/`。
- 产出：推荐数据流、候选优先级、类型/API、provider 改动面、重试/翻译/直连语义、测试矩阵、明确不采用的方案。
- 非目标：凭证/安全 header 策略、`REQUEST_FLOOR` 扩表、多租户会话存储。

## 0. 对照事实（任务陈述 vs HEAD vs 工作区）

任务陈述描述的是「尚未抽出」的状态。核对 `/home/xp/src/ghc-api-proxy-py` 后，三层必须分开写，否则方案会打在错误的地面上。

### 0.1 HEAD（已提交，`git show HEAD`）

与任务陈述一致的部分：

- `RequestContext` 没有 `interaction_id`。
- `build_context` 只放入 `client_headers` / `source_headers`。
- `direct_driver.base._send` 只传 `extra_headers=context.client_headers`。
- `ModelProvider.send` 只有 `extra_headers`。
- `GithubCopilotProvider.send` 把 `extra_headers` 交给 `GhcApiClient`。

与任务陈述不一致、必须校正的部分：

1. **`GhcApiClient` 并不从 `extra_headers` 猜 interaction id。** HEAD 的 `request_headers()` 始终使用构造时的 `self._interaction_id`。`X-Interaction-Id` 属于 owned header，`extra_headers` 里同名键会被丢掉，其它会话头即使活到 extra 也不会改写 owned 字段。因此「把会话头放进翻译白名单」即使做了，也**不能**把 Claude Code 的 session UUID 变成上游 `X-Interaction-Id`。
2. **HEAD 的 `TRANSLATED_PATH_WHITELIST` 已经是空元组。** `message-format-reshape.md` 写「（暂无）」；`request_headers.py` 与之一致。任务里「当前把会话 header 加入翻译白名单」不是 HEAD 事实。`tests/int/test_pipeline_app.py` 仍有一句过期注释（「whitelist contains only session identity」），那是注释漂移，不是白名单内容。

HEAD 的真实缺陷因此更窄、也更硬：**客户端会话身份从未进入 Copilot 的 interaction binding。** 未带会话头的流量，整进程共用 `GhcApiClient` 构造时的一个 UUID（测试里常是 `"interaction"`，生产 `build_chain` 默认也曾是 `"interaction"`）。

### 0.2 工作区 WIP（未提交，且与其它改动混在一起）

工作区已经朝「显式字段」方向改了一轮，但 **git status 把 openai_compatible provider、schema、composition 接线混在同一份 dirty tree 里**。身份抽出本身可见于：

- 新模块 `src/app/pipeline/session_identity.py`
- `RequestContext.interaction_id`
- `build_context` 调用 `interaction_id_from_headers(inbound_headers)`
- `ModelProvider.send(..., interaction_id=)`
- `direct_driver._send` 透传 `context.interaction_id`
- `GhcApiClient.request_headers(interaction_id=...)` 覆盖构造期 fallback
- 若干测试（inbound / driver / ghc client / 翻译路径绑定）

本报告**不把 WIP 当作已定稿**。下面用三次对照设计独立选型；第 10 节再对照 WIP 的偏差。

---

## 1. 问题空间

### 1.1 要分开的三个名字

| 名字 | 生命周期 | 含义 | 谁消费 |
|------|----------|------|--------|
| `RequestContext.id` | 一次 HTTP 请求（含该请求的全部 retry / delivery 再打开） | 代理内部请求标识 | 日志、观测、内部关联 |
| `RequestContext.interaction_id` | 客户端的逻辑会话；一次请求内不变 | 客户端声明的 conversation identity | 仅「上游协议有 interaction binding」的 provider |
| `GhcApiClient._interaction_id` | 进程 / provider 实例 | 库在无人声明身份时仍必须写出 `X-Interaction-Id` | 仅 GHC 客户端的 fallback |

把三者合成一个 UUID，会在「Claude Code 多轮会话」和「curl 无会话头」之间选错。

### 1.2 约束

1. Copilot 上游请求**必须**带 `X-Interaction-Id`（`build_request_headers` 总是写入；缺身份头会被拒）。这是 GHC 客户端的协议义务，不是 HTTP 转发义务。
2. Claude Code 稳定会话 UUID 是 `x-claude-code-session-id`。参考实现还出现 `x-session-id`、`x-conversation-id`、`x-chat-session-id`、`x-thread-id`、`x-interaction-id`。
3. 会话身份**不是**协议协商头（`anthropic-beta` 那一类），也**不是**凭证。禁止把本方案扩成 `REQUEST_FLOOR` / 安全 denylist。
4. 直连与翻译共用同一个 send 缝（翻译改的是 body，不是另一套 `_send`）。身份必须在路由/翻译之前成为请求字段，否则翻译白名单一空，身份就丢。
5. 本代理是单 Copilot 账户、多客户端。进程级 UUID 当 fallback，会把所有匿名流量绑成同一场 Copilot 会话。
6. `RequestContext` 按既有裁定是可变记录，不为身份字段发明所有权规则。
7. `count_tokens` 不是一轮对话。默认不把会话身份绑到计数腿，除非将来有测量证明 Copilot 计数也按 interaction 分组。

### 1.3 依赖类别

抽出逻辑是 in-process 纯函数（header 名 → `str | None`）。GHC 写入 `X-Interaction-Id` 是 true external（Copilot）。不要为抽出再做 port；provider 协议上的可选 `interaction_id` 已经是那条外部缝。

---

## 2. 三次对照设计

按 codebase-design 的 DESIGN-IT-TWICE：同一加深对象给三个不同接口，再比 depth / locality / seam。

加深对象：把「客户端逻辑会话」从「可转发 HTTP 头袋子」里拿出来，变成请求上下文的一等事实。

### 设计 A — 最小接口（推荐）

**接口：**

- `interaction_id_from_headers(headers) -> str | None`
- `without_interaction_id_headers(headers) -> dict[str, str]`
- `RequestContext.interaction_id: str | None`（`None` = 客户端没声明）
- `ModelProvider.send(..., interaction_id: str | None = None)`
- 驱动在 send 时解析：`context.interaction_id or context.id`
- GHC：`interaction_id or self._interaction_id`（仅非 pipeline 调用才落到后者）

**调用方要学的：** 一个可选字符串。不知道源 header 名，不知道 Copilot 的大小写拼写。

**藏在缝后面的：** 候选名表、大小写、空白、多 header 同时出现时的优先级、从 extra 里剥掉已消费的身份头、owned `X-Interaction-Id` 的覆盖规则。

**Leverage：** 翻译、直连、retry、embeddings 都走同一字段。新客户端只要改候选表。

**薄的地方：** 非 Copilot provider 必须在签名上接受并忽略该参数（`del interaction_id`）。这是协议稳定的代价，不是深度不足。

### 设计 B — 最大灵活性

**接口：** `SessionIdentity(source_header, value, stability)` 值对象；每家 provider 自己映射到上游头；可插拔 extractor 注册表。

**Leverage 低：** 目前只有 Copilot 一个消费者，第二套 adapter 是假想缝。值对象把「一个字符串」摊成调用方必须理解的结构。

**何时才值得：** 出现第二家上游、且它要的不是「同一个 UUID 写成另一个头」——例如要 source 名、要 TTL、要和 body 里的 `previous_response_id` 合并。今天没有这个需求。

### 设计 C — 迁就最常见调用方（GHC 客户端）

**接口：** 继续让 `GhcApiClient` 从 `extra_headers` 猜；翻译白名单放行会话头；`RequestContext` 不动。

**这是 HEAD 缺陷的直接延长：**

- 身份与协议头政策绑在一起；白名单一空（或一改）身份就消失。
- owned `X-Interaction-Id` 本来就会挡住 extra 里的同名键；要猜，还得在 GHC 里写例外，让 extra 能覆盖 owned 字段——和「协议/身份头由本库拥有」的既有不变量冲突。
- 直连路径会把 `x-claude-code-session-id` 当作未知 extra 转发出去，同时 `X-Interaction-Id` 仍是进程 UUID。上游看到两个不同身份。

**深度最浅：** 每个调用方都要知道候选头名和 Copilot 的覆盖规则。

### 比较与选型

| | Depth | Locality | Seam |
|---|---|---|---|
| A | 高：调用方一个可选 str | 抽出、剥头、写入 Copilot 各在一处 | inbound 抽出；driver 解析 fallback；GHC 只写 owned 头 |
| B | 低：接口几乎等于实现 | 注册表把变化散开 | 假想的第二 adapter |
| C | 最低 | 猜逻辑、白名单、owned 覆盖三处会再漂移 | 把身份放回 extra_headers，缝选错了 |

**推荐 A。** 工作区 WIP 已走 A 的主干，但 fallback 解析位置、剥头装位、与 `REQUEST_FLOOR` 的关系还没收到 A 的不变量上（见 §10）。

---

## 3. 推荐数据流

```
ASGI headers (raw)
        │
        ├─ interaction_id_from_headers(raw)  →  RequestContext.interaction_id
        │         （只读候选表；空白视为未提供；大小写不敏感）
        │
        ├─ forwarded_client_headers(raw)     →  floor 后的协议头
        │         （REQUEST_FLOOR：凭证 / hop-by-hop / forwarded chain）
        │
        └─ without_interaction_id_headers(floor)
                  →  RequestContext.client_headers
                  →  RequestContext.source_headers 快照
                  （已消费的身份头不再进入转发袋；这不是安全策略）

shape_request
        │
        └─ apply_path_header_policy(client_headers)
                  直连：blacklist（今日空）
                  翻译：whitelist（今日空，保持空）
                  此处再也不谈论会话头

translation（若需要）
        │
        └─ 只改 payload；interaction_id 不动

direct_driver._send  （直连与翻译共用）
        │
        └─ provider.send(
               extra_headers=context.client_headers or None,
               interaction_id=context.interaction_id or context.id,
           )

GithubCopilotProvider
        │
        └─ GhcApiClient.send_*(..., interaction_id=…)
                  build_request_headers(interaction_id=…)
                  extra 不得覆盖 X-Interaction-Id / X-Interaction-Type / …
                  客户端的 x-claude-code-session-id 不得作为 extra 出现在上游

其它 provider
        │
        └─ 忽略 interaction_id；行为与今天一致
```

**装位原则：**

- 抽出发生在 `build_context`，因为它是唯一还拿得到 ASGI 原始头、且保证下游永远不持有客户端凭证的地方。driver 没有 ASGI 请求。
- 剥身份头是「字段已经拿走，禁止再当 extra 转发」，紧挨抽出。不要塞进 `REQUEST_FLOOR`。
- fallback 解析发生在 **driver send 缝**，不在 inbound（inbound 必须能区分「客户端没说」和「我们补了一个」），也不在 GHC 构造期（构造期 UUID 是库默认，不是一次客户端请求）。

---

## 4. 候选来源优先级

单一有序列表，**第一个非空（strip 后）获胜**。不合并、不拼接、不按「看起来更像 UUID」打分。

| 序 | Header | 角色 |
|----|--------|------|
| 1 | `x-claude-code-session-id` | Claude Code 稳定会话 UUID。本代理的主客户端。必须压过其它泛会话头。 |
| 2 | `x-session-id` | 通用会话 |
| 3 | `x-conversation-id` | 通用会话 |
| 4 | `x-chat-session-id` | 聊天会话 |
| 5 | `x-thread-id` | 线程 |
| 6 | `x-interaction-id` | 已是 Copilot 线名。放最后：避免一个随手带了 Copilot 头的客户端压过 Claude Code 的稳定 UUID。 |

规则：

- 比较时 header 名大小写不敏感。
- 值为空或纯空白 → 视为未提供，继续往下。
- 同名多值：inbound 侧是 mapping，后写覆盖；不在抽出层发明多值语义。
- **不要**把 `x-request-id`、`x-stainless-*`、`user-agent`、body 里的 `previous_response_id` 放进这张表。前者是单次请求，后者是 Responses 协议自己的延续，不是本字段的职责。
- 表只存在于 `session_identity` 一处。GHC 客户端不再维护第二份候选名。

---

## 5. 类型与 API 改动

### 5.1 新模块 `app.pipeline.session_identity`

两个函数 + 一列名字。不要做成 class / Protocol / 注册表。

`None` 的含义冻结为：**客户端未声明逻辑会话。** 禁止在此模块生成 UUID。

### 5.2 `RequestContext`

```python
interaction_id: str | None = None
```

注释必须写清：这是客户端逻辑会话，不是 `id`，也不是 attempt 级标识。保持可选；测试里直接构造的 context 缺省为 `None` 仍然合法。

### 5.3 `build_context`

- 用**原始** inbound headers 抽出（floor 之前）。否则一旦有人误把身份头放进 floor，抽出与剥头会同时静默失败。
- `client_headers` / `source_headers` 是 floor **之后**再剥身份头的结果。
- `request_headers.forwarded_client_headers` **不** import `session_identity`。floor 继续只回答凭证与 hop-by-hop。

### 5.4 `ModelProvider.send`

```python
async def send(
    self,
    endpoint: ModelEndpoint,
    payload: Mapping[str, Any],
    *,
    descriptor: ModelDescriptor,
    stream: bool = False,
    extra_headers: Mapping[str, str] | None = None,
    interaction_id: str | None = None,
) -> httpx2.Response:
```

`interaction_id` 是可选关键字，默认 `None`。文档写：仅对「上游协议绑定 interaction」的 provider 有意义；其它 provider 忽略。

不要把身份塞进 `extra_headers` 的约定键（例如 `"x-interaction-id"`）。那会立刻退化成设计 C。

### 5.5 `direct_driver.base._send`

```python
interaction_id=context.interaction_id or context.id,
```

一次请求的全部 attempt 共用这个值（`context.id` 在 `begin_attempt` 时不会换）。禁止在 `_send` 里 `uuid4()`。

### 5.6 `GhcApiClient`

- 每个 `send_*` / `_post_*` / `request_headers` 接受 `interaction_id: str | None = None`。
- `build_request_headers(interaction_id=interaction_id or self._interaction_id)`。
- 构造期 `_interaction_id` 保留，供 catalog refresh、未走 pipeline 的库调用、旧测试。
- **inference 路径不应再落到构造期 UUID**——驱动已经传入 `interaction_id or context.id`。
- `send_anthropic_count_tokens` **不**增加该参数（见 §7.4）。
- owned 头集合继续 case-insensitive 挡住 extra，含 `X-Interaction-Id`。

### 5.7 明确不改的

- `REQUEST_FLOOR` / `DIRECT_PATH_BLACKLIST` / `TRANSLATED_PATH_WHITELIST`
- `Attempt`（身份不是 attempt 属性）
- `count_tokens` 的 `ModelProvider` 协议
- 安全头、凭证、hop-by-hop 名单

---

## 6. 哪些 provider 要改

| Provider | 改动 | 理由 |
|----------|------|------|
| `ModelProvider` Protocol | 签名加可选 `interaction_id` | 驱动不按 provider 类型分支 |
| `GithubCopilotProvider` | 四个 endpoint 的 send 全部下传；embeddings 也下传 | 唯一真正写入 `X-Interaction-Id` 的 adapter |
| `GhcApiClient` | 见 §5.6 | Copilot 线协议 |
| `CodebuddyProvider` | 签名对齐，`del interaction_id` | 上游无 interaction binding |
| `XingchenProvider` | 同上 | 同上 |
| `OpenAICompatibleProvider` | 同上（若该树要落地） | OpenAI 兼容上游不消费 Copilot interaction |
| 测试用 FakeProvider / Recording 替身 | 签名对齐；断言用的 fake 要记下传入值 | 协议测试面 |

**不需要**为 CodeBuddy / Xingchen / OpenAI-compatible 发明会话头。第二消费者出现之前，忽略就是正确 adapter。

`GithubCopilotProvider.count_tokens` → `send_anthropic_count_tokens`：不下传。计数不是对话轮次；避免用会话 UUID 去污染 Copilot 若按 interaction 聚合的遥测。catalog `request_headers()` 也不传 per-request id，继续用实例 fallback。

---

## 7. 重试 / 翻译 / 直连语义

### 7.1 直连

身份与 `anthropic-beta` 等协议头分离。直连仍可转发客户端协议头；身份只走 `interaction_id` 字段，由 GHC 写成 owned `X-Interaction-Id`。原始 `x-claude-code-session-id` **不得**出现在上游 extra 里。

### 7.2 翻译

翻译路径白名单保持空：客户端协商的 Anthropic 头对 Responses 端点无意义。身份在 `build_context` 已进 `RequestContext`，`shape_request` 清空 `client_headers` 也不影响它。翻译只替换 `payload`。因此 Anthropic→Responses 与直连 Messages 看到同一条会话 UUID。这是本方案相对「白名单放行会话头」的全部收益。

`source_headers_for_translation()` 快照的是剥掉身份头之后的协议头。翻译器不需要会话头。

### 7.3 重试与 delivery 再打开

`interaction_id` 在 `RequestContext` 上，不在 `Attempt` 上。同一客户端请求的：

- 限流 / 超时 / 分类为 RETRY 的后续 attempt
- torn body 之后 delivery 再打开的 attempt

都复用同一值。这是「同一逻辑会话的同一轮」，不是新会话。

`x-request-id` / `X-Agent-Task-Id` 仍由 `build_request_headers` 每次生成（或按现有逻辑）。**不要**用会话 UUID 去填 request id。

### 7.4 count_tokens

`handle_count_tokens` 走 `provider.count_tokens`，不走 `_send`。长期方案：**不绑定**。若将来测量证明 Copilot 计数也按 `X-Interaction-Id` 分组，再在计数腿显式传入 `context.interaction_id or context.id`，而不是让它偷偷用进程 UUID。

### 7.5 匿名请求的 fallback

| 场景 | `X-Interaction-Id` |
|------|-------------------|
| 客户端声明了候选头 | 该值（请求内稳定，跨 HTTP 请求也稳定——只要客户端继续送同一头） |
| 客户端未声明，走 pipeline inference | `RequestContext.id`（跨 retry 稳定，跨 HTTP 请求不稳——我们本来就没有会话键） |
| catalog / 库直呼 / 旧测试 | `GhcApiClient._interaction_id` |

**不要**继续用进程级 UUID 填匿名 inference。单账户代理上，那会把 Claude Code 未带头的探测、curl、其它客户端绑成同一场 Copilot 对话。

**不要**用 `RequestContext.id` 去覆盖客户端已经声明的会话。`id` 每次 HTTP 请求都是新的，会拆掉 Claude Code 的多轮绑定。

---

## 8. 测试矩阵

接口即测试面。抽出测 `session_identity` 与 `build_context`；绑定测 driver 与 GHC；端到端测一条翻译、一条直连。不要在 GHC 里再测候选优先级。

### 8.1 抽出（纯函数 / inbound）

| 用例 | 期望 |
|------|------|
| 只有 `x-claude-code-session-id` | 该值 |
| Claude Code 头与 `x-session-id` 同时出现 | Claude Code 获胜 |
| 只有更低优先级头 | 该值 |
| 高优先级头值为空白、低优先级非空 | 跳过空白，取下一个 |
| 名字大小写混用（`X-Claude-Code-Session-Id`） | 仍抽出 |
| 无候选头 | `interaction_id is None` |
| 抽出后 `client_headers` 不含任何候选名 | 剥头成立 |
| `authorization` 等仍被 floor 去掉 | 安全 floor 未因本方案改语义 |
| 未知头（如 `x-stainless-timeout`）直连仍在 | 不是 denylist 扩表 |

### 8.2 驱动

| 用例 | 期望 |
|------|------|
| `context.interaction_id = "session-a"` | `provider.send` 收到 `"session-a"` |
| `interaction_id is None` | 收到 `context.id`，不是 `None`，不是新的随机 UUID |
| 两次 retry | 两次 send 的 interaction_id 相同 |
| `client_headers` 仍单独传递 | 身份与协议头不混在一个袋子里核对 |

### 8.3 GHC 客户端

| 用例 | 期望 |
|------|------|
| 显式 `interaction_id="session-a"` | 上游 `x-interaction-id: session-a` |
| 不传 | 构造期 fallback |
| extra 里带 `x-claude-code-session-id` | **不得**靠 extra 改写 owned `X-Interaction-Id`（回归：身份不走 extra） |
| extra 里带 `x-interaction-id` | owned 仍赢（大小写不敏感） |
| 客户端 UA 不得覆盖 Copilot UA | 既有身份头不变量仍在 |

### 8.4 端到端

| 用例 | 期望 |
|------|------|
| `POST /v1/messages` + Claude 模型 + `x-claude-code-session-id` | 上游 Messages 的 `x-interaction-id` 等于该 UUID；原头不在上游 |
| `POST /v1/messages` + GPT 模型（翻译到 Responses）+ 同一头 | 上游 `/responses` 的 `x-interaction-id` 等于该 UUID；无 `anthropic-beta` |
| 直连不带头 | 上游 interaction 等于该次请求的 `RequestContext.id`（或可观测代理：同一次请求的两次 attempt 相同、两次 HTTP 请求不同） |
| 翻译不带头 | 同上，且仍不转发协议头 |

### 8.5 负空间（必须保持红，如果有人改回去）

- 翻译白名单重新加入会话头，但 `RequestContext.interaction_id` 被删。
- GHC 重新从 extra 猜候选名。
- 把候选名写入 `REQUEST_FLOOR`。
- FakeProvider 丢掉 `interaction_id` 关键字导致协议测试面说谎。

工作区已有：inbound 双头优先级、driver 透传、GHC 显式 id、翻译路径绑定。缺的是：纯函数表驱动、空白跳过、匿名 fallback 用 `context.id` 而非进程 UUID、直连路径端到端、retry 稳定性、`session_identity` 自己的单测。过期注释「whitelist contains only session identity」应删。

---

## 9. 明确不采用的方案及理由

1. **把会话头加入 `TRANSLATED_PATH_WHITELIST`。** 身份不是协议协商。白名单一空身份就丢。即使放行，HEAD 的 owned `X-Interaction-Id` 也不会被 extra 改写，Claude Code 的 UUID 到不了 Copilot binding。这正是任务要拆开的混用。
2. **在 `GhcApiClient` 从 `extra_headers` 猜候选名。** 让最深的上游客户端理解 Claude Code 的头名。候选表一变，所有 send 路径和测试双份。与 owned-header 不变量冲突。
3. **扩 `REQUEST_FLOOR` / 当凭证剥。** 用户明确排除。会话 UUID 不是密钥；floor 的承诺是「下游永不持有客户端凭证」。把身份放进去，以后想在日志里保留源头名都会被安全叙事绑住。
4. **用 `RequestContext.id` 当唯一 interaction。** 每次 HTTP 请求新 UUID，拆掉 Claude Code 多轮会话。`id` 只做匿名 fallback。
5. **用进程级 UUID 当匿名 inference 的 fallback。** 多客户端共享一场 Copilot 对话。构造期 UUID 只留给非 pipeline 调用。
6. **Attempt 级 identity / 每次 retry 新 UUID。** 重试是同一轮，不是新会话。
7. **`SessionIdentity` 值对象或 extractor 插件。** 一个消费者，一个字符串。假想缝。
8. **只改 `GithubCopilotProvider.send`，协议不加字段。** 驱动必须 `isinstance` 分支；FakeProvider 与真实协议分叉。
9. **把身份放进 `extras`。** `extras` 是订阅者杂物袋，没有类型，也没有「翻译不得丢掉」的保证。
10. **让 extra 覆盖 owned `X-Interaction-Id`。** 2026-08-22 已测量：大小写不一致时 OpenAI SDK 路径会双头出站。身份头必须由 GHC 写入，且 extra 不得同名并存。
11. **从 body（`metadata.user`、`previous_response_id`）推断会话。** 那是另一套协议事实；混进 header 抽出等于猜。
12. **count_tokens 自动绑定同一 interaction。** 未测量；默认不绑。
13. **为非 Copilot provider 转发会话头。** 它们没有这个上游字段；不要假装有。

---

## 10. 对工作区 WIP 的审查（不是合并许可）

WIP 方向对（设计 A 的主干），下列偏差若直接落地会留下长期味道：

| WIP | 长期方案 | 为什么算偏差 |
|-----|----------|--------------|
| `forwarded_client_headers` 内部调用 `without_interaction_id_headers` | inbound 先 floor、再剥头；`request_headers` 不依赖 `session_identity` | 把身份消费塞进「floor」函数，下一次改 floor 的人会以为这是安全策略 |
| 驱动传 `context.interaction_id`（可为 `None`），GHC 用进程 UUID fallback | 驱动传 `context.interaction_id or context.id` | 匿名 inference 仍整进程共会话 |
| `build_chain(..., interaction_id=None)` 时 `uuid4()` 作为实例 fallback | 实例 fallback 可保留，但 inference 不应落到它 | 与上一行是同一缺陷的两个装位 |
| 无 `tests/unit/pipeline/test_session_identity.py` | 候选表、空白、大小写应测在抽出模块 | inbound 只测了 Claude 头压过 `x-session-id` 一条 |
| 与 `openai_compatible` 接线、schema、composition 同一份 dirty tree | 身份抽出应可单独审查、单独提交 | 对照评审会把两个主题的回归缠在一起 |
| int 测试注释仍说「whitelist contains only session identity」 | 白名单是空的；身份不在白名单 | 注释与不变量相反 |

WIP 已做对的，长期方案应保留：

- 候选表顺序（Claude Code 第一，`x-interaction-id` 最后）
- 从**原始** inbound 头抽出
- Protocol 级可选参数；非 Copilot `del interaction_id`
- 翻译路径端到端断言 `x-interaction-id == session-a` 且原头不在上游
- GHC 显式参数写入 owned 头，而不是改 extra 覆盖规则

---

## 11. 建议实施顺序（交给主会话）

1. 把身份抽出从其它 dirty 改动里拆开（至少逻辑上按该 diff 审查）。
2. 落地 `session_identity` + inbound 抽出 + 剥头（剥头不要进 floor 函数）。
3. Protocol / 全 provider 签名 / driver `interaction_id or context.id`。
4. GHC 显式参数；构造期 fallback 只服务非 pipeline。
5. 测试按 §8：先纯函数，再 driver，再 GHC，再一条直连 + 一条翻译 e2e。
6. 不改 `message-format-reshape.md` 的白名单正文（仍是「暂无」）。若要在人控文档记一笔，只加：「会话身份在进入 header 政策之前抽出，不走转发名单。」是否写入人控文档由该文档作者决定。

---

## 12. 术语（本方案用到的、且与代码一致）

- **逻辑会话 / conversation identity：** 客户端认为连续的那一段对话；本方案的 `interaction_id`。
- **interaction binding：** Copilot 用 `X-Interaction-Id` 把多次请求算作同一 interaction。这是上游协议，不是 HTTP 转发。
- **floor：** 解析期无条件去掉凭证与 hop-by-hop。与身份抽出无关。
- **path policy：** 路由之后，直连黑名单 / 翻译白名单。与身份抽出无关。
- **owned headers：** GHC 客户端写入、extra 不得覆盖的协议/身份头。

本仓库无 `CONTEXT.md`。以上四词若要进领域词表，需另开 domain-modeling 会话；本次按任务只落本报告。
