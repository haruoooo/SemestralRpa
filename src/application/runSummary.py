from dataclasses import asdict, dataclass, field
from enum import StrEnum


class RunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RunSummary:
    runId: str
    flow: str
    status: RunStatus = RunStatus.SUCCESS
    itemsTotal: int = 0
    itemsSucceeded: int = 0
    itemsFailed: int = 0
    itemsSkipped: int = 0
    durationSeconds: float = 0.0
    details: dict = field(default_factory=dict)

    def toDict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @property
    def exitCode(self) -> int:
        """0 = success/skipped, 2 = partial (some items failed), 1 = failed."""
        return {RunStatus.SUCCESS: 0, RunStatus.SKIPPED: 0, RunStatus.PARTIAL: 2, RunStatus.FAILED: 1}[self.status]
