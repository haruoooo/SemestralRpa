from datetime import datetime, time, timedelta

import pytest

from src.domain.lineStatus import (
    ContingencyAction,
    LineStatusCode,
    classifyStatus,
    decideContingency,
    isStale,
    isWindowStillAhead,
    isWithinOperatingWindow,
    nextEntryWindow,
)
from src.infrastructure.timeProvider import SAO_PAULO

WINDOWS = ["07:00", "08:00", "09:30", "10:30"]


@pytest.mark.parametrize(
    ("rawText", "expected"),
    [
        ("Operação Normal", LineStatusCode.NORMAL),
        ("OPERACAO NORMAL", LineStatusCode.NORMAL),
        ("Velocidade Reduzida", LineStatusCode.DEGRADED),
        ("Operação Parcial", LineStatusCode.DEGRADED),
        ("Paralisada", LineStatusCode.STOPPED),
        ("Operação Encerrada", LineStatusCode.CLOSED),
        ("Operação Transitória", LineStatusCode.UNKNOWN),
        ("", LineStatusCode.UNKNOWN),
    ],
)
def testClassifyStatusFollowsRn12(rawText, expected):
    assert classifyStatus(rawText) == expected


def testNextEntryWindowReturnsFirstLaterWindow():
    assert nextEntryWindow("08:00", WINDOWS) == "09:30"
    assert nextEntryWindow("10:30", WINDOWS) is None


def testStoppedLineSuggestsRemoteWork():
    assert decideContingency(LineStatusCode.STOPPED, "08:00", WINDOWS) == (ContingencyAction.REMOTE_WORK, None)


def testDegradedLineSuggestsLaterWindow():
    assert decideContingency(LineStatusCode.DEGRADED, "08:00", WINDOWS) == (ContingencyAction.SHIFT_ENTRY_WINDOW, "09:30")


def testDegradedLineWithoutLaterWindowFallsBackToRemote():
    assert decideContingency(LineStatusCode.DEGRADED, "10:30", WINDOWS) == (ContingencyAction.REMOTE_WORK, None)


def testWindowAlreadyPassedIsNotAffected():
    now = datetime(2026, 11, 10, 8, 15, tzinfo=SAO_PAULO)
    assert not isWindowStillAhead("08:00", now)
    assert isWindowStillAhead("09:30", now)


def testStaleAfterLimit():
    now = datetime(2026, 11, 10, 8, 0, tzinfo=SAO_PAULO)
    assert not isStale(now - timedelta(minutes=10), now, 30)
    assert isStale(now - timedelta(minutes=31), now, 30)
    assert isStale(None, now, 30)


def testOperatingWindowOnlyOnWeekdays():
    tuesday = datetime(2026, 11, 10, 7, 0, tzinfo=SAO_PAULO)
    saturday = datetime(2026, 11, 14, 7, 0, tzinfo=SAO_PAULO)
    assert isWithinOperatingWindow(tuesday, time(5), time(22))
    assert not isWithinOperatingWindow(saturday, time(5), time(22))
    assert not isWithinOperatingWindow(tuesday.replace(hour=23), time(5), time(22))
