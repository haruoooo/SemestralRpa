"""Robot state persisted in SQLite (single local file, no server)."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.domain.lineStatus import LineReading, LineStatusCode

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineState (
    lineNumber INTEGER PRIMARY KEY,
    lineName TEXT NOT NULL,
    rawText TEXT NOT NULL,
    status TEXT NOT NULL,
    sourceUpdatedAt TEXT,
    savedAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processedFile (
    fileHash TEXT PRIMARY KEY,
    fileName TEXT NOT NULL,
    outcome TEXT NOT NULL,
    processedAt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    outboxId INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    idempotencyKey TEXT NOT NULL,
    payload TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 1,
    lastError TEXT,
    createdAt TEXT NOT NULL,
    UNIQUE (kind, idempotencyKey)
);
CREATE TABLE IF NOT EXISTS keyValue (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SqliteRobotState:
    def __init__(self, dbPath: Path):
        if str(dbPath) != ":memory:":
            dbPath.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(dbPath))
        self._connection.executescript(_SCHEMA)

    def getLastLineStatus(self, lineNumber: int) -> LineStatusCode | None:
        row = self._connection.execute("SELECT status FROM lineState WHERE lineNumber = ?", (lineNumber,)).fetchone()
        return LineStatusCode(row[0]) if row else None

    def saveLineStatus(self, reading: LineReading, savedAt: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO lineState VALUES (?, ?, ?, ?, ?, ?)",
                (
                    reading.lineNumber,
                    reading.lineName,
                    reading.rawText,
                    reading.status.value,
                    reading.sourceUpdatedAt.isoformat() if reading.sourceUpdatedAt else None,
                    savedAt.isoformat(),
                ),
            )

    def getLastReadings(self) -> list[LineReading]:
        rows = self._connection.execute(
            "SELECT lineNumber, lineName, rawText, status, sourceUpdatedAt FROM lineState ORDER BY lineNumber"
        ).fetchall()
        return [
            LineReading(
                lineNumber=row[0],
                lineName=row[1],
                rawText=row[2],
                status=LineStatusCode(row[3]),
                sourceUpdatedAt=datetime.fromisoformat(row[4]) if row[4] else None,
            )
            for row in rows
        ]

    def getLastSourceSuccessAt(self) -> datetime | None:
        row = self._connection.execute("SELECT value FROM keyValue WHERE key = 'lastSourceSuccessAt'").fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def saveSourceSuccessAt(self, moment: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO keyValue VALUES ('lastSourceSuccessAt', ?)", (moment.isoformat(),)
            )

    # ---------- scheduleImportFlow ----------

    def isFileProcessed(self, fileHash: str) -> bool:
        return self._connection.execute("SELECT 1 FROM processedFile WHERE fileHash = ?", (fileHash,)).fetchone() is not None

    def markFileProcessed(self, fileHash: str, fileName: str, outcome: str, processedAt: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO processedFile VALUES (?, ?, ?, ?)", (fileHash, fileName, outcome, processedAt.isoformat())
            )

    def enqueueOutbox(self, kind: str, idempotencyKey: str, payload: dict, error: str, createdAt: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO outbox (kind, idempotencyKey, payload, lastError, createdAt) VALUES (?, ?, ?, ?, ?)",
                (kind, idempotencyKey, json.dumps(payload, ensure_ascii=False), error, createdAt.isoformat()),
            )

    def listOutbox(self, kind: str) -> list[dict]:
        rows = self._connection.execute(
            "SELECT outboxId, kind, idempotencyKey, payload, attempts FROM outbox WHERE kind = ? ORDER BY outboxId", (kind,)
        ).fetchall()
        return [
            {"outboxId": row[0], "kind": row[1], "idempotencyKey": row[2], "payload": json.loads(row[3]), "attempts": row[4]}
            for row in rows
        ]

    def removeOutbox(self, outboxId: int) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM outbox WHERE outboxId = ?", (outboxId,))

    def recordOutboxFailure(self, outboxId: int, error: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE outbox SET attempts = attempts + 1, lastError = ? WHERE outboxId = ?", (error, outboxId)
            )
