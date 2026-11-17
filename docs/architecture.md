# Arquitetura do robô ForaDoPico RPA

> Decisão válida para o projeto inteiro. Qualquer código novo segue esta estrutura.

## 1. Estilo escolhido: Ports & Adapters (hexagonal)

O núcleo do robô (regras de negócio e fluxos) não conhece planilha, site, API, e-mail nem banco. Ele conversa apenas com **portas** (interfaces). Cada tecnologia externa é um **adaptador** que implementa uma porta.

**Por que essa arquitetura atende melhor à disciplina de RPA:**

| Exigência da disciplina | Como a arquitetura ajuda |
|---|---|
| 04 Exceções e resiliência | Toda falha externa nasce num adaptador e vira uma exceção de domínio conhecida (`SourceUnavailableError`, `ApiUnavailableError`...). O fluxo decide o que fazer, e nenhuma falha passa em silêncio. |
| 06 Integração com o MVP | A porta `ProductApiPort` tem três adaptadores trocáveis por variável de ambiente: `real` (API do Pedro), `mock` (API falsa local) e `file` (JSON estruturado). |
| 07 Testes (sucesso, decisão, falha) | Os testes usam adaptadores falsos, sem rede e sem site real, e cada cenário é reproduzível. |
| Demonstração em vídeo | A porta `LineStatusSourcePort` tem um adaptador `simulated` que força "Paralisada" para mostrar o plano B. |

## 2. Camadas

```
src/
├── domain/           Entidades, regras de negócio puras e exceções de domínio
├── application/      Fluxos (casos de uso): orquestram as regras chamando portas
│   └── ports/        Interfaces (contratos) que os adaptadores implementam
├── adapters/
│   ├── inbound/      Fontes de entrada: planilha .xlsx, site do Metrô
│   └── outbound/     Saídas: API do produto, e-mail, pasta de pouso, estado local
├── infrastructure/   Configuração, logs, retry, ids de execução
└── main.py           CLI: escolhe o fluxo e injeta os adaptadores
```

Regra de dependência: `domain` ← `application` ← `adapters` / `infrastructure` ← `main`. Uma camada interna nunca importa uma externa.

## 3. Fluxos (robôs)

| Fluxo | Gatilho | Resumo |
|---|---|---|
| `scheduleImportFlow` | Agendado (a cada 5 min) ou manual | Lê planilhas do RH, valida, envia à API e grava na pasta de pouso |
| `agendaDispatchFlow` | Agendado (a cada 10 min) | Busca escalas e planos B **aprovados pelo RH**, gera a agenda (.ics) e envia por e-mail |
| `lineMonitorFlow` | Agendado (a cada 5 min, dias úteis) | Lê a situação das linhas, detecta mudanças, cria alertas e propõe o plano B |

Detalhes no [processDesign.md](processDesign.md).

## 4. Portas e adaptadores

| Porta | Adaptadores | Selecionado por |
|---|---|---|
| `SpreadsheetReaderPort` | `botcityExcelReader` (plugin `botcity-excel-plugin`) | — |
| `OrchestratorPort` | `maestroOrchestrator` (BotCity Maestro SDK; offline quando roda localmente) | Argumentos do BotCity Runner |
| `InputFolderPort` | `localInputFolder` (`data/input/`, `processed/`, `rejected/`) | `INPUT_DIR` |
| `ImportReportPort` | `xlsxImportReport` (relatório do RH) | `REPORT_DIR` |
| `LineStatusSourcePort` | `metroWebsiteSource` (raspagem), `simulatedSource` (fixture) | `LINE_STATUS_SOURCE` |
| `ProductApiPort` | `httpProductApi` (real ou mock), `fileProductApi` | `PRODUCT_API_MODE` |
| `NotificationPort` | `SmtpNotifier` (Mailtrap) e `ConsoleNotifier` (salva `.eml`), em `emailNotifiers.py` | `NOTIFIER_MODE` |
| `CalendarPort` | `icalendarCalendar` (`.ics` RFC 5545) | — |
| `LandingZonePort` | `localLandingZone` (pasta `chegada/` do Big Data) | `LANDING_ZONE_PATH` |
| `RobotStatePort` | `sqliteRobotState` | `STATE_DB_PATH` |

`RobotStatePort` guarda o estado interno do robô: hashes de arquivos já processados, último status de cada linha, chaves de deduplicação e a **outbox**, que é a fila de envios pendentes quando a API está fora do ar.

## 5. Stack

| Necessidade | Biblioteca | Motivo |
|---|---|---|
| Linguagem | Python 3.13 | Mesma linguagem da API, dos dados e da IA do grupo |
| Leitura de .xlsx | `botcity-excel-plugin` (BotCity) | Plugin do repositório aberto da BotCity, visto em aula. O openpyxl fica só para gravar o relatório formatado do RH |
| Validação | Regras próprias no `domain` | Mensagens em português por aba, linha e coluna, prontas para o relatório do RH (o pydantic entra só via FastAPI no mock) |
| HTTP | httpx | Timeout explícito, cliente usado também nos testes |
| Retry | tenacity | Backoff exponencial declarativo |
| Raspagem | beautifulsoup4 | HTML do Metrô |
| Agenda | icalendar | Gera .ics compatível com Google, Outlook e celular |
| Orquestração | BotCity Maestro (`botcity-maestro-sdk`) + template Custom da BotCity (`bot.py`, `build.*`, `.botproj`) | Em produção, o Maestro agenda as tarefas, o Runner executa o `bot.py`, e o robô devolve status, contagem de itens, alertas, artefatos e lê as senhas do cofre de credenciais |
| Agendamento local | APScheduler | Alternativa sem Maestro: roda os 3 fluxos num único processo (`python -m src.main scheduler`) |
| Estado | sqlite3 (stdlib) | Sem servidor; arquivo único |
| Mock da API | FastAPI + uvicorn | Mesmo framework da API real (decisão do grupo) |
| Testes | pytest | `python_files = test*.py` para manter camelCase |

## 6. Aderência ao conteúdo da disciplina (BotCity)

| Conteúdo da aula | Como aparece no robô |
|---|---|
| Template Python da BotCity (cookiecutter, tipo **Custom**) | `bot.py` na raiz com `BotMaestroSDK.from_sys_args()`, `RAISE_NOT_CONNECTED = False`, `get_execution()` e `finish_task(...)`; `build.bat`/`build.ps1`/`build.sh`; `foraDoPicoRpa.botproj` |
| BotCity Maestro: orquestração e gestão | Tarefa com parâmetro `flow`; `finish_task` com `SUCCESS`/`PARTIALLY_COMPLETED`/`FAILED` e `total_items`/`processed_items`/`failed_items`; `alert` para o time de operação; `post_artifact` com o relatório do RH e o log; `error` em falha inesperada; `get_credential` para as senhas |
| Repositório aberto de plugins | `botcity-excel-plugin` lê a planilha do RH |
| BotCity Runner | Executa o `bot.py` em cada tarefa, recebendo servidor, tarefa e token por argumento |

O que **não** foi trocado, e por quê:

| Conteúdo da aula | Motivo |
|---|---|
| `botcity-email-plugin` | O remetente seria o usuário do login SMTP (no Mailtrap, um código), e todo anexo iria como `application/octet-stream`. O `.ics` deixaria de ser convite e o plano B não cancelaria mais o evento. O adaptador próprio usa a mesma biblioteca padrão (`smtplib`) com MIME correto |
| `botcity-http-plugin` | Não aceita timeout nem cabeçalhos, então não daria para enviar `X-Api-Key`, `Idempotency-Key` e o User-Agent do robô. Ficou o `httpx`, com timeout de 15 s |
| `botcity-framework-web` (WebBot) e `botcity-framework-core` (desktop) | Servem para automatizar telas. O processo não tem tela: a página do Metrô é HTML estático, lido com uma requisição. Abrir um navegador só adicionaria dependência e instabilidade. É exatamente o caso do tipo de projeto **Custom** do template |
| pywinauto / Accessibility Insights (MyCRM, ContosoInvoicing) | Automação de aplicativo desktop Windows. Nenhuma etapa do processo usa um aplicativo desktop |
| n8n | O enunciado aceita Python, e a solução é Python versionado e testado. Ligar um fluxo n8n agora seria uma segunda plataforma sem ganho para o processo |

## 7. Convenções

- Pastas e arquivos em inglês, camelCase (`lineMonitorFlow.py`). Exceções impostas por ferramentas: `README.md`, `requirements.txt`, `Dockerfile`, `.env.example`, `pyproject.toml`.
- Código: funções e variáveis em camelCase, classes em PascalCase; campos JSON e paths da API em camelCase.
- Logs internos em inglês e textos ao usuário (RH, funcionário, planilhas, e-mails) em português. Os dois sempre começam com letra maiúscula.

## 8. Segurança e LGPD

- Credenciais (API key, SMTP) só em `.env`, que nunca é versionado; o `.env.example` vai sem valores.
- Os logs nunca contêm nome, e-mail ou estação. O funcionário aparece como `employeeRef`, um hash SHA-256 da matrícula com salt, truncado em 12 caracteres.
- Todas as planilhas de exemplo do repositório são fictícias (geradas com Faker pt_BR).
- Os arquivos gravados na pasta de pouso do Big Data contêm dados pessoais e por isso ficam fora do Git (`.gitignore`). O mascaramento acontece na camada Ouro, sob responsabilidade do Big Data.
