# ADR: Block-level delivery remains separate from the semantic IR

## Status

Accepted, 2026-09-11.

## Decision

`ContentBlock` is the semantic content unit. `DeliveryUnit` is the complete block-level unit committed to a client. They remain separate types and stages. Wire codecs may decode and encode semantic blocks, but they do not expose token- or event-level delivery boundaries.

Streaming assemblers may consume incremental upstream events, but downstream visibility begins only when a complete block-level delivery unit is available. Buffered and streaming paths use the same semantic mappings and diagnostics.

## Consequences

- Retry boundaries remain before the first committed delivery unit.
- A target codec cannot bypass block buffering by forwarding raw upstream events.
- Codec tests and delivery tests verify different contracts: semantic reshape versus commit framing.
