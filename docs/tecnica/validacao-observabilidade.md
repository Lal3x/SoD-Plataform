# Validação e testes

## 1. Validação mede a solução; não controla a solução

A validação V2 roda em DAG separado.

!!! tip "Em linguagem simples"
    **Runtime** é a parte que produz a decisão. **Ground truth (gabarito)** é a resposta esperada usada depois para conferir o resultado. **Leakage** seria deixar esse gabarito influenciar a decisão antes da avaliação. O desenho separa essas etapas justamente para evitar isso.

    O **Validation Mart** é o conjunto de tabelas de avaliação produzido depois da execução, com matriz de confusão e métricas de qualidade.

A sequência correta é:

~~~text
runtime
  ↓
Gold congelada
  ↓
registro do run
  ↓
validation DAG
  ↓
ground truth
  ↓
Validation Mart
~~~

Isso é uma escolha arquitetural para evitar leakage.

## 2. Dataset sintético como ambiente controlado

O case não fornece uma base de dados.

A POC criou um universo sintético com seed fixa e cenários conhecidos.

Os relatórios versionados descrevem uma ordem de grandeza de:

- cerca de 9,9 mil identidades;
- cerca de 75,5 mil grants;
- 1,9 mil entitlements;
- 2,6 mil requests;
- 18,8 mil certificações.

Os cenários incluem:

- birthright;
- normal;
- sigla pública;
- acesso opcional aprovado;
- cross legítimo;
- cross sem aprovação;
- acesso herdado;
- contractor fora de escopo;
- comunidade pequena;
- tecnologia com acesso a negócio.

O objetivo desses dados não é provar performance produtiva. É garantir que o pipeline seja testado contra situações conhecidas.

## 3. Ground truth é contrato de teste

O ground truth V2 possui semântica explícita.

Exemplo:

~~~text
cross_legitimo
  expected_class = LEGITIMO
  evidência necessária = request aprovada antes da concessão

cross_sem_aprovacao
  expected_class = INDEVIDO
  premissa = fonte de requests completa/autoritativa
~~~

Isso permite saber exatamente o que está sendo validado.

## 4. O que o runtime é proibido de ler

Scripts runtime verificam ausência de colunas como:

- scenario;
- cenario;
- classificacao_esperada;
- ground_truth;
- expected_class;
- offline_label.

Esse controle aparece em Expected Access, Policy, Risk e Gold.

A ideia é simples:

> o gabarito não pode ensinar a resposta para o pipeline que será avaliado.

## 5. O que a validação calcula

O código de validação gera um arquivo por execução em `artifacts/validation/v2-validation-mart-metrics.json` e também materializa tabelas consumidas pelo dashboard.

!!! note "Importante para interpretar a documentação"
    O **método de cálculo está versionado no repositório**, mas o snapshot final desse arquivo de métricas **não está versionado na `main`**. Por isso a documentação não publica uma accuracy fixa sem associá-la a uma execução concreta.

O Validation Mart produz:

### Matriz de confusão

Ground truth × decisão de Policy.

### Métricas por classe

- precision;
- recall;
- F1;
- support.

### Métricas por cenário

- total;
- PADRÃO;
- LEGÍTIMO;
- INDEVIDO;
- REVISÃO;
- accuracy;
- automation rate;
- review rate.

### Métricas executivas

- grants runtime;
- grants rotulados;
- grants sem rótulo;
- accuracy exata;
- accuracy das decisões automatizadas;
- taxa de automação;
- taxa de revisão;
- false-safe crítico;
- false-indevido;
- cobertura de autorização cross legítimo.

## 6. Por que accuracy sozinha seria insuficiente

Imagine uma base dominada por casos normais.

Um classificador que marque quase tudo como PADRÃO poderia obter accuracy alta e ainda falhar justamente nos casos mais importantes.

Por isso a validação olha classe, cenário e tipo de erro.

Em segurança, dois erros merecem atenção especial:

**False-safe crítico:** ground truth INDEVIDO classificado como PADRÃO/LEGÍTIMO.

**False-indevido:** ground truth PADRÃO/LEGÍTIMO classificado como INDEVIDO.

Eles representam riscos diferentes.

## 7. Testes automatizados

O projeto separa:

- unit;
- integration;
- e2e.

Existem testes específicos de:

- Bronze;
- Silver;
- Access Intelligence;
- Gold;
- Observability;
- Streamlit.

Os testes de observabilidade, por exemplo, verificam se componentes registram métricas usando o mesmo run_id da Silver e se o funil do fallback é persistido.

## 8. CI

A pipeline de CI executa testes e build das imagens de Streamlit e Airflow.

A documentação também passa a ser validada com build estrito do MkDocs.

Isso reduz o risco de publicar navegação quebrada ou referência inválida.

## 9. O que seria necessário antes de produção

Uma sequência segura seria:

1. profiling de fontes reais;
2. shadow run;
3. amostra revisada por especialistas;
4. comparação com RC/achados confirmados;
5. calibração de thresholds;
6. aprovação formal das regras;
7. rollout gradual;
8. monitoramento de drift e distribuição;
9. revisão periódica da política.

A POC demonstra método. Produção exige evidência operacional.


---

Para fórmulas, thresholds, pesos e definição das variáveis, consulte **[Como os cálculos funcionam](calculos.md)**.
