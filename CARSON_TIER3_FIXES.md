# Carson Tier 3 Fixes — Mejoras de Funcionalidad

**Repo**: `high-touch-agent-prompts`
**Fecha**: 2026-04-14
**Prerequisito**: Tier 1 y Tier 2 aplicados

Cinco mejoras funcionales. Más trabajo que Tier 1/2 pero con impacto directo en calidad de respuestas y observabilidad.

---

## FIX #10 — Subir `max_rag_context_tokens` de 2000 a 4000

### Archivo
`langgraph-system/config.yaml` — sección `performance:` (línea ~180)

### Problema
`max_rag_context_tokens: 2000` es muy conservador. Queries complejas de terraform que necesitan múltiples module docs + ejemplos de uso + docs de compatibilidad fácilmente exceden los 2K tokens de contexto RAG.

### Evidencia
Para una query típica como *"Cómo usar el módulo ATLAS de VPC con el módulo de IAM boundaries?"* el RAG ideal devuelve:
- `modules/vpc/README.md` (~800 tokens)
- `modules/iam-boundaries/README.md` (~600 tokens)
- `bundle_matrix` compatibility notes (~400 tokens)
- Ejemplo de uso conjunto (~500 tokens)
- **Total: ~2300 tokens** → ya pasa el límite de 2000

Con el límite actual, el retriever trunca arbitrariamente y la respuesta queda coja.

### Cambio propuesto
```yaml
performance:
  # ...
  max_rag_context_tokens: 4000   # subido de 2000 — queries TF complejas necesitan más contexto
```

### Justificación
- Sonnet 3.5 tiene 200K context window. 4000 tokens de RAG usan 2% del window — sobra.
- Prompt caching (`enable_prompt_caching: true`) amortiza el costo del contexto extra.
- **Costo marginal**: ~2x el costo por query pero solo en la parte de input tokens (barato), no en output.

### Verificación
Correr 10 queries complejas de terraform antes/después y medir:
- `quality_score` promedio (debe subir)
- Latency (puede subir levemente, tolerable si sigue bajo 120s)
- Si Carson reporta "no encontré info sobre X" aunque X esté en RAG — debería reducirse

---

## FIX #11 — Crear colección RAG `operation_model`

### Archivos
- `langgraph-system/config.yaml` (agregar collection)
- `langgraph-system/scripts/ingest_operation_model.py` (nuevo, o ejecutar `kb_auto_ingest`)

### Problema
En `config.yaml` hay definida la página de Confluence `operation_model` (Confluence page 2538506858) pero **no hay colección RAG** que la ingeste. Resultado: Carson no puede responder preguntas sobre el operating model del equipo.

### Cambio propuesto

**Agregar en `config.yaml`** bajo `rag.team_collections:`:

```yaml
rag:
  team_collections:
    # ... existentes ...
    operation_model:
      description: "Operating Model (team ops & processes)"
      source: confluence
      page_id: "2538506858"
      refresh_interval_hours: 24    # ver FIX #12
```

**Ejecutar ingesta inicial**:
```bash
cd langgraph-system/
python -m carson_agents.kb_auto_ingest --collection operation_model
```

### Justificación
- **Cierra gap de conocimiento**: queries sobre "quién es el owner de X?", "qué proceso seguimos para Y?" antes no tenían respuesta, ahora sí.
- **Consistencia con config**: si la página está en `confluence_pages`, debe tener una colección asociada (o removerse de confluence_pages).

### Verificación
```python
kb._get_client().get_collection("operation_model_ahtw").count()
# Debe devolver > 0
```

---

## FIX #12 — Auto-refresh RAG (mecanismo de staleness)

### Archivos
- `langgraph-system/config.yaml` (agregar refresh intervals)
- `langgraph-system/autonomous_jobs/rag_refresh.py` (nuevo)

### Problema
ChromaDB se ingesta **manualmente** (corriendo `kb_auto_ingest`). Sin auto-refresh:
- Docs de Confluence quedan desactualizados
- Nuevos commits en repos no se indexan hasta que alguien corre re-ingest
- **No hay manera de saber cuán stale está cada colección**

### Cambio propuesto

**Agregar timestamps y intervals en config.yaml**:
```yaml
rag:
  # ...
  refresh:
    enabled: true
    default_interval_hours: 24    # refresh diario por default
    staleness_warning_hours: 48   # warning si no refresh en 48h

  global_collections:
    modules:
      refresh_interval_hours: 168   # weekly — modules cambian poco
    engineers_docs:
      refresh_interval_hours: 168

  team_collections:
    repo_code:
      refresh_interval_hours: 6     # cada 6h — código cambia seguido
    ahtw_confluence:
      refresh_interval_hours: 24    # daily
```

**Nuevo script**: `langgraph-system/autonomous_jobs/rag_refresh.py`

```python
"""
Autonomous job: refresh RAG collections based on per-collection schedule.
Run via cron/Spinnaker every hour:
    python -m autonomous_jobs.rag_refresh
"""
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from carson_agents.rag.knowledge_base import CarsonKnowledgeBase
from carson_agents.kb_auto_ingest import ingest_collection

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
LAST_REFRESH_FILE = Path("./carson_kb") / ".last_refresh.yaml"

def load_last_refresh() -> dict:
    if not LAST_REFRESH_FILE.exists():
        return {}
    with open(LAST_REFRESH_FILE) as f:
        return yaml.safe_load(f) or {}

def save_last_refresh(state: dict):
    LAST_REFRESH_FILE.parent.mkdir(exist_ok=True)
    with open(LAST_REFRESH_FILE, "w") as f:
        yaml.safe_dump(state, f)

def needs_refresh(name: str, interval_hours: int, last_refresh_state: dict) -> bool:
    last = last_refresh_state.get(name)
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    return datetime.utcnow() - last_dt > timedelta(hours=interval_hours)

def main():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    if not config.get("rag", {}).get("refresh", {}).get("enabled", False):
        logger.info("RAG auto-refresh disabled in config")
        return

    state = load_last_refresh()
    default_interval = config["rag"]["refresh"].get("default_interval_hours", 24)
    refreshed = []

    for section in ("global_collections", "team_collections"):
        for name, coll_cfg in config["rag"].get(section, {}).items():
            interval = coll_cfg.get("refresh_interval_hours", default_interval)
            if needs_refresh(name, interval, state):
                logger.info(f"Refreshing collection: {name}")
                try:
                    ingest_collection(name, coll_cfg, config)
                    state[name] = datetime.utcnow().isoformat()
                    refreshed.append(name)
                except Exception as e:
                    logger.error(f"Failed to refresh {name}: {e}")

    save_last_refresh(state)
    logger.info(f"Refreshed {len(refreshed)} collections: {refreshed}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
```

**Schedule via cron o Spinnaker** (correr cada hora):
```
0 * * * * cd /path/to/high-touch-agent-prompts/langgraph-system && python -m autonomous_jobs.rag_refresh
```

### Justificación
- **Freshness automática**: no dependemos de que alguien se acuerde de re-ingestar.
- **Per-collection scheduling**: repo_code cada 6h (cambia seguido), modules cada semana (cambia poco).
- **Observabilidad**: `.last_refresh.yaml` es chequeable por monitoring/healthcheck.
- **Failsafe**: si una colección falla el refresh, las otras siguen adelante.

### Verificación
1. Correr una vez manual: `python -m autonomous_jobs.rag_refresh` — debe refrescar todas.
2. Correrlo de nuevo inmediatamente — debe saltarse todas (ninguna stale).
3. Editar `.last_refresh.yaml` y poner fecha vieja para una colección — debe refrescar esa sola.

---

## FIX #13 — `critique_mode: "always"` para tool agents

### Archivo
`langgraph-system/config.yaml` — sección `feedback:`

### Problema
Actual: `critique_mode: "knowledge_only"` → Le Critique solo evalúa agentes knowledge-only (bob, hydra, etc.). **Los tool agents (jira, git, build, deploy, terraform) NO tienen quality check**.

Casos reales de falla silenciosa:
- `jira.create_ticket()` devuelve un ticket pero el campo "component" está vacío (config mal) — respuesta parece OK pero el ticket está roto
- `git.create_pr()` crea el PR pero al destination branch equivocado — respuesta "PR created successfully" pero es incorrecto
- `terraform.plan()` corre pero el plan tiene errores que el agent minimiza en el summary

### Cambio propuesto

**Paso 1 — Modo conservador: "always_with_tool_validation"**

En vez de switchear a `"always"` directo (que puede generar ruido), introducir un modo intermedio:

```yaml
feedback:
  critique_mode: "always_with_tool_validation"   # nuevo modo
  min_quality_score: 7
  collect_user_feedback: true

  # Nueva sección: reglas de validación básica para tool agents
  tool_agent_validation:
    enabled: true
    check_tool_call_success: true     # fail si tool_response.success == false
    check_response_references_tool_output: true  # response debe citar datos del tool
    require_links_for_resources: true  # create_ticket → debe incluir URL del ticket
```

**Paso 2 — Implementación en `carson_service.py`** (código nuevo, no existe todavía)

```python
def validate_tool_agent_response(agent_name: str, tool_calls: list, response: str) -> tuple[bool, str]:
    """Basic sanity checks for tool-agent responses. Returns (is_valid, reason)."""
    # Check 1: ningún tool call falló silenciosamente
    for call in tool_calls:
        if call.get("error") or call.get("status") == "failed":
            return False, f"Tool call {call['name']} failed: {call.get('error')}"

    # Check 2: respuesta referencia el output del tool (heurística: comparte >= 3 tokens distintivos)
    if tool_calls:
        tool_output_tokens = set()
        for call in tool_calls:
            tool_output_tokens.update(str(call.get("output", "")).split())
        response_tokens = set(response.split())
        overlap = len(tool_output_tokens & response_tokens)
        if overlap < 3:
            return False, "Response does not appear to reference tool output"

    # Check 3: para agents que crean recursos (jira, git, snow), debe haber URL
    resource_creating_agents = {"jira", "git", "snow", "postman"}
    if agent_name in resource_creating_agents:
        if not any(s in response.lower() for s in ["http://", "https://", "url:"]):
            return False, f"{agent_name} should return a link to the created resource"

    return True, "OK"
```

Y en el flujo principal del critique:
```python
if config["feedback"]["critique_mode"] == "always_with_tool_validation":
    if agent_is_tool_equipped:
        valid, reason = validate_tool_agent_response(agent_name, tool_calls, response)
        if not valid:
            # Trigger critique with validation failure context
            critique_result = run_critique(
                response,
                extra_context=f"Validation failure: {reason}"
            )
```

### Justificación
- **No es quality check completo**: es validación básica — dos niveles de defensa (sanity checks fáciles + full critique).
- **Menos ruido**: no corre el critique LLM en todos los tool responses (caro), solo cuando las heurísticas fallan.
- **Observabilidad mejorada**: logs de "validation failed" son señal directa para debug.

### Verificación
Simular un tool failure y confirmar que:
1. El response cae en el validation
2. Se dispara critique
3. Se loguea la razón del fail

---

## FIX #14 — Subir `max_tokens` de 4096 a 8192 para planner

### Archivo
`langgraph-system/config.yaml` — sección `performance:`

### Problema
`max_tokens: 4096` global. El planner (Monsieur Planchet) hace multi-step reasoning donde tiene que:
- Enumerar pasos del plan
- Justificar cada paso
- Listar tools/agentes requeridos
- Manejar edge cases

Para planes complejos (ej: "crear un nuevo módulo terraform + PR + Jira ticket + deploy a UAT"), 4096 tokens de output queda corto y el plan se trunca.

### Cambio propuesto

**Estrategia: per-agent max_tokens override**

```yaml
performance:
  max_tokens: 4096              # default para la mayoría
  max_tokens_per_agent:
    planner: 8192               # Monsieur Planchet hace reasoning multi-step
    terraform: 6144             # TF responses suelen ser largas (HCL completo)
    docs: 6144                  # Docs generation puede ser larga
    # Resto usa default
```

**Cambio en `carson_service.py`** para respetar el override:

```python
def get_max_tokens_for(agent_name: str) -> int:
    perf = config["performance"]
    overrides = perf.get("max_tokens_per_agent", {})
    return overrides.get(agent_name, perf["max_tokens"])
```

### Justificación
- **Sin cambio global innecesario**: subir todos a 8192 infla costo para agents que no lo necesitan (jira responses son cortos).
- **Específico por necesidad**: planner y terraform son los que más sufren truncado.
- **Rollback fácil**: si un agente específico da problemas, se baja solo ese.

### Verificación
Correr query compleja para el planner ("crear módulo nuevo + pipeline completo") y confirmar que el plan NO se trunca a mitad de paso.

---

## Orden de aplicación

1. **FIX #10** (max_rag_context_tokens) — 1 línea de config, efecto inmediato
2. **FIX #14** (max_tokens per agent) — config + cambio chico en código
3. **FIX #11** (operation_model collection) — config + ingesta
4. **FIX #12** (auto-refresh RAG) — requiere escribir el autonomous job completo (~60 LOC)
5. **FIX #13** (critique_mode always_with_validation) — requiere implementación de validación (~50 LOC + cambios al flujo)
