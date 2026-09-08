# Copilot Token 后台刷新循环——删除面勘察

日期：2026-08-22。范围：仅勘察，未改动任何文件。

背景：用户裁决——既然 `get_token()`（`tokens.py:76-80`）已有懒刷新，移除 `CopilotTokenManager.run_refresh_loop` 这个后台刷新循环。全仓唯一调用点是 `app_factory.py:105`，而 `app_factory.create_app` 在 `src/` 下零调用者（legacy 链路，生产走 `composition.py` 的新链路）。

**注意区分**：`src/app/upstream/models_api.py:64` 也有一个同名方法 `ModelCatalog.run_refresh_loop`，那是模型列表缓存刷新（配置项 `model_refresh_interval`），与本次裁决的 Copilot token 刷新循环是两个不相干的机制。下文所有分析仅针对 `tokens.py` 里的那一个。

## 1. `run_refresh_loop` 本体与它独占依赖的成员

`src/app/model_provider/ghc_client/tokens.py:86-103`：

```python
    def next_refresh_delay(self, *, refresh_in: int) -> float:
        return max(float(refresh_in) - self._validity_margin, self._minimum_refresh_interval)

    async def run_refresh_loop(self) -> None:
        info: CopilotTokenInfo | None = self._current
        while True:
            delay = (
                self.next_refresh_delay(refresh_in=info.refresh_in)
                if info is not None
                else self._minimum_refresh_interval
            )
            await self._sleep(delay)
            try:
                info = await self.refresh(force=True)
            except Exception:
                # A failed background refresh must not end the loop.
                # get_token() still refreshes synchronously and propagates the error to callers.
                await self._sleep(self._minimum_refresh_interval)
```

逐个成员的「删掉循环后还有没有别的调用者」核查（全仓 `rg` 结果）：

- **`next_refresh_delay`**（`tokens.py:86-87`）——全仓仅两处调用：`run_refresh_loop` 自身（`tokens.py:93`）和单测 `tests/component/model_provider/ghc_client/test_tokens.py:258-259`（该单测就是专门测这个方法，见第 4 节）。**结论：无其他调用者，应随循环一并删除。**
- **`_sleep`**（构造参数 `sleep`，`tokens.py:49,62`）——**不是循环独占**。`run_refresh_loop` 用它两处（97、103），但 `_exchange_with_retry` 的指数退避也用它一处：

  ```python
  158                await self._sleep(float(2**attempt))
  ```
  （`tokens.py:158`，在 `_exchange_with_retry` 里，负责 408/429/5xx 重试之间的退避。）**结论：`_sleep` 本体、构造参数 `sleep`、成员 `self._sleep` 都必须保留，只删循环里用到它的那两行调用点。**
- **`_minimum_refresh_interval`**（构造参数 `minimum_refresh_interval`，`tokens.py:51,64`）——除了 `next_refresh_delay`（87 行）和 `run_refresh_loop` 自身（95、103 行）之外，全仓无其他读取者；唯一传参处是单测 `test_tokens.py:255`，该单测同属待删（第 4 节）。**结论：`next_refresh_delay` 删除后，`_minimum_refresh_interval` 属性与构造参数彻底死掉，应一并删除，否则就是「把死代码换个地方放」的典型案例。**
- **`CopilotTokenInfo.refresh_in` 字段**（`tokens.py:32`）——`.refresh_in` 的属性访问全仓仅一处：`tokens.py:93`（`next_refresh_delay(refresh_in=info.refresh_in)`），随循环一起消失。但**字段本身不能删**：`refresh()` 在解析上游响应时（`tokens.py:110-119`）要求 `raw["refresh_in"]` 存在且能转成 `int`，否则整体判为「invalid Copilot token response」并抛 `RuntimeError`；这是响应格式契约校验，与循环无关，且被多处测试显式断言（`tests/systemd/test_systemd_units.py:90` 注释「`refresh_in` is required: without it the exchange is rejected as an invalid」、`tests/systemd/test_systemd_pipeline_unit.py:42` 同类注释、以及所有构造 mock 响应的测试都带着这个字段）。**结论：字段保留，但删除循环之后它的*值*在生产代码里将不再被任何人读取，只在解析期被拿来做「存在性 + 可转 int」校验——这是一个刻意的遗留契约，不是需要清理的死代码，只是需要在报告里点出来，别误删。**

## 2. `refresh(force=True)` 的 `force` 参数

`tokens.py:105-121`：

```python
    async def refresh(self, *, force: bool = False) -> CopilotTokenInfo:
        async with self._lock:
            if not force and self._is_valid():
                assert self._current is not None
                return self._current
            raw = await self._exchange_with_retry()
            ...
```

全仓 `force=True` 传参点：

- `tokens.py:99`（`run_refresh_loop` 内部，即将删除）
- `tests/component/model_provider/ghc_client/test_tokens.py:61`（`test_copilot_token_exchange_preserves_raw_response`）
- `tests/component/model_provider/ghc_client/test_tokens.py:99`（`test_dynamic_token_headers_override_case_variant_identity_headers`）

除后台循环外没有生产代码调用 `refresh(force=True)`（`bootstrap.py`、`copilot.py`、`auth/providers.py` 里出现的 `.refresh()` 调用全部不带 `force`，见下方汇总）。上述两个单测里，`manager` 都是刚构造、从未 `get_token()` 过的全新实例，`self._current is None` ⇒ `_is_valid()` 恒为 `False`，`force=True` 与不传效果完全一致——**这两处的 `force=True` 是历史遗留的多余写法，不是在测 force 语义本身**。

**结论：循环删除后，`force` 参数在全仓范围内失去唯一使用理由，成为死参数。建议一并删除 `force` 形参与 `if not force and self._is_valid()` 判断（等价于恒定走 `if self._is_valid(): return self._current` 之后再退回原分支），并把上述两个测试里的 `refresh(force=True)` 改写成 `refresh()`（行为不变，见第 4 节）。这一步不在用户原始裁决的字面范围内（用户只说删循环），但直接是循环删除的连带死代码，按「不留同形死代码」的精神一并列出，供你决定是否采纳。**

## 3. `app_factory.py:104-105` 的上下文

`src/app/server/app_factory.py:95-110`（`_lifespan` 内，前后各留出上下文）：

```python
             token_path = Path(settings.auth.token_file) if settings.auth.token_file else None
             has_noninteractive_token = await noninteractive_token_available(
                 settings.auth.github_token,
                 token_path,
             )
             if settings.upstream.type == "generic" or has_noninteractive_token:
                 services = await initialize_upstream_services(runtime)
                 if runtime.history_store is not None and runtime.anthropic_client is not None:
                     runtime.anthropic_client.history = HistoryConsumer(runtime.history_store)
                 if runtime.anthropic_client is not None:
                     runtime.anthropic_client.approval_gate = runtime.approval_gate
                 if services.copilot_tokens is not None:
                     task_group.start_soon(services.copilot_tokens.run_refresh_loop)
                 if settings.model_refresh_interval > 0:
                     task_group.start_soon(
                         services.run_model_refresh_loop,
                         settings.model_refresh_interval,
                     )
             hook_builder = HookRegistryBuilder(disabled=tuple(settings.hooks.disabled))
```

- **`services.copilot_tokens` 字段还有没有别的用途？** 有。这个字段定义在 `src/app/upstream/bootstrap.py:63`（`UpstreamServices` dataclass），在同一文件里被大量使用：构造后立即 `await copilot_tokens.ensure_valid_token()`（177 行）、传给 `CopilotUpstream` 作为 target 的 token 源（195 行）、`get_token()` 取值去构造模型目录刷新请求头（201、212 行）、最终作为 dataclass 字段整体返回（226 行）。**删掉 `app_factory.py:104-105` 这两行，只是去掉「用它启动后台循环」这一个用途，字段本身在 `bootstrap.py` 里依旧是核心、必须保留。**
- **`task_group` 删完后还剩别的 `start_soon` 吗？** 剩，不会变成空 task group。同一 `_lifespan` 里还有：
  - `task_group.start_soon(runtime.tokenization_state.run_periodic_flush, settings.tokenization.flush_interval)`（`app_factory.py:69-72`，无条件执行）
  - `task_group.start_soon(services.run_model_refresh_loop, settings.model_refresh_interval)`（`app_factory.py:106-110`，条件 `settings.model_refresh_interval > 0`，默认配置下为真）
  删除 104-105 行后至少还有一个无条件的 `start_soon`（tokenization flush），task group 不会变空。

- **顺带发现（不在第 4 题范围，但与本节上下文直接相关）**：`tests/int/test_server_startup.py:32` 有一行 `services.copilot_tokens = None`，专门用来让 `if services.copilot_tokens is not None:` 这个判断走 `False` 分支、避免 lifespan 测试里真的起后台循环。这一行本身不测 `run_refresh_loop`，但删掉 104-105 行后这行 mock 设置会失去意义（判断分支不存在了，设不设 `None` 都一样），建议顺手一并删掉，纯粹是不留摆设，不影响测试通过与否。

## 4. 现有测试逐项判定

范围：直接测 `run_refresh_loop` / `next_refresh_delay` / `refresh(force=True)` / `_sleep` 注入的测试。均在 `tests/component/model_provider/ghc_client/test_tokens.py`。

| 行号 | 测试函数 | 测的是什么 | 判定 |
|---|---|---|---|
| 30-73 | `test_copilot_token_exchange_preserves_raw_response` | `refresh(force=True)`，但 manager 是全新实例，`force` 不改变行为；实际测的是身份请求头透传 + `raw` 保留 | **改写保留**——把 `await manager.refresh(force=True)` 改成 `await manager.refresh()`，语义不变 |
| 76-104 | `test_dynamic_token_headers_override_case_variant_identity_headers` | 同上，`refresh(force=True)` 测大小写变体请求头覆盖 | **改写保留**——同上改法 |
| 108-129 | `test_valid_copilot_token_is_cached` | `get_token()` 缓存命中，不涉及循环/force/sleep 独占成员 | 不受影响，无需改动 |
| 133-162 | `test_concurrent_refresh_is_single_flight` | 并发 `get_token()` 单飞，不涉及循环 | 不受影响 |
| 166-197 | `test_exchange_retries_transient_server_error` | `_exchange_with_retry` 的 5xx 重试退避，用到 `sleep=` 注入，但这是 `_exchange_with_retry` 自己的退避（158 行），不是循环 | 不受影响，`sleep` 参数保留 |
| 201-246 | `test_401_refreshes_github_token_before_retry` | 401 触发 GitHub token 刷新重试，不涉及循环 | 不受影响 |
| 249-259 | `test_next_refresh_delay_uses_server_hint_with_safety_margin` | 直接调用 `next_refresh_delay` | **该删除**——被测方法本身随循环一起删除 |
| 262-290 | `test_refresh_loop_survives_exhausted_refresh_failure` | 直接 `await manager.run_refresh_loop()`，断言重试耗尽后循环不崩 | **该删除**——被测方法本体删除，测试失去对象 |
| 293-318 | `test_refresh_loop_survives_invalid_success_payload` | 直接 `await manager.run_refresh_loop()`，断言响应体缺字段时循环不崩 | **该删除**——同上 |

另有 `tests/int/test_server_startup.py:32`（`services.copilot_tokens = None`）——不直接测循环，但与循环的 `if` 判断绑定，见第 3 节，建议顺手清理，不强制。

`tests/unit/upstream/test_models_api.py:101` 的 `run_refresh_loop` 属于 `ModelCatalog`（模型列表刷新），与本次删除无关，**不要动**。

## 5. 配置旋钮核查

全仓搜索 `minimum_refresh_interval` / `validity_margin` / 任何 copilot-token 相关 refresh 旋钮：

- `src/app/config/schema.py` 与 `src/app/config/settings.py` 里唯一的 refresh 相关配置是 `model_refresh_interval`（`schema.py:94`、`settings.py:192`），这是 `ModelCatalog.run_refresh_loop`（模型列表缓存）的间隔，与 Copilot token 刷新循环无关。
- `docs/.human-controlled/config.example.yaml:166-167` 同样只暴露了 `model_refresh_interval`（注释「后台刷新模型列表…的间隔秒数」），未提及 Copilot token 刷新。
- `minimum_refresh_interval`、`validity_margin` 全仓只在 `CopilotTokenManager.__init__` 的默认参数（`tokens.py:50-51`）和测试构造调用里出现，从未被任何配置层、环境变量、或用户文档暴露为可调项。

**结论：没有配置旋钮会因为删除循环而变成空配置——它们本来就不是外部可配置的，只是构造函数的内部默认值。`docs/.human-controlled/config.example.yaml` 不需要任何改动（也不允许我改）。**

## 6. 删除后剩下的懒刷新路径是否自洽

`tokens.py:70-121`：

```python
    def _is_valid(self) -> bool:
        return (
            self._current is not None
            and self._clock() < self._current.expires_at - self._validity_margin
        )

    async def get_token(self) -> str:
        if self._is_valid():
            assert self._current is not None
            return self._current.token
        return (await self.refresh()).token

    async def ensure_valid_token(self) -> None:
        if not self._is_valid():
            await self.refresh()
```

- **锁**：`refresh()` 整体在 `async with self._lock` 内（105-121 行），并发 `get_token()` 调用者共享同一把 `anyio.Lock`，天然单飞——已有测试 `test_concurrent_refresh_is_single_flight` 覆盖，删除循环不影响这条路径。
- **401 重试**：`_exchange_with_retry`（123-160 行）里，收到 401 会调用 `self._github_tokens.refresh()` 换新的 GitHub token 后 `continue` 重试一次；这条路径不依赖后台循环，独立自洽。
- **退避**：408/429/5xx 用 `await self._sleep(float(2**attempt))` 指数退避（158 行），如第 1 节所述 `_sleep` 保留，退避机制不受影响。
- **懒刷新自身**：`get_token()` 在 `_is_valid()` 为假时同步调用 `refresh()`，`refresh()` 内部会重新走一次完整的 `_exchange_with_retry`（含上面两条），失败会把异常原样抛给调用者——这正是循环注释里写的「get_token() still refreshes synchronously and propagates the error to callers」，删除循环不会破坏这一保证，因为这本来就是 `get_token()` 自己的逻辑，不依赖循环。

**功能上自洽，没有发现该路径本身的回归。**

**但存在一个必须点出的行为变化（不是 bug，是裁决的直接后果）**：后台循环原本会在 token 到期前主动换新，且换新失败时静默重试（`except Exception: await self._sleep(...)`，103 行），相当于把网络往返和潜在的失败重试都挪到了「没人在等」的后台。删除循环后，如果服务空闲时间超过一个 token 的有效期（`expires_at - validity_margin` 之后一直没有请求进来），**下一个到来的真实请求会同步背上这次换新的网络往返、以及可能的 401/5xx 重试退避**——即把原本摊在后台的延迟和失败风险，转移到了第一个撞上过期的用户请求头上。这正是「懒刷新」相对「后台预刷新」的固有取舍，用户裁决的前提（「既然有懒刷新」）已经认可了这个取舍，我只如实指出这一点，不建议因此保留循环或加别的补偿机制。

## 7. `ensure_valid_token()` 的调用者（如实报告，不建议顺手改）

全仓仅一处调用：`src/app/upstream/bootstrap.py:177`，在 `initialize_upstream_services` 里构造完 `CopilotTokenManager` 之后立即调用一次，做启动期的凭据校验（`bootstrap.py:172-178`）。而 `initialize_upstream_services` 只被 legacy 的 `app_factory.py:99` 调用（以及它自己的测试 `tests/int/test_phase1_bootstrap.py`）；生产新链路 `src/app/server/composition.py:411` 构造 `CopilotTokenManager` 后**没有**调用 `ensure_valid_token()`，也没有任何等价的启动期凭据校验。**这条不在本次裁决范围内，只报告现状，不建议处理。**

---

## 删除清单

| 文件 | 符号 / 位置 | 删还是改 | 理由 |
|---|---|---|---|
| `src/app/model_provider/ghc_client/tokens.py` | `run_refresh_loop`（89-103 行） | 删 | 用户裁决的直接目标；唯一调用点即将消失 |
| `src/app/model_provider/ghc_client/tokens.py` | `next_refresh_delay`（86-87 行） | 删 | 除循环外仅被待删单测调用，无其他生产/测试调用者 |
| `src/app/model_provider/ghc_client/tokens.py` | `_minimum_refresh_interval` 属性 + 构造参数 `minimum_refresh_interval`（51、64 行） | 删 | 除 `next_refresh_delay`/循环外无读取者，随二者一起变成死代码 |
| `src/app/model_provider/ghc_client/tokens.py` | `refresh()` 的 `force` 形参与 `if not force and ...` 判断（105-109 行） | 建议删（超出字面裁决范围，供你决定） | 循环是全仓唯一传 `True` 的调用点；两处单测传 `True` 属历史遗留写法，改成不传不影响其断言 |
| `src/app/model_provider/ghc_client/tokens.py` | `CopilotTokenInfo.refresh_in` 字段（32 行）与 `_exchange_with_retry`/`refresh()` 里对它的解析（115、118 行附近） | **不删** | 值本身不再被生产代码读取，但字段存在性校验是独立于循环的响应契约，多处测试显式依赖它 |
| `src/app/model_provider/ghc_client/tokens.py` | `_sleep` / 构造参数 `sleep`（49、62、97、103、158 行） | **不删**，仅删循环里的两处调用点（97、103） | `_exchange_with_retry` 的指数退避（158 行）仍要用它 |
| `src/app/server/app_factory.py` | 104-105 行 `if services.copilot_tokens is not None: task_group.start_soon(...)` | 删 | 循环消失后这个 start_soon 目标不存在；`services.copilot_tokens` 字段本身在 `bootstrap.py` 内另有多处用途，保留 |
| `tests/component/model_provider/ghc_client/test_tokens.py` | `test_next_refresh_delay_uses_server_hint_with_safety_margin`（249-259 行） | 删 | 被测方法删除 |
| `tests/component/model_provider/ghc_client/test_tokens.py` | `test_refresh_loop_survives_exhausted_refresh_failure`（262-290 行） | 删 | 被测方法删除 |
| `tests/component/model_provider/ghc_client/test_tokens.py` | `test_refresh_loop_survives_invalid_success_payload`（293-318 行） | 删 | 被测方法删除 |
| `tests/component/model_provider/ghc_client/test_tokens.py` | `test_copilot_token_exchange_preserves_raw_response`（61 行 `refresh(force=True)`） | 改 | `force=True` 对首次刷新无实质效果，改为 `refresh()` 保留原测试意图 |
| `tests/component/model_provider/ghc_client/test_tokens.py` | `test_dynamic_token_headers_override_case_variant_identity_headers`（99 行 `refresh(force=True)`） | 改 | 同上 |
| `tests/int/test_server_startup.py` | 32 行 `services.copilot_tokens = None` | 建议顺手删（非必须） | 绑定的 `if` 分支消失后这行只是摆设，删不删都不影响测试通过 |
| `src/app/config/schema.py` / `docs/.human-controlled/config.example.yaml` | — | 不动 | 未暴露任何 Copilot-token-refresh 相关配置旋钮，`model_refresh_interval` 是另一机制（模型列表刷新），与本次无关 |
| `src/app/upstream/models_api.py` / `tests/unit/upstream/test_models_api.py` | `ModelCatalog.run_refresh_loop` 及其测试 | 不动 | 同名但不同机制，不在裁决范围内 |

行为回归提示：删除后台循环会把「token 到期后的换新网络往返 + 可能的重试退避」从后台转移到空闲期后第一个真实请求的响应路径上——这是懒刷新方案的固有取舍，用户裁决已认可，仅在此明确记录，不建议因此追加补偿机制。
