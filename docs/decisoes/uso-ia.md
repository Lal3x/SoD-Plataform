# Uso de IA no desenvolvimento

## 1. Posicionamento

IA foi usada como **ferramenta de engenharia e produtividade**, não como autoridade de domínio nem como componente do runtime.

A POC não chama LLM para classificar acessos.

## 2. Onde a IA ajudou

Durante o desenvolvimento, IA foi utilizada para:

- brainstorming de alternativas arquiteturais;
- questionamento de hipóteses;
- aceleração de implementação;
- revisão de código;
- geração e revisão de testes;
- exploração de edge cases;
- organização da documentação;
- comparação entre desenho e implementação.

## 3. O que permaneceu responsabilidade humana

O engenheiro manteve responsabilidade por:

- interpretação do case;
- definição do problema;
- decisões arquiteturais;
- modelagem das regras;
- escolha dos trade-offs;
- avaliação de riscos;
- validação da implementação;
- aceitação ou rejeição das sugestões da IA;
- definição do que entra ou não no runtime.

Em termos simples:

> **IA aumentou a velocidade de execução; conhecimento técnico e decisão permaneceram sob responsabilidade humana.**

## 4. Por que não usar LLM no runtime

Para a Fase 1, a necessidade principal é produzir decisões:

- reproduzíveis;
- explicáveis;
- auditáveis;
- versionáveis;
- testáveis.

Regras determinísticas e estatísticas controladas atendem melhor a esse núcleo.

Isso não significa que LLM nunca poderia agregar valor.

Possíveis usos futuros, sempre com controles, incluem:

- auxiliar analista a resumir evidências;
- traduzir reason codes para linguagem executiva;
- ajudar a consultar documentação de regras;
- apoiar investigação de casos.

Esses usos devem consumir decisões e evidências existentes, não substituir silenciosamente a política.

## 5. Transparência

A documentação também foi produzida com apoio de IA e revisada contra o case e a implementação do repositório.

Esse uso é declarado porque o objetivo é demonstrar engenharia responsável, não esconder ferramentas de produtividade.
