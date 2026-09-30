# Validação e testes

## 1. A ideia central: primeiro decidir, depois conferir

A validação V2 roda separada do caminho que produz a decisão.

!!! tip "Em linguagem simples"
    Pense em uma prova: **a solução responde primeiro e o gabarito só é aberto depois**.

    **Runtime** é a parte que produz a decisão. **Ground truth (gabarito)** é a resposta esperada usada para conferir o resultado. **Leakage** seria deixar o gabarito influenciar a resposta antes da avaliação.

A sequência é:

```text
runtime
  ↓
Gold congelada
  ↓
registro do run
  ↓
Validation DAG
  ↓
gabarito
  ↓
Validation Mart
```

No run validado, a auditoria encontrou **zero campos de gabarito** em Expected Access, Evidence, Policy, Risk e Gold.

## 2. Dataset sintético como ambiente controlado

O case não fornece uma base real. A POC criou um universo sintético com seed fixa e cenários conhecidos para testar:

- acessos normais;
- birthright;
- siglas públicas;
- exceções aprovadas;
- cross-community legítimo;
- cross-community sem aprovação;
- acesso herdado;
- terceiros;
- comunidades pequenas;
- tecnologia com acesso a negócio.

O objetivo é testar método, regras, rastreabilidade e comportamento. **Não é estimar a performance em produção.**

## 3. Ground truth é contrato de teste

O gabarito descreve a resposta esperada para os casos rotulados.

Exemplo:

```text
cross_legitimo
→ resposta esperada: LEGÍTIMO
→ deve existir autorização anterior à concessão

cross_sem_aprovacao
→ resposta esperada: INDEVIDO
→ premissa: fonte de requests completa para o universo da POC
```

O runtime é proibido de usar campos como:

```text
scenario
cenario
classificacao_esperada
ground_truth
expected_class
offline_label
```

Isso protege a independência da avaliação.

## 4. Run de validação registrado

A documentação usa como referência o run completo executado em **30/09/2026**:

| Item | Valor |
|---|---|
| Run ID | `manual__2026-09-30T16:28:00` |
| Git SHA | `205bde89b06633d49403fea953d627bf0281aee8` |
| runtime grants | **75.577** |
| grants com gabarito | **75.485** |
| grants sem gabarito | **92** |
| Gold snapshot | `3052553428006043189` |

O snapshot bruto das métricas fica versionado em `artifacts/validation/v2-validation-mart-metrics.json`.

## 5. Métricas executivas observadas

| Métrica | Valor | Pergunta respondida |
|---|---:|---|
| accuracy exata | **94,64%** | quantos casos receberam exatamente a classe do gabarito? |
| accuracy das decisões automatizadas | **95,86%** | quando a solução decidiu automaticamente, quantas decisões estavam corretas? |
| automation rate | **98,73%** | quantos casos receberam PADRÃO, LEGÍTIMO ou INDEVIDO? |
| review rate | **1,27%** | quantos foram preservados para revisão humana? |
| critical false-safe | **0** | quantos indevidos foram tratados como PADRÃO/LEGÍTIMO? |
| false-indevido | **0** | quantos acessos válidos foram tratados como INDEVIDO? |

Accuracy sozinha não basta. Em um problema de segurança, é essencial saber **que tipo de erro ocorreu**.

## 6. Matriz de confusão

| Gabarito | PADRÃO | LEGÍTIMO | INDEVIDO | REVISÃO | Total |
|---|---:|---:|---:|---:|---:|
| PADRÃO | **68.531** | 0 | 0 | 889 | **69.420** |
| LEGÍTIMO | 3.084 | **2.639** | 0 | 70 | **5.793** |
| INDEVIDO | 0 | 0 | **272** | 0 | **272** |

A principal confusão ocorre entre **LEGÍTIMO e PADRÃO**, e não entre LEGÍTIMO e INDEVIDO.

## 7. Métricas por classe

| Classe | Precision | Recall | F1 |
|---|---:|---:|---:|
| PADRÃO | **95,69%** | **98,72%** | **97,18%** |
| LEGÍTIMO | **100%** | **45,55%** | **62,59%** |
| INDEVIDO | **100%** | **100%** | **100%** |

**Precision** responde: entre os casos classificados nessa classe, quantos realmente pertenciam a ela?

**Recall** responde: entre todos os casos que realmente pertenciam à classe, quantos foram encontrados?

O recall de LEGÍTIMO é o principal ponto de calibração do run: 3.084 casos legítimos foram classificados como PADRÃO e 70 foram enviados para REVISÃO; **zero foram classificados como INDEVIDO**.

## 8. Métricas adicionais

O run também registrou:

- `cross_legitimo_authorization_coverage = 100%`;
- `indevido_critical_risk_rate = 100%`;
- `normal_identifiability_90 = 99,97%`;
- `critical_false_safe_count = 0`;
- `false_indevido_count = 0`.

Essas métricas foram desenhadas para verificar propriedades específicas do cenário sintético. Elas não substituem validação sobre dados reais.

## 9. Testes pós-run

Depois da execução completa:

```text
pytest tests/access_intelligence tests/gold tests/observability -q
75 passed
```

Foi observado apenas um `FutureWarning` de scikit-learn, sem falha de teste.

A documentação também foi validada com:

```text
mkdocs build --strict
passou
```

O aviso informativo do Material for MkDocs sobre MkDocs 2.0 não impediu o build.

## 10. O que seria necessário antes de produção

Uma promoção segura exigiria:

1. profiling das fontes reais;
2. shadow run com dados reais;
3. amostra revisada por especialistas;
4. comparação com achados confirmados;
5. calibração de thresholds e pesos;
6. aprovação formal das regras;
7. rollout gradual;
8. monitoramento de drift, qualidade e revisão humana.

A POC agora possui **evidência de execução completa no cenário sintético**. Produção exige evidência equivalente sobre o ambiente real.

---

Para fórmulas, thresholds, pesos e definição das variáveis, consulte **[Como os cálculos funcionam](calculos.md)**.
