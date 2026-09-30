# SoD Platform

## Visão geral

Esta POC foi construída para responder a um problema de governança de acessos que antecede a SoD transacional completa: antes de procurar combinações de transações conflitantes, é necessário reduzir o ruído dos acessos atuais e entender **quem possui qual acesso, em qual contexto, com quais evidências e com qual risco**.

O case propõe duas etapas relacionadas:

~~~text
FASE 1 — Sanitização / Access Governance
        ↓
entender o contexto dos acessos
        ↓
separar padrão × legítimo × indevido
        ↓
explicar e priorizar a tratativa
        ↓
FUNDAÇÃO REUTILIZÁVEL
        ↓
FASE 2 — SoD transacional
        ↓
mapear funções, transações e ações
        ↓
detectar acumulações conflitantes
        ↓
considerar exceções e controles compensatórios
~~~

!!! important "Escopo desta POC"
    A implementação atual concentra-se na **Fase 1**, porque esse é o primeiro problema operacional descrito pelo case. A **Fase 2** é apresentada como evolução arquitetural. A documentação não trata a sanitização como SoD plena.

## Como ler esta documentação

A documentação foi separada em duas visões para permitir que pessoas com diferentes perfis entendam a solução.

**Parte I — Negócio** explica o problema sem depender do código. Ela apresenta as duas fases, as regras extraídas do case, as hipóteses assumidas pela POC e como a solução responde aos nove desafios.

**Partes II e III — Arquitetura e Técnica** mostram como o problema foi transformado em componentes de engenharia: Bronze, Silver, Access Context, Hard Trusted Set, Observed Baseline, Hierarchical Fallback, Expected Access, Evidence, Policy, Risk, Gold, validação, observabilidade, Airflow e Streamlit.

**Parte IV — Decisões** registra o que foi experimentado, o que ficou fora do runtime, quais premissas ainda seriam necessárias em produção e como a IA foi utilizada no desenvolvimento.

## Princípios que orientam a solução

1. **Contexto antes da decisão.** Um grant isolado não possui significado suficiente.
2. **Comportamento observado não é autorização.** Um acesso frequente pode estar errado; um acesso raro pode ser legítimo.
3. **Evidência e política são responsabilidades diferentes.** Fatos são organizados antes da classificação.
4. **Classificação e prioridade também são diferentes.** A decisão responde “o que é este acesso?”; o risco responde “o que tratar primeiro?”.
5. **Incerteza deve aparecer.** Ausência de evidência não é automaticamente evidência de irregularidade.
6. **Ground truth não pode contaminar o runtime.** O gabarito é usado apenas depois da execução, na validação offline.
7. **A Fase 1 não deve ser descartável.** Os componentes atuais foram separados para permitir evolução futura para SoD transacional.

## Estado atual

| Elemento | Estado |
|---|---|
| Bronze e Silver | Implementado |
| Access Context | Implementado |
| Hard Trusted Set | Implementado |
| Observed Baseline + Fallback | Implementado |
| Expected Access | Implementado |
| Evidence | Implementado |
| Policy PD002 | Implementado |
| Risk RISK001 | Implementado |
| Gold GOLD001 | Implementado |
| Airflow runtime/validation | Implementado |
| Streamlit | Implementado |
| Peer Discovery / clustering / grafos | Experimental, shadow |
| Matriz SoD transacional | Futuro |
| Arquitetura AWS | Arquitetura-alvo, não implantação atual |

## Tese da solução

A proposta não tenta adivinhar uma regra de acesso apenas pela frequência. Ela combina **contexto organizacional, âncoras explícitas, comportamento observado, evidências de autorização, política determinística, risco e rastreabilidade** para produzir decisões explicáveis e acionáveis em escala.

Acesse **Parte I — Negócio** antes da parte técnica. Essa ordem reproduz a forma como a solução deve ser defendida: primeiro o problema e as regras; depois a implementação.
