from typing import Protocol

from src.domain.scheduleImport import RowIssue


class ImportReportPort(Protocol):
    """Report for HR (Portuguese) with the outcome of one spreadsheet."""

    def write(self, fileName: str, fileHash: str, outcome: str, summary: dict[str, object], issues: list[RowIssue]) -> str:
        """Returns the report location."""
        ...
