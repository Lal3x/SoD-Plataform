# Evolução para a Fase 2 — SoD transacional

## 1. O que muda

A Fase 1 responde principalmente:

> “Este acesso faz sentido para esta identidade neste contexto?”

A Fase 2 acrescenta:

> “A combinação das capacidades desta identidade cria conflito dentro de um processo de negócio?”

Para responder isso, entitlement e sigla deixam de ser suficientes.

## 2. Nova cadeia semântica

~~~text
Entitlement
    ↓
Função
    ↓
Transação
    ↓
Ação
    ↓
Objeto / Escopo
~~~

Exemplo:

~~~text
ENT_AP_001
    ↓
Contas a Pagar
    ↓
Pagamento
    ↓
Criar pagamento
~~~

e:

~~~text
ENT_AP_017
    ↓
Contas a Pagar
    ↓
Pagamento
    ↓
Aprovar pagamento
~~~

Se a mesma identidade possui as duas capacidades, pode existir um conflito. A existência real do conflito ainda depende de escopo, vigência, exceções e controles compensatórios.

## 3. Componentes adicionais

A Fase 2 precisa acrescentar pelo menos quatro capacidades.

### Transaction Context

Normaliza a relação entitlement → função → transação → ação → objeto.

### SoD Policy Catalog

Mantém regras versionadas como:

- funções incompatíveis;
- ações conflitantes;
- escopo da regra;
- owner;
- criticidade;
- vigência;
- exceções permitidas.

### Conflict Engine

Avalia acumulações da identidade e materializa conflitos potenciais.

### Compensating Controls

Registra controles que permitem aceitar ou reduzir um risco sem apagar o fato de que a combinação conflitante existe.

## 4. Arquitetura evoluída

~~~text
                         FONTES
                           │
                           ▼
                    Bronze → Silver
                           │
              ┌────────────┴─────────────┐
              ▼                          ▼
        Access Context            Transaction Context
              │                          │
              │                    entitlement
              │                         ↓
              │                      função
              │                         ↓
              │                    transação
              │                         ↓
              │                       ação
              │                         ↓
              │                  objeto / escopo
              │                          │
              └─────────────┬────────────┘
                            ▼
                  Authorization Context
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
       Expected Access              SoD Policy Catalog
                                      ├── conflicts
                                      ├── exceptions
                                      └── compensating controls
             │                             │
             └──────────────┬──────────────┘
                            ▼
                    SoD Conflict Engine
                            │
                            ▼
                    Unified Evidence
                            │
                            ▼
                         Policy
                            │
                            ▼
                     Risk / Priority
                            │
                            ▼
                           Gold
                     ┌──────┴──────┐
                     ▼             ▼
             Access Assessment  SoD Assessment
                     └──────┬──────┘
                            ▼
                   Review / Remediation
~~~

## 5. O que é reutilizado

A maior parte da plataforma continua válida.

| Componente atual | Papel na Fase 2 |
|---|---|
| Bronze/Silver | ingestão e contratos das novas fontes |
| Access Context | contexto da identidade |
| HTS/Baseline | comportamento esperado continua como evidência |
| Expected Access | sinal adicional, não decisão SoD |
| Evidence | incorpora evidências transacionais e compensatórias |
| Policy | passa a considerar conflitos do catálogo |
| Risk | prioriza conflitos por impacto |
| Gold | publica assessments de acesso e SoD |
| Airflow | orquestra novos jobs |
| Observabilidade | monitora novas fontes e regras |
| Validation Mart | valida conflitos e decisões |

## 6. Matriz SoD não é apenas uma tabela de pares

Uma matriz mínima pode começar com função A × função B, mas produção exige contexto adicional:

- processo;
- transação;
- ação;
- objeto;
- escopo organizacional;
- vigência;
- criticidade;
- owner da regra;
- exceções;
- controle compensatório;
- versionamento.

Sem esses elementos, a matriz tende a produzir falsos positivos ou se tornar impossível de governar.

## 7. Exemplo de decisão futura

~~~text
Identidade possui:
  criar pagamento
  +
  aprovar pagamento
        │
        ▼
Conflict Engine encontra regra ativa
        │
        ▼
Evidence verifica:
  mesmo escopo?
  vigência simultânea?
  exceção formal?
  controle compensatório?
        │
        ▼
Policy classifica
        │
        ▼
Risk prioriza
~~~

## 8. Por que a Fase 1 é fundação

A Fase 2 precisa exatamente das disciplinas já construídas:

- dados canônicos;
- contexto;
- temporalidade;
- evidência;
- política explícita;
- versionamento;
- rastreabilidade;
- priorização;
- validação separada.

Por isso, a arquitetura atual não é uma solução descartável de “limpeza de acessos”. Ela é a primeira camada de uma plataforma de decisão de acesso e SoD.
