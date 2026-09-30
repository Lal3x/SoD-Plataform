# Validação, observabilidade e testes

## 1. Validação não é runtime

A validação V2 possui um DAG próprio: sod_validation_v2.

O runtime dispara a validação apenas depois de registrar e congelar sua execução.

~~~text
runtime
  ↓
Gold
  ↓
freeze / registro
  ↓
validation DAG
  ↓
Validation Mart
~~~

Essa direção importa. O Validation Mart nunca deve alimentar Policy ou Expected Access durante a mesma avaliação.

## 2. Gabarito sintético

O gabarito existe para medir o comportamento da POC em cenários controlados.

Ele não deve ser usado para:

- gerar thresholds;
- descobrir regras;
- treinar a Policy;
- selecionar parâmetros;
- produzir features runtime.

A finalidade é avaliação posterior.

## 3. O que validar

A avaliação técnica deve olhar mais do que uma acurácia total.

### Por classe

- PADRÃO;
- LEGÍTIMO;
- INDEVIDO;
- REVISÃO.

### Por cenário

- público;
- cross aprovado;
- cross sem aprovação;
- birthright;
- acesso herdado;
- sem uso registrado;
- comunidades pequenas.

### Por comportamento operacional

- cobertura;
- taxa de revisão;
- falsos positivos;
- falsos negativos;
- distribuição de risk bands;
- estabilidade entre versões.

## 4. O que seria necessário antes de produção

Dados reais exigiriam validação com especialistas e amostras confirmadas.

Uma estratégia segura incluiria:

1. shadow run;
2. comparação com achados existentes;
3. revisão de amostras por especialistas;
4. análise por comunidade;
5. calibração sem leakage;
6. aprovação formal das regras;
7. rollout gradual;
8. monitoramento contínuo.

## 5. Observabilidade

A observabilidade deve responder três grupos de perguntas.

### Dados

- chegaram todos os inputs?
- houve mudança brusca de volume?
- aumentaram rejects?
- há campos-chave ausentes?

### Pipeline

- qual etapa falhou?
- quanto tempo levou?
- qual snapshot foi produzido?
- houve reprocessamento?

### Decisão

- mudou a proporção de PADRÃO/LEGÍTIMO/INDEVIDO/REVISÃO?
- aumentou a taxa de fallback?
- aumentou INSUFFICIENT_EVIDENCE?
- alguma regra passou a dominar as decisões?
- mudou a distribuição de risco?

A observabilidade de decisão é importante porque um pipeline pode estar “verde” tecnicamente e ainda produzir comportamento anômalo.

## 6. Testes

O projeto separa testes em:

- unit;
- integration;
- e2e.

A suite também possui testes específicos de Bronze, Silver, Access Intelligence, Gold, Streamlit e Observability.

O objetivo é testar:

- funções isoladas;
- contratos entre componentes;
- comportamento Spark;
- pipeline reduzido ponta a ponta;
- invariantes de decisão.

## 7. CI

O GitHub Actions atual executa testes e constrói as imagens Docker de Streamlit e Airflow.

Isso garante um nível mínimo de controle antes de integrar alterações.

Uma evolução natural é adicionar ao CI:

- lint;
- build do MkDocs;
- validação de links internos;
- checks de schema/config;
- scanner de dependências e imagem;
- publicação controlada de artefatos.

## 8. Métricas de valor de negócio

Além de métricas técnicas, a implantação real deve medir:

- redução do número de entrevistas;
- tempo médio para analisar um apontamento;
- proporção de casos automaticamente explicados;
- proporção encaminhada a revisão;
- tempo de remediação;
- reincidência;
- cobertura de comunidades;
- estabilidade das regras.

O objetivo não é apenas “ter um modelo”. É reduzir custo operacional mantendo controle e evidência.
