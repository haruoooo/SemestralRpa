"""BotCity Maestro integration (bot.py): task parameters, credential vault, finish status, alerts and artifacts.

A fake SDK records the calls; the real BotMaestroSDK is used only to check the offline mode of the template.
"""

from types import SimpleNamespace

import pytest
from botcity.maestro import AlertType, AutomationTaskFinishStatus, BotMaestroSDK

from src.adapters.outbound.maestroOrchestrator import MaestroOrchestrator, finishItems
from src.application.runSummary import RunStatus, RunSummary
from src.maestroBot import buildAlerts, runBot


class FakeSdk:
    def __init__(self, parameters=None, credentials=None, failOn: str = ""):
        self.access_token = "token"
        self.parameters = parameters or {}
        self.credentials = credentials or {}
        self.failOn = failOn
        self.calls: list[tuple] = []

    def _record(self, name, **kwargs):
        if name == self.failOn:
            raise ConnectionError("Maestro unreachable")
        self.calls.append((name, kwargs))

    def get_execution(self):
        return SimpleNamespace(task_id="42", parameters=self.parameters)

    def get_credential(self, label, key):
        self._record("get_credential", label=label, key=key)
        return self.credentials.get(key)

    def finish_task(self, **kwargs):
        self._record("finish_task", **kwargs)

    def alert(self, **kwargs):
        self._record("alert", **kwargs)

    def post_artifact(self, **kwargs):
        self._record("post_artifact", **kwargs)

    def error(self, **kwargs):
        self._record("error", **kwargs)

    def named(self, name):
        return [kwargs for call, kwargs in self.calls if call == name]


def summary(status=RunStatus.SUCCESS, succeeded=0, failed=0, skipped=0, flow="lineMonitorFlow", **details):
    return RunSummary(runId="run-1", flow=flow, status=status, itemsTotal=succeeded + failed + skipped,
                      itemsSucceeded=succeeded, itemsFailed=failed, itemsSkipped=skipped, details=details)


@pytest.fixture(autouse=True)
def isolatedFolders(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    return tmp_path


# ---------- Finish status and items ----------


@pytest.mark.parametrize(
    "status, expected",
    [
        (RunStatus.SUCCESS, AutomationTaskFinishStatus.SUCCESS),
        (RunStatus.SKIPPED, AutomationTaskFinishStatus.SUCCESS),
        (RunStatus.PARTIAL, AutomationTaskFinishStatus.PARTIALLY_COMPLETED),
        (RunStatus.FAILED, AutomationTaskFinishStatus.FAILED),
    ],
)
def testRunStatusMapsToMaestroFinishStatus(status, expected):
    sdk = FakeSdk(parameters={"flow": "lineMonitor"})
    runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=lambda *args, **kwargs: summary(status))
    [finish] = sdk.named("finish_task")
    assert finish["status"] == expected and finish["task_id"] == "42"
    assert finish["message"][0].isupper()


def testItemCountsFollowMaestroRule():
    # processed + failed must equal total; already-done items (RN11/RN13) count as processed
    assert finishItems(summary(succeeded=3, failed=1, skipped=2)) == (6, 5, 1)


# ---------- Task parameters and credentials ----------


def testFlowAndDemoParametersComeFromTheMaestroTask():
    received = {}

    def fakeExecute(name, settings, at=None, ignoreWindow=False):
        received.update(name=name, at=at, ignoreWindow=ignoreWindow)
        return summary()

    sdk = FakeSdk(parameters={"flow": "lineMonitor", "at": "2026-11-24T07:30", "ignoreWindow": "true"})
    assert runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=fakeExecute) == 0
    assert received == {"name": "lineMonitor", "at": "2026-11-24T07:30", "ignoreWindow": True}


def testSecretsComeFromTheMaestroVaultAndAreNeverPrinted(capsys):
    environment: dict = {}
    sdk = FakeSdk(parameters={"flow": "agendaDispatch"}, credentials={"smtpPassword": "s3cr3t", "productApiKey": "k3y"})
    runBot(MaestroOrchestrator(sdk), ["bot.py"], environment, executeFlow=lambda *args, **kwargs: summary(flow="agendaDispatchFlow"))
    assert environment["SMTP_PASSWORD"] == "s3cr3t" and environment["PRODUCT_API_KEY"] == "k3y"
    assert {call["label"] for call in sdk.named("get_credential")} == {"foraDoPico"}
    output = capsys.readouterr().out
    assert "s3cr3t" not in output and "k3y" not in output


def testInvalidFlowFailsTheTaskWithAnAlert():
    sdk = FakeSdk(parameters={"flow": "naoExiste"})
    assert runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=lambda *args, **kwargs: summary()) == 1
    assert sdk.named("finish_task")[0]["status"] == AutomationTaskFinishStatus.FAILED
    assert sdk.named("alert")[0]["alert_type"] == AlertType.ERROR


# ---------- Alerts and artifacts ----------


def testLineChangeRaisesAlertForHrApproval():
    alerts = buildAlerts("lineMonitor", summary(alertsCreated=2, plansProposed=6))
    assert alerts == [("Monitor das linhas: mudança nas linhas", "Foram criados 2 alerta(s) e 6 plano(s) B aguardando aprovação do RH.", "warn")]


def testFailuresAndPendingWorkRaiseAlerts():
    assert buildAlerts("scheduleImport", summary(RunStatus.PARTIAL, filesRejected=1, filesQueued=1))[1][2] == "warn"
    assert buildAlerts("agendaDispatch", summary(RunStatus.PARTIAL, stoppedEarly="mailServerUnavailable"))[0][0].endswith("servidor de e-mail fora do ar")
    assert buildAlerts("lineMonitor", summary(RunStatus.FAILED))[0][2] == "error"
    assert buildAlerts("lineMonitor", summary()) == []
    everyAlert = (
        buildAlerts("scheduleImport", summary(RunStatus.FAILED, filesRejected=1, filesQueued=1))
        + buildAlerts("agendaDispatch", summary(RunStatus.PARTIAL, stoppedEarly="mailServerUnavailable", refusedAddresses=2))
        + buildAlerts("lineMonitor", summary(RunStatus.PARTIAL, alertsCreated=1, plansProposed=0, stale=True))
    )
    for title, message, _ in everyAlert:
        assert title[0].isupper() and message[0].isupper()


def testReportsOfThisRunAndTheAuditLogAreUploaded(isolatedFolders):
    from src.infrastructure.timeProvider import nowLocal

    (isolatedFolders / "logs").mkdir()
    (isolatedFolders / "logs" / f"robot{nowLocal():%Y%m%d}.log").write_text("{}\n", encoding="utf-8")

    def fakeImport(*args, **kwargs):
        (isolatedFolders / "reports").mkdir()
        (isolatedFolders / "reports" / "importReportabcd1234.xlsx").write_bytes(b"x")
        return summary(flow="scheduleImportFlow", succeeded=1)

    sdk = FakeSdk(parameters={"flow": "scheduleImport"})
    runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=fakeImport)
    assert [call["artifact_name"] for call in sdk.named("post_artifact")] == ["importReportabcd1234.xlsx", f"robot{nowLocal():%Y%m%d}.log"]


# ---------- Resilience and offline mode ----------


def testMaestroOutageNeverChangesTheRobotResult():
    sdk = FakeSdk(parameters={"flow": "lineMonitor"}, failOn="finish_task")
    assert runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=lambda *args, **kwargs: summary(RunStatus.PARTIAL)) == 2


def testUnexpectedCrashIsReportedToMaestro():
    def crash(*args, **kwargs):
        raise RuntimeError("Boom")

    sdk = FakeSdk(parameters={"flow": "lineMonitor"})
    assert runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=crash) == 1
    assert len(sdk.named("error")) == 1 and sdk.named("finish_task")[0]["status"] == AutomationTaskFinishStatus.FAILED


def testOfflineTemplateModeRunsLocallyWithoutMaestro():
    orchestrator = MaestroOrchestrator(BotMaestroSDK())  # No server, no token: the template's offline mode
    assert not orchestrator.connected and orchestrator.taskParameters() == {}
    assert runBot(orchestrator, ["bot.py", "lineMonitor"], {}, executeFlow=lambda *args, **kwargs: summary()) == 0


def testWorkingFolderComesFromTaskParameterOrMachineVariable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "foraDoPicoHome"
    home.mkdir()
    seen = {}

    def fakeExecute(*args, **kwargs):
        import os
        seen["cwd"] = os.getcwd()
        return summary()

    runBot(MaestroOrchestrator(FakeSdk(parameters={"flow": "lineMonitor"})), ["bot.py"], {"FORADOPICO_HOME": str(home)}, executeFlow=fakeExecute)
    assert seen["cwd"] == str(home)

    sdk = FakeSdk(parameters={"flow": "lineMonitor", "homeDir": str(tmp_path / "naoExiste")})
    assert runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=fakeExecute) == 1
    assert sdk.named("finish_task")[0]["status"] == AutomationTaskFinishStatus.FAILED
    assert sdk.named("alert")[0]["message"][0].isupper()


@pytest.mark.parametrize(
    "raw",
    [
        {"flow": "lineMonitor"},
        '{"flow": "lineMonitor"}',
        [{"name": "flow", "value": "lineMonitor"}],
        [{"label": "flow", "value": "lineMonitor"}],
    ],
)
def testTaskParametersAcceptEveryMaestroFormat(raw):
    from src.adapters.outbound.maestroOrchestrator import normalizeParameters

    assert normalizeParameters(raw)["flow"] == "lineMonitor"


def testInvalidFlowListsTheParameterNamesReceived(capsys):
    sdk = FakeSdk(parameters={"Fluxo": "lineMonitor"})
    runBot(MaestroOrchestrator(sdk), ["bot.py"], {}, executeFlow=lambda *args, **kwargs: summary())
    assert "Parâmetros recebidos: Fluxo." in capsys.readouterr().out
