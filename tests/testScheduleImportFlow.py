"""Etapa 07 — success, decision and failure scenarios of scheduleImportFlow.

Real adapters for disk (spreadsheet reader, folders, landing zone, HR report) on a temporary folder,
fake product API (no network) and in-memory robot state.
"""

import json
import logging
import shutil
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from src.adapters.inbound.localInputFolder import LocalInputFolder
from src.adapters.inbound.openpyxlSpreadsheetReader import OpenpyxlSpreadsheetReader
from src.adapters.outbound.localLandingZone import LocalLandingZone
from src.adapters.outbound.sqliteRobotState import SqliteRobotState
from src.adapters.outbound.xlsxImportReport import XlsxImportReport
from src.application.flows.scheduleImportFlow import ScheduleImportFlow
from src.application.runSummary import RunStatus
from src.domain.exceptions import ApiRejectedError, ApiUnavailableError
from src.infrastructure.robotLogger import RunLogger, buildEmployeeRef
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import SAO_PAULO
from tools.sampleSpreadsheets import buildAllSamples, defaultEmployees

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=SAO_PAULO)


class FakeApi:
    def __init__(self):
        self.imports: dict[str, dict] = {}
        self.down = False
        self.reject = False
        self.calls = 0

    def submitScheduleImport(self, payload, idempotencyKey):
        self.calls += 1
        if self.down:
            raise ApiUnavailableError("Connection refused")
        if self.reject:
            raise ApiRejectedError("POST /scheduleImports rejected with HTTP 422", 422, '{"errors":[]}')
        if idempotencyKey not in self.imports:
            self.imports[idempotencyKey] = {"importId": f"imp-{len(self.imports) + 1}", "scheduleId": f"sch-{len(self.imports) + 1}", "payload": payload}
        return self.imports[idempotencyKey]


class Environment:
    def __init__(self, root: Path):
        self.root = root
        self.samples = root / "samples"
        buildAllSamples(self.samples)
        self.input = root / "input"
        self.settings = replace(
            Settings(), retryBaseSeconds=0, logSalt="test", logDir=root / "logs",
            inputDir=self.input, reportDir=root / "reports", landingZonePath=root / "landing",
        )
        self.api = FakeApi()
        self.state = SqliteRobotState(Path(":memory:"))
        self.records: list[logging.LogRecord] = []

    def drop(self, sampleName: str, asName: str | None = None) -> Path:
        self.input.mkdir(parents=True, exist_ok=True)
        return Path(shutil.copy(self.samples / sampleName, self.input / (asName or sampleName)))

    def run(self):
        baseLogger = logging.getLogger(f"testScheduleImport{id(self)}{len(self.records)}")
        baseLogger.setLevel(logging.INFO)
        collector = logging.Handler()
        collector.emit = self.records.append
        baseLogger.handlers = [collector]
        baseLogger.propagate = False
        logger = RunLogger("scheduleImportFlow", "si-test", baseLogger=baseLogger)
        return ScheduleImportFlow(
            OpenpyxlSpreadsheetReader(), LocalInputFolder(self.input), self.api, LocalLandingZone(self.settings.landingZonePath),
            XlsxImportReport(self.settings.reportDir), self.state, self.settings, logger, clock=lambda: NOW,
        ).run()

    def files(self, sub: str) -> list[str]:
        folder = self.input / sub
        return sorted(path.name for path in folder.iterdir() if path.is_file()) if folder.exists() else []

    def reportRows(self, sheet: str) -> list[tuple]:
        [report] = list((self.root / "reports").glob("importReport*.xlsx"))
        return list(load_workbook(report)[sheet].iter_rows(values_only=True))

    def events(self) -> list[str]:
        return [record.event for record in self.records]


@pytest.fixture
def env(tmp_path: Path) -> Environment:
    return Environment(tmp_path)


# ---------- Success ----------


def testValidSpreadsheetIsSentArchivedAndLanded(env):
    env.drop("scheduleValid.xlsx")
    summary = env.run()

    assert summary.status == RunStatus.SUCCESS and summary.exitCode == 0
    assert summary.itemsSucceeded == 1 and summary.details["rowsAccepted"] == 20
    [sent] = env.api.imports.values()
    assert len(sent["payload"]["employees"]) == 20
    assert env.files("processed") == ["scheduleValid.xlsx"]
    [batch] = list((env.root / "landing" / "schedule").glob("schedule*.json"))
    assert json.loads(batch.read_text(encoding="utf-8"))["scheduleId"] == "sch-1"
    assert ("Situação", "Aceita") in env.reportRows("Resumo")


def testIdempotencyKeyIsTheFileHash(env):
    env.drop("scheduleValid.xlsx")
    env.run()
    [key] = env.api.imports
    assert len(key) == 64


def testEmptyFolderEndsWithoutError(env):
    summary = env.run()
    assert summary.status == RunStatus.SUCCESS and summary.itemsTotal == 0
    assert "InputFolderCreated" in env.events() and "NoFilesToProcess" in env.events()  # EX01


# ---------- Decision ----------


def testTenPercentInvalidAcceptsValidRowsAndReportsTheOthers(env):
    env.drop("scheduleTenPercentInvalid.xlsx")
    summary = env.run()

    assert summary.itemsSucceeded == 1
    assert summary.details["rowsAccepted"] == 18 and summary.details["rowsRejected"] == 2
    refused = env.reportRows("Linhas recusadas")[1:]
    assert len(refused) == 2
    assert ("Funcionarios", 11, "E-mail", "E-mail inválido: email-sem-arroba.example") in refused
    assert ("Situação", "Aceita com linhas recusadas") in env.reportRows("Resumo")


def testThirtyPercentInvalidRejectsWholeFile(env):  # RN09
    env.drop("scheduleThirtyPercentInvalid.xlsx")
    summary = env.run()

    assert summary.status == RunStatus.PARTIAL and summary.itemsFailed == 1
    assert env.api.calls == 0
    assert env.files("rejected") == ["scheduleThirtyPercentInvalid.xlsx"]
    assert ("Situação", "Rejeitada") in env.reportRows("Resumo")


def testOneBadFileDoesNotStopTheOthers(env):
    env.drop("scheduleCorrupted.xlsx")
    env.drop("scheduleValid.xlsx")
    summary = env.run()
    assert summary.itemsSucceeded == 1 and summary.itemsFailed == 1
    assert env.files("processed") == ["scheduleValid.xlsx"]


# ---------- Failure ----------


def testCorruptedFileIsRejectedWithReport(env):  # EX02
    env.drop("scheduleCorrupted.xlsx")
    summary = env.run()
    assert summary.itemsFailed == 1
    assert env.files("rejected") == ["scheduleCorrupted.xlsx"]
    assert any("corrompido" in str(row[3]) for row in env.reportRows("Linhas recusadas"))


def testNonXlsxFileIsRejectedNotIgnored(env):  # EX02
    env.input.mkdir(parents=True)
    (env.input / "escala.csv").write_text("Matrícula;Nome\n", encoding="utf-8")
    env.run()
    assert env.files("rejected") == ["escala.csv"]


def testMissingSheetIsRejected(env):  # EX03
    env.drop("scheduleMissingSheet.xlsx")
    env.run()
    assert env.files("rejected") == ["scheduleMissingSheet.xlsx"]
    assert ("Janelas", "-", "-", "Aba Janelas não encontrada") in env.reportRows("Linhas recusadas")


def testSameFileTwiceIsImportedOnce(env):  # RN02 / EX05
    env.drop("scheduleValid.xlsx")
    env.run()
    env.drop("scheduleValid.xlsx", asName="scheduleValidCopia.xlsx")
    summary = env.run()

    assert summary.itemsSkipped == 1 and summary.details["filesDuplicated"] == 1
    assert len(env.api.imports) == 1
    assert env.files("rejected/duplicates") == ["scheduleValidCopia.xlsx"]


def testApiDownQueuesInOutboxAndDeliversNextRun(env):  # EX06
    env.drop("scheduleValid.xlsx")
    env.api.down = True
    first = env.run()

    assert first.status == RunStatus.PARTIAL and first.exitCode == 2
    assert env.api.calls == 3  # 3 attempts before giving up
    assert first.details["filesQueued"] == 1
    assert env.files("processed") == ["scheduleValid.xlsx"]  # Validated work is not lost
    assert len(env.state.listOutbox("scheduleImport")) == 1

    env.api.down = False
    second = env.run()
    assert second.details["outboxDelivered"] == 1
    assert len(env.api.imports) == 1 and env.state.listOutbox("scheduleImport") == []


def testOutboxStaysWhileApiIsDown(env):
    env.drop("scheduleValid.xlsx")
    env.api.down = True
    env.run()
    second = env.run()
    assert second.status == RunStatus.PARTIAL and second.details["outboxPending"] == 1
    assert env.state.listOutbox("scheduleImport")[0]["attempts"] == 2


def testApiRejectionIsNotRetriedAndFileIsRejected(env):  # EX07
    env.drop("scheduleValid.xlsx")
    env.api.reject = True
    summary = env.run()
    assert env.api.calls == 1
    assert summary.itemsFailed == 1 and env.files("rejected") == ["scheduleValid.xlsx"]
    assert "ImportRejectedByApi" in env.events()


# ---------- LGPD ----------


def testNoPersonalDataInLogsOrLandingZone(env):
    env.drop("scheduleTenPercentInvalid.xlsx")
    env.run()
    names = [row[1] for row in defaultEmployees()]
    emails = [row[2] for row in defaultEmployees()]

    logText = " ".join(f"{record.getMessage()} {getattr(record, 'data', '')}" for record in env.records)
    assert not any(item in logText for item in names + emails + ["email-sem-arroba"])

    [batch] = list((env.root / "landing" / "schedule").glob("schedule*.json"))
    landed = batch.read_text(encoding="utf-8")
    assert not any(item in landed for item in names + emails)
    assert buildEmployeeRef("F1001", "test") in landed
    assert all(record.getMessage()[0].isupper() for record in env.records)
