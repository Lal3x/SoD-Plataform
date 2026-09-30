# Arquitetura alvo na AWS

## 1. Objetivo

A implementação atual é executável localmente com Spark, Iceberg, Airflow e Streamlit. Esta página mostra como as mesmas responsabilidades poderiam ser levadas para AWS sem alterar a semântica central da solução.

!!! info "Status"
    Esta é uma **arquitetura-alvo de produção**, não uma descrição de infraestrutura já implantada.

## 2. Mapeamento de componentes

| Implementação atual | Arquitetura AWS sugerida | Responsabilidade |
|---|---|---|
| data/raw | Amazon S3 landing/raw | entrada imutável |
| warehouse Iceberg | Amazon S3 | armazenamento Bronze/Silver/Intelligence/Gold |
| catálogo local Iceberg | AWS Glue Data Catalog | catálogo das tabelas Iceberg |
| jobs PySpark | Amazon EMR / EMR Serverless | processamento distribuído |
| Airflow local | Amazon MWAA | orquestração gerenciada |
| configs locais | S3 + versionamento / Parameter Store | configuração |
| segredos locais | AWS Secrets Manager | credenciais e segredos |
| Streamlit Docker | Amazon ECS Fargate | aplicação web |
| imagens Docker | Amazon ECR | registry |
| logs locais | Amazon CloudWatch | logs, métricas e alarmes |
| controles de acesso ao data lake | IAM + Lake Formation | autorização e governança |
| criptografia local/volume | AWS KMS | chaves e criptografia |
| consultas ad hoc | Amazon Athena | exploração SQL sobre Iceberg |
| trilha de ações cloud | AWS CloudTrail | auditoria de API |

EMR é a opção mais natural para preservar o modelo PySpark existente. AWS Glue ETL também pode ser avaliado em uma implementação real; a decisão dependeria de padrões internos, custo, runtime suportado e operação da plataforma.

## 3. Arquitetura lógica

~~~text
           SISTEMAS CORPORATIVOS / IAM / IGA / HR
                         │
                         ▼
                 S3 Landing / Raw
                         │
                         ▼
               ┌─────────────────┐
               │   MWAA Airflow  │
               └────────┬────────┘
                        │ orquestra
                        ▼
               EMR / Spark Jobs
                        │
        ┌───────────────┼───────────────────────────┐
        ▼               ▼                           ▼
   S3 Bronze        S3 Silver              S3 Access Intelligence
        │               │                           │
        └───────────────┴──────────────┬────────────┘
                                       ▼
                                   S3 Gold
                                       │
                         Glue Data Catalog / Iceberg
                                       │
                ┌──────────────────────┼─────────────────────┐
                ▼                      ▼                     ▼
             Athena               ECS Fargate          Validation Mart
          consulta ad hoc          Streamlit             S3 separado
                                       │
                                      ALB
                                       │
                                OIDC / IdP corporativo

Observabilidade: CloudWatch
Auditoria: CloudTrail
Segurança: IAM + Lake Formation + KMS + Secrets Manager
CI/CD: GitHub Actions → ECR → ambientes AWS
~~~

## 4. Separação do data lake

Uma organização recomendada é separar zonas lógicas:

~~~text
s3://.../bronze/
s3://.../silver/
s3://.../access-intelligence/
s3://.../gold/
s3://.../validation/
s3://.../artifacts/
~~~

A separação mais importante é **runtime versus validation**. O papel usado pelos jobs de runtime não deve ter permissão de leitura sobre o gabarito de validação.

Essa restrição transforma a prevenção de leakage em controle técnico, não apenas convenção de código.

## 5. Orquestração com MWAA

O DAG atual pode ser preservado conceitualmente:

~~~text
validate
 → bronze
 → bronze_gate
 → silver
 → silver_gate
 → context_hts
 → baseline_fallback
 → expected_access
 → evidence
 → policy
 → risk
 → gold
 → gold_gate
 → register_run
 → trigger_validation
~~~

Em produção, cada tarefa pode disparar um job Spark gerenciado e monitorar seu término.

Gates devem impedir a propagação de dados incompletos para a próxima camada.

## 6. Iceberg + Glue Data Catalog

Apache Iceberg continua sendo útil porque oferece:

- snapshots;
- evolução de schema;
- leitura consistente;
- possibilidade de time travel;
- interoperabilidade entre Spark e mecanismos SQL.

O Glue Data Catalog substitui o catálogo local e permite que Spark e Athena encontrem as mesmas tabelas.

## 7. Dashboard

O Streamlit pode ser empacotado na imagem já existente e publicado em ECS Fargate.

Uma topologia simples:

~~~text
Usuário corporativo
       │
       ▼
Application Load Balancer
       │
 OIDC / IdP corporativo
       │
       ▼
ECS Fargate — Streamlit
       │
       ▼
Gold / consultas autorizadas
~~~

A interface continua read-only. Remediação real deveria ser integrada a um workflow de IAM/IGA ou ferramenta de tickets, não executada diretamente pela página sem governança.

## 8. Segurança

### IAM

Cada job recebe uma role de menor privilégio. Runtime, validação e dashboard não precisam compartilhar a mesma role.

### Lake Formation

Pode governar acesso a tabelas, domínios e colunas sensíveis do data lake.

### KMS

Buckets, logs e segredos devem usar criptografia gerenciada por chaves apropriadas ao ambiente.

### Secrets Manager

Credenciais e tokens não devem aparecer em variáveis versionadas no Git.

### Rede

MWAA, jobs de processamento e ECS podem operar em sub-redes privadas, com acesso controlado aos serviços necessários por endpoints privados quando aplicável.

## 9. Observabilidade e auditoria

CloudWatch deve concentrar:

- duração e status dos jobs;
- volume por camada;
- falhas de gates;
- taxa de REVISÃO;
- mudanças de distribuição;
- erros de leitura/escrita;
- saúde do dashboard.

CloudTrail complementa a observabilidade ao registrar operações na conta e acesso administrativo à infraestrutura.

## 10. CI/CD

Fluxo sugerido:

~~~text
GitHub
  │
  ├── lint/test
  ├── build imagens
  └── build documentação
        │
        ▼
       ECR
        │
        ▼
 ambiente dev
        │
        ▼
 validações
        │
        ▼
 homologação / produção
~~~

Infraestrutura produtiva deveria ser declarativa via IaC. Terraform, CDK ou CloudFormation podem cumprir esse papel conforme o padrão da organização.

## 11. Data Mesh como lente de governança

Data Mesh não é requisito do case e não é o motor de processamento.

Ele pode ser aplicado como modelo de ownership:

- domínio de identidade publica dados de identidade;
- IGA publica grants, requests e certificações;
- domínios de aplicações publicam metadados de criticidade e função;
- a plataforma SoD consome esses produtos por contratos.

A arquitetura Medallion resolve processamento. Data Mesh resolve principalmente **ownership, contratos e responsabilidade sobre os dados**. São conceitos complementares, não concorrentes.

## 12. O que permanece igual na nuvem

Migrar para AWS não muda as regras fundamentais:

- Expected Access continua não sendo autorização;
- Evidence continua separado de Policy;
- Risk continua posterior à decisão;
- Gold continua sem criar inteligência;
- validação continua isolada;
- experimentos continuam fora do runtime até aprovação.

Cloud é uma mudança de execução e operação, não uma desculpa para alterar a semântica do domínio.
