"""Historical vectors for the superseded ordinal-only v2 candidate.

This is not the current v2 contract or an acceptance oracle. The 2026-09-04 living Spec at
`.dev/docs/reasoning-carrier/spec.md` replaced `{tag, encrypted_content, i}` with a typed-record
envelope and removed ordinal `i` from this producer. Kept only as a reproducible counterexample
to that rejected candidate; current vectors belong to the implementing patch and must be derived
independently from the living Spec.
"""
import base64
import json

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
print("\nHISTORICAL ONLY: superseded ordinal-only vectors round-trip as originally specified")
