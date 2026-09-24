# History Export Access Fix — Independent Review

## 评审范围

仅评审 `src/app/server/routes/history.py` 的 history export access fix，以及为此直接引入的 `ServerConfig.history_export_token`、直接配置加载测试、history route/security 测试和相关文档。明确不评审 archive storage、raw capture、replay/process、retention，以及当前工作树中其他并发 WIP。

## 总体 Verdict

**needs-fix**：发现 1 个 major 和 2 个 minor。访问边界本身已接入实际路由并且默认 fail-closed，但 direct transport 在已授权的 writer-unavailable 路径泄露为 500；公开 operator 文档和拒绝路径的 credential/capture regression coverage 也不完整。

## Blocker 数

0。

## 独立判据

调用方提供的验收判据是本评审的主判据：

1. 会携带 credentials 的 transport/full export 不得仅依赖可配置的 localhost；必须存在明确访问边界。
2. semantic/index 查询必须与 credential-bearing transport/full export 分开授权。
3. 拒绝路径必须稳定返回 4xx 或 503，且不能泄漏 credentials。
4. 测试必须分别覆盖 allow/deny、transport/full，以及 semantic/index。
5. 不能只证明 helper；须核实配置 host、管理 token、loopback/访问控制在实际 FastAPI 路由接线中生效。

仓库通用 API 文档只声明 history 的 `/history/api/*` 和 `/history/ws` 路径，未发现更细的 history export authentication 规格。因此上述调用方判据是本次授权语义的唯一明确、独立来源。

## 初始范围地图

工作树中与本主题直接相关的未提交改动为：

- `src/app/server/routes/history.py`：对 `?export=full` 和 `/transport` 引入 `X-History-Export-Token` 检查。
- `src/app/config/schema.py`：在 `ServerConfig` 新增无默认值的 `history_export_token`。
- `tests/unit/history/test_history_routes.py`：覆盖缺 token、错 token、正确 token、semantic export 和 unavailable store 的部分路径。

其余未提交改动（archive、writer、replay、provider、inference/ops 与其他测试）按范围排除。

## 已确认发现

### F001 — `transport` 通过授权后对未运行 writer 返回 500，而同等的 full export 返回 503

- **severity:** major
- **status:** open
- **primary_location:** `src/app/server/routes/history.py:282-316`（`export_history_transport`）
- **related_locations:** `src/app/server/routes/history.py:220-258`（`export_history_full`）；`src/app/history/writer.py`（`get_entry()` 在 writer 未运行时抛出 `RuntimeError`）；`tests/unit/history/test_history_routes.py:115-131,271-363`
- **criterion:** 调用方要求拒绝稳定为 4xx/503；History Spec 规定 unavailable history store 走稳定的可用性语义，并要求 transport/full 共享独立访问合同。
- **evidence:** 实际以 `load_proxy_config()` 的 nested environment 设置外部 bind host 与管理 token，使用 `build_chain()` 和 `create_pipeline_app()` 创建完整路由装配后探测。无 header 的 `/transport` 与 `?export=full` 都为 403；携带正确 header 时 `?export=full` 为 503，但 `/transport` 为 500。探针未读取或输出响应正文、token 或任何 capture。代码原因是 full handler 捕获 `RuntimeError` 后返回 `_history_unavailable()`，而 transport handler 的 `try` 只捕获 `OSError`/`ValueError`，会放出 `HistoryWriter.get_entry()` 的 “not running” RuntimeError。
- **impact:** 访问控制通过后，如果 History writer 尚未运行或已不可用，credential-bearing direct transport export 产生未约定的 500，而 full export 和其他 History route 使用 503。这个分歧既破坏稳定的 API failure contract，也使监控/调用方不能把同一 availability 状态一致处理。
- **suggested_resolution:** 在 `export_history_transport()` 按 `export_history_full()` 的方式处理 `RuntimeError` 并返回 `_history_unavailable()`；增加实际 route 覆盖：正确 token + unavailable/unstarted writer 的 direct `/transport` 必须为 503，同时保留无 token 优先为 403 的断言。

### F002 — 面向 operator 的完整配置与 API 文档没有公开管理 token/header 合同

- **severity:** minor
- **status:** open
- **primary_location:** `docs/.human-controlled/config.example.yaml:28-55`
- **related_locations:** `README.md` 的 History API 摘要；`docs/.human-controlled/api.md` 的 History API 摘要；`.dev/docs/history/spec.md` 的 v3 access contract
- **criterion:** Spec 要求 operator 配置 `server.history_export_token`，并明确外部监听时仍须管理 secret 与网络/TLS；配置示例自称“完整”配置文档，且 docs README 将它作为 operator 配置入口。
- **evidence:** 公开的 `config.example.yaml` 的 `server` 段只列 host、port、tls；README 与 `api.md` 只列 `/history/api/*`。三个面均无 `history_export_token`、`X-History-Export-Token`、transport/full export 的授权范围或外部监听提示。唯一可检索到的完整合同位于 `.dev/docs/history/spec.md`。同轮实现 ledger 也明确说明没有修改 user-controlled YAML example。
- **impact:** 从项目公开入口配置的 operator 不会获知如何启用必要的管理边界，或哪些 history 读取需要 header。安全地 fail-closed 会避免错误暴露，但会把 transport/full export 留在不可用的 403 状态，并令外部 bind 的运维要求不可发现。
- **suggested_resolution:** 在 `config.example.yaml` 的 `server` 段增加不带真实值的 `history_export_token` 注释与至少 16 字符的约束，说明它与 `X-History-Export-Token` 的配对、保护的三种 credential-bearing projection、以及 host 不是授权边界；在 README/API 摘要链接或简述该合同。

### F003 — 拒绝测试只检查管理 token 未回显，没有覆盖 capture 中 credentials 的不泄漏断言

- **severity:** minor
- **status:** open
- **primary_location:** `tests/unit/history/test_history_routes.py:271-363`
- **related_locations:** `src/app/server/routes/history.py:27-37,219-316`
- **criterion:** 调用方与 History Spec 均要求 access-denied response 不得泄漏 token、capture 或 credential；测试应覆盖拒绝路径的安全结果，而不是只覆盖 status/type。
- **evidence:** 四个 deny case 均验证 403、`access_denied`，并只断言 response text 不含测试用管理 token。相同 fixture 的 capture 没有 credential-shaped sentinel 或其他可识别的 captured-content sentinel；因此即便未来拒绝路径错误地回显 capture，现有“不包含管理 token”的断言仍可保持绿色。当前实现的静态 deny envelope 和 access-before-writer 顺序表明本版本没有该泄漏，但测试没有把该安全性质钉住。
- **impact:** 后续修改若在 deny response 中附带 diagnostics、entry/capture metadata 或 transport preview，可能暴露真正应保护的 capture credentials，而 focused suite 不会因现有断言失败。
- **suggested_resolution:** 在 capture fixture 写入一个仅用于测试的 credential-shaped sentinel（或 request header record），并在每个 deny response 断言该 sentinel 与任何 transport/capture field 均不存在；保持命令输出和报告不打印该 sentinel。

## 验证与 route probe

已运行：

| 操作 | 结果 |
|---|---|
| `uv --directory /home/xp/src/ghc-api-proxy-py run pytest -q tests/unit/history/test_history_routes.py tests/unit/config/test_config_loading.py` | 55 passed |
| `uv --directory /home/xp/src/ghc-api-proxy-py run pytest -q tests/unit/history/test_history_routes.py` | 5 passed |
| `uv --directory /home/xp/src/ghc-api-proxy-py run ruff check src/app/config/schema.py src/app/server/routes/history.py tests/unit/history/test_history_routes.py` | passed |
| `uv --directory /home/xp/src/ghc-api-proxy-py run pyright src/app/config/schema.py src/app/server/routes/history.py tests/unit/history/test_history_routes.py` | 0 errors, 0 warnings |

另行执行了不打印 response body、capture 或 token 的 route probe：以隔离的临时 XDG data 目录加载 nested environment 的 `server.host`（外部 bind 值）及 management token，随后经 `build_chain()`、`create_pipeline_app()` 和完整 router 装配发请求。观测结果为：

- 外部 host 设置确实进入生效 `ProxyConfig`；
- token 缺失时 direct transport 与 full export 都是 403；
- 相同 token 通过 direct transport gate 后得到 500，full export 对同一 unavailable writer 得到 503；
- 不带 header 的 semantic/index 未被 access gate 改写为 403（该 probe 中它们因 writer 未启动而为 503）；
- `/api/config` 快照中未包含 probe token。

独立的 config probe 同时确认 nested environment 能加载 token，短于 16 字符的值被 schema 拒绝。当前工作树默认 config 含不在本次范围内的 provider WIP，因此 probes 用隔离的 XDG data 目录避免把该无关配置作为本次 access review 的变量。

## 测试矩阵判断

| 判据面 | 当前证据 | 判断 |
|---|---|---|
| token 未配置/缺失/错误时拒绝 transport/full | unit route test + 完整装配 probe | 已覆盖；缺失 token 优先于 writer lookup |
| 正确 token 允许 transport/full | unit route test | 已覆盖；direct transport 的 unavailable 异常面见 F001 |
| semantic/index 与 credential-bearing export 分开 | unit route test + probe | 已覆盖行为分界 |
| 拒绝不得泄漏 management token | unit route test + probe | 已覆盖 |
| 拒绝不得泄漏 capture/上游 credential | 当前实现可由静态 deny envelope 支持；没有专门 regression sentinel | 测试不足，见 F003 |
| host 不能替代 access boundary | schema、Spec、完整装配 probe | 已覆盖 |
| 配置展示脱敏 | 完整装配 probe | 已覆盖 |

没有在主工作树修改实现或做受控 mutation；因此 focused test suite 的 mutation discrimination 未独立验证。F003 记录了可从当前 fixture 直接得出的具体分辨力缺口，而非将未执行的 mutation 作为事实发现。

## 搜索面与未覆盖面

已读：调用方判据；`.dev/docs/history/spec.md` 的 v3 access contract；`.dev/docs/raw-capture/spec.md` 的敏感数据面合同；`README.md`、`docs/.human-controlled/api.md`、`docs/.human-controlled/README.md`、`docs/.human-controlled/config.example.yaml`；最终的 `history.py`、`schema.py`、`loading.py`、`pipeline_app.py`、`routes/router.py`、`app_state.py`、`composition.py` 的装配段、`ops.py` 的 config presentation 段；以及直接的 history/config/ops 测试。

明确未评审：archive storage 的正确性、raw capture 实现、replay/process、retention，以及当前并发 provider/inference/observability WIP。为解释 F001 仅查询了 HistoryWriter 对未运行状态抛出 `RuntimeError` 的公开行为，没有审查其存储实现。

## 最终结论

修复 F001 后应重跑 focused route/security tests，并补齐 F002/F003 所述文档与 regression tests；在此之前不建议把本 access fix 作为可完成的 history export access contract 交付。
