# Token exchange identity 只读评审

## 评审范围

- Python current main：`/home/xp/src/ghc-api-proxy-py`，`main@6e0112f90f39245f77618a7b4887dfe6b526c60a`。
- Python 实现 WIP：`/home/xp/src/ghc-api-proxy-py-token-identity`，`fix/copilot-token-identity`，基线 HEAD 同为 `6e0112f90f39245f77618a7b4887dfe6b526c60a`；最终冻结的未提交状态哈希为 `35a2dcf5467e739da0570ac52f6f32c457d097cf3defb9ec7cc097e21dd7b1dd`。
- JavaScript 对照：`/home/xp/src/copilot-api-js`，`master@03c3dd131e15b13ac4294fd09fc10a95ad86c04b`。
- 仅核对 token exchange 的必需身份头、动态 `Authorization` 优先级、内部 API version、`user-agent` 与 editor/plugin 版本来源、测试边界。未发网络请求，未读取运行时 token 值，未扩展认证框架。

## 总体 verdict

**修复 major 后可进入下一阶段。**

- blocker：0
- major：1

Python current main 的 token exchange 只有 `Accept`、动态 `Authorization` 与内部 API version，尚缺 JS 对照的四个身份头。当前 WIP 已把四个身份头从 `settings.headers` 接入 bootstrap，并把 token exchange 的内部 API version 固定为 `2025-04-01`，方向与 JS 对照一致；但其通用 `identity_headers` 合并仍允许大小写变体的静态认证头与动态头并存，违反本轮明确要求。

## 双视角覆盖证据

### 机械核对

- 对账 JS `packages/token/src/copilot-client.ts:18-21`、`packages/token/src/ghc-auth-http.ts:23-31` 与 `packages/foundation/src/ghc-http-primitives.ts:11-23`：exchange 使用 GitHub identity headers，并将 `x-github-api-version` 覆盖为内部版本 `2025-04-01`；plugin 与 user-agent 由同一 `COPILOT_VERSION` 生成，VS Code 版本来自运行时 identity。
- 对账 Python current main 的 `src/app/auth/copilot.py:13-14,99-111` 与 `src/app/upstream/bootstrap.py:168`：确认 main 尚未向 token exchange 注入 editor/plugin、user-agent 与 electron-fetch 身份头。
- 对账 WIP 的 5 个改动文件及最终源码：`src/app/upstream/copilot.py` 新增共享 identity builder，`src/app/upstream/bootstrap.py` 从 `settings.headers` 注入，`src/app/auth/copilot.py:104-111` 在逐请求构造中后写动态认证与内部 API version。
- 运行本地 `MockTransport` 相关测试：`tests/unit/test_copilot_token.py` 与 `tests/integration/test_phase1_bootstrap.py` 共 12 条通过；解释器内 load oracle 确认加载路径为 WIP 的 `src/app/auth/copilot.py`。测试前后工作树状态哈希一致。
- 用本地 `httpx.Headers` 最小探针核对大小写不敏感语义：同时传入 `authorization` 与 `Authorization` 时，最终值被合并为两个逗号分隔值；API version 同理。未发生网络访问。

### 第一人称执行模拟

- 模拟首次 token exchange：从 `AppSettings.headers` 生成四个身份头，加入动态 GitHub `Authorization` 与内部 API version，请求可得到 JS 对照所需身份。
- 模拟 401 后刷新并重试：每轮重新取得 GitHub token，动态 `Authorization` 更新，四个身份头保持不变；现有测试覆盖了该路径。
- 模拟调用方把静态 headers 交给 `identity_headers`，且使用 HTTP 合法的不同大小写拼写：Python `dict` 不把它视为同一键，`httpx` 随后把静态值与动态值合并，服务端收到的认证字段不再是唯一动态值。现有测试只传无冲突 identity headers，无法拦住此路径。
- 模拟正确的无冲突输入：现有 12 条定向测试通过，未发现新增校验误拒绝正常身份头配置的 false-red。

## 事实性发现

[major] `src/app/auth/copilot.py:35,44,104-111` — 动态 `Authorization` 和内部 API version 不能抵御 `identity_headers` 中大小写不同的静态同名头 — `identity_headers` 是任意 `Mapping[str, str]`，先原样复制，再通过普通 `dict` 展开并写入 `Authorization`／`X-GitHub-Api-Version`。若静态映射使用小写键，Python 同时保留大小写不同的两个键；`httpx.Headers` 会将它们归一化并合并，而不是让后写的动态值唯一获胜。本地最小探针得到 `authorization=identity-static, token dynamic` 与 `api_version=identity-static, 2025-04-01`。`tests/unit/test_copilot_token.py:58-81,193-219` 只传四个无冲突身份头，也未断言 `x-github-api-version`，因此当前 12 条测试全绿仍漏掉本轮点名的覆盖边界 — 在存储或合并前按 header 名大小写不敏感地拒绝／过滤受保护字段，保证逐请求动态 `Authorization` 与固定内部 API version 是唯一最终值；补一条向 `identity_headers` 注入大小写变体冲突头的回归测试，同时断言 `authorization` 唯一为当前动态值、`x-github-api-version` 唯一为 `2025-04-01`，并保留正常四身份头与 401 重试断言。

## 主观建议

无。本报告按要求仅报告 blocker／major。
