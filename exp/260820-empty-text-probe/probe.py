"""Ask the real GHC Responses upstream whether it accepts a text part carrying no text.

Run by hand, never by the test suite: it needs credentials and it makes real calls.

    PYTHONPATH=src uv run python exp/260820-empty-text-probe/probe.py

The question this settles. `docs/tmp/260820-empty-text-block-synthesis.md` records that the Anthropic Messages leg refuses a blank text block outright — that is the 400 the whole investigation started from. Whether the Responses leg refuses the shape it translates into was never measured; the request-side strip was first gated on that not being known, and the gate was later removed by ruling. This probe replaces the unknown with an answer.

E5 is the positive control and is not optional. A row of 200s means nothing on its own: it could equally mean the probe never reached anything that judges bodies. E5 sends the shape already known to be refused, on the leg already known to refuse it, in the same run and with the same credentials. If E5 does not come back 400, the whole run is uninformative and the 200s must not be read as acceptance.

Prompts are trivial. Each probe is sent once; a failure is recorded, not retried. The Copilot token and the account identifiers ride through the wire untouched and are scrubbed only on the way to disk, because the live upstream must receive what it actually needs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.ghc_client.config import GhcClientConfig
from app.ghc_client.headers import build_identity_headers, build_request_headers

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
TOKEN_FILE = Path.home() / ".local/share/copilot-api/github_token"

BASE_URL = "https://api.githubcopilot.com"
AUTH_URL = "https://api.github.com/copilot_internal/v2/token"

GPT_MODEL = "gpt-5.5"
CLAUDE_MODEL = "claude-sonnet-5"
TRIVIAL = "Say OK."

REDACT_FIELDS = frozenset({"token", "tracking_id", "enterprise_list", "organization_list", "safety_identifier"})
REDACTION = "REDACTED"


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTION if k in REDACT_FIELDS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


async def copilot_token(client: httpx.AsyncClient, config: GhcClientConfig) -> str:
    gh = TOKEN_FILE.read_text(encoding="utf-8").strip()
    headers = {
        **build_identity_headers(config),
        "Accept": "application/json",
        "Authorization": f"token {gh}",
        "X-GitHub-Api-Version": "2025-04-01",
    }
    response = await client.get(AUTH_URL, headers=headers)
    response.raise_for_status()
    return str(response.json()["token"])


def responses_body(content: list[dict[str, Any]], *, extra_input: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": GPT_MODEL,
        "input": [{"type": "message", "role": "user", "content": content}],
        "max_output_tokens": 32,
        "stream": False,
    }
    if extra_input:
        body["input"].extend(extra_input)
    return body


CASES: list[dict[str, Any]] = [
    {
        "name": "E1-control-normal-text",
        "why": "The baseline. If this is not 200, nothing below can be read.",
        "path": "/responses",
        "body": responses_body([{"type": "input_text", "text": TRIVIAL}]),
    },
    {
        "name": "E2-empty-input-text-beside-a-real-one",
        "why": "The exact shape the proxy used to send after a blank Anthropic block was translated.",
        "path": "/responses",
        "body": responses_body(
            [{"type": "input_text", "text": ""}, {"type": "input_text", "text": TRIVIAL}]
        ),
    },
    {
        "name": "E3-whitespace-only-input-text",
        "why": "The sibling predicate. Anthropic refuses whitespace under its own wording; this asks whether Responses draws the same line.",
        "path": "/responses",
        "body": responses_body(
            [{"type": "input_text", "text": "   \n"}, {"type": "input_text", "text": TRIVIAL}]
        ),
    },
    {
        "name": "E4-empty-output-text-on-an-assistant-turn",
        "why": "What `[text(''), tool_use]` used to become: an assistant message item carrying nothing.",
        "path": "/responses",
        "body": responses_body(
            [{"type": "input_text", "text": TRIVIAL}],
            extra_input=[
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": ""}]},
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Again."}]},
            ],
        ),
    },
    {
        "name": "E5-positive-control-anthropic-leg",
        "why": "Proves this probe can see a refusal at all. Expected 400 `text content blocks must be non-empty`.",
        "path": "/v1/messages",
        "anthropic": True,
        "body": {
            "model": CLAUDE_MODEL,
            "max_tokens": 32,
            "messages": [{"role": "user", "content": [{"type": "text", "text": ""}, {"type": "text", "text": TRIVIAL}]}],
        },
    },
]


async def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    config = GhcClientConfig()
    async with httpx.AsyncClient(timeout=60.0) as client:
        token = await copilot_token(client, config)
        for case in CASES:
            headers = build_request_headers(token, config, interaction_id="empty-text-probe-260820")
            if case.get("anthropic"):
                headers["anthropic-version"] = "2023-06-01"
            response = await client.post(
                f"{BASE_URL}{case['path']}", headers=headers, json=case["body"]
            )
            text = response.text
            try:
                pretty = json.dumps(scrub(json.loads(text)), indent=2)
            except json.JSONDecodeError:
                pretty = text
            (RAW / f"{case['name']}.json").write_text(
                json.dumps(
                    {"why": case["why"], "request": case["body"], "status": response.status_code},
                    indent=2,
                )
                + "\n\n"
                + pretty
                + "\n",
                encoding="utf-8",
            )
            head = pretty if len(pretty) < 400 else pretty[:400] + f"... [{len(pretty)} bytes]"
            print(f"=== {case['name']}: HTTP {response.status_code}\n{head}\n")


if __name__ == "__main__":
    asyncio.run(main())
