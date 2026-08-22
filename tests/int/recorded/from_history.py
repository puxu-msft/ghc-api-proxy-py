"""Build a cassette from the copilot-api history database instead of making a new call.

Recording needs credentials and a live upstream, so it is the wrong default. The existing service already kept what upstream sent: `~/.local/share/copilot-api/history-v3*.db` stores every SSE frame as a content-addressed object, with a timeline that gives their order and their timestamps.

Two limits, both load-bearing, both encoded below rather than left to a reader's memory:

Frame boundaries, not chunk boundaries. History keeps one object per SSE event, so a cassette built from it replays one frame per chunk. That is a faithful *shape* and a plausible one, but it is not what the wire did — a recording is still the only source for how chunks actually fell. Cassettes from here are marked so nothing mistakes one for the other.

Only the frames upstream actually sent. History stores the same event several times over — once as it arrived, then once per client-side transform that rewrote it — and taking all of them yields a stream where every event repeats three or four times, none of them upstream's. Worse, the copies are *repaired*: `rewrite-out:responses-fix-stream-ids` is the existing service's own fix for the id instability these fixtures exist to capture, so the derived copies show stability that the wire did not have. `_upstream_frames` keeps the roots of the transform graph and nothing else.

The text is somebody's real conversation. These databases hold the operator's own prompts, source code and tool output, so every free-text field is replaced with a placeholder of the same shape.
What survives is the protocol: event order, field structure, ids, indices, block types. That is exactly what a fixture is for, and it is the part that cannot be imagined correctly.
"""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import orjson
import zstandard

from recorded.cassettes import Cassette, Interaction

HISTORY_DIR = Path.home() / ".local/share/copilot-api"
CASSETTE_DIR = Path(__file__).resolve().parents[1] / "cassettes"

# String fields worth keeping, by name. An allowlist because naming what to *remove* missed `description`, `instructions` and `definition` — tool definitions and system prompts echoed back inside the response — on the first attempt. Everything here is structural: it names a kind, a state or a position, and none of it is anybody's prose.
STRUCTURAL_FIELDS = frozenset(
    {
        "type",
        "role",
        "status",
        "object",
        "event",
        "model",
        "stop_reason",
        "finish_reason",
        "reason",
        "effort",
        "mode",
        "context",
        "service_tier",
        "truncation",
    }
)

# Identifiers keep their shape because the assembler pairs on them, and the whole reason a real capture is worth having is that upstream does not always keep them stable. Substituted rather than passed through: an id is opaque, and an opaque value may carry more than an id.
IDENTIFIER_FIELDS = frozenset({"id", "item_id", "call_id", "response_id", "previous_response_id"})

PLACEHOLDER = "placeholder"


@dataclass(frozen=True, slots=True)
class Selection:
    """Which operation to build a cassette from."""

    endpoint: str
    stream: bool = True
    success: bool = True
    model: str | None = None


def history_databases() -> list[Path]:
    """Every history database that still carries frames, newest first.

    The service stopped writing frame objects on 2026-08-15, so the newest database is often not the newest *usable* one. Ordered by modification time and filtered by what is actually there, rather than by a date in a filename.
    """
    candidates = sorted(HISTORY_DIR.glob("history-v3*.db"), key=lambda p: p.stat().st_mtime)
    usable: list[Path] = []
    for path in candidates:
        with sqlite3.connect(f"file:{path}?immutable=1", uri=True) as db:
            try:
                frames = db.execute(
                    "select count(*) from v3_objects where kind='frame' limit 1"
                ).fetchone()
            except sqlite3.DatabaseError:
                continue
        if frames and frames[0]:
            usable.append(path)
    return list(reversed(usable))


def _scrub(value: object, identifiers: dict[str, str], field: str = "") -> object:
    """Keep the protocol, drop the prose.

    Every string is replaced unless its field name is structural. Identifiers are replaced too, but consistently: the same original always becomes the same substitute, so a capture where upstream changed an item's id between `added` and `done` still shows two different ids — which is the one property these fixtures exist to carry.
    """
    if isinstance(value, dict):
        entry = cast(dict[str, Any], value)
        return {name: _scrub(inner, identifiers, name) for name, inner in entry.items()}
    if isinstance(value, list):
        return [_scrub(item, identifiers, field) for item in cast(list[Any], value)]
    if isinstance(value, str):
        if not value or field in STRUCTURAL_FIELDS:
            return value
        if field in IDENTIFIER_FIELDS:
            return identifiers.setdefault(value, f"id_{len(identifiers):03d}")
        return PLACEHOLDER
    return value


def _upstream_frames(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The frames upstream sent, dropping the rewritten copies of them.

    Every `transform` entry names the frames it consumed and the frames it produced, so the ones upstream sent are exactly the frames that no transform produced. Without this the same event comes back three or four times, and the copies have already been through the existing service's id repair — which would quietly hide the behaviour these fixtures are here to record.
    """
    derived = {
        output["handle"]
        for event in events
        if event.get("type") == "transform"
        for output in cast(dict[str, Any], event.get("value", {})).get("outputs", [])
        if cast(dict[str, Any], output).get("kind") == "frame"
    }
    return sorted(
        (
            event
            for event in events
            if event.get("type") == "frame" and event.get("handle") not in derived
        ),
        key=lambda event: int(event["sequence"]),
    )


def _frames(db: sqlite3.Connection, operation_id: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every SSE frame upstream sent for one operation, in the order it arrived."""
    decompressor = zstandard.ZstdDecompressor()
    manifest = orjson.loads(
        decompressor.decompress(
            cast(
                bytes,
                db.execute(
                    "select manifest_gz from v3_operations where operation_id=?", (operation_id,)
                ).fetchone()[0],
            )
        )
    )
    hashes = cast(dict[str, str], manifest["objectHashes"])
    # Shared across the whole operation so one original id keeps one substitute throughout.
    identifiers: dict[str, str] = {}

    events: list[dict[str, Any]] = []
    for row in db.execute(
        "select payload_gz from v3_timeline_chunks where operation_id=? order by chunk_index",
        (operation_id,),
    ):
        events.extend(cast(list[dict[str, Any]], orjson.loads(decompressor.decompress(row[0]))))

    for event in _upstream_frames(events):
        digest = hashes.get(str(event.get("handle", "")))
        if digest is None:
            continue
        stored = db.execute(
            "select canonical_gz from v3_objects where hash=?", (digest,)
        ).fetchone()
        if stored is None:
            continue
        frame = cast(dict[str, Any], orjson.loads(decompressor.decompress(stored[0])))
        raw = frame.get("data")
        if not isinstance(raw, str):
            continue
        try:
            payload = cast(dict[str, Any], orjson.loads(raw))
        except orjson.JSONDecodeError:
            continue
        name = str(frame.get("event") or payload.get("type", ""))
        yield name, cast(dict[str, Any], _scrub(payload, identifiers))


def find_operation(db: sqlite3.Connection, selection: Selection) -> str | None:
    """The most recent operation matching the selection, or None."""
    query = (
        "select operation_id from v3_operations"
        " where json_extract(summary_json,'$.endpoint')=?"
        " and json_extract(summary_json,'$.stream')=?"
        " and json_extract(summary_json,'$.responseSuccess')=?"
    )
    params: list[Any] = [selection.endpoint, int(selection.stream), int(selection.success)]
    if selection.model is not None:
        query += " and json_extract(summary_json,'$.responseModel')=?"
        params.append(selection.model)
    query += " order by created_at desc limit 1"
    row = db.execute(query, params).fetchone()
    return str(row[0]) if row else None


def build(selection: Selection, path: str) -> Cassette:
    """A cassette carrying one recorded upstream response, scrubbed of its content."""
    for database in history_databases():
        with sqlite3.connect(f"file:{database}?immutable=1", uri=True) as db:
            operation_id = find_operation(db, selection)
            if operation_id is None:
                continue
            chunks = [
                f"event: {name}\ndata: {orjson.dumps(payload).decode()}\n\n".encode()
                for name, payload in _frames(db, operation_id)
            ]
            if not chunks:
                continue
            return Cassette(
                interactions=[
                    Interaction(
                        method="POST",
                        path=path,
                        authenticated=True,
                        # Left empty: history records no request body, so there is nothing to project. A replay of this cassette checks order and path, not shape.
                        request_shape={},
                        status=200,
                        headers={"content-type": "text/event-stream"},
                        extensions={"http_version": "HTTP/1.1"},
                        chunks=chunks,
                        source=f"history:{database.name}:{operation_id}",
                    )
                ]
            )
    raise LookupError(f"no history operation matches {selection}")


SCENARIOS: dict[str, tuple[Selection, str]] = {
    "history_responses_stream": (
        Selection(endpoint="openai-responses", model="gpt-5.5"),
        "/responses",
    ),
    "history_anthropic_stream": (
        Selection(endpoint="anthropic-messages"),
        "/v1/messages",
    ),
    "history_anthropic_failure": (
        Selection(endpoint="anthropic-messages", success=False),
        "/v1/messages",
    ),
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SCENARIOS:
        print(f"usage: from_history.py {{{'|'.join(SCENARIOS)}}}", file=sys.stderr)
        return 2
    name = sys.argv[1]
    selection, path = SCENARIOS[name]
    cassette = build(selection, path)
    destination = CASSETTE_DIR / f"{name}.json"
    cassette.write(destination)
    interaction = cassette.interactions[0]
    print(f"wrote {destination} ({len(interaction.chunks)} frames)")
    print(f"  from {interaction.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
