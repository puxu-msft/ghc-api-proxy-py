# History + stream integration 独立验收

## 判定

**PASS**。

验收对象为 `/home/xp/src/ghc-api-proxy-py-integrate-stream` 的 `HEAD b5d5d0ce9dff4a1c28aac4371b3fdc71e806bba0`，比较基线为 `38bb06ff0eefef69fd4fdab830e67ff549563a20`。本轮只覆盖用户指定的关键路径与本轮失败机制，不外推为 Anthropic Responses bridge 全规格通过。

候选工作树在测试、probe 与最终收口前后均保持干净。状态摘要的 SHA-256 始终为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，即空 `git status --porcelain=v1 -z` 的摘要；`git diff-tree --check 38bb06f HEAD` 通过。

## 冻结规格与独立验收矩阵

行为 oracle 来自 `docs/agents/anthropic-responses-bridge/spec.md` 的 SSE／WS envelope、block-level buffering、History、client cancel 与 error 契约，以及 `docs/2604-rewrite/history-system.md` 的 History 终态投影。先据此推导下列矩阵，再读取实现与现有测试。

| 验收项 | 用户可观察判据 | 结果 |
|---|---|---|
| 真实 `HistoryConsumer` stream success | 保存完整 committed Anthropic response、完整 delivery 与 usage，终态为 `completed` | PASS |
| 真实 `HistoryConsumer` partial／uncertain | partial 保存 committed prefix 与 error；uncertain 保存 possibly-visible／frontier facts，均不得伪装 completed | PASS |
| nonstream History facts 不回退 | nonstream success 保留 hook 后最终响应与 typed usage／conversion facts；失败且无显式 stream projection 时不得保存成功 response／usage | PASS |
| stream text happy withholding／terminal | 首个 semantic block 完成前零 success headers／body；完成后输出闭合 block envelope；合法 terminal 才输出 `message_delta`＋`message_stop` | PASS |
| cancel cleanup | prefetch disconnect 与再次 cancellation 后 upstream close、observer `FINALIZE`、History finalize 均完成且恰好一次 | PASS |
| postcommit error | 已提交 prefix 保留一次；随后只输出 Anthropic `error` SSE，不输出 `message_stop`，History 为 failed partial | PASS |
| capability thinking route | `PRE_SEND` 修改后的 thinking 重新依据 resolved-model capability facts 转成 Responses reasoning，不退回模型名猜测或旧 payload | PASS |

## 实际执行证据

### 定向测试

目标 worktree 没有独立 `.venv`，因此使用主仓解释器 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python`，并以 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-integrate-stream/src` 绑定候选实现。运行前的 load oracle 实际输出：

- `app`：`/home/xp/src/ghc-api-proxy-py-integrate-stream/src/app`
- `app.history.consumer`：`/home/xp/src/ghc-api-proxy-py-integrate-stream/src/app/history/consumer.py`

核心 selector 先执行 `pytest --collect-only -q`，pytest 报告 `12 tests collected`；再以独立文本计数统计 collection 日志中以 `tests/` 开头的 node 行，同样得到 12。随后执行相同 selector，结果为 `12 passed`，退出码 0。全文通读报告时发现核心 ASGI happy-path 在首块阶段直接证明的是 reasoning block withholding，因此另行补跑 3 个 text-specific 节点，结果为 `3 passed`，退出码 0。两个批次合计 15 个实例，未把邻近 reasoning 证据冒充 text 独立证据。

执行的节点如下。参数化展开后共 12 个实例：

- `tests/component/test_history_store.py::test_history_consumer_persists_explicit_stream_projection`
- `tests/component/test_history_store.py::test_history_consumer_failure_without_projection_has_no_success_facts`
- `tests/component/test_pipeline_executor.py::test_responses_success_persists_hooked_response_and_exact_facts`
- `tests/component/test_pipeline_executor.py::test_history_preserves_request_and_response_conversion_provenance`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_uncertainty_is_projected_into_history`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_postcommit_protocol_failure_emits_error_sse_and_saves_partial_history`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_success_terminal_is_validated_before_message_stop`
- `tests/smoke/test_anthropic_responses_route.py::test_pre_send_reasoning_modification_is_reconverted_with_capability_facts`

text-specific 补充节点如下：

- `tests/unit/test_responses_stream_parser.py::test_text_block_is_emitted_only_after_authoritative_done`
- `tests/smoke/test_anthropic_block_delivery.py::test_first_batch_binds_message_start_to_the_complete_first_block`
- `tests/smoke/test_anthropic_block_delivery.py::test_terminal_batch_records_usage_after_all_blocks`

关键判别断言位于：

- `tests/component/test_history_store.py:167-255`：真实 `HistoryConsumer` 的 success／uncertain projection，以及 nonstream failure 不携带成功 facts。
- `tests/unit/test_responses_stream_parser.py:43-78`：text delta 尚未 authoritative done 时不产出 `CompletedBlock`；done 后才产生 immutable `TextBlock`。
- `tests/smoke/test_anthropic_block_delivery.py:119-134`：首个完整 text block 与 `message_start` 组成同一闭合 sink batch。
- `tests/smoke/test_anthropic_block_delivery.py:187-216`：text block 之后的成功 terminal batch恰好包含 `message_delta`＋`message_stop`，重复 finish 被拒绝。
- `tests/smoke/test_anthropic_responses_stream_route.py:640-940`：真实 ASGI 流在首个 reasoning block authoritative done 前 `sent == []`，之后输出首个闭合 batch，并在合法 terminal 后完成包含 reasoning、text 与 tool block 的 History success projection。
- `tests/smoke/test_anthropic_responses_stream_route.py:1055-1095`：再次 cancellation 后 observer、History 与 upstream cleanup 全部完成，finalize 各一次。
- `tests/smoke/test_anthropic_responses_stream_route.py:1099-1181`：postcommit protocol failure 保留 `committed prefix`，末事件为 `error`，且明确断言无 `message_stop`。
- `tests/smoke/test_anthropic_responses_stream_route.py:1323-1372`：terminal identity mismatch 或 terminal 后追加事件均阻止 `message_stop` 并进入 failed History。
- `tests/smoke/test_anthropic_responses_route.py:546-563`：`PRE_SEND` thinking 修改重新转换为 capability-driven Responses reasoning。

### 真实 `HistoryConsumer` 简单 probe

在 `tempfile.TemporaryDirectory` 下创建临时 SQLite，通过候选树真实 `HistoryStore`＋`HistoryConsumer`，逐项调用 `started()` 与 `finalized()`；没有使用测试 fake，也没有写候选树。probe 退出码为 0，实际观察为：

| 输入投影 | 持久化终态 | 持久化关键事实 |
|---|---|---|
| success | `completed` | text `complete`；`delivery.complete=true`；`uncertain=false` |
| partial | `failed` | committed text `committed prefix`；error code `unsupported_responses_event`；未标 uncertain |
| uncertain | `failed` | committed content 为空；保留 `possibly_visible_block={type:text,text:maybe}`；error code `delivery_uncertain` |

三个 case 均原样保留显式 stream projection，usage total 为 5；只有 uncertain case 标记 `estimated=true`。probe 明确打印并断言所加载 consumer 为候选树 `src/app/history/consumer.py`。

## 本轮失败机制结论

预审指出的缺陷是 stream route 以 `response=` 调用 `HistoryConsumer.finalized()`，而旧真实 consumer 不接受该参数；测试 fake 的宽签名曾掩盖这一接缝。候选实现现于 `src/app/history/consumer.py:26-46` 接受显式 stream projection，并保持以下优先级：

1. 提供 `response` 时，保存 stream success／partial／uncertain projection及对应 stream usage。
2. 未提供 projection 且 context 为 `COMPLETED` 时，继续保存 nonstream 的 `final_response_payload` 与 typed usage／conversion facts。
3. nonstream failure 未提供 projection 时，不回填成功 response／usage。

真实 consumer 定向测试与独立临时 SQLite probe 均命中该接缝，因此本轮 fake 比真实接口更宽导致的 false-green 已关闭。

## 明确未验证范围

按用户要求，本轮没有扩展到 retry 全矩阵、quota／resident backpressure、真实 socket partial-write 全 offset、HTTP／WS parity、全 reasoning carrier 状态空间、真上游 canary或全仓测试。上述项目均为本轮 **未验证**，不影响本次限定范围的 `PASS`，也不得从本报告推导为全 bridge 通过。

## 只读与产物

- 候选树 `/home/xp/src/ghc-api-proxy-py-integrate-stream`：未写入，最终状态干净。
- probe 数据：仅位于自动清理的临时目录。
- 主树唯一新增产物：`docs/tmp/260807-resume-verify-history-stream-integration.md`。

本报告是叶子验收者的持久化验证产物；按项目协作规则，主会话在把它作为最终交接事实前仍需完成独立报告评审。
