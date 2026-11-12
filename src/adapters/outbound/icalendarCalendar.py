"""Builds .ics files with the icalendar library (RFC 5545), readable by Google Calendar, Outlook and phones.

Every event uses the assignmentId as UID: a plan B e-mail cancels or moves the same event that the
weekly agenda created, instead of adding a duplicate to the employee's calendar.
"""

from datetime import date, datetime, timedelta
from email.utils import parseaddr

from icalendar import Alarm, Calendar, Event, vCalAddress, vText

from src.domain.agenda import lineLabel
from src.domain.assignment import Assignment
from src.infrastructure.timeProvider import SAO_PAULO, nowLocal

WORKDAY_HOURS = 8
ALARM_MINUTES_BEFORE_DEPARTURE = 15
_CROWDING = {"empty": "vazio", "moderate": "moderada", "full": "cheio", "critical": "crítica"}


class IcalendarCalendar:
    def __init__(self, organizer: str):
        name, address = parseaddr(organizer)
        self._organizer = vCalAddress(f"mailto:{address or 'agenda@foradopico.example'}")
        self._organizer.params["cn"] = vText(name or "ForaDoPico")

    def buildAgenda(self, assignments: list[Assignment], sequence: int) -> bytes:
        calendar = self._calendar("REQUEST")
        for item in assignments:
            calendar.add_component(self._event(item, item.entryWindow, sequence))
        return self._finish(calendar)

    def buildRemoteWork(self, assignment: Assignment, sequence: int) -> bytes:
        calendar = self._calendar("CANCEL")
        event = self._event(assignment, assignment.entryWindow, sequence, withAlarm=False)
        event["status"] = "CANCELLED"
        event["summary"] = "Dia presencial cancelado: trabalho remoto"
        calendar.add_component(event)
        return self._finish(calendar)

    def buildShiftedEntry(self, assignment: Assignment, newEntryWindow: str, sequence: int) -> bytes:
        calendar = self._calendar("REQUEST")
        calendar.add_component(self._event(assignment, newEntryWindow, sequence, withAlarm=False))
        return self._finish(calendar)

    # ---------- Helpers ----------

    def _calendar(self, method: str) -> Calendar:
        calendar = Calendar()
        calendar.add("prodid", "-//ForaDoPico//RPA agendaDispatchFlow//PT-BR")
        calendar.add("version", "2.0")
        calendar.add("method", method)
        return calendar

    def _event(self, item: Assignment, entryWindow: str, sequence: int, withAlarm: bool = True) -> Event:
        start = _at(item.date, entryWindow)
        event = Event()
        event.add("uid", f"{item.assignmentId}@foradopico")
        event.add("sequence", sequence)
        event.add("dtstamp", nowLocal())
        event.add("dtstart", start)
        event.add("dtend", start + timedelta(hours=WORKDAY_HOURS))
        event.add("summary", f"Dia presencial · entrada às {entryWindow}")
        if item.boardingStation:
            event.add("location", f"Embarque: {item.boardingStation} ({lineLabel(item.lineNumber)})")
        event.add("description", _description(item, entryWindow))
        event.add("organizer", self._organizer)
        if item.email:
            attendee = vCalAddress(f"mailto:{item.email}")
            attendee.params["cn"] = vText(item.name or item.email)
            event.add("attendee", attendee)
        if withAlarm and item.suggestedDepartureTime:
            departure = _at(item.date, item.suggestedDepartureTime)
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"Hora de sair para o trabalho ({item.suggestedDepartureTime})")
            alarm.add("trigger", departure - timedelta(minutes=ALARM_MINUTES_BEFORE_DEPARTURE) - start)
            event.add_component(alarm)
        return event

    @staticmethod
    def _finish(calendar: Calendar) -> bytes:
        calendar.add_missing_timezones()
        return calendar.to_ical()


def _at(isoDate: str, window: str) -> datetime:
    hours, minutes = window.split(":")
    return datetime.combine(date.fromisoformat(isoDate), datetime.min.time(), tzinfo=SAO_PAULO).replace(hour=int(hours), minute=int(minutes))


def _description(item: Assignment, entryWindow: str) -> str:
    lines = [f"Entrada às {entryWindow}."]
    if item.suggestedDepartureTime and entryWindow == item.entryWindow:
        lines.append(f"Saia de casa às {item.suggestedDepartureTime}.")
    if item.predictedCrowding in _CROWDING and entryWindow == item.entryWindow:
        lines.append(f"Lotação prevista no seu trajeto: {_CROWDING[item.predictedCrowding]}.")
    lines.append("Agenda gerada pelo ForaDoPico.")
    return " ".join(lines)
