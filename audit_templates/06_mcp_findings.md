# Phase 5 · MCP server findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

---

## MCP server inventory

| server | package | version pin | entry point | tool count |
|--------|---------|-------------|-------------|-----------:|
|        |         |             |             |            |

---

## Auth + scoping

| server | auth method | scopes | min-perms? |
|--------|-------------|--------|-----------:|
|        |             |        |  yes / no  |

---

## Reliability config

| server | timeout | retry policy | circuit breaker | idempotent? |
|--------|---------|--------------|-----------------|-------------|
|        |         |              |                 |             |

---

## Tool name collisions

If two MCP servers expose the same tool name:

| tool name | server A | server B | resolution |
|-----------|----------|----------|------------|
|           |          |          |            |

---

## Schema drift

If a strands `@tool` wrapper around an MCP call has different types
than the underlying MCP schema:

| tool | strands wrapper signature | mcp schema | drift |
|------|---------------------------|------------|-------|
|      |                           |            |       |

---

## Findings

### Finding M-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 5-mcp
- **Location**: `mcp-servers/<server>/<file>:<line>`
- **Category**: name_collision | no_timeout | broad_scope | no_retry | schema_drift | hardcoded_url | unpinned_version | other
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
- Servers needing immediate attention:
- Servers in good shape (use as reference):
