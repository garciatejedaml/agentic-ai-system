# Carson Tier 4 Fixes — Infraestructura y Observabilidad

**Repo**: `high-touch-agent-prompts`
**Fecha**: 2026-04-14
**Prerequisito**: Tier 1, 2, 3 aplicados

Tres mejoras de largo plazo: persistencia resiliente, observabilidad del routing, y validación de infraestructura AWS.

---

## FIX #15 — ChromaDB con persistencia S3

### Archivos
- `langgraph-system/config.yaml` — opciones S3
- `langgraph-system/carson_agents/rag/s3_persistence.py` (nuevo)
- `langgraph-system/carson_agents/rag/knowledge_base.py` — hook init/shutdown

### Problema actual
`persist_dir: "./carson_kb"` → ChromaDB persiste en directorio local del contenedor ECS.

**Implicaciones**:
- Container rebuild → pierde TODAS las embeddings → re-ingesta completa (costo: ~30 min + $$$ en embeddings)
- Multiple Carson instances no comparten estado
- No hay backup automático
- Si el volumen Fargate se corrompe → sin recovery

### Cambio propuesto

**Arquitectura: ChromaDB local + sync S3 al startup/shutdown + snapshots periódicos**

```
┌─────────────────┐         startup: pull latest
│  Carson Service │ ◄─────────────────────────── ┐
│   (Fargate)     │                              │
│                 │  shutdown: push if modified  │
│   ChromaDB      │ ───────────────────────────► │
│  ./carson_kb/   │                              │
└─────────────────┘                              │
                                                 ▼
                                      ┌──────────────────┐
                                      │   S3 Bucket      │
                                      │ carson-kb-ahtw/  │
                                      │   latest/        │
                                      │   snapshots/     │
                                      │     2026-04-14/  │
                                      └──────────────────┘
```

**Config**:
```yaml
rag:
  persist_dir: "./carson_kb"
  s3_backup:
    enabled: true
    bucket: "carson-kb-ahtw"
    prefix: "chroma/"
    sync_on_startup: true          # pull latest al arrancar
    sync_on_shutdown: true         # push si hubo cambios
    snapshot_interval_hours: 6     # snapshot cada 6h (backup incremental)
    snapshot_retention_days: 30    # mantener 30 días de snapshots
    aws_region: "us-east-1"
```

**Nuevo módulo**: `langgraph-system/carson_agents/rag/s3_persistence.py`

```python
"""S3-backed persistence for ChromaDB. Sync strategies: startup pull, shutdown push, periodic snapshots."""
import hashlib
import logging
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class ChromaS3Persistence:
    def __init__(self, persist_dir: Path, bucket: str, prefix: str = "chroma/", region: str = "us-east-1"):
        self.persist_dir = Path(persist_dir)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        self.s3 = boto3.client("s3", region_name=region)
        self._last_hash = None

    def _hash_dir(self) -> str:
        """Fast hash of the persist_dir to detect changes."""
        h = hashlib.sha256()
        for p in sorted(self.persist_dir.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(self.persist_dir).as_posix().encode())
                h.update(str(p.stat().st_mtime_ns).encode())
                h.update(str(p.stat().st_size).encode())
        return h.hexdigest()

    def _tar_and_upload(self, s3_key: str):
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            with tarfile.open(tmp.name, "w:gz") as tar:
                tar.add(self.persist_dir, arcname=self.persist_dir.name)
            self.s3.upload_file(tmp.name, self.bucket, s3_key)
            logger.info(f"Uploaded {self.persist_dir} to s3://{self.bucket}/{s3_key}")

    def _download_and_extract(self, s3_key: str) -> bool:
        try:
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                self.s3.download_file(self.bucket, s3_key, tmp.name)
                with tarfile.open(tmp.name, "r:gz") as tar:
                    tar.extractall(self.persist_dir.parent)
                logger.info(f"Restored {self.persist_dir} from s3://{self.bucket}/{s3_key}")
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.info(f"No existing backup at s3://{self.bucket}/{s3_key} — starting fresh")
                return False
            raise

    def sync_from_s3(self) -> bool:
        """Pull latest from S3 at startup. Returns True if restored."""
        return self._download_and_extract(f"{self.prefix}latest/carson_kb.tar.gz")

    def sync_to_s3(self, force: bool = False) -> bool:
        """Push to S3 if contents changed (or if force=True). Returns True if uploaded."""
        current_hash = self._hash_dir()
        if not force and current_hash == self._last_hash:
            logger.info("No changes detected — skipping S3 sync")
            return False
        self._tar_and_upload(f"{self.prefix}latest/carson_kb.tar.gz")
        self._last_hash = current_hash
        return True

    def snapshot(self):
        """Create a timestamped snapshot (for periodic backups)."""
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        self._tar_and_upload(f"{self.prefix}snapshots/{ts}/carson_kb.tar.gz")

    def cleanup_old_snapshots(self, retention_days: int):
        """Delete snapshots older than retention_days."""
        paginator = self.s3.get_paginator("list_objects_v2")
        cutoff = datetime.utcnow().timestamp() - retention_days * 86400
        to_delete = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{self.prefix}snapshots/"):
            for obj in page.get("Contents", []):
                if obj["LastModified"].timestamp() < cutoff:
                    to_delete.append({"Key": obj["Key"]})
        if to_delete:
            # S3 delete_objects limit: 1000 per request
            for i in range(0, len(to_delete), 1000):
                self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": to_delete[i:i+1000]})
            logger.info(f"Cleaned up {len(to_delete)} old snapshots")
```

**Hook en carson_service.py startup/shutdown**:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pull latest from S3
    if config["rag"]["s3_backup"]["enabled"]:
        s3 = ChromaS3Persistence(
            persist_dir=config["rag"]["persist_dir"],
            bucket=config["rag"]["s3_backup"]["bucket"],
            prefix=config["rag"]["s3_backup"]["prefix"],
            region=config["rag"]["s3_backup"]["aws_region"],
        )
        if config["rag"]["s3_backup"]["sync_on_startup"]:
            s3.sync_from_s3()
        app.state.chroma_s3 = s3

    yield

    # Shutdown: push if modified
    if config["rag"]["s3_backup"]["enabled"] and config["rag"]["s3_backup"]["sync_on_shutdown"]:
        app.state.chroma_s3.sync_to_s3()

app = FastAPI(lifespan=lifespan)
```

**Autonomous job para snapshots**: `autonomous_jobs/chroma_snapshot.py` corriendo cada 6h.

### Justificación
- **Resilience**: container rebuild → pull latest → recuperado en ~2 min en vez de re-ingestar todo.
- **Multi-instance**: future Carson instances pueden pullear del mismo S3.
- **Auditability**: snapshots timestamped permiten debugging ("hace 3 días estas queries funcionaban") y rollback si una ingesta malogra la DB.

### IAM permissions necesarios
El execution role de Carson ECS/Fargate necesita:
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject",
    "s3:ListBucket"
  ],
  "Resource": [
    "arn:aws:s3:::carson-kb-ahtw",
    "arn:aws:s3:::carson-kb-ahtw/*"
  ]
}
```

### Verificación
1. Crear bucket `carson-kb-ahtw`, dar permisos.
2. Primera vez: `sync_from_s3()` retorna False (404, fresh start) — OK.
3. Ingestar algunas colecciones, shutdown del servicio — debe subir a S3.
4. Container rebuild → startup → debe bajar de S3 y NO re-ingestar.

---

## FIX #16 — Logging de routing decisions

### Archivos
- `langgraph-system/carson_service.py` — hook de routing
- `langgraph-system/carson_agents/router.py` — emit structured logs

### Problema
El LLM router (Haiku 4.5) toma decisiones de routing pero **no se loguean**. Consecuencias:
- Cuando una query va al agente equivocado, no hay forma fácil de debuggear *por qué*.
- No hay métricas para saber si el router está confiado o dudando.
- Imposible detectar degradación del router over time.

### Cambio propuesto

**Agregar logging estructurado en el router**:

```python
import json
import logging

router_logger = logging.getLogger("carson.routing")

def route_query(query: str, available_agents: list[str]) -> RoutingDecision:
    # ... llamada al Haiku 4.5 ...
    decision = RoutingDecision(
        selected_agent=result["agent"],
        confidence=result["confidence"],       # 0.0-1.0
        reasoning=result["reasoning"],
        alternatives=result.get("alternatives", []),  # segunda/tercera opción
        latency_ms=latency_ms,
    )

    router_logger.info(json.dumps({
        "event": "routing_decision",
        "query": query[:500],                  # truncar queries largas
        "query_length": len(query),
        "selected_agent": decision.selected_agent,
        "confidence": decision.confidence,
        "alternatives": decision.alternatives,
        "reasoning": decision.reasoning,
        "latency_ms": decision.latency_ms,
        "available_agents_count": len(available_agents),
        "timestamp": datetime.utcnow().isoformat(),
    }))

    return decision
```

**Config para control de verbosity**:
```yaml
observability:
  routing_log:
    enabled: true
    level: "INFO"
    include_full_query: true           # false en prod si hay PII concern
    low_confidence_threshold: 0.6      # queries con confidence < 0.6 se marcan como "uncertain"
```

**Métricas derivadas** (para un dashboard):
- Routing decisions por agente (distribución)
- Confidence promedio por agente
- Tasa de "uncertain" routing (< 0.6) — señal de degradación
- Top 20 queries con confidence más baja (para mejora de .agent.md files)
- p50/p99 latency del routing

**Opción más robusta: Datadog/CloudWatch Logs Insights**. Si Datadog está integrado (ver FIX #1), agregar tag `carson:routing` a estos logs.

### Justificación
- **Debuggeable**: cuando alguien reporta "mi pregunta fue al agente equivocado", hay evidencia clara.
- **Detección de drift**: si el router empieza a fallar por cambios en .agent.md files o en el modelo base, las métricas avisan.
- **Input para mejora**: queries con confidence baja son candidatas directas para enriquecer la descripción del agente correspondiente.

### Verificación
Hacer 20 queries variadas, buscar en logs:
```
grep "routing_decision" carson.log | jq 'select(.confidence < 0.6)'
```
Debe mostrar las queries donde el router tuvo dudas.

---

## FIX #17 — Validar Bedrock inference profile ARNs

### Archivos
- Nuevo: `langgraph-system/scripts/validate_bedrock_config.py`
- `langgraph-system/carson_service.py` — validación al startup

### Problema
Config.yaml contiene 2 ARNs de Bedrock inference profiles:
- `routing_model_arn` → Haiku 4.5 (profile `k4yvmctvgxzy`)
- `embedding_model_arn` → probablemente Titan o Cohere

**Sin validación al startup**, si los ARNs están mal, Carson arranca "OK" pero la primera query falla con un error oscuro.

### Cambio propuesto

**Script standalone**: `langgraph-system/scripts/validate_bedrock_config.py`

```python
"""Validate all Bedrock ARNs in config.yaml actually exist and are accessible."""
import sys
import boto3
import yaml
from pathlib import Path
from botocore.exceptions import ClientError

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def main():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    region = config.get("aws", {}).get("region", "us-east-1")
    bedrock = boto3.client("bedrock", region_name=region)

    arns_to_check = [
        ("llm.routing_model_arn", config["llm"].get("routing_model_arn")),
        ("llm.embedding_model_arn", config["llm"].get("embedding_model_arn")),
    ]

    # main_model: resolve to model ID, check via list_foundation_models
    main_model = config["llm"].get("main_model")
    errors = []

    # 1) Check inference profiles
    for name, arn in arns_to_check:
        if not arn:
            errors.append(f"{name}: MISSING in config.yaml")
            continue
        profile_id = arn.split("/")[-1]
        try:
            response = bedrock.get_inference_profile(inferenceProfileIdentifier=profile_id)
            status = response.get("status")
            if status != "ACTIVE":
                errors.append(f"{name}: inference profile status is {status} (expected ACTIVE)")
            else:
                print(f"✓ {name}: ACTIVE ({response.get('inferenceProfileName')})")
        except ClientError as e:
            errors.append(f"{name}: {e.response['Error']['Code']} — {e.response['Error']['Message']}")

    # 2) Check main_model availability
    if main_model:
        try:
            bedrock.get_foundation_model(modelIdentifier=main_model)
            print(f"✓ main_model: available ({main_model})")
        except ClientError as e:
            errors.append(f"llm.main_model: {e.response['Error']['Code']} — {main_model}")

    # 3) Check role_arn (iam.get_role requires IAM read permission)
    role_arn = config.get("aws", {}).get("role_arn")
    if role_arn:
        iam = boto3.client("iam")
        role_name = role_arn.split("/")[-1]
        try:
            iam.get_role(RoleName=role_name)
            print(f"✓ aws.role_arn: exists ({role_name})")
        except ClientError as e:
            errors.append(f"aws.role_arn: {e.response['Error']['Code']} — {role_arn}")

    if errors:
        print("\n=== VALIDATION FAILED ===")
        for err in errors:
            print(f"  ✗ {err}")
        sys.exit(1)

    print("\n=== ALL BEDROCK CONFIG VALIDATED ===")

if __name__ == "__main__":
    main()
```

**Integración al startup de carson_service.py** (opcional, con flag):

```yaml
# En config.yaml
service:
  validate_aws_config_on_startup: true   # corre la validación al arrancar
```

```python
# En carson_service.py
if config["service"].get("validate_aws_config_on_startup"):
    from scripts.validate_bedrock_config import main as validate_bedrock
    try:
        validate_bedrock()
    except SystemExit:
        logger.critical("AWS config validation failed — refusing to start")
        raise
```

### Justificación
- **Fail-fast**: errores de configuración se detectan al deploy, no cuando llega la primera query a producción.
- **Script standalone**: útil como pre-commit check o como paso en el pipeline de Spinnaker antes del deploy.
- **Cobertura amplia**: valida ARNs + rol IAM + availability del modelo — los 3 puntos más comunes de falla.

### Verificación
1. Correr con config actual: debe mostrar 3+ checkmarks verdes.
2. Romper a propósito un ARN (cambiar una letra): debe fallar con mensaje claro.
3. Integrar en Jules pipeline como paso pre-deploy.

---

## Orden de aplicación

1. **FIX #17** (validate bedrock) — independiente, bajo riesgo, ~30 min
2. **FIX #16** (routing logging) — hook en router.py, requiere que Datadog esté listo idealmente (ver FIX #1)
3. **FIX #15** (S3 persistence) — **el más grande** — requiere bucket S3 + IAM + testing cuidadoso; aplicar último

---

## Resumen del journey completo (Tier 1 → Tier 4)

| Tier | Fixes | Riesgo | Tiempo estimado | Impacto |
|---|---|---|---|---|
| **Tier 1** | 5 fixes (bugs) | Bajo | 1-2 horas | Alto — bugs concretos resueltos |
| **Tier 2** | 4 fixes (consistencia) | Bajo-Medio | 2-3 horas | Medio-Alto — mantenibilidad, onboarding |
| **Tier 3** | 5 fixes (funcionalidad) | Medio | 1 día | Alto — calidad de respuestas, observabilidad |
| **Tier 4** | 3 fixes (infraestructura) | Medio-Alto | 2-3 días | Muy Alto — resilience y debugging |

**Total: 17 mejoras concretas documentadas** con patches listos para aplicar.
