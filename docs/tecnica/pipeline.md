# Pipeline e contratos de dados

## 1. Pipeline não é apenas sequência de transformações

Nesta POC, cada camada possui uma responsabilidade específica e um contrato de entrada/saída. Isso evita que uma regra de negócio apareça escondida em uma etapa de ingestão ou que um problema de qualidade seja confundido com evidência de risco.

!!! tip "Em linguagem simples"
    O pipeline faz sete coisas em ordem: **recebe os dados → padroniza → entende o contexto → mede o comportamento esperado → organiza evidências → aplica regras → prioriza e publica o resultado**.

Antes da tabela, duas definições ajudam na leitura:

- **nível de detalhe:** indica o que cada linha representa;
- **canônico:** formato padronizado em que o restante da plataforma pode confiar;
- **lineage:** trilha que permite descobrir de qual fonte, arquivo e execução um dado veio.

| Etapa | Nível de detalhe principal | Input | Output | Papel |
|---|---|---|---|---|
| Bronze | registro da fonte | arquivos/source extracts | tabelas Bronze | preservar ingestão e lineage |
| Silver | entidade/grant canônico | Bronze | tabelas canônicas | normalizar e validar |
| Access Context | grant × assessment_date | Silver + dimensões | contexto factual | enriquecer sem decidir |
| HTS | grant × assessment_date | Access Context | âncora explícita | identificar confiança forte |
| Baseline | população × entitlement × data | Access Context | prevalência | medir comportamento |
| Fallback | grant × assessment_date | Context + Baseline | baseline selecionado | escolher referência |
| Expected Access | grant × assessment_date | HTS + Fallback | expectation | estimar expectedness |
| Evidence | grant × assessment_date | Context + EA + requests/cert | bundle de fatos | normalizar evidência |
| Policy | grant × assessment_date | Evidence | decisão | classificar |
| Risk | grant × assessment_date | Policy + Context | score/prioridade | ordenar ação |
| Gold | grant × assessment_date | outputs congelados | assessment final | publicar consumo |

## 2. Bronze — preservar o que chegou

Bronze responde:

> “O que recebemos, quando recebemos e de qual fonte?”

Ela registra dados antes de qualquer interpretação de negócio.

A observabilidade de ingestão acompanha:

- arquivos descobertos;
- processados;
- ignorados;
- falhos;
- registros recebidos;
- registros escritos;
- bytes processados;
- duração;
- falhas de auditoria.

Esse nível é importante porque um problema upstream pode alterar todo o comportamento analítico sem gerar erro de código.

## 3. Bronze Gate

Após materializar Bronze, o DAG executa um gate.

O gate atual verifica se todas as tabelas obrigatórias existem e estão não vazias.

Ele é simples, mas responde a um princípio importante:

> **não executar inteligência sobre ausência silenciosa de dados.**

Em produção, esse gate poderia evoluir para validar freshness, schema, volume mínimo/máximo e SLA.

## 4. Silver — canonicalização e DQ

Silver responde:

> “Qual é a representação canônica em que o restante da plataforma pode confiar?”

Ela trata:

- tipos;
- nomes;
- formatos;
- chaves;
- integridade;
- qualidade;
- quarentena.

Problemas estruturais devem ser isolados aqui, e não reinterpretados depois como “anomalia de acesso”.

### Exemplo

~~~text
grant com identidade inexistente
        ↓
problema de integridade
        ↓
quarentena / DQ

não:

grant estranho
        ↓
INDEVIDO
~~~

Esse detalhe evita falsos positivos causados por dados quebrados.

## 5. Do nível de negócio ao nível de cada decisão

O case trabalha com comunidade e Entitlement × Sigla.

Para decidir e explicar um caso individual, a implementação trabalha em um nível mais específico:

~~~text
grant_id + assessment_date
~~~

Em linguagem simples, isso significa **um acesso específico de uma identidade avaliado em uma determinada data**.

Por quê?

Porque duas pessoas com o mesmo entitlement podem possuir:

- datas de concessão diferentes;
- aprovações diferentes;
- comunidade diferente;
- contexto de risco diferente;
- certificação diferente.

A decisão deve ser reconstruível para o grant individual.

## 6. Temporalidade faz parte do contrato

A assessment_date não é apenas metadado.

Ela impede que o futuro contamine o passado.

Exemplos:

- grant concedido depois da avaliação não entra no baseline daquela data;
- approval posterior ao grant não deve ser tratada automaticamente como autorização original;
- evidência futura é rejeitada pela Policy.

A plataforma tenta responder:

> “Com o que sabíamos naquele momento, qual seria a decisão?”

Isso é mais auditável do que usar sempre o estado atual.

## 7. Persistência Iceberg

Iceberg é usado porque snapshots fazem parte da arquitetura.

Eles ajudam a responder:

- qual estado da tabela foi usado?
- o input mudou depois?
- qual output corresponde àquele run?
- é possível reconstruir a cadeia?

A V2 congela snapshots entre estágios críticos.

## 8. Reconciliação entre camadas

Uma boa pipeline não olha apenas se o job terminou.

Ela pergunta:

~~~text
Bronze grants
   ↓
Silver grants
   ↓
Access Context
   ↓
Expected Access
   ↓
Policy
   ↓
Risk
   ↓
Gold
~~~

As diferenças de volume precisam ser explicáveis.

Se Bronze possui mais registros que Silver, o motivo deve aparecer em DQ, duplicidade, integridade ou quarentena.

Se Policy possui 75.577 decisões e Gold publica 75.570, isso é falha de reconciliação.

## 9. Exemplo de reconciliação da POC

O run final recebeu **75.585 access assignments** e publicou **75.577 grants canônicos** na Silver.

A diferença foi explicada pelos controles de qualidade:

```text
75.585 registros recebidos
    - 2 duplicados
    - 3 referências de identidade inválidas
    - 3 referências de entitlement inválidas
-------------------------------------------
75.577 grants canônicos
```

Isso demonstra por que reconciliação faz parte do pipeline: uma diferença de volume só é aceitável quando existe uma causa conhecida e observável. Em produção, diferenças não explicadas devem ser tratadas como falha de controle.

## 10. Idempotência e retry

Airflow pode executar retry.

Logo, estágios precisam ser reexecutáveis.

Nas etapas congeladas, a lógica de escrita substitui a saída do próprio estágio quando necessário, evitando duplicação em caso de retry após uma falha parcial de operação.

O objetivo é:

~~~text
mesmo input + mesma versão
        ↓
mesmo resultado lógico
~~~

## 11. O que não existe hoje

A POC local não implementa uma transação distribuída global envolvendo todas as tabelas.

Cada estágio possui sua persistência e seus gates.

Em produção, isso exigiria disciplina de run state, commit por estágio, rollback lógico, cleanup e catálogo operacional central.

Documentar essa limitação é mais correto do que sugerir atomicidade que a implementação não possui.
