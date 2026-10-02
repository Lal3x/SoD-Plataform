# Arquitetura conceitual inicial

## 1. De onde a solução partiu

Esta página registra **a proposta conceitual que formulei no início do case, antes da implementação**. Ela representa a minha hipótese arquitetural inicial para decompor o problema, orientar a análise dos dados e testar caminhos de solução.

!!! info "Arquitetura conceitual, não estado implementado"
    Este desenho não representa uma primeira versão implantada da plataforma. Ele é o **modelo mental de partida**: uma arquitetura conceitual criada durante a leitura do problema para organizar as hipóteses que depois seriam validadas, refinadas e transformadas em componentes implementáveis.

O desenho inicial não partiu apenas de ferramentas de Engenharia de Dados. Ele combinava **princípios de Segurança da Informação** com uma arquitetura capaz de executá-los em escala.

> **Não é possível identificar um desvio de acesso sem antes estabelecer uma referência de comportamento esperado, entender o contexto e preservar evidências suficientes para explicar a decisão.**

```mermaid
flowchart TB
    A["Fontes<br/>identidades · acessos · contexto"] --> B["Bronze<br/>preservar o recebido"]
    B --> C["Silver<br/>qualidade · contratos · chaves"]

    C --> D["Baseline"]
    D --> E["Análise por grupos"]
    E --> F["Clustering / Peer Discovery"]
    E --> G["Detecção de desvios"]
    F --> G
    G --> H["Regras / hipótese SoD"]
    H --> I["Gold"]
    I --> J["Visualização"]

    O["Observabilidade"] -. acompanha .-> B
    O -. acompanha .-> C
    O -. acompanha .-> D
    O -. acompanha .-> I
```

A arquitetura atual não substituiu esse raciocínio. Ela **formalizou responsabilidades que, na proposta conceitual inicial, ainda estavam agrupadas**.

## 2. Segurança da Informação já orientava a solução

| Princípio | Como aparecia desde o início | Como foi formalizado depois |
|---|---|---|
| **Baseline comportamental** | estabelecer uma referência antes de procurar desvios | Observed Baseline + Fallback + Expected Access |
| **Least Privilege** | questionar acessos além do necessário | Policy + revisão de acessos |
| **Need-to-Know** | interpretar o acesso pelo contexto funcional | Access Context + comunidade + função |
| **Anomaly Detection** | localizar comportamentos fora do padrão | Expected Access, sem transformar raridade em culpa |
| **Segregation of Duties** | hipótese de matriz SoD | Fase 2 transacional |
| **Accountability** | necessidade de decisão explicável e observável | lineage + snapshots + versões + reason codes |
| **Defense in Depth** | não depender de um único sinal | DQ → contexto → baseline → Evidence → Policy → Risk |

!!! info "Leitura correta"
    **Engenharia de Dados fornece escala, contratos e rastreabilidade. Segurança da Informação fornece os princípios que determinam o que observar, comparar e proteger.**

Veja também a página dedicada **[Fundamentos de Segurança da Informação](fundamentos-seguranca.md)**.

## 3. A baseline já fazia parte da ideia inicial

Desde o início, a análise por grupos e a detecção de anomalias já pressupunham uma baseline.

```mermaid
flowchart LR
    A["Definir população comparável"] --> B["Entender comportamento normal"]
    B --> C["Identificar desvios"]
    C --> D["Investigar com contexto e regras"]
```

A implementação atual tornou essa ideia explícita em componentes separados:

```mermaid
flowchart LR
    A["Observed Baseline<br/>mede prevalência"] --> B["Hierarchical Fallback<br/>trata grupos pequenos"]
    B --> C["Expected Access<br/>EXPECTED · UNEXPECTED · INSUFFICIENT"]
```

Isso é diferente de autorização.

> **Um acesso pode ser frequente e ainda assim contrariar uma regra. Frequente ≠ autorizado. Raro ≠ indevido.**

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

Na arquitetura conceitual inicial, análise de padrão, desvio e regra ainda estavam concentradas no mesmo bloco. A arquitetura atual separa três perguntas diferentes:

| Pergunta | Responsabilidade |
|---|---|
| **É comum?** | Baseline + Expected Access |
| **É justificável?** | Evidence organiza fatos, aprovações, birthright, certificações e contexto |
| **Como classificar?** | Policy aplica regras explícitas; Risk prioriza depois |

```mermaid
flowchart LR
    A["Comportamento<br/>Baseline"] --> B["Evidência<br/>fatos + confiabilidade"]
    B --> C["Policy<br/>classificação"]
    C --> D["Risk<br/>prioridade"]
```

Essa separação evita que uma anomalia estatística seja tratada diretamente como violação.

## 6. O que a implementação acrescentou

A arquitetura atual não inventou as preocupações originais; ela resolveu ambiguidades que aparecem quando a ideia conceitual vira software:

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

## 7. Da arquitetura conceitual inicial à arquitetura atual

```mermaid
flowchart TB
    subgraph INICIAL["IDEIA CONCEITUAL INICIAL"]
        A1["Bronze"] --> A2["Silver"]
        A2 --> A3["Baseline + grupos + clustering"]
        A3 --> A4["Anomalias + regras"]
        A4 --> A5["Gold"]
    end

    subgraph ATUAL["ARQUITETURA ATUAL"]
        B1["Access Context"] --> B2["HTS + Observed Baseline"]
        B2 --> B3["Hierarchical Fallback"]
        B3 --> B4["Expected Access"]
        B4 --> B5["Evidence"]
        B5 --> B6["Policy"]
        B6 --> B7["Risk"]
        B7 --> B8["Gold"]
    end

    INICIAL -->|"validação, formalização e separação de responsabilidades"| ATUAL
```

A ideia central foi preservada. O que mudou foi o nível de formalização, testabilidade e auditabilidade.

## 8. Por que ML e grafos ficaram em shadow mode na Fase 1

Clustering, LDA, NMF-HDBSCAN, FP-Growth e grafos foram mantidos como experimentos porque a Fase 1 precisa privilegiar:

- explicabilidade;
- previsibilidade;
- rastreabilidade;
- testabilidade.

Isso não reduz o valor dessas técnicas. Elas ganham mais relevância na Fase 2, quando a plataforma passa a analisar padrões funcionais e transacionais mais complexos.

## 9. Por que a matriz SoD completa fica na Fase 2

A SoD transacional precisa de uma semântica mais profunda:

```mermaid
flowchart LR
    A["Entitlement"] --> B["Função"]
    B --> C["Transação"]
    C --> D["Ação"]
    D --> E["Objeto / Escopo"]
```

**Fase 1:** limpar, contextualizar e governar os acessos.

**Fase 2:** usar essa fundação para avaliar acumulações transacionais conflitantes.

## 10. Leitura correta da evolução

> **A arquitetura conceitual inicial já identificava baseline, análise por grupos, descoberta de padrões, anomalias, regras, SoD, publicação e observabilidade. A implementação atual transformou essas ideias em componentes independentes, testáveis, seguros e auditáveis.**
