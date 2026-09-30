# Hipóteses de domínio e dados sintéticos

## 1. O case não fornece uma base de dados

O case descreve a **natureza das informações que existiriam em produção**, mas não entrega um dataset para exploração.

Isso altera a narrativa correta do projeto.

Não partimos de “padrões encontrados nos dados do case”. Partimos de:

~~~text
descrição do problema
        ↓
hipóteses de domínio
        ↓
modelo de dados necessário
        ↓
dataset sintético
        ↓
implementação e experimentação
        ↓
validação offline
~~~

Essa distinção evita atribuir ao case evidências empíricas que ele não forneceu.

## 2. Dados assumidos

A POC modela fontes equivalentes a:

- identidade e atributos organizacionais;
- diretório de contas;
- catálogo de entitlements;
- grants de acesso;
- solicitações e aprovações;
- certificações;
- catálogo de aplicações e siglas.

Os nomes são vendor-agnostic. O objetivo é demonstrar a lógica de engenharia, não depender de uma ferramenta específica de IAM ou IGA.

## 3. Por que gerar dados sintéticos

Os dados sintéticos cumprem quatro funções:

1. permitir desenvolver o pipeline completo sem dados sensíveis;
2. materializar os cenários descritos no case;
3. criar casos de controle conhecidos para testes;
4. fornecer um gabarito apenas para validação offline.

O dataset sintético não transforma a POC em uma prova de desempenho produtivo. Ele é um ambiente controlado para demonstrar método, arquitetura e isolamento entre runtime e validação.

## 4. Hipóteses principais

### H1 — O grant precisa de contexto

Um par identidade-entitlement isolado é insuficiente. A decisão pode depender de comunidade, squad, cargo, tipo de identidade, dono da sigla, caráter público, criticidade, data de concessão e evidências de autorização.

**Consequência:** criação do Access Context.

### H2 — Acesso esperado pode ser estimado por populações comparáveis

Sem entrevistar cada área, a prevalência de entitlements em grupos organizacionais pode servir como sinal de comportamento esperado.

**Consequência:** Observed Baseline.

### H3 — Nem todo grupo é grande o suficiente

Grupos muito específicos podem ter baixa população ou baixo suporte.

**Consequência:** Hierarchical Fallback.

### H4 — Âncoras explícitas devem ser separadas de inferência estatística

Birthright representa uma evidência mais forte do que simples frequência.

**Consequência:** Hard Trusted Set.

### H5 — Expectedness e autorização precisam ser separadas

Um acesso pode ser raro e aprovado; também pode ser frequente e incompatível com política.

**Consequência:** Expected Access não produz decisão final. Evidence e Policy vêm depois.

### H6 — Decisão e urgência são problemas diferentes

Um acesso INDEVIDO privilegiado em aplicação crítica não deve competir na mesma fila com um caso de baixo impacto.

**Consequência:** Risk é posterior à Policy.

### H7 — O gabarito não pode influenciar as regras

Usar o label sintético para escolher thresholds, regras ou features criaria data leakage.

**Consequência:** Validation Mart separado do runtime e executado depois dos outputs congelados.

## 5. Ground truth: onde ele pode aparecer

~~~text
RUNTIME
Sources → Bronze → Silver → Intelligence → Policy → Risk → Gold
                                                    │
                                                    ▼
                                             outputs congelados
                                                    │
                                                    ▼
VALIDAÇÃO OFFLINE                              Ground truth
                                                    │
                                                    ▼
                                            Validation Mart
~~~

O runtime não deve possuir colunas como scenario, classificacao_esperada ou ground_truth.

## 6. O que seria diferente com dados reais

Com dados produtivos, o primeiro trabalho seria um profiling controlado para confirmar:

- completude temporal;
- cobertura das solicitações;
- cobertura de uso;
- qualidade do vínculo request → grant;
- histórico de comunidade;
- taxonomias de aplicação e função;
- qualidade das classificações de criticidade e dados;
- distribuição de comunidades pequenas.

Essas verificações determinariam quais premissas da POC podem ser mantidas e quais precisariam ser alteradas antes da ativação de decisões automáticas.
