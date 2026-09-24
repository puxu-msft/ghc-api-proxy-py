# History export access review rerun — 2026-09-15

## 评审范围

本次是独立、只读的最终状态评审。判据来自调用方：含 credentials 的 transport 与 full export 必须有明确、有效且不依赖可配置 localhost 的访问边界；semantic 与 index 继续可用；拒绝必须稳定且不泄漏；实际 routes、配置和 tests 必须接线一致。

已审：`src/app/server/routes/history.py`、`ServerConfig.history_export_token` 的 schema/config 接线、history router 挂载、`tests/unit/history/test_history_routes.py`，以及配置示例中的 `server` 文档面。

明确未审：`archive.py`、`raw_capture.py`、`replay/process.py`、retention，以及调用方列出的其他并发 WIP；`config.example.yaml` 中的 raw-capture quota hunk 也不属于本次结论。

## 总体 verdict

未发现阻断性问题；发现 1 个 minor 文档缺口。代码的默认拒绝和 token 边界有效，semantic/index 路径未被收紧。

**Blocker 数：0**

## Findings

### F001 — minor — 管理员没有可发现的正式配置说明来启用唯一的 export 边界

- **primary_location:** `docs/.human-controlled/config.example.yaml:30-38`
- **related_locations:** `src/app/config/schema.py:128-135`; `src/app/server/routes/history.py:39-50`
- **evidence:** 唯一允许 transport/full export 的配置是 `server.history_export_token`，且请求必须附 `X-History-Export-Token`。schema 明确将它设为无默认值的 `SecretStr`，但当前 canonical config example 的 `server` 段只列出 `host`、`port` 与 TLS；对 docs、README、CONTEXT 的 token/header/transport/full route 定向检索也没有匹配。外部操作者无法从受维护的配置说明得知应配置哪个 key、token 的最小长度或应发送哪个 header。
- **impact:** 在需要访问历史取证导出的部署中，安全实现默认 fail-closed，却没有受支持的配置路径说明可将它有意开启；操作者容易只能从源码反推协议或错误地认为 export 不可用。该问题不使未经授权请求取得数据，因此定为 minor。
- **suggested_resolution:** 在 `server` 示例段补充 `history_export_token`，说明它保护 transport 和 `export=full`、默认拒绝、至少 16 个字符、使用 `X-History-Export-Token`，并明确它不改变 semantic/index 的可访问性。示例中应只放占位符，不能放真实 token。

## 已核验的承重要求

- `history.py` 对 `/transport`、`?include=transport` 与 `?export=full` 都在读取 history store 之前走同一个 token 检查；没有 token、没有 chain config、错误 token 都是固定的 `403/access_denied` JSON。正确 token 由 `SecretStr` 保存并使用 `hmac.compare_digest` 比较。配置缺省或短于 16 字符会分别拒绝访问或验证失败。
- `?export=semantic`、`?include=semantic`、entry detail 与 index 没有经过 transport gate。route test 以未配置 token 的 app 验证 index/detail/semantic；带 configured token 的 export test 再验证 semantic 不需 header、transport/full 需要 header。
- `build_router()` 实际 include 了 history router；composition 产生的 `Chain` 保存同一个 `ProxyConfig` 为 `chain.config`，与 route 的读取点及测试中的 app-state 接线一致。
- 拒绝响应是静态 error envelope，不回显 supplied/configured token。focused tests 对无 header、错误 header、`include=transport` 与 `export=full` 都断言 `403/access_denied`，并断言拒绝文本不含测试 token。

## 执行记录与搜索面

- `uv run pytest -q tests/unit/history/test_history_routes.py tests/unit/config/test_config_loading.py`：**55 passed**（4.79s）。
- 无正文、无 credentials/header 的 ASGI route probe：index 与 semantic 在 history store 缺席时为 `503/proxy_internal_error`；full 与 transport 为 `403/access_denied`；输出只含 path、status、error type 和 header-name presence boolean。
- 为检查该绿色结果的分辨力，在独立 Python 进程内临时 monkeypatch access predicate 为允许、仍不发送正文或 header；相同 transport probe 从 `403` 变为 `503`。该进程结束即还原，未修改工作树。这证实无凭据的拒绝断言确实依赖 gate，而不是在 store-unavailable 分支中偶然得到相同结果。
- 读过：上述 in-scope route/schema/router/app-state/composition/test/config-example 文件和与 token/header/route 名称匹配的 docs、README、CONTEXT 搜索结果。未读取或评判 caller 排除的 archive、raw capture、replay/process、retention 和其他并发 WIP。
- `git diff --check` 对 in-scope code/test diff 无 whitespace error；除本报告外，未修改任何文件。

## 未核验项

无。本评审没有对真实监听 socket 或真实 history evidence 执行包含凭据的成功导出，因为该项既超出“无正文/凭据 probe”约束，也不是验证拒绝边界所必需；已由 focused unit test 覆盖其带 token 的 ASGI 成功路径。
