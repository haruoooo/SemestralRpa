"""Reads the public 'Direto do Metrô' page (there is no official open API for line status)."""

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from src.domain.exceptions import SourceLayoutChangedError, SourceUnavailableError
from src.domain.lineStatus import LineReading, classifyStatus
from src.infrastructure.timeProvider import SAO_PAULO

USER_AGENT = "ForaDoPicoRpa/0.1 (+https://github.com/haruoooo/SemestralRpa; academic project FIAP)"
_UPDATED_AT_PATTERN = re.compile(r"atualizado em (\d{2}/\d{2}/\d{4} \d{2}:\d{2}(?::\d{2})?)")


def parseUpdatedAt(text: str) -> datetime | None:
    match = _UPDATED_AT_PATTERN.search(text or "")
    if not match:
        return None
    value = match.group(1)
    pattern = "%d/%m/%Y %H:%M:%S" if value.count(":") == 2 else "%d/%m/%Y %H:%M"
    return datetime.strptime(value, pattern).replace(tzinfo=SAO_PAULO)


def parseMetroPage(html: str) -> list[LineReading]:
    """Extracts one reading per line. Raises SourceLayoutChangedError if the expected structure is missing (EX10)."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("li.linha")
    if not items:
        raise SourceLayoutChangedError("No 'li.linha' elements found in the Metro page")

    readings = []
    for item in items:
        numberTag = item.select_one(".linha-numero")
        nameTag = item.select_one(".linha-nome")
        statusTag = item.select_one(".linha-situacao")
        if not (numberTag and nameTag and statusTag):
            raise SourceLayoutChangedError("A line item is missing number, name or status")
        try:
            lineNumber = int(numberTag.get_text(strip=True))
        except ValueError as error:
            raise SourceLayoutChangedError(f"Unexpected line number: {numberTag.get_text(strip=True)!r}") from error

        rawText = statusTag.get_text(strip=True)
        infoTag = item.select_one(".linha-info")
        readings.append(
            LineReading(
                lineNumber=lineNumber,
                lineName=nameTag.get_text(strip=True),
                rawText=rawText,
                status=classifyStatus(rawText),
                sourceUpdatedAt=parseUpdatedAt(infoTag.get("title", "")) if infoTag else None,
            )
        )
    return readings


class MetroWebsiteSource:
    sourceName = "metroWebsite"

    def __init__(self, url: str, timeoutSeconds: float, client: httpx.Client | None = None):
        self._url = url
        self._client = client or httpx.Client(timeout=timeoutSeconds, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    def fetchReadings(self) -> list[LineReading]:
        try:
            response = self._client.get(self._url)
        except httpx.HTTPError as error:
            raise SourceUnavailableError(f"Metro page unreachable: {type(error).__name__}") from error
        if response.status_code != 200:
            raise SourceUnavailableError(f"Metro page answered HTTP {response.status_code}")
        return parseMetroPage(response.content.decode("utf-8", errors="replace"))
