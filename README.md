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
| `scheduleImportFlow` | Importa e valida a planilha de escala do RH e envia à plataforma | 🚧 Em desenvolvimento |
| `agendaDispatchFlow` | Envia a agenda (.ics) por e-mail depois que o RH aprova | 🚧 Em desenvolvimento |

Documentação:
- [docs/processDesign.md](docs/processDesign.md): PDD com o passo a passo, regras de negócio, exceções, logs e testes.
- [docs/architecture.md](docs/architecture.md): arquitetura Ports & Adapters.
- [docs/contracts/productApiContract.yaml](docs/contracts/productApiContract.yaml): contrato com a API do produto.

## Estrutura

```
src/            Código do robô (domain, application, adapters, infrastructure)
mockApi/        Mock da API do produto (mesmo contrato) com painel para demonstração
docs/           PDD, BPMN, arquitetura e contrato da API
tests/          Testes automatizados (sucesso, decisão e falha)
logs/           Logs de auditoria (JSON Lines, sem dados pessoais)
data/fixtures/  Dados fictícios para testes e demonstração
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

**2. Rodar o monitor contra o site real do Metrô** (terminal 2):

```bash
python -m src.main lineMonitor
```

**3. Demonstrar o plano B** com uma falha simulada:

```bash
# No .env: LINE_STATUS_SOURCE=simulated
python -m src.main simulate --line 3 --text "Paralisada"
python -m src.main lineMonitor --ignoreWindow --at 07:30
python -m src.main simulate --unavailable                 # Simula a fonte fora do ar
```

**4. Testes:**

```bash
pytest -v
```

## Segurança e LGPD

- As credenciais ficam só no `.env`, que não é versionado.
- Os logs não têm nome, e-mail nem estação; o funcionário aparece como hash da matrícula com salt.
- Todos os dados do repositório são fictícios.
- O robô nunca aplica um plano B sozinho: o RH sempre aprova (pessoa no circuito).

## Links

- Vídeo de demonstração: _a publicar_
- Relatório técnico (PDF): _a publicar_
