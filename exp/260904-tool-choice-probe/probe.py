"""Probe the Copilot upstream for the `tool_choice` spellings a structural translation would send.

Run by hand, never by the test suite: it needs credentials and it makes real calls.

    PYTHONPATH=src uv run python exp/260904-tool-choice-probe/probe.py search
    PYTHONPATH=src uv run python exp/260904-tool-choice-probe/probe.py anthropic

The original 2026-09-04 captures live in `raw/`. T1-T6 accepted the tested Responses choices; required and the named function case produced calls. T7/T8 rejected the bare tool_search choice, and T9/T10 rejected the tested choices with a tools list; T10 explicitly says the type must be allowed_tools. T11's object-form allowed_tools returned a plain message, demonstrating that this tested shape did not force a call, not that every possible forcing shape is unavailable.

A1-A5 returned model_not_supported for the tested Anthropic model. They do not establish live Responses-to-Anthropic interoperability. Each probe is sent once without retries; exceptions are reported as failures. New captures go to a separate timestamped directory under `runs/`, preserving the original evidence. Credentials are used only for transport and are not included in request-body captures.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx

from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_identity_headers, build_request_headers

HERE = Path(__file__).resolve().parent
RAW = HERE / "runs" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
TOKEN_FILE = Path.home() / ".local/share/ghc-api-proxy/github_token-ghc-msft.txt"

BASE_URL = "https://api.githubcopilot.com"
AUTH_URL = "https://api.github.com/copilot_internal/v2/token"

GPT_MODEL = "gpt-5.5"
CLAUDE_MODEL = "claude-sonnet-5"

FUNCTION_TOOL = {
    "type": "function",
    "name": "get_weather",
    "description": "Get the weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
}
DEFERRED_TOOL = {**FUNCTION_TOOL, "defer_loading": True}
CLIENT_TOOL_SEARCH = {
    "type": "tool_search",
    "execution": "client",
    "description": "Search for tools that are available but not yet loaded.",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
}
HOSTED_TOOL_SEARCH = {"type": "tool_search", "execution": "server"}

ANTHROPIC_FUNCTION_TOOL = {
    "name": "get_weather",
    "description": "Get the weather for a city",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
}

TRIVIAL = "What is the capital of France?"

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


def responses_body(tools: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model": GPT_MODEL,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": TRIVIAL}]}],
        "max_output_tokens": 256,
        "stream": False,
        "tools": tools,
    }
    base.update(extra)
    return base


def anthropic_body(tools: list[dict[str, Any]] | None, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model": CLAUDE_MODEL,
        "messages": [{"role": "user", "content": TRIVIAL}],
        "max_tokens": 64,
        "stream": False,
    }
    if tools is not None:
        base["tools"] = tools
    base.update(extra)
    return base


# name -> (path, request body, anthropic leg?, which output item/block type means "forced")
SPECS: dict[str, list[dict[str, Any]]] = {
    "search": [
        {
            "name": "T7-choice-tool-search-client",
            "body": responses_body(
                [DEFERRED_TOOL, CLIENT_TOOL_SEARCH], tool_choice={"type": "tool_search"}
            ),
            "forced_marker": "tool_search_call",
        },
        {
            "name": "T8-choice-tool-search-server",
            "body": responses_body(
                [DEFERRED_TOOL, HOSTED_TOOL_SEARCH], tool_choice={"type": "tool_search"}
            ),
            "forced_marker": "tool_search_call",
        },
        {
            "name": "T11-choice-allowed-tools-object",
            "body": responses_body(
                [FUNCTION_TOOL, CLIENT_TOOL_SEARCH],
                tool_choice={
                    "type": "allowed_tools",
                    "tools": [{"type": "function", "name": "get_weather"}],
                },
            ),
            "forced_marker": "function_call",
        },
    ],
    "anthropic": [
        {"name": "A1-control-no-choice", "body": anthropic_body([ANTHROPIC_FUNCTION_TOOL]), "forced_marker": "tool_use"},
        {"name": "A2-choice-auto", "body": anthropic_body([ANTHROPIC_FUNCTION_TOOL], tool_choice={"type": "auto"}), "forced_marker": "tool_use"},
        {"name": "A3-choice-any", "body": anthropic_body([ANTHROPIC_FUNCTION_TOOL], tool_choice={"type": "any"}), "forced_marker": "tool_use"},
        {
            "name": "A4-choice-named-tool",
            "body": anthropic_body(
                [ANTHROPIC_FUNCTION_TOOL], tool_choice={"type": "tool", "name": "get_weather"}
            ),
            "forced_marker": "tool_use",
        },
        {
            "name": "A5-choice-named-disable-parallel",
            "body": anthropic_body(
                [ANTHROPIC_FUNCTION_TOOL],
                tool_choice={"type": "tool", "name": "get_weather", "disable_parallel_tool_use": True},
            ),
            "forced_marker": "tool_use",
        },
    ],
}


async def probe(
    client: httpx.AsyncClient,
    token: str,
    config: GhcClientConfig,
    *,
    name: str,
    body: dict[str, Any],
    forced_marker: str,
    anthropic: bool = False,
) -> None:
    headers = build_request_headers(token, config, interaction_id="probe-260904")
    path = "/v1/messages" if anthropic else "/responses"
    if anthropic:
        headers["anthropic-version"] = "2023-06-01"
    response = await client.post(f"{BASE_URL}{path}", headers=headers, json=body)
    text = response.text

    header = f"# HTTP {response.status_code} content-type: {response.headers.get('content-type', '')}\n\n"
    if response.status_code == 200:
        body_text = json.dumps(scrub(json.loads(text)), indent=2) + "\n"
    else:
        # A refusal body is where account identifiers would show if the endpoint echoed them.
        body_text = scrub_text(text) + "\n"
    (RAW / f"{name}-request.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    (RAW / f"{name}-response.txt").write_text(header + body_text, encoding="utf-8")

    forced_note = ""
    if response.status_code == 200:
        payload = response.json()
        if anthropic:
            kinds = [str(block.get("type")) for block in payload.get("content", [])]
        else:
            kinds = [str(item.get("type")) for item in payload.get("output", [])]
        forced_note = f" forced={'YES' if forced_marker in kinds else 'NO'} kinds={kinds}"
    print(f"=== {name}: HTTP {response.status_code}{forced_note}")
    head = text if len(text) < 400 else text[:400] + f"... [{len(text)} bytes total]"
    print(head + "\n")


def scrub_text(raw: str) -> str:
    """Scrub a whole response body, JSON or not, on its way to disk."""
    try:
        return json.dumps(scrub(json.loads(raw)), indent=2)
    except json.JSONDecodeError:
        return raw


async def run(group: str) -> int:
    assert RAW.resolve().is_relative_to(HERE / "runs")
    RAW.mkdir(parents=True, exist_ok=False)
    print(f"Captures: {RAW}")
    failed = False
    config = GhcClientConfig()
    async with httpx.AsyncClient(timeout=180) as client:
        token = await copilot_token(client, config)
        anthropic = group == "anthropic"
        for spec in SPECS[group]:
            try:
                await probe(client, token, config, anthropic=anthropic, **spec)
            except Exception as error:  # one shot each: record the failure, never retry
                failed = True
                print(f"=== {spec['name']}: FAILED {type(error).__name__}: {error}\n")
    return int(failed)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SPECS:
        print(f"usage: probe.py {{{'|'.join(SPECS)}}}", file=sys.stderr)
        return 2
    return asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
