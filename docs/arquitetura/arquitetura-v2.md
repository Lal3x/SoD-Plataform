# Arquitetura V2 atual

## 1. Arquitetura canônica

O DAG Airflow sod_runtime_v2 é a referência operacional da implementação atual.

~~~text
VALIDAÇÃO DE PARÂMETROS E FONTES
            │
            ▼
          Bronze
            │
       Bronze Gate
            │
            ▼
          Silver
            │
       Silver Gate
            │
            ▼
 Access Context + HTS
            │
            ▼
Observed Baseline + Fallback
            │
            ▼
     Expected Access
            │
            ▼
        Evidence
            │
            ▼
     Policy PD002
            │
            ▼
      Risk RISK001
            │
            ▼
      Gold GOLD001
            │
        Gold Gate
            │
            ▼
     Registro do Run
            │
            ▼
  dispara validação offline
~~~

O DAG de validação é separado. Ele não é upstream do runtime.

## 2. Fronteiras de responsabilidade

### Preparação

**Bronze** preserva o dado ingerido e seu lineage técnico.

**Silver** normaliza contratos, tipos, qualidade, rejeições e dados canônicos.

### Curadoria de contexto

**Access Context** consolida os fatos necessários para interpretar cada grant.

**Hard Trusted Set** marca âncoras explícitas de alta confiança.

### Inteligência de acesso

**Observed Baseline** mede prevalência.

**Hierarchical Fallback** escolhe a melhor população disponível.

**Expected Access** responde se o grant adere ao comportamento esperado.

### Decisão

**Evidence** organiza fatos e confiabilidade.

**Policy** classifica.

**Risk** prioriza.

**Gold** materializa o contrato operacional.

## 3. Por que Gold vem depois de Risk

A Gold é uma camada de publicação. Colocar regras novas na Gold teria três efeitos ruins:

1. esconder lógica de negócio no consumo;
2. dificultar testes isolados;
3. quebrar rastreabilidade entre decisão e score.

Na V2, campos como policy_decision, policy_rule_id, risk_score e expected_access_state chegam à Gold já calculados.

## 4. Runtime versus validação

~~~text
                    RUNTIME
Sources → ... → Policy → Risk → Gold
                              │
                              ▼
                         Freeze/Snapshot
                              │
              ┌───────────────┘
              ▼
       VALIDATION DAG
              │
              ├── gabarito sintético
              ├── métricas descritivas
              └── Validation Mart
~~~

A separação é intencional. Um label de validação jamais deve alterar a saída que ele próprio será usado para avaliar.

## 5. Runtime versus experimental

O arquivo de configuração de Access Intelligence contém experimentos de Peer Discovery em shadow mode.

Eles não participam de:

- EA001;
- Evidence;
- Policy;
- Gold;
- decisão runtime.

Isso permite explorar novas técnicas sem transformar a POC em uma caixa-preta operacional.

## 6. Versionamento

A arquitetura preserva versões explícitas de engines e regras, incluindo:

- HTS;
- baseline;
- fallback;
- Expected Access;
- Evidence;
- Policy;
- Risk;
- Gold.

O objetivo é permitir que uma decisão seja reconstruída não apenas pelos dados, mas também pela versão do comportamento que a produziu.

## 7. Propriedades desejadas

A arquitetura atual busca cinco propriedades:

**Reprodutibilidade:** mesma entrada e mesma configuração devem produzir a mesma lógica de decisão.

**Explicabilidade:** cada grant deve trazer fatos, motivo e regra.

**Auditabilidade:** snapshots e versões devem permitir reconstrução.

**Separação de concerns:** estatística, evidência, política e prioridade não são misturadas.

**Evolutividade:** novos sinais e a futura SoD transacional podem ser adicionados sem reescrever todo o pipeline.
