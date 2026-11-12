"""Builds the fictitious HR spreadsheets used by tests, by the demo and as the HR template.

Run:  python -m tools.sampleSpreadsheets            (writes into data/fixtures/)
All people and the company are fictitious; e-mails use the reserved .example domain.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from src.domain.scheduleImport import REQUIRED_COLUMNS, SHEET_DEMAND, SHEET_EMPLOYEES, SHEET_WEEK, SHEET_WINDOWS

COMPANY = "Empresa Fictícia S.A."
WEEK = "2026-W48"
MONDAY = date.fromisocalendar(2026, 48, 1)
WINDOWS = ["07:00", "08:00", "09:30", "10:30"]

_PEOPLE = [
    ("Ana Ribeiro", 3, "Corinthians-Itaquera"), ("Bruno Matos", 1, "Tucuruvi"), ("Carla Nunes", 3, "Tatuapé"),
    ("Diego Prado", 1, "Santana"), ("Elisa Campos", 3, "Penha"), ("Fábio Lima", 1, "Jabaquara"),
    ("Gabriela Souza", 3, "Brás"), ("Heitor Alves", 1, "Vila Mariana"), ("Iara Costa", 3, "Artur Alvim"),
    ("Jonas Teixeira", 1, "Paraíso"),
]
_TEAMS = ["Financeiro", "Tecnologia"]


def _ascii(text: str) -> str:
    return text.lower().translate(str.maketrans("áéíóúâêôãõç", "aeiouaeoaoc")).replace(" ", ".")


def defaultEmployees() -> list[list]:
    rows = []
    for teamIndex, team in enumerate(_TEAMS):
        for index, (name, line, station) in enumerate(_PEOPLE):
            employeeId = f"F{teamIndex + 1}{index + 1:03d}"
            unavailable = (MONDAY + timedelta(days=index % 5)).strftime("%d/%m/%Y") if index % 4 == 0 else None
            restriction = "08:00" if index == 2 else None
            rows.append([employeeId, name, f"{_ascii(name)}.{team.lower()}@empresaficticia.example", team, station, line, 8 + index % 5, unavailable, restriction])
    return rows


def defaultDemand() -> list[list]:
    rows = []
    for team in _TEAMS:
        for offset in range(5):
            mandatory = offset == 1  # Tuesday is the team meeting day
            rows.append([team, MONDAY + timedelta(days=offset), 4 if mandatory else 2, 6, "Sim" if mandatory else "Não"])
    return rows


def buildWorkbook(path: Path, employees: list[list] | None = None, demand: list[list] | None = None,
                  windows: list[str] | None = None, week: str = WEEK, dropSheets: tuple[str, ...] = ()) -> Path:
    workbook = Workbook()
    workbook.remove(workbook.active)
    content = {
        SHEET_WEEK: [[COMPANY, week]],
        SHEET_DEMAND: defaultDemand() if demand is None else demand,
        SHEET_EMPLOYEES: defaultEmployees() if employees is None else employees,
        SHEET_WINDOWS: [[window] for window in (WINDOWS if windows is None else windows)],
    }
    for sheet, rows in content.items():
        if sheet in dropSheets:
            continue
        worksheet = workbook.create_sheet(sheet)
        worksheet.append(list(REQUIRED_COLUMNS[sheet]))
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E79")
        for row in rows:
            worksheet.append(row)
        for column in "ABCDEFGHI":
            worksheet.column_dimensions[column].width = 22
        for cell in worksheet["B"] if sheet == SHEET_DEMAND else []:
            cell.number_format = "DD/MM/YYYY"
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def employeesWithInvalidRows(count: int) -> list[list]:
    """Breaks `count` employee rows, each with a different kind of error (RN03 to RN06)."""
    rows = defaultEmployees()
    breakers = [
        lambda row: row.__setitem__(2, "email-sem-arroba.example"),          # RN03 e-mail
        lambda row: row.__setitem__(4, "Tucuruvi") or row.__setitem__(5, 3),  # RN05 station of another line
        lambda row: row.__setitem__(0, rows[0][0]),                          # RN04 duplicated id
        lambda row: row.__setitem__(8, "11:00"),                             # RN06 window not in Janelas
        lambda row: row.__setitem__(6, "muitos"),                            # RN03 integer
        lambda row: row.__setitem__(5, 4),                                   # Line outside the MVP
    ]
    # Spread the broken rows across both teams so RN07 (max <= valid team size) still holds
    targets = [index for pair in zip(range(9, 4, -1), range(19, 14, -1)) for index in pair]
    for position, index in enumerate(targets[:count]):
        breakers[position % len(breakers)](rows[index])
    return rows


def demoEmployees() -> list[list]:
    """3 people of one team: small enough for the Mailtrap free quota in the demo video."""
    return [row for row in defaultEmployees() if row[3] == "Financeiro"][:3]


def demoDemand() -> list[list]:
    return [["Financeiro", MONDAY + timedelta(days=offset), 1, 3, "Sim" if offset == 1 else "Não"] for offset in range(5)]


def buildAllSamples(folder: Path) -> list[Path]:
    built = [
        buildWorkbook(folder / "scheduleValid.xlsx"),
        buildWorkbook(folder / "scheduleDemoSmall.xlsx", employees=demoEmployees(), demand=demoDemand()),
        buildWorkbook(folder / "scheduleTenPercentInvalid.xlsx", employees=employeesWithInvalidRows(2)),
        buildWorkbook(folder / "scheduleThirtyPercentInvalid.xlsx", employees=employeesWithInvalidRows(6)),
        buildWorkbook(folder / "scheduleMissingSheet.xlsx", dropSheets=(SHEET_WINDOWS,)),
        buildWorkbook(folder / "scheduleTemplate.xlsx", employees=[], demand=[], week=WEEK),
    ]
    corrupted = folder / "scheduleCorrupted.xlsx"
    corrupted.write_bytes(b"Este arquivo nao e uma planilha valida")
    built.append(corrupted)
    return built


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/fixtures")
    for item in buildAllSamples(target):
        print(f"Planilha gerada: {item}")
