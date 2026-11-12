#!/usr/bin/env bash
# Runs every test scenario of the PDD (success, decision, failure) end to end against the mock API,
# in an isolated folder, and collects the evidence into the repository:
#   logs/samples/      JSON Lines logs of the run (no personal data)
#   tests/evidence/    console transcript and pytest report
#   assets/            screenshots (mock panel, e-mails, HR report, BPMN) and sample files
#   docs/integrations/bigDataDataIntegration/sampleBatch.json
#
# Requirements: Git Bash on Windows (or bash on Linux/macOS), the .venv installed, Microsoft Edge or Chrome
# for the screenshots, internet for the live Metro reading. No e-mail is really sent (console mode and a
# fake SMTP port for the failure scenario).
# Run from the repository root:  bash tools/collectEvidence.sh

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FILE_ROOT="$ROOT"; command -v cygpath > /dev/null && FILE_ROOT="$(cygpath -m "$ROOT")"  # Browser needs C:/... on Windows
PY=".venv/Scripts/python.exe"; [ -x "$PY" ] || PY=".venv/bin/python"
BROWSER="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
[ -x "$BROWSER" ] || BROWSER="$(command -v google-chrome || command -v chromium || echo "")"
E="data/runtime/evidence"
PORT=8000

rm -rf "$E" && mkdir -p "$E/input" assets/emails assets/reports logs/samples tests/evidence
export PYTHONIOENCODING=utf-8 LOG_DIR="$E/logs" STATE_DB_PATH="$E/state.db" INPUT_DIR="$E/input" REPORT_DIR="$E/reports"
export LANDING_ZONE_PATH="$E/landing" MAIL_OUTPUT_DIR="$E/mail" SIMULATED_SCENARIO_PATH="$E/scenario.json"
export NOTIFIER_MODE=console LINE_STATUS_SOURCE=simulated MAIL_MIN_INTERVAL_SECONDS=0 PRODUCT_API_MODE=http
export PRODUCT_API_URL="http://127.0.0.1:$PORT" DISPATCH_LIMIT_PER_RUN=0 RETRY_ATTEMPTS=3

TRANSCRIPT="$E/console.txt"
: > "$TRANSCRIPT"

startMock() {
  ("$PY" -m uvicorn mockApi.app:app --port $PORT > "$E/mock.out" 2>&1 &)
  for _ in $(seq 1 20); do curl -s "http://127.0.0.1:$PORT/health" > /dev/null && return; sleep 1; done
  echo "Mock API did not start" >&2; exit 1
}
stopMock() {
  if command -v powershell > /dev/null; then
    powershell -NoProfile -Command "\$c = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue; if (\$c) { Stop-Process -Id \$c.OwningProcess -Force }"
  else
    pkill -f "uvicorn mockApi.app:app" || true
  fi
  sleep 1
}
step() { printf '\n### %s\n\n' "$1" >> "$TRANSCRIPT"; }
run() {
  echo "\$ python -m src.main $*" >> "$TRANSCRIPT"
  "$PY" -m src.main "$@" >> "$TRANSCRIPT" 2>&1
  echo "(exit code $?)" >> "$TRANSCRIPT"; echo >> "$TRANSCRIPT"
}
api() { curl -s "http://127.0.0.1:$PORT$1"; }
post() { curl -s -o /dev/null -X POST "http://127.0.0.1:$PORT$1"; }
ids() { "$PY" -c "import json,sys; [print(item['$1']) for item in json.load(sys.stdin)]" | tr -d '\r'; }  # Windows Python prints CRLF
shot() {  # shot <file> <height> <url> [width]
  [ -n "$BROWSER" ] && "$BROWSER" --headless --disable-gpu --hide-scrollbars --window-size="${4:-1100}","$2" --screenshot="$ROOT/assets/$1" "$3" 2> /dev/null
}

stopMock; startMock

step "Fluxo 1 · Sucesso, decisão e falha na importação (válida, 10% inválida, 30% inválida, corrompida, sem aba)"
cp data/fixtures/scheduleDemoSmall.xlsx data/fixtures/scheduleTenPercentInvalid.xlsx data/fixtures/scheduleThirtyPercentInvalid.xlsx \
   data/fixtures/scheduleCorrupted.xlsx data/fixtures/scheduleMissingSheet.xlsx "$E/input/"
run scheduleImport
step "Fluxo 1 · Falha: o mesmo arquivo de novo (RN02)"
cp data/fixtures/scheduleDemoSmall.xlsx "$E/input/scheduleDemoSmallCopia.xlsx"
run scheduleImport
step "Fluxo 1 · Falha: API fora do ar durante a importação (EX06, outbox)"
stopMock
cp data/fixtures/scheduleValid.xlsx "$E/input/"
run scheduleImport
step "Fluxo 1 · Recuperação: API de volta, outbox reenviada"
startMock
run scheduleImport
shot mockPanelScheduleImported.png 600 "http://127.0.0.1:$PORT/"

step "Fluxo 2 · Sucesso: RH aprova a escala e o robô envia as agendas"
SCHEDULE_ID=$(api "/schedules?status=pendingApproval" | ids scheduleId | head -1)
post "/admin/schedules/$SCHEDULE_ID/approve"
run agendaDispatch --at 2026-11-20T18:00
step "Fluxo 2 · Decisão: segunda execução não reenvia (RN11)"
run agendaDispatch --at 2026-11-20T18:10
step "Fluxo 2 · Falha: RH edita a escala (versão 2) com o servidor de e-mail fora do ar (EX08)"
post "/admin/scheduleVersions/$SCHEDULE_ID"
NOTIFIER_MODE=smtp SMTP_HOST=127.0.0.1 SMTP_PORT=1 run agendaDispatch --at 2026-11-20T18:20
step "Fluxo 2 · Recuperação: servidor de volta, versão 2 enviada como Agenda atualizada"
run agendaDispatch --at 2026-11-20T18:30

step "Fluxo 3 · Leitura de base (todas as linhas normais)"
run simulate
run lineMonitor --ignoreWindow --at 2026-11-24T07:00
step "Fluxo 3 · Decisão: Linha 3 paralisada e Linha 1 com velocidade reduzida às 07:30"
run simulate --line 3 --text "Paralisada"
run simulate --line 1 --text "Velocidade Reduzida"
run lineMonitor --ignoreWindow --at 2026-11-24T07:30
step "Fluxo 3 · Decisão: mesmo status na leitura seguinte não gera alerta (RN13)"
run lineMonitor --ignoreWindow --at 2026-11-24T07:35
shot mockPanelPlanBPending.png 1500 "http://127.0.0.1:$PORT/"
step "Fluxo 2 · RH aprova os planos B e o robô avisa os funcionários"
for PLAN in $(api "/contingencyPlans?status=pendingApproval" | ids planId); do post "/admin/contingencyPlans/$PLAN/approve"; done
run agendaDispatch --at 2026-11-24T07:37
shot mockPanelAfterApproval.png 1500 "http://127.0.0.1:$PORT/"
step "Fluxo 3 · Falha: site do Metrô fora do ar (EX09) e dados desatualizados após 30 min (RN16)"
run simulate --unavailable
run lineMonitor --ignoreWindow --at 2026-11-24T07:40
run lineMonitor --ignoreWindow --at 2026-11-24T08:20
step "Fluxo 3 · Decisão: fora da janela de operação (RN17)"
run lineMonitor --at 2026-11-24T23:30
step "Fluxo 3 · Leitura real do site do Metrô"
LINE_STATUS_SOURCE=metroWebsite STATE_DB_PATH="$E/liveState.db" run lineMonitor --ignoreWindow
stopMock

# ---------- Collect ----------
cp "$E"/logs/robot*.log logs/samples/robotSample.log
cp "$TRANSCRIPT" tests/evidence/scenarioRun.txt
"$PY" -m pytest -v > tests/evidence/pytestReport.txt 2>&1
findMail() { "$PY" -m tools.renderEvidence find "$E/mail" "$1"; }
FIRST_AGENDA=$(findMail "Sua agenda presencial")
UPDATED_AGENDA=$(findMail "Agenda atualizada")
REMOTE=$(findMail "virou remoto")
SHIFT=$(findMail "entrada mudou")
for pair in "agendaEmail:$FIRST_AGENDA" "updatedAgendaEmail:$UPDATED_AGENDA" "remoteWorkEmail:$REMOTE" "shiftedEntryEmail:$SHIFT"; do
  name="${pair%%:*}"; file="${pair#*:}"
  [ -n "$file" ] || continue
  cp "$file" "assets/emails/$name.eml"
  "$PY" -m tools.renderEvidence eml "$file" "$E/$name.html"
  shot "$name.png" 900 "file:///$FILE_ROOT/$E/$name.html"
done
ACCEPTED_REPORT=$(ls -t "$E"/reports/*.xlsx | while read -r f; do "$PY" -c "import sys; from openpyxl import load_workbook; ws=load_workbook(sys.argv[1])['Resumo']; sys.exit(0 if any(r[1]=='Aceita com linhas recusadas' for r in ws.iter_rows(values_only=True)) else 1)" "$f" && echo "$f" && break; done)
REJECTED_REPORT=$(ls -t "$E"/reports/*.xlsx | while read -r f; do "$PY" -c "import sys; from openpyxl import load_workbook; ws=load_workbook(sys.argv[1])['Linhas recusadas']; sys.exit(0 if ws.max_row > 5 else 1)" "$f" && echo "$f" && break; done)
for pair in "hrReportAcceptedWithIssues:$ACCEPTED_REPORT" "hrReportRejected:$REJECTED_REPORT"; do
  name="${pair%%:*}"; file="${pair#*:}"
  [ -n "$file" ] || continue
  cp "$file" "assets/reports/$name.xlsx"
  "$PY" -m tools.renderEvidence xlsx "$file" "$E/$name.html"
  shot "$name.png" 700 "file:///$FILE_ROOT/$E/$name.html"
done
cp "$(ls "$E"/landing/schedule/*.json | head -1)" docs/integrations/bigDataDataIntegration/sampleBatch.json
for flow in scheduleImportFlow agendaDispatchFlow lineMonitorFlow; do
  size=$(grep -o 'width="[0-9]*" height="[0-9]*"' "docs/bpmn/$flow.svg" | head -1 | tr -dc '0-9 ' )
  shot "bpmn${flow^}.png" "$(echo "$size" | awk '{print $2}')" "file:///$FILE_ROOT/docs/bpmn/$flow.svg" "$(echo "$size" | awk '{print $1}')"
done
echo "Evidências geradas: logs/samples, tests/evidence, assets"
