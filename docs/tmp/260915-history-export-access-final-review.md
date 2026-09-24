# History export access 最终只读评审

## 评审范围

仅审最终状态中的 history export access：`src/app/server/routes/history.py`、config schema/loading、`docs/.human-controlled/config.example.yaml`、`docs/.human-controlled/api.md`，以及相关 history route/config tests。明确不审 archive、raw、replay、retention 与并发 WIP。

## 总体 verdict

needs-fix：当前最终状态满足 access contract；但 configuration security contract 缺少直接的、可防回归的 automated coverage。

## Blocker 数

0

## 独立判据

- 含 credentials 的 transport 与 `export=full` 必须被有效 token/header gate 保护，且默认拒绝。
- `semantic`、`index`、`detail` 不应被误伤。
- canonical config example 与 API docs 都须以占位符说明 token 配置、至少 16 字符，以及 `X-History-Export-Token`。
- 拒绝响应不得回显 token。

## 初始进度账本

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| 取判据与定边界 | done | 判据直接来自调用方；范围与排除项已固定。 |
| 建地图与逐处比对 | WIP | 尚未读取被审实现。 |
| focused tests 与安全 probe | pending | 仅记录状态、headers 与安全相关元数据；不读取 response body。 |
| 汇总最终报告 | pending | 待所有承重判据完成核对。 |

## 最终状态地图

- Gate 唯一入口是 `_has_history_transport_access`；`include=transport` 和 `export=transport` 都委托同一个 transport handler，`export=full` 在独立 handler 入口先验证。
- `ServerConfig.history_export_token` 是可选 `SecretStr`，最小长度为 16；`load_proxy_config` 将 file/environment/CLI layers 合并后统一 `ProxyConfig.model_validate`。
- 文档的 canonical surfaces 已定位为 `docs/.human-controlled/config.example.yaml` 与 `docs/.human-controlled/api.md`。
- 路由测试集中在 `tests/unit/history/test_history_routes.py`。未发现 `history_export_token` 出现在 config schema/loading 测试的命中面，待结合测试执行与测试内容判定覆盖是否充分。

## 发现

### HXA-001 · minor · config access contract 缺少直接回归测试

- **primary_location**：`tests/unit/config/test_config_loading.py`、`tests/unit/config/test_config_schema.py`
- **related_locations**：`src/app/config/schema.py:134`、`src/app/config/loading.py:198-242`
- **证据**：对这三个 config test files 做 AST 静态检索，`history_export_token` 的直接 field reference 均为 `none`；随后运行的两个 config test modules 虽全绿（109 passed），但不能在 `history_export_token` 的 minimum length 或 nested environment loading 被误改时可靠变红。
- **影响**：当前实现仍正确且 fail-closed；不过“至少 16 字符”与 operator 通过 config/environment 配置 gate 的安全契约没有专门回归保护，未来删除长度限制或破坏 `server` nested loading 时，现有 config tests 可以继续通过。
- **建议**：增加不含真实 credential 的 config tests，至少断言短于 16 字符被 schema 拒绝，以及 `GHC_API_PROXY_SERVER__HISTORY_EXPORT_TOKEN` 载入后形成 `SecretStr`。现有 runtime probe 已覆盖这些行为，但它不是仓库中的持久回归测试。

## 判据核对

| 承重判据 | 最终证据 | 结论 |
| --- | --- | --- |
| transport 与 `export=full` 默认拒绝且由 token/header gate 保护 | `_has_history_transport_access` 要求 `SecretStr`、header 存在且使用 `compare_digest` 匹配；transport、`include=transport` 与 full entry points 都在访问 writer 前调用 gate。非 body probe 对未配置 token 的三条路径均得到 403；配置后缺 header、错误 header、full 缺 header 也均得到 403。 | pass |
| `semantic`、index、detail 未被 gate 误伤 | `get_history_entry` 仅将 `include=transport` 委托 gated handler；semantic 另有 ungated handler。无 token 的 probe 对 index、detail、`include=semantic`、`export=semantic` 均得到 200；相应 route test 也覆盖 index/detail/semantic。 | pass |
| 最少 16 字符与正常配置 loading | schema 将该 field 定义为 optional `SecretStr` 且 `min_length=16`；loader 的 nested environment values 进入统一 `ProxyConfig.model_validate`。probe 证实 15 字符被拒绝，nested environment spelling 可载入为 `SecretStr`。 | pass（但见 HXA-001） |
| canonical docs 与示例 | `config.example.yaml` 同时说明 default deny、至少 16 字符、`X-History-Export-Token`、不应放入版本控制、semantic/index 不受影响，并只提供 placeholder；API docs 说明 protected routes、header、minimum length 与 stable 403/no-echo 行为。 | pass |
| 拒绝不回显 token | denial response 是不引用 configured/supplied token 的固定 `403 access_denied` payload；route unit test 对拒绝 response 的 text 断言不含 supplied value。为遵守本次限制，runtime probe 只观测 status、未读取 response body。 | pass |

## 执行与搜索面

- 已读/核对：`src/app/server/routes/history.py` 的 gate、dispatch 与 protected handlers；`src/app/config/schema.py`、`src/app/config/loading.py`；两份指定 canonical docs；history route test 和 config test 的安全静态摘要。
- 执行：history route focused selection 为 **3 passed, 111 deselected**；config test modules 为 **109 passed**。首次 non-body probe 因环境内客户端模块名称为 `httpx2` 而非 `httpx` 未运行；改用项目实际依赖后，probe 通过，结果为 default-denials `[403, 403, 403]`、configured-denials `[403, 403, 403]`、safe-paths `[200, 200, 200, 200]`、short-token rejection 和 nested environment loading 均为 true。
- 安全 probe 未读取或输出 response body、transport payload、token 或 credentials；报告亦未记录它们。
- 明确未评：archive、raw、replay、retention、并发 WIP、其他 history persistence/transport content correctness，以及未列出的全仓行为。

## 最终进度账本

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| 取判据与定边界 | done | 判据直接来自调用方；范围与排除项已固定。 |
| 建地图与逐处比对 | done | 全部承重判据均已逐项对照最终状态。 |
| focused tests 与安全 probe | done | 结果与限制已记录在“执行与搜索面”。 |
| 汇总最终报告 | done | HXA-001 是唯一有效发现。 |
