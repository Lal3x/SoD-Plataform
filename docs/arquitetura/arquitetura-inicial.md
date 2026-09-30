# Arquitetura inicial e hipóteses de solução

## 1. O desenho inicial já partia de uma decomposição do problema

A arquitetura inicial não foi um desenho “incompleto” que depois precisou ser substituído.

Ela já partia de uma hipótese arquitetural importante:

> **separar preparação dos dados, entendimento do comportamento de acesso, identificação de desvios, regras de decisão, publicação e observabilidade.**

O primeiro desenho organizava essas responsabilidades em blocos mais amplos:

~~~text
FONTES DE DADOS
      │
      ▼
INGESTÃO
      │
      ▼
BRONZE
dados recebidos e rastreáveis
      │
      ▼
SILVER
padronização + qualidade
      │
      ▼
CAMADA ANALÍTICA / CLASSIFICAÇÃO
      │
      ├─ análise por grupos
      ├─ descoberta de agrupamentos naturais de acesso
      ├─ identificação de comportamento esperado
      ├─ identificação de desvios/anomalias
      └─ regras / hipótese de matriz SoD
      │
      ▼
GOLD
resultado consumível
      │
      ▼
VISUALIZAÇÃO + OBSERVABILIDADE
~~~

Esse desenho já continha as principais preocupações que orientaram a implementação posterior.

A V2 não abandona essa arquitetura. Ela **especializa os blocos que inicialmente estavam agrupados**.

## 2. O que já estava pensado desde o início

### Engenharia de dados antes da classificação

Bronze e Silver já apareciam para separar ingestão, padronização e qualidade da análise de acesso.

Isso evitava construir uma solução em que regra de negócio estivesse acoplada diretamente aos arquivos de origem.

### Análise em escala por grupos

A ideia de analisar pessoas em grupos semelhantes já existia porque entrevistar comunidade por comunidade não escalaria.

O objetivo era descobrir:

- quais acessos formam o núcleo de um grupo;
- quais combinações aparecem naturalmente;
- quais acessos destoam desse comportamento.

Esse raciocínio é a origem do que posteriormente foi formalizado como **Observed Baseline, grupos comparáveis e Expected Access**.

### Descoberta de agrupamentos naturais

A arquitetura inicial já considerava clustering e análise de similaridade para descobrir agrupamentos de acesso que não dependessem exclusivamente da estrutura organizacional declarada.

Isso levou aos experimentos posteriores com Peer Discovery.

Esses experimentos permaneceram em shadow mode porque a V2 priorizou explicabilidade no caminho de decisão, não porque a hipótese inicial estivesse errada.

### Identificação de desvios

A detecção de anomalias também estava presente desde o desenho inicial.

Durante a implementação, a pergunta foi refinada.

Em vez de manter um bloco genérico chamado “Anomaly Detection”, a V2 passou a responder de forma mais específica:

> “Este acesso é esperado ou inesperado quando comparado com uma população defensável?”

Essa responsabilidade passou para Expected Access.

### Regras e horizonte SoD

A hipótese de regras/matriz SoD também já estava no desenho inicial.

O refinamento posterior mostrou que havia dois problemas diferentes:

1. sanitizar os acessos atuais por comunidade;
2. detectar combinações transacionais conflitantes.

Por isso a Policy da Fase 1 foi implementada agora, enquanto a matriz SoD transacional foi posicionada como evolução da Fase 2.

### Gold e visualização

Desde o começo havia a preocupação de publicar um resultado consumível, e não apenas produzir um notebook ou relatório analítico isolado.

Essa ideia evoluiu para a Gold versionada consumida pelo Streamlit.

### Observabilidade

Observabilidade já fazia parte da arquitetura como necessidade transversal.

Na V2 ela foi aprofundada em mecanismos concretos:

- métricas de ingestão;
- qualidade e quarentena;
- journal de componentes;
- snapshots;
- lineage;
- versões;
- reconciliação;
- saúde da decisão.

Portanto, observabilidade não surgiu depois como acabamento operacional. A implementação materializou uma preocupação que já estava presente no desenho.

## 3. O que mudou da arquitetura inicial para a V2

O principal refinamento foi perceber que **“Classificação” era um bloco amplo demais**.

Dentro dele existiam perguntas diferentes:

~~~text
Qual é o contexto do acesso?
        ↓
Access Context

Existe alguma referência explícita confiável?
        ↓
Hard Trusted Set

O que pessoas comparáveis normalmente possuem?
        ↓
Observed Baseline

E se o grupo for pequeno?
        ↓
Hierarchical Fallback

Este acesso parece esperado?
        ↓
Expected Access

Quais fatos sustentam a análise?
        ↓
Evidence

O que as regras dizem sobre esses fatos?
        ↓
Policy

Qual caso deve ser tratado primeiro?
        ↓
Risk
~~~

A arquitetura inicial já percebia a necessidade de **entender padrão, encontrar desvio e aplicar regras**.

A V2 transformou essas intenções em contratos independentes e testáveis.

## 4. A evolução não foi “pensar depois”; foi reduzir ambiguidade

Um exemplo importante é comportamento esperado.

No desenho inicial:

~~~text
analisar grupos
      ↓
identificar padrões
      ↓
detectar anomalias
~~~

Durante a implementação apareceu uma questão crítica:

> “Se um acesso é comum, isso significa que ele é autorizado?”

A resposta é não.

Por isso o conceito inicial foi decomposto:

~~~text
comportamento observado
        ↓
Expected Access
        ↓
é apenas evidência

autorização
        ↓
Policy
        ↓
decisão
~~~

Esse refinamento não invalida a hipótese inicial. Ele a torna mais segura.

## 5. Outro refinamento: grupos pequenos

A arquitetura inicial já previa análise por grupos e agrupamentos naturais.

Quando isso foi transformado em código, apareceu um problema estatístico concreto:

> “O que fazer quando o grupo de comparação possui poucas pessoas?”

A resposta virou um componente explícito:

~~~text
grupo mais específico
       ↓ insuficiente
grupo um pouco mais amplo
       ↓ insuficiente
grupo mais amplo
       ↓
Hierarchical Fallback
~~~

Ou seja, a necessidade já existia na estratégia de comparação por pares; a V2 formalizou o tratamento do edge case.

## 6. Outro refinamento: contexto organizacional e temporal

A arquitetura inicial buscava desvios por comunidade e grupos de acesso.

Para fazer isso de maneira confiável, a implementação precisou formalizar informações que estavam implícitas na própria ideia de contexto:

- comunidade da pessoa;
- comunidade dona da sigla;
- tipo de identidade;
- cargo;
- squad;
- data de concessão;
- data de entrada na comunidade;
- acesso público;
- aprovação;
- certificação.

Esses elementos foram consolidados em **Access Context**.

A necessidade de contexto não surgiu na V2; a V2 deu a ela um contrato próprio.

## 7. Do desenho inicial à arquitetura implementada

A evolução pode ser resumida assim:

~~~text
ARQUITETURA INICIAL

Dados
  ↓
Bronze
  ↓
Silver
  ↓
Classificação / Analytics
  ├─ grupos
  ├─ clustering
  ├─ padrões
  ├─ anomalias
  └─ regras / SoD
  ↓
Gold
  ↓
Observabilidade


             REFINAMENTO


ARQUITETURA V2

Bronze
  ↓
Silver
  ↓
Access Context
  ↓
HTS + Observed Baseline
  ↓
Hierarchical Fallback
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

Airflow + Observabilidade atravessando o pipeline
~~~

A ideia central foi preservada.

O que mudou foi o grau de formalização.

## 8. O que ficou experimental e por quê

Clustering, LDA, NMF-HDBSCAN, FP-Growth e grafos continuaram sendo explorados.

Eles não entraram no caminho crítico da decisão porque a Fase 1 exigia alto grau de:

- explicabilidade;
- previsibilidade;
- rastreabilidade;
- testabilidade.

Por isso foram mantidos em **modo experimental (shadow mode)**.

Isso permite comparar valor sem tornar a decisão dependente de um método ainda não validado operacionalmente.

## 9. O que foi deslocado para a Fase 2

A matriz SoD completa precisa de semântica que não existe apenas no inventário de acessos:

~~~text
entitlement
   ↓
função
   ↓
transação
   ↓
ação
   ↓
objeto / escopo
~~~

Por isso a intenção inicial de chegar à SoD não foi abandonada.

Ela foi dividida em uma sequência mais racional:

~~~text
Fase 1
sanitizar e contextualizar os acessos
        ↓
construir evidências e governança
        ↓
Fase 2
avaliar acumulações transacionais conflitantes
~~~

## 10. Leitura correta da evolução

A interpretação que esta documentação pretende transmitir é:

> **A arquitetura inicial já identificava as capacidades essenciais: preparação de dados, análise por grupos, descoberta de padrões, identificação de desvios, aplicação de regras, publicação e observabilidade. A implementação V2 refinou essas capacidades em componentes independentes à medida que questões de contexto, temporalidade, confiabilidade e explicabilidade foram formalizadas.**

Isso mostra evolução arquitetural sem reescrever a história do projeto.
