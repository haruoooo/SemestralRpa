"""Fluxo 3 — lineMonitorFlow: monitors line status and proposes plan B (docs/processDesign.md, section 5)."""

import time as timeModule
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime

from src.application.ports.lineStatusSourcePort import LineStatusSourcePort
from src.application.ports.productApiPort import ProductApiPort
from src.application.ports.robotStatePort import RobotStatePort
from src.application.runSummary import RunStatus, RunSummary
from src.domain.assignment import Assignment
from src.domain.exceptions import ApiRejectedError, ApiUnavailableError, SourceLayoutChangedError, SourceUnavailableError
from src.domain.lineStatus import (
    LineReading,
    LineStatusCode,
    buildAlertMessage,
    buildContingencyReason,
    buildDedupeKey,
    decideContingency,
    hasStatusChanged,
    isStale,
    isWindowStillAhead,
    isWithinOperatingWindow,
    requiresContingency,
)
from src.infrastructure.retryPolicy import callWithRetry
from src.infrastructure.robotLogger import RunLogger, buildEmployeeRef
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import nowLocal

FLOW_NAME = "lineMonitorFlow"


class LineMonitorFlow:
    def __init__(
        self,
        source: LineStatusSourcePort,
        api: ProductApiPort,
        state: RobotStatePort,
        settings: Settings,
        logger: RunLogger,
        clock: Callable[[], datetime] = nowLocal,
        respectOperatingWindow: bool = True,
    ):
        self._respectOperatingWindow = respectOperatingWindow
        self._source = source
        self._api = api
        self._state = state
        self._settings = settings
        self._logger = logger
        self._clock = clock

    # ---------- Orchestration ----------

    def run(self) -> RunSummary:
        startedAt = timeModule.perf_counter()
        now = self._clock()
        summary = RunSummary(runId=self._logger.runId, flow=FLOW_NAME)
        summary.details = {"alertsCreated": 0, "plansProposed": 0, "stale": False, "source": self._source.sourceName}
        self._logger.info("1", "RunStarted", f"Line monitor started (source={self._source.sourceName})")

        try:
            if self._respectOperatingWindow and not isWithinOperatingWindow(now, self._settings.monitorStart, self._settings.monitorEnd):
                self._logger.info("1", "OutsideOperatingWindow", "Outside weekday operating window; nothing to do (RN17)")
                summary.status = RunStatus.SKIPPED
                return summary

            try:
                readings = self._fetchReadings()
            except SourceUnavailableError as error:
                self._handleSourceUnavailable(error, now, summary)
                return summary

            self._state.saveSourceSuccessAt(now)
            monitored = self._selectMonitored(readings)
            summary.itemsTotal = len(monitored)

            for reading in monitored:
                self._processLineSafely(reading, now, summary)

            snapshotPublished = self._publishSnapshot(readings, now, stale=False)
            if summary.itemsFailed or not snapshotPublished:
                summary.status = RunStatus.PARTIAL

        except SourceLayoutChangedError as error:
            summary.status = RunStatus.FAILED
            self._logger.error("4", "SourceLayoutChanged", f"Source content could not be interpreted; no plan B generated (EX10): {error}")
        except Exception as error:  # EX11: never fail silently
            summary.status = RunStatus.FAILED
            self._logger.error("-", "UnexpectedError", f"Unexpected failure: {type(error).__name__}", excInfo=True)
        finally:
            summary.durationSeconds = round(timeModule.perf_counter() - startedAt, 3)
            self._logger.info("7", "RunSummary", f"Line monitor finished with status {summary.status.value}", data=summary.toDict())
        return summary

    # ---------- Step 2/3: source ----------

    def _fetchReadings(self) -> list[LineReading]:
        readings = callWithRetry(
            self._source.fetchReadings,
            retryOn=(SourceUnavailableError,),
            attempts=self._settings.retryAttempts,
            baseSeconds=self._settings.retryBaseSeconds,
            logger=self._logger,
            step="2",
            description="Fetching line status",
        )
        self._logger.info("2", "SourceFetched", f"Received {len(readings)} lines from {self._source.sourceName}")
        return readings

    def _selectMonitored(self, readings: list[LineReading]) -> list[LineReading]:
        found = {reading.lineNumber for reading in readings}
        missing = [line for line in self._settings.monitoredLines if line not in found]
        if missing:
            raise SourceLayoutChangedError(f"Monitored lines missing from source: {missing}")
        return [reading for reading in readings if reading.lineNumber in self._settings.monitoredLines]

    def _handleSourceUnavailable(self, error: Exception, now: datetime, summary: RunSummary) -> None:
        stale = isStale(self._state.getLastSourceSuccessAt(), now, self._settings.staleAfterMinutes)
        summary.status = RunStatus.PARTIAL
        summary.details["stale"] = stale
        self._logger.warning("3", "SourceUnavailable", f"Source unavailable after retries, using last known state (EX09): {error}")
        if stale:
            self._logger.warning(
                "3", "DataStale", f"Last successful reading is older than {self._settings.staleAfterMinutes} min; no plan B will be generated (RN16)"
            )
        lastReadings = self._state.getLastReadings()
        if lastReadings:
            self._publishSnapshot(lastReadings, now, stale=stale)

    # ---------- Step 5: per line ----------

    def _processLineSafely(self, reading: LineReading, now: datetime, summary: RunSummary) -> None:
        itemRef = f"line{reading.lineNumber}"
        try:
            outcome = self._processLine(reading, now, summary)
            if outcome == "unchanged":
                summary.itemsSkipped += 1
            else:
                summary.itemsSucceeded += 1
        except ApiUnavailableError as error:
            summary.itemsFailed += 1
            self._logger.error("5", "ApiUnavailable", f"API unavailable; line state not committed, change will be retried next run (EX06): {error}", itemRef)
        except ApiRejectedError as error:
            summary.itemsFailed += 1
            self._state.saveLineStatus(reading, now)  # EX07: not retryable, avoid an endless loop
            self._logger.error(
                "5", "ApiRejected", f"API rejected the payload; not retried (EX07): {error}", itemRef, data={"statusCode": error.statusCode, "body": error.responseBody}
            )

    def _processLine(self, reading: LineReading, now: datetime, summary: RunSummary) -> str:
        itemRef = f"line{reading.lineNumber}"
        previous = self._state.getLastLineStatus(reading.lineNumber)

        if reading.status == LineStatusCode.UNKNOWN:
            self._logger.warning("5.1", "UnknownStatusText", f"Unrecognized status text {reading.rawText!r}; keeping previous state (RN12)", itemRef)
            return "unchanged"

        if not hasStatusChanged(previous, reading.status):
            self._logger.info("5.2", "LineStatusUnchanged", f"Line {reading.lineNumber} still {reading.status.value} (RN13)", itemRef)
            return "unchanged"

        baseline = previous or LineStatusCode.NORMAL
        if reading.status in (LineStatusCode.NORMAL, LineStatusCode.CLOSED) and baseline in (LineStatusCode.NORMAL, LineStatusCode.CLOSED):
            self._state.saveLineStatus(reading, now)
            self._logger.info("5.2", "LineStatusRecorded", f"Line {reading.lineNumber} recorded as {reading.status.value}; routine change, no alert", itemRef)
            return "recorded"

        self._logger.warning("5.2", "LineStatusChanged", f"Line {reading.lineNumber} changed from {baseline.value} to {reading.status.value}", itemRef)
        alert = self._createAlert(reading, baseline, now)
        summary.details["alertsCreated"] += 1

        if requiresContingency(reading.status):
            summary.details["plansProposed"] += self._proposeContingency(reading, alert["alertId"], now)
        elif reading.status == LineStatusCode.NORMAL:
            self._logger.info("5.6", "LineNormalized", f"Line {reading.lineNumber} back to normal", itemRef)

        self._state.saveLineStatus(reading, now)
        return "changed"

    def _createAlert(self, reading: LineReading, previous: LineStatusCode, now: datetime) -> dict:
        payload = {
            "dedupeKey": buildDedupeKey(reading.lineNumber, reading.status, now),
            "lineNumber": reading.lineNumber,
            "previousStatus": previous.value,
            "status": reading.status.value,
            "detectedAt": now.isoformat(timespec="seconds"),
            "message": buildAlertMessage(reading.lineNumber, reading.status, now),
        }
        alert = self._callApi(lambda: self._api.createAlert(payload), "5.3", "Creating alert")
        self._logger.info("5.3", "AlertCreated", f"Alert {alert['alertId']} created ({payload['dedupeKey']})", f"line{reading.lineNumber}")
        return alert

    def _proposeContingency(self, reading: LineReading, alertId: str, now: datetime) -> int:
        itemRef = f"line{reading.lineNumber}"
        today = now.date().isoformat()
        assignments: list[Assignment] = self._callApi(
            lambda: self._api.listAssignments(today, reading.lineNumber), "5.4", "Listing affected assignments"
        )
        affected = [item for item in assignments if isWindowStillAhead(item.entryWindow, now)]
        self._logger.info(
            "5.4",
            "AffectedAssignmentsFound",
            f"Found {len(affected)} of {len(assignments)} on-site assignments still ahead on line {reading.lineNumber}",
            itemRef,
        )
        if not affected:
            return 0

        groups: dict[tuple, list[Assignment]] = defaultdict(list)
        for item in affected:  # Loop: one decision per employee, grouped into one plan per team/action
            action, newWindow = decideContingency(reading.status, item.entryWindow, item.allowedEntryWindows)
            groups[(item.teamName, action, newWindow)].append(item)

        for (teamName, action, newWindow), members in groups.items():
            plan = {
                "alertId": alertId,
                "date": today,
                "teamName": teamName,
                "action": action.value,
                "assignmentIds": [member.assignmentId for member in members],
                "reason": buildContingencyReason(reading.lineNumber, action, newWindow),
            }
            if newWindow:
                plan["newEntryWindow"] = newWindow
            created = self._callApi(lambda: self._api.createContingencyPlan(plan), "5.5", "Proposing plan B")
            self._logger.info(
                "5.5",
                "ContingencyPlanProposed",
                f"Plan B {created.get('planId')} ({action.value}{' to ' + newWindow if newWindow else ''}) proposed for team {teamName}, pending HR approval (RN15)",
                itemRef,
                data={"employeeRefs": [buildEmployeeRef(member.employeeId, self._settings.logSalt) for member in members]},
            )
        return len(groups)

    # ---------- Step 6: snapshot ----------

    def _publishSnapshot(self, readings: list[LineReading], now: datetime, stale: bool) -> bool:
        snapshot = {
            "collectedAt": now.isoformat(timespec="seconds"),
            "source": self._source.sourceName,
            "stale": stale,
            "lines": [
                {
                    "lineNumber": reading.lineNumber,
                    "lineName": reading.lineName,
                    "status": reading.status.value,
                    "rawText": reading.rawText,
                    "sourceUpdatedAt": reading.sourceUpdatedAt.isoformat() if reading.sourceUpdatedAt else None,
                }
                for reading in readings
            ],
        }
        try:
            self._callApi(lambda: self._api.publishLineStatus(snapshot), "6", "Publishing line status snapshot")
            self._logger.info("6", "SnapshotPublished", f"Snapshot with {len(readings)} lines published (stale={stale})")
            return True
        except (ApiUnavailableError, ApiRejectedError) as error:
            self._logger.error("6", "SnapshotNotPublished", f"Snapshot not published; next run will send a fresh one: {error}")
            return False

    def _callApi(self, operation, step: str, description: str):
        return callWithRetry(
            operation,
            retryOn=(ApiUnavailableError,),
            attempts=self._settings.retryAttempts,
            baseSeconds=self._settings.retryBaseSeconds,
            logger=self._logger,
            step=step,
            description=description,
        )
