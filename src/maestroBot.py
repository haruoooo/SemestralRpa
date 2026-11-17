"""Glue between the BotCity Maestro task and the robot flows (used by bot.py, the BotCity template entry point).

What happens in one Maestro task:
1. Read the task parameters: flow (scheduleImport, agendaDispatch or lineMonitor) and, for demos, at / ignoreWindow.
2. Read the secrets from the Maestro credential vault (when connected), instead of the .env file.
3. Run the flow exactly as the CLI does.
4. Finish the task with SUCCESS / PARTIALLY_COMPLETED / FAILED and the item counts (Maestro ROI and success rate).
5. Raise alerts the operation team must see, in Portuguese.
6. Upload the HR reports produced in this run and the day's audit log as artifacts.
"""

import os
import time as timeModule
from collections.abc import Callable
from pathlib import Path

from src.application.ports.orchestratorPort import OrchestratorPort
from src.application.runSummary import RunStatus, RunSummary
from src.infrastructure.settings import Settings
from src.infrastructure.timeProvider import nowLocal

CREDENTIAL_LABEL_ENV = "MAESTRO_CREDENTIAL_LABEL"
DEFAULT_CREDENTIAL_LABEL = "foraDoPico"
# Maestro credential key -> environment variable read by Settings
CREDENTIAL_KEYS = {
    "productApiKey": "PRODUCT_API_KEY",
    "smtpUser": "SMTP_USER",
    "smtpPassword": "SMTP_PASSWORD",
    "logSalt": "LOG_SALT",
}
FLOW_TITLES = {"scheduleImport": "Importação da escala", "agendaDispatch": "Envio das agendas", "lineMonitor": "Monitor das linhas"}


def resolveFlow(parameters: dict[str, str], argv: list[str]) -> str | None:
    """Maestro task parameter `flow`; locally: `python bot.py lineMonitor` or BOT_FLOW."""
    if parameters.get("flow"):
        return parameters["flow"]
    if len(argv) == 2:
        return argv[1]
    return os.getenv("BOT_FLOW")


def loadCredentials(orchestrator: OrchestratorPort, environment: dict) -> list[str]:
    """Copies the secrets from the Maestro vault into the environment. Returns the keys found (never the values)."""
    label = environment.get(CREDENTIAL_LABEL_ENV, DEFAULT_CREDENTIAL_LABEL)
    loaded = []
    for key, variable in CREDENTIAL_KEYS.items():
        value = orchestrator.credential(label, key)
        if value:
            environment[variable] = value
            loaded.append(key)
    return loaded


def buildAlerts(flow: str, summary: RunSummary) -> list[tuple[str, str, str]]:
    """(title, message, level) for the Maestro alert panel, in Portuguese."""
    title = FLOW_TITLES.get(flow, flow)
    details = summary.details or {}
    alerts: list[tuple[str, str, str]] = []
    if summary.status == RunStatus.FAILED:
        alerts.append((f"{title}: falha", f"A execução {summary.runId} falhou. Veja o log de auditoria anexado.", "error"))
    if flow == "scheduleImport":
        if details.get("filesRejected"):
            alerts.append((f"{title}: planilha rejeitada", f"Planilhas rejeitadas: {details['filesRejected']}. O RH deve ver o relatório anexado e reenviar.", "warn"))
        if details.get("filesQueued") or details.get("outboxPending"):
            alerts.append((f"{title}: API fora do ar", "Importação guardada na fila (outbox); será reenviada automaticamente.", "warn"))
    if flow == "agendaDispatch":
        if details.get("stoppedEarly") == "mailServerUnavailable":
            alerts.append((f"{title}: servidor de e-mail fora do ar", "Envios pendentes serão feitos na próxima execução.", "warn"))
        if details.get("refusedAddresses"):
            alerts.append((f"{title}: e-mail recusado", f"Endereços recusados: {details['refusedAddresses']}. O RH deve corrigir o cadastro.", "warn"))
    if flow == "lineMonitor":
        if details.get("alertsCreated"):
            alerts.append((
                f"{title}: mudança nas linhas",
                f"Foram criados {details['alertsCreated']} alerta(s) e {details.get('plansProposed', 0)} plano(s) B aguardando aprovação do RH.",
                "warn" if details.get("plansProposed") else "info",
            ))
        if details.get("stale"):
            alerts.append((f"{title}: dados desatualizados", "O site do Metrô está fora do ar há mais de 30 minutos; nenhum plano B novo será gerado.", "warn"))
    return alerts


def runBot(
    orchestrator: OrchestratorPort,
    argv: list[str],
    environment: dict | None = None,
    executeFlow: Callable[..., RunSummary] | None = None,
) -> int:
    environment = os.environ if environment is None else environment
    if executeFlow is None:
        from src.main import executeFlow  # Late import: keeps this module light for tests
    parameters = orchestrator.taskParameters()
    flow = resolveFlow(parameters, argv)
    if flow not in FLOW_TITLES:
        message = f"Parâmetro 'flow' inválido: {flow!r}. Use scheduleImport, agendaDispatch ou lineMonitor."
        print(message)
        orchestrator.alert("Tarefa sem fluxo válido", message, "error")
        orchestrator.finishTask(RunSummary(runId="-", flow=str(flow), status=RunStatus.FAILED))
        return 1

    loaded = loadCredentials(orchestrator, environment)
    if loaded:
        print(f"Credenciais lidas do cofre do Maestro: {', '.join(loaded)}")
    settings = Settings.fromEnvironment()
    startedAt = timeModule.time()
    try:
        summary = executeFlow(
            flow, settings, at=parameters.get("at") or None,
            ignoreWindow=str(parameters.get("ignoreWindow", "")).lower() in ("true", "1", "sim"),
        )
    except Exception as error:  # EX11 at task level: the flows already catch everything, this is the last net
        orchestrator.reportError(error)
        summary = RunSummary(runId="-", flow=flow, status=RunStatus.FAILED)

    orchestrator.finishTask(summary)
    for title, message, level in buildAlerts(flow, summary):
        orchestrator.alert(title, message, level)
    for path in _artifactsOf(settings, startedAt):
        orchestrator.uploadArtifact(path.name, path)
    return summary.exitCode


def _artifactsOf(settings: Settings, startedAt: float) -> list[Path]:
    reports = [path for path in settings.reportDir.glob("importReport*.xlsx") if path.stat().st_mtime >= startedAt - 1] if settings.reportDir.exists() else []
    log = settings.logDir / f"robot{nowLocal():%Y%m%d}.log"
    return sorted(reports) + ([log] if log.exists() else [])
