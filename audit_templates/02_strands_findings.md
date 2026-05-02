# Phase 1 · Strands migration findings

**Audit run**: <YYYY-MM-DD HH:MM>
**Status**: complete / partial / failed

If partial or failed, reason: <one-line>

---

## Migration matrix

For each agent file in `agents/` (and any agent-style file in
`langgraph-system/`), categorize:

| file | strands-native | hybrid | legacy | unknown | notes |
|------|---------------:|-------:|-------:|--------:|-------|
|      |                |        |        |         |       |

`strands-native` = uses `Agent(...)` and `@tool`, no legacy base class.
`hybrid` = both patterns present.
`legacy` = only the legacy base class, no strands references.
`unknown` = neither pattern matches — manual triage required.

---

## Provider config matrix

For every agent that calls `Agent(model=..., provider=...)` or
equivalent, capture the resolved model id and provider:

| agent | provider | model id | region | rationale |
|-------|----------|----------|--------|-----------|
|       |          |          |        |           |

Look for inconsistencies: different agents on different model
families without a documented reason.

---

## System prompt sanity

For each agent, eyeball the system prompt:

| agent | prompt loc | length (lines) | empty? | hardcoded paths? | dated examples? |
|-------|-----------|----------------|--------|-------------------|----------------|
|       |           |                |        |                   |                |

---

## Tool surface

For each agent, list its `@tool`-decorated functions:

| agent | tool count | tool names |
|-------|-----------:|------------|
|       |            |            |

Flag any tool count of 0 (just a prompt, should be a function) or > 15
(overscoped, likely needs split).

---

## Findings

### Finding S-01: <title>
- **Severity**: P0 / P1 / P2 / P3
- **Phase**: 1-strands
- **Location**: `<file>:<line>`
- **Category**: mixed_paradigms | missing_tool_decorator | hardcoded_model | prompt_empty | provider_drift | other
- **Evidence**:
  ```python
  <code excerpt>
  ```
- **Why it's a problem**: <one paragraph>
- **Proposed fix**:
  ```python
  <code excerpt>
  ```
- **Estimated fix time**: <X min/h>
- **Verification**: <one-line command>
- **Owner**: <agent name or "platform">

(Repeat for each finding S-02, S-03, ...)

---

## Phase summary

- Total findings: <N>
- By severity: P0 <a> · P1 <b> · P2 <c> · P3 <d>
- Most-affected files (top 5):
  1.
  2.
  3.
- Inconsistencies that suggest mid-migration state:
- Recommended cluster for first fix PR:
