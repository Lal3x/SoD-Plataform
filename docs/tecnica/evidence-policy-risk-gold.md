# Evidence, Policy, Risk e Gold

## 1. Por que separar quatro responsabilidades?

Seria possível criar uma única função que recebesse todos os dados e devolvesse uma classe final com score. Isso seria simples de demonstrar, mas frágil para governança.

A V2 separa quatro perguntas:

| Camada | Pergunta |
|---|---|
| Evidence | Quais fatos existem e quão confiáveis são? |
| Policy | O que esses fatos significam segundo a regra vigente? |
| Risk | Qual a prioridade operacional? |
| Gold | Como publicar o resultado de forma consistente e auditável? |

Essa separação permite testar, versionar e explicar cada estágio.

## 2. Evidence — fatos antes de opinião

Evidence organiza sinais vindos de contexto, expectedness, requests e certificações.

Exemplos:

- relação same/cross-community;
- caráter público;
- birthright;
- aprovação encontrada ou não;
- qualidade do vínculo da aprovação;
- certificação;
- Expected Access;
- cobertura de uso;
- candidato a acesso herdado;
- contradições;
- qualidade de dados.

A regra fundamental é:

> **Evidence não decide.**

Ela prepara um bundle de fatos para que Policy tome a decisão sem precisar reconstruir joins e inferências toda vez.

## 3. Policy PD002 — transformar evidência em decisão

A Policy atual é determinística e versionada.

A precedência faz parte da própria política:

~~~text
R010 DQ bloqueante                          → REVISÃO
R025 aprovação × certificação conflitante  → REVISÃO
R020 cross aprovado                        → LEGÍTIMO
R030 cross sem aprovação em fonte autoritativa → INDEVIDO
R040 certificação REVOKE                    → REVISÃO
R140 autorização ambígua                   → REVISÃO
R050 trusted birthright                    → PADRÃO
R060 padrão funcional observado            → PADRÃO
R070 acesso opcional aprovado              → LEGÍTIMO
R080 acesso público                        → LEGÍTIMO
R130 cobertura de autorização insuficiente → REVISÃO
R110 inesperado sem violação explícita     → REVISÃO
R120 expectedness insuficiente             → REVISÃO
R999 não resolvido                         → REVISÃO
~~~

A ordem é intencional. Contradições e DQ são avaliadas antes de regras permissivas.

## 4. Walkthrough 1 — cross legítimo

Considere:

~~~text
Pessoa: I-1023
Comunidade: Crédito
Entitlement: ENT-COB-LEITURA
Dona da sigla: Cobrança
Sigla pública: não
~~~

Access Context identifica cross-community.

Evidence encontra:

~~~text
approval_evidence_status = UNIQUE_MATCH
approval_linkage_quality = STRONG_INFERRED
certification_status != REVOKE
~~~

Policy avalia a precedência:

~~~text
R010? não
R025? não
R020? sim
~~~

Resultado:

~~~text
policy_decision = LEGÍTIMO
policy_rule_id = R020
~~~

O fato de o acesso ser raro ou inesperado não invalida uma autorização forte.

## 5. Walkthrough 2 — cross sem autorização

Agora considere o mesmo contexto, mas sem request válida.

Evidence:

~~~text
community_relation = CROSS_COMMUNITY
public_application = false
approval_evidence_status = NOT_FOUND
request_source_coverage = AUTHORITATIVE_FOR_V2
~~~

Policy:

~~~text
R030 → INDEVIDO
~~~

A conclusão só é possível porque a POC assume que a fonte de requests é autoritativa para esse universo.

Sem essa premissa:

~~~text
R130 → REVISÃO
~~~

## 6. Walkthrough 3 — contradição

Considere um cross com approval forte, porém certificação REVOKE.

~~~text
approval = strong
certification = REVOKE
~~~

A regra R025 vem antes de R020.

Resultado:

~~~text
REVISÃO
~~~

Isso evita legitimar automaticamente um acesso quando existe evidência posterior de revogação.

## 7. Risk — prioridade não é classificação

Depois da Policy, Risk responde outra pergunta:

> “Mesmo sabendo a classe, qual caso merece atenção primeiro?”

A V2 soma componentes de impacto.

### Exemplo A — indevido crítico

~~~text
Policy = INDEVIDO               +50
Privileged = true               +15
Application = CRITICAL          +15
Regulatory scope = BACEN        +10
Data classification = RESTRICTED +5
-----------------------------------
Risk Score                        95
Risk Band                   CRITICAL
Priority Action             REMEDIATE
~~~

### Exemplo B — legítimo sensível

~~~text
Policy = LEGÍTIMO                +5
Privileged = true               +15
Application = CRITICAL          +15
-----------------------------------
Risk Score                        35
Risk Band                    MEDIUM
Priority Action              MONITOR
~~~

Esse segundo exemplo é importante: alto impacto não transforma LEGÍTIMO em INDEVIDO.

## 8. Por que Policy tem o maior peso

A classificação de negócio é o principal componente do score.

Isso impede que sensibilidade ou privilégio, sozinhos, convertam um acesso permitido em violação.

Risk ordena tratamento. Ele não reescreve a decisão.

## 9. Gold — contrato de consumo

Gold reúne outputs já produzidos.

Entre os campos publicados estão:

- identidade e contexto;
- entitlement e sigla;
- Expected Access;
- baseline selecionado;
- evidências;
- policy_decision;
- policy_rule_id;
- policy_reason_code;
- decision_confidence;
- risk_score;
- risk_band;
- priority_action;
- risk drivers;
- versões;
- snapshots;
- processing timestamp.

Ela também cria conveniências operacionais, como review_required, remediation_candidate e operational_queue.

## 10. O que Gold deliberadamente não faz

Gold não deve:

- criar nova regra;
- recalcular classificação;
- mudar risk score;
- consultar ground truth;
- esconder divergências upstream.

O script de materialização reconcilia Gold com Policy, Risk, Expected Access e Evidence.

Se houver divergência, a publicação deve falhar.

## 11. Explicabilidade ponta a ponta

Uma linha Gold deve permitir reconstruir:

~~~text
quem?
  ↓
qual grant?
  ↓
qual contexto?
  ↓
qual expectedness?
  ↓
qual evidência?
  ↓
qual regra venceu?
  ↓
qual risco?
  ↓
qual ação?
  ↓
quais versões e snapshots?
~~~

A meta não é apenas fornecer uma resposta, mas fornecer uma resposta que possa ser contestada, reproduzida e auditada.
