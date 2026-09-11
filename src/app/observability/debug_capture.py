"""SQLite-backed rules that select individual requests for raw capture."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock


@dataclass(frozen=True, slots=True)
class DebugCaptureRule:
    id: int
    provider: str
    model_id: str
    session_id: str
    agent_id: str | None
    created_at: str

    def as_dict(self) -> dict[str, int | str | None]:
        return {
            "id": self.id,
            "provider": self.provider,
            "model_id": self.model_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "created_at": self.created_at,
        }


class DebugCaptureRuleStore:
    """A small serialized SQLite interface for request-selection rules.

    The connection is private to this store and all operations use the same lock.
    This keeps rule changes and request matches ordered without making callers know
    anything about SQLite transactions.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(
            str(path),
            timeout=5.0,
            check_same_thread=False,
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS debug_capture_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE (provider, model_id, session_id, agent_id)
            );
            CREATE INDEX IF NOT EXISTS debug_capture_rules_match
                ON debug_capture_rules (provider, model_id, session_id, agent_id);
            """
        )
        self._connection.commit()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._connection.close()

    def list_rules(self) -> tuple[DebugCaptureRule, ...]:
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT id, provider, model_id, session_id, agent_id, created_at
                FROM debug_capture_rules
                ORDER BY id
                """
            ).fetchall()
        return tuple(self._row_to_rule(row) for row in rows)

    def create_rule(
        self,
        *,
        provider: str,
        model_id: str,
        session_id: str,
        agent_id: str | None = None,
    ) -> tuple[DebugCaptureRule, bool]:
        normalized = self._normalize(provider, model_id, session_id, agent_id)
        with self._lock:
            self._ensure_open()
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO debug_capture_rules
                    (provider, model_id, session_id, agent_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (*normalized[:3], normalized[3], _now()),
            )
            self._connection.commit()
            row = self._connection.execute(
                """
                SELECT id, provider, model_id, session_id, agent_id, created_at
                FROM debug_capture_rules
                WHERE provider = ? AND model_id = ? AND session_id = ? AND agent_id = ?
                """,
                normalized,
            ).fetchone()
        if row is None:
            raise RuntimeError("created debug capture rule could not be read back")
        return self._row_to_rule(row), cursor.rowcount == 1

    def delete_rule(self, rule_id: int) -> bool:
        if rule_id <= 0:
            return False
        with self._lock:
            self._ensure_open()
            cursor = self._connection.execute(
                "DELETE FROM debug_capture_rules WHERE id = ?",
                (rule_id,),
            )
            self._connection.commit()
        return cursor.rowcount == 1

    def matches(
        self,
        *,
        provider: str,
        model_id: str,
        session_id: str,
        agent_id: str | None = None,
    ) -> bool:
        normalized = self._normalize(provider, model_id, session_id, agent_id)
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                """
                SELECT 1
                FROM debug_capture_rules
                WHERE provider = ? AND model_id = ? AND session_id = ?
                  AND (agent_id = '' OR agent_id = ?)
                LIMIT 1
                """,
                (*normalized[:3], normalized[3]),
            ).fetchone()
        return row is not None

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("debug capture rule store is closed")

    @staticmethod
    def _normalize(
        provider: str,
        model_id: str,
        session_id: str,
        agent_id: str | None,
    ) -> tuple[str, str, str, str]:
        if not provider.strip() or not model_id.strip() or not session_id.strip():
            raise ValueError("provider, model_id and session_id must be non-empty strings")
        if agent_id is not None and not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string when supplied")
        return (
            provider.strip(),
            model_id.strip(),
            session_id.strip(),
            agent_id.strip() if agent_id is not None else "",
        )

    @staticmethod
    def _row_to_rule(row: tuple[object, ...]) -> DebugCaptureRule:
        rule_id, provider, model_id, session_id, agent_id, created_at = row
        if (
            type(rule_id) is not int
            or not isinstance(provider, str)
            or not isinstance(model_id, str)
            or not isinstance(session_id, str)
            or not isinstance(agent_id, str)
            or not isinstance(created_at, str)
        ):
            raise RuntimeError("debug capture rule database contains an invalid row")
        return DebugCaptureRule(
            id=rule_id,
            provider=provider,
            model_id=model_id,
            session_id=session_id,
            agent_id=agent_id or None,
            created_at=created_at,
        )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = ["DebugCaptureRule", "DebugCaptureRuleStore"]
