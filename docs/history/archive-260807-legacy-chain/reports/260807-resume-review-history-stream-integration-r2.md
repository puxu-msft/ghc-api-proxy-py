# History + stream integration 定向终审 R2

## 评审范围与 verdict

- 候选：`/home/xp/src/ghc-api-proxy-py-integrate-stream`，branch `integrate/260807-post-history-stream`，HEAD `b5d5d0ce9dff4a1c28aac4371b3fdc71e806bba0`。
- Base：`38bb06ff0eefef69fd4fdab830e67ff549563a20`。
- 定向范围：上一预审唯一 major，以及共享 `client`／`executor`／`route` 的 capability、strict validation、callback 顺序、stream cleanup 与 History projection 合成语义。
- 总体 verdict：**可进入下一阶段；可 squash。**
- Blocker：**0**。
- Major：**0**。

## 双视角覆盖证据

### 机械核对

- 每次 shell 调用均在同一调用内核验候选目录、repository root、branch、HEAD 与 base；候选工作树在所有只读检查和测试前后保持同一 clean status hash。
- 对照上一轮报告 `docs/tmp/260807-resume-review-history-stream-integration.md`，逐项复核唯一 major 的失败形态与继续条件。
- 逐 hunk 对账 base→HEAD 的 `src/app/history/consumer.py`、`src/app/anthropic/client.py`、`src/app/pipeline/executor.py`、`src/app/routes/anthropic.py`，并读取最终 merged code，而非只看 diff。
- 核对真实 `HistoryConsumer.finalized()` 签名、route 调用参数、真实 SQLite store 回归、non-stream fallback 与 failed non-stream 零成功事实。
- 核对 `git diff-tree --check 38bb06ff0eefef69fd4fdab830e67ff549563a20 HEAD`，通过。
- 运行上一预审冻结的最小 selectors；运行结果为 `34 passed in 2.89s`。同一 selectors 的 `pytest --collect-only` 独立得到 `34 tests collected`，数量口径为该定向 selector 集在候选 HEAD 上展开参数化后的 test case 数。

### 第一人称执行模拟

- 模拟 non-stream Responses 成功：request 在每个 attempt 重新按 resolved-model capability 转换；最终 client-visible body 先经过 response hook 与 strict Anthropic wire validation，再写入 conversion／usage facts，随后依次执行 strategy、limiter、`RESPONSE`、`COMPLETED`、`FINALIZE`、History。
- 模拟 non-stream strict validation／response hook 失败：不会发布 success callback，不会向 History 写入成功 response／usage facts，只进入一次 failure lifecycle。
- 模拟 Responses stream 完成：executor 仅进入 `STREAMING`；route 依据真实 ASGI send outcome推进 delivery frontier，终态接受后才发布 `RESPONSE`／`FINALIZE` 与完整 committed History projection，最后关闭 upstream。
- 模拟 postcommit protocol failure：已接受 prefix 被投影到 History，输出单一 Anthropic `error` SSE，不输出 `message_stop`，request 状态为 failed。
- 模拟 first-body delivery uncertain：不把 possibly-visible block 伪装为 committed；History 保存 frontier uncertainty 与 error facts。
- 模拟 prefetch disconnect 及再次 cancellation：observer finalize、History finalize 与 upstream close 均完成且恰好一次，不发送 success headers。

## 上一轮 major 复核

**已关闭。** `src/app/history/consumer.py:26` 的真实 `HistoryConsumer.finalized()` 现接受 keyword-only `response`、`usage`、`usage_estimated`；`src/app/routes/anthropic.py:116` 的 stream route 调用与真实签名一致。

语义优先级正确：

1. `src/app/history/consumer.py:36` 在显式 stream projection 存在时持久化 projection，并从显式 normalized usage 生成 stream usage summary。
2. `src/app/history/consumer.py:43` 在未提供 projection 且状态 completed 时保留既有 non-stream `final_response_payload` 与 typed usage／conversion facts 路径。
3. Failed non-stream 未提供 projection 时不写成功 response／usage facts。

回归不是只靠签名更宽的 fake：`tests/component/test_history_store.py:167` 参数化使用真实 `HistoryConsumer` 与真实 `HistoryStore`，分别覆盖 completed projection 和 failed／uncertain projection；`tests/component/test_history_store.py:225` 继续覆盖 failed non-stream 零成功事实。

## 共享语义合成复核

### Capability 与 client attempt facts

- `src/app/anthropic/client.py:247` 继续把 `_reasoning_capabilities(prepared.resolved_model)` 的结果传给 request conversion；未退回 model-name guessing。
- `src/app/anthropic/client.py:266` 的 stream success 返回未消费、未关闭的 upstream，同时保留 request conversion facts。
- `AnthropicAttemptResult` 仍同时承载 response、request conversion facts 与 non-stream converted response；未被 stream 合成覆盖。

### Strict validation 与 callback 顺序

- `src/app/pipeline/executor.py:339` 在 success callbacks 前验证最终 client-visible body。
- `src/app/pipeline/executor.py:361` 在 validation 后写入最终 attempt 的 request／response conversion facts 与 typed usage。
- `src/app/pipeline/executor.py:382`、`:391` 保持 strategy／limiter 先于 `ObserverEvent.RESPONSE`；stream 分支在 `src/app/pipeline/executor.py:401` 仅进入 `STREAMING`，不提前 finalize History。

### Stream cleanup 与 History projection

- `src/app/routes/anthropic.py:34` 的 `_history_stream()` 以 terminal accepted／error／delivery uncertain 决定 completed 或 failed，并在 `:89` 后按 observer→History 的顺序 finalize。
- `src/app/routes/anthropic.py:102` 从 delivery ledger 的 `committed_response` 构造 History projection，成功、partial failure 与 uncertain 均保留各自语义。
- `src/app/routes/anthropic.py:231` 以 `passthrough_bytes(..., cleanup=upstream.aclose)` 统一托管 upstream cleanup；`src/app/streaming/sse.py:193` 的 delayed response cleanup 等待 pending pull 与 body iterator cleanup。
- Accepted／uncertain frontier 仅由实际 ASGI start／body send outcome推进，未发现 assembly-time 提前 commit 的旁路。

## 最小测试结果

首次尝试候选本地 `.venv/bin/pytest` 时，入口不存在，命令以 `127` 退出且未进入 test collection；候选状态未变化。随后只读验证 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python` 在候选 cwd、显式候选 `PYTHONPATH` 下导入的 `app.__file__` 为 `/home/xp/src/ghc-api-proxy-py-integrate-stream/src/app/__init__.py`，再用该解释器运行冻结 selectors。

覆盖内容包括：

- resolved-model reasoning capability 在 `PRE_SEND` 修改后重新转换；
- non-stream hooked response 与 exact facts 持久化；
- strict validation／hook failure 不发布 success callbacks；
- success callback 顺序与恰好一次；
- strict wire validator 的合法与非法 SDK message 形态；
- 完整 stream ASGI flow、prefetch recancellation cleanup、first-body uncertainty History projection、estimated usage、terminal identity／seal；
- 真实 `HistoryConsumer` 的 completed 与 failed／uncertain stream projection。

结果：`34 passed in 2.89s`；同一 selectors collect-only：`34 tests collected in 1.61s`。

## 事实性发现

未发现问题。上一轮唯一 major 已关闭；未发现新的 blocker、major、minor 或 nit。

## 主观建议

无。

## 范围边界与结构扫描

- 按用户要求未扩展到全仓测试、retry、quota、resident backpressure 或真实 socket partial-write 矩阵；本 verdict 仅覆盖上述定向范围。
- 结构怪味扫描范围为 `HistoryConsumer`、共享 client／executor、route、delivery frontier、delayed SSE cleanup 及其定向 tests；判据包括重复 lifecycle、职责错位、fake／real contract 漂移、成功 facts 提前发布、cleanup 所有权分叉与 projection 双来源冲突。未发现新的结构怪味。
- 本轮机制边界清晰，未发现需要引入第三方库替代的自研重复轮子。
