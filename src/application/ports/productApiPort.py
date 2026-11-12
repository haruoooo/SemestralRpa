from typing import Protocol

from src.domain.assignment import Assignment


class ProductApiPort(Protocol):
    """Contract with the ForaDoPico product API (docs/integrations/secureDevOpsCloud/productApiContract.yaml).

    Every method raises ApiUnavailableError (retryable) or ApiRejectedError (not retryable).
    """

    def submitScheduleImport(self, payload: dict, idempotencyKey: str) -> dict:
        """POST /scheduleImports. Replaying the same key returns the original import (never a duplicate)."""
        ...

    def publishLineStatus(self, snapshot: dict) -> None: ...

    def createAlert(self, alert: dict) -> dict: ...

    def listAssignments(self, date: str, lineNumber: int | None = None) -> list[Assignment]: ...

    def createContingencyPlan(self, plan: dict) -> dict: ...
