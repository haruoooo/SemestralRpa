from pathlib import Path
from typing import Protocol

from src.domain.scheduleImport import SheetData


class SpreadsheetReaderPort(Protocol):
    def read(self, path: Path) -> dict[str, SheetData]:
        """Raw cells of every sheet. Raises InvalidSpreadsheetError when the file cannot be opened (EX02)."""
        ...
