# Xingchen provider 代码正确性评审

> 转录件。原评审者为先前调查 provider 架构的只读 Explore agent；该运行身份不能写报告文件，因此由主会话于 2026-09-04 原样转录结论。评审对象是 feature worktree 冻结提交 `14a5fbec1f7abd349c45058b89f2c651ec2555d1`，基线 `39274d7bc3601f2236ffdfc52ea6f34f885ba405`。未发真实网络请求，未修改文件。

## 评审结论：FAIL

### MAJOR 1——reload 可产生与实际 provider graph 不一致的配置

`_pin_provider_graph()` 删除新增 provider，却不恢复 `default_model_provider`、`fallback_model_provider` 等引用：  
`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/config/provider.py:80-97,118-152`  
实测新增 `x` 并选为 default 后，结果是 `providers=['ghc']`、`default='x'`；显式 count-token leg 指向 `x` 时则直接抛 `ValidationError`。  
这违反 C2 的原子保留要求；需同步 pin graph-dependent selectors/legs，或重构为原子恢复完整 provider graph 配置。

### MAJOR 2——无效配置的错误消息可能泄露 credential

`repr=False` 只保护模型 repr；基础 `ConfigDict` 没有隐藏 validation input：  
`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/config/schema.py:73-74,136-173`  
CLI 又原样输出 `ValidationError`：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/cli.py:499-511`。  
实测把 `gateway_api_key` 放在 YAML mapping 尾部并遗漏 `install_id`，`str(error)` 完整包含 `LEAK-CREDENTIAL`。应在模型错误配置或展示边界统一隐藏 input。

### MAJOR 3——canonical-equivalent 静态模型会跨进程随机路由

Xingchen 只拒绝字节完全相同的重复项：  
`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/config/schema.py:166-173`  
但路由把大小写及 `.`/`-` 视为等价，并从 `frozenset` 建索引：  
`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/pipeline/model_resolution.py:52-58,283-303`  
实测同一配置 `["m-1.0","m-1-0"]` 在 `PYTHONHASHSEED=1/2` 分别解析为不同 ID。配置期应拒绝 canonical collision。

## C1–C8 核验

- **C1 PASS（限定所列判别联合要求）**：跨 variant、缺字段及现有 GHC 均有正负控；另有 MAJOR 3。
- **C2 FAIL**：MAJOR 1、2。
- **C3 PASS**：类型分派、独立 client、无 GitHub probe、关闭责任均有测试。
- **C4 PASS**：`CatalogProvider`、static/upstream provenance 和 GHC 输出均覆盖。
- **C5 PASS**：三个 CLI 命令都在 GitHub host/device/token-file 副作用前拒绝。
- **C6 PASS**：仅遮盖 `gateway_api_key`、`x_token`，保留诊断字段。
- **C7 PASS**：共享 error seam 的 GHC retry/delivery 回归通过。
- **C8 PASS（现有目标路径）**：原生 Chat 非流式/SSE 贯通；非 Chat 与 count-token 均证明零网络。

## 运行证据

- 定向套件：`248 passed in 2.94s`
- 全量非 E2E：`2245 passed, 2 skipped in 97.99s`
- Ruff：`All checks passed`
- Pyright：`0 errors, 0 warnings, 0 informations`
- 未发真实网络请求，未修改文件。
