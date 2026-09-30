# SoD Platform

Prova de conceito de **Access Governance / SoD Analytics** orientada ao primeiro estágio do case: sanitizar acessos em escala, distinguindo **PADRÃO**, **LEGÍTIMO**, **INDEVIDO** e casos que exigem **REVISÃO**, sem confundir frequência de uso com autorização.

A implementação atual possui pipeline V2, orquestração Airflow, dashboard Streamlit, validação offline, testes, containers e documentação MkDocs. A AWS é tratada como arquitetura-alvo de produção.

~~~text
Sources
  ↓
Bronze
  ↓
Silver
  ↓
Access Context + Hard Trusted Set
  ↓
Observed Baseline + Hierarchical Fallback
  ↓
Expected Access
  ↓
Evidence
  ↓
Policy PD002
  ↓
Risk RISK001
  ↓
Gold GOLD001
  ↓
Dashboard / Review / Remediation

Validation Mart: separado do runtime
Peer Discovery: experimental / shadow
~~~

## Princípios

- Expectedness não é autorização.
- Frequência não é autorização.
- UNEXPECTED não significa INDEVIDO.
- Evidence organiza fatos; Policy classifica; Risk prioriza.
- Gold publica decisões já produzidas e não cria inteligência.
- Ground truth é usado somente na validação offline.
- A Fase 1 prepara a fundação para a futura SoD transacional.

## Documentação

A documentação oficial está em [docs/](docs/index.md) e é organizada em duas perspectivas complementares:

1. **Negócio:** problema, duas fases do case, regras, hipóteses e resposta aos nove desafios.
2. **Técnica:** evolução arquitetural, runtime V2, componentes analíticos, validação, operação, AWS e evolução para SoD transacional.

Para visualizar localmente:

~~~bash
poetry install --with docs
poetry run mkdocs serve
~~~

## Estrutura principal

- src/sod_platform/bronze/: ingestão e materialização bruta.
- src/sod_platform/silver/: dados canônicos, qualidade e quarentena.
- src/sod_platform/access_intelligence/: contexto, HTS, baseline, Expected Access, Evidence, Policy e Risk.
- src/sod_platform/access_intelligence/experimental/: experimentos shadow de Peer Discovery.
- orchestration/airflow/: DAGs do runtime e da validação offline.
- apps/streamlit/: dashboard somente leitura.
- scripts/runtime/: execução V2 congelada.
- scripts/validation/: validação offline.
- configs/: parâmetros versionados.
- docs/: documentação MkDocs.

## Execução local

Requer Python 3.12 e Java compatível com PySpark 4.1.

~~~bash
poetry install
poetry run sod-bronze --help
poetry run sod-silver --help
poetry run pytest
docker compose up --build
~~~

O runtime V2 canônico é o DAG orchestration/airflow/dags/sod_runtime_v2.py. A validação é executada em um DAG separado e nunca é upstream do runtime.
