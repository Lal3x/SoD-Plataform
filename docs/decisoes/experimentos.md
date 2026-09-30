# Experimentos e shadow mode

## 1. Por que experimentar

A arquitetura inicial considerou técnicas de clustering, descoberta de comunidades e anomalias para reduzir dependência de grupos organizacionais fixos.

Essas técnicas continuam interessantes, mas o critério para entrar no runtime é diferente do critério para ser útil em pesquisa.

Uma técnica pode descobrir estrutura relevante e ainda não ser adequada para tomar uma decisão operacional.

## 2. Experimentos existentes

A configuração atual contém três famílias.

### PDISC001 — LDA + FP-Growth

LDA procura fatores latentes no padrão de entitlements.

FP-Growth pode identificar combinações frequentes dentro de grupos.

### PDISC002 — NMF-HDBSCAN

NMF reduz a representação esparsa de acessos para fatores latentes.

HDBSCAN tenta descobrir clusters sem exigir número fixo de grupos e permite ruído.

### GPDISC001 — MinHash/Jaccard + Leiden

A abordagem de grafo conecta identidades com padrões semelhantes e usa Leiden para descobrir comunidades.

## 3. Por que estão em shadow mode

Nenhum deles controla a Policy atual.

Motivos:

- dificuldade de explicar uma decisão somente pelo cluster;
- sensibilidade a população e parâmetros;
- risco de aprender padrões historicamente indevidos;
- necessidade de validar estabilidade;
- baseline atual já resolve o requisito mínimo da Fase 1 de forma mais transparente.

## 4. O que seria necessário para promoção

Um experimento só deveria entrar no runtime depois de demonstrar:

- ganho mensurável;
- estabilidade;
- explicabilidade;
- ausência de leakage;
- comportamento seguro em grupos pequenos;
- estratégia contra contaminação;
- fallback;
- versionamento;
- monitoramento.

## 5. Clustering não substitui política

Mesmo se um cluster descobrir um grupo funcional excelente, ele responderia:

> “Quem se parece com quem?”

Ele não responderia sozinho:

> “Este acesso é autorizado?”

Portanto, qualquer técnica de Peer Discovery continuaria alimentando Expected Access ou Evidence, e não substituindo Policy.

## 6. Anomaly Detection

A arquitetura inicial falava em detecção de anomalias.

Na V2 não existe um engine canônico separado de Anomaly Detection.

A responsabilidade foi refinada para:

- prevalência;
- expectedness;
- evidência;
- política.

Isso torna o significado de “desvio” mais explícito e testável.

## 7. Matriz SoD

Arquivos de configuração ainda podem existir como scaffolding, mas uma matriz SoD transacional ativa não faz parte do runtime V2.

Ela pertence à evolução da Fase 2, quando os entitlements forem mapeados para funções, transações e ações.
