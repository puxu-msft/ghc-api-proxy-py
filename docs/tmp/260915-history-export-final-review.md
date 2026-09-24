# History export access 最终只读评审

## 评审范围

- 判据来源：调用方于 2026-09-15 提供的验收判据。
- 已审对象：`src/app/server/routes/history.py`、history-export 所涉 config schema/loading、`docs/.human-controlled/config.example.yaml`、`docs/.human-controlled/api.md`、`tests/unit/history/test_history_routes.py`、`tests/unit/config/test_config_schema.py`、`tests/unit/config/test_config_loading.py` 的最终工作树状态。
- 明确未审：archive、raw、replay、retention、并发相关 WIP，以及其余未列出的改动。

## 总体 Verdict

pass。未发现 history export access 在指定范围内违背调用方判据的问题。

## Blocker 数

0。

## 发现

未发现问题（`findings_total=0`；`blocker=0`；`major=0`；`minor=0`；`nit=0`）。

## 判据对照与证据

- **Fail-closed access 与 header gate**：`transport`、`include=transport`、`export=transport` 和 `export=full` 都在读取 history store 前经过同一 access helper。未配置 token、未提供 header 或 header 不匹配均走固定的 `403 access_denied` 响应；比较使用 `compare_digest`。拒绝响应只含固定错误类型和消息，不携带 token、capture 或 credentials。路由单测覆盖未提供、错误 header、以及 `export=full` 的拒绝，并覆盖匹配 header 的授权成功。
- **未受门控影响的投影**：index、普通 detail、`include=semantic` 与 `export=semantic` 均不调用 access helper；路由单测确认 semantic export 无需 header 且标注不含 credentials。
- **Schema 与环境加载**：`server.history_export_token` 是无默认值的 `SecretStr | None`，最小长度为 16。配置加载器的双下划线嵌套规则将 `GHC_API_PROXY_SERVER__HISTORY_EXPORT_TOKEN` 直接映射至该字段；回归测试验证该路径加载为 `SecretStr`。聚焦测试已验证少于 16 字符被拒绝，额外只读探针确认恰好 16 字符可接受。
- **文档契约**：config example 提供非真实值占位符，说明最小长度、`X-History-Export-Token` header、默认拒绝及 semantic/index 不受影响；API 文档列出 credential-bearing routes、相同 header、未配置/缺失/不匹配时的 `403 access_denied`，以及拒绝不会回显敏感内容。

## 验证结果

- `uv run pytest tests/unit/history/test_history_routes.py tests/unit/config/test_config_schema.py tests/unit/config/test_config_loading.py`：116 passed。
- `uv run ruff check src/app/server/routes/history.py src/app/config/schema.py src/app/config/loading.py tests/unit/history/test_history_routes.py tests/unit/config/test_config_schema.py tests/unit/config/test_config_loading.py`：passed。
- `uv run pyright`：0 errors, 0 warnings, 0 informations。
- `uv run ruff check .`：未通过；失败来自评审开始前已存在的未追踪 `.claude/worktrees/` 下的独立工作树文件，不属于本次指定范围，且未作为本评审结论的依据。未修改这些文件。

## 搜索面与边界

已读最终状态的指定 route、schema、通用 config loader、两份指定文档和三份指定单测；亦检查了相关改动的最终 diff。未审 archive、raw、replay、retention、并发 WIP，以及 `.claude/worktrees/` 中的独立工作树内容；未修改被审产物。报告文件是本任务唯一落盘产物。
