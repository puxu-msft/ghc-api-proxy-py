# Replay Capability Fix

## 结果

Replay 的资格现在由 `HistoryEntry.capture` 投影出的 `CaptureCapabilities` 正式决定，而不是由 `ReplayProcess` 读取原始 capture 后自行推断。`ReplayRequest.source_grant` 是必需的授权输入；grant 将 immutable capability projection 与 `source_entry_id`、resolved `capture_path` 和 History `capture_ref` 绑定。未提供 grant 时以 `source_capability_unavailable` 拒绝；任一 binding 不符时以 `source_capability_mismatch` 拒绝，且两种路径都不会开始读取或执行 replay。

`CaptureCapabilities.replay_rejection_code()` 集中定义资格判定和稳定错误码：

| 条件 | 错误码 |
| --- | --- |
| capture status 为 `corrupt` | `source_capture_corrupt` |
| capture status 为 `none` | `source_content_unavailable` |
| capture status 不是 `complete` | `source_capture_incomplete` |
| mode 对应 capability 为 false，或 semantic/live 没有完整 client request capability | `source_capability_denied` |
| 未给入 source-bound History grant | `source_capability_unavailable` |
| grant 的 entry/path/ref 与 replay source 不一致，或完整 capture 缺 ref | `source_capability_mismatch` |

这使 `ReplayProcess` 只消费 history 的已冻结、source-bound capability grant，不会用 capture records 改写或推翻资格结论。所有 request deadline 先经 `math.isfinite()` 和范围检查，再进行 grant、source 或 executor 操作；NaN、正无穷和负无穷稳定返回 `invalid_deadline`。capture records 仍仅作为 evidence：semantic/live 会验证 client request body 完整且可解析；wire diagnostic 会验证所选 attempt 含 `upstream.attempt.start`、request start/body、response start/body/end（`complete=true`）和 `upstream.attempt.end`（`complete=true`）。因此错误 selector、未知 attempt、损坏或缺失的实物 evidence 不会进入 executor。

History index 现在持久化并读回五项 capability 字段；`HistoryIndexEntry.capture` 因而可作为 replay 的 history read projection。旧 SQLite 行的迁移默认值均为 false，故旧记录会安全拒绝 replay 而不会被误放行。

## REPLAY-CAP-FINAL-01

wire diagnostic 的默认 `ReplayResult.diagnostic_records` 不再携带 selected upstream attempt 的 raw capture records。process 只投影 credential-free summary：`event`、`attempt`、`status_code`、`complete` 及 `body_bytes`。raw `body`、`headers` 和其他原始 payload 字段只在 process 内部用于证据验证，不进入 `ReplayResult` 或 `as_dict()`。

Replay Spec 已明确这一默认边界：若将来要保留完整 evidence，必须建立单独的显式敏感 projection，并标记 `contains_credentials=true`；当前默认 result 没有该 projection。

## 覆盖

`tests/unit/replay/test_process.py` 覆盖：

- wire/semantic/live 的允许路径；
- 对仍然可读的完整 capture 传入 false capability 时的拒绝，证明 capability 是事实源；
- capability 缺失、`incomplete`、`corrupt`；
- `none`/无 capture reference 的 History source；
- semantic/live 的 client request incomplete；
- wire attempt incomplete、未知 attempt、错误 selector；
- NaN、正无穷、负无穷 deadline 在 reader/executor 前拒绝；
- entry id、capture path 或 capture ref 任一错配的 swapped grant 在 reader/executor 前拒绝；
- executor deadline；
- capability 拒绝信息不携带 JSON body key 或 authorization header 名。
- wire diagnostic 的序列化 result 只含允许 summary keys，且不含 raw `body`/`headers` 字段、upstream raw body marker 或 `x-request-id` header marker。

`tests/unit/history/test_history_entry.py` 覆盖 HistoryEntry 的完整 capture projection，以及 `CaptureCapabilities` 对 corrupt、incomplete、缺 client request 和允许 wire 的集中判定。

## 验证

通过：

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py
# 35 passed

cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py src/app/history/writer.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# All checks passed

cd /home/xp/src/ghc-api-proxy-py && uv run pyright src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py src/app/history/writer.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# 0 errors, 0 warnings
```

Repository-wide checks were also run:

- `uv run ruff check` fails while scanning foreign `.claude/worktrees/` content. This is outside the permitted files; the scoped Ruff command above passes.
- `uv run pyright` passes with `0 errors, 0 warnings`.

REPLAY-CAP-FINAL-01 的最新 focused 验证：

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# 32 passed

cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# All checks passed

cd /home/xp/src/ghc-api-proxy-py && uv run pyright src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# 0 errors, 0 warnings
```

## Final Review 2 闭合

已闭合五项 replay finding：

1. `incomplete` 不再是跨 mode 否决。`none`/`corrupt` 仍稳定拒绝；semantic/live 在 client request available 且其 mode capability 为 true 时允许，反向 capability=false 时拒绝。
2. `CaptureAttemptCapabilities` 作为 `CaptureCapabilities.upstream_attempts` 的安全逐 attempt matrix 投影进 `HistoryEntry.as_dict()` 与 History index read projection。wire grant 必须同时允许 aggregate wire capability 和所选 `attempt_id` 的 `wire_diagnostic_eligible`；未授权 attempt 在 reader 前拒绝。
3. wire evidence gate 现在要求 request/response start 都有 Mapping headers，以及 body 和完整 attempt/response boundaries；缺 request headers、response headers、非-Mapping headers 或 response body 的 record 均以 `source_evidence_unavailable` 拒绝。
4. deadline 在任何 capture read 前建立。每条读取 record、source decode、wire summary 与 executor invocation 均检查剩余预算；同步 reader 不会创建后台任务，慢 reader/decode 在继续执行或调用 executor 前以 `deadline_exceeded` 停止。
5. semantic/live 的 default result 只投影受限 `outcome`；client action 只保留 `type`/`name`。opaque executor 的 body、headers、credentials、transport payload 和 action arguments 均不会进入 `ReplayResult.as_dict()`。

最终验证：

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py
# 51 passed

cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py src/app/history/writer.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# All checks passed

cd /home/xp/src/ghc-api-proxy-py && uv run pyright
# 0 errors, 0 warnings
```

## RCR 二次 review 状态

本轮直接收敛了两条可在白名单内独立完成的边界：

- `RCR-03`：`ReplayResult.as_dict()` 现在无论 result 是由 process 还是调用者直接构造，都会重新投影 diagnostic records、output 和 client actions。直接构造的 nested body/header/credential/action-argument marker regression 已通过。
- `RCR-04`：新增 `RawCaptureAttemptObservation` 与直接 History projection；`CaptureAttemptCapabilities` 不再从 `UpstreamBodyAttempt` response timing 推断 request/header/boundary 完整性。没有实际 capture attempt facts 时 matrix 为空，wire selector capability fail-closed。

仍未闭合：

- `RCR-01`：当前 `ReplaySourceGrant` 仍是调用方可构造的对象，尚未替换为 process 内受控的 History resolver/source receipt。
- `RCR-02`：当前同步 source reader 在每个可观测 record/decode 边界检查 deadline，但无法中断一个正在阻塞的 `next()`/open/decode 调用。为满足 review 所要求的硬时限和无后台遗留，需要受控、可终止的 reader worker，不能把同步 iterator 包装成事后检查。
- `RCR-04` 的实际数据生产：本轮允许修改 observation projection，但 `RawRequestCapture.observation()` 目前不会填充新增的 `upstream_attempts`。按本次白名单不得修改 raw capture writer，因此完整的实际 attempt-facts production 需要扩大该 writer 的授权；在此前 wire 继续因缺矩阵而拒绝，避免错误放行。

本轮验证：

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py
# 52 passed

cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src/app/observability/capture_observation.py src/app/history/entry.py src/app/history/writer.py src/app/replay/process.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# All checks passed

cd /home/xp/src/ghc-api-proxy-py && uv run pyright src/app/observability/capture_observation.py src/app/history/entry.py src/app/history/writer.py src/app/replay/process.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# 0 errors, 0 warnings
```

## RCR-01/RCR-02 并发交接

2026-09-16 在实现受控 source authority 与可终止 reader worker 时，`src/app/replay/process.py` 同时被另一项工作修改：`_validate_source()` 从 selected attempt 的完整 structural validation 改为只检查 attempt 存在。当前 replay focused tests 因此有 6 条 wire evidence regression 失败，错误不是 RCR-01/RCR-02 的稳定验收结果。为避免覆盖同一函数的并发 WIP，本次停止继续修改 `process.py`。

当前未可交付地宣称 RCR-01/RCR-02 已闭合。后续接手者需要先协调/合并该 concurrent `process.py` 改动，再重新验证 source-authority receipt、worker termination/deadline 与 selected-attempt structural gate 的共同语义。

## RCR-01/RCR-02 merged-state 闭合

在 RCR-04 变更合并后已重新读取 `ReplayProcess` 与 History capability matrix，并只修改 RCR-01/RCR-02 seam：

- `ReplaySourceGrant` 已从 `ReplayRequest` 和 public replay exports 移除。`ReplayProcess` 在 `run()` 内通过构造时注入的 `ReplaySourceAuthority` 查询 `ReplaySourceReceipt`；request 的 `capture_path` 不再是 source authority。receipt 必须与 request 的 `source_entry_id`、`source_capture_ref` 相等，且 capability 与实际 reader path 只来自 authority receipt。没有 authority 的 process 稳定拒绝 `source_authority_unavailable`；错配 receipt 在 reader/executor 前拒绝。
- raw capture reader/CBOR decode 运行在受控的 fork worker。parent 只以当前剩余 deadline 等待 worker 的 IPC result；超时即 `terminate()` 并 `join()`，随后返回 `deadline_exceeded`，不会遗留 worker 或继续调用 executor。slow-reader regression 对 wire 和 semantic 都断言在 reader 的 300 ms sleep 结束前返回。

merged-state 验证：

```text
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py
# 52 passed

cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py src/app/history/writer.py src/app/observability/capture_observation.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# All checks passed

cd /home/xp/src/ghc-api-proxy-py && uv run pyright
# 0 errors, 0 warnings
```

## 范围

修改仅在允许范围内：

- `src/app/history/entry.py`
- `src/app/history/writer.py`
- `src/app/observability/capture_observation.py`
- `src/app/replay/process.py`
- `src/app/replay/__init__.py`
- `tests/unit/history/test_history_entry.py`
- `tests/unit/replay/test_process.py`
- `.dev/docs/history/spec.md`
- `.dev/docs/raw-capture/spec.md`
- `.dev/docs/replay/spec.md`

没有修改 raw capture writer、history archive storage、history routes 或 provider/inference。
