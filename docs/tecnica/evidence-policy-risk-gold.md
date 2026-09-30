# Evidence, Policy, Risk e Gold

## 1. Por que quatro camadas?

Uma única função poderia receber todos os dados e devolver uma classe e um score. Isso seria simples de codificar, mas ruim para governança.

A V2 separa quatro perguntas:

| Camada | Pergunta |
|---|---|
| Evidence | Quais fatos e sinais existem? |
| Policy | O que esses fatos significam segundo a regra vigente? |
| Risk | Qual a prioridade operacional? |
| Gold | Como publicar o resultado para consumo? |

## 2. Evidence

EV001 normaliza fatos sem produzir outcome final.

Entre as evidências estão:

- relação de comunidade;
- público ou não;
- birthright;
- aprovação;
- qualidade do vínculo da aprovação;
- certificação;
- Expected Access;
- uso;
- histórico temporal;
- contradições;
- qualidade de dados.

A existência de Evidence torna Policy mais simples: as regras não precisam reconstruir todas as fontes.

## 3. Policy PD002/1.0.1

A Policy V2 usa precedência explícita.

Ordem atual:

| Regra | Resultado | Intenção |
|---|---|---|
| R010 | REVISÃO | qualidade bloqueante |
| R025 | REVISÃO | conflito aprovação × certificação |
| R020 | LEGÍTIMO | cross aprovado |
| R030 | INDEVIDO | cross que requer aprovação sem aprovação encontrada |
| R040 | REVISÃO | contradição de certificação |
| R140 | REVISÃO | autorização ambígua |
| R050 | PADRÃO | birthright confiável |
| R060 | PADRÃO | padrão funcional observado |
| R070 | LEGÍTIMO | acesso opcional aprovado |
| R080 | LEGÍTIMO | acesso público |
| R130 | REVISÃO | cobertura de autorização insuficiente |
| R110 | REVISÃO | inesperado sem violação explícita |
| R120 | REVISÃO | expectedness insuficiente |
| R999 | REVISÃO | caso não resolvido |

A ordem faz parte da política. Uma regra anterior pode impedir que outra seja alcançada.

### Premissa crítica da R030

A configuração declara request_source_coverage = AUTHORITATIVE_FOR_V2.

Só sob essa premissa a ausência de uma aprovação exigida pode sustentar INDEVIDO.

Essa hipótese deve ser revalidada em produção.

## 4. Por que existe REVISÃO

Sem REVISÃO, toda incerteza teria de ser forçada para legítimo ou indevido.

Isso aumentaria falsos positivos ou falsos negativos.

A classe funciona como uma fila operacional para:

- dados insuficientes;
- ambiguidades;
- contradições;
- casos não cobertos.

Ela não é uma falha do modelo; é uma forma explícita de representar incerteza.

## 5. Risk RISK001

Risk roda depois da Policy.

A versão atual usa componentes para:

- decisão de Policy;
- privilégio;
- criticidade da aplicação;
- escopo regulatório;
- classificação do dado;
- contradições de evidência.

A Policy possui o maior peso do score, evitando que impacto sozinho transforme um acesso legítimo em irregular.

Faixas atuais:

- LOW: 0–19;
- MEDIUM: 20–39;
- HIGH: 40–69;
- CRITICAL: 70–100.

Ações:

~~~text
INDEVIDO → REMEDIATE
REVISÃO  → REVIEW
outros de alto impacto → MONITOR
demais → NONE
~~~

Os pesos e faixas são parâmetros da POC, não políticas institucionais definitivas.

## 6. Gold GOLD001

Gold reúne as saídas congeladas de:

- Access Context;
- Expected Access;
- Evidence;
- Policy;
- Risk.

Ela publica campos de negócio e técnicos, por exemplo:

- identidade e contexto;
- entitlement e sigla;
- estado de expectedness;
- baseline selecionado;
- evidências;
- decisão e reason code;
- risk score e drivers;
- fila operacional;
- versões e timestamps.

Gold também deriva conveniências de consumo como:

- review_required;
- remediation_candidate;
- operational_queue.

Esses campos derivam de decisões já existentes. Gold não executa nova inteligência.

## 7. Proteção contra leakage

O script Gold contém uma lista de colunas proibidas relacionadas ao ground truth e verifica que elas não estão presentes nos inputs e output.

Isso reforça uma regra arquitetural:

> Dados usados para avaliar o runtime não devem participar da construção da decisão.

## 8. Explicabilidade ponta a ponta

Uma linha Gold deve permitir responder:

1. Qual identidade e acesso foram avaliados?
2. Qual era o contexto?
3. O acesso era esperado?
4. Com base em qual população?
5. Havia aprovação ou certificação?
6. Qual regra decidiu?
7. Por que aquela regra?
8. Qual o risco?
9. O que fazer?
10. Com quais versões essa decisão foi produzida?
