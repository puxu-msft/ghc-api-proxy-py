# History export access fix

## Progress ledger

| Time (UTC) | Item | Status | Evidence |
|---|---|---|---|
| 2026-09-15 | Route and configuration inspection | done | No inbound/admin access-control primitive existed; `server.host` defaults to loopback but is configurable. |
| 2026-09-15 | Credential-bearing export guard | done | Added a fail-closed `server.history_export_token` contract and route gate for transport/full export. |
| 2026-09-15 | Validation and final report | done | Focused History route tests, full Ruff, and full Pyright pass. |
| 2026-09-15 | F001 canonical documentation closure | done | Canonical server-section placeholder and API contract are synchronized without code changes; focused config/history tests pass. |
| 2026-09-15 | HXA-001 configuration regression closure | done | Schema-length and nested-environment regression coverage pass using example-only values; no runtime or contract change. |

## Decision

The smallest explicit management boundary is a separately configured secret, not listener locality. `server.history_export_token` is unset by default; only a matching `X-History-Export-Token` allows the routes that return captured transport with credentials. Index, detail, and semantic export remain available without that header because they are credential-free projections.

## Implemented boundary

- Added optional secret config `server.history_export_token`; it is unset by default and Pydantic's `SecretStr` masks it in JSON configuration presentation.
- Added a constant-time `X-History-Export-Token` comparison before the route reads the writer or looks up the entry.
- `GET /history/api/entries/{id}/transport`, `GET /history/api/entries/{id}?include=transport`, and `GET /history/api/entries/{id}?export=full` return the stable credential-free error envelope `403 {"error":{"type":"access_denied",...}}` when the secret is missing, not configured, or wrong.
- `GET /history/api/entries`, normal detail, `include=semantic`, and `export=semantic` deliberately retain their existing credential-free access behavior.
- Updated the normative History and raw-capture Specs. The canonical YAML example and API documentation now also name the exact configuration key and header.

## Validation

- `cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/history/test_history_routes.py` — passed: 5 tests.
- `cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src tests` — passed.
- `cd /home/xp/src/ghc-api-proxy-py && uv run pyright src tests` — passed: 0 errors, 0 warnings.

## Test boundary coverage

- An unconfigured service denies transport even if its History writer is unavailable, demonstrating the access decision occurs before resource lookup.
- A configured service denies missing and wrong headers for the direct transport endpoint, `include=transport`, and `export=full`.
- The matching header permits transport and full export.
- Existing no-header index/detail/semantic coverage remains green, including semantic export on the configured service.

## F001 canonical documentation closure

- `docs/.human-controlled/config.example.yaml` now documents, in the `server` section only, the commented `history_export_token` placeholder, its at-least-16-character requirement, default denial, `X-History-Export-Token`, the protected transport/full routes, and semantic/index exception. It contains no real token.
- `docs/.human-controlled/api.md` now identifies the three credential-bearing History access forms, the same secret/header contract, stable denial behavior, and the fact that listener locality is not authorization.
- No source code, tests, or other concurrent worktree files were modified for this closure.

### Closure validation

- `cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/config/test_config_schema.py tests/unit/history/test_history_routes.py` — passed: 64 tests.
- A direct canonical-file check confirmed the token is a commented placeholder and that the required key/header wording is present.

## HXA-001 configuration regression closure

- Added a schema regression that rejects the 15-character placeholder `fifteen-charss!`.
- Added a public config-loader regression for `GHC_API_PROXY_SERVER__HISTORY_EXPORT_TOKEN`; it asserts the nested value arrives as `SecretStr` and remains usable through its secret API.
- Both values are examples only, not credentials. Runtime code and the access contract are unchanged.

### HXA-001 validation

- `cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/config/test_config_schema.py tests/unit/config/test_config_loading.py tests/unit/history/test_history_routes.py` — passed: 116 tests.
- `cd /home/xp/src/ghc-api-proxy-py && uv run ruff check src tests` — passed.
- `cd /home/xp/src/ghc-api-proxy-py && uv run pyright src tests` — passed: 0 errors, 0 warnings.
