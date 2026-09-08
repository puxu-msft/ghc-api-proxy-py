"""Counterexample probe for `_failure_words` / the two failure branches at d19ae45.

Read-only: imports the worktree's src, feeds malformed payloads, records raise-or-log.
"""

import logging
import sys

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-never-silent-upstream-failure/src")

import orjson

from app.pipeline.delivery.formats.anthropic_messages import AnthropicAssembler
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler
from app.pipeline.delivery.sse_source import SseEvent


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


handler = Capture()
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)


def run(label, assembler_factory, event, data):
    handler.lines.clear()
    a = assembler_factory()
    raw = data if isinstance(data, str) else orjson.dumps(data).decode()
    try:
        out = a.push(SseEvent(event=event, data=raw))
    except BaseException as exc:  # noqa: BLE001 - the whole point is to see if anything escapes
        print(f"{label:52s} RAISED {type(exc).__name__}: {exc}")
        return
    logged = handler.lines[-1] if handler.lines else "<NO LOG LINE>"
    print(f"{label:52s} ok blocks={out!r} seen={a.terminal.seen} | {logged}")


R = ResponsesAssembler
A = AnthropicAssembler

print("=== POSITIVE CONTROL: well-formed, expect a log line with words ===")
run("R error flat (OpenAI shape)", R, "error", {"code": "server_error", "message": "boom"})
run("R response.failed nested", R, "response.failed", {"response": {"error": {"code": "rate_limit_exceeded", "message": "boom"}}})
run("A error nested (Anthropic shape)", A, "error", {"type": "error", "error": {"type": "overloaded_error", "message": "slow down"}})

print()
print("=== THE SHAPE THE PROJECT BELIEVES CAPI ACTUALLY SENDS ===")
run("R error CAPI nested", R, "error", {"type": "error", "error": {"code": "rate_limit", "message": "quota gone"}})

print()
print("=== MALFORMED: does anything raise? ===")
run("R failed: response is a string", R, "response.failed", {"response": "nope"})
run("R failed: response is a list", R, "response.failed", {"response": [1, 2]})
run("R failed: response is null", R, "response.failed", {"response": None})
run("R failed: error is a string", R, "response.failed", {"response": {"error": "nope"}})
run("R failed: error is a list", R, "response.failed", {"response": {"error": ["a"]}})
run("R failed: code is a number", R, "response.failed", {"response": {"error": {"code": 500, "message": "x"}}})
run("R failed: code is null", R, "response.failed", {"response": {"error": {"code": None, "message": "x"}}})
run("R failed: code is a dict", R, "response.failed", {"response": {"error": {"code": {"a": 1}, "message": "x"}}})
run("R failed: message is a list", R, "response.failed", {"response": {"error": {"code": "c", "message": [1, 2]}}})
run("R error: code is null (SDK says str|None)", R, "error", {"code": None, "message": "x"})
run("R error: code is a number", R, "error", {"code": 429, "message": "x"})
run("R cancelled: bare {}", R, "response.cancelled", {})
run("R failed: payload is a JSON array", R, "response.failed", "[1,2,3]")
run("R failed: payload is invalid JSON", R, "response.failed", "{not json")
run("R failed: payload is a JSON string", R, "response.failed", '"hello"')
run("R error: huge message (1MB)", R, "error", {"code": "c", "message": "x" * 1_000_000})
run("A error: error is a string", A, "error", {"type": "error", "error": "nope"})
run("A error: error is a list", A, "error", {"type": "error", "error": [1]})
run("A error: type is a dict", A, "error", {"type": "error", "error": {"type": {"a": 1}, "message": "m"}})
run("A error: bare {}", A, "error", {})
run("A error: invalid JSON", A, "error", "{not json")
