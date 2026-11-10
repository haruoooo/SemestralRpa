from pathlib import Path

import httpx
import pytest

from src.adapters.inbound.metroWebsiteSource import MetroWebsiteSource, parseMetroPage
from src.domain.exceptions import SourceLayoutChangedError, SourceUnavailableError
from src.domain.lineStatus import LineStatusCode

SAMPLE = Path(__file__).parent / "fixtures" / "metroDiretoSample.html"


def testParsesRealPageSample():
    readings = parseMetroPage(SAMPLE.read_text(encoding="utf-8"))
    byNumber = {reading.lineNumber: reading for reading in readings}
    assert set(byNumber) == {1, 2, 3, 4, 5, 15, 17}
    assert byNumber[3].lineName == "Vermelha"
    assert byNumber[3].status == LineStatusCode.NORMAL
    assert byNumber[3].sourceUpdatedAt is not None
    assert byNumber[17].status == LineStatusCode.UNKNOWN  # "Operação Transitória"


def testLayoutChangeIsDetected():
    with pytest.raises(SourceLayoutChangedError):
        parseMetroPage("<html><body><p>Novo site</p></body></html>")


def _sourceWith(handler) -> MetroWebsiteSource:
    return MetroWebsiteSource("https://example.test/status", 5, client=httpx.Client(transport=httpx.MockTransport(handler)))


def testBlockedSourceRaisesUnavailable():
    with pytest.raises(SourceUnavailableError):
        _sourceWith(lambda request: httpx.Response(403)).fetchReadings()


def testTimeoutRaisesUnavailable():
    def raiseTimeout(request):
        raise httpx.ConnectTimeout("Timeout", request=request)

    with pytest.raises(SourceUnavailableError):
        _sourceWith(raiseTimeout).fetchReadings()
