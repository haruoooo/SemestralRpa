from typing import Protocol

from src.domain.lineStatus import LineReading


class LineStatusSourcePort(Protocol):
    """Where the line status comes from (live website or simulated scenario)."""

    sourceName: str

    def fetchReadings(self) -> list[LineReading]:
        """Returns one reading per line.

        Raises SourceUnavailableError when the source cannot be reached and
        SourceLayoutChangedError when the content cannot be interpreted.
        """
        ...
