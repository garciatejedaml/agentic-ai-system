# Carson Self-Improvement Execution Prompt

**Para qué es esto**: Pegás esto a Carson (vía Copilot Chat o sesión Claude con el repo `high-touch-agent-prompts` montado) y arranca a aplicar las mejoras documentadas en `CARSON_TIER1_FIXES.md` → `CARSON_TIER4_FIXES.md`.

**Pre-requisito**: Tener clonado el repo `agentic-ai-system` (este repo) o tener acceso a los docs `CARSON_TIER*_FIXES.md`.

---

## Prompt para pegar (start with this)

```
Estás a punto de mejorarte. En este repositorio (high-touch-agent-prompts) hay un set de mejoras documentadas en 4 archivos:

- CARSON_TIER1_FIXES.md — 5 bug fixes críticos
- CARSON_TIER2_FIXES.md — 4 fixes de consistencia de config
- CARSON_TIER3_FIXES.md — 5 mejoras de funcionalidad
- CARSON_TIER4_FIXES.md — 3 fixes de infraestructura

Si esos archivos no están en este repo, traelos del repo personal de Martín:
https://github.com/garciatejedaml/agentic-ai-system (root)

Tu trabajo: implementar Tier 1 completo (5 fixes) en este sprint, en orden, con commits separados por fix. NO empezar Tier 2 hasta que Tier 1 esté validado y mergeado.

Reglas (NO negociables):
1. NUNCA pushes a main directamente. Trabajá en branch feature/carson-tier1-fixes.
2. UN commit por fix. Mensaje de commit prefijado con "tier1/fixN: <título>".
3. Cada fix incluye una sección "Verificación post-fix" en el doc — corré esos checks ANTES de commitear ese fix.
4. Si un fix toca código (no solo config.yaml), agregá/actualizá tests si existe el módulo correspondiente en tests/.
5. Si un check de verificación falla, NO commitees — preguntale a Martín antes de seguir.
6. Mantené la lista de imports limpia y respetá el style del archivo (PEP 8, comillas dobles si el archivo las usa, etc.).
7. NO toques los archivos del directorio mcp-servers/ ni autonomous_jobs/ a menos que el fix lo pida explícitamente.
8. Si encontrás algo en el código que no coincide con la descripción del fix (ej: el doc dice "línea 149" pero el código actual difiere), parate y reportame antes de aplicar el cambio adaptado.

Plan de ejecución para Tier 1:

  ┌──────────────────────────────────────────────────────────────┐
  │ FIX  | Archivo            | Tipo            | Tiempo estim. │
  ├──────────────────────────────────────────────────────────────┤
  │  #1  | config.yaml        | YAML add        | 5 min          │
  │  #2  | config.yaml        | YAML edit       | 5 min          │
  │  #5  | config.yaml + .py  | Refactor email  | 20 min         │
  │  #3  | send_carson_reply  | Try/except      | 15 min         │
  │  #4  | fix_chromadb.py    | Load config     | 15 min         │
  └──────────────────────────────────────────────────────────────┘

Empezá YA con FIX #1. Antes de cada commit:
- Mostrá el diff exacto (solo las líneas modificadas, no el archivo completo).
- Listá los checks de verificación que corriste y su resultado.
- Esperá mi "OK" antes de pushear el commit (commit local sí, push no).

Después de los 5 commits de Tier 1:
- Pusheá la branch
- Abrí el PR con descripción que enumere los 5 fixes con links a los commits
- Esperá review/merge antes de pasar a Tier 2

Si necesitás contexto adicional sobre la arquitectura, el doc CARSON_SELF_IMPROVEMENT_PROMPT.md tiene la auditoría completa (Apéndices A-I son del repo correcto; M-R son de otro repo, ignoralos).

Empezá ahora con FIX #1. Mostrame primero el contenido actual de config.yaml en la sección agents (líneas ~95-118 aprox) para que verifiquemos juntos antes de modificar.
```

---

## Cómo usarlo (3 modos de despliegue)

### Modo A — Copilot Chat con `@carson` participant (si ya está implementado)
1. Abrí VS Code en el repo `high-touch-agent-prompts`
2. Asegurate de tener los archivos `CARSON_TIER*_FIXES.md` en el root del repo (o copialos del repo personal)
3. En Copilot Chat, escribí `@carson` y pegá el prompt de arriba
4. Carson empieza con FIX #1 y va commit por commit, esperando tu OK

### Modo B — Carson via terminal (FastAPI directo)
1. Asegurate que Carson esté corriendo (`uvicorn carson_service:app --port 8765`)
2. Hacé curl al endpoint de chat:
```bash
curl -X POST http://localhost:8765/chat \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$(cat CARSON_SELF_IMPROVEMENT_EXECUTION.md | sed -n '/^```$/,/^```$/p' | sed '1d;$d')\", \"session_id\": \"self-improve-tier1\"}"
```
3. Carson responde con el plan y arranca

### Modo C — Sesión Claude (Cowork o Code CLI) si Carson no anda en Copilot todavía
1. Abrí una sesión nueva con el repo `high-touch-agent-prompts` montado
2. Pegá el prompt de arriba
3. La sesión Claude actúa como Carson — leé los Tier docs, aplica fixes, commitea

---

## Checkpoints después de cada Tier

### Después de Tier 1 (esta semana)
- [ ] PR mergeado en `main`
- [ ] Smoke test: hacer una query "show me the latency metrics" y confirmar que rutea a `datadog` (no a `general`)
- [ ] Smoke test: re-ingestar repo_code y confirmar que hay docs `.hcl` indexados
- [ ] Smoke test: forzar fallo de Outlook (cerrarlo) y confirmar que `send_reply()` retorna `False` con log claro

Si los 3 smoke tests pasan: arrancá Tier 2 con un prompt similar. Si no: rollback del fix problemático y pingueame.

### Después de Tier 2
- [ ] Template y config sincronizados — diff manual debería mostrar solo placeholders YOUR_*
- [ ] Confirmar que sdlc/bob están bien clasificados (tool-equipped vs knowledge-only)
- [ ] Si aplicaste el upgrade a Sonnet 4: monitorear `quality_score` por 48h antes de escalar el rollout %

### Después de Tier 3
- [ ] El job `rag_refresh.py` tiene que estar agendado en cron/Spinnaker
- [ ] Confirmar que `operation_model` collection tiene >0 docs

### Después de Tier 4
- [ ] Bucket S3 `carson-kb-ahtw` creado con permisos IAM correctos
- [ ] Primer snapshot exitoso visible en S3
- [ ] Logs de routing decisions visibles en CloudWatch o Datadog

---

## Si algo se rompe

Carson tiene Le Critique para validar respuestas. Si después de un fix el `min_quality_score` empieza a caer:

1. Revertí el último commit: `git revert <hash>`
2. Pingueá a Martín con el quality_score promedio antes/después
3. NO sigas con el próximo fix hasta entender por qué bajó

---

## Por qué Tier 1 primero (y no en otro orden)

Los fixes están ordenados por **dependencias** y **riesgo**:

- **FIX #1, #2** — Solo tocan `config.yaml`, zero riesgo, alto valor inmediato (Rocky funcional, .hcl indexable). Ideal para arrancar y ganar momentum.
- **FIX #5 antes que #3** — Porque #3 (try/except) referencia `DEFAULT_REPLY_EMAIL` que se introduce en #5. Hacer #3 primero y después #5 te obliga a editar el mismo archivo dos veces.
- **FIX #4 al final** — Porque puede revelar problemas de schema en colecciones de ChromaDB que requieran investigación. Mejor que sea el último para no bloquear los otros 4.

---

## Prompt corto (TL;DR para pegar rápido)

Si no tenés tiempo para el prompt largo y querés algo mínimo:

```
Implementá los 5 fixes documentados en CARSON_TIER1_FIXES.md de este repo. Reglas:
- Branch feature/carson-tier1-fixes (no main)
- Un commit por fix con prefijo "tier1/fixN: <title>"
- Corré los checks de verificación de cada fix antes de commitear
- Mostrame el diff y esperá OK antes del push
- Empezá con FIX #1 (Rocky/datadog en config.yaml)
```
