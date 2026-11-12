"""Contingency integration: writes the same payloads as structured JSON files (allowed by etapa 06)."""

import json
from pathlib import Path
from uuid import uuid4

from src.domain.assignment import Assignment
from src.infrastructure.timeProvider import nowLocal


class FileProductApi:
    def __init__(self, outputDir: Path, assignmentsFixture: Path | None = None):
        self._outputDir = outputDir
        self._assignmentsFixture = assignmentsFixture

    def _write(self, resource: str, payload: dict) -> Path:
        folder = self._outputDir / resource
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{resource}{nowLocal().strftime('%Y%m%d%H%M%S')}{uuid4().hex[:6]}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def submitScheduleImport(self, payload: dict, idempotencyKey: str) -> dict:
        marker = self._outputDir / "scheduleImports" / f"import{idempotencyKey[:16]}.json"
        if marker.exists():  # Same idempotency semantics as the API
            return json.loads(marker.read_text(encoding="utf-8"))["result"]
        result = {
            "importId": f"imp-{uuid4().hex[:8]}",
            "scheduleId": f"sch-{uuid4().hex[:8]}",
            "status": "pendingApproval",
            "receivedEmployees": len(payload.get("employees", [])),
        }
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"idempotencyKey": idempotencyKey, "result": result, "payload": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    def publishLineStatus(self, snapshot: dict) -> None:
        self._write("lineStatus", snapshot)

    def createAlert(self, alert: dict) -> dict:
        created = {**alert, "alertId": f"alert-{uuid4().hex[:8]}"}
        self._write("alerts", created)
        return created

    def listAssignments(self, date: str, lineNumber: int | None = None) -> list[Assignment]:
        if not self._assignmentsFixture or not self._assignmentsFixture.exists():
            return []
        items = json.loads(self._assignmentsFixture.read_text(encoding="utf-8"))
        return [
            Assignment.fromApi(item)
            for item in items
            if item["date"] == date and (lineNumber is None or item["lineNumber"] == lineNumber)
        ]

    def createContingencyPlan(self, plan: dict) -> dict:
        created = {**plan, "planId": f"plan-{uuid4().hex[:8]}", "status": "pendingApproval"}
        self._write("contingencyPlans", created)
        return created

    # Contingency mode has no HR approval screen: approved items come from fixture files, if present
    def listSchedules(self, status: str, dispatched: bool | None = None) -> list[dict]:
        return self._readApproved("approvedSchedules.json", status)

    def listContingencyPlans(self, status: str, dispatched: bool | None = None) -> list[dict]:
        return self._readApproved("approvedContingencyPlans.json", status)

    def reportDispatches(self, report: dict) -> None:
        self._write("dispatches", report)

    def _readApproved(self, fileName: str, status: str) -> list[dict]:
        path = self._outputDir / fileName
        if not path.exists():
            return []
        return [item for item in json.loads(path.read_text(encoding="utf-8")) if item.get("status") == status]
