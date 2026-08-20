# 合并态对抗性评审：请求日志与实时 footer

## 评审范围

评审对象是 `main` 的 `5395fdb feat: show what the proxy is doing — a request log and a live footer`，包括请求日志、`rich.Live` footer、终端能力探测、`ActiveRequestRegistry` 与两个 serve 入口的接线。未修改产品代码或测试；本报告是唯一新增文件。

## 已读取／执行的证据

- `git show --stat HEAD`：确认本次 squash 触及 `src/app/cli.py`、`src/app/server/pipeline_app.py`、全部 observability 模块及对应测试。
- 已逐段读取 `/home/xp/src/ghc-api-proxy-py/src/app/cli.py`、`src/app/server/pipeline_app.py`、`src/app/server/composition.py`、`src/app/observability/{active_requests,footer,terminal,tui,logging,request_log}.py`，以及本提交新增／修改的 HTTP、unit、PTY 测试与规格。
- `uv run pytest -q tests/unit/test_observability_footer.py tests/unit/test_observability_terminal.py tests/unit/test_request_log.py tests/http/test_pipeline_app.py tests/unit/test_cli.py`：`86 passed in 2.77s`。
- `uv run pytest -q tests/tui`：`6 passed in 9.07s`。
- 独立反例探针：并发 `snapshot()` 与 add/remove 得到 `RuntimeError('dictionary keys changed during iteration')`；`rich.Live.start()` 的 source 显示它启动 `_RefreshThread`，其 `run()` 在后台线程调用 `live.refresh()`。
- 独立宽度探针：单请求模型名为 `界 * 36`、`columns=80` 时，`build_footer` 返回 48 个 code point 但为 84 个终端 cell；按生产的 `Console(width=80).print(Text(..., no_wrap=True, overflow="crop"))` 实际输出在 `界... ` 后换行，再输出 `1.0s`。
- 独立流取消探针：对尚未首次 `anext()` 的 async generator 调用 `aclose()`，其 `finally` 不执行，registry 条目仍存在。已读取 Starlette 0.52.1 的 `StreamingResponse.__call__`／`stream_response` source；它先发送 response start，才首次迭代 body。

## 总体 verdict

**修复 major 后可进入下一阶段。** blocker 数量：**0**。存在 3 个 major、1 个 minor。最重要的问题是 `rich.Live` 的刷新线程与无锁 registry 同时访问同一个 `dict`，会在真实并发请求下让 footer 刷新线程崩溃。其次，宽字符会突破本提交承诺的“一物理行”硬不变量；流式响应在 body 尚未开始时若已断连，会泄漏登记并缺失完成日志。

## 逐条核验的命题

### 1．日志是否在可能产生日志前安装，并覆盖 `--fd`

**已确认，限于 `start` 的实际 serve 路径。** `/home/xp/src/ghc-api-proxy-py/src/app/cli.py:198-202` 先拒绝无效的 `--fd` 组合，随后在加载配置、建 HTTP client、建 chain、构造 app 和进入任一 server 前调用 `setup_logging()`。`--generate-config` 在 `:192-195` 早退且不 serve；无效参数也不进入服务，二者不构成反例。

普通路径从 `:257-289` 经 `_serve_pipeline()` 的 `:149-160` 到 `run_standalone(create_pipeline_app(...))`；后者在 `/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:85-93` 仍明确传 `log_config=None`。`--fd` 路径同样先经过 `:201-202`，再在 `:234-255` 调 `serve_inherited()`；后者在 `:128-145` 用同样的 `create_pipeline_app()`，并在 `:136-142` 传 `log_config=None`。因此 lifespan 的第一条日志 `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:286-306` 之前，root logging 已由 `/home/xp/src/ghc-api-proxy-py/src/app/observability/logging.py:77-132` 安装。

补充：`logging.py:83` 的“one detector for the whole process”文字不准确。它在 `:84` 自己调用一次 `detect_terminal()`，而 `Chain.capabilities` 又在 `/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:94-96` 默认调用一次。实际 footer 与 request log 的 `unicode` 确实共享 `Chain.capabilities`，但 logging setup 与它并不共享同一探测结果；当前 renderer 又在 `logging.py:70-74` 忽略 `colors`，所以这是误导性注释，不是本轮单列缺陷。

### 2．`_serve`／`_dispatch` 的完成日志是否恰好一条

**普通 return 路径已确认；流式在一个取消窗口内不成立，见 major 3。** `_dispatch` 的所有非流式 return 分别位于 `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:114,121,124,131,152-157,165-169,179-183,212`。它们均回到 `_serve()`，后者在 `:105-108` 对非 `StreamingResponse` 只调用一次 `_log_completion()`。这覆盖 404、JSON 400、非对象 400、`InboundRequestError` 400、count-tokens 成功／异常、`handle_bounded` 异常、无 response 与普通成功；注册后的非流式路径又由 `:213-214` 的 finally 释放。

流式唯一 return 在 `:191-208`。`_serve()` 特意不记录它，而 `_tracked_delivery()` 在 `:236-238` 的 finally 记录一次，因此已开始消费的成功、delivery 异常与已开始后取消均不会双打，且会产生一条完成日志。现有 `tests/http/test_pipeline_app.py:924-941` 只证明正常完成时一条，`844-859` 用 `TestClient` 验证已读出首块后的关闭；二者没有覆盖 body 从未开始迭代的窗口。

### 3．在飞请求 add/remove 是否配平，客户端中断如何处理

**非流式与已开始的流式分支配平；未开始消费的流式分支不配平，见 major 3。** 登记在 `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:133-143`，每个 count-tokens／bounded return 均受 `:144-214` 的 finally 覆盖。流式分支将 `released=True` 设于 `:190`，由 `_tracked_delivery()` 的 `:236-238` remove；一旦 async generator 已进入 `try`，客户端中断导致 cancellation 也会运行该 finally。

但 `StreamingResponse` 在外层先 return，真正第一次迭代在 Starlette 响应层之后。若断连或发送 response start 失败发生在首次 `anext()` 前，`_tracked_delivery` 的 finally 根本未进入；前述独立 probe 已证实 Python 对“未启动 async generator 的 aclose”不执行生成器体中的 finally。结果是 `context.id` 永远留在 registry，完成日志也完全缺失。应将流式 registration／completion 的责任放到能覆盖 `StreamingResponse.__call__` 全生命周期的 finally 中，或在 response 建立处使用明确的启动失败清理路径；并加入“response body 从未首迭代即断连／send start 失败”的 ASGI 级测试。

### 4．footer 的两轮预算和 `+K more` 尾巴

**ASCII 的尾巴预留未被证伪；“不超过一物理行”的最终断言被宽字符反例推翻。** `/home/xp/src/ghc-api-proxy-py/src/app/observability/footer.py:106-142` 在 pass one 依精确剩余组数预留尾巴，`_finalize()` 的 `:145-150` 对 Python 字符数作最终截断。穷举 2～30 个 ASCII 组、`columns=1..99`，包括 `+9 more` 到 `+10 more` 的数字位数边界，全部满足 `len(line) <= max(0, columns - 1)`；没有发现 `+K more` 预留算错令 ASCII 字符长度越界的反例。

但 `len()` 不是终端列宽。`_group()` 和 `_finalize()` 均按 code point 长度计量（`footer.py:115,150`），模型名只要求非空 string：`/home/xp/src/ghc-api-proxy-py/src/app/server/inbound.py:72-82`；配置的 `model_mappings` 也是无字符集约束的 `dict[str, str]`（`src/app/config/schema.py:267`）。`界 * 36` 在 80 列 terminal 的 footer 有 84 cell，且按 `FooterTui._render()` 实际构造的 `Text(..., no_wrap=True, overflow="crop")`（`src/app/observability/tui.py:104-107`）仍实测换行。故规格 `/home/xp/src/ghc-api-proxy-py/docs/agents/tui-request-log/SPEC.md:52-58` 与 footer docstring `footer.py:145-150` 的“`columns - 1` 显示列／永远一物理行”断言不成立。

### 5．终端能力探测是否误判常见环境

- `TERM` 虽设置但 stderr 被重定向：**正确**。`/home/xp/src/ghc-api-proxy-py/src/app/observability/terminal.py:64-70` 要求 `_is_tty(target)`，pipe／file 不会开 live；`tests/unit/test_observability_terminal.py:30-35` 覆盖该情形。
- 普通无 TTY 容器与 systemd：**正确**，同一 `isatty()` 门阻止控制序列。带 PTY 的容器被视为 interactive；这是当前“只从 stream 和 env 探测”的既定定义，代码无法判断是否有人实际观看 PTY，未定为缺陷。
- `NO_COLOR=""`：**误判，见 minor 4。** 实测 `detect_terminal(tty, {TERM: xterm, NO_COLOR: ""})` 返回 `color=False`；而 NO_COLOR 约定要求变量“存在且非空”才禁色，见 https://no-color.org/。

## 事实性发现

[major] `/home/xp/src/ghc-api-proxy-py/src/app/observability/active_requests.py:28-39`、`/home/xp/src/ghc-api-proxy-py/src/app/observability/tui.py:102-107` — 无锁 registry 的“所有变更都在 event loop thread”不足以保证安全，因为读者不是 event loop。`FooterTui` 以默认 `auto_refresh=True` 建造 `Live`（`tui.py:111-118`），Rich `Live.start()` 启动 `_RefreshThread`，该线程调用 `_render()` 再调用 `registry.snapshot()`；请求路径在 event-loop 线程执行 add/remove/set（`pipeline_app.py:133-143,170-171,234,237`）。独立双线程压力已实际复现 `RuntimeError('dictionary keys changed during iteration')`，来自 `snapshot()` 对 live `dict.items()` 的遍历。真实效果是刷新线程异常退出、footer 冻结，并可能在运行期间留下隐藏光标；请求服务本身继续但观察面失效。修复：以 `threading.Lock` 同时保护所有 registry mutation 与复制 snapshot，复制后再构造 `ActiveRequest`；或取消 Rich 背景刷新，改由同一事件循环显式刷新。补一条让渲染线程和 request mutation 同时运行的回归测试。

[major] `/home/xp/src/ghc-api-proxy-py/src/app/observability/footer.py:106-150`、`/home/xp/src/ghc-api-proxy-py/src/app/observability/tui.py:104-107` — 宽字符模型名突破“一物理行”硬不变量。反例 `model="界" * 36, columns=80`：`build_footer` 产生 48 code point、84 display cells；生产相同的 Rich `Console`／`Text` 接线实测在 `1.0s` 前换行。`no_wrap=True` 不能把 84 cells 塞进 79-cell 预算。修复：使用 Rich 已提供的 cell-width 工具或等价的 display-width 计算，按 cell 预算计量 segment、尾巴与最终截断；在 PTY 测试中加入宽 CJK／emoji 模型名并断言无第二行。`[?25l`／`[?25h` 的正常配对不是这里的根因，根因是实际 renderable 已超过一行。

[major] `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:190-208,217-238` — 流式请求把唯一的 remove 与完成日志交给 `_tracked_delivery`，但在 `StreamingResponse` 首次消费该 async generator 前没有兜底。独立 probe 已证明未启动 generator 的 finally 不运行；Starlette 0.52.1 source 也表明先发送 response-start，随后才 `async for body_iterator`。客户端在 response start 前后断连、或 send start 抛出时，可能完全不进 `:230-238`，而外层已在 `:190` 抑制 `_dispatch` finally 的 release。结果是 stale footer entry 与零条完成日志，违反“客户端中途断开仍清理／一请求一完成行”的注释和规格意图。修复建议同“命题 3”：将流式生命周期的清理提升到响应执行层的 finally，且对首次迭代前失败明确 release／记录；测试须模拟 `http.disconnect` 或 send response-start 抛出，而非只读取一块后关闭。

[minor] `/home/xp/src/ghc-api-proxy-py/src/app/observability/terminal.py:69-74` — `"NO_COLOR" in env` 将空值也当成禁色。独立 probe 输出 `{TERM: xterm, NO_COLOR: ""} => TerminalCapabilities(live=True, color=False, unicode=True)`；NO_COLOR 约定明确仅非空值禁色。修复为 `not env.get("NO_COLOR")` 的反向条件，补空值正向控制测试；这只影响颜色，不影响 footer。

## 主动核验的其它接缝

- `FooterTui.activate()` 的正常异常路径会恢复 handlers：`/home/xp/src/ghc-api-proxy-py/src/app/observability/tui.py:124-136` 在 `yield` 的 finally 恢复 previous handlers。正常 SIGINT／SIGTERM 也不构成隐藏光标缺陷：standalone 通过 `src/app/lifecycle/standalone.py:132-135` 进入 lifespan shutdown，Rich `Live.stop()` source 在 finally 调用 `console.show_cursor(True)`；`--fd` 的 `uvicorn.Server.serve()` source 也包在 `capture_signals()` 内。SIGKILL 不运行任何 finally，项目文档本来也把它定义为强制退出，不能要求配对恢复。
- 但上述 major 1 会在 Rich 的 refresh thread 内抛异常；Rich `_RefreshThread.run()` 不捕获该异常。因此它会使正常结束前的 footer 停刷，且隐藏光标只能等后续有序 shutdown 才恢复。这是 major 1 的直接后果，不另计一条。
- 未发现正常 LIFO 嵌套的 handler 恢复泄漏。`FooterTui.activate()` 不是为乱序手动 exit 设计的公共重入 API；没有产品调用点会形成那种顺序，故不把人为乱序嵌套列为缺陷。
- 未发现 `_dispatch` 的普通 return 路径重复写 completion line；`_serve` 的非流式单点与 `_tracked_delivery` 的流式单点互斥。未捕获的意外异常本来不会生成 JSON response，故不属于“return 路径”的一条完成日志证明范围。

## 结构怪味与处置

- `/home/xp/src/ghc-api-proxy-py/src/app/observability/active_requests.py:25-39` — 怪味类型：跨线程共享可变状态却按单事件循环假设设计。处置：本轮列为 major，需修复，不接受“只有 event loop 写者”作为同步理由。
- `/home/xp/src/ghc-api-proxy-py/src/app/observability/footer.py:106-150` — 怪味类型：把 Python 字符数当成终端显示宽度。处置：本轮列为 major，需改为 cell-width 度量。
- 成熟库评估：未发现应手搓而未用库的情形；`rich.Live` 已是现有依赖树的成熟实现。本轮问题是其线程模型未被接入代码正确同步，而不是应撤回该功能或改为自研 TUI。

## 结论与建议路由

先由 `gpt-souls:implementer` 修复上述三个明确的 major，并补针对线程竞争、宽字符、首迭代前断连的测试；之后请新的独立 reviewer 做一次合并态复评。若实现团队不确定 Starlette／Uvicorn 断连时序，应改由 `gpt-souls:debugger` 先以真实 ASGI harness 复现并确定负责清理的最低共同层。