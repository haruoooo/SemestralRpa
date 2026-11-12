"""Local mock of the ForaDoPico product API, implementing docs/integrations/secureDevOpsCloud/productApiContract.yaml.

Purpose: let the robot run end to end before the real API exists, and serve as a reference
implementation for the product API team. Data lives in memory and is fictitious.

Run:  uvicorn mockApi.app:app --port 8000
Panel (for the demo video): http://localhost:8000/
"""

import os
from html import escape
from itertools import cycle
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

API_KEY = os.getenv("MOCK_API_KEY", "")
DEFAULT_WINDOWS = ["07:00", "08:00", "09:30", "10:30"]

app = FastAPI(title="ForaDoPico mock API", version="0.1.0")

store: dict = {
    "imports": {},  # idempotencyKey -> result
    "schedules": {},
    "alerts": {},  # dedupeKey -> alert
    "contingencyPlans": {},
    "dispatches": [],
    "lineStatus": None,
}

# ---------- Fictitious demo company ----------

_FIRST_NAMES = ["Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabi", "Heitor", "Iara", "João"]
_STATIONS = {1: ["Tucuruvi", "Santana", "Jabaquara", "Paraíso"], 3: ["Corinthians-Itaquera", "Tatuapé", "Penha", "Brás"]}


def _demoAssignments(day: str) -> list[dict]:
    items = []
    windows = cycle(["07:00", "08:00", "08:00", "09:30", "10:30"])
    for teamIndex, teamName in enumerate(["Financeiro", "Tecnologia"]):
        for index, firstName in enumerate(_FIRST_NAMES):
            lineNumber = 3 if index % 2 == 0 else 1
            employeeId = f"F{teamIndex + 1}{index:03d}"
            items.append(
                {
                    "assignmentId": f"as-{day}-{employeeId}",
                    "employeeId": employeeId,
                    "name": f"{firstName} Exemplo",
                    "email": f"{firstName.lower()}.{teamName.lower()}@empresaficticia.com.br",
                    "teamName": teamName,
                    "lineNumber": lineNumber,
                    "boardingStation": _STATIONS[lineNumber][index % 4],
                    "date": day,
                    "entryWindow": next(windows),
                    "allowedEntryWindows": DEFAULT_WINDOWS,
                    "suggestedDepartureTime": "",
                    "predictedCrowding": "moderate",
                }
            )
    return items


# ---------- Auth ----------


def _checkKey(apiKey: str | None) -> None:
    if API_KEY and apiKey != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid X-Api-Key")


# ---------- Contract endpoints ----------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scheduleImports", status_code=201)
async def createScheduleImport(request: Request, idempotencyKey: str = Header(alias="Idempotency-Key"), apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    if idempotencyKey in store["imports"]:
        return JSONResponse(store["imports"][idempotencyKey], status_code=200)
    payload = await request.json()
    scheduleId = f"sch-{uuid4().hex[:8]}"
    store["schedules"][scheduleId] = {"scheduleId": scheduleId, "version": 1, "week": payload["week"], "status": "pendingApproval", "assignments": [], "source": payload}
    result = {"importId": f"imp-{uuid4().hex[:8]}", "scheduleId": scheduleId, "status": "pendingApproval", "receivedEmployees": len(payload.get("employees", []))}
    store["imports"][idempotencyKey] = result
    return result


@app.get("/schedules")
def listSchedules(status: str, dispatched: bool | None = None, apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    return [{key: value for key, value in item.items() if key != "source"} for item in store["schedules"].values() if item["status"] == status]


@app.get("/assignments")
def listAssignments(date: str, lineNumber: int | None = None, apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    items = _demoAssignments(date)
    return [item for item in items if lineNumber is None or item["lineNumber"] == lineNumber]


@app.post("/lineStatus", status_code=204)
async def publishLineStatus(request: Request, apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    store["lineStatus"] = await request.json()


@app.get("/lineStatus")
def getLineStatus():
    if not store["lineStatus"]:
        raise HTTPException(status_code=404, detail="No snapshot yet")
    return store["lineStatus"]


@app.post("/alerts", status_code=201)
async def createAlert(request: Request, apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    payload = await request.json()
    existing = store["alerts"].get(payload["dedupeKey"])
    if existing:
        return JSONResponse(existing, status_code=200)
    alert = {**payload, "alertId": f"alert-{uuid4().hex[:8]}"}
    store["alerts"][payload["dedupeKey"]] = alert
    return alert


def _planKey(plan: dict) -> tuple:
    """Dedupe key from the contract: same alert, team, action and new window = same plan."""
    return (plan["alertId"], plan["teamName"], plan["action"], plan.get("newEntryWindow"))


@app.post("/contingencyPlans", status_code=201)
async def createContingencyPlan(request: Request, apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    payload = await request.json()
    for plan in store["contingencyPlans"].values():
        if _planKey(plan) == _planKey(payload):
                return JSONResponse(plan, status_code=200)
    allAssignments = {item["assignmentId"]: item for item in _demoAssignments(payload["date"])}
    plan = {
        **payload,
        "planId": f"plan-{uuid4().hex[:8]}",
        "status": "pendingApproval",
        "affected": [allAssignments[item] for item in payload["assignmentIds"] if item in allAssignments],
    }
    store["contingencyPlans"][plan["planId"]] = plan
    return plan


@app.get("/contingencyPlans")
def listContingencyPlans(status: str, dispatched: bool | None = None, apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    return [plan for plan in store["contingencyPlans"].values() if plan["status"] == status]


@app.post("/dispatches", status_code=204)
async def reportDispatches(request: Request, apiKey: str | None = Header(default=None, alias="X-Api-Key")):
    _checkKey(apiKey)
    store["dispatches"].append(await request.json())


# ---------- Demo helpers (not part of the contract): simulate HR actions ----------


@app.post("/admin/contingencyPlans/{planId}/{decision}")
def decideContingencyPlan(planId: str, decision: str):
    plan = store["contingencyPlans"].get(planId)
    if not plan or decision not in ("approve", "reject"):
        raise HTTPException(status_code=404)
    plan["status"] = "approved" if decision == "approve" else "rejected"
    return RedirectResponse("/", status_code=303)


@app.post("/admin/schedules/{scheduleId}/{decision}")
def decideSchedule(scheduleId: str, decision: str):
    schedule = store["schedules"].get(scheduleId)
    if not schedule or decision not in ("approve", "reject"):
        raise HTTPException(status_code=404)
    schedule["status"] = "approved" if decision == "approve" else "rejected"
    return RedirectResponse("/", status_code=303)


@app.post("/admin/reset")
def reset():
    for key in ("imports", "schedules", "alerts", "contingencyPlans"):
        store[key].clear()
    store["dispatches"].clear()
    store["lineStatus"] = None
    return RedirectResponse("/", status_code=303)


_STATUS_LABELS = {"normal": "Normal", "degraded": "Lentidão", "stopped": "Paralisada", "closed": "Encerrada", "unknown": "Desconhecida"}
_SCHEDULE_LABELS = {"pendingApproval": "Aguardando aprovação", "approved": "Aprovada", "rejected": "Recusada"}
_ACTION_LABELS = {"remoteWork": "Trabalho remoto", "shiftEntryWindow": "Mudar horário de entrada"}


@app.get("/", response_class=HTMLResponse)
def panel():
    """Minimal page that makes the integration visible in the video (stands in for the app screens)."""
    snapshot = store["lineStatus"]
    lineRows = "".join(
        f"<tr><td>Linha {line['lineNumber']}-{escape(line['lineName'])}</td><td class='{line['status']}'>{_STATUS_LABELS.get(line['status'], line['status'])}</td><td>{escape(line['rawText'])}</td></tr>"
        for line in (snapshot["lines"] if snapshot else [])
    )
    alertRows = "".join(
        f"<tr><td>{escape(alert['detectedAt'][11:16])}</td><td>{escape(alert['message'])}</td></tr>" for alert in reversed(list(store["alerts"].values()))
    )
    planRows = "".join(
        f"<tr><td>{escape(plan['teamName'])}</td><td>{_ACTION_LABELS[plan['action']]}{' → ' + plan['newEntryWindow'] if plan.get('newEntryWindow') else ''}</td>"
        f"<td>{len(plan['assignmentIds'])}</td><td>{escape(plan['reason'])}</td><td>{plan['status']}</td>"
        f"<td>{_decisionButtons('contingencyPlans', plan['planId']) if plan['status'] == 'pendingApproval' else ''}</td></tr>"
        for plan in store["contingencyPlans"].values()
    )
    scheduleRows = "".join(
        f"<tr><td>{escape(item['source']['companyName'])}</td><td>{escape(item['week'])}</td><td>{len(item['source']['employees'])}</td>"
        f"<td>{item['source'].get('rejectedRows', 0)}</td><td>v{item['version']}</td><td>{_SCHEDULE_LABELS.get(item['status'], item['status'])}</td>"
        f"<td>{_decisionButtons('schedules', item['scheduleId']) if item['status'] == 'pendingApproval' else ''}</td></tr>"
        for item in reversed(list(store["schedules"].values()))
    )
    staleNote = "<p class='stale'>Atenção: dados desatualizados (fonte indisponível).</p>" if snapshot and snapshot.get("stale") else ""
    collected = f"Atualizado em {escape(snapshot['collectedAt'])} · fonte: {escape(snapshot['source'])}" if snapshot else "Nenhuma leitura recebida ainda."
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta http-equiv="refresh" content="10">
<title>ForaDoPico · Mock API</title><style>
body{{font-family:system-ui,sans-serif;margin:24px;max-width:1000px;color:#1b1b1b}} table{{border-collapse:collapse;width:100%;margin-bottom:24px}}
td,th{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left}} .normal{{color:#0a7d2c}} .degraded{{color:#b26b00}} .stopped{{color:#b00020;font-weight:600}}
.stale{{background:#fff3cd;padding:8px}} form{{display:inline}} button{{margin-right:4px}}</style></head><body>
<h1>ForaDoPico · painel do mock da API</h1><p>{collected}</p>{staleNote}
<h2>Escalas importadas (aprovação do RH)</h2><table><tr><th>Empresa</th><th>Semana</th><th>Funcionários</th><th>Linhas recusadas</th><th>Versão</th><th>Status</th><th></th></tr>{scheduleRows}</table>
<h2>Situação das linhas</h2><table><tr><th>Linha</th><th>Status</th><th>Texto do Metrô</th></tr>{lineRows}</table>
<h2>Alertas</h2><table><tr><th>Hora</th><th>Mensagem</th></tr>{alertRows}</table>
<h2>Planos B (aprovação do RH)</h2><table><tr><th>Time</th><th>Ação</th><th>Pessoas</th><th>Motivo</th><th>Status</th><th></th></tr>{planRows}</table>
<form method="post" action="/admin/reset"><button>Limpar dados do mock</button></form></body></html>"""


def _decisionButtons(resource: str, itemId: str) -> str:
    return (
        f"<form method='post' action='/admin/{resource}/{itemId}/approve'><button>Aprovar</button></form>"
        f"<form method='post' action='/admin/{resource}/{itemId}/reject'><button>Recusar</button></form>"
    )
