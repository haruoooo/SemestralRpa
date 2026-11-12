# ForaDoPico · RPA

> Global Solution 2026.2 · FIAP · Engenharia de Software 4º ano · Disciplina **Robotic Process Automation**
> Componente **Automação** da CitizenTech **ForaDoPico**

## Integrantes

| Nome | RM |
|---|---|
| Matheus Haruo | 97663 |
| João Saborido | 98184 |
| Pedro Guerra de Souza Freitas | 99526 |
| Victor Wittner | 98667 |

## O problema e o papel da automação

O trabalhador CLT que vai ao escritório de metrô perde quase 3 horas por dia no transporte, em trens com 8 a 10 pessoas por m² no pico. O ForaDoPico monta a escala presencial das empresas híbridas fugindo do pico.

O robô tira do RH as tarefas manuais que existem por trás do produto:

| Fluxo | O que faz | Status |
|---|---|---|
| `lineMonitorFlow` | Monitora a situação das Linhas 1 e 3 a cada 5 min e, se houver falha, cria o alerta e propõe o plano B (remoto ou outro horário) para o RH aprovar | ✅ Implementado |
| `scheduleImportFlow` | Importa e valida a planilha de escala do RH, envia à plataforma, grava o lote pseudonimizado para Big Data e gera o relatório do RH | ✅ Implementado |
| `agendaDispatchFlow` | Envia por e-mail a agenda (.ics) aprovada pelo RH e os avisos de plano B, que cancelam ou movem o evento no calendário | ✅ Implementado |

Documentação:
- [docs/processDesign.md](docs/processDesign.md): PDD com o passo a passo, regras de negócio, exceções, logs e testes.
- [docs/bpmn/](docs/bpmn/): diagramas BPMN 2.0 dos três fluxos (`.bpmn` e `.svg`).
- [docs/architecture.md](docs/architecture.md): arquitetura Ports & Adapters.
- [docs/integrations/secureDevOpsCloud/](docs/integrations/secureDevOpsCloud/): contrato da API do produto e guia de deploy do robô.
- [docs/integrations/bigDataDataIntegration/](docs/integrations/bigDataDataIntegration/): formato do lote entregue à pasta de pouso do Big Data.

## Estrutura

```
src/            Código do robô (domain, application, adapters, infrastructure)
mockApi/        Mock da API do produto (mesmo contrato) com painel para demonstração
docs/           PDD, BPMN, arquitetura, integrações e relatório técnico (PDF)
tests/          Testes automatizados (sucesso, decisão e falha) e evidências em tests/evidence/
logs/           Logs de auditoria (JSON Lines, sem dados pessoais); amostra em logs/samples/
assets/         Prints e arquivos de evidência (painel, e-mails, relatório do RH, BPMN)
data/fixtures/  Dados fictícios para testes e demonstração (planilhas de exemplo e modelo do RH)
tools/          Geradores das planilhas fictícias e dos diagramas BPMN
```

## Como rodar

Pré-requisito: Python 3.13.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # Linux/macOS: cp .env.example .env
```

**1. Subir o mock da API** (terminal 1). O painel fica em http://127.0.0.1:8000/:

```bash
uvicorn mockApi.app:app --port 8000
```

**2. Importar a planilha do RH** (terminal 2):

```bash
copy data\fixtures\scheduleValid.xlsx data\input\        # Linux/macOS: cp
python -m src.main scheduleImport
```

O arquivo vai para `data/input/processed/` (ou `rejected/`), o relatório do RH para `data/output/reports/`, o lote para Big Data para `landingZone/chegada/schedule/` e a escala aparece no painel aguardando aprovação. Outras planilhas de exemplo: `scheduleTenPercentInvalid.xlsx` (2 linhas recusadas), `scheduleThirtyPercentInvalid.xlsx` (rejeitada pela RN09), `scheduleCorrupted.xlsx` e `scheduleMissingSheet.xlsx`. O modelo em branco para o RH é o `scheduleTemplate.xlsx`.

**3. Aprovar e enviar as agendas.** No painel, clique em **Aprovar** na escala e rode:

```bash
python -m src.main agendaDispatch
```

Com `NOTIFIER_MODE=console`, cada e-mail é salvo como `.eml` em `data/output/mail/` (abre no Outlook). Com `NOTIFIER_MODE=smtp`, ele chega na caixa do Mailtrap. Para a demonstração, use a planilha `scheduleDemoSmall.xlsx` (3 pessoas), que cabe na cota gratuita do Mailtrap.

**Roteiro completo do vídeo** (semana fictícia de 23 a 27/11/2026):

```bash
# No .env: LINE_STATUS_SOURCE=simulated e NOTIFIER_MODE=smtp
copy data\fixtures\scheduleDemoSmall.xlsx data\input\
python -m src.main scheduleImport                                  # Escala aguardando aprovação no painel
#   -> Aprovar no painel
python -m src.main agendaDispatch                                  # Agendas no Mailtrap
python -m src.main simulate --line 3 --text "Paralisada"
python -m src.main lineMonitor --ignoreWindow --at 2026-11-24T07:30  # Alerta + plano B pendente
#   -> Aprovar o plano B no painel
python -m src.main agendaDispatch --at 2026-11-24T07:32            # "Hoje: seu dia presencial virou remoto"
```

**4. Rodar o monitor contra o site real do Metrô**:

```bash
python -m src.main lineMonitor
```

**5. Demonstrar só o plano B** com uma falha simulada:

```bash
# No .env: LINE_STATUS_SOURCE=simulated
python -m src.main simulate --line 3 --text "Paralisada"
python -m src.main lineMonitor --ignoreWindow --at 07:30
python -m src.main simulate --unavailable                 # Simula a fonte fora do ar
```

**6. Modo produção** (os três fluxos agendados num único processo: importação a cada 5 min, envio a cada 10 min e monitor a cada 5 min em dias úteis):

```bash
python -m src.main scheduler
```

**7. Testes:**

```bash
pytest -v                         # 81 testes automatizados
bash tools/collectEvidence.sh     # Execução de ponta a ponta de todos os cenários + prints (Git Bash)
```

O mapa de cenários (sucesso, decisão e falha) e onde cada um é verificado está em [tests/README.md](tests/README.md). Para gerar o PDF de novo depois de mudar o relatório, imprima `docs/report/technicalReport.html` com o Edge ou o Chrome (`--headless --print-to-pdf`).

## Segurança e LGPD

- As credenciais ficam só no `.env`, que não é versionado.
- Os logs não têm nome, e-mail nem estação; o funcionário aparece como hash da matrícula com salt.
- Todos os dados do repositório são fictícios.
- O robô nunca aplica um plano B sozinho: o RH sempre aprova (pessoa no circuito).

## Links

- Vídeo de demonstração: _a publicar_
- Relatório técnico (PDF): [docs/technicalReport.pdf](docs/technicalReport.pdf)
