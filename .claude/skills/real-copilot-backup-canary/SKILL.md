---
name: real-copilot-backup-canary
description: "Use when validating ghc-api-proxy-py against the real Copilot upstream on an isolated backup port before deployment or cutover. Triggers: real Copilot canary, 4142 backup service, verify Anthropic-to-Responses with a real model, protect and optionally compare a scoped canary against whatever process owns 4141, or recheck authentication/model-catalog/stream compatibility without controlling production 4141."
---

# Real Copilot backup-port canary

## Purpose and boundary

Validate the current `main` against the real Copilot token exchange, model catalog, Anthropic-to-Responses non-stream path, and Anthropic SSE stream path, without disturbing whatever process currently owns production `4141`.

**Do not assume what that process is — read it.** This workflow was written when `4141` belonged to the old Bun service; measured 2026-09-01, it is this project's own `ghc-api-proxy`, started 2026-08-29 and therefore serving a build that predates commits made after that date. Neither fact is permanent: `ss -ltnp | rg :4141` says who holds the listener today. A canary that assumes the wrong owner will either protect nothing or misreport a comparison.

**Start time bounds the code; it does not identify it.** A process started before commit X cannot contain X, which is often the whole point — but no ordering recovers *which* commit it is running, and nothing exposes one: `/api/status` carries no build revision, and PID, cwd and argv say nothing about the tree's state at launch. So a claim of the form "4141 runs commit Y" needs evidence this workflow does not provide; "4141 predates Y" usually does not.

This workflow never authorizes cutover. It must not signal, stop, restart, reconfigure, or replace the `4141` owner, whichever process that is. It does not install systemd units or operate a system/user manager.

## Preconditions

Before creating a temporary root or copying a credential, enter one outer `try/finally` cleanup owner and initialize child, listener, log, and temp-root handles to `None`. Every setup step, including token copy and temporary config creation, runs inside that owner. The `finally` block closes every initialized handle and removes every created path even when setup fails before the application starts.

1. Gate the physical repository, branch, full `HEAD`, and tracked product-code cleanliness.
2. Confirm `127.0.0.1:4142` has no listener. Then let the controller bind and retain the listener, pass its inherited fd to the exact candidate child with `--fd`, and verify the listener inode belongs to that child path. This closes the check-then-bind race. Use `ss` to test listener presence; do not use a bind failure alone because TIME_WAIT can produce false results.
3. Confirm the existing GitHub token source is a regular non-empty file with mode `0600`. Never print, hash, or place its value in a command line, report, or log.
4. Snapshot the `4141` listener owner using at least PID, `/proc/<pid>/stat` start time, cwd, cgroup, argv shape, parent chain, and listener identity. Compare the same fields after the canary and record that the canary sends it zero signals. A changed incarnation is reported as an external runtime change; it is never repaired by controlling that process.
5. Create a temporary HOME, `XDG_DATA_HOME`, and `XDG_CONFIG_HOME`. Copy only the required token into `<temp-data>/ghc-api-proxy/github_token-<provider>.txt` with mode `0600`. **The per-provider name is required, not cosmetic** — ruled by the user 2026-08-28 and derived in `app.server.composition.github_token_path`, because two providers may authenticate against different tenants. A file called plain `github_token` is not found, and the symptom is not an auth error: the service starts, listens, logs `catalog refresh failed: No GitHub token provider produced a usable token`, and never becomes ready.
6. A `--config` file is validated as `ProxyConfig`, and a minimal working one is just the provider and the default:

   ```yaml
   model_providers:
     ghc-msft:
       type: github_copilot
   default_model_provider: ghc-msft
   ```

   **`anthropic.route_override` does not belong in that file, and today it has no way in at all.** The key exists on `AppSettings`, not `ProxyConfig`; putting it in a `--config` file aborts start-up with `ValidationError: anthropic — Extra inputs are not permitted`. Checked 2026-09-01: every current entry point loads `ProxyConfig`, and `AppSettings` has no production caller — so there is no place to set this for the service this workflow starts. **Do not route the Anthropic-to-Responses canary through it.** Select the leg with the model instead, as the model-selection section says. The project does not use `@responses` as a model-name suffix.

Build the child environment from an explicit allowlist rather than copying `os.environ`. Remove every `COPILOT_API_GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`, `GHC_*`, `GHC_CONFIG`, and credential/config override unless the current canary explicitly owns that exact input. This ensures the temporary token file and temporary YAML are the only authentication and route sources.

## Start the isolated candidate

Start the current repository interpreter on the controller-owned loopback listener with:

- `--config <temporary-config>` and `--fd <inherited-fd>`;
- isolated HOME/XDG environment;
- `--no-history` for a minimal connectivity canary unless History is the specific behavior under test;
- `--no-rate-limit` for a single low-volume canary.

Hold the exact child handle and listener identity. Poll `/health/readiness` until a fixed monotonic startup deadline while checking `child.poll()` every iteration. A child exit or deadline expiry is a failure that immediately enters the outer cleanup path; never wait indefinitely for readiness. Tolerate connection-refused responses only before that deadline while Uvicorn is still starting. Send stdout/stderr either to `/dev/null` or to a mode-`0600` file inside the temporary root. If startup fails, read that file only after replacing token values, authorization values, API keys, long opaque IDs, generated content, reasoning, and tool arguments in memory; display only the sanitized exception tail. Delete the raw log after the child is reaped.

## Select a real model without guessing

Read `/api/models`, not `/models`, because `/api/models` exposes the full `ModelInfo.supported_endpoints` field. Exclude every ID listed in the response's top-level `disabled` set, then choose a model whose `supported_endpoints` explicitly contains `/responses` or `ws:/responses`.

Do not infer Responses support from a model name.

**For the Anthropic-to-Responses path, that is not enough, and the gap is silent.** `routing.py` prefers the inbound endpoint, so a model advertising both `/responses` and `/v1/messages` serves a `/v1/messages` canary as a *direct Anthropic* request — no translation happens, and the run still reports the target path as verified. Require `supported_endpoints` to contain `/responses` and **not** `/v1/messages`, and confirm the leg from the run itself rather than from the model list: the request's own log line names the endpoint, and `translation_required` / `target_format` are what decide it. Every model in the repository's own catalog cassette that advertises `/responses` today lacks `/v1/messages` — 12 of 42, checked 2026-09-01 — so the selection usually works; a catalog is a moving target and "usually" is what makes the failure silent. If no model satisfies both conditions, report that this canary cannot cover the translated path rather than letting it run the other leg.

## Minimal canary

Run exactly the main path needed for the current decision:

1. A minimal non-stream Anthropic `/v1/messages` request with the selected model. Record only HTTP status, Anthropic content block types, and usage key names.
2. A minimal stream request with the same model. Record only HTTP status and event type sequence. Validate Anthropic grammar rather than one exact six-event trace: one `message_start`; zero or more complete, non-interleaved blocks with continuous indexes; one `message_delta`; one final `message_stop`; no events after terminal. Multiple deltas, multiple blocks, and legal zero-delta blocks remain valid.

Do not record generated text, token values, reasoning payloads, signatures, response bodies, or tool arguments.

Expand the canary only when a real missing surface requires it, for example a tool or reasoning failure. Do not turn this workflow into a complete Acceptance matrix.

## Optional scoped comparison with the running 4141 service

Only when the user explicitly asks for a behavioral comparison, send the same low-impact, non-sensitive canary request to the existing `4141` front door before or after the isolated candidate. Compare only HTTP status, Anthropic block types, event grammar, and broad error category. Do not compare or retain generated text, reasoning, signatures, tool arguments, tokens, or latency conclusions from a single sample. Never change that service's configuration or lifecycle for the comparison. An incarnation change invalidates the comparison window and is reported rather than repaired.

**When `4141` runs this same project, establish the code gap or the comparison says nothing.** A difference between the two ports may be a difference in code rather than in behaviour — measured 2026-09-01, `4141` had been started before `1fb37cd` while the candidate carried it, and the two answered differently for exactly that reason. The candidate's commit is known, since this workflow starts it; the running one's is not directly readable (see the note above), so bound it by start time and say so in those terms. Without that bound, do not draw a behavioural conclusion.

## Copilot-specific compatibility facts

- Token exchange requires the client identity headers used by the current Copilot clients: editor version, editor plugin version, user agent, and `x-vscode-user-agent-library-version`. Dynamic Authorization and API version must override conflicting static identity headers case-insensitively.
- Copilot stream nested `response.id` values may drift across lifecycle frames. Generic/OpenAI mode remains strict; only the Copilot leg relaxes cross-frame equality, while every non-error lifecycle/terminal ID remains non-empty.
- Copilot stream item IDs may drift across item/content/delta/done frames for the same `output_index`. Generic/OpenAI mode remains strict; only the Copilot leg relaxes cross-frame item-ID equality. Output/content indexes, item type, call ID, and function name remain strict.

## Cleanup and verdict

1. Put all child, listener, request, and log operations in one `try/finally` cleanup path. Send SIGTERM only through the exact Python child handle, then `wait()`/reap it. Kill only that same child if it exceeds the cleanup deadline.
2. Close the controller-owned listener, confirm `4142` has zero listeners, delete the raw log, and remove the temporary HOME/XDG root only after every child has been reaped.
3. Re-snapshot the `4141` owner using the same identity fields. A changed incarnation is a finding, not permission to control it. That service may run under an external `--restart` wrapper.
4. State a scoped verdict. A successful canary proves real startup, catalog, one selected real model, and the tested non-stream/stream path. It does not prove cutover readiness, full tools/reasoning, complete quota/backpressure, kernel-level partial-write semantics, systemd manager/cgroup activation, data migration, rollback, or complete Acceptance PASS.
