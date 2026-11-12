"""Reads the HR .xlsx with openpyxl (values only, formulas already computed by Excel)."""

import zipfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from src.domain.exceptions import InvalidSpreadsheetError
from src.domain.scheduleImport import SheetData

MAX_ROWS_PER_SHEET = 5000  # Protects the robot from a huge or malformed file


class OpenpyxlSpreadsheetReader:
    def read(self, path: Path) -> dict[str, SheetData]:
        if path.suffix.lower() != ".xlsx":
            raise InvalidSpreadsheetError(f"Unsupported extension {path.suffix!r}")
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
            raise InvalidSpreadsheetError(f"Workbook could not be opened: {type(error).__name__}") from error
        try:
            sheets: dict[str, SheetData] = {}
            for worksheet in workbook.worksheets:
                rows = worksheet.iter_rows(values_only=True, max_row=MAX_ROWS_PER_SHEET)
                headers = list(next(rows, ()) or ())
                data = [(index, list(cells)) for index, cells in enumerate(rows, start=2)]
                sheets[worksheet.title] = SheetData(headers=headers, rows=data)
            return sheets
        finally:
            workbook.close()
