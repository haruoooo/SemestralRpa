"""Agenda dispatch rules and e-mail texts (docs/processDesign.md, section 4, RN10-RN11).

Texts are in Portuguese because they go to the employee.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from html import escape

from src.domain.assignment import Assignment
from src.domain.lineStatus import LINE_DISPLAY_NAMES

KIND_SCHEDULE = "schedule"
KIND_CONTINGENCY_PLAN = "contingencyPlan"
PLAN_VERSION = 1  # A plan B never changes after approval; a new decision is a new plan

_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
_CROWDING = {"empty": "vazio", "moderate": "moderada", "full": "cheio", "critical": "crítica"}


@dataclass(frozen=True)
class Schedule:
    scheduleId: str
    version: int
    week: str
    status: str
    assignments: list[Assignment] = field(default_factory=list)

    @classmethod
    def fromApi(cls, payload: dict) -> "Schedule":
        return cls(
            scheduleId=payload["scheduleId"],
            version=int(payload.get("version", 1)),
            week=payload.get("week", ""),
            status=payload["status"],
            assignments=[Assignment.fromApi(item) for item in payload.get("assignments", [])],
        )


@dataclass(frozen=True)
class ContingencyPlan:
    planId: str
    date: str
    teamName: str
    action: str
    reason: str
    status: str
    assignmentIds: list[str] = field(default_factory=list)
    newEntryWindow: str | None = None
    affected: list[Assignment] = field(default_factory=list)

    @classmethod
    def fromApi(cls, payload: dict) -> "ContingencyPlan":
        return cls(
            planId=payload["planId"],
            date=payload["date"],
            teamName=payload.get("teamName", ""),
            action=payload["action"],
            reason=payload.get("reason", ""),
            status=payload["status"],
            assignmentIds=list(payload.get("assignmentIds", [])),
            newEntryWindow=payload.get("newEntryWindow"),
            affected=[Assignment.fromApi(item) for item in payload.get("affected", [])],
        )


@dataclass(frozen=True)
class EmailAttachment:
    fileName: str
    content: bytes
    mimeType: str


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    textBody: str
    htmlBody: str
    attachments: tuple[EmailAttachment, ...] = ()


def isApproved(status: str) -> bool:  # RN10
    return status == "approved"


def groupByEmployee(assignments: list[Assignment]) -> dict[str, list[Assignment]]:
    groups: dict[str, list[Assignment]] = defaultdict(list)
    for item in assignments:
        groups[item.employeeId].append(item)
    return {employeeId: sorted(items, key=lambda item: (item.date, item.entryWindow)) for employeeId, items in groups.items()}


def greeting(fullName: str) -> str:
    return f"Olá, {fullName.split()[0]}!" if fullName.strip() else "Olá!"


def formatDay(isoDate: str) -> str:
    day = date.fromisoformat(isoDate)
    return f"{_WEEKDAYS[day.weekday()].capitalize()}, {day:%d/%m}"


def lineLabel(lineNumber: int) -> str:
    return LINE_DISPLAY_NAMES.get(lineNumber, f"Linha {lineNumber}")


def describeDay(item: Assignment) -> str:
    parts = [f"{formatDay(item.date)} · entrada às {item.entryWindow}"]
    if item.suggestedDepartureTime:
        parts.append(f"saia de casa às {item.suggestedDepartureTime}")
    if item.boardingStation:
        parts.append(f"embarque em {item.boardingStation} ({lineLabel(item.lineNumber)})")
    if item.predictedCrowding in _CROWDING:
        parts.append(f"lotação prevista {_CROWDING[item.predictedCrowding]}")
    return " · ".join(parts)


_FOOTER = "Mensagem automática do ForaDoPico. Em caso de dúvida, fale com o RH da sua empresa."


def buildScheduleEmail(items: list[Assignment], schedule: Schedule) -> tuple[str, str, str]:
    """Subject, plain text and HTML of the weekly agenda e-mail."""
    person = items[0]
    first, last = formatDay(items[0].date), formatDay(items[-1].date)
    updated = schedule.version > 1
    subject = f"{'Agenda atualizada' if updated else 'Sua agenda presencial'}: {first} a {last} · ForaDoPico" if len(items) > 1 else (
        f"{'Agenda atualizada' if updated else 'Sua agenda presencial'}: {first} · ForaDoPico"
    )
    intro = (
        "O RH atualizou a sua escala presencial. Esta versão substitui a anterior."
        if updated else "O RH aprovou a sua escala presencial da semana, montada para você fugir do pico do metrô."
    )
    days = [describeDay(item) for item in items]
    text = "\n".join(
        [greeting(person.name), "", intro, "", "Seus dias presenciais:", *[f"- {day}" for day in days], "",
         "O arquivo agenda.ics em anexo coloca esses dias no seu calendário (Google, Outlook ou celular).", "", _FOOTER]
    )
    html = (
        f"<p>{escape(greeting(person.name))}</p><p>{escape(intro)}</p><p><strong>Seus dias presenciais:</strong></p>"
        f"<ul>{''.join(f'<li>{escape(day)}</li>' for day in days)}</ul>"
        "<p>O arquivo <em>agenda.ics</em> em anexo coloca esses dias no seu calendário (Google, Outlook ou celular).</p>"
        f"<p style='color:#666;font-size:12px'>{escape(_FOOTER)}</p>"
    )
    return subject, text, html


def buildPlanEmail(item: Assignment, plan: ContingencyPlan, today: date) -> tuple[str, str, str]:
    """Subject, plain text and HTML of the plan B notice (remote work or later entry)."""
    when = "hoje" if plan.date == today.isoformat() else f"em {formatDay(plan.date).lower()}"
    whenTitle = "Hoje" if plan.date == today.isoformat() else formatDay(plan.date)
    if plan.action == "remoteWork":
        subject = f"{whenTitle}: seu dia presencial virou remoto · ForaDoPico"
        change = f"Seu dia presencial {when} virou trabalho remoto. Não é preciso ir ao escritório."
    else:
        subject = f"{whenTitle}: sua entrada mudou para {plan.newEntryWindow} · ForaDoPico"
        change = f"Sua entrada {when} mudou de {item.entryWindow} para {plan.newEntryWindow}, para você fugir do trecho com problema."
    lines = [greeting(item.name), "", change, f"Motivo: {plan.reason}", "",
             "O RH aprovou esta mudança. O anexo agenda.ics atualiza o seu calendário.", "", _FOOTER]
    html = (
        f"<p>{escape(greeting(item.name))}</p><p><strong>{escape(change)}</strong></p><p>Motivo: {escape(plan.reason)}</p>"
        "<p>O RH aprovou esta mudança. O anexo <em>agenda.ics</em> atualiza o seu calendário.</p>"
        f"<p style='color:#666;font-size:12px'>{escape(_FOOTER)}</p>"
    )
    return subject, "\n".join(lines), html
