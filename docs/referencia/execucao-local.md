# Execução local

## Pré-requisitos

- Python 3.12;
- Java compatível com PySpark 4.1;
- Docker, para execução containerizada;
- Poetry, se o fluxo de desenvolvimento usar os grupos do projeto.

## Instalação

~~~bash
poetry install
~~~

Para incluir documentação:

~~~bash
poetry install --with docs
~~~

## Testes

~~~bash
poetry run pytest
~~~

Tarefas disponíveis no pyproject:

~~~bash
poetry run task tests-unit
poetry run task tests-integration
poetry run task tests-e2e
~~~

## Dashboard

~~~bash
PYTHONPATH=src:. poetry run streamlit run apps/streamlit/app.py
~~~

A aplicação fica normalmente em http://localhost:8501.

## Docker Compose

~~~bash
docker compose up --build
~~~

Serviços locais:

- Streamlit: porta 8501;
- Airflow: porta 8080.

## MkDocs

~~~bash
poetry run mkdocs serve
~~~

Para validar build estático:

~~~bash
poetry run mkdocs build --strict
~~~

## Runtime V2

O fluxo canônico é orquestrado por:

~~~text
orchestration/airflow/dags/sod_runtime_v2.py
~~~

Os scripts usados pelo DAG ficam em scripts/runtime/.

Esses scripts trabalham com snapshots e freezes. Use um warehouse isolado para execuções de desenvolvimento que possam substituir saídas.

## Validação

A validação offline está separada em:

~~~text
orchestration/airflow/dags/sod_validation_v2.py
scripts/validation/
~~~

Ela deve ser executada depois do runtime.
