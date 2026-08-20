"""Durable structured records for completed proxy requests.

Always on and derived rather than configured, like `rejection_capture`: the first incident is the one whose evidence is wanted, and `config.example.yaml` names no setting for this path. One JSON object is appended per completed request, split into UTC-day files so the newest 14 days can be retained by filename alone.
"""

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.config.paths import user_data_path
from app.observability.request_log import RequestLine

logger = logging.getLogger(__name__)

KEEP_DAYS = 14


def request_logs_dir() -> Path:
    """Where completed-request JSONL files are kept."""
    return user_data_path() / "requests"


def utc_timestamp(moment: datetime | None = None) -> str:
    """An ISO-8601 UTC timestamp at the precision used by request records."""
    value = moment or datetime.now(UTC)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_request_record(line: RequestLine, *, status: str) -> Path | None:
    """Append one completed request and return its daily file, or `None` on failure.

    Never raises. Durable observability is subordinate to serving the request: losing the note must not replace or alter the response whose outcome it describes.
    """
    try:
        now = datetime.now(UTC)
        directory = request_logs_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"requests-{now:%Y%m%d}.jsonl"
        record = {"at": utc_timestamp(now), "status": status, **asdict(line)}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
        _prune(directory)
    except Exception as failure:
        # Every failure, not just `OSError`: an invalid path can raise `ValueError` before touching the filesystem, serialization can reject an unexpected value, and this function promises never to affect the request. Report the loss rather than swallowing it, but do not turn an already-determined request outcome into a logging failure.
        logger.warning("could not keep the structured request record: %r", failure)
        return None
    return path


def _prune(directory: Path) -> None:
    """Keep the newest `KEEP_DAYS` UTC-day files, by name.

    The filename ends in `YYYYMMDD`, so lexical order is chronological order and a copied or restored file does not jump the queue because its mtime changed.
    """
    captures = sorted(entry for entry in directory.glob("requests-*.jsonl") if entry.is_file())
    for stale in captures[:-KEEP_DAYS]:
        stale.unlink(missing_ok=True)
