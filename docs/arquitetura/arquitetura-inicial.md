# Arquitetura inicial

## 1. O primeiro desenho

A primeira arquitetura não nasceu com todos os componentes que hoje existem na V2. Ela nasceu de uma pergunta mais simples:

> Como transformar um inventário de acessos em uma análise escalável que encontre padrões, desvios e possíveis violações?

O desenho inicial pode ser resumido assim:

~~~text
Fontes
  ↓
Bronze
  ↓
Silver
  ↓
Camada analítica
  ├── análise por grupos
  ├── descoberta de agrupamentos naturais
  ├── identificação de desvios
  └── hipótese de regras / matriz SoD
  ↓
Gold
  ↓
Observabilidade e visualização
~~~

Naquele estágio, clustering, agrupamentos por comunidade, detecção de anomalias e regras SoD eram **hipóteses de solução**, não componentes já formalizados.

## 2. O que estava correto nessa arquitetura

Mesmo antes dos nomes atuais, quatro ideias importantes já estavam presentes.

### Separar ingestão de análise

Bronze e Silver impedem que lógica analítica fique acoplada à forma original de cada fonte.

### Procurar comportamento coletivo

A ideia de descobrir agrupamentos e padrões surgia da necessidade de reduzir entrevistas e inferir comportamento esperado em escala.

### Detectar desvios

A POC precisava identificar acessos que não combinavam com o contexto dos pares.

### Publicar uma saída consumível

Gold e observabilidade já apareciam como necessidades de entrega, e não como parte da inteligência em si.

## 3. O que ainda faltava

Ao transformar a ideia em um pipeline executável, surgiram perguntas que a arquitetura inicial não respondia bem:

- O que significa um grant sem contexto organizacional?
- Frequência alta significa autorização?
- Como lidar com uma comunidade pequena?
- Como impedir que acessos indevidos contaminem o padrão observado?
- Como tratar birthright de forma diferente de frequência?
- Como provar que uma aprovação corresponde ao grant?
- Como distinguir ausência de uso de ausência de telemetria?
- Quem classifica: o modelo estatístico ou uma política explícita?
- Como separar a classe do acesso da prioridade operacional?
- Como validar sem deixar o gabarito influenciar a decisão?

Essas perguntas levaram à especialização dos componentes.

## 4. O que aconteceu com as hipóteses analíticas

Clustering, LDA, NMF-HDBSCAN, FP-Growth e grafos não foram descartados. Eles foram deslocados para um espaço experimental, em **shadow mode**, porque ainda não eram necessários para controlar a decisão operacional da Fase 1.

Já a “detecção de anomalias” deixou de ser um engine isolado. Na V2, o conceito foi refinado para uma pergunta mais controlável:

> O acesso é esperado ou inesperado em uma população comparável?

Essa resposta é dada por Expected Access usando prevalência e fallback, sem transformar “anomalia” diretamente em irregularidade.

A matriz SoD, por sua vez, foi corretamente movida para a **Fase 2**, onde haverá semântica de funções e transações.

## 5. Como contar essa evolução

A narrativa correta não é:

> “Todos os componentes V2 já existiam desde o primeiro desenho.”

A narrativa correta é:

> **As necessidades de contextualização e de estabelecer comportamento esperado já estavam presentes nas hipóteses iniciais. Durante o refinamento, essas responsabilidades foram formalizadas em componentes independentes, testáveis e auditáveis.**

Essa evolução é um resultado de engenharia: a arquitetura ficou mais específica à medida que perguntas de domínio, dados e risco foram sendo respondidas.
