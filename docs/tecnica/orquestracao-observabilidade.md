# Orquestração e observabilidade

## 1. Por que estes dois temas são parte da solução

Uma arquitetura de decisão sobre acessos não é confiável apenas porque as transformações estão corretas.

Também é necessário saber:

- em que ordem cada estágio rodou;
- quais inputs estavam disponíveis;
- se alguma camada estava vazia;
- qual run produziu a decisão;
- quais snapshots foram usados;
- se o resultado final reconciliou com os componentes upstream;
- se a distribuição das decisões mudou;
- se houve queda de qualidade ou aumento de quarentena.

Por isso, **orquestração e observabilidade são capacidades de controle**, não detalhes operacionais.

## 2. Airflow como contrato de ordem

O DAG V2 define a sequência operacional canônica:

~~~text
validar parâmetros/fontes
        ↓
Bronze
        ↓
Bronze Gate
        ↓
Silver
        ↓
Silver Gate
        ↓
Access Context + HTS
        ↓
Observed Baseline + Fallback
        ↓
Expected Access
        ↓
Evidence
        ↓
Policy
        ↓
Risk
        ↓
Gold
        ↓
Gold Gate
        ↓
registrar run
        ↓
disparar validação offline
~~~

Essa ordem possui semântica.

Expected Access não pode rodar antes do baseline. Policy não deve rodar antes de Evidence. Validação não deve acontecer antes de Gold estar congelada.

## 3. Gates — falhar cedo

O runtime possui gates depois de Bronze, Silver e Gold.

O gate verifica se as tabelas esperadas:

- existem;
- possuem ao menos um registro.

Exemplo:

~~~text
Silver terminou
     ↓
gate_silver
     ↓
tabelas esperadas existem?
     ↓
possuem dados?
     ↓
sim → continua
não → DAG falha
~~~

Isso impede que um estágio posterior trate ausência de dados como comportamento de negócio.

!!! note "Limite atual"
    Os gates V2 são deliberadamente simples: existência e não-vazio. Em produção, poderiam incluir freshness, schema, volume esperado, DQ crítica, reconciliação e SLAs.

## 4. Retry e determinismo

O DAG configura retries para as tarefas.

Isso exige que cada estágio suporte reexecução segura.

Os scripts runtime trabalham com snapshots e, em etapas como Policy, Risk e Gold, substituem a saída do próprio estágio quando necessário para manter retry determinístico.

O objetivo é evitar:

~~~text
primeira tentativa grava output
        ↓
falha ao registrar artefato
        ↓
retry duplica resultado
~~~

A reexecução deve reproduzir o estágio, não multiplicá-lo.

## 5. Registro do run

Depois do Gold Gate, o runtime registra:

- dataset_version;
- lote;
- data_ingestao;
- airflow_run_id;
- timestamp de registro.

Esse registro conecta a execução do orquestrador aos artefatos gerados.

Em uma arquitetura produtiva, esse journal deveria migrar para um repositório persistente central de runs, com status, ownership, SLA e referência de snapshots.

## 6. Validação offline só depois do runtime

O último passo do DAG runtime dispara o DAG de validação.

Isso garante a direção correta:

~~~text
runtime produz
      ↓
runtime congela
      ↓
validation observa
~~~

e evita:

~~~text
validation influencia
      ↓
runtime produz
~~~

Essa separação é uma barreira contra data leakage.

## 7. Observabilidade em três níveis

A observabilidade foi pensada em três camadas.

### Nível 1 — ingestão e qualidade

Bronze possui métricas como:

- arquivos descobertos;
- processados;
- ignorados;
- falhos;
- registros recebidos;
- registros escritos;
- bytes processados;
- audit failures;
- duração.

Silver persiste resultados de qualidade e quarentena.

### Nível 2 — componentes analíticos

Access Intelligence possui journal persistido em Iceberg:

~~~text
sod.metadata.access_intelligence_runs
~~~

Cada evento registra:

- run_id;
- component;
- status;
- started_at;
- finished_at;
- duration_seconds;
- metrics_json.

Isso permite responder:

> “Qual componente rodou, quando, com qual resultado e quais métricas?”

### Nível 3 — reconciliação da decisão

O dashboard de observabilidade compara Gold com outputs upstream.

As reconciliações incluem:

- Policy;
- Risk;
- Expected Access;
- Evidence.

Se Gold publicou uma decisão diferente da Policy congelada, isso é um problema de integridade do pipeline, não uma diferença aceitável.

## 8. O que o dashboard consegue observar hoje

A página Saúde dos Dados e do Pipeline expõe:

### Contagens entre estágios

- Bronze grants;
- Silver grants;
- Access Context;
- Expected Access;
- Evidence summaries;
- Evidence facts;
- Policy;
- Risk;
- Gold.

### Qualidade

- resultados de DQ;
- quarentena;
- agrupamentos por status/severity/regra quando disponíveis.

### Consistência

- divergências entre Gold e Policy;
- divergências entre Gold e Risk;
- divergências de expectedness;
- divergências de Evidence.

### Auditoria

- versões;
- snapshots;
- input tables;
- output table;
- processing timestamp.

## 9. Por que contagem entre camadas importa

Considere:

~~~text
Bronze grants = 75.585
Silver grants = 75.577
Gold = 75.577
~~~

A diferença entre Bronze e Silver precisa ser explicável por qualidade, duplicidade, integridade ou regras de canonicalização.

Sem observabilidade, alguém poderia ver apenas Gold e nunca perceber que houve descarte ou quarentena.

Com observabilidade, a pergunta muda de:

> “O job terminou?”

para:

> “O job terminou com dados completos, reconciliados e dentro do comportamento esperado?”

## 10. Observabilidade da decisão

Não basta monitorar CPU e duração.

Também é importante acompanhar distribuições como:

- PADRÃO / LEGÍTIMO / INDEVIDO / REVISÃO;
- Expected / Unexpected / Insufficient Evidence;
- níveis de fallback;
- regras de Policy mais frequentes;
- risk bands;
- proporção de remediação versus revisão.

Exemplo:

~~~text
ontem:
REVISÃO = 8%

hoje:
REVISÃO = 42%
~~~

Mesmo que todos os jobs estejam verdes, essa mudança pode indicar:

- fonte de requests incompleta;
- quebra de join;
- mudança organizacional;
- alteração de regra;
- problema de baseline.

Isso é **observabilidade semântica**.

## 11. Lineage e snapshots

A Gold preserva referências às versões e snapshots utilizados.

A observabilidade expõe:

~~~text
input_tables
input_snapshots
output_table
output_snapshot
~~~

Isso permite reconstruir a cadeia de dados que levou a uma decisão.

Em contexto de auditoria, “qual código rodou?” não é suficiente. Também precisamos saber “sobre qual estado dos dados?”.

## 12. Como isso evolui na AWS

Na arquitetura-alvo:

- MWAA assume a orquestração;
- CloudWatch centraliza logs, métricas e alarmes;
- Glue/Iceberg preservam catálogo e snapshots;
- CloudTrail registra ações administrativas;
- Lake Formation/IAM ajudam a provar fronteiras de acesso;
- dashboards podem acompanhar SLOs de dados e decisão.

O princípio permanece o mesmo: **pipeline confiável é pipeline observável e reproduzível**.

## 13. Valor de engenharia

Orquestração e observabilidade agregam valor porque reduzem três riscos:

| Risco | Controle |
|---|---|
| executar estágio com input inválido | dependências + gates |
| publicar decisão inconsistente | freezes + reconciliação |
| não conseguir explicar uma execução | journal + snapshots + lineage |

Isso transforma a POC de um conjunto de scripts em uma plataforma operacionalmente governável.
