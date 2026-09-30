# Dashboard e operação

## 1. Papel do Streamlit

O dashboard é uma camada de consumo e explicabilidade.

Ele não executa a Policy e não deve recalcular o risk score.

As páginas operacionais leem a Gold por meio de GoldRepository.

A validação usa ValidationRepository separadamente.

Metadados de engenharia são acessados por ObservabilityRepository.

## 2. Sete visões

A aplicação atual possui sete páginas:

1. Visão Executiva;
2. Acessos;
3. Risco & Priorização;
4. Explainability;
5. Análise de Dados;
6. Validação POC V2;
7. Observabilidade.

Essa divisão evita misturar a visão de operação com a visão de validação.

## 3. Interface read-only

A interface atual é somente leitura.

Isso é deliberado.

Uma decisão de remediação pode precisar:

- aprovação;
- workflow;
- evidência adicional;
- segregação de responsabilidade;
- integração com IAM/IGA.

Em produção, o dashboard pode iniciar ou acompanhar um workflow, mas a revogação não deveria ser escondida em uma ação sem governança.

## 4. Filas operacionais

A Gold já materializa informações adequadas a filas:

- remediation_candidate;
- review_required;
- operational_queue;
- priority_action;
- risk_band.

Exemplo conceitual:

~~~text
CRITICAL_REMEDIATION
      ↓
analista verifica evidências
      ↓
workflow de revogação
      ↓
registro do resultado
      ↓
feedback para controle e validação
~~~

## 5. Explainability

Para cada grant, a interface deve permitir navegar de uma conclusão até seus fatos:

~~~text
INDEVIDO
   ↓
R030
   ↓
cross-community
   ↓
aprovação exigida
   ↓
fonte considerada autoritativa
   ↓
aprovação não encontrada
   ↓
criticidade / privilégio
   ↓
prioridade
~~~

Isso reduz o custo de uma revisão e facilita contestação.

## 6. Operação com Airflow

O DAG runtime organiza as etapas em grupos:

- preparação;
- curadoria;
- inteligência de acesso;
- decisão.

Ao final:

- Gold é validada por gate;
- o run é registrado;
- a validação offline é disparada.

Essa sequência cria um ponto de separação claro entre produzir e avaliar a decisão.

## 7. Operação futura

Em produção, a interface e a orquestração deveriam também contemplar:

- ownership do caso;
- SLA;
- justificativa da revisão;
- decisão humana;
- remediação executada;
- exceção aprovada;
- data de expiração;
- reabertura;
- métricas de eficiência.

Esse feedback não deve ser automaticamente convertido em verdade de treinamento sem governança. Ele é primeiro um registro operacional sujeito a validação.
