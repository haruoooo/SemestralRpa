"""Etapa 07 — success, decision and failure scenarios of lineMonitorFlow, using fake adapters (no network)."""

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.adapters.outbound.sqliteRobotState import SqliteRobotState
from src.application.flows.lineMonitorFlow import LineMonitorFlow
from src.application.runSummary import RunStatus
from src.domain.assignment import Assignment
from src.domain.exceptions import ApiUnavailableError, SourceLayoutChangedError, SourceUnavailableError
from src.domain.lineStatus import LineReading, classifyStatus
from src.infrastructure.robotLogger import RunLogger
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import SAO_PAULO

TUESDAY_0730 = datetime(2026, 11, 10, 7, 30, tzinfo=SAO_PAULO)
WINDOWS = ["07:00", "08:00", "09:30", "10:30"]


def reading(lineNumber: int, rawText: str) -> LineReading:
    return LineReading(lineNumber, {1: "Azul", 3: "Vermelha"}.get(lineNumber, "X"), rawText, classifyStatus(rawText))


class FakeSource:
    sourceName = "fake"

    def __init__(self, readings=None, error: Exception | None = None):
        self.readings = readings or []
        self.error = error

    def fetchReadings(self):
        if self.error:
            raise self.error
        return self.readings


class FakeApi:
    def __init__(self, assignments: list[Assignment] | None = None):
        self.assignments = assignments or []
        self.alerts, self.plans, self.snapshots = [], [], []
        self.failAlerts = False

    def publishLineStatus(self, snapshot):
        self.snapshots.append(snapshot)

    def createAlert(self, alert):
        if self.failAlerts:
            raise ApiUnavailableError("Connection refused")
        self.alerts.append(alert)
        return {**alert, "alertId": f"alert-{len(self.alerts)}"}

    def listAssignments(self, date, lineNumber=None):
        return [item for item in self.assignments if item.date == date and item.lineNumber == lineNumber]

    def createContingencyPlan(self, plan):
        self.plans.append(plan)
        return {**plan, "planId": f"plan-{len(self.plans)}", "status": "pendingApproval"}


def assignment(employeeId: str, team: str, line: int, window: str) -> Assignment:
    return Assignment(f"as-{employeeId}", employeeId, team, line, "2026-11-10", window, WINDOWS)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return replace(Settings(), retryBaseSeconds=0, logDir=tmp_path, logSalt="test")


@pytest.fixture
def state() -> SqliteRobotState:
    return SqliteRobotState(Path(":memory:"))


def runFlow(source, api, state, settings, now=TUESDAY_0730, respectWindow=True):
    logger = RunLogger("lineMonitorFlow", "test-run")
    return LineMonitorFlow(source, api, state, settings, logger, clock=lambda: now, respectOperatingWindow=respectWindow).run()


# ---------- Success ----------


def testFirstRunWithNormalLinesRecordsStateWithoutAlerts(settings, state):
    api = FakeApi()
    summary = runFlow(FakeSource([reading(1, "Operação Normal"), reading(3, "Operação Normal")]), api, state, settings)
    assert summary.status == RunStatus.SUCCESS
    assert api.alerts == []
    assert len(api.snapshots) == 1 and api.snapshots[0]["stale"] is False


# ---------- Decision ----------


def testStoppedLineCreatesAlertAndRemotePlanPerTeam(settings, state):
    api = FakeApi(
        [
            assignment("F1", "Financeiro", 3, "08:00"),
            assignment("F2", "Financeiro", 3, "09:30"),
            assignment("F3", "Tecnologia", 3, "10:30"),
            assignment("F4", "Tecnologia", 3, "07:00"),  # Window already passed at 07:30
            assignment("F5", "Tecnologia", 1, "08:00"),  # Other line
        ]
    )
    summary = runFlow(FakeSource([reading(1, "Operação Normal"), reading(3, "Paralisada")]), api, state, settings)

    assert summary.status == RunStatus.SUCCESS
    assert [alert["dedupeKey"] for alert in api.alerts] == ["line3-stopped-2026-11-10"]
    assert api.alerts[0]["message"].startswith("Linha 3-Vermelha paralisada")
    assert {(plan["teamName"], plan["action"]) for plan in api.plans} == {("Financeiro", "remoteWork"), ("Tecnologia", "remoteWork")}
    tecnologia = next(plan for plan in api.plans if plan["teamName"] == "Tecnologia")
    assert tecnologia["assignmentIds"] == ["as-F3"]


def testDegradedLineProposesLaterEntryWindow(settings, state):
    api = FakeApi([assignment("F1", "Financeiro", 1, "08:00"), assignment("F2", "Financeiro", 1, "10:30")])
    runFlow(FakeSource([reading(1, "Velocidade Reduzida"), reading(3, "Operação Normal")]), api, state, settings)

    actions = {(plan["action"], plan.get("newEntryWindow")) for plan in api.plans}
    assert actions == {("shiftEntryWindow", "09:30"), ("remoteWork", None)}


def testSameStatusTwiceDoesNotDuplicateAlert(settings, state):
    api = FakeApi()
    source = FakeSource([reading(1, "Operação Normal"), reading(3, "Paralisada")])
    runFlow(source, api, state, settings)
    summary = runFlow(source, api, state, settings)
    assert len(api.alerts) == 1
    assert summary.itemsSkipped == 2


def testLineBackToNormalCreatesNormalizedAlertWithoutPlan(settings, state):
    api = FakeApi([assignment("F1", "Financeiro", 3, "09:30")])
    runFlow(FakeSource([reading(1, "Operação Normal"), reading(3, "Paralisada")]), api, state, settings)
    runFlow(FakeSource([reading(1, "Operação Normal"), reading(3, "Operação Normal")]), api, state, settings)
    assert [alert["status"] for alert in api.alerts] == ["stopped", "normal"]
    assert len(api.plans) == 1


def testClosedOperationNeverTriggersPlanB(settings, state):
    api = FakeApi([assignment("F1", "Financeiro", 3, "09:30")])
    runFlow(FakeSource([reading(1, "Operação Encerrada"), reading(3, "Operação Encerrada")]), api, state, settings)
    assert api.alerts == [] and api.plans == []


def testOutsideOperatingWindowIsSkipped(settings, state):
    api = FakeApi()
    saturday = datetime(2026, 11, 14, 9, 0, tzinfo=SAO_PAULO)
    summary = runFlow(FakeSource([reading(1, "Paralisada"), reading(3, "Paralisada")]), api, state, settings, now=saturday)
    assert summary.status == RunStatus.SKIPPED
    assert api.alerts == []


# ---------- Failure ----------


def testSourceDownUsesLastKnownStateNotStale(settings, state):
    api = FakeApi()
    runFlow(FakeSource([reading(1, "Operação Normal"), reading(3, "Operação Normal")]), api, state, settings)
    later = TUESDAY_0730 + timedelta(minutes=10)
    summary = runFlow(FakeSource(error=SourceUnavailableError("HTTP 503")), api, state, settings, now=later)
    assert summary.status == RunStatus.PARTIAL
    assert api.snapshots[-1]["stale"] is False
    assert len(api.snapshots[-1]["lines"]) == 2


def testSourceDownForTooLongMarksDataStale(settings, state):
    api = FakeApi()
    runFlow(FakeSource([reading(1, "Operação Normal"), reading(3, "Operação Normal")]), api, state, settings)
    later = TUESDAY_0730 + timedelta(minutes=45)
    summary = runFlow(FakeSource(error=SourceUnavailableError("Timeout")), api, state, settings, now=later)
    assert summary.details["stale"] is True
    assert api.snapshots[-1]["stale"] is True


def testLayoutChangeFailsWithoutPlanB(settings, state):
    api = FakeApi()
    summary = runFlow(FakeSource(error=SourceLayoutChangedError("No li.linha")), api, state, settings)
    assert summary.status == RunStatus.FAILED
    assert summary.exitCode == 1
    assert api.alerts == [] and api.plans == []


def testMissingMonitoredLineIsTreatedAsLayoutChange(settings, state):
    summary = runFlow(FakeSource([reading(1, "Operação Normal")]), FakeApi(), state, settings)
    assert summary.status == RunStatus.FAILED


def testApiDownKeepsChangePendingAndRecoversNextRun(settings, state):
    api = FakeApi()
    api.failAlerts = True
    source = FakeSource([reading(1, "Operação Normal"), reading(3, "Paralisada")])

    first = runFlow(source, api, state, settings)
    assert first.status == RunStatus.PARTIAL and first.itemsFailed == 1
    assert api.alerts == []

    api.failAlerts = False
    second = runFlow(source, api, state, settings)
    assert second.status == RunStatus.SUCCESS
    assert [alert["status"] for alert in api.alerts] == ["stopped"]


def testLogsNeverContainEmployeeIds(settings, state):
    import json
    import logging

    from src.infrastructure.robotLogger import buildEmployeeRef

    captured: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = captured.append
    baseLogger = logging.getLogger("lgpdCapture")
    baseLogger.addHandler(handler)
    baseLogger.setLevel(logging.INFO)

    api = FakeApi([assignment("EMP12345", "Financeiro", 3, "09:30")])
    logger = RunLogger("lineMonitorFlow", "lgpd-run", baseLogger=baseLogger)
    LineMonitorFlow(FakeSource([reading(1, "Operação Normal"), reading(3, "Paralisada")]), api, state, settings, logger, clock=lambda: TUESDAY_0730).run()

    dump = json.dumps([[record.getMessage(), getattr(record, "data", None), getattr(record, "itemRef", None)] for record in captured])
    assert "EMP12345" not in dump
    assert buildEmployeeRef("EMP12345", "test") in dump
    assert all(record.getMessage()[0].isupper() for record in captured)
