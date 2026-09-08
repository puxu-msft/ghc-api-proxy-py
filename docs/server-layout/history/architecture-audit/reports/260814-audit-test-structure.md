# 测试结构独立体检 — 260814

- 仓库：`/home/xp/src/ghc-api-proxy-py`，分支 `main`，HEAD `44471c6ceedd8a06a7e0cca480314f8fc205e7c0`
- 轴线：仅测试结构（分层 / 重复覆盖 / 同源风险 / 无鉴别力断言 / 巨型文件切分 / fixture 结构 / 速度资源）
- 全量口径（本次实测，HEAD 同上）：`uv run pytest tests --collect-only -q` = **808 项 / 93 文件**；`uv run pytest tests -q` = **808 passed in 34.94s**

## 1. 结论摘要

1. **实际分层是 5 层不是 4 层**：还有一个 `tests/http/`（9 文件 / 32 用例），派活说明里没提。四层判据不成立。
2. **`smoke/` 不是一个层，是一个杂物袋**：9 个文件里同时装着纯函数断言（`test_route_policy.py`）、组件级内存管线（`test_anthropic_block_delivery.py` 1152 行）、真 ASGI 路由（2 个千行文件）和真子进程 systemd 验收。四者判据互不相同。
3. **路由级测试散在 4 个目录**：`create_app` 被 13 个文件实例化，分布于 `http/`(9)、`smoke/`(2)、`integration/`(1)、`unit/`(1)。`tests/http/` 这个专门的层没有收拢它该收的东西。
4. **全仓 0 个 `conftest.py`、0 个 `pytest.fixture`**（AST 实测）。好处：无 autouse 隐式耦合，轴 6 无风险。代价：所有 harness 逐文件复制，是巨型文件的**主因**——3 个大文件 26%–38% 的行数是首个测试之前的脚手架。
5. **同源风险已证实（做了变异实验）**：`tests/unit/test_responses_reasoning.py` 全 10 个用例用生产编码器自己算 expected，改掉 v1 载荷线格式后**10/10 依旧全绿**；只有另外 4 个文件里的字面量锚点变红。
6. **无鉴别力断言：基本干净**。129 处「assert 在 try 里」经复核全是 `try/finally` 清理，0 处被 except 吞掉；3 处「无断言」全是 `unittest.mock` 的 `assert_*`，误报。真发现仅 1 处。
7. **速度健康**：34.94s / 808 项。唯一真实墙钟浪费是 `tests/unit/test_rolling_runtime.py:632` 的 `sleep(1.1)`。无真实网络、无真实 systemd manager（`FakeSystemctl` + `systemd-analyze` 只读校验且带 skipif）。
8. **一处需裁决的历史遗留**：`tests/verification/` 残留 6 个 `.pyc`，对应 42 个 `test_spec_*` 用例，**从未进入 git 历史**。多数有同名后继，`test_spec_deletions` 那一类无后继。

**总体判断**：这套测试的**内容质量明显高于其结构质量**——判据设计（字面量锚点、fail-closed、typed terminal、正反双向）比多数项目扎实；问题几乎全部集中在「东西放在哪、harness 复制了几份」，而不是「测得对不对」。

## 2. 分层现状表

| 层 | 文件数 | 用例数 | 代码里的实际判据（非目录名） | 错层案例 |
|---|---|---|---|---|
| `unit/` | 65 | 551 | 无统一判据。主体是单模块纯函数；但含真 UNIX socket、真子进程、真 TestClient | `tests/unit/test_socket_activation.py:169`（`subprocess.run` 起真进程传 fd）、`tests/unit/test_systemd_notify.py:26`（真 `AF_UNIX` datagram socket）、`tests/unit/test_generation_control.py`（真 UNIX socket + 真文件 unlink×9）、`tests/unit/test_observability_phase6.py:47`（`TestClient(create_app(...))` 打真 `/metrics`） |
| `component/` | 2 | 43 | 单个子系统 + 真依赖替身，不过 ASGI | 判据最自洽的一层。仅 2 个文件，名不副实的是**规模**：该层承载力被浪费 |
| `integration/` | 8 | 48 | 跨进程 / 跨 socket / 真 fd 继承 / 真信号 | 判据成立。`test_rolling_controller.py` 619 行用 `FakeSystemctl`、全内存，其实是 component 级 |
| `smoke/` | 9 | 134 | **无统一判据**（见下） | `tests/smoke/test_route_policy.py`（7 用例，纯函数 `decide_protocol_leg`，零 I/O 零 app）、`tests/smoke/test_anthropic_responses_happy_path.py`（6 用例，纯函数）、`tests/smoke/test_anthropic_block_delivery.py`（1152 行 27 用例，纯内存 delivery 管线，无 app） |
| `http/` | 9 | 32 | `TestClient(create_app())` + stub client，逐路由前缀一个文件 | 判据最清晰的一层，但**没有独占它的职责**（见发现 L-3） |

`smoke/` 内部四类判据并存，逐文件列明：

| 文件 | 实际性质 | 应属 |
|---|---|---|
| `test_route_policy.py` | 纯函数真值表 | `unit/` |
| `test_anthropic_responses_happy_path.py` | 纯函数，跨模块串讲 | `unit/` 或保留为「契约导览」但改名 |
| `test_anthropic_block_delivery.py` | 内存 delivery 管线 + 并发 | `component/` |
| `test_anthropic_responses_route.py` | 真 ASGI + stub 上游 | `http/` 或 `component/` |
| `test_anthropic_responses_stream_route.py` | 真 ASGI + 流式 + 断连 | 同上 |
| `test_imports.py` | 依赖可导入性 | 真 smoke（唯一名副其实的） |
| `test_systemd_units.py` / `test_systemd_rolling_units.py` / `test_systemd_user_install.py` | 真子进程 + unit 文件渲染 | `integration/` 或独立 `deploy/` |

## 3. 发现表

| # | 位置 | 问题类型 | 证据 | 严重度 | 建议处置 |
|---|---|---|---|---|---|
| S-1 | `tests/unit/test_responses_reasoning.py:39,94,128,135,142` | **测试与实现同源** | expected 的 `signature` 字段由 `encode_reasoning_carrier(...)` 算出，而被测的 `responses_reasoning_to_anthropic` 内部正是调它（`src/app/anthropic/thinking/responses_reasoning.py:78`）。该字段的断言退化为 `f(x)==f(x)`。**变异实验实证**：交换 v1 载荷 JSON 键序后（`/tmp/mutcheck`），该文件 **10/10 全绿**；变红的只有 `tests/unit/test_reasoning_carrier.py:20`、`tests/smoke/test_anthropic_responses_happy_path.py`、`test_anthropic_block_delivery.py`、`test_anthropic_responses_route.py`、`test_anthropic_responses_stream_route.py` 各 1 例 | major | 该文件至少 1 例把 signature 换成字面量（可复用 `test_anthropic_responses_happy_path.py:30` 已有的 `PROJECT_V1_OPAQUE_SIGNATURE` 常量）。**其余用例保持现状是合理的**——它们守的是「路由/基数/summary 拼接」，不是线格式，不要一刀切改 |
| L-1 | `tests/smoke/test_route_policy.py`（全 7 例）、`tests/smoke/test_anthropic_responses_happy_path.py`（全 6 例） | **错层**：smoke 里只做纯函数断言 | 两文件 import 面仅 `app.pipeline.route_policy` 等纯模块，无 `create_app`、无 I/O、无 socket。`test_route_policy.py:34` 起全是 `decide_protocol_leg(...)` 真值表 | major | 移入 `tests/unit/`。纯改位置，无语义变化 |
| L-2 | `tests/smoke/test_anthropic_block_delivery.py`（1152 行 / 27 例） | **错层**：smoke 里跑组件级并发管线 | 只 import `app.delivery` 与 `app.openai.responses_stream_parser`，无 app、无 HTTP；含 `test_concurrent_consume_serializes_block_and_terminal_writes:645` 这类单写者并发不变量 | major | 移入 `tests/component/`——那一层目前只有 2 个文件，正缺这类内容 |
| L-3 | `app.server.create_app` 被 13 文件实例化，横跨 `http/`(9)、`smoke/`(2)、`integration/`(1)、`unit/`(1) | **分层名不副实**：专职层没有独占职责 | `tests/unit/test_observability_phase6.py:47` 用 `TestClient(create_app(AppSettings()))` 打真 `/metrics`；`tests/smoke/test_anthropic_responses_route.py` / `..._stream_route.py` 是真 ASGI 路由测试 | major | 先定义每层的**一句话准入判据**并写进 `tests/README.md`（当前无任何此类文档），再据此归位。`test_observability_phase6.py` 的 `/metrics` 用例移入 `tests/http/` |
| L-4 | `tests/unit/test_socket_activation.py:169`、`tests/unit/test_systemd_notify.py:26`、`tests/unit/test_generation_control.py` | **错层**：unit 里跑真实 I/O | `subprocess.run` 起真 Python 进程并传 fd；`socket.socket(AF_UNIX, SOCK_DGRAM)` 真 bind；真文件 `unlink`×9 | minor | 移入 `tests/integration/`。这些测试**本身是对的**（真 fd 继承只能这么测），只是位置错 |
| D-1 | `tests/component/test_pipeline_executor.py:175` ↔ `tests/smoke/test_anthropic_responses_route.py:142` | **helper 重复**（AST 完全相同） | `RecordingHistory` 两处 AST hash 均 `19af0cfe`，各 19 行 | minor | 抽到共享 harness（见 F-1） |
| D-2 | `tests/smoke/test_anthropic_responses_route.py:164` ↔ `tests/smoke/test_anthropic_responses_stream_route.py:169` | **helper 重复**（AST 完全相同） | `RecordingApproval` 两处 AST hash 均 `9a3a13cb`，各 7 行 | minor | 同上 |
| D-3 | `tests/integration/test_rolling_control_process.py:41` ↔ `tests/integration/test_rolling_runtime_integration.py:30`；同两文件 `_request`（:28 ↔ :72，hash `65469ce5`） | **helper 重复**（AST 完全相同） | `_listener` 两处 hash 均 `d474645f` | minor | 同上 |
| D-4 | `_harness`（`test_anthropic_responses_route.py:253` 64 行 ↔ `..._stream_route.py:225` 65 行）、`RecordingTarget`（:33 106 行 ↔ :88 36 行）、`RecordingObserver`（3 份）、`_request_body`（:319 ↔ :292，各 18 行） | **helper 近重复**（同名异体） | 见 §5 扫描输出；`_request` 6 份、`_app` 6 份、`Target` 3 份、`StubClient` 3 份 | minor | 同名异体比完全重复更危险：读者会以为语义一致。抽共享件时必须**逐对确认差异是有意的**，不要机械合并 |
| D-5 | `tests/smoke/test_anthropic_responses_happy_path.py:195` `test_route_truth_table_fails_closed_for_unknown_capability` | **重复覆盖**：是 `tests/smoke/test_route_policy.py:92` `test_unknown_missing_and_conflicting_capabilities_fail_closed` 的**严格子集**（后者 3 个 parametrize 分支且断言 `error code`，前者只断一种） | 两者均调 `decide_protocol_leg(ResolvedModelFacts("unknown-model", []), transports=ALL_TRANSPORTS)` | minor | **它守的不变量**：路由能力未知时必须 fail-closed，不得猜模型名。依据在 `route_policy.py` 的 `RouteDecisionErrorCode`。**建议保留而非删除**——它在 happy_path 文件里承担「契约导览」职责。若确要合并，**需独立裁决，不可自行删除** |
| A-1 | `tests/smoke/test_imports.py:30` | **无鉴别力断言** | `assert import_module(module_name) is not None`——`import_module` 成功时永不返回 `None`，失败时抛异常。断言恒真，真正起作用的是 import 本身没抛 | nit | 改 `import_module(name)` 直接调用并去掉断言（意图更诚实），或加一条真判据（如 `__version__` 可读）。**注意它守的是「依赖装齐」**，别整个删掉 |
| P-1 | `tests/unit/test_rolling_runtime.py:632` | **真实墙钟等待** | `await __import__("asyncio").sleep(1.1)`，为证明 `drain_timeout=1` 的定时器**没有**触发。实测该用例 1.10s，同文件 `test_positive_drain_timeout_cancels_active_operation` 1.01s——两者合计约占全量 34.94s 的 6% | minor | 用「断言 timer handle 已被 cancel」替代等过期；或给 drain_timeout 开亚秒注入缝。**证否式等待无法用更短 sleep 修**，只能换判据 |
| P-2 | `tests/unit/test_rolling_runtime.py` 内 26 处 `__import__("asyncio")` | 可读性 / 一致性 | 该文件顶部 import 了 `signal`、`pytest`、`fastapi` 等，唯独 `asyncio` 全程用 `__import__` 内联（:625/:626/:629/:632/:667 等） | nit | 顶部 `import asyncio`。无功能影响，但会误导读者以为存在导入时序约束 |
| V-1 | `tests/verification/__pycache__/`（6 个 `.pyc`，42 个用例） | **未提交即消失的测试层** | `git log --all --pretty= --name-only \| grep -c "^tests/verification"` = **0**，即从未进入历史；`.pyc` 时间戳 Jul 17。反编译得模块：`test_spec_calibration_flow`(8)、`test_spec_deletions`(8)、`test_spec_hooks_system`(9)、`test_spec_prompt_limit_observation`(9)、`test_spec_stream_bytes_fidelity`(5)、`test_spec_tool_pair_idempotence`(3) | minor | 多数有同名后继（`test_hook_context_is_frozen` → `tests/unit/test_hooks_registry.py:78`；calibration → `test_tokenization_calibration.py`；prompt limit → `test_tokenization_limits.py`；usage tap → `test_anthropic_usage_tap.py`；tool pair → `test_anthropic_tool_pair_repair.py`）。**唯一无后继的是 `test_spec_deletions` 那一类**——「`auto_truncate` 不得复活」的物理缺席守卫（实测 `auto_truncate` 在 `src/` 与 `tests/` 各 0 命中，即删除本身仍成立，只是无人守）。**需独立裁决**：是补回缺席守卫，还是明确记录该不变量已退役 |

## 4. 无鉴别力断言清单

用 Python `ast` 全量扫描 93 文件（脚本 `/tmp/audit/asserts.py`、`/tmp/audit/asserts2.py`）。**结果是：这一轴基本干净，绝大多数初筛命中经复核都是误报。** 逐条交代，避免「没扫」和「无发现」混淆：

| 模式 | 初筛命中 | 复核后真发现 | 复核结论 |
|---|---|---|---|
| `assert` 被 `try/except` 吞掉 | 129 | **0** | 129 处全部位于 `try/finally`（清理），无 `except` 分支。用「仅统计带 `handlers` 的 `Try`」重扫 → 0 命中 |
| `assert` 在 `contextlib.suppress` 内 | 0 | 0 | 无 |
| 恒真谓词（`assert True` / `>= 0` / `> -1`） | 0 | 0 | 无 |
| 整个测试只有 `is not None` 断言 | 1 | **1** | 仅 `tests/smoke/test_imports.py:30`（见 A-1）。其余 `is not None` 均为 pyright strict 的类型收窄前置，后面跟真断言 |
| 无任何 `assert` 且无 `pytest.raises` | 3 | **0** | `tests/integration/test_server_startup.py:25`、`tests/unit/test_rolling_runtime.py:273`、`:478` 全部使用 `unittest.mock` 的 `assert_awaited_once_with` / `assert_called_once_with` / `assert_not_called` —— 是真断言，扫描器不认得 |
| `pytest.raises(Exception)` 无 `match=` | 0 | 0 | 无。44 处 `pytest.raises` 无 `match=` 的，异常类型均为项目自定义具体类型（`RouteDecisionError`、`DeliveryOrderError`、`StreamIdleTimeoutError` 等），有鉴别力 |

**反向证据**：全量 808 用例对 v1 载荷线格式变异有 5 例变红（§3 S-1），说明判据整体不是聋的。

## 5. 扫描范围与判据

全部脚本在 `/tmp/audit/`，可复跑。**未修改 `src/`、`tests/` 或任何既有文件；未执行任何 git 写操作。**

| 轴 | 扫描范围 | 判据 / 方法 | 结果 |
|---|---|---|---|
| 1 分层 | 93 文件全量 | AST 取 import 面 + 调用名，按「是否触真 I/O / 是否实例化 `create_app` / 是否只调纯函数」分类，**不看目录名** | 见 §2；发现第 5 层 `http/` |
| 2 重复 | 93 文件全量 | AST：模块级非 `test_` 定义按名分组，`ast.dump` 归一化后 hash 比对，区分「完全相同」与「同名异体」 | 22 组重名，3 组 AST 完全相同（D-1/2/3） |
| 2 重复（跨层行为） | 93 文件全量 | 按 `from app.X import Y` 建 symbol→files 倒排，筛 ≥3 文件且跨 ≥2 层 | `AppSettings` 26 文件 5 层、`create_app` 13 文件 4 层、`RequestContext` 9 文件 4 层 |
| 3 同源 | 93 文件全量 | ①AST 找同一测试内同时调 encode/decode 类反函数对；②AST 找 `assert` 两侧含 app 导入符号的 `Call`（113 命中，逐条人工复核区分「SUT 调用 vs 字面量」与「expected 由生产代码算出」）；③**变异实验**：`/tmp/mutcheck` 隔离副本改线格式，`PYTHONPATH` 覆盖后全量复跑 | S-1 一处确证；`test_reasoning_carrier.py:20`（字面量 base64）与 `test_wire_json_codec.py:32`（stdlib `json` 作独立 oracle）**判据设计正确，是正面样板** |
| 4 断言 | 93 文件全量 | 见 §4 表；两轮扫描（初筛 + 排除 `try/finally` 与 mock `assert_*` 的复核） | 真发现 1 处 |
| 6 fixture | 93 文件全量 | AST 找带 `fixture` 装饰器的定义；`find` 找 `conftest.py` | **0 fixture、0 conftest**。故「过宽 autouse 导致隐式耦合」**风险为零**——不是没扫，是结构上不存在 |
| 7 速度 | 全量实跑 | `uv run pytest tests -q --durations=35`，808 passed in **34.94s** | 最慢 3.50s（`test_systemd_units.py::test_short_graceful_timeout_...`，真子进程）。TOP-35 合计约 21s |
| 7 资源 | 93 文件全量 | AST 分类 `sleep` 实参；grep `systemctl` / `subprocess` / 外网域名 | 49 处 sleep：31 处 `sleep(0)`（仅让出事件循环，无成本）、18 处墙钟。18 处中 17 处 ≤0.05s；`test_streaming_sse.py:219` 的 `sleep(1)` 是**被 0.01s 超时取消的**，非真等待。**真实浪费仅 P-1 一处**。无真实 systemd manager（`FakeSystemctl`）、无外网（子进程只连本机 `ThreadingHTTPServer`）、无真 Copilot 凭据 |
| 结构 | `tests/` 全目录 | `find` 非 `test_*.py` 文件 | 0 个共享 helper 模块、0 个 `__init__.py`；basename 全局唯一（无 rootdir import 冲突）。另发现 `tests/verification/` 残留（V-1） |

## 6. 巨型测试文件的切分建议

前提：**这 6 个文件"大"的原因不同，不能用同一把刀切。** 关键测量是「首个测试之前的脚手架占比」：

| 文件 | 行数 | 用例 | helper 数 | 首个测试行号 | 脚手架占比 | 大的原因 |
|---|---|---|---|---|---|---|
| `tests/smoke/test_anthropic_responses_stream_route.py` | 1656 | 16 | 15 | 428 | **26%** | harness 复制 + 单例超长 |
| `tests/component/test_pipeline_executor.py` | 1453 | 24 | 25 | 546 | **38%** | harness 复制为主 |
| `tests/unit/test_responses_stream_parser.py` | 1288 | 39 | 2 | 43 | 3% | **纯用例密度**，非脚手架 |
| `tests/smoke/test_anthropic_block_delivery.py` | 1153 | 27 | 12 | 102 | 9% | 用例密度 |
| `tests/smoke/test_anthropic_responses_route.py` | 1088 | 13 | 9 | 346 | **32%** | harness 复制为主 |
| `tests/unit/test_anthropic_responses_request.py` | 1078 | 35 | 4 | 29 | 3% | 用例密度 |

### F-1（最高价值，一改解决三处）：抽共享 harness

`test_pipeline_executor.py`(546) + `test_anthropic_responses_route.py`(346) + `test_anthropic_responses_stream_route.py`(428) = **约 1320 行脚手架**，其中 `RecordingHistory` / `RecordingApproval` 已是逐字节相同（D-1、D-2）。

建议建 `tests/support/`（普通包，非 conftest——这些是**显式导入的构造器**，不是隐式注入的 fixture，显式 import 更利于 pyright strict 与可读性）：
- `tests/support/recording.py` — `RecordingHistory` / `RecordingApproval` / `RecordingObserver` / `RecordingTarget`
- `tests/support/harness.py` — `Harness` / `_harness` / `_request_body`
- `tests/support/streams.py` — `BytesStream` / `RawStream` / `ControlledResponsesStream`

**注意**：`RecordingObserver` 与 `RecordingTarget` 是**同名异体**（D-4），合并前必须逐对确认差异是有意的；stream 版 `RecordingHistory` 39 行 vs 另两处 19 行，多出的是流式专有钩子，**不能强行合并成一个**——用基类 + 流式子类。

### F-2：按维度切分（脚手架抽走后再做）

- `test_responses_stream_parser.py`（39 例，脚手架仅 3%，**本身不臃肿**）：若要切，按**协议对象**分 `_text.py` / `_function_call.py` / `_reasoning.py` / `_identity.py`（`:95–:208` 那 6 例 identity 校验自成一族）/ `_terminal.py`。优先级低。
- `test_anthropic_responses_request.py`（35 例）：已有天然聚类——`:314–:488` thinking/reasoning 能力协商（10 例）、`:827–:990` 工具名双射（7 例）、`:500–:661` 未知字段拒绝（5 例）。可切 3 个文件。
- `test_anthropic_block_delivery.py`（27 例）：`:102–:612` 交付顺序与 terminal、`:645–:744` 并发单写者、`:744–:1119` resident budget/lease。**三个子系统**，切 3 个文件最自然。
- `test_anthropic_responses_stream_route.py`（16 例）：`:428–:657` frontier/commit、`:967–:1236` 预算与断连、`:1321–:1636` terminal 语义与错误信封。
- `test_pipeline_executor.py`（24 例）：`:546–:631` 生命周期、`:631–:1069` success facts / calibration、`:1069–:1185` history provenance、`:1185–:1380` 重试预算。

**切分前置条件**：先补 §2 说的每层准入判据文档，否则切完还是不知道新文件该放哪一层。

## 7. 未覆盖面（本轮明确没做的）

- **未做覆盖率测量**：`pytest-cov` 在 dev 依赖里，但本轮未跑 `--cov`，故无法回答「哪些 `src/` 分支无人测」。这是「重复覆盖」的对偶面，建议单独一轮。
- **未逐用例做变异对照**：只对 v1 reasoning 载荷做了 1 次变异（为证 S-1）。其余 807 个用例的鉴别力**未经变异验证**——§4 的结论只说明「没有形态上恒真的断言」，不等于「判据覆盖面足够」。
- **未评估 parametrize 的有效性**：66 处 `@pytest.mark.parametrize`，未检查是否存在「多个分支实际走同一条代码路径」。
- **未读 `docs/agents/anthropic-responses-bridge/architecture.md` 与 `implementation.md`**（派活明令禁止锚定），故**无法判断测试是否覆盖了设计文档声称的契约**——本报告全部结论仅来自代码本身。
- **未评估根目录 `verification/`**（`final_acceptance/probes/*.py`、`phase3_acceptance.py`）：这是 `tests/` 之外的第二套验收载体，不被 pytest 收集。它与 `tests/` 的职责边界是否清晰，属本轴但本轮未展开。
- `out-of-axis`（按要求各记一行）：模块划分、重复实现、生命周期、类型化、第三方库选型、依赖环——均未评估。

## 8. 变异实验复现步骤（S-1 的证据）

```
cp -a src tests pyproject.toml uv.lock README.md /tmp/mutcheck/
# 在 /tmp/mutcheck/src/app/anthropic/thinking/reasoning_carrier.py 的 encode_reasoning_carrier 中交换 payload 两个键的顺序
PYTHONPATH=/tmp/mutcheck/src .venv/bin/python -m pytest /tmp/mutcheck/tests/unit/test_responses_reasoning.py -q   # 10 passed  <- 全绿，未察觉
PYTHONPATH=/tmp/mutcheck/src .venv/bin/python -m pytest /tmp/mutcheck/tests/unit/test_reasoning_carrier.py  -q   # 1 failed   <- 字面量锚点抓到
```

全量复跑 23 failed，其中 **18 个是环境性误报**（`/tmp` 副本未含 `contrib/`，systemd unit 渲染测试找不到模板；这 18 个在真实 HEAD 上全绿，见 §1 的 808 passed），**归因于本次变异的恰好 5 个**，已在 S-1 列名。
