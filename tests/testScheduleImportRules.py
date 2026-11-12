"""Etapa 07 — business rules of the HR spreadsheet (RN01 to RN09), without files or network."""

from datetime import date

import pytest

from src.domain.scheduleImport import REQUIRED_COLUMNS, SheetData, validateWorkbook
from src.domain.stations import findStation
from tools.sampleSpreadsheets import MONDAY, WEEK, WINDOWS, defaultDemand, defaultEmployees, employeesWithInvalidRows


def sheets(employees=None, demand=None, windows=None, week=WEEK, headers=None) -> dict[str, SheetData]:
    def build(name, rows):
        columns = list((headers or {}).get(name, REQUIRED_COLUMNS[name]))
        return SheetData(columns, [(index, list(row)) for index, row in enumerate(rows, start=2)])

    return {
        "Semana": build("Semana", [["Empresa Fictícia S.A.", week]]),
        "Demanda": build("Demanda", defaultDemand() if demand is None else demand),
        "Funcionarios": build("Funcionarios", defaultEmployees() if employees is None else employees),
        "Janelas": build("Janelas", [[item] for item in (WINDOWS if windows is None else windows)]),
    }


def messages(result) -> list[str]:
    return [issue.message for issue in result.issues]


# ---------- Success ----------


def testValidSpreadsheetBuildsContractPayload():
    result = validateWorkbook(sheets())
    assert result.accepted
    payload = result.payload
    assert payload["week"] == WEEK and payload["entryWindows"] == WINDOWS
    assert len(payload["employees"]) == 20 and payload["rejectedRows"] == 0
    assert {team["teamName"] for team in payload["teams"]} == {"Financeiro", "Tecnologia"}
    assert payload["teams"][0]["demand"][0] == {"date": MONDAY.isoformat(), "minPeople": 2, "maxPeople": 6, "mandatory": False}
    employee = payload["employees"][0]
    assert set(employee) >= {"employeeId", "name", "email", "teamName", "boardingStation", "lineNumber", "monthlyOnSiteDays", "unavailableDates"}


def testHeadersAndSheetNamesIgnoreAccentsAndCase():
    data = sheets()
    data["Funcionários"] = data.pop("Funcionarios")
    data["Funcionários"].headers[0] = "MATRICULA"
    assert validateWorkbook(data).accepted


def testStationIsNormalizedToCanonicalName():
    assert findStation("corinthians - itaquera", 3) == "Corinthians-Itaquera"
    assert findStation("Paraiso", 1) == "Paraíso"
    assert findStation("Paraíso", 3) is None


# ---------- Decision ----------


def testTenPercentInvalidRowsAreRefusedButFileIsAccepted():
    result = validateWorkbook(sheets(employees=employeesWithInvalidRows(2)))
    assert result.accepted
    assert result.employeesValid == 18 and result.payload["rejectedRows"] == 2
    assert "E-mail inválido: email-sem-arroba.example" in messages(result)


def testExactlyTwentyPercentIsStillAccepted():
    assert validateWorkbook(sheets(employees=employeesWithInvalidRows(4))).accepted


def testThirtyPercentInvalidRejectsWholeFile():  # RN09
    result = validateWorkbook(sheets(employees=employeesWithInvalidRows(6)))
    assert not result.accepted and result.payload is None
    assert "30%" in result.rejectionReason


def testAnyInvalidDemandRowRejectsWholeFile():  # RN09
    demand = defaultDemand()
    demand[0][2] = 7  # Mínimo > Máximo
    result = validateWorkbook(sheets(demand=demand))
    assert not result.accepted
    assert any("Mínimo (7) maior que o Máximo (6)" in message for message in messages(result))


def testDuplicatedEmployeeIdKeepsFirstOccurrence():  # RN04
    employees = defaultEmployees()
    employees[5][0] = employees[0][0]
    result = validateWorkbook(sheets(employees=employees))
    assert result.accepted and result.employeesValid == 19
    assert [issue.rowNumber for issue in result.issues if issue.message == "Matrícula duplicada"] == [7]


def testStationMustBelongToInformedLine():  # RN05
    employees = defaultEmployees()
    employees[0][4] = "Jabaquara"  # Line 1 station on a line 3 employee
    assert "Estação Jabaquara não pertence à Linha 3 (pertence à Linha 1)" in messages(validateWorkbook(sheets(employees=employees)))


def testRestrictionWindowMustExistInWindowsSheet():  # RN06
    employees = defaultEmployees()
    employees[0][8] = "06:15"
    assert any("06:15 não está na aba Janelas" in message for message in messages(validateWorkbook(sheets(employees=employees))))


def testMaximumCannotExceedValidTeamSize():  # RN07
    demand = defaultDemand()
    demand[0][3] = 11
    result = validateWorkbook(sheets(demand=demand))
    assert not result.accepted
    assert any("Máximo (11) maior que o total de funcionários válidos do time Financeiro (10)" in message for message in messages(result))


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 11, 28), "não é dia útil"),  # Saturday of the same week
        (date(2026, 12, 1), "fora da semana informada"),
    ],
)
def testDemandDateMustBeWeekdayInsideWeek(day, expected):  # RN08
    demand = defaultDemand()
    demand[0][1] = day
    assert any(expected in message for message in messages(validateWorkbook(sheets(demand=demand))))


def testDatesTypedAsTextAreAccepted():
    demand = defaultDemand()
    for row in demand:
        row[1] = row[1].strftime("%d/%m/%Y")
    assert validateWorkbook(sheets(demand=demand)).accepted


# ---------- Failure ----------


def testMissingSheetRejectsWithStructureIssue():  # RN01 / EX03
    data = sheets()
    del data["Janelas"]
    result = validateWorkbook(data)
    assert not result.accepted
    assert messages(result) == ["Aba Janelas não encontrada"]


def testMissingColumnIsListed():  # RN01 / EX03
    headers = {"Funcionarios": [column for column in REQUIRED_COLUMNS["Funcionarios"] if column != "E-mail"]}
    result = validateWorkbook(sheets(headers=headers))
    assert "Coluna E-mail não encontrada na aba Funcionarios" in messages(result)


def testInvalidWeekIsRejected():
    result = validateWorkbook(sheets(week="semana 48"))
    assert not result.accepted
    assert any("Semana inválida" in message for message in messages(result))


def testAllMessagesForHrStartWithCapitalLetter():
    result = validateWorkbook(sheets(employees=employeesWithInvalidRows(6)))
    assert result.issues and all(message[0].isupper() for message in messages(result) + [result.rejectionReason])
