# Roteiro do vídeo (até 3 minutos)

O enunciado pede três coisas no vídeo:
1. o problema e o papel da automação;
2. a execução de ponta a ponta;
3. uma regra de decisão, a integração com o MVP e o tratamento de falhas.

## Antes de gravar

1. No `.env`, configure `LINE_STATUS_SOURCE=simulated`, `NOTIFIER_MODE=smtp` e `MAIL_MIN_INTERVAL_SECONDS=10`.
2. Apague o estado antigo e prepare a pasta de entrada (PowerShell):
   ```
   Remove-Item -Recurse -Force data\runtime, data\input, data\output -ErrorAction SilentlyContinue
   python -m src.main simulate
   ```
3. Abra a caixa **My Sandbox** do Mailtrap e apague os e-mails antigos. A demonstração gasta cerca de 6 envios: 3 agendas e até 3 avisos.
4. Abra **dois terminais** e o painel do mock em http://127.0.0.1:8000/.
   - Terminal 1: `uvicorn mockApi.app:app --port 8000`
   - Terminal 2: os comandos abaixo, já digitados no histórico para ganhar tempo.
5. Deixe a fonte do terminal grande, para os logs ficarem legíveis no vídeo.

## Roteiro

| Tempo | Na tela | Fala (sugestão) |
|---|---|---|
| 0:00–0:20 | Slide ou README | "O ForaDoPico monta a escala presencial fugindo do pico do metrô. Por trás dele, o RH fazia tudo à mão: planilha, conferência e envio das agendas, e ninguém acompanhava as falhas das linhas. O nosso robô em Python automatiza três processos: importar a escala, enviar as agendas e monitorar as linhas." |
| 0:20–0:30 | BPMN do fluxo 1 (`assets/bpmnScheduleImportFlow.png`) | "Cada fluxo segue o PDD e o BPMN, com decisões, repetições e tratamento de falhas." |
| 0:30–0:55 | Terminal 2: `copy data\fixtures\scheduleDemoSmall.xlsx data\input\` e `copy data\fixtures\scheduleTenPercentInvalid.xlsx data\input\`, depois `python -m src.main scheduleImport` | "O RH solta as planilhas na pasta. O robô valida cada linha. Esta tem 10% de linhas erradas, abaixo do limite de 20%: as linhas válidas seguem e o RH recebe um relatório com a linha e o motivo." Mostre por 2 segundos o `importReport…xlsx` em `data\output\reports`. |
| 0:55–1:10 | Painel do mock | "A escala chegou à API do produto e aguarda o RH. O robô nunca publica nada sem aprovação." Clique em **Aprovar** na escala da Empresa Fictícia com 3 funcionários. |
| 1:10–1:35 | Terminal 2: `python -m src.main agendaDispatch` e, em seguida, o Mailtrap | "Aprovada a escala, o robô envia a agenda de cada funcionário, com o convite para o calendário e a hora de sair de casa." Abra um e-mail e mostre o anexo `agenda.ics`. |
| 1:35–2:05 | Terminal 2: `python -m src.main simulate --line 3 --text "Paralisada"` e `python -m src.main lineMonitor --ignoreWindow --at 2026-11-24T07:30`. Depois, o painel | "Terça-feira, 07:30: a Linha 3 para. O robô lê a situação, cria o alerta e propõe o plano B por time. Só entra quem ainda não embarcou. O plano fica pendente para o RH." Clique em **Aprovar** no plano B. |
| 2:05–2:25 | Terminal 2: `python -m src.main agendaDispatch --at 2026-11-24T07:32` e, em seguida, o Mailtrap | "O funcionário recebe: hoje seu dia presencial virou remoto. O anexo cancela o compromisso no calendário." |
| 2:25–2:50 | Feche o terminal 1 (mock fora do ar). Terminal 2: `copy data\fixtures\scheduleValid.xlsx data\input\` e `python -m src.main scheduleImport` | "E se a API cair? O robô tenta 3 vezes, guarda o envio numa fila e não perde nada." Suba o mock de novo, rode `python -m src.main scheduleImport` e mostre "OutboxDelivered". |
| 2:50–3:00 | `logs\robot….log` ou README | "Tudo fica registrado em log, sem dados pessoais, e há 81 testes automatizados de sucesso, decisão e falha. O código está no GitHub." |

## Depois de gravar

1. Publique o vídeo (YouTube "não listado" ou Google Drive com acesso por link).
2. Me passe o link para eu colocá-lo no README e no PDF e gerar o PDF de novo.
