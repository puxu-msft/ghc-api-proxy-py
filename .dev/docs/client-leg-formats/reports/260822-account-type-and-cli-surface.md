# 勘察报告：A. `account_type` 自动识别接线到新链路 / B. 删除 `--ghc-api-base-url`

日期：2026-08-22。只读勘察，未修改任何文件。

## A-1. `infer_account_type` 与 `GitHubAccountClient` 的完整签名与行为

`src/app/model_provider/ghc_client/account.py:1-66`（全文件，无删节）：

```python
from collections.abc import Mapping

import httpx2

from app.model_provider.ghc_client.config import GITHUB_AUTH_BASE_URL

USER_PATH = "/user"
COPILOT_USER_PATH = "/copilot_internal/user"
GITHUB_API_VERSION = "2022-11-28"
COPILOT_INTERNAL_API_VERSION = "2025-04-01"


def infer_account_type(usage: Mapping[str, object]) -> str | None:
    haystack = f"{usage.get('copilot_plan', '')} {usage.get('access_type_sku', '')}".lower()
    if "enterprise" in haystack:
        return "enterprise"
    if "business" in haystack:
        return "business"
    if any(marker in haystack for marker in ("individual", "free", "pro")):
        return "individual"
    return None


class GitHubAccountClient:
    """Read-only GitHub REST endpoints describing the Copilot subscription.

    Used only to infer the account type, which selects the API base URL.
    """

    def __init__(
        self,
        http_client: httpx2.AsyncClient,
        *,
        auth_base_url: str = GITHUB_AUTH_BASE_URL,
    ) -> None:
        self._http = http_client
        self._auth_base_url = auth_base_url.rstrip("/")

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"token {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    async def get_user(self, token: str) -> dict[str, object]:
        response = await self._http.get(
            f"{self._auth_base_url}{USER_PATH}",
            headers=self._headers(token),
        )
        response.raise_for_status()
        data: dict[str, object] = response.json()
        return data

    async def get_copilot_usage(self, token: str) -> dict[str, object]:
        headers = self._headers(token)
        headers["X-GitHub-Api-Version"] = COPILOT_INTERNAL_API_VERSION
        response = await self._http.get(
            f"{self._auth_base_url}{COPILOT_USER_PATH}",
            headers=headers,
        )
        response.raise_for_status()
        data: dict[str, object] = response.json()
        return data
```

要点：

- `infer_account_type` 是纯函数，同步，只读一个 `Mapping[str, object]`（`get_copilot_usage` 的返回体），返回 `"enterprise" | "business" | "individual" | None`。判据是对 `copilot_plan` + `access_type_sku` 两个字段拼接后做子串匹配，`None` 表示两个字段都不认识（保守：不猜）。
- `GitHubAccountClient` 依赖：一个已构造好的 `httpx2.AsyncClient`（不建自己的连接池）、一个 `auth_base_url`（默认 `GITHUB_AUTH_BASE_URL = "https://api.github.com"`，可覆盖），以及调用时传入的裸 GitHub token（不是 Copilot token）。
- 两个方法都是 `async def`，都发 `GET`，都用 `token {token}` 认证头（不是 `Bearer`，这是 GitHub REST 的旧式方案头）。`get_copilot_usage` 请求 `{auth_base_url}/copilot_internal/user`，`X-GitHub-Api-Version: 2025-04-01`；`get_user` 请求 `{auth_base_url}/user`（当前无调用点，只有 `get_copilot_usage` 被用于探测）。
- **关键：探测走的是 `auth_base_url`（`api.github.com` 一侧），完全不碰 `api_base_url`（推理侧）**。这一点是回答 A-3 里“先有鸡还是先有蛋”问题的核心依据。

## A-2. legacy `bootstrap.py:161-230` 完整逻辑

`src/app/upstream/bootstrap.py:161-230`（全文，未删节）：

```python
    token_path = Path(settings.auth.token_file) if settings.auth.token_file else None
    file_provider = FileTokenProvider(token_path)
    github_tokens = GitHubTokenManager(
        [
            CLITokenProvider(settings.auth.github_token),
            EnvTokenProvider(),
            file_provider,
        ]
    )
    github_info = await github_tokens.get_token()
    runtime.github_token_ready = True
    copilot_tokens = CopilotTokenManager(
        GitHubTokenSourceAdapter(github_tokens),
        client,
        identity_headers=build_copilot_identity_headers(settings),
    )
    await copilot_tokens.ensure_valid_token()
    runtime.copilot_token_ready = True

    account_type = settings.auth.account_type
    if account_type is None and not settings.upstream.ghc_api_base_url:
        usage = await GitHubAccountClient(client).get_copilot_usage(github_info.token)
        inferred = infer_account_type(usage)
        account_type = cast(AccountType, inferred or "individual")
        settings = settings.model_copy(
            update={"auth": settings.auth.model_copy(update={"account_type": account_type})}
        )
    else:
        account_type = account_type or "individual"

    sdk_clients = create_copilot_sdk_clients(settings, http_client=client)
    interaction_id = str(uuid4())
    target = CopilotUpstream(
        sdk_clients,
        copilot_tokens,
        settings,
        interaction_id=interaction_id,
    )
    base_url = resolve_copilot_base_url(settings)
    catalog = ModelCatalog(client, base_url, disabled_ids=set(settings.disabled_models))
    token = await copilot_tokens.get_token()
    await catalog.refresh(
        build_copilot_headers(token, settings, interaction_id=interaction_id)
    )
```

顺序（完全线性，无环）：

1. 组装 GitHub token 来源链（CLI/env/file），`await github_tokens.get_token()` 拿到裸 GitHub token（`github_info.token`）。
2. 构造 `CopilotTokenManager`（用 `client` 这个共享 `httpx.AsyncClient`），`await ensure_valid_token()` —— 这一步走的是 `CopilotTokenManager` 自己默认的 `auth_base_url`（同样是 `GITHUB_AUTH_BASE_URL`，与 `account_type` 完全无关），换出一枚 Copilot token。**这一步不依赖 `account_type`。**
3. **探测条件**：`account_type is None and not settings.upstream.ghc_api_base_url` —— 只有当（a）用户没有显式配置 `account_type` **且**（b）用户也没有显式配置 `ghc_api_base_url`（一旦手工指定了推理 base_url，探测毫无意义，直接跳过）时才探测。
4. 探测失败怎么办：**没有 try/except**。`GitHubAccountClient.get_copilot_usage` 内部 `response.raise_for_status()` 会在非 2xx 时抛 `httpx.HTTPStatusError`；这里没有捕获，异常会直接向上冒泡，导致 `initialize_upstream_services` 失败——即探测失败=启动失败（在这条 legacy 路径上）。`infer_account_type` 返回 `None`（能连上但字段不认识）时才会静默降级为 `"individual"`（`inferred or "individual"`）。
5. 结果写回哪里：`account_type` 变量本身，并且**回写进 `settings`**（`settings.model_copy(update={"auth": settings.auth.model_copy(update={"account_type": account_type})})`），随后这份新 `settings` 一路向下传给 `create_copilot_sdk_clients`、`resolve_copilot_base_url`、`build_copilot_headers` 等，且最终 `runtime.settings = settings`（第 230 行）替换掉运行时设置。也就是说探测结果被永久固化进这次启动的配置快照。
6. 若跳过探测（条件不满足），`account_type = account_type or "individual"`——用户配了就用用户的，否则兜底 `"individual"`，不做任何网络调用。
7. 之后才 `resolve_copilot_base_url(settings)` 算出推理 host、`ModelCatalog(...)`、`await copilot_tokens.get_token()` 换 Copilot token、`await catalog.refresh(...)` 拉模型目录——这些都在 `account_type` 已经落定之后发生。

## A-3. 新链路 `composition.py` 两处构造点的完整上下文

### 3a. `build_copilot_provider`（`src/app/server/composition.py:348-385`）

```python
def build_copilot_provider(
    name: str,
    config: ProxyConfig,
    *,
    http_client: httpx2.AsyncClient,
    token_manager: CopilotTokenManager,
    interaction_id: str,
) -> GithubCopilotProvider:
    provider_config = config.model_providers[name]
    ghc_config = GhcClientConfig(
        api_base_url_override=provider_config.api_base_url,
        auth_base_url_override=provider_config.auth_base_url,
    )
    base_url = ghc_config.api_base_url
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
        AsyncAnthropic(
            api_key="proxy-managed",
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        ),
        token_manager,
        ghc_config,
        interaction_id=interaction_id,
    )
    return GithubCopilotProvider(
        name,
        client,
        provider_config,
        http_client=http_client,
        base_url=base_url,
    )
```

**同步函数（`def`，不是 `async def`）**。`base_url = ghc_config.api_base_url` 在构造时就被算死并塞进 `AsyncOpenAI`/`AsyncAnthropic` 的 `base_url=`——之后不会再变。`GhcClientConfig` 目前永远不传 `account_type`，恒为 dataclass 默认值 `"individual"`（见 A-4）。

### 3b. `build_chain` 里对应片段（`src/app/server/composition.py:388-424`，节选调用点）

```python
def build_chain(
    config: ProxyConfig,
    *,
    http_client: httpx2.AsyncClient,
    providers: dict[str, ModelProvider] | None = None,
    subscribers: SubscriberRegistry[RequestContext] | None = None,
    interaction_id: str = "interaction",
) -> Chain:
    if providers is None:
        built: dict[str, ModelProvider] = {}
        for name, provider_config in config.model_providers.items():
            if provider_config.type != PROVIDER_TYPE:
                raise ValueError(f"unsupported provider type {provider_config.type!r}")
            token_source = build_github_token_source(config, name)
            ghc_config = GhcClientConfig(
                api_base_url_override=provider_config.api_base_url,
                auth_base_url_override=provider_config.auth_base_url,
            )
            token_manager = CopilotTokenManager(
                token_source,
                http_client,
                auth_base_url=ghc_config.auth_base_url,
                identity_headers=build_identity_headers(ghc_config),
            )
            built[name] = build_copilot_provider(
                name, config, http_client=http_client,
                token_manager=token_manager, interaction_id=interaction_id,
            )
        providers = built
    ...
```

**`build_chain` 本身也是同步函数**（不是 `async def`）。它在这个循环里，对每个 provider：

- 用 `build_github_token_source(config, name)` 组出 CLI/env/file 的 `GitHubTokenSourceAdapter`（但**没有调用 `.get_token()`**——只是把 provider 链组好，真正取裸 token 是 `async def get_token()`，这里从未 await）。
- 构造 `GhcClientConfig`（此时 `account_type` 恒默认）。
- 构造 `CopilotTokenManager`（这一步不发网络请求，只是把依赖装配好）。
- 调 `build_copilot_provider`，里面 `base_url = ghc_config.api_base_url` 已经把 URL 算死。

**catalog 刷新是异步启动时单独做的**：`build_chain` 本身完全不发 HTTP，真正认证 + 拉模型目录发生在 `refresh_catalogs(chain)`（`composition.py:455-465`），由 `pipeline_app.py:819` 的 FastAPI `_lifespan`（`@asynccontextmanager async def _lifespan(app)`，`pipeline_app.py:799-829`）调用：

```python
    try:
        await refresh_catalogs(chain)
    except Exception as error:
        logger.warning(f"model catalog unavailable, serving as not-ready: {error}", status="fail")
```

`refresh_catalogs` 遍历 `chain.providers.names`，对每个调 `await chain.providers.get(name).refresh_catalog()`；`GithubCopilotProvider.refresh_catalog()`（`src/app/model_provider/github_copilot.py:119-138`）里 `headers = await self._client.request_headers(...)`（这一步才真正 `await copilot_tokens.get_token()`，触发 GitHub→Copilot token 换取），然后 `fetch_models(self._http, self._base_url, headers, ...)`——**`self._base_url` 此时早已在 `build_chain`/`build_copilot_provider` 阶段被冻结**，`refresh_catalog` 改不了它。

**关于“先有鸡还是先有蛋”的关键问题**：

答案是**没有真正的数据依赖环**，但有一个**同步/异步边界问题**。理由：

1. 探测 `account_type` 走的是 `auth_base_url`（`GitHubAccountClient` 只认 `auth_base_url_override or GITHUB_AUTH_BASE_URL`，见 A-1），**与 `api_base_url` 完全无关**。`auth_base_url` 是配置项本身（或常量），不依赖 `account_type` 推导，所以探测调用不需要先知道 `api_base_url`。
2. 探测需要的裸 GitHub token，来自 `token_source.get_token()`（`build_github_token_source` 已经在 `build_chain` 里组好），这一步也不依赖 `account_type` 或 `api_base_url`。
3. 依赖顺序完全线性：拿裸 GitHub token → （可选）探测 account_type（打 `auth_base_url`）→ 用 account_type 算出 `api_base_url` → 构造 `GhcApiClient`/`GithubCopilotProvider`（`base_url=` 参数）→ 后续 `refresh_catalog()` 才用得到 `api_base_url`。legacy `bootstrap.py` 正是这个顺序（A-2）。
4. **真正的障碍是工程性的**：`build_chain`/`build_copilot_provider` 现在是**同步函数**，而“拿裸 token”“打 HTTP 探测请求”都是 `async def`。要把探测接进 `build_chain`，`build_chain`（以及可能 `build_copilot_provider`）必须变成 `async def`，在 `for name, provider_config in config.model_providers.items():` 循环内部对每个 provider **在构造 `GhcClientConfig`/算 `base_url` 之前**先 `await token_source.get_token()` 再按需 `await GitHubAccountClient(...).get_copilot_usage(...)`。这不是"先有鸡先有蛋"式的死锁，而是一次可控的签名改动，影响面见下。

`build_chain` 现有调用点（全部需要跟着改，`await`）：

- `src/app/cli.py:148`（`serve_inherited`，已是 `async def`，加 `await` 即可）
- `src/app/cli.py:170`（`_serve_pipeline`，已是 `async def`，加 `await` 即可）
- `src/app/debug/models.py:232`（`collect_catalogs`，已是 `async def`，加 `await` 即可）
- 测试（均需要改成 `await build_chain(...)` 或把测试函数标 `async`）：
  - `tests/int/recorded/recorded_provider.py:103`
  - `tests/int/recorded/record_cassette.py:58`
  - `tests/int/test_pipeline_app.py:147,806,838,869`
  - `tests/unit/config/test_config_paths.py:112`
  - `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:73,233,280,313`
  - `tests/e2e/claude/_harness.py:95`
  - `tests/unit/debug/test_debug_models.py:530` 有一个**手写的假 `build_chain`**（`def build_chain(config: ProxyConfig, *, http_client: object) -> SimpleNamespace`），也要跟着改签名，否则 monkeypatch 替身和真实签名不一致会被 pyright/测试发现不一致（目前是同步桩子，替换真实同步函数；改造后要么保持桩子同步但调用方对其 `await`——会炸，因为同步函数返回值不是 awaitable——要么桩子也改成 `async def`）。

`auth_base_url` 与 `api_base_url` 是两个不同 host 的确认：`ModelProviderConfig` 里两者本就是分开的字段（`schema.py:86-91`），`GhcClientConfig.auth_base_url` 属性只读 `auth_base_url_override or GITHUB_AUTH_BASE_URL`（`ghc_client/config.py:34-36`），与 `api_base_url` 属性（读 `account_type` 或 `api_base_url_override`）完全独立（`ghc_client/config.py:30-32, 39-48`）。探测（`GitHubAccountClient`）只使用前者。

## A-4. `ModelProviderConfig` 加字段要同步改的地方

1. **`src/app/config/schema.py`**：
   - `ModelProviderConfig`（83-127 行）里加一个 `account_type: Literal["individual", "business", "enterprise", "self-hosted"] | None = None` 字段（镜像 legacy `app/config/settings.py:33` 的写法；类型可复用 `composition.py:48` / `ghc_client/config.py:4` 已有的 `AccountType` 别名，但那两处目前是模块内 `type AccountType = ...`，各自定义，没有共享的公共位置——引入时要么在 schema.py 里再定义一份 `type AccountType = Literal[...]`，要么挑一个现有定义提升成公共导出。三处字面量目前是各自重复写的："composition.py:48"、"ghc_client/config.py:4"、legacy "settings.py:33"，尚无单一权威源）。
   - `NOT_HOT_RELOADABLE`（`schema.py:37-52`）需要加一条 `"model_providers.*.account_type"`，紧挨着已有的 `"model_providers.*.api_base_url"` / `"model_providers.*.auth_base_url"`（37-41 行）——因为 `api_base_url` 在启动时被 `build_copilot_provider` 算死塞进 `AsyncOpenAI`/`AsyncAnthropic` 的 `base_url=`，`account_type` 只要没设 `api_base_url_override` 就直接决定 `api_base_url`，同样"改了也不会在运行中生效"，必须标记为重启项，否则热重载会谎报生效。
2. **`src/app/config/provider.py`**（`pin_restart_only`，1-60+ 行）：不需要改代码本身——`_expand` 是通用的 glob 展开逻辑，新增的 `NOT_HOT_RELOADABLE` 条目会被它自动认出来。只是提醒：加了字段却忘记加 `NOT_HOT_RELOADABLE` 条目，`pin_restart_only` 不会报错，只会悄悄允许热重载生效（这正是 `tests/unit/config/test_config_loading.py:130-149` 用来测 `api_base_url` 那条目的方式，`account_type` 应该照抄一条同构的测试）。
3. **`tests/unit/config/test_config_loading.py:130-149`**：建议照抄 `test_spec_config_path_is_under_xdg_data` 里对 `api_base_url` 的 restart-required 断言，加一条对 `account_type` 的等价用例（不是强制，但这是本项目一贯的"新增 NOT_HOT_RELOADABLE 条目配一条测试"的写法）。
4. **`docs/.human-controlled/config.example.yaml`**：用户会自己加（任务说明里已声明），代码侧不用碰，但 `ModelProviderConfig` 的 `extra="forbid"`（`Section.model_config`，`schema.py:56`）意味着**用户在 yaml 里加了 `account_type` key 而代码没同步加字段，会直接校验失败（额外字段被拒绝）**——这是本次改动的强约束，不能只做 A-3 的接线而漏掉 schema 字段。
5. **`src/app/server/composition.py`**：
   - `build_copilot_provider`（348-360 行）与 `build_chain`（407-410 行）两处构造 `GhcClientConfig` 时，都要从 `provider_config.account_type` 读值传入 `GhcClientConfig(account_type=..., ...)`；目前两处都没有传 `account_type`，恒为 dataclass 默认 `"individual"`（`ghc_client/config.py:23`）。
   - 若 `provider_config.account_type is None`，则要触发探测流程（见 A-3 的顺序结论），这一步必然让 `build_chain` 变成 `async def`。
6. **任何遍历 `ModelProviderConfig` 字段的代码**：搜索确认没有基于反射/`model_fields`遍历该模型全部字段做逐字段处理的代码（`model_dump()`/`model_copy()`调用点都是整体操作，不逐字段展开），所以新增字段不会破坏这类代码；只有 `NOT_HOT_RELOADABLE` 这种"手工列出关心的字段路径"的清单需要人工同步（如上）。

## A-5. 新链路的异步初始化钩子

有且只有一个：`src/app/server/pipeline_app.py:799-829` 的 `@asynccontextmanager async def _lifespan(app: FastAPI)`，在 `create_pipeline_app`（`pipeline_app.py:771-785`）里作为 FastAPI 的 `lifespan=_lifespan` 挂载。目前它做的事是 `await refresh_catalogs(chain)`（`composition.py:455-465`），失败降级为 `not-ready`（不致命）。

**但探测本身不适合直接挂在这个 `_lifespan` 里**，原因：`_lifespan` 拿到的 `chain: Chain` 是 `build_chain(...)` 已经构造完毕的产物——此时每个 provider 的 `GhcApiClient`/`AsyncOpenAI`/`AsyncAnthropic` 已经带着算死的 `base_url` 构造好了（`build_copilot_provider` 148-385 行），`_lifespan` 阶段再探测出新的 `account_type` 也没有地方能把新的 `base_url` 塞回已经建好的 `AsyncOpenAI`/`AsyncAnthropic` 实例（它们的 `base_url` 不是运行时可变的公开接口）。

所以探测必须**在 `build_chain` 内部、构造 `GhcApiClient` 之前**完成（也就是让 `build_chain`/`build_copilot_provider` 本身变成 `async def`，在算 `ghc_config.api_base_url` 之前先 `await` 探测），而不是依赖 `_lifespan` 这个已有钩子。`_lifespan` 仍然是"启动时可以做异步初始化"的钩子，但它出手的时机已经太晚——`refresh_catalogs` 只是刷新目录，不能重建 provider。这与 legacy `bootstrap.initialize_upstream_services`（本身就是一个大的 `async def`，探测、建 client、建 catalog 全在一次函数体内顺序完成）的结构是一致的：**探测必须和"构造 provider/client"在同一个 async 调用序列里，不能拆成两个先后独立的钩子**。

## B-1. `--ghc-api-base-url` 完整影响面（逐个列出）

### 代码

- **CLI 定义处**：`src/app/cli.py:233`
  ```python
  ghc_api_base_url: Annotated[str | None, typer.Option("--ghc-api-base-url")] = None,
  ```
  这是 `start` 命令（`cli.py:219-245` 起）的一个参数。
- **`_load_spec_config` 里的使用**（`cli.py:81-138`，参数声明在 89 行，使用在 126-137 行）：
  ```python
  if ghc_api_base_url is not None:
      # Applied after loading rather than as an override: which provider it belongs to is only
      # known once the config names a default.
      name = config.default_model_provider
      providers = dict(config.model_providers)
      if name in providers:
          providers[name] = providers[name].model_copy(update={"base_url": ghc_api_base_url})
          config = config.model_copy(update={"model_providers": providers})
      else:
          inactive.append(
              ("--ghc-api-base-url", f"no provider named {name!r} to apply it to")
          )
  ```
  **重要发现（已用 Python 现场验证）：这段代码本身是死代码/已损坏**。`ModelProviderConfig` 的字段名是 `api_base_url`，不是 `base_url`；`model_copy(update={"base_url": ...})` 在 pydantic v2 里**不做校验**，会把 `base_url` 塞成一个野字段挂在实例上（`hasattr(p2, 'base_url') == True`），但 `p2.api_base_url` 保持原值不变，`p2.model_dump()` 里根本不出现 `base_url`。也就是说，**`--ghc-api-base-url` 在新链路（无论 `--fd` 还是 standalone）上现在完全不起作用**——`composition.py` 里读的是 `provider_config.api_base_url`，永远读到没被这段代码改动过的原值。这不是本次改动引入的新事实，是现状；删除该选项即删除一段已经失效的代码，不会造成任何行为回归。
- **两条 serve 分支的传参**：
  - `--fd` 分支：`cli.py:289-303`（`_load_spec_config(..., ghc_api_base_url=ghc_api_base_url, ...)`），随后 `run(partial(serve_inherited, proxy_config, fd, ...))`（`cli.py:303`）——`serve_inherited` 本身不直接吃这个参数，只吃已经"应用"过（但其实没生效）的 `proxy_config`。
  - standalone 分支：`cli.py:306-319`（同样调 `_load_spec_config(..., ghc_api_base_url=ghc_api_base_url, ...)`），随后 `inactive` 列表被打印警告（`cli.py:320-323`），再 `run(partial(_serve_pipeline, proxy_config, options, ...))`。
  - 另外 `start()` 函数体里还有一段**完全独立、写向另一套（legacy）配置模型的分支**：`cli.py:264-265`
    ```python
    if ghc_api_base_url is not None:
        upstream_overrides["ghc_api_base_url"] = ghc_api_base_url
    ```
    这段把值塞进 `upstream_overrides`（后面 `cli_overrides["upstream"] = upstream_overrides"`，`cli.py:280-281`），但 `cli_overrides` **从未被使用**——往下看 `start()` 函数体，`cli_overrides` 构造完之后没有任何代码读取它、传给 `load_proxy_config` 或别的函数（`_load_spec_config` 走的是它自己独立算的 `overrides` 局部变量，`cli.py:103-113`，与 `cli_overrides` 无关）。**`cli_overrides`/`upstream_overrides`/`auth_overrides` 这一整套变量看起来是遗留的死代码**（附带说明：这不只是 `ghc_api_base_url` 一个字段的问题，`account_type`、`github_token`、`proxy` 等也都塞进了同一个从未被读取的 `cli_overrides`——但这已超出本次勘察范围，只做记录，不建议本次顺手清，除非用户认可这个观察后决定一并处理）。
- **测试引用**：
  - `tests/unit/test_cli.py:73`：`test_start_subcommand_exposes_bootstrap_options` 只是断言 `--ghc-api-base-url` 出现在 `start --help` 的输出里（字符串存在性检查），删除选项后这一断言要同步删掉这一行。
  - 未发现任何测试真正驱动 `--ghc-api-base-url` 走一遍 `_load_spec_config`/`build_chain` 验证其效果（与"这段代码已损坏而无人发现"的事实吻合）。
  - `tests/unit/upstream/test_upstream_client.py:14`、`tests/unit/upstream/test_upstream_targets.py:52` 里出现的 `ghc_api_base_url` 是 **legacy `app.config.settings.AppSettings` 的 `upstream.ghc_api_base_url` 字段**（`settings.py:17`），与本次要删的 CLI 选项、以及 `ModelProviderConfig` 无关，**不在删除范围内，不要动**。

### 非代码

- `contrib/systemd/`（`ghc-api-proxy.service`、`ghc-api-proxy.slice`、`ghc-api-proxy.socket`、`install-user.py`、`rolling/`）：全文件搜索 `ghc.api.base.url`（大小写不敏感、`-`/`_`任意）**零命中**，无需改动。
- `Dockerfile`、`docker-compose.yml`：同样零命中，无需改动。
- `README.md`、`docs/`：零命中。
- 结论：**`--ghc-api-base-url` 的全部引用只存在于 `src/app/cli.py`（4 处）和 `tests/unit/test_cli.py`（1 处）**，其余全仓库（含 `.dev/`）没有第二处。

## B-2. 删除后对 `_load_spec_config` 与 `inactive` 机制、`_NO_HOME_IN_SPEC` 的影响

- `_load_spec_config` 签名（`cli.py:81-95`）需要去掉 `ghc_api_base_url: str | None,` 这一参数；函数体去掉 126-137 行整段 `if ghc_api_base_url is not None: ...` 分支。因为这段分支本身就是唯一会把 `("--ghc-api-base-url", ...)` 追加进 `inactive` 列表的地方（仅在"配置里没有 `default_model_provider` 对应的 provider"这个边界情况下才会追加，`cli.py:134-137`）——删掉整个选项后，这一条 inactive 消息也随之消失，不需要额外处理。
- `_NO_HOME_IN_SPEC`（`cli.py:73-78`）**不需要改**：`--ghc-api-base-url` 从来没有出现在这个字典里（它是走 126-137 行那条独立的"应用后再报 inactive"逻辑，不是走 115-124 行那条基于 `_NO_HOME_IN_SPEC` 查表的"直接判定 inactive"逻辑）。`_NO_HOME_IN_SPEC` 目前的四个键（`--manual`、`--rate-limit/--no-rate-limit`、`--github-token`、`--account-type`）都还在用，不受本次删除影响。
  - 但要注意：**`--account-type` 目前也在 `_NO_HOME_IN_SPEC` 里，注释是"config.example.yaml has no `auth` section"**（`cli.py:77`）。一旦 A 任务把 `account_type` 加进 `ModelProviderConfig`（per-provider），`--account-type` 这个 CLI 选项本身要不要恢复生效、`_NO_HOME_IN_SPEC` 里这一条要不要摘掉，是 A 任务连带的一个决策点——**当前只是记录这个关联，不擅自下结论**，因为任务描述里只要求"加字段并接线"探测逻辑，没有明确要求同时把 `--account-type` CLI 选项也接回新链路；建议向用户确认这一点是否属于本次范围（`--account-type` 目前也和 `--ghc-api-base-url` 一样打在 `cli.py:262-263` 那个死掉的 `auth_overrides`/`cli_overrides` 路径上，同样从未真正生效）。
- `start()` 函数体里 `ghc_api_base_url` 的另外两处（`cli.py:233` 参数定义、`cli.py:264-265` 写入死掉的 `upstream_overrides`、`cli.py:296`/`cli.py:313` 传给 `_load_spec_config`）要一并删除，否则会留下未使用的局部变量（pyright/ruff 会报）。

## 小结：改动清单（供实现阶段直接对照）

**A（account_type 接线）：**
1. `src/app/config/schema.py`：`ModelProviderConfig` 加 `account_type` 字段；`NOT_HOT_RELOADABLE` 加 `"model_providers.*.account_type"`。
2. `src/app/server/composition.py`：`build_chain` 改 `async def`；在 348-360 / 407-410 两处构造 `GhcClientConfig` 之前，对 `provider_config.account_type is None` 的 provider，`await` 拿裸 GitHub token → `await GitHubAccountClient(http_client, auth_base_url=ghc_config.auth_base_url).get_copilot_usage(token)` → `infer_account_type` → 传入 `GhcClientConfig(account_type=..., ...)`；`build_copilot_provider` 视需要一并改 `async def`（它内部现在不发网络请求，但如果探测逻辑放在这里而不是 `build_chain` 循环体，则也要改)。
3. 所有 `build_chain(...)` 调用点补 `await`（列表见 A-3 末尾），含 `tests/unit/debug/test_debug_models.py:530` 的假实现。
4. 视情况给 `tests/unit/config/test_config_loading.py` 加一条 `account_type` 的 restart-required 用例。

**B（删除 `--ghc-api-base-url`）：**
1. `src/app/cli.py`：删 233 行参数定义、264-265 行死代码写入、81-138 行 `_load_spec_config` 里的参数与 126-137 行整段分支、289-319 行两处传参。
2. `tests/unit/test_cli.py:73`：删掉这一行断言。
3. 无需改 `contrib/systemd/`、`Dockerfile`、`docker-compose.yml`、`README.md`、`docs/`。
4. 记录但不擅自处理：`start()` 里 `cli_overrides`/`auth_overrides`/`upstream_overrides` 这一整套变量疑似整体死代码（构造了但从未被读取），以及 `--account-type` 选项与 `_NO_HOME_IN_SPEC` 的联动是否要在本次一并调整——两者都建议向用户确认后再动，不在本次勘察授权范围内擅自扩大。
