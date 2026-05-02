# Phase 4 · LangGraph residue findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

---

## LangGraph reference inventory

| file | langgraph imports | StateGraph nodes | conditional edges | step guards |
|------|-------------------|------------------|-------------------|-------------|
|      |                   |                  |                   |             |

---

## Hybrid surfaces

| file | strands surface | langgraph surface | recommendation |
|------|-----------------|-------------------|----------------|
|      |                 |                   | remove / adapt / rewrite |

---

## Orchestrator inventory

If multiple orchestrators exist (the pre-strands sin), list each:

| name | location | scope | dependencies | recommended fate |
|------|----------|-------|--------------|------------------|
|      |          |       |              | keep / merge / delete |

---

## State schema divergence

If `Agent.state` (strands) and `StateGraph` typed dict (langgraph)
both exist, document differences:

| field | strands type | langgraph type | divergence | impact |
|-------|--------------|----------------|------------|--------|
|       |              |                |            |        |

---

## Findings

### Finding L-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 4-langgraph
- **Location**: `<file>:<line>`
- **Category**: dual_orchestrators | state_schema_drift | orphaned_field | step_counter_guard | deferred_consolidation | other
- **Evidence**:
- **Why it's a problem**:
- **Proposed fix**:
- **Estimated fix time**:
- **Verification**:
- **Owner**:

---

## Phase summary

- Total findings: <N>
- By severity: P0 <a> · P1 <b> · P2 <c> · P3 <d>
- Recommendation: keep langgraph in <files> · phase out langgraph in <files>
