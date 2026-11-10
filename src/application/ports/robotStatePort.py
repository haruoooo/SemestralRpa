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
