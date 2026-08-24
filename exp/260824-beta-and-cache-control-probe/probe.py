"""What this upstream does with `cache_control.scope` and with the betas Claude Code negotiates.

Run by hand, never by the test suite: it needs credentials and it makes real calls.

    PYTHONPATH=src .venv/bin/python exp/260824-beta-and-cache-control-probe/probe.py

Two 400s from a user's machine started this, both on the direct path — the body travels to `/v1/messages` as the client wrote it:

    system.1.cache_control.ephemeral.scope: Extra inputs are not permitted
    unsupported beta header(s): tool-search-tool-2025-10-19

The second envelope is the Copilot gateway's own shape (`{"error": {"message", "code"}}`) rather than Anthropic's, so the two rejections are made by different layers. That is the first thing this probe has to confirm rather than assume.

**What cannot be read off the code**, and is therefore why this exists:

- Whether the `scope` field is refused *because* the enabling beta was absent. If sending `prompt-caching-scope-2026-01-05` makes the same body pass, the repair is a header to add, not a field to strip — the opposite change. C3 is that control.
- Which betas this gateway accepts at all. The strip table in the config is per-model because a capability belongs to a model; but `unsupported beta header(s)` is a gateway envelope, which suggests a deployment-wide allowlist instead. B-series measures the list.
- Whether stripping a beta leaves the body broken. `request_headers.py` warns that a field the beta enabled becomes an unrecognised field and upstream answers 400 rather than ignoring it. If `defer_loading` and a `tool_search_tool_regex_*` tool are refused on their own, then removing the header is not a fix by itself. T-series measures that.

C0 is the positive control and is not optional. A row of 400s could equally mean the credentials lapsed or the model name is wrong; C0 sends an ordinary body in the same run with the same credentials, and if it is not 200 nothing else here may be read as a verdict.

Prompts are trivial and `max_tokens` is small. Each case is sent once; a failure is recorded, not retried. The Copilot token rides through the wire untouched and is scrubbed only on the way to disk.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from app.model_provider.ghc_client.config import GhcClientConfig
from app.model_provider.ghc_client.headers import build_identity_headers, build_request_headers

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
TOKEN_FILE = Path.home() / ".local/share/ghc-api-proxy/github_token"

AUTH_URL = "https://api.github.com/copilot_internal/v2/token"

# The model the user's own 400s named. Kept rather than swapped for a cheaper one: a beta is a capability of the model that answers, so a verdict measured on another model would not transfer.
MODEL = "claude-opus-5"
TRIVIAL = "Say OK."

REDACT_FIELDS = frozenset({"token", "tracking_id", "enterprise_list", "organization_list", "safety_identifier"})
REDACTION = "REDACTED"

# The betas Claude Code negotiates, as observed in the two rejected requests plus the table in `config.example.yaml`. Sent one per case in the B series so the gateway names one flag at a time — sending them together only reveals whichever it complains about first.
CANDIDATE_BETAS = [
    "claude-code-20250219",
    "oauth-2025-04-20",
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
    "context-management-2025-06-27",
    "prompt-caching-2024-07-31",
    "extended-cache-ttl-2025-04-11",
    "prompt-caching-scope-2026-01-05",
    "mid-conversation-system-2026-04-07",
    "tool-search-tool-2025-10-19",
    "tool-search-tool-2025-11-19",
    "advanced-tool-use-2025-11-20",
    "token-efficient-tools-2025-02-19",
    "output-128k-2025-02-19",
]

WEATHER: dict[str, Any] = {
    "name": "get_weather",
    "description": "Get the weather.",
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
}


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTION if k in REDACT_FIELDS else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


async def copilot_token(client: httpx.AsyncClient, config: GhcClientConfig) -> tuple[str, str]:
    """The Copilot token and the API base url this account resolves to.

    The base url comes from the exchange rather than from a constant: this account resolves to the enterprise host, which is the host both of the user's 400s name.
    """
    gh = TOKEN_FILE.read_text(encoding="utf-8").strip()
    headers = {
        **build_identity_headers(config),
        "Accept": "application/json",
        "Authorization": f"token {gh}",
        "X-GitHub-Api-Version": "2025-04-01",
    }
    response = await client.get(AUTH_URL, headers=headers)
    response.raise_for_status()
    payload = response.json()
    return str(payload["token"]), str(payload["endpoints"]["api"]).rstrip("/")


def body(
    *,
    system: Any = None,
    tools: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": TRIVIAL}],
    }
    if system is not None:
        payload["system"] = system
    if tools is not None:
        payload["tools"] = tools
    if extra:
        payload.update(extra)
    return payload


def system_blocks(cache_control: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Two system blocks, the marker on the second — index 1, exactly where the user's 400 pointed."""
    second: dict[str, Any] = {"type": "text", "text": "Be concise."}
    if cache_control is not None:
        second["cache_control"] = cache_control
    return [{"type": "text", "text": "You are a helpful assistant."}, second]


CASES: list[dict[str, Any]] = [
    {
        "name": "C0-control-plain",
        "why": "Positive control. If this is not 200, nothing below is a verdict on anything.",
        "body": body(),
    },
    {
        "name": "C1-cache-control-bare-ephemeral",
        "why": "The shape the sanitize mode would produce. Establishes that a marker is accepted at all.",
        "body": body(system=system_blocks({"type": "ephemeral"})),
    },
    {
        "name": "C2-cache-control-scope-no-beta",
        "why": "Reproduces the user's first 400 verbatim: scope on system[1], no enabling beta.",
        "body": body(system=system_blocks({"type": "ephemeral", "scope": "organization"})),
    },
    {
        "name": "C3-cache-control-scope-with-beta",
        "why": "THE control that decides the repair's direction. If the beta makes C2 pass, the fix is a header to add rather than a field to strip.",
        "beta": "prompt-caching-scope-2026-01-05",
        "body": body(system=system_blocks({"type": "ephemeral", "scope": "organization"})),
    },
    {
        "name": "C4-cache-control-ttl-1h-no-beta",
        "why": "Whether a second well-known non-bare field fares the same, which says whether the repair must be a whitelist rather than a scope-shaped patch.",
        "body": body(system=system_blocks({"type": "ephemeral", "ttl": "1h"})),
    },
    {
        "name": "C5-cache-control-ttl-1h-with-beta",
        "why": "Pairs with C4. Together with C2/C3 it says whether this gateway honours enabling betas for body fields at all.",
        "beta": "extended-cache-ttl-2025-04-11",
        "body": body(system=system_blocks({"type": "ephemeral", "ttl": "1h"})),
    },
    {
        "name": "C6-scope-on-a-message-block",
        "why": "Whether the refusal is about system specifically or about cache_control anywhere, which decides how wide the strip has to reach.",
        "body": {
            "model": MODEL,
            "max_tokens": 16,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": TRIVIAL, "cache_control": {"type": "ephemeral", "scope": "organization"}}
                    ],
                }
            ],
        },
    },
    {
        "name": "C7-scope-on-a-tool",
        "why": "Same question for the tools layer, which carries its own cache_control and is a separate schema upstream.",
        "body": body(tools=[{**WEATHER, "cache_control": {"type": "ephemeral", "scope": "organization"}}]),
    },
    {
        "name": "T1-defer-loading-no-beta",
        "why": "What a tool-search body looks like once its beta has been stripped. If this is 400, stripping the header alone leaves the request broken.",
        "body": body(tools=[{**WEATHER, "defer_loading": True}]),
    },
    {
        "name": "T2-tool-search-tool-no-beta",
        "why": "The server tool the beta introduces, with the header removed. Same question as T1 for the other field the beta enables.",
        "body": body(
            tools=[
                {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},
                {**WEATHER, "defer_loading": True},
            ]
        ),
    },
    {
        "name": "T3-tool-search-tool-with-1119-beta",
        "why": "The same body with the flag the previous proxy was seen sending. If this passes, the repair is a beta rewrite rather than a strip.",
        "beta": "tool-search-tool-2025-11-19",
        "body": body(
            tools=[
                {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},
                {**WEATHER, "defer_loading": True},
            ]
        ),
    },
    {
        "name": "T4-defer-loading-with-1019-beta",
        "why": "The client's own combination, reproduced. Separates 'the flag is unknown' from 'the body is unacceptable'.",
        "beta": "tool-search-tool-2025-10-19",
        "body": body(tools=[{**WEATHER, "defer_loading": True}]),
    },
]

# One case per candidate beta, each sent alone with an otherwise ordinary body. Alone rather than together because the gateway names what it refuses, and a batch only reveals the first refusal.
CASES.extend(
    {
        "name": f"B-{flag}",
        "why": "Does this gateway accept the flag at all, with a body that uses nothing it enables.",
        "beta": flag,
        "body": body(),
    }
    for flag in CANDIDATE_BETAS
)


async def run() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    config = GhcClientConfig(account_type="enterprise")
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        token, base_url = await copilot_token(client, config)
        print(f"api base url: {base_url}\nmodel: {MODEL}\n")

        for case in CASES:
            headers = build_request_headers(token, config, interaction_id=str(uuid4()))
            beta = case.get("beta")
            if beta:
                headers["anthropic-beta"] = str(beta)
            try:
                response = await client.post(
                    f"{base_url}/v1/messages", headers=headers, json=case["body"]
                )
                status = response.status_code
                text = response.text
            except Exception as exc:  # noqa: BLE001 — a transport failure is a result here, not a crash
                status = 0
                text = f"{type(exc).__name__}: {exc}"

            verdict = "OK " if status == 200 else "400" if status == 400 else str(status)
            message = ""
            if status != 200:
                try:
                    parsed = json.loads(text)
                    error = parsed.get("error", {})
                    message = error.get("message") or json.dumps(error)[:200]
                except (json.JSONDecodeError, AttributeError):
                    message = text[:200]
            print(f"[{verdict}] {case['name']}: {message}")

            results.append(
                {
                    "name": case["name"],
                    "why": case["why"],
                    "beta": beta,
                    "status": status,
                    "body": scrub(case["body"]),
                    "response": text[:4000],
                }
            )

    (RAW / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {RAW / 'results.json'}")


if __name__ == "__main__":
    asyncio.run(run())
