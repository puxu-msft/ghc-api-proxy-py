# Project glossary

- **Wire format**: A public request or response shape: Anthropic Messages, OpenAI Responses, or OpenAI Chat Completions.
- **Decode**: Convert one wire payload into the typed semantic IR.
- **Encode**: Convert the typed semantic IR into one wire payload.
- **Client leg**: The wire format requested by the client.
- **Upstream leg**: The wire format used for the selected provider endpoint.
- **Semantic IR**: The typed, format-independent request/response model shared by all codecs.
- **Unknown request fields**: Source-scoped request keys no decoder claimed. They are replayed only when a target codec explicitly projects them.
- **Opaque response payloads**: Source-scoped response structures a decoder cannot interpret. A target codec preserves them only when it understands the source shape; otherwise it skips them and records a structured warning.
- **ContentBlock**: One semantic content block.
- **DeliveryUnit**: One complete block-level unit committed by delivery. It is separate from `ContentBlock`.
- **Translation**: Moving between client and upstream wire formats through the semantic IR.
- **Wire reshape**: Preparing one wire payload at a codec boundary.
- **IR reshape**: Editing typed semantic facts before encoding.
- **Options snapshot**: The immutable typed codec options captured for one request and reused by its retries unless an attempt explicitly overrides it.
