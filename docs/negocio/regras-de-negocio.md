# Regras de negócio

## 1. Regra, hipótese e implementação não são a mesma coisa

O case fornece **semântica de domínio**, mas não entrega uma política institucional completa. Por isso esta documentação separa quatro níveis:

| Nível | Pergunta |
|---|---|
| Regra do case | O que o desafio declara explicitamente? |
| Hipótese da POC | O que precisamos assumir para tornar o problema executável? |
| Regra runtime | Como a hipótese foi materializada tecnicamente? |
| Produção | O que precisaria de owner e aprovação institucional? |

Essa separação evita apresentar uma escolha técnica como se fosse norma do banco.

## 2. Catálogo resumido

| ID conceitual | Origem | Condição resumida | Saída | Runtime V2 |
|---|---|---|---|---|
| BR-001 | Case | sigla pública | LEGÍTIMO | R080 |
| BR-002 | Case | cross com autorização válida | LEGÍTIMO | R020 |
| BR-003 | POC | cross non-public, aprovação necessária ausente e fonte autoritativa | INDEVIDO | R030 |
| BR-004 | POC | birthright explícito sem contradição | PADRÃO | R050 |
| BR-005 | POC | padrão observado com evidência HIGH | PADRÃO | R060 |
| BR-006 | Engenharia | qualidade bloqueante | REVISÃO | R010 |
| BR-007 | Engenharia | aprovação conflitante com REVOKE | REVISÃO | R025 |
| BR-008 | Engenharia | inesperado/insuficiente sem violação explícita | REVISÃO | R110/R120 |
| BR-009 | Engenharia | cobertura de autorização insuficiente | REVISÃO | R130 |

A tabela é apenas o mapa. A decisão real respeita **precedência**.

## 3. Sigla pública

O case estabelece que uma sigla pública é legítima para qualquer pessoa e não deve ser tratada como risco apenas por atravessar comunidade.

Exemplo:

~~~text
Pessoa: comunidade Crédito
Sigla: PORTAL_CORPORATIVO
Owner: Serviços Compartilhados
sigla_publica = true
~~~

Mesmo que a comunidade da pessoa seja diferente da dona da sigla, a fronteira é pública. Portanto, esse fato não sustenta uma violação.

Na V2, a regra correspondente é R080 → LEGÍTIMO, desde que nenhuma regra de maior precedência tenha sido acionada.

## 4. Cross-community aprovado

Considere:

~~~text
Identidade: I-1023
Comunidade: Crédito
Entitlement: ENT-COB-LEITURA
Sigla: COB
Dona da sigla: Cobrança
~~~

Temos uma relação cross-community. Isso ainda não determina irregularidade.

Se existe uma request aprovada antes da concessão e o vínculo é suficientemente forte:

~~~text
approval_evidence_status = UNIQUE_MATCH
approval_linkage_quality = STRONG_INFERRED
~~~

a Policy pode aplicar:

~~~text
R020 → LEGÍTIMO
~~~

### Por que STRONG_INFERRED e não DIRECT?

A fonte sintética não possui uma chave transacional request → grant. A associação é inferida por identidade, entitlement e coerência temporal.

Essa diferença importa. Um vínculo inferido forte é melhor do que ausência de evidência, mas é mais fraco do que uma FK explícita. Em uma implementação produtiva, uma referência transacional direta seria preferível.

## 5. Cross sem aprovação

Este é o caso mais sensível:

~~~text
cross non-public
+
approval_evidence_status = NOT_FOUND
~~~

Ausência de request só sustenta INDEVIDO se soubermos que a fonte observada cobre aquele universo de concessões.

A V2 declara explicitamente:

~~~text
request_source_coverage = AUTHORITATIVE_FOR_V2
~~~

Com essa premissa:

~~~text
R030 → INDEVIDO
~~~

Sem essa premissa:

~~~text
R130 → REVISÃO
~~~

!!! warning "Decisão de POC"
    Em produção, a completude da fonte de requests teria de ser demonstrada por contrato, lineage, reconciliação e ownership. Se existirem canais de concessão fora da fonte observada, NOT_FOUND não pode ser interpretado como ausência de autorização.

## 6. Birthright como âncora explícita

Birthright é tratado como evidência explícita, não como frequência.

Ele entra no Hard Trusted Set quando não existe contradição relevante:

~~~text
birthright = true
AND data_quality_blocking = false
AND certification != REVOKE
AND (
    same-community
    OR sigla_publica = true
)
~~~

Se a âncora permanece válida, a Policy pode aplicar R050 → PADRÃO.

Essa decisão não depende de quantas outras pessoas possuem o entitlement.

## 7. Padrão observado

Para grants sem âncora explícita, Expected Access pode identificar um padrão comportamental.

Exemplo:

~~~text
20 identidades comparáveis
18 possuem o entitlement

population_size = 20
support_count = 18
prevalence = 18 / 20 = 0.90
~~~

Com threshold de expectedness em 0.80, o acesso pode ser classificado como EXPECTED.

Mas a Policy não transforma qualquer EXPECTED em PADRÃO. R060 exige evidência HIGH, baseline selecionado e contexto same-community ou público.

Logo:

~~~text
EXPECTED
   ≠
PADRÃO automático
~~~

Esse é um dos princípios centrais da solução: comportamento observado é **evidência**, não autorização.

## 8. Acesso herdado

A implementação compara a data de concessão com a entrada na comunidade atual.

~~~text
data_concessao < data_entrada_comunidade_atual
        ↓
inherited_access_candidate = true
~~~

Isso não significa INDEVIDO.

Como o histórico organizacional completo não está garantido, a conclusão correta é: “há um sinal temporal que merece análise”.

## 9. Sem uso registrado

Quando ultimo_uso é nulo:

~~~text
no_usage_recorded = true
usage_coverage = UNKNOWN
~~~

A expressão correta é **sem uso registrado na fonte**. Sem conhecer cobertura e retenção da telemetria, afirmar “nunca utilizado” seria mais forte do que os dados permitem.

## 10. Contractor fora de escopo

O atributo contractor é observável.

Já “fora de escopo” depende de um dado adicional: contrato, assignment, frente ou relação autorizada. Como o case não fornece essa taxonomia, a POC não inventa uma política.

## 11. Tecnologia × perfil de negócio

O case apresenta esse cenário, mas não fornece uma taxonomia completa de funções de negócio.

A arquitetura futura trata esse gap com um catálogo de funções, transações e ações. Até lá, o runtime evita fingir que conhece uma semântica que os dados não fornecem.

## 12. Precedência é parte da segurança

Considere um acesso cross com aprovação forte, mas cuja certificação mais recente indica REVOKE.

Se verificássemos apenas “tem aprovação?”, chegaríamos a LEGÍTIMO.

A V2 evita isso:

~~~text
R025 — aprovação + certificação REVOKE
        ↓
      REVISÃO

vem antes de:

R020 — cross aprovado
        ↓
      LEGÍTIMO
~~~

A ordem das regras é, portanto, parte da política.

## 13. Quatro classes operacionais

| Decisão | Interpretação |
|---|---|
| PADRÃO | coerente com âncora explícita ou padrão funcional confiável |
| LEGÍTIMO | exceção válida e explicável |
| INDEVIDO | violação sustentada por regra e cobertura suficiente |
| REVISÃO | incerteza, conflito ou cobertura insuficiente |

REVISÃO existe para impedir que falta de informação seja convertida em certeza artificial.
