# Evolução para a Fase 2 — SoD transacional + inteligência assistida

## Resumo executivo

A Fase 2 não substitui a Fase 1. Ela **reutiliza sua fundação** e adiciona profundidade semântica para responder uma pergunta mais difícil:

> **A combinação de capacidades desta identidade cria um conflito real dentro de um processo de negócio?**

Para isso, a evolução prevista adiciona:

<div class="sod-grid">
  <div class="sod-card"><span class="sod-kicker">Semântica</span><h3>Transaction Context</h3><p>Mapear entitlement → função → transação → ação → objeto/escopo.</p></div>
  <div class="sod-card"><span class="sod-kicker">Descoberta</span><h3>ML + Graph Analytics</h3><p>Encontrar peers, padrões naturais, combinações raras e sinais de comportamento anômalo.</p></div>
  <div class="sod-card"><span class="sod-kicker">Conhecimento</span><h3>LLM + RAG</h3><p>Interpretar catálogos, políticas e manuais para sugerir mapeamentos semânticos e candidatos a conflito.</p></div>
  <div class="sod-card"><span class="sod-kicker">Governança</span><h3>SoD Policy Catalog</h3><p>Versionar conflitos aprovados, escopo, vigência, exceções e controles compensatórios.</p></div>
  <div class="sod-card"><span class="sod-kicker">Controle</span><h3>Conflict Engine</h3><p>Confirmar conflitos somente com regras formais e contexto suficiente.</p></div>
  <div class="sod-card"><span class="sod-kicker">Continuidade</span><h3>Evidence → Policy → Risk</h3><p>Reutilizar a mesma disciplina de decisão explicável construída na Fase 1.</p></div>
</div>

!!! important "Princípio da Fase 2"
    **ML, Graph e LLM + RAG ampliam descoberta e contexto; eles não substituem a política governada nem decidem sozinhos que um acesso é indevido.**

## 1. O que muda em relação à Fase 1

A Fase 1 responde:

> “Este acesso faz sentido para esta identidade neste contexto?”

A Fase 2 acrescenta:

> “Estas capacidades, quando acumuladas, permitem executar etapas incompatíveis do mesmo processo?”

Para isso, entitlement e sigla deixam de ser suficientes.

<div class="sod-mini-flow sod-mini-flow--5">
  <div><strong>1</strong><span>entitlement</span></div>
  <div><strong>2</strong><span>função</span></div>
  <div><strong>3</strong><span>transação</span></div>
  <div><strong>4</strong><span>ação</span></div>
  <div><strong>5</strong><span>objeto / escopo</span></div>
</div>

## 2. A fundação da Fase 1 continua

<div class="sod-diagram" markdown>
  <div class="sod-diagram-title">Núcleo reutilizado</div>
  <div class="sod-diagram-row">
    <div class="sod-node"><strong>Bronze</strong><small>ingestão rastreável</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Silver</strong><small>contratos + DQ</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Context</strong><small>identidade + acesso</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node sod-node--accent"><strong>Evidence</strong><small>fatos + confiabilidade</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Policy</strong><small>decisão governada</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Risk</strong><small>prioridade</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Gold</strong><small>consumo</small></div>
  </div>
  <div class="sod-diagram-band"><strong>Airflow + Observabilidade + Lineage</strong><span>continuam atravessando as duas fases</span></div>
</div>

## 3. Nova camada semântica

Um conflito SoD exige saber o que o acesso permite fazer.

<div class="sod-lane-grid sod-lane-grid--2">
  <div class="sod-lane"><span class="sod-kicker">ENT_AP_001</span><h3>Cadastrar pagamento</h3><p>Contas a Pagar → Pagamento → Criar.</p></div>
  <div class="sod-lane"><span class="sod-kicker">ENT_AP_017</span><h3>Aprovar pagamento</h3><p>Contas a Pagar → Pagamento → Aprovar.</p></div>
</div>

Se a mesma identidade possui as duas capacidades, existe um **candidato a conflito**. A confirmação ainda depende de regra formal, escopo, vigência, exceção e controles compensatórios.

## 4. ML e Graph Analytics: descobrir padrões

Na Fase 2, ML e grafos deixam de ser apenas experimentos de apoio e podem ganhar um papel maior de descoberta.

Eles podem ajudar a encontrar:

- grupos funcionais que não aparecem claramente no organograma;
- peers realmente comparáveis;
- combinações recorrentes de funções;
- combinações raras ou inesperadas;
- comunidades de acesso;
- hubs e relações incomuns;
- novos candidatos a regras SoD.

A saída continua sendo um **sinal**, não uma decisão.

<div class="sod-signal-card">
  <span>ML / Graph</span>
  <strong>Padrão incomum detectado</strong>
  <p>Resultado: <b>POTENTIAL_CONFLICT</b> ou candidato para investigação.</p>
</div>

## 5. LLM + RAG: entender significado e documentação

O LLM entra como **camada semântica assistida**.

O RAG fornece ao modelo documentos corporativos relevantes antes da resposta, por exemplo:

- catálogo de aplicações;
- descrição de roles;
- catálogo de entitlements;
- documentação de transações;
- políticas de segurança;
- procedimentos;
- matriz SoD;
- exceções aprovadas;
- controles compensatórios;
- achados históricos já validados.

O objetivo é transformar nomes técnicos pouco expressivos em semântica de negócio.

<div class="sod-evolution">
  <div class="sod-evolution-col">
    <span class="sod-kicker">Entrada técnica</span>
    <h3>ROLE_FIN_N2</h3>
    <p>Nome isolado com pouco significado para a análise.</p>
  </div>
  <div class="sod-evolution-arrow">→</div>
  <div class="sod-evolution-col sod-evolution-col--highlight">
    <span class="sod-kicker">LLM + RAG</span>
    <h3>Contas a Pagar · Fornecedor · Cadastrar</h3>
    <p>Mapeamento sugerido com fontes recuperadas e confiança explícita.</p>
  </div>
</div>

### O LLM não vira fonte da verdade

A saída desejada é:

~~~text
sugestão semântica
        ↓
fontes utilizadas
        ↓
confidence
        ↓
validação humana / governança
        ↓
Semantic Access Catalog versionado
~~~

O catálogo aprovado passa a alimentar o runtime. A resposta livre do LLM não deve ser usada diretamente como regra de produção.

## 6. RAG com temporalidade e escopo

Uma política recuperada pelo RAG só é útil se for pertinente ao caso.

Por isso os documentos devem carregar metadados como:

- aplicação;
- processo;
- função;
- tipo de documento;
- versão;
- valid_from;
- valid_to;
- escopo organizacional;
- classificação;
- owner.

Isso preserva uma disciplina já presente na Fase 1:

> **evidência futura ou fora de escopo não deve influenciar uma decisão histórica.**

## 7. SoD Policy Catalog

O catálogo formal mantém regras aprovadas, por exemplo:

| Campo | Exemplo |
|---|---|
| rule_id | SOD_FIN_017 |
| função A | CADASTRAR_FORNECEDOR |
| função B | APROVAR_PAGAMENTO |
| processo | Contas a Pagar |
| escopo | mesma entidade / mesmo domínio |
| criticidade | HIGH |
| vigência | versionada |
| exceção permitida | sim, sob condições |
| controle compensatório | revisão independente |

É esse catálogo governado — e não o LLM — que sustenta o Conflict Engine.

## 8. Como controlar falsos positivos

A arquitetura usa o mesmo princípio da Fase 1: **sinal não é decisão**.

<div class="sod-diagram" markdown>
  <div class="sod-diagram-title">Do sinal à decisão</div>
  <div class="sod-diagram-row">
    <div class="sod-node sod-node--future"><strong>ML / Graph</strong><small>padrão ou combinação incomum</small></div>
    <div class="sod-arrow">+</div>
    <div class="sod-node sod-node--future"><strong>LLM + RAG</strong><small>semântica + fontes</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Unified Evidence</strong><small>corroboração e qualidade</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node sod-node--accent"><strong>SoD Rule</strong><small>regra aprovada e vigente</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Exception Check</strong><small>exceção + controle compensatório</small></div>
  </div>
</div>

A plataforma distingue:

<div class="sod-lane-grid">
  <div class="sod-lane"><span class="sod-kicker">Confirmed</span><h3>Conflito confirmado</h3><p>Regra formal aplicável, contexto suficiente e nenhuma exceção válida.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Potential</span><h3>Possível conflito</h3><p>Sinais relevantes existem, mas ainda falta evidência para decisão automática.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Unknown</span><h3>Evidência insuficiente</h3><p>O sistema preserva incerteza em vez de forçar uma resposta.</p></div>
</div>

## 9. Como a decisão final continua governada

~~~text
sinais de ML / Graph
+
sugestões de LLM / RAG
+
contexto transacional
+
regra SoD aprovada
+
exceções / controles
        ↓
Unified Evidence
        ↓
Policy
        ↓
Risk
        ↓
Gold
~~~

O resultado final pode reutilizar a filosofia da Fase 1:

- **PADRÃO** — nenhuma incompatibilidade aplicável;
- **LEGÍTIMO** — situação sensível, porém coberta por exceção ou controle aprovado;
- **INDEVIDO** — conflito confirmado e sem justificativa válida;
- **REVISÃO** — sinais existem, mas a evidência ainda não permite automação segura.

## 10. Arquitetura combinada

<div class="sod-phase-architecture">
  <div class="sod-phase">
    <span class="sod-kicker">Fase 1 · implementada</span>
    <h3>Access Governance</h3>
    <p>Contexto → Baseline → Expected Access → Evidence → Policy → Risk.</p>
  </div>
  <div class="sod-phase-bridge">
    <strong>Fundação compartilhada</strong>
    <span>Bronze · Silver · Evidence · Policy · Risk · Gold · Airflow · Observabilidade</span>
  </div>
  <div class="sod-phase sod-phase--future">
    <span class="sod-kicker">Fase 2 · evolução</span>
    <h3>SoD Transacional</h3>
    <p>Transaction Context + ML/Graph + LLM/RAG + SoD Catalog + Conflict Engine.</p>
  </div>
</div>

## 11. O que pretendemos fazer

Em uma implementação futura, a sequência proposta é:

1. incorporar fontes que descrevam função, transação, ação e escopo;
2. construir o **Transaction Context**;
3. versionar um **Semantic Access Catalog**;
4. usar ML/Graph para descobrir peers, padrões e candidatos;
5. usar LLM + RAG para acelerar interpretação de documentação e mapeamentos;
6. validar sugestões humanas antes de torná-las catálogo de produção;
7. construir o **SoD Policy Catalog**;
8. executar o **Conflict Engine** com regras aprovadas;
9. verificar exceções e controles compensatórios;
10. alimentar o mesmo fluxo de Evidence → Policy → Risk → Gold;
11. medir falsos positivos, taxa de revisão e estabilidade antes de qualquer automação ampla.

## 12. Por que essa evolução é coerente

A Fase 1 já construiu as disciplinas difíceis:

- contratos de dados;
- contexto;
- baseline;
- temporalidade;
- evidência;
- confiabilidade;
- política explícita;
- risco;
- versionamento;
- lineage;
- observabilidade;
- validação separada.

A Fase 2 adiciona **semântica e novas fontes de inteligência**, sem abandonar essas garantias.

> **ML e LLM aumentam cobertura de descoberta. Evidence e Policy continuam controlando a decisão.**
