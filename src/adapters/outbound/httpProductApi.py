"""Product API client over HTTP. Works against the real API or the local mock (same contract)."""

import httpx

from src.domain.assignment import Assignment
from src.domain.exceptions import ApiRejectedError, ApiUnavailableError


class HttpProductApi:
    def __init__(self, baseUrl: str, apiKey: str, timeoutSeconds: float, client: httpx.Client | None = None):
        self._client = client or httpx.Client(
            base_url=baseUrl, timeout=timeoutSeconds, headers={"X-Api-Key": apiKey}
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise ApiUnavailableError(f"{method} {path} unreachable: {type(error).__name__}") from error
        if response.status_code >= 500:
            raise ApiUnavailableError(f"{method} {path} answered HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ApiRejectedError(
                f"{method} {path} rejected with HTTP {response.status_code}", response.status_code, response.text[:500]
            )
        return response

    def healthCheck(self) -> bool:
        return self._request("GET", "/health").status_code == 200

    def submitScheduleImport(self, payload: dict, idempotencyKey: str) -> dict:
        return self._request("POST", "/scheduleImports", json=payload, headers={"Idempotency-Key": idempotencyKey}).json()

    def publishLineStatus(self, snapshot: dict) -> None:
        self._request("POST", "/lineStatus", json=snapshot)

    def createAlert(self, alert: dict) -> dict:
        return self._request("POST", "/alerts", json=alert).json()

    def listAssignments(self, date: str, lineNumber: int | None = None) -> list[Assignment]:
        params = {"date": date}
        if lineNumber is not None:
            params["lineNumber"] = lineNumber
        return [Assignment.fromApi(item) for item in self._request("GET", "/assignments", params=params).json()]

    def createContingencyPlan(self, plan: dict) -> dict:
        return self._request("POST", "/contingencyPlans", json=plan).json()

    def listSchedules(self, status: str, dispatched: bool | None = None) -> list[dict]:
        return self._request("GET", "/schedules", params=_statusParams(status, dispatched)).json()

    def listContingencyPlans(self, status: str, dispatched: bool | None = None) -> list[dict]:
        return self._request("GET", "/contingencyPlans", params=_statusParams(status, dispatched)).json()

    def reportDispatches(self, report: dict) -> None:
        self._request("POST", "/dispatches", json=report)


def _statusParams(status: str, dispatched: bool | None) -> dict:
    params = {"status": status}
    if dispatched is not None:
        params["dispatched"] = "true" if dispatched else "false"
    return params
