<div class="sod-hero" markdown>

<span class="sod-eyebrow">Access Governance · Data Engineering · Security</span>

# SoD Platform

Uma POC executável para transformar acessos dispersos em **decisões explicáveis, priorizadas e auditáveis**, resolvendo a sanitização top-down da Fase 1 sem fechar o caminho para a SoD transacional da Fase 2.

<div class="sod-actions">
<a href="negocio/problema-e-fases/" class="md-button md-button--primary">Entender o problema</a>
<a href="arquitetura/arquitetura-v2/" class="md-button sod-secondary">Ver arquitetura V2</a>
</div>

</div>

<div class="sod-metric-strip">
  <div class="sod-metric"><b>Fase 1</b><span>sanitização e governança de acesso</span></div>
  <div class="sod-metric"><b>4 decisões</b><span>PADRÃO · LEGÍTIMO · INDEVIDO · REVISÃO</span></div>
  <div class="sod-metric"><b>Runtime V2</b><span>Airflow + Spark + Iceberg</span></div>
  <div class="sod-metric"><b>Fase 2</b><span>evolução para SoD transacional</span></div>
</div>

!!! tip "Não conhece IAM ou os termos técnicos?"
    A documentação foi escrita para começar pela linguagem de negócio. Consulte o [Vocabulário essencial](negocio/vocabulario.md) para entender termos como grant, birthright, cross-community, baseline, Hierarchical Fallback, âncora, Policy e Risk.

## O problema em uma frase

Hoje, descobrir se um acesso é realmente inadequado pode exigir entrevistas, conhecimento distribuído e análise manual. O desafio é transformar esse processo em uma decisão baseada em dados **sem confundir comportamento frequente com autorização**.

<div class="sod-flow" markdown>

**A proposta:** contextualizar o acesso → estimar comportamento esperado → organizar evidências → aplicar política explícita → calcular risco → publicar uma fila acionável.

</div>

## Duas fases, uma única fundação

A solução foi desenhada para resolver o problema imediato sem criar uma arquitetura descartável.

~~~text
FASE 1 — AGORA
sanitizar acessos por comunidade
        │
        ├─ contexto organizacional
        ├─ padrão observado
        ├─ exceções legítimas
        ├─ evidências de autorização
        ├─ decisão explicável
        └─ priorização por risco
        │
        ▼
FUNDAÇÃO DE GOVERNANÇA
        │
        ▼
FASE 2 — EVOLUÇÃO
entitlement → função → transação → ação
        │
        ├─ conflitos SoD
        ├─ escopo
        ├─ vigência
        ├─ exceções
        └─ controles compensatórios
~~~

!!! important "Escopo correto"
    A POC implementa a **Fase 1**. Ela não chama a sanitização top-down de “SoD plena”. A **Fase 2** é uma arquitetura evolutiva que reutiliza contexto, evidência, política, risco, lineage, observabilidade e operação.

## A arquitetura em uma visão

~~~text
                    ┌──────────────────────────────┐
                    │      ORQUESTRAÇÃO AIRFLOW    │
                    │ ordem · gates · retry · run  │
                    └──────────────┬───────────────┘
                                   │
Sources → Bronze → Silver → Access Context
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
          Hard Trusted Set       Observed Baseline
                                          │
                                  Hierarchical Fallback
                  └───────────┬───────────┘
                              ▼
                       Expected Access
                              ▼
                           Evidence
                              ▼
                        Policy PD002
                              ▼
                         Risk RISK001
                              ▼
                         Gold GOLD001
                              ▼
                 Dashboard / Review / Action

       OBSERVABILIDADE atravessa todo o fluxo:
       métricas · DQ · quarentena · snapshots · lineage
       reconciliação · versões · saúde da decisão
~~~

A escolha de colocar **orquestração e observabilidade ao redor do fluxo**, e não no final, é deliberada: uma decisão de acesso só é confiável se for possível provar **qual dado entrou, em que ordem foi processado, qual versão decidiu e se o resultado final reconciliou com os componentes upstream**.

## O que está implementado

<div class="sod-grid">
  <div class="sod-card"><span class="sod-kicker">Implementado</span><h3>Pipeline de dados</h3><p>Bronze e Silver com contratos, qualidade, quarentena e persistência Iceberg.</p></div>
  <div class="sod-card"><span class="sod-kicker">Implementado</span><h3>Entendimento do acesso</h3><p>Contexto, referências explícitas confiáveis, padrão observado e comparação por pares. Na parte técnica: Access Context, HTS, Baseline, Fallback e Expected Access.</p></div>
  <div class="sod-card"><span class="sod-kicker">Implementado</span><h3>Decisão e prioridade</h3><p>Fatos são organizados, regras classificam e o risco define o que tratar primeiro. Tecnicamente: Evidence → Policy → Risk → Gold.</p></div>
  <div class="sod-card"><span class="sod-kicker">Operação</span><h3>Airflow</h3><p>DAG V2 com gates, dependências, retries, registro de execução e validação offline separada.</p></div>
  <div class="sod-card"><span class="sod-kicker">Controle</span><h3>Observabilidade</h3><p>Contagens, DQ, quarentena, journal de componentes, snapshots, lineage, versões e reconciliação.</p></div>
  <div class="sod-card"><span class="sod-kicker">Consumo</span><h3>Streamlit</h3><p>Visões executiva, operacional, explicabilidade, validação e saúde do pipeline.</p></div>
</div>

## Três princípios que evitam decisões perigosas

### 1. Frequência não é autorização

Se 90% de um grupo possui determinado entitlement, isso prova que o acesso é **comum**, não que ele seja **permitido**. Por isso Expected Access é anterior à Policy.

### 2. Ausência de evidência não é automaticamente irregularidade

Se não existe registro de uso, mas a cobertura da telemetria é desconhecida, a conclusão correta é **“sem uso registrado”**, e não “nunca utilizado”. Se uma autorização não pode ser ligada com confiança ao grant, a incerteza é preservada.

### 3. Classificação não é prioridade

Policy responde **o que o acesso é**. Risk responde **o que tratar primeiro**. Um acesso pode ser legítimo e ainda assim possuir alto impacto. Alto impacto não reclassifica automaticamente um acesso legítimo como indevido.

## Como ler

<div class="sod-grid">
  <div class="sod-card sod-card--wide"><span class="sod-kicker">01 · Negócio</span><h3>Comece pelo problema</h3><p>Entenda as duas fases, as regras explícitas do case, as hipóteses da POC e os nove desafios antes de entrar em componentes.</p></div>
  <div class="sod-card sod-card--wide"><span class="sod-kicker">02 · Arquitetura</span><h3>Veja como a solução evoluiu</h3><p>A arquitetura inicial é confrontada com problemas reais de contexto, temporalidade, grupos pequenos, leakage e explicabilidade até chegar à V2.</p></div>
  <div class="sod-card sod-card--wide"><span class="sod-kicker">03 · Técnica</span><h3>Entre nos contratos</h3><p>Grain, inputs, outputs, baseline, regras, score, gates, observabilidade, testes e operação são explicados com exemplos.</p></div>
  <div class="sod-card sod-card--wide"><span class="sod-kicker">04 · Decisões</span><h3>Entenda trade-offs</h3><p>Experimentos shadow, limitações, premissas de produção e o papel da IA são tratados sem esconder incertezas.</p></div>
</div>

## Estado da solução

| Elemento | Estado | Papel |
|---|---|---|
| Bronze / Silver | <span class="sod-status sod-status--live">IMPLEMENTADO</span> | ingestão, contrato e qualidade |
| Access Context / HTS / Baseline / EA | <span class="sod-status sod-status--live">IMPLEMENTADO</span> | inteligência de acesso |
| Evidence / Policy / Risk / Gold | <span class="sod-status sod-status--live">IMPLEMENTADO</span> | decisão e priorização |
| Airflow runtime + validation | <span class="sod-status sod-status--live">IMPLEMENTADO</span> | controle operacional |
| Observabilidade + dashboard | <span class="sod-status sod-status--live">IMPLEMENTADO</span> | saúde, auditoria e consumo |
| Peer Discovery / clustering / grafos | <span class="sod-status sod-status--shadow">SHADOW</span> | experimentação |
| Matriz SoD transacional | <span class="sod-status sod-status--future">FASE 2</span> | estado futuro |
| AWS | <span class="sod-status sod-status--future">ARQUITETURA-ALVO</span> | produção cloud |

A documentação foi escrita para permitir que a solução seja questionada. Onde existe uma premissa de POC, ela é declarada; onde existe uma limitação, ela não é escondida.
