# Regras de negócio

## 1. Como esta página deve ser interpretada

Nem toda regra desta POC tem a mesma origem. Para evitar confusão, usamos quatro categorias:

| Categoria | Significado |
|---|---|
| Regra do case | Comportamento explicitamente descrito no desafio |
| Hipótese da POC | Decisão metodológica necessária para tornar o problema executável |
| Regra runtime V2 | Lógica efetivamente implementada hoje |
| Evolução de produção | Regra ou dado que exigiria validação institucional |

Essa distinção é importante porque o case descreve o domínio, mas não fornece uma política institucional completa de autorização.

## 2. Regras explícitas do case

### Comunidade e sigla

Uma comunidade possui siglas. Por padrão, seus acessos devem ser coerentes com esse contexto, exceto quando há uma justificativa legítima para atravessar a fronteira organizacional.

**Cross-community é um sinal que exige explicação; não é sinônimo automático de indevido.**

### Sigla pública

Se a sigla é pública e disponibilizada para todo o banco, o fato de a pessoa pertencer a outra comunidade não deve gerar risco apenas por ser cross-community.

No runtime V2, essa regra aparece como classificação LEGÍTIMO quando as condições anteriores de conflito não bloqueiam a decisão.

### Acesso aprovado

Um acesso cross-community legitimamente solicitado e aprovado não deve ser classificado como indevido.

A dificuldade técnica é provar que uma solicitação encontrada realmente corresponde ao grant analisado. Por isso, Access Context e Evidence preservam a qualidade do vínculo entre solicitação e concessão.

### Comunidade pequena

Poucos integrantes tornam uma comparação estatística local frágil. A solução não transforma “grupo pequeno” em risco; ela amplia progressivamente a população de referência por Hierarchical Fallback.

## 3. Situações que são sinais, não sentenças

### Acesso herdado

Se o grant é anterior à entrada na comunidade atual, existe uma indicação temporal de acesso residual. Porém, a base atual não contém histórico organizacional completo.

Portanto:

~~~text
grant anterior à comunidade atual
        ↓
inherited_access_candidate
        ≠
INDEVIDO automático
~~~

### Sem uso registrado

O case pede que o cenário “provisionado e nunca utilizado” seja considerado. A implementação faz uma distinção mais conservadora:

- ultimo_uso nulo → no_usage_recorded;
- usage_coverage = UNKNOWN.

Sem conhecer a cobertura da telemetria, ausência de registro não prova que o acesso nunca foi utilizado.

### Contractor fora de escopo

O tipo de identidade pode ser observado. Entretanto, “escopo da frente” precisa existir como dado confiável para uma regra institucional.

Na POC, contractor compõe o contexto e pode influenciar comparações. Uma política forte de “fora do escopo” depende de uma taxonomia de escopo que não é fornecida pelo case.

### Tecnologia/engenharia × perfil de negócio

O case apresenta esse cenário como relevante, mas não fornece uma classificação formal de “perfil de negócio” aplicável a todos os entitlements.

Em produção, essa regra exigiria um catálogo governado de aplicações, funções e perfis. A arquitetura da Fase 2 contempla exatamente essa evolução sem inventar a taxonomia no runtime atual.

## 4. Padrão observado não é autorização

A POC calcula prevalência para responder:

> “Este entitlement é comum entre identidades comparáveis?”

Isso é uma pergunta analítica, não jurídica ou normativa.

Por isso:

~~~text
FREQUENTE ≠ AUTORIZADO
RARO      ≠ INDEVIDO
EXPECTED  ≠ LEGÍTIMO
UNEXPECTED ≠ INDEVIDO
~~~

A autorização é decidida posteriormente pela camada Policy, usando evidências e premissas explícitas.

## 5. Regra de aprovação na V2

A Policy PD002 usa a premissa de POC:

**request_source_coverage = AUTHORITATIVE_FOR_V2**

Com essa premissa, um cross-community que exige aprovação e não possui aprovação encontrada pode ser classificado como INDEVIDO.

Essa é uma das decisões mais importantes a validar antes de produção. Se a fonte de solicitações não for completa e autoritativa, ausência de aprovação deve voltar para REVISÃO em vez de INDEVIDO.

## 6. Decisões produzidas

| Decisão | Semântica operacional |
|---|---|
| PADRÃO | Coerente com âncora explícita ou padrão funcional observado sob as condições da política |
| LEGÍTIMO | Exceção permitida, como cross aprovado ou sigla pública |
| INDEVIDO | Violação sustentada por uma regra explícita e premissas suficientes |
| REVISÃO | Evidência insuficiente, ambígua, contraditória ou não coberta |

A POC não elimina revisão humana. Ela tenta concentrá-la nos casos em que a incerteza realmente existe.
