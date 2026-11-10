"""Demo source: reads line statuses from a JSON scenario file so the video can show plan B on demand."""

import json
from pathlib import Path

from src.domain.exceptions import SourceLayoutChangedError, SourceUnavailableError
from src.domain.lineStatus import LineReading, classifyStatus

DEFAULT_SCENARIO = {
    "available": True,
    "lines": [
        {"lineNumber": 1, "lineName": "Azul", "rawText": "Operação Normal"},
        {"lineNumber": 2, "lineName": "Verde", "rawText": "Operação Normal"},
        {"lineNumber": 3, "lineName": "Vermelha", "rawText": "Operação Normal"},
    ],
}


def writeScenario(path: Path, lineNumber: int, rawText: str, available: bool = True) -> dict:
    """Changes one line (or the source availability) in the scenario file. Used by the 'simulate' CLI command."""
    scenario = json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(json.dumps(DEFAULT_SCENARIO))
    scenario["available"] = available
    for line in scenario["lines"]:
        if line["lineNumber"] == lineNumber:
            line["rawText"] = rawText
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8")
    return scenario


class SimulatedSource:
    sourceName = "simulated"

    def __init__(self, scenarioPath: Path):
        self._scenarioPath = scenarioPath

    def fetchReadings(self) -> list[LineReading]:
        if not self._scenarioPath.exists():
            writeScenario(self._scenarioPath, 1, "Operação Normal")
        try:
            scenario = json.loads(self._scenarioPath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SourceLayoutChangedError("Simulated scenario file is not valid JSON") from error
        if not scenario.get("available", True):
            raise SourceUnavailableError("Simulated source marked as unavailable")
        return [
            LineReading(
                lineNumber=line["lineNumber"],
                lineName=line["lineName"],
                rawText=line["rawText"],
                status=classifyStatus(line["rawText"]),
            )
            for line in scenario["lines"]
        ]
