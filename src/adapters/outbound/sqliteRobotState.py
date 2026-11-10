"""Robot state persisted in SQLite (single local file, no server)."""

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
