# Estrutura do repositório

~~~text
SoD-Plataform/
├── apps/
│   └── streamlit/              # interface de consumo
├── configs/                    # parâmetros e políticas versionadas
├── data/                       # dados locais/warehouse quando aplicável
├── docs/                       # documentação MkDocs
├── orchestration/
│   └── airflow/                # DAGs e imagem Airflow
├── scripts/
│   ├── runtime/                # pipeline V2 congelado
│   ├── validation/             # validação offline
│   ├── operations/             # gates e registro
│   ├── audit/
│   ├── maintenance/
│   └── development/
├── src/
│   └── sod_platform/
│       ├── bronze/
│       ├── silver/
│       ├── access_intelligence/
│       │   ├── context/
│       │   ├── trusted_set/
│       │   ├── baseline/
│       │   ├── expected_access/
│       │   ├── evidence/
│       │   ├── policy/
│       │   ├── risk/
│       │   └── experimental/
│       ├── gold/
│       ├── validation/
│       └── observability/
├── tests/
├── .github/workflows/
├── Dockerfile
├── docker-compose.yml
├── mkdocs.yml
└── pyproject.toml
~~~

## Onde encontrar a fonte da verdade operacional

Para entender **o que realmente roda na V2**, comece por:

1. orchestration/airflow/dags/sod_runtime_v2.py;
2. scripts/runtime/;
3. configs/policy_decision_pd002_1_0_1.yml;
4. configs/risk.yml;
5. configs/access_intelligence.yml.

Isso é mais seguro do que inferir comportamento apenas pela existência de um arquivo ou módulo.

## Código ativo versus scaffolding

Alguns arquivos podem existir como preparação para hipóteses futuras.

A existência de um arquivo como sod_rules.yml ou clustering.yml não significa que ele esteja no runtime.

A documentação utiliza o DAG V2 como referência para separar:

- ativo;
- experimental;
- futuro.

## Dashboard

apps/streamlit contém a interface.

Ela consome repositórios de leitura que encapsulam Spark/Iceberg, reduzindo acoplamento entre UI e persistência.

## CI

.github/workflows/ci.yml executa testes e build das imagens.

## Documentação

mkdocs.yml define a navegação oficial.

A estrutura foi propositalmente separada entre:

- negócio;
- arquitetura;
- técnica;
- decisões;
- referência.

Isso permite que um avaliador compreenda primeiro **por que** a solução existe antes de entrar em **como** ela foi implementada.
