"""Edge cases the mapping has to answer before it can be written down.

E1: can a request carry two `tool_search` entries (server + client)? The Anthropic side
    can in principle declare a hosted search tool *and* a custom one.
E2: does a client-executed search coexist with the client's original function tool still
    present? That is what happens if we promote a copy instead of replacing it.
E3: does `tool_search_output` carrying several tool definitions work? Anthropic's
    `tool_result` may hold several `tool_reference` blocks.
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
CLIENT_SEARCH = {"type": "tool_search", "execution": "client",
                 "description": "Search for available tools by regex.",
                 "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}
SERVER_SEARCH = {"type": "tool_search", "execution": "server"}
W = {"type": "function", "name": "get_weather", "description": "Get weather.",
     "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}
T = {"type": "function", "name": "get_time", "description": "Get time.",
     "parameters": {"type": "object", "properties": {}}}
ORIGINAL_SEARCH_TOOL = {"type": "function", "name": "ToolSearch", "description": "Search for tools.",
                        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}}}
ASK = {"type": "message", "role": "user",
       "content": [{"type": "input_text", "text": "What is the weather in Paris? Use a tool."}]}

def summarise(items): 
    out = []
    for it in items:
        k = it.get("type", "?")
        out.append(f"{k}:{it.get('name')}" if k in ("function_call","custom_tool_call") else k)
    return " | ".join(out) or "(none)"

CASES = [
    ("E1 both server and client tool_search", [SERVER_SEARCH, CLIENT_SEARCH, {**W, "defer_loading": True}, T], None),
    ("E2 client tool_search + the original function tool still present",
     [CLIENT_SEARCH, ORIGINAL_SEARCH_TOOL, {**W, "defer_loading": True}, T], None),
    ("E3 output carrying two tool definitions", [CLIENT_SEARCH, {**W, "defer_loading": True}, {**T, "defer_loading": True}], "two"),
]

async def run() -> None:
    cfg = GhcClientConfig(account_type="enterprise")
    async with httpx.AsyncClient(timeout=180.0) as c:
        gh = TOKEN.read_text().strip()
        h = {**build_identity_headers(cfg), "Accept": "application/json",
             "Authorization": f"token {gh}", "X-GitHub-Api-Version": "2025-04-01"}
        r = await c.get("https://api.github.com/copilot_internal/v2/token", headers=h); r.raise_for_status()
        tok, base = r.json()["token"], r.json()["endpoints"]["api"].rstrip("/")
        hdr = lambda: build_request_headers(tok, cfg, interaction_id=str(uuid4()))

        for label, tools, extra in CASES:
            resp = await c.post(f"{base}/responses", headers=hdr(),
                                json={"model": MODEL, "input": [ASK], "tools": tools,
                                      "max_output_tokens": 400, "stream": False})
            if resp.status_code != 200:
                try: msg = json.loads(resp.text).get("error", {}).get("message", "")[:150]
                except Exception: msg = resp.text[:150]
                print(f"[{resp.status_code}] {label} -> {msg}")
                continue
            items = resp.json()["output"]
            print(f"[ 200] {label} -> {summarise(items)}")
            if extra == "two":
                call = next((i for i in items if i.get("type") == "tool_search_call"), None)
                if call:
                    r2 = await c.post(f"{base}/responses", headers=hdr(), json={
                        "model": MODEL,
                        "input": [ASK, {k: v for k, v in call.items() if k in ("type","id","call_id","arguments","execution","status")},
                                  {"type": "tool_search_output", "call_id": call.get("call_id"),
                                   "execution": "client", "status": "completed", "tools": [W, T]}],
                        "tools": tools, "max_output_tokens": 400, "stream": False})
                    if r2.status_code == 200:
                        print(f"        second leg with two definitions -> {summarise(r2.json()['output'])}")
                    else:
                        print(f"        second leg -> {r2.status_code} {r2.text[:120]}")

asyncio.run(run())
