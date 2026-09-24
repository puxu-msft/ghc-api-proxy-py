# 配置载入与 Pydantic ValidationError 容错策略调研报告

## 1. 调研背景与核心问题

当前 `ghc-api-proxy` 在启动阶段与热加载（SIGHUP / reload）阶段采用极度严格的校验机制：
- 配置模型体系基于 Pydantic v2，基类 `Section` 统一设置 `model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)`。
- 入口通过 `ProxyConfig.model_validate(merged)` 进行全量构造校验。只要 YAML、环境变量或 CLI 存在任何未知字段、类型不匹配、枚举越界或子模型校验失败，直接抛出 `pydantic.ValidationError`。
- 在服务启动时，该异常导致服务直接崩溃退出；在配置热重载时，`ConfigProvider.reload()` 捕获到异常（由于未特殊拦截 Pydantic 错误，直接向上抛出），虽保全了已有快照不被损坏，但完全阻断了任何配置的更新生效。

用户指出：当前严格的 Pydantic 配置检查在很多地方是不必要的（例如上游客户端/下游配置文件常见的前向兼容键、打错不影响核心运行的注释性键、局部独立 provider 的语法错误等），希望讨论哪些应改为 **warn and continue**（发出告警并继续运行），从而提升运行韧性与运维体验。

本调研报告不对“宽松更好”作预设推断，而是依据当前代码架构、安全契约（`13-redefined-security.md`）、不可变性约束、多协议路由与运行时依赖关系，全面盘点配置载入与 ValidationError 的所有边界，逐类评估其容错可行性、不能容错的深层原因、安全降级策略及必要诊断信息。

---

## 2. 配置载入与验证边界全景盘点

配置加载全链路经历五层合并（`app.config.loading.load_proxy_config`）：
`bundled-config.yaml` → `user config.yaml`（经 `migrate_compat` 与相对路径重基准） → `GHC_API_PROXY_*` 环境变量（按 `__` 展开嵌套与扁平别名映射） → CLI 显式参数。
最终合并字典送入 `ProxyConfig.model_validate(merged)`。

### 2.1 边界分类全景

| 边界大类 | 具体分布与代表性字段 | 当前 Pydantic / 逻辑校验行为 | 失败触发的 Exception |
|---|---|---|---|
| **A. 未知键 (Extra Keys)** | `Section` 级基类、`ProxyConfig` 顶层、各嵌套子模型（`server`、`hooks`、`model_providers.<name>` 等） | `extra="forbid"`，任何未声明的键均引发错误 | `ValidationError: Extra inputs are not permitted` |
| **B. 标量类型与数值范围约束** | `server.port` (1..65535)、`local_estimate_multiplier` (ge=1.0, 且禁止 bool)、超时与重试次数 (`ge=0`)、`buffer_cap_bytes`、`max_inflight` 等 | Pydantic 内置类型转换及 `ge`/`le` 校验，自定义 `@field_validator` 拦截 bool 等 | `ValidationError: Input should be greater than or equal to...` / `ValueError` |
| **C. 字符串非空/空白与格式约束** | Xingchen / CommandCode / Bridge 的 `api_base_url`（绝对 HTTP/S URL）、`api_key`（min_length=1、禁止空白）、`server.history_export_token`（min_length=16） | `@field_validator` 自定义 `urlsplit` 检查或 `min_length` 约束 | `ValidationError: Value error, api_base_url must be a valid absolute HTTP(S) URL` |
| **D. 强类型枚举与字面量 (Literal / Enum)** | `buffering_policy` ("block"\|"until-tool-use"\|"full")、`cache_control` ("disabled"\|"passthrough"\|"sanitize"\|"proxied")、`tls.mode` (bool\|"both")、`fingerprint_mode` 等 | `typing.Literal` 严格匹配，非预期值直接拒收 | `ValidationError: Input should be 'block', 'until-tool-use' or 'full'` |
| **E. 模型映射与正则表达式表** | `model_mappings` (dict[str, str])、`models_support_web_search` (list[str])、`strip_anthropic_beta_flags` (dict[str, list[str]])、`cache_control_sanitize` (dict[str, list[str]]) | 校验语法格式；并在运行时（`Chain.__post_init__` 或请求期）执行 `re.compile()` | Pydantic 校验 `dict[str, str]`，若含非 str 报 ValidationError；非法正则报 `re.error` |
| **F. Provider 判别联合与实例配置** | `model_providers: dict[str, Annotated[..., Field(discriminator="type")]]`（包含 `github_copilot`, `xingchen`, `codebuddy`, `commandcode`, `bridge`） | 1. 键名校验：`_reject_unaddressable_provider_names`（禁止包含 `/` 或为空）<br>2. 判别键 `type` 匹配<br>3. 各 provider 独立字段完整性（如 xingchen 的 5 项必填凭证、commandcode 的 fingerprint 约束） | `ValidationError: Unable to extract tag using discriminator 'type'` / `Field required` |
| **G. 重启锁定字段变更 (Restart-Only)** | `NOT_HOT_RELOADABLE`（包含 `server.host/port`、`proxy`、大部分 provider 静态字段、`upstream_transport.http2` 等共 36 项）及 `PROVIDER_NOT_HOT_RELOADABLE` | 由 `pin_restart_only` 处理：将候选值重置为启动初值，记录到 `ReloadOutcome.restart_required` | 不抛异常，静默保留启动值并输出重启报告 |

---

## 3. 逐类评估：启动与热重载的正确处理策略

针对各边界，需区分三种处理策略：
1. **策略 R (Refuse)**：拒绝启动 / 拒绝本次热重载（保留旧快照）。
2. **策略 W-Drop (Warn and Drop/Ignore Key)**：告警并忽略单键，降级使用默认值。
3. **策略 W-Disable (Warn and Disable Instance)**：告警并剔除/隔离单 provider 实例，不影响其他 provider 正常工作。

### 3.1 边界处理评估矩阵

| 边界项 / 场景 | 启动时推荐处理 | 热重载时推荐处理 | 正确性与安全影响分析 |
|---|---|---|---|
| **A. 未知键 (Extra Keys)** (顶层或子 Section) | **Warn and Ignore (W-Drop)** | **Warn and Ignore (W-Drop)** | 绝大多数未知键为注释失误、版本升级前后的废弃键（如旧版 `manual`, `rate-limit`）或客户端/运维扩展键。直接崩溃极为脆弱。丢弃并 `logger.warning` 对核心运转无害。 |
| **B1. 端口与网络监听 (`server.host/port`)** | **Refuse (R)** | **Pin to Startup (现有机制)** | 监听端口错配或越界（如 port="abc" 或 99999）无法 bind，启动必须失败；热重载时端口已锁定（由 `pin_restart_only` 覆盖），不可动态变更。 |
| **B2. 核心鉴权令牌 (`server.history_export_token`)** | **Refuse (R)** | **Refuse / Pin (R)** | 安全契约强制要求：History transport 暴露全量取证凭证，必须 fail-closed。若长度不足 16 位强行启动将击穿凭证防护或导致授权检查失效。 |
| **B3. 运行数值与超时限制 (`timeouts`, `retries`, `buffer_cap`)** | **Warn and Fallback (W-Drop)** | **Warn and Fallback (W-Drop)** | 如配置了负数重试次数或非法超时字符串，回退至 schema 默认值（或保留热加载前旧值）并输出 WARN。其物理边界由代码默认常数兜底，不会造成状态机崩溃。 |
| **C1. 基础 URL 格式 (`api_base_url`)** | 见 Provider 隔离 (W-Disable) | 见 Provider 隔离 (W-Disable) | 若单 provider 的 base_url 格式损坏，破坏该 provider 通信；若该 provider 是 `default_model_provider`，影响全局。 |
| **D1. 核心状态机枚举 (`buffering_policy`, `tls.mode`)** | **Refuse (R)** | **Refuse (R)** | 交付策略 "block" / "full" 决定了整条流式分帧与背压状态机的底层逻辑。若填入 "stream" 等伪值，无法在不改变语义的情况下凭空猜测，容错会导致不可预期的协议违约。 |
| **D2. 次要特性枚举 (`reasoning_encrypted_include`, `cache_control`)** | **Warn and Fallback (W-Drop)** | **Warn and Fallback (W-Drop)** | 回退至安全默认值（如 "passthrough" / "sanitize"），记录 WARN 告知降级。对主路由流转无破坏性。 |
| **E1. 正则表达式语法 (`web_search_models`, `beta_flags`)** | **Warn and Drop Entry (W-Drop)** | **Warn and Drop Entry (W-Drop)** | 单个正则损坏（如 `[` 未闭合）若打崩整体服务极不合理。应告警并丢弃该条正则模式，其他规则正常编译。若整项为空则回退默认。 |
| **E2. 模型映射表 (`model_mappings`)** | **Warn and Drop Mapping (W-Drop)** | **Warn and Drop Mapping (W-Drop)** | 若某条映射目标格式不支持或语法非法，丢弃该单条映射并警告，未出错映射照常生效。若目标未命中在请求期自然走 400 保护。 |
| **F1. 单个 Provider 内部语法/必填项错误** | **Warn and Disable (W-Disable)**（非 default 时）<br>**Refuse (R)**（当且仅当 default 时） | **Warn and Disable (W-Disable)** | 若配置了 3 个 provider（如 copilot, bridge, xingchen），仅 bridge 缺少 api_key，将整个 proxy 拒起是不合理的。应标记 bridge 为 `disabled/uninitialized`，其余 provider 照常工作。只有当损坏的 provider 是唯一的 `default_model_provider` 且无任何可用 provider 时才必须拒绝启动。 |
| **F2. Provider 键名非法 (`/` 或 空白)** | **Refuse (R)** | **Refuse (R)** | 静态名称冲突与路由解析歧义：`A/B` 导致请求解析截断为 unknown provider `A` 并静默路由给 fallback，造成流量静默窜改。属于严重语义冲突。 |

---

## 4. 深度论证：为什么某些项绝不能安全局部容错？

任何容错设计都必须回答：“如果猜错了默认值，系统会发生什么破坏？”以下三类属于绝对不可盲目容错（Refuse）的底线：

### 4.1 核心网络与安全边界破坏（Fail-Closed 违约）
- **`server.history_export_token`**：
  代码与架构明确规定：`History transport can carry upstream credentials, so it must fail closed`。如果运维输入了 8 位短字符，若系统“容错”截断或默认置空，将导致任意能够连上本机的调用者直接免鉴权或低复杂度拖走原始认证凭证与对话敏感数据。
- **Provider 命名含 `/` 或为空**：
  路由层 `split_provider_qualifier` 强依赖 `/` 作为限定符。若容忍 `A/B` 作为 provider 名，所有向 `A/B/model` 发送的请求在 `rpartition` 或 `split` 时均会被错误切割为 provider=`A`、model=`B/model`。这不仅导致该 provider 无法被寻址，还会触发静默回退（fallback），将预期发往内部私有模型的数据发送至默认上游（如公网 Copilot），造成严重的未预期数据外溢。

### 4.2 交付语义与状态机协议破坏
- **`client_delivery.buffering_policy` ("block" | "until-tool-use" | "full")**：
  项目核心契约是**“块级交付”（Block-level delivery）**（见 MEMORY.md: `say-block-level-delivery-not-streaming.md`）。这是下游客户端（如 Claude Code）解析多模态、思考块与工具调用的基石。如果配置了无法识别的模式，系统无法假设应该退回 raw SSE streaming（系统压根未实现也不支持），若随意降级为 full，则可能导致客户端因 10 分钟收不到任何首块而产生超时断连。
- **`upstream_transport.http2` / `max_streams_per_connection`**：
  连接池复用与 GOAWAY 隔离是极高风险的物理传输层边界。配置必须精确映射物理连接行为，任何伪容错（如解析失败强行开 h2）都会重现 active-stream loss。

### 4.3 整体唯一根依赖缺失
- **损坏的 Provider 恰好是 `default_model_provider` 且无后备可用**：
  如果系统中唯一的兜底上游的凭据或配置完全损坏，服务即便强行启动，所有的健康检查 `/health/readiness` 也会是 503，所有入站请求均会返回 400/502。此时强行“假成功启动”会蒙骗 systemd 进程管理器，导致客户端流量持续涌入黑洞，不如在启动阶段立即 fail-fast 报错。

---

## 5. 明确具有独立边界可安全降级（Warn & Continue）的项

### 5.1 未知配置键 (Extra / Unknown Keys)
- **隔离边界**：Pydantic 模型的 `extra="ignore"`，配合前置收集或自定义 root validator。
- **机制**：由 `extra="forbid"` 放宽为 `extra="ignore"` 或在验证前通过 schema 字段集对比，过滤出未知键。
- **诊断信息**：
  ```text
  [WARN] config: ignoring unknown configuration key 'hooks.legacy_approval' at section 'hooks'
  ```

### 5.2 单个 Provider 局部损坏与隔离（Multi-Provider Resilience）
- **隔离边界**：`model_providers` 字典。每个 provider 是独立的配置与运行时子图。
- **机制**：
  在校验 `model_providers` 映射时，对每个 provider 单独进行 `model_validate`。若 provider `foo` 抛出 `ValidationError`：
  1. 若 `foo == default_model_provider` 且系统无其他合法 provider：拒绝启动。
  2. 否则：从候选有效 `model_providers` 中剔除 `foo`，记入 `disabled_providers`，输出严重警告（WARN/ERROR）；
  3. `/api/status` 将该 provider 状态标为 `uninitialized: <validation_error>`，`/models` 不暴露其模型；
  4. 其他 provider（如 `ghc`）继续正常工作，请求该损坏 provider 时在路由期明确报错 404/400（`UnknownProvider`）。
- **诊断信息**：
  ```text
  [WARN] config: provider 'bridge_local' failed validation and is disabled: field required: api_base_url (type=missing)
  ```

### 5.3 规则匹配表与正则单项损坏（Regex Tables）
- **隔离边界**：`models_support_web_search`、`strip_anthropic_beta_flags`、`cache_control_sanitize`。
- **机制**：将整表拒绝改为单项过滤。在解析/编译正则时，单个模式报错（`re.error`）仅丢弃该条正则，发出 WARNING，保留其余合法模式。
- **诊断信息**：
  ```text
  [WARN] config: invalid regular expression in 'models_support_web_search': 'gpt-[5-9(\\' (unterminated character set); pattern skipped
  ```

### 5.4 非核心数值超限与字段拼写废弃
- **隔离边界**：`timeouts`、`rate_limiters`、`retry`。
- **机制**：利用 Pydantic validator 将非法值截断至合法区间，或回退至 `Field(default=...)`，记录警告。

---

## 6. 现有 Warning 与兼容机制、测试证据盘点

项目中已存在部分容错与警告机制的先例，但目前分布零散、机制不统一：

### 6.1 现有机制证据
1. **`app.config.compat.migrate_compat`**（结构兼容与 DeprecationWarning）：
   - 文件：`src/app/config/compat.py`
   - 机制：在 YAML 解析完成后拦截旧键，自动迁移至新键并发出 `warnings.warn(..., DeprecationWarning)`。
   - 覆盖键：`fallback_model_provider` → `default_model_provider`，`history.limit` → `success_limit`，`timeouts.stream_idle_timeout` → `stream_idle` 等。
   - 测试支撑：`tests/unit/config/test_config_loading.py:test_legacy_yaml_fallback_provider_migrates_to_default`。
2. **`app.cli._load_spec_config`**（CLI 废弃参数报告）：
   - 文件：`src/app/cli.py:86-136`
   - 机制：对已无 spec 归宿的 CLI 参数（如 `--manual`, `--rate-limit`），不直接崩溃，而是收集为 `inactive: list[tuple[str, str]]`，由 `cli.py:318` 统一输出提示而不中断启动。
3. **`app.config.provider.pin_restart_only`**（热重载隔离）：
   - 文件：`src/app/config/provider.py:139-171`
   - 机制：当热重载试图修改 `NOT_HOT_RELOADABLE` 字段时，不报错退出，而是强行恢复为启动初值，并在 `ReloadOutcome.restart_required` 记录被忽略的路径。
   - 测试支撑：`tests/unit/config/test_config_loading.py:test_restart_only_scalar_is_pinned_to_the_startup_value` 等 7 个单元测试。
4. **启动期非致命服务降级**（Lifespan 容错）：
   - 文件：`src/app/server/pipeline_app.py:151-184`
   - 机制：`refresh_catalogs` 失败时仅打印 warning 并标记 `readiness=False`，允许进程启动；`history_writer` 启动失败时置 `None` 并继续。

---

## 7. 实施优先级建议与演进路线

建议按“风险极低、收益极大”的原则分阶段实施：

### 优先级 1 (P0 - Immediate Low Risk)：未知键容错 (Extra Keys Tolerance)
- **目标**：彻底解决因编写了未来字段、调试字段或打错顶层键导致的服务拒起。
- **改动面**：修改 `Section` 的 `model_config = ConfigDict(extra="ignore")`，或增加 pre-validator 捕获 extra keys 并统一使用 `logger.warning("Unrecognized configuration key: %s (ignored)", key)` 打印。
- **风险**：极低。不影响已声明字段的类型校验。

### 优先级 2 (P1 - High Value)：Provider 局部隔离容错 (Provider Fault Isolation)
- **目标**：实现单个第三方或实验性 provider 配置错误时不拖垮整体 proxy 启动。
- **改动面**：在 `ProxyConfig` 构造或 `load_proxy_config` 阶段，对 `model_providers` 的每个条目尝试局部验证。失败者打上 `ValidationFailedProvider` 标记并从运行时 provider 列表剔除，记录详细 WARN；仅当 `default_model_provider` 损坏且无可替代时报错拒绝。
- **风险**：低。受影响的仅是本身配置错误的 provider。

### 优先级 3 (P2 - Medium Value)：列表与正则模式容错 (Regex/List Resilience)
- **目标**：避免单个正则或映射语法错误导致全局失效。
- **改动面**：在 `models_support_web_search`、`cache_control_sanitize` 等涉及正则编译处，增加 `re.error` 捕获，丢弃坏模式并记录 WARN。
- **风险**：低。需要确保丢弃坏模式后，有默认/兜底行为生效。

### 优先级 4 (P3 - Polish)：热重载报告强化 (Reload Diagnostics)
- **目标**：热加载遇到配置错误时，不仅是保持旧快照，还应通过管理接口（如 `/api/config/status` 或日志）暴露最新的校验失败诊断日志，便于运维查看为何重载未生效。

---

## 8. 调研中明确否决的路线 (Rejected Alternatives)

在本次调研推演中，以下方案经过严格技术权衡已被明确否决：

1. **否决全盘 `model_validate(..., strict=False)` 与隐式类型强转**：
   - *理由*：Pydantic 默认是宽松模式，但盲目对布尔、枚举进行宽松解析极其危险。例如在 YAML 1.1 中，`off` / `no` 会被转为 `False`；若用于 `assistant_message_layout`，Pydantic 会误将其解析为布尔值而非具体模式，造成语义漂移。类型边界必须维持严谨，不能用“模糊猜想”替代明确配置。
2. **否决对 `server.history_export_token` 等安全凭据做默认降级或截断**：
   - *理由*：严重违反 `13-redefined-security.md` 中的安全契约。安全特性的缺失必须是显式的、受控的，绝不能把安全失控伪装为容错。
3. **否决对 `model_providers` 命名中的 `/` 进行自动替换（如替换为 `_`）**：
   - *理由*：隐式修改 provider 名字会导致客户端以原名 `provider/model` 请求时永远无法匹配，反而产生更隐蔽的 404 故障。必须在静态边界显式阻断。
4. **否决在热重载失败时自动将配置部分回滚至 `bundled-config`**：
   - *理由*：热重载失败必须严格保持**当前正在运行的内存快照**，绝不能回退到 bundled。回退到 bundled 会把正在运行的生产自定义配置突然刷掉，造成灾难性生产事故。现有 `test_failed_reload_leaves_the_current_snapshot_in_place` 的行为是绝对正确的。
