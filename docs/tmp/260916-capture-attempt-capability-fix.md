# RCR-04 capture attempt capability fix

日期：2026-09-16

## 进度账本

| 阶段 | 状态 | 依据 |
|---|---|---|
| 读取 current Spec 与现有 WIP | done | Raw Capture v28、History v4、Replay v4、Observability v2 |
| 建立 RawCapture per-attempt evidence projection | done | RCR-04 |
| 接通 History async projection 与 Replay gate | done | RCR-04 |
| 回归与静态验证 | done | 89 focused tests、Ruff、Pyright |

## 约束与范围

- 只修改用户允许的 RawCapture、直接 capture facts projection、History entry/writer、Replay process、对应单元测试，以及直接 Raw/History/Replay Spec/deferred 文档。
- 普通 History projection 不包含 raw body、headers 或 credentials。
- capability 必须来自每个 attempt 的 RawCapture evidence；不得以 `UpstreamBodyAttempt` 的 response timing 推断 request/header/boundary completeness。

## 实施结果

### RawCapture 到 RequestFacts

- queued raw frame 携带无敏感内容的 `_CaptureEventEvidence`；只有 writer acknowledgement 成功时，`RawRequestCapture` 才把 event 投影到该 attempt 的 capability state。
- `RawCaptureAttemptObservation` 逐项表达 attempt/request/response start、request/response headers/body、response end、attempt end；任意字段缺失、未提交或明确不完整均为 false。
- `wire_diagnostic_eligible` 由同一 matrix 的全部必要事实重新计算；client semantic/live eligibility 只要求完整的 captured client request，且 `pending`/`corrupt` 保持 fail-closed。
- `upstream_request_start(headers=None)` 不再捏造空 header map；真实 transport 提供 headers（包括真实空 mapping）时才记录 headers evidence。

### History 与 Replay

- `HistoryEntry` 和 `HistoryIndexEntry` 投影/持久化逐 attempt matrix，不带 raw body、headers 或 credentials；读取缺少新字段的旧 index row 时一律投影 false。
- `CaptureAttemptCapabilities.__post_init__` 根据 matrix 重算 wire eligibility，拒绝把存储的 standalone boolean 当成可放行事实。
- Replay 的 source receipt 先按 selected attempt 的 History matrix fail-closed gate；capture reread 只确认 selected attempt 存在/可读，不再以 response timing 或零散 raw events二次猜测 completeness。semantic/live 继续只按 client request capability gate。

### 回归

- 新增完整 attempt 与缺 headers、partial attempt 的 committed-raw-evidence regression，覆盖 matrix、wire 与 semantic/live 的分离。
- History entry projection 和 async writer round-trip 覆盖 multi-attempt safe matrix，断言普通 projection 的 capture schema 不含 raw transport 字段。
- Replay regression 覆盖选中 ungranted/incomplete attempt 在 source read 前以 `source_capability_denied` 拒绝；完整 selected attempt 仍可离线 wire diagnostic。

## 文档处置

- Raw Capture Spec 升至 v28、History Spec 升至 v4、Replay Spec 升至 v4，明确 evidence authority 和 fail-closed source gate。
- 已从 deferred 移除 HIS-D-02 与 RPL-D-04；本报告保留完成依据。未采纳的 Raw Capture D-3 等长期项未变更。

## 验证

在 `/home/xp/src/ghc-api-proxy-py` 运行：

```text
uv --directory /home/xp/src/ghc-api-proxy-py run pytest /home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_raw_capture.py /home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_full_header_capture.py /home/xp/src/ghc-api-proxy-py/tests/unit/history/test_history_entry.py /home/xp/src/ghc-api-proxy-py/tests/unit/history/test_writer.py /home/xp/src/ghc-api-proxy-py/tests/unit/replay/test_process.py
87 passed, 13 warnings

uv --directory /home/xp/src/ghc-api-proxy-py run ruff check /home/xp/src/ghc-api-proxy-py/src /home/xp/src/ghc-api-proxy-py/tests
All checks passed!

uv --directory /home/xp/src/ghc-api-proxy-py run pyright /home/xp/src/ghc-api-proxy-py/src /home/xp/src/ghc-api-proxy-py/tests
0 errors, 0 warnings, 0 informations
```

Replay focused tests 的 13 条 warning 来自 Python 3.14 对多线程进程中 `fork()` 的 `DeprecationWarning`；测试和静态检查均通过，且该 process isolation implementation 不在本次 RCR-04 行为变更范围内。

## RCR04-001 follow-up（2026-09-16）

- `_capture_headers()` 现在返回 `dict[str, str] | None`：有效 mapping 或每个元素均为二元 pair 的 iterable（包含真正的空 mapping/iterable）返回 mapping；`None`、string/bytes、错误 pair、抛出迭代/字符串化错误的输入返回 `None`。
- capture event 只有在上述结果是 mapping 时才包含 `headers`。因此有效空 headers 仍会记录为 `{}` 并在 writer acknowledgement 后成为 evidence；invalid/malformed input 不写伪造 `{}`，`_capture_event_evidence` 也只认可同一 valid-header predicate。
- 新增参数化 committed-writer regression：分别使 request headers 或 response headers malformed，断言 start 仍被记录、对应 `headers_available=false`、wire eligibility fail-closed，且 capture raw record 不含伪造 `headers`。另一侧的真实空 mapping 仍为 available。
- follow-up 验证：focused suite `89 passed, 13 warnings`；Ruff `All checks passed!`；Pyright `0 errors, 0 warnings, 0 informations`。
