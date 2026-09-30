# Arquitetura V2 atual

## 1. A arquitetura canônica é o DAG

O runtime V2 não é definido apenas pela existência dos módulos no repositório. A fonte operacional de verdade é o DAG Airflow sod_runtime_v2.

<div class="sod-diagram" markdown>
  <div class="sod-diagram-title">Fluxo de dados e decisão</div>
  <div class="sod-diagram-row">
    <div class="sod-node"><span>01</span><strong>Bronze</strong><small>dados recebidos + metadados</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><span>02</span><strong>Silver</strong><small>contratos + DQ + quarentena</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><span>03</span><strong>Context + HTS</strong><small>contexto factual + âncoras</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node sod-node--accent"><span>04</span><strong>Baseline + EA</strong><small>comportamento esperado</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><span>05</span><strong>Evidence + Policy</strong><small>evidências + decisão</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><span>06</span><strong>Risk + Gold</strong><small>prioridade + publicação</small></div>
  </div>
  <div class="sod-diagram-band"><strong>Control path</strong><span>Airflow · gates · run registry · observabilidade · validação offline</span></div>
</div>

A arquitetura técnica possui, portanto, dois eixos:

**Data/decision path:** transforma dados em decisão.

**Control path:** garante ordem, qualidade, rastreabilidade e observabilidade.

## 2. Preparação — Bronze

Bronze recebe as fontes e preserva a visão ingerida.

Seu objetivo não é “limpar” o dado até ele parecer bom. É registrar o que chegou, com metadados suficientes para reprocessamento e auditoria.

A observabilidade de Bronze registra volumes, arquivos, bytes, falhas e duração.

Depois da execução, Bronze Gate impede avanço se as tabelas obrigatórias estiverem ausentes ou vazias.

## 3. Curadoria — Silver

Silver transforma fontes heterogêneas em contratos canônicos.

Ela concentra:

- normalização;
- tipos;
- chaves;
- DQ;
- quarentena;
- persistência Iceberg.

O DAG usa a opção silver-only. Access Context é executado separadamente depois do Silver Gate.

Essa separação é importante porque canonicalização e interpretação do acesso são responsabilidades distintas.

## 4. Contexto e âncoras

Access Context monta a representação factual por grant.

HTS marca âncoras explícitas.

Esses dois componentes preparam a análise, mas ainda não classificam o acesso.

## 5. Baseline e Fallback

Observed Baseline materializa estatísticas em diferentes níveis de contexto.

Hierarchical Fallback escolhe o nível defensável para cada grant.

Se nenhum nível possui suporte, o pipeline preserva insuficiência de evidência.

## 6. Expected Access

Expected Access converte âncora e prevalência em uma expectativa analítica.

Ele responde:

- EXPECTED;
- UNEXPECTED;
- INSUFFICIENT_EVIDENCE.

Ele não responde “autorizado” ou “indevido”.

## 7. Evidence e Policy

Evidence normaliza fatos e confiabilidade.

Policy aplica regras explícitas e precedência.

Essa divisão é central: o mesmo Evidence Bundle pode ser reavaliado por uma nova versão de Policy sem reconstruir toda a contextualização.

## 8. Risk

Risk recebe a decisão e adiciona impacto.

A ordem é proposital:

~~~text
Policy primeiro
Risk depois
~~~

Se Risk viesse antes, impacto poderia contaminar a própria classificação.

## 9. Gold

Gold é contrato de consumo.

Ela reconcilia os componentes upstream e publica:

- decisão;
- evidências;
- expectedness;
- risco;
- fila operacional;
- versões;
- lineage.

Se a reconciliação falhar, o estágio não deve ser considerado válido.

## 10. Control path: por que Airflow importa

Airflow não está sendo usado apenas para “agendar scripts”.

Ele materializa dependências arquiteturais:

~~~text
não existe Policy válida
sem Evidence válido

não existe Evidence válido
sem Expected Access válido

não existe validação offline
antes de Gold congelada
~~~

Também controla retry e max_active_runs para reduzir concorrência acidental sobre um warehouse local compartilhado.

## 11. Control path: observabilidade

A plataforma acompanha:

- saúde da ingestão;
- DQ e quarentena;
- execução por componente;
- contagem por estágio;
- versões;
- snapshots;
- lineage;
- reconciliação final.

Esse caminho de controle é tão importante quanto as transformações, porque uma decisão sem prova de origem não atende bem a requisitos de auditoria.

## 12. Runtime versus experimental

Peer Discovery existe em modo shadow.

LDA, FP-Growth, NMF-HDBSCAN e Leiden não participam de EA001, Evidence, Policy, Risk ou Gold do runtime V2.

Isso permite experimentação sem colocar um método ainda não aprovado no caminho crítico da decisão.

## 13. Runtime versus validação

~~~text
RUNTIME
  ↓
Gold congelada
  ↓
registro do run
  ↓
trigger
  ↓
VALIDATION DAG
  ↓
ground truth
  ↓
Validation Mart
~~~

A direção é unilateral.

## 14. Propriedades que a V2 busca

**Reprodutibilidade** — versões e snapshots explícitos.

**Explicabilidade** — regra, motivo e evidências por grant.

**Auditabilidade** — lineage, freeze e journal.

**Segurança de decisão** — incerteza não é escondida.

**Operabilidade** — gates, retry, health view e reconciliação.

**Evolutividade** — componentes podem receber a semântica transacional da Fase 2 sem reescrever a fundação.
