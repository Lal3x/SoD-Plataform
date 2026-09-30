# Access Intelligence

## 1. Por que existe uma camada própria

Bronze e Silver organizam dados. Access Intelligence transforma esses dados em **contexto e sinais analíticos**, ainda preservando a separação entre observação e autorização.

~~~text
Access Context
      │
      ├───────────────┐
      ▼               ▼
Hard Trusted Set   Observed Baseline
      │               │
      │        Hierarchical Fallback
      │               │
      └───────┬───────┘
              ▼
        Expected Access
~~~

## 2. Access Context

O engine cria uma visão factual por grant.

Entre os campos derivados estão:

- cross_community;
- approval_exists;
- approval_relevance;
- approval_linkage_quality;
- inherited_access_candidate;
- no_usage_recorded;
- usage_coverage;
- identity_history_complete;
- application_criticality;
- entitlement_privileged;
- source_snapshot_id;
- access_age_days;
- days_since_last_use.

A palavra importante é **factual**. Access Context não classifica o grant.

### Aprovação

Quando existe fonte de requests, a implementação procura candidatos por identidade e entitlement e exige coerência temporal com a concessão.

Se existe um único candidato, o linkage pode ser marcado como STRONG_INFERRED, mas a relevância ainda é conservadora.

Isso representa uma limitação real: sem uma chave direta request → grant, associação temporal forte ainda é inferência.

### Acesso herdado

A implementação compara data_concessao com data_entrada_comunidade_atual.

Se a concessão é anterior, o acesso é marcado como candidato herdado.

identity_history_complete permanece falso na POC porque o histórico organizacional completo não está garantido.

### Uso

ultimo_uso nulo gera no_usage_recorded, mas usage_coverage permanece UNKNOWN.

Assim, a aplicação não transforma ausência de telemetria em “nunca usado” com certeza indevida.

## 3. Hard Trusted Set

HTS001 marca âncoras explícitas.

A principal âncora atual é birthright, desde que não exista:

- bloqueio de qualidade;
- certificação REVOKE;
- conflito contextual cross-community não público.

Sigla pública, frequência ou aprovação não criam sozinhas uma âncora HTS.

O resultado contém:

- hard_trusted_flag;
- hard_trusted_reason;
- hard_trusted_rule_id;
- hard_trusted_rule_version.

## 4. Observed Baseline

Observed Baseline mede comportamento, não legitimidade.

A população observável atual exige:

- dado sem bloqueio de qualidade;
- identidade ativa;
- acesso same-community;
- data de concessão válida e anterior à assessment_date.

Níveis materializados:

1. SQUAD_CARGO_TIPO_IDENTIDADE;
2. COMUNIDADE_CARGO;
3. COMUNIDADE;
4. POPULACAO_COMPARAVEL por tipo_identidade.

Para cada entitlement e população são calculados:

- population_size;
- support_count;
- prevalence.

### Por que o baseline não usa apenas HTS?

Na V2 congelada, baseline é construído a partir do Access Context filtrado, não apenas das âncoras HTS.

Isso amplia a capacidade de observar comportamento real, mas mantém um risco residual de contaminação.

Essa é uma escolha de POC que deve ser monitorada e pode ser refinada futuramente com estratégias mais robustas de população confiável.

## 5. Hierarchical Fallback

Um baseline muito específico pode ter pouca população.

O fallback escolhe o primeiro nível que satisfaz os mínimos configurados de população e suporte.

Na POC, os mínimos são baixos para permitir demonstração com dados sintéticos. Esses números são parâmetros técnicos e não política institucional.

## 6. Expected Access

EA001 recebe HTS e o baseline selecionado.

Regras conceituais:

~~~text
hard trusted
    → EXPECTED por âncora explícita

senão, baseline suficiente:
    prevalência alta  → EXPECTED
    prevalência baixa → UNEXPECTED
    zona intermediária → INSUFFICIENT_EVIDENCE

sem baseline suficiente
    → INSUFFICIENT_EVIDENCE
~~~

Os thresholds atuais são parâmetros calibráveis da POC e foram definidos independentemente do gabarito de validação.

## 7. O que Expected Access não faz

Expected Access não decide:

- autorização;
- legitimidade;
- violação de política;
- risco;
- prioridade;
- remediação.

Essa fronteira é central para evitar a falácia “raro = irregular”.

## 8. Peer Discovery

O repositório contém experimentos de:

- LDA + FP-Growth;
- NMF-HDBSCAN;
- MinHash/Jaccard + Leiden.

Eles estão em shadow mode.

Seu objetivo é explorar se grupos comportamentais descobertos nos dados podem melhorar a referência de pares no futuro.

No runtime V2 atual eles **não alimentam EA001, Evidence, Policy, Risk ou Gold**.
