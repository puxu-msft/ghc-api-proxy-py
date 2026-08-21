# Current main stream route 定向复核

- **评审范围**：只读复核 `/home/xp/src/ghc-api-proxy-py` 当前 `main` 的 stream-route squash 合并态；用户给出的短 SHA `ae84aa9` 已解析为完整 SHA `ae84aa9d4330e56b83aefdad977e7d93190ff0d4`，并与评审时 `main` HEAD 做同调用 gate。范围仅覆盖刚回并的 Responses→Anthropic stream route 与 capability＋History 语义合成：关键路径、R3 三项修复机制、真实 `HistoryConsumer` 接口、single lifecycle，以及主线测试结果身份。未执行完整 Acceptance，未建立新矩阵。
- **总体 verdict**：**可进入下一阶段。当前 main stream slice 可继续。** 在本轮定向范围内未发现 blocker 或 major。
- **blocker 数**：**0**。
- **major 数**：**0**。
- **双视角覆盖证据——机械核对**：每个承载结论的 shell 调用均在同一调用内打印并校验物理 cwd、Git top-level、branch 与完整 HEAD。读取当前最终代码而非只看 diff；对账 `client → executor → route → parser/delivery → History`，复核 R3 三项生产／fixture 修复和真实 `HistoryConsumer` 测试。`git diff-tree --check ae84aa9^ ae84aa9` 退出码为 0。当前 main tree object `a016ff3e22ffc6f747ed7d3643958615d0c4606f` 与已审 integration tip `b5d5d0ce9dff4a1c28aac4371b3fdc71e806bba0` 的 tree object 完全相同；两者相对 base `38bb06ff0eefef69fd4fdab830e67ff549563a20` 的 stable patch id 同为 `d18e55e2e21d41ba9152baf5dca4969567af7eb6`。
- **双视角覆盖证据——第一人称执行**：模拟 resolved-model capability 在每次 attempt 的 `PRE_SEND` 后重新参与 request conversion；模拟 non-stream success facts 留在 executor lifecycle；模拟 stream success 由 executor 仅交接到 `STREAMING`，route 再依据真实 delivery frontier 终结；模拟 postcommit protocol failure 只输出 Anthropic error SSE 并保存 partial History；模拟 prefetch disconnect 后再次取消仍等待 observer finalize、History finalize 与 upstream close；模拟空 delta 与非空 authoritative done 冲突，以及 done-only／多层等值的合法正样本；模拟真实 `HistoryConsumer` 的 completed stream projection、failed uncertain projection与 failed non-stream 零成功事实。

## 定向复核结果

### 关键路径与 capability＋History 合成

- `src/app/anthropic/client.py:80-83,184-275,306-345` 同时保留 `AnthropicAttemptResult` 的 response／request conversion facts／converted response，以及基于 `prepared.resolved_model` 的 `ReasoningCapabilityFacts` 输入；stream success 返回未消费 upstream 和该 attempt 的 request facts，未被 capability 合并覆盖。
- `src/app/pipeline/executor.py:260-282,330-415` 在每次 `PRE_SEND` 后重建当前 prepared request并调用 `send_prepared_attempt()`；non-stream 在最终 client-visible body 校验后写 facts并发布 success lifecycle，stream 只 transition 到 `RequestState.STREAMING`，不在 executor 提前发布 stream `RESPONSE`／`FINALIZE` 或 finalize History。
- `src/app/routes/anthropic.py:34-121,214-260` 的 stream owner 使用 delivery state 决定 completed／failed，随后按 observer→History 顺序终结，并由 delayed ASGI response 的真实 start／body outcome推进 headers／body uncertainty；upstream close 统一交给 `passthrough_bytes(..., cleanup=upstream.aclose)`。
- `src/app/history/consumer.py:26-46` 的真实 `HistoryConsumer.finalized()` 接受 keyword-only `response`、`usage`、`usage_estimated`。显式 stream projection 优先；未提供 projection且 completed 时保留 non-stream final response／typed usage fallback；failed non-stream 不写成功 response／usage。

### R3 三项修复机制

1. **抗二次取消的 cleanup ownership**：`src/app/streaming/sse.py:95-113,189-203` 把 pending pull task与 body iterator交给统一 cleanup；`src/app/streaming/keepalive.py:69-115` 以独立 cleanup task加重复 `asyncio.shield()` 完成收尾并延后外层 cancellation。`tests/smoke/test_anthropic_responses_stream_route.py:1055-1096` 在 observer、History、upstream close 三个 checkpoint 间再次取消 owner，并断言三者均完成且 `FINALIZE`／History 各一次。
2. **空 delta 不能绕过 authoritative 一致性**：`src/app/openai/responses_stream_parser.py:340-399,713-729` 在 output-text done、content-part done和item done三个 authoritative 接点都按 `draft.deltas` 是否存在判定，因此观察到的空 delta仍会与后续非空 authoritative 值冲突。`tests/unit/test_responses_stream_parser.py:718-783` 同时覆盖两个失败终点与 done-only 合法正样本。
3. **fixture 确实抵达目标 guard并保留 false-red 控制**：`tests/smoke/test_anthropic_responses_stream_route.py:1378-1402` 的 empty-message created id与 terminal fixture一致，实际抵达 `empty_response_content`；`tests/unit/test_responses_stream_parser.py:683-715` 的 reverse-order 三层 authoritative 等值样本只完成一次 item并断言零重复 block。两者均在本轮最小 suite 中通过。

### 真实 HistoryConsumer 与 single lifecycle

- 真实接口不是由宽签名 fake 代替：`tests/component/test_history_store.py:167-221` 使用真实 `HistoryStore`＋`HistoryConsumer` 参数化验证 completed stream projection和 failed／uncertain projection；`tests/component/test_history_store.py:225-255` 验证 failed non-stream 即使 context 曾持有 final payload，也不持久化成功 response／usage。
- single lifecycle 的边界清楚：executor 负责 attempt、retry 与 non-stream terminal；stream 成功只交接到 `STREAMING`，route 的 `_history_stream()` 才依据 delivery frontier transition 到 `COMPLETED` 或 `FAILED` 并调用一次 observer／History finalize。prefetch recancellation 与 happy／postcommit tests未见第二个隐式 terminal owner。

## 主线测试结果身份

- 执行对象：`main@ae84aa9d4330e56b83aefdad977e7d93190ff0d4`，tree `a016ff3e22ffc6f747ed7d3643958615d0c4606f`。
- 运行前导入路径探针确认 `app`、`app.routes.anthropic`、`app.history.consumer`、`app.openai.responses_stream_parser` 均从 `/home/xp/src/ghc-api-proxy-py/src/app/` 加载。
- 最小 selectors只覆盖本报告依赖的 capability 重转换、executor stream handoff、non-stream facts、真实 History projection、stream happy、postcommit failure、prefetch recancellation、R3 empty-message／tool-args fixture、空 delta冲突、done-only正样本与reverse-order等值正样本。
- 同一 selector 集的 `pytest --collect-only` 得到 `15 tests collected`；实际运行得到 `15 passed in 2.51s`，退出码为 0。数量已由 collection与execution两种路径交叉核对，口径固定为上述 selector 集、当前完整 HEAD。
- 测试前后 `git status --porcelain=v1 -z` 的 SHA-256 均为 `3d6529f46e85c41e2e7646af334d6af122a2a52654105a55dedccd6bb535aeb1`；本轮未改代码、测试、Git refs、index、服务或进程。该哈希包含评审前已存在的未跟踪材料，因此不声称工作树 clean，只证明本轮最小测试未改变状态。

## 事实性发现

未发现问题。当前 main 的 stream route、capability facts、attempt facts、真实 History projection与 single lifecycle 在本轮定向范围内一致；R3 三项修复机制及其正反样本未见回归。

## 主观建议

无。本轮没有把范围外项目改写为当前实现缺陷。

## 结构扫描与方法反思

- 结构怪味扫描范围：`src/app/anthropic/client.py`、`src/app/pipeline/executor.py`、`src/app/routes/anthropic.py`、`src/app/history/consumer.py`、`src/app/delivery/responses_anthropic_stream.py`、`src/app/streaming/{sse,keepalive}.py` 与对应最小 tests。判据为重复 lifecycle owner、fake／real contract漂移、capability／attempt facts互相覆盖、成功事实提前发布、cleanup ownership分叉和History projection双来源冲突。**未发现新的结构怪味**，故无 `file:line` backlog项。
- 更好的内部替代方案：本轮未发现比“executor交接 stream、route按真实 delivery outcome终结、consumer统一持久化”更一致的现有项目内路径。
- 判据判别力：同时运行失败样本与合法正样本；真实 consumer test关闭 fake宽签名假绿，done-only／reverse-order正样本防止 authoritative guard过严。未执行新的mutation，因为用户明确要求定向复核且既有R3正控已冻结，本轮以主线身份与接缝回归为目标。
- 成熟第三方方案：本轮是项目内部协议状态、ASGI delivery frontier与History语义合成，未发现可直接替代这些领域契约的成熟库；继续使用 `httpx`、Starlette/FastAPI、AnyIO与pytest的既有能力，没有新增自研通用基础设施。

## 未验证边界

**完整 retry、quota／resident backpressure，以及真实 socket partial-write 仍为 `UNVERIFIED`。** 本轮没有执行完整 Acceptance，也没有扩张到这些矩阵；它们不升级为本轮 blocker或major，同时不得从本报告的绿灯外推出已经通过。

## 结论

`main@ae84aa9d4330e56b83aefdad977e7d93190ff0d4` 的当前 stream slice 为 **0 blocker／0 major，可继续进入下一阶段**。该结论仅覆盖本报告列出的 stream-route 与 capability＋History 合成定向范围；完整 retry、quota／resident backpressure、真实 socket partial-write继续保持 `UNVERIFIED`。
