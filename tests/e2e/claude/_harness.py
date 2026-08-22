"""The proxy on a real port, and the real `claude` binary pointed at it.

Everything between the client and the upstream stand-in is the shipping application: the same `create_pipeline_app`, the same chain, the same subscribers. Only the socket to Copilot is replaced. That is the whole point of this group — a test that reimplements any part of the middle can no longer answer what the client would actually receive.

**Isolation is the precondition, not a nicety.** The binary under test is the same one the developer uses, and left alone it would read their credentials, write to their session history, and pick up their `~/.claude` settings. `CLAUDE_CONFIG_DIR` moves all of that into a temporary directory, and the API key is a string that would fail against the real API — the requests go to `ANTHROPIC_BASE_URL` instead, which is us.

**Why a thread rather than a subprocess for the proxy.** The upstream stand-in has to be programmable per test and inspected after it, which means it has to live in the test's own process. Running the proxy there too keeps the stand-in a plain object instead of a second server with its own wire protocol to script over.
"""

import json
import os
import socket
import subprocess
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import httpx2
import uvicorn
from _upstream import BASE_URL, CATALOG, ScriptedUpstream

from app.config.schema import ProxyConfig
from app.model_provider import GithubCopilotProvider
from app.model_provider.ghc_client import GhcApiClient, GhcClientConfig
from app.model_provider.ghc_client.tokens import CopilotTokenManager
from app.server.composition import build_chain
from app.server.pipeline_app import create_pipeline_app

CLAUDE_BINARY = "claude"


class _StaticTokenSource:
    async def get_token(self) -> str:
        return "ghu_test"

    async def refresh(self) -> str | None:
        return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass(slots=True)
class RunningProxy:
    port: int
    upstream: ScriptedUpstream

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@contextmanager
def running_proxy(
    upstream: ScriptedUpstream, *, overrides: dict[str, Any] | None = None
) -> Generator[RunningProxy]:
    """The real application, serving on a real port, talking to `upstream` and nothing else."""
    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI

    http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(upstream.handle))
    tokens = CopilotTokenManager(_StaticTokenSource(), http_client, clock=lambda: 1000)
    client = GhcApiClient(
        AsyncOpenAI(
            api_key="proxy-managed", base_url=BASE_URL, http_client=http_client, max_retries=0
        ),
        AsyncAnthropic(
            api_key="proxy-managed", base_url=BASE_URL, http_client=http_client, max_retries=0
        ),
        tokens,
        GhcClientConfig(api_base_url_override=BASE_URL),
        interaction_id="client-e2e",
    )
    settings: dict[str, Any] = {
        "model_providers": {"ghc": {"type": "github_copilot", "api_base_url": BASE_URL}}
    }
    for key, value in (overrides or {}).items():
        settings[key] = value
    config = ProxyConfig.model_validate(settings)
    provider = GithubCopilotProvider(
        "ghc",
        client,
        config.model_providers["ghc"],
        http_client=http_client,
        base_url=BASE_URL,
    )
    provider.replace_catalog(CATALOG)
    chain = build_chain(config, http_client=http_client, providers={"ghc": provider})

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_pipeline_app(chain), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _await_listening(port)
        yield RunningProxy(port=port, upstream=upstream)
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _await_listening(port: int, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"proxy did not begin listening on {port}")


@dataclass(slots=True)
class ClaudeResult:
    stdout: str
    stderr: str
    returncode: int


def run_claude(
    prompt: str,
    *,
    proxy: RunningProxy,
    config_dir: Path,
    model: str = "claude-model",
    extra_args: list[str] | None = None,
    timeout: float = 120.0,
) -> ClaudeResult:
    """Drive the real binary against the proxy, with nothing of the developer's in reach.

    `stdin` is closed rather than inherited: left open the CLI waits three seconds for piped input before every run, and under pytest that wait is spent against a terminal nobody is typing at.
    """
    env = dict(os.environ)
    env.update(
        {
            "CLAUDE_CONFIG_DIR": str(config_dir),
            "ANTHROPIC_BASE_URL": proxy.base_url,
            "ANTHROPIC_API_KEY": "sk-ant-test-not-a-real-key",
            # Nothing in this group should reach the network. If a future version of the CLI grows a call that ignores `ANTHROPIC_BASE_URL`, the failure should be a refused connection rather than a silent packet leaving the machine.
            "no_proxy": "*",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "DISABLE_AUTOUPDATER": "1",
        }
    )
    args = [CLAUDE_BINARY, "-p", prompt, "--model", model, *(extra_args or [])]
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    return ClaudeResult(
        stdout=completed.stdout, stderr=completed.stderr, returncode=completed.returncode
    )


def claude_available() -> bool:
    """Whether the binary this group drives is installed.

    Checked rather than assumed so the group skips on a machine without it instead of failing with a `FileNotFoundError` that says nothing about why.
    """
    try:
        subprocess.run(
            [CLAUDE_BINARY, "--version"],
            capture_output=True,
            timeout=30,
            check=True,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def written_transcript(config_dir: Path) -> list[dict[str, Any]]:
    """Every JSONL record the CLI wrote for this run, in order.

    The transcript is where the client records what it made of a reply — a `tool_result` and whether it was flagged as an error, which is exactly the thing a proxy cannot see from its own side of the wire.
    """
    records: list[dict[str, Any]] = []
    for path in sorted(config_dir.rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed: object = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(cast(dict[str, Any], parsed))
    return records
