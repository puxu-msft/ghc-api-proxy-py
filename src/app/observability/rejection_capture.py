"""What was actually sent, kept when upstream refuses to read it.

A rejection is upstream's verdict on a body, and the body is the one thing this proxy did not keep. Twice in one day — `The use of the web search tool is not supported.` and `messages: text content blocks must be non-empty` — the investigation had to reconstruct the outbound request from the *client's* own transcripts, because the pipeline records no history and the request that caused the refusal is gone the moment the response is written. Both times the reconstruction worked; neither time was that a property of this service.

**Only 4xx that is not a rate limit.** `UpstreamRejected` is the closed set of "upstream read this and would not take it" — a 429 is about pace and a 5xx is about upstream itself, and neither is answered by looking at the body. Timeouts and connection failures never got a verdict at all.

**Always on, and derived rather than configured.** These are supposed to be rare; the run where one first happens is the run whose evidence is wanted, and a switch that has to be turned on beforehand is a switch that is off when it matters. `config.example.yaml` has no key for this, and inventing one would put a decision in the operator's hands that they can only get wrong in one direction. The cost is bounded instead: the newest few are kept and the rest are pruned on the way in.

**Two forms of the body, because they are two different facts.** `payload` is the dict the pipeline built, after translation and after every subscriber; `sent` is the bytes httpx put on the wire. They are usually the same request said twice, and the day they are not is the day one of them is the answer: a refusal about a duplicated key, a number's spelling, or an encoding cannot be read off a dict that was never serialized. See `UpstreamRejected.sent` for why the bytes have to be carried on the error rather than fetched here.

**Headers are not written.** Not redaction — scope. What answers "why was this refused" is the body and upstream's own words about it; the request headers are the same on the request that succeeded a second earlier.
"""

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config.paths import user_data_path
from app.pipeline.exceptions import UpstreamRejected
from app.pipeline.request import RequestContext

logger = logging.getLogger(__name__)

# Enough to see a pattern across a session, few enough that a storm cannot fill a disk. A rejected body is as large as the conversation that produced it, so this is bounded by count rather than by age: an operator reading these wants the last few, whenever they happened.
KEEP_NEWEST = 50


def rejected_requests_dir() -> Path:
    """Where refused request bodies are kept.

    Derived rather than configured, for the same reason as `tokenization_state_path`: the spec names no key for it, and one invented here would be a decision the operator did not ask to make.
    """
    return user_data_path() / "rejected"


def _jsonable(value: Any) -> Any:
    """Whatever `json` can write, for the few typed facts that ride alongside the payload."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return str(value)


def capture_rejection(context: RequestContext, error: BaseException, *, request_id: str = "") -> Path | None:
    """Write the refused body to disk and return where it went, or `None` if there was nothing to write.

    Never raises. A request that upstream refused is already being reported to the client, and failing to keep a note about it must not turn that report into something else.
    """
    if not isinstance(error, UpstreamRejected):
        return None

    sent = error.sent
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%f")[:-3]
    name = f"{stamp}-{error.status_code}-{request_id or context.id}.json"
    record: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "request_id": request_id or context.id,
        "status": error.status_code,
        # Upstream's own words, kept apart from ours so nothing reads this wrapper's wording as though upstream had said it.
        "upstream": error.body,
        "proxy_error": str(error),
        "requested_model": context.requested_model,
        "resolved_model": context.resolved_model,
        "provider": context.provider_name,
        "endpoint": getattr(context.endpoint, "value", None),
        "target_format": getattr(context.target_format, "value", None),
        "translation_required": context.translation_required,
        "route_reason": context.route_reason,
        "attempts": context.attempt_count,
        # The point of the file. This is the payload as it stood when the attempt was made, which is after translation and after every `attempt.prepare` subscriber has had it.
        "payload": context.payload,
        # And what actually crossed the wire. `payload` above is a dict that had yet to be serialized, so it cannot show key order, separators, or anything the SDK did on the way out — and upstream's verdict is a verdict on the bytes, not on the dict they were built from. Only the length of these was ever recorded before, which answers "was it big" and nothing else.
        # Both halves are always written. `sent_bytes` is the exact length whatever happens to the text beside it, so a zero there says the failure reached us without a request attached — the SDK boundary is the only place these are read, and a refusal synthesised anywhere else has none — rather than saying upstream refused an empty body.
        "sent_bytes": len(sent),
        # `replace` rather than a strict decode: these are JSON bodies the SDK serialized and are UTF-8 by construction, and the substitution is there so a body that somehow is not still gets written instead of losing the whole capture to a decode error. `sent_bytes` stays exact, so a substitution shows up as a length that no longer matches the text.
        "sent": sent.decode("utf-8", errors="replace"),
    }

    try:
        directory = rejected_requests_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(json.dumps(record, indent=2, default=_jsonable) + "\n", encoding="utf-8")
        _prune(directory)
    except Exception as failure:
        # Every failure, not just `OSError`: a path the operator's environment made unusable raises `ValueError` before it ever reaches the filesystem, and this promised not to raise. Reported rather than swallowed, and not re-raised — the client is already being told what upstream said, and that answer must not be replaced by a problem with the note about it.
        logger.warning("could not keep the refused request body: %r", failure)
        return None

    logger.info("upstream refused a request; the body it refused is at %s", path)
    return path


def _prune(directory: Path) -> None:
    """Keep the newest `KEEP_NEWEST` captures, by name.

    By name rather than by mtime because the name begins with a UTC timestamp, so lexical order is chronological order and a file copied or restored out of band does not jump the queue.
    """
    captures = sorted(entry for entry in directory.glob("*.json") if entry.is_file())
    for stale in captures[:-KEEP_NEWEST]:
        stale.unlink(missing_ok=True)
