"""Business rules of the HR schedule spreadsheet (docs/processDesign.md, section 3, RN01-RN09).

Pure functions: they receive the raw cells already read from the file and return the payload for
the product API plus every issue found. Messages for HR are in Portuguese.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from src.domain.lineStatus import normalizeText
from src.domain.stations import SUPPORTED_LINES, findStation, linesOfStation

REJECTION_THRESHOLD = 0.20  # RN09
MAX_MONTHLY_ON_SITE_DAYS = 23

SHEET_WEEK = "Semana"
SHEET_DEMAND = "Demanda"
SHEET_EMPLOYEES = "Funcionarios"
SHEET_WINDOWS = "Janelas"

# Sheet -> ordered columns (display name used in the template and in HR messages)
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    SHEET_WEEK: ("Empresa", "Semana"),
    SHEET_DEMAND: ("Time", "Data", "Mínimo", "Máximo", "Obrigatório"),
    SHEET_EMPLOYEES: (
        "Matrícula", "Nome", "E-mail", "Time", "Estação de embarque", "Linha",
        "Dias presenciais no mês", "Dias indisponíveis", "Restrição de horário",
    ),
    SHEET_WINDOWS: ("Horário de entrada permitido",),
}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WEEK = re.compile(r"^(\d{4})-W(\d{2})$")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")
_WEEKDAYS_PT = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@dataclass(frozen=True)
class SheetData:
    """Raw content of one sheet: header cells and data rows with their spreadsheet row number."""

    headers: list[Any]
    rows: list[tuple[int, list[Any]]]


@dataclass(frozen=True)
class RowIssue:
    sheet: str
    rowNumber: int | None
    column: str | None
    message: str  # Portuguese, shown to HR


@dataclass
class ValidationResult:
    accepted: bool = False
    rejectionReason: str | None = None  # Portuguese, shown to HR
    payload: dict | None = None
    issues: list[RowIssue] = field(default_factory=list)
    employeesTotal: int = 0
    employeesValid: int = 0
    demandTotal: int = 0
    demandValid: int = 0

    @property
    def rejectedRows(self) -> int:
        return (self.employeesTotal - self.employeesValid) + (self.demandTotal - self.demandValid)


class _RowValidationError(Exception):
    pass


# ---------- Cell parsers (raise _RowValidationError with a Portuguese message) ----------


def _isEmpty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value: Any, column: str) -> str:
    if _isEmpty(value):
        raise _RowValidationError(f"{column} é obrigatório")
    return str(value).strip()


def _integer(value: Any, column: str, minimum: int = 0, maximum: int | None = None) -> int:
    if _isEmpty(value):
        raise _RowValidationError(f"{column} é obrigatório")
    if isinstance(value, bool):
        raise _RowValidationError(f"{column} precisa ser um número inteiro")
    try:
        number = float(str(value).strip().replace(",", ".")) if not isinstance(value, (int, float)) else float(value)
    except ValueError:
        raise _RowValidationError(f"{column} precisa ser um número inteiro (recebido: {value})") from None
    if not number.is_integer():
        raise _RowValidationError(f"{column} precisa ser um número inteiro (recebido: {value})")
    result = int(number)
    if result < minimum or (maximum is not None and result > maximum):
        limit = f"entre {minimum} e {maximum}" if maximum is not None else f"maior ou igual a {minimum}"
        raise _RowValidationError(f"{column} precisa ser {limit} (recebido: {result})")
    return result


def parseDate(value: Any, column: str = "Data") -> date:
    if _isEmpty(value):
        raise _RowValidationError(f"{column} é obrigatória")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise _RowValidationError(f"{column} inválida (use dd/mm/aaaa): {text}")


def parseTime(value: Any, column: str) -> str:
    if _isEmpty(value):
        raise _RowValidationError(f"{column} é obrigatório")
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    match = _TIME.match(str(value).strip())
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise _RowValidationError(f"{column} inválido (use HH:MM): {value}")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _yesNo(value: Any, column: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = normalizeText(str(value or ""))
    if normalized in ("sim", "s", "true"):
        return True
    if normalized in ("nao", "n", "false"):
        return False
    raise _RowValidationError(f"{column} precisa ser Sim ou Não (recebido: {value})")


def parseWeek(value: Any) -> tuple[str, date]:
    """ISO week like 2026-W48 -> (week, monday)."""
    text = str(value or "").strip().upper()
    match = _WEEK.match(text)
    if not match:
        raise _RowValidationError(f"Semana inválida (use o formato 2026-W48): {value}")
    try:
        monday = date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    except ValueError:
        raise _RowValidationError(f"Semana inexistente: {value}") from None
    return text, monday


# ---------- Structure (RN01) ----------


def _headerKey(name: Any) -> str:
    return " ".join(normalizeText(str(name or "")).split())


def checkStructure(sheets: dict[str, SheetData]) -> tuple[dict[str, SheetData], dict[str, dict[str, int]], list[RowIssue]]:
    """Finds the 4 sheets and the column positions, ignoring accents and case (RN01, EX03)."""
    byKey = {_headerKey(name): data for name, data in sheets.items()}
    found: dict[str, SheetData] = {}
    positions: dict[str, dict[str, int]] = {}
    issues: list[RowIssue] = []
    for sheet, columns in REQUIRED_COLUMNS.items():
        data = byKey.get(_headerKey(sheet))
        if data is None:
            issues.append(RowIssue(sheet, None, None, f"Aba {sheet} não encontrada"))
            continue
        headerIndex = {_headerKey(header): index for index, header in enumerate(data.headers) if not _isEmpty(header)}
        missing = [column for column in columns if _headerKey(column) not in headerIndex]
        for column in missing:
            issues.append(RowIssue(sheet, 1, column, f"Coluna {column} não encontrada na aba {sheet}"))
        found[sheet] = data
        positions[sheet] = {column: headerIndex.get(_headerKey(column), -1) for column in columns}
    return found, positions, issues


def _rowValues(row: list[Any], columnPositions: dict[str, int]) -> dict[str, Any]:
    return {column: (row[index] if 0 <= index < len(row) else None) for column, index in columnPositions.items()}


def _dataRows(data: SheetData) -> list[tuple[int, list[Any]]]:
    return [(number, cells) for number, cells in data.rows if not all(_isEmpty(cell) for cell in cells)]


# ---------- Full validation ----------


def validateWorkbook(sheets: dict[str, SheetData]) -> ValidationResult:
    result = ValidationResult()
    found, positions, structureIssues = checkStructure(sheets)
    if structureIssues:
        result.issues = structureIssues
        result.rejectionReason = "Estrutura da planilha inválida: faltam abas ou colunas obrigatórias (RN01)"
        return result

    week = _validateWeekSheet(found[SHEET_WEEK], positions[SHEET_WEEK], result)
    windows = _validateWindowsSheet(found[SHEET_WINDOWS], positions[SHEET_WINDOWS], result)
    if week is None or windows is None:
        result.rejectionReason = result.rejectionReason or "Abas Semana ou Janelas inválidas"
        return result
    companyName, weekCode, monday = week

    employees = _validateEmployees(found[SHEET_EMPLOYEES], positions[SHEET_EMPLOYEES], windows, result)
    teamSizes = Counter(employee["teamName"] for employee in employees)
    teams = _validateDemand(found[SHEET_DEMAND], positions[SHEET_DEMAND], monday, teamSizes, result)

    # RN09: rejection threshold
    if result.employeesTotal == 0:
        result.rejectionReason = "A aba Funcionarios não tem nenhuma linha preenchida"
        return result
    if result.demandTotal == 0:
        result.rejectionReason = "A aba Demanda não tem nenhuma linha preenchida"
        return result
    invalidShare = (result.employeesTotal - result.employeesValid) / result.employeesTotal
    if invalidShare > REJECTION_THRESHOLD:
        result.rejectionReason = (
            f"A aba Funcionarios tem {invalidShare:.0%} de linhas inválidas, acima do limite de {REJECTION_THRESHOLD:.0%}. "
            "Corrija a planilha e envie de novo (RN09)"
        )
        return result
    if result.demandValid < result.demandTotal:
        result.rejectionReason = "Há linhas inválidas na aba Demanda; a escala não pode ser montada com demanda incompleta (RN09)"
        return result

    result.accepted = True
    result.payload = {
        "companyName": companyName,
        "week": weekCode,
        "entryWindows": windows,
        "teams": teams,
        "employees": employees,
        "rejectedRows": result.rejectedRows,
    }
    return result


def _validateWeekSheet(data: SheetData, columns: dict[str, int], result: ValidationResult) -> tuple[str, str, date] | None:
    rows = _dataRows(data)
    if not rows:
        result.issues.append(RowIssue(SHEET_WEEK, 2, None, "Aba Semana sem empresa e semana preenchidas"))
        return None
    rowNumber, cells = rows[0]
    values = _rowValues(cells, columns)
    try:
        companyName = _text(values["Empresa"], "Empresa")
        weekCode, monday = parseWeek(values["Semana"])
    except _RowValidationError as error:
        result.issues.append(RowIssue(SHEET_WEEK, rowNumber, None, str(error)))
        return None
    return companyName, weekCode, monday


def _validateWindowsSheet(data: SheetData, columns: dict[str, int], result: ValidationResult) -> list[str] | None:
    column = REQUIRED_COLUMNS[SHEET_WINDOWS][0]
    windows: list[str] = []
    valid = True
    for rowNumber, cells in _dataRows(data):
        try:
            window = parseTime(_rowValues(cells, columns)[column], "Horário de entrada")
        except _RowValidationError as error:
            result.issues.append(RowIssue(SHEET_WINDOWS, rowNumber, column, str(error)))
            valid = False
            continue
        if window not in windows:
            windows.append(window)
    if not windows:
        result.issues.append(RowIssue(SHEET_WINDOWS, 2, column, "Informe ao menos um horário de entrada permitido"))
        return None
    return sorted(windows) if valid else None


def _validateEmployees(data: SheetData, columns: dict[str, int], windows: list[str], result: ValidationResult) -> list[dict]:
    employees: list[dict] = []
    seenIds: set[str] = set()
    for rowNumber, cells in _dataRows(data):
        result.employeesTotal += 1
        values = _rowValues(cells, columns)
        rowIssues: list[RowIssue] = []

        def check(column: str, parser):
            try:
                return parser()
            except _RowValidationError as error:
                rowIssues.append(RowIssue(SHEET_EMPLOYEES, rowNumber, column, str(error)))
                return None

        employeeId = check("Matrícula", lambda: _text(values["Matrícula"], "Matrícula"))
        if employeeId is not None:
            if employeeId in seenIds:  # RN04: first occurrence wins
                rowIssues.append(RowIssue(SHEET_EMPLOYEES, rowNumber, "Matrícula", "Matrícula duplicada"))
            seenIds.add(employeeId)
        name = check("Nome", lambda: _text(values["Nome"], "Nome"))
        email = check("E-mail", lambda: _email(values["E-mail"]))
        teamName = check("Time", lambda: _text(values["Time"], "Time"))
        lineNumber = check("Linha", lambda: _line(values["Linha"]))
        station = check("Estação de embarque", lambda: _station(values["Estação de embarque"], lineNumber)) if lineNumber else None
        monthlyDays = check(
            "Dias presenciais no mês",
            lambda: _integer(values["Dias presenciais no mês"], "Dias presenciais no mês", 0, MAX_MONTHLY_ON_SITE_DAYS),
        )
        unavailable = check("Dias indisponíveis", lambda: _dateList(values["Dias indisponíveis"]))
        latestWindow = check("Restrição de horário", lambda: _optionalWindow(values["Restrição de horário"], windows))

        if rowIssues:
            result.issues.extend(rowIssues)
            continue
        employee = {
            "employeeId": employeeId,
            "name": name,
            "email": email,
            "teamName": teamName,
            "boardingStation": station,
            "lineNumber": lineNumber,
            "monthlyOnSiteDays": monthlyDays,
            "unavailableDates": unavailable,
        }
        if latestWindow:
            employee["latestEntryWindow"] = latestWindow
        employees.append(employee)
    result.employeesValid = len(employees)
    return employees


def _validateDemand(data: SheetData, columns: dict[str, int], monday: date, teamSizes: Counter, result: ValidationResult) -> list[dict]:
    teams: dict[str, list[dict]] = {}
    seen: set[tuple[str, date]] = set()
    for rowNumber, cells in _dataRows(data):
        result.demandTotal += 1
        values = _rowValues(cells, columns)
        rowIssues: list[RowIssue] = []

        def check(column: str, parser):
            try:
                return parser()
            except _RowValidationError as error:
                rowIssues.append(RowIssue(SHEET_DEMAND, rowNumber, column, str(error)))
                return None

        teamName = check("Time", lambda: _text(values["Time"], "Time"))
        day = check("Data", lambda: _weekday(values["Data"], monday))
        minimum = check("Mínimo", lambda: _integer(values["Mínimo"], "Mínimo"))
        maximum = check("Máximo", lambda: _integer(values["Máximo"], "Máximo"))
        mandatory = check("Obrigatório", lambda: _yesNo(values["Obrigatório"], "Obrigatório"))

        if minimum is not None and maximum is not None and minimum > maximum:  # RN07
            rowIssues.append(RowIssue(SHEET_DEMAND, rowNumber, "Mínimo", f"Mínimo ({minimum}) maior que o Máximo ({maximum})"))
        if teamName is not None and maximum is not None and maximum > teamSizes.get(teamName, 0):  # RN07
            rowIssues.append(
                RowIssue(
                    SHEET_DEMAND, rowNumber, "Máximo",
                    f"Máximo ({maximum}) maior que o total de funcionários válidos do time {teamName} ({teamSizes.get(teamName, 0)})",
                )
            )
        if teamName is not None and day is not None:
            if (teamName, day) in seen:
                rowIssues.append(RowIssue(SHEET_DEMAND, rowNumber, "Data", f"Demanda repetida para o time {teamName} em {day:%d/%m/%Y}"))
            seen.add((teamName, day))

        if rowIssues:
            result.issues.extend(rowIssues)
            continue
        result.demandValid += 1
        teams.setdefault(teamName, []).append(
            {"date": day.isoformat(), "minPeople": minimum, "maxPeople": maximum, "mandatory": mandatory}
        )
    return [{"teamName": name, "demand": sorted(demand, key=lambda item: item["date"])} for name, demand in teams.items()]


# ---------- Field rules ----------


def _email(value: Any) -> str:
    text = _text(value, "E-mail").lower()
    if not _EMAIL.match(text):
        raise _RowValidationError(f"E-mail inválido: {text}")
    return text


def _line(value: Any) -> int:
    line = _integer(value, "Linha", 1)
    if line not in SUPPORTED_LINES:
        supported = " e ".join(str(item) for item in SUPPORTED_LINES)
        raise _RowValidationError(f"Linha {line} fora do MVP (somente Linhas {supported})")
    return line


def _station(value: Any, lineNumber: int) -> str:  # RN05
    name = _text(value, "Estação de embarque")
    canonical = findStation(name, lineNumber)
    if canonical:
        return canonical
    otherLines = linesOfStation(name)
    if otherLines:
        raise _RowValidationError(f"Estação {name} não pertence à Linha {lineNumber} (pertence à Linha {otherLines[0]})")
    raise _RowValidationError(f"Estação {name} não encontrada na lista de referência")


def _dateList(value: Any) -> list[str]:
    if _isEmpty(value):
        return []
    if isinstance(value, (date, datetime)):
        return [parseDate(value, "Dias indisponíveis").isoformat()]
    parts = [part for part in re.split(r"[;,\s]+", str(value).strip()) if part]
    return sorted({parseDate(part, "Dias indisponíveis").isoformat() for part in parts})


def _optionalWindow(value: Any, windows: list[str]) -> str | None:  # RN06
    if _isEmpty(value):
        return None
    window = parseTime(value, "Restrição de horário")
    if window not in windows:
        raise _RowValidationError(f"Horário {window} não está na aba Janelas ({', '.join(windows)})")
    return window


def _weekday(value: Any, monday: date) -> date:  # RN08
    day = parseDate(value, "Data")
    friday = date.fromordinal(monday.toordinal() + 4)
    sunday = date.fromordinal(monday.toordinal() + 6)
    if not monday <= day <= sunday:
        raise _RowValidationError(f"Data {day:%d/%m/%Y} fora da semana informada ({monday:%d/%m} a {friday:%d/%m/%Y})")
    if day.weekday() > 4:
        raise _RowValidationError(f"Data {day:%d/%m/%Y} cai num {_WEEKDAYS_PT[day.weekday()]}, não é dia útil")
    return day
