"""Fluxo 1 — scheduleImportFlow: imports and validates the HR spreadsheet (docs/processDesign.md, section 3)."""

import hashlib
import time as timeModule
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from src.application.ports.importReportPort import ImportReportPort
from src.application.ports.inputFolderPort import InputFolderPort
from src.application.ports.landingZonePort import LandingZonePort
from src.application.ports.productApiPort import ProductApiPort
from src.application.ports.robotStatePort import RobotStatePort
from src.application.ports.spreadsheetReaderPort import SpreadsheetReaderPort
from src.application.runSummary import RunStatus, RunSummary
from src.domain.exceptions import ApiRejectedError, ApiUnavailableError, InvalidSpreadsheetError
from src.domain.scheduleImport import RowIssue, ValidationResult, validateWorkbook
from src.infrastructure.retryPolicy import callWithRetry
from src.infrastructure.robotLogger import RunLogger, buildEmployeeRef
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import nowLocal

FLOW_NAME = "scheduleImportFlow"
OUTBOX_KIND = "scheduleImport"
LANDING_DATASET = "schedule"

# Outcomes shown to HR in the report (Portuguese)
OUTCOME_ACCEPTED = "Aceita"
OUTCOME_ACCEPTED_WITH_ISSUES = "Aceita com linhas recusadas"
OUTCOME_QUEUED = "Aceita; envio à plataforma pendente (será reenviada automaticamente)"
OUTCOME_REJECTED = "Rejeitada"


def sha256File(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ScheduleImportFlow:
    def __init__(
        self,
        reader: SpreadsheetReaderPort,
        inputFolder: InputFolderPort,
        api: ProductApiPort,
        landingZone: LandingZonePort,
        report: ImportReportPort,
        state: RobotStatePort,
        settings: Settings,
        logger: RunLogger,
        clock: Callable[[], datetime] = nowLocal,
    ):
        self._reader = reader
        self._inputFolder = inputFolder
        self._api = api
        self._landingZone = landingZone
        self._report = report
        self._state = state
        self._settings = settings
        self._logger = logger
        self._clock = clock

    # ---------- Orchestration ----------

    def run(self) -> RunSummary:
        startedAt = timeModule.perf_counter()
        summary = RunSummary(runId=self._logger.runId, flow=FLOW_NAME)
        summary.details = {
            "rowsAccepted": 0, "rowsRejected": 0, "filesRejected": 0, "filesDuplicated": 0,
            "filesQueued": 0, "outboxDelivered": 0, "outboxPending": 0,
        }
        self._logger.info("1", "RunStarted", "Schedule import started")
        try:
            self._replayOutbox(summary)

            if self._inputFolder.ensureExists():
                self._logger.warning("3", "InputFolderCreated", "Input folder was missing and has been created (EX01)")
            files = self._inputFolder.listPending()
            if not files:
                self._logger.info("3", "NoFilesToProcess", "No files to process")
                if summary.details["outboxPending"]:
                    summary.status = RunStatus.PARTIAL
                return summary

            summary.itemsTotal = len(files)
            self._logger.info("3", "FilesFound", f"Found {len(files)} file(s) to process")
            for path in files:  # Loop: one file at a time; a failure never stops the others
                self._processFileSafely(path, summary)

            if summary.itemsFailed or summary.details["filesQueued"] or summary.details["outboxPending"]:
                summary.status = RunStatus.PARTIAL
        except Exception:  # EX11: never fail silently
            summary.status = RunStatus.FAILED
            self._logger.error("-", "UnexpectedError", "Unexpected failure in schedule import", excInfo=True)
        finally:
            summary.durationSeconds = round(timeModule.perf_counter() - startedAt, 3)
            self._logger.info("5", "RunSummary", f"Schedule import finished with status {summary.status.value}", data=summary.toDict())
        return summary

    # ---------- Step 2: outbox ----------

    def _replayOutbox(self, summary: RunSummary) -> None:
        pending = self._state.listOutbox(OUTBOX_KIND)
        if not pending:
            return
        self._logger.info("2", "OutboxReplayStarted", f"Replaying {len(pending)} pending send(s) from the outbox (EX06)")
        for index, item in enumerate(pending):
            itemRef = f"file{item['idempotencyKey'][:8]}"
            try:
                result = self._api.submitScheduleImport(item["payload"], item["idempotencyKey"])
            except ApiUnavailableError as error:
                self._state.recordOutboxFailure(item["outboxId"], str(error))
                summary.details["outboxPending"] = len(pending) - index
                self._logger.warning("2", "OutboxStillPending", f"API still unavailable; {len(pending) - index} send(s) kept in the outbox: {error}", itemRef)
                return  # API is down: no point trying the next ones now
            except ApiRejectedError as error:
                self._state.removeOutbox(item["outboxId"])
                self._logger.error(
                    "2", "OutboxRejected", f"API rejected a queued import; removed from the outbox (EX07): {error}", itemRef,
                    data={"statusCode": error.statusCode, "body": error.responseBody},
                )
                continue
            self._state.removeOutbox(item["outboxId"])
            summary.details["outboxDelivered"] += 1
            self._logger.info("2", "OutboxDelivered", f"Queued import delivered as {result.get('importId')} (schedule {result.get('scheduleId')})", itemRef)

    # ---------- Step 4: per file ----------

    def _processFileSafely(self, path: Path, summary: RunSummary) -> None:
        try:
            outcome = self._processFile(path, summary)
        except Exception:  # EX11 at file level: log, park the file, keep going
            outcome = "failed"
            self._logger.error("4", "FileProcessingError", f"Unexpected failure while processing {path.name}", f"file:{path.name}", excInfo=True)
            self._safeMove(path, "rejected")
        if outcome in ("accepted", "queued"):
            summary.itemsSucceeded += 1
        elif outcome == "duplicate":
            summary.itemsSkipped += 1
        else:
            summary.itemsFailed += 1

    def _processFile(self, path: Path, summary: RunSummary) -> str:
        now = self._clock()
        fileHash = sha256File(path)
        itemRef = f"file{fileHash[:8]}"
        self._logger.info("4.1", "FileStarted", f"Processing file {path.name}", itemRef)

        if self._state.isFileProcessed(fileHash):  # RN02 / EX05
            self._inputFolder.moveTo(path, "rejected/duplicates")
            summary.details["filesDuplicated"] += 1
            self._logger.warning("4.1", "DuplicateFile", f"File {path.name} was already imported; moved to rejected/duplicates (RN02)", itemRef)
            return "duplicate"

        try:
            sheets = self._reader.read(path)
        except InvalidSpreadsheetError as error:  # EX02
            issue = RowIssue("-", None, None, "O arquivo está corrompido ou não é uma planilha .xlsx. Salve-o de novo no Excel como .xlsx")
            return self._reject(path, fileHash, summary, f"Invalid file (EX02): {error}", ValidationResult(issues=[issue], rejectionReason=issue.message))

        result = validateWorkbook(sheets)  # 4.3 to 4.5
        self._logRowIssues(result, itemRef)
        summary.details["rowsRejected"] += result.rejectedRows
        if not result.accepted:
            return self._reject(path, fileHash, summary, "Spreadsheet rejected by validation rules (RN01/RN09)", result)

        # 4.6 send to the product API
        apiResult, outcome = self._submit(result.payload, fileHash, now, itemRef)
        if outcome == "rejectedByApi":
            return self._reject(path, fileHash, summary, "Product API refused the import (EX07)", result, apiRejected=True)

        summary.details["rowsAccepted"] += result.employeesValid
        if outcome == "queued":
            summary.details["filesQueued"] += 1

        # 4.7 Big Data landing zone (pseudonymized)
        location = self._landingZone.write(LANDING_DATASET, f"schedule{now.strftime('%Y%m%d_%H%M%S')}_{fileHash[:8]}.json", self._buildLandingBatch(result, fileHash, apiResult, now))
        self._logger.info("4.7", "LandingZoneWritten", f"Pseudonymized batch written to the landing zone: {location}", itemRef)

        # 4.8 HR report
        hrOutcome = OUTCOME_QUEUED if outcome == "queued" else (OUTCOME_ACCEPTED_WITH_ISSUES if result.issues else OUTCOME_ACCEPTED)
        self._writeReport(path.name, fileHash, hrOutcome, result, apiResult, itemRef)

        # 4.9 archive + remember the hash
        self._inputFolder.moveTo(path, "processed")
        self._state.markFileProcessed(fileHash, path.name, outcome, now)
        self._logger.info(
            "4.9", "FileImported",
            f"File {path.name} imported with {result.employeesValid} employee(s) and {result.rejectedRows} refused row(s); moved to processed",
            itemRef, data={"importId": (apiResult or {}).get("importId"), "queued": outcome == "queued"},
        )
        return outcome

    def _submit(self, payload: dict, fileHash: str, now: datetime, itemRef: str) -> tuple[dict | None, str]:
        try:
            apiResult = callWithRetry(
                lambda: self._api.submitScheduleImport(payload, fileHash),
                retryOn=(ApiUnavailableError,),
                attempts=self._settings.retryAttempts,
                baseSeconds=self._settings.retryBaseSeconds,
                logger=self._logger,
                step="4.6",
                description="Sending schedule import",
            )
        except ApiUnavailableError as error:  # EX06: nothing is lost
            self._state.enqueueOutbox(OUTBOX_KIND, fileHash, payload, str(error), now)
            self._logger.warning("4.6", "ImportQueued", f"API unavailable after retries; import saved to the outbox for the next run (EX06): {error}", itemRef)
            return None, "queued"
        except ApiRejectedError as error:  # EX07: not retried
            self._logger.error(
                "4.6", "ImportRejectedByApi", f"API refused the import: {error}", itemRef,
                data={"statusCode": error.statusCode, "body": error.responseBody},
            )
            return None, "rejectedByApi"
        self._logger.info("4.6", "ImportSent", f"Import {apiResult.get('importId')} created, schedule {apiResult.get('scheduleId')} pending HR approval", itemRef)
        return apiResult, "accepted"

    def _reject(self, path: Path, fileHash: str, summary: RunSummary, logMessage: str, result: ValidationResult, apiRejected: bool = False) -> str:
        itemRef = f"file{fileHash[:8]}"
        summary.details["filesRejected"] += 1
        if apiRejected:
            result.rejectionReason = "A plataforma recusou a importação. A equipe técnica foi avisada pelo log do robô"
        self._writeReport(path.name, fileHash, OUTCOME_REJECTED, result, None, itemRef)
        self._inputFolder.moveTo(path, "rejected")
        self._logger.warning("4.5", "FileRejected", f"File {path.name} moved to rejected: {logMessage}", itemRef, data={"issues": len(result.issues)})
        return "rejected"

    # ---------- Helpers ----------

    def _logRowIssues(self, result: ValidationResult, itemRef: str) -> None:
        # LGPD: only sheet/row/column go to the log; the values (names, e-mails) stay in the HR report
        for issue in result.issues:
            self._logger.warning("4.4", "RowRefused", f"Refused {issue.sheet} row {issue.rowNumber or '-'} column {issue.column or '-'}", itemRef)
        self._logger.info(
            "4.5", "ValidationFinished",
            f"Validation: {result.employeesValid}/{result.employeesTotal} employees and {result.demandValid}/{result.demandTotal} demand rows valid",
            itemRef, data={"accepted": result.accepted},
        )

    def _writeReport(self, fileName: str, fileHash: str, outcome: str, result: ValidationResult, apiResult: dict | None, itemRef: str) -> None:
        summary: dict[str, object] = {
            "Motivo da rejeição": result.rejectionReason or "-",
            "Funcionários aceitos": f"{result.employeesValid} de {result.employeesTotal}",
            "Linhas de demanda aceitas": f"{result.demandValid} de {result.demandTotal}",
            "Escala na plataforma": (apiResult or {}).get("scheduleId", "-"),
            "Processado em": self._clock().strftime("%d/%m/%Y %H:%M"),
        }
        location = self._report.write(fileName, fileHash, outcome, summary, result.issues)
        self._logger.info("4.8", "ReportWritten", f"HR report written: {location}", itemRef)

    def _safeMove(self, path: Path, destination: str) -> None:
        try:
            if path.exists():
                self._inputFolder.moveTo(path, destination)
        except OSError:
            self._logger.error("4", "FileMoveFailed", f"Could not move {path.name} to {destination}", f"file:{path.name}")

    def _buildLandingBatch(self, result: ValidationResult, fileHash: str, apiResult: dict | None, now: datetime) -> dict:
        """Big Data batch: no name or e-mail; the employee is a salted hash (LGPD). See docs/integrations/bigDataDataIntegration/landingZoneHandoff.md."""
        payload = result.payload
        return {
            "dataset": LANDING_DATASET,
            "schemaVersion": 1,
            "batchId": f"{self._logger.runId}-{fileHash[:8]}",
            "generatedAt": now.isoformat(timespec="seconds"),
            "sourceFileHash": fileHash,
            "importId": (apiResult or {}).get("importId"),
            "scheduleId": (apiResult or {}).get("scheduleId"),
            "companyName": payload["companyName"],
            "week": payload["week"],
            "entryWindows": payload["entryWindows"],
            "teams": payload["teams"],
            "employees": [
                {
                    "employeeRef": buildEmployeeRef(employee["employeeId"], self._settings.logSalt),
                    "teamName": employee["teamName"],
                    "lineNumber": employee["lineNumber"],
                    "boardingStation": employee["boardingStation"],
                    "monthlyOnSiteDays": employee["monthlyOnSiteDays"],
                    "unavailableDates": employee["unavailableDates"],
                    "latestEntryWindow": employee.get("latestEntryWindow"),
                }
                for employee in payload["employees"]
            ],
            "quality": {
                "employeesTotal": result.employeesTotal,
                "employeesValid": result.employeesValid,
                "demandTotal": result.demandTotal,
                "demandValid": result.demandValid,
                "rejectedRows": result.rejectedRows,
            },
        }
