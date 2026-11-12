# Entrega para a API do produto e o deploy · robô RPA

> Para: quem implementa a API do ForaDoPico e coloca o produto no ar (Secure DevOps & Cloud).
> De: Matheus Haruo (RPA). Repositório: https://github.com/haruoooo/SemestralRpa

## 1. Resumo

O robô RPA é **cliente** da API do produto. Ele não tem banco de dados de negócio: lê e grava tudo pela API, seguindo o contrato desta pasta ([productApiContract.yaml](productApiContract.yaml), OpenAPI 3.1).

Enquanto a API real não existe, o robô usa um **mock** com o mesmo contrato (`mockApi/app.py` no repositório do RPA). O mock serve também de **implementação de referência**: dá para copiar a lógica de idempotência e de "já enviado".

Para o robô usar a API real, basta mudar duas variáveis no `.env` do robô:

```
PRODUCT_API_URL=https://<endereço da API>
PRODUCT_API_KEY=<chave do robô>
```

## 2. Endpoints que a API precisa ter

| Endpoint | Quem chama | Para quê | Regras importantes |
|---|---|---|---|
| `GET /health` | Robô | Saber se a API está no ar | Sem autenticação |
| `POST /scheduleImports` | `scheduleImportFlow` | Receber a planilha do RH já validada | **Idempotente** pelo header `Idempotency-Key` (SHA-256 do arquivo): a mesma chave devolve a importação original com 200, sem duplicar. Depois de gravar, a API roda o motor de escala e deixa a escala `pendingApproval` |
| `GET /schedules?status=approved&dispatched=false` | `agendaDispatchFlow` | Escalas aprovadas pelo RH com agenda ainda não enviada a alguém | Cada escala traz `version` e a lista `assignments` (com nome e e-mail). `dispatched=false` significa que pelo menos um funcionário ainda não recebeu **a versão atual** |
| `GET /assignments?date=&lineNumber=` | `lineMonitorFlow` | Quem tem presencial no dia, numa linha | Só escalas aprovadas. Cada item traz `allowedEntryWindows`, que o robô usa para propor um horário mais tarde |
| `POST /lineStatus` | `lineMonitorFlow` | Situação de todas as linhas (alimenta a tela Alertas e a versão gratuita) | 204. Guardar só o último snapshot já basta |
| `GET /lineStatus` | App | Ler a situação atual | Público |
| `POST /alerts` | `lineMonitorFlow` | Criar o alerta quando uma linha muda de status | **Idempotente** por `dedupeKey`: chave repetida devolve 200 com o alerta existente |
| `POST /contingencyPlans` | `lineMonitorFlow` | Propor o plano B de um time | Sempre criado como `pendingApproval` (o RH aprova no app). **Idempotente** por `alertId + teamName + action + newEntryWindow`. A resposta deve trazer `affected` (as escalas cobertas, com nome e e-mail) |
| `GET /contingencyPlans?status=approved&dispatched=false` | `agendaDispatchFlow` | Planos B aprovados com aviso ainda não enviado | Mesma ideia de `dispatched` das escalas |
| `POST /dispatches` | `agendaDispatchFlow` | Resultado de cada e-mail enviado | 204. Itens com `delivered=true` marcam o funcionário como "já recebeu" aquela versão (escala) ou aquele plano (plano B, `version=1`) |

**Erros:** o robô trata 5xx e timeout como "API fora do ar", tenta de novo 3 vezes e depois guarda o envio numa fila local (outbox). Já 4xx é tratado como "dados recusados", sem nova tentativa. Por isso:
- devolvam **4xx** só para payload inválido;
- devolvam **5xx** para falhas internas;
- quando houver detalhe do erro, usem o formato `{"errors":[{"field","message"}]}`.

**Autenticação:** header `X-Api-Key`. A chave do robô fica só no `.env` dele e nunca vai para o repositório.

## 3. Telas do app que dependem do robô

| Tela | O que o robô entrega |
|---|---|
| Montar a semana (RH) | Escala importada, aguardando aprovação, com o número de linhas recusadas (`rejectedRows`) |
| Aprovar escala (RH) | Ao aprovar, a API muda o status para `approved` e o robô envia as agendas sozinho em até 10 minutos |
| Alertas | Snapshot das linhas (`GET /lineStatus`) e alertas criados |
| Plano B (RH) | Planos `pendingApproval` com Aprovar ou Recusar. Ao aprovar, o robô avisa os funcionários |
| Editar escala (RH) | Ao editar uma escala aprovada, **incrementem `version`**; o robô reenvia a agenda como "Agenda atualizada" |

## 4. Motor de escala (referência)

O mock tem uma heurística simples em `mockApi/schedulingEngine.py`:
1. Cada pessoa entra na janela com menor lotação prevista que respeite a restrição de horário dela.
2. Cada dia do time é preenchido até a demanda, começando pelos dias obrigatórios e respeitando os dias indisponíveis e a cota semanal (dias presenciais no mês ÷ 4).

Podem usar como ponto de partida. A previsão de lotação real vem da camada Ouro de Big Data.

## 5. Como colocar o robô no ar

| Item | Valor |
|---|---|
| Runtime | Python 3.13, `pip install -r requirements.txt` |
| Comando | `python -m src.main scheduler`: um único processo de longa duração que agenda os três fluxos (importação a cada 5 min, envio a cada 10 min, monitor a cada 5 min em dias úteis). Cada fluxo também roda sozinho (`scheduleImport`, `agendaDispatch`, `lineMonitor`), se preferirem cron |
| Código de saída | 0 = sucesso, 2 = parcial (algum item falhou e será refeito), 1 = falha. Dá para alertar no Grafana quando aparecer 1 |
| Logs | JSON Lines em `logs/robotYYYYMMDD.log`, um registro por evento, e um `RunSummary` por execução com contagens e duração (bom para as métricas de ouro). Sem dados pessoais |
| Estado | SQLite em `data/runtime/robotState.db` (precisa de volume persistente) |
| Segredos | `PRODUCT_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `LOG_SALT`, todos por variável de ambiente ou secret manager. Lista completa em `.env.example` |
| Rede de saída | API do produto, `www.metro.sp.gov.br` (HTTPS) e o servidor SMTP |

## 6. O que precisamos de vocês

1. **A URL da API e uma chave para o robô**, quando a API estiver no ar.
2. **Confirmar o contrato** desta pasta. Se algum nome de campo ou caminho mudar, me avisem para eu ajustar o robô e o mock.
