"""Independent canonical vectors for the reasoning carrier v2 living Spec.

This script deliberately imports no product code. It is a readable transcription of the wire
contract, not a second encoder implementation used at runtime.
"""

import base64
import json

PREFIX = "ghc-api-proxy:synthetic-reasoning:v2:"

VECTORS = [
    {
        "name": "responses-summary-layout-and-opaque",
        "records": [
            {
                "type": "openai.responses.reasoning.encrypted_content",
                "value": "ENC==",
            },
            {
                "type": "openai.responses.reasoning.summary_text_layout",
                "value": {
                    "lengths": [3, 0, 7],
                    "extensions": [{}, {}, {}],
                },
            },
        ],
    },
    {
        "name": "anthropic-thinking-signature",
        "records": [
            {
                "type": "anthropic.messages.thinking.signature",
                "value": "CAIS-😀",
            }
        ],
    },
    {
        "name": "anthropic-redacted-thinking",
        "records": [
            {
                "type": "anthropic.messages.redacted_thinking.data",
                "value": "opaque-redacted",
            }
        ],
    },
    {
        "name": "chat-reasoning-origin",
        "records": [
            {
                "type": "openai.chat_completions.reasoning_content",
                "value": None,
            }
        ],
    },
]

for vector in VECTORS:
    document = {"records": sorted(vector["records"], key=lambda record: record["type"])}
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    print(vector["name"])
    print(raw.decode())
    print(f"{PREFIX}{encoded}")
