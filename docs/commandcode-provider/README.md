# Command Code provider

`commandcode` is an upstream provider that translates through the semantic IR
and sends the native Command Code envelope to `/alpha/generate`. It is not an
OpenAI-compatible provider.

Minimal configuration:

```yaml
model_providers:
  cc:
    type: commandcode
    api_key: user_...
    # Optional: use a validated snapshot captured from a running Command Code CLI.
    # Disabled by default; lifecycle initialization remains enabled.
    fingerprint_mode: captured
    fingerprint_snapshot_file: "$XDG_DATA_HOME/ghc-api-proxy/commandcode-fingerprint.json"
    # Optional: pin the catalog while the upstream catalog is unavailable.
    models:
      - deepseek/deepseek-v4-flash
```

The provider refreshes `/provider/v1/models` when `models` is empty or when a
refresh interval is configured. The upstream always receives a streaming
generation request; non-streaming client requests are aggregated inside the
provider before the normal IR response translation runs.

### CLI fingerprint snapshots

`fingerprint_mode: captured` does not generate a replacement identity. It reads
an externally captured snapshot from `fingerprint_snapshot_file`. The capture
producer should route a real Command Code CLI through an explicitly configured
local capture proxy and write this envelope after validating the observed
`/alpha/fingerprint/record` payload:

```json
{
  "schema_version": 1,
  "source": "commandcode-cli",
  "captured_at": "2026-09-15T22:00:00Z",
  "expires_at": "2026-09-16T06:00:00Z",
  "api_key_sha256": "<sha256 of the configured API key>",
  "fingerprint": {
    "thumbmark": "<CLI thumbmark>",
    "components": {}
  }
}
```

The proxy accepts the snapshot only when its source, API-key binding, timestamps,
and fingerprint shape are valid. An invalid or missing snapshot is logged and
does not fall back to `generated`. The snapshot file should be user-readable
only.

Supported client paths are the existing Anthropic Messages, OpenAI Responses,
and OpenAI Chat Completions routes. Command Code-specific response events are
assembled into the project's block-level delivery units before any client
format is written.
