# Phase 9 · Testing findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

---

## Test inventory

| test type | count | location | status |
|-----------|------:|----------|--------|
| unit                |  | tests/unit/ |  |
| integration         |  | tests/integration/ |  |
| e2e                 |  | tests/e2e/ |  |
| MCP-server-specific |  | mcp-servers/*/tests/ |  |

---

## Coverage by area

| area | files | tested files | coverage % |
|------|------:|-------------:|-----------:|
| agents/             |  |  |  |
| langgraph-system/   |  |  |  |
| mcp-servers/        |  |  |  |
| carson_dashboard/   |  |  |  |

---

## Critical paths covered?

- [ ] HITL approve → state transition
- [ ] HITL reject → state transition
- [ ] Deterministic-mode branch
- [ ] Non-deterministic (reactive) branch
- [ ] Router classification (heuristic backend)
- [ ] Router classification (haiku backend, when enabled)
- [ ] MCP timeout / retry path
- [ ] Audit log write on each event_type
- [ ] Agent prompt cache hit
- [ ] Multi-session chat isolation

---

## Findings

### Finding T-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 9-testing
- **Location**: `<file>:<line>` or `<area> (gap)`
- **Category**: missing_path_coverage | only_mocks_no_integration | obsolete_after_strands | flaky | other
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
- Untested critical path with highest demo risk: <one-line>
