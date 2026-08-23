# `src/.archived/` — the chain no entry point reaches

**Moved here 2026-08-22, on the user's instruction, from `src/app/`.** Nothing in this directory runs. It is kept because it is the only implementation of several endpoints `docs/.human-controlled/api.md` ratifies, not because anything imports it.

## What this is

Two request chains lived under `src/app/` at once. The live one is built by `app.cli` → `create_pipeline_app`; the other was built by `app.server.app_factory`, which **no production entry point called** — measured with a fresh interpreter per entry point, `app.routes` was not among the 151 modules `app.cli` loads, and `app_factory` was the only door to any of it. That count still reproduces: `PYTHONPATH=src uv run --no-project python .dev/docs/server-layout/probes/reach.py app.cli` gives 151 with zero `app.routes`. An earlier figure of 139 appears in the session record; it was taken before the first five steps moved code around, and both are correct for their moment.

77 source files moved. The criterion was mechanical: reachable from `app.server.app_factory`, not reachable from `app.cli`; plus every module of a top-level package none of whose modules the live chain reaches. A reverse check confirmed no live module was swept up. The count comes from `git show --name-status 2248a69`, which records 77 renames into `src/.archived` and 48 into `tests/.archived`, 125 in total — do not recount with `git ls-files 'src/.archived/**/*.py'` unless you know why that glob is safe here: git's `**` demands at least one directory level, so the same spelling against `src/app` silently drops the six modules sitting directly in it.

Three of those packages were not the retired chain but dead in both — `context/`, `repetition_detector.py`, `shutdown.py` (the latter a twin of the live `lifecycle/shutdown.py`). They moved by the same criterion and are named here rather than folded silently into "the old chain".

49 test files moved to `tests/.archived/` by the same measurement: they import archived modules and nothing the live chain owns exclusively. **No test spanned both chains** — the separation held all the way through the suite.

## Why a leading dot

`.archived` is invisible to the things that would otherwise treat it as source: pytest does not recurse into dot-directories, pyright excludes `**/.*` by default, and hatchling packages `src/app`, not this. It is also not on `sys.path`, so `import app.routes` raises `ModuleNotFoundError` — asserted by `tests/unit/test_module_boundaries.py`, which now pins that the names do not resolve rather than the weaker fact that the live chain does not import them.

## What is unfinished, and what it costs

`api.md` ratifies Azure, Gemini, `/history/api/*`, `/history/ws`, `/api/status` and `/api/config`. **The live chain serves none of them**, and the only implementations are in here. That was already true before this move — the chain holding them was unreachable — but the move makes it visible instead of latent.

`src/.archived/app/routes/management.py` mixes the two: `/api/status` and `/api/config` are ratified, while the two `/api/tokenization/*` endpoints beside them are ruled **暂不支持**. Whoever migrates that file cannot take or leave it whole.

One test lost half its coverage rather than moving: `tests/systemd/test_systemd_units.py::test_service_permissions_restrict_real_state_writers` asserted `0o600` on `history.db` and its siblings *and* on `tokenization.json`. The history half went with the chain; the tokenization half is what the service actually writes and still runs. The docstring there says so.

## Reading it

The tree keeps its original layout under `app/`, so relative imports inside the archive still line up. It is not importable as-is and is not meant to be: to run any of it you would put `src/.archived` on the path yourself, deliberately.
