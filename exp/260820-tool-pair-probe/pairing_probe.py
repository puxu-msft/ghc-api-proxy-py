"""What the two endpoints do with a broken `tool_use` / `tool_result` pairing.

Run by hand, never by the test suite: it needs credentials and it makes real calls.

    PYTHONPATH=src:exp/260820-empty-text-probe uv run python exp/260820-tool-pair-probe/pairing_probe.py

Three things the repair's design turns on, none of which can be read off the code:

- **What upstream actually refuses.** The legacy sanitizer removes orphan calls, orphan results and duplicate ids. Whether this upstream refuses each of those, and in what words, decides whether the repair is needed and how a future matcher would recognise the failure.
- **Whether an emptied turn can be dropped.** Removing an orphan result can leave a user turn with nothing in it, and `content: []` is refused for a user turn — measured on 2026-08-20. The alternative is dropping the turn, which puts two same-role turns next to each other. If that is refused too, then neither rewrite is available and the orphan has to travel.
- **Which legs care.** The Anthropic endpoint is the one with the documented invariant. Whether the Responses endpoint refuses the translated equivalent — a `function_call` with no `function_call_output` — decides whether the repair belongs on the outbound Anthropic leg alone or earlier.

G0 is the positive control: an ordinary well-paired request on the same leg in the same run, so a row of 400s cannot be read as the credentials having lapsed.

Helpers come from the empty-text probe so both speak to upstream identically.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from probe import BASE_URL, CLAUDE_MODEL, GPT_MODEL, copilot_token, scrub

from app.ghc_client.config import GhcClientConfig
from app.ghc_client.headers import build_request_headers

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

WEATHER: dict[str, Any] = {
    "name": "get_weather",
    "description": "Get the weather.",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
}
ASK: dict[str, Any] = {"role": "user", "content": [{"type": "text", "text": "Weather in Paris?"}]}


def call(use_id: str = "toolu_1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": use_id, "name": "get_weather", "input": {"city": "Paris"}}],
    }


def answer(use_id: str = "toolu_1") -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id, "content": "18C"}]}


def anthropic(messages: list[dict[str, Any]], *, tools: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {"model": CLAUDE_MODEL, "max_tokens": 32, "messages": messages}
    if tools:
        body["tools"] = [WEATHER]
    return body


CASES: list[dict[str, Any]] = [
    {
        "name": "G0-control-well-paired",
        "why": "Positive control. If this is not 200 nothing below can be read as a verdict on pairing.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic([ASK, call(), answer()]),
    },
    {
        "name": "G1-orphan-tool-use",
        "why": "A call the next turn never answers. The first thing the repair removes.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic([ASK, call(), {"role": "user", "content": [{"type": "text", "text": "never mind"}]}]),
    },
    {
        "name": "G2-orphan-tool-result",
        "why": "A result with no call before it. The second thing the repair removes.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic([ASK, {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}, answer()]),
    },
    {
        "name": "G3-duplicate-tool-use-id",
        "why": "The same id used twice. The third thing the repair removes, and a family Claude Code's own classifier names.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic([ASK, call(), answer(), call(), answer()]),
    },
    {
        "name": "G4-two-assistant-turns-in-a-row",
        "why": "What dropping an emptied turn produces. If this is refused, dropping is not an available repair.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": anthropic(
            [
                ASK,
                {"role": "assistant", "content": [{"type": "text", "text": "one"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "two"}]},
                {"role": "user", "content": [{"type": "text", "text": "go on"}]},
            ],
            tools=False,
        ),
    },
    {
        "name": "G5-responses-orphan-function-call",
        "why": "The translated equivalent on the other leg. Decides whether the repair is a property of the Anthropic endpoint or of the body.",
        "path": "/responses",
        "body": {
            "model": GPT_MODEL,
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Weather in Paris?"}]},
                {"type": "function_call", "call_id": "call_1", "name": "get_weather", "arguments": '{"city":"Paris"}'},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "never mind"}]},
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
            headers = build_request_headers(token, config, interaction_id="tool-pair-probe-260820")
            if case.get("anthropic"):
                headers["anthropic-version"] = "2023-06-01"
            response = await client.post(f"{BASE_URL}{case['path']}", headers=headers, json=case["body"])
            try:
                pretty = json.dumps(scrub(json.loads(response.text)), indent=2)
            except json.JSONDecodeError:
                pretty = response.text
            (RAW / f"{case['name']}.json").write_text(
                json.dumps({"why": case["why"], "request": case["body"], "status": response.status_code}, indent=2)
                + "\n\n"
                + pretty
                + "\n",
                encoding="utf-8",
            )
            head = pretty if len(pretty) < 300 else pretty[:300] + f"... [{len(pretty)} bytes]"
            print(f"=== {case['name']}: HTTP {response.status_code}\n{head}\n")


if __name__ == "__main__":
    asyncio.run(main())
