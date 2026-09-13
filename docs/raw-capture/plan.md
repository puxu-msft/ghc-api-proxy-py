# Raw capture v23 Implementation Plan

> 本文是 2026-09-09 v23 实现切片的执行记录。当前行为权威已由 2026-09-13 的 ACTIVE v24 `spec.md` 修订；v24 的 full-header capture、History attachment、capability matrix 和 replay 关系是后续设计合同，不被本文的 v23 scoped verification 视为已实现。

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. This plan is executed inline in the current shared worktree; do not use a fresh worktree as the source of truth.

**Goal:** Make rule-selected raw capture preserve every available wire body and report capture completeness truthfully without changing the proxy response when diagnostics fail.

**Architecture:** Keep the existing SQLite rule selector, per-session/agent CBOR Sequence plus zstd writer, and request-completion integration. Separate business attempt outcome from request-level evidence completeness, observe request bytes at the exact provider transport boundary so proxy-owned timeouts cannot discard them, and keep all ordinary diagnostics on fixed safe metadata. The HTTP management surface remains a rule-control API, not a capture reader.

**Tech Stack:** Python 3.14, FastAPI, httpx2, CBOR2, zstandard, SQLite, pytest, Ruff, Pyright.

**Spec at execution:** `.dev/docs/raw-capture/spec.md` ACTIVE v23.  
**Current authority:** `.dev/docs/raw-capture/spec.md` ACTIVE v24.

**Execution status:** Implemented and scoped-reviewed in the shared worktree on 2026-09-09. The semantic patch remains uncommitted because the worktree contains unrelated peer WIP and overlapping mixed-file hunks; integration is explicitly kept for a later coordinated commit.

## Global Constraints

- Capture is opt-in through persisted provider/model/session/optional-agent rules; configuration must not become an all-request switch.
- The file format is RFC 8742 CBOR Sequence with one CBOR map per zstd frame and native CBOR byte strings; never create or append JSONL.
- Capture failures are best-effort and must not alter the proxied response or swallow the original application error.
- Ordinary logs and completion records may contain only request IDs, fixed event/reason values, exception types, status metadata and completeness booleans; no body, header, token, raw identity or exception text.
- A failed or discarded upstream attempt may have `complete=false` as an attempt result while the request-level capture remains complete if its actual wire evidence is committed.
- Only a partial body boundary, a capture drop, or an incomplete client request may make the request-level capture incomplete.
- Directory-level `max_total_bytes` does not exist; only the per-file compressed-byte quota remains.
- Do not run `ruff format`; use `ruff check` only.
- Do not use broad staging or reset operations in the shared worktree; preserve unrelated peer changes.

## File Map

- `src/app/observability/raw_capture.py`: capture event state, committed-event accounting, safe writer diagnostics, request-boundary context and transport request observation.
- `src/app/pipeline/direct_driver/base.py`: establish the per-attempt capture context around provider sends and preserve fallback failure evidence.
- `src/app/pipeline/driver.py`: establish the same context for count_tokens and defer buffered response completion until cleanup is known.
- `src/app/model_provider/ghc_client/client.py`: activate the capture context only around the SDK inference request, after token/auth preparation, and install the request hook on the shared httpx client.
- `src/app/model_provider/openai_compatible/client.py`, `src/app/model_provider/xingchen/client.py`, `src/app/model_provider/codebuddy_client/client.py`: observe the exact built request immediately before their upstream HTTP send.
- `src/app/server/routes/inference.py`: keep unknown exception details type-only in ordinary completion projection.
- `src/app/server/routes/ops.py`: return a stable JSON service-unavailable response when the rule store is absent.
- `tests/unit/observability/test_raw_capture.py`: unit-level completeness, safe warning, deduplication and transport-observer controls.
- `tests/int/test_pipeline_app.py`: black-box retry, timeout and rule-selected wire evidence.
- `tests/int/test_pipeline_ops_routes.py`: management API unavailable response control.
- `tests/unit/pipeline/test_timeout_enforcement.py`: direct-driver timeout capture control where a fake provider exposes the request bytes it handed to transport.
- `.dev/docs/raw-capture/spec.md`: v23 contract used by this execution record; current authority is ACTIVE v24.
- `.dev/docs/raw-capture/raw-capture-review-disposition.md`: finding-by-finding evidence and final dispositions.

---

### Task 1: Separate attempt outcomes from request-level capture completeness

**Files:**
- Modify: `src/app/observability/raw_capture.py:RawRequestCapture.upstream_attempt_end`, `RawRequestCapture.finish`, `RawRequestCapture.note_writer_frame_completed`, and event-state initialization.
- Test: `tests/unit/observability/test_raw_capture.py`.
- Test: `tests/int/test_pipeline_app.py` retry capture test.

**Interfaces:**
- `upstream_attempt_end(attempt: int, *, complete: bool) -> None` continues to write the attempt boundary and keeps `complete` as the attempt outcome only.
- `RawRequestCapture` internally records committed event types from successful writer acknowledgements; this is not exposed as a new public protocol.
- `finish(...)` continues to emit at most one completion warning and derives `response_body_capture_complete` from committed response-body evidence plus known incomplete/drop state.

- [x] **Step 1: Add the reverse-control unit case.** Extend the existing partial-boundary test with a companion case that writes a complete upstream response body and response end, writes `upstream_attempt_end(complete=False)`, then finishes a complete client request; assert the attempt event remains `complete=false` and no completion warning is emitted.
- [x] **Step 2: Add committed-event tracking.** Add a private set of committed event types; update it only when `note_writer_frame_completed` receives no drop reason. Keep dropped and skipped event types in the existing missing set.
- [x] **Step 3: Remove the false request-level escalation.** Stop calling `_note_incomplete` merely because `upstream_attempt_end` receives `complete=False`. Keep `_note_incomplete` on explicit response/body boundary failures and request incompleteness.
- [x] **Step 4: Correct the response completeness predicate.** Report `false` when no response-body event has been committed and the capture is incomplete or dropped; report `true` when the relevant response-body event was committed and only a later non-body event was lost. Preserve `false` for partial response boundaries and writer/quota failures before response evidence.
- [x] **Step 5: Harden immediate writer-preparation warnings.** Replace path/exception interpolation in quota, queue-full and capture-error warnings with request ID, fixed event type, fixed reason, exception type and errno only.
- [x] **Step 6: Run focused tests.** Run `uv run pytest tests/unit/observability/test_raw_capture.py --no-cov -q` and the two rule-selected retry tests with `--log-cli-level=WARNING`; expect the reverse-control warning to be absent while the partial-boundary warning remains present.

### Task 2: Preserve request bytes across proxy-owned timeouts

**Files:**
- Modify: `src/app/observability/raw_capture.py` to add a context-local pending/active capture scope, a safe request observer, and per-attempt duplicate suppression.
- Modify: `src/app/pipeline/direct_driver/base.py` around `_send` / `_run_attempt`.
- Modify: `src/app/pipeline/driver.py` around `ask_upstream`.
- Modify: `src/app/model_provider/ghc_client/client.py` around `_post_openai`, `_post_anthropic` and `GhcApiClient` initialization.
- Modify: `src/app/model_provider/openai_compatible/client.py`, `src/app/model_provider/xingchen/client.py`, and `src/app/model_provider/codebuddy_client/client.py` at their exact request-send boundaries.
- Test: `tests/unit/observability/test_raw_capture.py` and `tests/unit/pipeline/test_timeout_enforcement.py`.
- Test: `tests/int/test_pipeline_app.py` with a short response-header timeout and an async mock transport that records the request bytes before delaying headers.

**Interfaces:**
- Add an internal context manager such as `pending_upstream_capture(capture: RawRequestCapture | None, attempt: int)`; it must be context-local and reset in `finally`.
- Add an internal activation context used only after provider authentication/request preparation is complete; it must not capture token exchange or catalog requests.
- Add an idempotent `observe_active_upstream_request(request: httpx2.Request) -> None` hook that reads only `request.content`, never headers, and never raises into the upstream call.
- Existing `ModelProvider.send` and `count_tokens` public signatures stay unchanged; capture propagation uses the internal context so injected providers remain compatible.

- [x] **Step 1: Write a transport-boundary control.** Unit-test that an active capture context observing an `httpx2.Request` appends exactly one `upstream.request.body` event, including an empty bytes body, and that no active context produces no event.
- [x] **Step 2: Establish the pending context in both drivers.** Wrap the awaited provider send/count call with the attempt-local context; ensure reset happens on success, retry, timeout and cancellation.
- [x] **Step 3: Activate only around inference HTTP sends.** In direct HTTP clients, activate the pending capture immediately before `http_client.send(request)` and deactivate after it returns or raises. In the Copilot SDK client, install one idempotent request hook and activate it only around the SDK POST after `headers_for_interaction` has completed, so authentication traffic is excluded.
- [x] **Step 4: Retain existing response/error fallback without duplicates.** Make `RawRequestCapture.upstream_request_body` ignore a second body observation for the same numbered attempt while retaining the first exact bytes; leave response-attached fallback for clients or test doubles that cannot use the transport hook.
- [x] **Step 5: Add the timeout black-box control.** Use the real pipeline app, a rule-selected request, an async mock upstream that records `request.content` then delays headers, and a short response-header timeout. Assert the upstream saw non-empty bytes and the capture contains exactly those bytes even though the client receives the proxy timeout response.
- [x] **Step 6: Run timeout and provider tests.** Run `uv run pytest tests/unit/pipeline/test_timeout_enforcement.py tests/unit/observability/test_raw_capture.py --no-cov -q` plus the focused integration timeout test; expect existing timeout semantics unchanged and the new capture evidence present.

### Task 3: Make buffered count_tokens cleanup evidence truthful

**Files:**
- Modify: `src/app/pipeline/driver.py:ask_upstream`.
- Test: `tests/int/test_pipeline_app.py` or a focused count-token capture test in `tests/unit/pipeline/test_direct_driver.py`.

**Interfaces:**
- No public API changes. The count attempt must emit one response-end boundary after `response.aclose()` has completed, with `complete` equal to cleanup success, and then emit the attempt boundary with the same cleanup result.

- [x] **Step 1: Add a cleanup-failure control.** Build a count provider response whose `aclose()` raises after a fully buffered body; assert the capture has `upstream.response.end.complete=false`, the attempt projection is incomplete, and the completion warning reports an incomplete forensic capture.
- [x] **Step 2: Move the response-end event.** Keep request/response body events before parsing, but move `upstream_response_end` into the existing `finally` after `aclose` has set `cleanup_error`; use `complete=cleanup_error is None`.
- [x] **Step 3: Keep primary-error precedence.** Preserve the current `primary` exception and `add_note` behavior; only the capture boundary changes. A cleanup error with no primary still propagates as before.
- [x] **Step 4: Run focused count tests.** Run the count capture tests and `uv run pyright src/app/pipeline/driver.py src/app/observability/raw_capture.py`.

### Task 4: Keep ordinary failure diagnostics safe and management errors explicit

**Files:**
- Modify: `src/app/server/routes/inference.py:_safe_failure_detail`.
- Modify: `src/app/server/routes/ops.py` rule-store lookup and three CRUD handlers.
- Test: `tests/int/test_pipeline_app.py` existing unexpected-exception completion test.
- Test: `tests/int/test_pipeline_ops_routes.py` or a new focused test in that file for absent rule storage.

**Interfaces:**
- Unknown ordinary failures project to `module.qualname` only; known upstream failures keep their fixed status projection.
- Unconfigured capture-rule management returns HTTP 503 with a stable JSON body such as `{"error": {"type": "proxy_internal_error", "message": "debug capture rule store is not configured"}}`; CRUD success and existing 404/422 contracts remain unchanged.

- [x] **Step 1: Make the existing exception regression discriminating.** Keep the assertion that the ordinary line contains `RuntimeError`, and add a negative assertion that the injected message does not occur in the line.
- [x] **Step 2: Replace the unsafe fallback.** Return the qualified exception type from `_safe_failure_detail` instead of arbitrary exception text; do not change the known `UpstreamError`/`UpstreamRejected` status branches.
- [x] **Step 3: Add the absent-store HTTP control.** Build a minimal app state with `debug_capture_rules=None`, call GET/POST/DELETE through ASGI, and assert 503 plus the fixed JSON error for each route.
- [x] **Step 4: Implement the stable management error.** Make all three handlers use the same unavailable response without duplicating a different message or status.
- [x] **Step 5: Run focused API/log tests.** Run the two integration tests and `uv run ruff check` on the changed route, observability and test files.

### Task 5: Synchronize the living spec and disposition evidence

**Files:**
- Modify: `.dev/docs/raw-capture/spec.md` (already revised to ACTIVE v23; verify its clauses against final behavior).
- Modify: `.dev/docs/raw-capture/raw-capture-review-disposition.md` with each finding’s final claim, adopted fix, evidence and any refuted scope.
- Modify: `.dev/docs/raw-capture/deferred.md` only if a finding is intentionally not adopted; otherwise do not add a second ledger.

**Interfaces:**
- The spec remains the sole authority for behavior. Reports remain point-in-time records and are not rewritten to match the final code.
- The disposition ledger must close duplicate F-01 findings together, mark the “no HTTP CRUD tests” portion of implementation finding 05 as refuted by `tests/int/test_pipeline_app.py:351-406`, and retain the unconfigured-store portion as adopted.

- [x] **Step 1: Compare implementation against every v23 clause.** Check rule selection, binary format, wire evidence, timeout boundary, cleanup boundary, quotas, safety and error envelope without changing the spec to excuse code drift.
- [x] **Step 2: Update the disposition ledger.** Record the independent timeout probe, the cleanup finding, the safe-warning finding, the safe-fallback regression and the management-error fix with exact commands or test names.
- [x] **Step 3: Run a document self-review.** Search the plan/spec for `TBD`, `TODO`, stale v22 status, contradictory `complete=false` language and any claim that “all tests pass” without a reproducible command.

### Task 6: Verification, independent review and scoped integration

**Files:**
- Review: all raw-capture production and test files changed by Tasks 1–4.
- Update: `.dev/docs/raw-capture/raw-capture-review-disposition.md` with the final review outcome.

- [x] **Step 1: Run the raw-capture regression set.** Run `uv run pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/int/test_pipeline_app.py::test_raw_capture_is_selective_and_rule_api_is_persistent tests/int/test_pipeline_app.py::test_rule_selected_count_capture_keeps_each_upstream_retry --no-cov -q`.
- [x] **Step 2: Run the timeout and count boundary set.** Run the focused timeout, count cleanup, error projection and absent-store tests from Tasks 2–4.
- [x] **Step 3: Run static checks.** Run `uv run ruff check` on all changed raw-capture and provider-client files and `uv run pyright` on the corresponding source files.
- [x] **Step 4: Dispatch an independent final review.** Ask a fresh reviewer to inspect only the v23 clauses touched by the patch, including a positive control and the known shared-worktree constraints; do not rely on self-review alone.
- [x] **Step 5: Re-run any failed test after root-cause classification.** Existing shared-worktree failures in unrelated pipeline tests must be reported separately, not fixed by weakening raw-capture assertions.
- [x] **Step 6: Decide the shared-worktree integration boundary.** The semantic raw-capture patch is reviewed and verified in place, but staging/commit is intentionally deferred because the shared tree contains unrelated peer WIP and overlapping mixed-file hunks; no broad staging, reset or publish was performed.
