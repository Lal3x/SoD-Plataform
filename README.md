# SoD Platform

Prova de conceito de governança de acessos por identidade, entitlement e aplicação. O núcleo analítico V2 e o dashboard Streamlit estão implementados; Airflow e MkDocs estão planejados, e AWS é a arquitetura alvo de implantação.

```text
Sources → Bronze → Silver → Access Intelligence → Gold
                            ├─ Access Context
                            ├─ Trusted Set
                            ├─ Observed Baseline + Fallback
                            ├─ Expected Access
                            ├─ Evidence
                            ├─ Policy
                            └─ Risk
Observability: transversal
Validation Mart: avaliação offline, fora do runtime
```

Expectedness não é autorização. Frequência não é autorização. `UNEXPECTED` não significa `INDEVIDO`. Risk prioriza, Policy classifica. Gold publica decisões existentes e não cria inteligência. Ground truth é usado apenas na validação offline.

## Estrutura

- `src/sod_platform/bronze/`: ingestão e materialização bruta.
- `src/sod_platform/silver/`: dados canônicos, concessões e qualidade.
- `src/sod_platform/access_intelligence/`: contexto, HTS, baseline, Expected Access, Evidence, Policy e Risk. Experimentos de Peer Discovery ficam em `experimental/`.
- `src/sod_platform/gold/`: contrato de consumo Gold.
- `src/sod_platform/validation/`: avaliação offline.
- `src/sod_platform/observability/`: métricas e auditoria.
- `configs/`, `scripts/`, `sql/`: configuração, operações e consultas.
- `docs/`: documentação oficial futura em MkDocs.
- `artifacts/`: relatórios de validação, freezes e evidências experimentais.

## Ambiente

Requer Python 3.12 e Java compatível com PySpark 4.1. Copie `.env.example` para `.env` e configure o warehouse local. Dados gerados e segredos locais são ignorados pelo Git.

```bash
poetry install
poetry run sod-bronze --help
poetry run sod-silver --help
poetry run sod-access-intelligence --help
poetry run sod-evidence --help
poetry run sod-policy-decision --help
poetry run pytest
```

O pipeline V2 congelado usa os scripts `scripts/run_v2_*.py`. Esses scripts escrevem snapshots e freezes: execute-os somente em um warehouse isolado. O estado de validação e as limitações atuais estão em `artifacts/validation/repository-refactor-validation.md`.

Peer Discovery permanece experimental e tem CLI próprio: `python -m sod_platform.access_intelligence.experimental.peer_discovery.cli --help`.

## Streamlit Dashboard

Execute `PYTHONPATH=src:. poetry run streamlit run apps/streamlit/app.py` na raiz do projeto. As sete páginas consultam a Gold V2 por repositórios somente leitura; a página de Validação POC V2 consulta separadamente o mart `sod.validation.*`. Nenhuma página operacional acessa o gabarito sintético. Consulte [o guia do dashboard](apps/streamlit/README.md) para a navegação e as fontes.
# SoD-Plataform
