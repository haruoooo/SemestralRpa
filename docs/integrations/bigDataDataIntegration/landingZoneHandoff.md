# Entrega para Big Data · pasta de pouso da escala

> Origem: robô RPA, fluxo `scheduleImportFlow`. Versão do formato: `schemaVersion = 1`.
> Contato: Matheus Haruo (RPA).

## 1. O que o robô entrega

Cada planilha de escala **aceita** pelo robô gera um lote JSON na pasta de pouso. Planilhas rejeitadas não geram lote.

| Item | Valor |
|---|---|
| Pasta | `LANDING_ZONE_PATH/schedule/` (padrão: `landingZone/chegada/schedule/`) |
| Nome do arquivo | `scheduleYYYYMMDD_HHMMSS_<hash8>.json` (data e hora da importação, horário de São Paulo, e os 8 primeiros caracteres do hash do arquivo de origem) |
| Formato | JSON, UTF-8, um lote por arquivo |
| Gravação | Atômica: o robô escreve um `.tmp` e renomeia. Um `.json` presente está sempre completo; ignore os arquivos `.tmp` |
| Frequência | A cada execução do robô (a cada 5 minutos), só quando houver planilha nova |
| Repetição | A mesma planilha (mesmo hash) nunca gera dois lotes (RN02) |

## 2. LGPD: o que **não** vem no lote

O lote é **pseudonimizado**: não traz nome nem e-mail. O funcionário aparece como `employeeRef`, que é o SHA-256 da matrícula com um salt secreto, truncado em 12 caracteres.

- O mesmo funcionário tem sempre o mesmo `employeeRef` enquanto o salt (`LOG_SALT`) não mudar. Isso permite cruzar semanas.
- Não é possível voltar do `employeeRef` para a matrícula sem o salt, que fica só no `.env` do robô.
- A estação de embarque vem no lote porque é o dado central para a análise de lotação. Sem nome e e-mail, ela não identifica a pessoa sozinha. Não cruze a estação com outras bases que tenham identificação.

## 3. Dicionário de dados

| Campo | Tipo | Exemplo | Descrição |
|---|---|---|---|
| `dataset` | texto | `schedule` | Sempre `schedule` |
| `schemaVersion` | inteiro | `1` | Muda se o formato mudar |
| `batchId` | texto | `si-20261111-223027-ab12-265023e6` | Identificador único do lote (execução + hash) |
| `generatedAt` | data-hora ISO 8601 | `2026-11-11T22:30:27-03:00` | Momento da importação |
| `sourceFileHash` | texto (64) | `265023e6…` | SHA-256 da planilha de origem |
| `importId` | texto ou `null` | `imp-468f9352` | Id da importação na API. É `null` quando a API estava fora do ar; a importação segue pela outbox e o `sourceFileHash` liga os dois lados |
| `scheduleId` | texto ou `null` | `sch-94280dab` | Id da escala na API (mesma regra do `importId`) |
| `companyName` | texto | `Empresa Fictícia S.A.` | Empresa cliente |
| `week` | texto | `2026-W48` | Semana ISO da escala |
| `entryWindows` | lista de textos | `["07:00","08:00","09:30","10:30"]` | Horários de entrada permitidos pela empresa |
| `teams[].teamName` | texto | `Financeiro` | Time |
| `teams[].demand[].date` | data | `2026-11-23` | Dia útil da semana |
| `teams[].demand[].minPeople` | inteiro | `2` | Mínimo de pessoas presenciais no dia |
| `teams[].demand[].maxPeople` | inteiro | `6` | Máximo de pessoas presenciais no dia |
| `teams[].demand[].mandatory` | booleano | `true` | Dia de presença obrigatória (ex.: reunião do time) |
| `employees[].employeeRef` | texto (12) | `69f58bb8297b` | Funcionário pseudonimizado |
| `employees[].teamName` | texto | `Financeiro` | Time |
| `employees[].lineNumber` | inteiro | `3` | Linha do metrô (MVP: 1 ou 3) |
| `employees[].boardingStation` | texto | `Corinthians-Itaquera` | Estação de embarque, com o nome oficial |
| `employees[].monthlyOnSiteDays` | inteiro (0 a 23) | `8` | Dias presenciais no mês pela política da empresa |
| `employees[].unavailableDates` | lista de datas | `["2026-11-23"]` | Dias em que a pessoa não pode ir |
| `employees[].latestEntryWindow` | texto ou `null` | `"08:00"` | Horário máximo de entrada (restrição pessoal) |
| `quality.employeesTotal` | inteiro | `20` | Linhas de funcionários na planilha |
| `quality.employeesValid` | inteiro | `18` | Linhas aceitas (só estas estão em `employees`) |
| `quality.demandTotal` / `demandValid` | inteiro | `10` / `10` | Linhas de demanda lidas e aceitas |
| `quality.rejectedRows` | inteiro | `2` | Total de linhas recusadas |

## 4. Exemplo (dados fictícios, resumido)

```json
{
  "dataset": "schedule",
  "schemaVersion": 1,
  "batchId": "si-20261111-223027-ab12-265023e6",
  "generatedAt": "2026-11-11T22:30:27-03:00",
  "sourceFileHash": "265023e6…",
  "importId": "imp-468f9352",
  "scheduleId": "sch-94280dab",
  "companyName": "Empresa Fictícia S.A.",
  "week": "2026-W48",
  "entryWindows": ["07:00", "08:00", "09:30", "10:30"],
  "teams": [
    {"teamName": "Financeiro", "demand": [{"date": "2026-11-23", "minPeople": 2, "maxPeople": 6, "mandatory": false}]}
  ],
  "employees": [
    {"employeeRef": "69f58bb8297b", "teamName": "Financeiro", "lineNumber": 3, "boardingStation": "Corinthians-Itaquera",
     "monthlyOnSiteDays": 8, "unavailableDates": ["2026-11-23"], "latestEntryWindow": null}
  ],
  "quality": {"employeesTotal": 20, "employeesValid": 18, "demandTotal": 10, "demandValid": 10, "rejectedRows": 2}
}
```

## 5. Como gerar lotes de teste

```bash
python -m tools.sampleSpreadsheets                  # Gera as planilhas fictícias em data/fixtures/
copy data\fixtures\scheduleValid.xlsx data\input\   # Linux/macOS: cp
python -m src.main scheduleImport                   # Com o mock da API no ar (ver README)
```

O lote aparece em `landingZone/chegada/schedule/`. Para apontar para outra pasta (por exemplo, uma pasta sincronizada com o ambiente de Big Data), mude `LANDING_ZONE_PATH` no `.env`.

## 6. O que ainda precisamos de vocês

- Confirmar se o nome da pasta (`chegada/schedule/`) e o formato JSON atendem ao pipeline de Big Data, ou se preferem outro formato (CSV ou Parquet) ou outra convenção de nomes.
- Dizer se precisam de mais algum campo. Qualquer dado pessoal novo precisa de justificativa de LGPD.
