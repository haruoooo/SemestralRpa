from datetime import datetime
from typing import Protocol

from src.domain.lineStatus import LineReading, LineStatusCode


class RobotStatePort(Protocol):
    """Robot's own persistent memory between runs."""

    def getLastLineStatus(self, lineNumber: int) -> LineStatusCode | None: ...

    def saveLineStatus(self, reading: LineReading, savedAt: datetime) -> None:
        """Committed only after the API accepted everything related to this line (natural retry on failure)."""
        ...

    def getLastReadings(self) -> list[LineReading]: ...

    def getLastSourceSuccessAt(self) -> datetime | None: ...

    def saveSourceSuccessAt(self, moment: datetime) -> None: ...

    # ---------- scheduleImportFlow ----------

    def isFileProcessed(self, fileHash: str) -> bool:
        """RN02: the same spreadsheet (same SHA-256) is imported only once."""
        ...

    def markFileProcessed(self, fileHash: str, fileName: str, outcome: str, processedAt: datetime) -> None: ...

    def enqueueOutbox(self, kind: str, idempotencyKey: str, payload: dict, error: str, createdAt: datetime) -> None:
        """EX06: keeps a send that failed after the retries, to be replayed on the next run."""
        ...

    def listOutbox(self, kind: str) -> list[dict]:
        """Pending items, oldest first: {outboxId, kind, idempotencyKey, payload, attempts}."""
        ...

    def removeOutbox(self, outboxId: int) -> None: ...

    def recordOutboxFailure(self, outboxId: int, error: str) -> None: ...
