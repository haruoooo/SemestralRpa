"""Reads the HR .xlsx with the BotCity Excel plugin (botcity-excel-plugin, the plugin repository shown in class).

The plugin loads every sheet with pandas. Pandas turns empty cells into NaN/NaT and whole numbers into floats
when a column has blanks, so the adapter normalizes the cells back to what the business rules expect:
empty -> None, 3.0 -> 3, Timestamp -> datetime.
"""

import math
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from botcity.plugins.excel import BotExcelPlugin

from src.domain.exceptions import InvalidSpreadsheetError
from src.domain.scheduleImport import SheetData

MAX_ROWS_PER_SHEET = 5000  # Protects the robot from a huge or malformed file


def normalizeCell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return int(value) if value.is_integer() else value
    if hasattr(value, "to_pydatetime"):  # pandas Timestamp / NaT
        return None if str(value) == "NaT" else value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):  # numpy scalars
        return normalizeCell(value.item())
    return value


class BotcityExcelReader:
    def read(self, path: Path) -> dict[str, SheetData]:
        if path.suffix.lower() != ".xlsx":
            raise InvalidSpreadsheetError(f"Unsupported extension {path.suffix!r}")
        plugin = BotExcelPlugin()
        try:
            plugin.read(str(path))
        except (zipfile.BadZipFile, KeyError, OSError, ValueError, IndexError) as error:
            raise InvalidSpreadsheetError(f"Workbook could not be opened: {type(error).__name__}") from error
        sheets: dict[str, SheetData] = {}
        for name in plugin.list_sheets():
            rows = [[normalizeCell(cell) for cell in row] for row in plugin.as_list(sheet=name)[: MAX_ROWS_PER_SHEET + 1]]
            headers = rows[0] if rows else []
            data = [(index, cells) for index, cells in enumerate(rows[1:], start=2)]
            sheets[str(name)] = SheetData(headers=headers, rows=data)
        return sheets

