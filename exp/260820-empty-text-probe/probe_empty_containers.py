"""What the two endpoints do with a container that holds nothing, rather than a block that says nothing.

Run by hand, never by the test suite: it needs credentials and it makes real calls.

    PYTHONPATH=src uv run python exp/260820-empty-text-probe/probe_empty_containers.py

`probe.py` settled the *block* question — an empty text part is refused on the Anthropic leg and accepted on the Responses one. It left two things unmeasured, and both are load-bearing:

- **`content: []`.** `subscribers/blank_text.py` refuses to empty a turn on the grounds that this shape is refused. That grounds is second-hand: two comments in the reference implementation, never checked here. If it turns out to be accepted, the all-blank exception is the wrong choice and a turn should simply be emptied.
- **A turn whose content is nothing but a blank block.** That is the one input the subscriber deliberately passes through untouched, so what the client ends up seeing in that case has never been observed.

A third question rides along: Anthropic's own contract is documented as allowing an empty final assistant turn (prefill). If this upstream honours that, "a turn cannot be emptied" is not even true in general, and the rule would need a position qualifier.

F0 is the positive control and is not optional in the other direction from `probe.py`'s E5: there the risk was that four 200s meant nothing, here it is that a row of 400s means the credentials or the leg are simply broken. F0 is an ordinary valid request on the same leg in the same run.

Helpers come from `probe.py` so both probes speak to upstream identically — same token exchange, same identity headers, same scrubbing on the way to disk.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from probe import AUTH_URL, BASE_URL, CLAUDE_MODEL, GPT_MODEL, copilot_token, scrub

from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_request_headers

del AUTH_URL  # Imported for provenance only; `copilot_token` uses it.

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
TRIVIAL = "Say OK."


def anthropic_body(messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {"model": CLAUDE_MODEL, "max_tokens": 32, "messages": messages}


USER_OK: dict[str, Any] = {"role": "user", "content": [{"type": "text", "text": TRIVIAL}]}
BLANK: dict[str, Any] = {"type": "text", "text": ""}

CASES: list[dict[str, Any]] = [
    {
        "name": "F0-control-valid-anthropic",
        "why": "Positive control. If this is not 200 the credentials or the leg are broken and no 400 below means anything.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic_body([USER_OK]),
    },
    {
        "name": "F1-user-turn-with-empty-content-array",
        "why": "The second-hand claim: `content: []` is refused. Never checked here.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic_body([{"role": "user", "content": []}]),
    },
    {
        "name": "F2-user-turn-of-nothing-but-a-blank-block",
        "why": "The one input the subscriber passes through untouched. What does the client actually get?",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic_body([{"role": "user", "content": [BLANK]}]),
    },
    {
        "name": "F3-assistant-turn-of-nothing-but-a-blank-block",
        "why": "Same shape on the other role, mid-conversation, which is where the synthesised placeholder actually landed.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic_body(
            [USER_OK, {"role": "assistant", "content": [BLANK]}, {"role": "user", "content": [{"type": "text", "text": "Again."}]}]
        ),
    },
    {
        "name": "F4-final-assistant-turn-with-empty-content-array",
        "why": "Anthropic's contract is documented as excepting the optional final assistant turn. If this upstream honours it, `content: []` is not refused everywhere.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic_body([USER_OK, {"role": "assistant", "content": []}]),
    },
    {
        "name": "F5-responses-message-with-empty-content-array",
        "why": "Completes the picture on the leg that accepted every empty part.",
        "path": "/responses",
        "body": {
            "model": GPT_MODEL,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TRIVIAL}]},
                {"type": "message", "role": "assistant", "content": []},
            ],
            "max_output_tokens": 32,
            "stream": False,
        },
    },
]


async def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    config = GhcClientConfig()
    async with httpx.AsyncClient(timeout=60.0) as client:
        token = await copilot_token(client, config)
        for case in CASES:
            headers = build_request_headers(token, config, interaction_id="empty-container-probe-260820")
            if case.get("anthropic"):
                headers["anthropic-version"] = "2023-06-01"
            response = await client.post(f"{BASE_URL}{case['path']}", headers=headers, json=case["body"])
            text = response.text
            try:
                pretty = json.dumps(scrub(json.loads(text)), indent=2)
            except json.JSONDecodeError:
                pretty = text
            (RAW / f"{case['name']}.json").write_text(
                json.dumps({"why": case["why"], "request": case["body"], "status": response.status_code}, indent=2)
                + "\n\n"
                + pretty
                + "\n",
                encoding="utf-8",
            )
            head = pretty if len(pretty) < 320 else pretty[:320] + f"... [{len(pretty)} bytes]"
            print(f"=== {case['name']}: HTTP {response.status_code}\n{head}\n")


if __name__ == "__main__":
    asyncio.run(main())
