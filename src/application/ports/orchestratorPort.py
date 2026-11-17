from pathlib import Path
from typing import Protocol

from src.application.runSummary import RunSummary


class OrchestratorPort(Protocol):
    """Orchestration platform that starts the robot and receives the outcome (BotCity Maestro)."""

    @property
    def connected(self) -> bool: ...

    def taskParameters(self) -> dict[str, str]:
        """Parameters of the task that started this execution (empty when running locally)."""
        ...

    def credential(self, label: str, key: str) -> str | None:
        """Secret stored in the orchestrator vault, or None when unavailable."""
        ...

    def finishTask(self, summary: RunSummary) -> None: ...

    def alert(self, title: str, message: str, level: str) -> None:
        """level: info, warn or error."""
        ...

    def uploadArtifact(self, name: str, path: Path) -> None: ...

    def reportError(self, error: Exception) -> None: ...
