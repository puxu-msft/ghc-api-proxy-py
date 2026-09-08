# httpx2 migration：步骤 4 残余审计

审计日期：2026-09-08。

## 评审范围

- 判据：`plan.md` 的步骤 4 要求逐条复核迁移时保留的散文与注释，且不得以命中数取代语义审计。
- 被检对象：主工作树 `src/`（排除 `src/.archived/`）中仍含完整单词 `httpx` 或 `httpcore` 的文本；`pyproject.toml` 的迁移文档指针；本主题已有计划与盘点报告。
- 明确不在范围内：源码或测试的修复、`src/.archived/`、其他 `.dev/docs` 主题，以及把历史迁移测试数字当作本次主线验证。

## 总体结论

**VERDICT：needs-fix；blocker：0。** 步骤 4 不能闭合，主题必须继续作为 living 记录。这里的结论是实测的 `confirmed`：活动源码已没有旧包 import，但仍有 46 个 `httpx` 与 29 个 `httpcore` 完整词命中；其中不止历史记录和真实 logger 名，存在把当前 `httpx2`／`httpcore2` 行为仍写作旧包的 live prose，另有一处旧 logger 名配置仍在影响运行时筛噪。

### F1：活动栈的 package label 仍有未处置项（major，confirmed）

- `uv run python` 实测当前解释器加载 `httpx2 2.12.0` 与 `httpcore2 2.12.0`，其类模块分别为 `httpx2`、`httpcore2`。
- `rg` 实测活动 `src/` 没有 `import httpx`／`import httpcore`，有 30 条 `httpx2`／`httpcore2` import；因此下列使用旧包名描述当前 transport、response、exception 或 pool 的文字不是历史名称的保留，而是待源代码所有者逐项更正的 live prose。
- 需要处置的精确位置、历史事实保留边界与 logger 项将在本报告后续审计条目及 `plan.md` 的 deferred 中登记；不得机械地全局替换。

### F2：旧 logger 名已不能代表当前库（major，confirmed）

- `uv run python` 读取已安装包源码：`httpx2._client` 建立 `logging.getLogger("httpx2")`；`httpcore2` 的 HTTP/1.1、HTTP/2、proxy、connection 与 SOCKS 模块均建立 `httpcore2.*` logger。
- `src/app/observability/logging.py:199` 仍只将 `"httpx"` 与 `"httpcore"` 提升到 `WARNING`。这不是仅供叙述的旧名称：当前库的 INFO 日志不会走该设置；同文件 `:34`、`:198`、`:216` 对库 logger 的说明也随之过时。
- 本任务没有源码所有权，故只登记 deferred，未修改该行为。

## 逐处审计账

| 结果 | 位置 | 结论与处置 |
|---|---|---|
| 待修正（当前 transport／pool 名称） | `config/schema.py:272,278,280`；`server/composition.py:111,115,159,161,180,184,191,217,230,232,270,283,293,295,311,323,327`；`upstream/stream_cap.py:7,11,20,44,59,103,105,117,124,128,130` | 当前活动 transport/pool 已是 `httpx2`/`httpcore2`；逐句改 live package label。`schema.py:272,278` 与 `stream_cap.py:20,105` 含旧栈历史，须保留时间限定的 `httpx`/`httpcore`。 |
| 待修正（当前 request／response／异常名称） | `model_provider/codebuddy_client/errors.py:42`；`model_provider/ghc_client/client.py:21`；`model_provider/upstream_errors.py:37,44,46,126,139`；`observability/rejection_capture.py:9`；`pipeline/delivery/stream.py:534`；`pipeline/hand_over.py:152,268`；`server/routes/inference.py:805,812,1738`；`observability/request_trace.py:57,99` | 这些文字描述当前请求、响应、异常映射或 pool；按每句的时间范围改为 `httpx2`/`httpcore2`，或显式保留已标版本的历史事实。 |
| 待修正（logger prose 与运行时配置） | `observability/logging.py:34,198,199,216`；`observability/request_trace.py:29` | 旧名既是过时说明，也是 `logging.py:199` 未对当前 `httpx2`/`httpcore2` logger 生效的配置。源代码所有者须修改并验证 INFO 筛噪仍有效。 |
| 已验证可保留 | `streaming/idle_timeout.py:26` | 明确区分 `httpx 0.28.1` 的已标日期观察与 `httpx2` 的当前行为；无改动。 |

这张账覆盖活动源码中全部 53 个含旧包完整词的位置（共 75 次出现）。它不是机械替换指令：同一行中的历史包名和当前包名可能分别正确与错误，必须按句子所述时间和对象处理。

## pyproject.toml 指针

`pyproject.toml:16` 的唯一指针是 `.dev/docs/httpx2-migration/plan.md`；本次实测该文件存在，且该 plan 是本主题仍处于 living 状态时的权威 deferred 载体。因此没有改动 `pyproject.toml`：步骤 4 未闭合，不能把它改指向一份声称完成的报告；现有指针已经指向正确、仍存在的位置。

## 验证边界与后续处置

- 本次验证只确认当前解释器的包身份、可导入性、logger 名称和活动源码文本；没有运行全量测试，也没有把历史测试数视作当前基线。
- 计划中 `1567 passed / 2 skipped` 等数字仍仅是 2026-08-21 迁移时快照。当前主线验证必须按项目根 `CLAUDE.md` 的当前命令独立运行和记录，不能由本报告或 plan 的历史数字替代。
- 后续由相应源码所有者处理 `plan.md` 的三个 deferred 后，重新跑同一文本盘点、验证 `httpx2`/`httpcore2` logger 筛噪行为，并逐项确认历史叙述未被篡改；届时才可重审步骤 4 是否关闭。
