# Carson Tier 2 Fixes — Consistencia de Config

**Repo**: `high-touch-agent-prompts`
**Fecha**: 2026-04-14
**Prerequisito**: Tier 1 aplicado

Cuatro fixes de limpieza de config. Bajo riesgo, alto valor de largo plazo (mantenibilidad, onboarding de equipos).

---

## FIX #6 — Reconciliar knowledge-only vs tool-equipped (contradicción C.4)

### Archivos
- `langgraph-system/config.yaml` (línea 106, comentario + declaraciones)
- `agents/sdlc.agent.md`
- `agents/bob.agent.md`

### Problema
El comentario en `config.yaml` línea 106 dice `# Knowledge-only agents (no MCP tools)` y lista: bob, hydra, cbb, pixie, studio, sdlc. **Pero**:
- `sdlc.agent.md` (13.24KB) referencia `sdlc-mcp-server` como tool-equipped en Appendix B
- `bob.agent.md` lista tools `query_bob_jobs`, `build_bob_url`, etc. en su tabla

Resultado: el router puede decidir "sdlc es knowledge-only, no le doy tool-heavy queries", cuando en realidad sdlc SÍ tiene MCP tools. Bug de routing por config desincronizado.

### Pasos para reconciliar

**Paso A — Verificar estado real**:
```bash
# Desde langgraph-system/
ls ../mcp-servers/ | grep -E "sdlc|bob|hydra|cbb|pixie|studio"
```

Si hay `sdlc-mcp-server/`, `bob-mcp-server/`, etc. → son tool-equipped. Si no existen → son realmente knowledge-only.

**Paso B — Sincronizar config.yaml**

Si confirmaste que todos/algunos tienen MCP server, remover el comentario engañoso y reagruparlos:

```yaml
  # Tool-equipped specialist agents
  bob:
    enabled: true       # Big Orange Button — bob-mcp-server
  sdlc:
    enabled: true       # SDLC compliance — sdlc-mcp-server
  hydra:
    enabled: true       # Reemplazar comment con MCP server si aplica
  cbb:
    enabled: true       # Idem
  pixie:
    enabled: true       # Idem
  studio:
    enabled: true       # Idem
```

**Paso C — Sincronizar `.agent.md` files**
Si algún agente listado arriba **NO** tiene MCP server, eliminar las tablas de tools falsas de su `.agent.md` para no confundir al LLM router durante el pre-routing analysis.

### Justificación
- **Routing correcto**: el router de Haiku 4.5 toma en cuenta el contenido de `.agent.md`. Tablas de tools falsas distorsionan la decisión.
- **Honestidad en docs**: el comentario "no MCP tools" está mintiendo en al menos 2 casos conocidos (sdlc, bob).

---

## FIX #7 — Sincronizar `config_template.yaml` con `config.yaml`

### Archivo
`langgraph-system/config_template.yaml` (3.46KB, 104 líneas)

### Problema
El template está **criticamente desactualizado**:

| Aspecto | Template | Config real | Gap |
|---|---|---|---|
| Agents | 7 (jira, git, build, deploy, terraform, docs, general) | 20 | Faltan 13 agentes |
| Performance | No existe | Sección completa (12 campos) | CRÍTICO — nuevos equipos sin tuning |
| Feedback/Critique | No existe | `critique_mode`, `min_quality_score`, etc. | CRÍTICO — sin quality control |
| `routing_model_arn` | No existe | Haiku 4.5 ARN | Nuevos equipos usan main model (caro) |
| `embedding_model_arn` | No existe | Titan/Cohere ARN | Embeddings rompen |
| `confluence_pages` | No existe | 3 páginas AHTW/BHTW/ops | Sin Confluence RAG |
| `team_id` | No existe | `"ahtw"` | Sin multi-tenancy |
| Extensiones RAG | 2 (`.py`, `.md`) | 7 (más `.yaml`, `.yml`, `.xml`, `.tf`, `.json`) | Falta cobertura |

Nuevo equipo que hace `cp config_template.yaml config.yaml` arranca con un sistema **roto**.

### Cambio propuesto
Reemplazar `config_template.yaml` completo con una versión sincronizada. La estrategia: **copiar `config.yaml` actual, reemplazar valores específicos de AHTW con placeholders `YOUR_*`, dejar comentarios explicativos**.

**Skeleton del nuevo template** (mantengo la estructura exacta de config.yaml):

```yaml
# =====================================================================
# Carson Multi-Agent System — Configuration Template
# =====================================================================
# Run: python scripts/onboarding.py for an interactive setup.
# Or copy this file to config.yaml and replace placeholders YOUR_*.
# =====================================================================

team_name: "YOUR_TEAM"           # e.g., "AHTW"
team_description: "YOUR_TEAM_DESCRIPTION"

# ----- Confluence pages (team wiki sources) --------------------------
confluence_pages:
  main_workflow:
    page_id: "YOUR_MAIN_PAGE_ID"
    title: "Your Main Workflow Page"
  secondary_workflow:
    page_id: "YOUR_SECONDARY_PAGE_ID"
    title: "Your Secondary Page"
  # Agregar más según necesidad

# ----- AWS -----------------------------------------------------------
aws:
  role_arn: "arn:aws:iam::YOUR_ACCOUNT:role/YOUR_ROLE"
  region: "us-east-1"
  is_execution_role: false       # true si es un role de ejecución directa

default_bitbucket_project: "YOUR_PROJECT"

# ----- Bitbucket projects --------------------------------------------
bitbucket_projects:
  YOUR_PROJECT:
    repositories:
      - "your-repo-1"
      - "your-repo-2"
  SHARED_PROJECT:
    repositories: []             # vacío = todos los repos del proyecto

# ----- LLM config ----------------------------------------------------
llm:
  provider: "bedrock"            # o "anthropic" para API directa
  main_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"   # o sonnet-4 cuando esté disponible
  # Anthropic direct (backup)
  anthropic_model: "claude-sonnet-4-20250514"
  routing_model_arn: "arn:aws:bedrock:us-east-1:YOUR_ACCOUNT:inference-profile/YOUR_HAIKU_PROFILE_ID"
  embedding_model_arn: "arn:aws:bedrock:us-east-1:YOUR_ACCOUNT:inference-profile/YOUR_EMBEDDING_PROFILE_ID"

# ----- Agents (sincronizado con config.yaml real) --------------------
agents:
  # Core workflow agents (tool-equipped)
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

  # Domain-specific tool-equipped agents
  amps:
    enabled: true
  snow:
    enabled: true
  postman:
    enabled: true
  picasso:
    enabled: true

  # Specialist tool-equipped agents (MCP-backed)
  bob:
    enabled: true
  sdlc:
    enabled: true

  # Knowledge-only agents (RAG-based, no MCP)
  hydra:
    enabled: true
  cbb:
    enabled: true
  pixie:
    enabled: true
  studio:
    enabled: true

  # Observability (FIX #1)
  datadog:
    enabled: false               # Cambiar a true cuando Rocky esté listo

  # Opt-in agents
  gossip:
    enabled: false
  teams:
    enabled: false

# ----- RAG / ChromaDB ------------------------------------------------
rag:
  enabled: true
  persist_dir: "./carson_kb"
  team_id: "your_team_id"        # lowercase, kebab/snake case

  global_collections:
    modules:
      description: "Terraform modules reference"
      source: "atlasterraform"
    engineers_docs:
      description: "JPMC Engineers Docs"
      source: "engineers_docs"
    # Agregar según aplique a tu equipo

  team_collections:
    repo_code:
      source: team_repos
      extensions: [".py", ".md", ".yaml", ".yml", ".xml", ".tf", ".tfvars", ".hcl", ".json"]  # FIX #2
    main_confluence:
      source: confluence
      page_id: "YOUR_MAIN_PAGE_ID"

# ----- Deploy pipeline mapping ---------------------------------------
deploy:
  branch_to_pipeline:
    "feature/": "dev"
    "develop": "uat"
    "main": "pre"                # prod deploys are manual-only
  repo_to_app_map: {}            # llenar si hay Spinnaker apps no-convencionales
  terraform_app_suffix: ""

# ----- Performance tuning (CRITICAL — no lo borres) ------------------
performance:
  max_tokens: 4096
  temperature: 0.0
  max_tool_iterations: 5
  max_workflow_steps: 100
  critique_max_retries: 3
  enable_prompt_caching: true
  truncate_tool_results: 8000
  max_rag_context_tokens: 2000   # considerar 4000 para queries complejas
  llm_timeout: 120
  mcp_tool_timeout: 30
  credential_refresh_timeout: 120

# ----- Feedback (Le Critique) ----------------------------------------
feedback:
  critique_mode: "knowledge_only"  # o "always" para quality-check en tool agents
  min_quality_score: 7
  collect_user_feedback: true

# ----- Notifications (FIX #5) ----------------------------------------
notifications:
  default_reply_email: "YOUR_EMAIL@YOUR_ORG"
  reply_subject_format: "[Carson:{session_id}] Re: {topic}"
  reply_footer: "Sent via Carson (Copilot Mode)"

# ----- Service -------------------------------------------------------
service:
  host: "0.0.0.0"
  port: 8765
  mcp_servers_path: "../mcp-servers"
```

### Justificación
- **Onboarding sin fricción**: nuevo equipo hace `cp template → config.yaml`, rellena YOUR_* y arranca.
- **Sin sorpresas**: todas las secciones críticas (performance, feedback, RAG, routing model) están presentes.
- **Documentación embebida**: comentarios en cada sección explican el para qué.

---

## FIX #8 — Upgrade de modelo (Sonnet 3.5 → Sonnet 4)

### Archivo
`langgraph-system/config.yaml` — sección `llm:`

### Problema
- `config.yaml` usa `anthropic.claude-3-5-sonnet-20241022-v2:0` (Sonnet 3.5)
- `config_template.yaml` referencia `claude-sonnet-4-20250514` (Sonnet 4)

Sonnet 4 tiene mejor razonamiento, mejor tool-calling, y mejor instruction-following. Especialmente relevante para Carson porque el planner/orchestrator hace multi-step reasoning.

### Cambio propuesto (en 2 pasos — **NO hacer directamente**)

**Paso 1 — Validar disponibilidad en Bedrock**:
```bash
aws bedrock list-foundation-models --region us-east-1 \
  | jq '.modelSummaries[] | select(.modelId | contains("sonnet-4"))'
```

Confirmar que el modelo está disponible en la cuenta AWS del equipo.

**Paso 2 — A/B test con shadow traffic o feature flag**:

En vez de switchear directo, agregar un flag:

```yaml
llm:
  provider: "bedrock"
  main_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"    # prod actual
  experimental_main_model: "anthropic.claude-sonnet-4-20250514-v1:0"  # nuevo
  experimental_rollout_percentage: 10    # empezar con 10% del tráfico
```

Requiere cambio en `carson_service.py` para respetar el rollout_percentage:
```python
import random

def get_main_model_id() -> str:
    cfg = config["llm"]
    if cfg.get("experimental_main_model"):
        pct = cfg.get("experimental_rollout_percentage", 0)
        if random.randint(1, 100) <= pct:
            return cfg["experimental_main_model"]
    return cfg["main_model"]
```

Luego escalar 10% → 50% → 100% según resultados.

### Justificación
- **No upgrade ciego**: cambiar el modelo de todos los usuarios de golpe es riesgoso — puede romper prompts finamente tuneados para 3.5.
- **Observabilidad primero**: con rollout_percentage podés comparar métricas (quality score, latency, cost) entre modelos en producción real.
- **Rollback fácil**: bajar `experimental_rollout_percentage: 0` corta el experimento sin redeploy.

### Verificación
Después de 100 queries con Sonnet 4:
- quality_score promedio debe ser ≥ Sonnet 3.5
- p99 latency no debe crecer más del 20%
- costo por query no debe crecer más del 30% (Sonnet 4 es más caro)

---

## FIX #9 — Agregar campos faltantes (`default_bitbucket_project`, `is_execution_role`)

### Archivo
`langgraph-system/config.yaml`

### Problema
`config_template.yaml` tiene dos campos que **no están en `config.yaml`**:

1. `default_bitbucket_project: "YOUR_PROJECT"` — Sin esto, código que busque el proyecto por defecto puede fallar silenciosamente o usar un fallback hardcoded.
2. `is_execution_role: false` — Sin esto, refresh de credenciales puede usar flujo equivocado (execution role vs user role usan paths distintos en PCL).

### Cambio propuesto

**Agregar en `config.yaml`** (cerca de la sección aws o bitbucket):

```yaml
aws:
  role_arn: "arn:aws:iam::YOUR_ACCOUNT:role/YOUR_ROLE"
  region: "us-east-1"
  is_execution_role: false       # true si es un role de ejecución directa, no asumido por usuario

default_bitbucket_project: "ACAMPS"
```

### Justificación
- **Paridad template ↔ config**: elimina sorpresas cuando code lee `config["default_bitbucket_project"]`.
- **PCL credential refresh**: el flujo de `is_execution_role: true` es distinto — confirmarlo para no romper refresh en VDI.

### Verificación
```python
# En carson_service.py, al startup:
assert "default_bitbucket_project" in config, "Missing required field"
assert "is_execution_role" in config.get("aws", {}), "Missing aws.is_execution_role"
```

---

## Orden de aplicación

1. **FIX #9** — campos faltantes (2 min, zero risk)
2. **FIX #6** — reconciliar knowledge-only vs tool (requiere verificación de mcp-servers/)
3. **FIX #7** — sync template (copy/paste + reemplazar valores, 15 min)
4. **FIX #8** — Sonnet 4 upgrade (requiere A/B test setup, **no hacer sin validación**)
