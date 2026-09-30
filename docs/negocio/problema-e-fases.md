# O problema e as duas fases

## 1. O problema de origem

O ponto de partida do case é um processo de identificação de acessos conflitantes e indevidos ainda muito dependente de entrevistas com áreas de negócio, desenvolvimento e gestores. O conhecimento sobre “quem pode o quê” está disperso, enquanto o volume de identidades, sistemas e acessos impede que a análise manual escale.

O case também deixa uma distinção essencial: muitos apontamentos atuais são acessos que parecem não pertencer à estrutura da pessoa, mas **tratar esse conjunto ainda não é SoD no sentido pleno**.

Exemplos apresentados no case incluem:

- tecnologia ou engenharia com perfil de sistema de negócio;
- pessoa de uma comunidade com acesso a sigla de outra;
- terceiro com acesso fora do escopo;
- acesso residual após mudança de área;
- acesso sem registro de utilização;
- sigla pública;
- acesso cross-community legitimamente solicitado e aprovado;
- comunidade pequena, com poucos pares para comparação.

A dificuldade real não é apenas encontrar acessos “diferentes”. É separar **diferença legítima** de **desvio que exige tratamento**.

## 2. Fase 1 — sanitização top-down

A primeira fase é uma sanitização por comunidade, descrita pelo próprio case como o momento de “cortar o mato-alto”.

A unidade de análise de negócio é a **comunidade**. A granularidade do acesso é **Entitlement × Sigla**, contextualizada pela identidade e pelo grant concreto.

O objetivo operacional é produzir uma decisão compreensível:

~~~text
ACESSO
  │
  ├── coerente com padrão explícito/observado → PADRÃO
  ├── exceção justificada                   → LEGÍTIMO
  ├── violação suportada por política       → INDEVIDO
  └── evidência insuficiente/contraditória  → REVISÃO
~~~

A classe REVISÃO é uma decisão de engenharia da POC para representar incerteza de forma explícita. O case pede padrão, legítimo e indevido; a POC evita forçar um desses três quando os dados não sustentam uma conclusão segura.

## 3. Fase 2 — SoD transacional

Depois da sanitização, a SoD madura precisa descer ao nível de funções, transações e ações nos sistemas.

A pergunta deixa de ser somente:

> “Este entitlement faz sentido para esta pessoa?”

e passa a incluir:

> “A combinação das capacidades dessa pessoa permite executar etapas conflitantes do mesmo processo?”

Exemplo conceitual:

~~~text
Identidade
  ├── cadastrar favorecido
  └── aprovar favorecido
          │
          ▼
  mesmo processo / mesmo escopo
          │
          ▼
  potencial conflito SoD
~~~

Uma análise madura ainda precisa considerar vigência, escopo, objeto, exceção formal e controles compensatórios.

## 4. Relação entre as fases

A Fase 2 não deve exigir uma nova plataforma do zero. Ela deve reutilizar o que a Fase 1 já organiza:

- identidade e contexto organizacional;
- grants e temporalidade;
- qualidade e lineage;
- evidências;
- catálogo de política;
- risco e priorização;
- trilha de decisão;
- Gold e mecanismos de consumo;
- observabilidade, versionamento e validação.

Por isso, a POC foi decomposta em responsabilidades independentes. A semântica transacional será adicionada posteriormente sem misturar contexto, evidência, política e risco em um único algoritmo.

## 5. O que a POC resolve hoje

A solução atual responde à Fase 1 de maneira executável e deixa a Fase 2 arquitetada.

Isso evita dois extremos:

- **resolver pouco demais:** apenas listar cross-community como suspeito;
- **prometer demais:** chamar uma análise top-down de “SoD transacional completa”.

A escolha é deliberada: resolver bem o primeiro problema, preservando um caminho técnico claro para o estado final.
