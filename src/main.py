"""Robot entry point (CLI). Builds the adapters chosen in .env and runs a flow.

Examples:
    python -m src.main scheduler          (runs the three flows on their schedules; Ctrl+C stops)
    python -m src.main scheduleImport
    python -m src.main agendaDispatch
    python -m src.main lineMonitor
    python -m src.main lineMonitor --ignoreWindow
    python -m src.main lineMonitor --ignoreWindow --at 07:30
    python -m src.main simulate --line 3 --text "Paralisada"
    python -m src.main simulate --unavailable
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from src.adapters.inbound.localInputFolder import LocalInputFolder
from src.adapters.inbound.metroWebsiteSource import MetroWebsiteSource
from src.adapters.inbound.openpyxlSpreadsheetReader import OpenpyxlSpreadsheetReader
from src.adapters.inbound.simulatedSource import SimulatedSource, writeScenario
from src.adapters.outbound.emailNotifiers import ConsoleNotifier, SmtpNotifier
from src.adapters.outbound.fileProductApi import FileProductApi
from src.adapters.outbound.httpProductApi import HttpProductApi
from src.adapters.outbound.icalendarCalendar import IcalendarCalendar
from src.adapters.outbound.localLandingZone import LocalLandingZone
from src.adapters.outbound.sqliteRobotState import SqliteRobotState
from src.adapters.outbound.xlsxImportReport import XlsxImportReport
from src.application.flows.agendaDispatchFlow import FLOW_NAME as AGENDA_DISPATCH_FLOW, AgendaDispatchFlow
from src.application.flows.lineMonitorFlow import FLOW_NAME as LINE_MONITOR_FLOW, LineMonitorFlow
from src.application.flows.scheduleImportFlow import FLOW_NAME as SCHEDULE_IMPORT_FLOW, ScheduleImportFlow
from src.infrastructure.robotLogger import RunLogger, buildRunId
from src.infrastructure.robotScheduler import buildScheduler
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import SAO_PAULO, nowLocal


def buildLineStatusSource(settings: Settings):
    if settings.lineStatusSource == "simulated":
        return SimulatedSource(settings.simulatedScenarioPath)
    return MetroWebsiteSource(settings.metroStatusUrl, settings.httpTimeoutSeconds)


def buildProductApi(settings: Settings):
    if settings.productApiMode == "file":
        return FileProductApi(settings.fileApiOutputDir, Path("data/fixtures/assignmentsSample.json"))
    return HttpProductApi(settings.productApiUrl, settings.productApiKey, settings.httpTimeoutSeconds)


def buildClock(at: str | None):
    """Demo/test only: freezes the robot clock at a given local time, e.g. 07:30 or 2026-11-10T07:30."""
    if not at:
        return nowLocal
    if "T" in at:
        fixed = datetime.fromisoformat(at).replace(tzinfo=SAO_PAULO)
    else:
        hours, minutes = at.split(":")
        fixed = nowLocal().replace(hour=int(hours), minute=int(minutes), second=0, microsecond=0)
    return lambda: fixed


def runLineMonitor(settings: Settings, ignoreWindow: bool, at: str | None = None) -> int:
    clock = buildClock(at)
    logger = RunLogger(LINE_MONITOR_FLOW, buildRunId("lm", nowLocal()), settings.logDir)
    if at:
        logger.warning("1", "ClockOverridden", f"Robot clock frozen at {clock().isoformat(timespec='minutes')} (demo mode)")
    flow = LineMonitorFlow(
        source=buildLineStatusSource(settings),
        api=buildProductApi(settings),
        state=SqliteRobotState(settings.stateDbPath),
        settings=settings,
        logger=logger,
        clock=clock,
        respectOperatingWindow=not ignoreWindow,
    )
    return flow.run().exitCode


def runScheduleImport(settings: Settings) -> int:
    flow = ScheduleImportFlow(
        reader=OpenpyxlSpreadsheetReader(),
        inputFolder=LocalInputFolder(settings.inputDir),
        api=buildProductApi(settings),
        landingZone=LocalLandingZone(settings.landingZonePath),
        report=XlsxImportReport(settings.reportDir),
        state=SqliteRobotState(settings.stateDbPath),
        settings=settings,
        logger=RunLogger(SCHEDULE_IMPORT_FLOW, buildRunId("si", nowLocal()), settings.logDir),
    )
    return flow.run().exitCode


def buildNotifier(settings: Settings):
    if settings.notifierMode == "smtp":
        return SmtpNotifier(
            settings.smtpHost, settings.smtpPort, settings.smtpUser, settings.smtpPassword, settings.mailFrom,
            settings.httpTimeoutSeconds, settings.mailMinIntervalSeconds,
        )
    return ConsoleNotifier(settings.mailOutputDir, settings.mailFrom)


def runAgendaDispatch(settings: Settings, at: str | None = None) -> int:
    clock = buildClock(at)
    logger = RunLogger(AGENDA_DISPATCH_FLOW, buildRunId("ad", nowLocal()), settings.logDir)
    if at:
        logger.warning("1", "ClockOverridden", f"Robot clock frozen at {clock().isoformat(timespec='minutes')} (demo mode)")
    flow = AgendaDispatchFlow(
        api=buildProductApi(settings),
        notifier=buildNotifier(settings),
        calendar=IcalendarCalendar(settings.mailFrom),
        state=SqliteRobotState(settings.stateDbPath),
        settings=settings,
        logger=logger,
        clock=clock,
    )
    return flow.run().exitCode


def runScheduler(settings: Settings) -> int:
    scheduler = buildScheduler(
        {
            "scheduleImport": (lambda: runScheduleImport(Settings.fromEnvironment()), settings.scheduleImportEveryMinutes),
            "agendaDispatch": (lambda: runAgendaDispatch(Settings.fromEnvironment()), settings.agendaDispatchEveryMinutes),
            "lineMonitor": (lambda: runLineMonitor(Settings.fromEnvironment(), ignoreWindow=False), settings.lineMonitorEveryMinutes),
        }
    )
    for job in scheduler.get_jobs():
        job.modify(next_run_time=nowLocal())  # Run everything once at start-up, then on the interval
    print(
        f"Robô agendado: importação a cada {settings.scheduleImportEveryMinutes} min, envio de agendas a cada "
        f"{settings.agendaDispatchEveryMinutes} min, monitor das linhas a cada {settings.lineMonitorEveryMinutes} min. Ctrl+C para parar."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Robô parado.")
    return 0


def runSimulate(settings: Settings, line: int | None, text: str | None, unavailable: bool) -> int:
    if (line is None) != (text is None):
        print("Informe --line e --text juntos (ex.: --line 3 --text \"Paralisada\").")
        return 1
    scenario = writeScenario(settings.simulatedScenarioPath, line or 0, text or "", available=not unavailable)
    print(f"Cenário simulado atualizado em {settings.simulatedScenarioPath}:")
    for item in scenario["lines"]:
        print(f"  Linha {item['lineNumber']}-{item['lineName']}: {item['rawText']}")
    print(f"  Fonte disponível: {'sim' if scenario['available'] else 'não'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="foraDoPicoRpa", description="ForaDoPico RPA robot")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("scheduler", help="Run the three flows on their schedules (production mode)")
    commands.add_parser("scheduleImport", help="Import the HR spreadsheets waiting in the input folder")

    dispatch = commands.add_parser("agendaDispatch", help="Send approved agendas and plan B notices by e-mail")
    dispatch.add_argument("--at", help="Freeze the robot clock (demo), e.g. 2026-11-24T07:40")

    monitor = commands.add_parser("lineMonitor", help="Run the line monitor flow once")
    monitor.add_argument("--ignoreWindow", action="store_true", help="Run even outside the weekday operating window (demo)")
    monitor.add_argument("--at", help="Freeze the robot clock (demo), e.g. 07:30 or 2026-11-10T07:30")

    simulate = commands.add_parser("simulate", help="Change the simulated scenario (LINE_STATUS_SOURCE=simulated)")
    simulate.add_argument("--line", type=int, help="Line number, e.g. 3")
    simulate.add_argument("--text", help='Status text as published by the Metro, e.g. "Paralisada"')
    simulate.add_argument("--unavailable", action="store_true", help="Simulate the source being down")

    args = parser.parse_args(argv)
    settings = Settings.fromEnvironment()

    if args.command == "scheduler":
        return runScheduler(settings)
    if args.command == "scheduleImport":
        return runScheduleImport(settings)
    if args.command == "agendaDispatch":
        return runAgendaDispatch(settings, args.at)
    if args.command == "lineMonitor":
        return runLineMonitor(settings, args.ignoreWindow, args.at)
    if args.command == "simulate":
        return runSimulate(settings, args.line, args.text, args.unavailable)
    return 1


if __name__ == "__main__":
    sys.exit(main())
