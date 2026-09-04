# Responses stream route R3 独立定向终审

- **评审范围**：严格只读终审 `/home/xp/src/ghc-api-proxy-py-stream-route` 的 `feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，base 为 `b91e58a29324b11840002efc53ed6f869b800c39`。范围只包含上一轮 `docs/tmp/260807-resume-review-stream-route-current.md` 的 3 个 major：cancel cleanup 抗二次取消且 upstream close／observer FINALIZE／History finalize 完成，空 delta authoritative 冲突不可绕过，以及两处 fixture 修复并保持测试目标有效；另抽查上一轮已关闭的 missing usage、delivery frontier History 与 terminal identity／seal 是否回归。未重新展开更早已关闭项或完整 Acceptance。
- **总体 verdict**：**可进入下一阶段；0 major，明确可 squash。** 上一轮 3 个 major 均已关闭，定向抽查未发现 missing usage、frontier History 或 terminal seal 回归。本结论只放行该 stream-route 候选按既定方式 squash，不表示完整 bridge Acceptance、部署或 cutover 已通过。
- **blocker 数**：0。
- **major 数**：0。
- **双视角覆盖证据——机械核对**：每次 shell 均在同一调用内打印并校验物理 cwd、Git top-level、branch 与完整 HEAD。完整读取上一轮报告及 current route、delayed ASGI response、cleanup helper、Responses parser、delivery adapter和相关测试；逐项对账 3 个旧 major 的生产修复与正反控制。`git diff --check bc436af647507df4ea45f3b01ca8942fade4f036..f3922a9ba9f90e4eea598dac1d899ebbe18985e8` 退出码为 0；测试前后候选 status 哈希均为 clean-tree SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。模块路径探针确认 `sse.py`、`keepalive.py` 与 parser 均从候选 worktree 加载。
- **双视角覆盖证据——第一人称执行**：模拟首个 `anext()` 尚未产出时 disconnect，cleanup 已开始后 owner 再次取消，随后依次放行 observer FINALIZE、History finalize 与 upstream close；模拟 pull task 尚未获得调度前 owner 取消；分别执行空 `output_text.delta` 后由 content-part done 与 item done 给出非空 authoritative 值；再执行无 delta 的 done-only 合法值与三层 authoritative 等值 reverse-order 正样本。另执行 empty-message typed failure、missing usage 的 `max_output_tokens` 成功终止、首 body uncertain 的 History 投影、terminal id 漂移及 terminal 后事件分支。

## 上一轮 3 个 major 处置

| 上一轮 major | R3 状态 | 终审证据 |
|---|---|---|
| cancel cleanup 抗二次取消 | **已关闭** | `src/app/streaming/sse.py:102-109,190-205` 把每次 pull 放入独立 task，并将 pending task 与 iterator 交给共享 cleanup；`src/app/streaming/keepalive.py:69-113` 以独立 cleanup task 配合重复 `asyncio.shield()`，记录后续 cancellation 而不让其中断 cleanup。`tests/smoke/test_anthropic_responses_stream_route.py:1047-1088` 的 route-level 正控在 cleanup 各 checkpoint 间实施再次取消，并断言 observer、History、upstream close 全部完成且 FINALIZE／History 各恰好一次。相关具名测试通过。 |
| 空 delta authoritative 冲突可绕过 | **已关闭** | `src/app/openai/responses_stream_parser.py:350-357,389-396,721-728` 三个 text authoritative 接点均按 `draft.deltas` 是否存在判断，而非按拼接结果 truthiness 判断；因此一个已观察到的空 delta 会与后续非空 authoritative 值比较并触发 `authoritative_text_mismatch`。`tests/unit/test_responses_stream_parser.py:719-756` 覆盖 content-part done 与 item done 两个失败终点；`tests/unit/test_responses_stream_parser.py:759-783` 保留无 delta 的 done-only 合法正样本，避免 false-red。 |
| 两处 fixture 失真导致定向 suite 红 | **已关闭** | `tests/smoke/test_anthropic_responses_stream_route.py:354-380,1378-1395` 的 empty-message terminal id 已与 created id 同为 `resp_semantic_bad`，测试可抵达并断言 `empty_response_content`；`tests/unit/test_responses_stream_parser.py:683-716` 的 reverse-order 正样本只对 `msg_reverse` 完成一次 item，不再被 item-id 或 duplicate-done guard 抢先拦截，并明确断言三个 authoritative 层等值时零重复 block。两个测试目标均有效且具名测试通过。 |

## 已关闭项回归抽查

- **Missing usage**：`src/app/delivery/responses_anthropic_stream.py:282-294` 仅在输入流真正结束后提交暂存 terminal，并保留 `usage_estimated`；`src/app/routes/anthropic.py:64-116` 把同一 normalized usage 与 estimated fact送入 observer和History。`tests/smoke/test_anthropic_responses_stream_route.py:1233-1286` 的缺失 usage／`max_output_tokens` 路径通过。
- **Frontier History**：`src/app/delivery/responses_anthropic_stream.py:91-124` 在 delivery uncertain 时保留 headers、message start、terminal与可能可见 block的 typed projection；`src/app/routes/anthropic.py:73-116` 将 `delivery_uncertain` 写入失败上下文及 History。`tests/smoke/test_anthropic_responses_stream_route.py:554-628` 的首 body uncertain History 节点通过。
- **Terminal identity／seal**：parser 仍在 terminal 时校验 response id，并拒绝 terminal 后事件；adapter 仍将成功 terminal 暂存到 EOF 后再交付，见 `src/app/delivery/responses_anthropic_stream.py:162-168,231-250,282-311`。`tests/smoke/test_anthropic_responses_stream_route.py:1290-1354` 的 id 漂移与 terminal 后事件参数化节点通过，均未先发 `message_stop`。

## 事实性发现

未发现问题。上一轮 3 个 major 均已由最终生产代码与具有目标判别力的正反控制关闭；定向抽查未发现 blocker、major、minor 或 nit。

## 主观建议

未提出额外主观建议。本轮范围已由调用方明确限定，不将未验证边界改写为本候选缺陷。

## 测试与只读性

- 在精确候选 HEAD gate 后，借用主树虚拟环境并显式设置候选 `PYTHONPATH`，运行 11 个具名测试选择器；参数化展开后 pytest 现场自报 `14 passed in 5.44s`，退出码为 0；该数量未以不同原理的方法交叉验证，仅记录该次运行口径，不作为硬编码验收阈值。判定依据是具名节点退出码与断言内容。
- 覆盖节点来自 `tests/unit/test_streaming_sse.py`、`tests/unit/test_streaming_resilience.py`、`tests/unit/test_responses_stream_parser.py` 与 `tests/smoke/test_anthropic_responses_stream_route.py`，仅覆盖本轮 3 个修复项和 3 个回归抽查项。
- 候选树在测试前后均为 clean，未修改代码、测试、Git refs、index、服务、进程或环境。唯一持久化写入为主树本报告。

## 未验证边界

按本轮明确口径，**retry、quota／resident backpressure，以及真实 socket partial-write** 仍未验证；它们不升级为本轮 blocker 或 major。本 verdict 不应外推覆盖这些边界。

## 结论

`feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8` 的上一轮 3 个 major 已全部关闭，相关最小测试通过，已关闭的 missing usage、frontier History 与 terminal identity／seal 未见回归。最终判定为 **0 blocker／0 major，明确可 squash**；retry、quota／resident backpressure 与真实 socket partial-write 继续保持未验证。
