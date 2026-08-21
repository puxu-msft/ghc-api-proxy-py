# Token exchange identity R2 定向终审

## 评审范围

- 候选：`/home/xp/src/ghc-api-proxy-py-token-identity`，`fix/copilot-token-identity@8f164d897966fd80f9a5087083f420f2caf79ac9`。
- Base：`6e0112f90f39245f77618a7b4887dfe6b526c60a`；候选范围由实现提交 `d48792f7e47cebd34aaf61b2b86bcea337446548` 与测试提交 `8f164d897966fd80f9a5087083f420f2caf79ac9` 组成。
- 定向范围仅包括真实失败机制：四个 token exchange 身份头、大小写不敏感条件下动态 `Authorization`／内部 API version 唯一胜出、401 后刷新 GitHub token、bootstrap 从当前 `AppSettings.headers` 取得身份版本。以调用方给定的真实 A/B 事实“current Python 请求为 403、bun-style 请求为 200”作外部行为对照，不扩展 auth provider、device flow、完整请求头或业务 upstream 矩阵。
- 操作边界：候选 worktree 全程只读；唯一写入为主树本报告。未读取、打印或记录真实 token，未重新发起真实 endpoint 请求。

## 总体 verdict

**可进入下一阶段；0 major，可 squash。**

- blocker：0
- major：0
- minor：0

## 双视角覆盖证据

### 机械核对

- 现场解析并核对完整提交身份：候选 HEAD 为 `8f164d897966fd80f9a5087083f420f2caf79ac9`，base 为 `6e0112f90f39245f77618a7b4887dfe6b526c60a`，分支为 `fix/copilot-token-identity`，候选 worktree 在测试前后均干净。
- 对账最终生产代码而非只看 diff：`src/app/upstream/copilot.py:24-31` 从 `settings.headers.vscode_version` 与 `settings.headers.copilot_version` 生成 `editor-version`、`editor-plugin-version`、`user-agent`，并固定生成 `x-vscode-user-agent-library-version=electron-fetch`；`src/app/upstream/bootstrap.py:157-173` 使用 runtime 当前 `settings` 构造身份头并注入 `CopilotTokenManager`，首次 exchange 完成前不设置 `copilot_token_ready`。
- 对账动态头合并语义：`src/app/auth/copilot.py:99-115` 每个 attempt 先以 `httpx.Headers` 装载静态身份头，再用 `Headers.update()` 写入动态 `Authorization`、`Accept` 与固定内部版本 `X-GitHub-Api-Version=2025-04-01`。独立最小探针从小写 `authorization` 与大写 `X-GITHUB-API-VERSION` 起步，更新后 `get_list()` 分别仅得到 `['token dynamic']` 与 `['2025-04-01']`，未发生旧值拼接。
- 对账 401 路径：`src/app/auth/copilot.py:101-131` 每个 attempt 重新调用 `GitHubTokenManager.get_token()`；401 时调用 `refresh()`，成功后进入下一 attempt，因此第二次请求读取刷新后的 token，而不是复用首次局部值。
- 独立读取本地 bun-style 参考实现：`packages/token/src/copilot-client.ts` 的 token endpoint 请求使用 `githubHeaders(currentGithubHeaderIdentity())` 并以 `COPILOT_INTERNAL_API_VERSION` 覆盖 API version；`packages/token/src/ghc-auth-http.ts` 生成同名四个身份头；`packages/foundation/src/ghc-http-primitives.ts` 将 plugin／user-agent 共同绑定到 Copilot 版本，并将内部 API version 固定为 `2025-04-01`。候选请求形状与该成功侧的本轮目标字段一致。
- 只运行四个直接判别本轮机制的测试节点：`test_copilot_token_exchange_preserves_raw_response`、`test_dynamic_token_headers_override_case_variant_identity_headers`、`test_401_refreshes_github_token_before_retry`、`test_copilot_bootstrap_initializes_typed_runtime_services`。结果为 `4 passed in 1.67s`，退出码为 0；未运行或扩展完整 auth 矩阵。
- A/B 证据等级已分开处理：本地 `/tmp/verifier-token-identity-f93b.log` 保存了 current Python 路径对真实 `/copilot_internal/v2/token` 得到 `403 Forbidden` 的记录，堆栈落在目标 worktree 的 bootstrap → `ensure_valid_token()` → exchange 接缝；bun-style `200` 是调用方在本轮明确提供的真实对照事实。本轮未找到可独立引用的 `200` 日志，也未联网重放，因此不把该侧伪装成本轮新取证。

### 第一人称执行模拟

- 正常启动：以自定义 `AppSettings.headers` 启动 Copilot upstream，bootstrap 在首次 token exchange 前生成并注入四个身份头；集成测试观察到 token endpoint 收到 `vscode/1.2.3`、`copilot-chat/4.5.6`、`GitHubCopilotChat/4.5.6` 与 `electron-fetch`，证明不是只存在未接线 helper。
- 大小写冲突：假设静态映射恶意或误配为 `authorization`／`X-GITHUB-API-VERSION`，`httpx.Headers.update()` 以大小写不敏感语义替换旧值；回归测试再用 `get_list()` 断言每个受保护字段只有一个值，关闭 R1 指出的“静态值与动态值合并”失败路径。
- 401 刷新：第一次请求使用 `token old` 并收到 401，provider 刷新一次，第二次请求使用 `token new`；两次请求的 `Authorization`、`Accept` 与内部 API version 都各自唯一，四个身份头保持不变。
- Settings 来源：身份 builder 接收的是 `initialize_upstream_services()` 入口处的 runtime `settings`；后续 account-type 推断只复制更新 `auth.account_type`，不会另建或覆盖 header identity。正确的自定义版本输入能通过，没有发现新增校验误拒绝合法 settings 的 false-red。
- 真实 A/B 解释：current `403` 与 bun-style `200` 的已知差异落在候选补齐的四个身份字段上，且候选同时保持动态认证与内部 API version 的唯一优先级。该对照支持修复方向；它不等同于“候选 HEAD 已由本轮真实 credential 重放得到 200”，后者不属于本次终审已执行证据。

## 事实性发现

未发现问题。

R1 的唯一 major 已关闭：`identity_headers` 中大小写不同的静态 `Authorization`／API version 不再与动态值合并，新增回归同时覆盖单次 exchange 与 401 刷新两次 attempt 的唯一值约束。

## 主观建议

无。

## 结论

候选在指定真实失败机制范围内为 **0 blocker／0 major／0 minor**。四个身份头已从 bootstrap 当前 settings 接入真实 token exchange，动态 `Authorization` 与内部 API version 在大小写变体下唯一胜出，401 刷新会在下一 attempt 使用新 GitHub token；结合 current `403` → bun-style `200` 的外部 A/B 事实与本轮本地代码对照，**允许 squash**。
