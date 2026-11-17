# Roteiro do vídeo (até 3 minutos)

Os fluxos rodam como tarefas no **BotCity Maestro**, executadas pelo **BotCity Runner**. O terminal só é usado para preparar os dados (copiar planilhas e simular a falha da linha).

## O que o enunciado exige no vídeo

| Exigência | Onde aparece no roteiro |
|---|---|
| Apresentação do problema e do papel da automação | Cena 1 |
| Execução do processo de ponta a ponta, na prática | Cenas 2 a 6 (planilha → Maestro → API → aprovação → e-mail → falha na linha → plano B → aviso) |
| Demonstração de **regra de decisão** | Cena 2 (RN09: 10% de linhas inválidas, abaixo do limite de 20%) e cena 5 (RN14: só quem ainda não embarcou) |
| Demonstração da **integração com o MVP** | Cenas 3 e 5 (painel da API: escala, alertas e plano B) e cena 4 (e-mail com agenda) |
| Demonstração de **tratamento de falhas** | Cena 7 (API fora do ar → 3 tentativas → tarefa "parcial" e alerta no Maestro → entrega automática) |

## Preparação (fora da gravação)

1. Conclua a configuração do Maestro (seção "Configurar o BotCity Maestro", no fim deste arquivo).
2. No `.env` do projeto, configure:
   ```
   LINE_STATUS_SOURCE=simulated
   NOTIFIER_MODE=smtp
   MAIL_MIN_INTERVAL_SECONDS=10
   ```
3. Limpe o estado de execuções anteriores. Abra o PowerShell na pasta do projeto, com o `.venv` ativado:
   ```
   Remove-Item -Recurse -Force data\runtime, data\input, data\output -ErrorAction SilentlyContinue
   python -m src.main simulate
   ```
4. No Mailtrap, abra **My Sandbox** e apague os e-mails antigos (ícone de lixeira). A gravação gasta 4 envios.
5. Deixe abertos e organizados:
   - **Terminal 1:** `uvicorn mockApi.app:app --port 8000`, o mock da API;
   - **Terminal 2:** para copiar as planilhas e simular a falha, com a fonte grande;
   - **BotCity Runner** aberto (janela do `BotRunner-gui`), conectado;
   - **Navegador, aba 1:** Maestro, na automação `foraDoPicoRpa`;
   - **Navegador, aba 2:** http://127.0.0.1:8000/, o painel;
   - **Navegador, aba 3:** Mailtrap → My Sandbox;
   - **Imagem** `assets/bpmnScheduleImportFlow.png`.
6. Faça um ensaio completo antes, depois repita os passos 3 e 4 e grave.

**Dicas de edição:**
- o Runner leva alguns segundos para pegar cada tarefa;
- o envio dos e-mails espera 10 s entre um e outro;
- a queda da API leva uns 10 s de tentativas.

Acelere esses trechos na edição para caber em 3 minutos.

**Como criar uma tarefa no Maestro durante a gravação:** na automação `foraDoPicoRpa`, clique em **Nova tarefa**, preencha os parâmetros indicados em cada cena e confirme. Deixe os parâmetros não citados em branco.

## Roteiro

### Cena 1 · O problema e o papel do robô (0:00–0:20)
**Tela:** README do GitHub, depois o BPMN do fluxo 1.
**Fala:** "O ForaDoPico monta a escala presencial das empresas fugindo do pico do metrô de São Paulo. Por trás dele, o RH fazia tudo à mão: conferia a planilha, mandava a agenda pessoa por pessoa, e ninguém acompanhava as falhas das linhas. O nosso robô automatiza esses três processos, seguindo o PDD e o BPMN, e roda no BotCity Maestro."

### Cena 2 · Importação pelo Maestro e regra de decisão (0:20–0:55)
**Terminal 2:**
```
copy data\fixtures\scheduleDemoSmall.xlsx data\input\
copy data\fixtures\scheduleTenPercentInvalid.xlsx data\input\
```
**Maestro:** nova tarefa com `flow` = `scheduleImport`. Mostre o Runner pegando a tarefa e a tarefa terminando como concluída.
**Fala:** "O RH salva as planilhas na pasta de entrada, e o Maestro dispara o robô. Ele valida cada linha: estação da linha certa, e-mail, horários. Esta segunda planilha tem 10% de linhas com erro. Como está abaixo do limite de 20%, as linhas válidas seguem e o RH recebe um relatório com a linha e o motivo de cada recusa."
**Mostre por 3 s:** na tarefa, os arquivos anexados. Baixe o `importReport….xlsx` da segunda planilha e abra a aba **Linhas recusadas**.

### Cena 3 · Integração com o MVP e pessoa no circuito (0:55–1:05)
**Tela:** painel, aba 2 (atualize a página).
**Fala:** "As escalas chegaram à API do produto e aguardam o RH. O robô nunca publica nada sem aprovação."
**Ação:** clique em **Aprovar** na escala com **3 funcionários**.

### Cena 4 · Envio das agendas (1:05–1:30)
**Maestro:** nova tarefa com `flow` = `agendaDispatch`.
**Tela:** Mailtrap, aba 3. Abra o e-mail da Ana e mostre o anexo `agenda.ics`.
**Fala:** "Com a escala aprovada, o robô envia a cada funcionário os dias presenciais, o horário de entrada fora do pico e a hora de sair de casa, com o convite para o calendário. Cada pessoa recebe cada versão uma única vez."

### Cena 5 · Linha paralisada e plano B (1:30–2:05)
**Terminal 2:**
```
python -m src.main simulate --line 3 --text "Paralisada"
```
**Maestro:** nova tarefa com `flow` = `lineMonitor`, `at` = `2026-11-24T07:30` e `ignoreWindow` = `true`. Quando terminar, abra **Alertas**: "Monitor das linhas: mudança nas linhas".
**Tela:** painel (atualize): Linha 3 paralisada, alerta e plano B pendente.
**Fala:** "Terça-feira, 07:30: a Linha 3 para. O robô lê a situação, cria o alerta e propõe o plano B por time. A operação é avisada no Maestro. Só entra quem ainda não embarcou: a Carla entraria às 07:00 e já está a caminho, então fica de fora. O plano fica pendente para o RH."
**Ação:** clique em **Aprovar** no plano B.

### Cena 6 · Aviso ao funcionário (2:05–2:20)
**Maestro:** nova tarefa com `flow` = `agendaDispatch` e `at` = `2026-11-24T07:32`.
**Tela:** Mailtrap, com o e-mail "Hoje: seu dia presencial virou remoto".
**Fala:** "A Ana recebe o aviso antes de sair de casa. O anexo cancela o compromisso no calendário dela, em vez de criar outro."

### Cena 7 · Tratamento de falha (2:20–2:45)
**Ação:** feche o mock com **Ctrl+C** no terminal 1.
**Terminal 2:**
```
copy data\fixtures\scheduleValid.xlsx data\input\
```
**Maestro:** nova tarefa com `flow` = `scheduleImport`. Mostre a tarefa como **parcialmente concluída** e o alerta "API fora do ar".
**Fala:** "E se a API do produto cair? O robô tenta 3 vezes, guarda o envio numa fila e avisa a operação no Maestro. Nada se perde."
**Ação:** suba o mock de novo no terminal 1 (`uvicorn mockApi.app:app --port 8000`) e crie outra tarefa com `flow` = `scheduleImport`.
**Fala:** "Assim que a API volta, o envio sai sozinho." Mostre a tarefa concluída. Se der tempo, abra o log anexado e destaque **OutboxDelivered**.

### Cena 8 · Encerramento (2:45–3:00)
**Tela:** a lista de tarefas do Maestro com os status, depois o `tests\README.md`.
**Fala:** "Cada execução fica registrada no Maestro e no log, sem dados pessoais. O projeto tem 102 testes automatizados de sucesso, decisão e falha, e o código está no GitHub."

## Depois de gravar

1. Publique o vídeo no YouTube como **Não listado**, ou no Google Drive com **qualquer pessoa com o link pode ver**.
2. Teste o link numa janela anônima.
3. Me passe o link para eu colocá-lo no README e no PDF e gerar o PDF de novo.

## Se o Maestro der problema na hora

Cada tarefa tem o mesmo efeito de um comando no terminal 2, então dá para gravar sem o Maestro:

| Tarefa no Maestro | Comando equivalente |
|---|---|
| `flow` = `scheduleImport` | `python -m src.main scheduleImport` |
| `flow` = `agendaDispatch` | `python -m src.main agendaDispatch` |
| `flow` = `lineMonitor`, `at` = `2026-11-24T07:30`, `ignoreWindow` = `true` | `python -m src.main lineMonitor --ignoreWindow --at 2026-11-24T07:30` |
| `flow` = `agendaDispatch`, `at` = `2026-11-24T07:32` | `python -m src.main agendaDispatch --at 2026-11-24T07:32` |

## Configurar o BotCity Maestro (uma vez)

Os nomes de menus podem variar um pouco conforme a versão do Maestro.

1. **Conta:** em https://developers.botcity.dev, crie a conta gratuita (**Sign up for Free**, plano Community).
2. **Runner:**
   1. No Maestro, abra o menu lateral e clique em **Download Studio**. Baixe a versão para Windows.
   2. Extraia numa pasta simples, como `C:\BotCity`. Evite `Program Files` e a pasta do projeto.
   3. Rode o `wizard` da pasta extraída. Faça login, conclua a instalação e escolha **Setup Runner** → **Create a New Runner**, com o nome `foraDoPicoRunner`.
   4. Abra `C:\BotCity\conf\conf.bcf` e confira se `server`, `login`, `key` e `machineId` estão preenchidos. Na linha `pythonBinary`, coloque o caminho com barras `/`, porque o arquivo trata `\` como caractere especial:
      ```
      pythonBinary=C:/Users/Matheus/AppData/Local/Programs/Python/Python313/python.exe
      ```
3. **Pasta de trabalho:** num PowerShell, rode o comando abaixo e feche o PowerShell. O Runner descompacta o robô numa pasta própria; esta variável faz o robô usar o `.env`, o `data\` e os `logs\` do projeto.
   ```
   setx FORADOPICO_HOME "C:\Users\Matheus\Desktop\SemestralRpa"
   ```
4. **Senhas:** no plano gratuito, o cofre de credenciais do Maestro não está disponível. O robô lê as senhas do `.env` da pasta de trabalho, que fica fora do pacote. Em plano pago, basta criar no cofre o rótulo `foraDoPico` com as chaves `smtpUser`, `smtpPassword` e `logSalt`, que passam a ter prioridade sobre o `.env`.
5. **Pacote:** na pasta do projeto, rode `.\build.ps1`. Ele gera o `foraDoPicoRpa.zip` sem o `.env`.
6. **Easy Deploy:**
   1. No Maestro, abra **Easy Deploy** e crie a automação.
   2. Preencha:
      - nome `foraDoPicoRpa`;
      - Bot ID `foraDoPicoRpa`;
      - versão `1.0`;
      - tecnologia **Python**;
      - o arquivo `foraDoPicoRpa.zip`;
      - o Runner `foraDoPicoRunner`.
7. **Parâmetros:** na automação, adicione três parâmetros do tipo texto: `flow` (obrigatório), `at` e `ignoreWindow` (opcionais).
8. **Ligar o Runner:** rode `C:\BotCity\BotRunner-gui.bat` e clique em **START**.
9. **Aquecimento:** com o mock da API no ar, crie uma tarefa com `flow` = `lineMonitor`. A primeira execução demora alguns minutos, porque o Runner cria o ambiente Python e instala as dependências. As próximas são rápidas.

   Confira se a tarefa terminou sem erro e se o log dela mostra "Pasta de trabalho".
10. **Agendamento (opcional, não usado no vídeo):** em **Agendamentos**, crie um para cada fluxo: `scheduleImport` a cada 5 min, `agendaDispatch` a cada 10 min e `lineMonitor` a cada 5 min.
