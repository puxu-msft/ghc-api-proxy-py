# RCR-04 Raw Capture Per-Attempt Final Review

## Review scope

**Boundary:** read-only final review of the current RCR-04 raw-capture per-attempt capability matrix and its direct History/Replay projections: `raw_capture.py`, `capture_observation.py`, direct request trace/completion handoff, `history/entry.py`, `history/writer.py`, `replay/process.py`, and their focused tests and normative Raw Capture, History, Replay, and Observability specifications.

**Explicitly excluded:** unrelated dirty working-tree changes; provider/pipeline paths beyond the direct capture handoff; History transport authorization; deployment; and deferred work outside the matrix/projection/replay-gate contract.

## Overall verdict

**Pass.** No blocker, major, minor, or nit finding was identified in the reviewed RCR-04 scope. RCR04-001 is closed in the final state: valid empty header containers remain evidence, while invalid header inputs neither synthesize an empty map nor grant wire capability.

**Blocker count: 0.**

## Criteria and final-state cross-check

| Required property | Result | Evidence |
|---|---|---|
| Writer acknowledgement is the authority for matrix facts | Pass | `RawRequestCapture` adds a fact only from `note_writer_frame_completed(..., drop_reason=None)`; `finish()` appends `request.end`, waits for all accepted writer receipts, then freezes the observation. `RequestCompletionCoordinator.publish()` calls `finish()` before it forms immutable `RequestFacts` and History handoff. |
| Valid empty headers differ from invalid headers | Pass | `_capture_headers()` returns `{}` for a valid empty mapping/pair iterable but `None` for absent, string/bytes, malformed pairs, iteration failures, or conversion failures. Only a non-`None` result reaches the raw event; acknowledged evidence uses the same predicate. The focused committed-writer regression exercises invalid request and response values. |
| Per-attempt matrix is complete and fail-closed | Pass | Attempt start; request start/header/body; response start/header/body/end; and attempt end are independently recorded from committed evidence. `RawCaptureAttemptObservation.wire_diagnostic_eligible` and `CaptureAttemptCapabilities.__post_init__` require every necessary fact; an incomplete boundary overrides a prior complete bit. |
| Queue, write failure, partial write, and poisoned path cannot create false completion | Pass | Queued/unacknowledged evidence remains non-authoritative; failed/dropped frames disable capture and preserve a stable incomplete reason. Short writes poison the shared path, roll back the unwritten reservation, and reject later frames. Focused tests cover queue capacity, writer error, partial write, restart validation, and poison isolation. |
| History carries only the safe matrix/reference projection | Pass | `HistoryEntry` and `HistoryIndexEntry` serialize capability scalars, attempt facts, and `capture_ref`, not raw headers/bodies/credentials. The History round-trip test asserts the public capture projection's exact safe field set. |
| Legacy index rows fail closed | Pass | Schema migration supplies defaults for absent capability columns and `[]` for the absent attempt matrix. The replay decision additionally requires a matching selected eligible attempt. A metadata-only probe against the actual pre-RCR table schema yielded an empty matrix and `source_capability_denied` for both wire and semantic gates. |
| Replay wire gate consumes the selected source receipt matrix | Pass | Replay validates the History-authorized receipt and selected `attempt_id` before capture read. It requires both top-level wire eligibility and that selected attempt's derived matrix eligibility; the later source read merely confirms the selected attempt exists. Focused tests assert denial before the reader for an ungranted attempt. |
| Partial capture may remain semantic/live-eligible without becoming wire-complete | Pass | The raw observation and replay gate reject `pending`/`corrupt`, permit semantic/live only when their client-request facts permit them, and require a complete selected attempt for wire diagnostic. Focused tests cover a complete first attempt plus a partial second attempt and incomplete-but-semantic/live-eligible captures. |

## RCR04-001 disposition

**closed.** The prior defect normalized malformed header containers to synthetic empty maps. The current code omits the `headers` field for invalid input, retains a genuine empty map for valid empty input, and commits `headers_available` only after successful writer acknowledgement. The metadata-only malformed-response probe returned: valid empty request headers `true`, invalid response headers `false`, and wire eligibility `false`; its persisted start-event metadata contained no response `headers` field.

## Verification performed

- `uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_full_header_capture.py tests/unit/observability/test_request_completion.py tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py tests/unit/replay/test_process.py --no-cov -q` — **144 passed**; 13 Python 3.14 `fork()` deprecation warnings in Replay source-read tests, with no test failure.
- `uv run ruff check src tests` — **passed**.
- `uv run pyright src tests` — **0 errors, 0 warnings, 0 informations**.
- Metadata-only probe: valid empty request headers plus malformed response headers produced a complete capture overview but a false response-header fact and false wire gate; persisted event-shape metadata contained no fabricated response-header field.
- Metadata-only migration probe: instantiated the actual pre-RCR `history_entries` schema, let the current writer migrate it, and read its capability projection. The resulting matrix length was zero and both wire and semantic replay gates denied the legacy row.

## Search surface and limits

Read normative Raw Capture v28, History v4, Replay v4, and Observability v2 specifications; the immediately preceding RCR-04 review and fix record; all scoped production modules; the focused Raw Capture/full-header/request-completion, History entry/writer, and Replay tests; and the pre-RCR History schema used by the compatibility probe.

No file was changed other than this requested review report. Excluded surfaces remain unrelated dirty changes, providers/pipeline behavior beyond their direct capture handoff, History transport authorization, deployment, and deferred work outside the specified capability-matrix/History/Replay scope.

## Findings

No findings.
