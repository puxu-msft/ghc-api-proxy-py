# RCR-04 Capture Attempt Capability Review

## Review scope

**Boundary:** independent, read-only review of the current final RCR-04 changes in
`src/app/observability/raw_capture.py`; capture observation/projection and direct
request-completion/trace facts; `src/app/history/entry.py` and
`src/app/history/writer.py` direct projections; `src/app/replay/process.py` attempt
gate; and the related Raw Capture, History, Replay, and Observability specifications,
deferred records, and focused unit tests.

**Excluded:** unrelated dirty working-tree changes, full pipeline/provider integration
outside the direct fact handoff, deployment/auth policy, and deferred work explicitly
retained by the reviewed specifications.

## Overall verdict

**Changes requested.** The writer-acknowledged per-attempt matrix, History
round-trip, and source-bound replay gate are substantially implemented and the
focused test/static suites pass, but malformed header inputs are normalized into
synthetic empty header maps and are then treated as real acknowledged header
evidence. That violates the fail-closed evidence contract.

**Blocker count: 0.**

## Findings

### RCR04-001 — Invalid header values can grant wire diagnostic capability

- **Severity:** minor
- **Primary location:** `src/app/observability/raw_capture.py:31-52`,
  `_capture_headers()`
- **Related locations:** `src/app/observability/raw_capture.py:165-173`,
  `_capture_event_evidence()`; `src/app/observability/raw_capture.py:647-706`,
  `upstream_request_start()` / `upstream_response_start()`
- **Criterion:** Raw Capture Spec v28 §4.1 requires every matrix fact to come from
  writer-acknowledged corresponding raw frames; a missing or type-invalid field is
  false. It specifically distinguishes an actually observed empty mapping from no
  header evidence.
- **Evidence:** For a non-`None` value, both upstream-start methods store
  `headers=_capture_headers(headers)`. `_capture_headers("invalid")` returns `{}`;
  after writer acknowledgement, `_capture_event_evidence()` only tests whether the
  stored value is a mapping and therefore marks `headers_available=True`. A
  non-persistent probe completed an otherwise full attempt with
  `headers="invalid"` and observed both
  `request_headers_available=True` and `wire_diagnostic_eligible=True`.
- **Impact:** A malformed/unrepresentable header value is indistinguishable from
  an actually captured empty header mapping. A complete-looking attempt can thereby
  pass the wire gate without evidence that request or response start headers existed
  in the captured transport exchange.
- **Requested remediation:** Preserve whether the input was a valid observed
  header container separately from its serialized header map, and set
  `headers_available` only for valid mappings or valid header-pair iterables
  (including a genuinely empty one). Add committed-writer regressions for invalid
  request and response header inputs; both must deny wire diagnostic replay.

## Verification and coverage

### Executed checks

- `uv run pytest tests/unit/observability/test_raw_capture.py
  tests/unit/observability/test_full_header_capture.py
  tests/unit/observability/test_request_completion.py
  tests/unit/history/test_history_entry.py tests/unit/history/test_writer.py
  tests/unit/replay/test_process.py --no-cov -q` — **142 passed**. The 13
  warnings are Python 3.14 `fork()` deprecation warnings in Replay source-read
  tests, not test failures.
- `uv run ruff check src tests` — **passed**.
- `uv run pyright src tests` — **0 errors, 0 warnings, 0 informations**.
- Non-persistent temporary-directory/direct-object probes:
  1. fully committed attempt admitted for wire diagnostics;
  2. missing request headers denied for wire diagnostics;
  3. partial response/attempt denied for wire while a complete client request
     remained semantic-eligible;
  4. queued but unacknowledged frames remained `pending` and wire-ineligible;
  5. an actual migrated old SQLite index row with no attempt-matrix column
     denied wire diagnostic replay;
  6. a request selecting an ungranted attempt was denied from its
     source-bound History receipt before the capture reader ran.

### Requirement cross-check

- RawCapture records attempt facts only from successful writer acknowledgements;
  the request-completion handoff calls `finish()` before freezing its
  `RawCaptureObservation`.
- The matrix requires attempt/request/response starts, both header/body facts,
  response-end completion, and attempt-end completion; a valid complete attempt,
  missing-header attempt, and partial attempt were each exercised.
- History serializes/deserializes the safe per-attempt matrix, and the focused
  round-trip test asserts that the index projection contains capability facts and
  references rather than raw body/header/credential fields.
- Replay validates the source-bound History receipt and selected attempt matrix
  before reading the capture; legacy rows lack a matrix and therefore
  fail-closed for wire mode. Semantic/live remain gated by a complete client
  request instead of an upstream wire attempt.

### Sources examined

Normative criteria: Raw Capture Spec v28 and deferred record; History Spec v4
and deferred record; Replay Spec v4 and deferred record; Observability Spec v2.
Implementation/test surface: the six scoped production files named in the
review boundary plus the requested raw, full-header, request-completion, History
entry/writer, and Replay process unit tests.

The review did not re-audit unrelated dirty files or unmodified provider/pipeline
producers beyond locating their direct capture calls; their end-to-end transport
behavior is outside this focused RCR-04 review.
