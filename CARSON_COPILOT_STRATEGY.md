# Carson + Copilot — Estrategia de integración

**Fecha**: 2026-04-14
**Audiencia**: cualquiera evaluando si Carson debería migrarse a Copilot, fusionarse, o quedarse separado.
**Recomendación corta**: **Copilot como cliente, Carson como motor**. No migrar.

---

## La pregunta que estamos respondiendo

¿Carson (multi-agent LangGraph system corriendo en ECS Fargate) debería:

A) Migrarse a vivir dentro de Copilot Workspace / Copilot Chat extension?
B) Mantenerse como servicio separado, con Copilot como cliente vía bridge?
C) Fusionarse con Copilot a nivel de modelos compartidos?

---

## Por qué NO migrar (Opción A descartada)

Carson tiene capacidades que Copilot no expone como primitivas:

- **20 agentes especializados** con MCP servers propios (jira, terraform, build, deploy, snow, etc.)
- **LangGraph orchestration**: planner (Monsieur Planchet) → router (Haiku 4.5) → agent → critique → response
- **RAG multi-collection**: 4 colecciones globales (modules, engineers_docs, amps_core, bundle_matrix) + 3 team-specific (repo_code, ahtw_confluence, bhtw_confluence)
- **Quality gates**: Le Critique con `min_quality_score: 7` y retry logic
- **PCL credential refresh** integrado con VDI/AWS — flujo específico de JPMC
- **Bedrock inference profiles** para routing model y embeddings

Copilot Chat / Workspace son excelentes para edits puntuales y completions, pero:

- No tienen un equivalente al multi-agent routing + RAG + critique pipeline
- No exponen MCP server orchestration (tienen su propio modelo de "skills")
- No permiten Bedrock inference profiles directamente (usan los modelos de OpenAI/MS)
- No integran con PCL/CDAO SDK

**Migrar = perder 6+ meses de trabajo arquitectónico y cerrar puertas a integraciones JPMC-específicas.**

---

## Por qué NO fusionar a nivel de modelos (Opción C descartada)

A primera vista, "usar el mismo modelo en ambos" suena lógico. Pero:

- **Carson usa Bedrock** (Sonnet 3.5 o 4 vía inference profile) — política JPMC para datos sensibles
- **Copilot usa Azure OpenAI** (GPT-4 / GPT-4 Turbo) — no se puede swap fácilmente sin perder funcionalidad de Copilot
- Los **prompts están finamente tuneados** para cada modelo (Anthropic vs OpenAI difieren en system prompt format, tool calling format, etc.)

El esfuerzo de unificar es alto, y el beneficio es marginal.

---

## Por qué SÍ usar Copilot como cliente (Opción B — recomendada)

Copilot es el **front-end conversacional dentro del IDE**. Carson es el **motor especializado de operaciones JPMC**. Conectarlos = mejor experiencia para ambos.

Hoy ya existe un bridge parcial: `send_carson_reply.py` (vía Outlook COM). Es funcional pero limitado:

- Es **asíncrono** (Carson responde por email, no inline en el editor)
- No pasa contexto del archivo abierto a Carson
- No tiene UI integrada en VS Code

Mejorar el bridge tiene mucho más valor que migrar todo el sistema.

### Arquitectura objetivo

```
┌───────────────────────────────────────────────────────┐
│  VS Code (developer machine / VDI)                    │
│  ┌────────────────────────────────────────────────┐   │
│  │  Copilot Chat                                  │   │
│  │  ├─ @copilot (default)                         │   │
│  │  ├─ @workspace                                 │   │
│  │  └─ @carson  ← NUEVO Chat Participant          │   │
│  │       │                                        │   │
│  │       │ HTTP POST /chat                        │   │
│  │       ▼                                        │   │
│  └───────┼────────────────────────────────────────┘   │
└──────────┼────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│  Carson Service (ECS Fargate :8765)                  │
│  ┌────────────────────────────────────────────────┐   │
│  │  FastAPI                                        │   │
│  │  ├─ POST /chat (NUEVO endpoint)                │   │
│  │  ├─ POST /carson_reply (existente, deprecate)  │   │
│  │  └─ Streaming response via SSE                  │   │
│  │       │                                          │   │
│  │       ▼                                          │   │
│  │  LangGraph: planner → router → agent → critique │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

---

## Roadmap concreto

### Semana 1 — Backend ready

**1.1 Endpoint `/chat` en `carson_service.py`**

Hoy `send_carson_reply.py` es asíncrono via email. Necesitamos sincrónico vía HTTP:

```python
from fastapi import FastAPI
from pydantic import BaseModel

class ChatRequest(BaseModel):
    query: str
    session_id: str
    file_context: str | None = None     # contenido del archivo abierto en VS Code
    file_path: str | None = None        # path relativo del archivo
    selected_text: str | None = None    # selección si la hay

class ChatResponse(BaseModel):
    response: str
    selected_agent: str
    confidence: float
    session_id: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # Augmentar query con file_context si existe
    augmented = req.query
    if req.file_path and req.file_context:
        augmented = (
            f"[Context: user is viewing {req.file_path}]\n"
            f"```\n{req.file_context[:2000]}\n```\n\n"
            f"User question: {req.query}"
        )

    # Invoke Carson LangGraph
    result = await run_carson(augmented, session_id=req.session_id)

    return ChatResponse(
        response=result["response"],
        selected_agent=result["selected_agent"],
        confidence=result["confidence"],
        session_id=req.session_id,
    )
```

**1.2 Streaming opcional via SSE** (para que Copilot muestre tokens incrementalmente):

```python
from fastapi.responses import StreamingResponse

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def event_generator():
        async for chunk in run_carson_streaming(req.query, req.session_id):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### Semana 2 — VS Code Chat Participant

**2.1 Crear extension** `carson-copilot-bridge` (TypeScript, ~150 LOC):

```typescript
// extension.ts
import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
    const carson = vscode.chat.createChatParticipant('carson', async (request, ctx, stream, token) => {
        // Capturar contexto del editor activo
        const editor = vscode.window.activeTextEditor;
        const fileContext = editor?.document.getText() ?? null;
        const filePath = editor?.document.uri.fsPath ?? null;
        const selectedText = editor?.selection
            ? editor.document.getText(editor.selection)
            : null;

        // Llamar a Carson FastAPI
        const response = await fetch(
            vscode.workspace.getConfiguration('carson').get<string>('endpoint') + '/chat',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: request.prompt,
                    session_id: ctx.history.length.toString(),
                    file_context: fileContext,
                    file_path: filePath,
                    selected_text: selectedText,
                }),
            }
        );

        const data = await response.json();
        stream.markdown(data.response);
        stream.markdown(`\n\n_Routed to: ${data.selected_agent} (confidence ${data.confidence})_`);
    });

    carson.iconPath = vscode.Uri.joinPath(context.extensionUri, 'carson.png');
    context.subscriptions.push(carson);
}
```

**2.2 Distribuir como VSIX interno** vía el portal de extensions de JPMC.

### Semana 3-4 — Polish

- Slash commands (`@carson /jira`, `@carson /terraform`) que fuerzan routing a un agente específico
- Diff suggestions: Carson devuelve `code_changes: [{file, diff}]` y la extension lo aplica via `WorkspaceEdit`
- Conversation history: pasar las últimas N respuestas en `ctx.history` para que Carson tenga continuidad

---

## Lo que NO hacer

- **No migrar Le Critique a Copilot** — la quality scoring de Carson es una feature diferenciadora, no la destruyas.
- **No exponer agentes individuales como Copilot participants distintos** — `@jira`, `@terraform`, etc. confunde al usuario y duplica trabajo. El router de Carson es lo que decide.
- **No usar Copilot Workspace** para esto — está diseñado para tareas de codificación largas, no para chat operacional.
- **No matar `send_carson_reply.py` todavía** — es el fallback async para cuando el usuario no está en VS Code (mobile, email, etc.). Marcalo como deprecated pero mantenlo 6 meses.

---

## Métricas de éxito (3 meses post-launch)

- **% queries resueltas via @carson** vs `@copilot`/email: target >40%
- **Tiempo medio de respuesta**: <8s p99 (latency Carson + RTT)
- **Quality score promedio**: >7.5 (sostenido)
- **Adoption rate**: >60% del equipo AHTW usando @carson semanalmente
- **Tickets Jira/SNOW creados via @carson**: >30% del total del equipo

---

## Resumen ejecutivo (1 párrafo)

Carson es demasiado grande, especializado, y JPMC-específico para vivir dentro de Copilot. La arquitectura correcta es **Carson como microservicio backend (lo que ya es) + Copilot como cliente conversacional vía Chat Participant**. El esfuerzo es de ~3-4 semanas (1 endpoint nuevo en FastAPI + 1 extension VS Code de ~150 LOC), preserva toda la inversión actual en multi-agent orchestration / RAG / Le Critique, y mejora drásticamente la UX (sincrónico inline en el editor en vez de async por email).
