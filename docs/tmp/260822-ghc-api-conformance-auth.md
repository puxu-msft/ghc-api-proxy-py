# `ghc_client/auth` 现状核实报告

日期：2026-08-22
核实范围：`docs/.human-controlled/ghc-api.md` 中 auth 子模块需求（device code 换 github_token、github_token 换 copilot_token）
方法：读源码 + 逐条追调用链，不修改任何代码/配置，仓库主树保持只读。

## 结论表

| 需求条目 | 现状 | 判定 | 证据 |
|---|---|---|---|
| 1. device code 流程获取 github_token | `DeviceFlowClient` 完整实现：请求 device code、轮询、`authorization_pending`/`slow_down`/过期均处理 | 满足（已实现且已接线，接线路径见下） | `src/app/model_provider/ghc_client/device_flow.py:51-88` |
| 2. github_token 换 copilot_token | `CopilotTokenManager` 完整实现兑换 + 过期刷新（后台循环 + 请求时懒刷新双保险） | 满足（已实现且已接线） | `src/app/model_provider/ghc_client/tokens.py:36-160`；接线 `src/app/server/app_factory.py:104-105` |

补充判定（非需求条目原文，但任务要求核查的问题）见下文第 3～6 节。

## 1. device_flow.py：流程是否完整

`src/app/model_provider/ghc_client/device_flow.py`：

- `request_device_code`（51-58 行）：`POST https://github.com/login/device/code`，`client_id` 硬编码为 GitHub Copilot Chat 的公开 client id（9 行），解析出 `DeviceCode`（18-25 行：`device_code/user_code/verification_uri/expires_in/interval`）。
- `poll_access_token`（60-88 行）：以 `device.interval` 为初始轮询间隔，`deadline = now + expires_in` 为截止时间；循环内：
  - 拿到 `access_token` 字符串即返回（76-78 行）；
  - `error == "authorization_pending"`：`continue`，按原间隔继续轮询（80-81 行）；
  - `error == "slow_down"`：间隔 `+5` 后 `continue`（82-84 行）；
  - 其他字符串错误：抛 `DeviceFlowError(f"GitHub device authorization failed: {error}")`（85-86 行）；
  - 响应既无 token 也无可识别 error：抛 `DeviceFlowError("invalid access token response")`（87 行）；
  - 超过 `deadline` 仍未成功：抛 `DeviceFlowError("GitHub device authorization expired")`（88 行，对应 `expired_token`）。

判定：三种错误分支（`authorization_pending`/`slow_down`/过期）均覆盖，实现完整。唯一未单独处理的是 GitHub 文档里的 `access_denied`（用户拒绝授权）——落入 85-86 行的通用字符串错误分支，行为正确（会抛出并终止），只是没有专门的错误子类型区分；不影响功能满足，仅是可读性/可分类粒度问题。

## 2. github_token → copilot_token 兑换与刷新

实现位置：`src/app/model_provider/ghc_client/tokens.py`，`CopilotTokenManager` 类（36-160 行）。

- 兑换端点：`GET {auth_base_url}/copilot_internal/v2/token`（`TOKEN_PATH`，12 行；实际请求见 136-138 行），带 `Authorization: token <github_token>` 与 `X-GitHub-Api-Version: 2025-04-01`（128-135 行）。
- 响应解析为 `CopilotTokenInfo(token, expires_at, refresh_in, raw)`（28-33 行，112-119 行）。
- **有效性判定**：`_is_valid()`（70-74 行）—— `now < expires_at - validity_margin`，`validity_margin` 默认 60 秒（构造参数，50 行）。
- **触发条件（两套，互为保险）**：
  1. 后台循环 `run_refresh_loop()`（89-103 行）：按 `next_refresh_delay(refresh_in=info.refresh_in)` 计算下次刷新延迟（86-87 行：`max(refresh_in - validity_margin, minimum_refresh_interval)`，`minimum_refresh_interval` 默认 60 秒），到时调用 `refresh(force=True)`；单次刷新失败不终止循环，而是 sleep `minimum_refresh_interval` 后重试（98-103 行注释：「A failed background refresh must not end the loop」）。
  2. 请求路径懒刷新：`get_token()`（76-80 行）与 `ensure_valid_token()`（82-84 行）在 token 失效时同步调用 `refresh()`；`refresh()` 内部用 `anyio.Lock`（68 行、106 行）保证并发调用只触发一次真实兑换请求。
- **重试与 401 处理**：`_exchange_with_retry()`（123-160 行）：最多 `max_exchange_attempts`（默认 3）次；命中 401 时先尝试 `github_tokens.refresh()`（149-152 行，即向上游 `GitHubTokenSource` 请求换新 github_token 再重试兑换）；408/429/5xx 或连接类错误按指数退避（`2**attempt` 秒）重试；其余错误直接抛出。

**刷新周期与触发条件小结**：周期由上游返回的 `refresh_in` 决定（通常远小于 token 实际有效期），触发条件是「距过期不足 `validity_margin`（60s）」或后台循环到点；两套机制共享同一把锁与同一个 `_current` 状态，不会重复兑换。

**接线**：`src/app/server/app_factory.py:104-105`：
```python
if services.copilot_tokens is not None:
    task_group.start_soon(services.copilot_tokens.run_refresh_loop)
```
在 FastAPI lifespan 中把后台刷新循环挂到 anyio task group 上，是真实生产接线（而非仅测试构造）。

## 3. `auth/providers.py` 与 `auth/service.py` 的职责边界

- **`providers.py`**（`src/app/model_provider/ghc_client/auth/providers.py`）：定义 github_token 的**来源抽象**——`GitHubTokenProvider` 基类（24-36 行）及四个实现：`CLITokenProvider`（39-53 行，优先级 1）、`EnvTokenProvider`（56-79 行，优先级 2，读 `GHC_API_PROXY_GITHUB_TOKEN`）、`FileTokenProvider`（82-122 行，优先级 3，兼具读/写/删除文件）、`DeviceAuthProvider`（131-150 行，优先级 4，驱动 device flow 并把结果写回 `FileTokenProvider`）。`GitHubTokenManager`（175-208 行）按优先级遍历 provider 链，缓存首个可用 token，`refresh()` 委托给当前 provider（若 `refreshable`）。这一层只关心「github_token 从哪来、怎么续」，不涉及 copilot_token。
- **`service.py`**（`src/app/model_provider/ghc_client/auth/service.py`）：面向**交互式登录场景**的编排——`run_device_authentication`（21-30 行）把「跑 device flow → 通知用户 → 落盘」串起来；`authenticate_device`（33-40 行）是可直接调用的入口，内部自建 `httpx2.AsyncClient`、`DeviceFlowClient`、`FileTokenProvider`；`clear_stored_token`（43-44 行）对应登出。它不参与运行时的 token 供给链，是**一次性动作**（登录/登出），产物落在与 `FileTokenProvider` 相同的文件上，供后续运行时的 `providers.py` 链读取。
- **与 `tokens.py` 的关系**：`tokens.py` 的 `CopilotTokenManager` 依赖一个满足 `GitHubTokenSource` 协议（`get_token()`/`refresh()`）的对象（`tokens.py:16-25`），完全不知道 `providers.py` 的存在；宿主项目通过适配器 `GitHubTokenSourceAdapter`（`src/app/upstream/copilot.py:26-41`）把 `GitHubTokenManager` 适配成该协议。即 `providers.py` 管 github_token 供给，`tokens.py` 管 github_token→copilot_token 兑换，两者靠宿主项目的适配器缝合，互不直接依赖。
- **与 `client.py` 的关系**：`GhcApiClient`（`client.py:23-198`）只持有一个 `CopilotTokenManager` 实例（构造参数 `tokens`，35 行），每次发请求前调用 `self._tokens.get_token()`（58 行）取 Bearer token 拼进请求头；`client.py` 完全不知道 `providers.py`/`service.py` 的存在。职责边界清晰：`providers.py` → `tokens.py`（经适配器）→ `client.py`，单向依赖，无环。

## 4. 接线核查（关键结论）

存在**两条独立的生产 composition root**，都会用到这套 auth 代码，但接线方式不同：

**(a) 服务器运行时路径（真正对外提供 HTTP 服务的入口）**

调用链：`src/app/server/app_factory.py`（FastAPI `_lifespan`，51-140 行）
→ `initialize_upstream_services`（`src/app/upstream/bootstrap.py:92-255`）
→ 第 163-169 行构造 `GitHubTokenManager([CLITokenProvider(settings.auth.github_token), EnvTokenProvider(), file_provider])`
→ 第 172-176 行构造 `CopilotTokenManager(GitHubTokenSourceAdapter(github_tokens), client, identity_headers=...)`
→ 第 177 行 `await copilot_tokens.ensure_valid_token()`（启动时就做一次真实兑换，验证凭据可用）
→ 第 193-198 行构造 `CopilotUpstream(sdk_clients, copilot_tokens, settings, interaction_id=...)`，赋给 `target`
→ `AnthropicClient`/`OpenAIClient` 持有该 `target`（236-248 行），是请求实际打到上游的对象。

`app_factory.py:94-99`：启动时先用 `noninteractive_token_available(settings.auth.github_token, token_path)`（`providers.py:153-165`，只探测 CLI/env/file 三种，**不含 device flow**）判断是否有可用凭据；`generic` 上游或探测到凭据时才调用 `initialize_upstream_services`。**没有发现任何「服务启动时若无凭据则自动跑 device flow」或「运行期懒加载重试 `initialize_upstream_services`」的代码**（对 `src/app/routes/*.py` 与 `src/app/runtime.py` 搜索 `upstream_services is None`/`initialize_upstream_services` 均无命中）。也没有任何管理 HTTP 端点触发 device flow——`src/app/routes/management.py` 只读 `runtime.github_token_ready`/`copilot_token_ready` 状态（37-38 行），不发起认证动作。

**(b) CLI 交互路径（`auth`/`login`/`logout` 命令，见第 6 节）**

调用链：`src/app/cli.py:348-357`（`auth`/`login` 命令）→ `_authenticate()`（341-345 行）→ `authenticate_device`（`auth/service.py:33-40`）→ `DeviceFlowClient`（`device_flow.py:27`）真实驱动 device flow → `FileTokenProvider.save_token`（`providers.py:106-116`）写入文件。这条链是**真实生产入口**（CLI 子命令，非测试专用），且是 device flow 唯一被调用的生产路径。

**(c) 孤儿代码：`DeviceAuthProvider`**

`grep DeviceAuthProvider` 全仓库命中：
```
src/app/model_provider/ghc_client/auth/providers.py:131  （定义）
tests/unit/model_provider/ghc_client/auth/test_auth_providers.py:7,163  （仅测试构造）
```
两条生产 composition root（`bootstrap.py:163-169` 与 `composition.py:338-345` 的 `build_github_token_source`）构造 `GitHubTokenManager` 时都只传了 `CLITokenProvider`/`EnvTokenProvider`/`FileTokenProvider` 三者，**从未把 `DeviceAuthProvider` 放进 provider 链**。也就是说：
- `DeviceAuthProvider` 本身「已实现但未接线」——它是 `providers.py` 里唯一一个会主动调用 device flow 的 `GitHubTokenProvider`，但运行时的 `GitHubTokenManager` 永远不会走到它，只被单元测试直接实例化验证。
- device flow 真正被使用的路径是 (b)：CLI 显式登录命令，而不是「provider 链里自动兜底」的形态。
- 这与需求文档「使用 device code 流程获取 github_token」在**功能上**是满足的（确实有完整流程且被 CLI 调用），但如果需求隐含的是「服务器在没有 token 时能自动走 device flow 兜底」，那部分**未实现/未接线**（`DeviceAuthProvider` 是死代码，且服务启动无自动回退）。这一点建议向用户确认其原始意图，本报告不代为裁决。

`build_chain`（`src/app/server/composition.py:388-424`，被 `cli.py`、`debug/models.py`、部分测试使用）同样只用三种 provider（`composition.py:338-345`），与 (a) 结论一致，未见第三条隐藏路径接入 `DeviceAuthProvider`。

## 5. github_token 的其他来源

除 device flow 外，确认三种来源，按 `GitHubTokenManager` 优先级排序（`providers.py:39-122`）：

1. **CLI 参数**：`CLITokenProvider`（优先级 1，`providers.py:39-53`），来自 `settings.auth.github_token`（`bootstrap.py:165`）/命令行 `--github-token` 选项（`cli.py` 中解析进 `AppSettings`）。
2. **环境变量**：`EnvTokenProvider`（优先级 2，`providers.py:56-79`），固定读取 `GHC_API_PROXY_GITHUB_TOKEN`（`GITHUB_TOKEN_VARIABLE`，`src/app/config/loading.py:29`）。`providers.py:63-66` 的类文档字符串明确记录了曾经也读 `COPILOT_API_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`，后来废弃——理由是后两者不是本项目的变量，`gh auth login` 与 CI 会到处设置，容易在不知情下认错身份。
3. **本地文件**：`FileTokenProvider`（优先级 3，`providers.py:82-122`），路径来自 `settings.auth.token_file`（若配置）否则默认 `user_data_path() / "github_token"`（`bootstrap.py:161-162`；`user_data_path()` 见 `src/app/config/paths.py:14-15`，`APP_NAME = "ghc-api-proxy"`，独立于旧项目 `copilot-api-js`/`copilot-api` 的数据目录）。

**是否复用现有 `copilot-api` 凭据文件**：没有发现任何自动复用逻辑——`user_data_path()` 用的是本项目专属的 `ghc-api-proxy` 应用名（`src/app/config/paths.py:7`），不是 `copilot-api` 的 `~/.local/share/copilot-api/`。若用户想复用旧工具已登录的 github_token，需要手动把 `settings.auth.token_file` 指向旧文件路径（`FileTokenProvider` 支持任意 `Path`，`providers.py:87-88`），代码没有为此做任何特判或默认探测。

## 6. CLI 是否暴露 device flow

有，`src/app/cli.py`：
- `auth` 命令（348-351 行）：调用 `_authenticate()` → `authenticate_device`。
- `login` 命令（354-357 行，`hidden=False`）：docstring 明确写「Alias for auth」，同样调用 `_authenticate()`。
- `logout` 命令（360-364 行）：调用 `clear_stored_token`（`auth/service.py:43-44`），删除本地存储的 github_token 文件。

`_authenticate()`（341-345 行）内部定义 `notify()` 回调向终端打印 `verification_uri`/`user_code`，再 `run(authenticate_device, notify)` 驱动整个 device flow 直到拿到 token 并落盘。这是用户可直接执行的命令行入口，非测试专用代码。

## 未采纳/待用户裁决的点

- `DeviceAuthProvider` 是否应该被接入运行时 `GitHubTokenManager` 链（即服务器在文件 token 失效、且用户在场时能否自动重新触发 device flow，而不是必须手动跑一次 `auth`/`login` 再重启服务），未在本次任务范围内改动，仅记录现状供用户裁决。
- device flow 的 `access_denied` 错误目前落入通用字符串错误分支，不影响功能满足，是否需要单独分类，同样留待用户决定。
