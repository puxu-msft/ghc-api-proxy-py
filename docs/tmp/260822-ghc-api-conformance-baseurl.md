# GHC API Base URL 需求对照核查

日期：2026-08-22
对照需求：`docs/.human-controlled/ghc-api.md`（用户亲笔）第 10-19 行

## 结论表

| 需求条目 | 现状 | 判定 | 证据 |
|---|---|---|---|
| `individual` → `api.githubcopilot.com` | 常量 `INDIVIDUAL_BASE_URL = "https://api.githubcopilot.com"`，与文档逐字符一致 | 已实现且已接线（当前默认唯一可达分支） | `src/app/model_provider/ghc_client/config.py:6,46-47` |
| `business` → `api.business.githubcopilot.com` | `f"https://api.{account_type}.githubcopilot.com"`，`account_type="business"` 时得到该值，与文档一致 | 代码已实现；但当前实际服务启动路径无法把 `account_type` 设为 `"business"`（见下） | `src/app/model_provider/ghc_client/config.py:48` |
| `enterprise` → `api.enterprise.githubcopilot.com` | 同上，`account_type="enterprise"` | 同上 | 同上 |
| self-hosted → `msft.ghe.com` | **代码中不存在此固定值。** `account_type == "self-hosted"` 分支直接 `raise ValueError`，要求必须显式提供 `api_base_url_override`；`msft.ghe.com` 仅出现在一行注释里作为「举例」 | 与文档字面矛盾：文档把 `msft.ghe.com` 列成该行的「API Base URL」值，代码里它不是任何默认值，只是注释示例 | `src/app/model_provider/ghc_client/config.py:43-45`（`# A self-hosted host (e.g. msft.ghe.com) cannot be derived; it must be configured.`） |
| 「如未配置，根据用户订阅自动识别选择」 | 探测逻辑**确实存在**：`infer_account_type()` 读 `/copilot_internal/user` 响应里的 `copilot_plan` / `access_type_sku` 字段做字符串匹配（`enterprise`/`business`/`individual|free|pro`），`GitHubAccountClient` 负责发起该请求；`initialize_upstream_services()`（`app/upstream/bootstrap.py`）在 `account_type is None` 且未显式给 `ghc_api_base_url` 时调用它，结果写回 `settings.auth.account_type`。**但这整条链路只挂在 legacy 的 `app.server.app_factory.create_app`（`AppSettings`）上**；当前实际服务启动路径 `cli.py → app.server.composition.build_chain → app.server.pipeline_app.create_pipeline_app` 完全不经过 `bootstrap.py`，也从不调用 `infer_account_type`。`composition.py` 里构造 `GhcClientConfig` 时只传 `api_base_url_override`/`auth_base_url_override`，从不传 `account_type`，因此当前活跃路径下 `account_type` 恒为 dataclass 默认值 `"individual"`（`config.py:23`）——未配置时的实际行为是**静默固定为 individual**，既不报错也不探测 | **已实现，但未接线到当前生产路径**（只接在已声明为 legacy 的旧链路上） | 探测实现：`src/app/model_provider/ghc_client/account.py:7-21`；旧链路调用点：`src/app/upstream/bootstrap.py:180-189`；新链路未传参：`src/app/server/composition.py:357-360, 407-410`；新旧链路定性：`src/app/server/app_factory.py`（被 `src/app/server/__init__.py:8` 与 `src/app/observability/metrics.py:5` 明文称为 "legacy app_factory"）vs `src/app/server/pipeline_app.py:6-10`（"the new chain"）；`cli.py` 实际只用新链路：`src/app/cli.py:22-23, 148-151, 170-176` |
| base URL 是否真接线到实际请求 | 是。`build_copilot_provider()` 用 `ghc_config.api_base_url` 同时构造 `AsyncOpenAI(base_url=...)` 与 `AsyncAnthropic(base_url=...)`（openai/anthropic 官方 SDK），再包进 `GhcApiClient`；`GhcApiClient.post`/等方法直接调用 `self._openai.post(...)` / `self._anthropic.post(...)`，SDK 内部会用其 `base_url` 拼出请求 URL——没有第二处再覆盖它 | 已实现且已接线（对于 override / individual 默认这两个可达分支） | `src/app/server/composition.py:356-385`；`src/app/model_provider/ghc_client/client.py:23,40-41,76,92` |
| 账户类型配置项：`src/app/config/` 现状 | 存在**两套并存的配置模型**：①旧 `AppSettings`（`app/config/settings.py`），有 `auth.account_type: Literal["individual","business","enterprise","self-hosted"] \| None`字段，仅服务于 legacy `--fd`/`app_factory` 路径（`app/config/loader.py:1` 自称 "Loading for the *old* `AppSettings`"）；②新 `ProxyConfig`/`ModelProviderConfig`（`app/config/schema.py`，"matching `docs/.human-controlled/config.example.yaml`"），**完全没有 `account_type` 字段**，`ModelProviderConfig` 只有 `type`/`api_base_url`/`auth_base_url`/`github_token_file`/`model_refresh_interval`/`disabled_models`/`models_support_web_search` | 现状分裂：只有已废弃的旧模型有此配置项 | `src/app/config/settings.py:31-35`；`src/app/config/loader.py:1`；`src/app/config/schema.py:83-125`（无 account_type） |
| 账户类型配置项：`docs/.human-controlled/config.example.yaml` 形态 | 该文件完全**不提账户类型**，也没有 `auth:` 顶层节（`cli.py:77` 注释自认："config.example.yaml has no `auth` section"）。唯一相关旋钮是被注释掉的 `model_providers.ghc.base_url: "https://api.githubcopilot.com"`（键名 `base_url`） | 与代码不一致（键名） | `docs/.human-controlled/config.example.yaml:154-159` |
| 两者是否一致 | **不一致，且是会直接炸掉的那种**：`config.example.yaml` 写的键名是 `base_url`，但 `ModelProviderConfig` 实际字段名是 `api_base_url`（无 alias），`Section` 又是 `extra="forbid"`。已用 `ProxyConfig.model_validate` 实测：把该注释行原样取消注释会得到 `pydantic.ValidationError: model_providers.ghc.base_url Extra inputs are not permitted [extra_forbidden]`。以 `config.example.yaml`（用户权威文档）为准，此处代码字段名与文档不符 | 文档-代码不一致（已用代码验证复现） | 字段定义：`src/app/config/schema.py:86`；文档键名：`docs/.human-controlled/config.example.yaml:159`；复现命令见下 |
| 是否存在允许覆盖 base URL 的配置项（应对企业各自 GHES 域名） | 存在：`model_providers.<name>.api_base_url`（`ModelProviderConfig.api_base_url`），任意字符串直接作为 `api_base_url_override` 传入 `GhcClientConfig`，非空即整体替换、不受 `account_type` 限制——这与文档「self-hosted 域名各企业不同」的现实相符，比文档字面暗示的固定 `msft.ghe.com` 更合理。但由于当前 schema 没有 `account_type` 字段，**这条 override 是当前唯一能让 base URL 偏离 individual 默认值的手段**（business/enterprise 语义化选择在新链路上不可达，只能自己拼完整 URL） | 已实现且已接线，但被迫承担了「本该由 account_type 完成」的全部职责 | `src/app/config/schema.py:86`；`src/app/model_provider/ghc_client/config.py:24,39-42` |

## 复现命令（只读，未修改任何文件）

```python
# uv run python -c "..."
from app.config.schema import ProxyConfig
ProxyConfig.model_validate({
    "model_providers": {"ghc": {"type": "github_copilot", "base_url": "https://api.githubcopilot.com"}}
})
# -> pydantic_core._pydantic_core.ValidationError: 1 validation error for ProxyConfig
#    model_providers.ghc.base_url  Extra inputs are not permitted [type=extra_forbidden, ...]
```

## 关键代码位置速查

- `src/app/model_provider/ghc_client/config.py` — `GhcClientConfig`/`resolve_api_base_url`，四种账户类型的 URL 拼接与 self-hosted 报错分支。
- `src/app/model_provider/ghc_client/account.py` — `infer_account_type` 探测实现 + `GitHubAccountClient`（`/user`、`/copilot_internal/user`）。
- `src/app/upstream/bootstrap.py:180-189` — 探测逻辑唯一的调用点，挂在 legacy 链路。
- `src/app/server/composition.py:356-385,388-420` — 当前生产链路构造 `GhcClientConfig` 处，未传 `account_type`。
- `src/app/config/settings.py` vs `src/app/config/schema.py` — 新旧两套配置模型，`account_type` 只存在于旧模型。
- `src/app/server/app_factory.py` vs `src/app/server/pipeline_app.py`/`src/app/server/__init__.py:6-13` — 新旧两条服务链路的项目自述定性（"legacy" vs "the new chain"）。

## 一句话摘要

四种 URL 的字符串拼接规则本身写对了三种（individual/business/enterprise），self-hosted 没有把 `msft.ghe.com` 当默认值（合理，但与文档字面矛盾，值得请用户确认文档措辞）；「未配置自动识别订阅」这条重点需求**曾经做出来过，但只焊在了项目自己标注为 legacy 的旧链路上，当前实际启动的服务完全不会触发它**，未配置时是静默恒为 individual；新配置 schema 里 `account_type` 整个消失了，`config.example.yaml` 里对应的 `base_url` 键名和代码实际字段名 `api_base_url` 对不上，已用代码实测复现该冲突会导致配置验证失败。
