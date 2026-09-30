# Premissas, controles e gates de produção

Esta página registra as **condições de validade da POC**, os controles já implementados e o que deve ser confirmado antes de uma implantação produtiva.

Em Segurança e Governança de Acessos, explicitar essas condições é parte do controle: uma decisão confiável precisa deixar claro **qual dado a sustenta, qual cobertura existe e quando a automação deve parar em REVISÃO**.

## Visão executiva

| Tema | O que a POC faz hoje | Gate antes de produção |
|---|---|---|
| dados de avaliação | cenários sintéticos conhecidos + ground truth isolado | profiling e validação com amostra real |
| requests | cobertura declarada no contrato V2 | medir completude por canal de concessão |
| request → acesso | qualidade do vínculo explicitada | usar chave transacional quando disponível |
| histórico organizacional | incerteza reduz força da evidência | integrar histórico temporal corporativo |
| telemetria de uso | UNKNOWN quando a cobertura não é conhecida | medir cobertura e retenção por aplicação |
| baseline | mede comportamento, não autorização | calibrar e monitorar por população |
| thresholds | parâmetros versionados fora do gabarito | calibração governada com amostras reais |
| função/transação | fora da decisão da Fase 1 | construir Transaction/Semantic Context |
| política | PD002 versionada para a POC | substituir/validar com regras institucionais |
| escala | Spark + Iceberg + componentes desacoplados | benchmark, sizing, SLA e custo |
| SoD transacional | arquitetura preparada para evolução | implementar Fase 2 com catálogo SoD |

## 1. Dados sintéticos: objetivo correto

O case não fornece uma base real. A POC usa dados sintéticos controlados para exercitar contratos, cenários, regras, rastreabilidade, validação e reprodutibilidade.

Isso permite testar **o método e a arquitetura**.

As métricas obtidas nesse universo não são apresentadas como estimativa de desempenho em produção. O gate produtivo é validar a solução sobre dados reais, com profiling e amostras revisadas por especialistas.

## 2. Cobertura de solicitações

Na V2 sintética, a base de requests é tratada como autoritativa para o universo definido pelo contrato da POC.

Esse contrato permite diferenciar duas situações:

<div class="sod-lane-grid sod-lane-grid--2">
  <div class="sod-lane"><span class="sod-kicker">Fonte completa</span><h3>Aprovação ausente tem significado</h3><p>Se sabemos que todas as aprovações relevantes deveriam estar ali, a ausência pode participar de uma regra.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Cobertura desconhecida</span><h3>A ausência permanece incerta</h3><p>Não encontrar um registro não é prova suficiente; o caso deve preservar incerteza.</p></div>
</div>

Em produção, a cobertura precisa ser medida por canal de concessão. Quando ela não for suficiente, a arquitetura deve preferir **REVISÃO** a uma conclusão automática.

## 3. Vínculo entre solicitação e acesso concedido

Quando não existe uma chave causal direta entre request e acesso, a POC usa identidade, entitlement e coerência temporal para identificar candidatos e registra explicitamente a qualidade desse vínculo.

A arquitetura não transforma uma inferência em evidência direta.

Em produção, quando a origem disponibilizar um identificador transacional de concessão, ele deve substituir a inferência e elevar a confiabilidade do vínculo.

## 4. Histórico organizacional

A solução diferencia um **sinal de acesso possivelmente herdado** de uma confirmação histórica.

Se o histórico organizacional estiver incompleto, a confiabilidade é reduzida e a incerteza permanece visível.

O gate produtivo é integrar histórico temporal suficiente para reconstruir movimentações relevantes da identidade.

## 5. Telemetria de uso

Um valor nulo em `ultimo_uso` significa **sem uso registrado**, não “nunca utilizado”.

A ausência só ganha significado quando a cobertura da telemetria é conhecida. Em produção, cada aplicação deve declarar cobertura, retenção e confiabilidade da fonte de uso.

## 6. Baseline: referência de comportamento, não autorização

A baseline é uma capacidade central desde o desenho inicial e materializa um princípio de monitoramento de segurança: **definir comportamento esperado antes de procurar desvios**.

O controle mais importante é que comportamento frequente não vira autorização automaticamente.

A POC já combina população comparável, contexto organizacional, temporalidade, âncoras explícitas, força de evidência, Expected Access separado de Policy e aprovações/certificações como sinais independentes.

Em produção, a baseline pode evoluir com janelas temporais, peer discovery validado, funções de negócio e exclusão governada de populações sabidamente contaminadas.

## 7. Thresholds

Os thresholds de prevalência e suporte mínimo são **parâmetros técnicos versionados**, independentes do ground truth de validação.

Eles existem para tornar o comportamento reproduzível e calibrável, não para representar uma política institucional universal.

O gate produtivo é calibrá-los com amostras reais, métricas por cenário, impacto operacional e monitoramento de drift.

## 8. Semântica de função e transação

A Fase 1 trabalha com o nível de informação disponível no case: identidade, entitlement, sigla e contexto organizacional.

A Fase 2 adiciona a semântica necessária para SoD transacional: **entitlement → função → transação → ação → objeto/escopo**.

LLM + RAG pode acelerar a interpretação de catálogos, políticas e manuais, mas o resultado aprovado deve ser materializado em um **Semantic Access Catalog versionado**, não permanecer como resposta livre de modelo.

## 9. Terceiros

O tipo de identidade é contexto; ele não substitui o escopo contratual.

Para terceiros, uma decisão mais profunda pode exigir assignment, contrato, período, sistema autorizado e escopo de atuação. Esses dados entram como enriquecimento de contexto, e não como presunções codificadas.

## 10. Política institucional

PD002 materializa, de forma versionada, a semântica usada pela POC para testar precedência, exceções, contradições e insuficiência de evidência.

A arquitetura separa **Evidence de Policy** justamente para permitir que regras institucionais aprovadas substituam ou evoluam a Policy sem reconstruir todo o pipeline de contexto.

Em produção, esse catálogo deve ter ownership definido entre Segurança, IAM/IGA, Negócio e Risco.

## 11. Escala e operação

A implementação utiliza PySpark, Iceberg, Airflow e separação entre processamento, armazenamento, orquestração e consumo.

Isso fornece uma base tecnicamente adequada para execução distribuída, mas capacidade produtiva só pode ser afirmada após benchmark com volume, concorrência, SLA e custo representativos.

A arquitetura AWS documenta o caminho proposto para esse sizing.

## 12. Fronteira de escopo entre as fases

A **Fase 1** resolve a sanitização top-down e a governança do acesso no nível solicitado pelo primeiro estágio do case.

A **Fase 2** aprofunda a semântica para conflitos transacionais, adicionando Transaction Context, Semantic Access Catalog, SoD Policy Catalog, exceções, controles compensatórios, ML/Graph e LLM + RAG assistido.

Essa divisão evita forçar uma conclusão transacional sem possuir os dados que a sustentam.

## 13. Critérios para promoção produtiva

<div class="sod-security-map">
  <div><b>Dados</b><span>profiling, cobertura, temporalidade e contratos de origem conhecidos.</span></div>
  <div><b>Decisão</b><span>Policy aprovada, thresholds calibrados e exceções governadas.</span></div>
  <div><b>Validação</b><span>precision, recall, false-safe e false-positive rate avaliados por cenário.</span></div>
  <div><b>Operação</b><span>SLA, reprocessamento, observabilidade, alertas e runbooks definidos.</span></div>
  <div><b>Segurança</b><span>segregação de roles, secrets, criptografia e isolamento do ground truth.</span></div>
  <div><b>Rollout</b><span>shadow run, revisão humana e aumento gradual da automação.</span></div>
</div>

## 14. O que essa página demonstra

A POC não depende de “dados perfeitos”. Ela foi desenhada para **medir cobertura, registrar confiabilidade, preservar UNKNOWN/REVISÃO e impedir automação quando a evidência não sustenta a conclusão**.

O objetivo de produção não é eliminar toda incerteza. É torná-la **observável, governável e tratável**.
