# Roteiro do vídeo (até 3 minutos)

O roteiro tem três partes:

1. **Preparação:** o que deixar pronto antes de gravar.
2. **Roteiro de vídeo:** o que fazer e o que mostrar na tela, cena por cena.
3. **Roteiro de áudio:** a narração, cena por cena.

O caminho mais simples é gravar a tela primeiro, sem falar. Depois grave a narração lendo a parte 3 e junte as duas no editor, por exemplo o Clipchamp, que já vem no Windows. No editor, acelere as esperas: o envio dos e-mails e a queda da API.

Os fluxos rodam pelo **terminal 2**, com os mesmos comandos que o BotCity Maestro executa em produção. O plano gratuito da BotCity limita o número de tarefas, e esse limite já foi usado na configuração. Por isso, o Maestro aparece só no fim do vídeo, com as tarefas que já rodaram.

## O que o enunciado exige e onde aparece

| Exigência | Cena |
|---|---|
| Apresentação do problema e do papel da automação | 1 |
| Execução do processo de ponta a ponta, na prática | 2 a 6 |
| Regra de decisão | 2 (planilha com 10% de erro é aceita) e 5 (só quem ainda não embarcou entra no plano B) |
| Integração com o MVP | 3 e 5 (painel da API) e 4 e 6 (e-mails) |
| Tratamento de falhas | 7 (API fora do ar, fila e reenvio automático) |

---

# Parte 1 · Preparação

Faça uma vez antes do ensaio e repita antes da gravação.

### 1.1 Dois PowerShell abertos na pasta do projeto
Abra dois PowerShell. Em cada um, rode:
```
cd C:\Users\Matheus\Desktop\SemestralRpa
.venv\Scripts\activate
```

- **Terminal 1, a API:** rode `uvicorn mockApi.app:app --port 8000` e deixe aberto. Ele só aparece no vídeo na cena 7.
- **Terminal 2, os comandos:** aumente a fonte com **Ctrl + roda do mouse**.

### 1.2 Limpar os dados das execuções anteriores
1. No **terminal 1**, pare a API com **Ctrl+C**.
2. No **terminal 2**, rode:
   ```
   Remove-Item -Recurse -Force data\runtime, data\input, data\output -ErrorAction SilentlyContinue
   New-Item -ItemType Directory -Force data\input | Out-Null
   python -m src.main simulate
   ```
   O `New-Item` recria a pasta de entrada vazia; sem ela, o `copy` da cena 2 falha com "O nome do diretório é inválido".
3. No **terminal 1**, suba a API de novo: `uvicorn mockApi.app:app --port 8000`.

**Importante:** a API de demonstração guarda os dados só na memória, mas o robô lembra os arquivos que já importou (`data\runtime`). Depois deste passo, só derrube a API na cena 7. Se precisar reiniciar a API em qualquer outro momento, refaça este passo 1.2 inteiro. Senão, a API fica vazia e o robô recusa as planilhas como repetidas (`rejected\duplicates`).

### 1.3 Mailtrap vazio
1. No Mailtrap, abra **Sandboxes** → **My Sandbox**.
2. Apague os e-mails antigos com o ícone de lixeira.

O vídeo usa 4 e-mails da cota gratuita.

### 1.4 Abas do navegador, nesta ordem
1. **GitHub:** https://github.com/haruoooo/SemestralRpa (README).
2. **BPMN:** https://github.com/haruoooo/SemestralRpa/blob/main/assets/bpmnScheduleImportFlow.png
3. **Painel da API:** http://127.0.0.1:8000/
4. **Mailtrap:** My Sandbox.
5. **Maestro:** Orquestrador → **Tarefas**, usada só na cena 8.

### 1.5 Gravação
- Use a **Ferramenta de Captura** do Windows (**Win+Shift+R** → selecione a tela inteira) ou o OBS.
- Deixe a tela limpa: feche notificações e outras janelas.
- Faça um **ensaio completo**. Depois repita os passos 1.2 e 1.3 e grave.

---

# Parte 2 · Roteiro de vídeo

### Cena 1 · Abertura (0:00–0:15)
**Faça:**
1. Mostre a aba **GitHub** no topo do README e role devagar até a tabela dos três fluxos.
2. Troque para a aba **BPMN**.

**Precisa aparecer:** o título "ForaDoPico · RPA", os integrantes, a tabela dos 3 fluxos e o diagrama BPMN.

### Cena 2 · Importação da planilha (0:15–0:50)
**Faça:**
1. No **terminal 2**, digite:
   ```
   New-Item -ItemType Directory -Force data\input | Out-Null
   copy data\fixtures\scheduleDemoSmall.xlsx data\input\
   copy data\fixtures\scheduleTenPercentInvalid.xlsx data\input\
   ```
2. Ainda no **terminal 2**, rode o robô:
   ```
   python -m src.main scheduleImport
   ```
   Ele termina em 1 ou 2 segundos com "Schedule import finished with status success".
3. No Explorador de Arquivos, abra `C:\Users\Matheus\Desktop\SemestralRpa\data\output\reports` e dê dois cliques em **`importReport683c568b.xlsx`**, o relatório da planilha com erros.
4. No Excel, clique na aba **Linhas recusadas**.

**Precisa aparecer:**
- os comandos de cópia e o robô rodando, com as linhas "RowRefused" (as duas recusas) e o "status success";
- no Excel, as 2 linhas recusadas com o motivo: e-mail inválido na linha 11 e estação inválida na linha 21.

### Cena 3 · A escala chega ao MVP e o RH aprova (0:50–1:05)
**Faça:**
1. Vá para a aba **Painel da API** e aperte **F5**.
2. Passe o mouse sobre a tabela **Escalas importadas**. Há duas linhas, com 18 e com 3 funcionários, as duas "Aguardando aprovação".
3. Clique em **Aprovar** na linha com **3** funcionários. Aperte o botão logo depois do **F5**: o painel não se atualiza sozinho, e um botão de uma página antiga não aprova nada.
4. Confira se a linha virou **Aprovada** e se o botão mudou para "Simular edição do RH". Sem isso, a cena 4 não envia nenhum e-mail.

**Precisa aparecer:**
- a linha de 18 funcionários com **2** em "Linhas recusadas";
- a linha de 3 funcionários mudando para **Aprovada**.

### Cena 4 · Envio das agendas (1:05–1:30)
**Faça:**
1. No **terminal 2**, rode:
   ```
   python -m src.main agendaDispatch
   ```
   Ele envia um e-mail a cada 10 segundos e termina com "status success".
2. Na aba **Mailtrap**, atualize a página. Chegam 3 e-mails, para Ana, Bruno e Carla.
3. Abra o e-mail da **Ana**: "Sua agenda presencial: Terça, 24/11 a Quinta, 26/11 · ForaDoPico".
4. Mostre o texto e o anexo **agenda.ics**.

**Precisa aparecer:**
- os 3 e-mails na caixa;
- no e-mail da Ana, "entrada às 10:30 · saia de casa às 09:35 · embarque em Corinthians-Itaquera (Linha 3-Vermelha)";
- o anexo `agenda.ics`.

### Cena 5 · A Linha 3 para e o robô propõe o plano B (1:30–2:05)
**Faça:**
1. No **terminal 2**, digite:
   ```
   python -m src.main simulate --line 3 --text "Paralisada"
   ```
2. Ainda no **terminal 2**, rode o monitor como se fosse terça-feira, 24/11, às 07:30:
   ```
   python -m src.main lineMonitor --ignoreWindow --at 2026-11-24T07:30
   ```
3. Vá para a aba **Painel da API**, aperte **F5** e role até as três tabelas de baixo.
4. Clique em **Aprovar** no plano B.

**Precisa aparecer:**
- no terminal, "AlertCreated" e "ContingencyPlanProposed";
- em **Situação das linhas**: "Linha 3-Vermelha · Paralisada";
- em **Alertas**: "07:30 · Linha 3-Vermelha paralisada desde 07:30.";
- em **Planos B**: "Financeiro · Trabalho remoto · **1** pessoa · Aguardando aprovação". Depois do clique, o status passa a **Aprovada**.

### Cena 6 · Aviso ao funcionário (2:05–2:20)
**Faça:**
1. No **terminal 2**, rode:
   ```
   python -m src.main agendaDispatch --at 2026-11-24T07:32
   ```
2. Na aba **Mailtrap**, atualize a página e abra o e-mail novo da **Ana**: "Hoje: seu dia presencial virou remoto · ForaDoPico".

**Precisa aparecer:**
- o assunto;
- o texto "Seu dia presencial hoje virou trabalho remoto";
- o anexo `agenda.ics`.

### Cena 7 · Falha: a API do produto cai (2:20–2:45)
**Faça:**
1. Mostre o **terminal 1** e aperte **Ctrl+C**. A API para.
2. No **terminal 2**, digite:
   ```
   copy data\fixtures\scheduleValid.xlsx data\input\
   ```
3. No **terminal 2**, rode:
   ```
   python -m src.main scheduleImport
   ```
   Ele leva uns 15 segundos, tentando 3 vezes, e termina com "ImportQueued" e "status partial".
4. No **terminal 1**, suba a API de novo: `uvicorn mockApi.app:app --port 8000`.
5. No **terminal 2**, rode o mesmo comando de novo:
   ```
   python -m src.main scheduleImport
   ```
   Agora aparecem "OutboxDelivered" e "status success".
6. Na aba **Painel da API**, aperte **F5**.

**Precisa aparecer:**
- o **Ctrl+C** derrubando a API;
- "ImportQueued" e "status partial" na primeira execução;
- a API voltando;
- "OutboxDelivered" e "status success" na segunda;
- no painel, uma escala nova com **20** funcionários, que é a planilha guardada na fila e entregue sozinha.

### Cena 8 · Produção no BotCity Maestro e encerramento (2:45–3:00)
**Faça:**
1. Na aba **Maestro**, mostre a lista de **Tarefas**, com as execuções do robô pelo Runner e os status **Sucesso**.
2. Na aba **GitHub**, abra a pasta `tests` para mostrar o `README.md` com o mapa de testes.

**Precisa aparecer:** as tarefas com **Sucesso** no Maestro, com o Runner `foraDoPicoRunner`, e o repositório.

---

# Parte 3 · Roteiro de áudio

Leia num ritmo calmo. Cada trecho tem mais ou menos o tamanho da cena.

**Cena 1 (0:00–0:15)**
> "O ForaDoPico monta a escala presencial das empresas fugindo do pico do metrô de São Paulo. Por trás do produto, o RH fazia tudo à mão. O nosso robô automatiza três processos: importa a escala, envia as agendas e monitora as linhas do metrô. Cada fluxo segue o PDD e o BPMN."

**Cena 2 (0:15–0:50)**
> "O RH salva as planilhas na pasta de entrada e o robô entra em ação. Ele valida cada linha: e-mail, estação da linha certa e horários. A segunda planilha tem 10% de linhas com erro. Como está abaixo do limite de 20%, as linhas válidas seguem, e o RH recebe este relatório com a linha e o motivo de cada recusa. Acima de 20%, o arquivo inteiro seria rejeitado."

**Cena 3 (0:50–1:05)**
> "As escalas chegaram à API do produto e aguardam o RH. O robô nunca publica nada sozinho: quem aprova é uma pessoa."

**Cena 4 (1:05–1:30)**
> "Com a escala aprovada, o robô envia a cada funcionário os dias presenciais, o horário de entrada fora do pico e a hora de sair de casa, com o convite para o calendário. Cada pessoa recebe cada versão da escala uma única vez."

**Cena 5 (1:30–2:05)**
> "Terça-feira, 7 e meia da manhã: a Linha 3 para. O robô lê a situação no site do Metrô, registra o alerta e propõe um plano B por time. Repare que só entra uma pessoa: a Ana, que entraria às 10:30. A Carla entraria às 7 e já está a caminho, então fica de fora. O plano B também espera a aprovação do RH."

**Cena 6 (2:05–2:20)**
> "Aprovado o plano, a Ana recebe o aviso antes de sair de casa. O anexo cancela o compromisso no calendário dela, em vez de criar outro."

**Cena 7 (2:20–2:45)**
> "E se a API do produto cair? O robô tenta três vezes, guarda o envio numa fila e encerra a execução como parcial. Nada se perde. Quando a API volta, a próxima execução entrega a escala sozinha."

**Cena 8 (2:45–3:00)**
> "Em produção, o robô roda no BotCity Maestro: cada fluxo é uma tarefa agendada, executada pelo Runner e registrada com seu status. Tudo também fica em log de auditoria, sem dados pessoais. O projeto tem 108 testes automatizados de sucesso, decisão e falha, e está todo no GitHub. Obrigado."

---

## Depois de gravar
1. Publique no YouTube como **Não listado**, ou no Google Drive com **qualquer pessoa com o link pode ver**.
2. Teste o link numa janela anônima.
3. Me passe o link para eu colocá-lo no README e no relatório.

## Os mesmos fluxos no BotCity Maestro
Em produção, cada comando do terminal 2 é uma tarefa do Maestro:

| Comando no terminal 2 | Tarefa no Maestro |
|---|---|
| `python -m src.main scheduleImport` | `flow` = `scheduleImport` |
| `python -m src.main agendaDispatch` | `flow` = `agendaDispatch` |
| `python -m src.main lineMonitor --ignoreWindow --at 2026-11-24T07:30` | `flow` = `lineMonitor`, `at` = `2026-11-24T07:30`, `ignoreWindow` = `true` |
| `python -m src.main agendaDispatch --at 2026-11-24T07:32` | `flow` = `agendaDispatch`, `at` = `2026-11-24T07:32` |

A configuração do Maestro está em [maestroSetup.md](maestroSetup.md).

