# Carson Tier 1 Fixes — `high-touch-agent-prompts`

**Repo**: `high-touch-agent-prompts`
**Branch**: (current feature branch — verify via VDI)
**Fecha**: 2026-04-14
**Base**: Findings de Appendix A–I en `CARSON_SELF_IMPROVEMENT_PROMPT.md`

Cinco fixes concretos, alto impacto, listos para aplicar. Cada uno incluye: ubicación, estado actual, cambio propuesto, y justificación.

---

## FIX #1 — Rocky/Datadog agent invisible para el router

### Archivo
`langgraph-system/config.yaml` — sección `agents:` (línea ~103)

### Problema
El agente Rocky (Datadog) existe como `.agent.md` y está en el inventario (Appendix B), pero **no está declarado en `config.yaml`**. Resultado: el LLM router nunca lo incluye como candidato de routing. Cualquier consulta sobre métricas Datadog cae en `general` o se pierde.

### Estado actual (config.yaml, sección agents)
```yaml
agents:
  jira:
    enabled: true
  git:
    enabled: true
  build:
    enabled: true
  deploy:
    enabled: true
  terraform:
    enabled: true
  terraform_compat:
    enabled: true
  docs:
    enabled: true
  general:
    enabled: true
  amps:
    enabled: true
  snow:
    enabled: true
  postman:
    enabled: true
  picasso:
    enabled: true

  # Knowledge-only agents (no MCP tools)
  bob:
    enabled: true
  hydra:
    enabled: true
  cbb:
    enabled: true
  pixie:
    enabled: true
  studio:
    enabled: true
  sdlc:
    enabled: true
```

### Cambio propuesto
Agregar `datadog`, y también `gossip` y `teams` si son agentes routables (el Appendix B los lista como agentes en el inventario pero están deshabilitados implícitamente):

```yaml
  # Observability / operational agents
  datadog:
    enabled: true        # Rocky — Datadog metrics & alerts
  gossip:
    enabled: false       # TODO: confirmar si se va a usar; dejar disabled por ahora
  teams:
    enabled: false       # TODO: confirmar si MS Teams agent está listo
```

Agregar el bloque antes de la sección "Knowledge-only agents".

### Justificación
- **Sin esto**: Rocky es código muerto. El router de Haiku 4.5 no lo ve como opción y cualquier pregunta sobre Datadog se responde mal.
- **`enabled: false` explícito** para gossip/teams es mejor que "no existe en config" porque documenta intención.

### Verificación post-fix
Ejecutar una query de routing de prueba tipo "check the latency metrics for the AHTW service" y confirmar que el router selecciona `datadog` en lugar de `general`.

---

## FIX #2 — `.hcl` faltante en extensiones de `repo_code` RAG

### Archivo
`langgraph-system/config.yaml` — sección `rag:` → `team_collections:` → `repo_code:` (línea ~149)

### Problema
El filtro de extensiones para ingesta de código de repos NO incluye `.hcl`. Cualquier archivo HashiCorp Configuration Language (HCL) — que es el lenguaje nativo de Terraform para muchos módulos y para Sentinel — **no se indexa**. Resultado: queries sobre HCL/Sentinel devuelven "no encontrado" aunque los archivos existan en el repo.

### Estado actual (aprox. línea 149)
```yaml
      repo_code:
        source: team_repos
        extensions: [".py", ".md", ".yaml", ".yml", ".xml", ".tf", ".json"]
```

### Cambio propuesto
```yaml
      repo_code:
        source: team_repos
        extensions: [".py", ".md", ".yaml", ".yml", ".xml", ".tf", ".tfvars", ".hcl", ".json"]
```

Agrego también `.tfvars` por consistencia — es el otro archivo clave del ecosistema Terraform.

### Justificación
- **Cobertura real**: Muchos módulos terraform usan `.hcl` para variables, backend config, o Sentinel policies.
- **Consistencia**: Si ya tomamos `.tf`, tomar `.hcl` y `.tfvars` es coherente.
- **Costo bajo**: Son archivos de texto chicos, no inflan la DB.

### Verificación post-fix
Re-ingestar el repo con `python -m carson_agents.kb_auto_ingest` y validar que aparecen docs `.hcl` en la colección `repo_code`:
```python
kb._get_client().get_collection("repo_code_ahtw").get(where={"extension": ".hcl"})
```

---

## FIX #3 — Error handling en `send_carson_reply.py`

### Archivo
`langgraph-system/send_carson_reply.py` (o la ruta exacta que uses)

### Problema
Las llamadas a `OutlookCOMClient()` y `client.send_email()` **no tienen try/except**. Si COM falla (Outlook cerrado, VDI desconectado, permisos), el script crashea con stacktrace sin contexto. Peor: Copilot puede recibir `False` silencioso sin saber qué falló.

### Estado actual (simplificado)
```python
def send_reply(session_id, topic, response, user_email=None):
    to_address = user_email or "martin.garciatejeda@jpmchase.com"
    subject = f"[Carson:{session_id}] Re: {topic}"
    body = f"🤖 Carson AI Butler\n\n{response}\n\n---\nSession: {session_id}\nTime: {datetime.now()}\nSent via Carson (Copilot Mode)"

    client = OutlookCOMClient()
    result = client.send_email(to_address, subject, body, is_html=False)
    return result
```

### Cambio propuesto
```python
import logging

logger = logging.getLogger(__name__)

def send_reply(session_id, topic, response, user_email=None):
    """Send a Carson reply via Outlook COM. Returns True/False for success."""
    to_address = user_email or DEFAULT_REPLY_EMAIL  # see FIX #5
    subject = f"[Carson:{session_id}] Re: {topic}"
    body = (
        f"🤖 Carson AI Butler\n\n"
        f"{response}\n\n"
        f"---\n"
        f"Session: {session_id}\n"
        f"Time: {datetime.now()}\n"
        f"Sent via Carson (Copilot Mode)"
    )

    try:
        client = OutlookCOMClient()
    except Exception as e:
        logger.error(f"Failed to initialize OutlookCOMClient for session {session_id}: {e}")
        return False

    try:
        result = client.send_email(to_address, subject, body, is_html=False)
        if not result:
            logger.warning(f"send_email returned falsy for session {session_id} to {to_address}")
        return bool(result)
    except Exception as e:
        logger.error(
            f"Outlook send_email failed for session {session_id}, "
            f"to={to_address}, subject={subject!r}: {e}"
        )
        return False
```

### Justificación
- **Visibilidad**: Copilot ahora recibe `False` con log asociado para debug.
- **Dos try/except separados**: distingue "COM no inicializa" de "email no se envía" para diagnóstico.
- **No cambia la interfaz**: `send_reply()` sigue devolviendo `bool` — retrocompat completo.

### Verificación post-fix
Correr con Outlook cerrado y confirmar que:
1. No crashea
2. Log muestra "Failed to initialize OutlookCOMClient"
3. Retorna `False`

---

## FIX #4 — `fix_chromadb.py` pasa `config={}` y bypasa config.yaml

### Archivo
`langgraph-system/fix_chromadb.py`

### Problema
El script instancia `CarsonKnowledgeBase(persist_dir="./carson_kb", config={})`. El `config={}` vacío significa que:
- Las definiciones de colecciones en `config.yaml` no se cargan
- El `health_check()` puede reportar "healthy" colecciones que en runtime el servicio considera broken
- El `repair_broken_collections()` puede eliminar colecciones que en realidad están bien configuradas

### Estado actual (aprox.)
```python
from carson_agents.rag.knowledge_base import CarsonKnowledgeBase

def main(dry_run=False):
    kb = CarsonKnowledgeBase(persist_dir="./carson_kb", config={})
    result = kb.health_check()
    # ...
```

### Cambio propuesto
```python
import yaml
from pathlib import Path
from carson_agents.rag.knowledge_base import CarsonKnowledgeBase

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_runtime_config() -> dict:
    """Load config.yaml using the same path resolution as carson_service."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config.yaml not found at {CONFIG_PATH}. "
            f"Run this script from the langgraph-system directory."
        )
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def main(dry_run=False):
    config = load_runtime_config()
    persist_dir = config.get("rag", {}).get("persist_dir", "./carson_kb")
    kb = CarsonKnowledgeBase(persist_dir=persist_dir, config=config)
    result = kb.health_check()
    # ...
```

### Justificación
- **Consistencia con runtime**: health_check ahora evalúa las mismas colecciones que usa el servicio en producción.
- **persist_dir también viene del config**: si el equipo cambia `./carson_kb` a otro path, `fix_chromadb.py` lo sigue automáticamente.
- **Error claro si se corre desde el directorio equivocado**: el `FileNotFoundError` explícito es mejor que un bug silencioso.

### Verificación post-fix
Correr `python fix_chromadb.py --dry` y confirmar que lista las 7 colecciones (4 global + 3 team) definidas en config.yaml, no solo las que ChromaDB reporta físicamente.

---

## FIX #5 — Email hardcoded → config.yaml

### Archivos
- `langgraph-system/config.yaml` (agregar entrada)
- `langgraph-system/send_carson_reply.py` (leer de config)

### Problema
`send_carson_reply.py` tiene hardcoded `martin.garciatejeda@jpmchase.com` como default. Al onboardear un nuevo usuario o transferir a otra persona del equipo, **hay que editar el código**. Esto rompe la idea de que config.yaml es el único punto de cambio.

### Cambios propuestos

**En `config.yaml` — agregar bajo `service:` o crear nueva sección `notifications:`**

```yaml
notifications:
  # Email fallback cuando el caller no pasa user_email explícito
  default_reply_email: "martin.garciatejeda@jpmchase.com"
  # Formato del subject: {session_id} y {topic} son placeholders
  reply_subject_format: "[Carson:{session_id}] Re: {topic}"
  # Signature footer
  reply_footer: "Sent via Carson (Copilot Mode)"
```

**En `send_carson_reply.py`:**

```python
import yaml
from pathlib import Path

_CONFIG_CACHE = None

def _load_config() -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        config_path = Path(__file__).parent / "config.yaml"
        with open(config_path, "r") as f:
            _CONFIG_CACHE = yaml.safe_load(f)
    return _CONFIG_CACHE

def _get_default_email() -> str:
    cfg = _load_config()
    notif = cfg.get("notifications", {})
    email = notif.get("default_reply_email")
    if not email:
        raise ValueError(
            "notifications.default_reply_email not set in config.yaml "
            "and no user_email provided to send_reply()"
        )
    return email

def send_reply(session_id, topic, response, user_email=None):
    to_address = user_email or _get_default_email()
    # ... resto igual (con el try/except del FIX #3) ...
```

### Justificación
- **Config-driven**: onboardear nuevo usuario = cambiar una línea en config.yaml, no en código.
- **Fail-fast**: si `default_reply_email` no está y nadie pasó `user_email`, errorea con mensaje claro en vez de mandar a un email aleatorio o crashear en Outlook.
- **Cache de config**: leer config.yaml una sola vez por proceso es suficiente — no hay razón para leerlo en cada `send_reply()`.
- **Extensible**: `reply_subject_format` y `reply_footer` siguen el mismo patrón, dejando flexibilidad para rebranding.

### Verificación post-fix
1. Borrar/comentar `default_reply_email` de config.yaml y correr sin `user_email` → debe fallar con `ValueError` claro.
2. Restaurar y correr con `user_email` explícito → debe usar el explícito.
3. Restaurar y correr sin `user_email` → debe usar el de config.

---

## Orden de aplicación sugerido

1. **FIX #1** (config.yaml, datadog) — 2 min, cero riesgo, alto valor
2. **FIX #2** (config.yaml, .hcl + .tfvars) — 2 min + re-ingesta (~10 min según tamaño del repo)
3. **FIX #5** (email a config) — primero este porque FIX #3 lo asume
4. **FIX #3** (error handling send_carson_reply) — depende de FIX #5
5. **FIX #4** (fix_chromadb load config) — independiente, puede ir al final

**Todos los fixes son de bajo riesgo** y ninguno requiere redeployment de infraestructura. Solo cambio de código + restart del servicio (o ni siquiera, para los que son solo config.yaml si hay hot-reload).

---

## Lo que NO está incluido acá (intencionalmente)

Estos son fixes posteriores, no Tier 1:
- Tiering de modelos (Sonnet 4 upgrade)
- `critique_mode: "always"` para tool agents
- `max_rag_context_tokens: 4000`
- `operation_model` RAG collection
- ChromaDB S3 persistence

Si los 5 Tier 1 funcionan bien, seguimos con Tier 2.
