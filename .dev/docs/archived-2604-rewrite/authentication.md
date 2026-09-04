# Copilot 认证

> 本文档是**目标设计**（design spec），标注约定见 [DESIGN.md](DESIGN.md#文档约定稳定性与借鉴状态标注)。未特别标注者默认 `[上游稳定][采纳]`。

## 概述

通过 GitHub Copilot 扩展获取 OAuth token，用于访问 Copilot API。认证由 `auth/` 模块管理，核心是一条**按优先级排序的 Token Provider 链**（`[上游稳定][采纳]`），支持多种 GitHub token 获取方式、Copilot token 自动续期、以及并发安全的刷新。

**Python 优化**：JS 版本的 token 状态存储在全局可变 `state.ts` 中（呼应 [DESIGN.md](DESIGN.md) P8）。Python 版本用 `GitHubTokenManager` + `CopilotTokenManager` 两个类封装各自的生命周期，通过 FastAPI 依赖注入传递单例引用，避免全局可变状态；Provider 链本身用 Python `abc.ABC`（等价于 TS 的抽象基类）实现，接口形状与上游保持一致，便于对照。

## 认证流程总览

```
启动时
    │
    ▼
[1. 通过 Token Provider 链获取 GitHub Token]
    按 priority 升序尝试：CLI(1) → Env(2) → File(3) → DeviceAuth(4, fallback)
    第一个 is_available() 为真且 get_token() 成功返回非 None 的 provider 胜出
    │
    ▼
[2. 交换 Copilot Token]
    POST https://api.github.com/copilot_internal/v2/token
    Headers:
        Authorization: token {github_token}
        Accept: application/json
    Response:
        {
            "token": "tid=...",
            "expires_at": 1234567890,
            "refresh_in": 1500,
            ...（其余字段保留在 raw 中，见 CopilotTokenInfo）
        }
    │
    ▼
[3. 探测账户类型（account-type 推断）]
    GET /copilot_internal/user → 提取 copilot_plan / access_type_sku → 推断账户类型
    │（显式 --account-type 或 --ghc-api-base-url 时跳过，见下文）
    ▼
[4. 使用 Copilot Token]
    所有 Copilot API 请求携带完整的 copilotHeaders()（见「请求头伪装」一节）
```

## 账户类型

不同账户类型使用不同的 Copilot API 基础 URL：

| 账户类型 | API Base URL | 说明 |
|----------|-------------|------|
| `individual` | `api.githubcopilot.com` | 个人订阅 |
| `business` | `api.business.githubcopilot.com` | 企业团队版 |
| `enterprise` | `api.enterprise.githubcopilot.com` | 企业高级版 |

### account-type 无默认——从探测推断，推断失败才回退 individual

**关键设计**：`account_type` **没有静态默认值**意义上的"个人版优先假设"——本项目在启动阶段主动探测账户实际类型，只有探测失败或无法解析时才**回退**到 `individual`，这与"默认就是 individual、除非用户手动改"的朴素设计不同：

```python
VALID_ACCOUNT_TYPES = ("individual", "business", "enterprise")

def infer_account_type_from_usage(usage: CopilotUsageResponse) -> str | None:
    """从 /copilot_internal/user 的 copilot_plan / access_type_sku 字段推断账户类型。

    保守启发式：子串匹配而非精确枚举，因为上游 SKU 命名会演进（如未来出现
    `enterprise_seat_v2` 这类变体），子串匹配让新 SKU 无需代码更新即可正确路由。
    找不到任何可用信号时返回 None（调用方决定如何兜底），而非强行猜测。
    """
    haystack = f"{usage.copilot_plan or ''} {usage.access_type_sku or ''}".lower()
    if not haystack.strip():
        return None
    if "enterprise" in haystack:
        return "enterprise"
    if "business" in haystack:
        return "business"
    if "individual" in haystack or "free" in haystack or "pro" in haystack:
        return "individual"
    return None
```

推断时机与优先级：

1. 应用启动阶段，在 GitHub token 就绪、Copilot token 首次交换成功后，探测性调用一次 `GET /copilot_internal/user`（非致命——探测失败不阻塞启动，回退到当前 `account_type` 配置值/默认 `individual`）。
2. **仅当用户未显式传入 `--account-type` 或 `auth.account_type` 配置**时才采用推断结果；显式配置永远优先于推断。
3. **`--ghc-api-base-url` 显式覆盖时，account-type 探测结果被完全忽略**——base URL 已经是终点，account-type 只是"派生 base URL 的中间手段"，两者语义冲突时以更具体、更明确的 base URL 覆盖为准。

```python
def resolve_ghc_base_url(settings: AuthConfig, upstream: UpstreamConfig) -> str:
    """账户类型 → base URL 的派生规则，`ghc_api_base_url` 显式设置时优先。"""
    if upstream.ghc_api_base_url:
        return upstream.ghc_api_base_url.rstrip("/")
    if settings.account_type == "individual":
        return "https://api.githubcopilot.com"
    return f"https://api.{settings.account_type}.githubcopilot.com"
```

配置方式：
- CLI: `--account-type business`
- Config: `auth.account_type: business`
- 环境变量: `GHC_AUTH__ACCOUNT_TYPE=business`

---

## Token Provider 系统 `[上游稳定][采纳]`

### 设计动机

GitHub token 的来源多样（CLI 参数、环境变量、本地文件、交互式设备授权），且这些来源有明确的**优先级**与**可刷新性**差异。上游用一组共享同一抽象基类的 Provider 类实现"责任链"模式：按优先级顺序依次询问每个 Provider 是否可用，第一个给出有效 token 的 Provider 胜出。本项目在 Python 中用 `abc.ABC` 复刻同一形状。

### 抽象基类

```python
# auth/providers.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

TokenSource = Literal["cli", "env", "file", "device-auth"]

@dataclass
class TokenInfo:
    """GitHub token 及其元数据。"""
    token: str
    source: TokenSource
    expires_at: float | None = None    # Unix 秒；大多数来源不提供过期信息（None）
    refreshable: bool = False

@dataclass
class TokenValidationResult:
    valid: bool
    error: str | None = None
    username: str | None = None


class GitHubTokenProvider(ABC):
    """GitHub token 来源的抽象基类。每个具体 Provider 代表一种获取方式。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """人类可读名称，用于日志。"""

    @property
    @abstractmethod
    def priority(self) -> int:
        """优先级（数值越小越优先尝试）。"""

    @property
    @abstractmethod
    def refreshable(self) -> bool:
        """该来源的 token 是否支持刷新。"""

    @abstractmethod
    async def is_available(self) -> bool:
        """检查该 Provider 是否具备必要的前提条件（如 CLI 参数是否传入）。"""

    @abstractmethod
    async def get_token(self) -> TokenInfo | None:
        """获取 token；不可用或获取失败时返回 None（不抛异常——责任链需要继续尝试下一个）。"""

    async def refresh(self) -> TokenInfo | None:
        """刷新 token（若支持）。默认实现返回 None（不支持刷新）。"""
        return None

    async def validate(self, token: str, *, github_client: "GitHubClient") -> TokenValidationResult:
        """通过调用 GitHub API 校验 token 有效性并取回用户名。"""
        try:
            user = await github_client.get_user(token)
            return TokenValidationResult(valid=True, username=user.login)
        except Exception as exc:
            return TokenValidationResult(valid=False, error=str(exc))
```

Python 用 `Protocol` 也能表达同样的静态接口约束，但这里选用 `ABC`——Provider 链有共享的默认行为（`refresh()`/`validate()` 的默认实现），`ABC` 的模板方法风格比纯 `Protocol`（无法携带默认实现，只能靠 mixin）更贴合这个场景；`Protocol` 更适合"只约束形状、不共享实现"的场景（如 [model-resolution.md](model-resolution.md) 里的 `UpstreamTarget`）。

### 四个具体 Provider

#### 1. CLITokenProvider（优先级 1，非可刷新）

```python
class CLITokenProvider(GitHubTokenProvider):
    """来自 --github-token CLI 参数——用户显式提供的 token，最高优先级。"""

    name = "CLI"
    priority = 1
    refreshable = False

    def __init__(self, token: str | None = None) -> None:
        self._token = token.strip() if token else None

    async def is_available(self) -> bool:
        return bool(self._token)

    async def get_token(self) -> TokenInfo | None:
        if not self._token:
            return None
        return TokenInfo(token=self._token, source="cli", refreshable=False)
```

#### 2. EnvTokenProvider（优先级 2，非可刷新）

按顺序检查三个环境变量，**第一个命中者胜出**：

```python
ENV_VARS = (
    "COPILOT_API_GITHUB_TOKEN",   # 本项目专属变量，优先级最高
    "GH_TOKEN",                    # GitHub CLI 兼容
    "GITHUB_TOKEN",                 # 通用约定
)

class EnvTokenProvider(GitHubTokenProvider):
    name = "Environment"
    priority = 2
    refreshable = False

    def __init__(self) -> None:
        self._found_env_var: str | None = None

    def _find_env_var(self) -> str | None:
        for name in ENV_VARS:
            if value := os.environ.get(name, "").strip():
                return name
        return None

    async def is_available(self) -> bool:
        return self._find_env_var() is not None

    async def get_token(self) -> TokenInfo | None:
        env_var = self._find_env_var()
        if env_var is None:
            return None
        self._found_env_var = env_var
        return TokenInfo(token=os.environ[env_var].strip(), source="env", refreshable=False)
```

#### 3. FileTokenProvider（优先级 3，非可刷新）

```python
class FileTokenProvider(GitHubTokenProvider):
    """来自持久化的文件存储；也被 DeviceAuthProvider 用来落盘新获取的 token。"""

    name = "File"
    priority = 3
    refreshable = False

    def __init__(self, token_path: Path | None = None) -> None:
        self._path = token_path or get_token_path()   # 见「配置」一节的路径解析

    async def is_available(self) -> bool:
        try:
            token = await self._read()
            return bool(token.strip())
        except OSError:
            return False

    async def get_token(self) -> TokenInfo | None:
        try:
            token = (await self._read()).strip()
        except OSError:
            return None
        if not token:
            return None
        return TokenInfo(token=token, source="file", refreshable=False)

    async def save_token(self, token: str) -> None:
        """由 DeviceAuthProvider 调用，把新获取的 token 落盘供下次启动直接读取。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._path.write_text, token.strip())

    async def clear_token(self) -> None:
        try:
            await asyncio.to_thread(self._path.write_text, "")
        except OSError:
            pass  # 清除失败不视为致命错误——下次启动仍会走 device flow

    async def _read(self) -> str:
        return await asyncio.to_thread(self._path.read_text, encoding="utf-8")
```

默认路径：`$XDG_DATA_HOME/ghc-api-proxy/github_token`，`XDG_DATA_HOME` 未设置时默认 `~/.local/share/ghc-api-proxy/github_token`（见「配置」一节的 `get_token_path()`）。文件 I/O 经 `asyncio.to_thread` 下沉到线程池，不阻塞事件循环（呼应 [DESIGN.md](DESIGN.md) 的异步优先取向；这里是启动期一次性 I/O，非热路径，但仍保持一致的异步纪律）。

#### 4. DeviceAuthProvider（优先级 4，fallback，可刷新）

```python
class DeviceAuthProvider(GitHubTokenProvider):
    """GitHub OAuth Device Flow——交互式回退，唯一支持"刷新"的来源（刷新即重新走一次
    完整流程，因为 device flow 场景本来就没有 refresh_token 概念）。
    """

    name = "DeviceAuth"
    priority = 4
    refreshable = True

    def __init__(self, file_provider: FileTokenProvider, github_client: "GitHubClient") -> None:
        self._file_provider = file_provider
        self._github_client = github_client

    async def is_available(self) -> bool:
        return True   # 永远可用——作为最后手段，会提示用户交互式登录

    async def get_token(self) -> TokenInfo | None:
        try:
            device = await self._github_client.get_device_code()
            logger.info(f'请访问 {device.verification_uri} 并输入代码 "{device.user_code}"')
            token = await self._github_client.poll_access_token(device)
            await self._file_provider.save_token(token)   # 持久化，供下次启动直接读文件
            return TokenInfo(token=token, source="device-auth", refreshable=True)
        except Exception as exc:
            logger.error(f"Device 授权失败: {exc}")
            return None

    async def refresh(self) -> TokenInfo | None:
        return await self.get_token()   # 重新走一次完整流程
```

### GitHubTokenManager：责任链编排

```python
class GitHubTokenManager:
    """按 priority 升序尝试各 Provider，第一个成功者的 token 被缓存复用。"""

    def __init__(self, providers: list[GitHubTokenProvider]) -> None:
        self._providers = sorted(providers, key=lambda p: p.priority)
        self._current: TokenInfo | None = None

    async def get_token(self) -> TokenInfo:
        if self._current is not None:
            return self._current
        for provider in self._providers:
            if not await provider.is_available():
                continue
            token_info = await provider.get_token()
            if token_info is None:
                continue
            self._current = token_info
            logger.debug(f"使用来自 {provider.name} Provider 的 token")
            return token_info
        raise RuntimeError("没有任何 Provider 能提供有效的 GitHub token")

    async def refresh(self) -> TokenInfo | None:
        """强制刷新。非 refreshable 来源（CLI/env/file）无法刷新——
        此时触发 on_token_expired 回调（通常提示用户重新认证），而非静默失败。
        """
        if self._current is None:
            return await self.get_token()
        if not self._current.refreshable:
            logger.warning(f"来自 {self._current.source} 的 token 不支持刷新")
            return None
        device_provider = next(
            (p for p in self._providers if isinstance(p, DeviceAuthProvider)), None,
        )
        if device_provider is None:
            return None
        new_token = await device_provider.refresh()
        if new_token is not None:
            self._current = new_token
        return new_token
```

**装配顺序**（`auth/manager.py` 组装 Provider 链，等价于上游 `GitHubTokenManager` 构造函数里的固定顺序）：

```python
providers = [
    CLITokenProvider(cli_token),
    EnvTokenProvider(),
    FileTokenProvider(),
    DeviceAuthProvider(file_provider=FileTokenProvider(), github_client=github_client),
]
manager = GitHubTokenManager(providers)
```

注意：上游明确**不包含** GitHub CLI（`gh` 命令）自身的 token 作为来源——`gh` 的 OAuth App 与 Copilot 使用的 OAuth App 不同，`gh auth token` 拿到的 token 无法访问 Copilot 内部 API，因此本项目同样不实现这一 Provider，避免用户误以为"我已经 `gh auth login` 了应该能用"。

---

## Copilot Token 管理

### 数据结构

```python
@dataclass
class CopilotTokenInfo:
    """Copilot token 及过期/刷新元数据。

    `raw` 保留完整原始响应（含 endpoints、sku 等所有字段），呼应
    richest-data-flow 原则——即使当前只用到 token/expires_at/refresh_in，
    未来新增消费者（如读取 endpoints.proxy）也无需改动交换逻辑本身。
    """
    token: str
    expires_at: float          # Unix 秒
    refresh_in: int             # 服务端建议的下次刷新间隔（秒）
    raw: dict
```

### CopilotTokenManager

```python
class CopilotTokenManager:
    """管理 Copilot token 的完整生命周期：交换、自动续期、并发安全刷新、per-request 校验。"""

    def __init__(self, github_manager: GitHubTokenManager, *, min_refresh_interval: float = 60.0) -> None:
        self._github_manager = github_manager
        self._current: CopilotTokenInfo | None = None
        self._lock = asyncio.Lock()
        self._refresh_task: asyncio.Task | None = None
        self._refresh_needed = False   # 上次刷新失败时置位，供 ensure_valid_token 感知

    async def get_token(self) -> str:
        if self._is_valid():
            return self._current.token
        return (await self.refresh()).token

    async def refresh(self) -> CopilotTokenInfo:
        """所有刷新路径（定时调度 + 401 触发）的唯一入口。

        asyncio.Lock + 内部 double-check：并发请求同时发现 token 过期时，
        只有第一个真正执行网络交换，其余在锁释放后直接读到已刷新的结果，
        不会触发多次冗余的 token 交换请求。
        """
        async with self._lock:
            if self._is_valid() and not self._refresh_needed:
                return self._current   # double-check：可能已被同一批等待者中的先行者刷新
            info = await self._exchange_with_retry()
            self._current = info
            self._refresh_needed = False
            self._schedule_next_refresh(info.refresh_in)
            return info

    async def ensure_valid_token(self) -> None:
        """per-request 校验入口（配置热重载中间件 / 请求前置钩子调用）。
        token 有效且上次刷新未失败时是纯内存判断，零 I/O。
        """
        if self._is_valid() and not self._refresh_needed:
            return
        await self.refresh()

    def _is_valid(self, margin_seconds: float = 60.0) -> bool:
        if self._current is None:
            return False
        return time.time() < self._current.expires_at - margin_seconds

    async def _exchange_with_retry(self, max_retries: int = 3) -> CopilotTokenInfo:
        """交换失败时指数退避重试；401 时先尝试刷新 GitHub token 再重试一次。"""
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await self._exchange()
            except HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code == 401:
                    github_token = await self._github_manager.refresh()
                    if github_token is not None:
                        continue   # 立即用新 GitHub token 重试，不计入退避延迟
                await asyncio.sleep(min(2 ** attempt, 30))
        raise last_exc

    async def _exchange(self) -> CopilotTokenInfo:
        github_token = await self._github_manager.get_token()
        response = await self._http_client.get(
            f"{GITHUB_API_BASE_URL}/copilot_internal/v2/token",
            headers=github_headers(github_token.token),
        )
        response.raise_for_status()
        data = response.json()
        return CopilotTokenInfo(token=data["token"], expires_at=data["expires_at"], refresh_in=data["refresh_in"], raw=data)

    def _schedule_next_refresh(self, refresh_in_seconds: int) -> None:
        """在服务端建议的 refresh_in 之前（留 60 秒余量）调度下一次自动刷新，
        作为独立于 ensure_valid_token 的第二道防线（后台常驻，避免长时间无请求时 token 过期后
        第一个请求都要付出刷新延迟）。
        """
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        delay = max(refresh_in_seconds - 60, self._min_refresh_interval)
        self._refresh_task = asyncio.create_task(self._auto_refresh_after(delay))

    async def _auto_refresh_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            await self.refresh()
        except Exception as exc:
            # 后台自动刷新失败不应该让进程崩溃——下次 ensure_valid_token 或下次定时任务会再次尝试
            logger.warning(f"后台自动刷新 Copilot token 失败，将在下次请求时按需重试: {exc}")
            self._refresh_needed = True
```

### 并发安全

**asyncio.Lock + double-check**：多个请求协程同时发现 token 过期时，只有第一个进入 `refresh()` 临界区的协程真正执行网络交换；其余协程在等待锁的过程中，第一个协程完成后已经把 `self._current` 更新为新 token，锁释放后它们进入临界区会立即在 `_is_valid()` 判断中发现 token 已经有效，直接返回，不会重复触发交换请求。这一模式直接对应上游 TS 版本的 `refreshInFlight` 共享 Promise 机制，Python 里用 `asyncio.Lock` 表达同样的语义更符合习惯用法（无需手动管理一个"进行中 Promise"的引用）。

### Token 刷新策略（管道集成）

在请求管道中，`TokenRefreshStrategy`（见 [request-pipeline.md](request-pipeline.md) 的策略列表）处理上游返回的 401/403：

```
收到 401/403
    │
    ▼
TokenRefreshStrategy.can_handle(error) → True（error.status_code in (401, 403)）
    │
    ▼
TokenRefreshStrategy.handle()
    ├─ await copilot_token_manager.refresh()
    ├─ 用新 token 更新本次 attempt 的 Authorization 头
    └─ 返回 RetryAction(should_retry=True)
```

### per-request 校验

除了后台定时刷新与 401 触发刷新外，还有第三条防线：**配置热重载中间件**（见 [config-system.md](config-system.md)）在每个请求进入 pipeline 前调用一次 `ensure_valid_token()`——这是纯内存判断（`_is_valid()` 检查），只有在真正需要刷新时才会产生 I/O，因此可以安全地放在每个请求的前置路径上而不引入额外延迟。

### Copilot Token 结构

Copilot token 是一个分号分隔的键值对字符串（形似但不是标准 JWT，不需要也不做签名校验——它只是一个 opaque bearer token，本项目只解析其中人类可读的元数据用于日志/调试）：

```
tid=xxxxxxxx;exp=1234567890;sku=copilot_for_individual;...
```

关键字段：
- `tid` — Token ID
- `exp` — 过期时间（Unix timestamp，与顶层 `expires_at` 语义一致，作为交叉校验）
- `sku` — 订阅类型（`copilot_for_individual`、`copilot_for_business`、`copilot_for_enterprise`）

这些字段仅用于日志与 `/api/tokens` 管理端点展示，不参与鉴权判断本身（鉴权完全由上游 Copilot API 基于 Bearer token 本身处理，本项目不做本地签名校验）。

---

## 请求头伪装 + 动态化 `[上游稳定][采纳]`

Copilot 上游要求所有请求伪装成 VSCode Copilot Chat 扩展发出的请求，`auth/copilot.py`（对应上游 `copilotHeaders()`）统一构建这组头：

```python
@dataclass
class CopilotHeaderOptions:
    vision: bool = False                          # 请求含视觉内容时设为 True
    model_request_headers: dict[str, str] | None = None   # 见下文「模型请求头转发」
    intent: str | None = None                      # 见下文「动态 intent」

def copilot_headers(
    copilot_token: str,
    settings: HeadersConfig,
    *,
    interaction_id: str,
    opts: CopilotHeaderOptions | None = None,
) -> dict[str, str]:
    opts = opts or CopilotHeaderOptions()
    interaction_type = opts.intent or "conversation-panel"
    request_id = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {copilot_token}",
        "content-type": "application/json",
        "copilot-integration-id": "vscode-chat",
        "editor-version": f"vscode/{settings.vscode_version}",       # 动态版本，见下文
        "editor-plugin-version": f"copilot-chat/{settings.copilot_version}",
        "user-agent": f"GitHubCopilotChat/{settings.copilot_version}",
        "openai-intent": interaction_type,
        "x-github-api-version": settings.api_version,
        "x-request-id": request_id,
        "X-Interaction-Id": interaction_id,         # 会话级常量（进程生命周期内不变）
        "X-Interaction-Type": interaction_type,
        "X-Agent-Task-Id": request_id,               # = 本次请求的 request_id
        "x-vscode-user-agent-library-version": "electron-fetch",
    }

    if opts.vision:
        headers["copilot-vision-request"] = "true"

    # 模型请求头转发：最低优先级——不覆盖任何已设置的核心头
    if opts.model_request_headers:
        core_keys_lower = {k.lower() for k in headers}
        for key, value in opts.model_request_headers.items():
            if key.lower() not in core_keys_lower:
                headers[key] = value

    return headers
```

### 动态 editor-version（VSCode 版本探测）

`editor-version` 头需要一个"看起来合理"的真实 VSCode 版本号，而非硬编码一个会逐渐过期的常量。启动阶段（[project-structure.md](project-structure.md) lifespan 的 Phase 4 外部依赖阶段）异步拉取一次 GitHub 最新 release 并缓存：

```python
VSCODE_VERSION_FALLBACK = "1.104.3"     # 网络不可用时的兜底常量
VSCODE_RELEASE_URL = "https://api.github.com/repos/microsoft/vscode/releases/latest"

async def fetch_and_cache_vscode_version(http_client: httpx.AsyncClient) -> str:
    """拉取最新 VSCode 版本号并缓存到 settings 快照；失败时静默回退到 fallback 常量，
    不阻塞启动（这是"锦上添花"的伪装真实度提升，不是功能性依赖）。
    """
    try:
        response = await http_client.get(VSCODE_RELEASE_URL, timeout=10.0)
        response.raise_for_status()
        tag = response.json()["tag_name"]           # 如 "1.104.3"
        return tag
    except Exception as exc:
        logger.debug(f"VSCode 版本探测失败，使用 fallback: {exc}")
        return VSCODE_VERSION_FALLBACK
```

### 动态 intent（opts.intent → openai-intent + X-Interaction-Type）

`intent` 参数控制 `openai-intent` 与 `X-Interaction-Type` 两个头的取值，**默认 `conversation-panel`**（模拟用户在 VSCode 聊天面板里的交互），需要区分 agent 调用（如 Claude Code 这类自主执行多轮工具调用的客户端）时传入 `conversation-agent`：

```python
def resolve_intent(request_context: RequestContext) -> str:
    """按调用来源决定 intent 取值。Claude Code / 其他 agent 客户端通过约定的请求头
    （如 x-claude-code-session-id 存在）识别为 agent 调用。"""
    if request_context.is_agent_call:
        return "conversation-agent"
    return "conversation-panel"
```

### 模型请求头转发（model request headers forwarding）

Copilot `/models` 目录中每个模型条目可能携带 `request_headers`（见 [data-models.md](data-models.md) 的 `ModelInfo.request_headers`）——这是 CAPI（Copilot API 后端）声明的、该模型特有的必需请求头（例如某些模型要求携带额外的路由提示头）。这些头以**最低优先级**合并进最终请求头：核心头（`Authorization`、`editor-version` 等）永远不会被模型特定头覆盖，只有模型头声明了核心头集合之外的新 key 才会被采纳。

### 核心头一览

| 头 | 含义 |
|---|---|
| `X-Interaction-Id` | 会话级常量（进程启动时生成一次的 UUID），用于关联同一服务器会话内的全部请求 |
| `X-Agent-Task-Id` | 等于本次请求的 `request_id`（每请求独立 UUID），与 `x-request-id` 语义重复但是 Copilot 侧的独立追踪维度 |
| `X-Initiator` | `agent` / `user`——标注该请求是由自主 agent 循环发起还是用户直接触发，供 Copilot 侧计费/审计区分 |
| `copilot-vision-request` | 请求含图片等视觉内容时设为 `"true"` |

---

## GitHub Token 获取详情：Device Flow

`auth/device_flow.py`（对应 `DeviceAuthProvider` 内部调用的 `github_client`）实现 GitHub OAuth 设备授权流程：

```
[1. 请求 Device Code]
    POST https://github.com/login/device/code
    Body: client_id=Iv1.b507a08c87ecfe98&scope=copilot
    Response:
        {
            "device_code": "...",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5
        }

[2. 提示用户]
    终端显示:
    "请访问 https://github.com/login/device"
    "输入代码: ABCD-1234"

[3. 轮询等待授权]
    POST https://github.com/login/oauth/access_token
    Body: client_id=...&device_code=...&grant_type=urn:ietf:params:oauth:grant-type:device_code
    轮询间隔: response.interval 秒（asyncio.sleep，不阻塞事件循环）

    可能的响应:
    ├─ authorization_pending → 继续轮询
    ├─ slow_down → 轮询间隔 +5 秒
    ├─ expired_token → 认证超时，提示重试（抛出异常，DeviceAuthProvider.get_token() 捕获并返回 None）
    ├─ access_denied → 用户拒绝（同上）
    └─ 成功 → 返回 access_token

[4. 保存 Token]
    经 FileTokenProvider.save_token() 写入 $XDG_DATA_HOME/ghc-api-proxy/github_token
    下次启动时 FileTokenProvider（优先级 3）会先于 DeviceAuthProvider（优先级 4）命中
```

```python
async def poll_access_token(device: DeviceCodeResponse, http_client: httpx.AsyncClient) -> str:
    interval = device.interval
    deadline = time.time() + device.expires_in
    while time.time() < deadline:
        await asyncio.sleep(interval)
        response = await http_client.post(
            f"{GITHUB_BASE_URL}/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "device_code": device.device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
        )
        body = response.json()
        if "access_token" in body:
            return body["access_token"]
        error = body.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise DeviceFlowError(f"设备授权失败: {error}")
    raise DeviceFlowError("设备授权超时（用户未在有效期内完成授权）")
```

---

## 配置

```yaml
auth:
  github_token: ""                 # 留空则走 Token Provider 链（env → file → device flow）
  account_type: individual         # 无静态默认意义——探测失败才回退到此值；显式设置时跳过探测
  # token_file: ""                 # 覆盖默认 token 文件路径（默认 $XDG_DATA_HOME/ghc-api-proxy/github_token）
  show_github_token: false         # 调试用：日志中显示 GitHub token 明文

headers:
  vscode_version: "1.99.0"         # 兜底值；启动阶段动态探测覆盖（见「动态 editor-version」）
  copilot_version: "0.25.2025020601"
  api_version: "2025-05-01"
```

| 键 | 说明 |
|---|---|
| `auth.github_token` | 等价于最高优先级的 CLI Provider 输入（配置项与 `--github-token` 参数二选一生效，CLI 参数优先） |
| `auth.account_type` | 见「account-type 无默认」一节 |
| `auth.token_file` | 覆盖 `FileTokenProvider` 的默认路径 |
| `headers.vscode_version` | `editor-version` 头的静态兜底值，探测成功时被覆盖 |
| `headers.copilot_version` | `editor-plugin-version`/`user-agent` 头 |
| `headers.api_version` | `x-github-api-version` 头（GitHub 公共 API 与 Copilot 内部 API 共用同一常量） |

## 相关文档

- [设计文档总纲](DESIGN.md)
- [配置系统](config-system.md)（完整配置键清单、路径解析 `get_token_path()`）
- [数据模型](data-models.md)（`ModelInfo.request_headers` 等模型级头字段）
- [请求执行管道](request-pipeline.md)（`TokenRefreshStrategy` 与 401/403 重试集成）
- [项目结构](project-structure.md)（lifespan 各阶段如何初始化 Token Provider 链与首次交换）
