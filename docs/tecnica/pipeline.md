# Pipeline de dados

## 1. Objetivo

O pipeline transforma fontes heterogêneas de identidade e acesso em dados canônicos, contextualizados e prontos para decisão.

A separação em camadas existe para que problemas de ingestão, qualidade, contexto e regra de negócio possam ser testados de forma independente.

~~~text
Fontes
  ↓
Bronze
  ↓
Quality Gate
  ↓
Silver
  ↓
Quality Gate
  ↓
Access Intelligence
  ↓
Decision
  ↓
Gold
~~~

## 2. Fontes modeladas

A POC trabalha com domínios equivalentes a:

- identity_master;
- identity_directory;
- iga_entitlements;
- iga_access_assignments;
- iga_access_requests;
- access_certifications;
- application_catalog.

A arquitetura não depende dos nomes dos produtos que forneceriam essas informações em produção. O contrato lógico é mais importante do que o fornecedor.

## 3. Bronze

Bronze responde:

> “O que recebemos e de onde veio?”

Responsabilidades:

- ingestão;
- preservação de estrutura e origem;
- metadados técnicos;
- rastreabilidade;
- materialização para reprocessamento.

Bronze não deve decidir se um acesso é bom ou ruim.

## 4. Silver

Silver responde:

> “Qual é a representação canônica e confiável deste dado?”

Responsabilidades:

- padronização de tipos;
- nomes e contratos;
- validações;
- rejeições/quarentena;
- chaves técnicas;
- integridade mínima;
- persistência em Iceberg.

O runtime V2 chama Silver com --silver-only. A construção de Access Context fica em uma etapa posterior e explícita.

## 5. Qualidade de dados

Um erro técnico e uma evidência de negócio são conceitos diferentes.

Exemplos:

~~~text
data inválida
    → problema de qualidade

cross-community
    → fato de negócio

ausência de aprovação em fonte autoritativa
    → possível evidência para Policy
~~~

Misturar os três tornaria a decisão difícil de explicar.

## 6. Grain

O runtime opera sobre um grant identificado por grant_id e assessment_date.

Essa granularidade é diferente da unidade conceitual do case.

- **Unidade de análise de negócio:** comunidade.
- **Granularidade do acesso:** Entitlement × Sigla.
- **Granularidade técnica da decisão:** grant de uma identidade em uma data de avaliação.

Essa distinção permite agregar resultados por comunidade sem perder a explicação de cada acesso individual.

## 7. Temporalidade

A data de avaliação é parte do contrato.

Um grant concedido depois da assessment_date não deve influenciar o baseline daquela avaliação.

Da mesma forma, uma aprovação posterior à concessão não deve ser tratada automaticamente como evidência de autorização original.

O pipeline procura preservar essas relações em vez de analisar somente o estado atual.

## 8. Persistência e snapshots

Apache Iceberg é usado para materialização das tabelas do pipeline.

Os snapshots são úteis para:

- rastreabilidade;
- reprodução;
- validação;
- comparação entre execuções;
- proteção contra usar acidentalmente outputs diferentes na mesma análise.

Os scripts runtime congelam referências dos inputs antes das etapas seguintes.

## 9. Gates

O DAG possui gates depois de Bronze, Silver e Gold.

A função do gate é simples:

> falhar cedo quando uma camada não satisfaz o contrato esperado.

Isso evita que uma falha silenciosa na ingestão se transforme mais tarde em uma “descoberta analítica”.

## 10. Idempotência e falhas parciais

As etapas são projetadas para reexecução controlada sobre snapshots e tabelas conhecidas. Entretanto, a POC local não implementa uma transação distribuída única cobrindo todas as tabelas do pipeline.

Em produção, a operação deve considerar:

- escrita por estágio;
- commit/snapshot por tabela;
- registro de run;
- gates;
- reexecução segura;
- limpeza ou substituição controlada de outputs parciais.

Essa limitação é preferível a afirmar atomicidade global que a implementação atual não possui.
