"""Fluxo 2 — agendaDispatchFlow: sends approved agendas and plan B notices (docs/processDesign.md, section 4)."""

import time as timeModule
from collections.abc import Callable
from datetime import datetime

from src.application.ports.calendarPort import CalendarPort
from src.application.ports.notificationPort import NotificationPort
from src.application.ports.productApiPort import ProductApiPort
from src.application.ports.robotStatePort import RobotStatePort
from src.application.runSummary import RunStatus, RunSummary
from src.domain.agenda import (
    KIND_CONTINGENCY_PLAN,
    KIND_SCHEDULE,
    PLAN_VERSION,
    ContingencyPlan,
    EmailAttachment,
    OutgoingEmail,
    Schedule,
    buildPlanEmail,
    buildScheduleEmail,
    groupByEmployee,
    isApproved,
)
from src.domain.assignment import Assignment
from src.domain.exceptions import (
    ApiRejectedError,
    ApiUnavailableError,
    NotificationRejectedError,
    NotificationUnavailableError,
)
from src.infrastructure.retryPolicy import callWithRetry
from src.infrastructure.robotLogger import RunLogger, buildEmployeeRef
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import nowLocal

FLOW_NAME = "agendaDispatchFlow"
OUTBOX_KIND = "dispatchReport"
ICS_MIME = "text/calendar; method=REQUEST"


class _MailServerDown(Exception):
    """Internal signal: stop sending in this run, everything left stays pending (EX08)."""


class _LimitReached(Exception):
    """Internal signal: the per-run e-mail limit was reached; the rest goes in the next run."""


class AgendaDispatchFlow:
    def __init__(
        self,
        api: ProductApiPort,
        notifier: NotificationPort,
        calendar: CalendarPort,
        state: RobotStatePort,
        settings: Settings,
        logger: RunLogger,
        clock: Callable[[], datetime] = nowLocal,
    ):
        self._api = api
        self._notifier = notifier
        self._calendar = calendar
        self._state = state
        self._settings = settings
        self._logger = logger
        self._clock = clock
        self._reportItems: list[dict] = []
        self._sentThisRun = 0

    # ---------- Orchestration ----------

    def run(self) -> RunSummary:
        startedAt = timeModule.perf_counter()
        summary = RunSummary(runId=self._logger.runId, flow=FLOW_NAME)
        summary.details = {"schedules": 0, "plans": 0, "emailsSent": 0, "refusedAddresses": 0, "stoppedEarly": None, "reportQueued": False}
        self._logger.info("1", "RunStarted", f"Agenda dispatch started (channel={self._notifier.channel})")
        try:
            self._replayReportOutbox()
            try:
                schedules = [Schedule.fromApi(item) for item in self._callApi(lambda: self._api.listSchedules("approved", dispatched=False), "2", "Listing approved schedules")]
                plans = [ContingencyPlan.fromApi(item) for item in self._callApi(lambda: self._api.listContingencyPlans("approved", dispatched=False), "4", "Listing approved plans B")]
            except ApiUnavailableError as error:  # EX06: nothing to do without the API; next run tries again
                summary.status = RunStatus.PARTIAL
                self._logger.error("2", "ApiUnavailable", f"API unavailable; nothing dispatched, next run will try again (EX06): {error}")
                return summary
            summary.details["schedules"], summary.details["plans"] = len(schedules), len(plans)
            self._logger.info("2", "WorkFound", f"Found {len(schedules)} approved schedule(s) and {len(plans)} approved plan(s) B not yet dispatched")

            try:
                for schedule in schedules:  # Loop 3: schedule -> employee
                    self._dispatchSchedule(schedule, summary)
                for plan in plans:  # Loop 4: plan B -> affected employee
                    self._dispatchPlan(plan, summary)
            except _MailServerDown as error:
                summary.details["stoppedEarly"] = "mailServerUnavailable"
                self._logger.error("3.3", "MailServerUnavailable", f"Mail server unavailable after retries; remaining e-mails stay pending for the next run (EX08): {error}")
            except _LimitReached:
                summary.details["stoppedEarly"] = "dispatchLimitReached"
                self._logger.warning("3.3", "DispatchLimitReached", f"Per-run e-mail limit of {self._settings.dispatchLimitPerRun} reached; the rest goes in the next run")

            self._sendReport(summary)
            if summary.itemsFailed or summary.details["reportQueued"]:
                summary.status = RunStatus.PARTIAL
        except Exception:  # EX11
            summary.status = RunStatus.FAILED
            self._logger.error("-", "UnexpectedError", "Unexpected failure in agenda dispatch", excInfo=True)
        finally:
            summary.durationSeconds = round(timeModule.perf_counter() - startedAt, 3)
            self._logger.info("6", "RunSummary", f"Agenda dispatch finished with status {summary.status.value}", data=summary.toDict())
        return summary

    # ---------- Step 3: schedules ----------

    def _dispatchSchedule(self, schedule: Schedule, summary: RunSummary) -> None:
        itemRef = f"{schedule.scheduleId}v{schedule.version}"
        if not isApproved(schedule.status):  # RN10, defensive: the API filter should already guarantee it
            self._logger.warning("3", "ScheduleNotApproved", f"Schedule {schedule.scheduleId} is {schedule.status}; not dispatched (RN10)", itemRef)
            return
        byEmployee = groupByEmployee(schedule.assignments)
        self._logger.info("3", "ScheduleStarted", f"Schedule {schedule.scheduleId} version {schedule.version}: {len(byEmployee)} employee(s)", itemRef)
        for employeeId, items in byEmployee.items():
            summary.itemsTotal += 1
            if self._state.isDispatched(KIND_SCHEDULE, schedule.scheduleId, schedule.version, employeeId):  # RN11
                summary.itemsSkipped += 1
                self._logger.info("3.1", "AlreadyDispatched", "Employee already received this version (RN11)", itemRef, data={"employeeRef": self._ref(employeeId)})
                continue
            subject, text, html = buildScheduleEmail(items, schedule)
            attachment = EmailAttachment("agenda.ics", self._calendar.buildAgenda(items, self._sequence()), ICS_MIME)
            email = OutgoingEmail(items[0].email, subject, text, html, (attachment,))
            self._deliver(KIND_SCHEDULE, schedule.scheduleId, schedule.version, employeeId, email, summary, itemRef)

    # ---------- Step 4: plans B ----------

    def _dispatchPlan(self, plan: ContingencyPlan, summary: RunSummary) -> None:
        itemRef = plan.planId
        if not isApproved(plan.status):
            self._logger.warning("4", "PlanNotApproved", f"Plan B {plan.planId} is {plan.status}; not dispatched (RN15)", itemRef)
            return
        affected = self._affectedOf(plan)
        self._logger.info("4", "PlanStarted", f"Plan B {plan.planId} ({plan.action}) for team {plan.teamName}: {len(affected)} employee(s)", itemRef)
        today = self._clock().date()
        for item in affected:
            summary.itemsTotal += 1
            if self._state.isDispatched(KIND_CONTINGENCY_PLAN, plan.planId, PLAN_VERSION, item.employeeId):
                summary.itemsSkipped += 1
                continue
            if plan.action == "remoteWork":
                ics = self._calendar.buildRemoteWork(item, self._sequence())
                attachment = EmailAttachment("agenda.ics", ics, "text/calendar; method=CANCEL")
            else:
                ics = self._calendar.buildShiftedEntry(item, plan.newEntryWindow or item.entryWindow, self._sequence())
                attachment = EmailAttachment("agenda.ics", ics, ICS_MIME)
            subject, text, html = buildPlanEmail(item, plan, today)
            email = OutgoingEmail(item.email, subject, text, html, (attachment,))
            self._deliver(KIND_CONTINGENCY_PLAN, plan.planId, PLAN_VERSION, item.employeeId, email, summary, itemRef)

    def _affectedOf(self, plan: ContingencyPlan) -> list[Assignment]:
        if plan.affected:
            return plan.affected
        # Fallback when the API does not embed the assignments: look them up by id
        byId = {item.assignmentId: item for item in self._callApi(lambda: self._api.listAssignments(plan.date), "4", "Listing plan assignments")}
        return [byId[assignmentId] for assignmentId in plan.assignmentIds if assignmentId in byId]

    # ---------- Delivery (3.3) ----------

    def _deliver(self, kind: str, referenceId: str, version: int, employeeId: str, email: OutgoingEmail, summary: RunSummary, itemRef: str) -> None:
        employeeRef = self._ref(employeeId)
        limit = self._settings.dispatchLimitPerRun
        if limit and self._sentThisRun >= limit:
            raise _LimitReached()
        report = {"kind": kind, "referenceId": referenceId, "version": version, "employeeId": employeeId, "channel": self._notifier.channel}

        if not email.to:
            self._refused(kind, referenceId, version, employeeId, report, "Employee has no e-mail address", summary, itemRef)
            return
        try:
            callWithRetry(
                lambda: self._notifier.send(email),
                retryOn=(NotificationUnavailableError,),
                attempts=self._settings.retryAttempts,
                baseSeconds=self._settings.retryBaseSeconds,
                logger=self._logger,
                step="3.3",
                description="Sending e-mail",
            )
        except NotificationRejectedError as error:
            self._refused(kind, referenceId, version, employeeId, report, str(error), summary, itemRef)
            return
        except NotificationUnavailableError as error:  # EX08: not recorded, so the next run sends it again
            summary.itemsFailed += 1
            self._reportItems.append({**report, "delivered": False, "errorMessage": "Mail server unavailable; will retry"})
            raise _MailServerDown(str(error)) from error

        self._state.markDispatched(kind, referenceId, version, employeeId, "delivered", self._clock())  # Before the API report: no double e-mail
        self._sentThisRun += 1
        summary.itemsSucceeded += 1
        summary.details["emailsSent"] += 1
        self._reportItems.append({**report, "delivered": True})
        self._logger.info("3.3", "EmailSent", f"E-mail sent ({kind} {referenceId} v{version})", itemRef, data={"employeeRef": employeeRef})

    def _refused(self, kind, referenceId, version, employeeId, report, reason, summary, itemRef) -> None:
        # Not retried: HR must fix the address, which creates a new schedule version
        summary.itemsFailed += 1
        summary.details["refusedAddresses"] += 1
        self._state.markDispatched(kind, referenceId, version, employeeId, "refused", self._clock())
        self._reportItems.append({**report, "delivered": False, "errorMessage": "Endereço de e-mail recusado ou ausente; corrija o cadastro"})
        self._logger.error("3.3", "RecipientRefused", f"E-mail not delivered and not retried: {reason}", itemRef, data={"employeeRef": self._ref(employeeId)})

    # ---------- Step 5: report to the API ----------

    def _sendReport(self, summary: RunSummary) -> None:
        if not self._reportItems:
            return
        report = {"runId": self._logger.runId, "items": self._reportItems}
        try:
            self._callApi(lambda: self._api.reportDispatches(report), "5", "Reporting dispatch results")
            self._logger.info("5", "DispatchReported", f"Reported {len(self._reportItems)} delivery result(s) to the API")
        except ApiUnavailableError as error:
            self._state.enqueueOutbox(OUTBOX_KIND, self._logger.runId, report, str(error), self._clock())
            summary.details["reportQueued"] = True
            self._logger.warning("5", "DispatchReportQueued", f"API unavailable; delivery report saved to the outbox (EX06): {error}")
        except ApiRejectedError as error:
            self._logger.error("5", "DispatchReportRejected", f"API refused the delivery report (EX07): {error}", data={"statusCode": error.statusCode})

    def _replayReportOutbox(self) -> None:
        for item in self._state.listOutbox(OUTBOX_KIND):
            try:
                self._api.reportDispatches(item["payload"])
            except ApiUnavailableError as error:
                self._state.recordOutboxFailure(item["outboxId"], str(error))
                self._logger.warning("1", "OutboxStillPending", f"Delivery report from run {item['idempotencyKey']} still pending: {error}")
                return
            except ApiRejectedError as error:
                self._logger.error("1", "OutboxRejected", f"API refused queued delivery report; removed (EX07): {error}")
            else:
                self._logger.info("1", "OutboxDelivered", f"Queued delivery report from run {item['idempotencyKey']} delivered")
            self._state.removeOutbox(item["outboxId"])

    # ---------- Helpers ----------

    def _sequence(self) -> int:
        """iCalendar SEQUENCE: grows with time, so a newer e-mail always wins in the calendar."""
        return int(self._clock().timestamp() // 60)

    def _ref(self, employeeId: str) -> str:
        return buildEmployeeRef(employeeId, self._settings.logSalt)

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
