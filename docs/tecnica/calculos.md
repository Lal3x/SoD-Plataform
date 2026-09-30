# Como os cálculos funcionam

Esta página consolida **como os principais resultados da POC são produzidos**. O objetivo é permitir que alguém consiga seguir o cálculo sem precisar abrir o código.

!!! important "Três tipos de lógica"
    Nem tudo nesta solução é uma fórmula matemática.

    - **Fórmula:** por exemplo, prevalência e métricas de validação;
    - **regra determinística:** por exemplo, Policy e classificação de confiabilidade;
    - **parâmetro configurável:** por exemplo, thresholds `0,80` e `0,20` ou pesos do Risk.

    Os parâmetros abaixo são **valores versionados da POC**, não políticas institucionais universais.

## 1. Geração do `grant_id`

A fonte física de assignments não fornece uma chave de grant. A Silver cria uma chave técnica determinística.

### Variáveis

| Variável | Significado |
|---|---|
| `identidade_id` | identificador da pessoa/identidade |
| `entitlement_id` | identificador da permissão concedida |
| `len(...)` | quantidade de caracteres do valor |
| `SHA-256` | função hash usada para criar a chave técnica |

### Regra

```text
grant_id =
  "technical-"
  + SHA256(
      len(identidade_id) + ":" + identidade_id
      + "|" +
      len(entitlement_id) + ":" + entitlement_id
    )
```

O prefixo de comprimento evita ambiguidades de concatenação. O mesmo par identidade × entitlement produz a mesma chave.

!!! note "Limitação conhecida da chave"
    No snapshot da POC existe um grant canônico por par identidade × entitlement, então essa chave é suficiente.

    Em um histórico produtivo, a mesma pessoa pode receber, perder e depois receber novamente o mesmo entitlement. Nesse cenário, as concessões são eventos diferentes e devem usar um **ID nativo de concessão** ou uma chave que represente também a temporalidade.

## 2. Observed Baseline — cálculo de prevalência

O baseline mede **quão comum é um entitlement dentro de uma população comparável**.

### Variáveis

| Variável | Significado |
|---|---|
| `population_size` | número de identidades distintas no grupo comparável |
| `support_count` | quantas identidades distintas desse grupo possuem o entitlement |
| `prevalence` | proporção do grupo que possui o entitlement |

### Fórmula

```text
prevalence = support_count / population_size
```

### Exemplo

```text
population_size = 20 pessoas
support_count   = 18 pessoas com o entitlement

prevalence = 18 / 20 = 0,90 = 90%
```

Interpretação: o acesso é **muito comum naquele grupo**. Isso ainda não significa que seja autorizado.

### Quem entra na população observável

O runtime atual considera grants com:

- identidade ativa;
- sem DQ bloqueante;
- relação `same-community`;
- data de concessão conhecida;
- concessão ocorrida até a `assessment_date`.

`assessment_date` é a data de referência da avaliação. Ela impede que informação futura participe de uma análise histórica.

Ela não é, conceitualmente, a mesma coisa que `data_ingestao`:

```text
data_ingestao
= quando os dados foram carregados

assessment_date
= a data em que queremos avaliar a situação
```

No run validado da POC, as duas valem `2025-02-01` porque o DAG atual passa `data_ingestao` para `--assessment-date`. Em produção, a separação é importante para permitir reprocessamento histórico sem alterar a data em que os dados foram fisicamente carregados.

## 3. Hierarchical Fallback — escolha do grupo comparável

O fallback não calcula uma média entre grupos. Ele procura **o primeiro nível suficientemente suportado**, do mais específico para o mais amplo.

### Ordem de tentativa

```text
0. comunidade + squad + cargo + tipo_identidade
1. comunidade + cargo
2. comunidade
3. tipo_identidade
```

### Critério mínimo atual

```text
population_size >= 2
E
support_count >= 2
```

### Variáveis

| Variável | Significado |
|---|---|
| `population_size` | tamanho do grupo de comparação naquele nível |
| `support_count` | número de pessoas do grupo que possuem o entitlement |
| `fallback_depth` | quantos níveis foi necessário ampliar; `0` significa o grupo mais específico |
| `baseline_sufficient` | indica se algum nível atingiu os mínimos |

Se nenhum nível atender aos mínimos, o resultado é:

```text
selection_status = INSUFFICIENT_EVIDENCE
fallback_depth   = 4
```

!!! note
    Os mínimos `2` e `2` são parâmetros demonstrativos da POC. Em produção, precisam de calibração.

## 4. Expected Access — esperado, inesperado ou insuficiente

Expected Access combina **âncora explícita** e **prevalência do baseline selecionado**.

### Ordem da decisão

```text
1. DQ bloqueante ou dado analítico inválido
      → INSUFFICIENT_EVIDENCE

2. hard_trusted_flag = true
      → EXPECTED
      → strength = HIGH

3. baseline não disponível/suficiente
      → INSUFFICIENT_EVIDENCE

4. prevalence >= 0,80
      → EXPECTED

5. prevalence <= 0,20
      → UNEXPECTED

6. 0,20 < prevalence < 0,80
      → INSUFFICIENT_EVIDENCE
```

### Variáveis

| Variável | Significado |
|---|---|
| `hard_trusted_flag` | existe uma âncora explícita forte, hoje principalmente birthright válido |
| `prevalence` | frequência do entitlement no grupo selecionado |
| `data_quality_blocking` | indica problema de qualidade que impede decisão analítica |
| `expectation_evidence_strength` | força da referência usada para classificar expectedness |

### Força da evidência por nível

| Baseline selecionado | Força |
|---|---|
| comunidade + squad + cargo + tipo | `HIGH` |
| comunidade + cargo | `MEDIUM` |
| comunidade | `MEDIUM` |
| população comparável por tipo de identidade | `LOW` |

Exemplo:

```text
population_size = 20
support_count   = 2
prevalence      = 0,10

0,10 <= 0,20
→ UNEXPECTED
```

`UNEXPECTED` significa **incomum**, não `INDEVIDO`.

## 5. Evidence — como a confiabilidade dos fatos é definida

Evidence **não soma tudo em uma nota final**. Cada fato recebe valor, contexto e uma classificação de confiabilidade própria.

### Aprovação

Para o fato de aprovação normalizado:

| Situação | Confiabilidade |
|---|---|
| `CONFIRMED` | `HIGH` |
| `UNCERTAIN` + vínculo `STRONG_INFERRED` | `MEDIUM` |
| `UNCERTAIN` | `LOW` |
| demais casos | `UNKNOWN` |

`STRONG_INFERRED` significa que existe um vínculo inferido forte, mas sem chave causal direta entre request e grant.

### Certificação

```text
decision preenchida
+ reviewed_at preenchida
+ record_id preenchido
→ HIGH

caso contrário
→ UNKNOWN
```

### Expected Access como evidência

| Situação | Confiabilidade |
|---|---|
| `INSUFFICIENT_EVIDENCE` | `UNKNOWN` |
| strength `HIGH` | `HIGH` |
| strength `MEDIUM` | `MEDIUM` |
| strength `LOW` | `LOW` |

### Acesso possivelmente herdado

```text
candidate nulo
→ UNKNOWN

candidate = true + histórico incompleto
→ LOW

demais casos conhecidos
→ HIGH
```

### Cobertura de uso

| `usage_coverage` | Confiabilidade |
|---|---|
| `COMPLETE` | `HIGH` |
| `PARTIAL` | `MEDIUM` |
| outros / desconhecido | `UNKNOWN` |

Essa modelagem evita transformar ausência de dado em certeza.

## 6. Policy — como a classe final é escolhida

Policy não calcula uma média ou probabilidade. Ela avalia regras **em ordem de precedência** e usa a **primeira regra verdadeira**.

```text
R010 → R025 → R020 → R030 → R040 → R140
     → R050 → R060 → R070 → R080 → R130
     → R110 → R120 → R999
```

### Exemplos das condições

| Regra | Condição resumida | Decisão |
|---|---|---|
| `R010` | DQ bloqueante | REVISÃO |
| `R025` | cross + approval forte + certificação REVOKE | REVISÃO |
| `R020` | cross + approval forte | LEGÍTIMO |
| `R030` | cross + approval ausente + fonte autoritativa | INDEVIDO |
| `R040` | certificação REVOKE | REVISÃO |
| `R050` | âncora explícita | PADRÃO |
| `R060` | não birthright + EXPECTED + força HIGH + same/public | PADRÃO |
| `R070` | approval forte | LEGÍTIMO |
| `R080` | aplicação pública sem âncora explícita | LEGÍTIMO |
| `R130` | cross sem approval, mas fonte não autoritativa | REVISÃO |
| `R110` | UNEXPECTED sem violação anterior | REVISÃO |
| `R120` | expectedness insuficiente | REVISÃO |
| `R999` | nenhum caso anterior resolveu | REVISÃO |

Exemplo:

```text
cross-community = true
approval forte  = true
certification   = MAINTAIN

R010? não
R025? não
R020? sim

→ LEGÍTIMO
```

### `decision_confidence`

O runtime atual materializa:

```text
Policy = REVISÃO  → LOW
regra R080        → MEDIUM
demais decisões   → HIGH
```

Isso é uma categoria técnica da POC, não uma probabilidade estatística.

## 7. Risk — cálculo do score

O Risk é calculado **depois da Policy**.

### Fórmula

```text
risk_score = min(
  100,
  decision_component
  + privileged_component
  + criticality_component
  + regulatory_component
  + data_classification_component
  + evidence_component
  + temporal_component
)
```

### Variáveis e pesos atuais

#### Decisão da Policy

| Valor | Pontos |
|---|---:|
| INDEVIDO | 50 |
| REVISÃO | 30 |
| LEGÍTIMO | 5 |
| PADRÃO | 0 |

#### Acesso privilegiado

```text
privileged = true  → +15
privileged = false → +0
```

#### Criticidade da aplicação

| Criticidade | Pontos |
|---|---:|
| CRITICAL | 15 |
| HIGH | 10 |
| LOW | 0 |

#### Escopo regulatório

| Escopo | Pontos |
|---|---:|
| BACEN | 10 |
| SOX | 10 |
| NONE | 0 |

#### Classificação do dado

| Classificação | Pontos |
|---|---:|
| RESTRICTED | 5 |
| CONFIDENTIAL | 3 |
| INTERNAL | 1 |
| PUBLIC | 0 |

#### Evidência

O componente de evidência adiciona **no máximo +5**:

```text
DQ bloqueante                      → +5
senão, certificação REVOKE         → +5
senão, autorização ambígua         → +5
senão                              → +0
```

Essas condições são avaliadas em sequência; elas não somam `5 + 5 + 5`.

#### Temporal

Na versão `RISK001/1.0.0`:

```text
temporal_component = 0
```

Existe como componente versionado, mas ainda não adiciona pontos.

### Exemplo

```text
Policy INDEVIDO        = 50
Privileged             = 15
Critical               = 15
BACEN                  = 10
Restricted             =  5
Evidence contradiction =  5
Temporal               =  0
--------------------------------
risk_score             = 100
```

### Faixas

| Score | Risk band |
|---:|---|
| 0–19 | LOW |
| 20–39 | MEDIUM |
| 40–69 | HIGH |
| 70–100 | CRITICAL |

## 8. `impact_score` e ação operacional

`impact_score` mede impacto **sem usar a classe da Policy nem o componente de evidência**:

```text
impact_score =
  privileged_component
  + criticality_component
  + regulatory_component
  + data_classification_component
```

A ação é definida assim:

```text
Policy = INDEVIDO
→ REMEDIATE

Policy = REVISÃO
→ REVIEW

Policy = PADRÃO ou LEGÍTIMO
+ impact_score >= 20
→ MONITOR

caso contrário
→ NONE
```

O `priority_rank` ordena os grants **dentro de cada classe de Policy** por `risk_score` decrescente; em empate, usa `grant_id` como desempate determinístico.

## 9. Métricas de validação

As métricas abaixo usam apenas casos com `ground_truth` quando a comparação exige resposta conhecida.

### Variáveis básicas

| Variável | Significado |
|---|---|
| `TP` — true positive | casos da classe que foram corretamente classificados nessa classe |
| `FP` — false positive | casos de outras classes classificados incorretamente nessa classe |
| `FN` — false negative | casos da classe que foram classificados como outra classe |
| `support` | quantidade real de exemplos daquela classe no gabarito |

### Precision

```text
precision = TP / (TP + FP)
```

Pergunta respondida: **entre os casos que a solução chamou de uma classe, quantos realmente eram daquela classe?**

### Recall

```text
recall = TP / (TP + FN)
```

Pergunta respondida: **entre todos os casos que realmente eram daquela classe, quantos a solução encontrou?**

### F1

```text
F1 = 2 × precision × recall / (precision + recall)
```

Equilibra precision e recall em uma única métrica.

### Accuracy exata

```text
overall_exact_accuracy =
  decisões iguais ao ground truth
  / grants com ground truth
```

`REVISÃO` conta como diferente quando o gabarito possui uma classe final PADRÃO, LEGÍTIMO ou INDEVIDO.

### Accuracy das decisões automatizadas

```text
automated_decision_accuracy =
  decisões automatizadas corretas
  / decisões automatizadas com ground truth
```

São automatizadas as classes:

```text
PADRÃO
LEGÍTIMO
INDEVIDO
```

`REVISÃO` é uma abstenção e não entra nessa accuracy.

### Taxa de automação

```text
automation_rate =
  grants com decisão PADRÃO, LEGÍTIMO ou INDEVIDO
  / total de grants do runtime
```

### Taxa de revisão

```text
review_rate = grants com REVISÃO / total de grants do runtime
```

### False-safe crítico

```text
ground_truth = INDEVIDO
E policy_decision ∈ {PADRÃO, LEGÍTIMO}
```

Essa métrica conta acessos realmente indevidos classificados como seguros/aceitáveis.

### False-indevido

```text
ground_truth ∈ {PADRÃO, LEGÍTIMO}
E policy_decision = INDEVIDO
```

Essa métrica conta acessos válidos que foram classificados como indevidos.

## 10. Métricas adicionais da POC

### Indevidos priorizados como críticos

```text
indevido_critical_risk_rate =
  ground_truth INDEVIDO com risk_band CRITICAL
  / total de ground_truth INDEVIDO
```

### Identificabilidade do cenário normal

```text
normal_identifiability_90 =
  cenários normal, não-birthright, não-públicos com prevalence >= 0,90
  / total de cenários normal, não-birthright, não-públicos
```

### Cobertura de autorização cross legítimo

```text
cross_legitimo_authorization_coverage =
  LEGÍTIMOS cross com approval STRONG_INFERRED
  / total de LEGÍTIMOS em cenários cross
```

## 11. Resumo ponta a ponta

```mermaid
flowchart LR
    A["Grupo comparável"] --> B["Prevalence"]
    B --> C["Expected Access"]
    C --> D["Evidence<br/>confiabilidade por fato"]
    D --> E["Policy<br/>primeira regra aplicável"]
    E --> F["Risk<br/>soma de componentes"]
    F --> G["Gold"]
    G --> H["Validation<br/>métricas pós-runtime"]
```

Em termos simples:

> **o baseline mede frequência; Expected Access interpreta a frequência; Evidence qualifica os fatos; Policy decide; Risk prioriza; Validation mede o desempenho depois.**

## 12. Onde alterar os parâmetros

| Comportamento | Fonte versionada |
|---|---|
| mínimos do fallback e thresholds de expectedness | `configs/access_intelligence.yml` |
| semântica/versionamento de Evidence | `configs/evidence_engine.yml` |
| ordem e resultado das regras de Policy | `configs/policy_decision_pd002_1_0_1.yml` |
| pesos, faixas e limiar de monitoramento do Risk | `configs/risk.yml` |
| fórmulas de validação | `scripts/validation/run_v2_validation_mart.py` |

Isso torna os cálculos auditáveis e permite distinguir **regra de negócio, parâmetro técnico e fórmula matemática**.
