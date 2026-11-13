# Roteiro do vídeo (até 3 minutos)

## O que o enunciado exige no vídeo

| Exigência | Onde aparece no roteiro |
|---|---|
| Apresentação do problema e do papel da automação | Cena 1 |
| Execução do processo de ponta a ponta, na prática | Cenas 2 a 6 (planilha → API → aprovação → e-mail → falha na linha → plano B → aviso) |
| Demonstração de **regra de decisão** | Cena 2 (RN09: 10% de linhas inválidas, abaixo do limite de 20%) e cena 5 (RN14: só quem ainda não embarcou) |
| Demonstração da **integração com o MVP** | Cenas 3 e 5 (painel da API: escala, alertas e plano B) e cena 4 (e-mail com agenda) |
| Demonstração de **tratamento de falhas** | Cena 7 (API fora do ar → 3 tentativas → outbox → entrega automática) |

## Preparação (fora da gravação)

1. No `.env`, configure:
   ```
   LINE_STATUS_SOURCE=simulated
   NOTIFIER_MODE=smtp
   MAIL_MIN_INTERVAL_SECONDS=10
   ```
2. Limpe o estado de execuções anteriores. Abra o PowerShell na pasta do projeto, com o `.venv` ativado:
   ```
   Remove-Item -Recurse -Force data\runtime, data\input, data\output -ErrorAction SilentlyContinue
   python -m src.main simulate
   ```
3. No Mailtrap, abra **My Sandbox** e apague os e-mails antigos (ícone de lixeira). A gravação gasta 4 envios.
4. Deixe abertos e organizados:
   - **Terminal 1:** `uvicorn mockApi.app:app --port 8000`, o mock da API;
   - **Terminal 2:** onde você vai digitar os comandos, com a fonte grande;
   - **Navegador, aba 1:** http://127.0.0.1:8000/, o painel;
   - **Navegador, aba 2:** Mailtrap → My Sandbox;
   - **Imagem** `assets/bpmnScheduleImportFlow.png`.
5. Faça um ensaio completo antes, depois repita os passos 2 e 3 e grave.

**Dica de edição:** o envio dos e-mails espera 10 s entre um e outro, e a queda da API leva uns 10 s de tentativas. Acelere esses trechos na edição para caber em 3 minutos.

## Roteiro

### Cena 1 · O problema e o papel do robô (0:00–0:25)
**Tela:** README do GitHub, depois o BPMN do fluxo 1.
**Fala:** "O ForaDoPico monta a escala presencial das empresas fugindo do pico do metrô de São Paulo. Por trás dele, o RH fazia tudo à mão: montava a planilha, conferia, mandava a agenda pessoa por pessoa, e ninguém acompanhava as falhas das linhas. O nosso robô em Python automatiza três processos: importa a escala, envia as agendas e monitora as linhas, propondo um plano B. Cada fluxo segue o PDD e o BPMN, com decisões, repetições e tratamento de falhas."

### Cena 2 · Importação da planilha e regra de decisão (0:25–0:55)
**Terminal 2:**
```
copy data\fixtures\scheduleDemoSmall.xlsx data\input\
copy data\fixtures\scheduleTenPercentInvalid.xlsx data\input\
python -m src.main scheduleImport
```
**Fala:** "O RH salva as planilhas na pasta de entrada. O robô valida cada linha: estação da linha certa, e-mail, horários. Esta segunda planilha tem 10% de linhas com erro. Como está abaixo do limite de 20%, as linhas válidas seguem e o RH recebe um relatório dizendo a linha e o motivo de cada recusa."
**Mostre por 3 s:** o relatório `data\output\reports\importReport….xlsx`, aba **Linhas recusadas**.

### Cena 3 · Integração com o MVP e pessoa no circuito (0:55–1:10)
**Tela:** painel, aba 1 (atualize a página).
**Fala:** "As escalas chegaram à API do produto e aguardam o RH. O robô nunca publica nada sem aprovação."
**Ação:** clique em **Aprovar** na escala com **3 funcionários**.

### Cena 4 · Envio das agendas (1:10–1:35)
**Terminal 2:**
```
python -m src.main agendaDispatch
```
**Tela:** Mailtrap, aba 2. Abra o e-mail da Ana e mostre o anexo `agenda.ics`.
**Fala:** "Com a escala aprovada, o robô envia a cada funcionário os dias presenciais, o horário de entrada fora do pico e a hora de sair de casa, com o convite para o calendário. Cada pessoa recebe cada versão uma única vez."

### Cena 5 · Linha paralisada e plano B (1:35–2:05)
**Terminal 2:**
```
python -m src.main simulate --line 3 --text "Paralisada"
python -m src.main lineMonitor --ignoreWindow --at 2026-11-24T07:30
```
**Tela:** painel (atualize): Linha 3 paralisada, alerta e plano B pendente.
**Fala:** "Terça-feira, 07:30: a Linha 3 para. O robô lê a situação no site do Metrô, cria o alerta e propõe o plano B por time. Só entra quem ainda não embarcou: a Carla entraria às 07:00 e já está a caminho, então fica de fora. O plano fica pendente para o RH."
**Ação:** clique em **Aprovar** no plano B.

### Cena 6 · Aviso ao funcionário (2:05–2:25)
**Terminal 2:**
```
python -m src.main agendaDispatch --at 2026-11-24T07:32
```
**Tela:** Mailtrap, com o e-mail "Hoje: seu dia presencial virou remoto".
**Fala:** "A Ana recebe o aviso antes de sair de casa. O anexo cancela o compromisso no calendário dela, em vez de criar outro."

### Cena 7 · Tratamento de falha (2:25–2:50)
**Ação:** feche o mock com **Ctrl+C** no terminal 1.
**Terminal 2:**
```
copy data\fixtures\scheduleValid.xlsx data\input\
python -m src.main scheduleImport
```
**Fala:** "E se a API do produto cair? O robô tenta 3 vezes e guarda o envio numa fila. Nada se perde."
**Ação:** suba o mock de novo no terminal 1 (`uvicorn mockApi.app:app --port 8000`). Depois, no terminal 2:
```
python -m src.main scheduleImport
```
**Fala:** "Assim que a API volta, o envio sai sozinho." Destaque a linha **OutboxDelivered**.

### Cena 8 · Logs, testes e encerramento (2:50–3:00)
**Tela:** o arquivo `logs\robot<data>.log` ou o `tests\README.md`.
**Fala:** "Tudo fica registrado em log, sem dados pessoais. O projeto tem 81 testes automatizados de sucesso, decisão e falha, e o código está no GitHub."

## Depois de gravar

1. Publique o vídeo no YouTube como **Não listado**, ou no Google Drive com **qualquer pessoa com o link pode ver**.
2. Teste o link numa janela anônima.
3. Me passe o link para eu colocá-lo no README e no PDF e gerar o PDF de novo.
