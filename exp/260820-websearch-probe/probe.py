"""Probe the real GitHub Copilot upstream for web-search request/response shapes.

Run by hand, never by the test suite: it needs credentials and it makes real calls.

    PYTHONPATH=src uv run python exp/260820-websearch-probe/probe.py A
    PYTHONPATH=src uv run python exp/260820-websearch-probe/probe.py B
    PYTHONPATH=src uv run python exp/260820-websearch-probe/probe.py C

Prompts are deliberately trivial. Each probe is sent once; a failure is recorded, not retried.

Raw request bodies and raw response bytes land in `raw/`. The Copilot token and the account identifiers ride through the wire untouched and are scrubbed only on the way to disk, because the live upstream must receive what it actually needs.
"""

from __future__ import annotations

import asyncio
import json
import sys
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

CLAUDE_MODEL = "claude-sonnet-5"
GPT_MODEL = "gpt-5.5"

ANTHROPIC_WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search"}
FUNCTION_TOOL = {
    "name": "get_weather",
    "description": "Get the weather",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
}

TRIVIAL = "What is the capital of France?"
SEARCH_PROMPT = "Search the web for today's date."

# Everything that names the account, redacted on the way to disk only.
REDACT_FIELDS = frozenset({"token", "tracking_id", "enterprise_list", "organization_list", "safety_identifier"})
REDACTION = "REDACTED"


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTION if k in REDACT_FIELDS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def scrub_text(raw: str) -> str:
    """Scrub a whole body, JSON or SSE, keeping the text readable."""
    try:
        return json.dumps(scrub(json.loads(raw)), indent=2)
    except json.JSONDecodeError:
        pass
    out: list[str] = []
    for line in raw.split("\n"):
        if line.startswith("data: "):
            try:
                out.append("data: " + json.dumps(scrub(json.loads(line[6:]))))
                continue
            except json.JSONDecodeError:
                pass
        out.append(line)
    return "\n".join(out)


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


async def probe(
    client: httpx.AsyncClient,
    token: str,
    config: GhcClientConfig,
    *,
    name: str,
    path: str,
    body: dict[str, Any],
    anthropic: bool = False,
    stream: bool = False,
) -> None:
    headers = build_request_headers(token, config, interaction_id="probe-260820")
    if anthropic:
        headers["anthropic-version"] = "2023-06-01"
    if stream:
        headers["accept"] = "text/event-stream"

    chunks: list[bytes] = []
    async with client.stream("POST", f"{BASE_URL}{path}", headers=headers, json=body) as response:
        status = response.status_code
        content_type = response.headers.get("content-type", "")
        async for chunk in response.aiter_raw():
            chunks.append(chunk)
    text = b"".join(chunks).decode("utf-8", errors="replace")

    (RAW / f"{name}-request.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    (RAW / f"{name}-response.txt").write_text(
        f"# HTTP {status} content-type: {content_type}\n\n" + scrub_text(text) + "\n",
        encoding="utf-8",
    )
    if stream:
        # Chunk boundaries are the one thing only a live recording can settle.
        (RAW / f"{name}-chunks.json").write_text(
            json.dumps(
                {"status": status, "chunks": [scrub_text(c.decode("utf-8", errors="replace")) for c in chunks]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    head = text if len(text) < 600 else text[:600] + f"... [{len(text)} bytes total]"
    print(f"=== {name}: HTTP {status} ({len(chunks)} chunks)\n{head}\n")


def responses_body(tools: list[dict[str, Any]] | None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": GPT_MODEL,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": TRIVIAL}]}],
        "max_output_tokens": 64,
        "stream": False,
    }
    if tools is not None:
        body["tools"] = tools
    body.update(extra)
    return body


def count_tokens_body(tools: list[dict[str, Any]] | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": CLAUDE_MODEL,
        "messages": [{"role": "user", "content": TRIVIAL}],
    }
    if tools is not None:
        body["tools"] = tools
    return body


GROUPS: dict[str, list[dict[str, Any]]] = {
    "A": [
        {"name": "A1-count-tokens-web-search", "path": "/v1/messages/count_tokens", "anthropic": True,
         "body": count_tokens_body([ANTHROPIC_WEB_SEARCH])},
        {"name": "A2-count-tokens-no-tools", "path": "/v1/messages/count_tokens", "anthropic": True,
         "body": count_tokens_body(None)},
        {"name": "A3-count-tokens-function-tool", "path": "/v1/messages/count_tokens", "anthropic": True,
         "body": count_tokens_body([FUNCTION_TOOL])},
    ],
    "B": [
        {"name": "B1-responses-web-search", "path": "/responses",
         "body": responses_body([{"type": "web_search"}])},
        {"name": "B2-responses-anthropic-spelling", "path": "/responses",
         "body": responses_body([ANTHROPIC_WEB_SEARCH])},
        {"name": "B3-responses-user-location", "path": "/responses",
         "body": responses_body([{"type": "web_search", "user_location": {
             "type": "approximate", "city": "Seattle", "country": "US",
             "region": "Washington", "timezone": "America/Los_Angeles"}}])},
        {"name": "B4-responses-allowed-domains", "path": "/responses",
         "body": responses_body([{"type": "web_search", "allowed_domains": ["example.com"]}])},
        {"name": "B5-responses-blocked-domains", "path": "/responses",
         "body": responses_body([{"type": "web_search", "blocked_domains": ["example.com"]}])},
        {"name": "B6-responses-max-uses", "path": "/responses",
         "body": responses_body([{"type": "web_search", "max_uses": 3}])},
        {"name": "B7-responses-tool-choice-builtin", "path": "/responses",
         "body": responses_body([{"type": "web_search"}], tool_choice={"type": "web_search"})},
        {"name": "B8-responses-include-sources", "path": "/responses",
         "body": responses_body([{"type": "web_search"}], include=["web_search_call.action.sources"])},
        {"name": "B9-responses-web-fetch", "path": "/responses",
         "body": responses_body([{"type": "web_fetch"}])},
    ],
    "C": [
        {"name": "C1-responses-search-nonstream", "path": "/responses",
         "body": {
             "model": GPT_MODEL,
             "input": [{"role": "user", "content": [{"type": "input_text", "text": SEARCH_PROMPT}]}],
             "max_output_tokens": 512,
             "stream": False,
             "tools": [{"type": "web_search"}],
         }},
        {"name": "C2-responses-search-stream", "path": "/responses", "stream": True,
         "body": {
             "model": GPT_MODEL,
             "input": [{"role": "user", "content": [{"type": "input_text", "text": SEARCH_PROMPT}]}],
             "max_output_tokens": 512,
             "stream": True,
             "tools": [{"type": "web_search"}],
         }},
    ],
}


async def run(group: str) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    config = GhcClientConfig()
    async with httpx.AsyncClient(timeout=180) as client:
        token = await copilot_token(client, config)
        for spec in GROUPS[group]:
            try:
                await probe(client, token, config, **spec)
            except Exception as error:  # one shot each: record the failure, never retry
                print(f"=== {spec['name']}: FAILED {type(error).__name__}: {error}\n")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in GROUPS:
        print(f"usage: probe.py {{{'|'.join(GROUPS)}}}", file=sys.stderr)
        return 2
    asyncio.run(run(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
