# Token exchange identity 只读验收

## 判定

**PASS**

验收范围仅覆盖 Copilot token exchange 的启动阻断主路径：四个身份头、每次交换动态生成的 `Authorization`，以及 token endpoint 失败时应用不得进入 ready 状态。不扩展到完整 auth provider、refresh、device flow 或上游请求头矩阵。

## 绑定快照

- Worktree：`/home/xp/src/ghc-api-proxy-py-token-identity`
- Branch：`fix/copilot-token-identity`
- 最终绑定 `HEAD`：`d48792f7e47cebd34aaf61b2b86bcea337446548`（`fix(auth): send identity headers for token exchange`）
- 最终 worktree 状态：干净。
- 提交路径：`src/app/auth/copilot.py`、`src/app/upstream/bootstrap.py`、`src/app/upstream/copilot.py`、`tests/integration/test_phase1_bootstrap.py`、`tests/unit/test_copilot_token.py`
- 该提交相对父提交 `6e0112f90f39245f77618a7b4887dfe6b526c60a` 的完整 `git diff --binary` SHA-256 为 `fa631418021109ec1d3bc7cffeb363e9722c6898469527c003d806953110834c`，与提交前已验收的冻结 worktree diff SHA-256 完全一致。提交后又在 `HEAD d48792f7e47cebd34aaf61b2b86bcea337446548` 上重跑独立探针和聚焦测试。

## 从规格推导的验收矩阵

| 验收项 | Oracle | 结果 |
|---|---|---|
| Token exchange 身份 | 请求携带 `editor-version`、`editor-plugin-version`、`user-agent`、`x-vscode-user-agent-library-version`，值来自当前 `AppSettings.headers` 与固定 library identity | PASS |
| 动态认证 | 首次请求使用当前 GitHub token；收到 401 并刷新 GitHub token 后，下一次请求的 `Authorization` 随 token 更新，且不得残留或合并 stale 值 | PASS |
| 实际装配 | 启动 bootstrap 将同一身份头 builder 的结果注入 `CopilotTokenManager`，不是只在孤立 helper 中存在 | PASS |
| 启动阻断 | Token endpoint 返回 403 时 lifespan 失败，`copilot_token_ready=False`、`models_ready=False`、`upstream_services=None` | PASS |
| 真实 endpoint A/B | 仅在现有非交互 token 可用时执行；只记录状态码且不消费 body | SKIP：当前环境没有可用的非交互 token，未发请求 |

## 实现接缝核对

- `src/app/upstream/copilot.py:24-31`：单一 builder 生成四个身份头。
- `src/app/upstream/bootstrap.py:166-174`：启动路径把 builder 结果传给 `CopilotTokenManager`，随后同步等待首次 token exchange。
- `src/app/auth/copilot.py:35-44`：构造时复制并冻结身份头，避免调用方后续修改影响请求。
- `src/app/auth/copilot.py:103-116`：每次 attempt 先复制身份头，再用 `httpx.Headers.update()` 写入动态 `Authorization`、`Accept` 和 API version；大小写不同的 stale 核心键不会形成重复值。
- `src/app/server.py:102-103`：lifespan 同步等待 upstream 初始化，exchange 异常阻止进入 `yield`。

## 实际验证

### 独立 MockTransport

在最终提交 `HEAD d48792f7e47cebd34aaf61b2b86bcea337446548` 上运行独立 Python harness，并在进程内断言 `app.auth.copilot`、`app.upstream.copilot`、`app.upstream.bootstrap`、`app.server` 均从目标 worktree 加载。之所以加入该 oracle，是因为共享 `.venv` 的 editable install 曾解析到另一个 worktree；未绑定目标 `src` 的结果已作废，未计入本判定。

有效运行结果：

- `LOAD_ORACLE=PASS modules=4 target_tree=yes`
- `MOCK_TRANSPORT=PASS requests=2 identity_headers=4 authorization_dynamic=yes positive_control=red`
- `STARTUP_BLOCKING=PASS endpoint_status=403 ready=no body_recorded=no`
- 进程退出码：`0`

MockTransport 的 A/B 路径为：第一次交换返回 401，GitHub provider 切换到新假 token，第二次返回 200。两次请求都逐项校验四个身份头；两次 `Authorization` 分别匹配当次假 token，且值不同。所有 token 均为 harness 内构造的假值。

正样本对照先从已知坏样本中删除 `user-agent`，同一 identity oracle 按预期转红并报 `identity mismatch: user-agent`；恢复完整头后转绿。这证明通过结果不是“断言未覆盖身份头”的假绿。

启动阻断探针使用真实 FastAPI lifespan 和 `MockTransport`：token endpoint 返回 403 后，AnyIO `TaskGroup` 传播包含唯一 `HTTPStatusError(403)` 的 `ExceptionGroup`，lifespan 未进入 ready 区间，runtime 三个就绪状态保持未完成。未记录响应 body。

### 项目聚焦回归

使用目标 worktree `src` 作为 import root，并先断言生产模块的 `__file__` 位于目标 worktree 后运行：

- `tests/unit/test_copilot_token.py`
- `tests/integration/test_phase1_bootstrap.py`

最终提交态结果：退出码 `0`，pytest summary 为 `12 passed in 1.44s`。

### 真实 endpoint A/B

可选真实探针只会以 streaming 方式取得 response headers 后立即关闭响应，不读取 body，也不输出 token 或请求头。当前环境的 CLI、env、file 非交互 provider 均未提供 token，因此结果为：

- `REAL_AB=SKIP reason=no_noninteractive_token body_recorded=no`

未执行网络请求；该可选项不影响必选 MockTransport 与启动阻断主路径的 PASS。

## 未覆盖范围

- 未验证完整 provider 优先级、device flow、后台 refresh loop、并发刷新、模型目录或业务上游请求。
- 未读取、打印或记录任何真实 token 值。
- 未记录真实 endpoint response body；由于没有现有非交互 token，真实状态码 A/B 未执行。

## 结论

绑定快照满足本轮限定范围：token exchange 在启动主路径携带四个身份头，`Authorization` 随每次 GitHub token attempt 动态更新，且 token endpoint 失败会阻断启动。最终判定为 **PASS**。
