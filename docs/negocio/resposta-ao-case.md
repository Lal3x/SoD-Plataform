# Como a solução responde aos 9 desafios

Esta página conecta diretamente o desafio de negócio aos componentes da POC.

!!! info "Como ler esta página"
    A implementação da POC funciona como **evidência adicional de que a arquitetura é executável**. O núcleo da resposta ao case, porém, continua sendo o **raciocínio**: como o problema foi decomposto, por que cada escolha foi feita, quais trade-offs foram aceitos e como a solução pode evoluir com segurança.

## 1. Abordagem e técnica

A solução usa uma abordagem híbrida:

- regras determinísticas para evidências e política;
- prevalência estatística para comportamento esperado;
- fallback hierárquico para grupos pequenos;
- score de risco para priorização;
- experimentos de descoberta de pares em shadow mode.

A decisão final do runtime não depende de clustering ou LLM.

**Por quê?** Porque a primeira fase exige explicabilidade, ação e auditabilidade. Métodos exploratórios são úteis para descoberta, mas não precisam controlar uma decisão operacional antes de serem validados.

## 2. Como estabelecer o acesso esperado

A solução combina duas fontes de sinal:

1. **Hard Trusted Set:** âncoras explícitas de alta confiança, atualmente baseadas em birthright sem contradição relevante.
2. **Observed Baseline:** prevalência observada em populações comparáveis.

O fallback tenta grupos do mais específico para o mais amplo:

~~~text
comunidade + squad + cargo + tipo_identidade
                  ↓
          comunidade + cargo
                  ↓
              comunidade
                  ↓
        tipo de identidade
~~~

Se não houver população ou suporte suficiente, a solução retorna evidência insuficiente em vez de inventar um padrão.

## 3. Classificação e priorização

A classificação é feita por Policy PD002.

A priorização é feita depois por Risk RISK001.

~~~text
Evidence
   ↓
Policy → PADRÃO / LEGÍTIMO / INDEVIDO / REVISÃO
   ↓
Risk → score / faixa / ação operacional
~~~

Isso evita misturar “o acesso é inadequado?” com “qual é a urgência deste caso?”.

## 4. Falsos positivos e falsos negativos

A solução reduz falsos positivos por meio de:

- tratamento explícito de siglas públicas;
- evidência de aprovação;
- REVISÃO quando há ambiguidade;
- fallback para comunidades pequenas;
- separação entre rareza e irregularidade;
- tratamento conservador de uso e histórico organizacional.

Falsos negativos são monitorados pela validação offline, por amostragem dirigida e, em produção, pela comparação com achados confirmados de controles.

## 5. Explicabilidade

Cada decisão preserva:

- rule id;
- reason code;
- confidence;
- evidências usadas;
- estado de Expected Access;
- nível de baseline selecionado;
- prevalência e suporte;
- drivers de risco;
- versões dos componentes;
- snapshot e lineage.

A pergunta que a interface deve responder não é apenas “qual classe?”, mas:

> “Quais fatos levaram a esta classe e qual ação é esperada agora?”

## 6. Escala

A implementação usa PySpark, Apache Iceberg e processamento desacoplado por etapas. O Airflow coordena gates e dependências.

A arquitetura-alvo AWS mapeia os mesmos componentes para S3 + Iceberg, Glue Data Catalog, EMR Serverless, MWAA, Athena e QuickSight, com CloudWatch/CloudTrail e controles via IAM, Lake Formation, KMS e Secrets Manager.

Escala, portanto, não depende de uma planilha ou de entrevistas por comunidade.

## 7. Evolução para SoD granular

A arquitetura adiciona uma camada de semântica transacional:

~~~text
entitlement → função → transação → ação → objeto/escopo
~~~

Essa camada alimentará um catálogo versionado de conflitos, exceções e controles compensatórios. O restante da plataforma — contexto, evidência, política, risco, Gold, lineage e observabilidade — permanece reutilizável.

## 8. Validação e valor

A validação ocorre fora do runtime, usando gabarito sintético ou posteriormente amostras confirmadas por especialistas.

Métricas relevantes incluem:

- cobertura de decisões;
- volume enviado a revisão;
- precisão por classe;
- falsos positivos em sigla pública e cross aprovado;
- concentração de risco;
- tempo de tratamento;
- redução de entrevistas;
- percentual de decisões explicáveis com evidência suficiente.

A POC não deve apresentar métricas sintéticas como prova de valor produtivo. Elas demonstram funcionamento controlado.

## 9. Sustentação

A solução foi desenhada para versionar:

- configurações;
- regras de política;
- thresholds analíticos;
- engines;
- snapshots Iceberg;
- outputs congelados.

CI, testes, observabilidade e DAGs separados ajudam a detectar regressões. Em produção, a sustentação também exigiria ownership formal das regras, SLAs das fontes, processo de mudança e recertificação periódica dos parâmetros.

## Resumo

| Pergunta do case | Resposta arquitetural |
|---|---|
| Como identificar? | Contexto + expectedness + evidência + política |
| Como definir padrão? | HTS + baseline + fallback |
| Como classificar? | Policy PD002 |
| Como priorizar? | Risk RISK001 |
| Como reduzir erros? | Regras explícitas + REVISÃO + fallback |
| Como explicar? | reason codes + evidência + lineage |
| Como escalar? | Spark + Iceberg + Airflow + arquitetura cloud |
| Como chegar à SoD transacional? | catálogo de funções/transações/conflitos |
| Como validar e sustentar? | Validation Mart + testes + versionamento + observabilidade |
