# Replay capability final replay review 2

日期：2026-09-16  
评审方式：最终状态、只读、独立复核  
总体 verdict：needs-fix  
Blocker：0

## 评审范围

审查当前最终状态中 replay capability 的 `src/app/replay/process.py`、`src/app/replay/__init__.py`、`src/app/history/entry.py`、直接 History read projection、`tests/unit/replay/test_process.py`、`tests/unit/history/test_history_entry.py`，以及 Replay、History、Raw Capture ACTIVE specs。

明确不在范围：Replay CLI/public API exposure、History archive/durability 实现、raw-capture writer 的独立实现、其余 provider pipeline，以及工作树内与本能力无关的既有 WIP。

## 独立判据

- Replay spec §2、§4、§6：capture-only source、显式 selector、source read 前建立并逐步检查的有限 deadline、none/corrupt 的 not-started 拒绝、按 attempt 的 wire eligibility、默认 result 的 credential-free boundary。
- History spec §1、§3、§4、§6：History semantic payload 不是 replay source；capture capability matrix 含 per-attempt request/response/boundary completeness 和 wire eligibility；普通 History projection 不复制 transport-sensitive fields。
- Raw Capture spec §4、§4.1：none/corrupt 否决全部 replay；pending/incomplete 不可单独否决 semantic/live；wire 还须验证被选 attempt 的 request/response headers、body、explicit boundaries；Replay 不复用 source headers/credentials。

## 发现

### Major

#### RCR-01 — `ReplaySourceGrant` 不是由 History 解析出的 source-bound capability，任意调用者可自行伪造允许执行的 grant

- **primary_location**：`src/app/replay/process.py:60-78, 297-332`
- **related_locations**：`src/app/replay/__init__.py:3-25`；`tests/unit/replay/test_process.py:128-148, 300-323`
- **判据**：Replay spec §2 要求 capture source，且 source eligibility 由 History/Capture capability 决定；本次复核范围明确要求核对 source-bound capability。
- **证据**：`ReplaySourceGrant`、`ReplayRequest.source_grant` 和 `CaptureCapabilities` 均是公开、可直接构造的值对象。`_validate_source_grant()` 只比较 grant 与同一调用者提供的 request 的 `entry_id`、path、ref，再信任 grant 中自带的 capability；它不读取或解析任何 History entry，也没有不可伪造的 source receipt。现有测试同样是手工构造 grant。一次不落盘 probe 使用实际临时 capture、一个不存在的 History source 和自行构造的 matching/eligible grant，semantic executor 仍被执行。
- **影响**：调用方只要能指定 capture path，就能把历史中 `none`、`corrupt` 或不具 replay eligibility 的 source 宣称成 eligible，绕过这次新增的 History capability gate。名称中的 “grant/authorization” 与实际信任根不一致，source-bound 约束只是在同一份可控输入内自洽。
- **建议修复**：让 process 只接受由受控 History resolver 解析出的不可伪造 source handle，或在 `run()` 内以 `source_entry_id`/`capture_ref` 向 History source 查询并验证 capability 与 capture binding；不要把可由调用者填充的 dataclass 当作 capability grant。

#### RCR-02 — source read 的 deadline 只能在一次同步读取结束后发现已超时，不能约束慢的首个/任一 I/O 或 decode

- **primary_location**：`src/app/replay/process.py:342-358`
- **related_locations**：`tests/unit/replay/test_process.py:631-659`
- **判据**：Replay spec §4 要求 deadline 在 source read 前建立，offline local read/decode/summary 在预算内逐步检查，超时后停止继续处理。
- **证据**：`for record in iter_raw_capture_records(...)` 先调用 iterator 的 `next()`，然后才在 loop body 的第 355 行检查剩余时间；首次记录前的 open/decompress/decode 和每个下一记录读取都不可中断，且直接阻塞 event loop。focused test 只验证慢 reader 返回后报告 deadline，并不验证 deadline 能在读取期间停止。一次不落盘 probe 的单次 `next()` 阻塞约 50ms，而请求 deadline 为 1ms；`deadline_exceeded` 只在读取返回约 50ms 后才发生。
- **影响**：损坏、慢速或大的离线 source 可以把 synchronous replay 卡在 deadline 之外；“deadline pre-I/O” 成为事后检测而非预算约束，也不能满足取消/不继续后台 replay 的时限语义。
- **建议修复**：在 deadline-aware worker/thread 中执行每段 blocking source read/decode，并以 remaining budget 等待；到期时停止消费、等待/取消受控工作且不派生后台 replay。至少应把 reader 的可中断边界设计成接受 deadline/cancellation，而不是在 `next()` 返回后再检查。

#### RCR-03 — `ReplayResult.as_dict()` 本身未执行安全 projection，公开构造的 result 会原样输出 body/header/credential/action arguments

- **primary_location**：`src/app/replay/process.py:87-127`
- **related_locations**：`src/app/replay/__init__.py:3-25`；`src/app/replay/process.py:518-548`；`tests/unit/replay/test_process.py:694-735`
- **判据**：Replay spec §6 要求 default result 的 `diagnostic_records` 与 semantic/live `output` 为 credential-free schema；不得包含 body、headers、raw payload、credentials 或 client action arguments。本次范围也明确要求 `ReplayResult.as_dict` 安全。
- **证据**：虽然后者的 process path 用 `_safe_executor_output()` 与 `_client_actions()` 清理 executor result，`ReplayResult` 被公开 re-export，且 `as_dict()` 在第 124-126 行直接返回构造时给入的 action、output 和 diagnostics mapping。一次不落盘 probe 直接构造该公开 type，确认所有不允许字段都会被 JSON serialization 原样保留。现有测试只覆盖 `ReplayProcess.run()` 产生的 result，未覆盖 `ReplayResult.as_dict()` 的 contract。
- **影响**：任何把 `ReplayResult` 作为 process/CLI integration boundary 或未来 executor adapter 直接构造的调用点，均可把完整 evidence 或 credentials 放进默认输出，破坏 fail-closed 的 result boundary。
- **建议修复**：将 unsafe storage type 私有化，并在 `ReplayResult` 构造/`as_dict()` 处总是以 allowlist 重新投影 action、output 与 diagnostic record；补充直接构造及 nested alias 字段的 regression test。

#### RCR-04 — History per-attempt matrix 从 response timing summary 推断 request/header/boundary 完整性，不能表示 Raw spec 所要求的实际 wire evidence

- **primary_location**：`src/app/history/entry.py:220-247`
- **related_locations**：`src/app/observability/request_log.py:117-132`；`src/app/observability/request_trace.py:243-259, 350-389`；`tests/unit/history/test_history_entry.py:173-235`
- **判据**：History spec §4 与 Raw Capture spec §4.1 要求 `upstream_attempts[]` 对每个 attempt 记录 request/response/boundary completeness 和 `wire_diagnostic_eligible`；wire eligibility 还必须验证所选 attempt 的 request/response headers、body、explicit boundaries。
- **证据**：`UpstreamBodyAttempt` 只记录 response body timing/status/outcome，不携带 upstream request/response header presence、request body completeness 或 capture boundary facts。`_capture_capabilities()` 却把 `status_code is not None` 写成 `request_complete`，把 `outcome == "complete"` 同时写成 response/boundaries complete，并据此发放 per-attempt wire grant。unit test 固化了这套推断；不存在将 Raw capture attempt evidence 投影进 History matrix 的路径。process 的额外 raw-record check 能在运行时挡住缺 headers 的 wire replay，但不能修正 History 读取面已发布的错误 capability，且错误 grant 会先通过其 capability gate。
- **影响**：HistoryIndexEntry 的 attempt matrix 不可信，UI/调用方会把未被记录的 header/body/boundary 条件显示为 complete/eligible；source capability 不能成为 wire grant 的权威来源，破坏本轮声称完成的 attempt-matrix binding。
- **建议修复**：由 RawCaptureObservation/CaptureAttachment 产生并持久化真正的 per-attempt evidence facts（至少 request/response headers、body、boundaries 的完成状态），再直接投影到 `CaptureAttemptCapabilities`；在缺失这些事实时 fail closed，而不是从 response timing 推断。

### 已核对且未发现偏差的承重面

- `none`/`corrupt`：`CaptureCapabilities.replay_rejection_code()` 分别稳定拒绝；`incomplete` 不再跨 mode 一刀切，semantic/live 由 client request 与各自 eligibility 决定。
- wire evidence：process 对 selected attempt 再检查 request/response header 为 mapping、response body、两个 completion boundary；缺 header、错误 type、缺 body 的 focused tests 均通过且被拒绝。
- process-produced semantic/live result：executor payload 经过 allowlist projection，client action 仅保留 type/name；focused tests 覆盖了 body/header/credential/transport/action arguments 的剔除。
- 直接 History read projection：`HistoryIndexEntry.as_dict()` 不包含 semantic payload 或 transport payload；不落盘临时 archive probe 验证 index read 后 default projection 不含 semantic request/response。`include=semantic` 才调用 cold semantic payload read。

## 执行与搜索面

- 阅读了 Replay、History、Raw Capture ACTIVE specs 的 source/capability、deadline、result/projection 条款。
- 阅读并核对了范围内 replay process/export、HistoryEntry/capability、History route/index projection、focused unit tests；为解释 attempt matrix 的数据来源，最小化读取了 `UpstreamBodyAttempt` 与其 request-trace 构造。
- 已执行：`uv run pytest -q --no-header tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py tests/unit/history/test_history_routes.py`，53 passed。
- 已执行：范围文件 `ruff check`，All checks passed；范围文件 `pyright`，0 errors / 0 warnings / 0 informations。
- 已执行不落盘 probes：慢 source-read deadline、直接 `ReplayResult.as_dict()` serialization、incomplete mode matrix、persisted default History index projection、forged matching source grant。probes 仅使用临时目录/内存对象，未打印正文或秘密。
- 未审：Replay CLI exposure、History archive/durability 的其它行为、raw-capture writer/reader 的独立实现、provider pipeline，及与本能力无关的现有 WIP。
