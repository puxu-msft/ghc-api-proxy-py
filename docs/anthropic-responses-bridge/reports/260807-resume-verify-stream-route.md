# Responses stream route happy slice 独立验收报告

## 判定

**PASS。** 候选 `/home/xp/src/ghc-api-proxy-py-stream-route` 的 `HEAD` `2087f8f02516136314985f5c48bdee20b2f4b861` 在 base `b91e58a29324b11840002efc53ed6f869b800c39` 之上，满足本轮限定的 Responses SSE text happy slice。该结论只覆盖本报告矩阵，不代表完整 Anthropic Messages ↔ OpenAI Responses bridge Acceptance 通过。

没有发现本切片内的实证缺陷。未覆盖项保持 `UNVERIFIED`，不折算为失败，也不从本轮结果外推。

## 输入与范围

行为 oracle 为目标 worktree 的 `docs/agents/anthropic-responses-bridge/acceptance.md`，执行时 SHA-256 为 `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`。切片边界输入为主树只读文件 `docs/tmp/260807-backup-port-smoke-resume.md`，执行时 SHA-256 为 `c723cfbf42a6d401da98d3b9f138752fc6fef695496167203782733c74a876ba`。两项 hash 均由 `sha256sum` 与 Python `hashlib.sha256` 两种不同实现交叉得到一致结果。

本轮从 Acceptance 的 STR-01、STR-02、STR-04、STR-05、TR-HTTP、LIFE-01、LIFE-02、LIFE-03 与 REL-05，以及 resume 的 STREAM-MERGE-01～09 中独立推导 text happy slice。按用户约束，没有扩张到 retry、quota、backpressure、sink partial-write 或 delivery-uncertain 全矩阵。

## 执行与来源证明

所有可承载结论的 shell 调用都在同一调用中打印并校验物理 cwd、Git top-level 与完整 `HEAD`。可信执行均显示：

- cwd 与 Git top-level 均为 `/home/xp/src/ghc-api-proxy-py-stream-route`。
- `HEAD` 为 `2087f8f02516136314985f5c48bdee20b2f4b861`。
- `git merge-base --is-ancestor b91e58a29324b11840002efc53ed6f869b800c39 HEAD` 退出码为 `0`。
- 最终 `git status --porcelain=v1` 在 `A20_STATUS_BEGIN` 与 `A20_STATUS_END` 之间无输出，目标 worktree 在验收后仍干净。

模块来源探针 `A13` 从执行测试的同一 Python 环境打印并断言以下路径均位于目标 worktree：

- `/home/xp/src/ghc-api-proxy-py-stream-route/src/app/__init__.py`。
- `/home/xp/src/ghc-api-proxy-py-stream-route/src/app/routes/anthropic.py`。
- `/home/xp/src/ghc-api-proxy-py-stream-route/src/app/delivery/responses_anthropic_stream.py`。

早期若干共享终端返回了其他 worktree 或其他会话的输出，因缺少本次 nonce、目标路径或目标完整 SHA 而全部作废，没有进入本报告证据。后续使用本会话专用 shell，并对每条 load-bearing 命令继续重述同调用 gate。

## 验收矩阵

| 验收项 | 独立 oracle | 实际证据 | 结果 |
|---|---|---|---|
| 真实 ASGI 与 fake Responses SSE text happy | 从真实 `/v1/messages` ASGI 入口发 Anthropic 请求，Responses-only fake 接收 `stream=true`，下游获得合法 Anthropic SSE | 候选 route 测试 `A14` 退出码 `0`；独立原始 ASGI probe `A17` 退出码 `0` | PASS |
| 上游调用恰一次 | 一个 Anthropic 请求只能产生一个 Responses exchange，且 context attempt 与真实调用一致 | `A17` 断言 captured Responses payload 只有一个，context attempts 只有一个；候选 route happy 同时断言相同事实 | PASS |
| Anthropic SSE 不泄漏 Responses | 所有 SSE event 名与 JSON `type` 一致，且不得出现 `response.*` event 或 JSON type | `A17` 逐 frame 独立解析，观测到的序列仅为 `message_start`、完整 text block envelope、`message_delta`、`message_stop`；显式断言 wire 不含 Responses event/type | PASS |
| authoritative done 前下游不可见 | `response.output_text.done` 与 `response.output_item.done` 前均不得提交 success headers 或 body；text authoritative done 本身未闭合 source 时也不得释放 | `A17` 在 delta 后与 `response.output_text.done` 后分别断言 ASGI send 列表为空，仅 `response.output_item.done` 后出现首批 | PASS |
| 首完整 block batch | 首次 body 提交必须把 `message_start → content_block_start → text_delta → content_block_stop` 放在同一 batch | `A17` 对首个 `http.response.body` 单独解析并精确比较四个 event；候选 route happy 另以 reasoning block 验证同类首批 | PASS |
| terminal 与 usage | 成功 terminal 恰好一个 `message_delta → message_stop`；usage 使用冻结净 input 算式 | `A17` 精确比较完整事件序列，`message_delta` 与 `message_stop` 各唯一；fake 的 upstream input `12`、cache read `3`、cache write `2`、output `7` 被归一为 Anthropic input `7`、output `7`、cache creation `2`、cache read `3` | PASS |
| `response.failed` | commit 前产生 Anthropic JSON error，不得出现 Responses wire 或 success terminal；资源与 lifecycle 失败收敛 | `A15` 观测 HTTP `502`、code `server_error`、单 upstream、单 finalize、FAILED、upstream closed，且 body 无 `response.*` 与 `message_stop` | PASS |
| Responses `error` | 与 failed 同样不能伪装成功 | `A15` 观测 HTTP `502`、code `overloaded`、单 upstream、单 finalize、FAILED、upstream closed，且无 success terminal | PASS |
| clean EOF | 无合法 terminal 的 EOF 必须失败，不得正常 flush | `A15` 观测 HTTP `502`、code `incomplete_responses_stream`、单 upstream、单 finalize、FAILED、upstream closed，且无 success terminal | PASS |
| 单 RequestContext、approval、hooks、FINALIZE | route、attempt、History、approval 与 hooks 必须共享同一 context；成功与失败各只 finalize 一次 | `A17` 成功路径断言 History started/finalized 为同一 context、approval 收到同一对象、attempt 唯一、hook 序列为 `request_received → response → finalize`；`A15` 失败路径为 `request_received → error → finalize` | PASS |
| 客户端取消基本 cleanup | 首 block 前取消不得泄漏字节或 retry；upstream 关闭，History 失败，FINALIZE 唯一 | `A16` 取消真实 ASGI task后观测 `CancelledError` 传播、零 ASGI response message、单 upstream、upstream closed、FAILED、`context.error.status_code=499`、单 finalize | PASS |
| 目标正控 | 若 route 在 authoritative done 前泄漏任意 body，同一时序 oracle 必须抓红且失败原因来自目标不变量 | `A18` 仅在独立 Python 进程内 monkeypatch renderer，使其读取首个 Responses chunk 后立即输出 `LEAK-BEFORE-DONE`；同一 pre-done 观察明确捕获该 body，进程退出后变异自动消失，未写生产文件 | PASS |

## 实际运行记录

### 候选自带 route gate

在目标 SHA gate 下执行 `tests/smoke/test_anthropic_responses_stream_route.py`，禁用 pytest cache 与 Python bytecode 写入。结果为退出码 `0`。Pytest 输出显示该文件全部通过；本报告不把其 case 数作为仓库总测试数。

### 相关回归

在目标 SHA gate 下执行以下明确文件集合：

- `tests/smoke/test_anthropic_responses_route.py`。
- `tests/smoke/test_anthropic_responses_stream_route.py`。
- `tests/unit/test_responses_stream_parser.py`。

结果为退出码 `0`，pytest 输出为 `29 passed in 2.75s`。该数字口径仅为上述三个文件在本次运行的 pytest summary，没有把它描述为仓库测试总数；是否全部收集到预期 test node 未以第二种收集算法交叉验证，因此测试数量本身不作为 PASS 判据，退出码与独立 probe 才是本报告的承载证据。

### 独立进程内 probes

- `A15`：同一真实 ASGI route 上参数化执行 `response.failed`、Responses `error` 与 clean EOF，进程退出码 `0`。
- `A16`：首 block 前取消真实 ASGI task并核对 upstream、History、hooks 与下游消息，进程退出码 `0`。
- `A17`：text-only fake Responses SSE 的逐 frame 原始 ASGI probe，进程退出码 `0`。
- `A18`：early-byte 目标正控变异，确认 pre-done oracle 能因目标原因抓红，进程退出码 `0`。

这些 probe 只复用候选测试文件中的 fake target 与 harness 构造，不调用产品 parser 或 renderer生成 expected。SSE expected、事件顺序、字段 equality、usage 算式与时序断言直接来自冻结 Acceptance 与 resume 切片矩阵。

## 未覆盖项

以下项目明确保持 `UNVERIFIED`：

- retry ownership、pre-commit retry、attempt reset、retry exhaustion 与 post-commit full-replay frontier。
- request/global quota、slow consumer、有限队列、backpressure、capacity deadline 与 memory accounting。
- sink partial-write、RST offset、delivery-uncertain、真实 socket durable visibility 与 post-commit error 全矩阵。
- 首 block 提交后的客户端取消；本轮只验证首 block 前基本 cleanup。
- 真实 loopback TCP server/client、Uvicorn listener、HTTP chunk packetization与真实内核 socket close；本轮“真实 ASGI”指直接调用生产 FastAPI/Starlette ASGI app，而不是内部 converter/generator。
- reasoning、tool、A/B乱序连续前缀、多个 blocks、random rechunk、官方 Anthropic SDK consumer与完整 CAL-04 strict grammar corpus。本轮候选自带 happy 测试虽覆盖 reasoning 与 tool，但本次独立切片只对 text happy 给出独立 frame oracle。
- History enabled持久化、approval modified/rejected/timeout、全部 hook phase、tokenization calibration与 shutdown。
- HTTP/WS upstream parity、live upstream canary、capture corpus 与真实凭据。
- nonstream/stream 完整语义等价和完整 bridge Acceptance 的其余 required gates。

这些未覆盖项符合本轮用户明确的 happy slice 边界；它们既没有被静默判绿，也没有被写成候选缺陷。

## 最终结论

候选 `2087f8f02516136314985f5c48bdee20b2f4b861` 对本轮限定的 Responses SSE text happy slice 判定为 **PASS**。真实生产 ASGI route 已被执行，模块来源已绑定目标 worktree；单 upstream、Anthropic-only SSE、authoritative done 前零可见、首完整 block batch、terminal/usage、failed/error/clean EOF、单 RequestContext/hooks/finalize与首 block 前取消基本 cleanup均有实际运行证据。early-byte 目标正控证明关键时序 oracle 具有判别力。

完整 bridge 与未覆盖矩阵仍为 `UNVERIFIED`。目标 worktree 全程严格只读，最终 status 干净；本轮唯一仓库写入为本报告。
