"""Line status entities and business rules RN12, RN13, RN14, RN16 and RN17 (see docs/processDesign.md)."""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum


class LineStatusCode(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class ContingencyAction(StrEnum):
    REMOTE_WORK = "remoteWork"
    SHIFT_ENTRY_WINDOW = "shiftEntryWindow"


@dataclass(frozen=True)
class LineReading:
    lineNumber: int
    lineName: str
    rawText: str
    status: LineStatusCode
    sourceUpdatedAt: datetime | None = None


def normalizeText(text: str) -> str:
    """Lowercase and strip accents so the classification does not depend on encoding details."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower().strip()


# RN12: keyword -> status. Order matters: the first match wins.
_STATUS_KEYWORDS: list[tuple[str, LineStatusCode]] = [
    ("paralisad", LineStatusCode.STOPPED),
    ("interrompid", LineStatusCode.STOPPED),
    ("velocidade reduzida", LineStatusCode.DEGRADED),
    ("operacao parcial", LineStatusCode.DEGRADED),
    ("encerrad", LineStatusCode.CLOSED),
    ("operacao normal", LineStatusCode.NORMAL),
    ("situacao normal", LineStatusCode.NORMAL),
]


def classifyStatus(rawText: str) -> LineStatusCode:
    """RN12: maps the text published by the operator to a status code. Unknown texts never trigger plan B."""
    normalized = normalizeText(rawText)
    for keyword, status in _STATUS_KEYWORDS:
        if keyword in normalized:
            return status
    return LineStatusCode.UNKNOWN


def requiresContingency(status: LineStatusCode) -> bool:
    """RN12/RN14: only degraded and stopped lines generate a plan B proposal."""
    return status in (LineStatusCode.DEGRADED, LineStatusCode.STOPPED)


def hasStatusChanged(previous: LineStatusCode | None, current: LineStatusCode) -> bool:
    """RN13: an alert is created only when the status differs from the last reading."""
    return previous != current


def buildDedupeKey(lineNumber: int, status: LineStatusCode, day: datetime) -> str:
    return f"line{lineNumber}-{status.value}-{day.date().isoformat()}"


def nextEntryWindow(currentWindow: str, allowedWindows: list[str]) -> str | None:
    """RN14: the next allowed entry window later than the current one, or None if there is none."""
    later = sorted(window for window in allowedWindows if window > currentWindow)
    return later[0] if later else None


def decideContingency(
    status: LineStatusCode, currentWindow: str, allowedWindows: list[str]
) -> tuple[ContingencyAction, str | None]:
    """RN14: stopped -> remote work; degraded -> next later window (remote work if there is no later window)."""
    if status == LineStatusCode.DEGRADED:
        laterWindow = nextEntryWindow(currentWindow, allowedWindows)
        if laterWindow:
            return ContingencyAction.SHIFT_ENTRY_WINDOW, laterWindow
    return ContingencyAction.REMOTE_WORK, None


def isWindowStillAhead(entryWindow: str, now: datetime) -> bool:
    """RN14: employees whose entry window already passed are not affected anymore."""
    return entryWindow > now.strftime("%H:%M")


def isStale(lastSuccessAt: datetime | None, now: datetime, staleAfterMinutes: int) -> bool:
    """RN16: data is stale when the last successful reading is older than the limit (or never happened)."""
    if lastSuccessAt is None:
        return True
    return now - lastSuccessAt > timedelta(minutes=staleAfterMinutes)


def isWithinOperatingWindow(now: datetime, start: time, end: time) -> bool:
    """RN17: the monitor runs only on weekdays inside the configured window."""
    isWeekday = now.weekday() < 5
    return isWeekday and start <= now.time() <= end


LINE_DISPLAY_NAMES = {
    1: "Linha 1-Azul",
    2: "Linha 2-Verde",
    3: "Linha 3-Vermelha",
    4: "Linha 4-Amarela",
    5: "Linha 5-Lilás",
    15: "Linha 15-Prata",
    17: "Linha 17-Ouro",
}

_STATUS_MESSAGES = {
    LineStatusCode.NORMAL: "operando normalmente",
    LineStatusCode.DEGRADED: "com velocidade reduzida ou operação parcial",
    LineStatusCode.STOPPED: "paralisada",
    LineStatusCode.CLOSED: "com operação encerrada",
    LineStatusCode.UNKNOWN: "em situação não identificada",
}


def buildAlertMessage(lineNumber: int, status: LineStatusCode, detectedAt: datetime) -> str:
    """User-facing text (Portuguese) shown on the Alertas screen."""
    lineName = LINE_DISPLAY_NAMES.get(lineNumber, f"Linha {lineNumber}")
    return f"{lineName} {_STATUS_MESSAGES[status]} desde {detectedAt.strftime('%H:%M')}."


def buildContingencyReason(lineNumber: int, action: ContingencyAction, newWindow: str | None) -> str:
    """User-facing text (Portuguese) shown to HR when approving the plan B."""
    lineName = LINE_DISPLAY_NAMES.get(lineNumber, f"Linha {lineNumber}")
    if action == ContingencyAction.SHIFT_ENTRY_WINDOW:
        return f"{lineName} com problemas. Sugestão: entrada às {newWindow} hoje."
    return f"{lineName} com problemas. Sugestão: trabalho remoto hoje."
