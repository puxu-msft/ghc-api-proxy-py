# `src/.archived/` — the chain no entry point reaches

**Moved here 2026-08-22, on the user's instruction, from `src/app/`.** Nothing in this directory runs. It is kept because it is the only implementation of several endpoints `docs/.human-controlled/api.md` ratifies, not because anything imports it.

## What this is

Two request chains lived under `src/app/` at once. The live one is built by `app.cli` → `create_pipeline_app`; the other was built by `app.server.app_factory`, which **no production entry point called** — measured with a fresh interpreter per entry point, `app.routes` was not among the 151 modules `app.cli` loads, and `app_factory` was the only door to any of it. The 151 is a reading taken at the move and is not expected to hold: it counts the live tree, which grows. Twelve hours later it was 152. **The part that has to keep holding is the zero** — `PYTHONPATH=src uv run --no-project python .dev/docs/server-layout/probes/reach.py app.cli` should report no `app.routes` module at all, and `tests/unit/test_module_boundaries.py` asserts the stronger form of that. An earlier figure of 139 also appears in the session record, taken before the first five steps moved code around; all three are correct for their moment, and none of them is the claim.

77 source files moved. The criterion was mechanical: reachable from `app.server.app_factory`, not reachable from `app.cli`; plus every module of a top-level package none of whose modules the live chain reaches. A reverse check confirmed no live module was swept up. The count comes from `git show --name-status 2248a69`, which records 77 renames into `src/.archived` and 48 into `tests/.archived`, 125 in total — do not recount with `git ls-files 'src/.archived/**/*.py'` unless you know why that glob is safe here: git's `**` demands at least one directory level, so the same spelling against `src/app` silently drops the six modules sitting directly in it.

Three of those packages were not the retired chain but dead in both — `context/`, `repetition_detector.py`, `shutdown.py` (the latter a twin of the live `lifecycle/shutdown.py`). They moved by the same criterion and are named here rather than folded silently into "the old chain".

49 test files moved to `tests/.archived/` by the same measurement: they import archived modules and nothing the live chain owns exclusively. **No test spanned both chains** — the separation held all the way through the suite.

## Why a leading dot

`.archived` is invisible to the things that would otherwise treat it as source: pytest does not recurse into dot-directories, pyright excludes `**/.*` by default, and hatchling packages `src/app`, not this. It is also not on `sys.path`, so `import app.routes` raises `ModuleNotFoundError` — asserted by `tests/unit/test_module_boundaries.py`, which now pins that the names do not resolve rather than the weaker fact that the live chain does not import them.

## What is unfinished, and what it costs

`api.md` ratifies Azure, Gemini, `/history/api/*`, `/history/ws`, `/api/status` and `/api/config`. When this move happened the live chain served none of them and the only implementations were in here. **Two slices have since closed most of that**: `/api/status` and `/api/config` are answered by `app/server/routes/ops.py` as of `7525f76`, and on 2026-08-23 the three Azure paths became live routes while the three Gemini ones became registered routes answering 501. What is left in here with no live equivalent is `/history/api/*` and `/history/ws`, together with the `app.history` package behind them.

Gemini is the case to read carefully: the paths are served and the wire translation is not. Until 2026-08-23 part of the old implementation had never come in here at all — `app/protocols/gemini.py`, `app/models/gemini.py` and `estimate_gemini_input` sat in the live tree with no caller, `app/protocols/__init__.py` re-exporting one of them. They are in here now, and the estimator is the one that did not arrive as a whole file: it was cut out of the live `app/tokenization/estimators.py`, whose other estimators are still in use, and landed as `app/tokenization/gemini_estimator.py` under a name that never existed upstream of the cut. `.dev/docs/server-layout/deferred.md` §D-A points at all of them, because reusing them is the point — `parse_model_with_method` in particular already agrees with how the live route templates capture a model containing colons.

`src/.archived/app/routes/management.py` mixes the two: `/api/status` and `/api/config` are ratified, while the two `/api/tokenization/*` endpoints beside them are ruled **暂不支持**. Whoever migrates that file cannot take or leave it whole.

One test lost half its coverage rather than moving: `tests/systemd/test_systemd_units.py::test_service_permissions_restrict_real_state_writers` asserted `0o600` on `history.db` and its siblings *and* on `tokenization.json`. The history half went with the chain; the tokenization half is what the service actually writes and still runs. The docstring there says so.

## Added 2026-08-23: the pre-header transport guard

Three things arrived here together, each the sole caller of the next:

| What | Was reached from |
|---|---|
| `app/upstream/copilot_upstream.py` (`CopilotUpstream`) | nothing — cut out of the live `app/upstream/copilot.py`, whose other contents stay live |
| `GhcApiClient.send_responses_headers` | `CopilotUpstream` only; deleted from the live `client.py` rather than moved, since the archived `app/upstream/generic.py` already holds its twin |
| `app/model_provider/ghc_client/transport.py` | `send_responses_headers` only |

`CopilotUpstream` adapted the live library to `UpstreamTarget` — a protocol that had *already* been archived in the 2026-08-22 move, which is what made it dead: an adapter whose target interface had gone. It was missed then because the criterion was reachability from `app.server.app_factory`, and this class is not reachable from there either. **Nothing reaches it at all**, which the earlier sweep had no question for.

**The cost of it sitting here is worth recording, because it is not "dead code takes up space".** `transport.py` was the module that *carried* a real defect in the dependencies — that httpcore guards only the socket read, so a bare `h2.exceptions.ProtocolError` reaches callers unwrapped — naming `H2ProtocolError` in an `except` clause to handle it. Two other places wrote the same mechanism down in prose (`client.py:190-191` and the test that came here with it), so it was not the only record; it was the only *handler*. Read casually, the tree therefore looked as though it already handled that case. It did not: the guard was on a chain nobody calls, and the live body path had no equivalent until 2026-08-23, when the same GOAWAY was found to be retried or not depending on whether the kernel had batched two frames into one read. The knowledge now lives on the live path in `app/model_provider/ghc_client/errors.py`, which is what made moving this safe rather than a loss. See `.dev/docs/upstream/retry-and-continuation/deferred.md` §22 and §22之三.

One test came with them (`tests/.archived/unit/model_provider/ghc_client/test_pre_header_retry.py`) and one lost a case rather than moving: `tests/component/model_provider/ghc_client/test_client.py` kept the half whose subject is the live path and says so in its docstring, the same way `tests/systemd/test_systemd_units.py` did in the first move.

## Reading it

The tree keeps its original layout under `app/`, so relative imports inside the archive still line up. It is not importable as-is and is not meant to be: to run any of it you would put `src/.archived` on the path yourself, deliberately.
