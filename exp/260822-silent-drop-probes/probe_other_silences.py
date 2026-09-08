"""Probe: which other discards on the delivery chain leave no trace at all?

Read-only. Feeds each candidate a payload that should lose content, then reports
whether ANY log record was emitted at ANY level, and whether content survived.
"""

import logging
import sys

sys.path.insert(0, "/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-never-silent-upstream-failure/src")

import orjson

from app.pipeline.delivery.formats.anthropic_messages import AnthropicAssembler
from app.pipeline.delivery.formats.openai_responses import ResponsesAssembler
from app.pipeline.delivery.sse_source import SseEvent, parse_frame


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


handler = Capture()
root = logging.getLogger()
root.addHandler(handler)
root.setLevel(logging.NOTSET)
logging.disable(logging.NOTSET)


def report(label, blocks, extra=""):
    logs = [f"{r.levelname}:{r.getMessage()[:70]}" for r in handler.records]
    trace = "; ".join(logs) if logs else "<<< NO LOG RECORD AT ANY LEVEL >>>"
    print(f"{label}\n    blocks={blocks!r} {extra}\n    {trace}\n")
    handler.records.clear()


def ev(name, payload):
    return SseEvent(event=name, data=payload if isinstance(payload, str) else orjson.dumps(payload).decode())


print("=== POSITIVE CONTROL: the branch d19ae45 added DOES log ===")
a = ResponsesAssembler()
out = a.push(ev("response.failed", {"response": {"error": {"code": "c", "message": "m"}}}))
report("R response.failed (the new branch)", out)

print("=== A1. Responses: a whole output item whose closing frame has corrupt JSON ===")
a = ResponsesAssembler()
a.push(ev("response.output_item.added", {"output_index": 0, "item": {"id": "m1", "type": "message"}}))
a.push(ev("response.output_text.delta", {"output_index": 0, "delta": "hello world"}))
out = a.push(SseEvent(event="response.output_item.done", data='{"output_index": 0, "item": {"id"'))
report("done frame truncated mid-JSON", out, "(the whole message block is gone)")

print("=== A2. Responses: closing frame for an index that was never opened ===")
a = ResponsesAssembler()
out = a.push(ev("response.output_item.done", {"output_index": 7, "item": {"id": "m9", "type": "message", "status": "completed"}}))
report("done for unopened index 7", out, "(item dropped; this is the id-instability failure mode)")

print("=== A3. Responses: a text delta for an index that was never opened ===")
a = ResponsesAssembler()
out = a.push(ev("response.output_text.delta", {"output_index": 3, "delta": "irretrievable text"}))
report("delta for unopened index 3", out, "(text silently discarded)")

print("=== A4. Anthropic: content_block_stop for an index never opened ===")
a = AnthropicAssembler()
out = a.push(ev("content_block_stop", {"index": 5}))
report("content_block_stop index 5", out)

print("=== A5. Anthropic: content_block_delta for an index never opened ===")
a = AnthropicAssembler()
out = a.push(ev("content_block_delta", {"index": 5, "delta": {"type": "text_delta", "text": "lost"}}))
report("content_block_delta index 5", out)

print("=== A6. Both: a payload that is valid JSON but not an object ===")
a = ResponsesAssembler()
out = a.push(SseEvent(event="response.output_item.done", data='["not","an","object"]'))
report("done frame is a JSON array", out)

print("=== A7. An event name neither assembler recognises ===")
a = ResponsesAssembler()
out = a.push(ev("response.refusal.done", {"output_index": 0, "refusal": "I will not answer that"}))
report("response.refusal.done (a real SDK event)", out, "(refusal content dropped)")
a = ResponsesAssembler()
out = a.push(ev("response.mcp_call.failed", {"output_index": 0}))
report("response.mcp_call.failed (a real SDK event)", out)
a = ResponsesAssembler()
out = a.push(ev("some.event.we.never.heard.of", {"x": 1}))
report("a genuinely unknown event name", out)

print("=== A8. Responses: usage that will not convert ===")
a = ResponsesAssembler()
out = a.push(ev("response.completed", {"response": {"usage": {"input_tokens": "not a number"}}}))
report("response.completed with malformed usage", out, f"terminal.usage={a.terminal.usage!r} upstream_usage={a.terminal.upstream_usage!r}")

print("=== A9. sse_source: a frame with a data line but no event line and unparsable JSON ===")
frame = parse_frame(b"data: {broken")
print(f"parse_frame -> {frame!r}")
print(f"  .json() -> {frame.json()!r}   <- the swallow, no log" if frame else "")
handler.records.clear()

print()
print("=== A10. Responses: tool call arguments that do not parse ===")
a = ResponsesAssembler()
a.push(ev("response.output_item.added", {"output_index": 0, "item": {"id": "f1", "type": "function_call", "call_id": "c1", "name": "n"}}))
a.push(ev("response.function_call_arguments.delta", {"output_index": 0, "delta": '{"a": '}))
out = a.push(ev("response.output_item.done", {"output_index": 0, "item": {"id": "f1", "type": "function_call", "call_id": "c1", "name": "n", "status": "completed"}}))
report("function_call with truncated arguments", out, "(kept as __raw marker -- the good pattern)")
