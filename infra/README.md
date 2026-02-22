# AWS Infrastructure — Agentic AI System

Terraform para deployar el sistema en AWS usando **ECS Fargate** + **Amazon Bedrock**.

## Arquitectura

```
Internet
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  ALB (port 80 → 443 cuando se agrega cert ACM)         │
│  POST /v1/chat/completions  (compatible OpenAI)         │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  ECS Fargate — agentic-ai-api  (private subnet)         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  LangGraph workflow (control plane)              │   │
│  │  Strands Financial Orchestrator (data plane)     │   │
│  │  MCP servers como subprocesos (stdio)            │   │
│  └─────────────────────────────────────────────────┘   │
└───────────────┬─────────────────────────────────────────┘
                │ IAM auth (no API keys)
                ▼
         Amazon Bedrock
         (Claude Sonnet + Haiku)
```

## Archivos Terraform

| Archivo | Recursos |
|---------|---------|
| `main.tf` | Provider AWS, backend S3 (comentado) |
| `variables.tf` | Todas las variables de input |
| `locals.tf` | Valores computados (name_prefix, model IDs) |
| `outputs.tf` | Outputs (ALB DNS, ECR URL, etc.) |
| `networking.tf` | VPC, subnets public/private/isolated, NAT, security groups |
| `vpc_endpoints.tf` | VPC Endpoints para Bedrock, ECR, SQS, Secrets Manager, CloudWatch, S3 |
| `ecr.tf` | Repositorio ECR con lifecycle policy |
| `iam.tf` | Task role (Bedrock + SQS + DynamoDB) + Execution role |
| `data.tf` | Aurora Serverless v2 (pgvector), DynamoDB, SQS, Secrets Manager |
| `ecs.tf` | ECS Cluster, Task Definition, Fargate Service |
| `alb.tf` | Application Load Balancer, Target Group, Listener |
| `autoscaling.tf` | Auto-scaling por CPU y memoria (1–4 tasks) |

## Prerequisitos

```bash
# Terraform 1.5+
terraform --version

# AWS CLI configurado
aws configure
aws sts get-caller-identity  # verificar acceso

# Docker (para build y push de imagen)
docker --version
```

## Deploy paso a paso

### 1. Preparar variables

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars con tus valores
```

### 2. (Opcional) Configurar remote state

```bash
# Crear S3 bucket para state
aws s3 mb s3://my-tf-state-bucket --region us-east-1

# Crear tabla DynamoDB para locks
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

# Descomentar el bloque backend "s3" en main.tf y completar con los valores
```

### 3. Init y plan

```bash
terraform init
terraform plan -out=tfplan
# Revisar el plan antes de aplicar
```

### 4. Crear infraestructura (sin imagen aún)

```bash
terraform apply tfplan
```

Esto crea todo excepto el ECS service con imagen real (usará `latest` por ahora).

### 5. Build y push de la imagen Docker

```bash
# Obtener el ECR URL del output
ECR_URL=$(terraform output -raw ecr_api_repository_url)
IMAGE_TAG=$(git rev-parse --short HEAD)

# Login a ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ${ECR_URL%/*}

# Build desde la raíz del proyecto
cd ..
docker build -t ${ECR_URL}:${IMAGE_TAG} .
docker tag ${ECR_URL}:${IMAGE_TAG} ${ECR_URL}:latest
docker push ${ECR_URL}:${IMAGE_TAG}
docker push ${ECR_URL}:latest
cd infra
```

### 6. Re-deploy con la imagen correcta

```bash
TF_VAR_image_tag=${IMAGE_TAG} terraform apply -auto-approve
```

### 7. Cargar secrets

```bash
SECRET_ARN=$(terraform output -raw app_secret_arn)

aws secretsmanager put-secret-value \
  --secret-id ${SECRET_ARN} \
  --secret-string '{
    "ANTHROPIC_API_KEY": "sk-ant-XXXXXX",
    "BRAVE_API_KEY": "BSA-XXXXXX",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-XXXXXX",
    "LANGFUSE_SECRET_KEY": "sk-lf-XXXXXX"
  }'
```

### 8. Forzar re-deploy del ECS service para que levante los secrets

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
SERVICE=$(terraform output -raw ecs_service_name)

aws ecs update-service \
  --cluster ${CLUSTER} \
  --service ${SERVICE} \
  --force-new-deployment
```

### 9. Verificar

```bash
ALB=$(terraform output -raw alb_dns_name)

# Health check
curl -s http://${ALB}/

# Test query
curl -s http://${ALB}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Who are the top HY traders?"}]}'
```

## Habilitar pgvector en Aurora (una sola vez)

```bash
# Obtener credenciales de Aurora
aws secretsmanager get-secret-value \
  --secret-id /agentic-ai-staging/aurora/credentials \
  --query SecretString --output text | jq .

# Conectar y habilitar extensión
psql -h $(terraform output -raw aurora_endpoint) \
     -U agenticai -d agenticai \
     -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## Estimación de costos (staging, 1 task 24/7)

| Recurso | $/mes aprox |
|---------|------------|
| ECS Fargate (1 vCPU, 2 GB) | ~$30 |
| ALB | ~$20 |
| NAT Gateway | ~$35 |
| VPC Endpoints (7 interface) | ~$50 |
| Aurora Serverless v2 (0.5 ACU, auto-pauses) | ~$5–15 |
| CloudWatch Logs | ~$2 |
| **Total** | **~$140–155** |

> Para reducir costos en staging: comentar los VPC endpoints en `vpc_endpoints.tf`
> (el tráfico irá por NAT, ~$35/mes extra pero sin el costo fijo de endpoints),
> poner `desired_count = 0` cuando no se usa, y activar `auto_pause` en Aurora.

## Destruir la infraestructura

```bash
# CUIDADO: esto destruye TODO incluyendo la base de datos
terraform destroy

# Si Aurora tiene deletion_protection=true, primero:
terraform apply -var="aurora_deletion_protection=false"
terraform destroy
```

## CI/CD (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write  # for OIDC auth
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::ACCOUNT_ID:role/github-actions-deploy
          aws-region: us-east-1

      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG .
          docker push $ECR_REGISTRY/agentic-ai-staging-api:$IMAGE_TAG

      - name: Terraform deploy
        working-directory: infra
        env:
          TF_VAR_image_tag: ${{ github.sha }}
        run: |
          terraform init
          terraform apply -auto-approve
```
