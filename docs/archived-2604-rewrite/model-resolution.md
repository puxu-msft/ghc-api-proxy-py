# Model 解析

> 本文档是**目标设计**（design spec），标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。未特别标注者默认 `[上游稳定][采纳]`。

## 概述

`transform/model_resolver.py` 将用户请求的模型名解析为实际可用的模型 ID。解析逻辑参考上游参考项目 `src/lib/models/resolver.ts`，在 Python 中使用 Pydantic 模型（[data-models.md](data-models.md) 的 `ModelInfo`）与 FastAPI 依赖注入重新实现。

## 解析流程

```
用户输入模型名（如 "opus"、"claude-opus-4-6"、"claude-opus-4-6-fast"）
    │
    ▼
[1. Model Overrides 查找]
    检查 raw name 是否在 config 的 model_overrides 中
    如 "opus" → "claude-opus-4.6"（内置默认）
    如 "gpt-4o" → "claude-opus-4.6"（用户自定义）
    │ 命中 → 对 override 目标递归解析（链式 + 循环检测）
    │ 未命中 ↓
    ▼
[2. 别名/规范化]
    ├─ 短别名: "opus" → 按优先级列表选择最佳可用
    ├─ 连字符版本: "claude-opus-4-6" → "claude-opus-4.6"
    ├─ 日期后缀: "claude-opus-4-20250514" → 提取 family → 最佳可用
    └─ 修饰符后缀: "claude-opus-4-6-fast" → "claude-opus-4.6-fast"
                    "opus[1m]" → "opus-1m" → "claude-opus-4.6-1m"
    │
    ▼
[3. 解析后再查 Overrides]
    规范化后的名称可能也在 overrides 中
    │
    ▼
[4. Family 级别 Override]
    如果 "opus" → "claude-opus-4.6-1m"，
    那么 "claude-opus-4-6" 也应被重定向到 "claude-opus-4.6-1m"
    通过检测 override 源和解析结果是否属于同一 family 实现
    │
    ▼
[5. Override 链式解析 + 循环检测]
    override 目标本身也可以是别名或 override 键
    使用 visited set 检测循环引用
    │
    ▼
[6. 可用性检查]
    解析结果是否在可用模型列表中（走 O(1) 索引查找，见下文「模型定期刷新」）
    ├─ 在 → 返回
    └─ 不在 → 原样透传（让上游判断）
```

## 标准化细节

### 版本号标准化

将连字符分隔的版本号转为点号：

| 输入 | 标准化后 |
|------|----------|
| `claude-opus-4-6` | `claude-opus-4.6` |
| `claude-sonnet-4-5` | `claude-sonnet-4.5` |
| `claude-haiku-4-5` | `claude-haiku-4.5` |
| `claude-opus-4-6-fast` | `claude-opus-4.6-fast` |

规则：识别 `claude-{family}-{major}-{minor}` 模式，将 `{major}-{minor}` 转为 `{major}.{minor}`。

### 日期后缀处理

移除 YYYYMMDD 格式的日期后缀，提取 family 并选择最佳可用：

| 输入 | 处理过程 |
|------|----------|
| `claude-sonnet-4-6-20250514` | → 去掉日期 → `claude-sonnet-4-6` → 标准化 → `claude-sonnet-4.6` |
| `claude-opus-4-20250514` | → 去掉日期 → `claude-opus-4` → family=opus → 最佳可用 opus |

带日期名也可以在 `model_mappings` 中显式登记（见下文「`model_mappings`」），两条路径并存：能被上述规则模式匹配的走自动剥离，配置里显式列出的走精确 override，互不冲突。

### 修饰符后缀

修饰符（`fast`、`1m`）在版本号标准化后保留：

| 输入 | 输出 |
|------|------|
| `claude-opus-4-6-fast` | `claude-opus-4.6-fast` |
| `opus[1m]` | → `opus-1m` → resolve `opus` → `claude-opus-4.6` → `claude-opus-4.6-1m` |
| `opus-1m` | → resolve `opus` → `claude-opus-4.6` → `claude-opus-4.6-1m` |

方括号语法 `model[suffix]` 会先转换为 `model-suffix` 再进入解析流程。

## 优先级列表

每个模型 family 有一个优先级列表。使用短别名时，选择列表中第一个可用的模型：

```python
MODEL_PREFERENCE = {
    "opus": [
        "claude-opus-4.6",
        "claude-opus-4.5",
        "claude-opus-4.1",
        "claude-opus-4",
    ],
    "sonnet": [
        "claude-sonnet-4.6",
        "claude-sonnet-4.5",
        "claude-sonnet-4",
    ],
    "haiku": [
        "claude-haiku-4.5",
    ],
}
```

### normalizeForMatching

内部用于 family 匹配和特性检测的标准化函数：

```python
def normalize_for_matching(model_id: str) -> str:
    """将模型名标准化用于特性匹配（全小写、连字符分隔）。"""
    return model_id.lower().replace(".", "-")
```

这使得 `claude-opus-4.6` 和 `claude-opus-4-6` 在特性检测中被视为等价。这一函数也是 [anthropic-compat.md](anthropic-compat.md) 里所有 `model_supports_*` 判定函数的公共前置步骤。

## `model_overrides`（简称别名，顶层便利层）`[新增]`

### 内置默认

```python
DEFAULT_MODEL_OVERRIDES = {
    "opus": "claude-opus-4.6",
    "sonnet": "claude-sonnet-4.6",
    "haiku": "claude-haiku-4.5",
}
```

### 用户配置

通过 config.yaml 的 `model_overrides` 配置任意映射：

```yaml
model_overrides:
  opus: claude-opus-4.6
  sonnet: claude-sonnet-4.6
  haiku: claude-haiku-4.5
  gpt-4o: claude-opus-4.6        # 将 GPT 请求重定向到 Claude
  claude-3-5-sonnet: claude-sonnet-4.6  # 旧版模型重定向
```

`model_overrides` 是本项目在 Python 侧新增的**便利别名层**，位于更通用的 `model_mappings`（见下）之上。用户配置**完全替换**内置默认（不是合并），因此如果要保留内置别名，需要在配置中显式包含。

### 链式解析

Override 目标自身也会被解析：

```yaml
model_overrides:
  fast: opus-fast
  opus-fast: claude-opus-4.6-fast
```

请求 `fast` → `opus-fast` → `claude-opus-4.6-fast`

使用 visited set 检测循环：如果解析链中出现重复名称，停止解析并返回当前结果。

### Family 级别 Override

当 override 源和目标属于同一 family 的不同变体时，该 family 的所有变体都会被重定向：

```yaml
model_overrides:
  opus: claude-opus-4.6-1m
```

此时 `claude-opus-4-6` → 标准化为 `claude-opus-4.6` → 属于 opus family → 重定向到 `claude-opus-4.6-1m`。

## `model_mappings`（通用别名 → 具体模型 ID，per-key 合并）`[上游稳定][采纳]`

`model_mappings` 是更底层、更通用的映射表，与 `model_overrides` 的关键区别是**合并策略**：`model_mappings` 采用 per-key 合并（用户只需声明要覆盖的键，未声明的内置键继续保留），而 `model_overrides` 是整表替换。两者共同参与解析流程的「Override 查找」步骤（`model_overrides` 优先于 `model_mappings` 被查询，语义上 `model_overrides` 是给常见短别名准备的一层"快捷方式"）。

```yaml
model_mappings:
  claude-haiku-4-5-20251001: claude-haiku-4.5   # 显式登记带日期名（见上文「日期后缀处理」）
  gpt-4-turbo: claude-sonnet-4.6
```

## `disabled_models`（禁用模型列表）`[上游稳定][采纳]`

```yaml
disabled_models:
  - claude-3-opus-20240229
```

列在此处的模型 ID 会从对外的可用模型列表与解析可用性检查中剔除（见下文「模型列表两种输出格式」），即使上游 Copilot 目录中仍然存在。典型用途：临时下线某个模型而不必等 Copilot 侧下架，或屏蔽账户配额不足以承受的高价模型。

## 端点支持检查

`upstream/models_api.py` 维护每个模型支持的端点列表（`ModelInfo.supported_endpoints`，见 [data-models.md](data-models.md#模型能力元数据-modelscapabilitiespy)）：

```python
def model_supports_endpoint(model: ModelInfo, endpoint: str) -> bool:
    """检查模型是否支持指定端点。"""
    return endpoint in model.supported_endpoints
```

路由决策使用此信息选择最佳端点：
- Claude 模型且 `supported_endpoints` 含 `/v1/messages` → 直连 Anthropic（见 [anthropic-compat.md](anthropic-compat.md)）
- 支持 `/responses` 且 `openai_responses.prefer_responses` 启用 → 使用 Responses
- 否则 → Chat Completions

这一判断结合 `ModelCapabilities.supports` 中的更细粒度字段（如 `adaptive_thinking`、`tool_search`）共同决定请求准备阶段的行为，详见 [anthropic-compat.md](anthropic-compat.md) 的模型特性检测。

## Feature Negotiation

`anthropic/feature_negotiation.py` 动态检测模型对特定功能的支持，是模型解析之外的另一层"运行时自愈"能力，完整设计见 [feature-negotiation.md](feature-negotiation.md)（11 个学习类别、TTL 裁决、内存常驻 + 异步持久化）。

简述：当某功能请求返回特定错误模式时，将该 `(model, feature)` 或 `(base_url, endpoint, feature)` 对标记为不支持，缓存直到 TTL 过期。后续请求主动跳过该功能而非每次都试错。

---

## 模型列表两种输出格式

Copilot `/models` 目录本身是"完整、未过滤"的内部格式；本项目对外暴露两种视图，服务不同的客户端期望：

### OpenAI 标准格式（`/models`、`/v1/models`、`/openai/v1/models`）

只保留 OpenAI SDK/spec 认可的基线字段，附加能力元数据作为**扩展字段**（符合 OpenAI spec 的客户端按约定忽略未知字段，不会因为多出字段而报错）：

```python
class OpenAIModelListItem(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int                        # Unix 秒；Copilot 目录若无该字段则用启动时间兜底
    owned_by: str                       # 映射自 ModelInfo.vendor（小写化，如 "anthropic"）
    # 扩展字段（非 OpenAI 标准，供本项目自身前端/工具消费；标准客户端会忽略）
    capabilities: ModelCapabilities | None = None

class OpenAIModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[OpenAIModelListItem]
```

```python
def to_openai_model_list(models: list[ModelInfo]) -> OpenAIModelList:
    return OpenAIModelList(data=[
        OpenAIModelListItem(
            id=m.id,
            created=DEFAULT_MODEL_CREATED_TS,
            owned_by=m.vendor.lower() or "copilot",
            capabilities=m.capabilities,
        )
        for m in models
        if m.id not in disabled_ids
    ])
```

### 内部格式（`/api/models`）

返回**完整、未过滤**的 Copilot 目录数据，附加 `disabled` 列表标注哪些 ID 被 `disabled_models` 剔除（供管理面板展示"存在但被禁用"的模型，而非直接从列表中消失让人误以为上游没有该模型）：

```python
class InternalModelList(BaseModel):
    object: str
    data: list[ModelInfo]            # 完整 Copilot 目录，含 request_headers、billing 等内部字段
    disabled: list[str]              # 被 disabled_models 剔除的 ID 列表（仅标注，不从 data 中移除）
```

`/api/models/{model}` 单模型端点复用同一份 `ModelInfo`，不额外做字段裁剪（内部管理 API，非对外协议兼容面）。

### Anthropic 格式（`/anthropic/v1/models`）

返回 Anthropic SDK 的 `ModelInfo` 形状（与 Anthropic 官方 `@anthropic-ai/sdk/resources/models` 声明的字段一致），**过滤 `vendor == "Anthropic"`**——GPT/Gemini 模型即使可通过其他端点访问，也不出现在这里，镜像 Anthropic 自己的模型目录语义：

```python
class AnthropicModelListItem(BaseModel):
    id: str
    type: Literal["model"] = "model"
    display_name: str
    created_at: str                  # ISO 8601

def to_anthropic_model_list(models: list[ModelInfo]) -> list[AnthropicModelListItem]:
    return [
        AnthropicModelListItem(id=m.id, display_name=m.name or m.id, created_at=DEFAULT_MODEL_CREATED_ISO)
        for m in models
        if m.vendor == "Anthropic" and m.id not in disabled_ids
    ]
```

`/anthropic/v1/models/{model}` 对不存在或 vendor 非 Anthropic 的 ID 返回 404（与列表行为一致：不在列表里出现的模型，单条查询也应该查不到）。

Gemini **没有独立的模型列表端点**（上游参考项目本身也未实现 `/v1beta/models` 的 GET），Gemini 客户端如需模型目录，走 `/api/models` 或标准 OpenAI `/v1/models`，详见 [multi-protocol.md](multi-protocol.md#模型列表两种格式)。

---

## 模型定期刷新

`upstream/models_api.py` 在应用启动阶段首次拉取模型目录（拉取失败则拒绝启动，因为没有模型目录整个代理无法正常工作），之后按 `timeouts.model_refresh_interval`（默认 **600** 秒，**0 = 禁用后台刷新**）周期性地在**后台 off-loop 任务**中重新拉取并替换缓存，不阻塞任何请求处理路径：

```python
async def model_refresh_loop(
    upstream: UpstreamTarget,
    interval_seconds: int,
    stop_event: asyncio.Event,
) -> None:
    """后台周期刷新任务，随 lifespan 一起启停。"""
    if interval_seconds <= 0:
        return  # 0 = 禁用
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            break  # stop_event 被设置，正常退出
        except asyncio.TimeoutError:
            pass  # 到达刷新周期
        try:
            new_models = await upstream.fetch_models()
            set_model_index(build_model_index(new_models))
        except Exception as exc:
            # 刷新失败保留旧缓存（宁可用旧数据，也不能让代理在一次网络抖动后失去所有模型信息）
            logger.warning("model refresh failed, keeping cached catalog: %s", exc)
```

刷新支持 `ETag`/`If-None-Match` 协商（若 Copilot 返回 304，跳过 JSON 解析与索引重建，直接保留当前缓存），减少无意义的重复解析开销。

### O(1) 查找索引

刷新完成后立即从模型列表构建两份索引，供解析流程与端点决策使用，避免每次请求都线性扫描模型列表：

```python
@dataclass
class ModelIndex:
    by_id: dict[str, ModelInfo]        # O(1) 精确 ID 查找
    available_ids: frozenset[str]      # O(1) 可用性检查（已排除 disabled_models）

def build_model_index(models: list[ModelInfo], disabled_ids: frozenset[str]) -> ModelIndex:
    by_id = {m.id: m for m in models}
    available_ids = frozenset(by_id) - disabled_ids
    return ModelIndex(by_id=by_id, available_ids=available_ids)
```

索引整体作为不可变对象通过一次原子替换（`set_model_index()`，底层是对一个模块级 `contextvars`/普通引用变量的重新赋值）更新，请求路径读取的引用要么是旧索引要么是新索引，不会读到"正在构建中"的中间态，天然避免了刷新与请求并发时的读写竞争，无需加锁。

## 相关文档

- [设计文档总纲](DESIGN.md)
- [数据模型](data-models.md)（`ModelInfo` / `ModelCapabilities` / `ModelSupports` 完整定义）
- [Anthropic 兼容性](anthropic-compat.md)（Feature 检测详情、模型特性判定优先级）
- [多协议适配](multi-protocol.md)（Gemini/Azure 复用模型解析与端点决策）
- [Feature Negotiation 学习缓存](feature-negotiation.md)
- [配置系统](config-system.md)（`model_overrides`/`model_mappings`/`disabled_models`/`model_refresh_interval` 配置）
