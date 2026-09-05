"""CodeBuddy provider live probe — hand-run, never in the test suite.

实测文化(见记忆 ghc-api-proxy-live-probe-culture):每个新上站的拼写,先跑真实请求,
raw/ 存脱敏请求/响应,一次性发送不重试。

Prerequisites:
  1. 桌面端 WorkBuddy/CodeBuddy 已登录(或 CODEBUDDY_AUTH_DIR 指向含 .info 的目录)。
  2. PYTHONPATH=src uv run python exp/260904-codebuddy-provider/probe.py [--model glm-5.2]

Checks, in order:
  P1 auth file discovery + summary (uid / expiry)
  P2 request headers build (no network)
  P3 token refresh (only when expired) — response shape {code:0, data:{...}}
  P4 streaming chat completion — 1 token prompt, stream=True, SSE chunk vocabulary
  P5 tool_calls round trip — one tool, name + arguments deltas on the stream
  P6 non-streaming behaviour — upstream *refuses* stream:false? (reference claims
     streaming-only; this is the negative control that proves it)

Every raw request/response pair lands in raw/ with secrets replaced before writing.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx2

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.model_provider.codebuddy_client.auth_state import (  # noqa: E402
    CodebuddyCredentials,
    DesktopAuthState,
    discover_auth_file,
)
from app.model_provider.codebuddy_client.client import CodebuddyClient  # noqa: E402
from app.model_provider.codebuddy_client.config import CodebuddyClientConfig  # noqa: E402

RAW_DIR = Path(__file__).parent / "raw"


def desensitize(obj):  # type: ignore[no-untyped-def]
    if isinstance(obj, dict):
        return {
            key: ("***" if any(s in key.lower() for s in ("token", "authorization")) else desensitize(value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [desensitize(item) for item in obj]
    if isinstance(obj, str) and len(obj) > 400:
        return obj[:200] + "...<truncated>"
    return obj


def dump(name: str, payload):  # type: ignore[no-untyped-def]
    RAW_DIR.mkdir(exist_ok=True)
    path = RAW_DIR / f"{name}.json"
    path.write_text(json.dumps(desensitize(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  raw -> {path}")


async def main() -> int:  # type: ignore[no-untyped-def]
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="glm-5.2")
    parser.add_argument("--skip-network", action="store_true")
    args = parser.parse_args()

    print("P1: auth file discovery")
    state_path = discover_auth_file()
    print(f"  state file: {state_path or '(none found)'}")
    if not state_path:
        return 1
    state = DesktopAuthState(state_path)
    print(f"  summary: {json.dumps(desensitize(state.summary()), ensure_ascii=False)}")

    print("P2: request headers (no network)")
    config = CodebuddyClientConfig()
    http_client = httpx2.AsyncClient()
    credentials = CodebuddyCredentials(state, http_client, config)
    try:
        headers = await credentials.request_headers()
        print(f"  header names: {sorted(headers)}")
        print(f"  X-Domain: {headers.get('X-Domain')}, X-User-Id present: {'X-User-Id' in headers}")

        if args.skip_network:
            print("(network skipped)")
            return 0

        client = CodebuddyClient(config, credentials, http_client=http_client)

        print("P4: streaming chat completion")
        started = time.time()
        response = await client.send_chat_completions(
            {
                "model": args.model,
                "messages": [{"role": "user", "content": "回答:1+1=?只回答数字"}],
                "max_tokens": 2000,
            },
            stream=True,
        )
        print(f"  status: {response.status_code} after {time.time() - started:.1f}s")
        lines: list[str] = []
        async for line in response.aiter_lines():
            lines.append(line)
            if len(lines) > 400:
                break
        await response.aclose()
        dump("p4-stream-lines", {"lines": lines[:400]})
        print(f"  lines: {len(lines)} (first data line: {next((l for l in lines if l.startswith('data:')), '')[:120]})")

        print("P5: tool_calls round trip")
        response = await client.send_chat_completions(
            {
                "model": args.model,
                "messages": [{"role": "user", "content": "深圳天气如何?必须调用工具查询"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "查询城市天气",
                            "parameters": {
                                "type": "object",
                                "properties": {"city": {"type": "string"}},
                                "required": ["city"],
                            },
                        },
                    }
                ],
            },
            stream=False,
        )
        body = json.loads(response.content)
        dump("p5-tool-aggregated", body)
        message = body["choices"][0]["message"]
        print(f"  finish: {body['choices'][0]['finish_reason']}, tool_calls: {message.get('tool_calls')}")

        print("P6: negative control — stream:false on the wire")
        async with httpx2.AsyncClient() as bare:
            try:
                answer = await bare.post(
                    f"{config.api_base_url}/v2/chat/completions",
                    headers=headers,
                    json={
                        "model": args.model,
                        "messages": [{"role": "user", "content": "1+1"}],
                        "stream": False,
                    },
                )
                dump("p6-non-stream", {"status": answer.status_code, "body": answer.text[:2000]})
                print(f"  stream:false answered {answer.status_code} — reference claim 'streaming-only' needs rechecking")
            except httpx2.HTTPError as error:
                print(f"  stream:false transport error: {error}")
    finally:
        await http_client.aclose()

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
