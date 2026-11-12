from typing import Protocol

from src.domain.assignment import Assignment


class CalendarPort(Protocol):
    """Builds the .ics attached to the e-mails. Event UID = assignmentId, so a plan B updates the same event."""

    def buildAgenda(self, assignments: list[Assignment], sequence: int) -> bytes: ...

    def buildRemoteWork(self, assignment: Assignment, sequence: int) -> bytes:
        """Cancels the on-site event of that day (METHOD:CANCEL)."""
        ...

    def buildShiftedEntry(self, assignment: Assignment, newEntryWindow: str, sequence: int) -> bytes: ...
