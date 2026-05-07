# Carson — Audit, Fixes, and Cloud Transformation Roadmap

**Repo**: `high-touch-agent-prompts`
**Branch**: `feature/CREDITTECH-241864-agentic-ai-mcp-servers`
**Document version**: 3.0 (consolidates Tier 1–4 from 2026-04-14 + 2026-04-26 deep audit + AWS-ready transformation plan)
**Last updated**: 2026-04-26

---

## Table of contents

1. [Document purpose](#document-purpose)
2. [Executive summary](#executive-summary)
3. [Target state — what Carson should be](#target-state)
4. [How to use this document (instructions for Copilot)](#how-to-use-this-document)
5. [Index of fixes](#index-of-fixes)
6. [Suggested order of application](#suggested-order-of-application)
7. [Tier 0 — Architectural P0 fixes](#tier-0)
8. [Tier 1 — Concrete bugs](#tier-1)
9. [Tier 2 — Config consistency](#tier-2)
10. [Tier 3 — Functionality](#tier-3)
11. [Tier 4 — Infrastructure & observability](#tier-4)
12. [Tier 5 — Additional findings (deep audit)](#tier-5)
13. [Cloud transformation — AWS-ready](#cloud-transformation)
    - [Containerization](#containerization)
    - [AWS deployment topology](#aws-deployment-topology)
    - [Auto-scaling and capacity](#auto-scaling)
    - [Multi-AZ HA and multi-region DR](#multi-az-multi-region)
    - [Observability stack](#observability-stack)
    - [Secrets management and encryption](#secrets-and-encryption)
    - [Infrastructure as Code](#iac)
    - [CI/CD pipeline](#cicd)
    - [Data layer and state](#data-layer)
    - [Cost optimization](#cost-optimization)
    - [Security hardening](#security-hardening)
    - [Compliance and audit](#compliance)
    - [SLOs, SLIs, and alerting](#slos)
14. [Phased roadmap (26-week plan)](#roadmap)
15. [Status tracking and document maintenance](#status-tracking)

---

## Document purpose

This document is the **single source of truth** for everything Carson needs to become a production enterprise-grade platform on AWS. It consolidates:

- **Bug-level fixes** (the 17 fixes from the original Tier 1–4 audit on 2026-04-14)
- **Architectural fixes** (6 P0 findings from the 2026-04-26 deep audit)
- **Structural debt cleanup** (20 additional P1/P2 findings)
- **Cloud transformation strategy** (containerization, AWS deployment, IaC, observability, secrets, security, compliance)
- **Phased delivery roadmap** (26-week plan from "fix the worst" to "enterprise-grade")

Every entry in this document is meant to be **executable by Copilot or Carson itself**. Each fix includes file paths, current code, fixed code, justification, and a verification step. The cloud transformation sections include reference architecture, Terraform/CDK snippets, and operational runbooks.

The North Star: **Carson should be a platform you can hand to another team, deploy in their AWS account in 30 minutes, and trust to run their multi-agent workflows reliably**. Today it works for one team in one VDI. The plan below makes it work for any team in any AWS region.

---

## Executive summary

### What Carson is today

A **25-agent LangGraph orchestration system** running as a Flask service on a Citrix VDI, fronted by a single 130 KB HTML dashboard, with a 27-command VSCode extension and a peer-to-peer git-synced data layer between user instances. It works. The team has done real engineering on several pieces: typed state, prompt caching, dual-model routing, JSON-schema tools, a base agent abstraction, an AST-chunked RAG with 70K+ chunks, and a sophisticated VSCode integration.

### What Carson is missing to be enterprise-grade

In one sentence: **everything that turns a successful internal tool into a platform**.

Concretely, Carson today has:

- **Three parallel orchestration layers** for the same agent pool, each with its own state schema. Half-finished consolidation is the root cause of the "infinite loop" guard the team had to add (`MAX_WORKFLOW_STEPS = 100`).
- **No containerization, no IaC, no CI/CD**. Carson is deployed by manually setting up a Windows VDI, installing Python, running PowerShell scripts. Replicating to another team takes a week of hand-holding.
- **No cloud-native observability**. There is a `token_tracker` in memory that never makes it to CloudWatch, structured logs that go to disk and rot, no distributed tracing, no metrics for routing decisions, no alerts.
- **Secrets and config hardcoded in source**. Proxy URLs, Windows paths (`I:/repositories`), default emails, model ARNs all live in Python files. Other teams adopting Carson have to fork and patch.
- **Persistence via git**. User conversations get auto-committed every 5 minutes to a `carson/data` branch and pulled by peers. Privacy issue (any repo reader sees everyone's conversations), bloat issue (thousands of commits/month at scale), Bitbucket-load issue.
- **No HA, no DR**. Single VDI. Container rebuild loses ChromaDB embeddings. No backups beyond the user's local disk.
- **No security hardening**. No least-privilege IAM, no WAF, no audit logging, no PII redaction in logs, no encryption-at-rest beyond what Bitbucket provides.
- **No SLOs**. Nobody knows what "Carson is up and healthy" means in numbers.

### What needs to change, in priority order

1. **Stop the bleeding** (Tier 0 P0 fixes): proxy to config, dashboard polling off Bedrock, retry-budget consistency, three orchestrators → one, conversation privacy.
2. **Make it deployable** (Cloud foundation): containerize, write IaC, set up CI/CD, deploy to ECS Fargate behind an ALB.
3. **Make it observable** (Observability stack): export `token_tracker` metrics to CloudWatch, instrument everything with OpenTelemetry, enable X-Ray distributed tracing, write CloudWatch dashboards and alarms.
4. **Make it secure** (Security hardening): Secrets Manager + KMS, least-privilege IAM, WAF in front of the ALB, PII redaction in logs, audit trail.
5. **Make it scale** (Auto-scaling, HA, DR): multi-AZ from day one, target group health checks, capacity-based scaling, cross-region DR for the data layer.
6. **Make it adoptable by other teams** (Multi-tenancy): config-driven onboarding, separate per-team data, parameterised IaC.
7. **Polish the developer experience** (Tier 1–5 cleanup fixes): config consistency, error handling, dependency lock, dashboard split, etc.

---

## Target state — what Carson should be

### One-sentence vision

Carson is the **agentic AI platform for internal engineering work** — multi-agent, multi-tenant, cloud-native, observable, secure, and trivial to adopt by any team in the org.

### Capabilities (production target)

- **Multi-agent orchestration** with one unified workflow (planner → router → agent → critic → synthesizer), supporting both quality-driven retries and human-in-the-loop approvals.
- **25+ specialist agents** (DevOps, observability, knowledge, autonomous coding, notifications) with per-agent prompt caching, per-agent token budgets, and per-agent capability flags.
- **Real-time observability dashboard** showing live agent activity, run history, distributed traces, cost-per-request, and SLO compliance.
- **MCP-server ecosystem** (10+ servers covering Jira, Bitbucket, Jenkins, Spinnaker, Confluence, Outlook, Datadog, Terraform, Farm, Rivet) installed as proper Python packages, deployed alongside Carson.
- **Multi-tenant**: each team's instance reads from its own `config.yaml`, has its own RAG collections, its own MCP credentials, its own dashboard URL.
- **Cloud-native**: deployed on AWS ECS Fargate behind an ALB, with auto-scaling, multi-AZ, encrypted at rest and in transit, observable via CloudWatch + X-Ray.
- **Self-service onboarding**: a new team can run `carson onboard --team my-team` and get a fully provisioned, deployed Carson instance pointing at their Bitbucket project, Jira instance, and Confluence space.

### Non-functional targets

| Aspect | Target |
|---|---|
| **Availability** | 99.5% monthly (≈ 3.6 hours unplanned downtime/month) for the LangGraph service; 99.9% for the dashboard read path |
| **Latency** | p50 < 3 s, p95 < 10 s, p99 < 30 s for an agent round-trip (excluding human-in-the-loop pauses) |
| **Cost per request** | < $0.05 average, < $0.30 worst case (with 3 critic retries on Sonnet) |
| **Time-to-onboard** | < 30 min from "I want Carson for my team" to "Carson is responding to my queries" |
| **Recovery time objective (RTO)** | < 1 hour for full service restoration |
| **Recovery point objective (RPO)** | < 15 minutes data loss (hot tier), < 1 hour (cold tier) |
| **Security posture** | All secrets in Secrets Manager, least-privilege IAM, WAF in front, PII redaction in logs, full audit trail of write actions |
| **Observability** | 100% of agent runs traced (X-Ray), 100% of LLM calls metered (CloudWatch), routing confidence and critic verdicts logged structurally |

### Delta from current state to target

The fix list below (Tier 0–5) is the bug-level work. The "Cloud transformation" section is the platform-level work. Both have to happen together: just fixing bugs without containerizing means Carson is a polished tool that still can't be deployed to AWS; just deploying to AWS without fixing the orchestration duplication means we lift-and-shift the bugs.

The roadmap at the end ties bug-level and platform-level work into a single 26-week plan.

---

## How to use this document (instructions for Copilot)

This document is meant to be read sequentially by an agent (Copilot, Carson, or a human-driven session) and applied as a workstream.

**Execution rules:**

1. **Apply fixes in priority order**: P0 first, then P1, then P2. Inside a priority bucket, follow the numeric order — earlier fixes set up context for later ones.
2. **Each fix is self-contained**: file paths, current code, fixed code, justification, verification.
3. **Always verify before commit**: every fix has a `Verification` block. Run it. If it does not pass, do not commit.
4. **Commit one fix per commit**: commit message format `Carson: FIX #X — <short title>`. Reference this document in the body.
5. **If a path or pattern does not match**: stop. Do not "best-effort" the fix. Carson's structure has changed across branches; ask the human to confirm the current path/pattern before continuing.
6. **All file paths are relative to the repo root** (`high-touch-agent-prompts/`) unless explicitly absolute.
7. **For platform-level work** (cloud transformation sections), do not start until at least Tier 0 P0 fixes are merged. The migration is easier on a stable base.

**Priority key:**

- **P0** — fix this week. Cost, reliability, or security blocker.
- **P1** — fix this month. Structural debt that grows fast.
- **P2** — fix when convenient. Polish.

**Tier organisation** (traceability, does not change priority order):

- **Tier 0** — architectural P0 (2026-04-26 deep audit)
- **Tier 1** — concrete bugs (2026-04-14)
- **Tier 2** — config consistency (2026-04-14)
- **Tier 3** — functionality (2026-04-14)
- **Tier 4** — infrastructure & observability (2026-04-14)
- **Tier 5** — additional findings from deep audit (P1/P2)
- **Cloud** — platform-level transformation (cross-cutting)

---

## Index of fixes

| ID | Priority | Tier | Title |
|---|---|---|---|
| FIX #0.1 | P0 | 0 | Proxy and environment hardcoded in carson_service.py |
| FIX #0.2 | P0 | 0 | Three parallel orchestration systems for the same agent pool |
| FIX #0.3 | P0 | 0 | Dashboard polls Bedrock on a timer |
| FIX #0.4 | P0 | 0 | Workflow loop guard at 100 steps masks routing bugs |
| FIX #0.5 | P0 | 0 | Critic retry budget disagrees with itself across files |
| FIX #0.6 | P0 | 0 | Git used as a peer-to-peer database for conversations |
| FIX #1 | P0 | 1 | Datadog/Rocky agent invisible to the router |
| FIX #2 | P0 | 1 | `.hcl` and `.tfvars` missing from `repo_code` RAG extensions |
| FIX #3 | P1 | 1 | Error handling in `send_carson_reply.py` |
| FIX #4 | P1 | 1 | `fix_chromadb.py` passes `config={}` and bypasses config.yaml |
| FIX #5 | P1 | 1 | Email hardcoded → move to config.yaml |
| FIX #6 | P1 | 2 | Reconcile knowledge-only vs tool-equipped agents |
| FIX #7 | P1 | 2 | Sync `config_template.yaml` with `config.yaml` |
| FIX #8 | P2 | 2 | Upgrade model (Sonnet 3.5 → Sonnet 4) — A/B rollout |
| FIX #9 | P1 | 2 | Add missing fields (`default_bitbucket_project`, `is_execution_role`) |
| FIX #10 | P1 | 3 | Raise `max_rag_context_tokens` from 2000 to 4000 |
| FIX #11 | P1 | 3 | Create `operation_model` RAG collection |
| FIX #12 | P1 | 3 | Auto-refresh RAG (staleness mechanism) |
| FIX #13 | P1 | 3 | `critique_mode: "always_with_tool_validation"` for tool agents |
| FIX #14 | P1 | 3 | `max_tokens` per agent (planner needs 8192) |
| FIX #15 | P1 | 4 | ChromaDB persistence to S3 |
| FIX #16 | P1 | 4 | Structured logging of routing decisions |
| FIX #17 | P0 | 4 | Validate Bedrock inference profile ARNs at startup |
| FIX #18 | P1 | 5 | MCP servers share `source/` package; sys.modules monkey-patch |
| FIX #19 | P1 | 5 | Flask + FastAPI both in production deps |
| FIX #20 | P1 | 5 | Eleven Flask blueprints, docstring lists six endpoints |
| FIX #21 | P1 | 5 | sys.path manipulation with hardcoded relative paths |
| FIX #22 | P1 | 5 | No dependency lock file |
| FIX #23 | P1 | 5 | Dashboard 130 KB monolith |
| FIX #24 | P1 | 5 | render_template_string for static template |
| FIX #25 | P1 | 5 | Mixed CSS design systems in dashboard |
| FIX #26 | P0 | 5 | 25-agent flat registry without category split |
| FIX #27 | P1 | 5 | Cache directories committed to git |
| FIX #28 | P2 | 5 | Two extra `*salesdash.html` dashboards |
| FIX #29 | P2 | 5 | onclick handlers, href="javascript:void(0)" |
| FIX #30 | P2 | 5 | Charts via innerHTML string interpolation |
| FIX #31 | P2 | 5 | f-strings inside logger.debug |
| FIX #32 | P2 | 5 | Bare except Exception in dashboard.py |
| FIX #33 | P2 | 5 | Default critique verdict is APPROVE |
| FIX #34 | P2 | 5 | Prompt duplication between router and planner |
| FIX #35 | P2 | 5 | Action queue is a JSON file (race conditions) |
| FIX #36 | P2 | 5 | JobRecord has duplicate result/response fields |
| FIX #37 | P2 | 5 | mcp_loader/agents 4-level parent chain |
| FIX #38 | P1 | 5 | Dual-mode deployment scaffolding (bridge to cloud) |
| CLD #1 | P0 | Cloud | Containerize Carson with Dockerfile + ECR |
| CLD #2 | P0 | Cloud | Terraform module for ECS Fargate + ALB + VPC |
| CLD #3 | P0 | Cloud | Secrets in AWS Secrets Manager + KMS |
| CLD #4 | P0 | Cloud | CI/CD pipeline (GitHub Actions + Spinnaker) |
| CLD #5 | P0 | Cloud | CloudWatch metrics from token_tracker |
| CLD #6 | P0 | Cloud | OpenTelemetry instrumentation + X-Ray export |
| CLD #7 | P1 | Cloud | DynamoDB hot path + S3 cold storage |
| CLD #8 | P1 | Cloud | Auto-scaling policies (CPU + custom metrics) |
| CLD #9 | P1 | Cloud | Multi-AZ deployment + ALB health checks |
| CLD #10 | P1 | Cloud | WAF in front of ALB + IP allowlisting |
| CLD #11 | P1 | Cloud | PII redaction in logs and traces |
| CLD #12 | P1 | Cloud | Audit log of all write operations to S3 |
| CLD #13 | P2 | Cloud | Cross-region DR (warm standby) |
| CLD #14 | P2 | Cloud | Cost allocation tags + per-team chargeback |
| CLD #15 | P2 | Cloud | SLO dashboards + error budget alerting |

---

## Suggested order of application

### Sprint 1 (week 1) — stop the bleeding

Highest cost/risk fixes first:

1. **FIX #0.1** — proxy to config (30 min)
2. **FIX #1** — datadog enabled (2 min)
3. **FIX #2** — `.hcl`/`.tfvars` in RAG (2 min + re-ingest)
4. **FIX #27** — caches out of git (30 min)
5. **FIX #22** — dependency lock file (1 hour)
6. **FIX #17** — Bedrock ARN validation at startup (1 hour)
7. **FIX #0.3** — kill dashboard LLM polling (1 day)

### Sprint 2 (week 2) — fix correctness

8. **FIX #0.4** + **FIX #26** — reorganise AGENT_REGISTRY into typed groups, fix routing, replace 100-step guard with cycle detection (2 days)
9. **FIX #0.5** — single source of truth for critic retry budget (4 hours)
10. **FIX #0.2** — decide between `workflow.py` and `orchestrator.py`, deprecate one (3 days)

### Sprint 3-4 (weeks 3-4) — make it deployable

11. **CLD #1** — Dockerfile + ECR push (1 day)
12. **CLD #2** — Terraform module for ECS Fargate + ALB + VPC (3 days)
13. **CLD #3** — Secrets in Secrets Manager + KMS (2 days)
14. **CLD #4** — CI/CD pipeline (GitHub Actions for tests + Spinnaker for deploy) (3 days)

### Sprint 5-6 (weeks 5-6) — make it observable

15. **CLD #5** — CloudWatch metrics from token_tracker (2 days)
16. **CLD #6** — OpenTelemetry instrumentation + X-Ray export (3 days)
17. **FIX #15** — ChromaDB persistence to S3 (3 days)
18. **FIX #16** — structured routing logs (1 day)

### Sprint 7-8 (weeks 7-8) — make it secure and resilient

19. **CLD #7** — DynamoDB hot path + S3 cold storage (3 days)
20. **CLD #8** — auto-scaling policies (1 day)
21. **CLD #9** — multi-AZ deployment + ALB health checks (1 day)
22. **CLD #10** — WAF + IP allowlist (1 day)
23. **CLD #11** — PII redaction in logs and traces (2 days)
24. **CLD #12** — audit log of writes to S3 (1 day)
25. **FIX #0.6** — encrypt user conversations (2 days)

### Pre-D — Dual-mode bridge (1 day, mandatory before Sprint 9)

25b. **FIX #38** — Dual-mode deployment scaffolding. Apply BEFORE starting Phase D / Sprint 9. Mandatory precondition for FIX #19 (Flask→FastAPI) and any future CLD fix that introduces an AWS dependency. Adds a single `deployment.mode` flag (`local` | `cloud`) plus `observability/` module that dispatches to `init_local_observability()` or `init_cloud_observability()` based on the flag. Without this, every subsequent fix has to retrofit cloud-aware code paths after the fact.

### Sprint 9-13 (weeks 9-13) — polish and cleanup

26. **FIX #19**, **#20**, **#21** — Flask → FastAPI migration (2 weeks)
27. **FIX #23**, **#24**, **#25** — dashboard split into static assets (1 week)
28. **FIX #18**, **#37** — MCP packaging cleanup (3 days)
29. **FIX #11**, **#12** — operation_model RAG + auto-refresh (3 days)
30. **FIX #13** — critique_mode tool validation (3 days)
31. Rest of P1 fixes (FIX #3–9, #14)

### Sprint 14-26 (weeks 14-26) — enterprise polish

32. **CLD #13** — cross-region DR (2 weeks)
33. **CLD #14** — cost allocation tags + chargeback (1 week)
34. **CLD #15** — SLO dashboards + error budget alerting (1 week)
35. **FIX #8** — Sonnet 4 A/B rollout (2 weeks staggered)
36. All P2 fixes (FIX #28–36)
37. Multi-tenant onboarding flow (`carson onboard` CLI) (3 weeks)

---

# Tier 0 — Architectural P0 fixes (2026-04-26 audit)

These are the most expensive issues. They produce the visible bugs (loop guard firing, retries inconsistent, dashboard cost spike) but the root cause is structural. Each is a multi-day fix done properly, but the pay-off is that several other findings disappear automatically.

---

## FIX #0.1 — Proxy and environment hardcoded in carson_service.py

**Priority**: P0 · **Tier**: 0 · **File**: `langgraph-system/carson_service.py`, lines 27-35

### Problem

Proxy URL, no_proxy list, and `PYNETA_PROFILE` are hardcoded in source. Six lines for the same value (case-duplicated `HTTPS_PROXY`/`https_proxy`/etc.) is error-prone. Carson **already has a config system** (`config.py` + `config.yaml` + `CARSON_CONFIG` env var), but the proxy block doesn't use it. The VSCode extension even has a button `carson.fixProxy` because environments break frequently — a config-driven approach would eliminate that whole UX.

### Current

```python
os.environ['HTTPS_PROXY'] = 'http://proxy.jpmchase.net:10443'
os.environ['https_proxy'] = 'http://proxy.jpmchase.net:10443'
os.environ['HTTP_PROXY']  = 'http://proxy.jpmchase.net:10443'
os.environ['http_proxy']  = 'http://proxy.jpmchase.net:10443'
os.environ['NO_PROXY']    = '.jpmchase.net,.jpmorgan.com,localhost,127.0.0.1,10.*'
os.environ['no_proxy']    = '.jpmchase.net,.jpmorgan.com,localhost,127.0.0.1,10.*'
os.environ['PYNETA_PROFILE'] = 'local'
```

### Fixed

In `config.yaml`:

```yaml
network:
  proxy_url: "http://proxy.jpmchase.net:10443"
  no_proxy: ".jpmchase.net,.jpmorgan.com,localhost,127.0.0.1,10.*"
  pyneta_profile: "local"
```

In `carson_service.py`:

```python
from carson_agents.config import get_config

_net = get_config().get("network", {})
_proxy = os.environ.get("CARSON_PROXY_URL", _net.get("proxy_url"))
_no_proxy = os.environ.get("CARSON_NO_PROXY", _net.get("no_proxy"))
_pyneta = os.environ.get("CARSON_PYNETA_PROFILE", _net.get("pyneta_profile", "local"))

if _proxy:
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[var] = _proxy
if _no_proxy:
    os.environ["NO_PROXY"] = _no_proxy
    os.environ["no_proxy"] = _no_proxy
os.environ["PYNETA_PROFILE"] = _pyneta
```

### Justification

Single source of truth, env-var override, eliminates case-duplication bug, aligns with `config_template.yaml` (FIX #7) for new-team onboarding.

### Verification

1. `CARSON_PROXY_URL=http://test-proxy:8080` overrides config — confirm via printed `os.environ['HTTPS_PROXY']`.
2. Remove `network:` from config.yaml; expect a startup warning, not a crash.

### Cloud impact

When Carson runs in AWS (CLD #2), there is no JPMC corporate proxy. The proxy_url should default to empty/null in cloud config; outbound traffic uses the VPC's NAT gateway. This fix is a precondition for clean AWS deployment.

---

## FIX #0.2 — Three parallel orchestration systems for the same agent pool

**Priority**: P0 · **Tier**: 0
**Files**: `workflow.py`, `orchestrator.py`, `autonomous_langgraph.py`, `agent_state.py`

### Problem

Three distinct LangGraph orchestration layers, each with its own state schema:

| File | Schema | Pattern | Persistence |
|---|---|---|---|
| `workflow.py` (325 lines) | `CarsonState` | planner → router → agent → critic | None (caller-managed) |
| `orchestrator.py` | `AgentState` (inline) | "Strands-like Supervisor" | `MemorySaver` (in-memory) |
| `autonomous_langgraph.py` | `AutonomousState` (inline) | clone → generate → commit → PR | `MemorySaver` (in-memory) |

The autonomous file's docstring literally says: *"Now built on LangGraph for unified architecture with the Orchestrator"* — meaning the team **knows** this is duplicate. The unification is half done.

State capabilities **diverge**:

- `CarsonState` has critique fields, no HITL.
- `AgentState` has HITL fields, no critique.
- `AutonomousState` has neither, but adds workspace/repo state.

### Fixed (multi-step migration)

**Step 1**: Promote `agent_state.py`'s `CarsonState` to a single union schema (all fields optional):

```python
class CarsonState(CarsonStateRequired, total=False):
    """Unified state across all orchestration patterns."""

    # ── Identity ──
    user_sid: Optional[str]
    session_id: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    final_response: Optional[str]

    # ── Original request ──
    original_user_request: Optional[str]
    context: Optional[dict]

    # ── Router output ──
    force_agent: Optional[str]
    intent: Optional[str]
    intent_category: Optional[str]                  # NEW — from FIX #26
    current_agent: Optional[str]

    # ── Agent output ──
    agent_response: Optional[str]                   # MUST be str, never dict
    tool_results_collected: Optional[List[Dict[str, Any]]]
    rag_context: Optional[str]
    agent_outputs: Optional[Dict[str, Any]]
    retry_count: Optional[int]

    # ── Critique loop ──
    critique_verdict: Optional[Literal["APPROVE", "RETRY", "REJECT", "UNKNOWN"]]
    critique_attempts: Optional[int]
    critique_feedback: Optional[str]
    critique_evaluation: Optional[Dict[str, Any]]
    critique_history: Optional[List[Dict[str, Any]]]

    # ── Confirmation ──
    confirmation_required: Optional[str]
    confirmed: Optional[bool]

    # ── Planning ──
    needs_planning: Optional[bool]
    plan: Optional[List[str]]
    plan_index: Optional[int]

    # ── Human-in-the-loop ──
    waiting_for_human: Optional[bool]
    human_action_required: Optional[str]
    human_approved: Optional[bool]
    jira_ticket: Optional[str]

    # ── Autonomous coding ──
    job_id: Optional[str]
    ticket_id: Optional[str]
    ticket_summary: Optional[str]
    request: Optional[str]
    repo_name: Optional[str]
    bitbucket_project: Optional[str]
    branch_name: Optional[str]
    workspace_path: Optional[str]
    cloned: Optional[bool]

    # ── Distributed tracing ──
    trace_id: Optional[str]                         # NEW — from CLD #6
    parent_span_id: Optional[str]
```

**Step 2**: Pick `orchestrator.py`'s supervisor pattern as the survivor (scales better to 25 agents). Rename it to `unified_workflow.py`.

**Step 3**: Migrate `workflow.py`'s critic loop into the supervisor as a routing branch:

```
supervisor decides:
  ├── direct → agent (simple/single)
  ├── plan → plan_executor → agent (multi-step)
  └── critic_loop → agent → critic → (retry?) → END
```

**Step 4**: Migrate `autonomous_langgraph.py` into a sub-graph invoked when `intent == "autonomous_coding"`.

**Step 5**: Replace `MemorySaver` with `SqliteSaver` writing to `carson_data/(SID)/threads/<thread_id>.db`. Restart-safe HITL and autonomous-job state become real.

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string(
    f"carson_data/{user_sid}/threads/{thread_id}.db"
)
graph = workflow.compile(checkpointer=checkpointer)
```

**Cloud step**: When Carson moves to AWS, `SqliteSaver` becomes `PostgresSaver` (RDS) for multi-instance state sharing. See CLD #7.

**Step 6**: Delete `workflow.py` and `autonomous_langgraph.py`. Update all imports.

### Verification

1. Step 1: existing tests pass against unified `CarsonState`.
2. Step 2-3: smoke-test critic-driven request, confirm `critique_attempts` increments.
3. Step 5: restart Carson mid-HITL flow, confirm pending approval recoverable.
4. Step 6: `grep -r "from .workflow import"` returns no hits.

---

## FIX #0.3 — Dashboard polls Bedrock on a timer

**Priority**: P0 · **Tier**: 0 · **File**: `langgraph-system/carson_agents/templates/dashboard.html`, line ~2896

### Problem

```javascript
// Auto-refresh every 30 seconds (reduced from 5s to save Bedrock calls)
setInterval(refresh, 30000);
```

Every browser tab pays for LLM calls indefinitely. The "reduced from 5s" comment confirms cost surprise. The dashboard should never invoke the LLM at refresh time — `token_tracker.py` already has all the metrics in memory.

### Fixed

**Step 1**: Add a metrics endpoint reading from the existing tracker:

```python
# langgraph-system/carson_agents/blueprints/metrics.py
from flask import Blueprint, jsonify
from ..token_tracker import get_token_tracker

metrics_bp = Blueprint("metrics", __name__)

@metrics_bp.route("/api/metrics", methods=["GET"])
def metrics():
    """Lightweight stats from in-memory token tracker. NO LLM call."""
    return jsonify(get_token_tracker().get_stats())
```

**Step 2**: Replace dashboard polling with `/api/metrics` fetch (5s interval is fine — no LLM in path).

**Step 3 (long-term)**: Replace polling with Server-Sent Events for true push-based updates. See CARSON_DASHBOARD.md for SSE architecture.

**Step 4 (cloud-aware)**: In AWS, also stream metrics to CloudWatch (CLD #5) and X-Ray (CLD #6) for centralised observability.

### Verification

1. Open dashboard, confirm Bedrock token usage in `token_tracker.get_stats()` does NOT increase while tab idle.
2. Trigger an agent run; metrics update within polling interval.
3. After SSE migration: zero polling traffic, instant updates on agent events.

---

## FIX #0.4 — Workflow loop guard at 100 steps masks routing bugs

**Priority**: P0 · **Tier**: 0 · **File**: `workflow.py`, lines 30 + 66-68

### Problem

```python
MAX_WORKFLOW_STEPS = 100
if step > MAX_WORKFLOW_STEPS:
    raise RuntimeError(f"Workflow exceeded {MAX_WORKFLOW_STEPS} steps - likely infinite loop")
```

Aborts at step 100 — costs ~100 LLM calls per failure. Root cause is FIX #0.2 (state mismatches between orchestrators) plus FIX #26 (25-agent flat registry).

### Fixed

Replace catch-all step counter with explicit cycle detection per (agent, intent) pair:

```python
class _CycleDetector:
    def __init__(self):
        self.visits: dict[tuple[str, str], int] = {}
        self.history: list[tuple[str, str]] = []

    def visit(self, node: str, intent: str | None):
        key = (node, intent or "")
        self.visits[key] = self.visits.get(key, 0) + 1
        self.history.append(key)

    def should_abort(self) -> tuple[bool, str | None]:
        for k, v in self.visits.items():
            if v > 3:
                return True, f"node={k[0]} intent={k[1]} visited {v} times"
        if len(self.history) > 100:
            return True, f"hard ceiling: {len(self.history)} total steps"
        return False, None
```

Aborts at ~step 12 instead of 100 — saves ~88 LLM calls per failure. Error message names offending (node, intent) pair.

### Verification

1. Force a cycle; confirm new exception names node and prints history.
2. Existing tests pass.
3. Add a regression test: state with `intent` not in `AGENT_REGISTRY`, confirm termination within 4 visits.

---

## FIX #0.5 — Critic retry budget disagrees with itself across files

**Priority**: P0 · **Tier**: 0
**Files**: `workflow.py` (line ~120), `critic_node.py` (line 21 + docstring line 9)

### Problem

Three sources, three different limits:

- `workflow.py`: `if verdict == "RETRY" and attempts < 10:`
- `critic_node.py` line 21: `MAX_CRITIQUE_LOOPS = 3  # (reduced from 10 to avoid excessive LLM calls)`
- `critic_node.py` docstring: `"Supports up to 10 reflection loops for maximum quality."`

### Fixed

**Step 1**: Single config-loaded constant in `config.py`:

```python
def get_max_critique_loops() -> int:
    return get_config().get("feedback", {}).get("max_critique_loops", 3)
```

In `config.yaml`:

```yaml
feedback:
  critique_mode: "always_with_tool_validation"   # see FIX #13
  max_critique_loops: 3
  min_quality_score: 7
```

**Step 2**: Both files import from config:

```python
from .config import get_max_critique_loops
# delete hardcoded MAX_CRITIQUE_LOOPS
# replace `< 10` with `< get_max_critique_loops()`
```

**Step 3**: Add stagnation check — if last two retries produced near-identical responses, stop:

```python
def _retries_stagnated(state: CarsonState) -> bool:
    history = state.get("critique_history") or []
    if len(history) < 2:
        return False
    last = history[-1].get("agent_response", "")
    prev = history[-2].get("agent_response", "")
    if not last or not prev:
        return False
    common = len(set(last.split()) & set(prev.split()))
    total = max(len(set(last.split())), len(set(prev.split())))
    return total > 0 and common / total > 0.9
```

### Verification

1. `grep -rn "MAX_CRITIQUE_LOOPS\|attempts <"` shows only `get_max_critique_loops()` references.
2. Set `feedback.max_critique_loops: 1`; trigger RETRY; confirm only one retry.
3. Regression: critic returns RETRY but agent returns same response twice; confirm stagnation triggers within 2 attempts.

---

## FIX #0.6 — Git used as a peer-to-peer database for conversations

**Priority**: P0 (privacy) · **Tier**: 0
**Files**: `headquarters.py` + `persistence.py`

### Problem

Each user's local Carson auto-commits conversations to `carson/data` branch every 5 min and pulls from peers every 2 min. **Privacy concern**: every user with repo read access sees every other user's conversations. Plus operational concerns (Bitbucket load, repo bloat, JSON merge conflicts, cross-OS hostility).

### Fixed (phased)

**Short term (week 1) — encryption at rest in git**:

```python
# persistence.py
import json
from cryptography.fernet import Fernet
from pathlib import Path

def _get_user_key(user_sid: str) -> bytes:
    """Per-user encryption key, stored locally, NOT in git."""
    key_path = Path.home() / ".carson" / f"{user_sid}.key"
    key_path.parent.mkdir(exist_ok=True, mode=0o700)
    if not key_path.exists():
        key_path.write_bytes(Fernet.generate_key())
    return key_path.read_bytes()

def write_record(user_sid: str, path: Path, data: dict):
    fernet = Fernet(_get_user_key(user_sid))
    path.write_bytes(fernet.encrypt(json.dumps(data).encode()))

def read_record(user_sid: str, path: Path) -> dict | None:
    try:
        fernet = Fernet(_get_user_key(user_sid))
        return json.loads(fernet.decrypt(path.read_bytes()))
    except Exception:
        return None
```

**Long term (Sprint 5+) — replace git with proper persistence**:

When Carson is in AWS (CLD #7), per-user threads live in DynamoDB partitioned by `user_sid`, with KMS-encrypted column-level fields for sensitive content. Each user's IAM role allows access only to their own partition. The git-data-branch sync is retired entirely.

**Cross-OS portability**:

```python
import getpass
USER_SID = os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser() or "unknown"
```

**One-time history cleanup**: After encryption rolls out, schedule `git filter-repo` to scrub plaintext history from `carson/data` branch.

### Verification

1. Encryption: clone repo as a different user, open peer's JSON; should be opaque ciphertext.
2. Own conversations still readable.
3. Cross-OS: empty `USERNAME` and `USER`; `USER_SID` falls back to `getpass.getuser()`.
4. Post-cloud migration: `git log carson/data` shows the branch retired.

---

# Tier 1 — Concrete bugs (2026-04-14)

Five fixes, high impact, ready to apply.

---

## FIX #1 — Datadog/Rocky agent invisible to the router

**Priority**: P0 · **Tier**: 1 · **File**: `langgraph-system/config.yaml`, line ~103

### Problem

Rocky (Datadog) exists as `.agent.md` and is in the inventory but NOT in `config.yaml`. The router never includes it as a candidate.

### Fixed

```yaml
  # Observability / operational agents
  datadog:
    enabled: true        # Rocky — Datadog metrics & alerts
  gossip:
    enabled: false       # TODO: confirm if used
  teams:
    enabled: false       # TODO: confirm if MS Teams agent ready
```

### Verification

Run query "check the latency metrics for the AHTW service"; router selects `datadog` not `general`.

---

## FIX #2 — `.hcl` and `.tfvars` missing from `repo_code` RAG extensions

**Priority**: P0 · **Tier**: 1 · **File**: `config.yaml`, line ~149

### Problem

Filter does not include `.hcl` or `.tfvars`. Sentinel policies and Terraform variable files are not indexed.

### Fixed

```yaml
      repo_code:
        source: team_repos
        extensions: [".py", ".md", ".yaml", ".yml", ".xml", ".tf", ".tfvars", ".hcl", ".json"]
```

### Verification

Re-ingest, then:

```python
kb._get_client().get_collection("repo_code_ahtw").get(where={"extension": ".hcl"})
# Should return matches
```

---

## FIX #3 — Error handling in `send_carson_reply.py`

**Priority**: P1 · **Tier**: 1 · **File**: `langgraph-system/send_carson_reply.py`

### Problem

`OutlookCOMClient()` and `client.send_email()` have no try/except. Crashes with stacktrace if Outlook closed.

### Fixed

```python
import logging

logger = logging.getLogger(__name__)

def send_reply(session_id, topic, response, user_email=None):
    """Send a Carson reply via Outlook COM. Returns True/False for success."""
    to_address = user_email or DEFAULT_REPLY_EMAIL  # FIX #5
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
        logger.error(f"Outlook send_email failed for session {session_id}, to={to_address}: {e}")
        return False
```

### Verification

Run with Outlook closed — no crash, returns `False`, log shows error.

---

## FIX #4 — `fix_chromadb.py` passes `config={}` and bypasses config.yaml

**Priority**: P1 · **Tier**: 1 · **File**: `langgraph-system/fix_chromadb.py`

### Problem

`CarsonKnowledgeBase(persist_dir="./carson_kb", config={})` — empty config means health_check evaluates wrong collections.

### Fixed

```python
import yaml
from pathlib import Path
from carson_agents.rag.knowledge_base import CarsonKnowledgeBase

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_runtime_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"config.yaml not found at {CONFIG_PATH}. "
            "Run from langgraph-system/ directory."
        )
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)

def main(dry_run=False):
    config = load_runtime_config()
    persist_dir = config.get("rag", {}).get("persist_dir", "./carson_kb")
    kb = CarsonKnowledgeBase(persist_dir=persist_dir, config=config)
    result = kb.health_check()
```

### Verification

`python fix_chromadb.py --dry` lists all 7 configured collections (4 global + 3 team), not just physically present ones.

---

## FIX #5 — Email hardcoded → move to config.yaml

**Priority**: P1 · **Tier**: 1
**Files**: `config.yaml` + `send_carson_reply.py`

### Problem

`send_carson_reply.py` defaults to `martin.garciatejeda@jpmchase.com`. Onboarding new user requires code edit.

### Fixed

In `config.yaml`:

```yaml
notifications:
  default_reply_email: "martin.garciatejeda@jpmchase.com"
  reply_subject_format: "[Carson:{session_id}] Re: {topic}"
  reply_footer: "Sent via Carson (Copilot Mode)"
```

In `send_carson_reply.py`:

```python
import yaml
from pathlib import Path

_CONFIG_CACHE = None

def _load_config() -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        with open(Path(__file__).parent / "config.yaml") as f:
            _CONFIG_CACHE = yaml.safe_load(f)
    return _CONFIG_CACHE

def _get_default_email() -> str:
    notif = _load_config().get("notifications", {})
    email = notif.get("default_reply_email")
    if not email:
        raise ValueError(
            "notifications.default_reply_email not set in config.yaml "
            "and no user_email provided"
        )
    return email

def send_reply(session_id, topic, response, user_email=None):
    to_address = user_email or _get_default_email()
    # ... rest with FIX #3 try/except ...
```

### Verification

1. Comment out `default_reply_email` and call without `user_email` → fails with clear error.
2. Restore and call without → uses config value.

---

# Tier 2 — Config consistency (2026-04-14)

---

## FIX #6 — Reconcile knowledge-only vs tool-equipped agents

**Priority**: P1 · **Tier**: 2

The comment in `config.yaml` says "Knowledge-only agents (no MCP tools)" listing bob/hydra/cbb/pixie/studio/sdlc, but `sdlc.agent.md` and `bob.agent.md` reference MCP servers and tools. Routing decisions are based on this contradiction.

### Steps

**A**: Verify `ls ../mcp-servers/ | grep -E "sdlc|bob|hydra|cbb|pixie|studio"`.

**B**: If MCP server exists, regroup in `config.yaml`:

```yaml
  # Tool-equipped specialist agents
  bob:
    enabled: true       # Big Orange Button — bob-mcp-server
  sdlc:
    enabled: true       # SDLC compliance — sdlc-mcp-server
  hydra:
    enabled: true
  cbb:
    enabled: true
  pixie:
    enabled: true
  studio:
    enabled: true
```

**C**: For agents WITHOUT MCP server, delete false tool tables from `.agent.md`.

---

## FIX #7 — Sync `config_template.yaml` with `config.yaml`

**Priority**: P1 · **Tier**: 2 · **File**: `langgraph-system/config_template.yaml`

Template missing 13+ agents, performance section, feedback section, `routing_model_arn`, `embedding_model_arn`, `confluence_pages`, `team_id`, RAG extensions. New team `cp template` starts broken.

Replace with the comprehensive template (see full content in [original CARSON_TIER2_FIXES.md](./CARSON_TIER2_FIXES.md)). Key sections: `team_name`, `confluence_pages`, `aws`, `network` (FIX #0.1), `llm` (with placeholders), full agent list, `rag` with proper extensions, `performance`, `feedback`, `notifications`, `service`.

### Verification

A new team can `cp config_template.yaml config.yaml`, fill `YOUR_*`, and start without further code changes.

---

## FIX #8 — Upgrade model (Sonnet 3.5 → Sonnet 4) — A/B rollout

**Priority**: P2 · **Tier**: 2

```yaml
llm:
  main_model: "anthropic.claude-3-5-sonnet-20241022-v2:0"           # current
  experimental_main_model: "anthropic.claude-sonnet-4-20250514-v1:0"  # new
  experimental_rollout_percentage: 10
```

Code:

```python
import random

def get_main_model_id() -> str:
    cfg = config["llm"]
    if cfg.get("experimental_main_model"):
        if random.randint(1, 100) <= cfg.get("experimental_rollout_percentage", 0):
            return cfg["experimental_main_model"]
    return cfg["main_model"]
```

Scale 10% → 50% → 100% based on quality, latency, cost.

---

## FIX #9 — Add missing fields (`default_bitbucket_project`, `is_execution_role`)

**Priority**: P1 · **Tier**: 2

```yaml
aws:
  role_arn: "arn:aws:iam::YOUR_ACCOUNT:role/YOUR_ROLE"
  region: "us-east-1"
  is_execution_role: false

default_bitbucket_project: "ACAMPS"
```

Startup assertion in `carson_service.py`:

```python
assert "default_bitbucket_project" in config
assert "is_execution_role" in config.get("aws", {})
```

---

# Tier 3 — Functionality (2026-04-14)

---

## FIX #10 — Raise `max_rag_context_tokens` from 2000 to 4000

**Priority**: P1 · **Tier**: 3

```yaml
performance:
  max_rag_context_tokens: 4000
```

Sonnet 3.5 has 200K context — 4000 is 2% of window.

---

## FIX #11 — Create `operation_model` RAG collection

**Priority**: P1 · **Tier**: 3

```yaml
rag:
  team_collections:
    operation_model:
      description: "Operating Model (team ops & processes)"
      source: confluence
      page_id: "2538506858"
      refresh_interval_hours: 24
```

Run `python -m carson_agents.kb_auto_ingest --collection operation_model`.

---

## FIX #12 — Auto-refresh RAG (staleness mechanism)

**Priority**: P1 · **Tier**: 3

```yaml
rag:
  refresh:
    enabled: true
    default_interval_hours: 24
    staleness_warning_hours: 48

  global_collections:
    modules:
      refresh_interval_hours: 168   # weekly
  team_collections:
    repo_code:
      refresh_interval_hours: 6     # 4× daily
    ahtw_confluence:
      refresh_interval_hours: 24
```

New script `autonomous_jobs/rag_refresh.py` (see Tier 3 original for full code). Scheduled via cron / Spinnaker / **EventBridge in cloud** (CLD #7).

---

## FIX #13 — `critique_mode: "always_with_tool_validation"` for tool agents

**Priority**: P1 · **Tier**: 3

```yaml
feedback:
  critique_mode: "always_with_tool_validation"
  max_critique_loops: 3
  min_quality_score: 7

  tool_agent_validation:
    enabled: true
    check_tool_call_success: true
    check_response_references_tool_output: true
    require_links_for_resources: true
```

In `carson_service.py`:

```python
def validate_tool_agent_response(agent_name, tool_calls, response):
    for call in tool_calls:
        if call.get("error") or call.get("status") == "failed":
            return False, f"Tool call {call['name']} failed: {call.get('error')}"
    if tool_calls:
        tool_tokens = set()
        for c in tool_calls:
            tool_tokens.update(str(c.get("output", "")).split())
        if len(tool_tokens & set(response.split())) < 3:
            return False, "Response does not reference tool output"
    if agent_name in {"jira", "git", "snow", "postman"}:
        if not any(s in response.lower() for s in ["http://", "https://", "url:"]):
            return False, f"{agent_name} should return a link"
    return True, "OK"
```

---

## FIX #14 — `max_tokens` per agent (planner needs 8192)

**Priority**: P1 · **Tier**: 3

```yaml
performance:
  max_tokens: 4096
  max_tokens_per_agent:
    planner: 8192
    terraform: 6144
    docs: 6144
    coder: 8192      # NEW — autonomous coding agent (FIX #14b)
```

```python
def get_max_tokens_for(agent_name: str) -> int:
    perf = config["performance"]
    return perf.get("max_tokens_per_agent", {}).get(agent_name, perf["max_tokens"])
```

---

# Tier 4 — Infrastructure & observability (2026-04-14)

---

## FIX #15 — ChromaDB persistence to S3

**Priority**: P1 · **Tier**: 4

Architecture: ChromaDB local + S3 sync at startup/shutdown + 6-hour snapshots, 30-day retention.

```yaml
rag:
  s3_backup:
    enabled: true
    bucket: "carson-kb-${TEAM_ID}"
    prefix: "chroma/"
    sync_on_startup: true
    sync_on_shutdown: true
    snapshot_interval_hours: 6
    snapshot_retention_days: 30
    aws_region: "us-east-1"
    kms_key_id: "${CARSON_KMS_KEY_ID}"      # NEW — encryption (CLD #3)
```

New module `langgraph-system/carson_agents/rag/s3_persistence.py` with `ChromaS3Persistence` class:

```python
import hashlib, logging, tarfile, tempfile
from datetime import datetime
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

class ChromaS3Persistence:
    def __init__(self, persist_dir, bucket, prefix="chroma/", region="us-east-1", kms_key_id=None):
        self.persist_dir = Path(persist_dir)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        self.s3 = boto3.client("s3", region_name=region)
        self.kms_key_id = kms_key_id
        self._last_hash = None

    def _hash_dir(self):
        h = hashlib.sha256()
        for p in sorted(self.persist_dir.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(self.persist_dir).as_posix().encode())
                h.update(str(p.stat().st_mtime_ns).encode())
                h.update(str(p.stat().st_size).encode())
        return h.hexdigest()

    def _tar_and_upload(self, s3_key):
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            with tarfile.open(tmp.name, "w:gz") as tar:
                tar.add(self.persist_dir, arcname=self.persist_dir.name)
            extra = {"ServerSideEncryption": "aws:kms"} if self.kms_key_id else {}
            if self.kms_key_id:
                extra["SSEKMSKeyId"] = self.kms_key_id
            self.s3.upload_file(tmp.name, self.bucket, s3_key, ExtraArgs=extra)

    def sync_from_s3(self):
        try:
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                self.s3.download_file(self.bucket, f"{self.prefix}latest/carson_kb.tar.gz", tmp.name)
                with tarfile.open(tmp.name, "r:gz") as tar:
                    tar.extractall(self.persist_dir.parent)
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def sync_to_s3(self, force=False):
        h = self._hash_dir()
        if not force and h == self._last_hash:
            return False
        self._tar_and_upload(f"{self.prefix}latest/carson_kb.tar.gz")
        self._last_hash = h
        return True

    def snapshot(self):
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        self._tar_and_upload(f"{self.prefix}snapshots/{ts}/carson_kb.tar.gz")

    def cleanup_old_snapshots(self, retention_days):
        # ... see CARSON_TIER4_FIXES.md for full implementation
        pass
```

IAM permissions on the Carson ECS execution role (CLD #2):

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::carson-kb-*",
    "arn:aws:s3:::carson-kb-*/*"
  ]
}
```

Plus `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey` on the team's KMS key.

---

## FIX #16 — Structured logging of routing decisions

**Priority**: P1 · **Tier**: 4

```python
router_logger = logging.getLogger("carson.routing")

def route_query(query, available_agents):
    decision = RoutingDecision(...)
    router_logger.info(json.dumps({
        "event": "routing_decision",
        "query": query[:500],
        "query_length": len(query),
        "selected_agent": decision.selected_agent,
        "confidence": decision.confidence,
        "alternatives": decision.alternatives,
        "reasoning": decision.reasoning,
        "latency_ms": decision.latency_ms,
        "available_agents_count": len(available_agents),
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": current_trace_id(),         # CLD #6 — link to X-Ray
        "span_id": current_span_id(),
    }))
    return decision
```

In cloud (CLD #5), these logs go to CloudWatch Logs and are aggregated into:
- `carson.routing.confidence` metric (avg, p50, p95)
- `carson.routing.uncertain_rate` (queries with confidence < 0.6)
- `carson.routing.latency` (p50, p95, p99)

---

## FIX #17 — Validate Bedrock inference profile ARNs at startup

**Priority**: P0 · **Tier**: 4

Standalone script `langgraph-system/scripts/validate_bedrock_config.py` checks `routing_model_arn`, `embedding_model_arn`, `main_model`, and `aws.role_arn`. Returns non-zero on validation failure.

In `config.yaml`:

```yaml
service:
  validate_aws_config_on_startup: true
```

In `carson_service.py`:

```python
if config["service"].get("validate_aws_config_on_startup"):
    from scripts.validate_bedrock_config import main as validate_bedrock
    try:
        validate_bedrock()
    except SystemExit:
        logger.critical("AWS config validation failed — refusing to start")
        raise
```

In CI/CD (CLD #4): also run this script in the Spinnaker deploy pipeline as a pre-deploy gate.

---

# Tier 5 — Additional findings (2026-04-26 deep audit)

---

## FIX #18 — MCP servers share `source/` package; sys.modules monkey-patch

**Priority**: P1 · **Tier**: 5

```python
# mcp_loader.py current hack:
def _clear_source_cache():
    to_remove = [n for n in sys.modules if n == 'source' or n.startswith('source.')]
    for n in to_remove:
        del sys.modules[n]
```

### Fixed

For each `mcp-servers/<name>-mcp-server-python/`:

1. Rename folder `source/` → `<name>_mcp/`.
2. Add `pyproject.toml`:

```toml
[project]
name = "<name>-mcp-server"
version = "0.1.0"

[tool.setuptools.packages.find]
include = ["<name>_mcp*"]
```

3. Update internal imports.
4. `pip install -e mcp-servers/<name>-mcp-server-python`.

Replace `_clear_source_cache()` with normal imports:

```python
from jira_mcp import JiraClient
client = JiraClient()
```

Delete `mcp_loader.py`'s cache-clearing code.

---

## FIX #19 — Flask + FastAPI both in production deps

**Priority**: P1 · **Tier**: 5

Migrate Flask blueprints to FastAPI routers. FastAPI has native SSE (FIX #0.3 dashboard), automatic OpenAPI docs (FIX #20), better async story.

Migration pattern:

```python
# Before (Flask):
from flask import Blueprint, request, jsonify
jobs_bp = Blueprint("jobs", __name__)
@jobs_bp.route("/ask/async", methods=["POST"])
def ask_async():
    return jsonify({"job_id": "..."})

# After (FastAPI):
from fastapi import APIRouter
from pydantic import BaseModel

class AskAsyncRequest(BaseModel):
    request: str
    user_sid: str = "unknown"

class AskAsyncResponse(BaseModel):
    job_id: str
    status: str

jobs_router = APIRouter()

@jobs_router.post("/ask/async", response_model=AskAsyncResponse)
async def ask_async(body: AskAsyncRequest):
    return AskAsyncResponse(job_id="...", status="pending")
```

In `carson_service.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Carson AI Butler", version="2.0")

from carson_agents.dashboard import dashboard_router
from carson_agents.blueprints.jobs import jobs_router
# ... 11 routers ...

app.include_router(dashboard_router)
app.include_router(jobs_router)
```

Remove `flask`, `flask-cors` from `requirements.txt`. Add `uvicorn[standard]>=0.27`. Update launch scripts.

---

## FIX #20 — Eleven Flask blueprints, docstring lists six endpoints

**Priority**: P1 · **Tier**: 5

After FIX #19: FastAPI auto-generates `/docs` (Swagger UI) and `/redoc`. Delete the misleading docstring.

If FIX #19 not yet applied: auto-dump endpoints in CI:

```python
# scripts/dump_endpoints.py
from carson_service import app
with app.test_request_context():
    for rule in app.url_map.iter_rules():
        methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
        print(f"{methods} {rule.rule}")
```

Commit `docs/endpoints.md`. CI fails if dump differs from committed file.

---

## FIX #21 — `sys.path` manipulation with hardcoded relative paths

**Priority**: P1 · **Tier**: 5

Solved by FIX #18 (proper packaging). After: no agent needs `MCP_BASE`, no `sys.path.insert`. Imports are clean.

---

## FIX #22 — No dependency lock file

**Priority**: P1 · **Tier**: 5

```bash
pip install pip-tools
# Create requirements.in with current human-readable deps
pip-compile requirements.in --output-file requirements.txt --resolver=backtracking
```

Commit both. CI: `pip-compile --check requirements.in` fails build if drift.

Alternative for cloud-native: migrate to `uv` (faster) for both local dev and Docker build (CLD #1).

---

## FIX #23 — Dashboard 130 KB monolith with embedded HTML/CSS/JS

**Priority**: P1 · **Tier**: 5

See `CARSON_DASHBOARD.md` for full split design. Summary:

```
langgraph-system/carson_agents/dashboard/    (replaces templates/dashboard.html + dashboard.py)
├── __init__.py
├── routes.py             FastAPI router · /dashboard · /api/* · /sse
├── db.py                 SQLite mirror of token_tracker for history
├── stream.py             SSE event bus (in-memory pub/sub)
├── instrumentation.py    LangGraph callback → bus
└── static/
    ├── index.html        ~5 KB shell only
    ├── dashboard.css     ~30 KB, all styles split out
    └── dashboard.js      ~50 KB, modular, hash router, SSE client
```

---

## FIX #24 — `render_template_string` for static 130 KB template

**Priority**: P1 · **Tier**: 5

After FIX #19 + #23:

```python
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

@dashboard_router.get("/dashboard", include_in_schema=False)
async def dashboard():
    return FileResponse(STATIC_DIR / "index.html")

# In carson_service.py:
app.mount("/dashboard/static", StaticFiles(directory=str(STATIC_DIR)), name="dashboard_static")
```

CPU per request drops from ~30 ms (Jinja parse 130 KB) to <1 ms (file send). Browser caches via ETag.

---

## FIX #25 — Mixed CSS design systems

**Priority**: P1 · **Tier**: 5

Standardize on Salt tokens. Map `--jpmc-*` to Salt equivalents. Replace raw hex with semantic tokens. Add stylelint to ban raw hex outside the tokens file.

---

## FIX #26 — 25-agent flat registry without category split

**Priority**: P0 · **Tier**: 5

Replace flat dict with typed registry:

```python
# carson_agents/agents/registry.py
from dataclasses import dataclass
from typing import Callable, Literal

AgentCategory = Literal[
    "devops_tools",
    "athena_knowledge",
    "autonomous_coding",
    "notifications",
    "observability",
]

@dataclass
class AgentEntry:
    id: str
    name: str
    category: AgentCategory
    node: Callable
    has_tools: bool
    description: str
    deprecated: bool = False

REGISTRY: dict[str, AgentEntry] = {
    "jira": AgentEntry(
        id="jira", name="Comptroller Jira", category="devops_tools",
        node=jira_agent_node, has_tools=True,
        description="Tickets, sprints, status, comments",
    ),
    "git": AgentEntry(id="git", name="Mr. Brandson", category="devops_tools", ...),
    "build": AgentEntry(id="build", name="Mr. Jenkins", category="devops_tools", ...),
    # ... 22 more ...
    "terraform_compat": AgentEntry(
        id="terraform_compat", name="Monsieur Modulaire", category="devops_tools",
        node=terraform_compat_agent_node, has_tools=True,
        description="Compatibility checks, find module version",
        deprecated=True,
    ),
}

def get_by_category(cat: AgentCategory) -> dict[str, AgentEntry]:
    return {k: v for k, v in REGISTRY.items() if v.category == cat and not v.deprecated}

def get_active_ids() -> list[str]:
    return [k for k, v in REGISTRY.items() if not v.deprecated]

# Back-compat shim:
AGENT_REGISTRY = {k: v.node for k, v in REGISTRY.items() if not v.deprecated}
```

Update router to 2-stage classification:
1. Classify into category (5 options)
2. Within category, classify into specific agent (max 17 options for devops_tools)

Two-stage classification is far more reliable than 25-way.

---

## FIX #27 — Cache directories committed to git

**Priority**: P1 · **Tier**: 5

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/

# Carson caches
*_docs_cache/
chroma_db/
carson_kb/

# Per-user data
carson_data/

# Local env
.venv/
.env
*.local
```

```bash
git rm -r --cached \
  .pytest_cache __pycache__ \
  ace_docs_cache ascode_docs_cache bob_docs_cache \
  cdb_docs_cache chroma_db cloud_docs_cache controls_docs_cache

git commit -m "Carson: FIX #27 — untrack cache directories"
```

**Security audit**: scan `chroma_db/` for embeddings of sensitive content. If found, schedule `git filter-repo` rewrite.

---

## FIX #28-37 — Polish

Brief summary, full content in 2026-04-26 deep audit:

- **#28** Two extra `*salesdash.html` dashboards: consolidate into unified dashboard with route params.
- **#29** `onclick=` and `href="javascript:void(0)"`: replace with semantic `<button>` + addEventListener, hash-based `<a href="#/route">` for nav.
- **#30** Charts via innerHTML: rewrite using DOM APIs or Salt chart components.
- **#31** f-strings in `logger.debug`: convert to lazy `%s` formatting.
- **#32** Bare `except Exception` in `dashboard.py`: catch `FileNotFoundError` specifically.
- **#33** Default critique verdict `"APPROVE"` → `"REJECT"` with explicit handling for malformed critic output.
- **#34** Prompt duplication router/planner: extract to `prompts/specialist_table.md`, both load via `prompt_loader.py`.
- **#35** Action queue JSON file → SQLite-backed queue with WAL, atomic dequeue.
- **#36** `JobRecord` `result`/`response` duplicate: keep `response`, deprecation shim, one-shot migration script for existing JSONs.
- **#37** 4-level parent traversal: solved by FIX #18 (proper packaging).

---

## FIX #38 — Dual-mode deployment scaffolding

**Priority**: P1 · **Tier**: 5 (Bridge to Cloud)
**Files**:
- `langgraph-system/config.yaml` (add `deployment` + `observability` sections)
- `langgraph-system/carson_agents/observability/` (new module: `__init__.py`, `local.py`, `cloud.py`)
- `langgraph-system/carson_service.py` (init dispatch on startup)

### Problem

Carson is being modernised over multiple sprints. Every observability/persistence fix between now and "fully cloud" risks introducing AWS-only code paths that silently break local development. Without explicit dual-mode scaffolding, developers end up either testing only in cloud (losing local velocity) or scattering ad-hoc `if AWS_REGION:` checks across the codebase.

This fix is a precondition for clean execution of FIX #19 (Flask→FastAPI), FIX #23 (dashboard split), and any future Cloud (CLD) fix that introduces an AWS dependency.

### Current

There is no central `deployment.mode` flag. `carson_service.py` imports observability backends statically. Cloud-only modules (e.g. `CloudWatchExporter` from CLD #5) cannot be safely added without breaking local imports.

### Fixed

#### Step 1 — `config.yaml` additions

```yaml
deployment:
  mode: "local"              # local | cloud
  team_id: "ahtw"

observability:
  metrics_backend: "memory"      # memory | cloudwatch
  traces_backend: "console"      # console | xray | otlp
  logs_backend: "file"           # file | cloudwatch | stdout
  logs_path: "./carson.log"      # for file backend
  pii_redaction: true
  audit_log:
    enabled: true
    backend: "file"              # file | s3
    path: "./carson_data/audit/"
    bucket: ""                   # for s3 backend (empty in local mode)
```

`mode: "local"` is the default — existing local installs keep working unchanged. The flag is the only thing the cloud migration day needs to flip.

#### Step 2 — new module `langgraph-system/carson_agents/observability/`

`observability/__init__.py`:

```python
"""Dual-mode observability initialisation.

Reads deployment.mode from config.yaml and initialises the appropriate
backends. Local mode = in-memory + file. Cloud mode = CloudWatch + X-Ray.
"""
import logging
from ..config import get_config

logger = logging.getLogger(__name__)


def init_observability():
    cfg = get_config()
    mode = cfg.get("deployment", {}).get("mode", "local")
    logger.info(f"Initialising observability in '{mode}' mode")
    if mode == "cloud":
        from .cloud import init_cloud_observability
        init_cloud_observability(cfg)
    elif mode == "local":
        from .local import init_local_observability
        init_local_observability(cfg)
    else:
        raise ValueError(
            f"Unknown deployment.mode: {mode!r} (expected 'local' or 'cloud')"
        )
```

`observability/local.py`:

```python
"""Local mode: file logs, in-memory metrics, console traces."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_local_observability(cfg):
    obs = cfg.get("observability", {})
    logs_backend = obs.get("logs_backend", "file")

    if logs_backend == "file":
        logs_path = Path(obs.get("logs_path", "./carson.log"))
        logs_path.parent.mkdir(exist_ok=True, parents=True)
        handler = logging.FileHandler(str(logs_path))
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        ))
        logging.root.addHandler(handler)
        logger.info(f"Local logs → {logs_path}")
    elif logs_backend == "stdout":
        logging.basicConfig(level=cfg.get("logging", {}).get("level", "INFO"))

    # Metrics: token_tracker keeps stats in memory (default).
    # Traces: no exporter → spans are no-ops in production but available
    #         to console-print in dev via OTEL_TRACES_EXPORTER=console.
    # Audit: writes to file backend (handled by audit module reading the same config).
```

`observability/cloud.py`:

```python
"""Cloud mode: CloudWatch + X-Ray + OpenTelemetry."""
import logging
import os

logger = logging.getLogger(__name__)


def init_cloud_observability(cfg):
    if not os.environ.get("AWS_REGION"):
        raise RuntimeError(
            "deployment.mode=cloud requires AWS_REGION env var. "
            "Either set it (typical for ECS Fargate) or switch to mode=local."
        )

    team_id = cfg["deployment"]["team_id"]

    # Metrics: CloudWatchExporter from CLD #5 (only imported in cloud mode)
    if cfg["observability"].get("metrics_backend") == "cloudwatch":
        from .cw_exporter import CloudWatchExporter
        CloudWatchExporter(namespace=f"Carson/{team_id}", team_id=team_id).start()
        logger.info(f"CloudWatch metrics exporter started for Carson/{team_id}")

    # Traces: X-Ray via OpenTelemetry (CLD #6)
    if cfg["observability"].get("traces_backend") in ("xray", "otlp"):
        from .tracing import init_xray_tracing
        init_xray_tracing(team_id=team_id)
        logger.info("X-Ray distributed tracing initialised")
```

Files `cw_exporter.py` and `tracing.py` are added later by CLD #5 and CLD #6 respectively. They are intentionally absent in this fix — local installs do not need them. Imports of these modules are lazy (inside `init_cloud_observability()`) so a local install with `mode: "local"` does not need `boto3` or the OpenTelemetry SDK.

#### Step 3 — `carson_service.py` startup hook

Add at the top of `carson_service.py`, right after the proxy block (FIX #0.1) and before the FastAPI/Flask app construction:

```python
from carson_agents.observability import init_observability
init_observability()
```

#### Step 4 — `requirements.txt` split

Move cloud-only deps to a separate `requirements-cloud.txt` so local installs do not pull `boto3`, `opentelemetry-*`, etc.:

```
# requirements.txt (local-friendly base)
flask>=3.0.0
langgraph>=0.2.0
chromadb>=0.4.0
cdaosdk-all>=12.0.0
# ... rest of base deps ...

# requirements-cloud.txt (only when mode=cloud)
-r requirements.txt
boto3>=1.34.0
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp>=1.20.0
opentelemetry-propagator-aws-xray>=1.0.0
opentelemetry-sdk-extension-aws>=2.0.0
```

In the Dockerfile (CLD #1), install `requirements-cloud.txt` instead of `requirements.txt`.

### Justification

- **One flag, one decision.** Every future cloud-aware fix (FIX #19, #23, CLD #5, CLD #6, CLD #11, CLD #12) checks `deployment.mode` exactly once at the entry point — no scattered conditionals.
- **Local stays default.** `mode: "local"` is the out-of-box value; existing dev environments keep working without config changes.
- **Cloud migration is config-flip + IaC.** When the team goes to AWS, switching `mode: "cloud"` plus deploying the Terraform from CLD #2 is the entire migration. No code changes for cloud-aware modules.
- **Imports are lazy.** Cloud-only modules are imported inside `init_cloud_observability()`, never at module top-level. Local installs without `boto3` / OpenTelemetry keep working.
- **Testable in both modes.** Same `init_observability()` entry point. Test fixtures override `mode` per test (e.g. `pytest --deployment-mode=cloud` flips a session-scoped fixture).

### Verification

1. With `deployment.mode: "local"` (default):
   - Start Carson. Log line shows `Initialising observability in 'local' mode`.
   - Confirm `./carson.log` file is created and receives entries.
   - Confirm `token_tracker.get_stats()` returns in-memory data.

2. With `deployment.mode: "cloud"` but **no** `AWS_REGION`:
   - Start Carson. Expect immediate `RuntimeError` from `init_cloud_observability()` with the message about needing `AWS_REGION`.

3. With `deployment.mode: "cloud"` + `AWS_REGION=us-east-1` + valid AWS creds + `requirements-cloud.txt` installed:
   - Start Carson. CloudWatch namespace `Carson/${team_id}` shows metric activity within 60s.

4. With invalid value (`deployment.mode: "banana"`):
   - Expect immediate `ValueError` with clear message listing valid options.

### Cloud impact

This fix is **the bridge** between local-first fixes (Tier 0–5, FIX #1–#37) and the Cloud sections (CLD #1–#15). After FIX #38, every CLD fix's first line becomes "Set `deployment.mode: cloud` in `config.yaml`". The remaining work in each CLD fix is purely the AWS infra wiring; the Carson code is already cloud-aware.

Apply this fix BEFORE FIX #19 (Flask→FastAPI) so the new FastAPI app's startup hook uses `init_observability()` from day one, instead of being retrofitted later.

---

# Cloud transformation — AWS-ready

This section is the **platform-level work** — turning Carson from "a tool that runs on a Citrix VDI" into "a cloud-native multi-tenant service that any team in the org can deploy in 30 minutes". It complements the bug-level fixes above; both happen in the same 26-week roadmap.

## Containerization (CLD #1)

**Priority**: P0 · **Tier**: Cloud

### Goal

A single Dockerfile that builds Carson into a runnable container image, pushed to a private ECR registry, deployed via the same artifact across dev/test/prod.

### Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.6

# ── Stage 1: build dependencies ──────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# System dependencies for kerberos, native libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libkrb5-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy lock file (FIX #22)
COPY requirements.txt .

# Use uv for faster install (alternative: pip install -r requirements.txt)
RUN pip install --user --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user
RUN groupadd -r carson && useradd -r -g carson -u 1000 carson

# Runtime libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libkrb5-3 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed deps from builder
COPY --from=builder /root/.local /home/carson/.local
ENV PATH=/home/carson/.local/bin:$PATH \
    PYTHONPATH=/app:/app/langgraph-system \
    PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO

WORKDIR /app

# Application code (don't COPY tests, .venv, .git, etc.)
COPY --chown=carson:carson langgraph-system /app/langgraph-system
COPY --chown=carson:carson mcp-servers /app/mcp-servers

# Install MCP servers as packages (FIX #18)
USER carson
RUN for d in /app/mcp-servers/*-mcp-server-python; do \
    pip install --user -e "$d"; \
    done

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl --fail http://localhost:8765/health || exit 1

# ECS Fargate sets the listener
EXPOSE 8765

# Entry point: run via uvicorn (after FIX #19)
CMD ["uvicorn", "langgraph_system.carson_service:app", \
     "--host", "0.0.0.0", "--port", "8765", "--workers", "4"]
```

### .dockerignore

```
.git
.venv
__pycache__
*.pyc
*.pyo
.pytest_cache
*_docs_cache
chroma_db
carson_kb
carson_data
.vscode
.idea
*.md
docs/
tests/
.github/
```

### Build and push to ECR

```bash
# One-time: create the repo
aws ecr create-repository --repository-name carson \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability IMMUTABLE \
    --encryption-configuration encryptionType=KMS

# Build
docker build -t carson:$(git rev-parse --short HEAD) .

# Tag for ECR
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
ECR=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com
docker tag carson:$(git rev-parse --short HEAD) $ECR/carson:$(git rev-parse --short HEAD)
docker tag carson:$(git rev-parse --short HEAD) $ECR/carson:latest

# Login + push
aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin $ECR
docker push $ECR/carson:$(git rev-parse --short HEAD)
docker push $ECR/carson:latest
```

### Verification

1. `docker build` succeeds, image size < 1.5 GB.
2. `docker run --rm -e CARSON_CONFIG=/app/config.yaml carson:latest` starts cleanly and responds to `GET /health`.
3. `aws ecr describe-image-scan-findings` returns no critical CVEs.

---

## AWS deployment topology (CLD #2)

**Priority**: P0 · **Tier**: Cloud

### Reference architecture

```
                ┌──────────────────────────────────────────────┐
                │            Internet (corp users)             │
                └───────────────────┬──────────────────────────┘
                                    │ TLS 1.3
                                    ▼
                        ┌───────────────────────┐
                        │      AWS WAFv2        │  CLD #10
                        │  (rate limit, geo)    │
                        └───────────┬───────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │  Application Load      │
                        │  Balancer (ALB)        │  multi-AZ, TLS termination
                        │  + ACM cert            │
                        └───────────┬───────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
       ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
       │ ECS Fargate  │    │ ECS Fargate  │    │ ECS Fargate  │
       │ Carson task  │    │ Carson task  │    │ Carson task  │  CLD #1, #8
       │  (AZ-1a)     │    │  (AZ-1b)     │    │  (AZ-1c)     │  multi-AZ
       └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
                  ┌───────────────┼───────────────┐
                  ▼               ▼               ▼
         ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
         │   RDS         │ │   DynamoDB    │ │      S3       │
         │  Postgres    │ │  hot path    │ │ cold storage │  CLD #7
         │  (sessions,  │ │  (metrics,   │ │ (chroma_kb,  │
         │   threads)   │ │   routing)   │ │  audit logs) │
         │  Multi-AZ    │ │              │ │  versioning  │
         └──────────────┘ └──────────────┘ └──────────────┘
                                  │
                                  ▼
                        ┌─────────────────┐
                        │  AWS Bedrock     │
                        │  (Claude Sonnet) │
                        └─────────────────┘

         ┌──────────────────────────────────────────────────┐
         │                Observability plane                │
         │                                                    │
         │  CloudWatch Logs ─┬─ CloudWatch Metrics            │  CLD #5
         │                   ├─ X-Ray traces                  │  CLD #6
         │                   ├─ EventBridge (alarms)          │
         │                   └─ Grafana (managed)             │
         └──────────────────────────────────────────────────┘
```

### Terraform module (skeleton)

```hcl
# infra/modules/carson/main.tf

variable "team_id"          { type = string }
variable "image_tag"        { type = string }
variable "vpc_id"           { type = string }
variable "private_subnets"  { type = list(string) }
variable "public_subnets"   { type = list(string) }
variable "domain_name"      { type = string }   # carson.${team_id}.jpmc.internal

locals {
  name = "carson-${var.team_id}"
  tags = {
    Application = "carson"
    Team        = var.team_id
    Owner       = "ahtw"
    ManagedBy   = "terraform"
  }
}

# ── Security ─────────────────────────────────────────────────────
resource "aws_security_group" "alb" {
  name   = "${local.name}-alb"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]   # corp network only
  }
  egress {
    from_port = 0; to_port = 0; protocol = "-1"; cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

resource "aws_security_group" "service" {
  name   = "${local.name}-svc"
  vpc_id = var.vpc_id

  ingress {
    from_port       = 8765
    to_port         = 8765
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port = 0; to_port = 0; protocol = "-1"; cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

# ── ALB ──────────────────────────────────────────────────────────
resource "aws_lb" "carson" {
  name               = local.name
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnets
  enable_deletion_protection = true
  enable_http2       = true
  tags = local.tags
}

resource "aws_lb_target_group" "carson" {
  name        = "${local.name}-tg"
  port        = 8765
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }
  deregistration_delay = 30
  tags = local.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.carson.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.carson.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.carson.arn
  }
}

# ── ECS cluster + service ────────────────────────────────────────
resource "aws_ecs_cluster" "carson" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = local.tags
}

resource "aws_ecs_task_definition" "carson" {
  family             = local.name
  network_mode       = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                = "1024"     # 1 vCPU
  memory             = "2048"     # 2 GB
  execution_role_arn = aws_iam_role.exec.arn
  task_role_arn      = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name  = "carson"
    image = "${aws_ecr_repository.carson.repository_url}:${var.image_tag}"
    portMappings = [{ containerPort = 8765, protocol = "tcp" }]
    environment = [
      { name = "CARSON_CONFIG", value = "/app/config.yaml" },
      { name = "AWS_REGION",    value = data.aws_region.current.name },
      { name = "TEAM_ID",       value = var.team_id },
    ]
    secrets = [
      # CLD #3 — Secrets Manager
      { name = "CDAOSDK_TOKEN",          valueFrom = aws_secretsmanager_secret.cdaosdk.arn },
      { name = "BITBUCKET_TOKEN",        valueFrom = aws_secretsmanager_secret.bitbucket.arn },
      { name = "JIRA_TOKEN",             valueFrom = aws_secretsmanager_secret.jira.arn },
      { name = "CONFLUENCE_TOKEN",       valueFrom = aws_secretsmanager_secret.confluence.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.carson.name
        awslogs-region        = data.aws_region.current.name
        awslogs-stream-prefix = "carson"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8765/health || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = local.tags
}

resource "aws_ecs_service" "carson" {
  name            = local.name
  cluster         = aws_ecs_cluster.carson.id
  task_definition = aws_ecs_task_definition.carson.arn
  desired_count   = 3                                 # multi-AZ
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  enable_execute_command             = true           # ECS Exec for debug

  network_configuration {
    subnets          = var.private_subnets
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.carson.arn
    container_name   = "carson"
    container_port   = 8765
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = local.tags
}

# ── Auto-scaling (CLD #8) ────────────────────────────────────────
resource "aws_appautoscaling_target" "carson" {
  max_capacity       = 20
  min_capacity       = 3
  resource_id        = "service/${aws_ecs_cluster.carson.name}/${aws_ecs_service.carson.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${local.name}-cpu-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.carson.resource_id
  scalable_dimension = aws_appautoscaling_target.carson.scalable_dimension
  service_namespace  = aws_appautoscaling_target.carson.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 60.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# Scale out faster on routing-queue depth
resource "aws_appautoscaling_policy" "queue_depth" {
  name               = "${local.name}-queue-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.carson.resource_id
  scalable_dimension = aws_appautoscaling_target.carson.scalable_dimension
  service_namespace  = aws_appautoscaling_target.carson.service_namespace

  target_tracking_scaling_policy_configuration {
    customized_metric_specification {
      metric_name = "carson_inflight_requests"
      namespace   = "Carson/${var.team_id}"
      statistic   = "Average"
    }
    target_value       = 8.0     # 8 inflight requests per task
    scale_out_cooldown = 30
    scale_in_cooldown  = 300
  }
}

# ── IAM ──────────────────────────────────────────────────────────
resource "aws_iam_role" "exec" {
  name               = "${local.name}-exec"
  assume_role_policy = data.aws_iam_policy_document.assume_ecs.json
}

resource "aws_iam_role_policy_attachment" "exec_managed" {
  role       = aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume_ecs.json
}

resource "aws_iam_role_policy" "task" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_perms.json
}

data "aws_iam_policy_document" "task_perms" {
  # Bedrock invoke (CDAOSDK)
  statement {
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["arn:aws:bedrock:*::foundation-model/anthropic.*"]
  }

  # S3 — ChromaDB and audit logs
  statement {
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [
      "arn:aws:s3:::carson-kb-${var.team_id}",
      "arn:aws:s3:::carson-kb-${var.team_id}/*",
      "arn:aws:s3:::carson-audit-${var.team_id}",
      "arn:aws:s3:::carson-audit-${var.team_id}/*",
    ]
  }

  # DynamoDB — hot path (CLD #7)
  statement {
    actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [
      aws_dynamodb_table.threads.arn,
      "${aws_dynamodb_table.threads.arn}/index/*",
      aws_dynamodb_table.metrics.arn,
    ]
  }

  # Secrets — explicit per-secret list (least privilege)
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.cdaosdk.arn,
      aws_secretsmanager_secret.bitbucket.arn,
      aws_secretsmanager_secret.jira.arn,
      aws_secretsmanager_secret.confluence.arn,
    ]
  }

  # KMS — decrypt secrets
  statement {
    actions = ["kms:Decrypt"]
    resources = [aws_kms_key.carson.arn]
  }

  # X-Ray (CLD #6)
  statement {
    actions = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }

  # CloudWatch metrics (CLD #5)
  statement {
    actions = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["Carson/${var.team_id}"]
    }
  }
}

# ── CloudWatch log group ─────────────────────────────────────────
resource "aws_cloudwatch_log_group" "carson" {
  name              = "/ecs/${local.name}"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.carson.arn
  tags              = local.tags
}

# ── ECR ──────────────────────────────────────────────────────────
resource "aws_ecr_repository" "carson" {
  name                 = "carson"
  image_tag_mutability = "IMMUTABLE"
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.carson.arn
  }
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}
```

### Verification

1. `terraform plan` produces a sensible plan with no destroy operations.
2. `terraform apply`; ECS service reaches steady state with desired_count=3 healthy tasks across 3 AZs.
3. `curl https://carson.${team}.jpmc.internal/health` returns 200 from each AZ (verify via direct task IPs).
4. ALB access logs show TLS 1.3 connections only.

---

## Auto-scaling and capacity (CLD #8)

**Priority**: P1 · **Tier**: Cloud

### Strategy

Two-axis scaling:

1. **CPU-based** (target 60%) — handles steady-state throughput growth.
2. **Custom metric `carson_inflight_requests` per task** (target 8) — handles burst LLM-bound requests faster than CPU lags.

Both scale out within 60 seconds; scale in only after 5 minutes of underuse. Min 3 tasks (one per AZ), max 20 (cost cap).

### Capacity sizing rule of thumb

Per task (1 vCPU, 2 GB RAM):
- Concurrent inflight requests: ~10 (LLM-bound, mostly waiting on Bedrock)
- p95 latency: ~5 seconds per request
- Throughput: ~2 req/s steady, ~5 req/s burst

For a team of 50 active users at 0.5 RPS each = 25 RPS total. With p95=5s, inflight ≈ 125 → 13 tasks. Round to 15 tasks at peak with 3 baseline.

### Pre-warming for known peaks

If usage spikes Mon-Fri 9am-11am, schedule:

```hcl
resource "aws_appautoscaling_scheduled_action" "morning_warm" {
  name               = "${local.name}-morning-warm"
  service_namespace  = "ecs"
  resource_id        = aws_appautoscaling_target.carson.resource_id
  scalable_dimension = "ecs:service:DesiredCount"
  schedule           = "cron(45 8 ? * MON-FRI *)"   # 8:45 EST
  scalable_target_action {
    min_capacity = 8
    max_capacity = 20
  }
}
```

---

## Multi-AZ HA and multi-region DR (CLD #9, #13)

**Priority**: P1 (multi-AZ) · P2 (multi-region) · **Tier**: Cloud

### Multi-AZ (CLD #9, day-1)

- ECS service desired_count = 3, one task per AZ.
- ALB cross-zone load balancing enabled.
- RDS Multi-AZ (synchronous standby in second AZ).
- DynamoDB native multi-AZ.
- S3 native cross-AZ.

### Multi-region DR (CLD #13, post-launch)

Strategy: **warm standby** in `us-west-2`.

- ECR replication to us-west-2.
- DynamoDB Global Tables (active-active read, single-region writes).
- S3 Cross-Region Replication (CRR) for ChromaDB backups + audit logs.
- RDS read replica in us-west-2; promoted on failover.
- Route 53 failover health check on ALB; DNS flips to us-west-2 on us-east-1 failure.

RTO target: < 1 hour. RPO target: < 15 minutes.

DR runbook (separate document `CARSON_DR_RUNBOOK.md`).

---

## Observability stack (CLD #5, #6)

**Priority**: P0 · **Tier**: Cloud

### Three pillars

1. **Logs** — structured JSON to CloudWatch Logs, 30-day retention, encrypted.
2. **Metrics** — `token_tracker` exports to CloudWatch via PutMetricData, plus ECS Container Insights, ALB metrics.
3. **Traces** — every agent run produces an X-Ray trace, with OpenTelemetry-compatible spans for vendor neutrality.

### CloudWatch metrics from token_tracker (CLD #5)

```python
# langgraph-system/carson_agents/observability/cw_exporter.py
import boto3, threading, time

class CloudWatchExporter:
    """Background thread that pushes token_tracker stats to CloudWatch every 60s."""

    def __init__(self, namespace: str, team_id: str):
        self.cw = boto3.client("cloudwatch")
        self.namespace = namespace        # "Carson/ahtw"
        self.team_id = team_id
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop.wait(60):
            try:
                stats = get_token_tracker().get_stats()
                self._publish(stats)
            except Exception as e:
                logger.exception("CloudWatch export failed: %s", e)

    def _publish(self, stats: dict):
        metrics = []
        for agent, agent_stats in stats.get("by_agent", {}).items():
            for metric_name, value in [
                ("InputTokens",  agent_stats["input_tokens"]),
                ("OutputTokens", agent_stats["output_tokens"]),
                ("CachedTokens", agent_stats["cached_tokens"]),
                ("EstimatedCostUsd", agent_stats["estimated_cost_usd"]),
                ("AvgLatencyMs", agent_stats["avg_latency_ms"]),
                ("RequestCount", agent_stats["request_count"]),
            ]:
                metrics.append({
                    "MetricName": metric_name,
                    "Value": float(value),
                    "Unit": "None" if "Token" in metric_name or "Count" in metric_name
                            else "Milliseconds" if "Latency" in metric_name
                            else "None",
                    "Dimensions": [
                        {"Name": "Team",  "Value": self.team_id},
                        {"Name": "Agent", "Value": agent},
                    ],
                })

        # CloudWatch limit: 1000 metrics per call
        for i in range(0, len(metrics), 1000):
            self.cw.put_metric_data(Namespace=self.namespace, MetricData=metrics[i:i+1000])
```

In `carson_service.py` startup:

```python
from carson_agents.observability.cw_exporter import CloudWatchExporter

if os.environ.get("AWS_REGION"):  # only in cloud
    CloudWatchExporter(
        namespace=f"Carson/{config['team_id']}",
        team_id=config["team_id"],
    ).start()
```

### CloudWatch dashboards

Per-team dashboard published via Terraform:

```hcl
resource "aws_cloudwatch_dashboard" "carson" {
  dashboard_name = "carson-${var.team_id}"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          title  = "Tokens per minute (by agent)"
          metrics = [["Carson/${var.team_id}", "InputTokens", "Team", var.team_id]]
          stat   = "Sum"
          period = 60
        }
      },
      {
        type = "metric"
        properties = {
          title  = "Estimated cost USD/hour"
          metrics = [["Carson/${var.team_id}", "EstimatedCostUsd", "Team", var.team_id]]
          stat   = "Sum"
          period = 3600
        }
      },
      {
        type = "metric"
        properties = {
          title  = "p95 agent latency"
          metrics = [["Carson/${var.team_id}", "AvgLatencyMs"]]
          stat   = "p95"
          period = 60
        }
      },
      # ... more widgets ...
    ]
  })
}
```

### Distributed tracing with X-Ray + OpenTelemetry (CLD #6)

```python
# langgraph-system/carson_agents/observability/tracing.py
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.propagators.aws.aws_xray_propagator import AwsXRayPropagator
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator

def init_tracing(team_id: str):
    resource = Resource(attributes={
        "service.name": "carson",
        "service.namespace": team_id,
        "deployment.environment": os.environ.get("CARSON_ENV", "prod"),
    })

    # X-Ray-compatible IDs (8 hex + 24 hex)
    provider = TracerProvider(
        resource=resource,
        id_generator=AwsXRayIdGenerator(),
    )

    # Export to ADOT collector running as sidecar
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    )

    trace.set_tracer_provider(provider)
    set_global_textmap(AwsXRayPropagator())

tracer = trace.get_tracer("carson")
```

In LangGraph nodes:

```python
def jira_agent_node(state: CarsonState) -> CarsonState:
    with tracer.start_as_current_span(
        "agent.jira",
        attributes={
            "agent.id":         "jira",
            "agent.intent":     state.get("intent"),
            "user.sid":         state.get("user_sid"),
            "session.id":       state.get("session_id"),
            "jira.ticket":      state.get("jira_ticket"),
        },
    ) as span:
        # ... agent logic ...
        span.set_attribute("agent.tokens_in", input_tokens)
        span.set_attribute("agent.tokens_out", output_tokens)
        span.set_attribute("agent.tool_calls", len(tool_calls))
        return new_state
```

ECS task definition includes ADOT collector sidecar:

```hcl
container_definitions = jsonencode([
  { name = "carson", ... },
  {
    name = "adot-collector"
    image = "public.ecr.aws/aws-observability/aws-otel-collector:latest"
    command = ["--config=/etc/ecs/ecs-default-config.yaml"]
    logConfiguration = { ... }
  }
])
```

X-Ray traces appear in the AWS console with:
- Service map showing Carson → Bedrock, Carson → DynamoDB, Carson → S3, Carson → MCP servers
- Per-trace breakdown of agent invocations, tool calls, LLM latency
- Filterable by `service.namespace` (team), `agent.id`, `user.sid`

### Optional: Datadog or Grafana

For teams that prefer non-AWS observability, the same OpenTelemetry SDK exports to:
- Datadog (`OTLPSpanExporter` to Datadog OTel endpoint)
- Grafana Tempo
- Honeycomb
- Self-hosted Jaeger

Single instrumentation, multiple backends. Vendor lock-in is avoided.

---

## Secrets management and encryption (CLD #3)

**Priority**: P0 · **Tier**: Cloud

### Threat model

Secrets in source = anyone with repo read access has prod credentials. Secrets in env vars at runtime = also leakable via process listing or core dumps. Secrets in Secrets Manager + decrypted only at request time = least-privilege.

### Secrets inventory

| Secret | Source today | Target |
|---|---|---|
| CDAOSDK token (Bedrock) | Kerberos via `pcl aws login` (manual refresh) | Secrets Manager + automatic IAM role assumption (preferred) |
| Bitbucket token | Kerberos / personal token in env | Secrets Manager |
| Jira token | `~/.config` per-user | Secrets Manager |
| Confluence token | Idem | Secrets Manager |
| Outlook | OAuth (per-user, OK) | Stay per-user (no central secret) |
| Datadog API key | None yet | Secrets Manager |
| Per-user Carson encryption key (FIX #0.6) | Local disk (`~/.carson/`) | KMS data keys, envelope encryption |

### Terraform: secrets + KMS

```hcl
resource "aws_kms_key" "carson" {
  description             = "Carson encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_policy.json

  tags = local.tags
}

resource "aws_kms_alias" "carson" {
  name          = "alias/carson-${var.team_id}"
  target_key_id = aws_kms_key.carson.key_id
}

resource "aws_secretsmanager_secret" "cdaosdk" {
  name                    = "carson/${var.team_id}/cdaosdk"
  description             = "CDAOSDK token for Bedrock"
  kms_key_id              = aws_kms_key.carson.id
  recovery_window_in_days = 7
  tags                    = local.tags
}

resource "aws_secretsmanager_secret_version" "cdaosdk" {
  secret_id     = aws_secretsmanager_secret.cdaosdk.id
  secret_string = jsonencode({
    token       = var.cdaosdk_token
    expires_at  = var.cdaosdk_token_expiry
  })
}

# Auto-rotation Lambda for tokens that have an API
resource "aws_secretsmanager_secret_rotation" "cdaosdk" {
  secret_id           = aws_secretsmanager_secret.cdaosdk.id
  rotation_lambda_arn = aws_lambda_function.cdaosdk_rotator.arn

  rotation_rules {
    automatically_after_days = 30
  }
}
```

### Carson code: read secrets at startup

```python
# langgraph-system/carson_agents/secrets.py
import boto3, json
from functools import lru_cache

@lru_cache(maxsize=32)
def get_secret(name: str) -> dict:
    """Cached secret read. Token never leaves Secrets Manager / process memory."""
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=name)
    return json.loads(resp["SecretString"])

def get_cdaosdk_token() -> str:
    return get_secret(f"carson/{TEAM_ID}/cdaosdk")["token"]
```

Refresh on `TOKEN_EXPIRED`:

```python
def _bedrock_client_with_refresh():
    try:
        return create_bedrock_client(get_cdaosdk_token())
    except TokenExpiredError:
        get_secret.cache_clear()             # force refresh
        return create_bedrock_client(get_cdaosdk_token())
```

### Verification

1. No secrets in `git ls-files | xargs grep -E '(token|password|secret).*=.*[A-Za-z0-9]{20}'`.
2. Carson tasks have no environment variables containing tokens.
3. ECS task role can read only the listed secrets (least-privilege).
4. KMS key rotation is enabled.

---

## Infrastructure as Code (IaC) (CLD #2 expanded)

**Priority**: P0 · **Tier**: Cloud

### Repo layout for infra

```
high-touch-agent-prompts/
├── infra/
│   ├── modules/
│   │   ├── carson/             # full Carson stack (this section)
│   │   ├── ecr/                # repo provisioning
│   │   ├── networking/         # VPC, subnets, NAT, etc.
│   │   ├── observability/      # CloudWatch, X-Ray, alarms
│   │   └── data/               # RDS, DynamoDB, S3
│   ├── envs/
│   │   ├── dev/
│   │   │   ├── main.tf
│   │   │   ├── terraform.tfvars
│   │   │   └── backend.tf
│   │   ├── uat/
│   │   ├── prod/
│   │   └── _shared/            # cross-env (ECR, KMS roots)
│   └── policies/               # Sentinel policies
└── ...
```

### Sentinel policies (governance)

For JPMC-internal Terraform Enterprise, attach Sentinel policies to enforce:

- All resources have `Application=carson`, `Team`, `Owner`, `ManagedBy=terraform` tags.
- All KMS keys have rotation enabled.
- All S3 buckets have versioning + encryption.
- All RDS instances are Multi-AZ in prod.
- ECR images use IMMUTABLE tags.
- No public-facing ALBs (all `internal=true`).

Example Sentinel:

```
import "tfplan/v2" as tfplan

mandatory_tags = ["Application", "Team", "Owner", "ManagedBy"]

main = rule {
    all tfplan.resource_changes as _, change {
        all mandatory_tags as t {
            change.change.after.tags contains t
        }
    }
}
```

### Verification

1. `terraform validate` passes in all envs.
2. `terraform plan -out=plan.bin && terraform show -json plan.bin | conftest test --policy infra/policies/` passes.
3. `tfsec` / `checkov` scan no critical findings.

---

## CI/CD pipeline (CLD #4)

**Priority**: P0 · **Tier**: Cloud

### Pipeline stages

```
┌───────────────────────────────────────────────────────────────┐
│  Developer pushes to feature/* branch                          │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│  GitHub Actions: lint + unit tests + type-check + security     │
│  - black, ruff, mypy                                            │
│  - pytest (unit + integration with mocked Bedrock)             │
│  - bandit, safety (CVE check)                                   │
│  - validate config.yaml schema                                  │
│  - validate Bedrock ARNs (FIX #17)                              │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│  Merge to develop → trigger Spinnaker pipeline                  │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│  Spinnaker: build container + push to ECR                       │
│  - docker build with --label commit=$GIT_SHA                    │
│  - ECR scan (block on critical CVEs)                            │
│  - Trivy scan                                                    │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│  Deploy to dev (auto)                                           │
│  - terraform plan + apply with -var image_tag=$GIT_SHA         │
│  - Smoke tests against dev URL                                  │
│  - Validation: GET /health, agent run, dashboard fetch          │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│  Deploy to UAT (auto, after manual gate)                        │
│  - terraform apply -var image_tag=$GIT_SHA                      │
│  - 24h soak test (run synthetic queries every 5 min)            │
└────────────────────────┬───────────────────────────────────────┘
                         ▼
┌───────────────────────────────────────────────────────────────┐
│  Deploy to PROD (manual approval required)                      │
│  - Canary: 10% traffic for 1h → 50% for 1h → 100%               │
│  - Auto-rollback on alarms (CLD #15)                            │
└───────────────────────────────────────────────────────────────┘
```

### GitHub Actions workflow

```yaml
# .github/workflows/ci.yml
name: Carson CI

on:
  pull_request:
  push:
    branches: [develop, main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: langgraph-system/requirements.txt

      - name: Install
        run: |
          python -m pip install --upgrade pip pip-tools
          pip install -r langgraph-system/requirements.txt
          pip install -r langgraph-system/requirements-dev.txt

      - name: Lint
        run: |
          ruff check langgraph-system/
          black --check langgraph-system/

      - name: Type check
        run: mypy langgraph-system/

      - name: Test
        run: pytest -v --cov=langgraph-system

      - name: Security scan
        run: |
          bandit -r langgraph-system/ -ll
          safety check --full-report

      - name: Lock file integrity
        run: |
          pip-compile --check langgraph-system/requirements.in

  build-image:
    needs: lint-and-test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/develop' || github.ref == 'refs/heads/main'
    permissions:
      id-token: write   # OIDC to AWS
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/github-actions-carson
          aws-region: us-east-1

      - name: Build and push
        run: |
          docker build -t carson:${{ github.sha }} .
          docker tag carson:${{ github.sha }} \
              123456789012.dkr.ecr.us-east-1.amazonaws.com/carson:${{ github.sha }}
          aws ecr get-login-password | docker login --username AWS \
              --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
          docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/carson:${{ github.sha }}
```

### Spinnaker pipeline

Triggered by ECR push event. Uses Spinnaker's "deploy manifest" stages with:
- Bake: Terraform plan
- Deploy to dev: Terraform apply
- Smoke test: Carson smoke test stage (`scripts/smoke_test.py` against dev URL)
- Manual judgment for UAT
- Deploy to UAT: same with vars
- Soak test: 24h
- Manual judgment for prod
- Canary deploy with traffic shifting

### Verification

1. Push a feature branch → CI green within 8 minutes.
2. Merge to develop → image visible in ECR within 12 minutes, dev URL serves new image within 20 minutes.
3. Smoke test failure → pipeline halts, rollback to previous task definition automatic.

---

## Data layer and state (CLD #7)

**Priority**: P1 · **Tier**: Cloud

### Storage tiering

| Data | Hot path | Warm path | Cold path |
|---|---|---|---|
| Active session state (LangGraph checkpoints) | DynamoDB | — | — |
| Threads (last 7 days) | DynamoDB | RDS Postgres | — |
| Threads (older) | — | RDS Postgres | S3 (Glacier IR after 90d) |
| Token tracker rolling stats | In-memory + DynamoDB | CloudWatch (90d) | — |
| Audit log | CloudWatch + DynamoDB stream | — | S3 with object lock |
| Run traces | X-Ray (30d) | — | S3 export (Glacier IR) |
| ChromaDB embeddings | Local volume | S3 (snapshots) | S3 IA after 30d |
| MCP server logs | CloudWatch | — | S3 export |

### DynamoDB tables

```hcl
resource "aws_dynamodb_table" "threads" {
  name         = "carson-${var.team_id}-threads"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_sid"
  range_key    = "thread_id"

  attribute { name = "user_sid"    type = "S" }
  attribute { name = "thread_id"   type = "S" }
  attribute { name = "updated_at"  type = "N" }
  attribute { name = "intent"      type = "S" }

  global_secondary_index {
    name            = "by_intent"
    hash_key        = "intent"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "by_user_recent"
    hash_key        = "user_sid"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  point_in_time_recovery { enabled = true }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.carson.arn
  }

  tags = local.tags
}

resource "aws_dynamodb_table" "metrics" {
  name         = "carson-${var.team_id}-metrics"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "team_agent"   # composite: "ahtw#jira"
  range_key    = "minute"        # YYYYMMDDHHMM

  attribute { name = "team_agent" type = "S" }
  attribute { name = "minute"     type = "N" }

  ttl {
    attribute_name = "expires_at"     # 7-day rolling window
    enabled        = true
  }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.carson.arn
  }

  tags = local.tags
}
```

### Migration from current state

Current → Cloud mapping:

- `carson_data/(SID)/threads/*.json` (git-synced) → DynamoDB threads table.
- `carson_data/(SID)/jobs/*.json` → DynamoDB threads (with `intent="autonomous_coding"`).
- `token_tracker._stats` (in-memory) → DynamoDB metrics + CloudWatch.
- `chroma_db/` (local) → S3 with cross-AZ replication.

Migration script (one-shot):

```python
# scripts/migrate_to_dynamodb.py
import boto3, json, time
from pathlib import Path

ddb = boto3.resource("dynamodb").Table(f"carson-{team_id}-threads")

for thread_file in Path("./carson_data").rglob("threads/*.json"):
    user_sid = thread_file.parts[-3]
    thread_id = thread_file.stem
    data = json.loads(thread_file.read_text())
    ddb.put_item(Item={
        "user_sid":   user_sid,
        "thread_id":  thread_id,
        "intent":     data.get("intent", "general"),
        "updated_at": int(time.time()),
        "data":       data,
    })
```

---

## Cost optimization (CLD #14)

**Priority**: P2 · **Tier**: Cloud

### Cost levers

1. **Prompt caching** — already enabled (FIX #14 references `enable_prompt_caching: true`). Saves 90% on repeated prompt prefixes (system prompt, agent instructions). Verify via `cached_input_tokens` in token_tracker stats.

2. **Dual-model routing** — Haiku for routing, Sonnet for agents. Already in place; document in cost runbook.

3. **Critic retry stagnation** (FIX #0.5) — caps retry cost when retries don't improve.

4. **Right-sizing Fargate** — start at 1 vCPU + 2 GB. Monitor CPU + mem in CloudWatch; scale task size up only if hitting limits sustained for 1 hour.

5. **Reserved Capacity / Savings Plans** — once steady-state usage is known (60+ days of metrics), commit to a Compute Savings Plan covering the 80th percentile of capacity. Saves 30-50%.

6. **S3 lifecycle policies** — ChromaDB snapshots → IA after 30d, Glacier IR after 90d. Audit logs → IA immediately, Glacier IR after 90d, expire after 7 years (compliance retention).

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "carson_kb" {
  bucket = aws_s3_bucket.carson_kb.id

  rule {
    id     = "snapshots-tiering"
    status = "Enabled"
    filter { prefix = "snapshots/" }
    transition { days = 30  storage_class = "STANDARD_IA" }
    transition { days = 90  storage_class = "GLACIER_IR" }
    expiration { days = 365 }
  }
}
```

7. **CloudWatch logs retention** — 30 days for service logs (debugging window), 7 years for audit logs (compliance), exported to S3 for long-term.

8. **Cost allocation tags** — every resource tagged with `Team`, `Application=carson`, `Environment`. AWS Cost Explorer breaks down spend by team for chargeback.

### Per-team chargeback

Monthly automated report:

```python
# scripts/team_cost_report.py
import boto3
from datetime import datetime, timedelta

ce = boto3.client("ce")
end = datetime.utcnow().date()
start = (end.replace(day=1))

resp = ce.get_cost_and_usage(
    TimePeriod={"Start": str(start), "End": str(end)},
    Granularity="MONTHLY",
    Metrics=["UnblendedCost", "UsageQuantity"],
    GroupBy=[
        {"Type": "TAG", "Key": "Team"},
        {"Type": "DIMENSION", "Key": "SERVICE"},
    ],
    Filter={"Tags": {"Key": "Application", "Values": ["carson"]}},
)

# Email report to each team owner
```

---

## Security hardening (CLD #10, #11, #12)

**Priority**: P1 · **Tier**: Cloud

### Network

- ALB internal only (`internal=true`), accessible from corp CIDRs only.
- ECS tasks in private subnets; outbound via NAT gateway.
- VPC endpoints (Gateway VPC endpoints for S3 and DynamoDB; Interface endpoints for Bedrock, Secrets Manager, KMS) — keeps traffic on AWS backbone, reduces NAT cost, reduces attack surface.
- Security groups: ALB→service on 8765 only. Service→Bedrock/S3/DDB through VPC endpoints. No 0.0.0.0/0 ingress.

### WAF (CLD #10)

```hcl
resource "aws_wafv2_web_acl" "carson" {
  name  = "carson-${var.team_id}"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "rate-limit"
    priority = 1
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 1000   # per 5 min per IP
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "managed-known-bad"
    priority = 2
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config { ... }
  }

  rule {
    name     = "managed-common"
    priority = 3
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config { ... }
  }
}

resource "aws_wafv2_web_acl_association" "carson" {
  resource_arn = aws_lb.carson.arn
  web_acl_arn  = aws_wafv2_web_acl.carson.arn
}
```

### Logs and traces — PII redaction (CLD #11)

```python
# langgraph-system/carson_agents/observability/redaction.py
import re

PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                "[SSN]"),
    (re.compile(r"\b\d{16}\b"),                           "[CC]"),
    (re.compile(r"\b[A-Z][a-z]+ [A-Z]\."),                "[NAME]"),  # "John D." style
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),             "[EMAIL]"),
    (re.compile(r"sso[a-z0-9]{8}", re.IGNORECASE),        "[SSO_ID]"),
    # JPMC-specific patterns
    (re.compile(r"SID[a-z0-9]{6,8}", re.IGNORECASE),      "[SID]"),
]

def redact(text: str) -> str:
    out = text
    for pat, repl in PII_PATTERNS:
        out = pat.sub(repl, out)
    return out

class RedactingFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        return redact(msg)
```

Apply:

```python
for handler in logging.root.handlers:
    handler.setFormatter(RedactingFormatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
```

For X-Ray spans, redact attribute values:

```python
def safe_set_attribute(span, key, value):
    if isinstance(value, str):
        value = redact(value)
    span.set_attribute(key, value)
```

### Audit log of writes (CLD #12)

Every agent action that creates/modifies external resources (Jira ticket, Bitbucket PR, Confluence page, Spinnaker deploy) is logged to a write-only S3 bucket with object lock:

```python
# langgraph-system/carson_agents/audit.py
import boto3, json, time, uuid

audit_s3 = boto3.client("s3")
AUDIT_BUCKET = f"carson-audit-{TEAM_ID}"

def record_write_action(
    user_sid: str, agent_id: str, action: str,
    target: dict, request: dict, response: dict,
    trace_id: str | None = None,
):
    """Append-only audit record for any write op."""
    record = {
        "id":         str(uuid.uuid4()),
        "timestamp":  time.time(),
        "user_sid":   user_sid,
        "agent_id":   agent_id,
        "action":     action,             # e.g. "jira.create_ticket"
        "target":     target,             # {"project": "AHTW", "ticket_id": "AHTW-123"}
        "request":    redact_dict(request),
        "response":   redact_dict(response),
        "trace_id":   trace_id,
    }
    key = f"{time.strftime('%Y/%m/%d')}/{record['id']}.json"
    audit_s3.put_object(
        Bucket=AUDIT_BUCKET,
        Key=key,
        Body=json.dumps(record),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )
```

S3 bucket has Object Lock in compliance mode, 7-year retention. Even an admin cannot delete audit records before retention expires.

### IAM least-privilege

Reviewed in CLD #2 Terraform. Key principles:

- Task role distinct from execution role.
- Per-secret resources in `secretsmanager:GetSecretValue` (no `*`).
- Per-bucket-prefix in S3 actions.
- KMS decrypt only on the carson key.
- CloudWatch PutMetricData restricted to `Carson/${team_id}` namespace.

### Verification

1. Penetration test (annual, mandatory at JPMC): tests must pass.
2. `aws iam simulate-principal-policy` for the task role: cannot describe IAM, cannot read secrets outside `carson/${team_id}/*`, cannot write outside owned S3 buckets.
3. CloudTrail shows no `*Decrypt` calls outside the carson KMS key.
4. WAF metrics show rate-limit triggers on synthetic stress test.

---

## Compliance and audit (CLD #12 expanded)

**Priority**: P1 · **Tier**: Cloud

### What needs auditing

For a banking platform, the audit trail must answer:

- Who initiated this agent run?
- What did the agent decide?
- What write actions did it take in external systems?
- What approvals were given (HITL)?
- When did each step happen?
- What data did the agent see (RAG results, Jira ticket content)?

### Trace + audit + log triangulation

Every request gets a `trace_id` propagated across:

- X-Ray traces (full timing + dependencies)
- CloudWatch Logs (structured JSON with `trace_id`)
- DynamoDB threads table (final state with `trace_id`)
- S3 audit bucket (per-write-action records with `trace_id`)

Compliance query: "Show me everything Carson did under trace_id `abc123`":

```python
# scripts/audit_trace.py
trace = xray.batch_get_traces(TraceIds=["abc123"])
logs = logs.filter_log_events(
    logGroupName="/ecs/carson-ahtw",
    filterPattern=f'{{ $.trace_id = "abc123" }}',
)
audit_records = s3.list_objects_v2(
    Bucket=f"carson-audit-{TEAM_ID}",
    Prefix=f"{date}/",
)  # filter by trace_id

# Compose unified timeline
```

### Retention

- **Service logs**: 30 days CloudWatch, exported to S3 with 13-month retention.
- **Audit logs**: 7 years S3 Object Lock (compliance mode).
- **Traces**: 30 days X-Ray, exported to S3 quarterly with 13-month retention.
- **Per-user threads**: 90 days DynamoDB, then exported to S3 with 13-month retention.

### Right-to-be-forgotten / GDPR-equivalent

If a user leaves and requests deletion:

```python
# scripts/redact_user.py
def redact_user(user_sid: str):
    # 1. Delete DynamoDB partition
    ddb.batch_delete_items(items_with_partition_key=user_sid)

    # 2. Tombstone in audit log (cannot delete due to Object Lock,
    #    but record a "USER_FORGOTTEN" entry referencing the SID)
    audit.record_user_forgotten(user_sid)

    # 3. Redact in old CloudWatch logs (best effort —
    #    CloudWatch logs are immutable after write; export then re-import redacted)

    # 4. Delete user-specific encryption key (FIX #0.6)
    kms.schedule_key_deletion(KeyId=user_kms_key, PendingWindowInDays=30)
```

---

## SLOs, SLIs, and alerting (CLD #15)

**Priority**: P2 · **Tier**: Cloud

### Service-level objectives

| SLO | Target | Window | SLI |
|---|---|---|---|
| Availability (LangGraph service) | 99.5% | 30 days rolling | (1 - 5xx_rate) over 30d |
| Availability (dashboard read) | 99.9% | 30 days rolling | dashboard_5xx_rate |
| Latency p95 | < 10s | 30 days rolling | agent_latency_p95 |
| Cost per request | < $0.05 avg | 30 days rolling | total_cost / request_count |
| Routing accuracy | > 90% | 30 days rolling | (1 - critic_rejection_rate) |
| Data durability | 99.999999999% | n/a | S3 native + DDB PITR |

### Error budget

Availability 99.5% = 3.6 hours/month allowed downtime. Cost-per-request 5 cents avg = if average rises above 7 cents for 7 days, freeze deploys until investigated.

### Alarms

```hcl
resource "aws_cloudwatch_metric_alarm" "high_5xx" {
  alarm_name          = "carson-${var.team_id}-high-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "5xx errors > 10 in 5 min"
  alarm_actions       = [aws_sns_topic.carson_alerts.arn]
  ok_actions          = [aws_sns_topic.carson_alerts.arn]

  dimensions = {
    LoadBalancer = aws_lb.carson.arn_suffix
    TargetGroup  = aws_lb_target_group.carson.arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "cost_spike" {
  alarm_name          = "carson-${var.team_id}-cost-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "EstimatedCostUsd"
  namespace           = "Carson/${var.team_id}"
  period              = 3600
  statistic           = "Sum"
  threshold           = 10.0   # $10/hour cap
  alarm_actions       = [aws_sns_topic.carson_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "loop_guard_fired" {
  alarm_name          = "carson-${var.team_id}-loop-guard"
  metric_name         = "WorkflowCycleDetected"
  namespace           = "Carson/${var.team_id}"
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  period              = 300
  evaluation_periods  = 1
  statistic           = "Sum"
  alarm_actions       = [aws_sns_topic.carson_alerts.arn]
}

resource "aws_sns_topic" "carson_alerts" {
  name              = "carson-${var.team_id}-alerts"
  kms_master_key_id = aws_kms_key.carson.id
}

resource "aws_sns_topic_subscription" "pagerduty" {
  topic_arn = aws_sns_topic.carson_alerts.arn
  protocol  = "https"
  endpoint  = var.pagerduty_endpoint
}
```

### Runbooks

For each alarm, a runbook lives in `docs/runbooks/`:

- `RUNBOOK_high_5xx.md` — diagnosis steps, rollback procedure.
- `RUNBOOK_cost_spike.md` — disable experimental_main_model, freeze critique retries, escalate.
- `RUNBOOK_loop_guard.md` — pull X-Ray trace, identify (node, intent) pair, file ticket.
- `RUNBOOK_dr_failover.md` — multi-region failover sequence (CLD #13).

---

# Phased roadmap (26-week plan)

A timeline from "fix the worst" to "platform-grade". Each phase has a clear exit criterion.

### Phase 1 — Stop the bleeding (weeks 1-2)

**Goal**: no money is being wasted, no preventable outages.

- [ ] Sprint 1: FIX #0.1, #1, #2, #17, #22, #27, #0.3 (proxy, datadog, .hcl, ARN validation, lock file, .gitignore, dashboard polling)
- [ ] Sprint 2: FIX #0.4, #0.5, #26, #0.2 (cycle detector, retry budget, registry split, orchestration unification)

**Exit**: Bedrock cost from dashboard polling = $0. No cycle-loop incidents in production for 1 week.

### Phase 2 — Make it deployable (weeks 3-4)

**Goal**: Carson runs on AWS in dev, deployed via CI/CD.

- [ ] Sprint 3: CLD #1 (Dockerfile + ECR), CLD #2 (Terraform module dev env)
- [ ] Sprint 4: CLD #3 (Secrets Manager), CLD #4 (CI/CD pipeline)

**Exit**: feature branch merge → image in ECR → dev URL serving traffic, all under 20 minutes. Zero hardcoded secrets in repo.

### Phase 3 — Make it observable (weeks 5-6)

**Goal**: every agent run is traced, every metric is in CloudWatch, alarms fire on real incidents.

- [ ] Sprint 5: CLD #5 (CloudWatch metrics from token_tracker), FIX #15 (ChromaDB to S3)
- [ ] Sprint 6: CLD #6 (OpenTelemetry + X-Ray), FIX #16 (structured routing logs)

**Exit**: a request to dev produces a complete X-Ray trace, CloudWatch dashboard shows agent breakdown live, ChromaDB survives container rebuild.

### Phase 4 — Make it secure (weeks 7-8)

**Goal**: passes security review, audit trail in place.

- [ ] Sprint 7: CLD #7 (DynamoDB hot path + S3 cold), CLD #8 (auto-scaling), CLD #9 (multi-AZ)
- [ ] Sprint 8: CLD #10 (WAF), CLD #11 (PII redaction), CLD #12 (audit log), FIX #0.6 (encrypted user data)

**Exit**: penetration test passes, audit query returns full timeline for any trace_id, no plaintext PII in any log.

### Phase 5 — Make it production-quality (weeks 9-13)

**Goal**: high developer experience, low cognitive load.

- [ ] Sprint 9-10: FIX #19, #20, #21 (Flask → FastAPI migration)
- [ ] Sprint 11: FIX #23, #24, #25 (dashboard split into static assets — see CARSON_DASHBOARD.md)
- [ ] Sprint 12: FIX #18, #37 (MCP packaging cleanup)
- [ ] Sprint 13: FIX #11, #12, #13, #14 (RAG, critique, max_tokens)

**Exit**: developer onboarding doc says "do this in 30 minutes", new agent added end-to-end in < 1 day, dashboard splits load in < 500ms.

### Phase 6 — Make it enterprise-grade (weeks 14-21)

**Goal**: SLOs measured and met, multi-region DR, multi-tenant onboarding.

- [ ] Sprint 14: FIX #3-9 (Tier 1-2 P1 polish)
- [ ] Sprint 15: CLD #15 (SLO dashboards + alerting + runbooks)
- [ ] Sprint 16-17: CLD #13 (cross-region DR)
- [ ] Sprint 18-20: Multi-tenant onboarding flow (`carson onboard --team my-team` CLI + Terraform module per team)
- [ ] Sprint 21: CLD #14 (cost allocation tags + chargeback)

**Exit**: 99.5% availability over 30 days, DR drill passes (RTO < 1h, RPO < 15m), 1 second team onboards via CLI.

### Phase 7 — Polish and differentiate (weeks 22-26)

**Goal**: Carson becomes the platform other teams imitate.

- [ ] Sprint 22-23: FIX #8 (Sonnet 4 A/B rollout)
- [ ] Sprint 24: FIX #28-36 (P2 polish)
- [ ] Sprint 25-26: New capabilities (whatever the team prioritises — could be: voice interface, mobile app, GitHub Copilot Workspace deeper integration, custom MCP server SDK)

**Exit**: 99.9% availability, < $0.04 cost/request avg, > 5 teams self-onboarded.

---

# Status tracking and document maintenance

### Per-fix status

Track in Jira (one ticket per FIX) or a markdown table in this doc, columns: Status, Owner, PR link, Date completed. Statuses: `Not started`, `In progress`, `In review`, `Done`, `Skipped`.

### Document versioning

This file lives at `docs/CARSON_AUDIT_FIXES.md` in the repo. Bump version at top whenever:

- A new section is added (major bump: 3.0 → 4.0).
- A new P0 is added (minor bump: 3.0 → 3.1).
- A fix is marked Done with PR link (patch bump: 3.0 → 3.0.1).

### When to revisit

- Quarterly architecture review.
- After any P0 incident — incidents that aren't covered by an existing fix become new fixes.
- Before adopting Carson in a new team — confirm Phase 1-4 is complete in their target environment.

---

# Final notes for Copilot

- **If a fix references a file that doesn't exist at the path given**: the repo has changed since this document. Stop and confirm the new path with a human.
- **If a fix references code that doesn't match the "current" example**: either the fix was partially applied or someone made an unrelated change. Inspect with `git log -p <file>` and ask.
- **For P0 fixes, write a short post-fix summary in the commit body** explaining what was done and why. These are load-bearing changes; future debuggers will thank you.
- **Do not bundle multiple fixes in one PR** unless they are explicitly co-dependent (e.g. FIX #18 and FIX #21 — both about MCP packaging — can be one PR; FIX #0.2 and FIX #0.5 cannot).
- **For Cloud fixes, work in the IaC repo (`infra/`)** with PR review by the platform/infra team. Do not apply Terraform manually outside CI.
- **Update this document** when a fix is completed: mark with date and PR link. When new findings emerge, add as `FIX #38`, `#39`, etc., and bump version.

---

# Appendix: Athena RAG Blueprint Integration

This audit document covers Carson's **infrastructure, config, and cloud readiness**. There is a companion document — `CARSON_ATHENA_RAG_BLUEPRINT.md` — that covers the **retrieval architecture** specifically for the Athena credit risk monorepo. The two documents are complementary:

| Concern | This document (`AUDIT_FIXES`) | Athena Blueprint |
|---------|-------------------------------|------------------|
| Agent orchestration | Fixes #0.1–#0.4 (routing, orchestration consolidation) | Wave 5 (routing), Wave 6 (behavior) |
| RAG quality | FIX #10 (max_rag_context_tokens), FIX #11 (operation_model collection) | Sections 1.2–1.7 (AST chunking, multi-view embeddings, history chain, LLM enrichment) |
| Tool discovery | Not covered | Section 1.8 (dynamic tool registry for Bob job) |
| ChromaDB persistence | FIX #15 (S3 backup) | Wave A1 (collection fixes from audit) |
| Dashboard tracing | Tier 4 FIX #16 (routing logging) + Cloud observability stack | Blueprint section 1.4 feeds into dashboard Trace view |
| SDLC commit flow | Not covered | Section 4.1 (Refactor #15, state machine + retry budget) |
| Cross-repo analysis | Not covered | Section 1.5 (JIRA ticket chain → multi-repo impact) |
| Execution safety | Not covered | Section 3 (wave-based execution with smoke tests, git tags, stop conditions) |

### Key architectural update

Carson has evolved from the LangGraph-only setup described in earlier tiers of this document:

- **Framework**: Now Strands Agents + LangGraph (not LangGraph-only)
- **Agent naming**: Capability names (`git agent`, `build agent`) — no more human names
- **Agent count**: 14+ specialized (down from 20+, consolidated)
- **Dashboard**: 130KB monolith with cost/replay/autonomy/audit/multi-chat/PM/agent-rooms views
- **Storage**: Multiple SQLite stores (ops, audit, autonomous, chats, agent_rooms, pm)
- **Guardrails**: 8 explicit behavioral invariants in `AGENT_BEHAVIOR_GUARDRAILS.md`

The Tier 1-4 fixes in this document remain valid for the `high-touch-agent-prompts` LangGraph layer. The Athena Blueprint adds the retrieval and autonomous coder improvements on top.

End of document.
