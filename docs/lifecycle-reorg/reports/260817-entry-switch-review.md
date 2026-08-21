# `59c9e45..7bfafdd` 评审报告

评审范围：`52b01a2` 的直接运行入口切换与其后的 synthesized headers 计时器，包含相关配置、生命周期、测试，以及 `.dev/human-controlled-docs-candidates/` 的当前状态断言。

已读取／执行的证据：逐文件 diff 与调用链；构造临时 YAML 实跑 `load_proxy_config`；`uv build --wheel --out-dir /tmp/ghc-entry-wheel-review.1OGMVd` 后用 `zipfile` 检查 wheel；实际走 Typer 解析器实跑五个 CLI 选项；定向测试 146 条与默认全量 `uv run pytest` 1221 条均通过；`uv run ruff check src tests`、`uv run pyright src tests` 均通过。

总体 verdict：修复 2 个 major 后可进入下一阶段。blocker 数量：0。

## 当前状态断言核验

- C1 已确认：`src/app/cli.py:215-227` 仍是 `load_settings` → `create_app` → `uvicorn.run`；该分支的变更仅把原先提前构造的对象移回分支内，行为未变。
- C2 已确认：实际构造仅含 `server.port: 4242` 的 YAML，`load_proxy_config` 输出 `4242 ghc ['ghc']`。
- C3 已确认：独立构建的 `/tmp/ghc-entry-wheel-review.1OGMVd/app-0.1.0-py3-none-any.whl` 含 `app/config/default_config.yaml`。
- C4 已确认：Typer 实跑五个选项均以 `warning: <option> has no effect on this path — <reason>` 输出，理由分别明确指向缺失的 schema 节或不兼容字段。
- C5 已确认：`pipeline_app._lifespan` 在 `src/app/server/pipeline_app.py:130-136` 先 `refresh_catalogs`；`StandaloneServer.serve()` 在 `src/app/lifecycle/standalone.py:90-96` 之后才注册、`arm()`、调用 `on_serving`，而 `on_serving` 才在 `entry.py:79-85` 写 pidfile／向前任发信号。
- C6 已确认：`startup_lifespan()` 仅在 Uvicorn startup 成功后才标记 `_lifespan_started`（`adapter.py:90-107`）；`serve()` 仅记录成功完成的阶段（`standalone.py:87-101`），失败时仍关闭构造时已有的 listener masters，未对未启动 lifespan 发 shutdown。
- C7 已确认：`_events_with_ping()` 只创建一个 `read_events(chunks).__aiter__()` 和一个未完成的 `anext(events)` task，两个 deadline 仅 `shield` 同一 task；带并发检测的实跑输出 `concurrent_anext False`。

## 事实性发现

[major] `src/app/config/loader.py:48-59,146-151` — `model_providers` 未列入递归合并路径，用户层会整体替换随包 provider，而不是叠加到基底层。实际 YAML `model_providers: {}` 载入为默认名 `ghc` 加空字典，随后 `build_chain()` 抛 `ProviderNotConfigured`；仅覆盖 `model_providers.ghc.base_url` 也因丢失基底 `type` 而 ValidationError。将 `model_providers` 纳入逐 provider 的递归合并，并增加空映射与局部 provider 覆盖的正向测试；若未来要支持删除基底 provider，另定义显式删除语义并校验默认名。

[major] `src/app/pipeline/delivery/stream.py:103-121` — 合成块仍交给 `BlockBuffer`，因此 `buffering_policy: full` 会把本应在 deadline 发往客户端的 preamble 一直扣到上游结束；`until-tool-use` 在工具块出现前也同样扣住它。实跑 `full`＋1 秒 deadline 在 1.3 秒内无任何下游字节，违背 `docs/.human-controlled/config.example.yaml:404-409` 的「合成…给客户端」承诺，也使候选文档 `config-schema-gap.md:72` 的无条件“已接入”断言过强。让 synthetic preamble 绕过业务块缓冲并立即写出，同时保持真实块的后续缓冲和 index 偏移；为 `block`、`until-tool-use`、`full` 都加入 deadline 的时序断言。

## 文档与结构检查

候选文档关于入口已切换、`--fd` 保留旧路径、count_tokens 新链已接线的断言与代码相符；但 `config-schema-gap.md:72` 对计时器的断言须随第二项修复而收窄或改正。

结构怪味扫描：`src/app/config/loader.py:14-59` 的层合并策略以旧 schema 的白名单表达，遗漏新的具名映射，处置为本轮修复（major 1）；`src/app/pipeline/delivery/stream.py:103-121` 把必须立即交付的控制性 preamble 交给业务缓冲策略，处置为本轮修复（major 2）。未发现其他由本范围顺带改变的默认值、count_tokens 交叉接线或第二个上游读取器问题。

## 主观建议

未列出。

## 复评与合并态

评审范围：`59c9e45..4bfaafe` 五个提交的最终合并态，重点复核前轮 M1／M2、TLS 监听接线、平滑重启与 `ListenerLifecycle` 协议。

已读取／执行的证据：生产调用链与完整 diff；实跑 `_deep_merge` 的 server／provider 覆盖；Typer CLI 注入 `server.tls.mode: both`；临时 `GHC_CONFIG` 配置；wheel 构建；`until-tool-use` 下的合成块 index 探针；定向 73 条和全量 `uv run pytest -q` 1226 条均通过，Ruff clean，Pyright 为 0 errors。

总体 verdict：存在 3 个 major，修复后再进入下一阶段。blocker 数量：0。

- 前轮 M1 已修复：`loading._deep_merge()` 保留 CLI `server.port` 之外的 `host`／`tls`，也保留基底 provider 的 `type`；`loader.py` 已只保留旧 `load_settings`，`--fd` 路径仍走它。
- 前轮 M2 已修复：`_frame_now()` 使 `full` 下合成块在 deadline 前到达；`until-tool-use` 实测 block index 为 `[0, 1, 2]` 且只有一个 `message_start`，未见 index 或策略交互回归。
- `ListenerLifecycle` 已完整覆盖 `StandaloneServer` 的九个实际调用，`FirstByteRoutingAdapter` 和 `UvicornListenerAdapter` 都具备它们；未发现该抽象的 major 漏项。

## 事实性发现

[major] `src/app/cli.py:134-145,251-258` — 直接运行入口完全没有把 `proxy_config.server.tls` 接到 `StandaloneOptions`，也从未调用 `resolve_tls_material()`。实际以 `server.tls.mode: both` 调 Typer `start`，捕获到的 config 是 `both`，options 却是 `tls_mode=False, tls_material=None`，因此用户配置仍启动明文 listener；现有 TLS 测试只直接构造 `StandaloneOptions`。在 `_serve_pipeline`／options 构造处按 `config.example.yaml:40-57` 解析 material，并以已解析用户配置文件所在目录的 `tls/` 作为无显式证书时的持久路径，补 CLI 级端到端测试。

[major] `src/app/config/loading.py:88-100,114-151` — 新恢复的 `GHC_CONFIG` 同时被 `environment_values()` 当作普通 `GHC_` schema 覆盖，生成未知顶层键 `config`。实跑仅设 `GHC_CONFIG=<有效临时 YAML>` 的 `load_proxy_config()` 即 ValidationError，故该旧启动入口并未真正恢复。将选择配置文件的控制变量从 schema 环境层排除，并增加“`GHC_CONFIG` 选中用户文件且不会成为 ProxyConfig 字段”的回归测试。

[major] `src/app/config/loading.py:20` — 随包资源被改名为 `bundled-config.yaml`，但用户裁决与 `.dev/human-controlled-docs-candidates/existing-rulings.md:106` 明确指定 `src/app/config/default_config.yaml`；本轮独立 wheel 检查也显示前者存在而后者不存在，原 C3 在当前 HEAD 已失效。复用已有 loader 不要求推翻该已裁决文件名：将其 resource 常量和文件恢复为 `default_config.yaml`，并同步 `config-schema-gap.md:78` 中仍称 TLS listener 未使用的陈旧状态。

## 文档与结构检查

结构怪味扫描：`src/app/cli.py:134-145,251-258` 的 config→lifecycle 接线缺少 TLS 字段，处置为本轮修复（major 1）；`src/app/config/loading.py:88-151` 让控制变量与通用环境 schema 共享前缀，处置为本轮修复（major 2）；`src/app/config/loading.py:20` 与用户指定资源名、候选文档漂移，处置为本轮修复（major 3）。

## 主观建议

未列出。


## 第三轮

评审范围：`fb16c2d` 对 R1／R2 的修复，以及 R3 的裁决归因更正；同时复核 TLS 材料目录、测试分辨力和最终合并态。

已读取／执行的证据：完整 diff、调用链、Typer CLI 实跑探针、loader 历史 blame、权威人写文档检索；定向 71 条与全量 `uv run pytest -q` 1229 条均通过，Ruff clean，Pyright 为 0 errors。

总体 verdict：可定稿。blocker 数量：0；major 数量：0。

- R1 已确认修复：CLI 实跑 `mode: both` 输出 config／options 均为 `both`，material 非空且位于 `tls_material_dir()`；两个新增断言分别会在删掉 mode 接线或 material 接线时失败，且 HTTP-only 反向控制防止无谓生成密钥。
- R1 的 C 级目录取舍接受：`user_data_path()/tls` 是 `spec_config_file_path()` 所定义的规范配置根，避免 cwd／显式配置文件把私钥写入任意工作树；这比把密钥跟随偶然读取路径更符合该项目的部署信任边界。`config.example.yaml` 的“配置目录”在存在 legacy cwd 回退时有歧义，但不构成 blocker 或 major。
- R2 已确认修复：`CONFIG_PATH_VARIABLE` 同时供解析路径和环境过滤使用；新测试既验证 `environment_values() == {}`，又验证实际 `GHC_CONFIG` 选中端口 4321 的文件。去掉过滤会使前一断言及完整 load 失败，判据有分辨力。
- R3 不再成立为代码问题：人写权威文档中无该文件名，`BUNDLED_CONFIG_RESOURCE = "bundled-config.yaml"` 可追溯至 `173d46e`；候选记录现在明确区分了用户裁决与实施选择。口头会话原话不在本 checkout，故无法独立证实该更正的历史归因，但现有一手仓库证据不支持把文件名当作不可改的用户契约。

## 事实性发现

未发现 blocker 或 major。

## 文档与结构检查

结构怪味扫描：检查了 `cli.py` 的 config→TLS→listener 接线、`loading.py` 的控制变量／schema 环境边界、以及 `paths.py` 的持久密钥目录；修复后未发现需在本轮处理的重复实现、职责错位或新增集成断裂。

## 主观建议

未列出。
