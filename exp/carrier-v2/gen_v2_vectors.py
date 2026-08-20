"""Canonical v2 vectors, computed from the spec text alone.

Deliberately imports nothing from `app`: acceptance.md:114 requires expected values not be
produced by the codec under test. This re-implements the written rules — compact UTF-8 JSON,
field order tag/encrypted_content/i, unpadded base64url — and nothing else.
"""
import base64, json

PREFIX = "ghc-api-proxy:synthetic-reasoning:v2:"
BARE   = "ghc-api-proxy:synthetic-reasoning:v2"
TAG    = "openai.responses.reasoning.encrypted_content"

def encode(encrypted_content: str, i: int) -> tuple[str, str]:
    payload = {"tag": TAG, "encrypted_content": encrypted_content, "i": i}
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    b64 = base64.urlsafe_b64encode(js.encode("utf-8")).decode().rstrip("=")
    return js, PREFIX + b64

cases = [("opaque-\U0001F600", 0), ("ENC==", 0), ("opaque-\U0001F600", 2), ("a", 41)]
for enc, i in cases:
    js, sig = encode(enc, i)
    print(f"--- encrypted_content={enc!r}  i={i}")
    print(f"    json      : {js}")
    print(f"    signature : {sig}")
print(f"--- bare marker (summary-only and strip)\n    signature : {BARE}")

# self-check: decode back
for enc, i in cases:
    _, sig = encode(enc, i)
    p = sig.removeprefix(PREFIX)
    raw = base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))
    back = json.loads(raw)
    assert back == {"tag": TAG, "encrypted_content": enc, "i": i}, back
    assert base64.urlsafe_b64encode(raw).decode().rstrip("=") == p, "not canonical"
print("\nself-check: all vectors round-trip and are canonical base64url")
