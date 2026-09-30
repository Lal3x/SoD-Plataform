# Premissas, controles e gates de produção

Esta página registra as **condições de validade da POC**, os controles já implementados e o que deve ser confirmado antes de uma implantação produtiva.

Em Segurança e Governança de Acessos, explicitar essas condições é parte do controle: uma decisão confiável precisa deixar claro **qual dado a sustenta, qual cobertura existe e quando a automação deve parar em REVISÃO**.

## Visão executiva

| Tema | O que a POC faz hoje | Gate antes de produção |
|---|---|---|
| dados de avaliação | cenários sintéticos conhecidos + ground truth isolado | profiling e validação com amostra real |
| requests | cobertura declarada no contrato V2 | medir completude por canal de concessão |
| request → acesso | qualidade do vínculo explicitada | usar chave transacional quando disponível |
| ciclo de vida do grant | chave técnica identidade × entitlement no snapshot atual | usar identificador nativo ou chave temporal para concessões repetidas |
| data de avaliação | `assessment_date` reutiliza `data_ingestao` na POC | separar as duas datas para reprocessamento histórico |
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

| Situação da fonte | O que a ausência de aprovação significa |
|---|---|
| **Fonte completa/autoritativa** | se todas as aprovações relevantes deveriam estar presentes, a ausência pode participar de uma regra |
| **Cobertura desconhecida ou incompleta** | não encontrar um registro não é prova suficiente; o caso deve preservar incerteza |

Em produção, a cobertura precisa ser medida por canal de concessão. Quando ela não for suficiente, a arquitetura deve preferir **REVISÃO** a uma conclusão automática.

## 3. Vínculo entre solicitação e acesso concedido

Quando não existe uma chave causal direta entre request e acesso, a POC usa identidade, entitlement e coerência temporal para identificar candidatos e registra explicitamente a qualidade desse vínculo.

A arquitetura não transforma uma inferência em evidência direta.

Em produção, quando a origem disponibilizar um identificador transacional de concessão, ele deve substituir a inferência e elevar a confiabilidade do vínculo.

### Chave técnica do grant e ciclo de vida

A fonte sintética não fornece um identificador nativo de concessão. Por isso a Silver gera `grant_id` de forma determinística a partir de **identidade × entitlement**.

Isso é suficiente para o contrato atual, que trabalha com um assignment canônico por par no snapshot.

Existe, porém, uma limitação importante para histórico produtivo:

```text
Pessoa recebe ENT_X
→ perde ENT_X
→ meses depois recebe ENT_X novamente
```

Essas são duas concessões diferentes no tempo, mas o par identidade × entitlement é o mesmo. Em produção, o ideal é usar **um ID nativo da concessão** ou incorporar a temporalidade/effective date à identidade técnica do evento.

A POC não esconde essa hipótese: a chave atual identifica o grant canônico do snapshot, não todo o ciclo de vida histórico de uma concessão.

## 4. Histórico organizacional

A solução diferencia um **sinal de acesso possivelmente herdado** de uma confirmação histórica.

Se o histórico organizacional estiver incompleto, a confiabilidade é reduzida e a incerteza permanece visível.

O gate produtivo é integrar histórico temporal suficiente para reconstruir movimentações relevantes da identidade.

### Data de ingestão versus data de avaliação

São conceitos diferentes:

| Data | Pergunta que responde |
|---|---|
| `data_ingestao` | quando os dados foram carregados/processados? |
| `assessment_date` | em qual data a situação de acesso está sendo avaliada? |

No run validado da POC, ambas são `2025-02-01`, porque o DAG atual reutiliza `data_ingestao` como `assessment_date`.

Isso é uma simplificação conhecida. Em produção, elas devem ser independentes para permitir, por exemplo, **carregar dados hoje e reproduzir como a decisão deveria ter sido em uma data histórica**.

Mudar apenas a separação dos parâmetros, mantendo os mesmos valores, não deveria alterar o resultado. Mudar efetivamente a `assessment_date` pode mudar concessões elegíveis, aprovações, certificações, baseline e a decisão final.

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

A calibração não deve ser feita escolhendo números que “fazem o gabarito passar”. O processo esperado é governado:

```text
parâmetro candidato
      ↓
amostra real revisada
      ↓
precision / recall / taxa de revisão
      ↓
impacto operacional e risco
      ↓
comparação entre configurações
      ↓
aprovação e versionamento
      ↓
monitoramento de drift
```

O mesmo princípio vale para os pesos do Risk: o número final deve refletir apetite a risco e prioridade institucional, não apenas o desempenho do cenário sintético.

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

| Dimensão | Critério para promoção |
|---|---|
| **Dados** | profiling, cobertura, temporalidade e contratos de origem conhecidos |
| **Decisão** | Policy aprovada, thresholds calibrados e exceções governadas |
| **Validação** | precision, recall, false-safe e false-positive rate avaliados por cenário |
| **Operação** | SLA, reprocessamento, observabilidade, alertas e runbooks definidos |
| **Segurança** | segregação de roles, secrets, criptografia e isolamento do ground truth |
| **Rollout** | shadow run, revisão humana e aumento gradual da automação |

## 14. O que essa página demonstra

A POC não depende de “dados perfeitos”. Ela foi desenhada para **medir cobertura, registrar confiabilidade, preservar UNKNOWN/REVISÃO e impedir automação quando a evidência não sustenta a conclusão**.

O objetivo de produção não é eliminar toda incerteza. É torná-la **observável, governável e tratável**.
