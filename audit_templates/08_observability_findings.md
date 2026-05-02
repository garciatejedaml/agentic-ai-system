# Phase 7 · Observability findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

---

## Logging coverage

| area | logger? | structured? | level appropriate? | print()? |
|------|--------:|------------:|-------------------:|---------:|
| agents/      |  |  |  |  |
| langgraph-system/ |  |  |  |  |
| mcp-servers/ |  |  |  |  |
| carson_dashboard/ |  |  |  |  |
| scripts/     |  |  |  |  |

---

## Telemetry destinations

| signal | source | destination | retention |
|--------|--------|-------------|-----------|
| token usage |  |  |  |
| latency per agent |  |  |  |
| router decisions |  |  |  |
| HITL pauses |  |  |  |
| errors |  |  |  |

---

## Correlation IDs

- Is there a correlation/trace id propagated per user request? <yes/no>
- If yes, where is it generated? `<file>:<line>`
- Is it captured in logs? <yes/no>
- Is it visible in the dashboard's run detail / replay? <yes/no>

---

## Findings

### Finding O-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 7-observability
- **Location**: `<file>:<line>`
- **Category**: print_in_prod | metrics_in_memory_only | no_correlation_id | router_decision_unlogged | hitl_untracked | error_no_stack | other
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
- Most urgent: <id> — what would the on-call engineer need that's missing today
