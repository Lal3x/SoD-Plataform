# Evolução da solução

A arquitetura V2 é resultado de refinamentos sucessivos. Cada componente existe para resolver uma pergunta concreta.

!!! info "A ideia não foi descartada"
    A arquitetura inicial **não estava “errada” e depois foi substituída**. A tese permaneceu: entender contexto, estabelecer uma referência, localizar desvios, usar evidências e aplicar regras. A V2 separou essas capacidades em componentes com responsabilidades, contratos e testes próprios.

## 1. Da ideia para responsabilidades explícitas

| Problema encontrado | Risco de uma solução simples | Decisão | Consequência arquitetural |
|---|---|---|---|
| Grant isolado não explica contexto | classificar sem entender organização | contextualizar antes de inferir | Access Context |
| Frequência pode refletir erro histórico | “popular = autorizado” | separar comportamento de autorização | Observed Baseline + Expected Access |
| Birthright não deveria depender da frequência | perder âncora explícita | manter âncoras determinísticas | Hard Trusted Set |
| Grupos pequenos não sustentam estatística | falsos desvios | ampliar referência gradualmente | Hierarchical Fallback |
| Aprovação pode ser ambígua | legitimar grant errado | preservar qualidade do vínculo | Evidence |
| Expectedness não é política | raro virar indevido automaticamente | decisão em camada separada | Policy |
| Classe não representa impacto | filas sem prioridade | calcular impacto após decisão | Risk |
| Gold poderia virar “caixa-preta” | regra escondida na camada de consumo | Gold apenas materializa | GOLD001 |
| Gabarito pode contaminar thresholds | data leakage | validar somente depois do runtime | Validation Mart |
| Clustering pode ser instável | decisão difícil de explicar | testar fora do runtime | Shadow experiments |

## 2. Access Context

Primeiro foi necessário transformar múltiplas fontes em um registro factual por grant.

Access Context agrega, sem decidir:

- identidade;
- comunidade, squad e cargo;
- entitlement e sigla;
- owner community;
- birthright;
- caráter público;
- temporalidade;
- aprovação;
- certificação;
- criticidade;
- privilégio;
- lineage.

Ele também conserva incertezas. Por exemplo, approval_linkage_quality e usage_coverage existem exatamente para não esconder limitações da fonte.

## 3. Hard Trusted Set e Observed Baseline

Durante o refinamento ficou claro que havia dois conceitos distintos.

**Hard Trusted Set** responde:

> Existe uma âncora explícita e suficientemente forte para este grant?

**Observed Baseline** responde:

> Com que frequência este entitlement aparece em uma população comparável observável?

Eles são complementares, mas não equivalentes.

!!! info "Controle importante da V2"
    O Observed Baseline atual é construído sobre uma população filtrada por qualidade, identidade ativa, temporalidade e same-community. Ele **não é restrito apenas ao Hard Trusted Set**. Por isso, a baseline é tratada como **evidência comportamental**, nunca como autorização. Policy, certificações, aprovações e força da evidência funcionam como controles independentes.

## 4. Hierarchical Fallback

A primeira população pode ser pequena demais.

A solução tenta níveis progressivamente mais amplos, preservando o tipo de identidade no nível mais amplo:

~~~text
1. comunidade + squad + cargo + tipo_identidade
2. comunidade + cargo
3. comunidade
4. tipo_identidade
~~~

O objetivo não é encontrar um grupo a qualquer custo. Se a evidência continua fraca, o resultado deve permanecer insuficiente.

## 5. Expected Access

Expected Access combina:

- âncora explícita de HTS;
- baseline selecionado;
- prevalência;
- suficiência da população;
- força da evidência.

Ele produz:

- EXPECTED;
- UNEXPECTED;
- INSUFFICIENT_EVIDENCE.

Essa saída ainda não é a classificação de negócio.

## 6. Evidence

Evidence converte sinais dispersos em fatos normalizados.

Exemplos:

- relação entre comunidades;
- status de aprovação;
- qualidade do match;
- certificação;
- ausência de uso registrada;
- cobertura de uso;
- candidato a acesso herdado;
- contradições;
- qualidade dos dados;
- expectedness.

Nenhuma regra de prioridade deveria estar aqui.

## 7. Policy

Policy é o local em que fatos se tornam uma decisão.

A V2 canônica usa PD002/1.0.1 e uma precedência explícita de regras. Isso torna a classificação reproduzível e auditável.

!!! note "Códigos internos da POC"
    Identificadores como `PD002`, `GOLD001`, `EV001`, `RISK001` e regras `R010`, `R020` etc. são **nomes internos usados para versionar contratos e lógica deste projeto**. Eles não representam normas externas, regulamentações ou códigos oficiais do banco.

## 8. Risk

Risk é executado depois da decisão. Ele combina a classe com impacto:

- privilégio;
- criticidade;
- escopo regulatório;
- classificação de dados;
- contradições de evidência.

Assim, dois grants da mesma classe podem receber prioridades diferentes.

## 9. Gold e validação

Gold não cria inteligência nova. Ele reúne outputs já produzidos e preserva lineage e versões.

Depois que o runtime é congelado, a validação offline pode comparar a saída com o gabarito sem risco de leakage.

## 10. Resultado do refinamento

```mermaid
flowchart LR
    A["V0<br/>Bronze → Silver → baseline / grupos / experimentos / regras → Gold"]
    -->|"formalização"|
    B["V2<br/>Context → HTS + Baseline/Fallback → Expected Access → Evidence → Policy → Risk → Gold"]
```

A evolução não foi adicionar complexidade por estética. Cada separação reduz uma ambiguidade específica do problema.
