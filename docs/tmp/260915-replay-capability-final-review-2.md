# Replay capability 最终只读评审（第 2 轮）

## 评审范围

评审时点为 2026-09-15 UTC。范围严格限于最终工作树中的 `src/app/replay/process.py`、`src/app/replay/__init__.py`、`src/app/history/entry.py` 的直接 projection、`tests/unit/replay/test_process.py`、`tests/unit/history/test_history_entry.py`，以及 `.dev/docs/replay/spec.md`、`.dev/docs/history/spec.md`、`.dev/docs/raw-capture/spec.md` 三份直接 Spec。

明确不评 raw-capture writer、History writer/archive、routes、CLI、providers、config、集成测试与范围外并发 WIP。未修改被评代码或测试；唯一持久化写入是本报告。

## 总体 verdict

**needs-fix。** 上轮 `REPLAY-CAP-FINAL-01` 的 wire-diagnostic 默认 summary 已按 Spec 收敛，`REPLAY-CAP-01` 的非有限 deadline pre-I/O 拒绝、`REPLAY-CAP-02` 的 grant/request source binding，以及 `REPLAY-CAP-03` 的 `none` source 拒绝均可独立核验为闭合。

不过，最终系统仍有五个 major：`incomplete` status 被错误地作为 semantic/live 的绝对否决；History capability projection 丢失 per-attempt matrix；wire 的 structural gate 不验证 headers；offline source read 不受 deadline 约束；semantic/live executor 的任意 `output` 被原样放进 `ReplayResult.as_dict()`。

## Blocker 数

**0。** 当前发现：major 5、minor 0、nit 0。

## 判据与承重面

- Replay Spec §2、§4、§6：replay 只能由 capture source 启动；selector 必须明确；mode 都有同步 deadline，offline diagnostic 必须受独立 local read/CPU deadline；默认 result 不能输出 raw transport。
- History Spec §1、§4：History capability 是 replay 的 authority；`capture_status=complete` 不能替代 capability matrix；matrix 必须带 `upstream_attempts[]` 的逐 attempt completeness。
- Raw Capture Spec §4.1：`none | pending | complete | incomplete | corrupt` 是总览状态而非所有 mode 的单一 gate；request body 完整、response partial 的 capture 仍可允许部分 semantic/live source；完整 wire diagnostic 必须有 request/response/boundary evidence。
- 调用方指定的核对点：source/capability binding、finite deadline pre-I/O、`none`/`incomplete`/`corrupt`、wire complete gate，以及 `ReplayResult.as_dict()` 不含 raw body、headers 或 credentials。

前序 review/fix 文档只作为待核验 claim，不作为判据或结论来源。

## 前序项的独立闭合度

| 项目 | 状态 | 最终证据 |
| --- | --- | --- |
| `REPLAY-CAP-01` | closed（仅“finite pre-I/O validation”这一命题） | `process.py:155` 在 reader 前调用 `_validate_request()`；`process.py:267-273` 使用 `math.isfinite()` 和上下界；focused test 参数化 NaN/±Inf 并将 reader/executor 替换为 fail-fast stub。 |
| `REPLAY-CAP-02` | closed | `ReplaySourceGrant` 绑定 entry/path/ref；`process.py:304-312` 在 reader 前拒绝任一不匹配；focused test 覆盖三个交换维度。 |
| `REPLAY-CAP-03` | closed（`none`） | `entry.py:51-52` 将 `none` 稳定映射为 `source_content_unavailable`，`process.py:314-333` 在 source read 前执行。 |
| `REPLAY-CAP-FINAL-01` | closed | `process.py:162-181,444-466` 使用安全 summary；focused wire test 断言 records 仅有 `event`、`attempt`、`status_code`、`complete`、`body_bytes`，且序列化不含 `body`/`headers`。 |

`corrupt` 同样在 reader 前稳定拒绝（`entry.py:49-50`）。下列 findings 是抛开上述清单重新检查最终系统所得；其中 deadline finding 不否定 `REPLAY-CAP-01` 的狭义 finite-validation 闭合，而是指出 ACTIVE Replay Spec 尚未落地的完整 deadline contract。

## Findings

### replay-incomplete-status-veto — `incomplete` 错误封死仍具 replay capability 的 semantic/live source

- **severity:** major
- **primary_location:** `src/app/history/entry.py:47-65`
- **related_locations:** `src/app/replay/process.py:292-333`; `tests/unit/replay/test_process.py:182-211`; `tests/unit/history/test_history_entry.py:164-213`; `.dev/docs/history/spec.md` §4; `.dev/docs/raw-capture/spec.md` §4.1

**证据：**

1. `CaptureCapabilities.replay_rejection_code()` 在检查 mode-specific capability 之前，对每个非 `complete` 且非 `none`/`corrupt` status 直接返回 `source_capture_incomplete`。
2. 两份 ACTIVE Spec 都明确 `capture_status=complete` 不是 capability matrix 的替代；特别是 client request 完整、response partial 的 capture 可以支持部分 semantic/live source。
3. focused test 明确将 `status="incomplete"` 但 semantic capability 为 true 的 source 期待为拒绝，故当前全绿实际上固化了与 Spec 相反的语义。
4. 受控内存 probe 以完整 client request、`status="incomplete"`、semantic/live capability=true 调用 process，得到 `source_capture_incomplete`，未进入 executor。

**影响：** 一次 response-side 或不相关 attempt-side evidence 不完整会错误剥夺仍有完整 client request 的 semantic/live diagnostic/replay 能力；History capability matrix 退化为单一状态 gate，无法表达 Spec 要求的部分可用性。

**闭合要求：** 只让 `none` 和 `corrupt` 成为跨 mode 的状态否决；wire 继续要求其自身完整 attempt capability，semantic/live 按其对应 eligibility 加完整 client-request evidence 决定。加入 `incomplete + client request complete + semantic/live eligible` 的允许回归，以及其反向拒绝组。

### replay-attempt-capability-projection-gap — History projection 未保留逐 attempt capability matrix

- **severity:** major
- **primary_location:** `src/app/history/entry.py:38-45`
- **related_locations:** `src/app/history/entry.py:122-130,159-166`; `tests/unit/history/test_history_entry.py:134-161`; `.dev/docs/history/spec.md` §4; `.dev/docs/raw-capture/spec.md` §4.1

**证据：**

1. `CaptureCapabilities` 只保存 capture-wide status、两个 client availability flag 和三个 aggregate replay eligibility bool；没有 `upstream_attempts[]` 或 attempt ID 到 request/response/boundary completeness 的任何字段。
2. `HistoryEntry.from_request_facts()` 和 `as_dict()` 只能复制这组 aggregate 字段。当前 unit test 的期望 projection 也正是该缺失 attempt matrix 的 shape。
3. History Spec 和 Raw Capture Spec 都规定每个 upstream attempt 必须独立表达 request/response/boundary completeness；这也是 explicit `upstream_attempt(attempt_id)` selector 应由 authority 判断的事实。

**影响：** History 无法把 capability authority 绑定到所选 attempt。process 虽另行扫描 capture records 作 best-effort structural check，但 grant 本身不能说明“这个 selected attempt”为何 eligible；这破坏了 capability/source binding 的逐 selector 粒度，并使历史查询面无法呈现规范要求的 matrix。

**闭合要求：** 将逐 attempt completeness/eligibility 加入 RawCapture-to-History direct projection、`CaptureCapabilities` 和其 safe `as_dict()` shape，并让 wire grant 对 selected `attempt_id` 作 capability 判断；为多个 attempt（一个完整、一个不完整）的 history projection 和 selector gate 加回归。

### replay-wire-header-completeness-gap — wire gate 把无 headers 的 attempt 当作完整 evidence

- **severity:** major
- **primary_location:** `src/app/replay/process.py:397-429`
- **related_locations:** `src/app/replay/process.py:386-394`; `tests/unit/replay/test_process.py:261-300`; `.dev/docs/replay/spec.md` §2.2; `.dev/docs/raw-capture/spec.md` §4.1

**证据：**

1. `_attempt_complete()` 只检查 event name 和 response/attempt end 的 `complete=true`；它既不要求 `upstream.request.start` 含 headers，也不要求 `upstream.response.start` 含 headers。
2. Raw Capture Spec 将每个 upstream attempt 的 request/response headers、body 和 boundary completeness 列为 full transport evidence；Replay Spec 要求 attempt request/response/boundary 不完整时拒绝 wire diagnostic。
3. focused wire test 的 fixture 始终提供 headers，测试只验证已成功路径的 summary 字段；没有移除 request 或 response headers 的 structural negative case。
4. 受控内存 probe 提供所有当前 `_attempt_complete()` 所需 events、但不提供 request/response headers，`wire_diagnostic` 仍返回 `completed`。

**影响：** 损坏、截断或不完整的 attempt 可被报告为完整 wire diagnostic 成功，违背 source evidence gate。`REPLAY-CAP-FINAL-01` 的 result 脱敏已正确，但不能替代完整性判定。

**闭合要求：** 将 event 的必需结构（至少 headers presence/type、body evidence 和显式 boundary semantics）纳入 selected-attempt validation，或以 History 中逐 attempt capability 作等价权威 gate；增加 no-request-headers、no-response-headers、no-body 的拒绝回归。

### replay-offline-deadline-not-enforced — source read 发生在 deadline 起算和任何 timeout 之外

- **severity:** major
- **primary_location:** `src/app/replay/process.py:155-160,336-383`
- **related_locations:** `src/app/replay/process.py:206-219`; `tests/unit/replay/test_process.py:381-425`; `.dev/docs/replay/spec.md` §4

**证据：**

1. 虽然 `_validate_request()` 正确在 source read 前拒绝 non-finite deadline，`_read_source()` 随后同步、无预算地遍历完整 capture 并构建 tuples；`deadline_at` 直到 read 完成后才计算。
2. `asyncio.wait_for()` 仅包围 semantic/live executor，wire diagnostic 从不经过 timeout，且 source reader 也不受 timeout。
3. Replay Spec 要求所有 mode 有 deadline，offline diagnostic 受独立 local read/CPU deadline，且 HTTP return/cancel 后不得继续后台执行。
4. 受控内存 probe 令 reader 比 `deadline_s` 更慢；`wire_diagnostic` 仍在 reader 返回后以 `completed` 结束，证明 offline deadline 被绕过。probe 不写文件且不输出 capture 内容。

**影响：** 一个很小且合法的 deadline 并不限制 capture IO/decoding 或 wire diagnostic；大文件、阻塞文件系统或异常 decoder work 可超出调用方的同步时间预算。

**闭合要求：** 在任何 source IO 前建立 mode-appropriate deadline budget，并把 local read/decode/diagnostic work 纳入可执行的 cancellation/timeout strategy；明确 executor 可用的剩余 budget。增加 slow-reader/slow-decoder 的 wire 和 semantic/live deadline regression，不能只测试 NaN/∞ 的 pre-I/O validation。

### replay-result-output-unsanitized — semantic/live executor 可以经默认 `as_dict()` 输出 raw fields

- **severity:** major
- **primary_location:** `src/app/replay/process.py:105-127,250-258`
- **related_locations:** `tests/unit/replay/test_process.py:303-330`; `.dev/docs/replay/spec.md` §6; `.dev/docs/raw-capture/spec.md` §4

**证据：**

1. semantic/live 成功路径把 executor 返回的任意 mapping 以 `dict(output)` 保存；`ReplayResult.as_dict()` 原样返回其 `output`。
2. `ReplayExecutor` 的类型仅约束为 `Awaitable[object]`，没有 result schema、allowlist 或 raw-transport sanitizer。
3. 受控内存 probe 让 executor 返回带 `body`、`headers`、`credentials` 字段的 mapping；对 `result.as_dict()` 的结构检查确认三个字段均可见。probe 只输出布尔结论，不打印测试值或任何 capture 内容。
4. 现有 semantic test 只返回 outcome/client action，未序列化或对抗性检查 executor output；wire test 的安全断言不能覆盖 semantic/live 这条独立通路。

**影响：** 即使 source grant、wire summary 与 ordinary History projection 都正确，任意 semantic/live executor 仍能把 raw transport 或 credentials 混入 default replay result，直接违反调用方给出的 `ReplayResult.as_dict()` 安全契约和 Replay Spec 的 default-result boundary。

**闭合要求：** 让 default result 使用显式、credential-free output schema/projection，或不在 `as_dict()` 交付 opaque executor output；递归拒绝/移除 raw body、headers、credentials 及等价 transport payload。完整 evidence 如确有需要，必须另建显式 sensitive projection 并标记 `contains_credentials=true`。加入 semantic 和 live 的 serialization negative regressions。

## 已核验的其余面

- `ReplaySourceGrant` 的 entry/path/ref 三元比较在 reader 前执行；缺 grant 与错配都不会触发 executor。
- wrong selector、unknown attempt、non-finite/max-exceeding deadline 在 source reader 前稳定拒绝。
- wire-diagnostic 不调用 executor，且其 `diagnostic_records` 现在是安全 summary；该修复不输出 raw header/body。
- `replay/__init__.py` 只重导出 process primitives，没有新增绕过 grant 的 public API。

## 执行、搜索面与限制

执行完成：

```text
uv run pytest -q tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# 32 passed

uv run ruff check src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# All checks passed

uv run pyright src/app/replay/process.py src/app/replay/__init__.py src/app/history/entry.py tests/unit/replay/test_process.py tests/unit/history/test_history_entry.py
# 0 errors, 0 warnings

git diff --check -- <five scoped implementation/test files>
# passed
```

另外运行了一个只在内存中替换 reader/executor 的受控 probe；它只输出 rejection/outcome 与布尔结构结论，不创建 capture、不打印 body、headers、credentials 或其值。该 probe 复现了四个动态 findings：`incomplete` semantic 被拒绝、headers 缺失的 wire 被接受、default result 可见 raw-field keys、offline deadline 被 reader 越过。

阅读面：完整读取五个指定实现/测试文件和三份直接 Spec；读取前序 replay capability 报告仅用于逐项核验其 self-reported closure。未读取或判断 scope 外实现；未运行全仓、集成或真实 upstream tests。focused test、Ruff 与 Pyright 全绿，但现有测试未对上述五条反例具有分辨力。
