# Vocabulário essencial

Esta página existe para que a documentação possa ser lida por pessoas de negócio, segurança, auditoria ou tecnologia sem exigir conhecimento prévio de IAM, IGA ou engenharia de dados.

A regra usada no restante da documentação é:

> **primeiro explicamos o conceito em linguagem de negócio; depois mostramos o nome técnico usado no código.**

## Acesso concedido — grant

Um **acesso concedido** representa uma autorização concreta que uma identidade possui em determinado entitlement/sistema.

No código e nos contratos técnicos, esse registro é chamado de **grant**.

Exemplo:

~~~text
Pessoa: Marina
Entitlement: ENT_COB_LEITURA
Sigla: COB
Data de concessão: 10/03/2026
~~~

Esse registro individual é um grant.

## Entitlement

Um **entitlement** é uma unidade de permissão ou pacote de permissões.

Pode representar, por exemplo:

- um grupo;
- um perfil;
- uma role;
- um bundle de acesso.

A POC usa entitlement porque o case define a granularidade de acesso como Entitlement × Sigla.

## Sigla

A **sigla** representa a aplicação/sistema no contexto do case.

Cada sigla possui uma comunidade proprietária e pode ser restrita ou disponibilizada de forma pública para o banco.

## Comunidade

A **comunidade** é a estrutura organizacional usada pelo case como principal unidade de análise da Fase 1.

Ela ajuda a responder:

> “Esse acesso pertence normalmente ao contexto em que essa pessoa trabalha?”

## Birthright — acesso nato

Um **acesso nato** é um acesso que deveria existir automaticamente em função de uma condição conhecida, como papel, área ou vínculo.

O termo técnico usado no projeto é **birthright**.

Na POC, um birthright sem contradições relevantes funciona como uma evidência explícita forte de que aquele acesso faz parte do padrão esperado.

## Acesso entre comunidades — cross-community

Quando a pessoa pertence a uma comunidade e acessa uma sigla pertencente a outra, chamamos isso de **acesso entre comunidades**.

No código:

~~~text
cross_community = true
~~~

Isso **não significa automaticamente acesso indevido**. Pode existir uma justificativa ou aprovação válida.

## Sigla pública

Uma **sigla pública** é uma aplicação disponibilizada para pessoas de diferentes comunidades.

Por isso, um acesso entre comunidades para uma sigla pública não deve ser tratado como risco apenas por atravessar a fronteira organizacional.

## Fonte autoritativa

Uma **fonte autoritativa** é uma fonte considerada completa e confiável para responder determinada pergunta.

Exemplo:

> Se afirmamos que a base de solicitações contém todas as aprovações relevantes para determinado universo, então não encontrar uma aprovação passa a ter significado.

Sem essa garantia, “não encontrei aprovação” pode significar apenas “minha fonte está incompleta”.

## Padrão observado — baseline

O **padrão observado** descreve o comportamento mais comum entre pessoas comparáveis.

No projeto, esse padrão é materializado pelo **Observed Baseline**.

Exemplo:

~~~text
20 analistas comparáveis
18 possuem o mesmo entitlement

prevalência = 18 / 20 = 90%
~~~

Isso mostra que o acesso é comum naquele grupo.

Não prova, sozinho, que seja autorizado.

## Grupo de comparação

É o conjunto de pessoas usado para avaliar se determinado acesso é comum ou incomum.

A solução tenta começar pelo grupo mais parecido possível com a pessoa analisada.

Exemplo:

~~~text
mesma comunidade
+ mesmo squad
+ mesmo cargo
+ mesmo tipo de vínculo
~~~

## Ampliação hierárquica da comparação — Hierarchical Fallback

Quando o grupo mais específico é pequeno demais para uma comparação confiável, a solução amplia gradualmente a referência.

Exemplo:

~~~text
mesma comunidade + squad + cargo + vínculo
                ↓ grupo pequeno
mesma comunidade + cargo
                ↓ ainda pequeno
mesma comunidade
                ↓ ainda insuficiente
tipo de vínculo comparável
~~~

O nome técnico desse mecanismo é **Hierarchical Fallback**.

Ele evita tomar uma decisão estatística forte com base em poucas pessoas.

## Acesso esperado — Expected Access

O **Expected Access** responde:

> “Com base nas evidências disponíveis, este acesso parece esperado para pessoas comparáveis?”

Os estados técnicos são:

- EXPECTED;
- UNEXPECTED;
- INSUFFICIENT_EVIDENCE.

Essa análise **não decide autorização**.

## Evidência

Uma **evidência** é um fato usado para sustentar uma decisão.

Exemplos:

- acesso nato;
- aprovação válida;
- sigla pública;
- padrão observado;
- certificação;
- relação entre comunidades;
- qualidade do dado.

## Âncora explícita

Uma **âncora explícita** é uma evidência considerada mais direta e confiável do que uma inferência estatística.

Exemplo:

> Um birthright válido informa explicitamente que o acesso pertence ao conjunto esperado daquela identidade.

Por isso ele pode servir de “ponto de referência” mesmo que a frequência observada seja baixa.

## Hard Trusted Set — conjunto de referências confiáveis

O **Hard Trusted Set (HTS)** é o conjunto de acessos que atendem critérios explícitos de alta confiança.

Na V2, ele é usado principalmente para identificar acessos natos confiáveis.

O HTS não significa que todo o comportamento esperado seja definido apenas por ele.

## Evidência HIGH — evidência forte

Quando a documentação usa **evidência HIGH**, significa:

> a evidência foi considerada forte o suficiente, dentro da regra técnica da POC, para sustentar determinada decisão automática.

Esse nível não é uma probabilidade universal. É uma categoria de força de evidência usada pelo runtime.

## Certificação REVOKE

Uma **certificação** registra uma decisão de revisão de acesso.

REVOKE significa que a certificação indica que o acesso deveria ser revogado.

Se encontramos simultaneamente:

~~~text
aprovação válida
+
certificação REVOKE
~~~

há uma contradição. A POC envia o caso para REVISÃO em vez de escolher automaticamente uma das evidências.

## Policy — regras de decisão

A **Policy** é o conjunto versionado de regras que transforma evidências em uma decisão:

- PADRÃO;
- LEGÍTIMO;
- INDEVIDO;
- REVISÃO.

## Risk — prioridade de tratamento

A camada **Risk** não redefine a classificação.

Ela responde:

> “Qual caso deve ser tratado primeiro?”

Para isso combina a decisão com impacto, como privilégio, criticidade da aplicação e classificação de dados.

## Gold — camada final de consumo

A **Gold** é a camada final publicada para dashboard, análise e operação.

Ela reúne resultados já produzidos por Expected Access, Evidence, Policy e Risk.

A Gold não deve inventar novas regras.

## Lineage — rastreabilidade

**Lineage** é a capacidade de reconstruir de onde veio um resultado.

Para uma decisão de acesso, isso inclui:

- quais tabelas foram usadas;
- quais snapshots;
- qual versão das regras;
- qual execução;
- qual output foi publicado.

## Snapshot

Um **snapshot** representa um estado versionado de uma tabela Iceberg em determinado momento.

Ele ajuda a reproduzir uma decisão mesmo se os dados mudarem depois.

## Shadow mode — modo experimental

Uma técnica em **shadow mode** pode ser executada e avaliada, mas não controla a decisão operacional.

Na POC, clustering, grafos e outras técnicas de Peer Discovery permanecem nesse modo até demonstrarem ganho, estabilidade e explicabilidade.
