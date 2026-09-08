# `src/app/` import 依赖事实测绘

## 方法与口径

- 范围固定为 `/home/xp/src/ghc-api-proxy-py/src/app/`，版本锚点为 `main` 的 commit `44471c6ceedd8a06a7e0cca480314f8fc205e7c0`。
- 分析脚本是 `/tmp/260814-depgraph.py`。它以 Python 3.13 的 `ast.parse()` 解析每个递归发现的 `*.py` 文件，并仅保留目标也存在于该目录的 `app.*` 静态 import 边；外部库、标准库和 `importlib`／`__import__` 的动态目标不计入本边表。
- `ast.Import` 的每个 alias 产生一条候选边；`ast.ImportFrom` 解析 `level` 与导入模块所在 package，将相对 import 还原为绝对模块名。`from . import sibling` 会在 sibling 为已知模块时连到该模块，否则保留 package 边。
- 作用域口径：`if TYPE_CHECKING:` 或 `if typing.TYPE_CHECKING:` 块内的 import 标记为 `type_checking`，因为该条件在正常运行时为假，不能作为运行时依赖；函数、异步函数及其嵌套函数体内的 import 标记为 `function` 并记录 `enclosing_function`；其余模块执行期 import 标记为 `toplevel`。类体在模块加载时执行，故类体 import 归 `toplevel`。
- 原始边表：`/tmp/260814-depgraph-edges.json`。每条记录严格含 `source_module`、`target_module`、`lineno`、`scope`、`enclosing_function` 五字段。
- 计数来自 AST，不来自文本正则：在该 commit 上运行 `cd /home/xp/src/ghc-api-proxy-py && python /tmp/260814-depgraph.py --root /home/xp/src/ghc-api-proxy-py/src/app --output /tmp/260814-depgraph-edges.json`，解析 **159** 个 Python 文件，抽取 **358** 条内部模块 import 边，其中 `toplevel` 为 **335** 条、`function` 为 **4** 条、`type_checking` 为 **19** 条；运行时图使用前两类，共 **339** 条边。
- 同一 JSON 的独立读取核对命令为 `cd /home/xp/src/ghc-api-proxy-py && python -c 'import json; e=json.load(open("/tmp/260814-depgraph-edges.json")); print(len(e)); print({k: sum(x["scope"] == k for x in e) for k in ("toplevel", "function")})'`，输出总数 **358**、`toplevel` **335**、`function` **4**、`type_checking` **19**；AST 合计与分组和相等。

## 循环依赖清单（模块级，全部 AST 边口径）

- 本节输入是 `/tmp/260814-depgraph-edges.json` 的全部 358 条 AST 边，包含 19 条 `type_checking` 边，故描述静态语法依赖而非仅运行时加载依赖。以端点去重后，模块图有 145 个顶点、356 条有向边。Tarjan low-link DFS 得到 143 个 SCC，其中 2 个为循环 SCC；独立的 Kosaraju 转置图双遍 DFS 同样得到 143 个 SCC、2 个循环 SCC，且完整组件集合逐项相同。两份可复核结果分别为 `/tmp/260814-cycles-tarjan.json` 与 `/tmp/260814-cycles-alt.json`。
- SCC 定义为互相可达的最大模块集合；本节将大小大于 1 的 SCC 视为环。扫描范围是边表的全部 145 个端点，因此不存在「未扫描的模块环」这一空白范围。
- 环 1：`app.anthropic.client` ↔ `app.pipeline.executor`。构成 SCC 的内部 import 行：`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:39 → app.pipeline.executor`（`type_checking`）；`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:357 → app.pipeline.executor`（`function`）；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/executor.py:9 → app.anthropic.client`（`toplevel`）。
- 环 2：`app.runtime` ↔ `app.upstream.bootstrap`。构成 SCC 的内部 import 行：`/home/xp/src/ghc-api-proxy-py/src/app/runtime.py:20 → app.upstream.bootstrap`（`type_checking`）；`/home/xp/src/ghc-api-proxy-py/src/app/upstream/bootstrap.py:23 → app.runtime`（`toplevel`）。

## 运行时循环与函数内延迟 import

- 运行时图排除 `type_checking`，保留 335 条 `toplevel` 与 4 条 `function` AST 边，即 339 条边、145 个顶点、339 条去重有向边。Tarjan 与 Kosaraju 分别得出 144 个 SCC、1 个循环 SCC，完整集合一致；结果在 `/tmp/260814-runtime-cycles-tarjan.json` 与 `/tmp/260814-runtime-cycles-alt.json`。唯一运行时环为 `app.anthropic.client` ↔ `app.pipeline.executor`：`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:357`（函数内）与 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/executor.py:9`（顶层）。静态环 `app.runtime` ↔ `app.upstream.bootstrap` 不在运行时图中，因为其反向边 `/home/xp/src/ghc-api-proxy-py/src/app/runtime.py:20` 是 `type_checking`。
- `/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:205` → `app.pipeline.route_policy`，函数 `AnthropicClient._decide_route`：**无明显理由**（按图）。将该边提升到运行时顶层后，顶层图仍无 SCC；目标模块没有指向 client 的运行时路径。
- `/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:357` → `app.pipeline.executor`，函数 `AnthropicClient.execute`：**为了打破循环依赖**。`app.pipeline.executor` 在 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/executor.py:9` 顶层反向 import client；将此边提升到顶层会新增该 2 模块 SCC。
- `/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:377` → `app.hooks.context`，函数 `AnthropicClient.observe_stream_finalized`：**无明显理由**（按图）。提升到顶层不会新增 SCC，且目标没有到 client 的运行时路径。
- `/home/xp/src/ghc-api-proxy-py/src/app/anthropic/client.py:378` → `app.hooks.types`，函数 `AnthropicClient.observe_stream_finalized`：**无明显理由**（按图）。提升到顶层不会新增 SCC，且目标没有到 client 的运行时路径。
- 对 335 条运行时顶层边逐条建图时没有环；将四条函数内边全部提升到顶层后恰新增 1 个环，即 client/executor。因此，按「避免导入时加载环」口径，4 条中仅 1 条隐藏了 1 个环；其余 3 条不改变顶层环数。上述「无明显理由」只表示静态图未给出循环或重依赖证据，不断言作者意图。

## 推断的运行时层次结构与违规边

- 算法与口径：读取运行时 339 条边，将每个一级子目录合并为一个包组，`src/app/` 直接子模块保持单独组；删除组内边后得到 39 个组、115 条跨组边。先求 SCC 并将其压缩为 DAG；叶子是跨组出度为 0 的组，顶层是跨组入度为 0 的组；组件层级为「到叶子最长依赖路径」，叶子为 L0。中间结果为 `/tmp/260814-layers.json`。
- 叶子（13）：`app`、`app.errors`、`app.generation`、`app.generation_identity`、`app.graceful_timeout`、`app.models`、`app.observability`、`app.release_identity`、`app.rolling_state`、`app.socket_activation`、`app.systemd_notify`、`app.transform`、`app.wire_json`。顶层（2）：`app.__main__`、`app.context`。
- L1：`app.config`、`app.generation_control`、`app.generation_control_client`、`app.openai`、`app.rolling_frontier`、`app.server_adapter`、`app.systemctl_adapter`、`app.tokenization`；L2：`app.auth`、`app.rolling_controller`、`app.rolling_runtime`、`app.runtime`、`app.streaming`；L3：循环组件 `{app.anthropic, app.history, app.hooks, app.pipeline, app.protocols, app.upstream}`；L4：`app.context`、`app.delivery`、`app.deps`；L5：`app.routes`；L6：`app.server`；L7：`app.cli`；L8：`app.__main__`。
- 违规判据是跨 SCC 边的 source 层级不高于 target 层级（`source_level <= target_level`），即低层或同层组件依赖高层。扫描运行时图的 102 条跨 SCC 边，**未发现违规边**；13 条循环组件内部跨组边不具有可排序的低／高关系，未被误报为违规。

## 扇入／扇出热点（运行时口径）

- 口径：对 159 个模块、339 条运行时 AST 边计数，每个数是不同内部模块端点数而非重复 import 行数；排序按数值降序、模块名升序。完整结果为 `/tmp/260814-hotspots-islands.json`。
- 扇入 top 15：`app.wire_json` 15；`app.config.settings` 14；`app.models.anthropic` 13；`app.deps` 9；`app.hooks.context`、`app.pipeline.context`、`app.transform.model_resolver` 各 8；`app.errors`、`app.history.types`、`app.hooks.types` 各 7；`app.anthropic.thinking.quarantine`、`app.models.common`、`app.pipeline.approval`、`app.runtime`、`app.streaming.sse` 各 6。
- 扇出 top 15：`app.server` 24；`app.upstream.bootstrap` 19；`app.anthropic.client` 17；`app.pipeline.executor`、`app.routes.anthropic` 各 14；`app.deps`、`app.routes.gemini` 各 10；`app.cli` 9；`app.routes.azure`、`app.routes.openai` 各 8；`app.delivery.responses_anthropic_stream`、`app.hooks.builtin`、`app.hooks.builtin.token_calibration`、`app.routes` 各 7；`app.rolling_controller` 6。

## 孤岛模块（运行时显式 AST import 口径）

- 判据：在 159 个模块组成的运行时显式 import 图中，入度为 0；排除入口 `app.__main__`、`app.cli` 后，共 34 个。`/home/xp/src/ghc-api-proxy-py/src/app/hooks/loader.py:17-18` 将 `settings.hooks.modules` 的运行时字符串传给 `importlib.import_module`，但 `/home/xp/src/ghc-api-proxy-py/src/app/config/settings.py:160-164` 的默认列表为空，`src/app/` 内无可枚举的动态模块名；因此本轮没有因动态加载排除的具体 `app.*` 模块。`app.hooks.builtin` 是 `/home/xp/src/ghc-api-proxy-py/src/app/server.py:18` 的静态 import，未排除。
- 入度为 0 的 34 个非入口模块：`app.anthropic`、`app.anthropic.feature_negotiation`、`app.anthropic.sanitize.deduplicate_tool_calls`、`app.anthropic.thinking`、`app.anthropic.thinking.signature_compat`、`app.auth`、`app.config`、`app.context`、`app.context.error_persistence`、`app.delivery`、`app.history`、`app.history.sessions`、`app.history.sqlite`、`app.hooks`、`app.models`、`app.observability`、`app.observability.tui`、`app.openai`、`app.openai.responses_stream_accumulator`、`app.openai.stream_accumulator`、`app.pipeline`、`app.pipeline.manager`、`app.protocols`、`app.repetition_detector`、`app.shutdown`、`app.streaming`、`app.streaming.buffered_retry`、`app.streaming.delayed_commit`、`app.streaming.translator`、`app.tokenization`、`app.transform`、`app.transform.system_prompt`、`app.transform.translator`、`app.upstream`。
- 正样本检验：`app.streaming.translator` 与 `app.transform.translator` 均在上述 34 个模块中；它们的运行时入度和出度均为 0。此结果与给定的「生产代码零消费者、仅测试 import」探针一致，但本报告的结论仅覆盖 `src/app/`，不把测试引用计为生产消费者。

## 观察（非判断）

- 静态语法图的 2 个模块环中，1 个只经 `type_checking` 边存在；运行时图仅保留 client/executor 环，且其 client → executor 边处于函数体内。
- 运行时跨包分层的唯一多包 SCC 含 `app.anthropic`、`app.history`、`app.hooks`、`app.pipeline`、`app.protocols`、`app.upstream`；其余组可按 L0～L8 排序。
- `app.wire_json` 的扇入最高（15），而 `app.server` 的扇出最高（24）；这是图上的端点计数，不包含外部库、动态字符串 import 或调用关系。

## 未覆盖面

- 本测绘只覆盖 commit `44471c6ceedd8a06a7e0cca480314f8fc205e7c0` 的 `src/app/**/*.py` 显式 AST import；未计标准库、第三方库、测试、配置中的未来动态模块名、`importlib`／`__import__` 动态目标及运行时插件。
- 图边不补充 Python 导入机制隐式加载的父 package `__init__.py`；因此 package `__init__` 可能在显式图中入度为 0，即此处的「孤岛」不等同于「运行时从未执行」。

