# `src/app` 双链现状取证：入口点、可达性、成员划分

- 日期：2026-08-22
- 取证基线：`git HEAD = 959e8d1`（`test: pin the case-insensitivity the header document now states outright`）
- 工作树状态：脏。`docs/.human-controlled/` 下 5 个文件有用户未提交的改动（其中 `module-org.md` 正在被追加 `pipeline/delivery` 一行，见 §0.1）；`Dockerfile`、`docker-compose.yml`、`.dockerignore`、`exp/260820-h2-stream-cap/`、`verification/phase3_acceptance.py` 等为未追踪文件。本报告的静态量测读的是**工作树**内容，不是 HEAD 的树。
- 性质：只读调研。除本文件外未写入仓库任何文件；探针脚本写在 `/tmp/importgraph.py`，在仓库之外。

---

## 0. 结论摘要（每条的证据在后文对应小节）

1. **进程入口只有一个模块：`app.cli`**。console script、`python -m app`、Dockerfile、systemd unit 四条路径全部收敛到它（§1）。
2. **两条链现在在导入图上真的是分开的**，`app/server/__init__.py` 那句「Deliberately empty of imports」的声称**当前成立**——用真解释器验证过：`import app.server.pipeline_app` 之后 `app.routes` / `app.deps` / `app.history` / `app.hooks` / `app.openai` / `app.delivery` / `app.server.app_factory` / `app.pipeline.executor` 一个都没被加载（§2.3）。
3. **旧链已经完全不在生产路径上**。`app.server.app_factory`（旧链唯一的 ASGI 工厂）在 `src/` 里**零个生产导入者**，只被 `tests/` 与一个未追踪的 `verification/phase3_acceptance.py` 引用，而后者用的 `from app.server import create_app` 现在会直接 `ImportError`（§4）。
4. **235 个 `app.*` 模块的划分**：共享 73、新链独占 67、旧链独占 68、两条链都到不了 27（§3）。
5. **`app/routes/` 整包 12 个模块全部只属于旧链**；新链的非推理面由 `app/server/ops_routes.py` 另写（§5）。
6. **`app/delivery/` 是旧链的交付实现，`app/pipeline/delivery/` 是新链的**，两者无任何互相导入（§6）。
7. **用户追认清单里的 `core`，以及 `context`（列在「有疑虑」）、`app/shutdown.py`、`app/repetition_detector.py`、`app/lifecycle/systemd/`、`app/transform/translator.py` 等 27 个模块，两条链都到不了**，只有测试在导入（§3.4、§7.3）。
8. **`src/app/lifecycle/rolling/` 目录里只剩 `__pycache__`，没有任何 `.py`，也没有任何 git 追踪文件**——它看起来像个包，其实不是（§3.5）。

---

## 0.1 与用户追认文档的对照（只作对照，不作裁决）

`docs/.human-controlled/module-org.md`（工作树版本，含用户未提交改动）追认的模块：`cli(debug,start) config core history lifecycle(shutdown) model_provider(ghc_client) observability pipeline(delivery) server(routes)`；「尚未确认、有疑虑」：`anthropic context openai`。

用户此刻正在改这份文档，未提交的 diff 是：

```
-    pipeline
+    pipeline            # 模型请求的处理管线
+        delivery            # 客户端侧的块级交付机制
```

对照量测结果的三处值得注意的落差（**只陈述事实，处置归主会话**）：

| 文档中的条目 | 量测事实 |
|---|---|
| `server / routes` | `app/server/routes.py` 这个模块**不存在**。`app/server/__init__.py` 的 docstring 自己已经写明这一点（见 §5.1）。实际存在的是独立顶层包 `app/routes/`，而它 100% 属于旧链。 |
| `core` | 已追认，但两条链都不可达（§3.4）。唯二的生产导入者 `app.lifecycle.systemd.systemctl` 与 `app.tokenization.snapshot_store` 自身也都不可达。 |
| `pipeline / delivery` | 与量测一致：`app/pipeline/delivery/` 是新链的交付层。但同时还存在一个顶层 `app/delivery/`，文档未提及，它属于旧链（§6）。 |

---

## 1. 入口点穷举

### 1.1 打包声明的入口

`pyproject.toml:54-55`：

```toml
[project.scripts]
ghc-api-proxy = "app.cli:main"
```

`pyproject.toml` 全文只有 `[build-system] [project] [dependency-groups] [project.scripts] [tool.pytest.ini_options] [tool.ruff] [tool.ruff.lint] [tool.pyright]` 八个节（`rg -n '^\[' pyproject.toml`）——**没有 `[project.entry-points]`**，因此不存在 entry point 插件面。

### 1.2 `python -m app`

`src/app/__main__.py` 全文：

```python
from app.cli import main

if __name__ == "__main__":
    main()
```

### 1.3 容器

`Dockerfile:28`：`CMD ["python", "-m", "app", "start"]` →（1.2）→ `app.cli`。

### 1.4 systemd

单元文件的 `ExecStart` 由测试钉住：

- `tests/systemd/test_systemd_user_install.py:121`：`ExecStart="{sys.executable}" -m app start --fd 3 ...`
- `tests/systemd/test_systemd_units.py:161-165`：`["/opt/ghc-api-proxy/.venv/bin/python", ...]`（`-m app start` 形式）

同样 →（1.2）→ `app.cli`。`--fd 3` 走 `app.cli:118 serve_inherited`，它 `uvicorn.Server(uvicorn.Config(create_pipeline_app(chain), fd=fd, ...))`（`src/app/cli.py:118-135`）。

### 1.5 ASGI app 工厂

`src/` 里只有两个 ASGI 应用工厂：

| 工厂 | 位置 | 生产导入者 |
|---|---|---|
| `create_pipeline_app` | `src/app/server/pipeline_app.py` | `app.cli`（唯一） |
| `create_app` | `src/app/server/app_factory.py` | **无** |

`app.cli` 两条服务路径都用前者：
- `--fd`：`src/app/cli.py:126` `create_pipeline_app(chain)`
- 独立运行：`src/app/cli.py:140-156` `_serve_pipeline` → `run_standalone(create_pipeline_app(chain), options, ...)`

没有任何 `uvicorn --factory "模块:函数"` 形式的字符串入口（`rg 'uvicorn\.|"app\.[a-z_.]+:' src/` 只命中 `pyproject.toml:55` 和 `cli.py` 里直接传对象的两处）。

### 1.6 `app.cli` 的命令面

`rg '@app\.command|@debug_app\.command' src/app/cli.py`：`gen-config`、`start`、`auth`、`login`、`logout`(314)、`setup-claude-code`、`setup-codex`、`list-claude-code`、`debug info`、`debug models`、`debug usage`。全部在同一个模块里，因此对导入图而言是同一个根。

**结论**：真实进程入口 = `{app.cli}`（`app.__main__` 是它的薄壳）。`app.server.app_factory` 是一个**仍可构造但无人构造**的第二工厂。

---

## 2. 探针与其正样本对照

### 2.1 探针

`/tmp/importgraph.py`：AST 遍历 `src/**/*.py` 的 `Import` / `ImportFrom`，解析相对导入，把 `from app.a.b import C` 同时解析为 `app.a.b` 与（若 `C` 是子模块）`app.a.b.C`，并补上 Python 运行时**真的会执行**的父包边（`app.a.b` → `app.a` → `app`）。可选开关 `--with-typechecking` 决定是否计入 `if TYPE_CHECKING:` 块里的导入。

规模：`modules=235 edges=1050`。

### 2.2 正样本对照：静态图 vs 真解释器

对已知可达的真实入口 `app.cli` 做全等比对：

```
$ PYTHONPATH=src uv run --no-sync python -c "import app.cli; ...dump sys.modules..."
$ python3 /tmp/importgraph.py roots app.cli
static=140 runtime=140
IDENTICAL SETS      # diff 无输出
```

即 140 个模块的集合**逐个相同**，不是只有计数相同。这条对照证明探针确实量到了东西，且在这个根上没有漏边也没有多边。

### 2.3 关键声称的直接验证：两条链的导入图是否真的分开

`src/app/server/__init__.py` 的 docstring 声称：

> Deliberately empty of imports. Re-exporting `create_app` here meant that importing *anything* under `app.server` — including `pipeline_app`, which is the new chain — eagerly pulled in the whole existing chain behind it. Measured before removing it: every one of the 175 reachable modules was reachable from both entry points ...

**验证（真解释器，非静态图）**：

```
$ python -c "import app.server.pipeline_app; ..."
total app modules: 127
  app.routes: absent          app.deps: absent
  app.runtime: absent         app.history: absent
  app.hooks: absent           app.openai: absent
  app.delivery: absent        app.server.app_factory: absent
  app.anthropic.client: absent  app.pipeline.executor: absent

$ python -c "import app.server.app_factory; ..."
total app modules: 141
  app.server.pipeline_app: absent   app.server.handler: absent
  app.server.composition: absent    app.cli: absent
  app.lifecycle: absent             app.pipeline.delivery: absent
  app.routes: LOADED                app.deps: LOADED
```

**声称成立**。`app/server/__init__.py` 文件本身确实一行 import 也没有（`cat` 全文只有 docstring）。

该状态的来源是 `aba73fb`（2026-08-19，`refactor: make the dependency graph tell the truth before moving anything`），diff 里 `src/app/server/__init__.py | 39 +---` 即为删除 re-export。

仓库里还有一道守卫钉住它：`tests/unit/test_module_boundaries.py::test_the_new_chain_does_not_drag_in_the_existing_one`，用**子进程**从 `app.server.pipeline_app` 出发断言 `app.server.app_factory`、`app.pipeline.executor`、任何 `app.routes*` 都不在 `sys.modules` 里。同文件另有两条：typed kernel（`app.pipeline.translation_driver.content`）必须是叶子；`app.pipeline.exceptions` 必须能脱离 pipeline 导入。

### 2.4 敏感度：`TYPE_CHECKING` 边

`python3 /tmp/importgraph.py pkgs app.cli --with-typechecking` 与不带该开关的结果**都是 140/235**，且 `routes / history / hooks / openai / delivery / core / context` 在两种口径下**都是 unreached**。也就是说本报告的划分不依赖「要不要算 TYPE_CHECKING 导入」这个选择。

---

## 3. 两条链的成员

判据：
- **新链** = 从 `app.cli` 可达（等价于从 `app.server.pipeline_app` 可达 + CLI/lifecycle 那一段）。
- **旧链** = 从 `app.server.app_factory` 可达。
- **共享** = 两者交集。
- **死岛** = 两者都不可达（`app.__main__` 因为它自己就是入口壳，不计入死岛）。

计数：共享 73 / 新链独占 67 / 旧链独占 68 / 死岛 27，合计 235。

### 3.1 共享（73）

`anthropic`（11：包 init、`header_policy`、`sanitize.*` 4 个、`thinking.*` 5 个）、`config`（7）、`errors`、`graceful_timeout`、`model_provider`（17）、`models`（5：不含 `models.openai`）、`observability`（3：包 init、`logging`、`terminal`）、`pipeline`（4：包 init、`exceptions`、`translation_driver` 包 init、`translation_driver.reasoning_carrier`）、`protocols`（4：不含 `protocols.azure`）、`server`（仅包 init）、`streaming`（4：`idle_timeout`、`keepalive`、`sse` + 包 init）、`tokenization`（6：不含 `snapshot_store`）、`transform`（2：包 init、`model_resolver`）、`upstream`（5：`client`、`copilot`、`ghc_settings`、`urls` + 包 init）、`wire_json`。

**注意**：`anthropic`、`pipeline`、`observability`、`streaming`、`upstream`、`models`、`protocols` 这几个包是**在包内部被切开的**——包名本身不能作为链归属的判据。

### 3.2 新链独占（67）

- `cli`
- `debug`（2）
- `lifecycle`（8：`activation` `adapter` `entry` `listener` `pidfile` `shutdown` `standalone` + 包 init；**不含 `lifecycle.systemd.*`**）
- `model_provider.ghc_client.auth.service`
- `observability`（7：`active_requests` `footer` `metrics` `rejection_capture` `request_log` `request_log_file` `tui`）
- `pipeline`（39：`delivery` 整个子树 13 个、`direct_driver` 5 个、`subscribers` 5 个、`translation_driver` 中除 `reasoning_carrier` 外的 7 个，以及 `anthropic_request_hook` `count_tokens` `events` `model_resolution` `rate_limiting` `request` `request_headers` `retry` `routing` `server_tool_text`）
- `server`（7：`admission` `composition` `handler` `inbound` `ops_routes` `pipeline_app` `tls`）
- `streaming.deadline`、`upstream.stream_cap`

### 3.3 旧链独占（68）

- `routes`（12，全包）
- `hooks`（10，全包）
- `history`（9：不含 `history.sessions`）
- `anthropic`（9：`client` `features` `message_tools` `request_preparation` `response_validation` `sanitize.read_tool_result_tags` `sanitize.system_reminders` `thinking.quarantine` `warmup`）
- `openai`（6：不含两个 accumulator）
- `pipeline`（6：`approval` `context` `executor` `protocol_guard` `rate_limiter` `strategies`）
- `delivery`（3，全包）
- `upstream`（4：`base` `bootstrap` `generic` `models_api`）
- `deps`、`runtime`、`server.app_factory`、`models.openai`、`protocols.azure`
- `observability`（2：`telemetry` `tracing`）、`streaming`（2：`anthropic_usage` `openai_sse`）

### 3.4 死岛（27）——两条链都到不了

`app.__main__`（入口壳，不算死）之外的 26 个：

| 包 | 模块 |
|---|---|
| anthropic | `feature_negotiation`、`sanitize.deduplicate_tool_calls`、`thinking.signature_compat` |
| config | `config.provider` |
| context | `context`、`context.consumers`、`context.error_persistence`（**整包**） |
| core | `core`、`core.generation_identity`、`core.release_identity`（**整包**） |
| history | `history.sessions` |
| lifecycle | `lifecycle.systemd`、`lifecycle.systemd.notify`、`lifecycle.systemd.systemctl`（**整个子包**） |
| openai | `responses_stream_accumulator`、`stream_accumulator` |
| pipeline | `manager`、`route_policy` |
| streaming | `buffered_retry`、`delayed_commit`、`translator` |
| tokenization | `snapshot_store` |
| transform | `system_prompt`、`translator` |
| 顶层单文件 | `repetition_detector`、`shutdown` |

`core` 的两个生产导入者（`app.lifecycle.systemd.systemctl`、`app.tokenization.snapshot_store`）本身也在这张表里——`core` 是一个**只被死模块引用的死岛**。它的 docstring 自称服务于 `lifecycle.rolling` 与 `tokenization.snapshot_store`（`src/app/core/__init__.py:1-6`），而 `lifecycle/rolling` 已无源码（§3.5）。

`pipeline.manager` / `pipeline.route_policy` / `repetition_detector` / `shutdown` / `transform.translator` / `streaming.translator` 的生产导入者数为 **0**（`importgraph.py who <mod>` 输出空）。

### 3.5 `src/app/lifecycle/rolling/`

```
$ find src/app/lifecycle/rolling -type f -o -type d
src/app/lifecycle/rolling
src/app/lifecycle/rolling/__pycache__
src/app/lifecycle/rolling/generation
src/app/lifecycle/rolling/__pycache__/{state,frontier,__init__,controller,runtime}.cpython-314.pyc
src/app/lifecycle/rolling/generation/__pycache__/{control,admission,__init__,phases,control_client}.cpython-314.pyc

$ git ls-files src/app/lifecycle/rolling      # 空
```

**没有任何 `.py`，也没有任何被 git 追踪的文件**。目录里只剩上一次存在过源码时留下的 `.pyc`。它不是一个包，也不出现在 235 个模块里。（这些 `.pyc` 在 CPython 3.14 下不会被当作模块加载——source-less 加载只对紧邻的 `.pyc` 生效，`__pycache__/` 下的不行。此判断基于 PEP 3147 的常规行为，**未实测**。）

---

## 4. 旧链是否仍在生产路径上

**否。没有任何真实入口走它。**

证据链：

1. `app.server.app_factory` 的生产导入者集合为空（`importgraph.py who app.server.app_factory` 输出为空）。
2. `create_app` 在 `src/` 中除定义处外零引用；全部引用来自 `tests/`（12 个文件）与未追踪脚本 `verification/phase3_acceptance.py:217`。
3. `verification/phase3_acceptance.py` 用的是 `from app.server import create_app`，现在直接报错：

   ```
   ImportError: cannot import name 'create_app' from 'app.server'
   ```

   该文件未被 git 追踪（`git status` 里是 `??`），且同文件还引用了 `app.routes.config`（不存在）、`app.ghc_client.*`（已迁到 `app.model_provider.ghc_client`）。它是历史遗留脚本，不构成入口。
4. `exp/260820-empty-text-probe/*.py` 同样引用早已搬走的 `app.ghc_client.*`，也不是入口。
5. 代码里已有一处白纸黑字的自述，`src/app/config/loader.py:3`：

   > As of 2026-08-22 `load_settings` has no caller in `src/` beyond `app.config.__init__` re-exporting it, and its only exercise is `tests/unit/config/test_config_loader.py`. It is kept because `AppSettings` still configures the legacy chain (`app.routes` / `AnthropicClient` / `app.deps`), which is present and not deleted; nothing on the new chain reads it.

**旧链的存活方式**：`AppSettings` → `create_app(AppSettings())` → `app.routes.*` + `app.deps` + `app.runtime`，这条链只在测试进程里被构造。

**一处需要注意的分叉**：`app.hooks` 整包只在旧链上。新链侧对 hooks 的唯一相关物是 `app.pipeline.subscribers`（新链独占）。也就是说 `config.schema` 里的 `hooks.on_*` 配置项（`src/app/config/schema.py:303-308`）在新链进程里没有消费者——这是本次量测顺带发现的事实，不作处置建议。

---

## 5. `app/routes/` 与 `app/server/`

### 5.1 `app/routes/`

一个**独立顶层包**，不是 `app/server/routes`。`src/app/routes/__init__.py` 只做 router re-export（7 个 router）。12 个模块：`anthropic approval azure gemini health history management metrics openai protocol_history responses_ws` + 包 init。

生产导入者：

```
app.routes  <-  app.routes.azure, app.routes.gemini, app.routes.openai, app.routes.responses_ws, app.server.app_factory
```

即：**只有 `app.server.app_factory` 从包外导入它**。`app_factory` 无生产导入者 ⇒ 整个 `app/routes/` 在生产进程里不可达。

`app/server/__init__.py` 的 docstring 也点名了这一点：

> It calls the entry `app.server.routes`; no such module exists here — the real list is below — so that spelling is the document's, not this package's.

### 5.2 `app/server/` 八个模块的导入者

| 模块 | 生产导入者（`src/app` 内） | 判定 |
|---|---|---|
| `pipeline_app.py` | `app.cli` | 新链 ASGI 工厂 |
| `composition.py` | `app.cli`、`app.debug.models`、`app.server.handler`、`app.server.ops_routes`、`app.server.pipeline_app` | 新链，`Chain` 装配 |
| `handler.py` | `app.server.pipeline_app` | 新链 |
| `inbound.py` | `app.server.pipeline_app` | 新链，入站格式解析 |
| `ops_routes.py` | `app.server.pipeline_app` | 新链的非推理面 |
| `admission.py` | `app.server.pipeline_app` | 新链 |
| `tls.py` | `app.cli`、`app.lifecycle.entry`、`app.lifecycle.listener` | 新链 |
| `app_factory.py` | **无** | 旧链工厂，仅测试使用 |

测试侧：`tests/unit/server/` 5 个文件全部只碰新链（`test_admission` `test_http_client_build` `test_provider_base_url_resolution` `test_server_inbound` `test_tls_and_count_tokens`）。`create_app` 的 12 个测试导入者全在 `tests/int/` 与 `tests/unit/observability/`。

`ops_routes.py:1-11` 的 docstring 自陈了它为什么不复用 `app/routes/`：

> Written against `Chain` rather than adapted from `app.routes`. Those routers resolve their state through `app.deps`, which reaches the existing chain's settings and runtime, so mounting them here would have pulled that chain back in and undone the separation the module boundaries now assert.
> ... History and the management API need state this chain does not own yet, and are absent rather than answered with a plausible stub.

**即：新链目前没有 history / management 端点**（这是文档已记录的事实，不是本次发现的缺陷）。

---

## 6. `app/delivery/` 与 `app/pipeline/delivery/`

| | `app/delivery/` | `app/pipeline/delivery/` |
|---|---|---|
| 文件 | `__init__.py` `anthropic_sse.py` `responses_anthropic_stream.py` | `__init__.py` `assembling.py` `blocks.py` `framing.py` `sse_frame.py` `sse_source.py` `stream.py` + `formats/{anthropic_messages, anthropic_messages_synthetic_reply, openai_responses}` |
| 包外生产导入者 | `app.routes.anthropic`（唯一） | `app.server.handler`、`app.server.pipeline_app`、`app.pipeline.request`、`app.observability.request_log` |
| 链归属 | 旧链独占 | 新链独占 |
| 导出物 | `AnthropicSseRenderer` `DeliveryFrontier` `DeliverySession` `DeliveryWriter` `ContinuousPrefixSequencer` `SingleWriterViolation` … | `BlockAssembler` `BlockBuffer` `CompletedBlock` `DeliverySession` `OutboundFramer` `SseFrame` `AnthropicFramer` `ResponsesFramer` … |

两者**没有任何互相导入**（`who` 的结果里互不出现）。注意两边都导出一个叫 `DeliverySession` 的名字，是两个不同的类。

`app/pipeline/delivery/__init__.py` 的 docstring 记录了它在 2026-08-22 的重组（generic 与 format-specific 两轴分离）。

---

## 7. 测试分布（粗粒度）

判据：解析每个测试文件的**直接** `import`，看它是否碰到「新链独占集」或「旧链独占集」中的模块。只碰共享集的记为 shared-only。

| 目录 | 文件 | 新 | 旧 | 碰到死岛 | 仅共享 | 不碰 app |
|---|---|---|---|---|---|---|
| component/history | 1 | 0 | 1 | 1 | 0 | 0 |
| component/model_provider | 7 | 0 | 0 | 0 | 7 | 0 |
| component/pipeline | 1 | 0 | 1 | 0 | 0 | 0 |
| e2e/claude | 5 | 1 | 0 | 0 | 0 | 4 |
| int | 26 | 7 | 18 | 1 | 0 | 1 |
| int/recorded | 5 | 2 | 0 | 0 | 0 | 3 |
| systemd | 4 | 0 | 1 | 0 | 1 | 2 |
| tui | 5 | 2 | 0 | 0 | 0 | 3 |
| unit（根） | 6 | 1 | 1 | 0 | 1 | 3 |
| unit/anthropic | 11 | 0 | 7 | 2 | 4 | 0 |
| unit/config | 4 | 1 | 0 | 1 | 2 | 0 |
| unit/context | 1 | 0 | 1 | 1 | 0 | 0 |
| unit/debug | 1 | 1 | 0 | 0 | 0 | 0 |
| unit/history | 1 | 0 | 1 | 0 | 0 | 0 |
| unit/hooks | 4 | 0 | 4 | 0 | 0 | 0 |
| unit/lifecycle | 6 | 6 | 0 | 1 | 0 | 0 |
| unit/model_provider | 5 | 2 | 0 | 0 | 3 | 0 |
| unit/models | 3 | 0 | 1 | 0 | 2 | 0 |
| unit/observability | 8 | 5 | 1 | 0 | 2 | 0 |
| unit/openai | 3 | 0 | 3 | 1 | 0 | 0 |
| unit/pipeline | 27 | 22 | 3 | 3 | 1 | 0 |
| unit/protocols | 4 | 0 | 2 | 0 | 2 | 0 |
| unit/server | 5 | 5 | 0 | 0 | 0 | 0 |
| unit/streaming | 3 | 0 | 2 | 1 | 0 | 0 |
| unit/tokenization | 6 | 0 | 0 | 1 | 5 | 0 |
| unit/transform | 2 | 0 | 0 | 1 | 1 | 0 |
| unit/upstream | 4 | 1 | 2 | 0 | 1 | 0 |

（一个文件可同时计入多列。）

### 7.1 明确测旧链的目录

`tests/unit/hooks/`（4/4）、`tests/unit/openai/`（3/3）、`tests/unit/history/`、`tests/unit/context/`、`tests/component/history/`、`tests/component/pipeline/`、`tests/unit/anthropic/` 的 7/11。`tests/int/` 里 18 个：

`test_anthropic_block_delivery` `test_anthropic_responses_happy_path` `test_anthropic_responses_route` `test_anthropic_responses_stream_route` `test_anthropic_routes` `test_approval_routes` `test_azure_routes` `test_gemini_routes` `test_health_routes` `test_history_multi_process` `test_history_routes` `test_hooks_pipeline` `test_management_routes` `test_openai_routes` `test_phase1_bootstrap` `test_responses_ws` `test_server_startup` `test_tracing_instrumentation`

### 7.2 明确测新链的目录

`tests/unit/server/`（5/5）、`tests/unit/lifecycle/`（6/6）、`tests/unit/pipeline/`（22/27，其中 `delivery/` 6 个、`subscribers/` 3 个、`translation_driver/` 3 个）、`tests/unit/debug/`、`tests/e2e/claude/_harness.py`、`tests/tui/`（2 个）、`tests/int/recorded/`（`record_cassette` `recorded_provider`）。`tests/int/` 里 7 个：`test_history_fixtures` `test_listener_quiesce_resume` `test_pipeline_app` `test_pipeline_ops_routes` `test_recorded_upstream` `test_standalone_lifecycle` `test_standalone_process`。

### 7.3 只有测试在导入死岛模块的文件

```
tests/component/history/test_history_store.py      : history.sessions
tests/int/test_anthropic_responses_happy_path.py   : pipeline.route_policy
tests/unit/anthropic/test_anthropic_deep_sanitize.py: anthropic.sanitize.deduplicate_tool_calls, anthropic.thinking.signature_compat
tests/unit/anthropic/test_feature_negotiation.py   : anthropic.feature_negotiation
tests/unit/config/test_config_loading.py           : config.provider
tests/unit/context/test_context_consumers_shutdown.py: context, context.consumers, context.error_persistence, shutdown
tests/unit/lifecycle/test_lifecycle_systemd_notify.py: lifecycle.systemd, lifecycle.systemd.notify
tests/unit/openai/test_openai_sanitize_accumulators.py: openai.responses_stream_accumulator, openai.stream_accumulator, streaming.translator
tests/unit/pipeline/test_context_manager.py        : pipeline.manager
tests/unit/pipeline/test_phase5_core.py            : repetition_detector, shutdown
tests/unit/pipeline/test_route_policy.py           : pipeline.route_policy
tests/unit/streaming/test_streaming_resilience.py  : streaming.buffered_retry, streaming.delayed_commit
tests/unit/tokenization/test_tokenization_snapshot_store.py: tokenization.snapshot_store
tests/unit/transform/test_translator.py            : transform.system_prompt, transform.translator
```

### 7.4 测试组入口

`pyproject.toml:60`：`addopts = "--strict-markers --strict-config --ignore=tests/tui --ignore=tests/e2e"`。默认扫描不含 `tests/tui` 与 `tests/e2e`。

---

## 8. 我**没有**查的部分，以及探针的能力边界

这一节按 `state-decisiveness` 标注每条结论能承担什么。

### 8.1 探针天生看不见的东西（静态导入图的盲区）

1. **动态导入**。`src/` 里唯一的运行时动态导入是 `src/app/hooks/loader.py:18` `importlib.import_module(module_name)`，模块名来自配置（`config.schema` 的 `hooks.on_*`）。这意味着**运营者配置的 hook 模块是我的图外的边**。但它只挂在旧链（`app.hooks` 旧链独占，且 `app_factory.py:17` 是唯一调用点），所以它不改变本报告任何关于新链的结论。
2. `__import__("os")` 两处（`lifecycle/listener.py:157`、`lifecycle/adapter.py:98`），标准库，不影响 `app.*` 图。
3. **字符串反射 / `getattr`**。`hooks/loader.py:19` 的 `getattr(module, "register", None)` 是唯一命中；其余未逐一审查。**未查**：是否有通过 `app.state.<x>` 或字符串键在运行时定位到某个模块对象的写法。
4. **entry point 插件**：`pyproject.toml` 无 `[project.entry-points]`，但**未查**已安装环境里是否有第三方包向本项目注册插件（例如 uvicorn 的 `--factory`、pytest 插件）。这条我判定为**存档级**，不足以据此下绝对结论。
5. **`try: import ... except ImportError:` 形式的可选依赖**：未专门枚举。我的 AST 遍历会把它们计为普通边（偏保守，宁多不少），因此不会造成「漏报可达」。

### 8.2 我做了但只做到某个程度的事

- **正样本对照只做了一个根**（`app.cli`，静态与运行时集合全等）。`app.server.app_factory` 的运行时数是 141，静态是 140 + `app.server` 包 init = 141，一致，但我**没有做逐模块 diff**，只比了计数与 8 个探针模块的在/不在。这条我判定为**足以据此行动**，因为探针模块覆盖了两条链的分界面。
- **探针对「根」本身不补父包边**（只对被导入的目标补），所以「从 `app_factory` 出发 server 只有 1/9」这个数字里少算了 `app.server` 包 init。我在 §3 的分类里手工补上了。这是探针的已知偏差，只影响根所在包的计数，不影响可达/不可达的判定。
- **`.pyc` 能否被加载**（§3.5 括注）：基于 PEP 3147 的常规行为推断，**未实测**。仅为「倾向性判断」，不要据此下删除决定。

### 8.3 完全没查的

- 两条链在**行为**上的差异（端点集合、请求语义、配置项消费面）。本报告只回答「谁导入谁」，不回答「谁做了什么」。§5.1 引用的 ops_routes docstring 是它的自述，不是我的验证。
- `.dev/docs/` 下已有文档（`architecture-audit/`、`pipeline-rewrite-parity/` 等）与本报告是否一致。我只确认了目标文件不存在、这两个 topic 目录下当前只有 `reports/` 子目录，**没有读其中内容**，因此本报告可能与既有报告重复或冲突。
- `tests/` 里的**间接**导入。§7 的分类只看直接 import；一个只 import 共享模块、却通过 fixture 拿到旧链对象的测试会被我记成 shared-only。这个表是**粗粒度**的，用于定位而非用于删除决策。
- 运行任何测试。本次未执行 `pytest` / `ruff` / `pyright`。

### 8.4 一条时效声明

「旧链无生产导入者」这个结论读的是**当前脏工作树**（HEAD=959e8d1 加上未提交改动），而不是 HEAD 的树。

**调研期间工作树被同伴改动过，已复测。** 我开工时 `git status` 里 `src/` 与 `tests/` 是干净的；收尾时出现了 5 个新的 ` M`：`src/app/cli.py`、`src/app/pipeline/direct_driver/base.py`、`src/app/server/handler.py`、`src/app/server/pipeline_app.py`、`tests/unit/pipeline/test_client_request_headers.py`。也就是说本报告 §1-§7 的量测**横跨了两个工作树状态**。

因此在这些改动落地之后重跑了一次全量探针，结果**逐项相同**：

```
modules: 235 cli: 140 factory: 141
shared: 73 new-only: 67 old-only: 68 dead: 27
app.routes/deps/history/hooks/openai/delivery/app_factory/pipeline.executor : cli=n factory=Y
app.core / app.context                                                       : cli=n factory=n
app_factory production importers: []
```

结论未受影响，**足以据此行动**。但同伴仍在改这几个文件，**若之后再有改动落地，§3 的成员划分需要重跑**——成本很低：`python3 /tmp/importgraph.py pkgs app.cli` 与 `... pkgs app.server.app_factory`（探针脚本在 `/tmp/importgraph.py`，仓库外，可能被系统清理；它是一份约 200 行的只读 AST 脚本，丢了重写即可）。
