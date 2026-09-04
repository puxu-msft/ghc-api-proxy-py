# 请求/响应头转发安全

`[上游稳定][采纳]`

## 背景

代理天然地处于客户端 ↔ 上游（Copilot）之间，两个方向都存在头转发需求：

- **响应方向**（上游 → 客户端）：客户端可能依赖某些上游响应头（如 `request-id`、`anthropic-ratelimit-*`）做限流感知或问题追踪；但直接转发上游全部响应头有风险——`content-length`/`content-encoding` 等**内容分帧头**会与代理重新序列化后的实际字节数不符，转发会让客户端按错误的字节数解析响应体；`set-cookie` 等也不该被转发。
- **请求方向**（客户端 → 上游）：客户端可能携带一些对上游有意义的头（如 Anthropic SDK 的 `anthropic-dangerous-direct-browser-access`、Claude Code 的 `x-claude-code-*`）；但直接转发客户端全部请求头同样有风险——`authorization`/`cookie`/`x-api-key` 等**凭据头**绝不能让客户端覆盖代理自己对上游的认证，`host`/`content-length`/`transfer-encoding` 等**分帧/跳段头**也不该被转发（代理重建了请求体）。

本项目采用统一的 **blacklist/whitelist 双模式** 设计（两个方向各自独立配置一对布尔 + 名单），外加一层**安全下限（security floor）**：无论选哪种模式，凡是会导致凭据泄漏或响应/请求帧损坏的头，**先于**模式判断被无条件剥离，模式的名单只能在"安全下限已经过滤过"的子集上生效——因此白名单模式**不可能**因为运维配置疏忏而重新放行一个凭据头。

## 响应头转发（上游 → 客户端，仅 Anthropic 路径）

配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.strict_response_headers` | `false` | `false` = **BLACKLIST 模式**：转发除黑名单外的一切上游响应头；`true` = **WHITELIST 模式**：只转发命中白名单的响应头 |
| `anthropic.response_header_blacklist` | `[]` | BLACKLIST 模式下要额外剔除的 glob 名单（空 = 不额外剔除任何头，即安全下限之外全部放行） |
| `anthropic.response_header_whitelist` | `["request-id", "x-request-id", "anthropic-ratelimit-*", "anthropic-organization-id", "retry-after"]` | WHITELIST 模式下允许转发的 glob 名单 |

### Security Floor（两模式共享，恒先执行）

无条件剔除代理自己控制/合成的响应头（`PROXY_CONTROLLED_RESPONSE_HEADERS`），不受任何配置影响：

- **内容分帧（load-bearing，不可移除）**：`content-length`、`content-encoding`、`content-type`、`transfer-encoding`——代理会重新序列化响应体（甚至可能整帧改写，见 [streaming-resilience.md](streaming-resilience.md) 的缓冲重试），上游这几个头描述的字节数/编码方式与客户端最终收到的字节完全对不上，转发会导致客户端解析错误。
- **跳段头（hop-by-hop，RFC 9110 §7.6.1）**：`connection`、`keep-alive`、`proxy-authenticate`、`proxy-authorization`、`te`、`trailer`、`upgrade`——只在上游 ↔ 代理这一段连接有意义，语义上不应跨代理转发。
- **代理自行决定的头**：`cache-control`、`date`。
- **防御性剔除**：`set-cookie`——Copilot 不会下发 cookie，但若上游意外携带，多值 `Set-Cookie` 在头合并时会被错误地拼成一个逗号分隔值，宁可无条件剔除。

Floor 执行顺序：先对全部上游响应头做 floor 过滤（得到"已过滤子集"），再对该子集应用模式判断（`keep_headers(floored, whitelist)` 或 `prune_headers(floored, blacklist)`）——因此运维配置 `response_header_whitelist` 时即便手滑写入 `content-length`，也不会被放行，因为 floor 已经把它从候选集里拿掉了。

### 注意：延迟提交流拿不到上游头

若响应已按延迟提交策略提前 flush 了 HTTP 200 状态行给客户端（见 [streaming-resilience.md](streaming-resilience.md) 的"延迟提交窗口"），此时上游响应头集合可能尚未完全到达或时序上已经来不及注入到已发送的响应头帧中——这类场景下响应头转发是 best-effort，不保证每次都能把上游头带上，属已知限制而非缺陷。

## 请求头转发（客户端 → 上游）

配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `anthropic.strict_request_headers` | `false` | `false` = **BLACKLIST 模式**：转发除黑名单外的客户端请求头（安全下限之外）；`true` = **WHITELIST 模式**：只转发命中白名单的客户端请求头 |
| `anthropic.request_header_blacklist` | `["x-anthropic-billing-header"]` | BLACKLIST 模式下要额外剔除的 glob 名单 |
| `anthropic.request_header_whitelist` | `["accept", "anthropic-dangerous-direct-browser-access", "x-app", "x-claude-code-*", "x-stainless-*"]` | WHITELIST 模式下允许转发的 glob 名单 |

### Security Floor（两模式共享，恒先执行）

第一层：剔除代理核心键（`copilot-integration-id`、`editor-version`、`anthropic-version`、`anthropic-beta`、`X-Initiator` 等由 `request_preparation.py` B5 步骤动态生成的键，含条件性的 `copilot-vision-request`——即便某次请求未触发 vision，也预留该键名不允许客户端伪造），确保**代理自己合成的头永远是权威值**，客户端无法通过同名头覆盖。

第二层：剔除敏感 denylist（精确名 + 前缀两种匹配）：

- **凭据类**：`cookie`、`set-cookie`、`authorization`、`proxy-authorization`、`x-api-key`、`api-key`
- **分帧/跳段类**：`host`、`content-length`、`content-encoding`、`accept-encoding`、`expect`、`connection`、`keep-alive`、`transfer-encoding`、`te`、`trailer`、`upgrade`
- **拓扑泄漏类**：`via`、`forwarded`、`x-real-ip`、`x-forwarded-for`、`x-forwarded-host`、`x-forwarded-proto`、`x-forwarded-port`、`x-forwarded-server`、`true-client-ip`、`cf-connecting-ip`、`x-client-ip`
- **代理专属命名空间前缀**：`x-github-*`、`openai-*`——客户端不得冒充代理自己的路由/计费身份头

两层 floor 过滤后得到"安全子集"，模式判断（`keep_headers` 白名单交集 / `prune_headers` 黑名单差集）只在该子集上生效，最终与核心键做 `{**selected, **core}` 合并（核心键永远权威，且已保证与 selected 无键冲突，因为 floor 第一层已排除核心键）。

## 归属头剥离（Attribution Header Strip）

配置项 `anthropic.strip_attribution_header`（默认 **`true`**），**仅 Anthropic 路径**。

现代 Claude Code 客户端**不是**通过 HTTP 头携带计费归属信息，而是把它作为请求体 `system` 参数的**第一个 block**（一段固定格式的归属文本），因此上述"请求头黑名单"从设计上根本够不着它——这是一个 body-level 的剥离，与 HTTP header 转发策略是互补但独立的两道防线。

`strip_attribution_header` 启用时，在消息清洗/请求准备阶段检测 `system` 参数首个 block 是否匹配已知的 Claude Code 归属行格式，命中则剥除该 block（若剥除后 `system` 为空数组则整体置空）。检测与清洗的具体位置详见 [消息清洗管道](sanitize-pipeline.md) 中 system prompt 处理部分；本文档只记录其"header 转发无法覆盖此项，需单独开关"的边界。

## Glob 匹配

所有名单（黑名单/白名单）均为 **glob 模式**（支持 `*` 通配任意长度、`?` 通配单字符），**大小写无关**匹配 HTTP 头名称。

### Python 实现设计

两种可行实现，推荐 `fnmatch`（标准库、零依赖、语义与上游 JS 版本的手写 glob-to-regex 等价）：

```python
import fnmatch

def compile_header_predicate(patterns: list[str]) -> Callable[[str], bool] | None:
    """把 glob 名单编译为大小写无关的匹配谓词；空名单返回 None（调用方按语境解释为
    "不剥离任何头"或"不放行任何头"，两种模式的空名单语义是镜像相反的，见下）。"""
    cleaned = [p.strip() for p in patterns if p.strip()]
    if not cleaned:
        return None
    lowered = [p.lower() for p in cleaned]
    return lambda name: any(fnmatch.fnmatch(name.lower(), p) for p in lowered)
```

若追求启动期一次性预编译正则以避免每请求重复走 `fnmatch.translate`（高频路径的性能考量，对齐 P1-P8 通用取向），可在配置加载时把每个 glob 转换为 `re.compile(fnmatch.translate(p), re.IGNORECASE)`，请求路径只做 `pattern.match(name)`。

### 空名单的镜像语义（黑名单 vs 白名单，务必留意）

- **黑名单模式**（`prune_headers`）：空名单 `[]` → 谓词恒为 `None` → **不剔除任何头**（在 floor 之外全部放行）。
- **白名单模式**（`keep_headers`）：空名单 `[]` → 谓词恒为 `None` → **不放行任何头**（等价于退回到"只有代理核心头"的最严格行为）。

两者刻意镜像相反：黑名单的"空"意味着"宽松到底"，白名单的"空"意味着"严格到底"——与各自模式的直觉一致（黑名单是"默认放行、点名剔除"，白名单是"默认拒绝、点名放行"）。实现与测试都必须覆盖这一对不对称语义，不能假定"空列表 = 无操作"对两种模式通用。

黑名单模式下 `protected_headers`（如 `authorization`、`content-type`、`content-length`、`copilot-integration-id`）即便被某条 glob 意外命中也**不会**被剔除——这是黑名单原语自身的一层防御性保护（尽管在当前调用链中这四个键在 `prune_headers` 执行前就已经被 floor 剔除，从未真正触发这层保护，但作为独立导出、可能被未来调用点直接复用的原语，仍保留此不变式）。白名单模式无需此保护——它是交集运算，代理核心头由下游的 `{**selected, **core}` 合并无条件重新注入。

## 配置速查表

| 配置项 | 默认值 | 方向 | 作用 |
|--------|--------|------|------|
| `anthropic.strict_response_headers` | `false` | 响应 | `false`=黑名单模式，`true`=白名单模式 |
| `anthropic.response_header_blacklist` | `[]` | 响应 | 黑名单模式下的剔除 glob（空=不额外剔除） |
| `anthropic.response_header_whitelist` | `["request-id", "x-request-id", "anthropic-ratelimit-*", "anthropic-organization-id", "retry-after"]` | 响应 | 白名单模式下的放行 glob |
| `anthropic.strict_request_headers` | `false` | 请求 | `false`=黑名单模式，`true`=白名单模式 |
| `anthropic.request_header_blacklist` | `["x-anthropic-billing-header"]` | 请求 | 黑名单模式下的剔除 glob |
| `anthropic.request_header_whitelist` | `["accept", "anthropic-dangerous-direct-browser-access", "x-app", "x-claude-code-*", "x-stainless-*"]` | 请求 | 白名单模式下的放行 glob |
| `anthropic.strip_attribution_header` | `true` | 请求（body-level） | 剥离 `system[0]` 归属计费块，非 HTTP 头，仅 Anthropic 路径 |

## 相关文档

- [设计文档总纲](DESIGN.md)
- [Anthropic API 兼容性](anthropic-compat.md)
- [消息清洗管道](sanitize-pipeline.md)（system prompt 归属块剥离的具体处理位置）
- [流式韧性](streaming-resilience.md)（延迟提交流下响应头转发的时序限制）
- [配置系统](config-system.md)
