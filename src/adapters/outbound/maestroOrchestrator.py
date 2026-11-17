"""BotCity Maestro integration (botcity-maestro-sdk), following the BotCity Python bot template.

When the BotCity Runner starts the robot it passes server, task id and token on the command line;
BotMaestroSDK.from_sys_args() reads them. Without them (local run, tests, the APScheduler mode) the SDK works
offline: RAISE_NOT_CONNECTED = False turns every call into a no-op, exactly as in the class template.
A failure talking to Maestro never breaks the robot: it is logged and the run result stays the same.
"""

import logging
from pathlib import Path

from botcity.maestro import AlertType, AutomationTaskFinishStatus, BotMaestroSDK

from src.application.runSummary import RunStatus, RunSummary

BotMaestroSDK.RAISE_NOT_CONNECTED = False

_log = logging.getLogger("foraDoPicoRpa.maestro")

FINISH_STATUS = {
    RunStatus.SUCCESS: AutomationTaskFinishStatus.SUCCESS,
    RunStatus.SKIPPED: AutomationTaskFinishStatus.SUCCESS,
    RunStatus.PARTIAL: AutomationTaskFinishStatus.PARTIALLY_COMPLETED,
    RunStatus.FAILED: AutomationTaskFinishStatus.FAILED,
}
ALERT_TYPE = {"info": AlertType.INFO, "warn": AlertType.WARN, "error": AlertType.ERROR}
FINISH_MESSAGES = {  # Shown in the Maestro task list (Portuguese: read by the operation team)
    RunStatus.SUCCESS: "Execução concluída com sucesso.",
    RunStatus.SKIPPED: "Nada a fazer nesta execução (fora da janela ou sem arquivos).",
    RunStatus.PARTIAL: "Execução concluída com itens pendentes; serão refeitos na próxima execução.",
    RunStatus.FAILED: "Execução falhou; veja os alertas e o log.",
}


def finishItems(summary: RunSummary) -> tuple[int, int, int]:
    """Maestro requires processed + failed = total. Skipped items (already done, RN11/RN13) count as processed."""
    failed = summary.itemsFailed
    processed = summary.itemsSucceeded + summary.itemsSkipped
    return processed + failed, processed, failed


class MaestroOrchestrator:
    def __init__(self, sdk: BotMaestroSDK | None = None):
        self._sdk = sdk if sdk is not None else BotMaestroSDK.from_sys_args()
        # Offline (local run): no task to fetch; avoids the SDK "offline mode" warnings on every run
        self._execution = self._safe("get_execution", self._sdk.get_execution) if self.connected else None

    @property
    def connected(self) -> bool:
        return bool(getattr(self._sdk, "access_token", None))

    @property
    def taskId(self) -> str:
        return str(getattr(self._execution, "task_id", "") or "")

    def taskParameters(self) -> dict[str, str]:
        return dict(getattr(self._execution, "parameters", None) or {})

    def credential(self, label: str, key: str) -> str | None:
        if not self.connected:
            return None
        return self._safe("get_credential", lambda: self._sdk.get_credential(label=label, key=key))

    def finishTask(self, summary: RunSummary) -> None:
        if not self.connected:
            return
        total, processed, failed = finishItems(summary)
        self._safe(
            "finish_task",
            lambda: self._sdk.finish_task(
                task_id=self.taskId, status=FINISH_STATUS[summary.status], message=FINISH_MESSAGES[summary.status],
                total_items=total, processed_items=processed, failed_items=failed,
            ),
        )

    def alert(self, title: str, message: str, level: str) -> None:
        if self.connected:
            self._safe("alert", lambda: self._sdk.alert(task_id=self.taskId, title=title, message=message, alert_type=ALERT_TYPE[level]))

    def uploadArtifact(self, name: str, path: Path) -> None:
        if self.connected:
            self._safe("post_artifact", lambda: self._sdk.post_artifact(task_id=self.taskId, artifact_name=name, filepath=str(path)))

    def reportError(self, error: Exception) -> None:
        if self.connected:
            self._safe("error", lambda: self._sdk.error(task_id=self.taskId, exception=error))

    @staticmethod
    def _safe(operation: str, call):
        try:
            return call()
        except Exception as error:  # Orchestration problems must never change the business result
            _log.warning(
                "Maestro %s failed: %s", operation, type(error).__name__,
                extra={"runId": "maestro", "flow": "-", "step": "-", "event": "MaestroCallFailed", "itemRef": None, "data": None},
            )
            return None
