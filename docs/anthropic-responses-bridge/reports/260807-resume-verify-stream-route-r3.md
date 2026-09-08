# Anthropic Responses stream route 独立验收 R3

## 判定

**PASS（仅限本轮实际修复与主路径的定向范围）。**

候选为 `/home/xp/src/ghc-api-proxy-py-stream-route` 的 `feat/anthropic-responses-stream-route@f3922a9ba9f90e4eea598dac1d899ebbe18985e8`，base 为 `b91e58a29324b11840002efc53ed6f869b800c39`。验收期间目标工作树保持只读；定向测试前后 `git status --porcelain=v1 -z` 的 SHA-256 均为 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`，即空输出的 SHA-256。

本报告的 `PASS` 不等于完整 Anthropic Responses bridge 或完整 Acceptance `PASS`。本轮按用户要求没有执行完整 Acceptance，也没有预建全状态空间。

## 冻结规格与本轮验收矩阵

行为 oracle 为候选树中的 `docs/agents/anthropic-responses-bridge/spec.md`，状态标记为 `FINALIZED`；验收细化参考 `docs/agents/anthropic-responses-bridge/acceptance.md` 的既有 `FINALIZED_ACCEPTANCE_ORACLE`。本轮先从规格推导以下用户可观察判据，再读取实现与现有测试：

| 验收项 | 规格判据 | 实证与结果 |
|---|---|---|
| Text happy withholding／terminal | 首个完整 semantic block 前不得出现 HTTP success headers、`message_start` 或 body；完整 text block 后才提交首批，合法 terminal 最后且仅一次产生 `message_delta` 与 `message_stop` | `tests/smoke/test_anthropic_responses_stream_route.py:632` 走真实 ASGI route，在 reasoning `.done` 前断言 `sent == []`，随后验证完整首批、text／tool 顺序、terminal、History 与 finalize。**PASS** |
| 二次 cancel cleanup | client cancel 不重试；重复 cancellation 不得中断 observer finalize、History finalize 或 upstream close；各资源及 finalize 恰好一次 | `tests/smoke/test_anthropic_responses_stream_route.py:1047` 在三个 cleanup checkpoint 中再次 `cancel()`，验证三段 cleanup 均完成、History finalize 一次、observer `FINALIZE` 一次。生产 cleanup owner 位于 `src/app/streaming/keepalive.py:69`，其 shield loop 位于 `src/app/streaming/keepalive.py:97`。**PASS** |
| 空 delta 与 authoritative done 冲突 | 一旦观察到空 delta，后续非空 authoritative content-part／item done 不得把它当作“没有 delta”并正常成功；必须给 typed `authoritative_text_mismatch` | `tests/unit/test_responses_stream_parser.py:719` 覆盖 content-part done 与 item done 两层。两参数均通过。**PASS** |
| Missing usage 的 `max_tokens` | `response.incomplete` 且 reason 为 `max_output_tokens` 时仍是合法 `stop_reason=max_tokens`；usage 缺失时 wire 为 Anthropic 零值且 History／observer 标记 `estimated=true` | `tests/smoke/test_anthropic_responses_stream_route.py:1233` 走真实 ASGI route并比较 wire、History 与 response observer。生产缺失 usage 分支位于 `src/app/delivery/responses_anthropic_stream.py:376`。**PASS** |
| Delivery-uncertain History | sink 结果不确定时不得把可能可见 block 记成 committed／completed，不得发送成功 terminal；History 必须保留代理所知的 uncertainty、possibly-visible block，并以 `delivery_uncertain` 失败终态 finalize | `tests/smoke/test_anthropic_responses_stream_route.py:554` 在真实 ASGI `Send` 的首个 body 写入抛出 `OSError`，验证 upstream close、History content 为空、uncertainty 投影、`delivery_uncertain` 与 `FAILED`。投影入口位于 `src/app/delivery/responses_anthropic_stream.py:91`。**PASS** |
| Terminal id／seal | terminal response id 必须与 created id 一致；terminal 后的任何事件都必须使成功 terminal 作废，不能在 seal 前发 `message_stop`；History 必须失败 | `tests/smoke/test_anthropic_responses_stream_route.py:1315` 两参数分别覆盖 `response_id_mismatch` 与 `event_after_terminal`，均验证无 `message_stop`、末事件为 Anthropic `error`、History 为 `FAILED`。parser identity guard 位于 `src/app/openai/responses_stream_parser.py:768`。**PASS** |

## 实际执行

测试使用主仓 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python` 提供依赖，但显式设置 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-stream-route/src`。执行前探针确认：

- `app.__file__=/home/xp/src/ghc-api-proxy-py-stream-route/src/app/__init__.py`
- `app.openai.responses_stream_parser.__file__=/home/xp/src/ghc-api-proxy-py-stream-route/src/app/openai/responses_stream_parser.py`

定向 pytest 节点：

- `tests/smoke/test_anthropic_responses_stream_route.py::test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`
- `tests/unit/test_responses_stream_parser.py::test_empty_text_delta_conflicts_with_nonempty_authoritative_text`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_max_output_tokens_without_usage_uses_estimated_zero_usage`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_first_body_uncertainty_is_projected_into_history`
- `tests/smoke/test_anthropic_responses_stream_route.py::test_success_terminal_is_validated_before_message_stop`

pytest 参数化后实际结果为 **`8 passed in 2.04s`，退出码 `0`**。其中空 delta 和 terminal id／seal 各展开为两个 case。

第一次尝试直接调用目标树 `.venv/bin/pytest`，因目标 worktree 没有独立 `.venv` 而以退出码 `127` 停止；没有执行测试，也没有写入目标树。随后采用上述共享解释器＋目标绝对 `PYTHONPATH`，并以导入路径探针消除了跑错树的风险。

## 目标正控

只执行一个目标正控，针对本轮“空 delta 绕过 authoritative text 一致性”修复。正控不修改磁盘：在单一 Python 进程中临时 monkeypatch `ResponsesStreamParser._on_output_text_delta`，注回旧缺陷——仅当 delta 非空时才调用生产实现，即让空 delta 不进入 observed deltas；随后复跑同一个两参数 regression test。

结果为 **`2 failed in 0.32s`，mutated pytest 退出码 `1`**。两个 case 均在 `tests/unit/test_responses_stream_parser.py:753` 以目标原因失败：`Failed: DID NOT RAISE ResponsesStreamProtocolError`。这证明测试能够区分“空 delta 被记录并与非空 authoritative done 冲突”与“空 delta 被静默忽略”两种实现，而不是因 fixture、导入或旁路断言偶然变红。正控 wrapper 将该预期红灯转换为自身退出码 `0`；正控前后目标状态 SHA-256 仍均为 `e3b0c442…b855`。

## 未验证边界

以下均是**未验证**，不是已证实缺陷：

- 完整 Acceptance 的 route／request／non-stream／stream／retry／lifecycle／limits／HTTP／WS／transport parity／live canary／capture corpus／local fault 全矩阵。
- 完整 text 状态空间、随机 chunk／frame 切分、property-based／fuzz、CRLF 与所有 SSE framing 组合。
- 其他 content 类型与组合，包括 refusal、多个 text parts、reasoning 多 item／carrier 全矩阵、tool arguments 全边界、server-tool／unknown item 全矩阵。
- response-start、任意 body byte offset、terminal batch 的真实 socket partial-write／RST 全矩阵；本轮仅验证首个 ASGI body send uncertainty 及其 History 投影。
- cancel 在所有时点、shutdown、idle timeout、backpressure、queue／resident quota、并发请求、WS close 的完整组合；本轮仅验证 prefetch disconnect 后的二次 cancellation cleanup。
- retry exhaustion、pre-commit retry、post-commit failure／continuation、attempt reset 与重复前缀 suppression 的完整组合。
- usage 的 cache／reasoning／malformed／inconsistent 数值矩阵；本轮仅验证 `max_output_tokens` 且整个 usage 缺失。
- terminal id／seal 的所有 terminal kind、重复 terminal、clean EOF、malformed SSE 和并发 terminal 组合；本轮仅验证 created／completed id mismatch 与 terminal 后 trailing event。
- 官方 Anthropic SDK consumer、真 upstream HTTP／WS 和部署环境行为。

## 结论

`f3922a9ba9f90e4eea598dac1d899ebbe18985e8` 在用户指定的 6 项定向范围内为 **PASS**：现有 8 个实际 pytest case 全绿，且唯一目标正控按预期机制变红。未发现该限定范围内的阻断缺陷。候选目标树全程只读；本任务唯一写入是主树中的本报告。
