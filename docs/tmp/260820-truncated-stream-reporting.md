# 上游流截断的上报：诊断、修复与遗留缺口

日期：2026-08-20
触发：用户贴出一条 TUI 请求日志并问「没有任何其他信息，这说明什么」。
状态：日志侧已修复并经独立评审处置完毕；下游侧的 Spec 不符合项**有意未修**，见「遗留缺口」。

## 触发现象

```
[ OK ] 09:00:11 H1/H2 200 anthropic-messages/claude-opus-5 385.0s ↑583.5KB ↓43.2KB
```

一次 385 秒、上游回了 43.2KB 的流式请求，整行只有协议、状态、模型、时长、字节数。缺 token 用量、缺 stop reason、缺 `think(...)`、缺 `retries=`。

## 诊断

`format_completion_line` 对每个字段都是「有内容才打印」，所以三项同缺只有一个来源：`_StreamAccounting.finish()` 里的 `if self.assembler.terminal.seen:` 没进去，`trace.absorb()` 从未被调用。

`Terminal.seen` 全仓库只在两处置 True：`AnthropicAssembler` 的 `message_stop`，`ResponsesAssembler` 的 `response.completed` / `response.incomplete`。都没来。

判据强度：**足以据以行动**，且已复现验证。探针 `RequestLine(bytes_in=597504, bytes_out=44237, duration_s=385.0, ...)` 逐字符渲染出用户贴的那一行，包括 `↑583.5KB ↓43.2KB` 两个数字。

唯一的替代解释是「非流式路径 + `terminal_from_anthropic` 读到的 body 既无 stop_reason 又无 usage」，但 anthropic-messages 入站 + 385 秒 + Claude Code 客户端，实际上排除。

### 三个互相独立的缺陷

1. **观测到的事实和没观测到的事实被一起丢掉。** `absorb` 是全有或全无。`Terminal.tools` 与 `Terminal.thinking` 是在每个 block 关闭时 `record()` 进去的，与终止事件无关，但同样被 `seen` 门挡住。
2. **前缀永远说 OK。** `pipeline_app.py` 写死 `status_for(status_code, failed=False)`，`failed=True` 分支在生产代码里不可达（只有单测调用过）。流式请求的状态码在响应头到达时就定死，此后无论流怎么结束都是 200。
3. **`Terminal.stop_reason` 默认 `"end_turn"`。** 「上游说了 end_turn」与「上游什么都没说」是同一个值。`terminal_from_anthropic` 早就发现了这个问题并显式传 `stop_reason=""`（见其 docstring），但流式路径没跟上。

### 更严重的、方向相反的一件事

`stream.py` 收尾处不看 `seen`，直接用 `terminal.stop_reason`（默认 `end_turn`）与 `terminal.usage or None`（空则 `{"output_tokens": 0}`）发 `message_delta` + `message_stop`。`synthesized_response_headers_after_sec` 默认 240 秒，385 > 240，`started` 必为真。

**客户端因此收到一个伪造的干净结束**，并把这个被截断的回答当作完整回答存进会话历史。

同一个事实上，两条交付路径撒了两种谎：对操作者是沉默（真话，但写成了没人读得出的缺席），对客户端是编造（假话，但说得斩钉截铁）。

## 已做的修复

| 文件 | 改动 |
|---|---|
| `pipeline/delivery/assembler.py` | `Terminal.stop_reason` 默认值 `"end_turn"` → `""`；给 `seen` 补注释说明它的含义 |
| `pipeline/delivery/stream.py` | 收尾改为显式 `terminal.stop_reason or "end_turn"`；注释标明 KNOWN SPEC VIOLATION、指向 legacy 参考实现，并记下唯一的字节差异（上游显式发空 `stop_reason` 时旧代码转发 `""`、新代码发 `end_turn`） |
| `server/pipeline_app.py` | `_Trace.status_override`（三态，取代布尔 `failed`）；`_StreamAccounting.drained` 与 `.failure`；`_tracked_delivery` 用 `aclosing` 包住它转发的生成器并分别记录三种结局；`finish()` 无条件 absorb，并按结局给出状态与说明 |
| `observability/request_log.py` | `status_for` 改为单值 `override`（`ok`/`fail`/`gone`）；新增 `LogStatus` 类型与 `format_pending_tools`；没有 stop reason 但有 tools 时渲染 `called(...)` |
| `observability/logging.py` | `STATUS_PREFIXES` 增 `"gone": "[GONE]"`，`PREFIX_COLOURS` 增 `"[GONE]": YELLOW` |

### 三种结局与它们的呈现

`finish()` 从 `finally` 里跑，所以三种结局走到同一处、`seen` 都是假。区分方式写在它们各自发生的地方，而不是在 `finish()` 里猜：

| 结局 | 怎么识别 | 前缀 | detail |
|---|---|---|---|
| 上游流自己跑完但没发终止事件 | `_tracked_delivery` 的 `async for` 正常结束 → `drained = True` | `[FAIL]` | `upstream stream ended without a terminal event` |
| 上游撕断（`ReadError`、reset、converter 抛异常） | `except Exception` 捕获 → `failure = error` | `[FAIL]` | `stream failed before a terminal event: <原文>` |
| 客户端走人（Esc、网络断） | GeneratorExit／CancelledError 从 `yield` 处展开，两个标记都没置上 | `[GONE]` | `delivery stopped before upstream finished` |

`except Exception` 而非 `BaseException` 是刻意的：GeneratorExit 与 CancelledError 正是「这一侧停止交付」，捕获它们会把三种结局重新揉成一种。

**`[GONE]` 是用户 2026-08-20 的裁决**。三选一：全红（Esc 频繁，会把真正的故障淹掉）／取消回到 `[ OK ]`（正是这次要消除的误导）／加第三档。选了第三档；`STATUS_PREFIXES` 里已有 `[RETRY]` 这个额外档位的先例，所以是既有机制而非新机制。

### 报告截断的门需要两个条件

```python
delivered_whole = self.drained and self.failure is None
if not (delivered_whole and terminal.stop_reason):
    self.trace.status_override, self.trace.detail = self._ending()
```

**两个条件缺一不可，这是 R2 抓到的 blocker。** 第一版只看 `terminal.stop_reason`，理由是 Anthropic 上游把结局拆成两半：`message_delta` 带 stop reason 与 usage，`message_stop` 只负责关闭；切在两者之间时客户端该拿的都拿到了。按 `seen` 判会渲染出自相矛盾的一行（`end_turn: upstream stream ended without a terminal event`）。

但「上游给了 reason」**不等于**「客户端拿到了 terminal frames」。`stream_delivery` 的收尾 flush 写在它的事件循环之后，撕断与断开都从 `yield` 展开、尾部根本不跑。于是「上游在 `message_delta` 之后撕断」这一种：assembler 记下了 `stop_reason`，客户端 `message_delta` 与 `message_stop` 一个都没收到，异常穿透到框架，而日志是绿色 `[ OK ] ... end_turn` 且无 detail——`failure` 明明记着却从没被读。这正是本次改动要消除的静默，被恢复在一条更窄的路径上。

`delivered_whole` 里额外的 `self.failure is None` 是评审建议之外的：`aclosing` 落地后 `chunks.aclose()` 若自身抛异常，会在 `drained = True` 已置上之后被捕获，只看 `drained` 会把「排空后清理失败」重新藏起来。

Responses 腿上 reason 与终止事件原子到达，这些区别不可见。

### 最终形态

```
[ OK ] 09:00:11 H1/H2 200 anthropic-messages/claude-opus-5 12.4s ↑583.5KB ↓43.2KB ↑12.0k+40.0k ↻77% ↓1.8k function_call(Bash,Read)
[FAIL] 09:02:33 H1/H2 200 anthropic-messages/claude-opus-5 385.0s ↑583.5KB ↓43.2KB called(Bash,Read) reason(enc:1,txt:2): upstream stream ended without a terminal event
[FAIL] 09:03:01 H1/H2 200 anthropic-messages/claude-opus-5 8.1s ↑583.5KB ↓12.0KB: stream failed before a terminal event: connection reset by peer
[GONE] 09:04:12 H1/H2 200 anthropic-messages/claude-opus-5 3.2s ↑583.5KB ↓4.1KB reason(txt:1): delivery stopped before upstream finished
```

## 测试与验证

新增：

- `tests/http/test_pipeline_app.py::test_a_stream_that_never_terminated_is_not_reported_as_a_clean_finish`
- `tests/http/test_pipeline_app.py::test_a_stream_that_did_terminate_is_still_reported_as_one`（控制样本）
- `tests/http/test_pipeline_app.py::test_an_upstream_that_tore_says_so_and_says_what_broke`
- `tests/http/test_pipeline_app.py::test_a_tear_after_the_stop_reason_is_still_a_tear`（R2 blocker 的回归）
- `tests/http/test_pipeline_app.py::test_a_stream_cut_after_its_stop_reason_is_not_called_truncated`
- `tests/http/test_pipeline_app.py::test_a_client_that_walked_away_is_not_blamed_on_upstream`
- `tests/unit/test_sse_assembly.py::test_a_stream_cut_off_before_its_ending_still_says_what_it_did_produce`
- `tests/unit/test_request_log.py::test_tools_without_a_stop_reason_are_still_named`
- `tests/unit/test_request_log.py::test_a_streaming_outcome_outranks_the_status_code_it_was_stuck_with`
- `tests/unit/test_stream_delivery.py::test_delivering_a_truncated_stream_does_not_make_its_record_look_finished`（长期不变式）
- `tests/unit/test_stream_delivery.py::test_a_truncated_stream_is_still_flushed_as_a_clean_ending_downstream`（钉住已知不符合项，**目的是被反转**）
- 辅助：`truncated_sse_upstream`、`sse_upstream_without_message_stop`（均由 `sse_upstream` 派生）、`_request_outcomes`、`_request_prefixes`

### 变异验证（五次，均已还原并逐字节比对）

1. `finish()` 的 `else` 分支改 `elif False` → 截断测试变红，捕获 stderr 打出 `[ OK ] ... ↑52B ↓429B`，与用户报告同形。
2. `accounting.failure = error` 改成不记录 → 撕断测试变红，打出 `delivery stopped before upstream finished`（评审 S1 描述的误报）。
3. 门改回 `not terminal.seen` → `cut_after_its_stop_reason` 测试变红，打出 `end_turn: upstream stream ended without a terminal event`（评审 S3 描述的自相矛盾）。
4. `STATUS_PREFIXES` 删掉 `"gone"` 键 → 前缀断言变红，打出 `['[....]']`。这一条尤其重要：`_add_status_prefix` 对不认识的 status **静默回落**到 `[....]`，只断言 status 字符串抓不到。
5. 门改回只看 `terminal.stop_reason` → `tear_after_the_stop_reason` 测试变红，打出 `200 POST /v1/messages 0ms ↓0B end_turn`（R2 blocker 描述的静默绿行）。

### 两次假绿，都被守卫断言挡住

1. 断开测试的第一版用 `TestClient` 流式读一个 chunk 后退出 `with` 块。`TestClient` 会把响应体读完，所以上游其实跑完了、日志是 `end_turn`，根本没触发断开。靠 `assert "end_turn" not in line` 才发现。
2. 改用「ASGI 边界让 `send` 抛 OSError」直接 `await app(scope, receive, send)` 会挂死，连 `asyncio.timeout` 都不生效，怀疑与没跑 lifespan 有关。放弃，改为直接驱动 `_tracked_delivery`（需 `# pyright: ignore[reportPrivateUsage]`，先例见 `tests/unit/test_model_provider.py:270`）。

全量：**1404 passed / 2 skipped / 1 deselected**。Ruff `check` 与 Pyright 干净（未跑 `ruff format`，项目禁用）。

被 deselect 的是 `tests/unit/test_lifecycle_pidfile.py::test_writing_leaves_no_temporary_behind`，**与本次改动无关**：并行会话在本次会话期间新落了四个未跟踪的 `tests/*/conftest.py`（`git status` 显示 `??`），其 autouse fixture 在 `tmp_path` 下建 `xdg-data` 目录，而那条测试断言 `tmp_path` 下只能有 `standalone.pid`。已实测 `app.lifecycle` 的导入闭包不含本次改过的任何模块。未去改它——那是同伴的在途切片，且有两种合理修法（pidfile 测试改用子目录，或 fixture 建到 `tmp_path` 之外），该由他们选。

## 独立评审处置

评审报告：`docs/tmp/260820-review-truncated-stream-reporting.md`（0 blocker / 5 should / 6 nit，verdict `needs-fix`）。

| 编号 | 结论 | 处置 |
|---|---|---|
| S1 上游异常撕断被误报为客户端走人 | **采纳**，属实且是我引入的缺陷 | 新增 `failure` 字段与 `except Exception` 分支；异常原文上线；补测试并变异验证 |
| S2 取消一律染红是把误报换了个方向 | **采纳**，交用户裁决 | 用户选择加第三档 `[GONE]`；`status_for` 由布尔改为三态单值 |
| S3 `message_delta` 后被切断时行自相矛盾 | **采纳** | 报告门由 `seen` 改为 `stop_reason`；补测试并变异验证 |
| S4 已知违反 Spec 未进 living doc，且是回归而非未开工 | **采纳** | 已写入 `implementation.md` 的「结构怪味登记」；`stream.py` 注释与钉住测试均改称回归并指向 legacy 实现 |
| S5 `context.reply` 仍 gate 在 `seen` 上 | **部分采纳** | 不改行为——`context.reply` 今天没有读者，「被截断的回复算不算一次 reply」要由第一个真实读者裁决，盲改无从验证。已就地注释并登记到「结构怪味登记」，接 History 时与 STR-04 一并处理 |
| N1 else 分支注释在断开这一支里是错的 | **采纳** | 已删除「client was handed a stop_reason」那句 |
| N2 `tools(...)` 与请求侧工具声明重名 | **采纳** | 改为 `called(...)` |
| N3 「下游字节完全一致」有例外 | **采纳** | 注释已写明该例外并说明为何 `end_turn` 优于转发 `""` |
| N4 引用的 Spec 句子出处不覆盖两条腿 | **采纳** | 注释改为分别引用下游 SSE envelope 合同与两条上游腿的条款 |
| N5 钉子把「长期不变」与「必须反转」混在一个函数 | **采纳** | 拆成两个测试函数，共享 `_truncated_delivery` helper；反转那条在 docstring 里写明「目的是被反转、不是被保留」 |
| N6 私有名导入 + pyright ignore 的位置违和 | **部分采纳** | 保留在 `tests/http/`，因为需要该文件的 `make_client` 与 `_chain_of`；已在 docstring 写明为何不搬走 |

评审同时独立复核确认：`Terminal` 默认值改动的波及面清点**无遗漏**；其余测试未发现恒真断言。

### R2 复评处置

R2 报告：`docs/tmp/260820-review-truncated-stream-reporting-r2.md`（1 blocker / 2 should / 3 nit）。

| 编号 | 结论 | 处置 |
|---|---|---|
| B1 新门太宽，把「上游在 `message_delta` 后撕断」放回静默成功 | **采纳**，属实且是我 S3 的过度修正 | 门改为 `not (delivered_whole and terminal.stop_reason)`，其中 `delivered_whole = drained and failure is None`（比评审建议多带 `failure is None`，见上文理由）；补 `test_a_tear_after_the_stop_reason_is_still_a_tear` 并变异验证 |
| S1 `_tracked_delivery` 没有 `aclose` 它包住的生成器 | **采纳** | 改用 `async with aclosing(chunks)`；`drained = True` 放在 `async with` 内部，使排空后 aclose 抛错仍被记为 `failure` |
| S2 我给 S5 的理由是反的 | **采纳更正**，行为不改 | 「不写 `context.reply` 是销毁信息而非推迟决定，`Terminal.seen` 就在记录上」；真正理由改为「保守：`reply is not None ⇒ 回复已完成` 是现有契约，且 STR-04 已点名需要 failed History，第一个读者不是假想的」 |
| N1 源码注释指向 `docs/tmp` | **采纳** | 源码内已无任何 `docs/tmp` 引用，两处均指向 `implementation.md` |
| N2 关停取消自己的在途流也记 `[GONE]`，但走掉的是我们 | **采纳** | `_ending()` docstring 补一段：措辞两边都成立，且此处分不出来，不假装分得出 |
| N3 「报告完全干净却仍不写 `context.reply`」是同一不一致的新形态 | **采纳** | 并入 `implementation.md` 同一条登记，明写两种分叉形态 |

R2 同时独立复核确认：`except Exception` 的边界在 py3.14.2 / anyio 4.14.2 实测**干净**（`CancelledError`、`GeneratorExit` 均非 `Exception`），四条路径归类全部正确；`status_for` 改单值后**无漏改**；`stop_reason` 空串／`null`／非法值／Responses 腿四种情形无额外假阴性。

### R3 复评：pass

R3 报告：`docs/tmp/260820-review-truncated-stream-reporting-r3.md`（0 blocker / 0 should / 2 nit，均为注释层面）。

B1 与 S1 均端到端实测闭合：撕断行变为 `[FAIL] ... end_turn: stream failed before a terminal event: connection reset by peer`，R2 那条绿行消失；`aclose()` 返回后上游确已释放（R2 时是 `UPSTREAM STILL OPEN`）。

| 编号 | 结论 | 处置 |
|---|---|---|
| N1 `failure is None` 的理由引用了当前不可达的场景 | **采纳** | 条件保留（评审确认它比其建议版本更正确，与 `_ending()` 判定顺序一致）；注释改写为「保持本门与 `_ending()` 同序，而非覆盖任何人造得出的状态」，并写明它需要循环里出现提前 `break` 才会变活，免得下一个人去为它造状态。**不补测试** |
| N2 `chunks.aclose()` 现在跑在 `finish()` 之前，记账及时性挂上了清理链 | **采纳** | `_tracked_delivery` docstring 记下这个新排序耦合，并说明为何不为解耦而重排——重排会把日志行放回释放之前，且下层已有自己的测试兜底 |

## 会话结束时的树状态

**1415 passed / 2 skipped / 0 failed**，Ruff `check` 与 Pyright 干净。

这个数字有一句必须附带的限定：**树在整个会话期间被并行会话高频改动**，全量结果多次变化，且不是每次都由本切片引起——

- 一次 1 failed（`test_lifecycle_pidfile.py`，同伴新落的未跟踪 `tests/*/conftest.py` 在 `tmp_path` 下建 `xdg-data`，与该测试的「只能有 standalone.pid」断言相撞）；
- 一次 2 failed（叠加 `test_count_tokens_refuses_a_model_that_advertises_other_endpoints`，同伴正在 `handler.py` 抽出 `shape_request`）；
- 评审方的树上同一时段是 17 failed（lifecycle／drain，`'StubAdapter' object has no attribute 'begin_draining'` 一类，同伴的新协议方法与测试替身不同步）；
- 一次 ruff 报 2 errors、数秒后同一命令又全通过。

以上都不由本切片引起（已实测 `app.lifecycle` 的导入闭包不含本次改过的任何模块），也都未由本会话修改——那是同伴的在途切片，改法该由他们选。**本切片自身可独立核验**：新增的 11 条测试全部通过，delta 文件 ruff 与 pyright 干净。

## 遗留缺口：STR-04 未在新链路实现

`docs/agents/anthropic-responses-bridge/spec.md`（FINALIZED）第 298 行：「没有合法 terminal event 的 EOF 是 truncation，不是成功。」第 289 行：「已提交后使用 Anthropic SSE error event，且不得再发 `message_stop` 冒充成功。」

`acceptance.md` STR-04：「成功只在合法 terminal 且全部 block drain 后产生 `message_delta`＋`message_stop`；其他路径产生确定 Anthropic error／连接终止和 failed History。」缺陷注入控制点名「在 clean EOF 上调用正常 flush」必须变红。

**legacy 链路已经正确实现了它。** `src/app/delivery/responses_anthropic_stream.py`：

```python
if not session.frontier.terminal_accepted:
    api_error = _upstream_error(
        "Responses stream ended before a successful terminal event",
        code="incomplete_responses_stream",
    )
    stream_state.error = api_error
    if session.frontier.message_start_accepted:
        await session.render_error(...)
```

所以在新链路补这一条是**移植而不是设计**。这是「守卫被留在了 legacy 链路上」在本仓的第三次击发，形态与前两次不同：前两次生产表现是上游 400（吵闹、必然被发现），这次是静默的假成功。

### 为什么本次不修

- 它改变客户端可见的字节，属于对外契约变更；落地需要配套的 failed History 与 STR-04 的缺陷注入控制，与本次「修日志行」的范围不成比例。
- 现状已在代码注释、钉住测试、`implementation.md` 结构怪味登记与本文档四处标注，不会静默消失。

### 下一棒要注意

`test_a_truncated_stream_is_still_flushed_as_a_clean_ending_downstream` **钉住的是当前的不符合行为**，实现 STR-04 时它应当被改写，而不是被当成回归。它存在的理由是防止有人顺手删掉 `or "end_turn"` 从而下发 `stop_reason: ""`——那比现状和 Spec 要求的形态都更糟。同文件的 `test_delivering_a_truncated_stream_does_not_make_its_record_look_finished` 则是长期不变式，落地 STR-04 后仍须为真。

## 未提交

会话结束时这些改动**未提交**。工作树里同时有并行会话的在途改动，其中 `src/app/pipeline/delivery/stream.py` 与 `tests/unit/test_stream_delivery.py` 与本次改动重叠，任何提交都会带上同伴未完成的工作。其余文件（`assembler.py`、`pipeline_app.py`、`request_log.py`、`logging.py` 及三个测试文件）为本次独占。
