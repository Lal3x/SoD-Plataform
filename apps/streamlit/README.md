# SoD Access Intelligence · Dashboard V2

Inicie na raiz com `PYTHONPATH=src:. poetry run streamlit run apps/streamlit/app.py`.

Sete páginas: Visão Executiva, Acessos, Risco & Priorização, Explainability, Análise de Dados, Validação POC V2 e Observabilidade. As páginas operacionais consomem somente `GoldRepository`; a validação offline usa `ValidationRepository`; a engenharia usa `ObservabilityRepository` para metadados e tabelas persistidas. Os repositórios encapsulam Spark/Iceberg, permitindo uma futura troca de adaptador sem alterar as páginas.

A interface é somente leitura. A fila `REVISAO` indica análise humana; `INDEVIDO` alimenta remediação. O detalhe de fatos de evidência é carregado somente para o grant selecionado. O warehouse local e o catálogo Spark devem estar configurados conforme `.env.example`.

A Gold já é uma tabela Iceberg materializada. Os filtros de cada página são obtidos em uma agregação e as consultas de leitura usam cache com chave no snapshot Gold e validade limitada; a primeira visita ainda precisa iniciar o Spark local.
