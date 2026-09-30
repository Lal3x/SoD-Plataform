# Arquitetura inicial e fundamentos de Segurança da Informação

## 1. A arquitetura inicial já tinha uma tese

O desenho inicial não partiu apenas de ferramentas de Engenharia de Dados. Ele partiu de uma combinação de **princípios de Segurança da Informação** com uma arquitetura capaz de executá-los em escala.

> **não é possível identificar um desvio de acesso sem antes estabelecer uma referência de comportamento esperado, entender o contexto e preservar evidências para explicar a decisão.**

```mermaid
flowchart LR
    A["Fontes<br/>identidades · acessos · contexto"] --> B["Bronze<br/>preservar o recebido"]
    B --> C["Silver<br/>qualidade · contratos · chaves"]

    subgraph ANALYTICS["ANÁLISE / CLASSIFICAÇÃO"]
        D["Baseline"] --> E["Análise por grupos"]
        E --> F["Clustering / Peer Discovery"]
        E --> G["Detecção de desvios"]
        F --> G
        G --> H["Regras / hipótese SoD"]
    end

    C --> D
    H --> I["Gold"]
    I --> J["Visualização"]
    O["Observabilidade"] -. qualidade · execução · rastreabilidade .-> B
    O -. acompanha .-> C
    O -. acompanha .-> ANALYTICS
    O -. acompanha .-> I
```

A V2 não substituiu esse raciocínio. Ela **formalizou responsabilidades que inicialmente estavam agrupadas**.

## 2. Segurança da Informação já orientava a solução

<div class="sod-grid">
  <div class="sod-card"><span class="sod-kicker">Baseline</span><h3>Normal antes do desvio</h3><p>Estabelecer uma referência de comportamento esperado antes de procurar anomalias. Na V2 isso foi formalizado em Observed Baseline, Fallback e Expected Access.</p></div>
  <div class="sod-card"><span class="sod-kicker">Least Privilege</span><h3>Menor privilégio</h3><p>A pergunta central sempre foi se a pessoa realmente precisa daquele acesso para o seu contexto, evitando permissões além do necessário.</p></div>
  <div class="sod-card"><span class="sod-kicker">Need-to-Know</span><h3>Contexto importa</h3><p>Um acesso fora da comunidade não é automaticamente errado; ele precisa ser interpretado à luz da necessidade funcional e de evidências de autorização.</p></div>
  <div class="sod-card"><span class="sod-kicker">Anomaly Detection</span><h3>Desvio é sinal</h3><p>Comportamento raro ajuda a direcionar investigação, mas não é tratado sozinho como prova de irregularidade.</p></div>
  <div class="sod-card"><span class="sod-kicker">SoD</span><h3>Separação de responsabilidades</h3><p>A hipótese de matriz SoD já existia; a evolução separou a sanitização da Fase 1 da análise transacional mais profunda da Fase 2.</p></div>
  <div class="sod-card"><span class="sod-kicker">Accountability</span><h3>Decisão auditável</h3><p>Gold e observabilidade já eram necessidades do desenho inicial. A V2 materializou lineage, snapshots, versões e reason codes.</p></div>
</div>

!!! info "Leitura correta"
    **A Engenharia de Dados fornece escala, contratos e rastreabilidade; Segurança da Informação fornece os princípios que determinam o que observar, comparar e proteger.**

### Como esses princípios viraram arquitetura

<div class="sod-security-map">
  <div><b>Baseline + monitoramento comportamental</b><span>motivaram comparação por grupos, prevalência e identificação de desvios.</span></div>
  <div><b>Least Privilege</b><span>orientou a busca por acessos além do necessário, sem transformar raridade em culpa.</span></div>
  <div><b>Need-to-Know</b><span>levou ao uso de comunidade, função e contexto para interpretar a necessidade do acesso.</span></div>
  <div><b>Segregation of Duties</b><span>manteve desde o início o horizonte de detectar combinações incompatíveis de capacidades.</span></div>
  <div><b>Accountability e auditoria</b><span>motivaram Gold, observabilidade, lineage, snapshots, reason codes e versionamento.</span></div>
  <div><b>Defesa em camadas</b><span>aparece na separação entre qualidade, contexto, comportamento, evidência, política e risco.</span></div>
</div>

## 3. A baseline não surgiu na V2

Desde o início, a análise por grupos e a detecção de anomalias pressupunham uma baseline.

O raciocínio era:

<div class="sod-mini-flow">
  <div><strong>1</strong><span>definir população comparável</span></div>
  <div><strong>2</strong><span>entender o comportamento normal</span></div>
  <div><strong>3</strong><span>identificar desvios</span></div>
  <div><strong>4</strong><span>investigar com contexto e regras</span></div>
</div>

A implementação V2 apenas tornou essa ideia explícita:

<div class="sod-diagram sod-diagram--compact" markdown>
  <div class="sod-diagram-row">
    <div class="sod-node sod-node--accent"><strong>Observed Baseline</strong><small>mede prevalência em grupos comparáveis</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Hierarchical Fallback</strong><small>amplia a comparação quando o grupo é pequeno</small></div>
    <div class="sod-arrow">→</div>
    <div class="sod-node"><strong>Expected Access</strong><small>esperado, inesperado ou evidência insuficiente</small></div>
  </div>
</div>

Isso é diferente de autorização. Um acesso pode ser frequente e ainda assim contrariar uma regra.

## 4. O bloco analítico inicial já continha várias hipóteses

| Ideia inicial | Pergunta que já existia | Formalização posterior |
|---|---|---|
| análise por grupos | com quem esta pessoa deve ser comparada? | grupos comparáveis |
| baseline | o que é normal neste contexto? | Observed Baseline |
| clustering / peer discovery | existem grupos naturais além do organograma? | experimentos shadow |
| anomaly detection | o que foge do comportamento esperado? | Expected Access |
| regras | o que fazer com os sinais encontrados? | Evidence + Policy |
| matriz SoD | quais capacidades não deveriam coexistir? | Fase 2 transacional |
| Gold | como disponibilizar a decisão? | GOLD001 |
| observabilidade | consigo confiar e reconstruir a execução? | métricas, lineage, snapshots e reconciliação |

## 5. O principal refinamento: separar sinal de decisão

<div class="sod-lane-grid">
  <div class="sod-lane"><span class="sod-kicker">Comportamento</span><h3>É comum?</h3><p>Baseline e Expected Access medem aderência a um padrão observado.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Autorização</span><h3>É justificável?</h3><p>Evidence organiza fatos como approval, birthright, certificação e contexto.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Decisão</span><h3>Como classificar?</h3><p>Policy aplica regras explícitas; Risk define prioridade depois da classificação.</p></div>
</div>

> **frequente ≠ autorizado e raro ≠ indevido.**

## 6. O que a implementação acrescentou

A V2 não “inventou” as preocupações originais; ela resolveu ambiguidades que aparecem quando a ideia vira software:

- formalizou contexto organizacional e temporal;
- criou âncoras explícitas de alta confiança;
- transformou a baseline em contrato versionado;
- tratou grupos pequenos com fallback hierárquico;
- separou expectedness de autorização;
- registrou confiabilidade e contradições de evidência;
- separou Policy de Risk;
- isolou validação do runtime;
- colocou experimentos de ML/Graph em shadow mode;
- transformou observabilidade em mecanismo operacional.

## 7. Da arquitetura inicial à V2

<div class="sod-evolution">
  <div class="sod-evolution-col">
    <span class="sod-kicker">Arquitetura inicial</span>
    <h3>Capacidades agrupadas</h3>
    <p>Bronze → Silver → baseline / grupos / clustering / anomalias / regras → Gold</p>
  </div>
  <div class="sod-evolution-arrow">→</div>
  <div class="sod-evolution-col sod-evolution-col--highlight">
    <span class="sod-kicker">Arquitetura V2</span>
    <h3>Responsabilidades explícitas</h3>
    <p>Context → HTS → Baseline/Fallback → Expected Access → Evidence → Policy → Risk → Gold</p>
  </div>
</div>

A ideia central foi preservada. O que mudou foi o nível de formalização, testabilidade e auditabilidade.

## 8. Por que ML e grafos ficaram em shadow mode na Fase 1

Clustering, LDA, NMF-HDBSCAN, FP-Growth e grafos foram mantidos como experimentos porque a Fase 1 precisa privilegiar explicabilidade, previsibilidade, rastreabilidade e testabilidade.

Isso não reduz o valor dessas técnicas. Elas se tornam ainda mais relevantes na Fase 2, quando a plataforma passa a analisar padrões funcionais e transacionais mais complexos.

## 9. Por que a matriz SoD completa fica na Fase 2

<div class="sod-mini-flow sod-mini-flow--5">
  <div><strong>1</strong><span>entitlement</span></div>
  <div><strong>2</strong><span>função</span></div>
  <div><strong>3</strong><span>transação</span></div>
  <div><strong>4</strong><span>ação</span></div>
  <div><strong>5</strong><span>objeto / escopo</span></div>
</div>

> **Fase 1:** limpar, contextualizar e governar os acessos.  
> **Fase 2:** usar essa fundação para avaliar acumulações transacionais conflitantes.

## 10. Leitura correta da evolução

> **A arquitetura inicial já identificava baseline, análise por grupos, descoberta de padrões, anomalias, regras, SoD, publicação e observabilidade. A implementação V2 transformou essas capacidades em componentes independentes, seguros e auditáveis.**
