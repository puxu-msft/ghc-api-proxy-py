# 合并态评审：`db14f0b` 与 `8c362a8`

## 评审范围

评审 `main` 上最近两个提交：`db14f0b fix: close the four holes an independent review found in the footer` 与 `8c362a8 feat: say more on the request line — mapping, bytes both ways, tokens, stop reason`，并读了其前四个提交的上下文。评审只新增本报告，未修改产品代码或测试。

## 已读取／执行的证据

- 执行了完整的 `git show db14f0b`、`git show 8c362a8`，以及 `git log --oneline -6`；`git diff --check db14f0b^..HEAD` 通过。
- 逐段读取了 `src/app/server/pipeline_app.py`、`src/app/observability/{active_requests,footer,terminal,tui,request_log}.py`、`src/app/pipeline/delivery/{assembler,stream}.py`、新增测试、`tests/tui/test_footer_screen.py`、`exp/tui-footer/pty_probe.py` 与 `docs/agents/tui-request-log/SPEC.md`。
- 执行 `uv run pytest -q tests/unit/test_observability_review_fixes.py tests/unit/test_observability_footer.py tests/unit/test_observability_terminal.py tests/unit/test_request_log.py tests/http/test_pipeline_app.py`：83 passed。
- 执行 `uv run pytest -q tests/tui`：6 passed。
- 执行 `uv run ruff check src tests` 与 `uv run pyright`：均通过，Pyright 为 0 errors／0 warnings／0 informations。
- 用真实安装的 Starlette 代码和 ASGI 探针验证 `Request.body()` 后 `Request.json()` 的缓存语义；分两段接收 `b'{"a":1'` 与 `b'}'`，总共仅调用 `receive()` 两次，得到原始字节 `b'{"a":1}'` 和 JSON `{'a': 1}`。
- 用实际 `_AccountedStreamingResponse`、`_tracked_delivery` 和 ASGI 2.4／2.0 探针验证正常、`http.response.start` 失败、第一段 body 发送失败的执行顺序；并用 PTY + pyte 以 40 列、30 条每条 180 个字符的真实 `FooterTui` 日志压力运行 12 次。
- 对照读取 `/home/xp/src/copilot-api-js/src/lib/observability/projections/format.ts:104-235`。

## 总体 verdict

**修复 major 后可进入下一阶段。** blocker 数量：**0**。发现 1 个 major、3 个 minor。

`db14f0b` 的四项既有发现均已实际核验成立：registry 的每个访问点均锁定；footer 全路径用 terminal cell 计宽；外层 response `finally` 在 body 未首次迭代、包括 response-start 发送失败时仍执行；`NO_COLOR=""` 不再禁色。`8c362a8` 的主要遗漏是 count-tokens 这个已成功路由、已拿到 token 数的 return 路径完全没有填充新 trace 字段。

## 逐条核验：上一轮四项修复

1. **跨线程 registry：已确认。** `/home/xp/src/ghc-api-proxy-py/src/app/observability/active_requests.py:38-76` 对 `snapshot`、add、remove、model、attempts、bytes 的 dict 读写全部以同一 `threading.Lock` 保护。新增并发测试与本轮路径审计一致；renderer 获得的是锁内构造的 immutable `ActiveRequest` 副本。
2. **宽字符 footer：已确认。** `/home/xp/src/ghc-api-proxy-py/src/app/observability/footer.py:112-135` 的全部预算项改用 `cell_len`，`_finalize` 使用 `set_cell_size`。CJK／emoji 的回归用例通过。边界实测：cell 长度恰等于 `columns - 1` 时原串直接返回，未被补空格；只有超宽才调用会 padding 的 `set_cell_size`。
3. **未开始流式 body 的 accounting：已确认，且双路径顺序无提前结算。** 实测正常 ASGI 2.4／2.0 路径依次为：`count(3)`、发送首块、`count(4)`、发送第二块、generator `finally`、首次 `finish(7)`、末尾空 body、外层 `finish(7)`；后一次是幂等 no-op。response-start 发送失败时 generator 根本未开始而外层仍 `finish(0)`，故不会泄漏 registry／完成行。第一段 body 的 `send` 失败时外层在 `count(3)` 后结算；不存在后续尚待累加的 chunk，但该计数的含义有下面的 minor 2 问题。
4. **`NO_COLOR=""`：已确认。** `/home/xp/src/ghc-api-proxy-py/src/app/observability/terminal.py:71-74` 使用 `not env.get("NO_COLOR")`，回归测试同时覆盖空与非空值。

## 事实性发现

[major] `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:158-170` — count-tokens 成功路径在已经完成 `handle_count_tokens()` 后，没有把 `context.requested_model`、`context.resolved_model` 或返回的 `input_tokens` 填入 `_Trace`。它们明明已经确定：`handle_count_tokens()` 在 `/home/xp/src/ghc-api-proxy-py/src/app/server/handler.py:116-124` 路由并写入 resolved model，随后在 `:159-163` 返回 token 数。实际请求 `model="alias"` 映射至 `claude-model` 后日志为 `200 POST /v1/messages/count_tokens 426ms ↑31B ↓35B`：只剩请求／响应字节，既不显示 `alias → claude-model`，也不显示 input token 计数。`RequestLine` 的 `:22` 所谓 model 为空即「routing never resolved one」在此路径也被事实反驳。修复：context 创建后即填 `trace.requested_model`；count 成功后填 `trace.model = context.resolved_model` 与 `trace.usage = {"input_tokens": counted["input_tokens"]}`，并决定是否保留 count endpoint 的 route 作为 subject；异常分支在路由已完成时也应保留已有 model。补映射 count 成功、count 失败、只含 input token 的回归测试。

[minor] `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:175-177, 260-273, 302-305` — post-routing 的 `handle_bounded()` 异常路径只填 `trace.model`，没有填已经存在的 `trace.requested_model`；且 `_tracked_delivery` 在 ASGI `send` 成功之前就把 chunk 计为 `sent`。实际将 handler 置于「路由已完成后抛错」的探针记录 `502 POST /v1/messages claude-model ...`，丢失已知的 `alias → claude-model`。第一段 `http.response.body` 的 `send` 抛错探针则记录 `count:3` 后立即由外层 `finish(3)`；ASGI 没有接受这段 body，日志仍会报 `↓3B`，与 `:116`「actually goes on the wire」的断言不符。修复：在 build_context 后立即保存 requested model，路由后尽早保存 resolved model；将 byte metric 的命名／注释收窄为「交给 ASGI 的字节」，或若必须声称已发送，则在能够确认 `send` 成功的边界计数。后者需要改变 wrapper 层的计数位置，不能仅移动当前的加法。

[minor] `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:123-128` — `_dispatch` 的 `route is None` return 发生在 `trace.bytes_in = len(await request.body())` 之前，故该 return 的 trace 必为空。更重要的是，公开 app 对未知 URL 根本不会进入 `_serve`：`build_router()` 只注册 `ROUTES` 中的精确 POST 路径，实测 `POST /does-not-exist` 得 FastAPI 的 404 且没有 request completion line。因此这不是已观察到的 body 误计，而是「每条 `_dispatch` return 都填 trace」与实际 public routing 的断裂。若该 defensive 404 应保留，先记录 body；若产品承诺所有 HTTP 404 也有请求日志，需在 router 之外的 middleware／exception 路径接线。当前测试只覆盖已注册 route 的 400，未覆盖这一区别。

[minor] `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:54, 76-79` — hit-rate 的分母语义本身正确，和 `copilot-api-js` 的 `formatCacheRate()` 一致：`input + cacheRead + cacheCreation`，并且零分母已防住。但本实现只呈现 `↻hit%`，上游在 cache creation 非零时还呈现 `+new%`，见 `/home/xp/src/copilot-api-js/src/lib/observability/projections/format.ts:207-234`。由于本行已经显示 cache-write token 绝对值，这不是错误的 hit rate；不过 `request_log.py:5` 将格式概括为跟随 upstream 时会使读者误以为 cache-rate 信息等价。推荐同步呈现 `+new%` 并加入 input／read／write 三者都非零的断言，或把文档收窄为只采纳其 hit-rate 公式。

## 主动核验的其它接缝

- `trace.bytes_in = len(await request.body())` 在 `request.json()` 之前的缓存语义成立。安装版本 Starlette 的 `json()` 本身也是 `body = await self.body()`；因此没有第二次 receive，也没有为流式请求体增加一次额外的全量读取。它仍与既有 JSON endpoint 一样必须把整个 body 聚合入内存，不能把此处的长度读取描述为支持逐块处理超大 JSON body。
- 正常非流式、已注册的 JSON 400、`InboundRequestError` 400 都正确记录 bytes in/out；本轮实际得到 malformed JSON 行 `400 POST /v1/messages 0ms ↑1B ↓46B: body is not valid JSON`，以及 unsupported stream 400 行 `↑45B ↓105B`。
- 流式 usage／stop reason 仅在 `assembler.terminal.seen` 后复制，正常流的 terminal event 可填充；response-start 失败保持空，符合不把 `end_turn` 默认值误称为真实终态的目标。
- `_finalize` 的 `cell_len <= limit` 边界正确，且探针确认 `set_cell_size` 在传入大于原 cell width 时会 padding；现有条件恰好避免了这一点。
- `soft_wrap=True` 未在实测中破坏 `rich.Live` 的行数记账：真实 `FooterTui` 通过 PTY + pyte 在 40 列下打印 30 条超长记录，连续 12 次均保留 `LOG-0001` 至 `LOG-0030`，无 footer 留在 scrollback。此结论只覆盖所测 Rich／pyte／Linux 组合，不能外推至所有终端实现。
- `_AccountedStreamingResponse` 的外层 finally 是所需的 unstarted-body 兜底，但已有测试没有模拟 response-start send 失败；本轮独立 ASGI probe 证明它有效。建议将该 probe 固化为回归测试，避免这一项重新退化为只覆盖「已读首块后关闭」。

## 结构怪味与处置

- `/home/xp/src/ghc-api-proxy-py/src/app/server/pipeline_app.py:158-187` — 怪味类型：trace 事实在不同 return 分支分散赋值，成功／异常／count 路径各弱一档。处置：本轮修复 major，按事实首次可知的公共基座填 trace，不要在各 return 临时补字段。
- `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:51-83` — 怪味类型：本地格式与 upstream formatCacheRate 的信息量不同但文档未标出边界。处置：本轮列为 minor，选择同步 `+new%` 或收窄文档声称。
- 成熟库评估：未发现应以第三方库替换当前实现的情况。Rich／Starlette 已承担终端 cell 度量、live renderer 与 ASGI response 的复杂机制；问题在接线与字段生命周期，而不是手搓替代品。

## 建议路由

先由 `gpt-souls:implementer` 修复 trace 的公共赋值时机、count-tokens token/model 填充及上述三项 minor；随后请新的独立 reviewer 复审最终合并态。若「已交给 ASGI」与「客户端实际收到」两种 bytes 定义需要产品裁决，再由 `gpt-souls:architect-advisor` 明确日志合同后实施。