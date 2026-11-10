"""Audit logging: JSON Lines file + readable console output (etapa 05 — Logs e Auditoria).

Rules enforced here:
- Every message starts with an uppercase letter.
- Internal logs are in English.
- Personal data never reaches the log: employees appear only as employeeRef (salted hash).
"""

import hashlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from src.infrastructure.timeProvider import nowLocal


def capitalizeFirst(message: str) -> str:
    return message[:1].upper() + message[1:] if message else message


def buildEmployeeRef(employeeId: str, salt: str) -> str:
    """LGPD: irreversible reference for an employee in logs."""
    return hashlib.sha256(f"{salt}:{employeeId}".encode("utf-8")).hexdigest()[:12]


def buildRunId(flowPrefix: str, moment: datetime) -> str:
    return f"{flowPrefix}-{moment.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:4]}"


class _JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": nowLocal().isoformat(timespec="seconds"),
            "level": record.levelname,
            "runId": getattr(record, "runId", None),
            "flow": getattr(record, "flow", None),
            "step": getattr(record, "step", None),
            "event": getattr(record, "event", None),
            "itemRef": getattr(record, "itemRef", None),
            "message": record.getMessage(),
        }
        extraData = getattr(record, "data", None)
        if extraData:
            entry["data"] = extraData
        return json.dumps(entry, ensure_ascii=False)


class _ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        step = getattr(record, "step", "-")
        event = getattr(record, "event", "-")
        return f"{nowLocal().strftime('%H:%M:%S')} {record.levelname:<8} [{step}] {event}: {record.getMessage()}"


def _buildBaseLogger(logDir: Path | None) -> logging.Logger:
    logger = logging.getLogger("foraDoPicoRpa")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_ConsoleFormatter())
    logger.addHandler(console)

    if logDir is not None:
        logDir.mkdir(parents=True, exist_ok=True)
        fileHandler = logging.FileHandler(logDir / f"robot{nowLocal().strftime('%Y%m%d')}.log", encoding="utf-8")
        fileHandler.setFormatter(_JsonLinesFormatter())
        logger.addHandler(fileHandler)
    return logger


class RunLogger:
    """Logger bound to one execution (runId) of one flow."""

    def __init__(self, flow: str, runId: str, logDir: Path | None = None, baseLogger: logging.Logger | None = None):
        self.flow = flow
        self.runId = runId
        self._logger = baseLogger or _buildBaseLogger(logDir)

    def _emit(self, level: int, step: str, event: str, message: str, itemRef: str | None, data: dict | None, excInfo: bool):
        self._logger.log(
            level,
            capitalizeFirst(message),
            exc_info=excInfo,
            extra={"runId": self.runId, "flow": self.flow, "step": step, "event": event, "itemRef": itemRef, "data": data},
        )

    def info(self, step: str, event: str, message: str, itemRef: str | None = None, data: dict | None = None):
        self._emit(logging.INFO, step, event, message, itemRef, data, False)

    def warning(self, step: str, event: str, message: str, itemRef: str | None = None, data: dict | None = None):
        self._emit(logging.WARNING, step, event, message, itemRef, data, False)

    def error(self, step: str, event: str, message: str, itemRef: str | None = None, data: dict | None = None, excInfo: bool = False):
        self._emit(logging.ERROR, step, event, message, itemRef, data, excInfo)
