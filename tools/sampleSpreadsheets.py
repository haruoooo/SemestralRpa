"""Builds the fictitious HR spreadsheets used by tests, by the demo and as the HR template.

Run:  python -m tools.sampleSpreadsheets            (writes into data/fixtures/)
All people and the company are fictitious; e-mails use the reserved .example domain.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from src.domain.scheduleImport import (
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    SHEET_CURRENT,
    SHEET_DEMAND,
    SHEET_EMPLOYEES,
    SHEET_WEEK,
    SHEET_WINDOWS,
)

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


def defaultEmployees(monday: date = MONDAY) -> list[list]:
    rows = []
    for teamIndex, team in enumerate(_TEAMS):
        for index, (name, line, station) in enumerate(_PEOPLE):
            employeeId = f"F{teamIndex + 1}{index + 1:03d}"
            unavailable = (monday + timedelta(days=index % 5)).strftime("%d/%m/%Y") if index % 4 == 0 else None
            restriction = "08:00" if index == 2 else None
            rows.append([employeeId, name, f"{_ascii(name)}.{team.lower()}@empresaficticia.example", team, station, line, 8 + index % 5, unavailable, restriction])
    return rows


def defaultDemand(monday: date = MONDAY) -> list[list]:
    rows = []
    for team in _TEAMS:
        for offset in range(5):
            mandatory = offset == 1  # Tuesday is the team meeting day
            rows.append([team, monday + timedelta(days=offset), 4 if mandatory else 2, 6, "Sim" if mandatory else "Não"])
    return rows


def currentScheduleFor(employees: list[list], monday: date = MONDAY) -> list[list]:
    """Schedule practiced today, before ForaDoPico: everybody on Tuesday to Thursday, at the peak (RN19 sheet)."""
    rows = []
    for index, row in enumerate(employees):
        window = "07:00" if index % 3 == 0 else "08:00"
        rows.extend([row[0], monday + timedelta(days=offset), window] for offset in (1, 2, 3))
    return rows


def buildWorkbook(path: Path, employees: list[list] | None = None, demand: list[list] | None = None,
                  windows: list[str] | None = None, week: str = WEEK, dropSheets: tuple[str, ...] = (),
                  currentSchedule: list[list] | None = None) -> Path:
    monday = date.fromisocalendar(int(week[:4]), int(week[6:]), 1) if week[6:].isdigit() and week[6:] != "00" else MONDAY
    employees = defaultEmployees(monday) if employees is None else employees
    workbook = Workbook()
    workbook.remove(workbook.active)
    content = {
        SHEET_WEEK: [[COMPANY, week]],
        SHEET_DEMAND: defaultDemand(monday) if demand is None else demand,
        SHEET_EMPLOYEES: employees,
        SHEET_WINDOWS: [[window] for window in (WINDOWS if windows is None else windows)],
        SHEET_CURRENT: currentScheduleFor(employees, monday) if currentSchedule is None else currentSchedule,
    }
    for sheet, rows in content.items():
        if sheet in dropSheets:
            continue
        worksheet = workbook.create_sheet(sheet)
        worksheet.append(list({**REQUIRED_COLUMNS, **OPTIONAL_COLUMNS}[sheet]))
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E79")
        for row in rows:
            worksheet.append(row)
        for column in "ABCDEFGHI":
            worksheet.column_dimensions[column].width = 22
        for cell in worksheet["B"] if sheet in (SHEET_DEMAND, SHEET_CURRENT) else []:
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


def demoDemand(monday: date = MONDAY) -> list[list]:
    return [["Financeiro", monday + timedelta(days=offset), 1, 3, "Sim" if offset == 1 else "Não"] for offset in range(5)]


def buildAllSamples(folder: Path) -> list[Path]:
    built = [
        buildWorkbook(folder / "scheduleValid.xlsx"),
        buildWorkbook(folder / "scheduleDemoSmall.xlsx", employees=demoEmployees(), demand=demoDemand()),
        buildWorkbook(folder / "scheduleTenPercentInvalid.xlsx", employees=employeesWithInvalidRows(2)),
        buildWorkbook(folder / "scheduleThirtyPercentInvalid.xlsx", employees=employeesWithInvalidRows(6)),
        buildWorkbook(folder / "scheduleMissingSheet.xlsx", dropSheets=(SHEET_WINDOWS,)),
        buildWorkbook(folder / "scheduleTemplate.xlsx", employees=[], demand=[], week=WEEK, currentSchedule=[]),
        # Two consecutive weeks for the Big Data incremental load; W47 has one person less (hired for W48)
        buildWorkbook(folder / "scheduleW47.xlsx", employees=[row for row in defaultEmployees(date.fromisocalendar(2026, 47, 1)) if row[0] != "F2010"], week="2026-W47"),
        buildWorkbook(folder / "scheduleW48.xlsx", week="2026-W48"),
    ]
    corrupted = folder / "scheduleCorrupted.xlsx"
    corrupted.write_bytes(b"Este arquivo nao e uma planilha valida")
    built.append(corrupted)
    return built


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/fixtures")
    for item in buildAllSamples(target):
        print(f"Planilha gerada: {item}")

