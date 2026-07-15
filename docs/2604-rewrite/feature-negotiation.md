# Feature Negotiation 学习缓存

`[上游稳定][采纳，内存 + 异步持久化]`

## 动机

Copilot 上游对不同模型、不同账户路由（例如部分账户经 Vertex AI 转发）支持的 Anthropic API 特性集合并不一致，且这个差异**不体现在模型元数据里**——唯一能确认某个特性是否被支持的方式是**发一次真实请求，看它是否 400**。如果每次请求都盲目携带全部特性（`context_management`、某些 beta header、某个 effort 档位等），已知会被拒绝的模型每次都要付出一次注定失败的往返（增加延迟、浪费一次重试预算、污染日志）。

Feature Negotiation 是一个**反应式学习缓存**：首次请求携带某功能被上游以特定错误模式拒绝后，记录"该模型/该 endpoint 不支持该功能"，后续请求**主动跳过**这个功能（不再携带），直到 TTL 过期后重新尝试（上游可能已经修复/升级）。这是一种运行时自愈机制，把"试错成本"从"每请求一次"摊薄为"每模型每 TTL 周期一次"。

## 性能设计：内存常驻 + 异步落盘

**这是本项目对上游反模式 P5 的直接呼应**（见 [DESIGN.md](DESIGN.md) 性能原则表）：上游 JS 实现的学习缓存本身是内存 `Map` 结构、查询本就 O(1)，本项目**完整保留这一优点**，但需要明确记录并强化以下两条设计约束，避免 Python 重写时引入回归：

1. **学习缓存本体常驻内存**（`dict` + 每条 entry 内嵌 TTL 元数据），**不做同步磁盘查询**——请求路径上的每一次"该功能是否被标记为不支持"判断都是纯内存字典查找，零 I/O、零阻塞。这是本模块能安全地放在热路径（`request_preparation.py` 的每一步准备）上的前提。
2. **持久化异步、off-loop、防抖 + 原子写**：学习到新条目（或已有条目被重新确认）时**不同步写盘**，而是调度一个防抖任务（默认 1 秒窗口内的多次学习合并成一次写），写入用临时文件 + `os.replace` 的原子重命名模式，避免进程崩溃留下半截 JSON。写入任务本身跑在专用后台协程/线程池，不占用请求处理的事件循环时间片。进程重启时从磁盘一次性恢复到内存（启动阶段的一次性 I/O，非热路径）。

**明确不复刻的反模式**：不做"请求路径查磁盘确认是否命中缓存"这类设计（上游本身也没有这么做，但作为"绝不原样复刻"的检查项特此存档确认——若未来有类似"每请求查一次 SQLite sidecar 判断状态"的提案，参照本节原则否决，理由同 P5）。

## 11 个学习类别

`negotiation_lifecycle.py` 定义的分类枚举（顺序即快照/管理 API 的展示顺序）：

| 类别 | 触发的上游错误模式 | 键结构 | 记录内容 |
|------|---------------------|--------|----------|
| `features` | 请求体字段被拒 `<field>: Extra inputs are not permitted`（如 `context_management`） | `(base_url, endpoint, model)` → 字段名集合 | 该模型不支持的请求体顶层字段名 |
| `betas` | `anthropic-beta` token 被拒 `unsupported beta header(s): X` | `(base_url, endpoint, model)` → beta token 集合 | 该模型不支持的 beta feature token |
| `efforts` | `invalid_reasoning_effort` 且带 `supported values: [...]` 列表 | `model` → 有序支持档位列表 | 该模型 `output_config.effort` 的完整支持白名单（不是剥离名单，是替换名单） |
| `effortUnsupported` | `invalid_reasoning_effort` 但**无** `supported values` 列表（"does not support reasoning effort"变体） | `model` → 成员布尔 | 该模型完全不支持 reasoning effort 维度，与 `efforts` 互斥（设置一方会清除另一方） |
| `deferredTools` | `Tool reference 'X' not found in available tools` | `(model, tool_name)` → 成员集合 | 该模型与工具组合必须 sticky 设为 `defer_loading: false`（不能延迟加载） |
| `serverTools` | `The use of the web search tool is not supported.`（`unsupported_value`） | `(model, server_tool_type_prefix)` → 集合 | 该模型不支持的原生 server tool 类型前缀（如 `web_search_`），一次学习免疫所有带日期后缀的变体 |
| `partnerFeatures` | Vertex org-policy 400：`constraints/vertexai.allowedPartnerModelFeatures violated ... disallowed feature X` | `(model, feature_name)` → 集合 | 该模型（经 Vertex 路由）被组织策略禁用的 partner-model 特性，如 `structured_outputs`（→ 对应剥离 `output_config.format`） |
| `systemRejectModels` | `Unexpected role "system"` 400（观察到的症状，非断言 Vertex 特有原因） | `model` → 成员布尔 | 该模型拒绝 inline `role: "system"` 消息，需改走标准 `system` 顶层参数 |
| `serverToolDowngrade` | `Tool '…' not found in provided tools` 400 | `model` → 成员布尔 | 该模型拒绝携带上一轮 server-tool 块，后续请求需降级/剥离历史消息中的 server-tool 块 |
| `toolFields` | `tools.N.<variant>.<field>: Extra inputs are not permitted`（endpoint-level，与具体模型无关） | `(base_url, endpoint)` → 字段名集合 | 上游版本级别不支持的自定义 tool 顶层字段（如 `eager_input_streaming`），一次 400 免疫该 endpoint 上的所有模型 |
| `cacheControlSubfields` | `<section>.N...cache_control.<variant>.<field>: Extra inputs are not permitted`（endpoint-level） | `(base_url, endpoint)` → 字段名集合 | 上游不支持的 `cache_control` 子字段（如 `scope`），一次 400 免疫该 endpoint 上的所有模型 |

### 键粒度的两种设计：per-model vs endpoint-level

大多数类别按 `(base_url, endpoint, model)` 三元组键控——因为这些拒绝是**模型特定**的（同一 endpoint 上不同模型的能力差异真实存在，例如某模型不支持 `web_search`，另一模型支持）。

但 `toolFields` 与 `cacheControlSubfields` 是**endpoint-level**（不含模型段）——因为这两类拒绝反映的是**上游 API 版本本身的属性**，与具体请求哪个模型无关：客户端给每个工具都附带了同一个字段，是否被拒只取决于 GHC 后端的版本，不取决于模型。因此这两类学习是**最泛化**的：任意模型上触发一次 400，就能免疫该 endpoint 上所有模型的后续请求，学习效率最高。

`efforts` / `effortUnsupported` 键控更细——仅按**模型名**（不含 `base_url`/`endpoint`），因为 reasoning effort 档位是模型自身的固有属性，与账号路由无关。

## TTL 裁决

每条学习到的 entry 携带统一的元数据结构 `LearnedEntryMeta`：

```python
@dataclass
class LearnedEntryMeta:
    first_learned_at: float   # 首次学到的时刻（epoch 秒）；迁移记录时记为迁移时刻，非真实首学
    last_confirmed_at: float  # 最后一次确认的时刻（TTL 计算基准；每次再命中/续约会刷新）
    pinned: bool = False      # True = 永不过期，无视 TTL 与 manually_expired
    manually_expired: bool = False  # 立即失效标记；保留行但视为过期，再确认/续约时自动清除
    migrated: bool = False    # 由旧版本格式迁移而来，first_learned_at 非真实首学时刻
```

**单一裁决点**：所有"该 entry 现在是否生效"的判断都收敛到一个纯函数 `is_entry_active(meta, category, now)`，不允许任何消费点自行判断过期逻辑：

```python
def is_entry_active(meta: LearnedEntryMeta, category: NegotiationCategory, now: float) -> bool:
    if meta.pinned:
        return True
    if meta.manually_expired:
        return False
    ttl = category_ttl_seconds(category)
    if ttl == math.inf:
        return True
    return now <= meta.last_confirmed_at + ttl
```

- 默认 TTL：`negotiation_learning.default_ttl_days`（默认 **30 天**）。
- 可按类别覆盖（`negotiation_learning.ttl_days`，per-category 秒数或 `never`）。
- 可通过管理 API 手动 `pin`（永不过期）或 `manually_expired`（立即失效，供运维在怀疑误判或上游已修复时手动重测）。
- 每次同一 entry 被再次命中（再次学习到同样的拒绝，或管理 API 续约）都会刷新 `last_confirmed_at` 并清除 `manually_expired`——这是"再确认"语义：只要上游还在拒绝，TTL 窗口就持续滚动延后；只有当上游不再拒绝（客户端不再触发学习函数）时 TTL 才会真正到期，届时下一次请求会重新尝试该功能。

### Config 孪生键

每个学习类别通常有一个对应的 **config 静态孪生配置**，两者取**并集**生效（config 是运维显式声明的、永久生效的规则；学习缓存是运行时发现的、有 TTL 的规则）：

| 学习类别 | Config 孪生键 | 合并语义 |
|----------|----------------|----------|
| `toolFields` | `anthropic.tool_strip_fields`（剥离，加法） / `anthropic.tool_keep_fields`（保留，减法，优先级更高） | config 声明剥离的字段与学习到的字段取并集一起剥；`tool_keep_fields` 可覆盖回来，即便学习缓存标记了不支持 |
| `betas` | `anthropic.beta_strip_headers` | config 声明的 beta 首次请求即剥离（不必等一次 400），学习缓存补充运行时发现的额外项 |
| `partnerFeatures` | `anthropic.partner_strip_features` | 运维显式声明的 partner 特性禁用与学习到的并集 |
| `cacheControlSubfields` | `anthropic.cache_control_strip_subfields` | 见 [anthropic-compat.md](anthropic-compat.md) 的 passthrough/sanitize 子字段剥离 |
| `systemRejectModels` | `anthropic.system_reject_models` | 静态声明的拒绝 inline system 的模型名单与学习到的并集 |

所有并集计算都是"config ∪ 学习缓存的 `active_keys()`"——请求路径每次都重新求并集（两边都是内存结构，开销可忽略），不做提前物化缓存，避免 config 热重载后并集结果失配。

## 持久化

默认路径：`<data_dir>/negotiation-states.json`（`PATHS.NEGOTIATION_STATES`，遵循 [config-system.md](config-system.md) 的跨平台数据目录约定）。

- **写入**：内存变更后调度一次防抖写（默认 1 秒窗口，多次学习合并为一次落盘），写入采用"写临时文件 + 原子 rename"模式（`os.replace`，同文件系统内保证原子性），避免写入过程中崩溃留下截断的 JSON（若截断，加载时的 `try/except` 会静默清零全部已学到的兼容性知识，代价很高，因此原子性是必须的，不是锦上添花）。
- **序列化格式（v2）**：一个顶层 JSON 对象，`version: 2` + 11 个类别字段，`record` 类型的类别（features/betas/deferredTools/serverTools/partnerFeatures/toolFields/cacheControlSubfields）序列化为 `{key: {value: meta}}` 两层嵌套；`flat` 类型的类别（effortUnsupported/systemRejectModels/serverToolDowngrade）序列化为 `{key: meta}`；`efforts` 单独序列化为 `{model: {values: [...], meta}}`。
- **v1 → v2 迁移**：v1 格式把每个类别存成纯字符串数组（无 TTL 元数据）。加载时检测到数组形状，自动转换为 v2 的 `{value: meta}` 形式，`meta.migrated = True`，`first_learned_at = last_confirmed_at = 加载时刻`（因为真实首学时刻已不可考）。加载器对 `version` 字段做白名单校验（仅接受 `1` 或 `2`），未知版本直接跳过（保守，不猜测格式）。
- **加载失败容错**：文件不存在或 JSON 解析失败 → 记一条 debug 日志，从空缓存开始（never-throw，不阻塞启动）。

## 管理 API

挂载于 `/api/negotiation`（详见 [project-structure.md](project-structure.md) 的 API 路由清单）：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/negotiation` | `GET` | 返回按类别分组的完整快照（含 `status`：`active`/`expired`/`pinned`/`manually_expired`，`expires_at` 派生时刻） |
| `/api/negotiation/renew` | `POST` | 续约指定 entry（`{category, key, value}`），刷新 `last_confirmed_at` 并清除 `manually_expired` |
| `/api/negotiation/expire` | `POST` | 立即使指定 entry 失效（设置 `manually_expired = true`），保留行以便审计 |
| `/api/negotiation/pin` | `POST` | `{category, key, value, pinned}`，设置/取消永不过期标记 |
| `/api/negotiation/entry/delete` | `POST` | 彻底删除指定 entry（从内存与下一次落盘中移除） |
| `/api/negotiation/export` | `GET` | 以 `Content-Disposition: attachment` 导出完整 v2 格式 JSON（供备份/迁移/离线分析，未经 TTL 过滤的原始快照） |

管理 API 的读操作（`GET`）返回时才计算 `status`/`expires_at` 等派生字段（惰性投影，呼应 [DESIGN.md](DESIGN.md) 性能原则 P7），内存中的 entry 本身不预存这些派生值。写操作（`renew`/`expire`/`pin`/`delete`）触发的持久化仍走上述防抖 + 原子写路径，不因为是管理 API 调用就同步落盘。

## 缓存键规范总结

```python
def model_key(base_url: str, endpoint: str, model_id: str) -> str:
    """per-model 学习类别的键：features / betas / deferredTools / serverTools / partnerFeatures。"""
    return f"{base_url}|{endpoint}|{normalize_for_matching(model_id)}"

def endpoint_key(base_url: str, endpoint: str) -> str:
    """endpoint-level 学习类别的键（model-agnostic）：toolFields / cacheControlSubfields。"""
    return f"{base_url}|{endpoint}"

def effort_key(model_id: str) -> str:
    """efforts / effortUnsupported 的键：仅模型名，与 base_url/endpoint 无关（模型固有属性）。"""
    return normalize_for_matching(model_id)
```

键中包含 `base_url` 是为了保证**不同账户类型/不同上游路由**（例如个人账户直连 vs 企业账户经 Vertex 转发）的学习结果互不污染——同一个模型名在不同路由下可能有不同的支持边界，键必须能区分。`model_id` 一律经 `normalize_for_matching()` 规范化（小写 + 连字符统一），使 `claude-opus-4.6` 与 `claude-opus-4-6` 命中同一条学习记录。

## 相关文档

- [设计文档总纲](DESIGN.md)（性能原则 P5：内存常驻隔离表，本模块是同一原则的另一处应用）
- [Anthropic API 兼容性](anthropic-compat.md)（请求准备流程中消费本缓存的各处：body 字段剥离、beta header 过滤、cache_control 子字段黑名单、effort 钳制）
- [Tool Use 机制](tool-use.md)（`deferredTools` / `serverTools` 学习类别的消费点）
- [配置系统](config-system.md)（config 孪生键、TTL 覆盖配置）
