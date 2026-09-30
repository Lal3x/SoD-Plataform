# Premissas, controles e evolução para produção

Esta página registra **condições de validade da POC** e como cada uma é tratada pela arquitetura.

O objetivo não é listar fraquezas. É deixar claro o que já está controlado, o que depende de dados corporativos reais e quais validações seriam necessárias antes de produção.

## Visão rápida

| Tema | Controle na POC | Evolução para produção |
|---|---|---|
| dados sintéticos | cenários conhecidos + ground truth isolado | profiling e amostras reais |
| requests | cobertura declarada no contrato V2 | medir completude por canal |
| request → acesso | qualidade do vínculo explícita | chave transacional quando disponível |
| histórico organizacional | incerteza preservada | histórico temporal completo |
| uso | UNKNOWN quando cobertura não é conhecida | telemetria por aplicação |
| baseline | separado de autorização | calibração + monitoramento |
| thresholds | parâmetros versionados, fora do gabarito | calibração governada |
| função de negócio | não inferida como verdade | Semantic/Transaction Context |
| política | PD002 versionada para a POC | regras institucionais aprovadas |
| escala | Spark/Iceberg + arquitetura distribuída | benchmark e sizing |
| SoD transacional | fronteira explícita de escopo | Fase 2 |

## 1. Dataset da POC

O case não fornece uma base real, então a implementação usa dados sintéticos controlados.

Isso permite testar contratos, cenários conhecidos, comportamento das regras, separação entre runtime e ground truth e reprodutibilidade.

O que **não** fazemos é usar essas métricas como prova de comportamento produtivo.

Antes de produção seriam necessários profiling, amostragem real e validação com especialistas.

## 2. Cobertura de requests

Na V2 sintética, a cobertura de solicitações é tratada como autoritativa para o universo definido pelo contrato da POC.

Essa premissa é proposital e permite testar a diferença entre:

~~~text
aprovação ausente em fonte completa
≠
aprovação não encontrada em fonte de cobertura desconhecida
~~~

Em produção, a cobertura deve ser medida por canal de concessão.

Se a fonte não for autoritativa, a arquitetura deve preservar a incerteza e direcionar o caso para **REVISÃO**, não para uma conclusão automática.

## 3. Vínculo entre request e acesso concedido

A POC pode relacionar uma solicitação ao acesso usando identidade, entitlement e coerência temporal.

Esse relacionamento é classificado explicitamente quanto à qualidade e não é apresentado como chave causal direta.

Uma implantação real pode fortalecer esse contrato com identificadores transacionais de concessão quando a origem disponibilizar essa informação.

## 4. Histórico organizacional

A arquitetura diferencia:

> “há sinal de que o acesso pode ter sido herdado”

de:

> “temos histórico suficiente para confirmar a origem”.

Quando o histórico não é completo, a confiabilidade do sinal é reduzida e a incerteza permanece visível.

Uma fonte temporal de movimentações organizacionais aumentaria a capacidade de confirmar esses casos.

## 5. Telemetria de uso

Um valor nulo em ultimo_uso significa **sem uso registrado**, não “nunca utilizado”.

A POC registra também a cobertura da telemetria. Se ela é desconhecida, a ausência de uso não recebe força indevida.

Em produção, o contrato deve registrar cobertura, retenção e confiabilidade por aplicação.

## 6. Baseline: comportamento não é autorização

O baseline é uma capacidade central da solução desde o desenho inicial.

Ao mesmo tempo, a arquitetura assume explicitamente que:

> **um comportamento frequente pode refletir um padrão histórico inadequado.**

Por isso a baseline não decide sozinha.

Os controles atuais incluem:

- população filtrada;
- contexto organizacional;
- temporalidade;
- âncoras explícitas;
- força de evidência;
- separação entre Expected Access e Policy;
- certificações e aprovações como evidências independentes.

Evoluções possíveis incluem baseline temporal, funções de negócio, peer discovery validado e exclusão de populações com achados confirmados.

## 7. Thresholds

Os thresholds de prevalência e população mínima são parâmetros técnicos, versionados e deliberadamente independentes do gabarito.

Isso reduz risco de leakage.

Eles não são apresentados como regra institucional.

Em produção, seriam calibrados com amostras revisadas, métricas por cenário e monitoramento de drift.

## 8. Catálogo de função de negócio

O case não fornece uma taxonomia completa de funções e transações.

A Fase 1 evita transformar inferência semântica em verdade operacional.

A Fase 2 trata essa necessidade de forma explícita por meio de Transaction Context, Semantic Access Catalog, LLM + RAG como mecanismo assistido de interpretação, validação humana e SoD Policy Catalog versionado.

## 9. Escopo de terceiros

Saber que uma identidade é contractor não informa automaticamente qual é seu escopo autorizado.

A arquitetura preserva o tipo de identidade como contexto, mas uma decisão mais profunda precisa de contrato, assignment ou escopo de atuação.

Esse dado é uma necessidade de integração, não uma regra a ser presumida.

## 10. Política institucional

PD002 é uma política versionada da POC para materializar e testar a semântica do case.

Ela demonstra precedência de regras, tratamento de exceções, contradições, evidência insuficiente e separação entre classificação e risco.

Em produção, o mesmo mecanismo receberia regras aprovadas pelos owners de Segurança, IAM/IGA, Negócio e Risco.

A arquitetura foi desenhada para que a **Policy possa evoluir sem reescrever as etapas de contexto e evidência**.

## 11. Escala produtiva

A implementação usa PySpark e Iceberg e já separa processamento, armazenamento, orquestração e consumo.

Isso torna a solução compatível com execução distribuída.

Dimensionamento produtivo depende de benchmark real de volume, concorrência, SLA, custo, tamanho das tabelas e frequência de execução.

A arquitetura AWS documenta o caminho proposto para esse sizing.

## 12. Fronteira entre Fase 1 e Fase 2

A Fase 1 resolve a sanitização top-down e a governança de acesso propostas para o primeiro estágio do case.

Ela **não tenta simular SoD transacional sem os dados necessários**.

Isso é uma decisão de escopo, não uma lacuna escondida.

A Fase 2 acrescenta função, transação, ação, objeto/escopo, regras de conflito, exceções, controles compensatórios, ML/Graph e LLM + RAG assistido.

## 13. O que estas premissas demonstram

<div class="sod-lane-grid">
  <div class="sod-lane"><span class="sod-kicker">Implementado</span><h3>O que o código garante</h3><p>Contratos, regras, lineage, isolamento do ground truth, observabilidade e decisão reproduzível.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Premissa</span><h3>O que depende do dado</h3><p>Cobertura de requests, histórico, telemetria e qualidade das fontes corporativas.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Produção</span><h3>O que precisa ser validado</h3><p>Calibração, benchmark, regras institucionais e rollout governado.</p></div>
</div>

Essa separação é intencional: uma plataforma de Segurança confiável deve deixar claro **o que sabe, o que assume e o que ainda precisa validar**.
