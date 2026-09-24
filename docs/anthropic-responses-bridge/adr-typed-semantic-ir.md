# ADR: Typed semantic IR is the unique codec hub

## Status

Accepted, 2026-09-11.

## Decision

Anthropic Messages, OpenAI Responses, and OpenAI Chat Completions decode into the existing typed semantic IR and encode from it. No codec may become a point-to-point adapter for another wire format. Same-format round trips use the same decode/encode path and preserve semantic and field-level facts rather than JSON byte identity.

Request unknown fields remain scoped to their source wire format and are projected only by an explicit target codec rule. Response structures that cannot be interpreted are retained as source-scoped opaque payloads; a target codec that cannot interpret one skips it and records a structured conversion warning.

## Consequences

- Adding a wire format requires one decoder and one encoder pair plus focused tests.
- Retry code can reuse the prepared target payload without silently rebuilding it from stale semantic state.
- Losses and warnings are typed conversion facts, not direct codec logging.
- The IR remains the single place for semantic ordering, block identity, tool calls, reasoning, usage, and stop reasons.
