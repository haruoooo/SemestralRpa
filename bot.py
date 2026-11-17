"""ForaDoPico RPA · BotCity bot entry point (BotCity Python bot template, project type "Custom").

The BotCity Runner starts this file for every task created in BotCity Maestro, passing server, task id and
access token on the command line. The task parameter `flow` chooses what to run:
    scheduleImport | agendaDispatch | lineMonitor

Locally (without Maestro) it works the same way, offline:
    python bot.py lineMonitor

Install the dependencies with `pip install --upgrade -r requirements.txt`.
"""

import sys

from src.adapters.outbound.maestroOrchestrator import MaestroOrchestrator
from src.maestroBot import runBot


def main() -> int:
    # Runner passes the server url, the id of the task being executed, the access token
    # and the parameters that this task receives (when applicable).
    return runBot(MaestroOrchestrator(), sys.argv)


if __name__ == "__main__":
    sys.exit(main())
