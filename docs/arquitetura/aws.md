# Arquitetura alvo na AWS

## 1. Princípio

A migração para AWS não deve mudar a semântica da solução. Ela deve mudar **como a plataforma executa, escala, protege e observa** seus componentes.

Esta página descreve arquitetura-alvo, não infraestrutura já implantada.

## 2. Escolha principal para processamento: EMR Serverless

A implementação atual é PySpark batch orientado por DAG.

Para esse perfil, a opção principal proposta é **Amazon EMR Serverless**.

Motivos:

- preserva Spark/PySpark;
- não exige cluster permanentemente ligado;
- encaixa bem em jobs disparados pelo Airflow;
- permite escalar por workload;
- reduz gestão de nós para uma POC evoluindo a plataforma.

EMR em cluster continua sendo alternativa quando houver necessidade de workloads persistentes, controle mais fino de infraestrutura ou tuning específico.

AWS Glue ETL também é alternativa possível, mas não é o alvo principal desta proposta.

## 3. Mapeamento

| Atual | AWS alvo | Função |
|---|---|---|
| data/raw | S3 Landing | ingestão |
| Iceberg warehouse | S3 | armazenamento |
| catálogo local | Glue Data Catalog | catálogo |
| PySpark | EMR Serverless | processamento |
| Airflow local | MWAA | orquestração |
| Docker Streamlit | ECS Fargate | dashboard |
| imagens | ECR | registry |
| logs | CloudWatch | observabilidade |
| segredos | Secrets Manager | credenciais |
| autorização data lake | IAM + Lake Formation | governança |
| criptografia | KMS | proteção |
| consulta ad hoc | Athena | exploração |
| auditoria cloud | CloudTrail | trilha administrativa |

## 4. Arquitetura

```mermaid
flowchart LR
    A["Fontes corporativas<br/>IAM · IGA · RH · aplicações"] --> B["Amazon S3<br/>Landing"]
    B --> C["Amazon MWAA<br/>Orquestração"]
    C --> D["EMR Serverless<br/>PySpark"]

    D --> E["S3 + Iceberg<br/>Bronze"]
    E --> F["S3 + Iceberg<br/>Silver"]
    F --> G["S3 + Iceberg<br/>Access Intelligence"]
    G --> H["S3 + Iceberg<br/>Gold"]

    H --> I["Glue Data Catalog"]
    I --> J["Athena"]
    I --> K["ECS Fargate<br/>Streamlit"]
    H --> L["Validation Mart<br/>isolado"]

    M["CloudWatch"] -. logs · métricas · alarmes .-> C
    M -. observa .-> D
    M -. observa .-> K
    N["IAM + Lake Formation + KMS + Secrets Manager"] -. protege .-> B
    N -. protege .-> D
    N -. protege .-> H
```

## 5. Ambientes

Produção bancária não deve compartilhar estado entre desenvolvimento, homologação e produção.

Arquitetura recomendada:

<div class="sod-mini-flow sod-mini-flow--3">
  <div><strong>1</strong><span>DEV</span></div>
  <div><strong>2</strong><span>HML · promoção controlada</span></div>
  <div><strong>3</strong><span>PRD · aprovação</span></div>
</div>

Cada ambiente deve possuir:

- buckets próprios;
- catálogo próprio;
- roles próprias;
- secrets próprios;
- logs próprios;
- parâmetros próprios.

## 6. Isolamento do Validation Mart

Uma das fronteiras mais importantes é runtime versus validação.

O role usado pelo runtime não deve ter acesso ao ground truth.

<div class="sod-lane-grid sod-lane-grid--2">
  <div class="sod-lane"><span class="sod-kicker">Runtime role</span><h3>Produção da decisão</h3><p>Lê Bronze/Silver e escreve Intelligence/Gold. Não recebe permissão para ler o ground truth.</p></div>
  <div class="sod-lane"><span class="sod-kicker">Validation role</span><h3>Avaliação posterior</h3><p>Lê a Gold congelada e o ground truth exclusivamente para medir a execução.</p></div>
</div>

Isso transforma prevenção de leakage em controle de infraestrutura.

## 7. Rede

MWAA, EMR Serverless e ECS devem operar em rede controlada.

Quando aplicável:

- sub-redes privadas;
- security groups restritivos;
- endpoints privados;
- S3 sem exposição pública;
- acesso corporativo autenticado ao dashboard.

## 8. Segurança e governança

### IAM

Roles distintas para:

- runtime;
- validation;
- dashboard;
- CI/CD.

### Lake Formation

Permissões de tabela/coluna para separar consumo operacional, validação e exploração.

### KMS

Criptografia para S3, logs e demais recursos persistentes.

### Secrets Manager

Nenhum segredo deve depender de arquivo versionado no Git.

## 9. Observabilidade na AWS

CloudWatch centraliza:

- status e duração dos jobs;
- falha de gates;
- volume por estágio;
- taxa de revisão;
- distribuição de Policy;
- métricas de fallback;
- saúde do dashboard.

CloudTrail complementa com auditoria administrativa.

Os snapshots Iceberg continuam sendo parte da rastreabilidade de dados.

## 10. CI/CD

<div class="sod-mini-flow sod-mini-flow--5">
  <div><strong>1</strong><span>GitHub</span></div>
  <div><strong>2</strong><span>testes / validações</span></div>
  <div><strong>3</strong><span>build + ECR</span></div>
  <div><strong>4</strong><span>DEV / HML</span></div>
  <div><strong>5</strong><span>PRD</span></div>
</div>

A infraestrutura deveria ser declarada em IaC conforme padrão organizacional, por exemplo Terraform, CDK ou CloudFormation.

## 11. Data Mesh

Data Mesh é tratado como lente de ownership, não como motor do pipeline.

Exemplo:

- domínio de Identidade publica identidade;
- IGA publica grants/requests/certificações;
- domínio de aplicações publica criticidade e função;
- SoD consome esses contratos.

Medallion organiza processamento. Data Mesh organiza responsabilidade.

## 12. O que não muda ao ir para cloud

Mesmo na AWS:

- frequência continua não sendo autorização;
- Evidence continua separado de Policy;
- Risk continua posterior à decisão;
- Gold continua sem criar inteligência;
- Validation continua isolada;
- shadow experiments continuam fora do runtime.

Cloud aumenta capacidade operacional. Não substitui disciplina de decisão.
