"""Robot entry point (CLI). Builds the adapters chosen in .env and runs a flow.

Examples:
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

from src.adapters.inbound.metroWebsiteSource import MetroWebsiteSource
from src.adapters.inbound.simulatedSource import SimulatedSource, writeScenario
from src.adapters.outbound.fileProductApi import FileProductApi
from src.adapters.outbound.httpProductApi import HttpProductApi
from src.adapters.outbound.sqliteRobotState import SqliteRobotState
from src.application.flows.lineMonitorFlow import FLOW_NAME as LINE_MONITOR_FLOW, LineMonitorFlow
from src.infrastructure.robotLogger import RunLogger, buildRunId
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

    monitor = commands.add_parser("lineMonitor", help="Run the line monitor flow once")
    monitor.add_argument("--ignoreWindow", action="store_true", help="Run even outside the weekday operating window (demo)")
    monitor.add_argument("--at", help="Freeze the robot clock (demo), e.g. 07:30 or 2026-11-10T07:30")

    simulate = commands.add_parser("simulate", help="Change the simulated scenario (LINE_STATUS_SOURCE=simulated)")
    simulate.add_argument("--line", type=int, help="Line number, e.g. 3")
    simulate.add_argument("--text", help='Status text as published by the Metro, e.g. "Paralisada"')
    simulate.add_argument("--unavailable", action="store_true", help="Simulate the source being down")

    args = parser.parse_args(argv)
    settings = Settings.fromEnvironment()

    if args.command == "lineMonitor":
        return runLineMonitor(settings, args.ignoreWindow, args.at)
    if args.command == "simulate":
        return runSimulate(settings, args.line, args.text, args.unavailable)
    return 1


if __name__ == "__main__":
    sys.exit(main())
