# Agentic AI System — POC

Sistema multi-agente que combina **LangGraph** como orquestador de flujo, **Strands Agents** como grupo de agentes en nodos específicos, y **RAG** con ChromaDB para recuperación de contexto.

## Arquitectura

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph StateGraph                    │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────┐   │
│  │  intake  │──▶│ retrieve │──▶│     strands       │   │
│  │  (node)  │   │  (RAG)   │   │  (multi-agent)    │   │
│  └──────────┘   └──────────┘   │  ┌─────────────┐  │   │
│                     │          │  │ Researcher  │  │   │
│                 ChromaDB       │  │   Agent     │  │   │
│                                │  └──────┬──────┘  │   │
│                                │         │         │   │
│                                │  ┌──────▼──────┐  │   │
│                                │  │ Synthesizer │  │   │
│                                │  │   Agent     │  │   │
│                                │  └─────────────┘  │   │
│                                └─────────┬─────────┘   │
│                                          │              │
│                                   ┌──────▼──────┐       │
│                                   │   format    │       │
│                                   │   (node)    │       │
│                                   └─────────────┘       │
└─────────────────────────────────────────────────────────┘
    │
    ▼
Final Response
```

### Responsabilidades

| Capa | Tecnología | Rol |
|------|------------|-----|
| Orquestación | **LangGraph** | Control de flujo, estado compartido, routing |
| Agentes | **Strands Agents** | Investigación + síntesis con tool use |
| Conocimiento | **ChromaDB + sentence-transformers** | RAG local (dev) |
| LLM local | **Anthropic API** | Claude via API key (dev) |
| LLM producción | **Amazon Bedrock** | Claude via IAM roles (AWS) |

---

## Setup local (MacBook)

### Prerequisitos

- Python 3.11+
- API Key de Anthropic

```bash
# Verifica Python
python3 --version  # >= 3.11

# Instala pyenv si no tienes Python 3.11+
brew install pyenv
pyenv install 3.11.9
pyenv local 3.11.9
```

### 1. Clonar y crear entorno virtual

```bash
git clone <repo-url>
cd agentic-ai-system

python3 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

> **Nota M1/M2/M3 Mac:** Si `chromadb` falla al instalar:
> ```bash
> brew install cmake
> pip install chroma-hnswlib
> pip install -r requirements.txt
> ```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env y pon tu API key
```

Variables clave en `.env`:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-tu-key-aqui
ANTHROPIC_MODEL=claude-haiku-4-5   # haiku = más barato para dev
```

### 4. Ingestar documentos al RAG

```bash
# Ingestar los docs de ejemplo incluidos en data/sample_docs/
python scripts/ingest_docs.py

# O tus propios archivos .txt / .md
python scripts/ingest_docs.py /ruta/a/tus/docs/
```

### 5. Correr

```bash
# Modo interactivo (REPL)
python main.py

# Query única
python main.py "¿Qué es LangGraph y cómo se integra con Strands?"

# Con debug info
LANGGRAPH_DEBUG=true python main.py "¿Cómo funciona el RAG?"
```

### 6. Tests

Los tests son unitarios y no requieren LLM real (todo mockeado):

```bash
# Todos los tests
pytest tests/ -v

# Tests individuales
pytest tests/test_rag.py -v
pytest tests/test_graph.py -v
```

---

## Estructura del proyecto

```
agentic-ai-system/
├── src/
│   ├── config.py                  # Config centralizada (env vars)
│   ├── rag/
│   │   └── retriever.py           # ChromaDB + sentence-transformers
│   ├── agents/
│   │   ├── model_factory.py       # Anthropic (local) ↔ Bedrock (AWS)
│   │   ├── tools.py               # @tool definitions para Strands
│   │   ├── researcher.py          # Strands researcher agent
│   │   ├── synthesizer.py         # Strands synthesizer agent
│   │   └── orchestrator.py        # Orquesta researcher → synthesizer
│   └── graph/
│       ├── state.py               # AgentState (TypedDict)
│       ├── nodes.py               # Funciones de cada nodo LangGraph
│       └── workflow.py            # StateGraph compilado
├── data/
│   └── sample_docs/               # Documentos de ejemplo para RAG
├── scripts/
│   └── ingest_docs.py             # CLI para ingestar documentos
├── tests/
│   ├── test_rag.py
│   └── test_graph.py
├── main.py                        # Entry point
├── requirements.txt
└── .env.example
```

---

## Migrar a AWS (producción)

### Cambios mínimos

1. **Variables de entorno en producción:**
   ```bash
   LLM_PROVIDER=bedrock
   AWS_DEFAULT_REGION=us-east-1
   BEDROCK_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0
   ```
   No se necesita API key — Bedrock usa IAM roles automáticamente.

2. **ChromaDB → OpenSearch (recomendado para prod):**
   En `src/rag/retriever.py` reemplaza `chromadb.PersistentClient` con
   `langchain_aws.vectorstores.OpenSearchVectorSearch`. El resto no cambia.

3. **Despliegue:** ECS Fargate, Lambda + container, o EC2.
   `main.py` se puede envolver en un FastAPI endpoint fácilmente.

### IAM permissions mínimas para Bedrock

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:InvokeModel",
    "bedrock:InvokeModelWithResponseStream"
  ],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.*"
}
```

---

## Extender el POC

### Agregar un nuevo agente Strands

```python
# src/agents/fact_checker.py
from strands import Agent
from src.agents.model_factory import get_strands_model
from src.agents.tools import search_knowledge_base

def create_fact_checker() -> Agent:
    return Agent(
        model=get_strands_model(),
        system_prompt="Verify factual claims against the knowledge base.",
        tools=[search_knowledge_base],
    )
```

Agrégalo en `orchestrator.py` entre researcher y synthesizer.

### Routing condicional en LangGraph

```python
# En workflow.py
def should_retry(state: AgentState) -> str:
    return "intake" if state.get("error") else "format"

graph.add_conditional_edges(
    "strands", should_retry, {"intake": "intake", "format": "format"}
)
```
