"""Etapa 07 — success, decision and failure scenarios of agendaDispatchFlow (fake API and fake mail server)."""

import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from icalendar import Calendar

from src.adapters.outbound.emailNotifiers import ConsoleNotifier, buildMimeMessage, maskEmail
from src.adapters.outbound.icalendarCalendar import IcalendarCalendar
from src.adapters.outbound.sqliteRobotState import SqliteRobotState
from src.application.flows.agendaDispatchFlow import AgendaDispatchFlow
from src.application.runSummary import RunStatus
from src.domain.agenda import OutgoingEmail
from src.domain.exceptions import ApiUnavailableError, NotificationRejectedError, NotificationUnavailableError
from src.infrastructure.robotLogger import RunLogger, buildEmployeeRef
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import SAO_PAULO

NOW = datetime(2026, 11, 24, 7, 40, tzinfo=SAO_PAULO)  # Tuesday of week 2026-W48
WINDOWS = ["07:00", "08:00", "09:30", "10:30"]
PEOPLE = [("F1001", "Ana Ribeiro"), ("F1002", "Bruno Matos"), ("F1003", "Carla Nunes")]


def assignment(employeeId: str, name: str, day: str, window: str = "10:30") -> dict:
    return {
        "assignmentId": f"as-sch1-{employeeId}-{day}", "employeeId": employeeId, "name": name,
        "email": f"{name.split()[0].lower()}@empresaficticia.example", "teamName": "Financeiro", "lineNumber": 3,
        "boardingStation": "Tatuapé", "date": day, "entryWindow": window, "allowedEntryWindows": WINDOWS,
        "suggestedDepartureTime": "09:35", "predictedCrowding": "moderate",
    }


def schedule(version: int = 1, status: str = "approved") -> dict:
    days = ["2026-11-24", "2026-11-26"]
    return {
        "scheduleId": "sch1", "version": version, "week": "2026-W48", "status": status,
        "assignments": [assignment(employeeId, name, day) for employeeId, name in PEOPLE for day in days],
    }


def plan(action: str = "remoteWork", newWindow: str | None = None, embedAffected: bool = True) -> dict:
    affected = [assignment("F1001", "Ana Ribeiro", "2026-11-24", "08:00")]
    item = {
        "planId": "plan1", "alertId": "alert1", "date": "2026-11-24", "teamName": "Financeiro", "action": action,
        "assignmentIds": [affected[0]["assignmentId"]], "reason": "Linha 3-Vermelha com problemas. Sugestão: trabalho remoto hoje.",
        "status": "approved", "affected": affected if embedAffected else [],
    }
    if newWindow:
        item["newEntryWindow"] = newWindow
    return item


class FakeApi:
    def __init__(self, schedules=None, plans=None, assignments=None):
        self.schedules = schedules or []
        self.plans = plans or []
        self.assignments = assignments or []
        self.reports: list[dict] = []
        self.listingDown = False
        self.reportDown = False

    def listSchedules(self, status, dispatched=None):
        if self.listingDown:
            raise ApiUnavailableError("Connection refused")
        return [item for item in self.schedules if item["status"] == status]

    def listContingencyPlans(self, status, dispatched=None):
        return [item for item in self.plans if item["status"] == status]

    def listAssignments(self, date, lineNumber=None):
        from src.domain.assignment import Assignment

        return [Assignment.fromApi(item) for item in self.assignments if item["date"] == date]

    def reportDispatches(self, report):
        if self.reportDown:
            raise ApiUnavailableError("Connection refused")
        self.reports.append(report)


class FakeNotifier:
    channel = "email"

    def __init__(self):
        self.sent: list[OutgoingEmail] = []
        self.down = False
        self.refuse: set[str] = set()
        self.attempts = 0

    def send(self, email):
        self.attempts += 1
        if self.down:
            raise NotificationUnavailableError("SMTP unreachable: ConnectionRefusedError")
        if email.to in self.refuse:
            raise NotificationRejectedError("Recipient refused by the mail server")
        self.sent.append(email)


@pytest.fixture
def state():
    return SqliteRobotState(Path(":memory:"))


@pytest.fixture
def settings(tmp_path):
    return replace(Settings(), retryBaseSeconds=0, logSalt="test", logDir=tmp_path)


def runFlow(api, notifier, state, settings, records=None):
    baseLogger = logging.getLogger(f"testAgendaDispatch{id(api)}{id(notifier)}{len(records or [])}")
    baseLogger.setLevel(logging.INFO)
    baseLogger.propagate = False
    collector = logging.Handler()
    collector.emit = (records if records is not None else []).append
    baseLogger.handlers = [collector]
    logger = RunLogger("agendaDispatchFlow", "ad-test", baseLogger=baseLogger)
    return AgendaDispatchFlow(api, notifier, IcalendarCalendar("ForaDoPico <agenda@foradopico.example>"), state, settings, logger, clock=lambda: NOW).run()


def events(email: OutgoingEmail) -> list:
    calendar = Calendar.from_ical(email.attachments[0].content)
    return calendar, [component for component in calendar.walk("VEVENT")]


# ---------- Success ----------


def testApprovedScheduleSendsOneEmailPerEmployeeWithIcs(state, settings):
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    summary = runFlow(api, notifier, state, settings)

    assert summary.status == RunStatus.SUCCESS and summary.details["emailsSent"] == 3
    first = notifier.sent[0]
    assert first.to == "ana@empresaficticia.example"
    assert first.subject.startswith("Sua agenda presencial: Terça, 24/11 a Quinta, 26/11")
    assert "Olá, Ana!" in first.textBody and "saia de casa às 09:35" in first.textBody
    calendar, vevents = events(first)
    assert str(calendar["method"]) == "REQUEST" and len(vevents) == 2
    assert vevents[0]["uid"] == "as-sch1-F1001-2026-11-24@foradopico"
    assert vevents[0].decoded("dtstart") == datetime(2026, 11, 24, 10, 30, tzinfo=SAO_PAULO)
    assert len(list(vevents[0].walk("VALARM"))) == 1
    [report] = api.reports
    assert [item["delivered"] for item in report["items"]] == [True, True, True]
    assert report["items"][0] == {"kind": "schedule", "referenceId": "sch1", "version": 1, "employeeId": "F1001", "channel": "email", "delivered": True}


def testRemotePlanCancelsTheCalendarEvent(state, settings):
    api, notifier = FakeApi(plans=[plan("remoteWork")]), FakeNotifier()
    runFlow(api, notifier, state, settings)

    [email] = notifier.sent
    assert email.subject == "Hoje: seu dia presencial virou remoto · ForaDoPico"
    calendar, [event] = events(email)
    assert str(calendar["method"]) == "CANCEL" and str(event["status"]) == "CANCELLED"
    assert event["uid"] == "as-sch1-F1001-2026-11-24@foradopico"  # Same event the weekly agenda created


def testShiftPlanMovesTheEntryWindow(state, settings):
    api, notifier = FakeApi(plans=[plan("shiftEntryWindow", "10:30")]), FakeNotifier()
    runFlow(api, notifier, state, settings)

    [email] = notifier.sent
    assert email.subject == "Hoje: sua entrada mudou para 10:30 · ForaDoPico"
    assert "mudou de 08:00 para 10:30" in email.textBody
    _, [event] = events(email)
    assert event.decoded("dtstart") == datetime(2026, 11, 24, 10, 30, tzinfo=SAO_PAULO)


def testPlanWithoutEmbeddedAssignmentsLooksThemUp(state, settings):
    api = FakeApi(plans=[plan(embedAffected=False)], assignments=[assignment("F1001", "Ana Ribeiro", "2026-11-24", "08:00")])
    notifier = FakeNotifier()
    runFlow(api, notifier, state, settings)
    assert len(notifier.sent) == 1


# ---------- Decision ----------


def testSameVersionIsNotSentTwice(state, settings):  # RN11
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    runFlow(api, notifier, state, settings)
    second = runFlow(api, notifier, state, settings)

    assert len(notifier.sent) == 3
    assert second.itemsSkipped == 3 and second.details["emailsSent"] == 0


def testNewVersionIsSentAgainAsUpdate(state, settings):  # RN11
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    runFlow(api, notifier, state, settings)
    api.schedules = [schedule(version=2)]
    runFlow(api, notifier, state, settings)

    assert len(notifier.sent) == 6
    assert notifier.sent[-1].subject.startswith("Agenda atualizada")


def testScheduleNotApprovedIsNeverSent(state, settings):  # RN10
    api = FakeApi(schedules=[schedule(status="pendingApproval")])
    api.listSchedules = lambda status, dispatched=None: api.schedules  # A buggy API that ignores the filter
    notifier = FakeNotifier()
    runFlow(api, notifier, state, settings)
    assert notifier.sent == []


def testPerRunLimitLeavesTheRestForNextRun(state, settings):
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    limited = replace(settings, dispatchLimitPerRun=2)
    first = runFlow(api, notifier, state, limited)
    assert len(notifier.sent) == 2 and first.details["stoppedEarly"] == "dispatchLimitReached"
    runFlow(api, notifier, state, limited)
    assert len(notifier.sent) == 3


# ---------- Failure ----------


def testMailServerDownStopsAndRetriesNextRun(state, settings):  # EX08
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    notifier.down = True
    first = runFlow(api, notifier, state, settings)

    assert first.status == RunStatus.PARTIAL and first.details["stoppedEarly"] == "mailServerUnavailable"
    assert notifier.attempts == 3  # 3 attempts, then stops instead of hammering a dead server
    assert api.reports[0]["items"] == [{"kind": "schedule", "referenceId": "sch1", "version": 1, "employeeId": "F1001", "channel": "email", "delivered": False, "errorMessage": "Mail server unavailable; will retry"}]

    notifier.down = False
    second = runFlow(api, notifier, state, settings)
    assert second.status == RunStatus.SUCCESS and len(notifier.sent) == 3


def testRefusedAddressIsReportedAndNotRetried(state, settings):
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    notifier.refuse = {"bruno@empresaficticia.example"}
    first = runFlow(api, notifier, state, settings)
    assert first.status == RunStatus.PARTIAL and first.details["refusedAddresses"] == 1
    assert len(notifier.sent) == 2

    attemptsBefore = notifier.attempts
    runFlow(api, notifier, state, settings)
    assert notifier.attempts == attemptsBefore  # HR must fix the address (new version)


def testApiDownWhenListingSendsNothing(state, settings):  # EX06
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    api.listingDown = True
    summary = runFlow(api, notifier, state, settings)
    assert summary.status == RunStatus.PARTIAL and notifier.sent == []


def testDeliveryReportGoesToOutboxAndIsReplayed(state, settings):  # EX06
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    api.reportDown = True
    first = runFlow(api, notifier, state, settings)
    assert first.details["reportQueued"] and first.status == RunStatus.PARTIAL
    assert len(notifier.sent) == 3  # E-mails were not held back by the API

    api.reportDown = False
    runFlow(api, notifier, state, settings)
    assert len(api.reports) == 1 and len(api.reports[0]["items"]) == 3
    assert state.listOutbox("dispatchReport") == []


# ---------- LGPD and adapters ----------


def testLogsHaveNoNamesOrEmails(state, settings):
    records: list = []
    api, notifier = FakeApi(schedules=[schedule()], plans=[plan()]), FakeNotifier()
    runFlow(api, notifier, state, settings, records)
    text = " ".join(f"{record.getMessage()} {getattr(record, 'data', '')}" for record in records)
    for employeeId, name in PEOPLE:
        assert name not in text and name.split()[0].lower() + "@" not in text
    assert buildEmployeeRef("F1001", "test") in text
    assert all(record.getMessage()[0].isupper() for record in records)


def testConsoleNotifierSavesEmlWithAttachment(tmp_path, capsys):
    notifier = ConsoleNotifier(tmp_path, "ForaDoPico <agenda@foradopico.example>")
    email = OutgoingEmail("ana@empresaficticia.example", "Assunto", "Texto", "<p>Texto</p>")
    notifier.send(email)
    [saved] = list(tmp_path.glob("*.eml"))
    assert b"Subject: Assunto" in saved.read_bytes()
    assert "a***@empresaficticia.example" in capsys.readouterr().out


def testMimeMessageCarriesIcsAttachment(state, settings):
    api, notifier = FakeApi(schedules=[schedule()]), FakeNotifier()
    runFlow(api, notifier, state, settings)
    message = buildMimeMessage(notifier.sent[0], "ForaDoPico <agenda@foradopico.example>")
    [attachment] = list(message.iter_attachments())
    assert attachment.get_filename() == "agenda.ics" and attachment.get_content_type() == "text/calendar"
    assert attachment.get_param("charset") == "utf-8" and attachment.get_param("method") == "REQUEST"
    assert "Dia presencial · entrada às 10:30" in attachment.get_content()
    assert maskEmail("ana@x.example") == "a***@x.example"


@pytest.mark.parametrize(
    "subject",
    [
        "Sua agenda presencial: Segunda, 23/11 a Quarta, 25/11 · ForaDoPico",
        "Agenda atualizada: Terça, 24/11 a Sexta, 27/11 · ForaDoPico · com acentuação e um assunto bem comprido",
    ],
)
def testSubjectWithAccentsSurvivesEncoding(subject):
    from email import message_from_bytes, policy

    raw = bytes(buildMimeMessage(OutgoingEmail("ana@x.example", subject, "Texto", "<p>Texto</p>"), "ForaDoPico <agenda@foradopico.example>"))
    assert b"?q??=" not in raw  # Broken empty encoded-word seen in Mailtrap
    assert message_from_bytes(raw, policy=policy.default)["Subject"] == subject
