"""Configuration loaded from environment variables (.env). Credentials never live in the code."""

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

from dotenv import load_dotenv


def _parseTime(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


@dataclass(frozen=True)
class Settings:
    productApiMode: str = "http"
    productApiUrl: str = "http://127.0.0.1:8000"
    productApiKey: str = ""
    lineStatusSource: str = "metroWebsite"
    metroStatusUrl: str = "https://www.metro.sp.gov.br/wp-content/themes/metrosp/direto-metro.php"
    simulatedScenarioPath: Path = Path("data/runtime/simulatedScenario.json")
    monitoredLines: tuple[int, ...] = (1, 3)
    monitorStart: time = time(5, 0)
    monitorEnd: time = time(22, 0)
    staleAfterMinutes: int = 30
    httpTimeoutSeconds: float = 15.0
    retryAttempts: int = 3
    retryBaseSeconds: float = 2.0
    stateDbPath: Path = Path("data/runtime/robotState.db")
    fileApiOutputDir: Path = Path("data/runtime/fileApi")
    logDir: Path = Path("logs")
    inputDir: Path = Path("data/input")
    reportDir: Path = Path("data/output/reports")
    landingZonePath: Path = Path("landingZone/chegada")
    notifierMode: str = "console"
    smtpHost: str = "sandbox.smtp.mailtrap.io"
    smtpPort: int = 2525
    smtpUser: str = ""
    smtpPassword: str = field(default="", repr=False)
    mailFrom: str = "ForaDoPico <agenda@foradopico.example>"
    mailMinIntervalSeconds: float = 10.0
    mailOutputDir: Path = Path("data/output/mail")
    dispatchLimitPerRun: int = 0
    scheduleImportEveryMinutes: int = 5
    agendaDispatchEveryMinutes: int = 10
    lineMonitorEveryMinutes: int = 5
    logSalt: str = field(default="", repr=False)

    @classmethod
    def fromEnvironment(cls) -> "Settings":
        load_dotenv()
        env = os.getenv
        return cls(
            productApiMode=env("PRODUCT_API_MODE", "http"),
            productApiUrl=env("PRODUCT_API_URL", "http://127.0.0.1:8000"),
            productApiKey=env("PRODUCT_API_KEY", ""),
            lineStatusSource=env("LINE_STATUS_SOURCE", "metroWebsite"),
            metroStatusUrl=env("METRO_STATUS_URL", cls.metroStatusUrl),
            simulatedScenarioPath=Path(env("SIMULATED_SCENARIO_PATH", "data/runtime/simulatedScenario.json")),
            monitoredLines=tuple(int(item) for item in env("MONITORED_LINES", "1,3").split(",") if item.strip()),
            monitorStart=_parseTime(env("MONITOR_START", "05:00")),
            monitorEnd=_parseTime(env("MONITOR_END", "22:00")),
            staleAfterMinutes=int(env("STALE_AFTER_MINUTES", "30")),
            httpTimeoutSeconds=float(env("HTTP_TIMEOUT_SECONDS", "15")),
            retryAttempts=int(env("RETRY_ATTEMPTS", "3")),
            stateDbPath=Path(env("STATE_DB_PATH", "data/runtime/robotState.db")),
            fileApiOutputDir=Path(env("FILE_API_OUTPUT_DIR", "data/runtime/fileApi")),
            logDir=Path(env("LOG_DIR", "logs")),
            inputDir=Path(env("INPUT_DIR", "data/input")),
            reportDir=Path(env("REPORT_DIR", "data/output/reports")),
            landingZonePath=Path(env("LANDING_ZONE_PATH", "landingZone/chegada")),
            notifierMode=env("NOTIFIER_MODE", "console"),
            smtpHost=env("SMTP_HOST", "sandbox.smtp.mailtrap.io"),
            smtpPort=int(env("SMTP_PORT", "2525")),
            smtpUser=env("SMTP_USER", ""),
            smtpPassword=env("SMTP_PASSWORD", ""),
            mailFrom=env("MAIL_FROM", "") or cls.mailFrom,
            mailMinIntervalSeconds=float(env("MAIL_MIN_INTERVAL_SECONDS", "10")),
            mailOutputDir=Path(env("MAIL_OUTPUT_DIR", "data/output/mail")),
            dispatchLimitPerRun=int(env("DISPATCH_LIMIT_PER_RUN", "0")),
            scheduleImportEveryMinutes=int(env("SCHEDULE_IMPORT_EVERY_MINUTES", "5")),
            agendaDispatchEveryMinutes=int(env("AGENDA_DISPATCH_EVERY_MINUTES", "10")),
            lineMonitorEveryMinutes=int(env("LINE_MONITOR_EVERY_MINUTES", "5")),
            logSalt=env("LOG_SALT", ""),
        )
