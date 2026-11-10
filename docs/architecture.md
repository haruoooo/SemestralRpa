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
| `SpreadsheetReaderPort` | `openpyxlSpreadsheetReader` | — |
| `LineStatusSourcePort` | `metroWebsiteSource` (raspagem), `simulatedSource` (fixture) | `LINE_STATUS_SOURCE` |
| `ProductApiPort` | `httpProductApi` (real ou mock), `fileProductApi` | `PRODUCT_API_MODE` |
| `NotificationPort` | `smtpNotifier` (Mailtrap), `consoleNotifier` | `NOTIFIER_MODE` |
| `LandingZonePort` | `localLandingZone` (pasta `chegada/` do Big Data) | `LANDING_ZONE_PATH` |
| `RobotStatePort` | `sqliteRobotState` | `STATE_DB_PATH` |

`RobotStatePort` guarda o estado interno do robô: hashes de arquivos já processados, último status de cada linha, chaves de deduplicação e a **outbox**, que é a fila de envios pendentes quando a API está fora do ar.

## 5. Stack

| Necessidade | Biblioteca | Motivo |
|---|---|---|
| Linguagem | Python 3.13 | Mesma linguagem da API, dos dados e da IA do grupo |
| Leitura de .xlsx | openpyxl | Leve e sem pandas |
| Validação | pydantic v2 | Mensagens de erro por campo, prontas para o relatório do RH |
| HTTP | httpx | Timeout explícito, cliente usado também nos testes |
| Retry | tenacity | Backoff exponencial declarativo |
| Raspagem | beautifulsoup4 | HTML do Metrô |
| Agenda | icalendar | Gera .ics compatível com Google, Outlook e celular |
| Agendamento | APScheduler | Roda os 3 fluxos num único processo |
| Estado | sqlite3 (stdlib) | Sem servidor; arquivo único |
| Mock da API | FastAPI + uvicorn | Mesmo framework da API real (decisão do grupo) |
| Testes | pytest | `python_files = test*.py` para manter camelCase |

## 6. Convenções

- Pastas e arquivos em inglês, camelCase (`lineMonitorFlow.py`). Exceções impostas por ferramentas: `README.md`, `requirements.txt`, `Dockerfile`, `.env.example`, `pyproject.toml`.
- Código: funções e variáveis em camelCase, classes em PascalCase; campos JSON e paths da API em camelCase.
- Logs internos em inglês e textos ao usuário (RH, funcionário, planilhas, e-mails) em português. Os dois sempre começam com letra maiúscula.

## 7. Segurança e LGPD

- Credenciais (API key, SMTP) só em `.env`, que nunca é versionado; o `.env.example` vai sem valores.
- Os logs nunca contêm nome, e-mail ou estação. O funcionário aparece como `employeeRef`, um hash SHA-256 da matrícula com salt, truncado em 12 caracteres.
- Todas as planilhas de exemplo do repositório são fictícias (geradas com Faker pt_BR).
- Os arquivos gravados na pasta de pouso do Big Data contêm dados pessoais e por isso ficam fora do Git (`.gitignore`). O mascaramento acontece na camada Ouro, sob responsabilidade do Big Data.
