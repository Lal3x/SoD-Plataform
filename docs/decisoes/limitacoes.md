# Limitações e premissas

Uma POC confiável precisa documentar não apenas o que funciona, mas também **sob quais condições funciona**.

## 1. Dados sintéticos

O case não fornece dados reais.

Consequências:

- distribuições não provam comportamento produtivo;
- métricas de validação demonstram consistência da POC, não performance do banco;
- SLAs e volumes reais precisam de teste próprio.

## 2. Cobertura de requests

PD002 considera a fonte de requests autoritativa na V2.

Essa premissa permite R030.

Em produção, é obrigatório verificar se todos os mecanismos de concessão relevante realmente aparecem nessa fonte. Caso contrário, ausência de request deve resultar em REVISÃO, não em INDEVIDO.

## 3. Vínculo request → grant

A POC pode inferir vínculo por identidade, entitlement e temporalidade.

Sem uma chave direta, o match não possui a mesma força de um relacionamento transacional explícito.

## 4. Histórico organizacional

A POC consegue identificar quando a data de concessão antecede a entrada na comunidade atual, mas marca identity_history_complete como falso.

Logo, inherited_access_candidate é sinal, não conclusão.

## 5. Telemetria de uso

ultimo_uso nulo é interpretado como “sem uso registrado”.

usage_coverage permanece UNKNOWN.

Produção precisa conhecer:

- quais aplicações geram telemetria;
- período de retenção;
- cobertura;
- possíveis falhas de integração.

## 6. Contaminação do baseline

Observed Baseline não é calculado apenas com Hard Trusted Set.

Ele filtra a população, mas ainda pode refletir padrões inadequados historicamente comuns.

Mitigações futuras possíveis:

- anchors mais fortes;
- excluir populações com achados confirmados;
- baseline temporal;
- segmentação por função;
- peer discovery validado;
- comparação com política institucional.

## 7. Thresholds

Os thresholds de expectedness e mínimos de população são parâmetros técnicos de POC.

Eles não foram calibrados com o gabarito e não são apresentados como política do banco.

Produção exigiria calibração governada e monitoramento de drift.

## 8. Catálogo de função de negócio

O case menciona tecnologia/engenharia acessando perfis de negócio, mas não fornece uma taxonomia completa de perfis.

A V2 não inventa uma.

Esse gap é tratado na arquitetura de Fase 2 por Transaction Context e SoD Policy Catalog.

## 9. Contractor fora de escopo

Saber que uma identidade é contractor não revela automaticamente qual é seu escopo autorizado.

Produção precisa de dado de escopo, contrato ou assignment de frente.

## 10. Política institucional

PD002 é uma política de POC construída para materializar a semântica do case.

Ela não deve ser confundida com norma institucional aprovada.

Antes de produção, owners de segurança, IAM/IGA, negócio e risco precisam validar:

- regras;
- precedência;
- exceções;
- thresholds;
- evidências mínimas;
- ações permitidas.

## 11. Escala produtiva

PySpark e Iceberg tornam a solução escalável conceitualmente, mas a POC local não comprova dimensionamento de produção.

A arquitetura AWS apresenta um caminho de execução distribuída; benchmarking real ainda é necessário.

## 12. SoD pleno

A Fase 1 não implementa matriz de conflito transacional.

Isso não é uma lacuna escondida: é a fronteira explicitamente definida pelo próprio case.

A Fase 2 está desenhada para adicionar essa semântica sem invalidar a arquitetura atual.
