# Testes e validação (etapa 07)

Há duas camadas de testes, e as duas cobrem cenários de **sucesso**, **decisão** e **falha**:

| Camada | O que roda | Como executar | Evidência |
|---|---|---|---|
| Testes automatizados | 81 testes com pytest, sem rede e sem envio de e-mail, usando adaptadores falsos | `pytest -v` | [evidence/pytestReport.txt](evidence/pytestReport.txt) |
| Execução de ponta a ponta | Os 3 fluxos rodando pela linha de comando contra o mock da API, com planilhas fictícias e falhas provocadas | `bash tools/collectEvidence.sh` | [evidence/scenarioRun.txt](evidence/scenarioRun.txt), [../logs/samples/robotSample.log](../logs/samples/robotSample.log) e prints em [../assets/](../assets/) |

## Cenários do PDD e onde cada um é verificado

| Tipo | Cenário (PDD, seção 8) | Teste automatizado | Na execução de ponta a ponta |
|---|---|---|---|
| Sucesso | Planilha válida com 2 times e 20 funcionários | `testValidSpreadsheetIsSentArchivedAndLanded` | `scheduleValid.xlsx` importada via outbox |
| Sucesso | Escala aprovada pelo RH | `testApprovedScheduleSendsOneEmailPerEmployeeWithIcs` | 20 agendas enviadas (`assets/agendaEmail.png`) |
| Decisão | Planilha com 2 linhas inválidas em 20 (10%) | `testTenPercentInvalidAcceptsValidRowsAndReportsTheOthers` | `assets/hrReportAcceptedWithIssues.png` |
| Decisão | Planilha com 30% de linhas inválidas | `testThirtyPercentInvalidRejectsWholeFile` | `assets/hrReportRejected.png` |
| Decisão | Mesma versão da escala em duas execuções (RN11) | `testSameVersionIsNotSentTwice` | Segunda execução sem envios |
| Decisão | RH edita a escala (versão 2) | `testNewVersionIsSentAgainAsUpdate` | `assets/updatedAgendaEmail.png` |
| Decisão | Linha 3 passa para "Paralisada" | `testStoppedLineCreatesAlertAndRemotePlanPerTeam` | Planos "Trabalho remoto" (`assets/mockPanelPlanBPending.png`) |
| Decisão | Linha 1 em "Velocidade Reduzida" | `testDegradedLineProposesLaterEntryWindow` | Planos "Mudar horário → 10:30" e `assets/shiftedEntryEmail.png` |
| Decisão | Plano B "remoto" aprovado | `testRemotePlanCancelsTheCalendarEvent` | `assets/remoteWorkEmail.png` |
| Decisão | "Operação Encerrada" às 23h | `testClosedOperationNeverTriggersPlanB` | — |
| Decisão | Mesmo status em duas leituras seguidas (RN13) | `testSameStatusTwiceDoesNotDuplicateAlert` | Leitura das 07:35 sem alerta novo |
| Decisão | Fora da janela de operação (RN17) | `testOutsideOperatingWindowIsSkipped` | Leitura das 23:30 com status `skipped` |
| Falha | Arquivo `.xlsx` corrompido | `testCorruptedFileIsRejectedWithReport` | `scheduleCorrupted.xlsx` em `rejected/` |
| Falha | Aba faltando | `testMissingSheetIsRejected` | `scheduleMissingSheet.xlsx` em `rejected/` |
| Falha | Mesmo arquivo enviado duas vezes | `testSameFileTwiceIsImportedOnce` | `scheduleDemoSmallCopia.xlsx` em `rejected/duplicates/` |
| Falha | API desligada durante a importação | `testApiDownQueuesInOutboxAndDeliversNextRun` | Envio para a outbox e entrega na execução seguinte |
| Falha | Servidor de e-mail fora do ar | `testMailServerDownStopsAndRetriesNextRun` | 3 tentativas, `partial`, envio completo na execução seguinte |
| Falha | Site do Metrô inacessível | `testSourceDownUsesLastKnownStateNotStale`, `testSourceDownForTooLongMarksDataStale` | Leituras das 07:40 e 08:20 (`stale` depois de 30 min) |
| Falha | HTML do Metrô alterado | `testLayoutChangeFailsWithoutPlanB` | — |
| Falha | API recusa os dados (4xx) | `testApiRejectionIsNotRetriedAndFileIsRejected` | — |
| LGPD | Nenhum nome, e-mail ou matrícula nos logs | `testNoPersonalDataInLogsOrLandingZone`, `testLogsHaveNoNamesOrEmails`, `testLogsNeverContainEmployeeIds` | Varredura do `robotSample.log` |

## Arquivos de teste

| Arquivo | Cobre |
|---|---|
| [testScheduleImportRules.py](testScheduleImportRules.py) | Regras da planilha (RN01 a RN09) |
| [testScheduleImportFlow.py](testScheduleImportFlow.py) | Fluxo 1 com disco real em pasta temporária |
| [testAgendaDispatchFlow.py](testAgendaDispatchFlow.py) | Fluxo 2, `.ics` e codificação dos e-mails |
| [testLineStatusRules.py](testLineStatusRules.py) | Regras das linhas (RN12 a RN17) |
| [testLineMonitorFlow.py](testLineMonitorFlow.py) | Fluxo 3 |
| [testMetroWebsiteSource.py](testMetroWebsiteSource.py) | Leitura do HTML real do Metrô (amostra salva), bloqueio e timeout |

A execução de ponta a ponta usa datas fixas da semana fictícia de 23 a 27/11/2026 (`--at`), para dar sempre o mesmo resultado, e não envia e-mail de verdade: usa o modo console e, no cenário de falha, uma porta SMTP inexistente.
