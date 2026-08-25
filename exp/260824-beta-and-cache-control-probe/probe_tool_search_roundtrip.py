"""The full client-executed tool-search round trip, end to end on the real upstream.

The translation the user asked for stands or falls on the second leg: the model emits
`tool_search_call`, the client is supposed to answer with `tool_search_output` carrying
the *loaded tool definitions*, and the model should then call the tool it just learned
about. The SDK types say that is the shape; only a real call says the endpoint agrees.

R2 is the one that matters. R1 exists so a failure in R2 can be told apart from a
request that was never going to work.
"""
from __future__ import annotations
import asyncio, json
from pathlib import Path
from typing import Any
from uuid import uuid4
import httpx2 as httpx
from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_identity_headers, build_request_headers

TOKEN = Path.home() / ".local/share/ghc-api-proxy/github_token"
MODEL = "gpt-5.6-sol"

SEARCH = {
    "type": "tool_search", "execution": "client",
    "description": "Search for available tools by regex. Returns tool references.",
    "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]},
}
WEATHER_FULL = {
    "type": "function", "name": "get_weather",
    "description": "Get the current weather for a city.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
}
DEFERRED = {**WEATHER_FULL, "defer_loading": True}
ASK = {"type": "message", "role": "user",
       "content": [{"type": "input_text", "text": "What is the weather in Paris? Use a tool."}]}

def summarise(items: list[dict[str, Any]]) -> str:
    out = []
    for it in items:
        k = it.get("type", "?")
        out.append(f"{k}:{it.get('name')}" if k in ("function_call", "custom_tool_call") else k)
    return " | ".join(out) or "(none)"

async def run() -> None:
    cfg = GhcClientConfig(account_type="enterprise")
    async with httpx.AsyncClient(timeout=180.0) as c:
        gh = TOKEN.read_text().strip()
        h = {**build_identity_headers(cfg), "Accept": "application/json",
             "Authorization": f"token {gh}", "X-GitHub-Api-Version": "2025-04-01"}
        r = await c.get("https://api.github.com/copilot_internal/v2/token", headers=h); r.raise_for_status()
        tok, base = r.json()["token"], r.json()["endpoints"]["api"].rstrip("/")

        def hdr() -> dict[str, str]:
            return build_request_headers(tok, cfg, interaction_id=str(uuid4()))

        # R1: first leg — model should ask the client to search.
        r1 = await c.post(f"{base}/responses", headers=hdr(), json={
            "model": MODEL, "input": [ASK], "tools": [SEARCH, DEFERRED],
            "max_output_tokens": 400, "stream": False})
        print(f"[R1 {r1.status_code}] first leg -> {summarise(r1.json().get('output') or []) if r1.status_code==200 else r1.text[:160]}")
        if r1.status_code != 200:
            return
        items = r1.json()["output"]
        call = next((i for i in items if i.get("type") == "tool_search_call"), None)
        if call is None:
            print("        no tool_search_call; nothing to answer")
            return
        print(f"        call_id={call.get('call_id')!r} arguments={json.dumps(call.get('arguments'))[:80]}")

        # R2: answer it the way the SDK type says a client should.
        answered = [
            ASK,
            {k: v for k, v in call.items() if k in ("type", "id", "call_id", "arguments", "execution", "status")},
            {"type": "tool_search_output", "call_id": call.get("call_id"),
             "execution": "client", "status": "completed", "tools": [WEATHER_FULL]},
        ]
        r2 = await c.post(f"{base}/responses", headers=hdr(), json={
            "model": MODEL, "input": answered, "tools": [SEARCH, DEFERRED],
            "max_output_tokens": 400, "stream": False})
        if r2.status_code != 200:
            try: msg = json.loads(r2.text).get("error", {}).get("message", r2.text[:200])
            except Exception: msg = r2.text[:200]
            print(f"[R2 {r2.status_code}] second leg -> {msg}")
            return
        print(f"[R2 200] second leg -> {summarise(r2.json().get('output') or [])}")

asyncio.run(run())
